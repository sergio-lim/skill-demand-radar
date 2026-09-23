from __future__ import annotations

from pathlib import Path
from urllib.error import URLError

import pytest

from radar.aggregate import (
    ReportData,
    aggregate_jobs,
    compute_skill_deltas,
    latest_report,
    previous_snapshot,
)
from radar.extract import (
    classify_role,
    extract_job_skills,
    extract_skills,
    infer_role_from_skills,
    is_tech_job,
    normalize_location,
)
from radar.fetchers import Job, _dedupe, fetch_all, job_from_mapping, strip_html
from radar.report import render_index_html, render_markdown, write_reports


def _job(**kwargs: object) -> Job:
    defaults = dict(
        title="Backend Engineer",
        description="Python Django APIs on Postgres.",
        company="Northwind Labs",
        location="Berlin, Germany",
        tags=("python",),
        remote=True,
        url="https://jobs.example.com/northwind-backend",
        source="sample",
    )
    defaults.update(kwargs)
    return Job(**defaults)  # type: ignore[arg-type]


def test_extract_skills_aliases_boundaries_and_empty() -> None:
    assert extract_skills("") == set()
    found = extract_skills("We need python3, k8s, and c++ on .net")
    assert {"python", "kubernetes", "c++", ".net"} <= found
    assert "java" not in extract_skills("javascript frontend with react")
    assert "javascript" in extract_skills("javascript frontend with react")


def test_remoteok_tags_are_ignored_but_sample_tags_count() -> None:
    ignored = extract_job_skills(
        "Sales Lead",
        "Close enterprise deals.",
        tags=["python", "kubernetes"],
        source="remoteok",
    )
    assert ignored == set()
    from_tags = extract_job_skills(
        "Sales Lead",
        "Close enterprise deals.",
        tags=["python"],
        source="sample",
    )
    assert from_tags == {"python"}


def test_classify_role_prefers_title_then_description_then_skills() -> None:
    assert classify_role("Senior ML Engineer") == "ml/ai"
    assert classify_role("Office Coordinator", "Looking for a frontend React developer") == "frontend"
    assert classify_role("Software Engineer", skills={"django", "flask"}) == "backend"
    assert infer_role_from_skills({"react", "django"}) == "fullstack"
    assert infer_role_from_skills(set()) == "other"


def test_is_tech_job_keeps_hard_skills_and_drops_sales() -> None:
    assert is_tech_job("Backend Engineer", {"python"}, "backend") is True
    assert is_tech_job("Coordinator", {"python", "docker"}, "other") is True
    assert is_tech_job("Account Executive", {"agile"}, "other") is False


def test_normalize_location_remote_city_and_empty() -> None:
    assert normalize_location("Berlin, Germany") == "Germany"
    assert normalize_location("Remote — Worldwide") == "Remote"
    assert normalize_location("Remote EMEA") == "EMEA"
    assert normalize_location("", remote=True) == "Remote"
    assert normalize_location("", source="remoteok") == "Remote"
    assert normalize_location("") == "Unknown"


def test_strip_html_and_job_from_mapping_edges() -> None:
    assert "Hi" in strip_html("<p>Hi <b>there</b></p>")
    assert job_from_mapping({"description": "no title"}) is None
    job = job_from_mapping(
        {
            "position": "Platform Engineer",
            "description": "<p>Own Kubernetes</p>",
            "company": "Helios Pay",
            "location": "Remote",
            "tags": "golang, kubernetes",
            "epoch": 1_700_000_000,
        },
        default_source="remoteok",
    )
    assert job is not None
    assert job.title == "Platform Engineer"
    assert "Kubernetes" in job.description
    assert "golang" in job.tags
    assert job.source == "remoteok"
    assert job.date == "2023-11-14"
    assert job.remote is True


def test_dedupe_prefers_url_then_title_company() -> None:
    first = _job(url="https://jobs.example.com/same")
    dup = _job(title="Other title", url="https://jobs.example.com/same")
    other = _job(title="Go Engineer", url="https://jobs.example.com/go")
    unique = _dedupe([first, dup, other])
    assert [job.url for job in unique] == [
        "https://jobs.example.com/same",
        "https://jobs.example.com/go",
    ]


def test_skill_deltas_first_snapshot_and_numeric_diff() -> None:
    assert compute_skill_deltas({"python": 5}, None) == {"python": 0}
    deltas = compute_skill_deltas({"python": 5, "go": 1}, {"python": 3, "rust": 2})
    assert deltas == {"python": 2, "go": 1, "rust": -2}


def test_aggregate_jobs_filters_non_tech_and_can_skip_persist(tmp_path: Path) -> None:
    jobs = [
        _job(),
        _job(
            title="Account Executive",
            description="Close deals and hit quota.",
            tags=(),
            url="https://jobs.example.com/sales",
            location="Remote",
        ),
    ]
    data = aggregate_jobs(
        jobs,
        sources=["sample"],
        persist=False,
        today="2026-09-23",
        history_dir=tmp_path,
    )
    assert data.total_jobs == 1
    assert data.fetched_jobs == 2
    assert data.roles.get("backend") == 1
    assert data.countries.get("Germany") == 1
    assert "python" in data.skills
    assert list(tmp_path.glob("*.json")) == []
    assert previous_snapshot("2026-09-23", history_dir=tmp_path) is None
    assert latest_report(history_dir=tmp_path) is None


def test_fetch_all_falls_back_to_sample_when_live_sources_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _offline() -> list[Job]:
        raise URLError("simulated-offline")

    monkeypatch.setattr("radar.fetchers.fetch_arbeitnow", _offline)
    monkeypatch.setattr("radar.fetchers.fetch_remoteok", _offline)
    result = fetch_all()
    assert result.sources == ["sample"]
    assert result.jobs
    assert any("sample" in warning.lower() or "bundled" in warning.lower() for warning in result.warnings)


def test_reports_escape_html_and_write_to_given_dir(tmp_path: Path) -> None:
    data = ReportData(
        date="2026-09-23",
        total_jobs=2,
        fetched_jobs=2,
        skills={"python": 2, "<script>": 1},
        roles={"backend": 2},
        countries={"Remote": 2},
        skill_deltas={"python": 1, "<script>": 0},
        sources=["sample"],
        previous_date="2026-09-22",
    )
    markdown = render_markdown(data)
    assert "| python |" in markdown
    assert "↑ 1" in markdown
    html = render_index_html(data)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    html_path, md_path = write_reports(data, docs_dir=tmp_path)
    assert html_path.parent == tmp_path
    assert md_path.read_text(encoding="utf-8").startswith("# Skill Demand Radar")
