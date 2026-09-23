"""Extract skills and classify roles from job text."""

from __future__ import annotations

import re
from functools import lru_cache

from radar.taxonomy import (
    CITY_TO_COUNTRY,
    GENERIC_TECH_TITLE,
    LOCATION_ALIASES,
    ROLE_PATTERNS,
    SKILL_ALIASES,
    SKILL_ROLE_HINTS,
    SOFT_SKILLS,
)


def _alias_pattern(alias: str) -> re.Pattern[str]:
    """Compile a case-insensitive pattern with ASCII word boundaries.

    Symbols such as ``+``, ``#``, ``.`` and ``/`` are escaped. We avoid
    ``\\b`` because it fails on tokens like ``c++`` and ``.net``.
    """

    escaped = re.escape(alias)
    return re.compile(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", re.IGNORECASE)


@lru_cache(maxsize=1)
def _skill_patterns() -> tuple[tuple[str, tuple[re.Pattern[str], ...]], ...]:
    compiled: list[tuple[str, tuple[re.Pattern[str], ...]]] = []
    for skill, aliases in SKILL_ALIASES.items():
        patterns = tuple(_alias_pattern(alias) for alias in aliases)
        compiled.append((skill, patterns))
    return tuple(compiled)


@lru_cache(maxsize=1)
def _role_patterns() -> tuple[tuple[re.Pattern[str], str], ...]:
    return tuple((re.compile(regex, re.IGNORECASE), role) for regex, role in ROLE_PATTERNS)


@lru_cache(maxsize=1)
def _generic_title() -> re.Pattern[str]:
    return re.compile(GENERIC_TECH_TITLE, re.IGNORECASE)


@lru_cache(maxsize=1)
def _alias_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for skill, aliases in SKILL_ALIASES.items():
        index[skill.lower()] = skill
        for alias in aliases:
            index[alias.lower()] = skill
    return index


def extract_skills(text: str) -> set[str]:
    """Return the set of taxonomy skills mentioned in ``text``."""

    if not text:
        return set()
    found: set[str] = set()
    for skill, patterns in _skill_patterns():
        for pattern in patterns:
            if pattern.search(text):
                found.add(skill)
                break
    return found


def extract_job_skills(
    title: str,
    description: str,
    tags: list[str] | tuple[str, ...] = (),
    source: str = "",
) -> set[str]:
    """Extract skills from title + description.

    Tags are used for Arbeitnow and the bundled sample. RemoteOK's tag list
    is a site-wide facet dump and is ignored to avoid false positives.
    """

    found = extract_skills(f"{title}\n{description}")
    if (source or "").lower() == "remoteok":
        return found
    index = _alias_index()
    for tag in tags or ():
        key = str(tag).strip().lower()
        if key in index:
            found.add(index[key])
    return found


def infer_role_from_skills(skills: set[str]) -> str:
    """Vote a role bucket from extracted skills. Tie → fullstack or other."""

    votes: dict[str, int] = {}
    for skill in skills:
        role = SKILL_ROLE_HINTS.get(skill)
        if role:
            votes[role] = votes.get(role, 0) + 1
    if not votes:
        return "other"
    if votes.get("frontend", 0) and votes.get("backend", 0):
        return "fullstack"
    return max(votes.items(), key=lambda item: (item[1], item[0]))[0]


def classify_role(title: str, description: str = "", skills: set[str] | None = None) -> str:
    """Map a job title (then description, then skills) to a role bucket."""

    for pattern, role in _role_patterns():
        if title and pattern.search(title):
            return role
    excerpt = (description or "")[:2500]
    for pattern, role in _role_patterns():
        if excerpt and pattern.search(excerpt):
            return role
    hinted = infer_role_from_skills(skills or set())
    if title and _generic_title().search(title):
        return hinted if hinted != "other" else "backend"
    return hinted


def is_tech_job(title: str, skills: set[str], role: str) -> bool:
    """Keep postings that look like tech work, drop sales/HR/linguistics."""

    if role != "other":
        return True
    hard = skills - SOFT_SKILLS
    if len(hard) >= 2:
        return True
    if title and _generic_title().search(title) and hard:
        return True
    return False


def _repair_mojibake(value: str) -> str:
    """Best-effort fix for UTF-8 text that was decoded as Latin-1."""

    if not value or value.isascii():
        return value
    try:
        repaired = value.encode("latin-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return value
    return repaired if repaired and repaired != value else value


def normalize_location(location: str, remote: bool = False, source: str = "") -> str:
    """Collapse a free-text location into a country / region label."""

    raw = _repair_mojibake((location or "").strip())
    if not raw:
        if remote or (source or "").lower() == "remoteok":
            return "Remote"
        return "Unknown"

    lowered = raw.lower()
    if any(
        token in lowered
        for token in ("remoto", "worldwide", "anywhere", "distributed", "work from home")
    ):
        return "Remote"
    if "remote" in lowered:
        if "emea" in lowered:
            return "EMEA"
        if "latam" in lowered:
            return "LATAM"
        if "apac" in lowered:
            return "APAC"
        if "europe" in lowered or "eu" in lowered.split():
            return "Europe"
        return "Remote"
    if "hybrid" in lowered:
        return "Hybrid"

    # Comma / slash only — do not split on hyphen (Nordrhein-Westfalen, Redwood City).
    segments = [part.strip() for part in re.split(r"[,|/–—]", raw) if part.strip()]
    candidates = [segments[-1], segments[0], raw] if segments else [raw]

    for candidate in candidates:
        key = candidate.lower().strip()
        if key in LOCATION_ALIASES:
            return LOCATION_ALIASES[key]
        if key in CITY_TO_COUNTRY:
            return CITY_TO_COUNTRY[key]

    for city, country in CITY_TO_COUNTRY.items():
        if city in lowered:
            return country
    for alias, country in LOCATION_ALIASES.items():
        if len(alias) >= 4 and alias in lowered:
            return country

    if remote:
        return "Remote"
    # Keep a short cleaned label rather than dropping the job.
    cleaned = segments[-1] if segments else raw
    return cleaned.title()[:40]


def job_skill_blob(title: str, description: str, tags: list[str] | tuple[str, ...]) -> str:
    """Concatenate the fields that are useful for skill matching."""

    tag_text = " ".join(tags or ())
    return f"{title}\n{tag_text}\n{description}"
