"""
Job Search Campaign Manager - Configuration
All tunable parameters, weights, thresholds, and search terms.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = PROJECT_ROOT / "job_hunter.db"
REPORT_DIR = PROJECT_ROOT / "reports"
COVER_LETTERS_DIR = PROJECT_ROOT / "cover_letters"

# ── Location ───────────────────────────────────────────────────────────────
HOME_ADDRESS = "Cornelius, NC 28031"
HOME_COORDS = (35.4868, -80.8601)  # Cornelius, NC
MAX_COMMUTE_MILES = 50
RELOCATION_SALARY_THRESHOLD = 200_000  # Willing to relocate for $200K+

# ── Salary ─────────────────────────────────────────────────────────────────
MIN_SALARY = 100_000
SALARY_TIERS = [
    (100_000, 120_000, 45),   # $100K-$120K → score 45
    (120_000, 140_000, 60),   # $120K-$140K → score 60
    (140_000, 160_000, 75),   # $140K-$160K → score 75
    (160_000, 180_000, 85),   # $160K-$180K → score 85
    (180_000, 220_000, 93),   # $180K-$220K → score 93
    (220_000, float('inf'), 100),  # $220K+ → score 100
]

# ── Dual Scoring: Obtainability + Desirability ───────────────────────────
# Obtainability = "Can she get this job?" (qualifications + location)
# Desirability  = "Is this a good job?" (salary, company, benefits)
# Composite     = weighted blend, gated by obtainability
OBTAINABILITY_WEIGHTS = {
    "qualifications":        0.40,   # Gap-analysis-based qualification match
    "location":              0.25,   # Distance / remote / commutability
    "semantic_fit":          0.20,   # AI semantic similarity to her resume
    "interview_probability": 0.15,   # How well she meets listed requirements
}

DESIRABILITY_WEIGHTS = {
    "compensation":    0.30,   # Salary relative to $100K floor
    "job_security":    0.25,   # Company stability + industry health
    "company_quality": 0.20,   # Culture, ratings, "best places to work"
    "benefits":        0.15,   # Health, 401k, PTO signals
    "interview_speed": 0.10,   # Easy apply, urgency, freshness
}

COMPOSITE_OBTAINABILITY_WEIGHT = 0.60
COMPOSITE_DESIRABILITY_WEIGHT = 0.40
COMPOSITE_GATING_THRESHOLD = 50   # Below this, progressive penalty kicks in

WFH_FLEXIBILITY_BONUS = 5  # Desirability bonus for WFH/hybrid/flexible options

# ── Score Tiers (applied to composite score) ──────────────────────────────
TIER_DREAM_JOB = 85       # Green - apply immediately
TIER_STRONG_MATCH = 70    # Blue - high priority
TIER_WORTH_CONSIDERING = 55  # Yellow - apply if time permits
TIER_MINIMUM = 55         # Below this = filtered out

# ── Location Penalty ─────────────────────────────────────────────────────
# Distant non-remote jobs that don't meet relocation threshold get penalized
DISTANT_NONREMOTE_TOTAL_PENALTY = 0.85  # 15% obtainability reduction

# ── Search Configuration ──────────────────────────────────────────────────
TARGET_JOB_TITLES = [
    # Core matches (highest priority)
    "Program Manager",
    "Senior Program Manager",
    "Enterprise Program Manager",
    "Project Manager",
    "Senior Project Manager",
    "Operations Manager",
    "Director of Operations",
    "Change Management Manager",
    "Change Management Lead",
    "Implementation Manager",
    "Systems Implementation Manager",

    # Strong matches
    "Product Manager",
    "Senior Product Manager",
    "Business Operations Manager",
    "Business Operations Director",
    "Vendor Management Manager",
    "Digital Transformation Manager",
    "Digital Transformation Lead",
    "PMO Manager",
    "PMO Lead",
    "PMO Director",
    "Strategy and Operations Manager",
    "Transformation Lead",
    "Transformation Manager",

    # Broader matches
    "Director of Program Management",
    "VP of Operations",
    "Director of Project Management",
    "Technical Program Manager",
    "IT Program Manager",
    "Supply Chain Manager",
    "Supply Chain Director",
    "Logistics Manager",
    "Director of Logistics",
    "Process Improvement Manager",
    "Continuous Improvement Manager",
    "Chief of Staff",
    "Director of Strategic Initiatives",
    "Business Transformation Manager",
    "Enterprise Solutions Manager",
    "Platform Manager",
    "Release Manager",
    "Delivery Manager",
    "Engagement Manager",
]

SEARCH_LOCATIONS = [
    "Charlotte, NC",
    "Cornelius, NC",
    "Huntersville, NC",
    "Davidson, NC",
    "Mooresville, NC",
    "Lake Norman, NC",
    "Remote",
]

# ── Scraping ───────────────────────────────────────────────────────────────
REQUEST_DELAY_MIN = 2.0    # Minimum seconds between requests
REQUEST_DELAY_MAX = 5.0    # Maximum seconds between requests
MAX_RETRIES = 3
REQUEST_TIMEOUT = 30       # seconds
MAX_PAGES_PER_SEARCH = 5   # Pagination limit per search query

# ── Deduplication ──────────────────────────────────────────────────────────
DEDUP_SIMILARITY_THRESHOLD = 0.85  # 85% title+company similarity = same job

# ── Alerts ─────────────────────────────────────────────────────────────────
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")  # Gmail app password
ALERT_TO_EMAIL = os.getenv("ALERT_TO_EMAIL", "cynthiafrancis814@gmail.com")
ALERT_FROM_EMAIL = os.getenv("ALERT_FROM_EMAIL", SMTP_USER)

# ── Dashboard URL (set by GitHub Pages after deployment) ───────────────────
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "")

# ── Claude API (optional, for cover letter generation) ─────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# ── Schedule ───────────────────────────────────────────────────────────────
QUICK_SCAN_INTERVAL_HOURS = 2     # Google Jobs + Indeed every 2 hours
FULL_SCAN_INTERVAL_HOURS = 24     # All sources once daily
DIGEST_HOUR = 7                    # Send daily digest at 7 AM
SCAN_START_HOUR = 6                # Start scanning at 6 AM
SCAN_END_HOUR = 22                 # Stop scanning at 10 PM
