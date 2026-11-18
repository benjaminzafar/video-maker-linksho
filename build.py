"""Build a Persian news podcast as a GitHub Actions artifact, without paid video/TTS APIs."""
import asyncio
import calendar
import datetime as dt
import html
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import textwrap
import time

import edge_tts
import feedparser
import requests
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output"
OUTPUT.mkdir(exist_ok=True)
MIN_SECONDS = 8 * 60
MAX_SECONDS = 12 * 60
PERSIAN = re.compile(r"[\u0600-\u06FF]")
TOPICS = {
    "اقتصاد و بازارهای مالی": ("اقتصاد", "بانک", "تورم", "بورس", "بیت‌کوین", "ارز", "دلار", "بازار", "مالی", "تجارت", "کریپتو"),
    "انرژی و قیمت‌ها": ("انرژی", "نفت", "گاز", "بنزین", "سوخت", "برق", "قیمت"),
    "اروپا و مهاجرت": ("اروپا", "اتحادیه اروپا", "مهاجرت", "پناهجو", "پناهنده", "آلمان", "سوئد", "فرانسه", "بریتانیا", "اتریش"),
}

def plain(value):
    value = re.sub(r"<[^>]+>", " ", str(value or ""))
    return re.sub(r"\s+", " ", html.unescape(value)).strip()

def load_event():
    path = os.getenv("GITHUB_EVENT_PATH")
    if not path or not Path(path).is_file():
        return {}
    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    if os.getenv("GITHUB_EVENT_NAME") == "repository_dispatch":
        return obj.get("client_payload") or {}
    return (obj.get("inputs") or {}) if os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch" else {}

def rss_news():
    urls = [line.strip() for line in (ROOT / "feeds.txt").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")]
    if not urls:
        raise RuntimeError("feeds.txt is empty")
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=8)
    seen, articles, errors = set(), [], []
    for url in urls:
        try:
            response = requests.get(url, timeout=25, headers={"User-Agent": "LinkshoPodcast/1.0 (RSS reader)"})
            response.raise_for_status()
            feed = feedparser.parse(response.content)
            source = plain(feed.feed.get("title") or url)[:100]
            for item in feed.entries:
                title = plain(item.get("title"))[:220]
                summary = plain(item.get("summary") or item.get("description"))[:320]
                link = str(item.get("link") or "").strip()
                stamp = item.get("published_parsed") or item.get("updated_parsed")
                if not stamp or not title or not link or not PERSIAN.search(title):
                    continue
                when = dt.datetime.fromtimestamp(calendar.timegm(stamp), tz=dt.timezone.utc)
                if when < cutoff or when > dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1):
                    continue
                key = re.sub(r"[^\w]+", "", title).casefold()[:100]
                if key in seen:
                    continue
                seen.add(key)
                articles.append({"title": title, "summary": summary, "source": source,
                                 "link": link, "published": when.isoformat()})
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__} {exc}")
    if errors:
        print("RSS warnings:", *errors, sep="\n  ", file=sys.stderr)
    def priority(item):
        text = item["title"] + " " + item["summary"]
        score = sum(3 for terms in TOPICS.values() for term in terms if term in text)
        return (score, item["published"])
    articles.sort(key=priority, reverse=True)
    return articles[:100]

def topic_for(article):
    text = article["title"] + " " + article["summary"]
    scores = {name: sum(term in text for term in terms) for name, terms in TOPICS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] else "دیگر خبرهای مهم"

def compose_script(items):
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    parts = [
        "سلام، به مرور هفتگی خبرهای لینک‌شو خوش آمدید. "
        "در این برنامه، مهم‌ترین تیترهای منتشرشده در روزهای اخیر را بر اساس منابع خبری مرور می‌کنیم. "
        "هر خبر همراه با نام منبع و لینک مطلب اصلی در توضیحات قرار می‌گیرد. "
        "این برنامه بازخوانی گزیده‌های فید خبری است و جایگزین مطالعه گزارش کامل نیست."
    ]
    groups = {}
    for item in items:
        groups.setdefault(topic_for(item), []).append(item)
    for group, stories in groups.items():
        parts.append(f"در بخش {group}، به خبرهای این هفته می‌پردازیم.")
        for i, item in enumerate(stories, 1):
            summary = item["summary"]
            if len(summary) < 30 or summary.casefold() == item["title"].casefold():
                detail = "فید منتشرشده اطلاعات بیشتری درباره جزئیات این خبر ارائه نمی‌کند."
            else:
                # Only a brief attributed source excerpt is used, never the full article.
                detail = "در خلاصه منتشرشده از این خبر آمده است: " + summary[:240]
            parts.append(
                f"خبر بعدی از {item['source']}. {item['title']}. {detail}. "
                "برای دانستن زمینه و جزئیات، گزارش اصلی را در لینک منبع مطالعه کنید."
            )
    parts.append(
        "این بود مرور هفتگی خبرها. منابع این قسمت، تاریخ انتشار و نشانی هر مطلب "
        "در فایل همراه پادکست موجود است. از همراهی شما سپاسگزاریم. تا هفته آینده، بدرود."
    )
    return "\n\n".join(parts)

def duration(path):
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        check=True, capture_output=True, text=True
    )
    return float(proc.stdout.strip())

async def speak(text, voice, rate):
    await edge_tts.Communicate(text, voice=voice, rate=rate).save(str(OUTPUT / "voice.mp3"))

def cover():
    w, h = 1280, 720
    im = Image.new("RGB", (w, h), (12, 20, 37))
    draw = ImageDraw.Draw(im)
    draw.rounded_rectangle((75, 80, 1205, 636), radius=24, fill=(19, 31, 54),
                           outline=(55, 79, 115), width=2)
    draw.rectangle((75, 80, 88, 636), fill=(42, 187, 179))
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    head = ImageFont.truetype(font_path, 64)
    sub = ImageFont.truetype(font_path, 34)
    small = ImageFont.truetype(font_path, 23)
    draw.text((145, 210), "LINKSHO", font=head, fill=(245, 250, 254))
    draw.text((149, 330), "WEEKLY NEWS PODCAST", font=sub, fill=(66, 216, 199))
    draw.text((149, 423), "Economy  /  Europe  /  Markets", font=small, fill=(194, 206, 224))
    draw.text((149, 524), dt.date.today().isoformat(), font=small, fill=(143, 160, 186))
    im.save(OUTPUT / "cover.png")

def render():
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-loop", "1", "-framerate", "1",
         "-i", str(OUTPUT / "cover.png"), "-i", str(OUTPUT / "voice.mp3"),
         "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage",
         "-c:a", "aac", "-b:a", "128k", "-pix_fmt", "yuv420p",
         "-shortest", "-movflags", "+faststart", str(OUTPUT / "podcast.mp4")],
        check=True
    )

async def main():
    event = load_event()
    voice = os.getenv("TTS_VOICE", "fa-IR-DilaraNeural")
    rate = os.getenv("TTS_RATE", "-5%")
    raw_script = event.get("script") if isinstance(event, dict) else None
    sources = event.get("sources", []) if isinstance(event, dict) else []
    if raw_script:
        if not isinstance(raw_script, str) or len(raw_script) > 55000:
            raise RuntimeError("Invalid script payload")
        script = plain(raw_script)
        if len(PERSIAN.findall(script)) < 300:
            raise RuntimeError("Payload script must be a substantial Persian narration")
        await speak(script, voice, rate)
        seconds = duration(OUTPUT / "voice.mp3")
        mode = "make-dispatch"
    else:
        news = rss_news()
        if len(news) < 15:
            raise RuntimeError(f"Only {len(news)} recent Persian RSS articles; need at least 15. Add more valid Persian RSS feeds.")
        seconds = 0
        script = ""
        count = min(len(news), 30)
        for attempt in range(5):
            selected = news[:count]
            script = compose_script(selected)
            await speak(script, voice, rate)
            seconds = duration(OUTPUT / "voice.mp3")
            print(f"Attempt {attempt + 1}: {count} news articles, {seconds:.1f} sec")
            if MIN_SECONDS <= seconds <= MAX_SECONDS:
                break
            if seconds < MIN_SECONDS and count < len(news):
                count = min(len(news), count + 12)
            elif seconds > MAX_SECONDS and count > 16:
                count = max(16, count - 7)
            else:
                break
        sources = news[:count]
        mode = "persian-rss"
    (OUTPUT / "script.txt").write_text(script, encoding="utf-8")
    (OUTPUT / "sources.json").write_text(json.dumps(sources, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUTPUT / "metadata.json").write_text(
        json.dumps({"generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "mode": mode, "voice": voice, "duration_seconds": seconds,
                    "source_count": len(sources)}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    if not MIN_SECONDS <= seconds <= MAX_SECONDS:
        raise RuntimeError(f"Audio duration is {seconds:.1f} seconds, outside 8–12 minutes. "
                           "Add more Persian RSS sources or provide a better-length script via Make.")
    cover()
    render()
    print(f"SUCCESS: {OUTPUT / 'podcast.mp4'} ({seconds:.1f} seconds; {mode})")

if __name__ == "__main__":
    asyncio.run(main())
