# Documentation map

Start here to find your way around `docs/`. Some developer and planning documents are written in Hungarian (the project's working language); the user documentation and the phase log are in English.

## For users

[`user/`](user/) is the user guide, one page per topic, shipped inside the app. Start with [Getting started](user/GETTING-STARTED.md). The README at the repository root links the rest.

## For developers

[`dev/`](dev/) holds the stable developer references (not shipped):

- [REPO-LAYOUT.md](dev/REPO-LAYOUT.md): what every top-level directory contains.
- [ARCHITECTURE.md](dev/ARCHITECTURE.md): shell, UI, core, model worker and pipelines; the API surface.
- [DECISIONS-v2.md](dev/DECISIONS-v2.md): the numbered decisions inherited from Manifold-OS 2.0 and the working contract.
- [DESIGN.md](dev/DESIGN.md): the design system (tokens, icons, motion, focus).
- [LEGACY-SZERZODESEK.md](dev/LEGACY-SZERZODESEK.md): behaviours that must stay identical to the legacy system.

Format of the plot code block: [PLOT-FORMATUM.md](PLOT-FORMATUM.md).

## Plan and history

- [PLAN.md](PLAN.md): the productization plan (phases, definition of done, open questions).
- [2026-10-18 audit and completion plan](plan/2026-10-18-STABILIZALASI-TERV.md): the annotated PDF mapped to current UNI code, fresh integration failures, RAM measurements, macOS 27 design direction and remaining release gates.
- [S0 integration report](plan/S0-INTEGRACIO.md): implementation, safety fixes and current verification of the first execution checkpoint.
- [`plan/NAPLO.md`](plan/NAPLO.md): the phase log: what changed in each phase, what remains, regressions, risks.
- [`plan/f3/`](plan/f3/), [`plan/f5/`](plan/f5/), [`plan/f11/`](plan/f11/): design documents and checklists of individual phases.
- [`plan/audit/`](plan/audit/): the audits that justify the plan (personal coupling, core architecture, UI, build and installer, AI layer, tests, security, backup and restore).
- [`plan/parity/`](plan/parity/): the Obsidian-parity audits of the editor (rendering, links, properties, embeds, editing, workspace, explorer, search, graph, templates, appearance).

`plan/` is excluded from release archives (see `.gitattributes`); `docs/user/` is the only part of `docs/` that is packaged into the app.
