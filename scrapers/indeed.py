"""
Indeed job scraper.
Scrapes Indeed search results pages for job listings.
"""
import re
import json
from typing import List, Optional
from urllib.parse import quote_plus
from bs4 import BeautifulSoup

from scrapers.base import BaseScraper
from storage.models import Job


class IndeedScraper(BaseScraper):
    source_name = "indeed"
    base_url = "https://www.indeed.com"

    def search(self, title: str, location: str) -> List[Job]:
        """Search Indeed for jobs."""
        jobs = []
        title_encoded = quote_plus(title)
        location_encoded = quote_plus(location)

        for start in range(0, 50, 10):  # Pages 1-5
            url = (
                f"{self.base_url}/jobs?"
                f"q={title_encoded}"
                f"&l={location_encoded}"
                f"&sort=date"
                f"&fromage=14"  # Last 14 days
                f"&start={start}"
            )

            # Indeed blocks basic HTTP - use Playwright
            html = self.fetch_with_playwright(url, wait_selector='div.job_seen_beacon', wait_time=4000)
            if not html:
                html = self.fetch(url)  # Fallback
            if not html:
                break

            page_jobs = self._parse_results(html)
            if not page_jobs:
                break

            jobs.extend(page_jobs)

        return jobs

    def _parse_results(self, html: str) -> List[Job]:
        """Parse Indeed search results HTML."""
        jobs = []
        soup = BeautifulSoup(html, 'lxml')

        # Try to find job data in script tags (Indeed embeds JSON)
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string)
                if isinstance(data, list):
                    for item in data:
                        job = self._parse_ld_json(item)
                        if job:
                            jobs.append(job)
                elif isinstance(data, dict):
                    job = self._parse_ld_json(data)
                    if job:
                        jobs.append(job)
            except (json.JSONDecodeError, TypeError):
                continue

        # Also try parsing from mosaic provider data
        for script in soup.find_all('script'):
            if script.string and 'mosaic-provider-jobcards' in str(script.string):
                try:
                    # Extract JSON data from the script
                    text = script.string
                    match = re.search(r'window\.mosaic\.providerData\["mosaic-provider-jobcards"\]\s*=\s*({.*?});', text, re.DOTALL)
                    if match:
                        data = json.loads(match.group(1))
                        results = data.get('metaData', {}).get('mosaicProviderJobCardsModel', {}).get('results', [])
                        for result in results:
                            job = self._parse_mosaic_result(result)
                            if job:
                                jobs.append(job)
                except (json.JSONDecodeError, AttributeError):
                    pass

        # Fallback: parse HTML cards directly
        if not jobs:
            cards = soup.find_all('div', class_=re.compile(r'job_seen_beacon|cardOutline|resultContent'))
            for card in cards:
                job = self._parse_html_card(card)
                if job:
                    jobs.append(job)

        return jobs

    def _parse_ld_json(self, data: dict) -> Optional[Job]:
        """Parse a structured data JSON-LD job posting."""
        if data.get('@type') != 'JobPosting':
            return None

        try:
            job = Job()
            job.source = self.source_name
            job.title = data.get('title', '')
            job.description = data.get('description', '')

            # Company
            org = data.get('hiringOrganization', {})
            if isinstance(org, dict):
                job.company = org.get('name', '')

            # Location
            loc = data.get('jobLocation', {})
            if isinstance(loc, dict):
                address = loc.get('address', {})
                if isinstance(address, dict):
                    city = address.get('addressLocality', '')
                    state = address.get('addressRegion', '')
                    job.location = f"{city}, {state}" if city else ''

            # Salary
            salary = data.get('baseSalary', {})
            if isinstance(salary, dict):
                value = salary.get('value', {})
                if isinstance(value, dict):
                    job.salary_min = self._normalize_salary(value.get('minValue'))
                    job.salary_max = self._normalize_salary(value.get('maxValue'))
                    unit = value.get('unitText', 'YEAR')
                    if unit == 'HOUR' and job.salary_min:
                        job.salary_min *= 2080
                    if unit == 'HOUR' and job.salary_max:
                        job.salary_max *= 2080

            # Dates
            job.posted_date = data.get('datePosted', '')

            # URL
            job.url = data.get('url', '')
            job.apply_url = job.url

            # Remote
            job_loc_type = data.get('jobLocationType', '')
            if 'TELECOMMUTE' in str(job_loc_type).upper():
                job.is_remote = True

            return job
        except Exception:
            return None

    def _parse_mosaic_result(self, result: dict) -> Optional[Job]:
        """Parse a result from Indeed's mosaic data."""
        try:
            job = Job()
            job.source = self.source_name
            job.title = result.get('title', '')
            job.company = result.get('company', '')
            job.location = result.get('formattedLocation', '')
            job.description = result.get('snippet', '')
            job.posted_date = result.get('formattedRelativeTime', '')
            job.external_id = result.get('jobkey', '')

            if job.external_id:
                job.url = f"{self.base_url}/viewjob?jk={job.external_id}"
                job.apply_url = job.url

            # Salary
            salary_text = result.get('extractedSalary', {})
            if salary_text:
                job.salary_min = self._normalize_salary(salary_text.get('min'))
                job.salary_max = self._normalize_salary(salary_text.get('max'))
                sal_type = salary_text.get('type', '')
                if sal_type == 'hourly':
                    if job.salary_min:
                        job.salary_min *= 2080
                    if job.salary_max:
                        job.salary_max *= 2080

            return job if job.title else None
        except Exception:
            return None

    def _parse_html_card(self, card) -> Optional[Job]:
        """Parse a job card from HTML."""
        try:
            job = Job()
            job.source = self.source_name

            # Title
            title_el = card.find('h2', class_=re.compile(r'jobTitle|title'))
            if title_el:
                link = title_el.find('a') or title_el.find('span')
                job.title = (link.get_text(strip=True) if link
                            else title_el.get_text(strip=True))
                if link and link.get('href'):
                    href = link['href']
                    if href.startswith('/'):
                        href = self.base_url + href
                    job.url = href

            # Company
            company_el = card.find('span', class_=re.compile(r'company|companyName'))
            if company_el:
                job.company = company_el.get_text(strip=True)

            # Location
            loc_el = card.find('div', class_=re.compile(r'companyLocation|location'))
            if loc_el:
                job.location = loc_el.get_text(strip=True)
                if 'remote' in job.location.lower():
                    job.is_remote = True
                if 'hybrid' in job.location.lower():
                    job.is_hybrid = True

            # Salary
            sal_el = card.find('div', class_=re.compile(r'salary|metadata'))
            if sal_el:
                job.salary_text = sal_el.get_text(strip=True)
                self._extract_salary_from_text(job)

            # Snippet
            snippet_el = card.find('div', class_=re.compile(r'job-snippet'))
            if snippet_el:
                job.description = snippet_el.get_text(strip=True)

            # Date
            date_el = card.find('span', class_=re.compile(r'date'))
            if date_el:
                job.posted_date = date_el.get_text(strip=True)

            return job if job.title else None
        except Exception:
            return None

    def _normalize_salary(self, value) -> Optional[float]:
        """Normalize salary value to annual float."""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _extract_salary_from_text(self, job: Job):
        """Extract salary numbers from text like '$100K - $150K'."""
        if not job.salary_text:
            return

        text = job.salary_text.replace(',', '').replace('$', '')

        # Match patterns like "100K - 150K" or "100,000 - 150,000"
        match = re.search(r'(\d+(?:\.\d+)?)\s*[kK]?\s*[-–to]+\s*(\d+(?:\.\d+)?)\s*[kK]?', text)
        if match:
            low = float(match.group(1))
            high = float(match.group(2))

            if low < 1000:
                low *= 1000
            if high < 1000:
                high *= 1000

            # Check if hourly
            if 'hour' in job.salary_text.lower() or 'hr' in job.salary_text.lower():
                low *= 2080
                high *= 2080

            job.salary_min = low
            job.salary_max = high
