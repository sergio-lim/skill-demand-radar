"""Render the static dashboard (HTML) and the Markdown report."""

from __future__ import annotations

from html import escape
from pathlib import Path

from radar.aggregate import ReportData
from radar.taxonomy import COUNTRY_FLAGS, SKILLS

ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "docs"
ATTRIBUTION = (
    "Job data from Remote OK (https://remoteok.com) and "
    "Arbeitnow (https://www.arbeitnow.com)."
)


def _pct(count: int, maximum: int) -> float:
    if maximum <= 0:
        return 0.0
    return 100.0 * count / maximum


def _delta_html(delta: int, has_previous: bool) -> str:
    if not has_previous:
        return '<span class="delta flat">new</span>'
    if delta > 0:
        return f'<span class="delta up">&#8593; {delta}</span>'
    if delta < 0:
        return f'<span class="delta down">&#8595; {abs(delta)}</span>'
    return '<span class="delta flat">&#8594; 0</span>'


def _delta_md(delta: int, has_previous: bool) -> str:
    if not has_previous:
        return "new"
    if delta > 0:
        return f"↑ {delta}"
    if delta < 0:
        return f"↓ {abs(delta)}"
    return "→ 0"


def _bar_rows(
    items: list[tuple[str, int]],
    *,
    maximum: int,
    limit: int,
    flags: dict[str, str] | None = None,
) -> str:
    chunks: list[str] = []
    for label, count in items[:limit]:
        width = max(4.0, _pct(count, maximum)) if count else 0.0
        prefix = ""
        if flags is not None:
            code = flags.get(label, "")
            if code:
                prefix = f'<span class="flag">{escape(code)}</span> '
        chunks.append(
            "<div class='bar-row'>"
            f"<span class='bar-label'>{prefix}{escape(label)}</span>"
            "<span class='bar-track'>"
            f"<span class='bar-fill' style='width:{width:.1f}%'></span>"
            "</span>"
            f"<span class='bar-count'>{count}</span>"
            "</div>"
        )
    return "\n".join(chunks)


def _skill_table(data: ReportData, limit: int = 15) -> str:
    has_previous = data.previous_date is not None
    rows: list[str] = []
    for index, (skill, count) in enumerate(list(data.skills.items())[:limit], start=1):
        delta = data.skill_deltas.get(skill, 0)
        share = _pct(count, data.total_jobs)
        rows.append(
            "<tr>"
            f"<td class='rank'>{index}</td>"
            f"<td class='skill'>{escape(skill)}</td>"
            f"<td class='num'>{count}</td>"
            f"<td class='num muted'>{share:.0f}%</td>"
            f"<td>{_delta_html(delta, has_previous)}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def _source_pills(sources: list[str]) -> str:
    if not sources:
        return "<span class='pill'>no sources</span>"
    return " ".join(f"<span class='pill'>{escape(name)}</span>" for name in sources)


def _warning_block(warnings: list[str]) -> str:
    if not warnings:
        return ""
    items = "".join(f"<li>{escape(item)}</li>" for item in warnings)
    return (
        "<section class='card warn'>"
        "<h2>Source notes</h2>"
        f"<ul class='notes'>{items}</ul>"
        "</section>"
    )


def render_index_html(data: ReportData) -> str:
    """Return a self-contained HTML dashboard (inline CSS, no external JS)."""

    skill_max = max(data.skills.values()) if data.skills else 1
    role_max = max(data.roles.values()) if data.roles else 1
    country_max = max(data.countries.values()) if data.countries else 1
    compared = (
        f"deltas vs {escape(data.previous_date)}"
        if data.previous_date
        else "first snapshot — deltas appear tomorrow"
    )
    top_skill = next(iter(data.skills), "—")
    top_role = next(iter(data.roles), "—")
    tracked = len(data.skills)
    taxonomy_size = len(SKILLS)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Skill Demand Radar — {escape(data.date)}</title>
  <style>
    :root {{
      --bg: #070b14;
      --bg-2: #0c1220;
      --card: #121a2b;
      --card-2: #172136;
      --line: #243049;
      --text: #e8eef8;
      --muted: #8b9bb4;
      --accent: #3ee0b3;
      --accent-2: #7c9cff;
      --accent-3: #f5c16c;
      --down: #ff7b93;
      --up-bg: rgba(62, 224, 179, 0.12);
      --down-bg: rgba(255, 123, 147, 0.12);
      --shadow: 0 18px 50px rgba(0, 0, 0, 0.35);
      --radius: 18px;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ margin: 0; padding: 0; }}
    body {{
      font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background:
        radial-gradient(1200px 600px at 10% -10%, rgba(62, 224, 179, 0.10), transparent 50%),
        radial-gradient(900px 500px at 110% 0%, rgba(124, 156, 255, 0.12), transparent 45%),
        var(--bg);
      color: var(--text);
      min-height: 100vh;
    }}
    .wrap {{ max-width: 1120px; margin: 0 auto; padding: 36px 22px 64px; }}
    header.hero {{
      display: flex; flex-wrap: wrap; gap: 18px; justify-content: space-between;
      align-items: flex-end; margin-bottom: 28px;
    }}
    .eyebrow {{
      color: var(--accent); letter-spacing: 0.16em; text-transform: uppercase;
      font-size: 11px; font-weight: 700; margin: 0 0 8px;
    }}
    h1 {{
      font-size: clamp(28px, 4vw, 42px); line-height: 1.1; margin: 0 0 8px;
      letter-spacing: -0.03em;
    }}
    .lede {{ color: var(--muted); max-width: 560px; margin: 0; line-height: 1.55; }}
    .meta {{
      text-align: right; color: var(--muted); font-size: 13px; line-height: 1.6;
    }}
    .meta strong {{ color: var(--text); }}
    .kpis {{
      display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin: 0 0 18px;
    }}
    .kpi {{
      background: linear-gradient(180deg, var(--card-2), var(--card));
      border: 1px solid var(--line); border-radius: var(--radius);
      padding: 18px 18px 16px; box-shadow: var(--shadow);
    }}
    .kpi .label {{ color: var(--muted); font-size: 12px; letter-spacing: 0.04em; text-transform: uppercase; }}
    .kpi .value {{ font-size: 30px; font-weight: 700; letter-spacing: -0.03em; margin: 6px 0 2px; }}
    .kpi .hint {{ color: var(--muted); font-size: 12px; }}
    .grid {{ display: grid; grid-template-columns: 1.35fr 0.85fr; gap: 14px; }}
    .card {{
      background: var(--card); border: 1px solid var(--line); border-radius: var(--radius);
      padding: 22px; box-shadow: var(--shadow);
    }}
    .card h2 {{ margin: 0 0 4px; font-size: 18px; letter-spacing: -0.02em; }}
    .sub {{ color: var(--muted); font-size: 12px; margin: 0 0 16px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th {{
      text-align: left; color: var(--muted); font-size: 11px; letter-spacing: 0.08em;
      text-transform: uppercase; font-weight: 600; padding: 0 8px 10px;
      border-bottom: 1px solid var(--line);
    }}
    td {{ padding: 10px 8px; border-bottom: 1px solid rgba(36, 48, 73, 0.7); font-size: 14px; }}
    tr:last-child td {{ border-bottom: none; }}
    td.rank {{ color: var(--muted); width: 28px; }}
    td.skill {{ font-weight: 600; }}
    td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .muted {{ color: var(--muted); }}
    .delta {{
      display: inline-block; min-width: 52px; text-align: center;
      border-radius: 999px; padding: 2px 8px; font-size: 12px; font-weight: 600;
    }}
    .delta.up {{ color: var(--accent); background: var(--up-bg); }}
    .delta.down {{ color: var(--down); background: var(--down-bg); }}
    .delta.flat {{ color: var(--muted); background: rgba(139, 155, 180, 0.10); }}
    .bar-row {{
      display: grid; grid-template-columns: 140px 1fr 42px; gap: 10px;
      align-items: center; margin: 0 0 10px;
    }}
    .bar-label {{ font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    .bar-track {{
      height: 9px; background: #0d1524; border-radius: 999px; overflow: hidden;
      border: 1px solid var(--line);
    }}
    .bar-fill {{
      display: block; height: 100%; border-radius: 999px;
      background: linear-gradient(90deg, var(--accent-2), var(--accent));
    }}
    .roles .bar-fill {{ background: linear-gradient(90deg, #8b7cff, #7c9cff); }}
    .bar-count {{ text-align: right; font-variant-numeric: tabular-nums; color: var(--muted); font-size: 12px; }}
    .flag {{
      display: inline-block; font-size: 10px; letter-spacing: 0.06em; color: var(--accent-3);
      border: 1px solid rgba(245, 193, 108, 0.25); border-radius: 4px; padding: 0 4px;
      margin-right: 2px;
    }}
    .pills {{ display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-end; }}
    .pill {{
      border: 1px solid var(--line); background: #0e1626; color: var(--text);
      border-radius: 999px; padding: 4px 10px; font-size: 12px;
    }}
    .warn {{ border-color: rgba(245, 193, 108, 0.35); }}
    .notes {{ margin: 8px 0 0; padding-left: 18px; color: var(--accent-3); }}
    footer {{
      margin-top: 22px; color: var(--muted); font-size: 12px; line-height: 1.7;
      display: flex; flex-wrap: wrap; justify-content: space-between; gap: 10px;
    }}
    footer a {{ color: var(--accent); text-decoration: none; }}
    footer a:hover {{ text-decoration: underline; }}
    .stack {{ display: grid; gap: 14px; }}
    @media (max-width: 860px) {{
      .kpis {{ grid-template-columns: 1fr 1fr; }}
      .grid {{ grid-template-columns: 1fr; }}
      .meta, header.hero {{ text-align: left; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <header class="hero">
      <div>
        <p class="eyebrow">Public labour-market radar</p>
        <h1>What skills does the market actually want?</h1>
        <p class="lede">
          Daily snapshot of tech job posts from public, keyless APIs.
          Skills are extracted with a transparent keyword taxonomy — no login, no scrape fight.
        </p>
      </div>
      <div class="meta">
        <div><strong>Updated</strong> {escape(data.date)}</div>
        <div>{escape(compared)}</div>
        <div class="pills" style="margin-top:10px">{_source_pills(data.sources)}</div>
      </div>
    </header>

    <section class="kpis">
      <article class="kpi">
        <div class="label">Open roles</div>
        <div class="value">{data.total_jobs}</div>
        <div class="hint">tech-relevant of {data.fetched_jobs or data.total_jobs} fetched</div>
      </article>
      <article class="kpi">
        <div class="label">Skills detected</div>
        <div class="value">{tracked}</div>
        <div class="hint">of {taxonomy_size} in the taxonomy</div>
      </article>
      <article class="kpi">
        <div class="label">Top skill</div>
        <div class="value" style="font-size:22px;padding-top:6px">{escape(top_skill)}</div>
        <div class="hint">{data.skills.get(top_skill, 0)} mentions</div>
      </article>
      <article class="kpi">
        <div class="label">Top role</div>
        <div class="value" style="font-size:22px;padding-top:6px">{escape(top_role)}</div>
        <div class="hint">{data.roles.get(top_role, 0)} postings</div>
      </article>
    </section>

    {_warning_block(data.warnings)}

    <div class="grid">
      <section class="card">
        <h2>Top 15 skills</h2>
        <p class="sub">Share is mentions / jobs. A posting can mention several skills.</p>
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>Skill</th>
              <th style="text-align:right">Count</th>
              <th style="text-align:right">Share</th>
              <th>Delta</th>
            </tr>
          </thead>
          <tbody>
            {_skill_table(data, 15)}
          </tbody>
        </table>
      </section>

      <div class="stack">
        <section class="card roles">
          <h2>Roles</h2>
          <p class="sub">Classified from title, then description.</p>
          {_bar_rows(list(data.roles.items()), maximum=role_max, limit=10)}
        </section>
        <section class="card">
          <h2>Countries</h2>
          <p class="sub">Normalized from free-text location. Remote stays Remote.</p>
          {_bar_rows(list(data.countries.items()), maximum=country_max, limit=10, flags=COUNTRY_FLAGS)}
        </section>
      </div>
    </div>

    <section class="card" style="margin-top:14px">
      <h2>Demand bars — full skill list</h2>
      <p class="sub">Every skill that appeared at least once, scaled to the current leader ({escape(top_skill)}).</p>
      {_bar_rows(list(data.skills.items()), maximum=skill_max, limit=40)}
    </section>

    <footer>
      <div>
        Job data from <a href="https://remoteok.com">Remote OK</a>
        and <a href="https://www.arbeitnow.com">Arbeitnow</a>.<br>
        Keyword taxonomy — implicit skills are under-counted. Remote boards bias the sample.
      </div>
      <div>Skill Demand Radar · MIT · {escape(data.date)}</div>
    </footer>
  </div>
</body>
</html>
"""


def render_markdown(data: ReportData) -> str:
    """Return a recruiter-friendly Markdown report."""

    has_previous = data.previous_date is not None
    compared = data.previous_date or "none (first snapshot)"
    skill_lines = [
        "| # | Skill | Count | Share | Delta |",
        "|--:|:------|------:|------:|:------|",
    ]
    for index, (skill, count) in enumerate(list(data.skills.items())[:15], start=1):
        share = _pct(count, data.total_jobs)
        delta = _delta_md(data.skill_deltas.get(skill, 0), has_previous)
        skill_lines.append(
            f"| {index} | {skill} | {count} | {share:.0f}% | {delta} |"
        )

    role_lines = [
        "| Role | Count |",
        "|:-----|------:|",
    ]
    for role, count in list(data.roles.items())[:10]:
        role_lines.append(f"| {role} | {count} |")

    country_lines = [
        "| Country | Count |",
        "|:--------|------:|",
    ]
    for country, count in list(data.countries.items())[:10]:
        country_lines.append(f"| {country} | {count} |")

    warning_block = ""
    if data.warnings:
        items = "\n".join(f"- {item}" for item in data.warnings)
        warning_block = f"\n## Source notes\n\n{items}\n"

    sources = ", ".join(data.sources) if data.sources else "none"
    return (
        f"# Skill Demand Radar — {data.date}\n\n"
        f"- Jobs: **{data.total_jobs}**\n"
        f"- Sources: {sources}\n"
        f"- Compared with: {compared}\n"
        f"{warning_block}\n"
        f"## Top 15 skills\n\n"
        + "\n".join(skill_lines)
        + "\n\n## Roles\n\n"
        + "\n".join(role_lines)
        + "\n\n## Countries\n\n"
        + "\n".join(country_lines)
        + f"\n\n---\n\n{ATTRIBUTION}\n"
    )


def write_reports(data: ReportData, docs_dir: Path | None = None) -> tuple[Path, Path]:
    """Write ``docs/index.html`` and ``docs/report.md``."""

    folder = docs_dir or DOCS_DIR
    folder.mkdir(parents=True, exist_ok=True)
    html_path = folder / "index.html"
    md_path = folder / "report.md"
    html_path.write_text(render_index_html(data), encoding="utf-8")
    md_path.write_text(render_markdown(data), encoding="utf-8")
    return html_path, md_path
