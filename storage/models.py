"""
Data models for job listings, companies, and applications.
"""
from dataclasses import dataclass, field, asdict
from typing import Optional
from datetime import datetime
import json


@dataclass
class Job:
    """Represents a single job listing."""
    # Identity
    id: Optional[int] = None
    external_id: str = ""          # ID from the source
    url: str = ""
    source: str = ""               # indeed, linkedin, google_jobs, company_direct, etc.

    # Core info
    title: str = ""
    company: str = ""
    location: str = ""
    description: str = ""
    posted_date: str = ""          # ISO format or text like "3 days ago"
    discovered_date: str = ""      # When we first found it

    # Compensation
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_text: str = ""          # Raw salary string from posting
    estimated_salary: Optional[float] = None  # Our estimate if not posted

    # Work arrangement
    is_remote: bool = False
    is_hybrid: bool = False
    remote_text: str = ""          # "Remote", "Hybrid", "On-site", etc.

    # Requirements extracted
    years_required: Optional[int] = None
    education_required: str = ""
    skills_required: list = field(default_factory=list)
    certifications_required: list = field(default_factory=list)

    # Application info
    apply_url: str = ""
    easy_apply: bool = False
    application_method: str = ""   # "Easy Apply", "External", "Email", etc.

    # Scores (0-100 each)
    score_total: float = 0.0          # Composite score (main rank)
    score_obtainability: float = 0.0  # "Can she get this?" score
    score_desirability: float = 0.0   # "Is it a good job?" score
    score_qualifications: float = 0.0 # Gap-analysis-based qualification match
    score_resume_fit: float = 0.0     # Legacy: semantic + skill + experience
    score_resume_fit_raw: float = 0.0 # Legacy: kept for backward compat
    score_job_security: float = 0.0
    score_compensation: float = 0.0
    score_company_quality: float = 0.0
    score_benefits: float = 0.0
    score_location: float = 0.0
    score_interview_prob: float = 0.0
    score_interview_speed: float = 0.0

    # Tier classification
    tier: str = ""                 # "DREAM_JOB", "STRONG_MATCH", "WORTH_CONSIDERING"
    is_stretch: bool = False       # Stretch opportunity flag
    stretch_severity: str = ""     # "Minor Stretch", "Moderate Stretch", etc.
    stretch_gap_analysis: str = "" # What she's missing + how to address

    # Application tracking
    status: str = "new"            # new, applied, phone_screen, interview, offer, rejected, passed
    applied_date: str = ""
    follow_up_date: str = ""
    notes: str = ""

    # Cover letter
    cover_letter_generated: bool = False
    cover_letter_path: str = ""

    # Metadata
    raw_html: str = ""             # Full HTML of listing (for re-parsing)
    company_id: Optional[int] = None

    def to_dict(self):
        d = asdict(self)
        # Convert lists to JSON strings for SQLite
        d['skills_required'] = json.dumps(d['skills_required'])
        d['certifications_required'] = json.dumps(d['certifications_required'])
        return d

    @classmethod
    def from_dict(cls, d):
        if isinstance(d.get('skills_required'), str):
            d['skills_required'] = json.loads(d['skills_required'])
        if isinstance(d.get('certifications_required'), str):
            d['certifications_required'] = json.loads(d['certifications_required'])
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    @property
    def salary_midpoint(self):
        if self.salary_min and self.salary_max:
            return (self.salary_min + self.salary_max) / 2
        if self.salary_min:
            return self.salary_min
        if self.salary_max:
            return self.salary_max
        if self.estimated_salary:
            return self.estimated_salary
        return None

    @property
    def display_salary(self):
        if self.salary_min and self.salary_max:
            return f"${self.salary_min:,.0f} - ${self.salary_max:,.0f}"
        if self.salary_min:
            return f"${self.salary_min:,.0f}+"
        if self.salary_max:
            return f"Up to ${self.salary_max:,.0f}"
        if self.estimated_salary:
            return f"~${self.estimated_salary:,.0f} (est.)"
        if self.salary_text:
            return self.salary_text
        return "Not listed"


@dataclass
class Company:
    """Represents company intelligence data."""
    id: Optional[int] = None
    name: str = ""
    normalized_name: str = ""      # Lowercase, stripped for matching
    industry: str = ""
    size: str = ""                 # "1-50", "51-200", "201-1000", "1001-5000", "5000+"
    size_employees: Optional[int] = None
    is_public: bool = False
    is_fortune_500: bool = False
    is_fortune_1000: bool = False

    # Location
    hq_location: str = ""
    charlotte_office: bool = True

    # Ratings
    glassdoor_rating: Optional[float] = None  # 0-5
    glassdoor_url: str = ""
    indeed_rating: Optional[float] = None
    ceo_approval: Optional[float] = None      # 0-100
    recommend_to_friend: Optional[float] = None  # 0-100
    best_places_to_work: bool = False

    # Career page
    careers_url: str = ""
    ats_platform: str = ""         # workday, greenhouse, lever, icims, taleo, etc.

    # Intelligence
    recent_layoffs: bool = False
    growth_signals: bool = False   # Lots of open positions
    recent_news: str = ""

    # Computed scores
    quality_score: float = 0.0     # Overall quality 0-100
    security_score: float = 0.0    # Job security 0-100
    benefits_score: float = 0.0    # Benefits quality 0-100

    last_updated: str = ""

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class SearchQuery:
    """Represents a search query to execute."""
    title: str = ""
    location: str = ""
    source: str = ""               # which scraper to use
    url: str = ""                  # pre-built search URL if applicable
    last_run: str = ""
    results_count: int = 0
