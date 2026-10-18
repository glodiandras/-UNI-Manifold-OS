# 10 — Bases (database views): Obsidian parity audit

**Subsystem:** the `.base` file format, the Bases query engine (`core/bazis/`), the Bases UI (`app/src/bazis/`) and its three hosts (the `.base` tab, the ```` ```base ```` block, the `![[x.base#View]]` embed).
**Reference:** the Obsidian help pages for Bases (overview, create/embed, syntax, views, Table/List/Cards/Kanban/Map, formulas and functions), read 2026-10-17 (`help.obsidian.md` redirects to `obsidian.md/help`). Where the Obsidian side is not documented in what I read, the row carries `confidence: low/medium`; no *must* rests on a low-confidence statement. Kanban is documented as **Obsidian 1.14+**; Map needs the separate Maps community plugin (1.10+).
**Code read** (paths relative to `/Volumes/Work/[UNI] Manifold-OS`): `core/bazis/{modell,lekerdezes,api,adat,kiertekelo,kifejezes,ertekek,fuggvenyek,hivatkozas}.py`, `app/src/bazis/*` (all 29 files), `core/vaultio.py:51`, `core/hibauzenetek.py`, `app/src/hej/Fa.svelte`, `app/src/szerkeszto/notion/sablonok.ts`; tests `tests/test_bazis_*.py`, `tests/kezi/bazis_*.py`, `app/tests/bazis-*.ts`. Context: `docs/dev/ARCHITECTURE.md:165-166,212-216`, `docs/dev/DECISIONS-v2.md:36` (decision 23), `docs/plan/parity/{01,04,07}`. I also evaluated about 50 documented expressions against the engine (`tests.test_bazis_kiertekelo` fixtures, `var/venv`); results are cited where they matter.

**Legend.** Status: *present* / *partial* / *missing* / *ahead* (Manifold does more than Obsidian) / *n.a.* (not Obsidian core). Priority: **must** = daily-use behaviour, or a product rule from `CLAUDE.md`; **should** = noticeable; **could** = polish or niche. Size: S (<1 day), M (1–3 days), L (>3 days). Gap ids `10-bases-NN` point to section 2.

**Overall picture.** This is the most complete subsystem audited so far. The file format, the expression language, the function library (every function on the Obsidian Functions page is registered, plus `list.sum/mean/median/stddev/min/max`), filters, multi-key sort, grouping, limit, all 14 built-in summaries plus custom ones, Table/Cards/Kanban, cell editing, embedding, and rename-safe `.base` references all exist and are tested (about 5 500 lines of Bases tests). The gaps are almost all in the **UI layer on top of the engine**: no List view, no visual filter builder, no sort/group management beyond the Table header, no "New" row, no export, plus a language leak (Hungarian defaults written into new `.base` files and shown as column headers). Two *must*, twelve *should*, five *could*.

---

## 1. Checklist

### 1.1 File format and hosts

| # | Obsidian behaviour | Manifold today (path:line) | Status | Priority | Size | Confidence | Gap |
|---|---|---|---|---|---|---|---|
| 1 | `.base` is YAML with `filters`, `formulas`, `properties`, `summaries`, `views`; invalid YAML is reported | `core/bazis/modell.py:222-271` (`betolt`; a YAML error is `vegzetes`, the file is not touched, the error is shown: `BazisNezet.svelte:78-83`) | present | – | – | high | – |
| 2 | Unknown keys and view keys survive an edit | raw YAML is the truth, key order kept: `modell.py:3-5,283-285`; round-trip proof on every write `:482-489` | ahead | – | – | high | – |
| 3 | Edit the file as text | `forras_csere` (comments survive): `modell.py:442-454`; YAML toggle `Eszkoztar.svelte:155-165`, `BazisNezet.svelte:98-111`; only *new* errors block a save | ahead | – | – | high | – |
| 4 | Comments in a `.base` after a UI edit | lost on full re-dump (`modell.py:6-7`, decision 23(f)) | present (parity unverified) | – | – | low | Q1 |
| 5 | ```` ```base ```` code block in a note | `beagyazas.ts:28-52`; interactive in Live Preview, writes through the host note's transaction (`forras.ts:116-135`) | present | – | – | high | – |
| 6 | `![[File.base]]` and `![[File.base#View]]` | `beagyazas.ts:54-86` (`link.alcel` → `nezet`); `this` = host note (`forras.ts:66`); chip in-line and in hover previews (`:60`) | present | – | – | high | – |
| 7 | New base from the explorer folder menu | `Fa.svelte:446`, `core/vaultio.py:51,555` | present | – | – | high | – |
| 8 | Palette commands: create a base, insert a base into the note, add a view | `app/src/bazis/index.ts:13-22` registers only a tab view and two renderers; no commands. The `/` menu inserts a ```` ```base ```` block (`sablonok.ts:249`) | partial | should | S | medium | 11 |
| 9 | Base in the sidebar, `this` = active file | no sidebar host (`index.ts:15-20`); `this` is always the base file or the host note (`forras.ts:66`) | missing | could | M | medium | 15 |
| 10 | Rename/move updates references inside bases | `core/bazis/hivatkozas.py` (plan, whitelist, warnings), `ARCHITECTURE.md:216` | ahead | – | – | high | – |

### 1.2 Views

| # | Obsidian behaviour | Manifold today (path:line) | Status | Priority | Size | Confidence | Gap |
|---|---|---|---|---|---|---|---|
| 11 | **Table** layout, row height short…extra tall, resizable columns | `Tabla.svelte` (windowed rows, `ablak.ts`), `rowHeight` `BeallitasPanel.svelte:138-141`, `columnSize` `lekerdezes.py:239-243`, resize `Tabla.svelte:162-164` | present | – | – | high | – |
| 12 | **Cards**: card size, image property (attachment, URL, hex colour), fit, aspect ratio | `Kartyak.svelte:17`, `Kartya.svelte`, `lekerdezes.py:107-133` (`_kep`), `BeallitasPanel.svelte:145-173` | present | – | – | high | – |
| 13 | **List** layout: bullets/numbers/none, indented properties or separator | `TIPUSOK = ("table","cards","kanban")` `modell.py:27`; `NezetTipus` `tipusok.ts:22`; `type: list` degrades to a table with a warning (`modell.py:207-215`) | missing | **must** | M | high | 02 |
| 14 | **Kanban** (1.14+): columns from the group property, drag changes the property, "None" column | `Kanban.svelte`, `kanban.ts:43-66`; `type: kanban` accepted, `board` alias (`modell.py:28`, assumption K12) | partial | should | M | medium | 14 |
| 15 | Kanban: reorder/hide/add columns, per-column "+" creates a note, folder grouping moves the file | none (`kanban.ts:43-66` derives columns from data; `Kanban.svelte` has no create action) | missing | should | M | medium | 14 |
| 16 | **Map** layout | not supported; needs the Maps community plugin in Obsidian | n.a. | could | L | high | 19 |
| 17 | Add, switch, rename, delete, reorder views; view name menu | `Eszkoztar.svelte:45-95,101-133`; `modell.py:368-391` (unique-name numbering); reorder by menu, not drag | present | – | – | high | – |
| 18 | Default view chosen by name (`#View`, `name`) | `Bazis.nezet_keres` `modell.py:190-204` (index, name, case-insensitive) | present | – | – | high | – |
| 19 | Unknown view type | kept in the file, shown as a table with a warning (`modell.py:207-215`) | ahead | – | – | high | – |

### 1.3 Filters, sort, group, limit

| # | Obsidian behaviour | Manifold today (path:line) | Status | Priority | Size | Confidence | Gap |
|---|---|---|---|---|---|---|---|
| 20 | Global and per-view filters combine with AND; no source key, every vault file is a row | `lekerdezes.py:153-163`; row set = every live index file `adat.py:1-8` | present | – | – | high | – |
| 21 | Filter = string statement or `and`/`or`/`not` of statements | `modell.py:64-88,99-126`; a list is an implicit `and` | present | – | – | high | – |
| 22 | Visual filter builder (property · operator · value rows) with an advanced text editor | text/YAML only (decision 23(b)): `SzuroPanel.svelte:35-57`, `SzovegMezo.svelte` | missing | should | L | high | 03 |
| 23 | A broken or failing statement | parse error → statement is false and listed; runtime error → row skipped, counted in `hibak[].db` (`modell.py:107-118`, `lekerdezes.py:165-168`) | ahead | – | – | high | – |
| 24 | Multi-key sort with priority, on any property or formula | `Nezet.rendezes` `modell.py:147-154`; stable back-to-front sort `lekerdezes.py:204-206` | present | – | – | high | – |
| 25 | Sort menu in the toolbar (add/remove keys, direction, priority) | only the **Table header** (click, ⇧-click, menu): `Tabla.svelte:218-222`, `muveletek.ts:55`. Cards and Kanban have no sort control (no `sort` hit in `Kartyak/Kanban/Eszkoztar/BeallitasPanel.svelte`) | partial | should | M | high | 04 |
| 26 | Group by one property, ASC/DESC | `lekerdezes.py:215-230`; header menu `Tabla.svelte:224-225`; panel `BeallitasPanel.svelte:104-125` | present | – | – | high | – |
| 27 | `groupOrder`: choose, order, hide groups; empty groups; `null` = no value | no occurrence of `groupOrder` in `core/`, `app/src/`, tests (key is preserved on write but ignored) | missing | should | M | high | 05 |
| 28 | Collapse groups in table, cards and list | group rows are static (`Tabla.svelte:454-465`); no expanded state anywhere | missing | should | S | medium | 06 |
| 29 | `limit` caps results (after sort) | `lekerdezes.py:207-209`; panel `BeallitasPanel.svelte:127-135`; hard cap 10 000 rows with a "cut" flag `:24,211-213` | present | – | – | high | – |

### 1.4 Properties, columns and namespaces

| # | Obsidian behaviour | Manifold today (path:line) | Status | Priority | Size | Confidence | Gap |
|---|---|---|---|---|---|---|---|
| 30 | Properties menu: show/hide/reorder (`order`), search | `OszlopPanel.svelte:45-69`; header menu hide/move `Tabla.svelte:239-241` | present | – | – | high | – |
| 31 | `properties.<id>.displayName` | `Bazis.megjelenes` `modell.py:185-188`; rename in header `Tabla.svelte:257-268`; `megjelenites_beallit` `modell.py:420-438` | present | – | – | high | – |
| 32 | Property picker lists every note property | `Tabla.tulajdonsag_lista(max_db=400)` `adat.py:146-150` | partial | could | S | high | 18 |
| 33 | Bare name = `note.name`; `note["x"]` | `kiertekelo.py:184-199`; `modell.py:39-45`; case-insensitive fallback `adat.py:73-79` | present | – | – | high | – |
| 34 | `file.name/path/folder/ext/size/ctime/mtime/tags/links/embeds/backlinks/properties/file` | `fuggvenyek.py:745-778` (+ `basename`, `note`); typed columns `lekerdezes.py:28-33` | present | – | – | high | – |
| 35 | `file.ctime` = creation time | `Tabla.ctime` `adat.py:170-183`: `os.stat` per row at query time, falls back to **mtime**; the F11 index now stores `ctime_ns` (`core/index/indexelo.py:607-626,723`) but Bases does not use it | partial | should | S | high | 13 |
| 36 | `formula.<name>`, formulas may use formulas, no cycles | `KepletTar` `kiertekelo.py:295-358`; cycle = error, error is a cell not a view failure (`lekerdezes.py:193-194`) | present | – | – | high | – |
| 37 | `this` (base file / host note / active file) | `kiertekelo.py:185-186`; `lekerdezes.py:147-149`; embed → host (`forras.ts:66`); sidebar case missing (row 9) | partial | – | – | high | 15 |

### 1.5 Expression language and functions

| # | Obsidian behaviour | Manifold today (path:line) | Status | Priority | Size | Confidence | Gap |
|---|---|---|---|---|---|---|---|
| 38 | Operators `+ - * / %`, `== != > < >= <=`, `! && \|\|`, lists, objects, regex literals, 0-based indexing | Pratt parser `kifejezes.py:1-12`; depth cap `MAX_MELY=200`; tests `tests/test_bazis_kifejezes.py` | present | – | – | high | – |
| 39 | Global functions `escapeHTML date duration file html if image icon link list max min now number today random` | all registered `fuggvenyek.py:97-255`; `if` is lazy `kiertekelo.py:220` | present | – | – | high | – |
| 40 | Any/Date/String/Number/List/Link/File/Object/RegExp methods and fields | all names on the Functions page registered `fuggvenyek.py:257-780`; spot-checked by evaluation (`map/filter/reduce`, `split`, `replace(/l/g,…)`, `flat`, `sort`, `keys`, `relative`, `format("dddd")`) | present | – | – | high | – |
| 41 | Extra list statistics | `list.sum/mean/median/stddev/min/max` `fuggvenyek.py:520-563` | ahead | – | – | high | – |
| 42 | Date arithmetic with duration strings (`now() + "1d"`, `"2 hours"`), date − date | `date + "2 hours"`, `+ "1M"`, `+ (duration("1d")*2)` evaluated OK; `date − date` returns milliseconds (`86400000`), matching the syntax page | present | – | – | medium | Q2 |
| 43 | `html()`, `image()`, `icon()` values render | core returns `{t:'html'|'kep'|'ikon'}` (`ertekek.py:763-767`) but the cell shows the raw source/path/name as text (`ertek.ts:102-107`, `Cella.svelte:63-68`) | partial | should | S | high | 08 |
| 44 | Formula/filter editor assistance (property and function suggestions, help) | plain textarea with live validation only (`SzovegMezo.svelte:105`, placeholder examples `SzuroPanel.svelte:39,50`) | missing | should | M | medium | 10 |
| 45 | Create/delete formulas from the UI | `SzuroPanel.svelte:60-105`; `keplet_beallit` `modell.py:401-419` removes dangling references (`:326-342`) | present | – | – | high | – |

### 1.6 Summaries

| # | Obsidian behaviour | Manifold today (path:line) | Status | Priority | Size | Confidence | Gap |
|---|---|---|---|---|---|---|---|
| 46 | Built-ins: Average Min Max Sum Range Median Stddev · Earliest Latest Range · Checked Unchecked · Empty Filled Unique | all 14 `lekerdezes.py:64-102`, `modell.py:31-32`; menu `Tabla.svelte:226-236`, `muveletek.ts:18` | present | – | – | high | – |
| 47 | Custom summaries (`values` list) | `lekerdezes.py:66-74`; validated on load `modell.py:264-270` | present | – | – | high | – |
| 48 | Per-view mapping, per group when grouped | `lekerdezes.py:258-284` | present | – | – | high | – |

### 1.7 Editing from the view

| # | Obsidian behaviour | Manifold today (path:line) | Status | Priority | Size | Confidence | Gap |
|---|---|---|---|---|---|---|---|
| 49 | Edit a note property in its cell | `cellaIr.ts`, `CellaSzerkeszto.svelte`; goes through the open `Dokumentum` (CAS, autosave, ⌘Z), core schema check with an explicit "write anyway", snapshot + undo button (`cellaIr.ts:57-112,114-144`) | ahead | – | – | high | – |
| 50 | Table selection (range, row, column), copy/paste, undo/redo, Backspace clears, Tab/Shift-Tab, Home/End, Page Up/Down | single active cell with arrows, Enter/F2/Space only (`Tabla.svelte:313-350`); no range, clipboard, clear, Tab, Home/End or paging | missing | should | L | medium | 12 |
| 51 | Kanban drag changes the grouped property | `Kanban.svelte:95-125`, `kanban.ts:64-66`; scalar values only, `.md` only | present | – | – | high | – |
| 52 | "New" button creates a note pre-filled from the filters / column | no create path in `app/src/bazis/` | missing | should | M | medium | 07 |
| 53 | Copy the view to the clipboard / export CSV | none (`csv` appears nowhere in `app/src/bazis/` or `core/bazis/`) | missing | should | S | high | 09 |
| 54 | Search within the base | none | missing | could | S | medium | 16 |

### 1.8 Product rules and robustness

| # | Rule / behaviour | Manifold today (path:line) | Status | Priority | Size | Confidence | Gap |
|---|---|---|---|---|---|---|---|
| 55 | English user-facing text (`CLAUDE.md`) | new bases and views are written with Hungarian names (`modell.py:24,215,252,373,477`, `vaultio.py:51`); default column headers are Hungarian (`lekerdezes.py:31-33,241`); engine/validation messages are Hungarian and shown verbatim (`BazisNezet.svelte:81-86`); `kod` on `hibak[]` is never translated by the Bases client (no `kod` use in `app/src/bazis/`) | partial | **must** | M | high | 01 |
| 56 | Live refresh, ordered writes, stale-response drop | 300 ms on `vault_valtozas` (`modell.svelte.ts:13`), numbered requests, serialised writes (`:42,117`) | present | – | – | high | – |
| 57 | Large vaults | 2 s query budget, 16 MiB value budget, request cancellation, incremental table (`api.py:29`, `lekerdezes.py:25`, `ARCHITECTURE.md:212`) | ahead | – | – | high | – |
| 58 | Kanban/cell editor hard-codes the property name `Status` | `kanban.ts:52`, `Kanban.svelte:34`, `cellaErtek.ts:12` | partial | could | S | high | 17 |

---

## 2. Gaps and proposals

All proposals keep the layering: the core computes, the UI writes through the single write path (`Dokumentum` for files, the host note's transaction for blocks), and every change to the `.base` goes through the pure `modosit` with its read-back proof (`modell.py:457-496`).

### 10-bases-01 — Hungarian defaults and messages leak into the product (must, M, high)
**Rule.** `CLAUDE.md`: user-facing text is English via `t()`/`en.json` in the UI and `kod` + `param` + English fallback in the core.
**Manifold.** (a) `UJ_BASE`/`UJ_SZOVEG` write `name: Táblázat` into every new `.base` (`vaultio.py:51`, `modell.py:24`); `nezet_uj` writes `Táblázat/Kártyák/Kanban/Nézet` (`modell.py:373`) and the empty-file fallbacks use `Táblázat` (`:252,477`), `Nézet N` (`:215`). These are *file data*, so they cannot be translated at render time. (b) Column headers fall back to `FAJL_NEV` = `Fájlnév`, `Méret`, `Létrehozva`, … (`lekerdezes.py:31-33,241`); there are no matching keys in `en/*.json`. (c) Every `KifejezesHiba`/`FutasHiba` text (about 58 raise sites in `kifejezes.py`, `ertekek.py`, `fuggvenyek.py`, `kiertekelo.py`) and the `hiba(...)` calls without `kod` in `modell.py:111,229,263,268,470,481` are Hungarian; the 14 coded ones (`hibauzenetek.py`, `bazis.*`) reach the UI in a 200 body and the Bases client prints `h.uzenet` directly (`BazisNezet.svelte:81-86`). (d) The `/` template carries the Hungarian view name (`sablonok.ts:249-256`, marked `i18n-ignore`).
**Proposal.** Default view names in new files become English ("Table", "Cards", "Kanban", "View N"); column headers come from stable ids and are translated in the UI (`o.id` → `t()`), never from the core string; expression/validation errors get a `kod` + `param` and an English fallback, and the Bases client maps `hibak[].kod` through the existing `kodFordit` (`app/src/lib/core/api.ts:112`). Keep reading old Hungarian-named files unchanged.

### 10-bases-02 — List view (must, M, high)
**Obsidian.** A layout alongside Table and Cards: one entry per file, bullet/numbered/no marker; either the other properties as indented sub-items (the first property is the main entry) or inline with a configurable separator.
**Manifold.** `TIPUSOK` has three entries; a `type: list` base authored in Obsidian renders as a table with a warning (`modell.py:27,207-215`). The type switcher offers three types (`Eszkoztar.svelte:45,50`; `BeallitasPanel.svelte:96-103`).
**Proposal.** Add `list` to `TIPUSOK`/`NezetTipus`, a `Lista.svelte` that reuses `Cella.svelte` and the Cards chunking (`Kartyak.svelte:13`), grouping headers as in Cards, settings for marker and separator stored as plain view keys through `nezet_beallit` (exact Obsidian key names are not in the pages I read: use the names found in a real Obsidian-authored fixture, otherwise round-trip unknown keys untouched, which `modosit` already guarantees). Cross-check with `tests/kezi/bazis_paritas.py` (K11).

### 10-bases-03 — Visual filter builder (should, L, high)
**Obsidian.** Filters are built with rows of property · operator · value, grouped with AND/OR/NOT, with an advanced editor for the raw syntax. Both global and per-view scope.
**Manifold.** Text only: an expression or `and/or/not` YAML in a text field with live validation (`SzuroPanel.svelte:35-57`, decision 23(b): "no point-and-click filter builder"). Typing `file.hasTag("x")` or `status != "done"` requires knowing the syntax.
**Proposal.** Keep the text editor as the "advanced" mode and add a builder that reads and writes the same structure (`szuro_fa` gives the tree, `szuro_szoveg` the text). Operators by property type from `valasz.fajl.elerheto[].tipus` (`lekerdezes.py:286-288`); statements the builder cannot represent stay in text mode untouched. **Needs a user decision**: this reverses decision 23(b).

### 10-bases-04 — Sort editor for every layout (should, M, high)
**Obsidian.** A toolbar Sort menu: several keys, each with property, direction and priority, on any property (including formulas), identical for all layouts.
**Manifold.** Sorting exists only as Table header clicks on displayed columns (`Tabla.svelte:218-222`, `muveletek.ts:55-71`). Cards and Kanban show no sort control; a property that is not a column can only be sorted by editing YAML.
**Proposal.** A "Sort" popover next to Columns/Filters/View (`Eszkoztar.svelte:140-152`) listing `view.sort` rows (property picker from `fajl.elerheto`, direction, ↑↓ to reorder, remove), built on the existing `rendezesBeallit` (`muveletek.ts:71`).

### 10-bases-05 — `groupOrder` and group management (should, M, high)
**Obsidian.** `groupOrder` lists which groups appear and in what order (empty list hides all, missing key shows all in `groupBy` order, `null` is the "no value" group); the Group menu offers automatic or manual order, hide/show and adding empty groups.
**Manifold.** The key is preserved but never read (no match in `core/`, `app/src/`, tests); `groupBy` only has `ASC`/`DESC` (`modell.py:156-160`, `lekerdezes.py:228`).
**Proposal.** In `futtat` apply `groupOrder` after grouping (include listed values that have no rows as empty groups, drop unlisted ones, treat `null` as the empty-value key); return the full group set so the UI can offer hide/show; add a Group popover section with drag/↑↓ and a "show hidden" list; Kanban columns use the same list (see 14).

### 10-bases-06 — Collapse groups (should, S, medium)
**Obsidian.** Groups can be collapsed in table, cards and list layouts.
**Manifold.** Group rows are plain headers (`Tabla.svelte:454-465`; Cards likewise).
**Proposal.** A per-view, in-memory (or `localStorage`-style per-viewer) collapsed set keyed by group value; a disclosure button with `aria-expanded` on the group header; the windowed row list (`ablak.ts`) skips collapsed ranges. Not persisted into the `.base` unless Obsidian does (unknown, see Q3).

### 10-bases-07 — Create a note from the view (should, M, medium)
**Obsidian.** A "New" button creates a note in the base (documented for Kanban as pre-filled from the column value; for Table/Cards it is pre-filled from simple equality filters as far as I remember — medium confidence).
**Manifold.** No create path in `app/src/bazis/`.
**Proposal.** A toolbar button that opens the existing safe name workflow (`Fa.svelte` create flow, `POST /api/vault/uj`) in the default folder, then writes the seed properties through `cellaIr` (so schema checks and undo apply). Seed values come from a small core helper that extracts `prop == literal` statements from the active filters, and from the column value in Kanban.

### 10-bases-08 — Render `html()`, `image()`, `icon()` (should, S, high)
**Obsidian.** These functions exist to render in the view.
**Manifold.** The core already returns typed values (`ertekek.py:763-767`) and cover images work for the `image` view key (`lekerdezes.py:107-133`), but the cell shows the HTML source, the image path or the icon name as text (`ertek.ts:102-107`, `Cella.svelte:63-68`).
**Proposal.** `kep` → vault image through `linkek.mediaUrl` (as `Kartya.svelte:41-47`) or colour swatch, external URLs stay a placeholder (D3); `ikon` → the icon set already in `lib/ikon`; `html` → sanitised through the existing inert, bounded sanitiser used for rich paste/Reading HTML (F11 checkpoint), never `{@html}` of raw core text.

### 10-bases-09 — Copy view / export CSV (should, S, high)
**Obsidian.** Copy the current view for pasting into notes or spreadsheets, or export as CSV.
**Manifold.** None; `tests/kezi/bazis_paritas.py` mentions Obsidian CSV only as a manual comparison step.
**Proposal.** Pure function over the `lekerdez` response (`oszlopok`, `sorok[].cellak`, groups flattened with a group column): `ertekSzoveg` → TSV for the clipboard (Markdown table as a second flavour), CSV with RFC 4180 quoting through the existing explicit-download path (D3: user-triggered only). No core change.

### 10-bases-10 — Expression editor assistance (should, M, medium)
**Obsidian.** Formula and filter editors suggest properties and functions.
**Manifold.** Plain textarea (`SzovegMezo.svelte:105`); the function list is only in code (`fuggvenyek.py:97-780`). Errors are shown under the field after 300 ms.
**Proposal.** Reuse the shared fuzzy-completion service (F11 checkpoint two) for `file.`/`note.`/`formula.` names from `fajl.elerheto`, and a function list exported by a `GET`/part of `lekerdez` (`fuggvenyek.metodus_nevek` `:686` exists). Inline signature hint from the registry arity (`_db_ellenor` `:36-45`). Error text localised via 01.

### 10-bases-11 — Command-palette commands (should, S, medium)
**Obsidian.** Commands to create a base, insert a base into the current note, and add a view to the open base.
**Manifold.** `bazisTelepit` registers none (`index.ts:13-22`); creation is explorer-only and the `/` menu. Same item as `07-explorer-23`, which is only "nice" in that audit.
**Proposal.** `bazis.uj` (folder of the active file, as `07-explorer-23`), `bazis.beszur` (inserts a ```` ```base ```` block or `![[…]]`), `bazis.nezet-uj` (when a base tab is active, `nezet_uj`). Keep a single ID across audits when the checklist is merged.

### 10-bases-12 — Table selection, clipboard and undo (should, L, medium)
**Obsidian.** Shift-click ranges, row/column/group selection shortcuts, copy/paste of cells, undo/redo of property changes, Backspace clears, Enter toggles a checkbox, Tab/Shift-Tab, Home/End, Page Up/Down.
**Manifold.** One active cell, arrows, Enter/F2/Space (`Tabla.svelte:313-350`); undo exists as the ⌘Z of an open note or the notification button (`cellaIr.ts:114-144`), not as a Table-level history.
**Proposal.** Selection model in `Tabla.svelte`; paste writes cell by cell with one batch notification and one snapshot per note (reuse `cellaIr` with the open `Dokumentum`); writes keep the schema "write anyway" prompt once per paste. Split: navigation keys (S) first, selection and copy (M), paste and clear (M).

### 10-bases-13 — `file.ctime` from the index (should, S, high)
**Manifold.** `Tabla.ctime` stats each file at query time and falls back to the mtime (`adat.py:170-183`). The F11 explorer work added a real `ctime_ns` index column (`indexelo.py:607-626,723`) and explicitly forbids an mtime stand-in (`CHECKLIST.md` 07-explorer-01).
**Impact.** "Created in the last 7 days" filters and sorts are common; per-query `os.stat` over 10 000 rows competes with the 2 s budget (`api.py:29`) and silently reports a wrong date when the filesystem has no birthtime.
**Proposal.** Carry `ctime_ns` on `Sor`, return `null` (not mtime) when unknown, keep `gyoker` only for tests. Doc line: unknown birthtime renders empty.

### 10-bases-14 — Kanban column management (should, M, medium)
**Obsidian 1.14+.** Drag column headers to reorder; the Group menu hides/adds columns and restores automatic order; the "+" in a column header (and New) creates a note with the column's value; grouping by `file.folder` moves the file on drop; grouping by a formula or other file property disables moves.
**Manifold.** Columns come from data (plus the schema order for `Status`, `kanban.ts:43-66`); drag moves cards between columns for scalar note properties (`kanban.ts:64-66`, `Kanban.svelte:95-125`); no column reorder/hide/add, no create, no folder move. The `type: kanban` spelling is an unverified assumption (K12, decision 23(d)); the Obsidian page does not show config keys.
**Proposal.** Share the `groupOrder` implementation (05) so column order and hiding are stored in the file; "+" uses 07; `file.folder` drop uses the existing move endpoint with the plan overlay skipped only when no links change (`07-explorer-15` mechanism). Verify the real key spellings against an Obsidian-authored base before writing them.

### 10-bases-15 — Base in the sidebar (could, M, medium)
**Obsidian.** A base can open in a sidebar, where `this` is the active file (e.g. "notes linking to this note").
**Manifold.** No sidebar host for arbitrary views (`index.ts:15-20`); `this` is the base or the host note (`forras.ts:66`).
**Proposal.** Register a right-sidebar tab hosting `BazisNezet` with a `forras` whose `ez` follows `felulet` active path; reuse `BazisModell` refresh. Low urgency: embedding in the note covers most uses.

### 10-bases-16 — Toolbar quick search (could, S, medium)
**Proposal.** A search field that filters the already fetched rows client-side on displayed cell text (no change to the saved query); `Eszkoztar.svelte` slot beside the count.

### 10-bases-17 — Hard-coded `Status` (could, S, high)
**Manifold.** Kanban and the cell editor special-case the literal property `Status` for the closed value set (`kanban.ts:52`, `Kanban.svelte:34`, `cellaErtek.ts:12`). With neutral defaults (`CLAUDE.md`) the schema, not a property name, should say which properties have a closed value set.
**Proposal.** Ask the schema endpoint (`tulajdonsagApi().sema`) for the value set of *the grouped key* instead of comparing to `'Status'`; keep `Status` as the neutral default key of that schema.

### 10-bases-18 — Property picker truncated at 400 (could, S, high)
**Manifold.** `Tabla.tulajdonsag_lista(max_db=400)` (`adat.py:146-150`) feeds the column and sort pickers; a vault with more distinct keys loses the rare ones from the picker (they still work in YAML). **Proposal.** Raise or page the list; keep frequency order; add the "n more" hint.

### 10-bases-19 — Map view (could, L, high)
In Obsidian it needs a separate community plugin plus online tiles, so it is outside the core-parity scope and conflicts with D3 (no runtime network). Keep unsupported; the existing "unknown view type → table + warning" fallback (`modell.py:207-215`) is the right behaviour. Record explicitly as "not planned".

---

## 3. Manifold strengths beyond Obsidian (keep)

1. **Complete function library plus extras and tested semantics.** Every Functions-page entry is registered; extra list statistics; a JavaScript-subset parser with a depth cap and a per-type method registry (`fuggvenyek.py`, `kifejezes.py`); about 300 engine tests (`tests/test_bazis_*.py`).
2. **A documented-semantics parity gate.** `tests/test_bazis_paritas.py` compares query results with sets derived by hand from the documentation, not from engine output (P1–P5, `:1-60`).
3. **Safe writes.** Cell edits go through the open document (CAS, autosave, ⌘Z) with schema validation, an explicit "write anyway" and a snapshot with an Undo button (`cellaIr.ts`); `.base` edits run a read-back proof and only new errors block a save (`modell.py:457-496`); two quick operations are serialised (`modell.svelte.ts:42`).
4. **Failure isolation.** A bad formula is a cell error, a failing filter statement skips rows and counts them, a malformed file never breaks the host note; cancellation, a 2 s query budget and a 16 MiB value budget bound the cost (`lekerdezes.py:165-195`, `api.py:29-95`).
5. **Rename-safe bases.** Link-like literals in `link()`, `file()`, `hasLink`, `linksTo`, `file.path ==`, `inFolder` are rewritten in the same plan and commit as note links; name-based expressions only warn (`hivatkozas.py`, `ARCHITECTURE.md:216`).
6. **Unknown view types and keys survive** and degrade visibly (warning, table).
7. **Embedding with `this`** bound to the host note, an interactive block that writes in the host note's transaction, and chips in hover previews and in-line (`beagyazas.ts`, `forras.ts`).
8. **Performance work** with measured targets: windowed table (<80 DOM rows at 2 000 rows), incremental `Tabla` refresh (≈1 ms at 10 000 notes), chunked cards (`ARCHITECTURE.md:212`, `Tabla.svelte`, `Kartyak.svelte:13`).
9. **Kanban already in place** with schema-ordered `Status` columns and empty-column drop targets (`kanban.ts`), ahead of the explicit Obsidian 1.14 documentation.

---

## 4. Open questions

1. **Comments on UI rewrite.** Manifold documents that a UI edit re-dumps the YAML and drops comments "like Obsidian" (decision 23(f)). I could not confirm Obsidian's behaviour from the pages read; verify with a real base. If Obsidian preserves comments, row 4 of section 1.1 becomes a *should* gap.
2. **Date subtraction.** The syntax page says subtracting two dates yields milliseconds, which Manifold matches. If current Obsidian returns a duration with fields such as days/hours, `(a - b).days` would return empty here. Confirm manually (K11).
3. **Persistence of collapse and group state.** Is the collapsed state, or a manual group order, stored in the `.base` view (then it must round-trip) or only in the workspace?
4. **Exact config keys** for List (markers, separator, indent) and Kanban (column order, hidden columns, column width) are not shown on the pages read. Capture them from an Obsidian-authored fixture before implementing 02/05/14. The existing `board` alias and `kanban` type are assumptions (K12).
5. **New-note seeding.** Which filters pre-fill a new note in Obsidian Table/Cards (equality only? tags? folder?) is only documented for Kanban columns.
6. **Decision 23(b).** Reopen "no visual filter builder"? This is the largest single UX item (L) and the only one that reverses an earlier decision.
7. **Editable file cells.** Whether `file.name`/formula cells are editable in Obsidian tables was not documented in the pages read; Manifold makes only note properties of `.md` rows editable (`lekerdezes.py:242`).
8. **Sidebar semantics** for `this` when the active file is not a note (canvas, PDF): Obsidian behaviour unknown.
