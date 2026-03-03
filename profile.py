"""
Cynthia Francis - Resume Profile
Used for matching against job descriptions.
"""
import os

CANDIDATE_NAME = "Cynthia Francis"
CANDIDATE_EMAIL = os.getenv("CANDIDATE_EMAIL", "")
CANDIDATE_PHONE = os.getenv("CANDIDATE_PHONE", "")
CANDIDATE_LOCATION = "Charlotte, NC"

# ── Full Resume Text (for semantic embedding) ──────────────────────────────
RESUME_TEXT = """
Strategic Enterprise Program and Operations leader with 10 years of corporate
experience who thrives in complex, global environments where clarity, structure,
and execution are needed to move initiatives forward. Trusted to step into
ambiguous or high-stakes projects, from global logistics operations managing
enterprise clients to leading enterprise technology implementations impacting
hundreds of users.

Led implementation and recovery of Product Lifecycle Management (PLM) system
supporting 750+ internal and external users, increasing adoption from 10% to 87%
through targeted change management, training strategy, and workflow optimization.

Experience spans systems implementation, operational transformation, and
executive-level program management, including managing initiatives and events
with budgets up to $20M.

CORE COMPETENCIES:
Project Leadership, End-to-End Systems Implementation, PTC PLM, Budget Management
$3M to $20M, Strategic Roadmap Development, User Acceptance Testing UAT, Feature
Prioritization, Workflow Optimization, JIRA, SAP, Salesforce, Global Logistics,
Vendor Management with 200+ partners, Process Re-engineering, Change Management,
Cross-functional Leadership, Training and Enablement, Stakeholder Management.

PROFESSIONAL EXPERIENCE:

Global Business Project Manager at Lowe's Companies, Charlotte NC (Dec 2024 - Present):
- Enterprise Event Program Management directing planning and execution of
  executive-level events with budgets from $3M to $20M, 500 to 4000+ attendees
- Vendor and Floorplan Strategy coordinating 110-200+ vendors per event
- Budget Oversight managing multi-million-dollar event budgets
- Cross-Functional Leadership with Corporate Events, merchandising, executives
- Spearheaded vendor donation initiative raising nearly $500K
- Oversaw venue coordination, vendor contracts, safety compliance, scheduling

Product Activation Manager PLM Lead at Lowe's Companies (Feb 2022 - Dec 2024):
- Led 6-month rapid rollout of white-label PTC Product Lifecycle Management platform
  replacing manual Excel/email workflows for 200 internal users and 500+ external vendors
- Facilitated evaluation of five PLM vendors, led SME workshops
- Recovered stalled implementation following executive sponsor departure
  driving adoption from 10% to 87%
- Served as voice of the user reducing click fatigue in 17-click workflows
- Conducted weekly adoption reviews with 30 key Product Development Merchants
- Designed training for internal teams and global sourcing offices Asia India Central America
- Quantified 4-week reduction in packaging timelines 13 to 9 weeks
  and 25-30% reduction in rush-order shipments
- Managed enterprise transformation with core team of 3 later 2

Lead Operations Analyst at Lowe's Companies (July 2020 - Feb 2022):
- Built SharePoint-based document repositories centralizing SOPs
- Led vendor education and internal adoption of new systems
- Managed stop-sales and recall communications
- Created internal leadership podcast

Lead Customer Service Incident Analyst at Maersk Line (March 2019 - July 2020):
- Investigated global shipping incidents including hurricane losses
- Resolved claims up to $273K
- Executed invoicing settlements and payment reconciliation within SAP
- Coordinated specialized equipment and port authorities

Global Care Business Partner at Maersk Line (Aug 2015 - March 2019):
- Primary contact for high-volume accounts: Amazon, Honda, Target, Home Depot
- Managed 100K-150K containers annually
- Negotiated container rerouting to save critical delivery windows
- Supplied shipment data and performance insights for contract negotiations

EDUCATION:
Bachelor of Arts in Elementary Education, University of North Carolina at Charlotte

CERTIFICATIONS:
Project Management Certification
Change Management Certification
Business Analytics and Operations Certificate
"""

# ── Hard Skills (for exact matching) ───────────────────────────────────────
HARD_SKILLS = [
    "PLM", "Product Lifecycle Management", "PTC",
    "SAP", "Salesforce", "JIRA", "SharePoint",
    "Excel", "Microsoft Office", "Microsoft 365",
    "UAT", "User Acceptance Testing",
    "Workday",  # common in enterprise environments
]

# ── Competency Keywords (broader matching) ─────────────────────────────────
COMPETENCY_KEYWORDS = [
    "program management", "project management", "portfolio management",
    "change management", "transformation", "implementation",
    "vendor management", "vendor relations", "supplier management",
    "budget management", "financial management", "cost control",
    "stakeholder management", "executive communication",
    "cross-functional", "cross functional", "matrixed",
    "global operations", "logistics", "supply chain",
    "process improvement", "process re-engineering", "lean",
    "training", "enablement", "adoption", "onboarding",
    "systems implementation", "software implementation", "ERP",
    "workflow optimization", "process optimization",
    "strategic planning", "roadmap", "strategy",
    "event management", "event planning",
    "data analysis", "analytics", "reporting",
    "agile", "scrum", "waterfall",
    "risk management", "compliance",
    "quality assurance", "QA",
]

# ── Industries Where She Has Direct Experience ─────────────────────────────
RELEVANT_INDUSTRIES = [
    "retail", "home improvement", "consumer goods",
    "logistics", "shipping", "freight", "supply chain", "transportation",
    "manufacturing", "industrial",
    "enterprise software", "SaaS", "technology",
]

# ── Experience Summary (for gap analysis) ──────────────────────────────────
YEARS_EXPERIENCE = 10
HAS_BACHELORS = True
HAS_MBA = False
HAS_PMP = True  # Project Management Certification
HAS_CHANGE_MGMT_CERT = True
HAS_ANALYTICS_CERT = True
MANAGEMENT_EXPERIENCE = True
DIRECT_REPORTS_MAX = 3  # Small team management
BUDGET_EXPERIENCE_MAX = 20_000_000  # $20M

# ── Seniority Level Classification ────────────────────────────────────────
# Title fragments indicating levels ABOVE her experience.
# She has held: Lead, Senior Analyst, Manager (of projects/products, not people).
# She has NOT held: Director, VP, SVP, EVP, C-suite, Head of, General Manager.
STRETCH_TITLE_KEYWORDS = [
    "director",
    "vice president", "vp ",
    "v.p.",
    "svp", "senior vice president",
    "evp", "executive vice president",
    "chief ",
    "coo", "cfo", "cto", "cio", "cmo", "cpo",
    "managing director",
    "general manager",
    "head of",
    "principal",
]

# Title fragments at or BELOW her level (never stretch)
NON_STRETCH_TITLE_KEYWORDS = [
    "coordinator",
    "specialist",
    "analyst",
    "associate",
    "administrator",
    "assistant",
    "intern",
    "entry level",
    "entry-level",
    "junior",
]

# Team management threshold — she's managed 2-3 max
STRETCH_TEAM_SIZE_THRESHOLD = 5

# ── Implicit Skills ───────────────────────────────────────────────────────
# Skills she almost certainly has but didn't list on resume.
# These should barely count as gaps in job requirement matching.
IMPLICIT_SKILLS = [
    "ms word", "microsoft word", "word",
    "ms office", "microsoft office", "office 365", "microsoft 365",
    "powerpoint", "ms powerpoint", "microsoft powerpoint",
    "outlook", "ms outlook", "microsoft outlook",
    "teams", "microsoft teams", "ms teams",
    "google workspace", "google docs", "google sheets",
    "zoom", "video conferencing", "webex",
    "slack",
    "windows", "mac os",
    "email", "e-mail",
    "communication", "written communication", "verbal communication",
    "team player", "teamwork", "collaboration",
    "organizational skills", "organized", "detail-oriented", "detail oriented",
    "time management", "multitasking", "multi-tasking",
    "problem solving", "problem-solving", "critical thinking",
    "interpersonal skills", "presentation skills",
    "self-starter", "self starter",
]

# ── Key Achievement Bullets (for cover letter mapping) ─────────────────────
KEY_ACHIEVEMENTS = [
    {
        "text": "Led PLM implementation for 750+ users, driving adoption from 10% to 87%",
        "tags": ["implementation", "change management", "adoption", "PLM", "enterprise"],
    },
    {
        "text": "Managed enterprise events with budgets from $3M to $20M for 500-4000+ attendees",
        "tags": ["budget management", "event management", "executive", "large-scale"],
    },
    {
        "text": "Recovered stalled PLM implementation after executive sponsor departure",
        "tags": ["leadership", "crisis management", "recovery", "resilience"],
    },
    {
        "text": "Reduced packaging timelines by 4 weeks (13 to 9 weeks) and rush shipments by 25-30%",
        "tags": ["process improvement", "ROI", "efficiency", "operations"],
    },
    {
        "text": "Managed global logistics for enterprise clients including Amazon, Honda, Target, Home Depot at Maersk",
        "tags": ["global", "logistics", "enterprise clients", "account management"],
    },
    {
        "text": "Coordinated 200+ vendors per event and managed vendor evaluation/selection processes",
        "tags": ["vendor management", "procurement", "coordination"],
    },
    {
        "text": "Designed and delivered training for global teams across Asia, India, and Central America",
        "tags": ["training", "global", "enablement", "international"],
    },
    {
        "text": "Spearheaded vendor donation initiative raising nearly $500K for catastrophe relief",
        "tags": ["fundraising", "initiative", "leadership", "community"],
    },
    {
        "text": "Resolved global shipping claims up to $273K including hurricane losses",
        "tags": ["crisis management", "claims", "risk", "resolution"],
    },
    {
        "text": "Managed enterprise transformation initiative with lean team of 2-3 people",
        "tags": ["lean", "resourceful", "transformation", "efficiency"],
    },
]
