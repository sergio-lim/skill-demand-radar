#!/usr/bin/env python3
"""Skill Demand Radar CLI.

    python3 main.py --all      fetch + aggregate + write docs (default)
    python3 main.py --fetch    fetch only, print source status
    python3 main.py --report   re-render docs from the latest snapshot
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from radar.aggregate import aggregate_jobs, latest_report
from radar.fetchers import fetch_all
from radar.report import write_reports

ROOT = Path(__file__).resolve().parent


def _print_summary(data) -> None:
    sources = ", ".join(data.sources) if data.sources else "none"
    print("Skill Demand Radar")
    print("==================")
    fetched = data.fetched_jobs or data.total_jobs
    print(
        f"Jobs: {data.total_jobs} tech / {fetched} fetched"
        f"  |  Sources: {sources}  |  Date: {data.date}"
    )
    if data.previous_date:
        print(f"Compared with: {data.previous_date}")
    if data.warnings:
        print("Warnings:")
        for warning in data.warnings:
            print(f"  - {warning}")
    print()
    print("Top 10 skills")
    for index, (skill, count, delta) in enumerate(data.top_skills(10), start=1):
        arrow = f"{delta:+d}" if data.previous_date else "new"
        print(f"  {index:>2}. {skill:<20} {count:>5}  ({arrow})")
    print()
    print("Top 5 roles")
    for index, (role, count) in enumerate(data.top_roles(5), start=1):
        print(f"  {index:>2}. {role:<20} {count:>5}")


def _maybe_render_png() -> Path | None:
    script = ROOT / "tools" / "make_dashboard_png.py"
    if not script.is_file():
        return None
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "png render failed").strip()
        print(f"warning: dashboard.png skipped ({detail})", file=sys.stderr)
        return None
    if result.stdout:
        print(result.stdout.strip())
    path = ROOT / "assets" / "dashboard.png"
    return path if path.is_file() else None


def cmd_fetch() -> int:
    result = fetch_all()
    print(f"fetched {len(result.jobs)} jobs from: {', '.join(result.sources) or 'none'}")
    for warning in result.warnings:
        print(f"warning: {warning}")
    return 0


def cmd_report() -> int:
    data = latest_report()
    if data is None:
        print("no snapshot in data/history/; run --all first", file=sys.stderr)
        return 1
    html_path, md_path = write_reports(data)
    png_path = _maybe_render_png()
    _print_summary(data)
    print()
    print(f"Wrote {html_path.relative_to(ROOT)}")
    print(f"Wrote {md_path.relative_to(ROOT)}")
    if png_path:
        print(f"Wrote {png_path.relative_to(ROOT)}")
    return 0


def cmd_all() -> int:
    fetched = fetch_all()
    data = aggregate_jobs(
        fetched.jobs,
        sources=fetched.sources,
        warnings=fetched.warnings,
    )
    html_path, md_path = write_reports(data)
    png_path = _maybe_render_png()
    _print_summary(data)
    print()
    print(f"Wrote {html_path.relative_to(ROOT)}")
    print(f"Wrote {md_path.relative_to(ROOT)}")
    print(f"Wrote data/history/{data.date}.json")
    if png_path:
        print(f"Wrote {png_path.relative_to(ROOT)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Measure which tech skills public job boards are asking for.",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--all", action="store_true", help="fetch, aggregate, write docs (default)")
    group.add_argument("--fetch", action="store_true", help="fetch sources only")
    group.add_argument("--report", action="store_true", help="re-render docs from the latest snapshot")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.fetch:
        return cmd_fetch()
    if args.report:
        return cmd_report()
    return cmd_all()


if __name__ == "__main__":
    raise SystemExit(main())
