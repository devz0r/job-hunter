"""
Keyword and skill matching — supplements semantic matching.
Catches exact skill matches that semantic similarity might underweight.
"""
import re
from typing import List, Tuple, Dict
from profile import HARD_SKILLS, COMPETENCY_KEYWORDS, RELEVANT_INDUSTRIES


def extract_skills_from_text(text: str) -> List[str]:
    """Extract recognized skills from text."""
    text_lower = text.lower()
    found = []
    for skill in HARD_SKILLS:
        if skill.lower() in text_lower:
            found.append(skill)
    return list(set(found))


def compute_skill_match_score(job_description: str) -> Tuple[float, Dict]:
    """
    Match hard skills from resume against job description.
    Returns (score 0-100, details dict).
    """
    text_lower = job_description.lower()

    # Hard skill matching (exact match)
    hard_matches = []
    hard_total = len(HARD_SKILLS)
    for skill in HARD_SKILLS:
        if skill.lower() in text_lower:
            hard_matches.append(skill)

    # Competency keyword matching (partial/related match)
    competency_matches = []
    competency_total = len(COMPETENCY_KEYWORDS)
    for keyword in COMPETENCY_KEYWORDS:
        if keyword.lower() in text_lower:
            competency_matches.append(keyword)

    # Industry matching
    industry_matches = []
    for industry in RELEVANT_INDUSTRIES:
        if industry.lower() in text_lower:
            industry_matches.append(industry)

    # Scoring
    hard_ratio = len(hard_matches) / max(hard_total, 1)
    comp_ratio = len(competency_matches) / max(competency_total, 1)
    industry_bonus = min(15, len(industry_matches) * 5)

    # Weighted: hard skills matter more
    score = (hard_ratio * 45) + (comp_ratio * 40) + industry_bonus
    score = min(100, score)

    details = {
        "hard_skills_matched": hard_matches,
        "hard_skills_total": hard_total,
        "competencies_matched": competency_matches,
        "competencies_total": competency_total,
        "industries_matched": industry_matches,
        "hard_ratio": hard_ratio,
        "competency_ratio": comp_ratio,
    }

    return score, details


def compute_experience_match(job_description: str, years_required: int = None) -> float:
    """
    Check if her 10+ years matches the job's requirement.
    Returns 0-100.
    """
    from profile import YEARS_EXPERIENCE

    # Try to extract years from description if not provided
    if years_required is None:
        years_required = extract_years_required(job_description)

    if years_required is None:
        return 75  # No requirement stated, neutral-positive

    if years_required <= YEARS_EXPERIENCE:
        if years_required <= 5:
            return 70  # She's overqualified for junior roles
        elif years_required <= 8:
            return 90  # Sweet spot
        else:
            return 95  # Perfect match
    else:
        # She doesn't meet the years requirement
        gap = years_required - YEARS_EXPERIENCE
        if gap <= 2:
            return 65  # Close enough
        elif gap <= 5:
            return 40  # Stretch
        else:
            return 20  # Significant gap


def extract_years_required(text: str) -> int:
    """Extract years of experience required from job description."""
    patterns = [
        r'(\d+)\+?\s*(?:years?|yrs?)\s*(?:of\s+)?(?:experience|exp)',
        r'(?:minimum|at\s+least|requires?)\s*(\d+)\s*(?:years?|yrs?)',
        r'(\d+)\s*-\s*\d+\s*(?:years?|yrs?)',
    ]

    years_found = []
    text_lower = text.lower()
    for pattern in patterns:
        matches = re.findall(pattern, text_lower)
        for m in matches:
            try:
                y = int(m)
                if 1 <= y <= 30:  # Sanity check
                    years_found.append(y)
            except ValueError:
                continue

    if years_found:
        return max(years_found)  # Use the highest requirement
    return None


def extract_education_required(text: str) -> str:
    """Extract education requirements from job description."""
    text_lower = text.lower()

    if any(term in text_lower for term in ["phd", "doctorate", "doctoral"]):
        return "PhD"
    if any(term in text_lower for term in ["master's", "masters", "mba", "m.s.", "m.a."]):
        return "Masters"
    if any(term in text_lower for term in ["bachelor's", "bachelors", "b.s.", "b.a.", "4-year degree", "four-year degree"]):
        return "Bachelors"
    if any(term in text_lower for term in ["associate", "2-year"]):
        return "Associates"
    if "high school" in text_lower or "ged" in text_lower:
        return "High School"

    return "Not specified"


def compute_education_match(job_description: str) -> float:
    """
    Check education requirements against her BA degree.
    Returns 0-100.
    """
    from profile import HAS_BACHELORS, HAS_MBA

    ed_required = extract_education_required(job_description)

    if ed_required == "Not specified":
        return 85  # No requirement, she has a degree so that's a plus
    elif ed_required == "High School" or ed_required == "Associates":
        return 95  # She exceeds
    elif ed_required == "Bachelors":
        return 95  # Exact match
    elif ed_required == "Masters":
        if HAS_MBA:
            return 95
        else:
            return 55  # She doesn't have a master's — but "preferred" vs "required" matters
    elif ed_required == "PhD":
        return 20  # Very unlikely match

    return 75


def compute_certification_match(job_description: str) -> float:
    """Check certification requirements."""
    from profile import HAS_PMP, HAS_CHANGE_MGMT_CERT, HAS_ANALYTICS_CERT

    text_lower = job_description.lower()
    score = 70  # Base score

    cert_mentions = {
        "pmp": HAS_PMP,
        "project management professional": HAS_PMP,
        "project management cert": HAS_PMP,
        "change management": HAS_CHANGE_MGMT_CERT,
        "prosci": HAS_CHANGE_MGMT_CERT,  # Common change mgmt cert
        "ccmp": HAS_CHANGE_MGMT_CERT,
        "analytics": HAS_ANALYTICS_CERT,
        "six sigma": False,
        "lean six sigma": False,
        "csm": False,  # Certified Scrum Master
        "safe": False,  # Scaled Agile
        "itil": False,
    }

    certs_required = []
    certs_matched = []
    certs_missing = []

    for cert_term, has_cert in cert_mentions.items():
        if cert_term in text_lower:
            certs_required.append(cert_term)
            if has_cert:
                certs_matched.append(cert_term)
            else:
                certs_missing.append(cert_term)

    if not certs_required:
        return 80  # No certs required, she has some = bonus

    match_ratio = len(certs_matched) / len(certs_required)
    score = 40 + (match_ratio * 60)

    return min(100, score)
