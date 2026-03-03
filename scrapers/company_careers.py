"""
Direct company career page scraper.
Uses Workday and Greenhouse public APIs where available.
Falls back to HTML scraping for other ATS platforms.
"""
import re
import json
import requests
from typing import List, Optional
from urllib.parse import quote_plus, urljoin
from bs4 import BeautifulSoup

from scrapers.base import BaseScraper
from storage.models import Job
import config


# ── Known Workday API endpoints ──────────────────────────────────────────
# Format: company_slug.wd{N}.myworkdayjobs.com/wday/cxs/{company_slug}/{board}/jobs
WORKDAY_ENDPOINTS = {
    "Duke Energy": {
        "company_id": "dukeenergy", "wd_num": 1, "board": "search",
    },
    "Truist Financial": {
        "company_id": "truist", "wd_num": 1, "board": "Careers",
    },
    "Sunbelt Rentals": {
        "company_id": "sunbeltrentals", "wd_num": 1, "board": "sbcareers",
    },
    "TIAA": {
        "company_id": "tiaa", "wd_num": 1, "board": "search",
    },
    "Atrium Health": {
        "company_id": "aah", "wd_num": 5, "board": "External",
    },
}

# ── Known Greenhouse API board slugs ─────────────────────────────────────
GREENHOUSE_BOARDS = {
    "Red Ventures": "redventures",
    "Credit Karma": "creditkarma",
    "LendingTree": "lendingtree",
    "Lending Tree": "lendingtree",
}


class CompanyCareersScraper(BaseScraper):
    source_name = "company_direct"

    def __init__(self):
        super().__init__()
        self._company_data = self._load_companies()

    def _load_companies(self) -> list:
        """Load company data from JSON."""
        path = config.DATA_DIR / "charlotte_companies.json"
        if path.exists():
            with open(path) as f:
                data = json.load(f)
                return data.get("companies", [])
        return []

    def search(self, title: str, location: str) -> List[Job]:
        """Not used directly — use search_all instead."""
        return []

    def search_all(self) -> List[Job]:
        """Search all configured company career pages using APIs where available."""
        from rich.console import Console
        console = Console()

        all_jobs = []
        companies = self._company_data

        console.print(f"  [bold]Searching {len(companies)} company career pages...[/bold]")

        for company_info in companies:
            name = company_info.get("name", "")
            careers_url = company_info.get("careers_url", "")
            ats = company_info.get("ats_platform", "")

            if not careers_url and name not in WORKDAY_ENDPOINTS and name not in GREENHOUSE_BOARDS:
                continue

            try:
                jobs = self._search_company(name, careers_url, ats)
                if jobs:
                    console.print(
                        f"  [green]{name}[/green]: {len(jobs)} relevant positions"
                    )
                    all_jobs.extend(jobs)
            except Exception as e:
                console.print(f"  [red]{name}[/red]: Error - {e}")

        console.print(f"  [bold]Company careers total: {len(all_jobs)} jobs[/bold]")
        return all_jobs

    def _search_company(self, company_name: str, careers_url: str,
                         ats_platform: str) -> List[Job]:
        """Search a specific company's career page, using API where available."""
        # Workday API (most reliable)
        if company_name in WORKDAY_ENDPOINTS:
            return self._search_workday_api(company_name)

        # Greenhouse API
        if company_name in GREENHOUSE_BOARDS:
            return self._search_greenhouse_api(company_name)

        # Greenhouse URLs (try API discovery)
        if ats_platform == "greenhouse" or "greenhouse.io" in (careers_url or ""):
            jobs = self._search_greenhouse(company_name, careers_url)
            if jobs:
                return jobs

        # For other ATS platforms, use generic scraping
        if careers_url:
            return self._search_generic(company_name, careers_url)

        return []

    # ── Workday API ──────────────────────────────────────────────────────

    def _search_workday_api(self, company_name: str) -> List[Job]:
        """Search via Workday's public JSON API."""
        endpoint = WORKDAY_ENDPOINTS[company_name]
        cid = endpoint["company_id"]
        wd = endpoint["wd_num"]
        board = endpoint["board"]

        base_url = f"https://{cid}.wd{wd}.myworkdayjobs.com"
        api_url = f"{base_url}/wday/cxs/{cid}/{board}/jobs"

        all_jobs = []
        search_terms = [
            "program manager", "project manager", "operations manager",
            "change management", "implementation manager", "PMO",
            "transformation", "director operations",
        ]

        seen_urls = set()

        for term in search_terms:
            try:
                resp = requests.post(
                    api_url,
                    json={
                        "appliedFacets": {},
                        "limit": 20,
                        "offset": 0,
                        "searchText": term,
                    },
                    headers={"Content-Type": "application/json"},
                    timeout=15,
                )
                if resp.status_code != 200:
                    continue

                data = resp.json()
                for posting in data.get("jobPostings", []):
                    job = self._parse_workday_posting(posting, company_name, base_url)
                    if job and job.url not in seen_urls and self._is_relevant(job.title):
                        seen_urls.add(job.url)
                        all_jobs.append(job)

            except Exception:
                continue

        return all_jobs

    def _parse_workday_posting(self, posting: dict, company_name: str,
                                base_url: str) -> Optional[Job]:
        """Parse a Workday API job posting."""
        try:
            job = Job()
            job.source = self.source_name
            job.company = company_name
            job.title = posting.get("title", "")
            job.location = posting.get("locationsText", "")
            job.posted_date = posting.get("postedOn", "")
            job.external_id = posting.get("bulletFields", [""])[0] if posting.get("bulletFields") else ""

            path = posting.get("externalPath", "")
            if path:
                job.url = f"{base_url}{path}"
                job.apply_url = job.url

            # Remote detection
            if job.location:
                loc_lower = job.location.lower()
                if "remote" in loc_lower:
                    job.is_remote = True
                if "hybrid" in loc_lower:
                    job.is_hybrid = True

            return job if job.title else None
        except Exception:
            return None

    # ── Greenhouse API ───────────────────────────────────────────────────

    def _search_greenhouse_api(self, company_name: str) -> List[Job]:
        """Search via Greenhouse's public boards API."""
        board_slug = GREENHOUSE_BOARDS[company_name]
        api_url = f"https://boards-api.greenhouse.io/v1/boards/{board_slug}/jobs"

        try:
            resp = requests.get(api_url, timeout=15)
            if resp.status_code != 200:
                return []

            data = resp.json()
            jobs = []
            for listing in data.get("jobs", []):
                job = self._parse_greenhouse_job(listing, company_name)
                if job and self._is_relevant(job.title):
                    jobs.append(job)

            return jobs
        except Exception:
            return []

    def _search_greenhouse(self, company_name: str, careers_url: str) -> List[Job]:
        """Search Greenhouse-powered career pages."""
        jobs = []

        # Try API endpoint
        if "greenhouse.io" in careers_url:
            api_url = careers_url.rstrip("/") + ".json"
        else:
            html = self.fetch(careers_url)
            if html:
                jobs = self._parse_generic_careers(html, company_name, careers_url)
            return jobs

        json_text = self.fetch(api_url)
        if json_text:
            try:
                data = json.loads(json_text)
                if isinstance(data, dict):
                    listings = data.get("jobs", [])
                elif isinstance(data, list):
                    listings = data
                else:
                    listings = []

                for listing in listings:
                    job = self._parse_greenhouse_job(listing, company_name)
                    if job and self._is_relevant(job.title):
                        jobs.append(job)

            except json.JSONDecodeError:
                html = self.fetch(careers_url)
                if html:
                    jobs = self._parse_generic_careers(html, company_name, careers_url)

        return jobs

    def _parse_greenhouse_job(self, data: dict, company_name: str) -> Optional[Job]:
        """Parse a Greenhouse API job listing."""
        try:
            job = Job()
            job.source = self.source_name
            job.company = company_name
            job.title = data.get("title", "")
            job.external_id = str(data.get("id", ""))
            job.url = data.get("absolute_url", "")
            job.apply_url = job.url
            job.posted_date = data.get("updated_at", "")[:10]

            loc = data.get("location", {})
            if isinstance(loc, dict):
                job.location = loc.get("name", "")

            # Content
            content = data.get("content", "")
            if content:
                soup = BeautifulSoup(content, "lxml")
                job.description = soup.get_text(separator="\n", strip=True)

            if job.location and "remote" in job.location.lower():
                job.is_remote = True

            return job if job.title else None
        except Exception:
            return None

    # ── Generic scraping (fallback) ──────────────────────────────────────

    def _search_generic(self, company_name: str, careers_url: str) -> List[Job]:
        """Search any generic career page."""
        jobs = []
        html = self.fetch(careers_url)
        if not html:
            html = self.fetch_with_playwright(careers_url, wait_time=5000)
        if html:
            jobs = self._parse_generic_careers(html, company_name, careers_url)
        return jobs

    def _parse_generic_careers(self, html: str, company_name: str,
                                base_url: str) -> List[Job]:
        """Generic career page parser — finds job listing links."""
        jobs = []
        soup = BeautifulSoup(html, "lxml")

        for link in soup.find_all("a", href=True):
            text = link.get_text(strip=True)
            href = link["href"]

            if not text or len(text) < 5 or len(text) > 200:
                continue

            if self._is_relevant(text):
                job = Job()
                job.source = self.source_name
                job.company = company_name
                job.title = text

                if href.startswith("/"):
                    href = urljoin(base_url, href)
                elif not href.startswith("http"):
                    href = urljoin(base_url, href)

                job.url = href
                job.apply_url = href

                parent = link.parent
                if parent:
                    loc_el = parent.find(
                        "span", class_=re.compile(r"loc|location|city")
                    )
                    if loc_el:
                        job.location = loc_el.get_text(strip=True)

                    parent_text = parent.get_text(strip=True).lower()
                    if "remote" in parent_text:
                        job.is_remote = True
                    if "hybrid" in parent_text:
                        job.is_hybrid = True
                    if "charlotte" in parent_text or "nc" in parent_text:
                        if not job.location:
                            job.location = "Charlotte, NC"

                jobs.append(job)

        return jobs

    def _is_relevant(self, title: str) -> bool:
        """Check if a job title is relevant for Cynthia."""
        title_lower = title.lower()

        relevant_keywords = [
            "manager", "director", "lead", "chief of staff",
            "program", "project", "operations", "change management",
            "implementation", "transformation", "vendor",
            "strategy", "pmo", "delivery", "engagement",
            "supply chain", "logistics", "process",
            "product", "platform", "business operations",
        ]

        exclusions = [
            "software engineer", "developer", "data scientist",
            "designer", "nurse", "physician", "accountant",
            "sales rep", "retail associate", "store manager",
            "customer service rep", "cashier", "warehouse",
            "mechanic", "technician", "electrician", "plumber",
            "intern", "internship", "entry level", "junior",
            "part-time", "part time", "seasonal", "temporary",
        ]

        if any(exc in title_lower for exc in exclusions):
            return False

        return any(kw in title_lower for kw in relevant_keywords)
