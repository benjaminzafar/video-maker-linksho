# video-maker-linksho

An automated Persian-language weekly-news podcast builder, with a **consistent Linksho visual identity**.

## Pipeline

1. Read recent Persian news headlines, short RSS summaries and their original URLs.
2. If `GEMINI_API_KEY` is available, use Gemini 2.5 Flash to prioritize stories and compose a sourced, neutral Persian narration, citing actual RSS IDs. Without the key, a basic source-attributed RSS summary is used.
3. If `ELEVENLABS_API_KEY` is available, use ElevenLabs multilingual voice. If unavailable, fail/quota-limited or not configured, use Persian Edge TTS.
4. Create consistent **1280x720** slides with the exact dark-navy, turquoise and white palette. All titles use the same logo/spacing/type hierarchy. The slides are generated locally, so there is **no paid image-generation dependency**.
5. Render with FFmpeg, validate audio duration (**8–12 minutes**), and store artifacts for review. Episodes are **NOT auto-published to YouTube**.

### Color and layout rules

- Navy: `#101A2B` background
- Deep blue: `#17283E` card/panel
- Turquoise: `#26C3B8` highlights and accent bar
- Off-white: `#F0F5FA` headlines
- Consistent typography, logo and margins throughout each video.

## One-time setup (GitHub Actions)

Open **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Purpose |
| --- | --- |
| `GEMINI_API_KEY` | Optional. AI journalism and Persian report writing. Obtain from [Google AI Studio](https://aistudio.google.com/apikey). |
| `ELEVENLABS_API_KEY` | Optional. Natural voice from your ElevenLabs account. If omitted, Edge TTS speaks for free. |

Optional: under **Variables → New repository variable**, add `ELEVENLABS_VOICE_ID` for a preferred Persian-capable voice. By default, the repository uses the old existing ElevenLabs Liam voice (English-oriented, so **select a tested Persian voice for good pronunciation**).

Never paste API keys in Issues, commits, chat, or a public repository file.

**No secret is required for the fallback workflow.** Only create secrets for services you choose to use. Gemini free-tier quotas and availability vary by model, region and billing status. ElevenLabs free-tier credits can be insufficient for a full 8–12-minute podcast; part of the credits may be consumed before the fallback is triggered. **ElevenLabs Free does not provide general commercial publishing rights**; review [their pricing/licensing](https://elevenlabs.io/pricing).

### Run it

Open [GitHub Actions](https://github.com/benjaminzafar/video-maker-linksho/actions) → **Build Persian news podcast** → **Run workflow**.

One scheduled weekly run is set for **Monday 07:00 UTC**. The final result appears in the workflow's **Artifacts** section: `podcast.mp4`, `voice.mp3`, `script.txt`, `sources.json`, `metadata.json` and the generated slides.

If the report is too short/long or contains too little current RSS evidence, the run fails rather than inventing filler or publishing a misleading podcast. You can add more **verified Persian RSS URLs** to `feeds.txt`.

### Make scenario 8648047

The existing Make scenario was modified to send its Persian narration to `/repos/benjaminzafar/video-maker-linksho/dispatches`, but this action returned HTTP 404 from Make's GitHub credential; a separate workflow-dispatch test also returned a 403 permissions error. Thus **Make scenario 8648047 remains inactive**, and **GitHub's own schedule runs the production workflow**. Do not enable both schedules until the permission issue is fixed.

The Gemini editor uses only the RSS-provided claims, does not independently fact-check every article and does not claim to do so. Search-grounding is **off by default** (`GEMINI_SEARCH_GROUNDING=false`) because pricing and availability can vary. Review source URLs and publication rights before publishing.

### Visuals

The system currently uses consistent generated editorial templates rather than paid Gemini image generation. If imagery is added later, preserve this template and brand colors as an overlay. Image generation with Gemini may require a paid model. Do not turn it on without reviewing costs.

## Local run

On Ubuntu, install `ffmpeg`, `fonts-noto-core` and `fonts-dejavu-core`, then `pip install -r requirements.txt` and `python build.py`. Environment-variable secrets are optional.

## Security and reliability

- Repository is public; secrets are available only via GitHub Actions secret environment variables.
- Workflow artifacts are available through the Actions UI to users permitted to read Actions artifacts; they are **not** published to YouTube.
- RSS text is untrusted input. The system restricts source IDs and dates but can't guarantee factual accuracy.
- FFmpeg and local slide generation are free; GitHub's public-repo Actions are subject to applicable usage conditions. API free tiers may change.

## Validated run (18 November 2026)

- [Successful end-to-end run](https://github.com/benjaminzafar/video-maker-linksho/actions/runs/44298892557): **513.3 seconds (8 minutes 33 seconds)**, saved as the `linksho-weekly-podcast` Actions artifact.
- Gemini 3.5 Flash-Lite successfully generated the Persian editorial opening; another 10 cited, previously unused RSS briefs completed the length. The episode is identified as `gemini-editorial`.
- ElevenLabs API rejected the configured secret with status `api_key_id_used_as_api_key`: it is an API **key ID**, not the actual secret key. The successful video uses **Edge TTS** as a fallback. To turn on ElevenLabs, replace `ELEVENLABS_API_KEY` in the existing GitHub Environment (named `GEMINI_API_KEY`) with a new genuine API secret from ElevenLabs. Never put it in the repository or chat.
- This repository produces reviewable MP4 files every Monday at 07:00 UTC. **YouTube auto-upload is not enabled** until valid YouTube OAuth authorization is configured; never claim a published video on the basis of an artifact alone.
- No JSON2Video or recurring video-render subscription is needed. API and GitHub quotas still apply.
