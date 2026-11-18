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
import imageio_ffmpeg
from mutagen.mp3 import MP3
from editorial import prepare
from voice import synthesize
from visuals import create as make_slides
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
    return float(MP3(str(path)).info.length)

async def speak(text, voice, rate):
    await edge_tts.Communicate(text, voice=voice, rate=rate).save(str(OUTPUT / "voice.mp3"))

def render(sources, seconds, title):
    slides = make_slides(OUTPUT / "slides", sources, title)
    if len(slides) < 2:
        raise RuntimeError("No slides generated")
    each = seconds / len(slides)
    list_path = OUTPUT / "slideshow.ffconcat"
    entries = ["ffconcat version 1.0"]
    for path in slides:
        entries.append(f"file 'slides/{path.name}'")
        entries.append(f"duration {each:.4f}")
    entries.append(f"file 'slides/{slides[-1].name}'")
    list_path.write_text("\n".join(entries) + "\n", encoding="utf-8")
    subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
         "-safe", "0", "-f", "concat", "-i", str(list_path),
         "-i", str(OUTPUT / "voice.mp3"), "-r", "25",
         "-c:v", "libx264", "-preset", "veryfast",
         "-c:a", "aac", "-b:a", "128k", "-pix_fmt", "yuv420p",
         "-shortest", "-movflags", "+faststart", str(OUTPUT / "podcast.mp4")],
        check=True
    )

async def main():
    event = load_event()
    raw_script = event.get("script") if isinstance(event, dict) else None
    sources = event.get("sources", []) if isinstance(event, dict) else []
    title = "مرور هفتگی خبرهای جهان"
    editorial = {"editor": "RSS summary"}
    if raw_script:
        if not isinstance(raw_script, str) or len(raw_script) > 55000:
            raise RuntimeError("Invalid script payload")
        script = plain(raw_script)
        if len(PERSIAN.findall(script)) < 300:
            raise RuntimeError("Payload script must be a substantial Persian narration")
        mode = "make-dispatch"
        sources = sources if isinstance(sources, list) else []
    else:
        news = rss_news()
        if len(news) < 15:
            raise RuntimeError(f"Only {len(news)} recent Persian RSS articles; need at least 15.")
        mode = "persian-rss"
        if os.getenv("GEMINI_API_KEY", "").strip():
            try:
                script, sources, editorial = prepare(news)
                mode = "gemini-editorial"
            except Exception as exc:
                # Keep production alive during Gemini free-tier capacity spikes,
                # with an explicit audit trail and fully source-attributed RSS narration.
                print(f"Gemini editorial unavailable: {type(exc).__name__}: {exc}")
                mode = "persian-rss-fallback"
                editorial = {"editor": "RSS fallback", "gemini_unavailable": type(exc).__name__}
                script = compose_script(news[:30])
                sources = news[:30]
        else:
            script = compose_script(news[:30])
            sources = news[:30]
    provider, seconds = await synthesize(script, OUTPUT / "voice.mp3")
    # The fallback RSS editor has predictable story-length granularity. Adjust
    # number of stories and resynthesize instead of silently accepting 14-minute episodes.
    if mode in ("persian-rss", "persian-rss-fallback") and not MIN_SECONDS <= seconds <= MAX_SECONDS:
        count = len(sources)
        for attempt in range(4):
            ratio = 600 / max(seconds, 1)
            next_count = min(len(news), max(8, int(count * ratio)))
            if next_count == count:
                next_count = count - 2 if seconds > MAX_SECONDS else count + 2
            next_count = min(len(news), max(8, next_count))
            if next_count == count:
                break
            count = next_count
            sources = news[:count]
            script = compose_script(sources)
            provider, seconds = await synthesize(script, OUTPUT / "voice.mp3")
            print(f"Adjusted RSS story count to {count}: {seconds:.1f}s")
            if MIN_SECONDS <= seconds <= MAX_SECONDS:
                break
    (OUTPUT / "script.txt").write_text(script, encoding="utf-8")
    (OUTPUT / "sources.json").write_text(json.dumps(sources, ensure_ascii=False, indent=2), encoding="utf-8")
    metadata = {
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "mode": mode, "provider": provider, "duration_seconds": seconds,
        "source_count": len(sources), "editorial": editorial,
        "title": editorial.get("title", title),
        "publication": "REVIEW_REQUIRED",
    }
    (OUTPUT / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    if not MIN_SECONDS <= seconds <= MAX_SECONDS:
        raise RuntimeError(f"Audio duration {seconds:.1f}s is outside 8–12 minutes. "
                           "Adjust editorial length or use the manual script dispatch.")
    render(sources, seconds, metadata["title"])
    print(f"SUCCESS: {OUTPUT / 'podcast.mp4'} ({seconds:.1f} seconds, {mode}, voice={provider})")

if __name__ == "__main__":
    asyncio.run(main())
