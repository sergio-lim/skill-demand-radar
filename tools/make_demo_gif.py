#!/usr/bin/env python3
"""Render assets/demo.gif from a canned CLI transcript.

Looks like a terminal: black background, monospace, green/white text,
lines appearing over time. This tool needs Pillow; the radar itself does not.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "assets" / "demo.gif"
FONT_CANDIDATES = (
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"),
    Path("/usr/share/fonts/truetype/ubuntu/UbuntuMono-R.ttf"),
    Path("/usr/share/fonts/TTF/DejaVuSansMono.ttf"),
)

WIDTH = 900
HEIGHT = 480
MARGIN_X = 22
LINE_GAP = 5
FRAME_MS = 420
BG = (13, 17, 23)
DIM = (110, 118, 129)
GREEN = (63, 185, 80)
WHITE = (230, 237, 243)
YELLOW = (210, 153, 34)
BLUE = (88, 166, 255)
RED = (248, 81, 73)
MUTED = (139, 148, 158)
CYAN = (62, 224, 179)

# Progressive reveal. Keep it short enough for 900x480.
TRANSCRIPT: list[str] = [
    "$ python3 main.py --all",
    "Skill Demand Radar",
    "==================",
    "Jobs: 143 tech / 349 fetched  |  Sources: arbeitnow, remoteok  |  Date: 2026-09-23",
    "",
    "Top 10 skills",
    "   1. python                 28  (new)",
    "   2. kubernetes             25  (new)",
    "   3. llm                    23  (new)",
    "   4. ci/cd                  20  (new)",
    "   5. aws                    19  (new)",
    "   6. docker                 16  (new)",
    "   7. openai                 15  (new)",
    "   8. sql                    15  (new)",
    "   9. agile                  14  (new)",
    "  10. typescript             14  (new)",
    "",
    "Top 5 roles",
    "   1. devops                 28",
    "   2. ml/ai                  28",
    "   3. mobile                 20",
    "   4. backend                17",
    "   5. frontend               10",
    "",
    "Wrote docs/index.html",
    "Wrote docs/report.md",
    "Wrote data/history/2026-09-23.json",
    "Wrote assets/dashboard.png",
]


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in FONT_CANDIDATES:
        if path.is_file():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _line_color(line: str) -> tuple[int, int, int]:
    stripped = line.strip()
    if line.startswith("$"):
        return GREEN
    if stripped.startswith("=="):
        return DIM
    if stripped.startswith("Skill Demand"):
        return CYAN
    if stripped.startswith("Jobs:"):
        return WHITE
    if stripped.startswith("Top "):
        return YELLOW
    if stripped.startswith("Wrote "):
        return BLUE
    if stripped[:1].isdigit() or (len(stripped) > 2 and stripped[0].isspace()):
        return WHITE
    if not stripped:
        return BG
    return MUTED


def _draw_chrome(draw: ImageDraw.ImageDraw, font_small: ImageFont.ImageFont) -> None:
    draw.rectangle((0, 0, WIDTH, 28), fill=(22, 27, 34))
    for cx, color in ((16, RED), (34, YELLOW), (52, GREEN)):
        draw.ellipse((cx, 8, cx + 12, 20), fill=color)
    draw.text((72, 6), "skill-demand-radar — keyless market scan", font=font_small, fill=DIM)


def render_frame(
    visible: list[str],
    font: ImageFont.ImageFont,
    font_small: ImageFont.ImageFont,
    line_h: int,
) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    _draw_chrome(draw, font_small)
    y = 38
    # Keep the latest lines if the transcript overflows the window.
    max_lines = max(1, (HEIGHT - 50) // (line_h + LINE_GAP))
    window = visible[-max_lines:]
    for line in window:
        if y + line_h > HEIGHT - 12:
            break
        draw.text((MARGIN_X, y), line, font=font, fill=_line_color(line))
        y += line_h + LINE_GAP
    if window:
        last = window[-1]
        cursor_y = 38 + (len(window) - 1) * (line_h + LINE_GAP)
        bbox = draw.textbbox((MARGIN_X, cursor_y), last, font=font)
        draw.rectangle(
            (bbox[2] + 3, cursor_y + 2, bbox[2] + 11, cursor_y + line_h - 2),
            fill=GREEN,
        )
    return image


def build_frames() -> list[Image.Image]:
    font = _load_font(14)
    font_small = _load_font(12)
    probe = Image.new("RGB", (10, 10))
    probe_draw = ImageDraw.Draw(probe)
    line_h = probe_draw.textbbox((0, 0), "Ag", font=font)[3]

    frames: list[Image.Image] = []
    frames.append(render_frame([], font, font_small, line_h))

    visible: list[str] = []
    for line in TRANSCRIPT:
        if line.startswith("$"):
            visible.append("$ python3")
            frames.append(render_frame(visible, font, font_small, line_h))
            visible[-1] = "$ python3 main.py --all"
            frames.append(render_frame(visible, font, font_small, line_h))
            continue
        visible.append(line)
        frames.append(render_frame(visible, font, font_small, line_h))

    frames.append(frames[-1].copy())
    frames.append(frames[-1].copy())
    return frames


def main() -> int:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    frames = build_frames()
    frames[0].save(
        OUTPUT,
        save_all=True,
        append_images=frames[1:],
        duration=FRAME_MS,
        loop=0,
        optimize=True,
    )
    size = OUTPUT.stat().st_size
    print(f"wrote {OUTPUT} ({size} bytes, {len(frames)} frames)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
