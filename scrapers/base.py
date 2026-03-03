"""
Base scraper with shared infrastructure:
- Rate limiting with randomized delays
- User-Agent rotation
- Retry logic with exponential backoff
- Cookie/session persistence
- Error handling
"""
import time
import random
import requests
from abc import ABC, abstractmethod
from typing import List, Optional
from datetime import datetime

from storage.models import Job
import config

# Realistic browser user agents
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:123.0) Gecko/20100101 Firefox/123.0",
]


class BaseScraper(ABC):
    """Base class for all job scrapers."""

    source_name: str = "unknown"
    base_url: str = ""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(self._get_headers())
        self._last_request_time = 0
        self._request_count = 0

    def _get_headers(self) -> dict:
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }

    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        delay = random.uniform(config.REQUEST_DELAY_MIN, config.REQUEST_DELAY_MAX)
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self._last_request_time = time.time()
        self._request_count += 1

        # Rotate user agent occasionally
        if self._request_count % 10 == 0:
            self.session.headers["User-Agent"] = random.choice(USER_AGENTS)

    def fetch(self, url: str, params: dict = None) -> Optional[str]:
        """Fetch a URL with rate limiting and retries."""
        for attempt in range(config.MAX_RETRIES):
            try:
                self._rate_limit()
                resp = self.session.get(
                    url, params=params,
                    timeout=config.REQUEST_TIMEOUT,
                    allow_redirects=True
                )

                if resp.status_code == 200:
                    return resp.text
                elif resp.status_code == 429:
                    # Rate limited — back off
                    wait = (2 ** attempt) * 10 + random.uniform(5, 15)
                    print(f"  [Rate limited by {self.source_name}] Waiting {wait:.0f}s...")
                    time.sleep(wait)
                elif resp.status_code in (403, 401):
                    print(f"  [Blocked by {self.source_name}] Status {resp.status_code}")
                    return None
                elif resp.status_code >= 500:
                    wait = (2 ** attempt) * 5
                    print(f"  [Server error {resp.status_code}] Retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    print(f"  [Unexpected status {resp.status_code} from {self.source_name}]")
                    return None

            except requests.Timeout:
                print(f"  [Timeout from {self.source_name}] Attempt {attempt + 1}")
                time.sleep(2 ** attempt)
            except requests.ConnectionError as e:
                print(f"  [Connection error from {self.source_name}] {e}")
                time.sleep(2 ** attempt)
            except Exception as e:
                print(f"  [Error from {self.source_name}] {e}")
                return None

        print(f"  [Failed after {config.MAX_RETRIES} attempts from {self.source_name}]")
        return None

    def fetch_with_playwright(self, url: str, wait_selector: str = None,
                               wait_time: int = 3000) -> Optional[str]:
        """Fetch a page using Playwright (headless browser) for JS-heavy sites.
        Uses playwright-stealth to avoid Cloudflare and anti-bot detection."""
        try:
            from playwright.sync_api import sync_playwright
            from playwright_stealth import Stealth

            stealth = Stealth()

            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                    ],
                )
                context = browser.new_context(
                    user_agent=random.choice(USER_AGENTS),
                    viewport={"width": 1920, "height": 1080},
                    locale="en-US",
                    java_script_enabled=True,
                )
                page = context.new_page()
                stealth.apply_stealth_sync(page)

                page.goto(url, wait_until="domcontentloaded", timeout=30000)

                if wait_selector:
                    try:
                        page.wait_for_selector(wait_selector, timeout=10000)
                    except Exception:
                        pass  # Continue even if selector not found

                page.wait_for_timeout(wait_time)

                # Check for Cloudflare "Just a moment..." and wait longer
                content = page.content()
                if "Just a moment" in content or "challenge-platform" in content:
                    page.wait_for_timeout(8000)  # Wait for CF challenge
                    content = page.content()

                html = content
                browser.close()
                return html

        except ImportError:
            print("[WARNING] Playwright/stealth not installed. Falling back to requests.")
            return self.fetch(url)
        except Exception as e:
            print(f"  [Playwright error] {e}")
            return None

    @abstractmethod
    def search(self, title: str, location: str) -> List[Job]:
        """Search for jobs. Must be implemented by subclasses."""
        pass

    def search_all(self) -> List[Job]:
        """Run all configured searches for this source."""
        from rich.console import Console
        console = Console()

        all_jobs = []
        titles = config.TARGET_JOB_TITLES
        locations = config.SEARCH_LOCATIONS

        # Use a subset of searches to avoid excessive requests
        # Prioritize the most important title+location combos
        priority_titles = titles[:15]  # Top 15 most relevant titles
        priority_locations = locations[:5]  # Top 5 locations

        total = len(priority_titles) * len(priority_locations)
        console.print(f"  [dim]{self.source_name}: Running {total} searches[/dim]")

        for title in priority_titles:
            for location in priority_locations:
                try:
                    jobs = self.search(title, location)
                    if jobs:
                        console.print(
                            f"  [green]{self.source_name}[/green]: "
                            f"'{title}' in {location} → {len(jobs)} results"
                        )
                        all_jobs.extend(jobs)
                except Exception as e:
                    console.print(
                        f"  [red]{self.source_name}[/red]: "
                        f"Error searching '{title}' in {location}: {e}"
                    )

        console.print(
            f"  [bold]{self.source_name}[/bold]: "
            f"Total {len(all_jobs)} jobs found"
        )
        return all_jobs
