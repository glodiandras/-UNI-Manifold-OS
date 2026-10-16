# 03 – Properties (frontmatter) and tags — Obsidian parity audit

Subsystem: **Properties (frontmatter) and tags**. Reference: Obsidian 1.8/1.9 desktop, core features and core plugins only (Properties view, Tag pane, Quick switcher, Search). Read-only audit of `/Volumes/Work/[UNI] Manifold-OS`; every claim is cited as `path:line` relative to that root. Developer references: `docs/dev/ARCHITECTURE.md:226-251` (C11b endpoints), `docs/dev/DESIGN.md:226-234` (section 15, tokens), `docs/plan/audit/03-felulet.md:54,81,231,273` (UI map).

Product goal: the Manifold editor must compete with Obsidian, and nothing Manifold already does may be lost. Severity: **must** = daily-use Obsidian behaviour users miss immediately; **should** = noticeable; **nice** = polish. Effort: S (< 1 day), M (1–3 days), L (> 3 days). Confidence marks how sure the Obsidian side of the comparison is (`low` = not certain Obsidian behaves exactly so).

Files read: `app/src/szerkeszto/tulajdonsagok/*` (14 files), `core/tulajdonsagok.py`, `core/index/elemzo.py`, `app/src/hej/Cimkek.svelte`, `app/src/lib/vault/cimkek.svelte.ts`, plus what they touch: `core/index/olvaso.py`, `core/index/indexelo.py`, `core/index/kereses.py`, `core/index/tar.py`, `app/src/szerkeszto/beallitas.ts`, `Szerkeszto.svelte`, `olvaso/html.ts`, `elo/sorok.ts`, `markdown/elemzo.ts`, `markdown/wikilink.ts`, `linkek/kiegeszites.ts`, `linkek/szerkeszto.ts`, `atfedes/Valto.svelte`, `lib/vault/linkek.svelte.ts`, `lib/vault/fajlok.svelte.ts`, `lib/kereses/vaultKereses.svelte.ts`, `alapParancsok.ts`, `hej/Oldalsav.svelte`, `hej/JobbPanel.svelte`, `config/vault-sema.json`.

---

## 0. Executive summary

The **properties editor itself is at parity or ahead** of Obsidian: a block widget replaces the YAML in Live Preview (`app/src/szerkeszto/tulajdonsagok/elo.svelte.ts:72-81`), the same panel is mounted in reading view (`app/src/szerkeszto/Szerkeszto.svelte:364-373`), all Obsidian value types except `cssclasses` are typed and rendered (`core/index/elemzo.py:44,174-191`; `Tulajdonsagok.svelte:97-108`), values and keys are suggested with usage counts (`core/tulajdonsagok.py:581-629`), invalid YAML degrades to an inline raw editor with the error (`EloTulajdonsagok.svelte:14-23`), and writes are byte-faithful line replacements proven by a read-back (`core/tulajdonsagok.py:8-11,527-541`). On top of that Manifold has a vault schema with confirmation flow, raw-YAML autocompletion in the editor, link-typed fields, `icon`/`cover`, and template merging — none of which Obsidian core has (section 3).

The **tag side is where Obsidian users will stumble on day one**. Body `#tags` are indexed (`core/index/elemzo.py:33,363-366`) and searchable (`core/index/kereses.py:318-322`), but in the editor they are **not parsed, not styled, not clickable and not autocompleted**: the Lezer extension list has no hashtag node (`app/src/szerkeszto/markdown/elemzo.ts:18-28`), the Live Preview decoration map has none (`app/src/szerkeszto/elo/sorok.ts:25-37`), the reading renderer has none (`app/src/szerkeszto/olvaso/html.ts:599-600` handles `Frontmatter` only). The **quick switcher ignores aliases** (`app/src/atfedes/Valto.svelte:20-47` searches `fajlok.kereso()` = file names only, `app/src/lib/vault/fajlok.svelte.ts:64-66`) even though the alias data and a working alias-aware fuzzy index already exist for `[[` completion (`app/src/szerkeszto/linkek/kiegeszites.ts:96-101`). **Per-key property types** are read from `.obsidian/types.json` and live-watched (`core/index/elemzo.py:444-452`, `core/index/indexelo.py:394-412`) but never written and there is no type menu, so the same key can render as a date in one note and text in another (`core/index/elemzo.py:245-246`).

Counts: 4 must, 9 should, 11 nice (24 gaps); 20 strengths to preserve; 10 open questions.

---

## 1. Checklist

Status: **present** / **partial** / **missing** / **n/a** (Obsidian does not have it either).

| # | Obsidian 1.8/1.9 behaviour | Manifold today (path:line) | Status | Sev. | Eff. | Gap |
|---|---|---|---|---|---|---|
| 1 | Properties editor replaces the YAML block at the top of the note in Live Preview; raw YAML stays in Source mode | Block widget replaces `---…---` in LP (`app/src/szerkeszto/tulajdonsagok/elo.svelte.ts:72-81`, `fm.ts:16-33`); only the LP extension set loads it (`app/src/szerkeszto/beallitas.ts:83-88`); Source mode keeps raw YAML (`beallitas.ts:87-88`, `elo.svelte.ts:1-2`) | present | – | – | – |
| 2 | Properties editor also shown (and editable) in Reading view | Same `Tulajdonsagok` mounted above the reader in `olvaso` mode (`app/src/szerkeszto/Szerkeszto.svelte:364-373`); the reader additionally renders a collapsed raw-YAML `<details>` (`app/src/szerkeszto/olvaso/html.ts:552-567`) | present (verify no duplicate box) | nice | S | 03-properties-18 |
| 3 | Cursor cannot land inside the hidden YAML; typing goes to the body | `kurzorOr` transaction filter moves empty cursors before the body start (`elo.svelte.ts:111-119`, `eloKurzorIgazit` `:122-125`) | present | – | – | – |
| 4 | Type **text** (single-line input, "Empty" placeholder) | `JavaslatMezo` text field, placeholder "Üres" (`Tulajdonsagok.svelte:391-403`) | present | – | – | – |
| 5 | Type **list** (pills; Enter/comma adds, Backspace removes last) | `ListaMezo` chips, Enter/`,` add, Backspace removes last (`ListaMezo.svelte:37-64`); `multitext` type (`core/index/elemzo.py:44,183-184`) | present | – | – | – |
| 6 | Type **number** | Text input `inputmode=decimal` with validation message (`Tulajdonsagok.svelte:378-389,126-132`; `ertek.ts:63-69`); core validates (`core/tulajdonsagok.py:242-252`) | present | – | – | – |
| 7 | Type **checkbox** | Native checkbox (`Tulajdonsagok.svelte:330-331`) | present | – | – | – |
| 8 | Type **date** / **datetime** (native pickers, `YYYY-MM-DD`, `YYYY-MM-DDTHH:mm`) | `type=date` / `datetime-local` (`Tulajdonsagok.svelte:332-340`, `ertek.ts:55-60`); calendar validity checked (`core/tulajdonsagok.py:49-64,253-262`) | present | – | – | – |
| 9 | Type **tags** (pills, `#` stripped, suggestions from vault tags, pill click → search) | Chips with vault-tag + schema suggestions (`Tulajdonsagok.svelte:356-365`; `core/tulajdonsagok.py:615-617`); `#` stripped on write (`core/tulajdonsagok.py:233-234`) and read (`core/index/elemzo.py:354-358`). **Chips are not clickable** (only wikilink chips get `onnyit`, `ListaMezo.svelte:70-75`) | partial | should | S | 03-properties-08 |
| 10 | Type **aliases** (list; used by quick switcher and `[[` completion) | Typed `aliases` (`core/index/elemzo.py:43,177-178,359-361`), chips (`Tulajdonsagok.svelte:104,112`). New-property form offers no "Aliasok" type and the key does not pre-select list (`Tulajdonsagok.svelte:175-183,202-208`) | partial | nice | S | 03-properties-19 |
| 11 | Type **cssclasses** (list; classes applied to the note view) | No reader, no type, no application (`core/index/elemzo.py:42-44` knows only tags/aliases) | missing | nice | S | 03-properties-10 |
| 12 | Per-key type stored in `.obsidian/types.json`; "Property type" menu on the key icon changes it vault-wide; new keys get their inferred type written | Reads `types.json` (`core/index/elemzo.py:444-452`), applies it (`:245-246`), re-types on file change (`core/index/indexelo.py:394-412,491-503`), surfaces it in key suggestions (`core/tulajdonsagok.py:589-597`). **Never written; no menu**; per-note inference otherwise | partial | must | M | 03-properties-05 |
| 13 | Type icon next to each key; right-click/menu: type, cut/copy, remove | Key is a plain label (`Tulajdonsagok.svelte:327`); only a trash button (`:407-411`) | missing | should | S | 03-properties-06 |
| 14 | Value suggestions while typing (values already used for the key; tags; links for `[[`) | `GET /api/vault/tulajdonsagok/ertekek` with counts and schema markers (`core/tulajdonsagok.py:601-629`; `javaslat.ts:66-92`); link fields get file suggestions (`javaslat.ts:180-249`). `[[` inside an *arbitrary* text field does not switch to file suggestions in the panel (`javaslat.ts:51-53`; raw YAML does: `fmKiegeszites.ts:168`) | present (+) | nice | S | 03-properties-21 |
| 15 | Key suggestions when adding a property | `GET /api/vault/tulajdonsagok/kulcsok` (`core/tulajdonsagok.py:581-599`; `Tulajdonsagok.svelte:193-199`) | present (+) | – | – | – |
| 16 | Add property ("Add property" button, command "Add file property") | "Új tulajdonság" form with name/type/value (`Tulajdonsagok.svelte:305-309,417-445`); creates the block when absent (`core/tulajdonsagok.py:708-710,552-553`). Only a show/hide command exists (`app/src/alapParancsok.ts:65-72`) | present / partial | nice | S | 03-properties-23 |
| 17 | Remove property | Trash button → `torol` (`Tulajdonsagok.svelte:119-121,407-411`; `core/tulajdonsagok.py:713-715`) | present | – | – | – |
| 18 | Rename a key in place (click the key name) | Not possible; `modosit` knows only `beallit`/`torol` (`core/tulajdonsagok.py:495-496`) | missing | should | M | 03-properties-07 |
| 19 | Reorder properties by drag | Not in Obsidian's UI either (order = YAML order) — **confidence low**. Manifold inserts new keys at the schema position (`core/tulajdonsagok.py:722-732`) | n/a | – | – | – |
| 20 | Source mode: raw YAML editing with highlighting | Raw YAML, `FrontmatterContent` highlighted (`app/src/szerkeszto/markdown/frontmatter.ts:14-15`), **plus** key/value/link autocompletion (`fmKiegeszites.ts:77-111,143-207`) — Obsidian has no YAML completion (confidence medium) | present (+) | – | – | – |
| 21 | Invalid YAML: properties UI gives way to the raw block with an error | Core reports `hiba` (`core/index/elemzo.py:232-241`; `core/tulajdonsagok.py:379-381`); LP shows error + editable raw YAML, widget restores on fix (`EloTulajdonsagok.svelte:14-23`, `elo.svelte.ts:76-80`); duplicate keys are an error (`core/index/elemzo.py:85-102`, `core/tulajdonsagok.py:314-316`) | present | – | – | – |
| 22 | "Properties in document" setting: Visible / Hidden / Source; nothing shown when the note has no frontmatter | Persisted collapse only (`app/src/lib/elrendezes/felulet.svelte.ts:58,128`; command `alapParancsok.ts:65-72`); an always-present header, "no frontmatter" row when absent (`Tulajdonsagok.svelte:320-322`) | partial | nice | S | 03-properties-17 |
| 23 | Properties view core plugin: "Properties" (current file) and "All properties" (every key, count, type; click → search) sidebar views | None; sidebar has Files/Tags only (`app/src/hej/Oldalsav.svelte:37-40`), right panel has backlinks/mentions/outgoing/outline/history (`app/src/hej/JobbPanel.svelte:173-185`). Backend already lists keys with counts and types (`core/tulajdonsagok.py:581-599`) | missing | should | M | 03-properties-09 |
| 24 | Search operators `[key]`, `[key:value]` | Search knows `path`, `file`, `tag`, `line` only (`core/index/kereses.py:38,316-322`) | missing | should | M | 03-properties-16 |
| 25 | Frontmatter `[[links]]` count for graph/backlinks and are clickable in the editor | Links in the block carry their key (`core/index/elemzo.py:129,341-351`); link chips open the target (`Tulajdonsagok.svelte:168-171,366-375`) | present | – | – | – |
| 26 | Tags pane (core plugin): nested `a/b` tree | Flat list → tree with ancestors synthesised (`core/index/olvaso.py:350-370`; `app/src/lib/vault/cimkek.svelte.ts:26-49`) | present | – | – | – |
| 27 | Tags pane: counts (occurrences, children included for parents) | `db` = notes with exactly the tag, `ossz` = notes incl. children (`core/index/olvaso.py:351-352,367-369`); `ossz` shown, tooltip with both (`Cimkek.svelte:172`). Semantics differ (notes vs occurrences) — **confidence medium** | present (different) | nice | S | 03-properties-15 |
| 28 | Tags pane: sort menu (name A→Z/Z→A, count ↑/↓) | Fixed name sort (`cimkek.svelte.ts:27`) | missing | should | S | 03-properties-11 |
| 29 | Tags pane: collapse all / expand all; expansion state remembered; "Show nested tags" toggle | Expansion is component-local (`Cimkek.svelte:21`); no buttons | missing | nice | S | 03-properties-12 |
| 30 | Tags pane: filter/search box | None — **confidence low** that Obsidian core has one | missing | nice | S | 03-properties-13 |
| 31 | Tags pane: click → Search pane with `tag:#x` | Click → inline note list under the tree via `/api/vault/kereses?q=tag:#x` (`Cimkek.svelte:43-68,181-211`); no hand-off to the search overlay to refine | partial (different) | nice | S | 03-properties-14 |
| 32 | Tags pane: keyboard navigation | ARIA tree with ↑↓←→ Home End ↩ space (`Cimkek.svelte:102-125,139-179`) | present (+) | – | – | – |
| 33 | `#tag` in the body styled as a pill in LP, Source and Reading | No hashtag node (`app/src/szerkeszto/markdown/elemzo.ts:18-28`), no decoration (`app/src/szerkeszto/elo/sorok.ts:25-37`), no reader element (`olvaso/html.ts:599-600`) | missing | must | M | 03-properties-01 |
| 34 | Click on `#tag` → Search with `tag:#tag` | None (`app/src/szerkeszto/linkek/szerkeszto.ts:119-140` handles links only) | missing | must | S | 03-properties-02 |
| 35 | Typing `#` in the body suggests existing tags (nested too) | None; the only completion sources are `[[` and the frontmatter (`beallitas.ts:129-130`) | missing | must | M | 03-properties-03 |
| 36 | Tag grammar: letters, digits, `_`, `-`, `/`, at least one non-digit; case-insensitive grouping | `#(?<!\S#)([\w/-]+)` + non-digit check, trailing `/` stripped (`core/index/elemzo.py:33,363-366`); lower-cased key (`core/index/indexelo.py:767-768`); most frequent spelling displayed (`olvaso.py:367`). A tag after punctuation (`(#tag`) is not recognised — **confidence low** on Obsidian | present | nice | S | 03-properties-24 |
| 37 | `tags`/`tag`, `aliases`/`alias` keys; string or list values; space/comma split | `^tags?$`, `^alias(es)?$` (`core/index/elemzo.py:42-43`), `_lista` split (`:209-216`) | present | – | – | – |
| 38 | Quick switcher matches **aliases** (row shows alias → file) | Searches file names only (`app/src/atfedes/Valto.svelte:20-47`; `app/src/lib/vault/fajlok.svelte.ts:64-66`); aliases available at `GET /api/vault/aliasok` (`core/index/olvaso.py:312-321`; `app/src/lib/vault/linkek.svelte.ts:142-152`) | missing | must | S | 03-properties-04 |
| 39 | `[[` completion offers aliases (`[[Note\|Alias]]`); unlinked mentions include aliases | Present (`app/src/szerkeszto/linkek/kiegeszites.ts:5-10,96-101,258-262`; `core/index/olvaso.py:256-264`) | present | – | – | – |
| 40 | Keyboard flow in the editor: Tab/Shift-Tab between fields, Enter on the last value adds a property | Enter blurs, Esc reverts (`Tulajdonsagok.svelte:137-143`); no "Enter → next / new" — **confidence medium** on Obsidian | partial | nice | S | 03-properties-22 |
| 41 | Property block grows with its content | Panel body capped at 40 % of the editor with its own scrollbar (`Tulajdonsagok.svelte:450-459`; `docs/dev/DESIGN.md:230`) — nested scrolling inside the LP widget | partial | nice | S | 03-properties-20 |

---

## 2. Gaps and proposals

Each proposal stays inside the existing architecture: the core stays the only YAML reader/writer and link resolver (L42), writes go through the open document (`docs/dev/ARCHITECTURE.md:226`), the UI uses the design tokens of `docs/dev/DESIGN.md`.

### 03-properties-01 — Body `#tags` are not parsed or styled (must, M, confidence high)

**Obsidian.** `#tag` in the body is a token: pill-styled in Live Preview and Source (`.cm-hashtag`), an `a.tag` in Reading view, excluded inside code and math.

**Manifold.** The index sees tags (`core/index/elemzo.py:33,363-366`, masked for code/formula at `:331,337`), but the editor's Lezer extension list has no hashtag node (`app/src/szerkeszto/markdown/elemzo.ts:18-28`), the LP decoration map has none (`app/src/szerkeszto/elo/sorok.ts:25-37`) and the reader renders nothing for it (`app/src/szerkeszto/olvaso/html.ts:599-600`).

**Proposal.**
1. New `app/src/szerkeszto/markdown/cimke.ts` inline parser (`parseInline`, `before: 'Link'`) modelled on `markdown/wikilink.ts:12-20,22-57`: node `Hashtag` with children `HashtagMark` (`#`) and `HashtagLabel`; same grammar as the core (`[\w/-]+`, at least one non-digit, not preceded by a non-space char, trailing `/` dropped) so index and editor agree. Register it in `OBSIDIAN_BOVITESEK` (`markdown/elemzo.ts:18-28`) — the reader, the editor and the formula script share that list.
2. LP/Source: add `Hashtag: Decoration.mark({ class: 'cm-cimke' })` to `JELOLES` (`elo/sorok.ts:25-37`); style with `--hatter-aktiv` background, `--akcent-szoveg` text, `--kerekites-kicsi`, 24 px dense height (`docs/dev/DESIGN.md:25,38,105`), same look as the chips in `ListaMezo.svelte:112-127`.
3. Reading view: a `case 'Hashtag'` in the inline renderer of `olvaso/html.ts` producing `<a class="cimke" data-cimke="…">`.
4. Tests: extend `app/tests/tulajdonsagok-elo.svelte.test.ts` siblings with a `cimke-elemzo.test.ts` covering `#a/b`, `#1` (not a tag), code/formula masking, and parity with `core/index/elemzo._CIMKE`.

### 03-properties-02 — Clicking a `#tag` does not open search (must, S, confidence high)

**Obsidian.** Click on a tag (editor or reading view) opens the Search pane with `tag:#tag`; nested tags include children.

**Manifold.** No click handling for tags; the link handler covers `Wikilink`/`Embed`/external only (`app/src/szerkeszto/linkek/szerkeszto.ts:119-140`). The search overlay already accepts a preset query (`app/src/lib/kereses/vaultKereses.svelte.ts:175-185` `beallit`/`fokuszal`), the `tag:` operator matches children (`core/index/kereses.py:318-322`), and the tag pane already builds that query (`app/src/hej/Cimkek.svelte:54`).

**Proposal.** After 01: in `linkek/szerkeszto.ts` `mousedown`, resolve a `Hashtag` node at the click position (same `kirajzolt` rule as links: plain click only on rendered lines, ⌘-click always) and call a new `cimkeKeres(cimke)` in `app/src/szerkeszto/linkek/navigacio.ts` that runs `keresoMegnyit` (as `alapParancsok.ts:46-54`) + `vaultKereses.fokuszal(`tag:#${cimke}`)`. Reading view: delegate click on `a.cimke` in `Olvaso.svelte`. Offer ⌥-click to select the tag in the Címkék sidebar instead (`alapParancsok.ts:55-64` already switches to `cimkek`; add an exported `kivalaszt(kis)` on `VaultCimkek`, `app/src/lib/vault/cimkek.svelte.ts:51`). See open question 3.

### 03-properties-03 — No tag autocomplete in the body (must, M, confidence high)

**Obsidian.** Typing `#` opens a suggestion list of existing tags (fuzzy, nested, with counts in recent versions); Enter inserts.

**Manifold.** Completion sources are `[[` (`app/src/szerkeszto/linkek/kiegeszites.ts`) and the frontmatter (`tulajdonsagok/fmKiegeszites.ts:143-207`), wired at `beallitas.ts:129-130`. Tag data is already cached client-side (`app/src/lib/vault/cimkek.svelte.ts:51-100`, refreshed on `vault_valtozas`/`index` events `:89-99`) and the fuzzy index exists (`app/src/lib/kereses/fuzzy.ts`).

**Proposal.** New `app/src/szerkeszto/tulajdonsagok/cimkeKiegeszites.ts` exporting a `CompletionSource`: trigger when the text before the cursor matches `(?<!\S)#([\w/-]*)$` outside code/math/frontmatter (use `syntaxTree` like `fmKiegeszites.ts:43-47`), candidates from `cimkek.lista` (ensure `cimkek.frissit()` once per editor session, since the list only refreshes while the pane is visible, `cimkek.svelte.ts:82-87` — add a `kerjen()` that loads if `!betoltve`), ranked by `FuzzyIndex` with a count bonus as in `javaslat.ts:83-89`, `jelzo` = `ossz`. **Important:** `fmKiegeszites()` already installs `autocompletion({ override: [...] })` (`fmKiegeszites.ts:219-229`); a second `autocompletion()` would conflict, so extend that `override` array (or move both sources into one `kiegeszitesek.ts`). Apply inserts the tag label (no trailing space).

### 03-properties-04 — Quick switcher ignores aliases (must, S, confidence high)

**Obsidian.** ⌘O matches `aliases`; alias rows show the alias with an arrow/"alias" indicator and the real file name; opening goes to the file.

**Manifold.** `Valto.svelte:20-47` searches `fajlok.kereso()`, an index over file names only (`app/src/lib/vault/fajlok.svelte.ts:64-66`). The alias map is cached in `linkek.aliasokKap()` (`app/src/lib/vault/linkek.svelte.ts:142-152`, backed by `GET /api/vault/aliasok`, `core/index/olvaso.py:312-321`) and `linkek/kiegeszites.ts:96-113` already builds an alias-aware `FuzzyIndex` keyed `{ut, alias?}`.

**Proposal.** Extract `fajlJeloltek`/`fajlIndex` from `linkek/kiegeszites.ts:96-115` into `app/src/lib/vault/fajlIndex.ts` and use it in `Valto.svelte`: `$derived` over `fajlok.lista` + an `aliasok` state loaded on open; alias hits render `nev` = alias, `ut` column = `→ fájlnév` (`kiegeszites.ts:124` pattern); dedupe a file that matches by both name and alias (keep the better score). No core change.

### 03-properties-05 — Per-key property types are read-only (must, M, confidence high)

**Obsidian.** The type of a key is vault-wide, stored in `.obsidian/types.json`; the icon menu "Property type" changes it for every note; a brand-new key gets its inferred type written. Bases (1.9) and the Properties view rely on it.

**Manifold.** Reads and live-watches `types.json` (`core/index/elemzo.py:444-452`; `core/index/indexelo.py:394-412,491-503`), prefers it over value inference (`elemzo.py:245-246`), exposes it in key suggestions (`core/tulajdonsagok.py:589-597`) and pre-selects it in the new-property form (`Tulajdonsagok.svelte:202-208`). Nothing writes it; a key without an entry is typed per note by its value (`elemzo.py:174-191`), so `Due: 2025-01-01` is a date here and `Due: tomorrow` is text there.

**Proposal.**
- Core: `POST /api/vault/tulajdonsagok/tipus {kulcs, tipus}` in `core/tulajdonsagok.py` `utvonalak` (`:735-773`) → `Tulajdonsagok.tipus_beallit`: validate `tipus in TIPUSOK` (`:42`), read-modify-write `.obsidian/types.json` atomically (temp file + rename, `ensure_ascii=False`, keep unknown keys); the watcher already re-types the index (`indexelo.py:394-412`), so the response can just return the new map. `tulajdonsagok.py` is documented as "never writes files" (`:4-5`) — add a one-paragraph exception for this config file (it is not a note; snapshot/history policy for `.obsidian/` must be confirmed, open question 2).
- Core: on `modosit` with a `tipus` for a key that has no `types.json` entry and no other note using it (`tulajdonsag_kulcsok`, `olvaso.py:403-417`), record the type (Obsidian's "first value fixes the type") — optional, behind the same endpoint.
- UI: see 03-properties-06 for the icon/menu; in `TulajdonsagModell` add `tipusValt(kulcs, tipus)` → endpoint → `frissit()`; `JavaslatTar.urit()` (`javaslat.ts:290-292`) so key suggestions show the new type.

### 03-properties-06 — No type icon and no per-property menu (should, S, confidence high)

**Obsidian.** Each row shows a type icon (text/list/number/checkbox/calendar/clock/tags); clicking it opens "Property type"; right-click gives Cut/Copy/Paste/Remove.

**Manifold.** `Tulajdonsagok.svelte:324-415`: label + value + trash only; the grid reserves 104 px for the key (`:558-565`).

**Proposal.** Add a 16 px `Ikon` button before the label (Lucide `Type`, `List`, `Hash`, `CheckSquare`, `Calendar`, `Clock`, `Tags`, `AtSign`) mapped from `t.tipus`; click → a small `nt-menu` listbox (reuse `JavaslatMezo.svelte:233-271` markup) with the 6 user types + the fixed ones greyed; selecting calls 03-properties-05. Right-click on the row → the same menu plus "Törlés" (existing `torol`) and "Érték másolása". Keep the grid at `104px minmax(0,1fr) 24px` by putting the icon inside the label cell.

### 03-properties-07 — Keys cannot be renamed in place (should, M, confidence high)

**Obsidian.** Clicking the key name edits it; Enter renames the key in that note (value kept).

**Manifold.** The key is a `<label>` (`Tulajdonsagok.svelte:327`); the core `modosit` accepts `beallit`/`torol` only (`core/tulajdonsagok.py:495-496`).

**Proposal.** Core: `muvelet: 'atnevez'` with `uj_kulcs` in `modosit` (`:490-555`): validate with `_KULCS_NEV` (`:37`), refuse if `uj_kulcs` exists (`duplikalt_kulcs`), then rewrite only the first line of the `_Blokk` (`:111-114`) replacing the matched key text (keep quoting style via `_kulcs_nev`, `:141-143`), run the read-back proof (`:529-541`) with `vart_ertek` moved to the new key, and the schema delta (`uj_sertesek`, `:403-418`). UI: double-click or pencil on the label → inline input, Enter commits via `m.muvelet({muvelet:'atnevez', kulcs, uj_kulcs})`, with key suggestions from `kulcsJavasol` (`Tulajdonsagok.svelte:193-199`).

### 03-properties-08 — Tag chips in the properties panel are not clickable (should, S, confidence high)

**Obsidian.** Pills in the `tags` property are clickable → search `tag:#x`.

**Manifold.** `ListaMezo.svelte:70-75` makes only wikilink chips buttons; `Tulajdonsagok.svelte:357-365` passes `onnyit={chipNyit}` which only handles wikilinks (`:168-171`).

**Proposal.** After 03-properties-02: give `ListaMezo` an optional `onkattint(elem)` used for non-link chips; in `Tulajdonsagok.svelte` pass it when `listaTipus(t) === 'tags'` → `cimkeKeres(elem.replace(/^#/, ''))`. Style the tag chip with the `cm-cimke` look from 01 so body and panel match.

### 03-properties-09 — No Properties / All-properties sidebar views (should, M, confidence high)

**Obsidian.** Core plugin "Properties view": a right-sidebar "Properties" view of the current file (editable, same editor) and an "All properties" view listing every key with type icon and count; clicking a key runs the search `[key]`.

**Manifold.** Sidebar views are Files/Tags (`app/src/hej/Oldalsav.svelte:37-40`); right panel sections are backlinks/mentions/outgoing/outline/history (`app/src/hej/JobbPanel.svelte:173-185`). The data exists: `GET /api/vault/tulajdonsagok/kulcsok?ut=` returns `{kulcs, db, sema, tipus}` (`core/tulajdonsagok.py:581-599`; `olvaso.py:403-417`).

**Proposal.** (a) "Tulajdonságok" `Szakasz` in `JobbPanel.svelte` mounting the existing `Tulajdonsagok` component for the active `.md` (props as in `Szerkeszto.svelte:364-373`; the document must be shared — read it from `szerkesztok.svelte.ts`). (b) A third sidebar view `tulajdonsagok` in `Oldalsav.svelte:37-40` with a `Tulajdonsagkulcsok.svelte` list (ARIA listbox like `Cimkek.svelte:139-179`), rows = key, type icon (06), `db`, schema badge (`javaslat.ts:104`); click → after 03-properties-16 opens search `[key]`, until then opens the inline note list via a new `GET /api/vault/tulajdonsagok/jegyzetek?kulcs=` (trivial over the `tulajdonsag` table, `core/index/tar.py:38-41`). Add a `tulajdonsagok.panel` command next to `cimkek.panel` (`alapParancsok.ts:55-64`).

### 03-properties-10 — `cssclasses` unsupported (nice, S, confidence high)

**Obsidian.** `cssclasses` (and legacy `cssclass`) is a fixed list type; its values are added as classes to the note's view container so CSS snippets/themes can target it.

**Manifold.** No key recognition (`core/index/elemzo.py:42-44`), so it shows as a generic list; nothing applies classes.

**Proposal.** Core: `_CSSCLASS_KULCS = ^cssclass(es)?$`, type `cssclasses` appended to `TIPUSOK` (`elemzo.py:44`, `tulajdonsagok.py:42`, `_LISTA_TIPUSOK :40`), treated as list in `_illik`/`_ertek_normal`. UI: `tipusok.ts:4` union; `fajta()` → `'lista'`; apply the classes on the `.szerkeszto` root in `Szerkeszto.svelte:326` (`class:` from the analysed properties, sanitised to `[\w-]+`). Value only matters if Manifold ever supports user CSS snippets — see open question 4.

### 03-properties-11 — Tag pane has no sort options (should, S, confidence high)

**Obsidian.** Sort menu: tag name (A→Z, Z→A), tag count (high→low, low→high).

**Manifold.** Fixed `localeCompare('hu', {numeric})` by key (`app/src/lib/vault/cimkek.svelte.ts:27`).

**Proposal.** `cimkeFa(lista, nyitott, rendezes)` with `'nev' | 'nev-forditott' | 'db' | 'db-forditott'`, sorting siblings only (the parent-before-child order must survive; sort each depth's children by the chosen key, ties by name). Persist in `felulet.oldalsav` (next to `nyitott`/`nezet`, `felulet.svelte.ts`). UI: a small `ArrowDownAZ` icon button in `Cimkek.svelte:135-137` header opening a 4-item menu.

### 03-properties-12 — No collapse/expand all, expansion not remembered, no nested/flat toggle (nice, S, confidence medium)

**Obsidian.** Header buttons "Collapse all"/"Expand all"; the pane remembers which tags were expanded; "Show nested tags" toggle switches to a flat list of full paths.

**Manifold.** `nyitott` is a component-local `Set` (`Cimkek.svelte:21,78-83`); no header buttons.

**Proposal.** Move `nyitott` into `felulet.oldalsav.cimkekNyitott: string[]` (persisted like the file tree's `oldalsav.nyitott`, `docs/dev/ARCHITECTURE.md:190`); add two icon buttons (`ChevronsDownUp`/`ChevronsUpDown`) and a "Beágyazott címkék" toggle that makes `cimkeFa` emit every node at depth 0 with `nev = cimke` (full path).

### 03-properties-13 — No filter box in the tag pane (nice, S, confidence low)

**Obsidian.** Recent versions let you filter the tag list by typing (confidence low — verify before building).

**Proposal.** A `JavaslatMezo`-less plain input in the `Cimkek.svelte` header filtering `sorok` by `normalizal()` substring on `cimke`, auto-expanding ancestors of matches.

### 03-properties-14 — Tag pane selection cannot be handed to the search overlay (nice, S, confidence high)

**Obsidian.** Clicking a tag populates the Search pane, where the user refines the query.

**Manifold.** Click shows the inline note list (`Cimkek.svelte:43-68,181-211`) — keep it (it is faster) — but there is no way to continue in search.

**Proposal.** A "Keresésben" icon button in the list header (`Cimkek.svelte:182-191`) calling the `cimkeKeres` helper from 03-properties-02; ⌘-click on a tree row does the same.

### 03-properties-15 — Count semantics differ (nice, S, confidence medium)

**Obsidian.** The number next to a tag is the occurrence count (a tag used twice in one note counts 2) — confidence medium.

**Manifold.** Notes-with-tag (`core/index/olvaso.py:351-352,367-369`), shown as `ossz` with the exact count in the tooltip (`Cimkek.svelte:172`). Arguably the more useful number.

**Proposal.** Keep notes as the primary number; add `elofordulas` (= `COUNT(*)` over the `cimke` table, one row per occurrence: `core/index/indexelo.py:767-768`) to the `GET /api/vault/cimkek` rows (`olvaso.py:367-369`, `docs/dev/ARCHITECTURE.md:235`) and mention it in the tooltip; optionally a setting "Számlálás: jegyzet / előfordulás".

### 03-properties-16 — No property search operators (should, M, confidence high; search subsystem, cross-reference)

**Obsidian.** `[key]` (notes that have the key) and `[key:value]` (value match) in Search, Bases filters and the graph filter.

**Manifold.** `OPERATOROK = ("path", "file", "tag", "line")` (`core/index/kereses.py:38`); evaluation at `:316-322`; per-document data loaded only for tags (`:390-393`).

**Proposal.** In `core/index/kereses.py`: tokenizer rule for `[k]` / `[k:v]` → `("op", "prop", (k, v|None))`; load a `{fid: {kulcs_lower: [szövegek]}}` map when the expression uses it, from the `tulajdonsag` table using the same value flattening as `core/index/graf_meta.py:16`; match with `_ertek_illik`. Document in `docs/dev/ARCHITECTURE.md:161`. This belongs to the Search parity report but unblocks 03-properties-09.

### 03-properties-17 — No "Properties in document: Visible / Hidden / Source" mode; header always shown (nice, S, confidence high)

**Obsidian.** Editor setting with three modes; a note without frontmatter shows nothing.

**Manifold.** One persisted boolean `felulet.tulajdonsagok.nyitva` (`felulet.svelte.ts:58,128`); the header is always rendered, with a "no frontmatter" row when absent (`Tulajdonsagok.svelte:320-322`), faint in quiet mode (`:88-89,280-283`).

**Proposal.** Replace the boolean with `mod: 'lathato' | 'osszecsukva' | 'rejtett' | 'forras'` (keep `nyitva` as alias for the first two); `rejtett` suppresses the widget (`elo.svelte.ts:72-81` returns `Decoration.none`), `forras` leaves the raw YAML visible in LP (skip the `Decoration.replace`). Add a "Tulajdonságok: nincs frontmatter → rejtve" option so empty notes look like Obsidian. Command `tulajdonsagok.kapcsol` (`alapParancsok.ts:65-72`) cycles the modes.

### 03-properties-18 — Reading view may show both the panel and a raw-YAML box (nice, S, confidence low — verify in the app)

`Szerkeszto.svelte:364-373` mounts the editable panel above the reader in `olvaso` mode, and the reader's own renderer still emits a collapsed `<details class="tulajdonsagok">` with the YAML (`app/src/szerkeszto/olvaso/html.ts:552-567`, styled at `app/src/szerkeszto/szerkeszto.css:726-740`). `docs/dev/ARCHITECTURE.md:242` says the raw box is hidden; I could not find the hiding rule. If it is visible, drop the `details` from `html.ts:599-600` when the renderer runs inside the editor (it may still be wanted for embeds/exports — make it a `RenderOpciok` flag).

### 03-properties-19 — New-property form lacks the `aliases` type and does not pre-select list for `aliases`/`cssclasses` (nice, S, confidence high)

`UJ_TIPUSOK` (`Tulajdonsagok.svelte:175-183`) has no "Aliasok"; `kulcsValaszt` (`:202-208`) only maps `Tags`/`LISTA_KULCSOK` (`ertek.ts:80`). Typing `aliases` with the default text type writes `aliases: "a, b"` — one alias (`core/tulajdonsagok.py:263-265,280`). Fix: add `{ id: 'aliases', nev: 'Aliasok' }` (and `cssclasses` after 03-properties-10) and let `kulcsValaszt` fall back to `elemzo.tipus_ertekbol`-equivalent rules on the client (`/^tags?$/i → tags`, `/^alias(es)?$/i → aliases`).

### 03-properties-20 — Panel capped at 40 % height with inner scroll (nice, S, confidence high)

`Tulajdonsagok.svelte:450-459` (`max-height: 40%`, `.torzs overflow:auto :547-552`), by design (`docs/dev/DESIGN.md:230`). In LP the widget is part of the document, so a long property list becomes a scroll region inside the editor's scroll. Obsidian lets the block grow. Proposal: apply the cap only in the reading-mode mount (`Szerkeszto.svelte:364`) via a prop, let the LP widget grow.

### 03-properties-21 — `[[` in a plain text/list property does not switch to file suggestions in the panel (nice, S, confidence high)

`javaslatFajta` (`javaslat.ts:51-53`) picks link mode only for `LINK_KULCSOK` or all-wikilink values; raw YAML completion already switches on a typed `[[` (`fmKiegeszites.ts:168`). Proposal: in `javaslo` (`Tulajdonsagok.svelte:151-158`) test `linkLekerdezes(q)` (`javaslat.ts:135-143`) — if the typed text starts with `[[`, route to `linkJavaslatok`.

### 03-properties-22 — Keyboard flow between properties (nice, S, confidence medium)

Obsidian: Tab/Shift-Tab move between key and value and down the list; Enter in the last value adds a new property. Manifold: Enter blurs (`Tulajdonsagok.svelte:137-143`), Tab follows DOM order (label is not focusable, trash buttons are). Proposal: `tabindex=-1` on `.torol` and the link-chip pencil; Enter in the last row opens the "Új tulajdonság" form (`ujNyitva = true`).

### 03-properties-23 — No "Add file property" command/hotkey (nice, S, confidence low on the default hotkey)

Only `tulajdonsagok.kapcsol` exists (`alapParancsok.ts:65-72`). Proposal: `tulajdonsagok.uj` command (category "Jegyzet") that opens the panel and the form with focus on the name field — expose `ujNyit()` from `Tulajdonsagok.svelte` through the `eloTulajdonsagForras` facet (`elo.svelte.ts:16-18`) or a small store in `szerkesztok.svelte.ts`.

### 03-properties-24 — Tag after punctuation (nice, S, confidence low)

`core/index/elemzo.py:33` requires the `#` to be preceded by whitespace/line start (`(?<!\S#)`), so `(#tag)` or `„#tag”` is not a tag. Obsidian's rule for the preceding character is not certain to me; if it accepts punctuation, relax the lookbehind to `(?<![\w#/])` in the core and in the editor parser of 03-properties-01 (both must stay identical).

---

## 3. Manifold strengths beyond Obsidian — preserve

1. **Vault schema with a confirmation flow.** `config/vault-sema.json:3-7` (field order, allowed `Tags`/`Status`, extra keys, path classes) loaded by `Sema` (`core/tulajdonsagok.py:69-106`); violations split into `hiba` (never written) and `sertes` (written only with `megerosit: true`, `:13-17,549-550`); only *new* violations need confirmation (`uj_sertesek`, `:403-418`); the machine may not set `Status` (`:507-510`). UI: warning box with "Mégis beírom"/"Mégse" (`Tulajdonsagok.svelte:257-269`), "N eltérés" chip (`:290-303`). Obsidian core has no schema at all.
2. **Byte-faithful YAML editing.** Line-level block replacement, comments/quotes/order/CRLF/BOM kept (`core/tulajdonsagok.py:8-11,111-135,173-184`), a read-back proof with a duplicate-key-strict loader before any write (`:527-541`; `core/index/elemzo.py:85-102`), quoting of values another YAML reader would misread (`_MAS_OLVASO`, `:200-221`), calendar-valid dates (`:49-64`). Obsidian re-serialises the block (comments are lost — confidence medium).
3. **Single write path through the open document** — autosave, conflict detection and ⌘Z stay the editor's (`app/src/szerkeszto/tulajdonsagok/modell.svelte.ts:70-110`, `fm.ts:37-48`, `docs/dev/ARCHITECTURE.md:226`); stale-response guard (`modell.svelte.ts:78-86`).
4. **Raw-YAML autocompletion in Source mode** — keys, values and link targets with YAML-safe quoting (`fmKiegeszites.ts:77-111,115-120,143-207`), same lists as the panel (`javaslat.ts:1-12`). Obsidian offers nothing in raw YAML.
5. **Suggestions with usage counts and schema badges** — "N jegyzetben", "séma", "vaultban használt" (`javaslat.ts:60-61,76-77,104`); schema values listed even when unused (`core/tulajdonsagok.py:625-628`); a value becomes legitimate when another note already uses it (`ertekkeszlet_hasznalat`, `core/index/olvaso.py:372-401`; `core/tulajdonsagok.py:338-345`).
6. **Status as a schema-driven combobox** that opens on focus (`Tulajdonsagok.svelte:341-355`; `JavaslatMezo.svelte:171-178`).
7. **Link-typed properties** (`Source`, `NN`, `Canvas`, and any all-wikilink value): file suggestions with type bonus (PDF for `Source`, canvas for `Canvas`, `javaslat.ts:150-155`), the shortest unambiguous target from the core (L42, `javaslat.ts:168-177`), `#page=12`/`|alias` preserved (`:134-143`), link chips open the target with ⌘/⌘⌥ (`Tulajdonsagok.svelte:168-171,366-375`; `ListaMezo.svelte:70-72`), typed names auto-wrapped as `[[…]]` (`ertek.ts:40-44`).
8. **Schema-ordered insertion of new keys** (`core/tulajdonsagok.py:722-732`) — Obsidian appends.
9. **Template frontmatter merge** with add / merge-list / fill-empty / keep / skip / pending semantics (`core/tulajdonsagok.py:637-698`; `POST /api/vault/tulajdonsagok/osszefesul`, `docs/dev/ARCHITECTURE.md:233`).
10. **`icon` and `cover` properties**: note icon in tab, tree, search and breadcrumb (`app/src/lib/ui/JegyzetIkon.svelte:1-25`; `core/index/olvaso.py:326-348`), cover banner above the panel (`Boritokep.svelte:1-30`). Obsidian core has neither.
11. **Per-value validity flag** (`ervenyes`, `core/index/elemzo.py:138,194-206`) rendered red (`Tulajdonsagok.svelte:326,683-685`).
12. **Hungarian decimal comma** accepted in number fields (`ertek.ts:63-66`; `core/tulajdonsagok.py:246-247`).
13. **Obsidian coexistence on the same vault**: `.obsidian/types.json` read and hot-reloaded (`core/index/elemzo.py:444-452`; `core/index/indexelo.py:394-412,491-503`), `tags`/`tag`, `aliases`/`alias` accepted (`elemzo.py:42-43`), YAML 1.2-like scalar rules matching Obsidian's parser (`elemzo.py:49-82`), frontmatter links tracked with their key (`elemzo.py:129,341-351`).
14. **Alias-aware `[[` completion and unlinked mentions** (`linkek/kiegeszites.ts:5-10,96-101`; `core/index/olvaso.py:256-264`).
15. **Tag pane as a full ARIA tree** with roving tabindex and the complete arrow/Home/End/Enter model (`Cimkek.svelte:102-125,139-156`), exact and inclusive counts (`:172`), most-frequent spelling (`core/index/olvaso.py:367`), inline note list with folder and file icons (`:192-210`), refresh only while visible and debounced on vault events (`cimkek.svelte.ts:55-57,82-99`).
16. **Quiet mode integration** — collapsed panel becomes a faint one-liner (`Tulajdonsagok.svelte:88-89,280-283`).
17. **Assistant learns user-added tags** (`api.ts:58-65`) — feeds later suggestions.
18. **Invalid-YAML path is a first-class state**: error text from the core, inline editable raw block, automatic return to the widget (`EloTulajdonsagok.svelte:14-23`; `elo.svelte.ts:61-68,76-80`), `yaml_hiba` surfaced in the problem list (`core/tulajdonsagok.py:379-381`).
19. **Graph filters on tags and properties** via `GET /api/vault/graf-meta` (`core/index/graf_meta.py:36-52`; `docs/dev/ARCHITECTURE.md:163`).
20. **Test coverage to keep green**: `app/tests/tulajdonsagok-panel.test.ts`, `tulajdonsagok-elo.svelte.test.ts`, `tulajdonsagok-szerkeszto.svelte.test.ts`, `tulajdonsagok-segedek.test.ts`, `tulajdonsag-javaslatok.test.ts`, `cimkek-elozmenyek.test.ts`.

---

## 4. Open questions

1. **Tag count semantics** (03-properties-15): keep "notes with the tag" as the headline number, or show Obsidian-style occurrences? Both are available from the `cimke` table.
2. **Who owns per-key types** (03-properties-05): write Obsidian's `.obsidian/types.json` (interoperable), extend `config/vault-sema.json` with a `tipusok` map (schema-owned), or both with a precedence rule? Also: does the snapshot/history policy (`docs/dev/ARCHITECTURE.md:379`) cover `.obsidian/` writes?
3. **Where does a `#tag` click land** (03-properties-02/14): the ⇧⌘F search overlay (Obsidian) or the Címkék sidebar with the tag selected (Manifold's inline list)? Proposal: plain click → search overlay, ⌥-click → sidebar; confirm.
4. **`cssclasses`** (03-properties-10): Manifold has no user CSS snippets or themes beyond the token system; is applying arbitrary classes desirable, or is recognising the type enough?
5. **Schema strictness vs Obsidian freedom**: every unknown key (including `icon`/`cover`) asks for confirmation (`core/tulajdonsagok.py:13-17`). Obsidian users add ad-hoc keys constantly. Is a per-vault "schema off / advisory only" switch wanted (today only `sema_nelkuli_utak` per path, `:79`)?
6. **Reading view raw YAML box** (03-properties-18): is it really hidden, as `docs/dev/ARCHITECTURE.md:242` states? Not found in CSS; needs a check in the app.
7. **Tag pane filter box** (03-properties-13): confirm Obsidian 1.8/1.9 has it before building.
8. **"Add file property" default hotkey** (03-properties-23): confirm whether Obsidian binds one by default; pick a Manifold chord consistent with `docs/dev/DESIGN.md` section 8.
9. **Quick switcher alias rows** (03-properties-04): show both the name hit and the alias hit for the same file, or collapse to one row?
10. **Property search operators** (03-properties-16) are owned by the Search parity report; this report only needs them for 03-properties-09 — agree on sequencing.

---

## 5. Cited file map

| Area | Files |
|---|---|
| Core analysis | `core/index/elemzo.py` (types `:44,174-206`, frontmatter `:226-248`, tags/aliases `:353-366`, `types.json` `:444-452`) |
| Core editing/schema | `core/tulajdonsagok.py` (schema `:69-106`, serialisation `:200-280`, problems `:302-360`, `elemez` `:366-385`, `modosit` `:490-555`, suggestions `:581-629`, merge `:637-698`, routes `:735-773`) |
| Index readers | `core/index/olvaso.py` (aliases `:312-321`, icons `:326-348`, tags `:350-370`, value usage `:372-401`, keys `:403-417`, values `:419-444`); `core/index/indexelo.py:394-412,491-503,764-768`; `core/index/tar.py:38-44`; `core/index/kereses.py:38,316-322,390-393` |
| Panel UI | `app/src/szerkeszto/tulajdonsagok/{Tulajdonsagok,ListaMezo,JavaslatMezo,EloTulajdonsagok,Boritokep}.svelte`, `{elo.svelte,modell.svelte,javaslat,fmKiegeszites,ertek,fm,api,tipusok}.ts` |
| Editor wiring | `app/src/szerkeszto/beallitas.ts:83-88,123,129-130`; `Szerkeszto.svelte:364-380`; `elo/sorok.ts:25-37,335-352`; `markdown/elemzo.ts:18-28`; `markdown/wikilink.ts:12-57`; `linkek/szerkeszto.ts:119-140`; `linkek/kiegeszites.ts:96-113`; `olvaso/html.ts:552-567,599-600` |
| Tags UI | `app/src/hej/Cimkek.svelte`; `app/src/lib/vault/cimkek.svelte.ts`; `app/src/hej/Oldalsav.svelte:37-40`; `app/src/alapParancsok.ts:46-72` |
| Quick switcher / search | `app/src/atfedes/Valto.svelte:20-47`; `app/src/lib/vault/fajlok.svelte.ts:64-66`; `app/src/lib/vault/linkek.svelte.ts:142-152`; `app/src/lib/kereses/vaultKereses.svelte.ts:175-185` |
| Docs | `docs/dev/ARCHITECTURE.md:158,161,163,190,226-251`; `docs/dev/DESIGN.md:25,38,105,226-234`; `docs/plan/audit/03-felulet.md:54,81,231,273` |
