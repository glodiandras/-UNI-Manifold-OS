# Repository layout

A map of the top-level directories. Module and directory names are Hungarian without accents (see [CONTRIBUTING.md](../../CONTRIBUTING.md)); the descriptions below are in English.

| Directory | Contents |
|---|---|
| `app/` | The user interface: Svelte 5 + TypeScript + CodeMirror 6 (`app/src`), its vitest tests (`app/tests`), and the build output `app/dist` (git-ignored) that the core serves. Design tokens are in `app/src/styles/tokens.css`; English strings are in `app/src/lib/i18n/en/`. |
| `core/` | The Python core: workspace and file I/O (`vaultio`), snapshots and undo, index and search, task queue, model router and loader (`core/modell`), machine-write service (`gepi_iras.py`), backup and restore, HTTP/WebSocket server, layered configuration (`config.py`, `gyokerek.py`), the `doctor` health check. |
| `modulok/` | Pipelines the core runs as subprocesses: cards (`kartya`), quiz (`kviz`), summaries (`osszefoglalas`), math (`matek`), plots (`grafikon`), notebook OCR (`fuzet`), code workbench (`kod`, `cpp`), video (`ytdlp`), the sandbox (`homokozo`), source-fidelity gates (`kapuk`) and evaluation sets (`eval`). |
| `shell/` | The macOS shell in Swift (AppKit + WKWebView): window, launcher, menus, calendar helper, trash, the build script `build.sh` and the app icon sources. |
| `packaging/` | Builds and verifies the app bundle and DMG (`build_app.py`), runtime fetching, relocation, signing and notarization helpers. Developer-only; not part of the shipped app. |
| `tools/` | Developer tools such as the synthetic-data generator. Never packaged. |
| `tests/` | The Python test suite (unittest): unit and integration tests, named test levels (`szintek.py`), synthetic-workspace helpers (`helpers.py`), fixtures (`adat/`) and manual gates (`kezi/`). UI tests are in `app/tests`. |
| `config/` | Shipped defaults (`os.toml`), the model manifest (`models.toml`), runtime pins (`runtime-pins.env`), the Python dependency source and hashed lock file (`requirements.in`, `requirements.lock`), and optional settings presets. |
| `docs/` | Documentation; see [docs/README.md](../README.md). |
| `bin/` | `bin/mos`, the single developer and runtime entry point (tests, build, runtime fetch, doctor, core start). |

Not in git (see `.gitignore`):

- `runtime/` is the portable toolchain (Python, Node, wheels, ffmpeg, LLVM). In a development checkout it can be a symlink to a toolchain kept elsewhere; it is created by `bin/mos runtime fetch`. Continuous integration has no `runtime/` and installs its tools from the pins instead.
- `var/` holds local state, models, caches, logs and the virtual environment.
- `app/dist/`, `app/node_modules/`, `packaging/out/`, `Manifold.app/` and `*.dmg` are build outputs.
