"""
Cover Letter Generator
Creates tailored cover letters for top job matches.
Two modes: Claude API (premium) and template-based (free).
"""
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from storage.models import Job
from profile import (
    CANDIDATE_NAME, CANDIDATE_EMAIL, CANDIDATE_PHONE,
    KEY_ACHIEVEMENTS, COMPETENCY_KEYWORDS
)
from matching.keyword import compute_skill_match_score
from matching.gap_analysis import analyze_gaps
import config


def generate_cover_letter(job: Job, output_dir: str = None) -> str:
    """
    Generate a tailored cover letter for a job listing.
    Returns the file path of the generated cover letter.
    """
    if output_dir is None:
        output_dir = str(config.COVER_LETTERS_DIR)

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Try Claude API first if configured
    if config.ANTHROPIC_API_KEY:
        try:
            content = _generate_with_claude(job)
            if content:
                return _save_cover_letter(content, job, output_dir)
        except Exception as e:
            print(f"  [Cover Letter] Claude API failed: {e}. Using template.")

    # Fall back to template-based generation
    content = _generate_from_template(job)
    return _save_cover_letter(content, job, output_dir)


def _generate_with_claude(job: Job) -> Optional[str]:
    """Generate cover letter using Claude API."""
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

        gap_analysis = analyze_gaps(job.title, job.description)

        prompt = f"""Write a tailored cover letter for this job application.

CANDIDATE: {CANDIDATE_NAME}
- 10+ years enterprise program management experience
- Led PLM implementation for 750+ users (adoption 10% to 87%)
- Managed events with $3M-$20M budgets
- Global logistics experience at Maersk (Amazon, Honda, Target, Home Depot accounts)
- Skills: PLM, SAP, Salesforce, JIRA, Change Management, Vendor Management
- Certifications: PMP, Change Management, Business Analytics

JOB:
Title: {job.title}
Company: {job.company}
Location: {job.location}
Description: {job.description[:3000]}

GAPS TO ADDRESS:
{chr(10).join(gap_analysis.get('gaps', ['None identified']))}

COVER LETTER ANGLES:
{chr(10).join(gap_analysis.get('cover_letter_angles', []))}

Write a professional, compelling cover letter that:
1. Opens with a strong hook connecting her experience to this specific role
2. Maps her key achievements to the job requirements (use specific numbers)
3. Addresses any gaps proactively with positive framing
4. Shows knowledge of the company
5. Closes with confidence and a clear call to action
6. Is concise (under 400 words)
7. Sounds human, not AI-generated — vary sentence length, use natural language"""

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )

        return response.content[0].text

    except ImportError:
        print("  [Cover Letter] anthropic package not installed.")
        return None
    except Exception as e:
        print(f"  [Cover Letter] API error: {e}")
        return None


def _generate_from_template(job: Job) -> str:
    """Generate cover letter from template with smart variable substitution."""
    # Analyze the job to find best matching achievements
    _, skill_details = compute_skill_match_score(job.description)
    gap_analysis = analyze_gaps(job.title, job.description)

    # Select top 3 most relevant achievements
    relevant_achievements = _select_achievements(job.description)

    # Determine role focus
    role_focus = _determine_role_focus(job.title, job.description)

    # Build the cover letter
    date_str = datetime.now().strftime("%B %d, %Y")

    letter = f"""{CANDIDATE_NAME}
Charlotte, NC | {CANDIDATE_PHONE} | {CANDIDATE_EMAIL}

{date_str}

Hiring Manager
{job.company}
Re: {job.title}

Dear Hiring Manager,

{_opening_paragraph(job, role_focus)}

{_body_paragraph_1(job, relevant_achievements, role_focus)}

{_body_paragraph_2(job, relevant_achievements, gap_analysis)}

{_closing_paragraph(job)}

Sincerely,
{CANDIDATE_NAME}
"""

    return letter


def _select_achievements(description: str) -> list:
    """Select the most relevant achievements for this job."""
    desc_lower = description.lower()
    scored = []

    for achievement in KEY_ACHIEVEMENTS:
        score = 0
        for tag in achievement['tags']:
            if tag.lower() in desc_lower:
                score += 1
        scored.append((score, achievement))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [a for _, a in scored[:3]]


def _determine_role_focus(title: str, description: str) -> str:
    """Determine what type of role this is."""
    combined = (title + " " + description).lower()

    if any(w in combined for w in ["program manag", "portfolio"]):
        return "program_management"
    elif any(w in combined for w in ["project manag"]):
        return "project_management"
    elif any(w in combined for w in ["operation", "ops"]):
        return "operations"
    elif any(w in combined for w in ["change management", "transformation"]):
        return "change_management"
    elif any(w in combined for w in ["implementation", "deployment", "rollout"]):
        return "implementation"
    elif any(w in combined for w in ["vendor", "procurement", "supplier"]):
        return "vendor_management"
    elif any(w in combined for w in ["product manag"]):
        return "product_management"
    elif any(w in combined for w in ["supply chain", "logistics"]):
        return "logistics"
    elif any(w in combined for w in ["pmo", "project management office"]):
        return "pmo"
    else:
        return "general_management"


def _opening_paragraph(job: Job, focus: str) -> str:
    """Generate a strong opening paragraph."""
    openers = {
        "program_management": (
            f"I am writing to express my strong interest in the {job.title} position "
            f"at {job.company}. With over a decade of experience leading enterprise "
            f"programs with budgets up to $20M and driving cross-functional initiatives "
            f"from concept to execution, I bring the strategic vision and operational "
            f"rigor that this role demands."
        ),
        "change_management": (
            f"I am excited to apply for the {job.title} role at {job.company}. "
            f"My track record of driving organizational change is best exemplified by "
            f"my work recovering a stalled PLM implementation at Lowe's, where I took "
            f"user adoption from 10% to 87% through targeted change management strategy "
            f"and stakeholder engagement."
        ),
        "implementation": (
            f"I am writing to apply for the {job.title} position at {job.company}. "
            f"Having led the rapid six-month rollout of an enterprise PLM platform for "
            f"750+ users, I understand what it takes to deliver complex system "
            f"implementations on time and drive real adoption."
        ),
        "operations": (
            f"I am excited about the {job.title} opportunity at {job.company}. "
            f"With experience spanning global logistics operations at Maersk and "
            f"enterprise program management at Lowe's, I have consistently delivered "
            f"operational improvements that measurably impact the bottom line."
        ),
        "logistics": (
            f"I am writing to express my interest in the {job.title} role at "
            f"{job.company}. My four years at Maersk managing logistics for enterprise "
            f"clients including Amazon, Honda, and Target, combined with my enterprise "
            f"technology experience at Lowe's, provide a unique perspective on modern "
            f"supply chain operations."
        ),
    }

    return openers.get(focus, (
        f"I am writing to express my strong interest in the {job.title} position "
        f"at {job.company}. With 10+ years of experience in enterprise program "
        f"management, systems implementation, and operational transformation, I am "
        f"confident in my ability to deliver immediate value to your team."
    ))


def _body_paragraph_1(job: Job, achievements: list, focus: str) -> str:
    """First body paragraph — map achievements to requirements."""
    if not achievements:
        return (
            "Throughout my career, I have consistently delivered results in complex, "
            "cross-functional environments. At Lowe's, I managed enterprise initiatives "
            "with budgets from $3M to $20M, and at Maersk, I served as the primary "
            "point of contact for accounts managing 100,000-150,000 containers annually."
        )

    achievement_bullets = []
    for a in achievements[:2]:
        achievement_bullets.append(a['text'])

    return (
        f"My experience directly aligns with the needs of this role. "
        f"{achievement_bullets[0]}. "
        + (f"Additionally, {achievement_bullets[1].lower()}. " if len(achievement_bullets) > 1 else "")
        + "These experiences have honed my ability to navigate complex stakeholder "
        "landscapes, manage competing priorities, and deliver measurable outcomes."
    )


def _body_paragraph_2(job: Job, achievements: list, gap_analysis: dict) -> str:
    """Second body paragraph — address gaps or reinforce strengths."""
    gaps = gap_analysis.get('gaps', [])
    angles = gap_analysis.get('cover_letter_angles', [])

    if gaps and angles:
        return (
            f"While my background is primarily in retail and global logistics, "
            f"the skills I have developed are highly transferable. "
            f"{angles[0]} "
            f"My certifications in Project Management, Change Management, and "
            f"Business Analytics further demonstrate my commitment to professional "
            f"excellence and continuous growth."
        )
    else:
        return (
            f"What sets me apart is my ability to drive adoption and deliver results "
            f"with lean resources. At Lowe's, I managed an enterprise-wide PLM "
            f"transformation with a core team of just 2-3 people, achieving 87% "
            f"adoption, a 4-week reduction in packaging timelines, and 25-30% fewer "
            f"rush-order shipments. I bring this same resourcefulness and results "
            f"orientation to every initiative I lead."
        )


def _closing_paragraph(job: Job) -> str:
    """Generate closing paragraph."""
    return (
        f"I would welcome the opportunity to discuss how my experience in enterprise "
        f"program management, systems implementation, and operational transformation "
        f"can contribute to {job.company}'s continued success. I am available for an "
        f"interview at your convenience and look forward to hearing from you."
    )


def _save_cover_letter(content: str, job: Job, output_dir: str) -> str:
    """Save cover letter to file."""
    # Clean filename
    company_clean = re.sub(r'[^\w\s-]', '', job.company)[:30].strip()
    title_clean = re.sub(r'[^\w\s-]', '', job.title)[:30].strip()
    filename = f"CL_{company_clean}_{title_clean}.txt"
    filepath = os.path.join(output_dir, filename)

    with open(filepath, 'w') as f:
        f.write(content)

    return filepath
