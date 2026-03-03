"""
Email Alert System
Sends notifications when Dream Jobs are found and daily digests.
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from typing import List

from storage.models import Job
from storage import database as db
import config


def send_dream_job_alert(job: Job):
    """Send immediate email alert for a Dream Job match."""
    if not config.SMTP_USER:
        print("  [Alert] Email not configured. Skipping alert.")
        return

    subject = f"DREAM JOB MATCH ({job.score_total:.0f}/100): {job.title} at {job.company}"

    body = f"""
    <html><body style="font-family: -apple-system, sans-serif; max-width: 600px; margin: 0 auto;">
    <div style="background: #22c55e; color: white; padding: 20px; border-radius: 12px 12px 0 0;">
        <h1 style="margin:0; font-size: 1.3rem;">Dream Job Match Found!</h1>
        <p style="margin: 5px 0 0; opacity: 0.9;">Score: {job.score_total:.0f}/100 — Apply ASAP</p>
    </div>
    <div style="background: #f8fafc; padding: 20px; border: 1px solid #e2e8f0; border-radius: 0 0 12px 12px;">
        <h2 style="color: #1e293b; margin-top: 0;">{job.title}</h2>
        <p style="color: #475569; margin: 5px 0;"><strong>{job.company}</strong> | {job.location}</p>
        <p style="color: #22c55e; font-weight: 700; font-size: 1.1rem;">{job.display_salary}</p>

        <table style="width: 100%; font-size: 0.9rem; margin: 15px 0;">
            <tr><td style="padding: 4px; color: #64748b;">Resume Fit</td><td style="padding: 4px; font-weight: 600;">{job.score_resume_fit:.0f}/100</td></tr>
            <tr><td style="padding: 4px; color: #64748b;">Job Security</td><td style="padding: 4px; font-weight: 600;">{job.score_job_security:.0f}/100</td></tr>
            <tr><td style="padding: 4px; color: #64748b;">Compensation</td><td style="padding: 4px; font-weight: 600;">{job.score_compensation:.0f}/100</td></tr>
            <tr><td style="padding: 4px; color: #64748b;">Company Quality</td><td style="padding: 4px; font-weight: 600;">{job.score_company_quality:.0f}/100</td></tr>
            <tr><td style="padding: 4px; color: #64748b;">Location</td><td style="padding: 4px; font-weight: 600;">{job.score_location:.0f}/100</td></tr>
        </table>

        {'<p style="color: #0f172a;"><strong>Remote:</strong> Yes</p>' if job.is_remote else ''}
        {'<p style="color: #0f172a;"><strong>Hybrid:</strong> Yes</p>' if job.is_hybrid else ''}
        {'<p style="color: #0f172a;"><strong>Easy Apply:</strong> Yes</p>' if job.easy_apply else ''}

        <div style="margin: 20px 0;">
            <a href="{job.url or job.apply_url}" style="background: #22c55e; color: white;
               padding: 12px 24px; border-radius: 8px; text-decoration: none;
               font-weight: 600; display: inline-block;">Apply Now</a>
        </div>

        <div style="background: #f1f5f9; padding: 12px; border-radius: 8px; margin-top: 15px;">
            <p style="font-size: 0.85rem; color: #475569; margin: 0;">
                {job.description[:500] if job.description else 'No description available'}...
            </p>
        </div>
    </div>
    </body></html>
    """

    _send_email(subject, body)


def send_daily_digest():
    """Send daily digest of new matches from the past 24 hours."""
    if not config.SMTP_USER:
        print("  [Alert] Email not configured. Skipping digest.")
        return

    since = (datetime.now() - timedelta(hours=24)).isoformat()
    new_jobs = db.get_new_jobs_since(since)

    if not new_jobs:
        print("  [Digest] No new jobs in the past 24 hours.")
        return

    dream_jobs = [j for j in new_jobs if j.tier == "DREAM_JOB"]
    strong_jobs = [j for j in new_jobs if j.tier == "STRONG_MATCH"]
    consider_jobs = [j for j in new_jobs if j.tier == "WORTH_CONSIDERING"]

    subject = f"Daily Job Digest: {len(new_jobs)} new matches ({len(dream_jobs)} Dream Jobs)"

    body = f"""
    <html><body style="font-family: -apple-system, sans-serif; max-width: 600px; margin: 0 auto;">
    <div style="background: #1e293b; color: white; padding: 20px; border-radius: 12px 12px 0 0;">
        <h1 style="margin:0; font-size: 1.3rem;">Daily Job Search Digest</h1>
        <p style="margin: 5px 0 0; opacity: 0.8;">{datetime.now().strftime('%B %d, %Y')}</p>
    </div>
    <div style="background: #f8fafc; padding: 20px; border: 1px solid #e2e8f0;">
        <div style="display: flex; gap: 15px; margin-bottom: 20px;">
            <div style="text-align: center; flex: 1;">
                <div style="font-size: 2rem; font-weight: 700; color: #22c55e;">{len(dream_jobs)}</div>
                <div style="font-size: 0.8rem; color: #64748b;">Dream Jobs</div>
            </div>
            <div style="text-align: center; flex: 1;">
                <div style="font-size: 2rem; font-weight: 700; color: #3b82f6;">{len(strong_jobs)}</div>
                <div style="font-size: 0.8rem; color: #64748b;">Strong Matches</div>
            </div>
            <div style="text-align: center; flex: 1;">
                <div style="font-size: 2rem; font-weight: 700; color: #eab308;">{len(consider_jobs)}</div>
                <div style="font-size: 0.8rem; color: #64748b;">Consider</div>
            </div>
        </div>
    """

    for tier_name, tier_jobs, color in [
        ("Dream Jobs", dream_jobs, "#22c55e"),
        ("Strong Matches", strong_jobs, "#3b82f6"),
        ("Worth Considering", consider_jobs[:10], "#eab308"),
    ]:
        if tier_jobs:
            body += f'<h3 style="color: {color}; border-bottom: 2px solid {color}; padding-bottom: 5px;">{tier_name}</h3>'
            for job in tier_jobs:
                body += f"""
                <div style="padding: 10px; border-bottom: 1px solid #e2e8f0;">
                    <div style="display: flex; justify-content: space-between;">
                        <strong style="color: #1e293b;">{job.title}</strong>
                        <span style="color: {color}; font-weight: 700;">{job.score_total:.0f}</span>
                    </div>
                    <div style="color: #475569; font-size: 0.9rem;">{job.company} | {job.location}</div>
                    <div style="color: #22c55e; font-weight: 600; font-size: 0.9rem;">{job.display_salary}</div>
                    <a href="{job.url or job.apply_url}" style="color: #3b82f6; font-size: 0.85rem;">Apply &rarr;</a>
                </div>
                """

    # Follow-up reminders
    followups = db.get_jobs_needing_followup()
    if followups:
        body += '<h3 style="color: #a855f7; border-bottom: 2px solid #a855f7; padding-bottom: 5px;">Follow-Up Reminders</h3>'
        for job in followups:
            body += f"""
            <div style="padding: 8px; border-bottom: 1px solid #e2e8f0;">
                <strong>{job.title}</strong> at {job.company}
                <br><span style="color: #a855f7; font-size: 0.85rem;">Applied: {job.applied_date[:10]} — Time to follow up!</span>
            </div>
            """

    dashboard_link = config.DASHBOARD_URL or f"file://{config.REPORT_DIR / 'dashboard.html'}"
    body += f"""
    <div style="margin-top: 20px; padding: 12px; background: #f1f5f9; border-radius: 8px;">
        <p style="font-size: 0.85rem; color: #64748b; margin: 0;">
            Open the <a href="{dashboard_link}">full dashboard</a>
            for detailed scores, filtering, and application tracking.
        </p>
    </div>
    </div></body></html>
    """

    _send_email(subject, body)


def _send_email(subject: str, html_body: str):
    """Send an HTML email."""
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = config.ALERT_FROM_EMAIL
        msg['To'] = config.ALERT_TO_EMAIL

        msg.attach(MIMEText(html_body, 'html'))

        with smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT) as server:
            server.starttls()
            server.login(config.SMTP_USER, config.SMTP_PASSWORD)
            server.sendmail(
                config.ALERT_FROM_EMAIL,
                config.ALERT_TO_EMAIL,
                msg.as_string()
            )

        print(f"  [Alert] Email sent: {subject}")

    except Exception as e:
        print(f"  [Alert] Failed to send email: {e}")
        print(f"  [Alert] Configure SMTP in .env file to enable email alerts.")
