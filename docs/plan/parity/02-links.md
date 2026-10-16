# 02 — Obsidian-parity audit: Links, autocomplete, navigation, backlinks

Scope: the Manifold link subsystem compared with Obsidian 1.8/1.9 desktop **core** behaviour (core plugins only; no community plugins). Paths are relative to `/Volumes/Work/[UNI] Manifold-OS`. Identifiers are Hungarian; user-facing text is out of scope here.

Files read: `app/src/szerkeszto/linkek/{adat,atnevezes,elonezet,emlites,kiegeszites,kulso,navigacio,szerkeszto}.ts`, `app/src/lib/vault/linkek.svelte.ts`, `app/src/lib/vault/kapcsolatok.svelte.ts`, `app/src/hej/kapcsolatok/{Visszahivatkozasok,KimenoLinkek,Emlitesek}.svelte`, `app/src/hej/JobbPanel.svelte`, `app/src/szerkeszto/{index.ts,Olvaso.svelte,FajlCim.svelte,csatolmany.ts,helyiMenu.ts}`, `app/src/szerkeszto/elo/sorok.ts`, `app/src/szerkeszto/olvaso/html.ts`, `app/src/szerkeszto/beagyazas/rajzol.ts`, `app/src/szerkeszto/notion/muveletek.ts`, `app/src/hej/Fa.svelte`, `app/src/atfedes/{Atnevezes,KeresoAblak}.svelte`, `core/index/{feloldas,linkek,olvaso,api,elemzo,kereses}.py`, `core/vaultio.py`, `core/atnevezes.py`, `core/asszisztens/emlites.py`, `docs/dev/ARCHITECTURE.md`, `docs/plan/audit/03-felulet.md`, and the tests under `app/tests/` named for these modules.

Severity: **must** = daily-use Obsidian behaviour users miss immediately · **should** = noticeable · **nice** = polish. Effort: S (<1 day), M (1–3 days), L (>3 days). Confidence is marked where the Obsidian side is not certain.

---

## 1. Checklist

Legend for *status*: present / partial / missing. Rows with no gap id are parity (nothing to do).

### 1.1 Resolution

| Obsidian behaviour | Manifold today (path:line) | Status | Sev. | Effort |
|---|---|---|---|---|
| `[[wikilink]]` resolved in `getLinkpathDest` order: basename → basename+`.md` → single candidate → full path → path-suffix closest to source | Single core resolver `Feloldo` (`core/index/feloldas.py:182-247`), same object serves graph, backlinks, rename and the UI (`core/index/olvaso.py:289-301`, `app/src/lib/vault/linkek.svelte.ts:104-128`); UI never resolves itself (`linkek.svelte.ts:1-6`) | present | – | – |
| Case-insensitive match as fallback, exact-case wins | Two passes, exact then lower-cased (`core/index/feloldas.py:216-244`) | present | – | – |
| `[[note.md]]` with extension; `[[folder/note]]` suffix match on segment boundary | `_menet` candidate lookup by basename incl. `.md` (`feloldas.py:220-223`); `_vegzodik` segment-boundary suffix (`feloldas.py:177-179`) | present | – | – |
| Markdown link `[text](note.md)` resolved like a wikilink; `<…>` wrapper; `%XX` decoded | `md_reszek`/`md_cel` (`core/index/feloldas.py:83-102`), index records `fajta: md` (`core/index/elemzo.py:276-288`), graph (`feloldas.py:134-138`) | present (core) | – | – |
| Internal markdown link is **clickable** and ⌘-hoverable in editor and reading view | Editor click only handles external URLs (`app/src/szerkeszto/linkek/szerkeszto.ts:40-54`, `:124-132`); LP decorates `Link` only as `cm-link` (`app/src/szerkeszto/elo/sorok.ts:31`); reader marks only external targets (`app/src/szerkeszto/olvaso/html.ts:234-242`, `:186-190`); hover `egerLink` only finds `Wikilink`/`Embed` (`szerkeszto.ts:16-24`) | **missing** | must | M | → 02-links-01 |
| Relative markdown targets `./x.md`, `../a/b.md` (what Obsidian's "Relative path to file" format emits) resolve | `_elokeszit` only strips leading `/` and turns `\` into `/` (`core/index/feloldas.py:169-174`); no `.`/`..` normalisation, so `_menet` suffix check fails (`feloldas.py:229-238`); no `../` case in `tests/test_index_feloldas.py` | missing | should | S | → 02-links-03 (conf. medium) |
| Aliases (`aliases:` / `alias:` frontmatter) resolve a link, show in suggester, count in backlinks and unlinked mentions | Parsed `core/index/elemzo.py:43,359-361`; `GET /api/vault/aliasok` (`core/index/olvaso.py:312-321`); suggester (`app/src/szerkeszto/linkek/kiegeszites.ts:96-103,119-129`); mentions (`olvaso.py:261-263`) | present | – | – |
| Heading links `[[note#Heading]]`, nested `[[note#A#B]]`, normalised comparison | `fejezet_tartomany` nested path (`core/index/linkek.py:52-73`), `alcel_norm` (`linkek.py:45-49`, documented as an approximation of Obsidian's rule) | present | – | – (see open Q3) |
| Block links `[[note#^id]]`; list block embeds children | `blokk_tartomany` (`core/index/linkek.py:76-99`), `blokk` table (`olvaso.py:222`) | present | – | – |
| Same-note links `[[#Heading]]`, `[[#^id]]` | empty target = current note (`app/src/szerkeszto/linkek/adat.ts:8`, `navigacio.ts:72`, `kiegeszites.ts:165`) | present | – | – |
| `[[note\|alias]]` renders alias; `[[note#h]]` renders `note > h`; `[[` `]]` hidden in Live Preview | `sorok.ts:335-354` (separator ` › ` at `:351`), reader `html.ts:265-278`, `linkFelirat` (`adat.ts:41-44`) | present | – | – |
| `\|` escape inside tables | `linkek.py:149-151`, `feloldas.py:170-174` | present | – | – |
| Links inside frontmatter properties are links (indexed, backlinked, clickable in Properties) | no mask in frontmatter (`feloldas.py:20`), `tulajdonsag` recorded (`elemzo.py:341-351`), badge in backlinks (`Visszahivatkozasok.svelte:16-19`), clickable (`app/src/szerkeszto/tulajdonsagok/Tulajdonsagok.svelte:170`) | present | – | – |
| Unresolved links rendered dimmed (`.is-unresolved`) in LP and reading view | one static class `cm-wikilink` for all (`sorok.ts:33-34`, `app/src/szerkeszto/szerkeszto.css:139-143`); reader `.wikilink` static (`html.ts:265-278`, `szerkeszto.css:712-718`); no resolution pass in either renderer | **missing** | must | M | → 02-links-02 |
| Ambiguous target (several files with the same basename) | core flags `tobbertelmu` (`feloldas.py:238`, `olvaso.py:299-300`) — Obsidian has no such flag | present (beyond Obsidian) | – | – |

### 1.2 Autocomplete popup

| Obsidian behaviour | Manifold today | Status | Sev. | Effort |
|---|---|---|---|---|
| Typing `[[` opens suggester; `]]` auto-paired; Backspace removes the pair | `gepeles` input handler (`app/src/szerkeszto/linkek/kiegeszites.ts:486-500`), `parTorles` (`:503-516`); `![[` same menu (`:491`) | present | – | – |
| Fuzzy, accent-insensitive match on file name **and** path; path shown as secondary text | `fajlElemek` (`kiegeszites.ts:117-159`), `FuzzyIndex` scores `ut` too (`app/src/lib/kereses/fuzzy.ts:5,12,216`); `jelzo: mappa(ut)` (`:124`) | present | – | – |
| Empty query lists recent files first | recents then mtime (`kiegeszites.ts:132-147`) | present | – | – |
| Alias entries, selecting one inserts `[[Note\|Alias]]` | `:100`, `:128` | present | – | – |
| Inserted target is the shortest unambiguous path | `linkek.linkCel` → `GET /api/vault/linkcel` → `rovid_cel` (`core/index/linkek.py:31-40`, `olvaso.py:303-310`) | present | – | – |
| `[[note#` lists that note's headings (level shown); `[[#` the current note's (live text) | `fejezetElemek` (`kiegeszites.ts:187-210`), live tree for current note (`:191`), `/api/vault/jegyzet` for others (`:194`); `#`,`\|`,`^`,`[`,`]` stripped (`app/src/szerkeszto/notion/muveletek.ts:514-516`) | present | – | – |
| `[[note#^` lists blocks with preview; picking an id-less block **writes a new `^id` into that note** (also when it is another note) | current note: id generated and written in the same transaction (`kiegeszites.ts:214-232,344-350`); other notes: only blocks that already have an id (`:233-250`) | partial | should | M | → 02-links-04 |
| `[[##` searches headings across the whole vault | `lekerdezesElemez` treats `##x` as heading filter `#x` of the current note (`kiegeszites.ts:72-81`) → empty | missing | should | M | → 02-links-05 |
| `[[^` searches blocks of the current note | `^` parsed as a file query (`:79`) | missing | nice | S | → 02-links-15 (conf. medium) |
| Suggester re-opens when the cursor is edited **inside an existing** `[[…` (trigger is "text before cursor matches", not only the `[[` keystroke) | opens only on the `[` keystroke (`:486-500`) or the command (`:524-535`); state closes when the cursor leaves (`:292-297`) and never re-opens | missing | should | M | → 02-links-06 |
| Typing `[[` with a selection wraps it: `[[selection]]` and the selection becomes the query | `linkBeszur` replaces the selection with `[[]]` — text is lost (`kiegeszites.ts:524-535`: `{ from: r.from, to: r.to, insert: '[[]]' }`); the input handler only fires for an empty selection (`:487`) | missing | should | S | → 02-links-07 |
| Unresolved link targets already used in the vault are offered as suggestions | candidates are `fajlok()` only (`:98`) | missing | should | S | → 02-links-14 (conf. medium) |
| Enter/Tab with no match inserts the typed text, cursor after `]]`; Esc closes keeping text | `:462-471`, `:455-459` | present | – | – |
| Suppressed in code, math, HTML | `TILTOTT`/`linkNyithato` (`:49-57`) | present | – | – |
| Display-text mode after `\|` (Obsidian closes the suggester there) | alias list after `\|` (`:258-266`) | present (beyond Obsidian) | – | – |
| Non-md files (images, PDF, canvas, base) suggested with extension; md ranked first | `:99`, bonus `:155`; test `app/tests/kiegeszites.test.ts:203` | present | – | – |
| When "Use [[Wikilinks]]" is off, suggester inserts `[text](path.md)` | always `]]` (`:351`) | missing | should | M | → 02-links-13 |
| Refresh on vault change | 500 ms polling of `linkek.verzio` (`:433-443`) | present (polish) | nice | S | → 02-links-27 |

### 1.3 Unresolved link → create note (`newFileLocation`)

| Obsidian behaviour | Manifold today | Status | Sev. | Effort |
|---|---|---|---|---|
| Click/⌘-click on an unresolved link creates the note and opens it (new tab with ⌘) | `linkMegnyit` → `jegyzetLetrehoz` → `POST /api/vault/uj {link}` (`app/src/szerkeszto/linkek/navigacio.ts:45-67,81-85`) | present | – | – |
| Location: `[[folder/x]]` → relative to vault root, folders created, case-insensitive folder match; bare name → `newFileLocation` (`root` / `current` / `folder` + `newFileFolderPath`) | `Vault.link_jegyzet_helye` (`core/vaultio.py:414-444`), `uj_fajl_beallitas` reads `.obsidian/app.json` (`vaultio.py:402-412`), folder creation `mappa_keszit` (`vaultio.py:468-472,487-489`) | present | – | – |
| Not created for attachment-like targets (`[[x.png]]`) | `ISMERT_KITERJESZTES` (`navigacio.ts:22,51-54`), `NEM_JEGYZET_CEL` (`vaultio.py:399-400,424-425`) | present | – | – |
| Create from the outgoing-links pane | `KimenoLinkek.svelte:56-67`, `JobbPanel.svelte:135-142` | present | – | – |
| Missing embed shows "not created yet, click to create" | `hianyzo` + "Létrehozás" (`app/src/szerkeszto/beagyazas/rajzol.ts:101-123`) | present | – | – |
| Setting editable in the app | read-only from `app.json`; no Manifold UI | partial | – | – (open Q1) |

### 1.4 Rename / move propagation

| Obsidian behaviour | Manifold today | Status | Sev. | Effort |
|---|---|---|---|---|
| Rename updates `[[links]]`, `![[embeds]]`, keeps alias, `#heading`, `^block`, size `\|300` | plan over every link before/after (`core/atnevezes.py:332-367`), only the target span is rewritten (`core/index/linkek.py:141-164`), `WIKI_RE` covers `!` (`feloldas.py:40`) | present | – | – |
| Markdown links updated with Obsidian's encoding; `<…>` wrapper preserved | `md_kodol` (`feloldas.py:105-108`, applied `atnevezes.py:400-403`), `burok` (`linkek.py:158-163`) | present | – | – |
| Canvas file nodes and `[[…]]` in canvas text nodes updated | `_canvas_terv` (`atnevezes.py:438-471`) | present | – | – |
| Links in frontmatter updated | frontmatter unmasked for `WIKI_RE` (`feloldas.py:20`) | present | – | – |
| Folder rename/move updates everything | `_ellenoriz_mappa`, `lek` mapping (`atnevezes.py:251-319`) | present | – | – |
| Only links whose resolution would change are rewritten (others untouched) | resolve before (`fo_e`) and after (`fo_u`) (`atnevezes.py:337-356`) | present | – | – |
| Inline title editable → renames the file | `app/src/szerkeszto/FajlCim.svelte:11-38` | present | – | – |
| Explorer F2 renames **inline** in the tree row | F2 opens the rename dialog (`app/src/hej/Fa.svelte:217-219,245`, `app/src/atfedes/Atnevezes.svelte:1-6`) | partial | nice | M | → 02-links-25 |
| Explorer drag file → folder moves it immediately with link updates | drag opens the plan dialog pre-filled with the target folder, nothing written until confirmed (`Fa.svelte:313`, `Atnevezes.svelte:5,37`) | present (confirm step is deliberate) | – | – |
| Rename works while the note (or linking notes) is open with unsaved edits; editors receive the rewritten text | all docs are closed/saved first (`app/src/szerkeszto/linkek/atnevezes.ts:94-107`); unsaved source → 409 `nyitott` (`core/atnevezes.py:586-595`) | partial | nice | M | → 02-links-26 |
| Case-only rename | allowed (`atnevezes.py:225-233`), not undoable (`:775-777`) | present | – | – |
| Plan preview, blockers, undo, reference proof, crash journal | `Atnevezes.svelte:185-235`, `atnevezes.ts:109-144`, `core/atnevezes.py:486-523,546-565` — beyond Obsidian | present (strength) | – | – |

### 1.5 Hover page preview (⌘-hover)

| Obsidian behaviour | Manifold today | Status | Sev. | Effort |
|---|---|---|---|---|
| ⌘/Ctrl + hover over an editor link shows a rendered popover after a short delay; Esc or mouse-out closes; popover stays while hovered | `LebegoElonezet` (`app/src/szerkeszto/linkek/elonezet.ts:23-131`), 300 ms (`:18`), bound to editor (`szerkeszto.ts:95-108`) | present | – | – |
| Works in reading view, canvas, embedded content | `Olvaso.svelte:115`, `app/src/canvas/Vaszon.svelte:826`, `beagyazas/widget.ts:56` | present | – | – |
| Heading/block links preview the section; images/PDF/video preview media | same renderer as embeds (`elonezet.ts:66-73` → `rajzol.ts:60-97`) | present | – | – |
| Unresolved target shows "not created yet" | `hianyzo` in popover (`rajzol.ts:101-123`) | present | – | – |
| Preview also on file-explorer rows, search results, backlinks and outgoing-links rows | `elonezetKapcsol` only in editor/reader/canvas; nothing in `hej/Fa.svelte`, `hej/JobbPanel.svelte`, `atfedes/KeresoAblak.svelte` | missing | should | S | → 02-links-09 |
| Per-source "Require Ctrl/Cmd" toggle | always requires ⌘ (`elonezet.ts:44,143`) | missing | nice | S | → 02-links-20 |
| Nested previews (hover a link inside the popover) | popover appended to `body` (`elonezet.ts:84`), outside the root that listens for `mousemove` (`:157`) | missing | nice | S | → 02-links-21 |
| Preview of internal markdown links | not a link in the editor (see 1.1) | missing | must | – | part of 02-links-01 |
| Keyboard trigger | command "Link előnézete a kurzornál" (`app/src/szerkeszto/index.ts:134-147`) — Obsidian has none | present (beyond) | – | – |

### 1.6 Navigation

| Obsidian behaviour | Manifold today | Status | Sev. | Effort |
|---|---|---|---|---|
| Click in Live Preview opens the rendered link; ⌘-click needed in the active line / source mode | `kattintas` (`szerkeszto.ts:119-141`), `kirajzolt` (`:87-93`) | present | – | – |
| ⌘-click → new tab; ⌘⌥-click → split | `nyitasMod` (`navigacio.ts:30-35`); honoured everywhere `linkMegnyit` is used (reader, canvas, panes, bases, cards) | present | – | – |
| ⌘⌥⇧-click → new window | single-window shell | missing | – | – (open Q5) |
| Middle-click → new tab | editor ignores `button !== 0` (`szerkeszto.ts:120`); reader click handler only (`Olvaso.svelte:75`) | missing | should | S | → 02-links-08 |
| Heading/block link scrolls to the target | `szerkesztok.ugras(ut, b.kezd)` (`navigacio.ts:89-94`); anchor error notifies (`:95-96`) | present | – | – (open Q4: flash) |
| PDF page / media time anchors | `mediaHorgony` (`adat.ts:58-69`), passed to the view (`navigacio.ts:87-93`, `index.ts:236-240`) | present (beyond: `#t=`) | – | – |
| "Follow link under cursor" command | `szerkeszto.link-megnyit` Mod+Enter (`index.ts:119-133`) | present | – | – |
| "Open link under cursor in new tab" / "…to the right" commands | `kurzorLinkMegnyit(v, mod)` supports modes (`szerkeszto.ts:78-84`) but only the active-tab command is registered | missing | nice | S | → 02-links-22 |
| Right-click on a link: open in new tab / to the right | generic note context menu, no link items (`app/src/szerkeszto/helyiMenu.ts:67-88`) | missing | nice | S | → 02-links-23 (conf. medium) |
| Back / forward per tab (⌘⌥← / ⌘⌥→) | `navigacio.vissza` (`app/src/alapParancsok.ts:127`), per-tab history (`app/src/lib/elrendezes/munkaterulet.svelte.ts:64-86`) | present | – | – |
| Non-note targets open in their own view | `fugg.megnyit(ut, mod, horgony)` (`navigacio.ts:93`) | present | – | – |

### 1.7 Backlinks pane

| Obsidian behaviour | Manifold today | Status | Sev. | Effort |
|---|---|---|---|---|
| Linked mentions grouped by source file, with the line as context and the link highlighted; count in the header | `Visszahivatkozasok.svelte:22-52`, `GET /api/vault/visszahivatkozasok` (`core/index/olvaso.py:236-252`), header count (`JobbPanel.svelte:173`) | present | – | – |
| Click opens the source at that line (⌘ new tab) | `nyit` (`JobbPanel.svelte:116-119`) | present | – | – |
| Pane sections collapsible, state remembered | `Szakasz.svelte:15-28`, persisted (`app/src/lib/elrendezes/felulet.svelte.ts:57,117-122`) | present | – | – |
| Collapse/expand individual source groups ("Collapse results") | none (all groups always expanded) | missing | nice | S | → 02-links-17 |
| Search/filter box inside the pane | none | missing | should | S | → 02-links-11 |
| Sort order (file name A→Z / Z→A, modified, created) | fixed `ORDER BY f.ut` (`olvaso.py:243`) | missing | nice | S | → 02-links-16 |
| "Show more context" (several lines around the link) | one line, ≤400 chars (`olvaso.py:247`), clamped to two visual lines (`Visszahivatkozasok.svelte:136-143`) | missing | nice | M | → 02-links-18 |
| Unlinked mentions: name + aliases, case-insensitive, excluding code / frontmatter / existing links, "Link" button per hit | `emlitesek` (`olvaso.py:254-281`), `emlites_talalatok` mask (`core/index/kereses.py:473-483`), `Emlitesek.svelte:47-55`, write path `emlites.ts:20-56` | present | – | – |
| Unlinked mentions unbounded | 100 source files max, no "more" (`app/src/lib/vault/kapcsolatok.svelte.ts:83`) | partial | nice | S | → 02-links-28 |
| Live refresh as other notes change | `vault_valtozas`/`index` events, 300 ms (`kapcsolatok.svelte.ts:104-122`) | present | – | – |
| Backlinks for attachments (image, PDF) | endpoint accepts any path (`olvaso.py:236-243`), UI loads for any file (`kapcsolatok.svelte.ts:82`) | present | – | – |
| Canvas and property-link sources marked | `Visszahivatkozasok.svelte:16-19` | present | – | – |
| "Backlinks in document" (show backlinks at the bottom of the note — core option, off by default) | nothing in `app/src/szerkeszto/` | missing | nice | M | → 02-links-19 |
| ⌘-hover preview on result rows | none | missing | should | – | part of 02-links-09 |

### 1.8 Outgoing links pane

| Obsidian behaviour | Manifold today | Status | Sev. | Effort |
|---|---|---|---|---|
| Resolved links (icon, name, `> subpath`), unresolved listed separately, click creates | `KimenoLinkek.svelte:24-67` | present | – | – |
| Markdown links included | `fajta: md` kept when `cel_nyers` non-empty (`kapcsolatok.svelte.ts:89`) | present | – | – |
| Duplicates collapsed | `egyedi` (`KimenoLinkek.svelte:24-34`) | present | – | – |
| **Unlinked mentions** section (other notes' names/aliases appearing in *this* note, with a Link button) | not in the pane; the engine exists for the editor assistant: `POST /api/asszisztens/emlitesek` (`core/asszisztens/emlites.py:1-31`, `core/asszisztens/api.py:36-46`) and inline Tab-to-link (`app/src/szerkeszto/asszisztens/javaslat.ts:1-18`) | missing (pane) | should | S | → 02-links-10 |
| ⌘-hover on rows | none | missing | should | – | part of 02-links-09 |

### 1.9 Link format & wikilink/markdown toggle

| Obsidian behaviour | Manifold today | Status | Sev. | Effort |
|---|---|---|---|---|
| "New link format": shortest path when possible / relative path to file / absolute path in vault — used by the suggester, drag-insert, rename rewrite | always shortest unambiguous (`core/index/linkek.py:31-40`, `olvaso.py:303-310`); `newLinkFormat` never read (no match for `newLinkFormat` in `core/` or `app/src/`); rename is style-preserving instead (`linkek.py:176-193`) | missing | should | M | → 02-links-12 |
| "Use [[Wikilinks]]" off → every generated link is `[text](path.md)` (suggester, drag, unlinked-mention Link, search insert, rename of md links) | wikilink hard-coded: `kiegeszites.ts:351`, `csatolmany.ts:67`, `KeresoAblak.svelte:143`, `javaslatSegedek.ts:188-190`; `useMarkdownLinks` never read | missing | should | M | → 02-links-13 |

### 1.10 Link drag from explorer

| Obsidian behaviour | Manifold today | Status | Sev. | Effort |
|---|---|---|---|---|
| Drag a file from the explorer into the editor inserts `[[link]]` (embed for images/media) at the drop point | `VAULT_HUZAS` set on drag (`app/src/hej/Fa.svelte:271-276`), drop → core `linkcel` → `[[…]]` / `![[…]]` for media (`app/src/szerkeszto/csatolmany.ts:56-72,93-101`) | present | – | – |
| Drag a search result / backlink row into the editor | only `Fa.svelte` sets `VAULT_HUZAS`; `KeresoAblak.svelte`, `JobbPanel.svelte` rows are not draggable | missing | nice | S | → 02-links-24 (conf. medium) |
| Paste URL over a selection → `[selection](url)` | `csatolmany.ts:83-90` | present | – | – |

---

## 2. Gaps and proposals

Each proposal stays inside the existing architecture: the UI never resolves links itself (L42, `linkek.svelte.ts:1-6`); anything that needs resolution goes through `/api/vault/feloldas`, `/api/vault/linkcel` or `/api/vault/beagyazas`; settings read from `.obsidian/app.json` follow the `uj_fajl_beallitas` pattern (`core/vaultio.py:402-412`).

### 02-links-01 — Internal markdown links are not navigable or previewable (must, M, high)
*Obsidian:* `[text](note.md)`, `[text](<note with space.md>)`, `[text](note.md#Heading)` open the note on click, ⌘-hover previews, ⌘-click opens in a new tab, both in Live Preview and reading view.
*Manifold:* core resolves them for graph/backlinks/rename (`core/index/feloldas.py:83-102,138`), but the editor only treats `Link`/`Autolink`/`URL` nodes as external (`app/src/szerkeszto/linkek/szerkeszto.ts:40-54`), the reader only marks external URLs (`app/src/szerkeszto/olvaso/html.ts:234-242`), and hover only knows `Wikilink`/`Embed` (`szerkeszto.ts:16-24`).
*Proposal:*
- `app/src/szerkeszto/linkek/adat.ts`: add `mdLinkAdat(n, olvas): LinkAdat | null` for a `Link`/`Image` node whose `URL` is not external (`kulsoCim(url) === null` and not `#`-only): port `md_reszek` (strip `<…>`, `decodeURI`, NBSP → space, split at `#`) and set `cel`/`alcel`/`alias = link text`.
- `szerkeszto.ts`: `linkAt`/`egerLink` fall back to `mdLinkAdat`; `kattintas` and `kulsoLinkAt` keep the external branch, otherwise call `linkMegnyit` with the md target. `LinkCel` already carries raw `cel` to the core, which decodes md targets the same way, so no new endpoint is needed.
- `olvaso/html.ts` `case 'Link'`: when not external, emit the same `span.wikilink[data-cel][data-alcel][data-forras]` contract used for wikilinks (`html.ts:265-278`) so `Olvaso.svelte:68-72` and `domCel` (`elonezet.ts:171-179`) work unchanged.
- `elo/sorok.ts`: decorate internal `Link` as `cm-wikilink` (plus `LinkMark` hiding already in `JELOLO_NEVEK`).
- Tests: extend `app/tests/link-nezet.test.ts` and `app/tests/kulso-link.test.ts` with `[x](a.md)`, `[x](<a b.md>)`, `[x](a.md#H)`, `[x](../a.md)` (after 02-links-03).

### 02-links-02 — No dimmed style for unresolved links (must, M, high)
*Obsidian:* unresolved `[[x]]` get `.is-unresolved` (lower opacity) in LP and reading view, updated live when the target appears.
*Manifold:* single static mark (`app/src/szerkeszto/elo/sorok.ts:33-34`, `app/src/szerkeszto/szerkeszto.css:139-143`), reader static (`html.ts:265-278`, `szerkeszto.css:712-718`).
*Proposal:* a small `ViewPlugin` in `app/src/szerkeszto/linkek/` that collects `Wikilink` targets of `view.visibleRanges`, batches them through `linkek.feloldas(forras, celok)` (already cached per folder and invalidated by `linkek.verzio`, `linkek.svelte.ts:48-53,104-123`) and adds a `cm-wikilink-feloldatlan` mark (token `--szoveg-halvany`, see `docs/dev/DESIGN.md`) to unresolved ones; re-run on `linkek.verzio` change (same hook as `linkekFigyel`, `kiegeszites.ts:433-443`) and on doc change (debounced). Reader: `Olvaso.svelte` after render, query all `.wikilink[data-cel]` the same way and toggle a class. Embeds already use `beagyazas-hianyzo`. No core change: `POST /api/vault/feloldas` accepts up to 500 targets (`core/index/olvaso.py:294`).

### 02-links-03 — `./` and `../` markdown targets do not resolve (should, S, medium)
*Obsidian:* its own "Relative path to file" format writes `../folder/note.md`; such links resolve (confidence medium: inferred from the generator, not verified against source).
*Manifold:* `_elokeszit` (`core/index/feloldas.py:169-174`) never normalises `.`/`..`; `_menet` fails on suffix (`:229-238`).
*Proposal:* in `Feloldo.resolve` (or `_elokeszit` given `src`), when the target starts with `./` or `../`, join with `os.path.dirname(src)` and `posixpath.normpath`, refuse escapes above the root, then run the normal order. Apply only to `fajta == "md"` records if Obsidian does not do it for wikilinks (open Q2). Add cases to `tests/test_index_feloldas.py` and the legacy parity classifier (`feloldas.py:15-25`). Rename: `uj_cel_szoveg` (`core/index/linkek.py:176-193`) must keep the relative style once 02-links-12 exists.

### 02-links-04 — Block suggester cannot mint a `^id` in another note (should, M, high)
*Obsidian:* `[[Other#^` lists all paragraphs/list items of *Other*; choosing one without an id writes `^xxxxxx` into *Other* and inserts the link.
*Manifold:* only `^id` blocks of the other note (`app/src/szerkeszto/linkek/kiegeszites.ts:233-250`); the current note gets a generated id (`:344-350`).
*Proposal:* extend `GET /api/vault/jegyzet` (or add `?blokkok=mind`) so `blokkok` also returns id-less blocks (`kezdo_sor`, `sor`, `szoveg`, `idMod`) computed by the index's block model (`core/index/olvaso.py:222`, `elemzo.py:293-300`); in `blokkElemek` list them with `jelzo: 'új ^id'`; on pick, open the target through `szerkesztok.dokumentumok.megnyit(ut)` and apply `idBeir`/`ujBlokkId` (`app/src/szerkeszto/notion/muveletek.ts:479-511`) on that `Dokumentum` with the hash-guarded save used by `emlitesLinkel` (`app/src/szerkeszto/linkek/emlites.ts:20-56`), then insert the link. If the save conflicts (409), fall back to the "elavult" notification pattern (`emlites.ts:58-61`).

### 02-links-05 — No vault-wide heading search `[[##` (should, M, high)
*Obsidian:* `[[##query` lists matching headings from every note, inserting `[[Note#Heading]]`.
*Manifold:* `lekerdezesElemez` (`kiegeszites.ts:72-81`) has no `##` mode.
*Proposal:* new mode `'fejezetMind'` when `q.cel === ''` and `q.alk` starts with `#`; core endpoint `GET /api/vault/fejezetek?q=&limit=` over the `fejezet` table joined with `fajl` (`core/index/olvaso.py:221` shows the table; register in `core/index/api.py:14-33`), returning `{ut, szint, szoveg, sor}`; fuzzy-rank client-side with `FuzzyIndex` on `szoveg` + `ut`; `beir` builds `${await linkek.linkCel(ut, forras)}#${fejezetLinkSzoveg(szoveg)}`.

### 02-links-06 — Suggester does not re-open when editing inside an existing link (should, M, high)
*Obsidian:* the suggester is driven by the text before the cursor (`EditorSuggest.onTrigger`), so clicking into `[[Jegy|` and typing re-opens it.
*Manifold:* `nyit` is dispatched only from the input handler on `[` (`kiegeszites.ts:486-500`) or the command (`:524-535`); the field closes when the cursor moves out (`:292-297`).
*Proposal:* add an `EditorView.updateListener` (or extend `kiegeszitesMezo.update`) that, on `docChanged` with `userEvent` starting `input.type` and the field closed, scans the current line left of the cursor for an unclosed `[[` / `![[` (no `]]` between) and dispatches `nyit({from, beagyazas})` when `linkNyithato` allows; keep Esc as the explicit "do not re-open on this link" (store `from` in a `StateField` set to ignore until the cursor leaves).

### 02-links-07 — `[[` with a selection drops the selected text (should, S, high)
*Obsidian:* typing `[[` or running "Add internal link" wraps the selection and uses it as the query.
*Manifold:* `linkBeszur` replaces `r.from..r.to` with `[[]]` (`kiegeszites.ts:528-532`); the input handler returns `false` for non-empty selections (`:487`).
*Proposal:* in `linkBeszur`, insert `[[${sel}]]`, set the cursor after `sel`, open with `from = r.from + 2` so `lekerdezes()` equals the selection; in `gepeles`, when `from !== to` and the text is `[` following `[`, do the same. Test next to `app/tests/kiegeszites.test.ts:116`.

### 02-links-08 — Middle-click does not open in a new tab (should, S, high)
*Obsidian:* middle-click on any link = new tab.
*Manifold:* `mousedown` returns for `button !== 0` (`app/src/szerkeszto/linkek/szerkeszto.ts:120`); reader uses `click` only (`Olvaso.svelte:75`); pane rows are buttons with `onclick`.
*Proposal:* extend `nyitasMod` (`navigacio.ts:31-35`) with `button?: number` → `'ujful'` when `button === 1`; handle `auxclick` (editor `domEventHandlers`, `Olvaso.svelte`, `JobbPanel.svelte` rows via `onauxclick`) and `preventDefault` to stop autoscroll.

### 02-links-09 — ⌘-hover preview missing outside the editor (should, S, high)
*Obsidian:* Page preview sources include file explorer, search, backlinks and outgoing links.
*Manifold:* `elonezetKapcsol` is bound only in `szerkeszto.ts:95-108`, `Olvaso.svelte:115`, `Vaszon.svelte:826`.
*Proposal:* call `elonezetKapcsol(root, azonosit)` in `hej/Fa.svelte` (rows carry `data-fa-ut`, `Fa.svelte:266`), `hej/JobbPanel.svelte` (add `data-cel`/`data-forras` on `.fej`/`.link`/`.sor` buttons in the three panes) and `atfedes/KeresoAblak.svelte`; `azonosit` returns `{ link: { cel: ut, alcel, … }, forras: aktiv note or ut, rect }`. The core resolves a full vault path as a target already (`feloldas.py:229-231`), so no new endpoint.

### 02-links-10 — Outgoing links pane has no "Unlinked mentions" (should, S, high)
*Obsidian:* the Outgoing links view has a second section listing other notes mentioned by name in the current note, each with a Link button.
*Manifold:* pane shows resolved/unresolved only (`KimenoLinkek.svelte:24-67`); the mention engine exists for the editor assistant (`core/asszisztens/emlites.py`, `POST /api/asszisztens/emlitesek`, `core/asszisztens/api.py:36-46`), gated by the assistant switch (`api.py:41`).
*Proposal:* add `kimenoEmlitesek` to `Kapcsolatok.frissit` (`app/src/lib/vault/kapcsolatok.svelte.ts:67-100`) calling the same engine with the saved text (or a new `GET /api/vault/kimeno-emlitesek?ut=` wrapper in `core/index/api.py` that bypasses the assistant switch); render under `KimenoLinkek` with a "Linkelés" button reusing `emlitesLinkel` (`emlites.ts:20-56`) with `forras = ful.ut` and `celUt = mention target`.

### 02-links-11 — Backlinks pane has no filter box (should, S, high)
*Obsidian:* search field filters results by text.
*Proposal:* local `$state` query in `Visszahivatkozasok.svelte` (and `Emlitesek.svelte`), filtering `forrasok` by `fajlNev(ut)` and `kornyezet` with `FuzzyIndex` or plain `includes`; keep count in the header.

### 02-links-12 — "New link format" setting not honoured (should, M, high)
*Obsidian:* `newLinkFormat` ∈ `shortest | relative | absolute` in `.obsidian/app.json`; used when inserting and when regenerating links on rename.
*Manifold:* `rovid_cel` only (`core/index/linkek.py:31-40`); rename keeps the author's style (`linkek.py:176-193`), which is better than Obsidian's regeneration and should stay.
*Proposal:* read `newLinkFormat` in `core/vaultio.py` next to `uj_fajl_beallitas` (`:402-412`); `Index.link_cel` (`core/index/olvaso.py:303-310`) returns the format-specific text (`absolute` = `cel_szoveg(ut)`; `relative` = `posixpath.relpath` from the source folder, with `.md` kept for md links); keep `shortest` default. The UI already takes the text verbatim (`linkek.svelte.ts:131-134`, `kiegeszites.ts:127`, `csatolmany.ts:62`, `KeresoAblak.svelte:143`). Rename: when the old link was unambiguous-shortest and the new one cannot be, `_uj_cel`'s fallback (`core/atnevezes.py:236-246`) should also respect the format.

### 02-links-13 — "Use [[Wikilinks]]" off is not honoured (should, M, high)
*Obsidian:* with `useMarkdownLinks: true` every generated link is `[Display](path%20enc.md)`.
*Manifold:* hard-coded wikilinks in `kiegeszites.ts:351`, `csatolmany.ts:67`, `KeresoAblak.svelte:143`, `javaslatSegedek.ts:188-190`.
*Proposal:* expose `linkAlak: 'wiki' | 'md'` through `GET /api/vault/linkcel` (`{ut, cel, alak}`) read from `app.json`; add one helper `linkSzoveg(cel, alias?, alcel?, beagyazas?)` in `app/src/szerkeszto/linkek/adat.ts` that emits either `[[cel#alcel|alias]]` or `[alias ?? name](<cel.md#alcel>)` using the `<…>` wrapper the core already preserves (`linkek.py:158-163`); route the four call sites through it. Suggester after `|`/`#` keeps working on the wiki form and converts at insert time.

### 02-links-14 — Unresolved link texts not offered in the suggester (should, S, medium)
*Obsidian:* link targets that do not exist yet but are used elsewhere appear as suggestions (no path), so spelling stays consistent (confidence medium).
*Proposal:* `GET /api/vault/feloldatlan` (or a field on `/api/vault/index`) from `SELECT DISTINCT cel_nyers FROM link WHERE cel IS NULL` (`core/index/olvaso.py:211-213` shows the columns); include them in `fajlJeloltek` with `jelzo: 'nincs még'` and lower bonus.

### 02-links-15 — `[[^` block shortcut (nice, S, medium)
*Proposal:* in `lekerdezesElemez` (`kiegeszites.ts:72-81`), when `cel` starts with `^` and there is no `#`, treat as `mod: 'blokk'`, `cel: ''`, `alk: cel.slice(1)`.

### 02-links-16 — Backlinks sort order (nice, S, high)
*Proposal:* client-side sort in `Visszahivatkozasok.svelte` using `fajlok.info(ut)?.mtime` (`app/src/lib/vault/fajlok.svelte.ts`) with a small menu (name A→Z / Z→A, modified new→old / old→new); persist in `felulet.jobbPanel`.

### 02-links-17 — Per-source collapse in backlinks / mentions (nice, S, high)
*Proposal:* make `.fej` a disclosure (`aria-expanded`) in `Visszahivatkozasok.svelte:29-33` and `Emlitesek.svelte:38-41`, plus a header "collapse all" toggle next to the count.

### 02-links-18 — "Show more context" (nice, M, high)
*Proposal:* `GET /api/vault/visszahivatkozasok?kornyezet=N` returning `N` lines before/after (`core/index/olvaso.py:244-247` already has the split text); a toggle in the pane that re-fetches and removes the 2-line clamp.

### 02-links-19 — Backlinks at the bottom of the note (nice, M, high)
*Obsidian:* Backlinks core plugin option "Show backlinks at the bottom of notes" (off by default).
*Proposal:* a `Szerkeszto.svelte` footer region rendering `Visszahivatkozasok` for the document's `ut`, reusing `Kapcsolatok` state; setting in `felulet`.

### 02-links-20 — Hover preview "require ⌘" per source (nice, S, high)
*Proposal:* `elonezetKapcsol(root, azonosit, { metaKell })` (`elonezet.ts:134-168`); `horgonyValt(cel, meta || !metaKell)`; settings per source (editor / reader / explorer / panes) in `felulet`.

### 02-links-21 — Nested hover previews (nice, S, medium)
*Proposal:* in `LebegoElonezet.mutat` bind `elonezetKapcsol(pop, domCel)` on the popover (`elonezet.ts:57-88`) and allow a small stack (close children when the parent closes).

### 02-links-22 — Commands "open link under cursor in new tab / to the right" (nice, S, high)
*Proposal:* two more entries in `app/src/szerkeszto/index.ts:119-133` calling `kurzorLinkMegnyit(v, 'ujful' | 'osztas')`.

### 02-links-23 — Link context menu (nice, S, medium)
*Proposal:* in `helyiMenu.ts` `menuElemek`, when `linkAt(state, pos)` (or the md variant after 02-links-01) is non-null, prepend "Megnyitás új fülön", "Megnyitás osztásban", "Link másolása"; the shell path (`helyiMenu.ts:77-80`) forwards the same ids.

### 02-links-24 — Drag from search results / pane rows into the editor (nice, S, medium)
*Proposal:* set `draggable` + `e.dataTransfer.setData(VAULT_HUZAS, ut)` (`csatolmany.ts:7`) on result rows in `KeresoAblak.svelte` and on `.fej`/`.sor` in the three panes; the drop path (`csatolmany.ts:93-101`) needs no change.

### 02-links-25 — Explorer inline rename (nice, M, high)
*Obsidian:* F2 edits the name in the tree row.
*Proposal:* inline `<input>` in the `Fa.svelte` row (same pattern as `FajlCim.svelte:11-38`: Enter → `atnevezesTerv` → `atnevezesVegrehajt`; blockers shown inline); keep the dialog for move and for folders.

### 02-links-26 — Rename with open/unsaved editors (nice, M, high)
*Obsidian:* rewrites links in open editors without closing them.
*Manifold:* `mindLezar()` then 409 `nyitott` guard (`atnevezes.ts:94-107`, `core/atnevezes.py:586-595`).
*Proposal:* keep the guard for the *moving* file, but for *linking* files let the UI apply the plan's per-file `linkek[]` (`atnevezes.ts:14-25`) to open `Dokumentum`s as a transaction after the `kesz` event (`atnevezes.ts:147-163`), instead of forcing close; the core already treats those writes as external changes (`core/atnevezes.py:16-17`).

### 02-links-27 — Suggester refresh by polling (nice, S, high)
*Proposal:* replace the 500 ms interval (`kiegeszites.ts:433-443`) with an `$effect`/subscriber on `linkek.verzio` exposed from `LinkSzolgaltatas` (`linkek.svelte.ts:43`).

### 02-links-28 — Unlinked mentions capped at 100 sources (nice, S, high)
*Proposal:* pass `limit` from a "Továbbiak" button in `Emlitesek.svelte`, or page in `Kapcsolatok.frissit` (`kapcsolatok.svelte.ts:83`); show "100+" in the header when capped.

---

## 3. Manifold strengths beyond Obsidian (preserve)

| Strength | Where |
|---|---|
| One resolver for everything (graph, backlinks, rename, UI) with an explicit **ambiguity flag** (`tobbertelmu`) and a parity classifier against the legacy vault | `core/index/feloldas.py:1-25,182-247`, `core/index/olvaso.py:289-301`, `app/src/lib/vault/linkek.svelte.ts:1-6` |
| Rename as a **plan**: files/lines before→after, blockers with reasons, "hijacked" links detected (links that would re-resolve to a different file after a move), style-preserving rewrite, `.base` expression warnings, Bases/canvas/frontmatter rewrite, atomic exclusive rename, **reference proof** after writing, crash journal + startup recovery, one-click **undo** | `core/atnevezes.py:1-18,236-246,343-356,426-471,486-523,546-565,629-633`, `app/src/atfedes/Atnevezes.svelte:1-6,185-235`, `app/src/szerkeszto/linkek/atnevezes.ts:109-144` |
| Folder move with the same plan, and explorer drag-to-folder opens the plan instead of moving blindly | `core/atnevezes.py:251-319`, `app/src/hej/Fa.svelte:313` |
| Suggester **alias mode** after `\|`, accent-insensitive fuzzy on name and path, recents-first, notes ranked before attachments, "learns" picked targets for the assistant | `app/src/szerkeszto/linkek/kiegeszites.ts:1-12,117-159,258-266,362` |
| Block link to an id-less block in the current note: id minted and written in **one undoable transaction** | `kiegeszites.ts:324-363`, test `app/tests/kiegeszites.test.ts:255` |
| Unlinked-mention "Linkelés" is applied through the document path so it is **⌘Z-undoable** in an open editor, alias-aware display text (`[[Cél\|szöveg]]`), stale-position guard | `app/src/szerkeszto/linkek/emlites.ts:1-61`, `app/src/szerkeszto/asszisztens/javaslatSegedek.ts:188-190` |
| **Inline link suggestions while typing** (unlinked mentions underlined, Tab inserts, similarity-filtered, typing-gated) | `app/src/szerkeszto/asszisztens/javaslat.ts:1-18`, `core/asszisztens/emlites.py:1-31` |
| ⌥↵ in the search dialog inserts a link to the hit (with heading anchor) | `app/src/atfedes/KeresoAblak.svelte:131-150` |
| Media anchors `#t=12:40` (video/audio seek) and `#page=3`, size alias `\|300x200` | `app/src/szerkeszto/linkek/adat.ts:46-69`, `navigacio.ts:87-93` |
| Hover preview from the **keyboard** ("Link előnézete a kurzornál"), same renderer as embeds, "Létrehozás" button for missing targets inside the popover | `app/src/szerkeszto/index.ts:134-147`, `elonezet.ts:52-88`, `rajzol.ts:101-123` |
| New note from a link uses Obsidian's exact placement rule read from the vault's own `app.json`, plus `.cpp` targets become C++ sources | `core/vaultio.py:402-444`, `navigacio.ts:55-60` |
| Backlinks show the **property key** for frontmatter links and a canvas badge; backlinks for any file type | `app/src/hej/kapcsolatok/Visszahivatkozasok.svelte:16-19`, `core/index/olvaso.py:236-252` |
| "Link másolása a blokkra" from the block handle (mints `^id`) and the command palette | `app/src/szerkeszto/notion/blokkfogo.ts:271`, `app/src/szerkeszto/index.ts:96` |
| Paste URL over a selection → markdown link with `<…>` wrapper | `app/src/szerkeszto/csatolmany.ts:83-90` |
| Drag from explorer inserts the **core-decided** shortest target (no client-side shortening rule) | `csatolmany.ts:56-72` |
| Inline file-name editing in the editor header goes through the same plan/proof path | `app/src/szerkeszto/FajlCim.svelte:11-28` |

---

## 4. Open questions

1. **Where do link settings live?** `newFileLocation` is read from `.obsidian/app.json` only (`core/vaultio.py:402-412`). Should `newLinkFormat` / `useMarkdownLinks` (02-links-12/13) also be read-only from `app.json` (Obsidian stays the editor of settings), mirrored into a Manifold setting, or both with precedence?
2. **Relative targets for wikilinks?** Obsidian clearly emits `../` only for markdown links; whether `[[../x]]` resolves is unknown. 02-links-03 proposes md-only until verified against an Obsidian vault.
3. **Heading slug parity.** `alcel_norm` is documented as an approximation (`core/index/linkek.py:45-49`). A fixture of Obsidian-generated `[[note#heading]]` links with punctuation, emphasis, emoji and code spans would settle it.
4. **Flash on arrival.** Obsidian highlights the target line after following a heading/block link; `szerkesztok.ugras` (`navigacio.ts:90-94`) was not inspected for a highlight — verify in `app/src/szerkeszto/szerkesztok.svelte.ts`.
5. **New window.** ⌘⌥⇧-click opens a new window in Obsidian; Manifold is single-window — is multi-window in scope for the shell at all?
6. **Links inside table cells.** Tables are rendered by `TablaSzerkesztoWidget` / `TablaWidget` (`app/src/szerkeszto/elo/blokkok.ts:66-79`); whether wikilinks in cells are clickable/hoverable was not verified (`sorok.ts:337` skips `Wikilink` whose parent is `Table`).
7. **Self-references in backlinks.** Manifold excludes the note's own links (`core/index/olvaso.py:243`); Obsidian's behaviour here is not certain.
8. **"Automatically update internal links" = off.** Manifold always rewrites. Is an opt-out wanted (Obsidian then prompts)? Probably not, but it is an Obsidian setting.
9. **Unlinked mention scope.** Obsidian scans all notes; Manifold pre-filters with FTS and caps at 100 sources (`olvaso.py:266-280`, `kapcsolatok.svelte.ts:83`). Is the FTS prefilter equivalent for accented/hyphenated names (`kereses.fts_kifejezes`)?
10. **Hover popover geometry.** Obsidian's popover follows the mouse and resizes with content; Manifold anchors to the link rect at 440 px (`elonezet.ts:119-128`). Keep as is or match?
