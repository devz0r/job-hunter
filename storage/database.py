"""
SQLite database operations for job storage, deduplication, and tracking.
"""
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from difflib import SequenceMatcher
from typing import List, Optional, Tuple

from storage.models import Job, Company
import config


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(config.DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create all tables if they don't exist."""
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            external_id TEXT DEFAULT '',
            url TEXT DEFAULT '',
            source TEXT DEFAULT '',
            title TEXT DEFAULT '',
            company TEXT DEFAULT '',
            location TEXT DEFAULT '',
            description TEXT DEFAULT '',
            posted_date TEXT DEFAULT '',
            discovered_date TEXT DEFAULT '',
            salary_min REAL,
            salary_max REAL,
            salary_text TEXT DEFAULT '',
            estimated_salary REAL,
            is_remote INTEGER DEFAULT 0,
            is_hybrid INTEGER DEFAULT 0,
            remote_text TEXT DEFAULT '',
            years_required INTEGER,
            education_required TEXT DEFAULT '',
            skills_required TEXT DEFAULT '[]',
            certifications_required TEXT DEFAULT '[]',
            apply_url TEXT DEFAULT '',
            easy_apply INTEGER DEFAULT 0,
            application_method TEXT DEFAULT '',
            score_total REAL DEFAULT 0,
            score_resume_fit REAL DEFAULT 0,
            score_job_security REAL DEFAULT 0,
            score_compensation REAL DEFAULT 0,
            score_company_quality REAL DEFAULT 0,
            score_benefits REAL DEFAULT 0,
            score_location REAL DEFAULT 0,
            score_interview_prob REAL DEFAULT 0,
            score_interview_speed REAL DEFAULT 0,
            tier TEXT DEFAULT '',
            is_stretch INTEGER DEFAULT 0,
            stretch_gap_analysis TEXT DEFAULT '',
            status TEXT DEFAULT 'new',
            applied_date TEXT DEFAULT '',
            follow_up_date TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            cover_letter_generated INTEGER DEFAULT 0,
            cover_letter_path TEXT DEFAULT '',
            raw_html TEXT DEFAULT '',
            company_id INTEGER,
            FOREIGN KEY (company_id) REFERENCES companies(id)
        );

        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT DEFAULT '',
            normalized_name TEXT DEFAULT '',
            industry TEXT DEFAULT '',
            size TEXT DEFAULT '',
            size_employees INTEGER,
            is_public INTEGER DEFAULT 0,
            is_fortune_500 INTEGER DEFAULT 0,
            is_fortune_1000 INTEGER DEFAULT 0,
            hq_location TEXT DEFAULT '',
            charlotte_office INTEGER DEFAULT 1,
            glassdoor_rating REAL,
            glassdoor_url TEXT DEFAULT '',
            indeed_rating REAL,
            ceo_approval REAL,
            recommend_to_friend REAL,
            best_places_to_work INTEGER DEFAULT 0,
            careers_url TEXT DEFAULT '',
            ats_platform TEXT DEFAULT '',
            recent_layoffs INTEGER DEFAULT 0,
            growth_signals INTEGER DEFAULT 0,
            recent_news TEXT DEFAULT '',
            quality_score REAL DEFAULT 0,
            security_score REAL DEFAULT 0,
            benefits_score REAL DEFAULT 0,
            last_updated TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS search_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT,
            source TEXT,
            location TEXT,
            timestamp TEXT,
            results_found INTEGER DEFAULT 0,
            new_jobs_added INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS alerts_sent (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER,
            alert_type TEXT,
            sent_at TEXT,
            FOREIGN KEY (job_id) REFERENCES jobs(id)
        );

        CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);
        CREATE INDEX IF NOT EXISTS idx_jobs_score ON jobs(score_total DESC);
        CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
        CREATE INDEX IF NOT EXISTS idx_jobs_tier ON jobs(tier);
        CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source);
        CREATE INDEX IF NOT EXISTS idx_companies_name ON companies(normalized_name);
    """)
    conn.commit()

    # ── Schema migrations (idempotent) ─────────────────────────────────────
    new_columns = [
        "score_resume_fit_raw REAL DEFAULT 0",
        "score_obtainability REAL DEFAULT 0",
        "score_desirability REAL DEFAULT 0",
        "score_qualifications REAL DEFAULT 0",
        "stretch_severity TEXT DEFAULT ''",
    ]
    for col_def in new_columns:
        try:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {col_def}")
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists

    conn.close()


def normalize_company_name(name: str) -> str:
    """Normalize company name for matching."""
    name = name.lower().strip()
    # Remove common suffixes
    for suffix in [", inc.", ", inc", " inc.", " inc", ", llc", " llc",
                   ", ltd", " ltd", " corp.", " corp", " corporation",
                   " company", " companies", " co.", " co",
                   ", na", " n.a.", " na"]:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
    return name.strip()


def is_duplicate(job: Job, conn: sqlite3.Connection) -> bool:
    """Check if a job is a duplicate of an existing listing."""
    # First check URL match
    if job.url:
        existing = conn.execute(
            "SELECT id FROM jobs WHERE url = ?", (job.url,)
        ).fetchone()
        if existing:
            return True

    # Then check fuzzy title + company match
    norm_company = normalize_company_name(job.company)
    candidates = conn.execute(
        "SELECT id, title, company FROM jobs WHERE company LIKE ?",
        (f"%{norm_company[:20]}%",)
    ).fetchall()

    for candidate in candidates:
        title_sim = SequenceMatcher(
            None, job.title.lower(), candidate['title'].lower()
        ).ratio()
        company_sim = SequenceMatcher(
            None, normalize_company_name(job.company),
            normalize_company_name(candidate['company'])
        ).ratio()
        combined = (title_sim * 0.6) + (company_sim * 0.4)
        if combined >= config.DEDUP_SIMILARITY_THRESHOLD:
            return True

    return False


def save_job(job: Job) -> Optional[int]:
    """Save a job to the database. Returns job ID or None if duplicate."""
    conn = get_connection()
    try:
        if is_duplicate(job, conn):
            return None

        job.discovered_date = datetime.now().isoformat()
        d = job.to_dict()
        del d['id']  # Let SQLite auto-increment

        columns = ', '.join(d.keys())
        placeholders = ', '.join(['?' for _ in d])
        values = list(d.values())

        cursor = conn.execute(
            f"INSERT INTO jobs ({columns}) VALUES ({placeholders})", values
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def save_jobs_batch(jobs: List[Job]) -> Tuple[int, int]:
    """Save multiple jobs. Returns (saved_count, duplicate_count)."""
    saved = 0
    dupes = 0
    conn = get_connection()
    try:
        for job in jobs:
            if is_duplicate(job, conn):
                dupes += 1
                continue

            job.discovered_date = datetime.now().isoformat()
            d = job.to_dict()
            del d['id']

            columns = ', '.join(d.keys())
            placeholders = ', '.join(['?' for _ in d])
            values = list(d.values())

            conn.execute(
                f"INSERT INTO jobs ({columns}) VALUES ({placeholders})", values
            )
            saved += 1

        conn.commit()
        return saved, dupes
    finally:
        conn.close()


def update_job_scores(job_id: int, scores: dict):
    """Update scoring fields for a job."""
    conn = get_connection()
    try:
        sets = ', '.join([f"{k} = ?" for k in scores.keys()])
        values = list(scores.values()) + [job_id]
        conn.execute(f"UPDATE jobs SET {sets} WHERE id = ?", values)
        conn.commit()
    finally:
        conn.close()


def update_job_status(job_id: int, status: str, notes: str = ""):
    """Update application status for a job."""
    conn = get_connection()
    try:
        now = datetime.now().isoformat()
        if status == "applied":
            conn.execute(
                "UPDATE jobs SET status=?, applied_date=?, notes=? WHERE id=?",
                (status, now, notes, job_id)
            )
        else:
            conn.execute(
                "UPDATE jobs SET status=?, notes=? WHERE id=?",
                (status, notes, job_id)
            )
        conn.commit()
    finally:
        conn.close()


def get_all_jobs(min_score: float = 0, status: str = None,
                 tier: str = None, limit: int = 500) -> List[Job]:
    """Get jobs filtered and sorted by score."""
    conn = get_connection()
    try:
        query = "SELECT * FROM jobs WHERE score_total >= ?"
        params = [min_score]

        if status:
            query += " AND status = ?"
            params.append(status)
        if tier:
            query += " AND tier = ?"
            params.append(tier)

        query += " ORDER BY score_total DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        return [Job.from_dict(dict(r)) for r in rows]
    finally:
        conn.close()


def get_new_jobs_since(since_iso: str) -> List[Job]:
    """Get jobs discovered since a given datetime."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE discovered_date > ? ORDER BY score_total DESC",
            (since_iso,)
        ).fetchall()
        return [Job.from_dict(dict(r)) for r in rows]
    finally:
        conn.close()


def get_jobs_needing_followup() -> List[Job]:
    """Get applied jobs where follow-up is due."""
    conn = get_connection()
    try:
        now = datetime.now().isoformat()
        rows = conn.execute(
            """SELECT * FROM jobs
               WHERE status = 'applied'
               AND follow_up_date != ''
               AND follow_up_date <= ?
               ORDER BY follow_up_date""",
            (now,)
        ).fetchall()
        return [Job.from_dict(dict(r)) for r in rows]
    finally:
        conn.close()


def get_unscored_jobs() -> List[Job]:
    """Get jobs that haven't been scored yet."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE score_total IS NULL OR score_total = 0"
        ).fetchall()
        return [Job.from_dict(dict(r)) for r in rows]
    finally:
        conn.close()


def get_job_count() -> dict:
    """Get counts by tier and status."""
    conn = get_connection()
    try:
        stats = {}
        for row in conn.execute(
            "SELECT tier, COUNT(*) as cnt FROM jobs WHERE tier != '' GROUP BY tier"
        ).fetchall():
            stats[f"tier_{row['tier'].lower()}"] = row['cnt']

        for row in conn.execute(
            "SELECT status, COUNT(*) as cnt FROM jobs GROUP BY status"
        ).fetchall():
            stats[f"status_{row['status']}"] = row['cnt']

        stats['total'] = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        return stats
    finally:
        conn.close()


# ── Company Operations ─────────────────────────────────────────────────────

def save_company(company: Company) -> int:
    """Save or update a company. Returns company ID."""
    conn = get_connection()
    try:
        company.normalized_name = normalize_company_name(company.name)
        company.last_updated = datetime.now().isoformat()

        # Check if exists
        existing = conn.execute(
            "SELECT id FROM companies WHERE normalized_name = ?",
            (company.normalized_name,)
        ).fetchone()

        if existing:
            d = company.to_dict()
            del d['id']
            sets = ', '.join([f"{k} = ?" for k in d.keys()])
            values = list(d.values()) + [existing['id']]
            conn.execute(f"UPDATE companies SET {sets} WHERE id = ?", values)
            conn.commit()
            return existing['id']
        else:
            d = company.to_dict()
            del d['id']
            columns = ', '.join(d.keys())
            placeholders = ', '.join(['?' for _ in d])
            cursor = conn.execute(
                f"INSERT INTO companies ({columns}) VALUES ({placeholders})",
                list(d.values())
            )
            conn.commit()
            return cursor.lastrowid
    finally:
        conn.close()


def get_company(name: str) -> Optional[Company]:
    """Look up company by name with exact, substring, and fuzzy matching."""
    conn = get_connection()
    try:
        norm = normalize_company_name(name)

        # 1. Exact normalized match
        row = conn.execute(
            "SELECT * FROM companies WHERE normalized_name = ?", (norm,)
        ).fetchone()
        if row:
            return Company.from_dict(dict(row))

        # 2. Substring match — "Ally" matches "Ally Financial",
        #    "Truist" matches "Truist Financial", etc.
        rows = conn.execute("SELECT * FROM companies").fetchall()
        for r in rows:
            db_norm = r['normalized_name']
            # Job name starts with DB name or vice versa
            if (len(norm) >= 3 and len(db_norm) >= 3 and
                    (db_norm.startswith(norm) or norm.startswith(db_norm))):
                return Company.from_dict(dict(r))

        # 3. Fuzzy fallback (lower threshold for better matching)
        best_match = None
        best_sim = 0
        for r in rows:
            sim = SequenceMatcher(None, norm, r['normalized_name']).ratio()
            if sim > best_sim:
                best_sim = sim
                best_match = r
        if best_match and best_sim > 0.7:
            return Company.from_dict(dict(best_match))

        return None
    finally:
        conn.close()


def get_all_companies() -> List[Company]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM companies ORDER BY quality_score DESC").fetchall()
        return [Company.from_dict(dict(r)) for r in rows]
    finally:
        conn.close()


def log_search(query: str, source: str, location: str,
               results_found: int, new_jobs: int):
    """Log a search execution."""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO search_log
               (query, source, location, timestamp, results_found, new_jobs_added)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (query, source, location, datetime.now().isoformat(),
             results_found, new_jobs)
        )
        conn.commit()
    finally:
        conn.close()
