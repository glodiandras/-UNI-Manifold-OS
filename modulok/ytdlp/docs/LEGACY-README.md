# Multimedia Source Pipeline

An **AI-ready multimedia source ingestion pipeline**. It turns a video URL into
a self-describing staging folder that a later, vault-aware step can integrate
into an Obsidian knowledge base:

```
URL → yt-dlp → video file
                 ├── metadata.json      curated, stable metadata
                 ├── source.md          the source note (entry point)
                 ├── transcript.md      transcript, or a "pending" placeholder
                 └── integration.json   machine-readable hand-off
```

It is **not** a knowledge base, and it is **not** a general video downloader
with extra steps. It is the staging layer between "a video exists somewhere on
the web" and "a source is ready to be considered for the vault".

---

## Table of contents

1. [Purpose](#1-purpose)
2. [Requirements](#2-requirements)
3. [Installation](#3-installation)
4. [Configuration](#4-configuration)
5. [First run](#5-first-run) · [web UI](#the-web-ui)
6. [Downloading one video](#6-downloading-one-video)
7. [Batch download](#7-batch-download)
8. [Duplicate protection](#8-duplicate-protection)
9. [Transcript workflow](#9-transcript-workflow)
10. [Validation](#10-validation)
11. [Troubleshooting](#11-troubleshooting)
12. [Project structure](#12-project-structure)
13. [Claude Code workflow](#13-claude-code-workflow)
14. [What zanza.tv actually turns out to be](#14-what-zanzatv-actually-turns-out-to-be)
15. [Video quality and the 1080p setup](#15-video-quality-and-the-1080p-setup)
16. [Security and legal boundaries](#16-security-and-legal-boundaries)
17. [Magyar összefoglaló](#17-magyar-összefoglaló)

---

## 1. Purpose

Three layers are kept strictly apart:

```
SOURCE MEDIA          the video file itself
      ↓
SOURCE METADATA       metadata.json + source.md
+ TRANSCRIPT          transcript.md
      ↓
LATER KNOWLEDGE       done elsewhere, by a human decision, in the real vault
INTEGRATION
```

The staging repository never becomes the knowledge base. `source.md` records
*where a media file came from*; it claims nothing about its content. Turning a
source into knowledge is a separate, human-gated step - see
[CLAUDE.md](CLAUDE.md).

The first use case is [zanza.tv](https://zanza.tv), but nothing is
Zanza-specific: provider identity, subject mapping and transcription are all
resolved generically and configured in `config/config.yaml`.

## 2. Requirements

| Requirement | Notes |
|---|---|
| Python 3.11+ | checked at startup by the `scripts/*.py` wrappers |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | Python module (preferred) or the CLI binary |
| PyYAML | installed with the project; a minimal built-in YAML reader keeps things working without it |
| macOS / Apple Silicon | developed and verified there; any POSIX system works |
| FFmpeg | installed with the project (`imageio-ffmpeg` wheel, venv-local); required for 1080p |
| A JS runtime (`node` or `deno`) | required for YouTube-hosted video above 360p - see [section 15](#15-video-quality-and-the-1080p-setup) |

Optional, only for local speech-to-text:

| Optional | Purpose |
|---|---|
| `faster-whisper` | recommended local ASR backend; reads `.mp4` directly |
| whisper.cpp | alternative local ASR; can read the media directly through FFmpeg |

Nothing is installed automatically. If yt-dlp is missing, the pipeline stops
with an explicit message and installation instructions.

## 3. Installation

```bash
cd "<this directory>"
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Then verify:

```bash
python3 scripts/download.py --check
```

It has to report a JS runtime as well - `node` or `deno` on PATH. Without one,
YouTube-hosted sources (zanza.tv among them) are served as a single 360p file
and nothing better is even offered; see
[section 15](#15-video-quality-and-the-1080p-setup). FFmpeg needs no separate
install: the `imageio-ffmpeg` dependency ships a static binary into the
virtualenv.

**Location (2026-09-24).** This project lives in `Manifold-OS/modulok/ytdlp` on
the Work SSD; after a move, `Manifold-OS/bin/mos doctor --javit` repairs the
venv's baked paths. *Historical iCloud note:* it once lived in an iCloud-synced Obsidian folder. A
virtualenv is thousands of small files that iCloud has no reason to sync, and
"Optimise Mac Storage" can evict them and break it. Two safe options:

```bash
# option A - keep it here but hidden from iCloud (macOS ignores *.nosync paths)
python3 -m venv .venv.nosync && source .venv.nosync/bin/activate && pip install -e .

# option B - keep the environment entirely outside iCloud
python3 -m venv ~/.venvs/msp && source ~/.venvs/msp/bin/activate && pip install -e "$PWD"
```

A ready-to-use `.venv.nosync` environment is already present in this project.

Optional extras:

```bash
pip install -e ".[dev]"              # pytest
pip install -e ".[faster-whisper]"   # local transcription backend
```

Installing also provides the console commands `msp-download`, `msp-inspect`,
`msp-validate` and `msp-transcribe`, which behave exactly like the scripts.

### Using a local yt-dlp checkout

If you keep a yt-dlp source tree (for example `~/Downloads/yt-dlp-master`) and
want the pipeline to use *that* instead of the installed package:

```yaml
# config/config.yaml
ytdlp:
  local_source_path: "~/Downloads/yt-dlp-master"
```

## 4. Configuration

Everything lives in [`config/config.yaml`](config/config.yaml); every setting is
commented there. Nothing is hardcoded - paths are resolved against the project
root (the directory containing `config/`).

| Key | Meaning |
|---|---|
| `output_root` | staging root (default `./staging`) |
| `video.max_height`, `video.preferred_extension` | target resolution (default 1080p) |
| `video.allow_merge`, `video.merge_output_format` | mux separate video+audio streams with FFmpeg - this is what makes 1080p reachable |
| `video.format_selector` | explicit yt-dlp selector; merging selectors are rejected only when `allow_merge` is false |
| `ytdlp.js_runtimes`, `ytdlp.ffmpeg_location` | which JS runtime and which ffmpeg binary to use (`auto` = PATH, else the venv-local one) |
| `metadata.save_json`, `metadata.save_raw_info` | curated and/or complete metadata |
| `metadata.default_language` | language recorded when the provider reports none (`null` keeps an honest `language: null`) |
| `ytdlp.extractor_args` | passed through to yt-dlp as `--extractor-args`; the YouTube default is what makes embed-only videos readable |
| `transcript.*` | backend, language, and the fidelity flag |
| `subtitles.*` | whether provider subtitles are downloaded alongside the video |
| `organization.*` | provider/subject folders, default subject, provider display names |
| `subjects.taxonomy`, `subjects.aliases` | canonical subject names and how raw values map onto them |
| `subjects.keywords` | topic words used to infer the subject when nothing else identifies it |
| `archive.*` | duplicate protection |
| `logging.*` | log directory, level, JSONL event stream |
| `playlist.*` | playlist safety switch and item limit |
| `download.*` | retries, timeout, rate limit, resume |
| `ytdlp.*` | local yt-dlp checkout or binary path |

Overrides, in order of precedence: command line (`--config`, `--output-root`),
`$MSP_CONFIG` / `$MSP_PROJECT_ROOT`, then `config/config.yaml`.

> **Before the first real run:** make `subjects.taxonomy` match your vault's own
> subject names *character for character* (accents, capitalisation). That is
> what removes the need for a mapping table at integration time.

## 5. First run

```bash
python3 scripts/download.py --check                 # dependencies + effective config
python3 scripts/inspect.py "https://..."            # what does this URL offer?
python3 scripts/download.py "https://..." --dry-run # plan without downloading
python3 scripts/download.py "https://..."           # the real thing
python3 scripts/validate.py                         # is the staging tree consistent?
```

### The web UI — now the Manifold-pult (2026-09-24)

`scripts/web.py` is archived (`Manifold-OS/archive/felulet-2026-09-24/`). The
same work is done from the Manifold-pult, which runs these scripts in a
subprocess and starts nothing until you press Start:

```bash
../../bin/mos pult                  # http://127.0.0.1:8771 — or double-click Manifold-OS/Manifold-pult.command
```

The description below is kept for the archived page; the pult has the same
parts (links, one-job-at-a-time queue with live output, library by subject).

Paste one URL or twenty (one per line) and press *Letöltés*. Jobs run one at a
time, their output streams into the page, and the library below shows what has
been staged, grouped by subject, with each source's transcript state. Nothing
has to be sorted by hand: the subject folder comes from the pipeline's own
heuristic, and transcription starts on its own when `transcript.enabled` is on.

The server binds to `127.0.0.1` only, holds no state of its own (the staging
tree is the state), and runs the same `scripts/*.py` commands documented here -
so a job's log in the browser is the same output a terminal would show.

## 6. Downloading one video

```bash
python3 scripts/download.py "https://zanza.tv/tortenelem/az-okori-athen"
```

Result:

```
staging/
└── Zanza/
    └── Történelem/
        └── Az ókori Athén/
            ├── video.mp4
            ├── source.md
            ├── transcript.md
            ├── metadata.json
            └── integration.json
```

Useful options:

| Option | Effect |
|---|---|
| `--subject "Fizika"` | force the subject folder instead of the heuristic |
| `--language hu` | record a language the provider does not report |
| `--dry-run` | plan only: target path, format selector, best reachable format |
| `--force` | re-download an already staged source (a finished transcript is still preserved) |
| `--playlist [--max-items N]` | allow a playlist URL |
| `--no-archive` | do not read or write the download archive |
| `-v` / `-q` | more / less terminal output |

The subject folder is decided in this order, so that nothing has to be sorted
by hand afterwards:

1. `--subject` on the command line
2. a `| Subject` hint in a batch file
3. metadata categories/tags, or the URL path - zanza.tv carries the subject in
   its path (`/tortenelem/` → `Történelem`)
4. **topic words** (`subjects.keywords`) found in the title, description and
   tags - this is what classifies a YouTube video, where the URL says nothing
5. `organization.default_subject` when even that finds nothing

Only names that exist in `subjects.taxonomy` are ever used: a heuristic may
recognise a subject, but it may not invent a new folder. `integration.json`
records which step decided (`subject_source`), so an inferred subject stays
distinguishable from one that was read off the source. On a sample of 29 real
history videos, step 4 classified 28 from the title alone.

Matching is accent- and case-insensitive substring matching, which is what
makes Hungarian suffixes work (`kozepkorban` contains `kozepkor`); for the same
reason a keyword must be at least four characters, and the config refuses
shorter ones rather than mis-filing videos.

## 7. Batch download

Any argument that is an existing file is treated as a URL list:

```bash
python3 scripts/download.py urls.txt
```

```text
# urls.txt - one URL per line
https://zanza.tv/tortenelem/az-okori-athen | Történelem
https://zanza.tv/fizika/newton-torvenyei   | Fizika
https://zanza.tv/irodalom/valami            # subject guessed
```

A batch continues after a failure, logs every failed URL, skips what is already
staged and prints a summary:

```
Downloaded: 17
Skipped: 4
Failed: 2
Total: 23
```

Playlists are refused unless `--playlist` is given, and a playlist larger than
`playlist.max_items` (default 50) aborts instead of quietly pulling hundreds of
videos.

### Every video of a listing page (`--crawl`)

```bash
python3 scripts/download.py --crawl "https://zanza.tv/tortenelem"                  # a whole subject
python3 scripts/download.py --crawl "https://zanza.tv/tortenelem/az-okori-hellasz" # one topic
python3 scripts/download.py --crawl "https://zanza.tv/tortenelem" --dry-run        # plan only
```

`--crawl` reads the given page, follows its links down to the video pages
(`crawl.max_depth`, default 2: subject → topic → video) and stages everything it
finds as one batch - same quality, subject folders, archive and transcription
as any other download. A page counts as a video page when it embeds a player
(`crawl.embed_patterns`).

- **It stays inside the start page:** same host, at or below its path.
  `/tortenelem` never wanders into `/irodalom`.
- **It is slow on purpose:** robots.txt is read first, disallowed pages are
  never fetched, and pages are read no faster than `crawl.delay_seconds` or the
  site's `Crawl-delay`, whichever is longer (zanza.tv asks for 10 s). A whole
  subject means a hundred or more page reads before the first download - and
  the transcription afterwards takes far longer still.
- **Re-running is cheap:** a video page already staged is neither read nor
  probed again, so the same command later only picks up new videos.
  `--force` downloads everything again.
- **Limits:** more than `crawl.max_items` videos (default 200, `--max-items`
  per run) or more than `crawl.max_pages` page reads (400) aborts the crawl.
- **No login:** no cookie or credential is sent; a page that redirects
  elsewhere (e.g. to a login form) is skipped.

In the web UI, tick *az oldal összes videója* before pressing *Letöltés*.

### A whole subject, unattended (`scripts/crawl_all.sh`)

A whole subject takes hours. The page reads alone take around half an hour at
zanza.tv's 10 s crawl delay, and every video is transcribed after it arrives.
`scripts/crawl_all.sh` wraps `--crawl` so that nobody has to watch it:

```bash
scripts/crawl_all.sh https://zanza.tv/irodalom               # in this terminal
scripts/crawl_all.sh --background https://zanza.tv/irodalom  # keeps running after the terminal closes
scripts/crawl_all.sh --stop                                  # stops the run in progress
```

Like the web UI, it is a thin shell around the commands above and has no
ingestion logic of its own. Compared with a plain `download.py --crawl`, it:

- **checks first:** runs `download.py --check`, and refuses to start when no
  speech-to-text backend is installed, because every transcript would stay
  pending;
- **retries:** while videos fail, it waits (`--pause`, 10 min) and runs the
  same crawl again, for up to `--retries` (2) extra rounds. Staged videos are
  not read again, so an extra round costs only the listing pages and the
  failed videos. YouTube's occasional `HTTP Error 403` clears this way. An
  age-gated video does not, and it stays on the failed list;
- **catches unreadable pages:** a network hiccup on a listing page hides every
  video below it without failing the run. When the crawl reports an unreadable
  page, the script runs another round;
- **finishes the job:** runs `transcribe.py --pending` for any transcript that
  failed inline, then `validate.py --repair-archive`;
- **keeps the Mac awake** with `caffeinate` (a closed MacBook lid still puts it
  to sleep), refuses a second run while one is in progress, and writes all
  output to `logs/crawl_all-<date>-<time>.log`.

The last line says either `OK - ...` or what is still missing
(`NOT COMPLETE - ...`), and the exit code is 0 only in the first case. Running
the same command again is always safe, because it only does what is still
missing. Here `--max-items` defaults to 500, since crawling a whole subject is
the point. `--dry-run` plans without downloading.

`scripts/crawl_status.sh` shows how far the current or last run has got: the
round, videos found, done and failed so far, the video in progress, and an
estimated finish time. It only reads the logs, and `--watch` refreshes it
every minute until the run ends.

## 8. Duplicate protection

Three independent layers:

1. `archive/index.json` - `source_id → path, url, timestamp`.
2. `archive/downloaded.txt` - the same in yt-dlp's `--download-archive` format.
3. On-disk check - a folder holding `source.md` plus a non-empty media file
   counts as downloaded even if the index was lost.

A known source prints `SKIPPED - already downloaded` and nothing is fetched.
Re-downloading is a deliberate act: `--force`.

The index is one file, so a save merges in whatever another run wrote in the
meantime: a terminal command next to the web UI cannot drop the other's
entries. What an interrupted run never got to write is repaired from the
staged folders themselves, without downloading anything:

```bash
python3 scripts/validate.py --repair-archive
```

`validate.py` reports such a folder as `archive.missing_entry`. Note that a
missing entry never causes a re-download on its own - the on-disk check
catches it - it only makes a later run re-read that one page.

The `source_id` is stable: `<provider>-<platform video id>`, e.g.
`zanza-abc123`. When a platform exposes no id, a hash of the canonical URL is
used and marked (`zanza-u1a2b3c4d5`).

## 9. Transcript workflow

With `transcript.enabled: true` (the default) every download is transcribed
right away. A failure there is a warning, never a failed download: the media
and the notes are already correct on disk, the transcript stays

```yaml
transcript_status: pending
```

and `transcribe.py --pending` can retry later. Set `transcript.enabled: false`
to keep downloading and transcribing strictly separate.

Transcription is also a standalone, pluggable step:

```bash
python3 scripts/transcribe.py --list-backends
python3 scripts/transcribe.py "staging/Zanza/Történelem/Az ókori Athén"
python3 scripts/transcribe.py --pending --language hu
python3 scripts/transcribe.py --pending --dry-run
```

| Backend | What it does |
|---|---|
| `subtitles` | converts a `.vtt`/`.srt` downloaded next to the video (enable `subtitles.download`) |
| `faster_whisper` | **default.** Local ASR (`large-v3-turbo`, int8), reads `.mp4` directly, reports per-segment confidence |
| `mlx_whisper` | same weights on the Apple Silicon GPU - about 3x faster, but see the measurement below |
| `whisper_cpp` | local whisper.cpp CLI; the media is decoded to 16 kHz WAV with the bundled FFmpeg |

`auto` tries them in that order. When none is available the command fails
loudly and the transcript stays `pending` - nothing is ever invented.

### Hungarian, and why these defaults

`transcript.language` is set to `"hu"` rather than left to auto-detection:
Whisper occasionally mistakes a short Hungarian opening for another language,
and a wrong guess ruins the whole transcript. Set it to `null` for a mixed
corpus, or override per run with `--language`.

The defaults come from measurements on a 5:47 Hungarian lesson video, not from
assumption:

| Setup | Time | Result |
|---|---|---|
| `faster_whisper` / `small` | 4:50 | usable, but mishears proper nouns ("Korvinus", "korvúsz") |
| `mlx_whisper` / `large-v3-turbo` | 0:45 | **dropped the first 30 seconds** (musical intro) |
| `faster_whisper` / `large-v3-turbo` + VAD | 3:03 | complete and markedly more accurate |

Hence the default: `large-v3-turbo`, `compute_type: int8`, `vad_filter: true`,
`condition_on_previous_text: false`. The last two are what keep a transcript
complete - VAD stops music from swallowing the speech around it, and without
disabling the conditioning one badly decoded 30-second window makes Whisper
repeat that text for the rest of the video. The first run downloads ~1.6 GB of
model weights into `~/.cache/huggingface`.

Expect roughly half of real time on an Apple Silicon CPU: a 6 minute video
takes about 3 minutes. The engine, the model and a mean confidence value are
recorded in the transcript frontmatter, so it stays visible later how a given
text was produced.

The body uses zero-padded markers, which is what makes a timestamp anchor
possible later:

```markdown
[00:00:00]

...

[00:01:32]

...
```

**Fidelity.** The text is written exactly as the engine produced it: no
punctuation repair, no rephrasing, no tidying up. Only surrounding whitespace
is normalised. If you ever edit a transcript by hand, set
`transcript_postprocessed: true` in its frontmatter - a later integration step
must know that the text is no longer a character-exact quote source.

## 10. Validation

```bash
python3 scripts/validate.py            # human readable
python3 scripts/validate.py --json     # machine readable
python3 scripts/validate.py --strict   # warnings fail too
```

Checks: required frontmatter fields and their enums, referenced files actually
existing, non-empty media, valid metadata JSON, duplicate `source_id`s,
`source_id` agreement across the three files, `HH:MM:SS` timestamp format and
ordering, manifest presence and shape, leftover `.part` files, orphaned files,
dangling archive entries, and subjects outside the configured taxonomy.

Exit code 0 means no errors, so it can gate an integration run.

### Hand-off to the vault: one workflow (`--integrate`)

Owner decision, 2026-09-19: *"Az a lényeg, hogy a ytdlp része legyen, mert
ezáltal, ezt összeköthetjük 1 db workflowra (link bemenet -> transcript &
videó -> videó, transcript & metadata integrálása a kért programmal)"*.

```bash
python3 scripts/download.py "URL" --integrate      # link -> staged -> integrated
python3 scripts/integrate.py --pending             # every staged source still 'pending'
python3 scripts/integrate.py --pending --subject Irodalom --limit 5 --dry-run
python3 scripts/integrate.py "staging/Zanza/Irodalom/A Biblia"
python3 scripts/integrate.py --status              # what stands where, no hand-off
```

After staging, every source whose `integration_status` is still `pending` is
handed to `integration.command` (config/config.yaml), with `{folder}` replaced
by the source folder. The pipeline itself still reads and writes nothing
outside this repository: the command is the vault's own integrator
(`media.py auto --staging`), which places the files, writes the source note,
links the video to the notes whose content it really carries, verifies, logs,
and finally writes its answer back into `integration.json`. A failing
integrator never fails the download; `integrate.py --pending` retries it.
`integration.enabled: true` makes every download hand off (`--no-integrate`
opts out once).

**The answer, and what each value means for a re-run:**

| `integration_status` | Meaning | `--pending` |
|---|---|---|
| `integrated` | done, the source is in the vault | skipped |
| `in_review` | the integrator **is asking you**: it could not decide where the video belongs or which notes it carries. Nothing is broken - the answer is given in the vault's own interface (`media.py serve`), and the chain continues from there | skipped, so a re-run does not repeat the question (`--retry-review` overrides, for when the integrator lost the half-finished run) |
| `pending` | not integrated yet, or the integrator stopped before deciding anything | handed off |

Since 2026-09-20 the receiving system decides with a **local model** (the
owner's own `Qwen3-VL-4B`, the same one the notebook-photo chain uses), so
placement and linking no longer cost a Claude session; `in_review` is what is
left after the model, and only that needs a human. The staging side neither
knows nor cares which model that is: this repository only starts the command
and reads the one field that comes back.

## 11. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `yt-dlp is not installed` | `pip install -e .` inside the virtualenv, or set `ytdlp.local_source_path` |
| `TLS certificate verification failed` | python.org macOS builds ship without certificates: run `Install Certificates.command`, or `pip install certifi` |
| `No single-file (video+audio) format matched` | the wanted resolution exists only as separate streams. `inspect.py URL --formats`, then lower `video.max_height` |
| Downloaded video is only 360p | a missing JS runtime or FFmpeg; run `download.py --check` - see [section 15](#15-video-quality-and-the-1080p-setup) |
| `This URL is a playlist/collection` | add `--playlist` (and `--max-items` if needed) |
| `The video is not publicly accessible` | private, age-gated or members-only. No bypass is implemented, by design |
| `Rate limited by the provider` | wait, or set `download.ratelimit: "2M"` |
| Interrupted download | just run the same command again; `.part` files are resumed |
| `SKIPPED - already downloaded` but you want it again | `--force` |
| `subject ... is not in subjects.taxonomy` (warning) | add the name to `subjects.taxonomy`, or fix the alias table |
| `This video is not available` on a zanza.tv page | the embedded YouTube video is embed-only. `ytdlp.extractor_args` must keep a `web_embedded` player client (it does by default) |
| `The page needs to be reloaded` | the configured player-client list no longer works. Restore the default list, or empty `ytdlp.extractor_args` to fall back to yt-dlp's own |
| `No supported JavaScript runtime` warning, some formats missing | YouTube's newer challenge needs a JS runtime. Basic extraction still works; if you need every format, install [deno](https://deno.com) and add `--js-runtimes` support via `ytdlp.extractor_args` or upgrade yt-dlp |
| `No transcription backend is available` | expected until you install one: `pip install -e ".[faster-whisper]"` |
| Wrong project root / staging path | run the scripts from this directory, or set `MSP_PROJECT_ROOT` |
| YAML errors from the built-in reader | `pip install PyYAML` for full YAML support |

Logs: `logs/pipeline-YYYY-MM-DD.log` (full detail) and `logs/events.jsonl`
(one JSON object per event, e.g. every download's real resolution).

## 12. Project structure

```
.
├── README.md               this file
├── CLAUDE.md               how an AI agent must treat this repository
├── pyproject.toml          packaging, dependencies, entry points
├── config/config.yaml      all configuration
├── scripts/                CLI wrappers: download, inspect, validate, transcribe;
│                           crawl_all.sh (unattended crawl),
│                           crawl_status.sh (its progress)
├── src/msp/                the package
│   ├── config.py           typed configuration
│   ├── paths.py            project-root discovery
│   ├── naming.py           filename/id sanitisation, path-traversal guard
│   ├── timestamps.py       HH:MM:SS handling and video anchors
│   ├── providers.py        provider identity (folder name, id prefix)
│   ├── subjects.py         subject resolution against the taxonomy
│   ├── downloader.py       yt-dlp adapter + typed error classification
│   ├── metadata.py         info-dict curation, format analysis
│   ├── schema.py           the staging schema (single source of truth)
│   ├── templates.py        note templates and their tiny renderer
│   ├── notes.py            building/writing/updating the notes
│   ├── manifest.py         integration.json
│   ├── archive.py          duplicate protection
│   ├── pipeline.py         orchestration (single, batch, playlist)
│   ├── validation.py       the validator
│   ├── transcription/      pluggable STT backends + transcript writer
│   └── cli/                argparse front-ends
├── templates/              editable copies of the note templates
├── staging/                generated sources (media files are gitignored)
├── archive/                download archive
├── logs/                   text log + JSONL events
└── tests/                  unit and integration tests (no network needed)
```

Editing `templates/source.md` or `templates/transcript.md` changes the note
layout without touching code. `{{key}}` is substituted; a frontmatter line
whose placeholder has no value at all is dropped, while an explicit `null`
stays visible.

## 13. Claude Code workflow

[CLAUDE.md](CLAUDE.md) is the contract for any AI agent working here. In short:

- `source.md` is the entry point of a source; the video and the transcript are
  **sources**, never knowledge notes.
- The staging repository is self-contained; its code never reads or writes a
  production vault. Since 2026-09-19 (owner decision) `--integrate` and
  `integrate.py` start the vault's **own** integrator as a command - the vault's
  rules decide what happens there, not this repository's.
- Before any knowledge link is derived from a video transcript, the vault
  owner must decide whether video-derived content is an accepted source
  category at all. That decision is recorded in `integration.json`
  (`nn_anchorable`), and `null` means "not decided" - never "yes".

## 14. What zanza.tv actually turns out to be

Verified against the live site in September 2026, because it changes what to
expect:

- **zanza.tv hosts no video itself.** Every lesson page embeds a YouTube player
  (`youtube.com/embed/<id>`) from the site's own channel. yt-dlp follows the
  embed, so the media really comes from YouTube.
- **The staged source is still the zanza.tv page.** Provider (`Zanza`), subject
  (from the URL path, e.g. `/tortenelem/` → `Történelem`) and `source_id`
  (`zanza-<youtube id>`) follow the page you asked for; `media_url` in
  `source.md` and `webpage_url` in `metadata.json` record the YouTube origin.
- **Many of those videos are embed-only.** The plain watch page answers
  *"This video is not available"*, while the embedded player works. That is why
  `ytdlp.extractor_args` selects the embedded player client by default. It is
  client selection, not a bypass: private, paid, age-gated and DRM-protected
  videos still fail, and no credential or cookie is ever used.
- **1080p is available, but only through merging.** These videos are published
  up to format 137 (1440x1080, ~36 MB for 6 minutes) as a video-only DASH
  stream; the single pre-muxed format is 360p (format 18). The pipeline
  downloads the 1080p video and the best audio separately and muxes them with
  FFmpeg. Two things have to be present for that, both checked by
  `download.py --check`: FFmpeg, and a JS runtime for YouTube's player
  challenge - without the latter YouTube does not even list the DASH formats.
- **No subtitles.** The sampled videos carry neither uploaded nor automatic
  captions, so the `subtitles` transcript backend has nothing to read there:
  transcription needs a local ASR backend (`faster-whisper` is the recommended
  one).
- **Eight subjects.** zanza.tv has exactly these sections, and
  `subjects.aliases` maps every one of them:
  `tortenelem`, `irodalom`, `magyar-nyelv`, `matematika`, `filozofia`, `etika`,
  `tarsadalomismeret`, `testneveles-es-sport`. The subject is taken from the
  first path segment of the URL, so a plain `download.py "<url>"` already lands
  in the right folder.

A verified end-to-end run:

```
python3 scripts/download.py "https://zanza.tv/tortenelem/magyarsag-tortenete-kezdetektol-1490-ig/hunyadiak-kora"

Downloading: A Hunyadiak kora
    quality: 1440x1080 (merged video+audio), best offered: 1080p
OK: A Hunyadiak kora -> Zanza/Történelem/A Hunyadiak kora
```

## 15. Video quality and the 1080p setup

The pipeline targets **1080p** (`video.max_height`) and gets there the only way
that works on most platforms: above roughly 360p, video and audio are published
as **separate DASH streams**, so the best video stream and the best audio
stream are downloaded and then muxed into a single MP4.

Three things decide the result:

| Requirement | Why | If missing |
|---|---|---|
| `video.allow_merge: true` | permits selecting separate streams | pre-muxed formats only (~360p) |
| FFmpeg | performs the muxing | the merging selector fails |
| A JS runtime (`node`/`deno`) + `yt-dlp-ejs` | solves YouTube's player ("n") challenge | YouTube lists the 360p pre-muxed format *only*, so nothing better can even be seen |

Both dependencies are part of the project: FFmpeg arrives as a static binary in
the `imageio-ffmpeg` wheel inside the virtualenv (no system-wide install), and
`yt-dlp-ejs` is a normal dependency. Only the JS runtime itself has to exist on
the machine - `node` or `deno`. Check what is actually in use:

```bash
python3 scripts/download.py --check
```

```
FFmpeg        : .../imageio_ffmpeg/binaries/ffmpeg-macos-aarch64-v7.1
JS runtime    : node
```

The selector is derived from the configuration:

```
bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]
  / bestvideo[height<=1080]+bestaudio
  / best[height<=1080][ext=mp4] / best[height<=1080] / best
```

so a source that genuinely has no separate streams still downloads, as a single
file. Every download logs the resolution it really got, and warns only when the
result is below *both* the target and what the video actually offers - a 360p
video that exists only in 360p is reported as source-limited, not as a failure:

```bash
python3 scripts/inspect.py "https://..." --formats   # before downloading
grep download.quality logs/events.jsonl | tail -5    # what was really obtained
```

`metadata.json` records `pipeline.ffmpeg_used`, so it stays visible per source
whether the file was muxed here or came down as one stream.

To go back to a strictly FFmpeg-free setup, set `video.allow_merge: false`;
the configuration then rejects any selector that would need merging, and 360p
becomes the expected result for YouTube-hosted sources.

## 16. Security and legal boundaries

- No passwords, cookies, API keys or tokens are stored, read or supported.
  `.gitignore` blocks such files from being committed by accident.
- No shell command is ever built from downloaded metadata.
- Every filename is sanitised, and every write is checked to stay inside the
  staging root (path-traversal guard).
- Direct, signed media URLs are not written into `metadata.json`.
- TLS verification is never disabled.
- The `--crawl` discovery honours robots.txt and its `Crawl-delay`, names
  itself honestly and never logs in.
- **No DRM circumvention and no access-control bypass** is implemented, and
  none will be. Private, age-gated or members-only videos fail with a clear
  message. Use this only for content you are allowed to download and store
  locally under the service's terms.

## 17. Magyar összefoglaló

Ez a projekt egy **staging (előkészítő) rendszer**: videó URL-ből letölti a
médiát, és egy önmagában értelmes forrásmappát készít belőle. Nem tudásbázis,
és soha nem ír bele az éles Obsidian vaultba.

**Telepítés** (iCloud-mappában a `.venv.nosync` a javasolt név, mert azt az
iCloud nem szinkronizálja; ez már készen van):

```bash
source .venv.nosync/bin/activate
```

**A négy parancs:**

```bash
python3 scripts/download.py "URL"        # egy videó letöltése és stagingelése
python3 scripts/download.py urls.txt     # kötegelt letöltés
python3 scripts/download.py --crawl "https://zanza.tv/tortenelem"  # egy oldal összes videója
python3 scripts/inspect.py "URL"         # mit kínál az oldal (formátumok!)
python3 scripts/validate.py              # a staging fa ellenőrzése
python3 scripts/transcribe.py --pending  # hiányzó transcriptek elkészítése
../../bin/mos pult                        # webes felület: a Manifold-pult (127.0.0.1:8771)
python3 scripts/download.py "URL" --integrate   # link → staging → a vaultba integrálva (2026-09-19)
python3 scripts/integrate.py --pending   # a már stagingelt, még nem integrált források átadása
python3 scripts/integrate.py --status    # mi van bent, mi vár a döntésedre, mi nincs még bent
scripts/crawl_all.sh --background "https://zanza.tv/irodalom"  # egy egész tárgy, felügyelet nélkül
```

**Amit érdemes tudni:**

- A rendszer **1080p-t céloz**: a videó- és hangsávot külön tölti le, majd
  FFmpeg-gel egyesíti (`video.allow_merge`). Ehhez kell az FFmpeg (a venv-ben
  van, nem kell rendszerszinten telepíteni) és egy JS futtatókörnyezet
  (`node`/`deno`) - ezek nélkül a YouTube csak a 360p-s változatot kínálja.
  A `python3 scripts/download.py --check` mindkettőt kiírja. Ha egy videó
  tényleg csak 360p-ben létezik, azt a napló forráskorlátként jelzi.
- Ha egy letöltés megszakad (vagy két futás egyszerre ír), a
  `python3 scripts/validate.py --repair-archive` pótolja a hiányzó
  archívum-bejegyzéseket a staging mappákból, letöltés nélkül.
- A `--crawl` egy tárgy- vagy témakör-oldal alatti **összes videót** letölti
  (webes felületen: *az oldal összes videója*). Betartja a robots.txt-t és a
  10 mp-es várakozást, ezért egy teljes tárgy felderítése ~20 perc, a
  transzkripciókkal együtt órák. Újrafuttatva csak az új videókat tölti le.
- Egy egész tárgyat felügyelet nélkül a `scripts/crawl_all.sh` tölt le, pl.
  `scripts/crawl_all.sh --background https://zanza.tv/irodalom`. Indulás előtt
  ellenőrzi, hogy van-e beszédfelismerő. A sikertelen videókat 10 perc múlva
  újra megpróbálja (legfeljebb 2 extra kör), a végén pótolja a hiányzó
  transcripteket és ellenőrzi a staging fát. Közben ébren tartja a Macet
  (lecsukott fedéllel azonban elalszik). A napló a
  `logs/crawl_all-*.log` fájlba kerül, leállítani a
  `scripts/crawl_all.sh --stop` paranccsal lehet. Újraindítva csak a még
  hiányzó videókat tölti le. Hogy hol tart, a `scripts/crawl_status.sh`
  mutatja meg (folyamatosan frissítve: `--watch`).
- A `subjects.taxonomy` listát érdemes a vault saját tantárgyneveihez igazítani
  (ékezet, nagybetű pontosan), mert így nem kell később mapping-tábla.
- A transzkript automatikus és magyarul fut (`transcript.language: "hu"`,
  `large-v3-turbo` modell). Egy 6 perces videó kb. 3 perc. Az első futás
  ~1,6 GB modellt tölt le a `~/.cache/huggingface` mappába.
- A transcript szövege nyers marad: nincs "megszépítés", mert az idézhetőséget
  rontaná. Ha kézzel átírod, állítsd `transcript_postprocessed: true`-ra.
- A videóból származó tartalom vault-beli felhasználása **eldöntött**: a vault
  2026-09-09-i `D2` döntése szerint a videó teljes jogú forrás (`#t=` horgony),
  NN-élt viszont nem kap. 2026-09-19 óta a letöltés és az integráció **egy
  munkafolyamat** (`--integrate`): a vault saját integrátora helyezi el a
  videót, és csak azokhoz a jegyzetekhez köti, amelyek tartalmát a videó
  ténylegesen hordozza - a részletek a [CLAUDE.md](CLAUDE.md) végén.
- **A döntést a vault oldalán 2026-09-20 óta egy helyi modell hozza**
  (`Qwen3-VL-4B`, ugyanaz, amelyik a füzetfotókat olvassa): nem kell hozzá
  Claude-munkamenet. Ahol a modell nem biztos - nem tudja, melyik témába való a
  videó, vagy melyik jegyzetet hordozza -, ott a lánc **megáll és kérdez**: a
  forrás `integration_status`-a `in_review` lesz, és a választ a vault saját
  felületén adod meg (`media.py serve`). A `--pending` az ilyen forrást békén
  hagyja (nem kérdezi meg újra), a `--status` pedig megmutatja, hány vár rád.
