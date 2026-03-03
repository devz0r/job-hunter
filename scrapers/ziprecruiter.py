"""
ZipRecruiter job scraper.
"""
import re
import json
from typing import List, Optional
from urllib.parse import quote_plus
from bs4 import BeautifulSoup

from scrapers.base import BaseScraper
from storage.models import Job


class ZipRecruiterScraper(BaseScraper):
    source_name = "ziprecruiter"
    base_url = "https://www.ziprecruiter.com"

    def search(self, title: str, location: str) -> List[Job]:
        """Search ZipRecruiter for jobs."""
        jobs = []
        title_encoded = quote_plus(title)
        location_encoded = quote_plus(location)

        url = (
            f"{self.base_url}/jobs-search?"
            f"search={title_encoded}"
            f"&location={location_encoded}"
            f"&days=14"
            f"&radius=50"
        )

        html = self.fetch(url)
        if html:
            jobs = self._parse_results(html)

        return jobs

    def _parse_results(self, html: str) -> List[Job]:
        """Parse ZipRecruiter search results."""
        jobs = []
        soup = BeautifulSoup(html, 'lxml')

        # Try JSON-LD
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string)
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and item.get('@type') == 'JobPosting':
                            job = self._parse_jsonld(item)
                            if job:
                                jobs.append(job)
                elif isinstance(data, dict):
                    if data.get('@type') == 'JobPosting':
                        job = self._parse_jsonld(data)
                        if job:
                            jobs.append(job)
                    elif data.get('@type') == 'ItemList':
                        for item in data.get('itemListElement', []):
                            if isinstance(item, dict):
                                listing = item.get('item', item)
                                if listing.get('@type') == 'JobPosting':
                                    job = self._parse_jsonld(listing)
                                    if job:
                                        jobs.append(job)
            except (json.JSONDecodeError, TypeError):
                continue

        # Parse HTML cards as fallback
        if not jobs:
            cards = soup.find_all('article', class_=re.compile(r'job_result|clV2'))
            if not cards:
                cards = soup.find_all('div', class_=re.compile(r'job_content|job-listing'))

            for card in cards:
                job = self._parse_card(card)
                if job:
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
            if isinstance(loc, list):
                loc = loc[0] if loc else {}
            if isinstance(loc, dict):
                address = loc.get('address', {})
                if isinstance(address, dict):
                    city = address.get('addressLocality', '')
                    state = address.get('addressRegion', '')
                    job.location = f"{city}, {state}" if city else ''

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
                        unit = value.get('unitText', 'YEAR').upper()
                        if unit == 'HOUR':
                            if job.salary_min:
                                job.salary_min *= 2080
                            if job.salary_max:
                                job.salary_max *= 2080
                    except (ValueError, TypeError):
                        pass

            if 'TELECOMMUTE' in str(data.get('jobLocationType', '')).upper():
                job.is_remote = True

            return job if job.title else None
        except Exception:
            return None

    def _parse_card(self, card) -> Optional[Job]:
        """Parse a ZipRecruiter job card."""
        try:
            job = Job()
            job.source = self.source_name

            title_el = card.find('a', class_=re.compile(r'job_link|jobTitle'))
            if not title_el:
                title_el = card.find('h2')
                if title_el:
                    title_el = title_el.find('a') or title_el

            if title_el:
                job.title = title_el.get_text(strip=True)
                href = title_el.get('href', '')
                if href:
                    if href.startswith('/'):
                        href = self.base_url + href
                    job.url = href
                    job.apply_url = href

            if not job.title:
                return None

            company_el = card.find('a', class_=re.compile(r'company_name|t_org_link'))
            if not company_el:
                company_el = card.find('p', class_=re.compile(r'company'))
            if company_el:
                job.company = company_el.get_text(strip=True)

            loc_el = card.find('span', class_=re.compile(r'location'))
            if not loc_el:
                loc_el = card.find('p', class_=re.compile(r'location'))
            if loc_el:
                job.location = loc_el.get_text(strip=True)

            sal_el = card.find('span', class_=re.compile(r'salary'))
            if sal_el:
                job.salary_text = sal_el.get_text(strip=True)

            if job.location and 'remote' in job.location.lower():
                job.is_remote = True

            # One-click apply
            apply_btn = card.find('button', string=re.compile(r'1-Click|Quick Apply|Easy Apply', re.I))
            if apply_btn:
                job.easy_apply = True

            return job
        except Exception:
            return None
