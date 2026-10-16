# 08 — Vault search and in-note search: Obsidian parity audit

Scope: the ⇧⌘F vault search window (`app/src/atfedes/KeresoAblak.svelte`, state in `app/src/lib/kereses/`), the core
lexical search (`core/index/kereses.py`, route `core/index/api.py:26`), the hybrid/semantic layer
(`core/kereses_api.py`, `core/index/hibrid/`), and the in-note search (the CodeMirror `@codemirror/search` panel wired in
`app/src/szerkeszto/beallitas.ts:119-120` and `app/src/kod/szerkeszto.ts:67-69`). Compared against Obsidian 1.8/1.9
desktop, core features and core plugins only (Search, Bookmarks, Page preview). Uncertain Obsidian claims are marked
*(confidence: low/medium)*; everything else is high confidence. Paths are relative to the repo root; `path:line` cites the
code as read on 2026‑10‑15.

Reference docs used: `docs/dev/ARCHITECTURE.md:161` (lexical endpoint), `:190` (search window), `:308-319` (hybrid, C25c);
`docs/dev/DESIGN.md:222` (search window design), `:26`, `:49` (tokens); `docs/plan/audit/03-felulet.md:231`, `:272`.

Summary: the query language covers the daily subset (words, quotes, OR, `-`, parentheses, `path:`, `file:`, `tag:`,
`line:`, `/regex/`) and the result window is keyboard-first, accessible and fast. The biggest Obsidian behaviours missing
are a **docked, persistent results pane**, **property search `[key:value]`**, **`match-case:`/sort order/“show more
context”**, **`task:`/`section:`/`block:`/`content:`**, **find in Reading view**, the **embedded `query` block**, and the
small productivity items (explain, copy results, history, bookmarks, live refresh). Manifold is ahead on semantic search,
media (PDF/VTT/OCR) search, relevance ranking, error reporting, regex safety and the in-note find/replace panel.

---

## 1. Checklist

Status: **present** / **partial** / **missing** / **extra** (Manifold only, preserve). Severity and effort only for gaps.
“must” = daily-use Obsidian behaviour users will miss immediately; “should” = noticeable; “nice” = polish.
Effort: S < 1 day, M 1–3 days, L > 3 days.

### 1.1 Query language (vault search)

| # | Obsidian behaviour | Manifold today (path:line) | Status | Sev. | Eff. |
|---|---|---|---|---|---|
| Q1 | Plain word: case-insensitive **substring** match in content, file name and path *(substring: confidence medium)* | Word matches at **word start only** (`(?<!\w)` prefix regex, `core/index/kereses.py:269-271`; FTS prefilter `fts_kifejezes(..., prefix=True)` `:226`), accent- and case-insensitive (`hajt` `:44-53`); falls back to name/path `:290-291`. “ház” finds “házak” but not “lakóház”. | partial | should | M–L |
| Q2 | `"exact phrase"` | Lexer `kif` token `core/index/kereses.py:67-71`, FTS phrase `:228`, Python phrase regex `:272` | present | — | — |
| Q3 | `-term` negation (also `-"phrase"`, `-(…)`, `-tag:x`) | `nem` token `:76-78`, parser `:136-137`, eval `:295-296` | present | — | — |
| Q4 | `a OR b` (uppercase) | `vagy` token `:90`, parser `:119-124`, FTS `:232-234`, eval `:305-311` | present | — | — |
| Q5 | `( … )` grouping | lexer `:64-66`, parser `:138-142`; unbalanced → 400 “hiányzó/fölösleges záró zárójel” `:141`, `:204-206` | present | — | — |
| Q6 | `path:x`, `path:"a b/"` | `op` token `:80-88`, eval substring `:314-315`, `_ertek_illik` `:275-278`; `/regex/` value too (extra) `:7` | present | — | — |
| Q7 | `file:x` | eval `:316-317` (matches `fajl.nev`, name with extension `core/index/tar.py:24`) | present | — | — |
| Q8 | `tag:#a` incl. nested `#a/b`, with or without `#` | `:318-322` (`cimke.kis` table `core/index/tar.py:42`); `tag:/regex/` extra `:319-320` | present | — | — |
| Q9 | `line:(a b)` / `line:x` | parser `:144-147`, eval per line `:323-330` (name/path fallback disabled for lines `:264-266`) | present | — | — |
| Q10 | `section:(a b)` — terms in the same heading section | not in `OPERATOROK` (`:38`); the index has `fejezet(fajl_id, szint, szoveg, sor)` `core/index/tar.py:45-46` | missing | should | M |
| Q11 | `block:(a b)` — terms in the same block/paragraph | missing (`blokk` table `core/index/tar.py:47-49` only holds `^id` blocks) | missing | nice | S |
| Q12 | `task:x`, `task-todo:x`, `task-done:x` | missing; the index already has `feladat(fajl_id, sor, allapot, szoveg, …)` `core/index/tar.py:66-68` | missing | should | M |
| Q13 | `content:x` — content only, not file name/path | missing (every bare word also matches name/path `:290-291`) | missing | nice | S |
| Q14 | `match-case:(…)`, `ignore-case:(…)` + **Match case** toggle button | missing: everything is folded by `hajt` (`:271-278`, `:286-287`); no toggle in `KeresoAblak.svelte` (only “Jelentés szerint” `:270-273`) | missing | should | S–M |
| Q15 | `/regex/` on content; follows the Match-case toggle (default insensitive) *(default-insensitive: confidence medium)* | present (`:72-75`, `:164-192`), but **always case-sensitive** (`regex.M` only `:174`, documented `:10`). Extra: 2 s budget, `concurrent=True`, clear 400 on timeout `:369-379`. | partial | nice | S |
| Q16 | Property search `[key]`, `[key:value]` (1.4+) | missing in the vault search lexer (`:58-92` has no `[`); exists in the **graph** filter (`app/src/lib/graf/lekerdezes.ts:7`) and the index has `tulajdonsag(fajl_id, kulcs, tipus, ertek)` `core/index/tar.py:38-41` | missing | should | M |
| Q17 | Malformed query → silently empty | Manifold returns 400 with a Hungarian message, shown in `role="alert"` (`core/index/kereses.py:131,141,176,206,376`; `vaultKereses.svelte.ts:235`; `KeresoAblak.svelte:276-278`) | extra | — | — |
| Q18 | Help link to search docs | Inline syntax cheat-sheet when the field is empty `KeresoAblak.svelte:281-295` | extra | — | — |
| Q19 | 1-character queries search | `MIN_HOSSZ = 2` (`vaultKereses.svelte.ts:140`, `:189-200`, tip `KeresoAblak.svelte:255-256`); deliberate (T152) | partial | nice | S |

### 1.2 Results, interaction, entry points

| # | Obsidian behaviour | Manifold today (path:line) | Status | Sev. | Eff. |
|---|---|---|---|---|---|
| R1 | Results grouped by file, per-file match badge | Card per file: name + “N egyezés” `KeresoAblak.svelte:301-320`; count = returned lines, **capped at 20 per file** (`MAX_SOR` `core/index/kereses.py:42`, `:364-365`) | partial | nice | S |
| R2 | Match lines with highlighted term and short context | Up to 4 snippet rows (`KIVAGAS_MAX` `:43`), window ±60/150 code points (`:339`; `darabok` `vaultKereses.svelte.ts:80-97`), same-line hits merged (`sorokraEgyesit` `:64-77`), “+N további sor” `:342` | present | — | — |
| R3 | “Show more context” toggle (neighbouring text) | Context lines are **requested** (`kornyezet=1` `vaultKereses.svelte.ts:214`; core `core/index/kereses.py:359-362`) and carried (`elotte/utana` `:15-16`, `:54-55`) but **never rendered** in `KeresoAblak.svelte`; hybrid endpoint has no `kornyezet` passthrough (`core/kereses_api.py:241-245`, `core/index/hibrid/kereso.py:127,156`) | partial | should | S |
| R4 | Collapse results (global) and per-file expand/collapse | Global ⌘G toggle, persisted (`KeresoAblak.svelte:202`, `felulet.svelte.ts:34,59,129,226`); per-file collapse missing | partial | nice | S |
| R5 | Explain search term | missing | missing | nice | S |
| R6 | Copy search results (link style, path, context options) *(exact options: confidence medium)* | missing | missing | nice | S |
| R7 | Sort order: file name A→Z/Z→A, modified new/old, created new/old (no relevance sort) *(confidence medium)* | Only relevance: `bm25(fts, 2.0, 10.0, 1.0)` `core/index/kereses.py:385-387`, media merged by score `:416`; hybrid: RRF/rerank `core/index/hibrid/kereso.py:169-181` | missing | should | S |
| R8 | Result count | “N találó fájl”, “legalább N” lower bound, “(az első 200 látszik)” `KeresoAblak.svelte:263-267`; `legalabb` from early stop/time budget `core/index/kereses.py:395-400` | present | — | — |
| R9 | All matching files listed (lazy rendered) | Hard cap `KERESES_LIMIT = 200` (`vaultKereses.svelte.ts:137`), no “load more”; core accepts up to 1000 (`core/index/olvaso.py:572`) | partial | nice | S |
| R10 | Results update live while the vault changes | Only `index` (rebuild) and `pdf_szoveg` events are watched `KeresoAblak.svelte:93-98`; `indexKesz` reruns only after a 503 `vaultKereses.svelte.ts:246-248`. Other panels already debounce `vault_valtozas` (`hasonlo.svelte.ts:84-98`, `hej/kapcsolatok/Elozmenyek.svelte:68`) | missing | should | S |
| R11 | Recent searches shown when the field is empty *(confidence medium)* | missing (last query is kept and re-selected on open: `kereso.ts:17-23`, `KeresoAblak.svelte:240-243`) | missing | nice | S |
| R12 | ↑↓ move through results, ↵ opens *(confidence medium)* | present, plus PageUp/Down, ^N/^P, wrap-around (`KeresoAblak.svelte:169-206`), ⌘↵ new tab, ⌥⌘↵ split (`:198`, `navigacio.nyitasMod`) | present (extra) | — | — |
| R13 | Opening a result selects/flashes the match | Cursor placed at match start only (`szerkesztok.ugras` `szerkesztok.svelte.ts:100-104` → `Szerkeszto.svelte:245-246`, anchor without head); no flash | partial | nice | S |
| R14 | Page preview on hover (Page preview plugin) | missing on result cards; link hover preview exists (`app/src/szerkeszto/linkek/elonezet.ts`) | missing | nice | S–M |
| R15 | Drag a result into the editor to create a link *(confidence medium)* | Alternative: ⌥↵ inserts `[[link]]` at the active editor cursor via core `linkcel` (`KeresoAblak.svelte:132-152`) | present (alt.) | — | — |
| R16 | Right-click result → file menu *(confidence medium)* | missing (cards only handle click `:304-315`); the file tree has the menu items (`hej/Fa.svelte:239-244`) | missing | nice | S |
| R17 | Search lives in the sidebar: results stay visible while opening/editing notes; next result without re-opening | Modal overlay (`lib/ui/Atfedes.svelte`, `Hej.svelte:75-76`) that **closes on open** (`megnyit` → `bezar()` `KeresoAblak.svelte:117`); state survives between openings (`vaultKereses.svelte.ts:1-4`, `:147-149`); the old sidebar view was removed by design (E3: `felulet.svelte.ts:15-16`, `ARCHITECTURE.md:190`, test `app/tests/kereso-ablak.test.ts:434`) | partial | must | M |
| R18 | Clear-search button | `KeresoAblak.svelte:245-249` | present | — | — |
| R19 | ⇧⌘F prefilled with the editor selection | `kereso.ts:9-23` (single-line, ≤ 200 chars) | present | — | — |
| R20 | File explorer: “Search in folder” | `hej/Fa.svelte:236-238` → `path:"…/" ` | present | — | — |
| R21 | Tag pane: click tag → search `tag:#x` | Alternative: the tag pane lists the files itself via `/api/vault/kereses?q=tag:#…` (`hej/Cimkek.svelte:53-56`); no hand-off to the search window | present (alt.) | nice | S |
| R22 | Click `#tag` in editor / reading view → search `tag:#x` | missing: no hashtag decoration or click handler in `app/src/szerkeszto/` (grep `hashtag|cm-cimke` empty); depends on the editor subsystem rendering tags | missing | should | S (+editor) |
| R23 | Bookmark a search (Bookmarks core plugin) | missing (no bookmarks subsystem; grep `bookmark|könyvjelz` empty) | missing | nice | S (+Bookmarks) |
| R24 | Embedded search: ```` ```query ```` code block renders live results in a note | missing (grep `'query'` in `app/src` empty) | missing | should | M |
| R25 | Search is Markdown-content only *(confidence medium)* | Extra: PDF pages (`fts_szakasz` `core/index/kereses.py:423-465`, open at `page=N` `vaultKereses.svelte.ts:118`), VTT subtitles opened at `t=N` on the media file (`:119`, `core/index/olvaso.py:575-589`), canvas/base text and notebook-photo OCR in `fts.tartalom` (`core/index/indexelo.py:752-756`) | extra | — | — |
| R26 | Index-building / not-ready state | 503 → “Az index még épül” and rerun on `index` (`vaultKereses.svelte.ts:230-232`, `:246-248`, `KeresoAblak.svelte:257-258`); PDF extraction progress `:262` | extra | — | — |
| R27 | Debounced typing, stale responses discarded | 250 ms, `AbortController`, sequence numbers `vaultKereses.svelte.ts:186-243` | present | — | — |
| R28 | Accessibility: list navigable by screen reader | `combobox` + `listbox` + `aria-activedescendant` `KeresoAblak.svelte:221-231`, `:297-337`; progressive rendering 30/step, `content-visibility` `:44-45`, `:474-475` | extra | — | — |
| R29 | Hand-off to in-file search | Tab closes the window and opens the CodeMirror panel with the free words (`KeresoAblak.svelte:154-167`) | extra | — | — |

### 1.3 In-note search (⌘F) and replace

| # | Obsidian behaviour | Manifold today (path:line) | Status | Sev. | Eff. |
|---|---|---|---|---|---|
| F1 | ⌘F “Search current file” opens a find bar in the editor | Command `szerkeszto.kereses` Mod+F → `openSearchPanel` (`szerkeszto/index.ts:199-210`); CM `search({ top: true })` + `searchKeymap` (`szerkeszto/beallitas.ts:119-120`; `.cpp` editor `kod/szerkeszto.ts:67-69`) | present | — | — |
| F2 | ↵ next, ⇧↵ previous, Esc closes, all matches highlighted, current emphasised | CM `searchKeymap` (F3/⌘G, ⇧ variants, Esc); styles `szerkeszto/szerkeszto.css:577-583` (`.cm-searchMatch`, `-selected`) | present | — | — |
| F3 | “Search & replace in current file” (separate command; default hotkey Ctrl+H on Win/Linux *(mac default: confidence low)*) with Replace / Replace all | Replace row is part of the same CM panel (labels `MAGYAR_FELIRATOK` `beallitas.ts:49-77`); **no separate command or hotkey** (only `szerkeszto.kereses` in `szerkeszto/index.ts:199-210`) | partial | nice | S |
| F4 | No regex, no case toggle in the in-file search (core) *(confidence medium)* | Extra: CM panel has **regexp**, **match case**, **by word** checkboxes, **select all** (`beallitas.ts:54-57`); ⌘⇧L select-matches, ⌘D next occurrence, ⌥⌘G go-to-line from `searchKeymap` (`szerkeszto/index.ts:187`, `beallitas.ts:120`) | extra | — | — |
| F5 | ⌘F also works in **Reading view** | Command is disabled in reading mode (`elerheto: … mod() !== 'olvaso'` `szerkeszto/index.ts:205`); `Olvaso.svelte` has no find; `ugras` in reading mode only scrolls (`Szerkeszto.svelte:241-244`) | missing | should | M |
| F6 | Match counter “x / y” in the find bar *(confidence low)* | CM default panel has none (`beallitas.ts:119`) | missing | nice | S |
| F7 | Find bar themed, localised | `szerkeszto/szerkeszto.css:513-583`; `EditorState.phrases` `beallitas.ts:118` | present | — | — |
| F8 | Find in the PDF viewer *(Obsidian: confidence medium)* | pdf.js find bus, diacritic-insensitive, highlight all `media/pdf/PdfFul.svelte:102-120` | present | — | — |
| F9 | — | Extra: transcript filter in the media player (`media/Lejatszo.svelte:47`, `:408`) | extra | — | — |
| F10 | Replace-all across the vault — **absent in Obsidian core** | missing in Manifold too (no `/api/vault/csere`; grep `csere` only hits diff/sablon helpers) | missing (both) | nice | L |

### 1.4 Semantic extras (no Obsidian core counterpart — preserve)

| # | Manifold feature | Where | Status |
|---|---|---|---|
| S1 | “Jelentés szerint” hybrid search (FTS bm25 + vector RRF, optional reranker), same query language, instant lexical fallback while models load, background completion and re-poll | `vaultKereses.svelte.ts:163-172`, `:212-226`; `core/kereses_api.py:141-172`; `core/index/hibrid/kereso.py:147-193`; `normal.operatoros` `core/index/hibrid/normal.py:50-56` | extra |
| S2 | Semantic hit opens at the best chunk when there is no literal line (`darab.sor_kezd`) and is labelled “jelentés szerint” | `KeresoAblak.svelte:129`, `:318`; `core/index/hibrid/kereso.py:187-190` | extra |
| S3 | “Kérdezz a vaulttól” (cited, gated answer stream) | `app/src/lib/kereses/kerdezz.svelte.ts`; `core/kereses_api.py:247-264` | extra |
| S4 | “Hasonló jegyzetek” from the vector store without a model | `app/src/lib/kereses/hasonlo.svelte.ts`; `core/kereses_api.py:266-269` | extra |
| S5 | Polish gap of S1: for natural-language queries the lexical branch returns files **without line hits** (`talalatok: []` `core/index/hibrid/kereso.py:143`), so cards show no snippet/count unless a vector chunk exists; no `kornyezet` either | — | partial (nice, M) |

---

## 2. Gaps and proposals

All proposals stay inside the existing architecture: the single lexical parser/evaluator in `core/index/kereses.py`
(`_lex` → `_Parser` → `_fts` prefilter → `_kiertekel`), the route `GET /api/vault/kereses` (`core/index/api.py:26` →
`Index.kereses` `core/index/olvaso.py:570-573`), the hybrid wrapper (`core/kereses_api.py:241-245`,
`core/index/hibrid/kereso.py`), the client state `VaultKereses` (`app/src/lib/kereses/vaultKereses.svelte.ts`) and the
window `KeresoAblak.svelte`. New operators must also be added to `OPERATOROK` (`kereses.py:38`), to `_van`
(`:334-343`), to `normal.OPERATOR_MINTA` (`core/index/hibrid/normal.py:50`) so the hybrid branch treats them as
operator queries, to `keresoSzavak` (`app/src/lib/kereses/kereso.ts:35-36`) so they are not highlighted, and to the
cheat-sheet (`KeresoAblak.svelte:284-294`).

### 08-search-01 — Docked, persistent results pane (R17) — must, M
**Obsidian:** the search pane sits in the left sidebar; opening a result keeps the list, the user walks the hits across
files.
**Manifold:** modal overlay that closes on ↵/click (`KeresoAblak.svelte:117`), veiling the editor; the state survives, so
⇧⌘F re-opens the same list (`vaultKereses.svelte.ts:147-149`), but every hop costs a re-open.
**Proposal:** (1) Extract the results list (cards, keyboard model, `kiemelt` snippet, `megnyit`/`linkBeszur`) from
`KeresoAblak.svelte:55-210, 297-346` into `app/src/lib/kereses/KeresoLista.svelte` driven by the shared `vaultKereses`
state. (2) Re-add `'kereses'` to `OldalsavNezet` (`app/src/lib/elrendezes/felulet.svelte.ts:16`; the loader already
maps the legacy value to `fajlok`, `app/tests/kereso-ablak.test.ts:434`) and render `KeresoLista` as a third sidebar tab in
`hej/Oldalsav.svelte` (same tab mechanics as `cimkek`, `Oldalsav.svelte:46-92`), with the field, the status line and the
“Jelentés szerint” toggle. (3) Keep the overlay as the fast keyboard entry (⇧⌘F) and add a “Dokkolás” footer action
(`KeresoAblak.svelte:350-359`) plus a command `kereses.oldalsav` (`alapParancsok.ts:46-53`) so both views exist; the
docked pane never closes on open. (4) In the docked view ↵ opens in the active tab without stealing the list; ⌘↵/⌥⌘↵ as
today. No core change.

### 08-search-02 — Property search `[key]`, `[key:value]` (Q16) — should, M
**Proposal:** core: in `_lex` (`core/index/kereses.py:58-92`) tokenise `[` … `]` into `("tul", kulcs, ertek|None)`
(quoted values allowed, as in the graph grammar `app/src/lib/graf/lekerdezes.ts:7`); in `_keres` load
`tulajdonsag(fajl_id, kulcs, ertek)` (`core/index/tar.py:38-41`) into a per-file dict when `_van(e, "tul")` (same pattern as
tags `:391-393`); in `_kiertekel` match key case-insensitively, value as folded substring (`hajt`), list/tags values by
element; `_fts` returns `None` for it (`:223-237`) so the prefilter only uses the free words. Client: add `[kulcs:érték]` to
the cheat-sheet and exclude `[`…`]` tokens from `keresoSzavak` (`kereso.ts:29-43`). Reuse the graph's grammar tests as
fixtures so the two parsers agree (open question 4).

### 08-search-03 — `match-case:` / `ignore-case:` and a Match-case toggle (Q14) — should, S–M
**Proposal:** core: add `match-case`, `ignore-case` to `OPERATOROK` (`kereses.py:38`); parser: like `line:` they take a
parenthesised sub-expression or a single value (`:144-148`); evaluation: carry a `kisnagy` flag down `_kiertekel`
(`:281-331`): under `match-case` compile `_szo_minta` on the raw term and run it on `d.tartalom` instead of `d.hajtott`
(`:286-287`), keep accent folding off too (Obsidian's match-case is byte-exact); under `ignore-case` the current path. The
FTS prefilter is unaffected (it is already a superset). Client: a `Aa` toggle button in the field row
(`KeresoAblak.svelte:219-274`, next to “Jelentés szerint”) that wraps the whole query as `match-case:( … )` at request time
(`vaultKereses.keres` `:204-214`), persisted in `felulet.kereso` (`felulet.svelte.ts:34,59`).

### 08-search-04 — Sort order (R7) — should, S
**Proposal:** client-only. Add `rendezes` to `VaultKereses` (`vaultKereses.svelte.ts:147-166`) with values
`relevancia` (today, keep as default — Manifold's advantage), `nev`, `nev-forditott`, `modositva`, `modositva-regi`; sort
`talalatok` in a `$derived` in `KeresoAblak.svelte:59-60` using `fajlNev` and `fajlok.info(ut).mtime`
(`app/src/lib/vault/fajlok.svelte.ts:10-15`). Created time is not in `FajlInfo`; add `ctime` to `/api/vault/fa` only if
wanted (open question). UI: a small `<select>` in the field row; persist in `felulet.kereso`.

### 08-search-05 — “Show more context” (R3) — should, S
**Proposal:** the data is already fetched (`kornyezet=1`, `vaultKereses.svelte.ts:214`; `elotte/utana`
`core/index/kereses.py:359-362`). Add a persisted `felulet.kereso.kornyezet` toggle (footer `⌘⇧G`), and in the snippet
row (`KeresoAblak.svelte:323-341`) render `h.elotte`/`h.utana` as dimmed lines above/below the hit when on (keep the
one-line form when off). Pass `kornyezet` through the hybrid endpoint: read `k.egesz("kornyezet", 0, 0, 5)` in
`core/kereses_api.py:241-245` and forward it to `HibridKereso.keres` → `kereses.keres(c, q, …, kornyezet)`
(`core/index/hibrid/kereso.py:127,133,156`). Request `kornyezet=2` when the toggle is on.

### 08-search-06 — Live refresh of results (R10) — should, S
**Proposal:** in `KeresoAblak.svelte:93-98` (and the docked pane) subscribe to `vault_valtozas` with a 1 s debounce
exactly like `hasonlo.svelte.ts:84-98`, and call `allapot.keres()` when `allapot.q` is non-empty; keep `aktiv` by element
key (`sorszamok` map `:78`) so the selection does not jump to the top (`$effect.pre` at `:81-85` resets it today — guard it
with a “same query” check).

### 08-search-07 — `task:`, `task-todo:`, `task-done:` (Q12) — should, M
**Proposal:** core: add the three to `OPERATOROK`; evaluation like `line:` (`kereses.py:323-330`) but iterating the
file's task lines from the `feladat` table (`core/index/tar.py:66-68`: `sor`, `allapot`, `szoveg`), filtered by `allapot`
for `-todo`/`-done`; spans offset to the task line (`_Sorok` from `elemzo.py:161-169`). Load tasks per file lazily in `_Dok`
(`:242-266`) only when `_van(e, "task…")`. Media sections (`_media`) ignore it. Client: cheat-sheet + `keresoSzavak`.

### 08-search-08 — `section:(…)` (Q10) — should, M
**Proposal:** core: evaluate on heading sections. Build section ranges from `fejezet(fajl_id, szint, sor)`
(`core/index/tar.py:45-46`, load per file like tags) — a section runs from its heading line to the next heading of the same
or higher level (Obsidian semantics); the pre-heading text is its own section. Evaluate the sub-expression on each
section's text with `d.sor(szoveg)` (`:264-266`), offsetting spans by the section's start. Alternative without the table:
split `d.tartalom` on `^#{1,6} ` lines with `maszk.link_maszk` applied (code fences excluded), reusing
`core/index/hibrid/darabolas.py`'s heading logic.

### 08-search-09 — `block:(…)` (Q11) — nice, S
**Proposal:** same shape as `line:` but the unit is a paragraph: split `d.tartalom` on blank lines (code fences kept
whole, as in `darabolas.py`), evaluate per block, offset spans. No index change.

### 08-search-10 — `content:` (Q13) — nice, S
**Proposal:** add `content` to `OPERATOROK`; in `_kiertekel` evaluate the sub-expression with the name/path fallback
disabled, i.e. on `d.sor(d.tartalom)` (`kereses.py:264-266` already builds a nameless `_Dok`) — spans unchanged.

### 08-search-11 — Substring matching for bare words (Q1) — should, M–L, confidence medium
**Obsidian:** bare terms match anywhere in the word. **Manifold:** word-start only (`kereses.py:3-4`, `:271`), a
deliberate choice that keeps the FTS prefix index effective (`prefix='2 3'` `core/index/tar.py:75-76`). Hungarian
compounds (“lakóház”) make the difference noticeable.
**Proposal (least invasive):** keep prefix matching as the default (it is faster and the cheat-sheet documents it) and add
an explicit infix form `*szó` (Obsidian has no wildcard, so this is additive): the lexer marks the term, `_fts` returns
`None` for it (full candidate scan, bounded by `MAX_JELOLT`/`hatar` `:395-400`), `_szo_minta` drops the `(?<!\w)`
lookbehind. If the product decides on Obsidian semantics by default (open question 2), the robust path is a second FTS5
table with `tokenize='trigram'` for the prefilter (migration in `core/index/tar.py`), which is the L estimate.

### 08-search-12 — Find in Reading view (F5) — should, M
**Proposal:** enable `szerkeszto.kereses` in reading mode (`szerkeszto/index.ts:205`) and implement a reader find bar in
`Olvaso.svelte` (same look as `.cm-search`, `szerkeszto.css:526-575`): walk text nodes of the rendered article, wrap
matches in `<mark class="olvaso-talalat">`, ↵/⇧↵ step with `scrollIntoView`, Esc clears. Accent/case folding with
`gyuru`/`szoKiemeles` from `kereso.ts:46-75`. Alternative with less code: on ⌘F switch the tab to source/live mode and open
the CM panel, switching back on close — acceptable interim.

### 08-search-13 — Embedded search block (R24) — should, M
**Proposal:** register a `query` code-block renderer in `app/src/szerkeszto/renderelok/` (reading view) and a widget in
`szerkeszto/elo/` (live preview, like other block widgets) that calls `/api/vault/kereses?q=…&limit=50&kornyezet=1` with
the same debounce/abort pattern as `VaultKereses` and renders `KeresoLista` (08-search-01) in compact mode; refresh on
`vault_valtozas` (08-search-06). Links in results use `linkek.linkCel` as ⌥↵ does. The block must stay plain Markdown
(no vault write).

### 08-search-14 — Explain search term (R5) — nice, S
**Proposal:** core: `magyaraz(e)` in `kereses.py` walking the AST from `elemez` (`:199-206`) into a sentence (“fájlok,
amelyek tartalmazzák „a”-t ÉS a címkéjük #x …”); return it as `magyarazat` when `?magyaraz=1` (route `core/index/api.py:26`).
Client: a toggle in the footer, text under the field (`KeresoAblak.svelte:276-278` area). Also useful to show *why* the
hybrid branch fell back (`ok` codes `core/index/hibrid/kereso.py:108-120`).

### 08-search-15 — Copy search results (R6) — nice, S
**Proposal:** client-only. Footer action “Találatok másolása” (`KeresoAblak.svelte:350-359`) opening a small options
row (link style: `[[wiki]]` / `[md](…)` / plain path; include snippets; include folder) and writing a Markdown list to the
clipboard (`navigator.clipboard`, helpers in `szerkeszto/vagolap.ts`); link targets from `linkek.linkCel`
(`KeresoAblak.svelte:141`) relative to the active note. Works on `allapot.eredmeny.talalatok` (all, not only the rendered 30).

### 08-search-16 — Per-file collapse (R4) — nice, S
**Proposal:** a `Set<string>` of collapsed paths in `VaultKereses`; a chevron on the card header
(`KeresoAblak.svelte:304-320`) and ←/→ on the active header (`billentyu` `:187-206`); `elemek` (`:70-77`) skips snippet
rows of collapsed cards so keyboard order stays correct. ⌘G remains the global toggle.

### 08-search-17 — Search history (R11) — nice, S, confidence medium
**Proposal:** persist the last 20 non-empty queries in `felulet.kereso.elozmenyek` (`FeluletMentes.kereso`
`felulet.svelte.ts:33-34`, loader `:129`, saver `:226`); when the field is empty show them above the cheat-sheet
(`KeresoAblak.svelte:281-295`) as `option`s navigable with ↓, ↵ runs, ⌘⌫ removes.

### 08-search-18 — Saved searches / bookmark a search (R23) — nice, S (+Bookmarks)
**Proposal:** until a Bookmarks subsystem exists, add “pinned” queries to the history store (08-search-17:
`felulet.kereso.mentett`) with a star in the history list and a palette command “Mentett keresés…” that opens the window
prefilled (`keresoMegnyit(f, q)` `kereso.ts:19-23`). When Bookmarks arrive, store `{tipus: 'kereses', q}` there instead.

### 08-search-19 — Select/flash the match after jumping (R13) — nice, S
**Proposal:** extend `ugras(sor, oszlop, hossz?)` (`szerkesztok.svelte.ts:23,100-104`; `Szerkeszto.svelte:237-248`) to
dispatch `selection: {anchor, head: anchor + hossz}` and add a short `--jeloles-hatter` flash decoration; the length is
available (`SorTalalat.jelek[0].hossz`, `vaultKereses.svelte.ts:60`; `KeresoAblak.svelte:128`). Convert `hossz` with
`utf16Oszlop` (`:143-145`) like the column.

### 08-search-20 — Hover page preview on results (R14) — nice, S–M
**Proposal:** reuse the link hover preview (`app/src/szerkeszto/linkek/elonezet.ts`) on the card header
(`KeresoAblak.svelte:304-315`) with ⌘-hover (Obsidian's default), anchored at the hit line (`elso.sor`).

### 08-search-21 — Result context menu (R16) — nice, S
**Proposal:** `oncontextmenu` on the card header → the existing `helyiMenu` list with “Megnyitás”, “új fülben”,
“osztásban”, “Átnevezés…”, “Keresés ebben a mappában” taken from `hej/Fa.svelte:239-244` (factor the file items into a
shared helper in `lib/vault/`).

### 08-search-22 — True per-file match count (R1) — nice, S
**Proposal:** core: in `_keres` (`kereses.py:406-407`) add `"egyezes": len(set(spanok))` independent of the `MAX_SOR`
line cap; `_media` likewise (`:445-453`). Client: `egyezes()` (`KeresoAblak.svelte:114`) reads it and “+N további sor” uses
`sorok.length` vs. the true count.

### 08-search-23 — More than 200 files (R9) — nice, S
**Proposal:** keep `KERESES_LIMIT = 200` (`vaultKereses.svelte.ts:137`) for the first page; when `cap` is true
(`KeresoAblak.svelte:101`) show “További találatok” at the list end (and on reaching the end with ↓) that re-requests with
`limit` doubled up to the core maximum 1000 (`core/index/olvaso.py:572`). The hybrid endpoint clamps the same way
(`core/kereses_api.py:243`).

### 08-search-24 — Click `#tag` → search (R22) — should, S (search side)
**Proposal:** once the editor/reader render hashtags (editor subsystem), the handler is one line:
`keresoMegnyit(felulet, \`tag:#${cimke} \`)` (`kereso.ts:19-23`), mirroring the folder menu (`Fa.svelte:236-238`). Add a
command `kereses.cimke` taking the tag under the cursor.

### 08-search-25 — Tag pane → open in the search window (R21) — nice, S
**Proposal:** in `hej/Cimkek.svelte` add a header icon/context item on the selected tag calling
`keresoMegnyit(felulet, \`tag:#${kis} \`)`, so the full query language (and the hybrid mode) is one click away from the
tag list.

### 08-search-26 — Separate “Csere a jegyzetben” command (F3) — nice, S
**Proposal:** command `szerkeszto.csere` in `szerkeszto/index.ts:199-210` style: `openSearchPanel(v)` then focus the
panel's `[name="replace"]` field; hotkey ⌥⌘F (⌘H hides the app on macOS; Obsidian's mac default is uncertain). Also add
“Csere…” to the editor's context menu (`szerkeszto/helyiMenu.ts`).

### 08-search-27 — Match counter in the find bar (F6) — nice, S, confidence low
**Proposal:** a small CM extension next to `search({ top: true })` (`beallitas.ts:119`): on `SearchQuery` change
(`getSearchQuery(state)`), count `query.getCursor(doc)` iterations (cap 10 000) and the index of the match containing the
selection; render “n / N” into the panel via a `ViewPlugin` that appends a span to `.cm-search`. Same for `kod/szerkeszto.ts`.

### 08-search-28 — Regex case-insensitive by default (Q15) — nice, S, confidence medium
**Proposal:** compile with `regex.M | regex.I` in `_Rx` (`kereses.py:174`) unless the term is inside `match-case:`
(08-search-03); document in the cheat-sheet. Behaviour change — see open question 3; if rejected, keep sensitive and let
`ignore-case:(/…/)` switch it.

### 08-search-29 — Snippets and context for natural-language semantic queries (S5) — nice, M (Manifold polish)
**Proposal:** in `HibridKereso.keres` after fusion (`core/index/hibrid/kereso.py:182-191`), for the `limit` returned
notes compute line hits for the free words with the lexical evaluator (`kereses._kiertekel` on a `_Dok` per note, the
`szabad` string parsed as an `es` of `szo` terms) and `_sorok(..., kornyezet)`; today `_lexikai` leaves `talalatok: []`
for the OR-query branch (`:143`). This gives the “N egyezés” badge and snippets in “Jelentés szerint” mode and makes
08-search-05 work there too.

### 08-search-30 — Replace across the vault (F10) — nice, L (absent in Obsidian core; opportunity)
**Proposal (if wanted):** `POST /api/vault/csere {q, csere, utak?, proba: true|false}` in `core/index/api.py` next to
`feloldas` (`:44-45`): run `kereses.keres` with the regex/word spans (`kereses.py:402`), build per-file replacement
previews, and on `proba: false` write each file through `vaultio.write` (atomic, git snapshot — `ARCHITECTURE.md:57`) in
one undoable operation. Client: a “Csere…” footer action in the window with a preview list (reuse `KeresoLista`) and a
confirm step. Not required for parity.

### 08-search-31 — One-character queries (Q19) — nice, S
**Proposal:** keep `MIN_HOSSZ = 2` for bare words (T152 cost) but let `file:x`, `path:x`, `tag:x` and quoted one-char
phrases through: in `utemez` (`vaultKereses.svelte.ts:189-200`) measure the free-word length from `keresoSzavak(q)`
instead of the raw query.

---

## 3. Manifold strengths beyond Obsidian (preserve)

1. **Semantic layer** — “Jelentés szerint” hybrid search with instant lexical fallback and background completion
   (`vaultKereses.svelte.ts:163-172, 212-226`; `core/kereses_api.py:141-172`; `core/index/hibrid/kereso.py:147-193`),
   “Kérdezz a vaulttól” and “Hasonló jegyzetek” (`kerdezz.svelte.ts`, `hasonlo.svelte.ts`). The operator query language
   also filters the semantic branch (`kereso.py:124-130`), so `tag:`/`path:` work in semantic mode.
2. **Media and non-Markdown content is searchable** — PDF pages open at `page=N`, VTT subtitles open the video at the
   second (`vaultKereses.svelte.ts:117-121`, `KeresoAblak.svelte:119-125`, `core/index/kereses.py:423-465`,
   `core/index/olvaso.py:575-589`), notebook-photo OCR, canvas and base text (`core/index/indexelo.py:752-756`), with
   extraction progress in the status line (`KeresoAblak.svelte:262`).
3. **Relevance ranking** — bm25 with field weights (path 2, name 10, content 1) `core/index/kereses.py:385-387`, media
   weighted `MEDIA_SULY` `:40`, time-budgeted scan with an honest “legalább N” lower bound (`:395-400`,
   `KeresoAblak.svelte:266`). Obsidian only offers name/date sorts.
4. **Query diagnostics** — 400 with a precise message for unbalanced parentheses, bad regex and regex timeouts
   (`kereses.py:141, 176, 206, 376`), shown in `role="alert"` (`KeresoAblak.svelte:276-278`); regex runs with a 2 s
   budget, `concurrent=True` and the `regex` package's timeout (`:168-192`), so catastrophic patterns cannot stall the core.
5. **Operator extras** — `path:/regex/`, `file:/regex/`, `tag:/regex/` (`kereses.py:7, 275-278, 319-320`).
6. **Accent- and case-insensitive, length-preserving folding** (`hajt` `kereses.py:44-53`; `gyuru` `kereso.ts:46-51`)
   so highlights land on the original text; name and folder path highlighted too (`KeresoAblak.svelte:317, 321`).
7. **Keyboard-first result window** — ↑↓/PageUp/PageDown/^N/^P, ↵, ⌘↵ new tab, ⌥⌘↵ split, ⌥↵ insert link to the hit
   (core-resolved `linkcel`), Tab hand-off to in-file search, ⌘G collapse (`KeresoAblak.svelte:132-206`), selection
   prefill (`kereso.ts:9-23`), folder prefill (`Fa.svelte:236-238`).
8. **Accessibility and performance** — `combobox`/`listbox`/`aria-activedescendant` (`KeresoAblak.svelte:221-231,
   297-337`), progressive rendering and `content-visibility` (`:44-45, 474-475`), 250 ms debounce with request abort
   and stale-response discard (`vaultKereses.svelte.ts:186-243`), index-building and core-down states (`:230-235`).
9. **In-note find/replace** — the CM panel offers regex, match case, whole word, select-all, replace/replace-all,
   go-to-line, ⌘⇧L select matches and ⌘D next occurrence (`beallitas.ts:49-77, 119-120`; `szerkeszto/index.ts:187`),
   themed and localised (`szerkeszto.css:513-583`). Obsidian core has none of regex/case/word toggles.
10. **Find in PDF and transcript filter** (`media/pdf/PdfFul.svelte:102-120`; `media/Lejatszo.svelte:47, 408`).
11. **Tag pane as a live `tag:` search** (`hej/Cimkek.svelte:53-56`) sharing the same endpoint and semantics.

---

## 4. Open questions

1. **Docked pane vs. overlay (08-search-01).** E3 deliberately removed the sidebar search tab
   (`felulet.svelte.ts:15-16`, `ARCHITECTURE.md:190`). Is re-adding a docked results view acceptable, or should the overlay
   get a non-modal “stay open” mode instead (less work, but the veil still hides the editor)?
2. **Prefix vs. substring (08-search-11).** Keep word-start matching as the default (fast, documented) and add an explicit
   infix form, or adopt Obsidian's substring default with a trigram FTS table? Hungarian compound words argue for at least
   the opt-in.
3. **Regex case sensitivity (08-search-28).** Switching `/…/` to case-insensitive by default changes existing behaviour
   (`kereses.py:10, 174`). Acceptable, or only via `ignore-case:`?
4. **One grammar, two parsers.** The graph filter (`app/src/lib/graf/lekerdezes.ts`) already parses `[key:value]` in
   TypeScript, the vault search parses in Python. When adding properties/`task:`/`section:` to the core, should the graph
   filter call the core (`/api/vault/kereses` returns paths) instead of keeping its own parser, or share a test fixture?
5. **Created time for sorting (08-search-04).** `FajlInfo` has `mtime` only (`fajlok.svelte.ts:10-15`); is adding
   `ctime` to `/api/vault/fa` worth it for Obsidian's two “created” sorts?
6. **Bookmarks subsystem.** Saved searches (08-search-18) are a Bookmarks feature in Obsidian; which parity report owns
   Bookmarks, and should search pins wait for it?
7. **Replace across the vault (08-search-30).** Not in Obsidian core — product decision whether Manifold wants it (it fits
   the atomic write + git snapshot model).
8. **Hybrid context (08-search-05/29).** Should the hybrid endpoint gain `kornyezet` and line hits for NL queries now, or
   only when the semantic mode graduates (M12 measurement, `core/index/hibrid/kereso.py:37-38`)?
9. **Uncertain Obsidian details to verify before scheduling:** in-file match counter (F6), mac default hotkey for
   search-and-replace (F3), exact “Copy search results” options (R6), substring semantics (Q1) and regex case default (Q15),
   search-history UI (R11), sort-order list (R7).
