#!/usr/bin/env python3
"""
Job Search Campaign Manager for Cynthia Francis
================================================
Automated system that discovers, scores, and ranks job opportunities
across 15+ sources to maximize the chance of landing the best possible job.

Usage:
    python main.py                  # Full pipeline: scrape → score → report
    python main.py --report         # Just regenerate report from existing data
    python main.py --top 20         # Show top 20 in terminal
    python main.py --source indeed  # Search single source
    python main.py --applied 42     # Mark job #42 as applied
    python main.py --cover-letter 42  # Generate cover letter for job #42
    python main.py --export csv     # Export to CSV
    python main.py --quick          # Quick scan (Google Jobs + Indeed only)
    python main.py --digest         # Send daily email digest
    python main.py --schedule       # Run on schedule (2hr quick, daily full)
"""
import sys
import os
import argparse
import time
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import print as rprint

import config
from storage import database as db
from storage.models import Job


console = Console()


def main():
    parser = argparse.ArgumentParser(description="Job Search Campaign Manager")
    parser.add_argument('--report', action='store_true', help='Regenerate HTML report only')
    parser.add_argument('--top', type=int, default=0, help='Show top N results in terminal')
    parser.add_argument('--source', type=str, help='Search single source (indeed, linkedin, google_jobs, etc.)')
    parser.add_argument('--applied', type=int, help='Mark a job as applied by ID')
    parser.add_argument('--cover-letter', type=int, dest='cover_letter', help='Generate cover letter for job ID')
    parser.add_argument('--export', type=str, choices=['csv'], help='Export data')
    parser.add_argument('--quick', action='store_true', help='Quick scan (Google Jobs + Indeed)')
    parser.add_argument('--digest', action='store_true', help='Send daily email digest')
    parser.add_argument('--schedule', action='store_true', help='Run on schedule')
    parser.add_argument('--score', action='store_true', help='Re-score all unscored jobs')
    parser.add_argument('--enrich', action='store_true', help='Fetch full descriptions for jobs missing them')
    parser.add_argument('--rescore', action='store_true', help='Reset and re-score ALL jobs')

    args = parser.parse_args()

    # Initialize database
    db.init_db()

    # Load company data into database
    _ensure_companies_loaded()

    if args.report:
        _generate_report()
    elif args.top:
        _show_top(args.top)
    elif args.applied:
        _mark_applied(args.applied)
    elif args.cover_letter:
        _generate_cover_letter(args.cover_letter)
    elif args.export == 'csv':
        _export_csv()
    elif args.digest:
        _send_digest()
    elif args.score:
        _score_jobs()
    elif args.enrich:
        _enrich_jobs()
        _score_jobs()
        _generate_report()
    elif args.rescore:
        _rescore_all()
    elif args.schedule:
        _run_on_schedule()
    elif args.source:
        _search_single_source(args.source)
    elif args.quick:
        _quick_scan()
    else:
        _full_pipeline()


def _full_pipeline():
    """Full pipeline: scrape all sources → score → report → alert."""
    console.print(Panel.fit(
        "[bold white]Job Search Campaign Manager[/bold white]\n"
        "[dim]Cynthia Francis | Cornelius, NC[/dim]\n"
        f"[dim]{datetime.now().strftime('%Y-%m-%d %H:%M')}[/dim]",
        border_style="blue"
    ))

    start_time = time.time()

    # Phase 1: Scrape all sources
    console.print("\n[bold cyan]Phase 1: Discovering Jobs[/bold cyan]")
    console.print("[dim]Searching across all configured sources...[/dim]\n")

    all_new_jobs = []
    scrapers = _get_all_scrapers()

    for name, scraper in scrapers:
        try:
            console.print(f"[bold]{name}[/bold]:")
            jobs = scraper.search_all()
            if jobs:
                saved, dupes = db.save_jobs_batch(jobs)
                console.print(f"  → {saved} new, {dupes} duplicates\n")
                all_new_jobs.extend(jobs[:saved])  # Approximate new ones
            else:
                console.print(f"  → 0 results\n")
        except Exception as e:
            console.print(f"  [red]Error: {e}[/red]\n")

    # Phase 2: Enrich jobs with full descriptions
    console.print("[bold cyan]Phase 2: Enriching Job Descriptions[/bold cyan]")
    _enrich_jobs()

    # Phase 3: Score all unscored jobs
    console.print("\n[bold cyan]Phase 3: Scoring Jobs[/bold cyan]")
    _score_jobs()

    # Phase 4: Generate report
    console.print("\n[bold cyan]Phase 4: Generating Report[/bold cyan]")
    _generate_report()

    # Phase 5: Show summary
    elapsed = time.time() - start_time
    stats = db.get_job_count()

    console.print("\n")
    console.print(Panel.fit(
        f"[bold green]Pipeline Complete![/bold green]\n\n"
        f"Total jobs in database: [bold]{stats.get('total', 0)}[/bold]\n"
        f"Dream Jobs (85+): [bold green]{stats.get('tier_dream_job', 0)}[/bold green]\n"
        f"Strong Matches (70-84): [bold blue]{stats.get('tier_strong_match', 0)}[/bold blue]\n"
        f"Worth Considering (55-69): [bold yellow]{stats.get('tier_worth_considering', 0)}[/bold yellow]\n"
        f"Applied: [bold purple]{stats.get('status_applied', 0)}[/bold purple]\n\n"
        f"Time: {elapsed:.0f}s\n"
        f"Report: [link]file://{config.REPORT_DIR / 'dashboard.html'}[/link]",
        title="Summary",
        border_style="green"
    ))

    # Phase 6: Send alerts for dream jobs
    dream_jobs = db.get_all_jobs(min_score=config.TIER_DREAM_JOB, status='new')
    if dream_jobs:
        console.print(f"\n[bold green]Found {len(dream_jobs)} Dream Jobs! Sending alerts...[/bold green]")
        from alerts.email_alert import send_dream_job_alert
        for job in dream_jobs[:5]:  # Alert on top 5
            try:
                send_dream_job_alert(job)
            except Exception:
                pass

    # Auto-open report (skip in CI environment)
    if not os.environ.get("CI"):
        report_path = config.REPORT_DIR / "dashboard.html"
        if report_path.exists():
            try:
                import webbrowser
                webbrowser.open(f"file://{report_path}")
            except Exception:
                pass


def _quick_scan():
    """Quick scan: Google Jobs + Indeed only."""
    console.print(Panel.fit(
        "[bold white]Quick Scan[/bold white]\n"
        "[dim]Google Jobs + Indeed[/dim]",
        border_style="cyan"
    ))

    from scrapers.indeed import IndeedScraper
    from scrapers.google_jobs import GoogleJobsScraper

    for name, scraper in [("Google Jobs", GoogleJobsScraper()),
                          ("Indeed", IndeedScraper())]:
        try:
            console.print(f"\n[bold]{name}[/bold]:")
            jobs = scraper.search_all()
            if jobs:
                saved, dupes = db.save_jobs_batch(jobs)
                console.print(f"  → {saved} new, {dupes} duplicates")
        except Exception as e:
            console.print(f"  [red]Error: {e}[/red]")

    _enrich_jobs()
    _score_jobs()
    _generate_report()

    stats = db.get_job_count()
    console.print(f"\n[green]Done.[/green] {stats.get('total', 0)} total jobs. "
                  f"Dream: {stats.get('tier_dream_job', 0)} | "
                  f"Strong: {stats.get('tier_strong_match', 0)}")


def _search_single_source(source: str):
    """Search a single source."""
    scrapers = dict(_get_all_scrapers())
    if source not in scrapers:
        console.print(f"[red]Unknown source: {source}[/red]")
        console.print(f"Available: {', '.join(scrapers.keys())}")
        return

    scraper = scrapers[source]
    console.print(f"[bold]Searching {source}...[/bold]")

    jobs = scraper.search_all()
    if jobs:
        saved, dupes = db.save_jobs_batch(jobs)
        console.print(f"→ {saved} new, {dupes} duplicates")

    _score_jobs()
    _show_top(10)


def _enrich_jobs():
    """Fetch full descriptions for jobs that don't have them,
    then scan all stored descriptions for salary data."""
    from scrapers.enrich import JobEnricher
    enricher = JobEnricher()
    enriched = enricher.enrich_jobs(limit=300)
    if enriched > 0:
        console.print(f"[green]Enriched {enriched} jobs with full descriptions.[/green]")
    # Always scan stored descriptions for salary (catches what URL-fetch missed)
    enricher.extract_salaries_from_stored_descriptions()


def _rescore_all():
    """Reset and re-score ALL jobs in database."""
    conn = db.get_connection()
    try:
        count = conn.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]
        conn.execute(
            "UPDATE jobs SET score_total = NULL, tier = NULL, "
            "score_obtainability = NULL, score_desirability = NULL, "
            "score_qualifications = NULL, "
            "score_resume_fit = NULL, score_resume_fit_raw = NULL, "
            "score_job_security = NULL, "
            "score_compensation = NULL, score_company_quality = NULL, "
            "score_benefits = NULL, score_location = NULL, "
            "score_interview_prob = NULL, score_interview_speed = NULL, "
            "is_stretch = 0, stretch_severity = '', stretch_gap_analysis = ''"
        )
        conn.commit()
        console.print(f"[yellow]Reset scores for {count} jobs.[/yellow]")
    finally:
        conn.close()

    _score_jobs()
    _generate_report()

    stats = db.get_job_count()
    console.print(f"\n[green]Re-scored! Dream: {stats.get('tier_dream_job', 0)} | "
                  f"Strong: {stats.get('tier_strong_match', 0)} | "
                  f"Consider: {stats.get('tier_worth_considering', 0)}[/green]")


def _score_jobs():
    """Score all unscored jobs."""
    from scoring.engine import score_all_unscored
    score_all_unscored()


def _generate_report():
    """Generate HTML dashboard."""
    from reporting.dashboard import generate_dashboard
    path = generate_dashboard()
    console.print(f"[green]Report generated:[/green] {path}")


def _export_csv():
    """Export to CSV."""
    from reporting.dashboard import generate_csv
    path = generate_csv()
    console.print(f"[green]CSV exported:[/green] {path}")


def _show_top(n: int):
    """Show top N jobs in terminal."""
    jobs = db.get_all_jobs(min_score=config.TIER_WORTH_CONSIDERING, limit=n)

    if not jobs:
        console.print("[yellow]No scored jobs found. Run a search first.[/yellow]")
        return

    table = Table(title=f"Top {n} Job Matches", border_style="blue")
    table.add_column("Score", style="bold", width=6)
    table.add_column("Tier", width=8)
    table.add_column("Title", width=30)
    table.add_column("Company", width=20)
    table.add_column("Salary", width=18)
    table.add_column("Location", width=20)
    table.add_column("Source", width=10)

    for job in jobs:
        tier_style = {
            "DREAM_JOB": "bold green",
            "STRONG_MATCH": "bold blue",
            "WORTH_CONSIDERING": "yellow",
        }.get(job.tier, "dim")

        tier_label = {
            "DREAM_JOB": "DREAM",
            "STRONG_MATCH": "STRONG",
            "WORTH_CONSIDERING": "CONSIDER",
        }.get(job.tier, job.tier)

        table.add_row(
            f"{job.score_total:.0f}",
            f"[{tier_style}]{tier_label}[/{tier_style}]",
            job.title[:30],
            job.company[:20],
            job.display_salary,
            job.location[:20],
            job.source,
        )

    console.print(table)


def _mark_applied(job_id: int):
    """Mark a job as applied."""
    from datetime import timedelta
    db.update_job_status(job_id, "applied")

    # Set follow-up reminder for 7 days later
    follow_up = (datetime.now() + timedelta(days=7)).isoformat()
    conn = db.get_connection()
    try:
        conn.execute(
            "UPDATE jobs SET follow_up_date = ? WHERE id = ?",
            (follow_up, job_id)
        )
        conn.commit()
    finally:
        conn.close()

    console.print(f"[green]Job #{job_id} marked as applied.[/green]")
    console.print(f"[dim]Follow-up reminder set for 7 days from now.[/dim]")


def _generate_cover_letter(job_id: int):
    """Generate cover letter for a specific job."""
    conn = db.get_connection()
    try:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    finally:
        conn.close()

    if not row:
        console.print(f"[red]Job #{job_id} not found.[/red]")
        return

    job = Job.from_dict(dict(row))

    from materials.cover_letter import generate_cover_letter
    path = generate_cover_letter(job)
    console.print(f"[green]Cover letter generated:[/green] {path}")


def _send_digest():
    """Send daily email digest."""
    from alerts.email_alert import send_daily_digest
    send_daily_digest()


def _run_on_schedule():
    """Run on a schedule using the schedule library."""
    try:
        import schedule
    except ImportError:
        console.print("[red]Install 'schedule' package: pip install schedule[/red]")
        return

    console.print(Panel.fit(
        "[bold]Running on Schedule[/bold]\n"
        "Quick scan: every 2 hours (6AM-10PM)\n"
        "Full scan: daily at 6AM\n"
        "Digest: daily at 7AM\n"
        "[dim]Press Ctrl+C to stop[/dim]",
        border_style="cyan"
    ))

    def quick_job():
        hour = datetime.now().hour
        if config.SCAN_START_HOUR <= hour <= config.SCAN_END_HOUR:
            console.print(f"\n[cyan][{datetime.now().strftime('%H:%M')}] Quick scan...[/cyan]")
            _quick_scan()

    def full_job():
        console.print(f"\n[cyan][{datetime.now().strftime('%H:%M')}] Full pipeline...[/cyan]")
        _full_pipeline()

    def digest_job():
        console.print(f"\n[cyan][{datetime.now().strftime('%H:%M')}] Sending digest...[/cyan]")
        _send_digest()

    schedule.every(config.QUICK_SCAN_INTERVAL_HOURS).hours.do(quick_job)
    schedule.every().day.at("06:00").do(full_job)
    schedule.every().day.at("07:00").do(digest_job)

    # Run initial full pipeline
    _full_pipeline()

    while True:
        schedule.run_pending()
        time.sleep(60)


def _get_all_scrapers():
    """Get all configured scrapers."""
    scrapers = []

    try:
        from scrapers.google_jobs import GoogleJobsScraper
        scrapers.append(("google_jobs", GoogleJobsScraper()))
    except Exception as e:
        console.print(f"[yellow]Google Jobs scraper unavailable: {e}[/yellow]")

    try:
        from scrapers.indeed import IndeedScraper
        scrapers.append(("indeed", IndeedScraper()))
    except Exception as e:
        console.print(f"[yellow]Indeed scraper unavailable: {e}[/yellow]")

    try:
        from scrapers.linkedin import LinkedInScraper
        scrapers.append(("linkedin", LinkedInScraper()))
    except Exception as e:
        console.print(f"[yellow]LinkedIn scraper unavailable: {e}[/yellow]")

    try:
        from scrapers.glassdoor import GlassdoorScraper
        scrapers.append(("glassdoor", GlassdoorScraper()))
    except Exception as e:
        console.print(f"[yellow]Glassdoor scraper unavailable: {e}[/yellow]")

    try:
        from scrapers.ziprecruiter import ZipRecruiterScraper
        scrapers.append(("ziprecruiter", ZipRecruiterScraper()))
    except Exception as e:
        console.print(f"[yellow]ZipRecruiter scraper unavailable: {e}[/yellow]")

    try:
        from scrapers.multi_board import MultiboardScraper
        scrapers.append(("multi_board", MultiboardScraper()))
    except Exception as e:
        console.print(f"[yellow]Multi-board scraper unavailable: {e}[/yellow]")

    try:
        from scrapers.multi_board import USAJobsScraper
        scrapers.append(("usajobs", USAJobsScraper()))
    except Exception as e:
        console.print(f"[yellow]USAJobs scraper unavailable: {e}[/yellow]")

    try:
        from scrapers.company_careers import CompanyCareersScraper
        scrapers.append(("company_direct", CompanyCareersScraper()))
    except Exception as e:
        console.print(f"[yellow]Company careers scraper unavailable: {e}[/yellow]")

    return scrapers


def _ensure_companies_loaded():
    """Load company data from JSON into database if not already loaded."""
    import json

    companies = db.get_all_companies()
    if companies:
        return  # Already loaded

    data_path = config.DATA_DIR / "charlotte_companies.json"
    if not data_path.exists():
        return

    with open(data_path) as f:
        data = json.load(f)

    from storage.models import Company

    for c_data in data.get("companies", []):
        company = Company(
            name=c_data.get("name", ""),
            industry=c_data.get("industry", ""),
            size_employees=c_data.get("size_employees"),
            is_public=c_data.get("is_public", False),
            is_fortune_500=c_data.get("is_fortune_500", False),
            is_fortune_1000=c_data.get("is_fortune_1000", False),
            hq_location=c_data.get("hq_location", ""),
            charlotte_office=c_data.get("charlotte_office", True),
            glassdoor_rating=c_data.get("glassdoor_rating"),
            careers_url=c_data.get("careers_url", ""),
            ats_platform=c_data.get("ats_platform", ""),
            best_places_to_work=c_data.get("best_places_to_work", False),
            recent_layoffs=c_data.get("recent_layoffs", False),
        )
        db.save_company(company)

    console.print(f"[dim]Loaded {len(data.get('companies', []))} companies into database.[/dim]")


if __name__ == "__main__":
    main()
