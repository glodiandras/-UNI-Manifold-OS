# Manifold (product repo) — working contract for AI agents

This repository is the **product** built from Manifold-OS 2.0. The plan is `docs/PLAN.md`; the phase log is `docs/plan/NAPLO.md`; the audits that justify the plan are `docs/plan/audit/`.

## Sources and boundaries

- `/Volumes/Work/Manifold-OS v2` is the **read-only source of truth**. Never write there, never run its `bin/mos`, never create files there. Read it when you need the original behaviour; cite it as `v2:<path>:<line>`.
- Everything you build goes **here**. If you need something from v2 (a file, a fixture, a doc), copy it here first.
- The user's real vault (`/Volumes/Work/Manifold`) is read-only and must never be opened by tests. Tests use synthetic vaults in temp dirs (`tests/helpers.py`).
- Local state lives in `var/` (gitignored). The dev checkout may symlink `runtime` to v2's runtime (read-only use).

## Non-negotiables (inherited from v2, see `docs/dev/DECISIONS-v2.md`)

- DO NOT REBUILD: keep the architecture (Swift shell → Svelte UI → Python core → model worker → `modulok/` pipelines) and all existing features. Product work is configuration, separation and UX, not rewriting.
- Data safety first: atomic writes with snapshots, conflict detection, trash instead of delete, undo = `git revert` (never `reset --hard`, `clean`, `checkout -- .`), machine writes only through the machine-write service (`core/gepi_iras.py`), sandboxed code execution, no network at runtime except explicit downloads (D3).
- Measured AI (D9): only a **calibrated** model runs for real; everything else is `proba` (trial clone). Do not weaken the gates; the calibration threshold is being moved *into* code, not removed.
- No hardcoded absolute paths; every path comes from the layered config (`config/os.toml` ← install `settings.toml` ← workspace `.manifold/workspace.toml`).
- Identifiers (variables, functions, modules, API routes) stay **Hungarian without accents** (v2 decision 12). **User-facing text is English** via `t()`/`en.json` in the UI and `kod` + `param` + English fallback in the core. Do not add new raw Hungarian UI strings (a ratchet test enforces this).
- Design: tokens only (`app/src/styles/tokens.css`), burgundy is the single accent and never signals state, errors always carry an icon and words, quiet mode never hides error / unsaved / disconnected indicators. New UI must pass `tests/tokenek.test.ts` and `tests/kontraszt.test.ts`.
- Nothing personal in the repo: no developer paths, vault folder names, subject maps, calendar keywords, handwriting fixtures, gold sets built from private notes. Defaults are neutral; the developer's own conventions are reachable only through settings or the v2-import tool.

## Working method

- One phase at a time (`docs/PLAN.md` §10). At the end of a phase: tests green (`bin/mos test`, `bin/mos app test`), a NAPLO entry (what changed, what remains, regressions, risks), commit. Do not silently continue into the next phase.
- Prefer small, reviewable changes; keep v2 behaviour unless the plan says otherwise; when you must deviate, write it in the NAPLO.
- Developer-only tooling is hidden behind Developer mode, not deleted.
