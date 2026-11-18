# video-maker-linksho

Free, auditable **Persian weekly-news podcast** builder: RSS headlines and summaries → Persian narration → Edge TTS → FFmpeg MP4 → private GitHub Actions artifact.

## What it does

- Pulls recent **Persian-language** RSS entries (currently BBC Persian) and attributes each headline to the originating publisher.
- Makes a short original transition-led digest from the titles and RSS summaries, with a source list. It **does not** pretend that unverified headlines are comprehensive reporting.
- Synthesizes Persian speech with Edge TTS, produces 1280x720 MP4 with FFmpeg, and saves script, MP3, sources and metadata.
- Checks actual spoken duration with ffprobe. **An episode that is not 8–12 minutes fails rather than publishing a misleading or too-short video.**
- Runs Mondays at 07:00 UTC, plus manually. GitHub schedules use UTC, not Europe/Stockholm daylight saving time.
- Accepts an optional Make-generated, fully Persian narration via the GitHub \`repository_dispatch\` event type \`make-podcast\`.
- **Does not upload publicly to YouTube.** Add OAuth separately after reviewing a few generated episodes.

## How to run

1. Open the repository **Actions** tab and select **Build Persian news podcast**.
2. Click **Run workflow**.
3. After a successful run, download **linksho-weekly-podcast** from the workflow's Artifacts section. The ZIP contains \`podcast.mp4\`, \`voice.mp3\`, \`script.txt\`, \`sources.json\`, and \`metadata.json\`.
4. If an episode fails for insufficient news, extend \`feeds.txt\` with verified, accessible **Persian-language** RSS feeds. The workflow does not invent or translate missing stories.

To test locally on Ubuntu:

\`\`\`bash
sudo apt-get install ffmpeg fonts-dejavu-core
python -m pip install -r requirements.txt
python build.py
\`\`\`

## Make scenario 8648047 connection

This repository is ready to receive a Persian script from Make, but **scenario 8648047 has not yet been reconfigured**. To connect Make, create a GitHub credential **in Make**, then have Make use GitHub's REST API:

\`\`\`http
POST /repos/benjaminzafar/video-maker-linksho/dispatches
Content-Type: application/json

{
  "event_type": "make-podcast",
  "client_payload": {
    "script": "متن گویندگی فارسی کامل از خروجی Make",
    "sources": [{"title": "عنوان", "link": "https://example.org/story"}]
  }
}
\`\`\`

The value of \`script\` must be **just narration**, not a whole JSON/meta-report. Target approximately 8–12 minutes of speech; the builder measures and rejects out-of-range narration.

Never put GitHub personal access tokens in a repository or in a publicly readable workflow. GitHub accepts this API only with appropriate authorization.

## Cost and constraints

- Standard GitHub-hosted Actions runners on **public repositories** are free, subject to GitHub's current usage policy and any ancillary storage limits.
- FFmpeg is free open-source software. Edge TTS is an unofficial third-party interface and may change, become unavailable, or impose limits.
- The source text and your generated files might be subject to publisher attribution/licensing rules. Do not reuse full third-party stories without permission.
- This is a **working baseline**, not a fully edited professional newsroom show. It doesn't independently fact-check linked articles, translate English feeds, guarantee all topic categories, add varied footage, or automatically publish to YouTube.
- The repo is public: **never send confidential Make AI outputs or sensitive information** in dispatched payloads or workflow logs.
