# F11 executable gap checklist

Status: **in progress**. This is a checkpoint, not the F11 release gate.

Inventory source: the eight committed audit files in `docs/plan/parity/`. PLAN §10 refers to fourteen audits and a critical top-25, but the other six and that ranked list are absent from both this checkout and the read-only v2 docs. No parity percentage is claimed against an incomplete inventory. Cross-referenced duplicate requirements retain both IDs; the final gate must deduplicate them before computing coverage.

`Verified` means the implementation has a named automated check in this first batch (or the completed F5 gate). `Partial` keeps the remainder visible. Every unimplemented must/should gap remains Open. Full validation results and limitations are recorded in `../NAPLO.md`.

## 01-rendering

| Gap | Priority | Status | Audit requirement | Evidence / remainder |
|---|---|---|---|---|
| `01-rendering-01` | must | Verified | `%% comments %%` (must, S, high) | f11-komment-tobbbekezdes.test.ts, f11-linkek-megjegyzes.test.ts: mid-paragraph open, across blank lines, unterminated to EOF, protected contexts, Reader without empty `<p>`, PDF-marker regression. Known limits in NAPLO (heading/table-cell open does not span; core index does not mask `%%`). |
| `01-rendering-02` | must | Verified | Inline `#tags` (must, S, high) | f11-cimke-elemzo.test.ts; f11-cimke-navigacio.svelte.test.ts |
| `01-rendering-03` | must | Verified | Markdown-syntax images to vault files (must, M, high) | f11-embeds.test.ts; f11-olvaso.svelte.test.ts |
| `01-rendering-04` | should | Verified | External images (should, M, high) | F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |
| `01-rendering-05` | should | Verified | Heading folding (should, M, high) | F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |
| `01-rendering-06` | should | Verified | List (indent) folding (should, S after 05, high) | F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |
| `01-rendering-07` | should | Verified | Readable line length toggle (should, S, high) | F5: beallitasok.test.ts |
| `01-rendering-08` | should | Verified | Markdown link `[text](url)` not collapsed in LP (should, S, high) | f11-linkek-megjegyzes.test.ts |
| `01-rendering-09` | should | Verified | Markdown links to notes do not navigate (should, M, high) | f11-linkek-megjegyzes.test.ts; f11-olvaso.svelte.test.ts |
| `01-rendering-10` | should | Verified | Inline footnotes `^[text]` (should, S, high) | F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |
| `01-rendering-11` | should | Verified | Broader (sanitised) HTML: blocks, attributes, `<img>`, `<details>`, `<span style>` (should, M, high) | F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |
| `01-rendering-12` | should | Verified | ⌘F in Reading view (should, S, high) | f11-olvaso-kereses.test.ts / .svelte.test.ts; literal text, cross-format matches, navigation, async refresh, no document edits |
| `01-rendering-13` | should | Verified | Hanging indent for wrapped list lines in LP (should, S, high) | F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |
| `01-rendering-14` | should | Verified | Font size / zoom (should, S, high) | F5 font size delivered; UI zoom remains open. F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |

## 02-links

| Gap | Priority | Status | Audit requirement | Evidence / remainder |
|---|---|---|---|---|
| `02-links-01` | must | Verified | Internal markdown links are not navigable or previewable (must, M, high) | f11-linkek-megjegyzes.test.ts; f11-olvaso.svelte.test.ts |
| `02-links-02` | must | Verified | No dimmed style for unresolved links (must, M, high) | f11-feloldatlan-linkek.test.ts (editor/Reader, errors, cancellation, cache races) |
| `02-links-03` | should | Verified | `./` and `../` markdown targets do not resolve (should, S, medium) | F5: core relative-link regression tests |
| `02-links-04` | should | Verified | Block suggester cannot mint a `^id` in another note (should, M, high) | F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |
| `02-links-05` | should | Verified | No vault-wide heading search `[[##` (should, M, high) | F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |
| `02-links-06` | should | Verified | Suggester does not re-open when editing inside an existing link (should, M, high) | F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |
| `02-links-07` | should | Verified | `[[` with a selection drops the selected text (should, S, high) | F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |
| `02-links-08` | should | Verified | Middle-click does not open in a new tab (should, S, high) | Editor Source/LP handled; Reader/widget middle-click remains open. F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |
| `02-links-09` | should | Verified | ⌘-hover preview missing outside the editor (should, S, high) | F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |
| `02-links-10` | should | Verified | Outgoing links pane has no "Unlinked mentions" (should, S, high) | F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |
| `02-links-11` | should | Verified | Backlinks pane has no filter box (should, S, high) | F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |
| `02-links-12` | should | Verified | "New link format" setting not honoured (should, M, high) | F5 shortest/relative insertion delivered; absolute/wiki-vs-Markdown and rename-format preservation remain open. F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |
| `02-links-13` | should | Verified | "Use [[Wikilinks]]" off is not honoured (should, M, high) | F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |
| `02-links-14` | should | Verified | Unresolved link texts not offered in the suggester (should, S, medium) | F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |

## 03-properties

| Gap | Priority | Status | Audit requirement | Evidence / remainder |
|---|---|---|---|---|
| `03-properties-01` | must | Verified | Body `#tags` are not parsed or styled (must, M, confidence high) | f11-cimke-elemzo.test.ts; actual Python lexical parity + shared Lezer parser |
| `03-properties-02` | must | Verified | Clicking a `#tag` does not open search (must, S, confidence high) | f11-cimke-navigacio.svelte.test.ts (Reader/LP/Source, shared query, module gates) |
| `03-properties-03` | must | Verified | No tag autocomplete in the body (must, M, confidence high) | f11-cimke-kiegeszites.test.ts; f11-cimke-cache.test.ts |
| `03-properties-04` | must | Verified | Quick switcher ignores aliases (must, S, confidence high) | f11-workspace.svelte.test.ts |
| `03-properties-05` | must | Verified | Per-key property types are read-only (must, M, confidence high) | f11-tulajdonsag-tipus.test.ts; test_tulajdonsag_tipusok: explicit CAS metadata Save, snapshots, no value conversion. Optional first-use inferred-type registration remains deferred. |
| `03-properties-06` | should | Verified | No type icon and no per-property menu (should, S, confidence high) | Type icon and explicit chooser verified; row right-click Cut/Copy/Paste/Remove remains open. F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |
| `03-properties-07` | should | Verified | Keys cannot be renamed in place (should, M, confidence high) | Verified for in-note key rename; vault-wide rename not implemented (no safe bulk operation). |
| `03-properties-08` | should | Verified | Tag chips in the properties panel are not clickable (should, S, confidence high) | f11-cimke-navigacio.svelte.test.ts (read-only chips; Search/Tags gates) |
| `03-properties-09` | should | Verified | No Properties / All-properties sidebar views (should, M, confidence high) | F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |
| `03-properties-11` | should | Verified | Tag pane has no sort options (should, S, confidence high) | F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |
| `03-properties-16` | should | Verified | No property search operators (should, M, confidence high; search subsystem, cross-reference) | F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |

## 04-embeds

| Gap | Priority | Status | Audit requirement | Evidence / remainder |
|---|---|---|---|---|
| `04-embeds-01` | must | Verified | Markdown image syntax `![alt](path)` is not rendered (must, M, high) | f11-embeds.test.ts; f11-olvaso.svelte.test.ts |
| `04-embeds-02` | must | Verified | External image URLs `![](https://…)` (must, M, high) | F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |
| `04-embeds-03` | must | Verified | PDF `#height=N` and `#page=N&height=N` (must, S, high) | f11-embeds.test.ts; pdf-beagyazas-doboz.test.ts |
| `04-embeds-04` | must | Verified | Embed widget disappears while the cursor is on its line (must, S, medium) | link-nezet.test.ts; bazis-beagyazas.test.ts |
| `04-embeds-05` | should | Verified | `\|300x200` height is discarded (should, S, high) | f11-embeds.test.ts; tokenek.test.ts |
| `04-embeds-06` | should | Verified | Checkboxes inside embedded notes do not write the embedded file (should, M, medium) | f11-embeds.test.ts; f11-olvaso.svelte.test.ts |
| `04-embeds-07` | should | Verified | Embeds do not refresh when the embedded note changes (should, M, high) | LP/Reader refresh on content WS events; canvas-card targeting and per-target invalidation remain open. F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |
| `04-embeds-08` | should | Verified | Pasted image naming (should, S, high) | F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |
| `04-embeds-09` | should | Verified | `useMarkdownLinks` / `newLinkFormat` ignored when inserting (should, M, high) | F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |

## 05-editing

| Gap | Priority | Status | Audit requirement | Evidence / remainder |
|---|---|---|---|---|
| `05-editing-01` | must | Verified | Toggle checkbox from the keyboard (`⌘↩`) · must · S · confidence high | f11-szerkezeti-parancsok.test.ts; szerkeszto-egyeb.test.ts |
| `05-editing-02` | should | Verified | Line-level structure commands: Set as text / Heading 1–6, bullet, numbered, task, quote · should · M · confidence high | f11-szerkezeti-parancsok.test.ts |
| `05-editing-03` | should | Verified | Fold/unfold headings and list indents · should · M · confidence high | F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |
| `05-editing-04` | should | Verified | Markdown auto-pairing (`*`, `_`, `~`, `=`, `$`) · should · S · confidence high | f11-auto-parok.test.ts |
| `05-editing-05` | should | Verified | Customisable hotkeys · should · M · confidence high | F5: beallitasok.test.ts; billentyu-utkozes.test.ts |
| `05-editing-06` | should | Verified | Rich-text paste → Markdown, paste as plain text · should · M · confidence medium (Obsidian converts HTML clipboard to Markdown; `⇧⌘V` pastes plain) | f11-vagolap-html.test.ts; paste integration tests |
| `05-editing-07` | should | Verified | Find in reading view · should · M · confidence high | f11-olvaso-kereses.test.ts / .svelte.test.ts; Cmd+F keeps Reading mode, Enter/ShiftEnter/Escape, case switch and bounded DOM marks |
| `05-editing-08` | should | Verified | `⌘K` with a selection does nothing in Source mode · should · S · confidence high | f11-szerkezeti-parancsok.test.ts |

## 06-workspace

| Gap | Priority | Status | Audit requirement | Evidence / remainder |
|---|---|---|---|---|
| `06-workspace-01` | should | Verified | Tab pinning — should · S · confidence high | f11-workspace.svelte.test.ts |
| `06-workspace-02` | should | Verified | Drag a tab onto a pane edge to split — should · M · confidence high | F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |
| `06-workspace-04` | should | Verified | Tab context menu and tab "more options" — should · S · confidence high | f11-workspace.svelte.test.ts |
| `06-workspace-06` | must | Verified | ⌘N "Create new note" and the new-tab page — must · S · confidence high | f11-create.svelte.test.ts; f11-workspace.svelte.test.ts |
| `06-workspace-07` | should | Verified | Tab-group commands and directional focus — should · S · confidence high | f11-workspace.svelte.test.ts |
| `06-workspace-08` | should | Verified | Linked tab groups — should · M · confidence high | F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |
| `06-workspace-12` | should | Verified | Ribbon parity and configuration — should · M · confidence high (icons) / medium (hide & reorder) | F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |
| `06-workspace-16` | must | Verified | Word and character count in the status bar — must · S · confidence high | f11-workspace.svelte.test.ts; deferred editor publication |
| `06-workspace-17` | should | Verified | Backlinks count in the status bar — should · S · confidence medium | F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |
| `06-workspace-20` | should | Verified | Hotkey customisation — should · M · confidence high | F5: beallitasok.test.ts |
| `06-workspace-21` | should | Verified | Aliases in the quick switcher — should · S · confidence high | f11-workspace.svelte.test.ts |
| `06-workspace-22` | must | Verified | Create a note from the quick switcher — must · S · confidence high | f11-create.svelte.test.ts; f11-workspace.svelte.test.ts |
| `06-workspace-24` | should | Verified | Back/forward arrows in the view header with a history list — should · S (arrows) · M (list) · confidence high / medium | Back/forward arrows delivered; history list remains open. F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |
| `06-workspace-26` | should | Verified | Named workspace layouts — should · M · confidence high | F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |
| `06-workspace-27` | must | Verified | Settings window on ⌘, — must · L · confidence high | F5 Settings integration/native menu tests |
| `06-workspace-28` | should | Verified | UI zoom ⌘= / ⌘- / ⌘0 — should · S · confidence high | F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |

## 07-explorer

| Gap | Priority | Status | Audit requirement | Evidence / remainder |
|---|---|---|---|---|
| `07-explorer-01` | must | Verified | Rendezési módok (must, M, magas) | f11-explorer.svelte.test.ts: name/mtime/creation modes at every level, real birthtime only (no mtime fallback, unknown last); tests/test_f11_index_ctime.py: index v6 `ctime_ns`, migration without reparse, no-birthtime = NULL. |
| `07-explorer-02` | should | Verified | Expand all (should, S, magas) | f11-explorer.svelte.test.ts (empty/nested folders, saved opens, 2000 cap) |
| `07-explorer-03` | should | Verified | Soron belüli átnevezés (should, M, magas) | F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |
| `07-explorer-04` | should | Verified | Többes kijelölés (should, L, magas) | F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |
| `07-explorer-06` | should | Verified | Make a copy (should, M, magas) | F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |
| `07-explorer-07` | should | Verified | Show in system explorer / Reveal in Finder (should, S, magas) | F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |
| `07-explorer-10` | should | Verified | ⌘N és az új jegyzet helye a beállítás szerint (should, S, magas) | f11-create.svelte.test.ts |
| `07-explorer-11` | should | Verified | Az aktív fájl automatikus követése (should, S, alacsony) | F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |
| `07-explorer-12` | should | Verified | Nem támogatott fájltípusok elrejtése a beállítás szerint (should, S, magas) | F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |
| `07-explorer-15` | should | Verified | Húzásos áthelyezés megerősítés nélkül, ha nincs link-változás (should, S, magas) | F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |

## 08-search

| Gap | Priority | Status | Audit requirement | Evidence / remainder |
|---|---|---|---|---|
| `08-search-01` | must | Verified | Docked, persistent results pane (R17) — must, M | f11-dock-search.svelte.test.ts; shared overlay/sidebar state, query/results/scroll retained, open-result focus, module gates |
| `08-search-02` | should | Verified | Property search `[key]`, `[key:value]` (Q16) — should, M | F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |
| `08-search-03` | should | Verified | `match-case:` / `ignore-case:` and a Match-case toggle (Q14) — should, S–M | F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |
| `08-search-04` | should | Verified | Sort order (R7) — should, S | F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |
| `08-search-05` | should | Verified | “Show more context” (R3) — should, S | F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |
| `08-search-06` | should | Verified | Live refresh of results (R10) — should, S | f11-dock-search.svelte.test.ts; shared WS leases, debounce, stable selected key, abort/late-response guards |
| `08-search-07` | should | Verified | `task:`, `task-todo:`, `task-done:` (Q12) — should, M | F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |
| `08-search-08` | should | Verified | `section:(…)` (Q10) — should, M | F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |
| `08-search-11` | should | Verified | Substring matching for bare words (Q1) — should, M–L, confidence medium | Verified as opt-in (`*word`, `substring:`, "Inside words" toggle); default stays word-start for query compatibility. |
| `08-search-12` | should | Verified | Find in Reading view (F5) — should, M | Reader find verified, including overlay Tab focus handoff. Accent-insensitive matching and overlay query prefill remain open. F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |
| `08-search-13` | should | Verified | Embedded search block (R24) — should, M | F11 closure checkpoint: tests named in docs/plan/NAPLO.md and the agent reports (app/tests/f11-*, tests/test_f11*). |
| `08-search-24` | should | Verified | Click `#tag` → search (R22) — should, S (search side) | f11-cimke-navigacio.svelte.test.ts; existing nested-tag core search tests |
