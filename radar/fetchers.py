"""Keyless job fetchers (Arbeitnow + RemoteOK) with a bundled fallback."""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ARBEITNOW_URL = "https://www.arbeitnow.com/api/job-board-api"
REMOTEOK_URL = "https://remoteok.com/api"
USER_AGENT = "Mozilla/5.0"
TIMEOUT_SECONDS = 25

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_PATH = ROOT / "data" / "sample_jobs.json"


class _HTMLTextExtractor(HTMLParser):
    """Collect visible text from a (possibly messy) HTML fragment."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self._chunks.append(text)

    def get_text(self) -> str:
        return unescape(" ".join(self._chunks))


def strip_html(value: str) -> str:
    """Return plain text from HTML, falling back to a tag strip."""

    if not value:
        return ""
    extractor = _HTMLTextExtractor()
    try:
        extractor.feed(value)
        extractor.close()
        text = extractor.get_text()
    except Exception:
        text = ""
    if text:
        return text
    return unescape(re_sub_tags(value))


def re_sub_tags(value: str) -> str:
    """Minimal fallback when the HTML parser chokes."""

    return re.sub(r"<[^>]+>", " ", value)


@dataclass
class Job:
    """Normalized job posting used by extract/aggregate."""

    title: str
    description: str
    company: str
    location: str
    tags: tuple[str, ...]
    remote: bool
    url: str
    source: str
    date: str | None = None


@dataclass
class FetchResult:
    """Outcome of ``fetch_all`` including which sources actually contributed."""

    jobs: list[Job]
    sources: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _get_json(url: str, user_agent: str = USER_AGENT) -> Any:
    request = Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "application/json",
        },
        method="GET",
    )
    with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        payload = response.read()
    return json.loads(payload.decode("utf-8"))


def _as_tags(raw: Any) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, str):
        parts = [part.strip() for part in raw.replace(";", ",").split(",")]
        return tuple(part for part in parts if part)
    if isinstance(raw, (list, tuple)):
        tags: list[str] = []
        for item in raw:
            text = str(item).strip()
            if text:
                tags.append(text)
        return tuple(tags)
    return ()


def _as_bool(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    if raw is None:
        return False
    return str(raw).strip().lower() in {"1", "true", "yes", "remote"}


def _as_date(raw: Any) -> str | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, (int, float)):
        # RemoteOK sometimes ships a unix epoch.
        try:
            from datetime import datetime, timezone

            return datetime.fromtimestamp(int(raw), tz=timezone.utc).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    text = str(raw).strip()
    if not text:
        return None
    return text[:10] if len(text) >= 10 and text[4] == "-" else text


def job_from_mapping(raw: dict[str, Any], default_source: str = "sample") -> Job | None:
    """Build a ``Job`` from a loosely-shaped dict (live APIs or sample file)."""

    title = str(
        raw.get("title")
        or raw.get("position")
        or raw.get("job_title")
        or ""
    ).strip()
    if not title:
        return None
    description = strip_html(
        str(raw.get("description") or raw.get("description_text") or "")
    )
    company = str(
        raw.get("company_name") or raw.get("company") or raw.get("company_name") or ""
    ).strip()
    location = str(raw.get("location") or raw.get("candidate_required_location") or "").strip()
    tags = _as_tags(raw.get("tags") or raw.get("job_types"))
    remote = _as_bool(raw.get("remote"))
    if not remote and "remote" in location.lower():
        remote = True
    url = str(raw.get("url") or raw.get("apply_url") or "").strip()
    source = str(raw.get("source") or default_source).strip() or default_source
    date = _as_date(raw.get("date") or raw.get("created_at") or raw.get("epoch"))
    return Job(
        title=title,
        description=description,
        company=company,
        location=location,
        tags=tags,
        remote=remote,
        url=url,
        source=source,
        date=date,
    )


def fetch_arbeitnow() -> list[Job]:
    """Fetch the public Arbeitnow job-board JSON endpoint."""

    payload = _get_json(ARBEITNOW_URL)
    rows = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("arbeitnow: unexpected payload (missing data list)")
    jobs: list[Job] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        job = job_from_mapping(row, default_source="arbeitnow")
        if job is not None:
            jobs.append(job)
    if not jobs:
        raise ValueError("arbeitnow: no usable jobs in payload")
    return jobs


def fetch_remoteok() -> list[Job]:
    """Fetch RemoteOK's public API. The first element is a legal notice."""

    payload = _get_json(REMOTEOK_URL, user_agent="Mozilla/5.0")
    if not isinstance(payload, list):
        raise ValueError("remoteok: unexpected payload (expected a list)")
    jobs: list[Job] = []
    for index, row in enumerate(payload):
        if not isinstance(row, dict):
            continue
        if index == 0 and "position" not in row and "title" not in row:
            continue
        job = job_from_mapping(row, default_source="remoteok")
        if job is not None:
            jobs.append(job)
    if not jobs:
        raise ValueError("remoteok: no usable jobs in payload")
    return jobs


def load_sample_jobs(path: Path | None = None) -> list[Job]:
    """Load the bundled fallback corpus."""

    target = path or SAMPLE_PATH
    with target.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    rows = payload.get("jobs") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError(f"sample jobs: {target} is not a list")
    jobs: list[Job] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        job = job_from_mapping(row, default_source="sample")
        if job is not None:
            jobs.append(job)
    return jobs


def _dedupe(jobs: list[Job]) -> list[Job]:
    seen: set[str] = set()
    unique: list[Job] = []
    for job in jobs:
        key = job.url.strip().lower() if job.url else ""
        if not key:
            key = f"{job.title.lower()}|{job.company.lower()}|{job.source}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(job)
    return unique


def fetch_all(use_sample_on_empty: bool = True) -> FetchResult:
    """Fetch every live source; fall back to the bundled sample if needed."""

    jobs: list[Job] = []
    sources: list[str] = []
    warnings: list[str] = []

    for name, loader in (
        ("arbeitnow", fetch_arbeitnow),
        ("remoteok", fetch_remoteok),
    ):
        try:
            batch = loader()
        except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError, OSError) as exc:
            warnings.append(f"{name} failed: {exc}")
            print(f"warning: {name} failed ({exc})", file=sys.stderr)
            continue
        jobs.extend(batch)
        sources.append(name)

    jobs = _dedupe(jobs)
    if jobs:
        return FetchResult(jobs=jobs, sources=sources, warnings=warnings)

    if not use_sample_on_empty:
        return FetchResult(jobs=[], sources=sources, warnings=warnings)

    sample = load_sample_jobs()
    warnings.append(
        "all live sources failed or returned no jobs; using bundled data/sample_jobs.json"
    )
    print("warning: using bundled sample_jobs.json (live sources unavailable)", file=sys.stderr)
    return FetchResult(jobs=sample, sources=["sample"], warnings=warnings)
