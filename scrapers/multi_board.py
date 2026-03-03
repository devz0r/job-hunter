"""
Multi-board scraper — handles Monster, CareerBuilder, SimplyHired, Dice,
Ladders, BuiltIn, FlexJobs, USAJobs, TheMuse, and other boards.
Uses a common parsing approach since most job boards use similar HTML structures.
"""
import re
import json
from typing import List, Optional
from urllib.parse import quote_plus
from bs4 import BeautifulSoup

from scrapers.base import BaseScraper
from storage.models import Job


class MultiboardScraper(BaseScraper):
    """Scrapes multiple smaller job boards with a unified approach."""

    source_name = "multi_board"

    # Board configurations
    # NOTE: Indeed, Google Jobs, Glassdoor, ZipRecruiter, SimplyHired, and
    # CareerBuilder all use aggressive Cloudflare anti-bot that blocks even
    # stealth Playwright. We focus on boards that actually work.
    BOARDS = {
        "monster": {
            "url": "https://www.monster.com/jobs/search?q={title}&where={location}&page=1&so=m.s.sh",
            "needs_playwright": True,  # Monster requires JS rendering
        },
        "dice": {
            "url": "https://www.dice.com/jobs?q={title}&location={location}&countryCode=US&radius=50&radiusUnit=mi",
            "needs_playwright": True,
        },
        "builtin": {
            "url": "https://builtin.com/jobs?search={title}&location=charlotte-nc",
            "needs_playwright": True,
        },
    }

    def search(self, title: str, location: str) -> List[Job]:
        """Search all configured boards for a single title/location."""
        all_jobs = []

        for board_name, board_config in self.BOARDS.items():
            try:
                url = board_config["url"].format(
                    title=quote_plus(title),
                    location=quote_plus(location)
                )

                if board_config.get("needs_playwright"):
                    html = self.fetch_with_playwright(url, wait_time=4000)
                else:
                    html = self.fetch(url)

                if html:
                    jobs = self._parse_board_results(html, board_name)
                    all_jobs.extend(jobs)

            except Exception as e:
                print(f"  [{board_name}] Error: {e}")

        return all_jobs

    def search_all(self) -> List[Job]:
        """Search all boards with priority titles."""
        from rich.console import Console
        console = Console()

        all_jobs = []

        # Use fewer title/location combos for secondary boards
        priority_titles = [
            "Program Manager", "Senior Program Manager",
            "Project Manager", "Operations Manager",
            "Change Management Manager", "Director of Operations",
            "Implementation Manager", "PMO Manager",
        ]

        priority_locations = ["Charlotte, NC", "Remote"]

        total_searches = len(self.BOARDS) * len(priority_titles) * len(priority_locations)
        console.print(f"  [dim]Multi-board: ~{total_searches} searches across {len(self.BOARDS)} boards[/dim]")

        for board_name, board_config in self.BOARDS.items():
            board_jobs = []

            for title in priority_titles:
                for location in priority_locations:
                    try:
                        url = board_config["url"].format(
                            title=quote_plus(title),
                            location=quote_plus(location)
                        )

                        if board_config.get("needs_playwright"):
                            html = self.fetch_with_playwright(url, wait_time=4000)
                        else:
                            html = self.fetch(url)

                        if html:
                            jobs = self._parse_board_results(html, board_name)
                            board_jobs.extend(jobs)

                    except Exception as e:
                        pass  # Silent failure for secondary boards

            if board_jobs:
                console.print(f"  [green]{board_name}[/green]: {len(board_jobs)} results")
                all_jobs.extend(board_jobs)

        return all_jobs

    def _parse_board_results(self, html: str, board_name: str) -> List[Job]:
        """Universal parser for job board results."""
        jobs = []
        soup = BeautifulSoup(html, 'lxml')

        # Check for Cloudflare block
        title = soup.find('title')
        if title and 'just a moment' in title.get_text(strip=True).lower():
            return []  # Blocked by Cloudflare

        # Board-specific parsers
        if board_name == "monster":
            return self._parse_monster_results(soup)

        # Strategy 1: JSON-LD structured data (most reliable)
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string)
                items = []
                if isinstance(data, list):
                    items = data
                elif isinstance(data, dict):
                    if data.get('@type') == 'JobPosting':
                        items = [data]
                    elif data.get('@type') == 'ItemList':
                        items = [
                            i.get('item', i)
                            for i in data.get('itemListElement', [])
                        ]
                    elif 'itemListElement' in data:
                        items = [
                            i.get('item', i)
                            for i in data['itemListElement']
                        ]

                for item in items:
                    if isinstance(item, dict) and item.get('@type') == 'JobPosting':
                        job = self._parse_jsonld(item, board_name)
                        if job:
                            jobs.append(job)

            except (json.JSONDecodeError, TypeError):
                continue

        # Strategy 2: Common HTML card patterns
        if not jobs:
            # Try common job card selectors
            selectors = [
                'article[class*="job"]',
                'div[class*="job-card"]',
                'div[class*="job_result"]',
                'div[class*="JobCard"]',
                'li[class*="job"]',
                'div[data-job-id]',
                'div[class*="result"]',
            ]

            for selector in selectors:
                cards = soup.select(selector)
                if cards:
                    for card in cards[:20]:  # Limit per selector
                        job = self._parse_generic_card(card, board_name)
                        if job:
                            jobs.append(job)
                    break  # Use first successful selector

        return jobs

    def _parse_monster_results(self, soup) -> List[Job]:
        """Parse Monster.com Playwright-rendered job cards.
        Monster renders job cards as h2 headings containing both title and company."""
        jobs = []

        for h2 in soup.find_all('h2'):
            link = h2.find('a')
            if not link:
                continue

            href = link.get('href', '')
            if '/job-openings/' not in href and '/jobs/' not in href:
                continue

            # The h2 text contains "Title\nCompany" or "TitleCompany"
            full_text = h2.get_text(separator='|', strip=True)
            parts = full_text.split('|')

            title = parts[0].strip() if parts else ''
            company = parts[1].strip() if len(parts) > 1 else ''

            if not title or len(title) < 3:
                continue

            job = Job()
            job.source = "monster"
            job.title = title
            job.company = company

            if href.startswith('//'):
                href = 'https:' + href
            elif href.startswith('/'):
                href = 'https://www.monster.com' + href
            job.url = href
            job.apply_url = href

            # Look for location/salary/remote in parent container
            parent = h2.parent
            if parent:
                parent_text = parent.get_text(strip=True).lower()
                # Location detection
                for loc_el in parent.find_all('span'):
                    loc_text = loc_el.get_text(strip=True)
                    if any(w in loc_text.lower() for w in
                           ['nc', 'sc', 'remote', 'charlotte', 'hybrid',
                            'united states', ',']) and len(loc_text) < 60:
                        job.location = loc_text
                        break
                if 'remote' in parent_text:
                    job.is_remote = True
                if 'hybrid' in parent_text:
                    job.is_hybrid = True

            jobs.append(job)

        return jobs

    def _parse_jsonld(self, data: dict, board_name: str) -> Optional[Job]:
        """Parse JSON-LD job posting."""
        try:
            job = Job()
            job.source = board_name
            job.title = data.get('title', '')
            job.description = data.get('description', '')[:2000]

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
            job.apply_url = data.get('directApply', job.url) or job.url

            salary = data.get('baseSalary', {})
            if isinstance(salary, dict):
                value = salary.get('value', {})
                if isinstance(value, dict):
                    try:
                        job.salary_min = float(value.get('minValue', 0)) or None
                        job.salary_max = float(value.get('maxValue', 0)) or None
                        unit = str(value.get('unitText', 'YEAR')).upper()
                        if unit == 'HOUR':
                            if job.salary_min:
                                job.salary_min *= 2080
                            if job.salary_max:
                                job.salary_max *= 2080
                    except (ValueError, TypeError):
                        pass

            loc_type = str(data.get('jobLocationType', '')).upper()
            if 'TELECOMMUTE' in loc_type:
                job.is_remote = True

            emp_type = str(data.get('employmentType', '')).upper()
            if 'PART' in emp_type:
                return None  # Skip part-time

            return job if job.title else None
        except Exception:
            return None

    def _parse_generic_card(self, card, board_name: str) -> Optional[Job]:
        """Parse a generic job card by finding common elements."""
        try:
            job = Job()
            job.source = board_name

            # Find title (usually in h2/h3/a with prominent class)
            for tag in ['h2', 'h3', 'h4']:
                el = card.find(tag)
                if el:
                    link = el.find('a')
                    if link:
                        job.title = link.get_text(strip=True)
                        job.url = link.get('href', '')
                    else:
                        job.title = el.get_text(strip=True)
                    break

            if not job.title:
                link = card.find('a')
                if link:
                    text = link.get_text(strip=True)
                    if len(text) > 5 and len(text) < 150:
                        job.title = text
                        job.url = link.get('href', '')

            if not job.title:
                return None

            # Find company
            for cls_pattern in [r'company', r'org', r'employer']:
                el = card.find(class_=re.compile(cls_pattern, re.I))
                if el:
                    job.company = el.get_text(strip=True)
                    break

            # Find location
            for cls_pattern in [r'location', r'loc', r'city']:
                el = card.find(class_=re.compile(cls_pattern, re.I))
                if el:
                    job.location = el.get_text(strip=True)
                    break

            # Find salary
            for cls_pattern in [r'salary', r'pay', r'compensation']:
                el = card.find(class_=re.compile(cls_pattern, re.I))
                if el:
                    job.salary_text = el.get_text(strip=True)
                    break

            # Remote detection
            card_text = card.get_text(strip=True).lower()
            if 'remote' in card_text:
                job.is_remote = True
            if 'hybrid' in card_text:
                job.is_hybrid = True

            job.apply_url = job.url
            return job
        except Exception:
            return None


class USAJobsScraper(BaseScraper):
    """Scraper for USAJobs.gov (federal government positions)."""

    source_name = "usajobs"
    base_url = "https://data.usajobs.gov/api/search"

    def search(self, title: str, location: str) -> List[Job]:
        """Search USAJobs API (public, no key required for basic search)."""
        # USAJobs has a public API
        params = {
            "Keyword": title,
            "LocationName": "Charlotte, North Carolina" if "charlotte" in location.lower() else location,
            "ResultsPerPage": 25,
            "SortField": "DatePosted",
            "SortDirection": "Desc",
        }

        # USAJobs requires specific headers
        self.session.headers.update({
            "Host": "data.usajobs.gov",
            "User-Agent": "cynthia.francis.job.search@email.com",
        })

        try:
            resp = self.session.get(self.base_url, params=params, timeout=30)
            if resp.status_code != 200:
                return []

            data = resp.json()
            results = data.get("SearchResult", {}).get("SearchResultItems", [])

            jobs = []
            for item in results:
                job = self._parse_result(item)
                if job:
                    jobs.append(job)

            return jobs
        except Exception as e:
            print(f"  [USAJobs] Error: {e}")
            return []

    def _parse_result(self, item: dict) -> Optional[Job]:
        """Parse a USAJobs search result."""
        try:
            matched = item.get("MatchedObjectDescriptor", {})

            job = Job()
            job.source = self.source_name
            job.title = matched.get("PositionTitle", "")
            job.company = matched.get("OrganizationName", "US Federal Government")
            job.url = matched.get("PositionURI", "")
            job.apply_url = matched.get("ApplyURI", [""])[0] if matched.get("ApplyURI") else job.url
            job.description = matched.get("QualificationSummary", "")

            # Location
            locations = matched.get("PositionLocation", [])
            if locations:
                loc = locations[0]
                city = loc.get("CityName", "")
                state = loc.get("CountrySubDivisionCode", "")
                job.location = f"{city}, {state}"

            # Salary
            remuneration = matched.get("PositionRemuneration", [])
            if remuneration:
                pay = remuneration[0]
                try:
                    job.salary_min = float(pay.get("MinimumRange", 0))
                    job.salary_max = float(pay.get("MaximumRange", 0))
                    if pay.get("RateIntervalCode") == "Per Hour":
                        job.salary_min *= 2080
                        job.salary_max *= 2080
                except (ValueError, TypeError):
                    pass

            # Date
            job.posted_date = matched.get("PositionStartDate", "")[:10]

            # Remote
            schedule = matched.get("PositionSchedule", [])
            if any("telework" in str(s).lower() or "remote" in str(s).lower()
                   for s in schedule):
                job.is_remote = True

            return job if job.title else None
        except Exception:
            return None

    def search_all(self) -> List[Job]:
        """Search USAJobs with relevant titles."""
        from rich.console import Console
        console = Console()

        all_jobs = []
        titles = [
            "Program Manager", "Project Manager", "Operations Manager",
            "Management Analyst", "Program Analyst", "Management and Program Analyst",
            "Logistics Management", "Supply Chain",
        ]

        for title in titles:
            try:
                jobs = self.search(title, "Charlotte, NC")
                if jobs:
                    console.print(f"  [green]USAJobs[/green]: '{title}' → {len(jobs)} results")
                    all_jobs.extend(jobs)
            except Exception as e:
                console.print(f"  [red]USAJobs[/red]: Error for '{title}': {e}")

        return all_jobs
