"""
Job Enrichment Module
Fetches full job descriptions AND salary data for jobs that lack them.
This dramatically improves scoring accuracy since semantic matching
and keyword matching both need the full description.
"""
import re
import time
import random
from typing import List, Optional, Dict

from rich.console import Console
from rich.progress import Progress

from storage import database as db
from storage.models import Job
from scrapers.base import BaseScraper, USER_AGENTS
import config

console = Console()


class JobEnricher(BaseScraper):
    """Fetches full job descriptions and salary data for stored jobs."""

    source_name = "enricher"
    base_url = ""

    def search(self, title: str, location: str) -> List[Job]:
        """Not used — enricher doesn't search."""
        return []

    def enrich_jobs(self, limit: int = 200) -> int:
        """
        Fetch full descriptions + salary for jobs missing them.
        Returns count of jobs enriched.
        """
        conn = db.get_connection()
        try:
            rows = conn.execute(
                """SELECT id, url, source, title, company, salary_min
                   FROM jobs
                   WHERE ((description IS NULL OR description = '')
                          OR (salary_min IS NULL AND salary_text = ''))
                   AND url IS NOT NULL AND url != ''
                   ORDER BY discovered_date DESC
                   LIMIT ?""",
                (limit,)
            ).fetchall()
        finally:
            conn.close()

        if not rows:
            console.print("[dim]No jobs need enrichment.[/dim]")
            return 0

        console.print(f"[bold]Enriching {len(rows)} jobs...[/bold]")
        enriched = 0
        failed = 0
        salaries_found = 0

        with Progress() as progress:
            task = progress.add_task("Enriching", total=len(rows))

            for row in rows:
                job_id = row[0]
                url = row[1]
                source = row[2]
                has_salary = row[5] is not None

                try:
                    data = self._fetch_data(url, source)
                    if data:
                        update_fields = {}

                        if data.get("description") and len(data["description"]) > 50:
                            update_fields["description"] = data["description"]

                        if not has_salary:
                            if data.get("salary_min"):
                                update_fields["salary_min"] = data["salary_min"]
                            if data.get("salary_max"):
                                update_fields["salary_max"] = data["salary_max"]
                            if data.get("salary_text"):
                                update_fields["salary_text"] = data["salary_text"]

                        if update_fields:
                            conn = db.get_connection()
                            try:
                                sets = ', '.join(f"{k} = ?" for k in update_fields)
                                values = list(update_fields.values()) + [job_id]
                                conn.execute(
                                    f"UPDATE jobs SET {sets} WHERE id = ?", values
                                )
                                conn.commit()
                                enriched += 1
                                if "salary_min" in update_fields:
                                    salaries_found += 1
                            finally:
                                conn.close()
                        else:
                            failed += 1
                    else:
                        failed += 1
                except Exception:
                    failed += 1

                progress.advance(task)

        console.print(
            f"[green]Enriched {enriched} jobs[/green] "
            f"([cyan]{salaries_found} salaries found[/cyan], {failed} failed)"
        )
        return enriched

    def extract_salaries_from_stored_descriptions(self) -> int:
        """
        Scan all stored descriptions AND salary_text for salary data
        WITHOUT refetching URLs. This catches salaries missed because:
        - The enrichment URL fetch failed
        - The regex was too narrow at the time of enrichment
        - salary_text was set but salary_min/max weren't parsed
        """
        conn = db.get_connection()
        try:
            # Get jobs with descriptions but no parsed salary
            rows = conn.execute(
                """SELECT id, description, salary_text FROM jobs
                   WHERE salary_min IS NULL
                   AND (
                       (description IS NOT NULL AND description != '')
                       OR (salary_text IS NOT NULL AND salary_text != '')
                   )"""
            ).fetchall()
        finally:
            conn.close()

        if not rows:
            console.print("[dim]No jobs with descriptions missing salary.[/dim]")
            return 0

        console.print(f"[bold]Scanning {len(rows)} jobs for salary data...[/bold]")
        found = 0

        for row in rows:
            job_id, description, salary_text = row[0], row[1] or "", row[2] or ""
            result = {}

            # Try salary_text first (e.g., "Base pay range$90,000/yr - $150,000/yr")
            if salary_text:
                self._extract_salary_from_text(salary_text, result)

            # If that didn't work, try the full description
            if not result.get("salary_min") and description:
                self._extract_salary_from_text(description, result)

            if result.get("salary_min"):
                conn = db.get_connection()
                try:
                    conn.execute(
                        """UPDATE jobs SET salary_min = ?, salary_max = ?
                           WHERE id = ?""",
                        (result["salary_min"], result.get("salary_max"), job_id)
                    )
                    conn.commit()
                    found += 1
                finally:
                    conn.close()

        console.print(f"[green]Extracted salary from {found}/{len(rows)} jobs[/green]")
        return found

    def _fetch_data(self, url: str, source: str) -> Optional[Dict]:
        """Fetch description + salary from a job URL."""
        if not url:
            return None

        if "linkedin.com" in url:
            return self._fetch_linkedin_data(url)
        else:
            # For non-LinkedIn, wrap description in dict + extract salary from text
            desc = self._fetch_description_only(url, source)
            if desc:
                result = {"description": desc}
                self._extract_salary_from_text(desc, result)
                return result
            return None

    def _fetch_linkedin_data(self, url: str) -> Optional[Dict]:
        """Fetch description AND salary from LinkedIn job page."""
        from bs4 import BeautifulSoup
        import json

        html = self.fetch(url)
        if not html:
            return None

        soup = BeautifulSoup(html, 'lxml')
        result = {"description": None, "salary_min": None,
                  "salary_max": None, "salary_text": None}

        # ── Extract Description ───────────────────────────────────
        desc_selectors = [
            ('div', {'class': lambda c: c and 'show-more-less-html' in c}),
            ('div', {'class': lambda c: c and 'description' in str(c).lower()}),
            ('section', {'class': lambda c: c and 'description' in str(c).lower()}),
            ('div', {'class': 'core-section-container'}),
        ]

        for tag, attrs in desc_selectors:
            el = soup.find(tag, attrs)
            if el:
                text = el.get_text(separator='\n', strip=True)
                if len(text) > 50:
                    result["description"] = text
                    break

        # ── Extract Salary from HTML elements ─────────────────────
        salary_selectors = [
            ('div', {'class': lambda c: c and 'salary' in str(c).lower()
                     and 'compensation' in str(c).lower()}),
            ('div', {'class': lambda c: c and 'salary-main-rail' in str(c)}),
            ('span', {'class': lambda c: c and 'compensation' in str(c).lower()}),
            ('div', {'class': lambda c: c and 'salary' in str(c).lower()}),
        ]

        for tag, attrs in salary_selectors:
            el = soup.find(tag, attrs)
            if el:
                salary_text = el.get_text(strip=True)
                if salary_text and '$' in salary_text:
                    result["salary_text"] = salary_text
                    self._parse_salary_range(salary_text, result)
                    break

        # ── Extract from JSON-LD ──────────────────────────────────
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string)
                if not isinstance(data, dict):
                    continue

                # Description fallback
                if not result["description"]:
                    desc = data.get('description', '')
                    if desc and len(desc) > 50:
                        desc_soup = BeautifulSoup(desc, 'lxml')
                        result["description"] = desc_soup.get_text(
                            separator='\n', strip=True
                        )

                # Salary from baseSalary (Schema.org JobPosting)
                if not result["salary_min"]:
                    base_salary = data.get('baseSalary', {})
                    if isinstance(base_salary, dict):
                        value = base_salary.get('value', {})
                        if isinstance(value, dict):
                            unit = value.get('unitText', 'YEAR')
                            min_val = value.get('minValue')
                            max_val = value.get('maxValue')

                            if min_val is not None:
                                result["salary_min"] = float(min_val)
                                if unit == 'HOUR':
                                    result["salary_min"] *= 2080
                            if max_val is not None:
                                result["salary_max"] = float(max_val)
                                if unit == 'HOUR':
                                    result["salary_max"] *= 2080
                            if not result["salary_text"]:
                                currency = base_salary.get('currency', 'USD')
                                if result["salary_min"] and result["salary_max"]:
                                    result["salary_text"] = (
                                        f"${result['salary_min']:,.0f} - "
                                        f"${result['salary_max']:,.0f}"
                                    )
            except Exception:
                pass

        # ── Salary from description text (last resort) ────────────
        if not result["salary_min"] and result["description"]:
            self._extract_salary_from_text(result["description"], result)

        return result if result["description"] else None

    def _parse_salary_range(self, text: str, result: Dict):
        """Parse salary range from text like '$120,000 - $150,000/yr'."""
        text_clean = text.replace(',', '').replace('$', '')

        match = re.search(
            r'(\d+(?:\.\d+)?)\s*[kK]?\s*[-–/to]+\s*(\d+(?:\.\d+)?)\s*[kK]?',
            text_clean
        )
        if match:
            low = float(match.group(1))
            high = float(match.group(2))
            if low < 1000:
                low *= 1000
            if high < 1000:
                high *= 1000
            if 'hour' in text.lower() or '/hr' in text.lower():
                low *= 2080
                high *= 2080
            result["salary_min"] = low
            result["salary_max"] = high

    def _extract_salary_from_text(self, text: str, result: Dict):
        """Extract salary range from description body text.

        Handles many real-world formats:
          $90,000 - $150,000          (comma-formatted)
          $90000 - $150000 USD        (unformatted)
          $60.00 - 64.54/hr           (hourly, missing $ on second number)
          $120K - $150K               (K shorthand)
          $95,000 to $115,000         ('to' separator)
          $70,000.00 to $100,000.00   (decimals + 'to')
        """
        # Pattern supports: optional $ on second number, unformatted large numbers,
        # comma-formatted numbers, decimals, K suffix, hourly rates,
        # unit suffixes like /yr, /hr between number and separator
        pattern = (
            r'\$\s*(\d[\d,]*(?:\.\d+)?)\s*[kK]?'            # First number: $NNN,NNN.NN
            r'(?:/(?:yr|hr|hour|year|mo))?\s*'               # Optional unit suffix: /yr, /hr
            r'(?:[-–—~]|\s+to\s+)\s*'                        # Separator: dash, en-dash, em-dash, ~, or "to"
            r'\$?\s*(\d[\d,]*(?:\.\d+)?)\s*[kK]?'            # Second number: optional $
        )
        match = re.search(pattern, text)
        if match:
            low_str = match.group(1).replace(',', '')
            high_str = match.group(2).replace(',', '')
            low = float(low_str)
            high = float(high_str)

            # Detect hourly rates from match text and surrounding context
            matched_full = match.group(0).lower()
            context_after = text[match.end():match.end()+30].lower()
            context_before = text[max(0,match.start()-30):match.start()].lower()
            full_context = context_before + matched_full + context_after

            # /yr or /year or "per year" means annual — NOT hourly
            is_annual = any(kw in full_context for kw in ['/yr', '/year', 'per year', 'annual'])
            is_hourly = any(kw in full_context for kw in ['/hr', 'per hour', 'hourly', '/hour'])

            # Small values (< $500) are hourly UNLESS explicitly marked annual
            if low < 500 and high < 500 and not is_annual:
                is_hourly = True

            if is_hourly:
                low *= 2080   # 40 hrs/week × 52 weeks
                high *= 2080

            # K suffix handling (e.g., $120K)
            matched_text = match.group(0).lower()
            if 'k' in matched_text:
                if low < 1000:
                    low *= 1000
                if high < 1000:
                    high *= 1000

            # Ensure low < high
            if low > high:
                low, high = high, low

            # Sanity check: must be reasonable annual salary values
            if 20000 <= low <= 500000 and 20000 <= high <= 1000000:
                result["salary_min"] = low
                result["salary_max"] = high
                result["salary_text"] = match.group(0)

    def _fetch_description_only(self, url: str, source: str) -> Optional[str]:
        """Fetch just the description for non-LinkedIn sources."""
        if "indeed.com" in url:
            return self._fetch_indeed_description(url)
        elif "glassdoor.com" in url:
            return self._fetch_glassdoor_description(url)
        else:
            return self._fetch_generic_description(url)

    def _fetch_indeed_description(self, url: str) -> Optional[str]:
        from bs4 import BeautifulSoup
        html = self.fetch(url)
        if not html:
            return None
        soup = BeautifulSoup(html, 'lxml')
        for tag, attrs in [
            ('div', {'id': 'jobDescriptionText'}),
            ('div', {'class': lambda c: c and 'jobsearch-jobDescriptionText' in str(c)}),
        ]:
            el = soup.find(tag, attrs)
            if el:
                text = el.get_text(separator='\n', strip=True)
                if len(text) > 50:
                    return text
        return None

    def _fetch_glassdoor_description(self, url: str) -> Optional[str]:
        from bs4 import BeautifulSoup
        html = self.fetch(url)
        if not html:
            return None
        soup = BeautifulSoup(html, 'lxml')
        for tag, attrs in [
            ('div', {'class': lambda c: c and 'JobDetails' in str(c)}),
            ('div', {'class': 'desc'}),
        ]:
            el = soup.find(tag, attrs)
            if el:
                text = el.get_text(separator='\n', strip=True)
                if len(text) > 50:
                    return text
        return None

    def _fetch_generic_description(self, url: str) -> Optional[str]:
        from bs4 import BeautifulSoup
        import json
        html = self.fetch(url)
        if not html:
            return None
        soup = BeautifulSoup(html, 'lxml')

        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string)
                if isinstance(data, dict):
                    desc = data.get('description', '')
                    if desc and len(desc) > 50:
                        desc_soup = BeautifulSoup(desc, 'lxml')
                        return desc_soup.get_text(separator='\n', strip=True)
            except Exception:
                pass

        for selector in ['[class*="description"]', '[class*="job-details"]',
                         '[id*="description"]', 'article', '.content', 'main']:
            try:
                els = soup.select(selector)
                for el in els:
                    text = el.get_text(separator='\n', strip=True)
                    if len(text) > 100:
                        return text[:5000]
            except Exception:
                pass
        return None
