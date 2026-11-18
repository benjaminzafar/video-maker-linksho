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
    preferred = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    models = list(dict.fromkeys([preferred, "gemini-3.5-flash-lite"]))
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
                    json=body, timeout=110
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
        "gemini_model": os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
        "title": str(obj.get("title", "مرور هفتگی خبرها"))[:130],
        "script_words": words,
        "uncertainties": obj.get("uncertainties", [])[:12],
        "verified_by_external_search": bool(grounding.get("grounding_metadata")),
        "search_review": grounding.get("search_review", "")[:2000],
    }
    return script, selected, details
