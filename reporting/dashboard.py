"""
HTML Dashboard Generator
Creates an interactive, sortable, filterable dashboard of job results.
Shows dual scores: Fit (obtainability), Quality (desirability), and Composite.
"""
import os
from datetime import datetime
from pathlib import Path
from typing import List

from jinja2 import Template

from storage.models import Job
from storage import database as db
import config


DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Job Search Campaign - Cynthia Francis</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               background: #0f172a; color: #e2e8f0; line-height: 1.5; }

        .container { max-width: 1700px; margin: 0 auto; padding: 20px; }

        h1 { font-size: 1.8rem; margin-bottom: 5px; color: #f1f5f9; }
        .subtitle { color: #94a3b8; margin-bottom: 20px; font-size: 0.9rem; }

        /* Stats Cards */
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
                 gap: 12px; margin-bottom: 24px; }
        .stat-card { background: #1e293b; border-radius: 12px; padding: 16px;
                     border: 1px solid #334155; }
        .stat-card .number { font-size: 2rem; font-weight: 700; }
        .stat-card .label { color: #94a3b8; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; }
        .stat-card.dream .number { color: #22c55e; }
        .stat-card.strong .number { color: #3b82f6; }
        .stat-card.consider .number { color: #eab308; }
        .stat-card.total .number { color: #f1f5f9; }
        .stat-card.applied .number { color: #a78bfa; }
        .stat-card.salary .number { color: #f97316; font-size: 1.4rem; }
        .stat-card.stretch .number { color: #f97316; }

        /* Filters */
        .filters { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 20px;
                   align-items: center; }
        .filters select, .filters input {
            background: #1e293b; border: 1px solid #334155; color: #e2e8f0;
            padding: 8px 12px; border-radius: 8px; font-size: 0.85rem;
        }
        .filters select:focus, .filters input:focus { outline: none; border-color: #3b82f6; }

        /* Table */
        .table-container { overflow-x: auto; border-radius: 12px;
                          border: 1px solid #334155; }
        table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
        thead { background: #1e293b; position: sticky; top: 0; }
        th { padding: 12px 8px; text-align: left; color: #94a3b8; font-weight: 600;
             cursor: pointer; user-select: none; white-space: nowrap;
             border-bottom: 2px solid #334155; font-size: 0.75rem;
             text-transform: uppercase; letter-spacing: 0.05em; }
        th:hover { color: #e2e8f0; }
        th.sorted-asc::after { content: ' ▲'; color: #3b82f6; }
        th.sorted-desc::after { content: ' ▼'; color: #3b82f6; }

        td { padding: 8px; border-bottom: 1px solid #1e293b; vertical-align: top; }
        tr { background: #0f172a; }
        tr:hover { background: #1e293b; }

        /* Tier colors */
        tr.dreamjob { border-left: 4px solid #22c55e; }
        tr.dreamjob td:first-child { color: #22c55e; font-weight: 700; }
        tr.strongmatch { border-left: 4px solid #3b82f6; }
        tr.strongmatch td:first-child { color: #3b82f6; font-weight: 600; }
        tr.worthconsidering { border-left: 4px solid #eab308; }

        /* Score badge */
        .score { display: inline-block; padding: 2px 8px; border-radius: 6px;
                 font-weight: 700; font-size: 0.8rem; min-width: 36px; text-align: center; }
        .score.high { background: rgba(34,197,94,0.15); color: #22c55e; }
        .score.mid { background: rgba(59,130,246,0.15); color: #3b82f6; }
        .score.low { background: rgba(234,179,8,0.15); color: #eab308; }
        .score.vlow { background: rgba(239,68,68,0.15); color: #ef4444; }

        .tag { display: inline-block; padding: 2px 6px; border-radius: 4px;
               font-size: 0.65rem; font-weight: 600; margin: 1px; }
        .tag.remote { background: rgba(34,197,94,0.15); color: #22c55e; }
        .tag.hybrid { background: rgba(59,130,246,0.15); color: #3b82f6; }
        .tag.easy-apply { background: rgba(168,85,247,0.15); color: #a855f7; }
        .tag.stretch-minor { background: rgba(234,179,8,0.15); color: #eab308; }
        .tag.stretch-moderate { background: rgba(249,115,22,0.15); color: #f97316; }
        .tag.stretch-significant { background: rgba(239,68,68,0.15); color: #ef4444; }
        .tag.stretch-reach { background: rgba(239,68,68,0.25); color: #ef4444; }

        /* Status */
        .status { padding: 2px 8px; border-radius: 4px; font-size: 0.75rem;
                  cursor: pointer; display: inline-block; }
        .status.new { background: rgba(100,116,139,0.2); color: #94a3b8; }
        .status.applied { background: rgba(168,85,247,0.15); color: #a855f7; }
        .status.interview { background: rgba(34,197,94,0.15); color: #22c55e; }
        .status.offer { background: rgba(249,115,22,0.15); color: #f97316; }
        .status.rejected { background: rgba(239,68,68,0.15); color: #ef4444; }

        a { color: #3b82f6; text-decoration: none; }
        a:hover { text-decoration: underline; }

        .company { font-weight: 500; color: #f1f5f9; }
        .location { color: #94a3b8; font-size: 0.8rem; }
        .salary { color: #22c55e; font-weight: 600; }
        .posted { color: #64748b; font-size: 0.8rem; }

        /* Expandable detail */
        .detail-row { display: none; }
        .detail-row.open { display: table-row; }
        .detail-content { padding: 16px; background: #1e293b; }
        .detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
        .detail-section h4 { color: #94a3b8; font-size: 0.75rem; text-transform: uppercase;
                             margin-bottom: 8px; }
        .score-bar { height: 6px; background: #334155; border-radius: 3px; margin: 4px 0; }
        .score-bar .fill { height: 100%; border-radius: 3px; }
        .score-label { display: flex; justify-content: space-between; font-size: 0.8rem; }

        .gap-analysis { background: #0f172a; padding: 12px; border-radius: 8px;
                        font-size: 0.8rem; white-space: pre-line; margin-top: 8px; }

        .section-header { margin: 30px 0 15px; padding: 10px 0;
                          border-bottom: 2px solid #334155; }
        .section-header h2 { font-size: 1.3rem; }
        .section-header .count { color: #94a3b8; font-size: 0.9rem; }

        /* ── Mobile Responsive ─────────────────────────── */
        @media (max-width: 768px) {
            .container { padding: 8px; }
            h1 { font-size: 1.3rem; }
            .subtitle { font-size: 0.8rem; }
            .stats { grid-template-columns: repeat(2, 1fr); gap: 8px; }
            .stat-card { padding: 10px; }
            .stat-card .value { font-size: 1.5rem; }

            /* Hide less-important columns: Fit, Quality, Source, Status */
            th:nth-child(2), td:nth-child(2),
            th:nth-child(3), td:nth-child(3),
            th:nth-child(8), td:nth-child(8),
            th:nth-child(9), td:nth-child(9)
            { display: none; }

            table { font-size: 0.78rem; }
            th, td { padding: 6px 4px; }
            .company { max-width: 80px; }
            .salary { max-width: 70px; font-size: 0.72rem; }
            .location { max-width: 80px; }

            /* Stack filters vertically */
            .filters { flex-direction: column; gap: 6px; }
            .filters select, .filters input { font-size: 16px; width: 100%; }

            /* Detail view adjustments */
            .detail-grid { grid-template-columns: 1fr; }
            .gap-analysis { font-size: 0.72rem; }

            /* Section headers */
            .section-header { margin: 20px 0 10px; }
            .section-header h2 { font-size: 1.1rem; }
        }

        @media (max-width: 480px) {
            /* Extra small phones: also hide Location column */
            th:nth-child(7), td:nth-child(7) { display: none; }
            table { font-size: 0.72rem; }
        }

        .timestamp { color: #475569; font-size: 0.75rem; text-align: right; margin-top: 20px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Job Search Campaign Dashboard</h1>
        <p class="subtitle">Cynthia Francis | Updated: {{ generated_at }}</p>

        <!-- Stats -->
        <div class="stats">
            <div class="stat-card total">
                <div class="number">{{ total_jobs }}</div>
                <div class="label">Total Jobs Found</div>
            </div>
            <div class="stat-card dream">
                <div class="number">{{ dream_count }}</div>
                <div class="label">Dream Jobs (85+)</div>
            </div>
            <div class="stat-card strong">
                <div class="number">{{ strong_count }}</div>
                <div class="label">Strong Match (70-84)</div>
            </div>
            <div class="stat-card consider">
                <div class="number">{{ consider_count }}</div>
                <div class="label">Worth Considering</div>
            </div>
            <div class="stat-card stretch">
                <div class="number">{{ stretch_count }}</div>
                <div class="label">Stretch Jobs</div>
            </div>
            <div class="stat-card salary">
                <div class="number">{{ avg_salary }}</div>
                <div class="label">Avg Salary (Top 20)</div>
            </div>
        </div>

        <!-- Filters -->
        <div class="filters">
            <select id="tierFilter" onchange="filterTable()">
                <option value="">All Tiers</option>
                <option value="DREAM_JOB">Dream Jobs Only</option>
                <option value="STRONG_MATCH">Strong Match+</option>
                <option value="WORTH_CONSIDERING">All Matches</option>
            </select>
            <select id="remoteFilter" onchange="filterTable()">
                <option value="">Any Location</option>
                <option value="remote">Remote Only</option>
                <option value="hybrid">Hybrid+Remote</option>
                <option value="local">Local Only</option>
            </select>
            <select id="stretchFilter" onchange="filterTable()">
                <option value="">Any Stretch</option>
                <option value="no">Non-Stretch Only</option>
                <option value="yes">Stretches Only</option>
            </select>
            <select id="statusFilter" onchange="filterTable()">
                <option value="">Any Status</option>
                <option value="new">New</option>
                <option value="applied">Applied</option>
                <option value="interview">Interview</option>
            </select>
            <input type="text" id="searchInput" placeholder="Search title/company..."
                   onkeyup="filterTable()" style="min-width: 200px;">
        </div>

        <!-- Main Job Table -->
        <div class="section-header">
            <h2>All Matching Jobs <span class="count">({{ jobs|length }})</span></h2>
        </div>
        <div class="table-container">
            <table id="jobTable">
                <thead>
                    <tr>
                        <th onclick="sortTable(0, 'num')" class="sorted-desc">Score</th>
                        <th onclick="sortTable(1, 'num')">Fit</th>
                        <th onclick="sortTable(2, 'num')">Quality</th>
                        <th onclick="sortTable(3, 'text')">Title</th>
                        <th onclick="sortTable(4, 'text')">Company</th>
                        <th>
                            <select id="salarySortSelect" onchange="sortBySalary()" style="
                                background: transparent; border: none; color: #94a3b8;
                                font-weight: 600; font-size: 0.75rem; text-transform: uppercase;
                                letter-spacing: 0.05em; cursor: pointer; padding: 0;
                            ">
                                <option value="avg">Salary (Avg)</option>
                                <option value="min">Salary (Min)</option>
                                <option value="max">Salary (Max)</option>
                            </select>
                        </th>
                        <th onclick="sortTable(6, 'text')">Location</th>
                        <th onclick="sortTable(7, 'text')">Source</th>
                        <th>Status</th>
                        <th>Link</th>
                    </tr>
                </thead>
                <tbody>
                {% for job in jobs %}
                    <tr class="{{ job.tier|lower|replace('_','') }} job-row"
                        data-tier="{{ job.tier }}"
                        data-remote="{{ 'remote' if job.is_remote else ('hybrid' if job.is_hybrid else 'onsite') }}"
                        data-status="{{ job.status }}"
                        data-stretch="{{ 'yes' if job.is_stretch else 'no' }}"
                        data-search="{{ job.title|lower }} {{ job.company|lower }}"
                        onclick="toggleDetail('detail-{{ loop.index }}')">
                        <td>
                            <span class="score {{ 'high' if job.score_total >= 85 else ('mid' if job.score_total >= 70 else ('low' if job.score_total >= 55 else 'vlow')) }}"
                                  data-sort="{{ job.score_total }}">
                                {{ "%.0f"|format(job.score_total) }}
                            </span>
                        </td>
                        <td>
                            <span class="score {{ 'high' if job.score_obtainability >= 70 else ('mid' if job.score_obtainability >= 50 else ('low' if job.score_obtainability >= 30 else 'vlow')) }}"
                                  data-sort="{{ job.score_obtainability }}">
                                {{ "%.0f"|format(job.score_obtainability) }}
                            </span>
                        </td>
                        <td>
                            <span class="score {{ 'high' if job.score_desirability >= 70 else ('mid' if job.score_desirability >= 50 else 'low') }}"
                                  data-sort="{{ job.score_desirability }}">
                                {{ "%.0f"|format(job.score_desirability) }}
                            </span>
                        </td>
                        <td>
                            {{ job.title }}
                            {% if job.stretch_severity == 'Minor Stretch' %}<span class="tag stretch-minor">MINOR STRETCH</span>
                            {% elif job.stretch_severity == 'Moderate Stretch' %}<span class="tag stretch-moderate">MODERATE</span>
                            {% elif job.stretch_severity == 'Significant Stretch' %}<span class="tag stretch-significant">SIGNIFICANT</span>
                            {% elif job.stretch_severity == 'Reach' %}<span class="tag stretch-reach">REACH</span>
                            {% endif %}
                            {% if job.easy_apply %}<span class="tag easy-apply">Easy Apply</span>{% endif %}
                        </td>
                        <td class="company">{{ job.company }}</td>
                        <td class="salary"
                            data-salary-min="{{ job.salary_min or 0 }}"
                            data-salary-max="{{ job.salary_max or 0 }}"
                            data-salary-avg="{{ job.salary_midpoint or 0 }}"
                            data-sort="{{ job.salary_midpoint or 0 }}">{{ job.display_salary }}</td>
                        <td class="location">{{ job.location }}
                            {% if job.is_remote %}<span class="tag remote">Remote</span>{% endif %}
                            {% if job.is_hybrid %}<span class="tag hybrid">Hybrid</span>{% endif %}
                        </td>
                        <td>{{ job.source }}</td>
                        <td><span class="status {{ job.status }}">{{ job.status }}</span></td>
                        <td><a href="{{ job.url or job.apply_url }}" target="_blank" onclick="event.stopPropagation()">Apply</a></td>
                    </tr>
                    <tr class="detail-row" id="detail-{{ loop.index }}">
                        <td colspan="10">
                            <div class="detail-content">
                                <div class="detail-grid">
                                    <div class="detail-section">
                                        <h4>Obtainability Breakdown (Fit: {{ "%.0f"|format(job.score_obtainability) }})</h4>
                                        {% set obt_scores = [
                                            ('Qualifications', job.score_qualifications, 40),
                                            ('Location', job.score_location, 25),
                                            ('Semantic Match', job.score_resume_fit, 20),
                                            ('Interview Prob.', job.score_interview_prob, 15),
                                        ] %}
                                        {% for name, score, weight in obt_scores %}
                                        <div class="score-label">
                                            <span>{{ name }} ({{ weight }}%)</span>
                                            <span>{{ "%.0f"|format(score) }}/100</span>
                                        </div>
                                        <div class="score-bar">
                                            <div class="fill" style="width: {{ score }}%;
                                                background: {{ '#22c55e' if score >= 75 else ('#3b82f6' if score >= 50 else ('#eab308' if score >= 30 else '#ef4444')) }};"></div>
                                        </div>
                                        {% endfor %}

                                        <h4 style="margin-top: 16px;">Desirability Breakdown (Quality: {{ "%.0f"|format(job.score_desirability) }})</h4>
                                        {% set des_scores = [
                                            ('Compensation', job.score_compensation, 30),
                                            ('Job Security', job.score_job_security, 25),
                                            ('Company Quality', job.score_company_quality, 20),
                                            ('Benefits', job.score_benefits, 15),
                                            ('Interview Speed', job.score_interview_speed, 10),
                                        ] %}
                                        {% for name, score, weight in des_scores %}
                                        <div class="score-label">
                                            <span>{{ name }} ({{ weight }}%)</span>
                                            <span>{{ "%.0f"|format(score) }}/100</span>
                                        </div>
                                        <div class="score-bar">
                                            <div class="fill" style="width: {{ score }}%;
                                                background: {{ '#22c55e' if score >= 75 else ('#3b82f6' if score >= 50 else '#eab308') }};"></div>
                                        </div>
                                        {% endfor %}
                                    </div>
                                    <div class="detail-section">
                                        {% if job.stretch_gap_analysis %}
                                        <h4>Gap Analysis{% if job.stretch_severity %} — {{ job.stretch_severity }}{% endif %}</h4>
                                        <div class="gap-analysis">{{ job.stretch_gap_analysis }}</div>
                                        {% endif %}
                                        <h4 style="margin-top: 12px;">Job Description</h4>
                                        <p style="font-size: 0.8rem; max-height: 300px; overflow-y: auto;">
                                            {{ job.description[:1500] if job.description else 'No description available' }}
                                        </p>
                                    </div>
                                </div>
                            </div>
                        </td>
                    </tr>
                {% endfor %}
                </tbody>
            </table>
        </div>

        <p class="timestamp">Generated: {{ generated_at }} | Database: {{ db_path }}</p>
    </div>

    <script>
        function toggleDetail(id) {
            const row = document.getElementById(id);
            if (row) row.classList.toggle('open');
        }

        function filterTable() {
            const tier = document.getElementById('tierFilter').value;
            const remote = document.getElementById('remoteFilter').value;
            const stretch = document.getElementById('stretchFilter').value;
            const status = document.getElementById('statusFilter').value;
            const search = document.getElementById('searchInput').value.toLowerCase();

            document.querySelectorAll('.job-row').forEach(row => {
                let show = true;

                if (tier) {
                    const rowTier = row.dataset.tier;
                    if (tier === 'DREAM_JOB' && rowTier !== 'DREAM_JOB') show = false;
                    if (tier === 'STRONG_MATCH' && !['DREAM_JOB', 'STRONG_MATCH'].includes(rowTier)) show = false;
                    if (tier === 'WORTH_CONSIDERING' && rowTier === 'BELOW_THRESHOLD') show = false;
                }

                if (remote) {
                    const rowRemote = row.dataset.remote;
                    if (remote === 'remote' && rowRemote !== 'remote') show = false;
                    if (remote === 'hybrid' && !['remote', 'hybrid'].includes(rowRemote)) show = false;
                    if (remote === 'local' && rowRemote !== 'onsite') show = false;
                }

                if (stretch) {
                    if (stretch === 'no' && row.dataset.stretch === 'yes') show = false;
                    if (stretch === 'yes' && row.dataset.stretch !== 'yes') show = false;
                }

                if (status && row.dataset.status !== status) show = false;

                if (search && !row.dataset.search.includes(search)) show = false;

                row.style.display = show ? '' : 'none';
                const nextRow = row.nextElementSibling;
                if (nextRow && nextRow.classList.contains('detail-row')) {
                    nextRow.style.display = 'none';
                    nextRow.classList.remove('open');
                }
            });
        }

        let salarySortDir = 'desc';

        function sortBySalary() {
            const field = document.getElementById('salarySortSelect').value;
            const table = document.getElementById('jobTable');
            const tbody = table.querySelector('tbody');
            const rows = Array.from(tbody.querySelectorAll('.job-row'));

            salarySortDir = salarySortDir === 'desc' ? 'asc' : 'desc';

            rows.sort((a, b) => {
                const aCell = a.querySelectorAll('td')[5];
                const bCell = b.querySelectorAll('td')[5];
                const aVal = parseFloat(aCell.dataset['salary' + field.charAt(0).toUpperCase() + field.slice(1)]) || 0;
                const bVal = parseFloat(bCell.dataset['salary' + field.charAt(0).toUpperCase() + field.slice(1)]) || 0;
                return salarySortDir === 'desc' ? bVal - aVal : aVal - bVal;
            });

            rows.forEach(row => {
                const detail = row.nextElementSibling;
                tbody.appendChild(row);
                if (detail && detail.classList.contains('detail-row')) {
                    tbody.appendChild(detail);
                }
            });

            table.querySelectorAll('th').forEach(th => {
                th.classList.remove('sorted-asc', 'sorted-desc');
            });
        }

        let currentSort = { col: 0, asc: false };

        function sortTable(colIdx, type) {
            const table = document.getElementById('jobTable');
            const tbody = table.querySelector('tbody');
            const rows = Array.from(tbody.querySelectorAll('.job-row'));

            if (currentSort.col === colIdx) {
                currentSort.asc = !currentSort.asc;
            } else {
                currentSort.col = colIdx;
                currentSort.asc = false;
            }

            rows.sort((a, b) => {
                let aVal, bVal;
                const aCells = a.querySelectorAll('td');
                const bCells = b.querySelectorAll('td');

                if (type === 'num') {
                    const aSort = aCells[colIdx].querySelector('[data-sort]');
                    const bSort = bCells[colIdx].querySelector('[data-sort]');
                    aVal = parseFloat((aSort ? aSort.dataset.sort : null) || aCells[colIdx].textContent) || 0;
                    bVal = parseFloat((bSort ? bSort.dataset.sort : null) || bCells[colIdx].textContent) || 0;
                } else {
                    aVal = aCells[colIdx].textContent.trim().toLowerCase();
                    bVal = bCells[colIdx].textContent.trim().toLowerCase();
                }

                if (aVal < bVal) return currentSort.asc ? -1 : 1;
                if (aVal > bVal) return currentSort.asc ? 1 : -1;
                return 0;
            });

            rows.forEach(row => {
                const detail = row.nextElementSibling;
                tbody.appendChild(row);
                if (detail && detail.classList.contains('detail-row')) {
                    tbody.appendChild(detail);
                }
            });

            table.querySelectorAll('th').forEach((th, i) => {
                th.classList.remove('sorted-asc', 'sorted-desc');
                if (i === colIdx) {
                    th.classList.add(currentSort.asc ? 'sorted-asc' : 'sorted-desc');
                }
            });
        }
    </script>
</body>
</html>
"""


def generate_dashboard(output_path: str = None) -> str:
    """Generate the HTML dashboard and return the file path."""
    config.REPORT_DIR.mkdir(parents=True, exist_ok=True)

    if output_path is None:
        output_path = str(config.REPORT_DIR / "dashboard.html")

    all_jobs = db.get_all_jobs(min_score=config.TIER_WORTH_CONSIDERING)
    stretch_jobs = [j for j in all_jobs if j.is_stretch]
    stats = db.get_job_count()

    # Calculate average salary of top 20
    top_salaries = []
    for job in all_jobs[:20]:
        sal = job.salary_midpoint
        if sal and sal >= 50000:
            top_salaries.append(sal)

    avg_salary = f"${sum(top_salaries)/len(top_salaries):,.0f}" if top_salaries else "N/A"

    template = Template(DASHBOARD_TEMPLATE)
    html = template.render(
        jobs=all_jobs,
        stretch_jobs=stretch_jobs,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        total_jobs=stats.get('total', 0),
        dream_count=stats.get('tier_dream_job', 0),
        strong_count=stats.get('tier_strong_match', 0),
        consider_count=stats.get('tier_worth_considering', 0),
        stretch_count=len(stretch_jobs),
        applied_count=stats.get('status_applied', 0),
        avg_salary=avg_salary,
        db_path=str(config.DB_PATH),
        now=datetime.now(),
    )

    with open(output_path, 'w') as f:
        f.write(html)

    # Also write as index.html for GitHub Pages (serves at root URL)
    index_path = config.REPORT_DIR / "index.html"
    with open(index_path, 'w') as f:
        f.write(html)

    return output_path


def generate_csv(output_path: str = None) -> str:
    """Export jobs to CSV."""
    import csv

    if output_path is None:
        output_path = str(config.REPORT_DIR / "jobs_export.csv")

    config.REPORT_DIR.mkdir(parents=True, exist_ok=True)

    all_jobs = db.get_all_jobs(min_score=0)

    headers = [
        "Composite", "Fit", "Quality", "Tier", "Title", "Company",
        "Salary", "Location", "Remote", "Source", "Posted", "Status", "URL",
        "Qualifications", "Location Score", "Resume Fit", "Interview Prob",
        "Compensation", "Security", "Company Quality", "Benefits", "Speed",
        "Stretch", "Severity", "Gap Analysis"
    ]

    with open(output_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(headers)

        for job in all_jobs:
            writer.writerow([
                f"{job.score_total:.0f}",
                f"{job.score_obtainability:.0f}",
                f"{job.score_desirability:.0f}",
                job.tier,
                job.title,
                job.company,
                job.display_salary,
                job.location,
                "Remote" if job.is_remote else ("Hybrid" if job.is_hybrid else "Onsite"),
                job.source,
                job.posted_date[:10] if job.posted_date else "",
                job.status,
                job.url or job.apply_url,
                f"{job.score_qualifications:.0f}",
                f"{job.score_location:.0f}",
                f"{job.score_resume_fit:.0f}",
                f"{job.score_interview_prob:.0f}",
                f"{job.score_compensation:.0f}",
                f"{job.score_job_security:.0f}",
                f"{job.score_company_quality:.0f}",
                f"{job.score_benefits:.0f}",
                f"{job.score_interview_speed:.0f}",
                "Yes" if job.is_stretch else "",
                job.stretch_severity or "",
                job.stretch_gap_analysis[:200] if job.stretch_gap_analysis else "",
            ])

    return output_path
