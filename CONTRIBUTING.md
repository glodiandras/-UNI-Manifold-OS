# Contributing to Manifold

Thanks for your interest. Manifold is a local-first knowledge OS for macOS (Apple Silicon). This page explains how the repository is organised, how to run the tests, and the rules every change has to respect.

The project is pre-release and the work is organised in phases ([docs/PLAN.md](docs/PLAN.md), progress in [docs/plan/NAPLO.md](docs/plan/NAPLO.md)). Please open an issue before starting anything larger than a small fix, so the change can be fitted into the plan.

## Repository structure

| Path | What |
|---|---|
| `shell/` | macOS shell (Swift, AppKit + WKWebView) |
| `app/` | User interface (Svelte 5 + TypeScript); UI tests in `app/tests` |
| `core/` | Python core |
| `modulok/` | Pipelines the core runs as subprocesses |
| `config/` | Shipped defaults, model manifest, runtime pins, Python lock file |
| `packaging/` | Builds the macOS app bundle and DMG |
| `tests/` | Python test suite (unittest) |
| `tools/` | Developer-only tools, never shipped |
| `docs/` | Plan, developer references, user documentation |

Each directory is described in [docs/dev/REPO-LAYOUT.md](docs/dev/REPO-LAYOUT.md); the documentation map is [docs/README.md](docs/README.md).

## Setting up

Manifold builds and runs on macOS (Apple Silicon) only.

```bash
bin/mos runtime fetch      # once, online: Python, Node, wheels, ffmpeg (sha256-pinned)
bin/mos runtime install    # offline: build var/venv from the wheels
bin/mos app install        # UI packages (first time: --online)
bin/mos doctor             # environment check
```

`runtime/` (portable toolchain) and `var/` (local state, models, logs) are git-ignored. In a development checkout `runtime` may be a symlink to an existing toolchain; it is never committed.

## Running the tests

```bash
bin/mos app test                                # UI tests (vitest)
bin/mos app build                               # svelte-check (warnings fail) + production build
MOS_DEVELOPER_BUILD=1 bash shell/build.sh         # native self-test hooks, ad-hoc signed
MOS_SETTINGS='' MOS_SZIGORU=1 bin/mos test        # whole Python suite, strict skips
bin/mos test test_dokumentacio test_csomag_jegyzek # only the named modules
bin/mos test --szint lista                       # named test levels (fresh-install, multi-user, migracio, biztonsag, mentes, dod)
MOS_DEVELOPER_BUILD=0 bash shell/build.sh         # restore the release shell after the tests
```

- `MOS_SZIGORU=1` turns a skipped test into a failure unless the skip is marked `[indokolt]` (a documented property of the machine, such as a missing optional tool). Do not hide a gate behind an unmarked skip.
- `MOS_SETTINGS=''` makes the tests ignore your personal install-level settings.
- Native self-tests require a developer shell built against the current sources. A release shell rejects `--selftest`; restore and verify a release build before packaging.
- Tests use synthetic workspaces in temporary directories (`tests/helpers.py`). They must never open a real notes folder.
- The continuous-integration workflow (`.github/workflows/ci.yml`) runs UI checks and the Python suite on a hosted macOS runner. The core job fetches the pinned Python/Node/ffmpeg runtime, builds the UI and developer shell, and runs the native WKWebView self-tests. Hosted-runner window-server support remains unconfirmed. Real model measurements, optional compiled-language toolchains, performance/manual gates and release steps remain outside this workflow; its comments list the limits. Local phase-closing gates remain required.

## Rules that every change follows

In short (the full contract for contributors working with an AI agent is [CLAUDE.md](CLAUDE.md)):

1. **Keep the architecture.** Swift shell, Svelte UI, Python core, model worker, `modulok/` pipelines. Product work is configuration, separation and UX, not rewrites. Keep existing behaviour unless the plan says otherwise, and record any deviation in the NAPLO.
2. **Your data comes first.** Atomic writes with snapshots, conflict detection, trash instead of delete, undo as `git revert` (never `reset --hard`, `clean` or `checkout -- .`). Automated writes go only through the machine-write service (`core/gepi_iras.py`). Code runs only in the sandbox. No network at runtime except explicit downloads.
3. **Measured AI.** Only a calibrated model runs for real; everything else is a trial clone. Do not weaken the gates.
4. **No hardcoded paths.** Every path comes from the layered configuration (`config/os.toml`, then the install `settings.toml`, then the workspace `.manifold/workspace.toml`).
5. **Nothing personal in the repository.** No developer paths, real names, vault or folder names, private notes, handwriting or gold sets built from private material. Defaults are neutral.
6. **Developer-only tooling** is hidden behind Developer mode, not deleted.

## Naming and language

- **Identifiers** (variables, functions, modules, API routes) are Hungarian **without accents** (for example `munkater`, `vaultio`, `/api/...`). This is a deliberate convention inherited from Manifold-OS 2.0; please follow it for new code rather than mixing in English identifiers.
- **User-facing text is English.** In the UI use `t()` with keys in the English dictionaries under `app/src/lib/i18n/en/`; in the core use an error code (`kod`), parameters (`param`) and an English fallback message. Do not add raw Hungarian strings to the UI; a ratchet test (`app/tests/i18n-ratchet.test.ts`) enforces this.
- Code comments and developer documents may be Hungarian or English.

## Design and quality gates

- Use design tokens only (`app/src/styles/tokens.css`); no raw colours, sizes or durations in components. See [docs/dev/DESIGN.md](docs/dev/DESIGN.md).
- Burgundy is the single accent and never signals state. Errors always carry an icon and words. Quiet mode never hides error, unsaved or disconnected indicators.
- New UI must pass `app/tests/tokenek.test.ts` and `app/tests/kontraszt.test.ts`.
- Documentation tests (`tests/test_dokumentacio.py`, `tests/test_felhasznaloi_doku.py`) check the README and `docs/user/` for broken links, unknown `bin/mos` commands and personal paths.

## Submitting a change

1. Keep the change small and reviewable; one concern per pull request.
2. Run the relevant tests (see above) and say in the pull request what you ran.
3. For phase work, add a NAPLO entry: what changed, what remains, regressions, risks.
4. Fill in the pull request template checklist.

Security problems: please do not open a public issue; see [SECURITY.md](SECURITY.md).

The project license has not been chosen yet. Until a `LICENSE` file is added, do not assume any license for contributions; ask in an issue before sending substantial work.
