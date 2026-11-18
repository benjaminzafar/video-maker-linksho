"""Consistent Linksho visual brand: deterministic typography and colors, no image API cost."""
from pathlib import Path
import datetime as dt
import re
from PIL import Image, ImageDraw, ImageFont
try:
    import arabic_reshaper
    from bidi.algorithm import get_display
except ImportError:
    arabic_reshaper = None
    get_display = None

WIDTH, HEIGHT = 1280, 720
BG = "#101A2B"
PANEL = "#17283E"
CYAN = "#26C3B8"
WHITE = "#F0F5FA"
MUTED = "#A1B2C6"

def fa(text):
    text = str(text)
    if arabic_reshaper and get_display:
        return get_display(arabic_reshaper.reshape(text))
    return text

def font(size, bold=False):
    choices = [
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf" if bold else "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in choices:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

def wrap_fa(text, draw, max_w, f, max_lines=4):
    result, line = [], ""
    for word in str(text).split():
        proposed = f"{line} {word}".strip()
        if draw.textbbox((0,0), fa(proposed), font=f)[2] > max_w and line:
            result.append(line)
            line = word
        else:
            line = proposed
        if len(result) >= max_lines:
            break
    if line and len(result) < max_lines:
        result.append(line)
    return result

def right_text(draw, x, y, text, f, color):
    shaped = fa(text)
    bounds = draw.textbbox((0,0), shaped, font=f)
    draw.text((x - bounds[2], y), shaped, font=f, fill=color)

def create(slides_dir, articles, episode_title="مرور هفتگی خبرهای جهان"):
    slides_dir = Path(slides_dir)
    slides_dir.mkdir(exist_ok=True)
    slide_infos = [("LINKSHO", episode_title, "NEWSROOM", "Weekly briefing")]
    for item in articles[:10]:
        title = item.get("title", "")
        source = item.get("source") or item.get("publisher") or "News"
        slide_infos.append(("LINKSHO", title, "SOURCE", source))
    slide_infos.append(("LINKSHO", "منابع خبری در فایل همراه این قسمت", "THANK YOU", "linksho"))
    results = []
    for idx, (logo, heading, kicker, footer) in enumerate(slide_infos):
        im = Image.new("RGB", (WIDTH, HEIGHT), BG)
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((64, 75, 1216, 646), radius=18, fill=PANEL, outline="#38516D", width=2)
        d.rectangle((64, 75, 76, 646), fill=CYAN)
        d.text((132, 120), logo, font=font(54, True), fill=WHITE)
        d.rectangle((132, 200, 266, 206), fill=CYAN)
        d.text((132, 238), kicker, font=font(26, True), fill=CYAN)
        lines = wrap_fa(heading, d, 985, font(45, True), max_lines=4)
        for line_no, line in enumerate(lines):
            right_text(d, 1140, 305 + line_no*75, line, font(45, True), WHITE)
        d.text((132, 584), str(footer)[:50], font=font(20), fill=MUTED)
        d.text((1080, 586), f"{idx + 1:02}", font=font(22, True), fill=CYAN)
        result = slides_dir / f"slide_{idx:03}.png"
        im.save(result)
        results.append(result)
    return results
