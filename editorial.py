"""Optional Gemini newsroom editing with strict RSS provenance and transparent limits."""
import datetime as dt
import json
import os
import re
import requests

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

def _call(prompt, *, grounded=False, json_mode=False):
    """Bounded retries and a free-tier Flash-Lite fallback; never expose the key."""
    import time
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    preferred = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    models = list(dict.fromkeys([preferred, "gemini-3.8-flash"]))
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.25, "maxOutputTokens": 8192},
    }
    if grounded:
        body["tools"] = [{"google_search": {}}]
    if json_mode:
        body["generationConfig"]["responseMimeType"] = "application/json"
    failures = []
    for model in models:
        for attempt in range(2):
            try:
                response = requests.post(
                    GEMINI_URL.format(model=model),
                    headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                    json=body, timeout=45
                )
                if response.status_code == 200:
                    data = response.json()
                    candidate = (data.get("candidates") or [{}])[0]
                    parts = candidate.get("content", {}).get("parts", [])
                    output = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
                    if not output.strip():
                        raise RuntimeError(f"Gemini returned no text ({candidate.get('finishReason')})")
                    print(f"Gemini editorial model used: {model}")
                    return output, candidate.get("groundingMetadata") or {}
                failures.append(f"{model}: HTTP {response.status_code}")
                # Switch model quickly for permanent model, permission, or quota errors.
                if response.status_code in (400, 401, 403, 404, 429):
                    break
                if response.status_code in (500, 502, 503, 504):
                    time.sleep(2 + attempt * 4)
                    continue
                break
            except requests.RequestException as exc:
                failures.append(f"{model}: network {type(exc).__name__}")
                time.sleep(2 + attempt * 4)
    raise RuntimeError("Gemini models unavailable: " + "; ".join(failures))

def prepare(items):
    """Return script, selected RSS items, editorial metadata; no sources fabricated."""
    payload = []
    for idx, item in enumerate(items[:32], 1):
        payload.append({
            "id": idx, "title": item["title"][:220],
            "summary": item.get("summary", "")[:500],
            "publisher": item["source"][:90],
            "published": item["published"], "url": item["link"],
        })
    if len(payload) < 8:
        raise RuntimeError("Not enough dated RSS news for reliable editorial report")
    grounding = {}
    if os.getenv("GEMINI_SEARCH_GROUNDING", "false").lower() == "true":
        search_text = (
            "برای بررسی تناقض‌ها در ۶ تیتر زیر جستجوی وب انجام بده. "
            "موارد تأییدنشده را مشخص کن و منابع را بنویس. "
            "اگر تأیید مستقل پیدا نکردی بگو تأیید نشد.\n" +
            json.dumps(payload[:6], ensure_ascii=False)
        )
        try:
            check_text, metadata = _call(search_text, grounded=True)
            grounding = {"search_review": check_text[:5000], "grounding_metadata": metadata}
        except Exception as exc:
            grounding = {"search_review": "Unavailable", "grounding_error": str(exc)[:250]}

    prompt = f"""
تو سردبیر حرفه‌ای پادکست فارسی Linksho هستی. امروز {dt.date.today().isoformat()} است.
تنها از اطلاعات خبری دارای ID و منابع واقعی داخل JSON استفاده کن.
یک اپیزود خبری با لحن بی‌طرف و دقیق تولید کن، حدود ۱۲۰۰ تا ۱۵۰۰ واژه،
هدف ۸ تا ۱۲ دقیقه گویندگی طبیعی. ساختار: شروع گیرا، اقتصاد اروپا، انرژی،
بازارهای مالی و مهاجرت (فقط اگر خبر مرتبط وجود دارد)، گذارهای طبیعی و جمع‌بندی.
روی خبرهای مهم تمرکز کن، نه خبرهای کم‌اهمیت و ورزش و سلبریتی.
هر عدد و تاریخ مهم را فقط اگر در عنوان یا خلاصه منبع آمده به کار ببر.
هیچ واقعیت، نقل‌قول، عدد، پیش‌بینی یا منبع جدید اختراع نکن.
نکات نامطمئن را مشروط بیان کن. مطالب را با نثر تازه بازنویسی کن،
نه کپی طولانی از منبع. از تکرار خبر برای طولانی‌کردن گزارش پرهیز کن.
اگر خبر کافی نیست، صادقانه متن کوتاه‌تر بده.

فقط یک شیء JSON با کلیدهای زیر بازگردان:
"title": عنوان کوتاه و جذاب فارسی.
"script": متن گویندگی فارسی؛ بدون Markdown، نشانی URL یا فهرست منابع.
"story_ids": آرایه عددی IDهای منابع واقعاً استفاده‌شده، بدون ID جدید.
"uncertainties": آرایه کوتاه نکاتی که قابل راستی‌آزمایی نبوده‌اند.

خبرهای منبع (تنها شواهد مجاز):
{json.dumps(payload, ensure_ascii=False)}
نتیجه بررسی وب (اگر موجود؛ ممکن است ناقص باشد):
{json.dumps(grounding, ensure_ascii=False)[:5000]}
"""
    raw, _ = _call(prompt, json_mode=True)
    raw = raw.strip()
    if raw.startswith("~~~json"):
        raw = raw[7:].rstrip("~\n ")
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Gemini did not return valid editorial JSON") from exc
    script = str(obj.get("script", "")).strip()
    words = len(script.split())
    if words < 700 or words > 2200:
        raise RuntimeError(f"Gemini script has {words} words; rejecting implausible duration")
    if len(re.findall(r"[\u0600-\u06ff]", script)) < 1200:
        raise RuntimeError("Gemini script does not contain enough Persian narration")
    permitted = {x["id"]: x for x in payload}
    ids = obj.get("story_ids", [])
    if not isinstance(ids, list) or not ids:
        raise RuntimeError("Gemini did not cite any article IDs")
    valid = sorted(set(i for i in ids if type(i) is int and i in permitted))
    if len(valid) < 4:
        raise RuntimeError("Gemini cited fewer than four real RSS articles")
    selected = [items[i - 1] for i in valid]
    details = {
        "editor": "gemini",
        "gemini_model": os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"),
        "title": str(obj.get("title", "مرور هفتگی خبرها"))[:130],
        "script_words": words,
        "uncertainties": obj.get("uncertainties", [])[:12],
        "verified_by_external_search": bool(grounding.get("grounding_metadata")),
        "search_review": grounding.get("search_review", "")[:2000],
    }
    return script, selected, details


def prepare_long(items):
    """Four source-disjoint Gemini passes produce an 8–12 minute newsroom draft."""
    if len(items) < 20:
        raise RuntimeError("Need at least 20 dated RSS items for a balanced long Gemini episode")
    topics = [
        ("بازارها و اقتصاد", ("اقتصاد","بانک","بازار","مالی","بورس","ارز","بیت‌کوین","تورم","تجارت")),
        ("اروپا و مهاجرت", ("اروپا","اتحادیه","مهاجرت","پناهجو","سوئد","آلمان","فرانسه","بریتانیا")),
        ("انرژی و محیط زیست", ("انرژی","نفت","گاز","سوخت","برق","اقلیم","قیمت")),
    ]
    chosen = []
    used = set()
    for _, keys in topics:
        relevant = [i for i, item in enumerate(items) if i not in used
                    and any(k in item["title"] + " " + item.get("summary","") for k in keys)]
        for i in relevant[:7]:
            used.add(i)
            chosen.append(items[i])
    for i, item in enumerate(items):
        if len(chosen) >= 28:
            break
        if i not in used:
            chosen.append(item)
    chosen = chosen[:28]
    batches = [chosen[i:i+7] for i in range(0, len(chosen), 7)]
    if len(batches) < 3:
        raise RuntimeError("Insufficient article groups for long-form narration")
    scripts = []
    story_ids = []
    for section_index, batch in enumerate(batches, 1):
        base = (section_index - 1) * 7
        references = [
            {"id": base + offset + 1, "title": a["title"][:180],
             "summary": a.get("summary","")[:360],
             "publisher": a.get("source",""), "published": a.get("published",""),
             "url": a.get("link","")}
            for offset, a in enumerate(batch)
        ]
        prompt = f"""
تو سردبیر خبری مستقل پادکست Linksho هستی. بخش {section_index} از {len(batches)}.
تنها از منابع خبری فهرست زیر استفاده کن. هفت خبر را با زبانی ساده، روان،
حرفه‌ای و بی‌طرف گزارش کن. حدود ۳۵۰ تا ۴۵۰ کلمه فارسی بنویس،
با گذار طبیعی میان خبرها. هیچ اطلاعات، تحلیل قطعی، عدد، تاریخ یا
نقل‌قول جدیدی که در متن کوتاه منبع وجود ندارد تولید نکن.
متن خبرگزاری‌ها را عیناً کپی نکن. از بازگویی مکرر یک خبر پرهیز کن.
برای هر خبر به نام رسانه‌اش اشاره کن؛ URL را در متن گویندگی نخوان.
اگر شواهد برای طول بخش کافی نیست، متن کوتاه‌تر تولید کن.
تنها خروجی یک JSON معتبر با دو کلید زیر است:
"script": متن فارسی گویندگی
"story_ids": آرایه ID عددیِ خبرهایی که واقعاً استفاده شدند
فقط از شناسه‌های همین بخش استفاده کن.
منابع:
{json.dumps(references, ensure_ascii=False)}
"""
        output, _ = _call(prompt, json_mode=True)
        try:
            obj = json.loads(output.strip())
            part = str(obj.get("script","")).strip()
            ids = obj.get("story_ids", [])
            valid_ids = {ref["id"] for ref in references}
            if len(part.split()) < 130 or len(re.findall(r"[\u0600-\u06FF]",part)) < 400:
                raise ValueError("section too short")
            if not isinstance(ids,list) or not any(type(i) is int and i in valid_ids for i in ids):
                raise ValueError("missing valid source citations")
            story_ids.extend(i for i in ids if type(i) is int and i in valid_ids)
            scripts.append(part)
        except (ValueError, TypeError, KeyError) as exc:
            raise RuntimeError(f"Gemini section {section_index} failed validation") from exc
    total = sum(len(part.split()) for part in scripts)
    if not 700 <= total <= 1900:
        raise RuntimeError(f"Gemini combined output has {total} words, outside usable range")
    intro = "سلام. به مرور هفتگی خبرهای لینک‌شو خوش آمدید. در این قسمت، خبرهای مهم را با اشاره به منابع اصلی مرور می‌کنیم."
    outro = "این گزارش بر اساس تیترها و خلاصه‌های منتشرشده از رسانه‌های خبری تهیه شده است. برای بررسی جزئیات، لینک منابع در فایل همراه ویدیو موجود است. تا هفته آینده، بدرود."
    ordered_ids = sorted(set(story_ids))
    sources = [chosen[i - 1] for i in ordered_ids]
    script = "\n\n".join([intro] + scripts + [outro])
    return script, sources, {
        "editor": "gemini-multipass",
        "gemini_model": os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"),
        "title": "مرور هفتگی اقتصاد، اروپا و جهان",
        "script_words": len(script.split()),
        "stories_cited": len(sources),
        "independently_verified": False,
        "sections": len(scripts)
    }
