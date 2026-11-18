"""Speech synthesis: ElevenLabs (opt-in) with a zero-subscription Edge TTS fallback."""
import asyncio
import os
from pathlib import Path
import subprocess
import time
import requests
import edge_tts

def length(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                       capture_output=True, text=True, check=True)
    return float(r.stdout.strip())

def chunks(script, max_chars=2900):
    paragraphs = script.replace("\r", "").split("\n")
    out, buf = [], ""
    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        pieces = [paragraph[i:i + max_chars] for i in range(0, len(paragraph), max_chars)]
        for piece in pieces:
            if buf and len(buf) + len(piece) + 2 > max_chars:
                out.append(buf)
                buf = ""
            buf = (buf + "\n" + piece).strip()
    if buf:
        out.append(buf)
    return out

def _eleven(script, output):
    key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    if not key:
        raise RuntimeError("ELEVENLABS_API_KEY was not configured")
    model = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")
    voice_id = os.getenv("ELEVENLABS_VOICE_ID", "").strip() or "TX3LPaxmHKxFdv7VOQHJ"
    segments = chunks(script)
    if not segments or len(segments) > 30:
        raise RuntimeError("Unreasonable script length for ElevenLabs")
    working = output.parent / "tts_parts"
    working.mkdir(exist_ok=True)
    paths = []
    for i, segment in enumerate(segments):
        resp = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            params={"output_format": "mp3_44100_128"},
            headers={"xi-api-key": key, "Content-Type": "application/json",
                     "Accept": "audio/mpeg"},
            json={"text": segment, "model_id": model,
                  "voice_settings": {"stability": 0.55, "similarity_boost": 0.75,
                                     "style": 0.0, "use_speaker_boost": True}},
            timeout=125
        )
        if resp.status_code != 200:
            # Never output API tokens, request headers or unfiltered service error bodies.
            raise RuntimeError(f"ElevenLabs returned HTTP {resp.status_code} for chunk {i + 1}/{len(segments)}")
        if len(resp.content) < 1024:
            raise RuntimeError("ElevenLabs returned an unexpectedly small audio file")
        part = working / f"part_{i:03}.mp3"
        part.write_bytes(resp.content)
        paths.append(part)
        time.sleep(0.4)
    lst = working / "list.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in paths), encoding="utf-8")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-c", "copy", str(output)], check=True, cwd=working)

async def _edge(script, output):
    voice = os.getenv("TTS_VOICE", "fa-IR-DilaraNeural")
    await edge_tts.Communicate(text=script, voice=voice,
                                rate=os.getenv("TTS_RATE", "-5%")).save(str(output))

async def synthesize(script, output):
    output = Path(output)
    mode = os.getenv("VOICE_PROVIDER", "edge").strip().lower()
    if mode == "elevenlabs":
        try:
            await asyncio.to_thread(_eleven, script, output)
            return "elevenlabs", length(output)
        except Exception as exc:
            # No silent changes: tell the operator and use fallback, which consumes
            # no further ElevenLabs quota. Some chunks may already have cost credits.
            print(f"ElevenLabs unavailable: {type(exc).__name__}: {exc}; falling back to Edge TTS")
    elif mode != "edge":
        raise RuntimeError("VOICE_PROVIDER must be edge or elevenlabs")
    await _edge(script, output)
    return "edge", length(output)
