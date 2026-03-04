"""
Dual Scoring Engine: Obtainability + Desirability
==================================================
Obtainability = "Can she actually get this job?" (qualifications + location)
Desirability  = "Is it a good job?" (salary, company, benefits, security)
Composite     = weighted blend, gated by obtainability

Key insight: there's no point considering how great a job is if she can't get it.
Required qualifications and location are foundational. Everything else is secondary.
"""
import json
import re
from typing import Dict, Optional, Tuple, List
from pathlib import Path

from storage.models import Job, Company
from storage import database as db
import config


def score_job(job: Job, company: Optional[Company] = None) -> Dict:
    """
    Score a single job using dual-score architecture.
    Returns dict with all sub-scores, obtainability, desirability, and composite.
    """
    # Look up company data if not provided
    if company is None and job.company:
        company = db.get_company(job.company)

    # ── 1. Run gap analysis on EVERY job ──────────────────────────────
    from matching.gap_analysis import (
        analyze_gaps, compute_qualification_score, format_gap_analysis,
    )
    gap_result = analyze_gaps(job.title, job.description)
    qualification_score = compute_qualification_score(gap_result)

    # ── 2. Compute all sub-scores ─────────────────────────────────────
    location_score = _score_location(job)
    semantic_score = _compute_semantic_only(job)
    interview_prob = _score_interview_probability(job)

    compensation = _score_compensation(job, company)
    job_security = _score_job_security(job, company)
    company_quality = _score_company_quality(company)
    benefits = _score_benefits(job)
    interview_speed = _score_interview_speed(job)

    # Keep resume_fit for backward compat in detail view
    resume_fit = _score_resume_fit(job)

    # ── 3. Obtainability ──────────────────────────────────────────────
    w = config.OBTAINABILITY_WEIGHTS
    obtainability = (
        qualification_score * w["qualifications"] +
        location_score * w["location"] +
        semantic_score * w["semantic_fit"] +
        interview_prob * w["interview_probability"]
    )

    # Distant non-remote penalty
    salary = job.salary_midpoint or job.estimated_salary
    if location_score == 0 and (not salary or salary < config.RELOCATION_SALARY_THRESHOLD):
        obtainability *= config.DISTANT_NONREMOTE_TOTAL_PENALTY

    obtainability = round(min(100, max(0, obtainability)), 1)

    # ── 4. Desirability ───────────────────────────────────────────────
    d = config.DESIRABILITY_WEIGHTS
    desirability = (
        compensation * d["compensation"] +
        job_security * d["job_security"] +
        company_quality * d["company_quality"] +
        benefits * d["benefits"] +
        interview_speed * d["interview_speed"]
    )

    # WFH flexibility bonus
    if _has_wfh_flexibility(job):
        desirability = min(100, desirability + config.WFH_FLEXIBILITY_BONUS)

    desirability = round(min(100, max(0, desirability)), 1)

    # ── 5. Composite ──────────────────────────────────────────────────
    composite = (
        obtainability * config.COMPOSITE_OBTAINABILITY_WEIGHT +
        desirability * config.COMPOSITE_DESIRABILITY_WEIGHT
    )
    # Progressive penalty when obtainability is low
    if obtainability < config.COMPOSITE_GATING_THRESHOLD:
        composite *= (obtainability / config.COMPOSITE_GATING_THRESHOLD)

    composite = round(min(100, max(0, composite)), 1)

    # ── 6. Stretch detection (gap-analysis-driven) ────────────────────
    # Only CLEARLY required gaps trigger stretch — "unknown" context
    # means we can't be sure (skill was just mentioned, not required)
    is_stretch = gap_result.get("is_stretch", False)
    stretch_severity = gap_result.get("stretch_severity", "")
    gap_text = format_gap_analysis(gap_result) if is_stretch else ""

    # ── 7. Tier determination ─────────────────────────────────────────
    if composite >= config.TIER_DREAM_JOB:
        tier = "DREAM_JOB"
    elif composite >= config.TIER_STRONG_MATCH:
        tier = "STRONG_MATCH"
    elif composite >= config.TIER_WORTH_CONSIDERING:
        tier = "WORTH_CONSIDERING"
    else:
        tier = "BELOW_THRESHOLD"

    return {
        # Dual scores
        "score_obtainability": obtainability,
        "score_desirability": desirability,
        "score_qualifications": qualification_score,
        "score_total": composite,

        # Sub-scores (for detail view)
        "score_resume_fit": resume_fit,
        "score_resume_fit_raw": resume_fit,  # no separate penalty now
        "score_job_security": job_security,
        "score_compensation": compensation,
        "score_company_quality": company_quality,
        "score_benefits": benefits,
        "score_location": location_score,
        "score_interview_prob": interview_prob,
        "score_interview_speed": interview_speed,

        # Tier & stretch
        "tier": tier,
        "is_stretch": is_stretch,
        "stretch_severity": stretch_severity,
        "stretch_gap_analysis": gap_text,
    }


def _has_wfh_flexibility(job: Job) -> bool:
    """Check if job offers WFH/hybrid/flexible work options."""
    if job.is_remote or job.is_hybrid:
        return True
    desc_lower = (job.description or "").lower()
    loc_lower = (job.location or "").lower()
    remote_lower = (job.remote_text or "").lower()
    combined = desc_lower + " " + loc_lower + " " + remote_lower
    wfh_signals = [
        "work from home", "remote option", "hybrid", "flexible schedule",
        "flexible work", "remote days", "wfh", "telecommute",
        "remote-friendly", "partially remote",
    ]
    return any(signal in combined for signal in wfh_signals)


def _compute_semantic_only(job: Job) -> float:
    """Get just the semantic similarity score (factored out of resume_fit)."""
    from matching.semantic import compute_semantic_similarity
    desc = f"{job.title} {job.description}"
    return compute_semantic_similarity(desc)


def score_all_unscored():
    """Score all unscored jobs in the database."""
    from rich.progress import Progress
    from rich.console import Console

    console = Console()
    unscored = db.get_unscored_jobs()

    if not unscored:
        console.print("[dim]No unscored jobs found.[/dim]")
        return

    console.print(f"[bold]Scoring {len(unscored)} jobs...[/bold]")

    with Progress() as progress:
        task = progress.add_task("Scoring", total=len(unscored))

        for job in unscored:
            scores = score_job(job)

            # Skip jobs below minimum salary
            if scores.get("score_compensation") == 0:
                db.update_job_scores(job.id, {
                    "score_total": 0,
                    "tier": "EXCLUDED",
                })
                progress.advance(task)
                continue

            db.update_job_scores(job.id, scores)
            progress.advance(task)


def _score_resume_fit(job: Job) -> float:
    """
    Resume fit: 60% semantic + 25% skill match + 15% experience match.
    Kept for backward compat in detail view. Not used in composite anymore.
    """
    from matching.semantic import compute_semantic_similarity
    from matching.keyword import (
        compute_skill_match_score, compute_experience_match
    )

    desc = f"{job.title} {job.description}"

    semantic_score = compute_semantic_similarity(desc)
    skill_score, _ = compute_skill_match_score(job.description)
    experience_score = compute_experience_match(
        job.description, job.years_required
    )

    combined = (semantic_score * 0.60) + (skill_score * 0.25) + (experience_score * 0.15)
    return round(min(100, combined), 1)


def _score_job_security(job: Job, company: Optional[Company]) -> float:
    """Job security: company stability + industry outlook + role essentiality."""
    industry_data = _load_json("industry_stability.json")
    industry_scores = industry_data.get("industry_scores", {})
    role_scores = industry_data.get("role_essentiality", {})

    score_components = []

    if company:
        company_score = 50
        if company.is_fortune_500:
            company_score = 82
        elif company.is_fortune_1000:
            company_score = 75
        elif company.size_employees and company.size_employees > 5000:
            company_score = 70
        elif company.size_employees and company.size_employees > 1000:
            company_score = 60

        if company.is_public:
            company_score += 5
        if company.recent_layoffs:
            company_score -= 15
        if company.growth_signals:
            company_score += 8

        score_components.append(("company", company_score, 0.40))
        ind_score = industry_scores.get(company.industry, 65)
        score_components.append(("industry", ind_score, 0.30))
    else:
        desc_lower = (job.description or "").lower()
        if any(w in desc_lower for w in ["fortune 500", "fortune 1000", "enterprise"]):
            score_components.append(("company_estimate", 75, 0.40))
        else:
            score_components.append(("company_estimate", 55, 0.40))
        score_components.append(("industry_default", 65, 0.30))

    title_lower = job.title.lower()
    best_role_score = 65
    for role_type, r_score in role_scores.items():
        if role_type in title_lower:
            best_role_score = max(best_role_score, r_score)
    score_components.append(("role", best_role_score, 0.30))

    total = sum(score * weight for _, score, weight in score_components)
    return round(min(100, max(0, total)), 1)


def _score_compensation(job: Job, company: Optional[Company]) -> float:
    """Compensation score. Below $100K = 0 (excluded)."""
    salary = job.salary_midpoint

    if salary is None:
        salary = _estimate_salary(job.title, company)
        if salary:
            job.estimated_salary = salary
        else:
            return 55  # Unknown salary — neutral

    if salary < config.MIN_SALARY:
        return 0  # EXCLUDED

    for low, high, score in config.SALARY_TIERS:
        if low <= salary < high:
            return score

    return 100


def _estimate_salary(title: str, company: Optional[Company]) -> Optional[float]:
    """Estimate salary from title and company data."""
    benchmarks = _load_json("salary_benchmarks.json")
    title_data = benchmarks.get("title_benchmarks", {})
    size_mult = benchmarks.get("company_size_multipliers", {})
    industry_mult = benchmarks.get("industry_multipliers", {})

    best_match = None
    title_lower = title.lower()
    for bench_title, data in title_data.items():
        if bench_title.lower() in title_lower or title_lower in bench_title.lower():
            best_match = data
            break

    if best_match is None:
        from difflib import SequenceMatcher
        best_sim = 0
        for bench_title, data in title_data.items():
            sim = SequenceMatcher(None, title_lower, bench_title.lower()).ratio()
            if sim > best_sim:
                best_sim = sim
                best_match = data
        if best_sim < 0.4:
            return None

    if best_match is None:
        return None

    base_salary = best_match.get("p50", 110000)

    multiplier = 1.0
    if company:
        if company.is_fortune_500:
            multiplier *= size_mult.get("fortune_500", 1.15)
        elif company.is_fortune_1000:
            multiplier *= size_mult.get("fortune_1000", 1.10)
        elif company.size_employees and company.size_employees > 5000:
            multiplier *= size_mult.get("large_5000_plus", 1.05)

        for ind_key, ind_m in industry_mult.items():
            if company.industry and ind_key.lower() in company.industry.lower():
                multiplier *= ind_m
                break

    return base_salary * multiplier


def _score_company_quality(company: Optional[Company]) -> float:
    """Company quality score from ratings and awards."""
    if company is None:
        return 55

    score = 50
    if company.glassdoor_rating:
        rating = company.glassdoor_rating
        if rating < 3.0:
            score = 25
        elif rating < 3.3:
            score = 40
        elif rating < 3.5:
            score = 52
        elif rating < 3.8:
            score = 65
        elif rating < 4.0:
            score = 75
        elif rating < 4.3:
            score = 85
        else:
            score = 95

    if company.best_places_to_work:
        score = min(100, score + 8)
    if company.ceo_approval and company.ceo_approval > 70:
        score = min(100, score + 3)
    if company.recommend_to_friend and company.recommend_to_friend > 60:
        score = min(100, score + 3)

    return round(min(100, score), 1)


def _score_benefits(job: Job) -> float:
    """Score benefits from job description keywords."""
    if not job.description:
        return 50

    text_lower = job.description.lower()
    points = 0

    benefit_keywords = {
        "health insurance": 15, "medical": 10, "dental": 8, "vision": 5,
        "health benefits": 12, "wellness program": 5,
        "401k": 15, "401(k)": 15, "retirement": 10, "pension": 15,
        "employer match": 12, "company match": 12,
        "pto": 10, "paid time off": 10, "vacation": 8,
        "unlimited pto": 15, "flexible time off": 12,
        "paid holidays": 5, "sick leave": 5,
        "parental leave": 10, "maternity": 8, "paternity": 8,
        "family leave": 8, "childcare": 8,
        "tuition reimbursement": 10, "tuition assistance": 10,
        "professional development": 8, "education assistance": 8,
        "learning and development": 5,
        "stock options": 10, "equity": 8, "rsu": 10, "espp": 8,
        "bonus": 8, "annual bonus": 10, "performance bonus": 8,
        "life insurance": 5, "disability": 5,
        "gym": 3, "fitness": 3,
        "remote work": 5, "work from home": 5, "flexible schedule": 5,
        "competitive benefits": 8, "comprehensive benefits": 10,
        "benefits package": 5,
    }

    for keyword, pts in benefit_keywords.items():
        if keyword in text_lower:
            points += pts

    return round(min(100, (points / 80) * 100), 1)


def _score_location(job: Job) -> float:
    """
    Score based on distance from Cornelius and remote/hybrid work.
    Charlotte area and remote are both top-tier (100).
    """
    # Check remote first
    if job.is_remote:
        return 100.0

    location_lower = (job.location or "").lower()
    remote_text = (job.remote_text or "").lower()
    desc_lower = (job.description or "").lower()

    # Check for remote/hybrid signals
    if any(w in location_lower for w in ["remote", "work from home", "anywhere"]):
        return 100.0
    if any(w in remote_text for w in ["remote", "work from home"]):
        return 100.0

    # "United States" — only score high if description confirms remote
    if location_lower.strip() in ["united states", "united states of america", "usa"]:
        if any(w in desc_lower for w in ["remote", "work from home", "fully remote",
                                          "remote-first", "distributed team",
                                          "work from anywhere", "telecommute"]):
            return 100.0
        return 60.0  # Ambiguous — might be any US city, not necessarily local

    if job.is_hybrid:
        return 100.0
    if any(w in location_lower for w in ["hybrid"]):
        return 100.0
    if any(w in remote_text for w in ["hybrid"]):
        return 100.0

    # Check description for remote/hybrid
    if "remote" in desc_lower and ("option" in desc_lower or "available" in desc_lower
                                    or "flexible" in desc_lower):
        return 100.0

    # Distance-based scoring for onsite roles
    score = _score_by_city(location_lower)

    # Check if high salary makes relocation viable
    salary = job.salary_midpoint or job.estimated_salary
    if score == 0 and salary and salary >= config.RELOCATION_SALARY_THRESHOLD:
        return 50.0  # Relocation-eligible

    return score


def _score_by_city(location: str) -> float:
    """
    Score based on city name.
    Charlotte area = home = 100.
    """
    # Immediate area + greater Charlotte (all 100 — it's home)
    home_cities = [
        "cornelius", "davidson", "huntersville", "lake norman",
        "mooresville", "charlotte", "concord", "kannapolis",
        "statesville", "denver nc",
    ]
    for city in home_cities:
        if city in location:
            return 100.0

    # SC border / southern suburbs — easy commute
    close_suburbs = [
        "fort mill", "rock hill", "indian trail", "matthews",
        "mint hill", "pineville", "ballantyne", "university city",
    ]
    for city in close_suburbs:
        if city in location:
            return 90.0

    # Longer commute but doable
    commute_cities = [
        "gastonia", "salisbury", "lincolnton", "sherrills ford",
        "troutman",
    ]
    for city in commute_cities:
        if city in location:
            return 70.0

    # Edge of range
    edge_cities = [
        "hickory", "albemarle", "monroe", "york sc",
        "lancaster sc", "clover sc",
    ]
    for city in edge_cities:
        if city in location:
            return 50.0

    # NC/SC in general — might be in range
    if "nc" in location or "north carolina" in location:
        return 50.0
    if "sc" in location or "south carolina" in location:
        return 50.0

    # Unknown or distant — not feasible without relocation
    return 0.0


def _score_interview_probability(job: Job) -> float:
    """How likely she is to get an interview."""
    from matching.keyword import (
        compute_skill_match_score, compute_experience_match,
        compute_education_match, compute_certification_match
    )

    skill_score, details = compute_skill_match_score(job.description)
    exp_score = compute_experience_match(job.description, job.years_required)
    edu_score = compute_education_match(job.description)
    cert_score = compute_certification_match(job.description)

    score = (
        skill_score * 0.35 +
        exp_score * 0.30 +
        edu_score * 0.20 +
        cert_score * 0.15
    )

    return round(min(100, score), 1)


def _score_interview_speed(job: Job) -> float:
    """How fast the interview process is likely to be."""
    score = 50

    if job.easy_apply:
        score += 20

    posted = (job.posted_date or "").lower()
    if any(w in posted for w in ["today", "just posted", "1 day", "just now"]):
        score += 25
    elif any(w in posted for w in ["2 day", "3 day", "yesterday"]):
        score += 20
    elif any(w in posted for w in ["4 day", "5 day", "6 day", "1 week", "7 day"]):
        score += 10
    elif any(w in posted for w in ["2 week", "14 day"]):
        score += 0
    else:
        score -= 5

    desc_lower = (job.description or "").lower()
    urgency_keywords = ["immediately", "asap", "urgent", "start date",
                        "immediate opening", "backfill", "quick hire"]
    for keyword in urgency_keywords:
        if keyword in desc_lower:
            score += 8
            break

    return round(min(100, max(0, score)), 1)


# ── Utility ────────────────────────────────────────────────────────────────

_json_cache = {}

def _load_json(filename: str) -> dict:
    """Load and cache a JSON data file."""
    if filename not in _json_cache:
        path = config.DATA_DIR / filename
        if path.exists():
            with open(path) as f:
                _json_cache[filename] = json.load(f)
        else:
            _json_cache[filename] = {}
    return _json_cache[filename]
