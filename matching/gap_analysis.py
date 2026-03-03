"""
Gap Analysis — Qualification Matching for All Jobs
Identifies what Cynthia is missing for a role, classifies required vs preferred,
and computes a qualification score that drives the Obtainability rating.
Uses weighted scoring: Masters > exec experience > skill > cert > implicit skill.
"""
import re
from typing import List, Dict, Tuple
from profile import (
    HARD_SKILLS, COMPETENCY_KEYWORDS, YEARS_EXPERIENCE,
    HAS_BACHELORS, HAS_MBA, HAS_PMP, HAS_CHANGE_MGMT_CERT,
    KEY_ACHIEVEMENTS, IMPLICIT_SKILLS, DIRECT_REPORTS_MAX,
    STRETCH_TEAM_SIZE_THRESHOLD, STRETCH_TITLE_KEYWORDS,
)
from matching.keyword import (
    extract_years_required, extract_education_required
)

# ── Gap Weights ───────────────────────────────────────────────────────────
WEIGHT_REQUIRED = 1.0
WEIGHT_PREFERRED = 0.3

WEIGHT_MASTERS_DEGREE = 0.8
WEIGHT_CERTIFICATION = 0.4
WEIGHT_SKILL_GAP = 0.6         # A real skill she doesn't have
WEIGHT_IMPLICIT_SKILL = 0.1    # A skill she certainly has but didn't list
WEIGHT_SENIORITY = 0.8         # Title-level above her experience

# Skills she doesn't have (distinct from IMPLICIT_SKILLS which she does have)
SKILLS_SHE_LACKS = [
    "tableau", "power bi", "python", "sql", "r programming",
    "aws", "azure", "gcp", "cloud",
    "scrum master", "safe", "scaled agile",
    "six sigma", "lean six sigma", "black belt", "green belt",
    "devops", "ci/cd", "kubernetes", "docker",
    "data science", "machine learning", "ai",
    "figma", "sketch", "ux design",
    "servicenow", "confluence",
    "prince2", "itil",
    "cpa", "cfa",
    "erp implementation",
    "oracle", "netsuite",
    "hubspot", "marketo",
    "product analytics", "amplitude", "mixpanel",
]

# Certification-type skills (weight differently from regular skills)
CERT_SKILLS = {
    "six sigma", "lean six sigma", "black belt", "green belt",
    "scrum master", "safe", "prince2", "itil", "cpa", "cfa",
}


def analyze_gaps(job_title: str, job_description: str) -> Dict:
    """
    Perform weighted gap analysis for a job listing.
    Each gap is a dict with text, weight, category, and context.
    Runs on ALL jobs (not just stretches) to drive the obtainability score.
    """
    text_lower = (job_description or "").lower()
    full_text = job_description or ""
    title_lower = (job_title or "").lower()

    gaps = []
    strengths = []
    cover_letter_angles = []

    # ── Title-Level Seniority Gap ─────────────────────────────────────
    for keyword in STRETCH_TITLE_KEYWORDS:
        if keyword in title_lower:
            gaps.append({
                "text": f"Title level '{keyword.strip()}' is above her experience",
                "weight": WEIGHT_SENIORITY,
                "category": "seniority",
                "context": "required",
            })
            cover_letter_angles.append(
                "Emphasize enterprise-scale accountability: $20M event budgets, "
                "750+ user PLM implementation, global vendor coordination. "
                "Frame as director-level impact without the title."
            )
            break  # Only flag once even if multiple keywords match

    # ── Experience Gap (scaled by severity) ───────────────────────────
    years_req = extract_years_required(full_text)
    if years_req and years_req > YEARS_EXPERIENCE:
        gap_years = years_req - YEARS_EXPERIENCE
        # Scale weight by how big the gap is
        if gap_years <= 2:
            exp_weight = 0.3    # minor — within reach
        elif gap_years <= 5:
            exp_weight = 0.6    # moderate
        else:
            exp_weight = 1.0    # significant — can't fix quickly

        context = _classify_requirement_context(full_text, f"{years_req}")
        if context == "preferred":
            exp_weight *= WEIGHT_PREFERRED

        gaps.append({
            "text": f"Requires {years_req}+ years (she has {YEARS_EXPERIENCE}, gap: {gap_years} yrs)",
            "weight": exp_weight,
            "category": "experience",
            "context": context,
        })
        cover_letter_angles.append(
            f"Frame her {YEARS_EXPERIENCE} years as highly concentrated, "
            f"high-impact experience. PLM recovery and $20M event management "
            f"demonstrate senior-level accountability beyond her years."
        )
    elif years_req and years_req <= YEARS_EXPERIENCE:
        strengths.append(f"Meets {years_req}+ years requirement with {YEARS_EXPERIENCE} years")

    # ── Education Gap ──────────────────────────────────────────────────
    ed_req = extract_education_required(full_text)
    if ed_req == "Masters" and not HAS_MBA:
        context = _classify_requirement_context(full_text, "master")
        base_weight = WEIGHT_MASTERS_DEGREE
        if context == "preferred":
            base_weight *= WEIGHT_PREFERRED
        gaps.append({
            "text": f"MBA/Master's degree {'preferred' if context == 'preferred' else 'required'}",
            "weight": base_weight,
            "category": "education",
            "context": context,
        })
        cover_letter_angles.append(
            "Highlight PMP, Change Management, and Business Analytics certificates "
            "as equivalent professional development. "
            "Emphasize hands-on enterprise transformation experience."
        )
    elif ed_req in ("Bachelors", "Not specified"):
        strengths.append("Meets education requirements")

    # ── Missing Hard Skills (real gaps) ───────────────────────────────
    for skill in SKILLS_SHE_LACKS:
        if skill in text_lower:
            context = _classify_requirement_context(full_text, skill)
            if skill in CERT_SKILLS:
                base_weight = WEIGHT_CERTIFICATION
            else:
                base_weight = WEIGHT_SKILL_GAP
            if context == "preferred":
                base_weight *= WEIGHT_PREFERRED
            gaps.append({
                "text": f"Skill not on resume: {skill}",
                "weight": base_weight,
                "category": "skill",
                "context": context,
            })
            angle = _suggest_skill_angle(skill)
            if angle:
                cover_letter_angles.append(angle)

    # ── Implicit Skills (she almost certainly has these) ──────────────
    for skill in IMPLICIT_SKILLS:
        if skill in text_lower:
            # Skip if already covered by her listed hard skills
            if any(skill.lower() in hs.lower() or hs.lower() in skill.lower()
                   for hs in HARD_SKILLS):
                continue
            # Skip very generic terms that appear in almost every posting
            if skill in ("communication", "team player", "teamwork",
                         "organized", "detail-oriented"):
                continue
            gaps.append({
                "text": f"Likely has (unlisted): {skill}",
                "weight": WEIGHT_IMPLICIT_SKILL,
                "category": "implicit",
                "context": "trivial",
            })

    # ── Industry Experience ────────────────────────────────────────────
    industry_gaps = _find_industry_gaps(text_lower)
    for industry in industry_gaps:
        context = _classify_requirement_context(full_text, industry)
        weight = 0.5 if context != "preferred" else 0.15
        gaps.append({
            "text": f"May prefer {industry} industry experience",
            "weight": weight,
            "category": "industry",
            "context": context,
        })
        cover_letter_angles.append(
            f"Position Maersk global logistics and Lowe's enterprise retail as "
            f"transferable to {industry}. Emphasize cross-industry adaptability."
        )

    # ── Management Scope Gap ──────────────────────────────────────────
    team_size = _extract_team_size(text_lower)
    if team_size and team_size > STRETCH_TEAM_SIZE_THRESHOLD:
        gaps.append({
            "text": f"Requires managing {team_size}+ people (her max: {DIRECT_REPORTS_MAX})",
            "weight": 0.7,
            "category": "management",
            "context": "required",
        })
        cover_letter_angles.append(
            "Frame influence scope beyond direct reports: managed 200+ vendors, "
            "750+ system users, 30 merchant stakeholder reviews weekly, and "
            "4,000-person events. Leadership isn't just headcount."
        )

    # ── Strengths ──────────────────────────────────────────────────────
    matched_skills = [s for s in HARD_SKILLS if s.lower() in text_lower]
    if matched_skills:
        strengths.append(f"Hard skill matches: {', '.join(matched_skills)}")

    matched_competencies = [c for c in COMPETENCY_KEYWORDS if c.lower() in text_lower]
    if matched_competencies:
        strengths.append(f"Competency matches: {', '.join(matched_competencies[:5])}")

    for achievement in KEY_ACHIEVEMENTS:
        for tag in achievement['tags']:
            if tag.lower() in text_lower:
                strengths.append(f"Relevant achievement: {achievement['text'][:80]}...")
                break

    # ── Weighted Score + Stretch Severity ─────────────────────────────
    total_weighted_gaps = sum(g["weight"] for g in gaps)
    significant_gaps = [g for g in gaps if g["weight"] >= 0.3]

    # Only CLEARLY required gaps trigger stretch (not "unknown" context
    # which often means the skill was just mentioned, not truly required)
    required_gaps = [g for g in gaps
                     if g["context"] == "required"
                     and g["weight"] >= 0.3
                     and g["category"] not in ("implicit", "industry")]

    # "Unknown" context gaps are ambiguous — could be required or just mentioned.
    # We'll include them in the qualification penalty at reduced weight,
    # but they don't trigger stretch by themselves.
    unknown_gaps = [g for g in gaps
                    if g["context"] == "unknown"
                    and g["weight"] >= 0.3
                    and g["category"] not in ("implicit", "industry")]

    total_items = len(significant_gaps) + len(strengths)
    if total_items > 0:
        met_pct = len(strengths) / total_items * 100
    else:
        met_pct = 70  # Default

    # Required gap weight (for reporting)
    required_weight = sum(g["weight"] for g in required_gaps)

    # Stretch severity — only truly required gaps drive stretch classification
    stretch_weight = required_weight
    if stretch_weight < 0.5:
        stretch_severity = ""
    elif stretch_weight < 1.2:
        stretch_severity = "Minor Stretch"
    elif stretch_weight < 2.5:
        stretch_severity = "Moderate Stretch"
    elif stretch_weight < 4.0:
        stretch_severity = "Significant Stretch"
    else:
        stretch_severity = "Reach"

    return {
        "gaps": gaps,
        "strengths": strengths,
        "cover_letter_angles": cover_letter_angles[:5],
        "requirements_met_pct": met_pct,
        "weighted_gap_score": total_weighted_gaps,
        "required_gap_weight": required_weight,
        "is_stretch": len(required_gaps) > 0,
        "stretch_severity": stretch_severity,
        "risk_level": _assess_risk_weighted(gaps, strengths),
    }


def compute_qualification_score(gap_result: dict) -> float:
    """
    Convert gap analysis into a 0-100 qualification score.
    This drives the 'qualifications' component of obtainability.
    Higher score = fewer/lighter gaps = more qualified.

    Context weighting:
    - "required" gaps:  full penalty (weight × 25 pts)
    - "preferred" gaps: already have reduced weight from analyze_gaps
    - "unknown" gaps:   halved penalty (many are casual mentions, not real requirements)
    - "implicit" gaps:  excluded (she likely has these skills)
    """
    penalty = 0
    for g in gap_result["gaps"]:
        if g["category"] == "implicit":
            continue
        base_penalty = g["weight"] * 25
        if g["context"] == "unknown":
            base_penalty *= 0.5  # Unknown context = half penalty
        penalty += base_penalty

    # Bonus for strengths (capped at +10)
    bonus = min(10, len(gap_result.get("strengths", [])) * 2)
    return round(max(0, min(100, 100 - penalty + bonus)), 1)


def _classify_requirement_context(text: str, keyword: str) -> str:
    """
    Determine if a keyword appears in a 'required' or 'preferred' context.
    Looks backwards from the keyword for the nearest section header.
    Returns 'required', 'preferred', or 'unknown'.
    """
    text_lower = text.lower()
    keyword_pos = text_lower.find(keyword.lower())
    if keyword_pos == -1:
        return "unknown"

    # Check the last 500 chars before the keyword for section headers
    preceding = text_lower[max(0, keyword_pos - 500):keyword_pos]

    preferred_headers = [
        "preferred qualifications", "preferred skills", "preferred experience",
        "nice to have", "nice-to-have", "desired qualifications",
        "desired skills", "bonus qualifications", "bonus skills",
        "preferred:", "plus:", "a plus", "advantageous",
        "ideally", "not required but", "strongly preferred",
    ]
    required_headers = [
        "required qualifications", "required skills", "required experience",
        "minimum qualifications", "must have", "must-have",
        "requirements:", "required:", "essential",
        "minimum requirements", "basic qualifications",
        "what you need", "what we require", "qualifications:",
        "what you'll need", "what you bring",
    ]

    last_pref_pos = max((preceding.rfind(h) for h in preferred_headers), default=-1)
    last_req_pos = max((preceding.rfind(h) for h in required_headers), default=-1)

    if last_pref_pos > last_req_pos:
        return "preferred"
    elif last_req_pos > last_pref_pos:
        return "required"
    return "unknown"


def _suggest_skill_angle(skill: str) -> str:
    """Suggest how to address a missing skill in cover letter."""
    angles = {
        "six sigma": "Her process improvement work (reducing packaging timelines by 4 weeks, 25-30% rush reduction) demonstrates Six Sigma principles in practice.",
        "lean six sigma": "Her lean team execution (enterprise transformation with 2-3 people) and process optimization exemplify lean principles.",
        "scrum master": "Her agile approach to PLM implementation, iterative feature prioritization, and sprint-like weekly adoption reviews show agile methodology experience.",
        "safe": "Her enterprise-scale coordination across multiple teams mirrors SAFe's program increment planning approach.",
        "python": "Focus on her data-driven approach: adoption metrics tracking, ROI analysis, and performance dashboards.",
        "sql": "Emphasize her SAP, Salesforce, and PLM data management experience as demonstrating database and data querying concepts.",
        "tableau": "Her executive reporting, ROI analysis, and dashboard visibility work demonstrates data visualization competency.",
        "power bi": "Her work creating executive dashboards and tracking adoption metrics shows BI tool proficiency potential.",
        "aws": "Her technology implementation experience (PLM) and digital transformation work show cloud-adjacent skills.",
        "confluence": "Her SharePoint knowledge management and document repository work is directly transferable.",
        "erp implementation": "Her PLM implementation is a subset of ERP — same methodology, vendor evaluation, change management, and training approach.",
        "servicenow": "Her systems implementation methodology (requirements, UAT, training, adoption) transfers directly to ServiceNow environments.",
    }
    return angles.get(skill, "")


def _find_industry_gaps(text_lower: str) -> List[str]:
    """Find if job requires specific industry experience she lacks."""
    her_industries = {"retail", "logistics", "shipping", "supply chain", "consumer goods"}

    industry_mentions = {
        "healthcare": "healthcare" in text_lower or "health system" in text_lower,
        "financial services": "financial services" in text_lower or ("banking" in text_lower and "bank" in text_lower),
        "pharmaceutical": "pharma" in text_lower or "pharmaceutical" in text_lower,
        "aerospace": "aerospace" in text_lower or "defense" in text_lower,
        "telecommunications": "telecom" in text_lower or "telecommunications" in text_lower,
        "media": "media" in text_lower and "entertainment" in text_lower,
        "real estate": "real estate" in text_lower,
    }

    gaps = []
    for industry, is_mentioned in industry_mentions.items():
        if is_mentioned and industry.lower() not in her_industries:
            gaps.append(industry)
    return gaps


def _extract_team_size(text_lower: str) -> int:
    """Extract the largest team size mentioned in description."""
    patterns = [
        r'manage\w*\s+(?:a\s+)?team\s+of\s+(\d+)',
        r'(\d+)\+?\s+direct\s+reports',
        r'leading\s+(?:a\s+)?team\s+of\s+(\d+)',
        r'oversee\w*\s+(?:a\s+)?(?:team|staff|department)\s+of\s+(\d+)',
        r'supervise\w*\s+(\d+)\+?\s+(?:employee|staff|team)',
    ]

    max_size = 0
    for pattern in patterns:
        matches = re.findall(pattern, text_lower)
        for m in matches:
            try:
                max_size = max(max_size, int(m))
            except ValueError:
                continue
    return max_size if max_size > 0 else None


def _assess_risk_weighted(gaps: List[Dict], strengths: List[str]) -> str:
    """Assess risk using weighted gap scores."""
    total_weight = sum(g["weight"] for g in gaps)
    significant = [g for g in gaps if g["weight"] >= 0.3]

    if len(significant) == 0:
        return "Low"
    elif total_weight < 1.0:
        return "Low-Medium"
    elif total_weight < 2.0:
        return "Medium"
    elif total_weight < 3.5:
        return "Medium-High"
    else:
        return "High"


def format_gap_analysis(analysis: Dict) -> str:
    """Format gap analysis for display, grouped by required vs preferred."""
    lines = []
    gaps = analysis.get("gaps", [])

    if gaps:
        required_gaps = [g for g in gaps
                         if g.get("context") in ("required", "unknown")
                         and g.get("category") != "implicit"]
        preferred_gaps = [g for g in gaps
                          if g.get("context") == "preferred"]
        implicit_gaps = [g for g in gaps
                          if g.get("category") == "implicit"]

        if required_gaps:
            lines.append("REQUIRED GAPS:")
            for gap in required_gaps:
                lines.append(f"  - {gap['text']}")

        if preferred_gaps:
            lines.append("\nPREFERRED/NICE-TO-HAVE GAPS:")
            for gap in preferred_gaps:
                lines.append(f"  - {gap['text']}")

        if implicit_gaps:
            names = [g["text"].replace("Likely has (unlisted): ", "") for g in implicit_gaps]
            lines.append(f"\nIMPLICIT SKILLS (she likely has): {', '.join(names)}")
    else:
        lines.append("NO SIGNIFICANT GAPS - Strong match!")

    if analysis.get("strengths"):
        lines.append("\nSTRENGTHS:")
        for s in analysis["strengths"][:5]:
            lines.append(f"  + {s}")

    if analysis.get("cover_letter_angles"):
        lines.append("\nCOVER LETTER ANGLES:")
        for angle in analysis["cover_letter_angles"][:3]:
            lines.append(f"  > {angle}")

    severity = analysis.get("stretch_severity", "")
    if severity:
        lines.append(f"\nStretch Level: {severity}")
    lines.append(f"Qualification Score: {compute_qualification_score(analysis):.0f}/100")
    lines.append(f"Risk Level: {analysis['risk_level']}")

    return "\n".join(lines)
