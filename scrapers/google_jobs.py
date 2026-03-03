"""
Google Jobs scraper.
Google Jobs is the best aggregator — it indexes Indeed, LinkedIn, ZipRecruiter,
Glassdoor, company career pages, and many more sources.
Uses Playwright since Google Jobs is entirely JS-rendered.
"""
import re
import json
from typing import List, Optional
from urllib.parse import quote_plus
from bs4 import BeautifulSoup

from scrapers.base import BaseScraper
from storage.models import Job


class GoogleJobsScraper(BaseScraper):
    source_name = "google_jobs"
    base_url = "https://www.google.com"

    def search(self, title: str, location: str) -> List[Job]:
        """Search Google Jobs."""
        jobs = []
        query = f"{title} jobs near {location}"
        query_encoded = quote_plus(query)

        url = f"{self.base_url}/search?q={query_encoded}&ibp=htl;jobs"

        # Google Jobs requires JS rendering
        html = self.fetch_with_playwright(
            url,
            wait_selector='div[role="treeitem"]',
            wait_time=5000
        )

        if not html:
            # Fallback: try simpler Google search for job listings
            return self._fallback_search(title, location)

        jobs = self._parse_results(html)
        return jobs

    def _parse_results(self, html: str) -> List[Job]:
        """Parse Google Jobs results."""
        jobs = []
        soup = BeautifulSoup(html, 'lxml')

        # Google Jobs renders job cards as tree items
        cards = soup.find_all('div', role='treeitem')
        if not cards:
            # Try alternative selectors
            cards = soup.find_all('li', class_=re.compile(r'iFjolb'))
            if not cards:
                cards = soup.find_all('div', class_=re.compile(r'PwjeAc|gws-plugins'))

        for card in cards:
            job = self._parse_card(card)
            if job:
                jobs.append(job)

        # Also try to extract from embedded JSON data
        json_jobs = self._extract_from_scripts(soup)
        jobs.extend(json_jobs)

        return jobs

    def _parse_card(self, card) -> Optional[Job]:
        """Parse a Google Jobs card."""
        try:
            job = Job()
            job.source = self.source_name

            # Title
            title_el = card.find('div', class_=re.compile(r'BjJfJf|title'))
            if not title_el:
                title_el = card.find('h2') or card.find('div', role='heading')
            if title_el:
                job.title = title_el.get_text(strip=True)

            if not job.title:
                # Try getting text from first prominent element
                all_text = card.get_text(separator='|', strip=True).split('|')
                if all_text:
                    job.title = all_text[0][:100]

            if not job.title:
                return None

            # Company
            company_el = card.find('div', class_=re.compile(r'vNEEBe|company'))
            if company_el:
                job.company = company_el.get_text(strip=True)
            else:
                # Try second prominent text element
                spans = card.find_all('span')
                for span in spans:
                    text = span.get_text(strip=True)
                    if text and text != job.title and len(text) < 60:
                        job.company = text
                        break

            # Location
            loc_el = card.find('div', class_=re.compile(r'Qk80Jf|location'))
            if loc_el:
                job.location = loc_el.get_text(strip=True)

            # Remote detection
            if job.location:
                loc_lower = job.location.lower()
                if 'remote' in loc_lower:
                    job.is_remote = True
                if 'hybrid' in loc_lower:
                    job.is_hybrid = True

            # Posted date
            date_el = card.find('span', class_=re.compile(r'LL4CDc|date'))
            if date_el:
                job.posted_date = date_el.get_text(strip=True)

            # Salary (Google sometimes shows salary)
            salary_el = card.find('span', class_=re.compile(r'salary|pay'))
            if salary_el:
                job.salary_text = salary_el.get_text(strip=True)
                self._extract_salary(job)

            return job
        except Exception:
            return None

    def _extract_from_scripts(self, soup) -> List[Job]:
        """Extract job data from Google's embedded script data."""
        jobs = []

        for script in soup.find_all('script'):
            if not script.string:
                continue

            # Look for job listing data in script tags
            text = script.string
            if 'JobPosting' in text or 'jobTitle' in text:
                try:
                    # Try to parse as JSON-LD
                    data = json.loads(text)
                    if isinstance(data, dict) and data.get('@type') == 'JobPosting':
                        job = self._parse_jsonld(data)
                        if job:
                            jobs.append(job)
                except (json.JSONDecodeError, TypeError):
                    pass

        return jobs

    def _parse_jsonld(self, data: dict) -> Optional[Job]:
        """Parse JSON-LD job posting data."""
        try:
            job = Job()
            job.source = self.source_name
            job.title = data.get('title', '')
            job.description = data.get('description', '')

            org = data.get('hiringOrganization', {})
            if isinstance(org, dict):
                job.company = org.get('name', '')

            loc = data.get('jobLocation', {})
            if isinstance(loc, dict):
                address = loc.get('address', {})
                if isinstance(address, dict):
                    city = address.get('addressLocality', '')
                    state = address.get('addressRegion', '')
                    job.location = f"{city}, {state}"

            job.posted_date = data.get('datePosted', '')

            salary = data.get('baseSalary', {})
            if isinstance(salary, dict):
                value = salary.get('value', {})
                if isinstance(value, dict):
                    job.salary_min = self._to_float(value.get('minValue'))
                    job.salary_max = self._to_float(value.get('maxValue'))

            return job if job.title else None
        except Exception:
            return None

    def _fallback_search(self, title: str, location: str) -> List[Job]:
        """Fallback: search Google directly and parse regular results for job listings."""
        query = f'"{title}" "charlotte" OR "cornelius" OR "remote" site:indeed.com OR site:linkedin.com/jobs OR site:glassdoor.com -intitle:resume -intitle:profile'
        url = f"{self.base_url}/search?q={quote_plus(query)}"

        html = self.fetch(url)
        if not html:
            return []

        jobs = []
        soup = BeautifulSoup(html, 'lxml')

        for result in soup.find_all('div', class_='g'):
            link_el = result.find('a')
            if link_el and link_el.get('href'):
                href = link_el['href']
                if any(d in href for d in ['indeed.com', 'linkedin.com/jobs', 'glassdoor.com']):
                    title_el = result.find('h3')
                    snippet_el = result.find('div', class_=re.compile(r'VwiC3b'))

                    if title_el:
                        job = Job()
                        job.source = "google_search"
                        job.title = title_el.get_text(strip=True)
                        job.url = href
                        job.apply_url = href
                        if snippet_el:
                            job.description = snippet_el.get_text(strip=True)
                        # Try to extract company from title
                        # Format often: "Job Title - Company - Location"
                        parts = job.title.split(' - ')
                        if len(parts) >= 2:
                            job.title = parts[0].strip()
                            job.company = parts[1].strip()
                        if len(parts) >= 3:
                            job.location = parts[2].strip()

                        jobs.append(job)

        return jobs

    def _extract_salary(self, job: Job):
        """Extract salary from text."""
        if not job.salary_text:
            return
        text = job.salary_text.replace(',', '').replace('$', '')
        match = re.search(r'(\d+(?:\.\d+)?)\s*[kK]?\s*[-–to]+\s*(\d+(?:\.\d+)?)\s*[kK]?', text)
        if match:
            low = float(match.group(1))
            high = float(match.group(2))
            if low < 1000:
                low *= 1000
            if high < 1000:
                high *= 1000
            if 'hour' in text.lower():
                low *= 2080
                high *= 2080
            job.salary_min = low
            job.salary_max = high

    def _to_float(self, value) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
