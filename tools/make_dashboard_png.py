#!/usr/bin/env python3
"""Render assets/dashboard.png from the latest history snapshot (Pillow only)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
HISTORY = ROOT / "data" / "history"
OUTPUT = ROOT / "assets" / "dashboard.png"

WIDTH = 1400
HEIGHT = 900
BG = (7, 11, 20)
CARD = (18, 26, 43)
LINE = (36, 48, 73)
TEXT = (232, 238, 248)
MUTED = (139, 155, 180)
ACCENT = (62, 224, 179)
BLUE = (124, 156, 255)
AMBER = (245, 193, 108)
DOWN = (255, 123, 147)
TRACK = (13, 21, 36)

FONT_CANDIDATES = (
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    Path("/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf"),
    Path("/usr/share/fonts/TTF/DejaVuSans.ttf"),
)
FONT_BOLD_CANDIDATES = (
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    Path("/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf"),
    Path("/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),
)


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    paths = FONT_BOLD_CANDIDATES if bold else FONT_CANDIDATES
    for path in paths:
        if path.is_file():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _latest_pair() -> tuple[dict, dict | None]:
    paths = sorted(HISTORY.glob("*.json"))
    if not paths:
        raise FileNotFoundError("no snapshots in data/history/; run python3 main.py --all first")
    current = json.loads(paths[-1].read_text(encoding="utf-8"))
    previous = None
    if len(paths) >= 2:
        previous = json.loads(paths[-2].read_text(encoding="utf-8"))
        if str(previous.get("date")) >= str(current.get("date")):
            previous = None
    return current, previous


def _round_card(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int]) -> None:
    draw.rounded_rectangle(box, radius=22, fill=CARD, outline=LINE, width=1)


def _bar(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    width: int,
    value: int,
    maximum: int,
    color: tuple[int, int, int],
) -> None:
    draw.rounded_rectangle((x, y, x + width, y + 10), radius=5, fill=TRACK, outline=LINE)
    fill = 8 if value <= 0 or maximum <= 0 else max(8, int(width * value / maximum))
    draw.rounded_rectangle((x, y, x + fill, y + 10), radius=5, fill=color)


def render_dashboard_png() -> Path:
    current, previous = _latest_pair()
    date = str(current.get("date") or "")
    total = int(current.get("total_jobs") or 0)
    fetched = int(current.get("fetched_jobs") or total)
    skills = current.get("skills") or {}
    roles = current.get("roles") or {}
    countries = current.get("countries") or {}
    prev_skills = (previous or {}).get("skills") or {}

    skill_items = sorted(skills.items(), key=lambda item: (-int(item[1]), item[0]))
    role_items = sorted(roles.items(), key=lambda item: (-int(item[1]), item[0]))
    country_items = sorted(countries.items(), key=lambda item: (-int(item[1]), item[0]))

    top_skill = skill_items[0][0] if skill_items else "—"
    top_role = role_items[0][0] if role_items else "—"

    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)

    title = _font(36, bold=True)
    lede = _font(16)
    label = _font(12)
    kpi = _font(32, bold=True)
    body = _font(15)
    small = _font(13)
    tiny = _font(11)

    draw.text((48, 36), "SKILL DEMAND RADAR", font=tiny, fill=ACCENT)
    draw.text((48, 56), "What the market is hiring for", font=title, fill=TEXT)
    draw.text(
        (48, 106),
        "Public job boards  ·  no API keys  ·  keyword taxonomy",
        font=lede,
        fill=MUTED,
    )
    draw.text((1080, 56), date, font=kpi, fill=TEXT)
    draw.text((1080, 100), "daily snapshot", font=small, fill=MUTED)

    cards = [
        (48, 148, 360, 248, "OPEN ROLES", str(total), f"tech-relevant of {fetched} fetched"),
        (376, 148, 688, 248, "SKILLS HIT", str(len(skill_items)), "in this run"),
        (704, 148, 1016, 248, "TOP SKILL", top_skill, f"{skill_items[0][1] if skill_items else 0} mentions"),
        (1032, 148, 1352, 248, "TOP ROLE", top_role, f"{role_items[0][1] if role_items else 0} postings"),
    ]
    for x0, y0, x1, y1, k, v, hint in cards:
        _round_card(draw, (x0, y0, x1, y1))
        draw.text((x0 + 22, y0 + 16), k, font=tiny, fill=MUTED)
        draw.text((x0 + 22, y0 + 38), v[:16], font=kpi, fill=TEXT)
        draw.text((x0 + 22, y1 - 32), hint, font=small, fill=MUTED)

    _round_card(draw, (48, 268, 860, 852))
    draw.text((72, 290), "Top 12 skills", font=_font(20, bold=True), fill=TEXT)
    compared = f"delta vs {previous['date']}" if previous else "first snapshot"
    draw.text((72, 318), compared, font=small, fill=MUTED)

    skill_max = max((int(v) for _, v in skill_items[:12]), default=1)
    y = 354
    for index, (skill, count) in enumerate(skill_items[:12], start=1):
        count_i = int(count)
        prev = int(prev_skills.get(skill, 0)) if previous else 0
        delta = count_i - prev if previous else 0
        draw.text((72, y), f"{index:02d}", font=small, fill=MUTED)
        draw.text((108, y), str(skill), font=body, fill=TEXT)
        _bar(draw, 340, y + 6, 360, count_i, skill_max, ACCENT if index <= 3 else BLUE)
        draw.text((714, y), str(count_i), font=body, fill=TEXT)
        if previous:
            if delta > 0:
                draw.text((780, y), f"↑ {delta}", font=small, fill=ACCENT)
            elif delta < 0:
                draw.text((780, y), f"↓ {abs(delta)}", font=small, fill=DOWN)
            else:
                draw.text((780, y), "→ 0", font=small, fill=MUTED)
        else:
            draw.text((780, y), "new", font=small, fill=AMBER)
        y += 40

    _round_card(draw, (880, 268, 1352, 548))
    draw.text((904, 290), "Roles", font=_font(20, bold=True), fill=TEXT)
    role_max = max((int(v) for _, v in role_items[:8]), default=1)
    y = 334
    for role, count in role_items[:8]:
        draw.text((904, y), str(role), font=small, fill=TEXT)
        _bar(draw, 1040, y + 4, 220, int(count), role_max, BLUE)
        draw.text((1274, y), str(count), font=small, fill=MUTED)
        y += 26

    _round_card(draw, (880, 568, 1352, 852))
    draw.text((904, 590), "Countries", font=_font(20, bold=True), fill=TEXT)
    country_max = max((int(v) for _, v in country_items[:8]), default=1)
    y = 634
    for country, count in country_items[:8]:
        label_text = str(country)[:18]
        draw.text((904, y), label_text, font=small, fill=TEXT)
        _bar(draw, 1080, y + 4, 180, int(count), country_max, AMBER)
        draw.text((1274, y), str(count), font=small, fill=MUTED)
        y += 26

    draw.text(
        (48, 868),
        "Job data from Remote OK (https://remoteok.com) and Arbeitnow (https://www.arbeitnow.com).",
        font=tiny,
        fill=MUTED,
    )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUTPUT, "PNG", optimize=True)
    return OUTPUT


def main() -> int:
    try:
        path = render_dashboard_png()
    except Exception as exc:
        print(f"dashboard png failed: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {path} ({path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
