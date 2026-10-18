# MANIFOLD

**Your knowledge. One system.**

Manifold is a local-first knowledge OS for macOS (Apple Silicon): a Markdown workspace with an Obsidian-style editor, and a measured local AI layer built into the workspace. Everything runs on your machine; your notes stay plain Markdown files in a folder you own.

## Highlights

- **Markdown-native** — your workspace is a folder of `.md` files; Obsidian vaults open as they are, and keep working in Obsidian.
- **Local AI, real verification** — models run on your Mac; AI-generated cards, quizzes, summaries and answers pass a source-fidelity gate, math is checked by a CAS sandbox, code runs in a sandbox with tests.
- **No cloud required** — no account, no internet at runtime. Network is used only when you explicitly download models or media.
- **Reversible machine actions** — every automated write is a snapshot you can undo in one click.
- **One workspace** — notes, PDFs, video transcripts, spaced-repetition cards (Anki-compatible), quizzes, math, a C++ workbench, graph view, Bases and canvas, calendar and reminders, assistant, backup and restore — in one app.

## Status

Pre-release. This repository is the productization of Manifold-OS 2.0 into an installable, multi-user product. The work is planned and tracked in [docs/PLAN.md](docs/PLAN.md); progress and per-phase reports are in [docs/plan/NAPLO.md](docs/plan/NAPLO.md).

## Requirements (target)

- Apple Silicon Mac, macOS 26 or newer, 16 GB RAM recommended for local AI (the app works without AI on 8 GB).
- Install: download the DMG, drag Manifold to Applications, launch. Local AI models are optional downloads from **Settings › AI › Models**.

## Quick start for developers

Manifold builds and runs on macOS only. The portable runtime (Python, Node, wheels, ffmpeg) is fetched once, hash-pinned, and lives under `runtime/` (git-ignored); local state lives under `var/` (git-ignored).

```bash
bin/mos runtime fetch      # once, online: Python, Node, wheels, ffmpeg (sha256-pinned)
bin/mos runtime install    # offline: build var/venv from the wheels
bin/mos app install        # UI packages (first time: --online)
bin/mos app build          # svelte-check + vite build → app/dist
bin/mos test               # Python tests
bin/mos app test           # UI tests
bin/mos doctor             # environment check
```

Tests use synthetic workspaces in temporary directories; they never touch a real notes folder. See [CONTRIBUTING.md](CONTRIBUTING.md) for the test levels, the quality gates and the project rules.

## Repository layout

| Path | What |
|---|---|
| `shell/` | macOS shell (Swift, AppKit + WKWebView): window, launcher, menus, calendar helper, trash |
| `app/` | User interface (Svelte 5 + TypeScript, CodeMirror 6) |
| `core/` | Python core: workspace I/O, snapshots, index and search, task queue, model router, backups |
| `modulok/` | Pipelines run by the core as subprocesses: cards, quiz, summaries, math, graphs, sandbox, C++, notebook OCR, video, source-fidelity gates, evaluation |
| `config/` | Shipped defaults (`os.toml`), model manifest, runtime pins, Python lock file |
| `bin/mos` | Developer and runtime entry point |
| `tests/` | Python test suite (unittest) and UI tests (vitest under `app/tests`) |
| `docs/` | Product plan, developer references, user documentation |

A more detailed map is in [docs/dev/REPO-LAYOUT.md](docs/dev/REPO-LAYOUT.md). Identifiers in the code base are Hungarian without accents (a deliberate convention inherited from Manifold-OS 2.0); the user interface is English.

## Documentation

- User guide: sixteen pages, starting at [Getting started](docs/user/GETTING-STARTED.md).
- Map of all documentation: [docs/README.md](docs/README.md).
- Plan and phase log: [docs/PLAN.md](docs/PLAN.md), [docs/plan/NAPLO.md](docs/plan/NAPLO.md).
- Contributing: [CONTRIBUTING.md](CONTRIBUTING.md). Security reports: [SECURITY.md](SECURITY.md).

## License

License: TBD — see LICENSE once chosen.
