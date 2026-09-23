"""Aggregate extracted skills / roles / countries and persist snapshots."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from radar.extract import classify_role, extract_job_skills, is_tech_job, normalize_location
from radar.fetchers import Job

ROOT = Path(__file__).resolve().parent.parent
HISTORY_DIR = ROOT / "data" / "history"


@dataclass
class ReportData:
    """Fully-baked numbers for the HTML / Markdown renderers."""

    date: str
    total_jobs: int
    skills: dict[str, int]
    roles: dict[str, int]
    countries: dict[str, int]
    skill_deltas: dict[str, int]
    fetched_jobs: int = 0
    sources: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    previous_date: str | None = None

    def top_skills(self, n: int = 10) -> list[tuple[str, int, int]]:
        rows: list[tuple[str, int, int]] = []
        for skill, count in list(self.skills.items())[:n]:
            rows.append((skill, count, self.skill_deltas.get(skill, 0)))
        return rows

    def top_roles(self, n: int = 5) -> list[tuple[str, int]]:
        return list(self.roles.items())[:n]

    def to_snapshot(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "total_jobs": self.total_jobs,
            "fetched_jobs": self.fetched_jobs,
            "skills": self.skills,
            "roles": self.roles,
            "countries": self.countries,
            "sources": self.sources,
        }


def _today() -> str:
    return date.today().isoformat()


def _sorted_counter(counter: Counter[str]) -> dict[str, int]:
    return dict(sorted(counter.items(), key=lambda item: (-item[1], item[0])))


def _snapshot_date(path: Path) -> str:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        raw = payload.get("date")
        if isinstance(raw, str) and len(raw) >= 10:
            return raw[:10]
    except (OSError, json.JSONDecodeError, AttributeError):
        pass
    return path.stem


def list_snapshots(history_dir: Path | None = None) -> list[Path]:
    folder = history_dir or HISTORY_DIR
    if not folder.is_dir():
        return []
    paths = [path for path in folder.glob("*.json") if path.is_file()]
    return sorted(paths, key=_snapshot_date)


def load_snapshot(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"snapshot {path} is not an object")
    return payload


def previous_snapshot(
    today: str,
    history_dir: Path | None = None,
) -> dict[str, Any] | None:
    """Return the most recent snapshot strictly before ``today``."""

    candidates: list[tuple[str, dict[str, Any]]] = []
    for path in list_snapshots(history_dir):
        payload = load_snapshot(path)
        stamp = str(payload.get("date") or path.stem)[:10]
        if stamp < today:
            candidates.append((stamp, payload))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[-1][1]


def save_snapshot(data: ReportData, history_dir: Path | None = None) -> Path:
    folder = history_dir or HISTORY_DIR
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{data.date}.json"
    path.write_text(
        json.dumps(data.to_snapshot(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def compute_skill_deltas(
    current: dict[str, int],
    previous: dict[str, int] | None,
) -> dict[str, int]:
    if not previous:
        return {skill: 0 for skill in current}
    deltas: dict[str, int] = {}
    keys = set(current) | set(previous)
    for skill in keys:
        deltas[skill] = int(current.get(skill, 0)) - int(previous.get(skill, 0))
    return deltas


def aggregate_jobs(
    jobs: list[Job],
    sources: list[str] | None = None,
    warnings: list[str] | None = None,
    today: str | None = None,
    history_dir: Path | None = None,
    persist: bool = True,
) -> ReportData:
    """Count skills, roles and countries, then persist today's snapshot."""

    stamp = today or _today()
    skill_counts: Counter[str] = Counter()
    role_counts: Counter[str] = Counter()
    country_counts: Counter[str] = Counter()

    included = 0
    for job in jobs:
        skills_found = extract_job_skills(
            job.title, job.description, job.tags, source=job.source
        )
        role = classify_role(job.title, job.description, skills=skills_found)
        if not is_tech_job(job.title, skills_found, role):
            continue
        included += 1
        skill_counts.update(skills_found)
        role_counts[role] += 1
        country_counts[
            normalize_location(job.location, remote=job.remote, source=job.source)
        ] += 1

    skills = _sorted_counter(skill_counts)
    roles = _sorted_counter(role_counts)
    countries = _sorted_counter(country_counts)

    prior = previous_snapshot(stamp, history_dir=history_dir)
    prior_skills = prior.get("skills") if prior else None
    if not isinstance(prior_skills, dict):
        prior_skills = None
    deltas = compute_skill_deltas(skills, prior_skills)

    report = ReportData(
        date=stamp,
        total_jobs=included,
        fetched_jobs=len(jobs),
        skills=skills,
        roles=roles,
        countries=countries,
        skill_deltas=deltas,
        sources=list(sources or []),
        warnings=list(warnings or []),
        previous_date=str(prior["date"]) if prior and prior.get("date") else None,
    )
    if persist:
        save_snapshot(report, history_dir=history_dir)
    return report


def report_from_snapshot(
    snapshot: dict[str, Any],
    previous: dict[str, Any] | None = None,
    sources: list[str] | None = None,
    warnings: list[str] | None = None,
) -> ReportData:
    """Rebuild ``ReportData`` from a stored snapshot (no re-fetch)."""

    skills = {
        str(key): int(value)
        for key, value in (snapshot.get("skills") or {}).items()
    }
    roles = {
        str(key): int(value)
        for key, value in (snapshot.get("roles") or {}).items()
    }
    countries = {
        str(key): int(value)
        for key, value in (snapshot.get("countries") or {}).items()
    }
    skills = dict(sorted(skills.items(), key=lambda item: (-item[1], item[0])))
    roles = dict(sorted(roles.items(), key=lambda item: (-item[1], item[0])))
    countries = dict(sorted(countries.items(), key=lambda item: (-item[1], item[0])))
    prior_skills = previous.get("skills") if previous else None
    if not isinstance(prior_skills, dict):
        prior_skills = None
    return ReportData(
        date=str(snapshot.get("date") or _today()),
        total_jobs=int(snapshot.get("total_jobs") or 0),
        fetched_jobs=int(snapshot.get("fetched_jobs") or snapshot.get("total_jobs") or 0),
        skills=skills,
        roles=roles,
        countries=countries,
        skill_deltas=compute_skill_deltas(skills, prior_skills),
        sources=list(sources or snapshot.get("sources") or []),
        warnings=list(warnings or []),
        previous_date=str(previous["date"]) if previous and previous.get("date") else None,
    )


def latest_report(history_dir: Path | None = None) -> ReportData | None:
    paths = list_snapshots(history_dir)
    if not paths:
        return None
    latest = load_snapshot(paths[-1])
    prior = previous_snapshot(str(latest.get("date") or paths[-1].stem), history_dir)
    return report_from_snapshot(latest, previous=prior)


def parse_iso_date(value: str) -> datetime:
    return datetime.strptime(value[:10], "%Y-%m-%d")
