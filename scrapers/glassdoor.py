"""
Glassdoor scraper — primarily for company ratings and reviews.
Also searches for job listings.
"""
import re
import json
from typing import List, Optional
from urllib.parse import quote_plus
from bs4 import BeautifulSoup

from scrapers.base import BaseScraper
from storage.models import Job, Company


class GlassdoorScraper(BaseScraper):
    source_name = "glassdoor"
    base_url = "https://www.glassdoor.com"

    def search(self, title: str, location: str) -> List[Job]:
        """Search Glassdoor for jobs."""
        jobs = []
        title_encoded = quote_plus(title)
        location_encoded = quote_plus(location)

        url = (
            f"{self.base_url}/Job/"
            f"{location_encoded.replace('+', '-')}-"
            f"{title_encoded.replace('+', '-')}-"
            f"jobs-SRCH_IL.0,12_IC1138644.htm"
        )

        # Glassdoor is heavily JS-rendered
        html = self.fetch_with_playwright(url, wait_time=5000)
        if not html:
            # Try regular request as fallback
            html = self.fetch(url)

        if html:
            jobs = self._parse_job_results(html)

        return jobs

    def _parse_job_results(self, html: str) -> List[Job]:
        """Parse Glassdoor job search results."""
        jobs = []
        soup = BeautifulSoup(html, 'lxml')

        # Try JSON-LD first
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string)
                if isinstance(data, dict) and data.get('@type') == 'JobPosting':
                    job = self._parse_jsonld(data)
                    if job:
                        jobs.append(job)
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and item.get('@type') == 'JobPosting':
                            job = self._parse_jsonld(item)
                            if job:
                                jobs.append(job)
            except (json.JSONDecodeError, TypeError):
                continue

        # Parse HTML cards
        cards = soup.find_all('li', class_=re.compile(r'react-job-listing|JobsList'))
        if not cards:
            cards = soup.find_all('div', class_=re.compile(r'jobCard|JobCard'))

        for card in cards:
            job = self._parse_card(card)
            if job and job not in jobs:
                jobs.append(job)

        return jobs

    def _parse_jsonld(self, data: dict) -> Optional[Job]:
        """Parse JSON-LD job posting."""
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
            job.url = data.get('url', '')
            job.apply_url = job.url

            salary = data.get('baseSalary', {})
            if isinstance(salary, dict):
                value = salary.get('value', {})
                if isinstance(value, dict):
                    try:
                        job.salary_min = float(value.get('minValue', 0)) or None
                        job.salary_max = float(value.get('maxValue', 0)) or None
                    except (ValueError, TypeError):
                        pass

            return job if job.title else None
        except Exception:
            return None

    def _parse_card(self, card) -> Optional[Job]:
        """Parse a Glassdoor job card."""
        try:
            job = Job()
            job.source = self.source_name

            # Title
            title_el = card.find('a', class_=re.compile(r'jobTitle|job-title'))
            if not title_el:
                title_el = card.find('a', {'data-test': 'job-link'})
            if title_el:
                job.title = title_el.get_text(strip=True)
                href = title_el.get('href', '')
                if href.startswith('/'):
                    href = self.base_url + href
                job.url = href
                job.apply_url = href

            if not job.title:
                return None

            # Company
            company_el = card.find('span', class_=re.compile(r'EmployerProfile|employer'))
            if not company_el:
                company_el = card.find('div', {'data-test': 'emp-name'})
            if company_el:
                job.company = company_el.get_text(strip=True)

            # Location
            loc_el = card.find('span', class_=re.compile(r'location|loc'))
            if loc_el:
                job.location = loc_el.get_text(strip=True)

            # Salary
            sal_el = card.find('span', class_=re.compile(r'salary|compensation'))
            if sal_el:
                job.salary_text = sal_el.get_text(strip=True)
                self._extract_salary(job)

            # Remote
            if job.location and 'remote' in job.location.lower():
                job.is_remote = True

            # Easy apply
            easy = card.find(string=re.compile(r'Easy Apply', re.I))
            if easy:
                job.easy_apply = True

            return job
        except Exception:
            return None

    def scrape_company_rating(self, company_name: str) -> Optional[dict]:
        """
        Scrape Glassdoor company rating.
        Returns dict with rating, CEO approval, recommend to friend, etc.
        """
        query = quote_plus(company_name)
        url = f"{self.base_url}/Reviews/{query}-reviews-SRCH_KE0,{len(company_name)}.htm"

        html = self.fetch_with_playwright(url, wait_time=4000)
        if not html:
            html = self.fetch(url)
        if not html:
            return None

        soup = BeautifulSoup(html, 'lxml')

        result = {}

        # Overall rating
        rating_el = soup.find('div', class_=re.compile(r'ratingNum|v2__EIReviewsRatingsStylesV2__ratingNum'))
        if rating_el:
            try:
                result['glassdoor_rating'] = float(rating_el.get_text(strip=True))
            except ValueError:
                pass

        # CEO approval
        ceo_el = soup.find('text', string=re.compile(r'\d+%'))
        if not ceo_el:
            ceo_el = soup.find('tspan', string=re.compile(r'\d+%'))
        if ceo_el:
            try:
                pct = int(re.search(r'(\d+)', ceo_el.get_text()).group(1))
                result['ceo_approval'] = pct
            except (AttributeError, ValueError):
                pass

        # Recommend to friend
        recommend_el = soup.find(string=re.compile(r'Recommend to a Friend', re.I))
        if recommend_el:
            parent = recommend_el.find_parent()
            if parent:
                pct_el = parent.find(string=re.compile(r'\d+%'))
                if pct_el:
                    try:
                        result['recommend_to_friend'] = int(
                            re.search(r'(\d+)', pct_el).group(1)
                        )
                    except (AttributeError, ValueError):
                        pass

        return result if result else None

    def _extract_salary(self, job: Job):
        """Extract salary from Glassdoor salary text."""
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
