"""
LinkedIn public job search scraper.
Scrapes LinkedIn's public job listings (no login required for basic search).
"""
import re
import json
from typing import List, Optional
from urllib.parse import quote_plus
from bs4 import BeautifulSoup

from scrapers.base import BaseScraper
from storage.models import Job


class LinkedInScraper(BaseScraper):
    source_name = "linkedin"
    base_url = "https://www.linkedin.com"

    def search(self, title: str, location: str) -> List[Job]:
        """Search LinkedIn public job listings."""
        jobs = []
        title_encoded = quote_plus(title)
        location_encoded = quote_plus(location)

        # LinkedIn's public job search API endpoint
        # geoId for Charlotte, NC area
        # LinkedIn geoId: Charlotte, NC = 102264677
        geo_ids = {
            "charlotte, nc": "102264677",
            "cornelius, nc": "102264677",
            "huntersville, nc": "102264677",
            "davidson, nc": "102264677",
            "mooresville, nc": "102264677",
            "concord, nc": "102264677",
            "lake norman, nc": "102264677",
            "remote": "",
        }

        geo_id = geo_ids.get(location.lower(), "102264677")

        for start in range(0, 50, 25):  # Pages 1-2 (25 per page)
            if location.lower() != "remote" and geo_id:
                url = (
                    f"{self.base_url}/jobs-guest/jobs/api/seeMoreJobPostings/search?"
                    f"keywords={title_encoded}"
                    f"&location={location_encoded}"
                    f"&geoId={geo_id}"
                    f"&distance=50"
                    f"&sortBy=DD"
                    f"&f_TPR=r1209600"  # Past 2 weeks
                    f"&position=1&pageNum=0"
                    f"&start={start}"
                )
            else:
                url = (
                    f"{self.base_url}/jobs-guest/jobs/api/seeMoreJobPostings/search?"
                    f"keywords={title_encoded}"
                    f"&location=United+States"
                    f"&sortBy=DD"
                    f"&f_TPR=r1209600"
                    f"&f_WT=2"  # Remote filter
                    f"&start={start}"
                )

            html = self.fetch(url)
            if not html:
                break

            page_jobs = self._parse_results(html)
            if not page_jobs:
                break

            jobs.extend(page_jobs)

        return jobs

    def _parse_results(self, html: str) -> List[Job]:
        """Parse LinkedIn search results."""
        jobs = []
        soup = BeautifulSoup(html, 'lxml')

        # LinkedIn returns a list of job cards
        cards = soup.find_all('li')

        for card in cards:
            job = self._parse_card(card)
            if job:
                jobs.append(job)

        return jobs

    def _parse_card(self, card) -> Optional[Job]:
        """Parse a single LinkedIn job card."""
        try:
            job = Job()
            job.source = self.source_name

            # Title and URL
            title_link = card.find('a', class_=re.compile(r'base-card__full-link|job-card'))
            if not title_link:
                title_link = card.find('a')

            if title_link:
                job.url = title_link.get('href', '').split('?')[0]
                title_span = card.find('h3') or card.find('span', class_=re.compile(r'base-search-card__title'))
                if title_span:
                    job.title = title_span.get_text(strip=True)

            if not job.title:
                return None

            # Company
            company_el = card.find('h4') or card.find('a', class_=re.compile(r'base-search-card__subtitle'))
            if company_el:
                job.company = company_el.get_text(strip=True)

            # Location
            loc_el = card.find('span', class_=re.compile(r'job-search-card__location'))
            if loc_el:
                job.location = loc_el.get_text(strip=True)

                # Remote detection
                loc_lower = job.location.lower()
                if 'remote' in loc_lower:
                    job.is_remote = True
                if 'hybrid' in loc_lower:
                    job.is_hybrid = True

            # Posted date
            time_el = card.find('time')
            if time_el:
                job.posted_date = time_el.get('datetime', '') or time_el.get_text(strip=True)

            # Salary (LinkedIn sometimes shows salary)
            salary_el = card.find('span', class_=re.compile(r'job-search-card__salary'))
            if salary_el:
                job.salary_text = salary_el.get_text(strip=True)
                self._extract_salary(job)

            # Apply URL
            job.apply_url = job.url

            # LinkedIn has "Easy Apply" sometimes noted
            easy_apply = card.find(string=re.compile(r'Easy Apply', re.I))
            if easy_apply:
                job.easy_apply = True

            return job
        except Exception:
            return None

    def _extract_salary(self, job: Job):
        """Extract salary from LinkedIn salary text."""
        if not job.salary_text:
            return

        text = job.salary_text.replace(',', '').replace('$', '')
        match = re.search(r'(\d+(?:\.\d+)?)\s*[kK]?\s*[-–/to]+\s*(\d+(?:\.\d+)?)\s*[kK]?', text)
        if match:
            low = float(match.group(1))
            high = float(match.group(2))
            if low < 1000:
                low *= 1000
            if high < 1000:
                high *= 1000

            if 'hr' in text.lower() or 'hour' in text.lower():
                low *= 2080
                high *= 2080

            job.salary_min = low
            job.salary_max = high

    def get_job_details(self, job_url: str) -> Optional[str]:
        """Fetch full job description from a LinkedIn job page."""
        html = self.fetch(job_url)
        if not html:
            return None

        soup = BeautifulSoup(html, 'lxml')

        # Try to find job description
        desc_el = soup.find('div', class_=re.compile(r'description|show-more-less-html'))
        if desc_el:
            return desc_el.get_text(separator='\n', strip=True)

        return None
