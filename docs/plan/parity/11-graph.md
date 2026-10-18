# 11 — Graph view and Outline: Obsidian-parity audit

Scope: the Manifold graph view (global and local) and the Outline panel compared with Obsidian 1.8/1.9 desktop **core** behaviour (core plugins only). The Backlinks and Outgoing links panes are audited in `02-links.md` (§1.7, §1.8, gaps 02-links-10/11/16/17/18/19/24/28); this document adds nothing there. Paths are relative to `/Volumes/Work/[UNI] Manifold-OS`. Identifiers are Hungarian; user-facing text is out of scope here.

Obsidian side: the official help pages (`obsidian.md/help/plugins/graph`, `.../plugins/outline`, fetched 2026-10-17) describe the graph in detail but the Outline page only three behaviours (list headings, click navigates, drag rearranges sections). Everything about Outline collapse/filter/follow and several graph details (where "Open local graph" opens, whether the local graph follows the active note, depth range, local-graph direction toggles) comes from my knowledge of the product, not from the help pages; those rows carry `confidence: medium` or `low`, and no `must` rests on a low-confidence claim.

Files read: `app/src/graf/{Graf.svelte,GrafVezerlo.svelte,index.ts,memoria.ts}`, `app/src/lib/graf/{modell,beallitasok,rajzolo,lekerdezes,fizika,fizikaGazda,fizikaMotor,kezdoallas}.ts`, `app/src/lib/vault/graf.svelte.ts`, `app/src/lib/elrendezes/{munkaterulet.svelte.ts,felulet.svelte.ts,ikonsav.ts}`, `app/src/hej/kapcsolatok/Vazlat.svelte`, `app/src/hej/JobbPanel.svelte`, `app/src/szerkeszto/{Szerkeszto.svelte,szerkesztok.svelte.ts,Olvaso.svelte}`, `app/src/szerkeszto/linkek/kiegeszites.ts`; core `core/index/{graf_meta.py,olvaso.py,api.py}`; tests `app/tests/graf*.ts`, `app/tests/graf-nezet-nyugalom.svelte.test.ts`, `app/tests/kapcsolatok.test.ts`, `tests/test_index_graf_meta.py`.

Severity: **must** = daily-use Obsidian behaviour users miss immediately · **should** = noticeable · **could** = polish or rarely used. Effort: S (<1 day), M (1–3 days), L (>3 days). Confidence is the confidence in the Obsidian-side claim. Status: present / partial / missing / ahead (Manifold goes beyond Obsidian) / n.a.

**Overall picture.** The graph is a mature, fast implementation (Canvas 2D renderer, physics in a Worker, zero idle CPU, keyboard-complete) that covers the global graph, orphans, attachments, a search-syntax filter, colour groups, force sliders, restore-defaults, hover highlighting and click-to-open. What is missing is mostly the *content* of the graph (no tag nodes, no unresolved-link nodes) and the *workflow* around the local graph (it is a separate tab that does not follow the note you are editing). The Outline pane lists and navigates headings but has none of the tree interactions (collapse, filter, drag-to-rearrange). Two `must`, six `should`, eleven `could`.

---

## 1. Checklist

### 1.1 Graph view — global and local

| Obsidian behaviour | Manifold today | Status | Sev. | Effort | Conf. | Gap |
|---|---|---|---|---|---|---|
| Nodes = notes, lines = internal links; node grows with the number of notes linking to it | nodes = all indexed files, edges = the core graph (`/api/vault/graf`, `core/index/olvaso.py:695-724`, registered `core/index/api.py:27-28`); radius from the total degree `fok` (`app/src/lib/graf/rajzolo.ts:221-224`) | present (size rule differs) | – | – | high | → 11-graph-11 |
| Global graph via ribbon / "Open graph view" | command `graf.megnyit` (`app/src/graf/index.ts:20-28`), icon-rail item (`app/src/lib/elrendezes/ikonsav.ts:29`), module gate `graf` (`app/src/lib/beallitasok/tipusok.ts:1`) | present | – | – | high | – |
| "Open local graph": local graph of the active note | command `graf.helyi` opens a **view tab** with `mod:'helyi'`, centre = the note active at command time (`app/src/graf/index.ts:29-41`, `munkaterulet.svelte.ts:186-205`) | partial | must | M | medium | 11-graph-01 |
| Local graph sits beside the note (split) and re-centres when another note becomes active | the tab replaces the note's view (or sits after it); the centre is frozen in `ful.nezet.kozeppont` (`Graf.svelte:42,58-63`); no effect reads the active file | missing | must | M | medium | 11-graph-01 |
| Depth slider on the local graph | 1–3 step buttons (`Graf.svelte:407-422`); the clamp `MAX_MELYSEG = 3` (`app/src/lib/graf/modell.ts:41`); BFS undirected over the filtered set (`modell.ts:236-254`) | partial | could | S | medium (Obsidian range believed 1–5) | 11-graph-09 |
| Local graph filter: incoming / outgoing / both links | undirected only (`modell.ts:244-249`) | missing | could | S | low | 11-graph-13 |
| Local graph supports all global settings | the same panel and `felulet.graf` apply to both modes (`Graf.svelte:40,457-459`) | present | – | – | high | – |
| Local settings are independent of the global graph's | one shared override object `Felulet.graf` (`app/src/lib/elrendezes/felulet.svelte.ts:92,152,253,437`) | partial | could | S | low | 11-graph-14 |
| Global graph includes notes from every folder; files matching *Excluded files* never appear | no user exclusion (core uses the fixed `SKIP_DIRS`); the Excluded-files setting itself is a gap in the explorer audit | missing | – | – | high | → 07-explorer-13 |

### 1.2 Filters

| Obsidian behaviour | Manifold today | Status | Sev. | Effort | Conf. | Gap |
|---|---|---|---|---|---|---|
| **Search files** with the full search syntax | `lekerdezesFordit` handles words, `path:`, `file:`, `tag:`, `[key:value]`, `OR`, `-`, parentheses, `/regex/` inside operators (`app/src/lib/graf/lekerdezes.ts:1-12`); `line:`, `section:`, `task:`, `content:`, `match-case:` etc. are flagged "not supported" and the filter does not apply (`lekerdezes.ts:39`, warning `GrafVezerlo.svelte:75-77`) | partial | could | M | high | 11-graph-16 |
| **Tags** toggle: tags become nodes | none; tags exist only as per-note metadata for the filter and the tooltip (`core/index/graf_meta.py:35-52`, `modell.ts:169-186`, tooltip `Graf.svelte:477`) | missing | should | M | medium | 11-graph-03 |
| **Attachments** toggle | checkbox, hides every non-md/canvas/base node (`modell.ts:43,195-197,230`; `GrafVezerlo.svelte:78`) | present | – | – | high | – |
| **Existing files only** off: unresolved link targets appear as (dim) nodes | not available. The core already counts unresolved targets (`feloldatlan`, `olvaso.py:700-710,718`) and the client types the field (`modell.ts:14`), but nothing reads it and no source→target edge is delivered (`rg feloldatlan app/src/graf app/src/lib/graf` finds only the type) | missing | must | M | high | 11-graph-02 |
| **Orphans** toggle | checkbox, hides degree-0 nodes (`modell.ts:231`; `GrafVezerlo.svelte:79`) | present | – | – | high | – |
| Filter state persists; "Restore default settings" | persistent overrides (`felulet.svelte.ts:253,437`); reset button (`GrafVezerlo.svelte:121-123`) restores the `graph.json` values | present | – | – | high | – |
| `.obsidian/graph.json` is the settings store | **read-only** import of search, attachments, orphans, arrows, size/line multipliers, text fade, forces, colour groups (`core/index/graf_meta.py:74-113`, `app/src/lib/graf/beallitasok.ts:50-76`); Manifold never writes it back (by design, `beallitasok.ts:3-4`) | partial (by design) | – | – | high | see §3 |

### 1.3 Groups

| Obsidian behaviour | Manifold today | Status | Sev. | Effort | Conf. | Gap |
|---|---|---|---|---|---|---|
| New group = query + colour; several groups | add / edit / delete up to 30 groups, colour input, query per group, first matching group wins (`GrafVezerlo.svelte:84-107`, `beallitasok.ts:36`, `modell.ts:277`); groups are seeded from `graph.json` | present | – | – | high | – |
| Group colour carries an opacity channel | `graph.json` alpha is read (`graf_meta.py:94-95`, `beallitasok.ts:21`) and then dropped when the effective list is built (`beallitasok.ts:73`); the UI is a plain `<input type="color">` | partial | could | S | medium | 11-graph-12 |
| Unsupported query in a group is reported | `aria-invalid` plus a message (`GrafVezerlo.svelte:97,102`) | ahead | – | – | – | §3 |

### 1.4 Display and forces

| Obsidian behaviour | Manifold today | Status | Sev. | Effort | Conf. | Gap |
|---|---|---|---|---|---|---|
| **Arrows** | checkbox (`GrafVezerlo.svelte:80`), drawn by `rajzolo.ts:604-605,615` | present | – | – | high | – |
| **Text fade threshold** slider | none. `textFadeMultiplier` is imported (`graf_meta.py:110`, `beallitasok.ts:19`) but no code reads it (`rg szoveg_halvanyitas app/src` finds only the type); label opacity is a fixed function of node radius (`rajzolo.ts:732`) | missing | should | S | high | 11-graph-04 |
| **Node size** slider | multiplier only from `graph.json` (`beallitasok.ts:74`, applied `rajzolo.ts:221`); no UI control, no per-user override (`GrafFeluliras` has no field, `beallitasok.ts:42-49`) | partial | should | S | high | 11-graph-04 |
| **Link thickness** slider | multiplier only from `graph.json` (`beallitasok.ts:75`, applied `rajzolo.ts:551`); no UI control | partial | should | S | high | 11-graph-04 |
| **Animate** time-lapse (nodes appear in creation order) | none. The index stores only `mtime_ns`; there is no creation time (`core/index/tar.py:21-36`; gap 07-explorer-01 step 4) | missing | could | M | high | 11-graph-10 |
| **Center / Repel / Link force, Link distance** sliders | four sliders (centre, repel, spring, spring length) as multipliers of the defaults; `graph.json` values are mapped onto them (`beallitasok.ts:28-33,47-56`; `GrafVezerlo.svelte:109-119`; physics `app/src/lib/graf/fizika.ts`) | present | – | – | high | – |

### 1.5 Interaction

| Obsidian behaviour | Manifold today | Status | Sev. | Effort | Conf. | Gap |
|---|---|---|---|---|---|---|
| Hover highlights the node and its neighbours | focus/fade transition on hover and selection (`rajzolo.ts:434-440,478-485,536-610`), plus a tooltip with name, path, degree and tags (`Graf.svelte:473-479`) | present | – | – | high | – |
| Click opens the note; modifier-click opens in a new tab / split | click opens in the active tab, ⌘/Ctrl new tab, ⌘⌥ split (`rajzolo.ts:804,849`); Enter / Shift+Enter on the selected node (`rajzolo.ts:949-951`); a note opened from the graph never overwrites the graph tab (`app/tests/graf_munkaterulet.test.ts:29`) | present | – | – | high | – |
| Right-click a node opens a context menu | `pointerdown` returns for any button other than the primary (`rajzolo.ts:786`); no `contextmenu` handler exists in `app/src/graf` or `app/src/lib/graf` | missing | should | S | high (help page states it) | 11-graph-05 |
| Middle-click opens in a new tab | not handled (same line); confidence of the Obsidian claim is low (not on the help page) | missing | could | S | low | 11-graph-15 |
| ⌘-hover shows a page preview of the node | none | missing | – | – | medium | → 02-links-09 |
| Drag a node; it relaxes after release | drag pins the node, release lets go, Alt keeps it fixed (`rajzolo.ts:822,859`) | present | – | – | high | – |
| Zoom: wheel, `+` / `-`; pan: drag, arrow keys, Shift+arrows faster | wheel and trackpad pinch incl. Safari `gesture*` events (`rajzolo.ts:884-912`), `+`/`-`/`0` and arrow keys at a fixed 90 px step (`rajzolo.ts:917-948`); no faster step with Shift | partial | could | S | high (help page) | 11-graph-15 |
| Find a node by name | search box with fly-to, arrow keys, `/` and ⌘F focus (`Graf.svelte:324-376,423-452`) — not an Obsidian core feature | ahead | – | – | – | §3 |

### 1.6 Outline

| Obsidian behaviour | Manifold today | Status | Sev. | Effort | Conf. | Gap |
|---|---|---|---|---|---|---|
| Lists the headings of the active note; updates as you type | section "Vázlat" of the right panel (`app/src/hej/JobbPanel.svelte:199-203`) fed from the live CodeMirror syntax tree, ATX and Setext, code/comments excluded by construction (`Vazlat.svelte:9-17`, `Szerkeszto.svelte:307`, `app/src/szerkeszto/linkek/kiegeszites.ts:239-253`); recomputed on every document change (`valtozat()`, `szerkesztok.svelte.ts:27-29`) | present | – | – | high | – |
| Click navigates to the section (Reading, Live Preview, Source) | `peldany.ugras(sor)` (`Vazlat.svelte:27`); Reading mode scrolls via `olvaso.gorget` (`Szerkeszto.svelte:295-305`); test `app/tests/kapcsolatok.test.ts:155-172` | present | – | – | high | – |
| Heading tree with collapsible parents; collapse-all / expand-all | flat list, indented by level relative to the shallowest heading (`Vazlat.svelte:16,26`); no disclosure arrows, no state | missing | should | S | medium | 11-graph-06 |
| Filter box in the pane header | none | missing | should | S | medium | 11-graph-07 |
| Drag a heading in the outline to rearrange the sections in the note | none; rows are plain buttons | missing | should | M | high (help page) | 11-graph-08 |
| Current heading is indicated while you scroll or move the cursor | no active-row state | missing | could | S | low | 11-graph-17 |
| Outline of non-Markdown files (PDF table of contents) | section shows "no open note" unless a Markdown editor is active (`Vazlat.svelte:9,19-20`) | missing | could | M | low | 11-graph-18 |
| Empty states | "Nincs megnyitott jegyzet." / "A jegyzetben nincs fejezet." (`Vazlat.svelte:19-23`) | present | – | – | – | – |
| Module can be switched off | gate `vazlat` (`JobbPanel.svelte:199`) | ahead (settings-level) | – | – | – | – |

### 1.7 Backlinks and Outgoing links

Covered entirely by `02-links.md` (§1.7, §1.8). No additional behaviour found: the pane filter, sort, collapse and "more context" gaps are 02-links-11/16/17/18; in-document backlinks is 02-links-19; hover preview on rows is 02-links-09. Entry points for "open the Backlinks / Outgoing links pane as a tab" are a layout matter (06-workspace S6).

---

## 2. Gaps and proposals

Proposals stay inside the existing layering: the UI never resolves links or invents edges (`LEGACY-SZERZODESEK.md` L42), so every graph *content* change is a core extension of `/api/vault/graf` and `graf-meta`; display and interaction changes are UI only.

### 11-graph-01 — Local graph beside the note, following the active note (must, M, medium)
**Obsidian.** "Open local graph" shows the notes connected to the active note, in a pane beside it; as another note becomes active the local graph re-centres on it (confidence: medium — the help page names only the command).
**Manifold.** `graf.helyi` creates a view tab centred on the note active at invocation (`app/src/graf/index.ts:29-41`, `Munkaterulet.megnyitNezet` `munkaterulet.svelte.ts:186-205`). The centre lives in `ful.nezet.kozeppont` and never changes unless the user toggles modes (`Graf.svelte:42,58-73`); nothing observes the active file. The note and its local graph cannot be seen together without manually splitting.
**Proposal.** (1) Add an option to `megnyitNezet` to open the view in a split next to the active group (the split API exists in `munkaterulet.svelte.ts`), used by `graf.helyi`. (2) Give the local view a "follow" state (`ful.nezet.kovet`, default true for commands launched from a note): an `$effect` in `Graf.svelte` watching the active note of the neighbouring group (`felulet.munkaterulet.aktivFul?.ut`, ignoring view tabs) and, when it is a graph node, setting `kozeppont` and calling `ujIllesztes()`. A pin toggle in the toolbar turns following off. (3) Keep the layout memory (`memoria.ts`) global-only as today. Test in `app/tests/graf_munkaterulet.test.ts` style: opening a second note re-centres; pin stops it.

### 11-graph-02 — Unresolved-link nodes and the "Existing files only" toggle (must, M, high)
**Obsidian.** *Existing files only* hides link targets that are not notes; with it off (the default state of the graph), unresolved targets appear as dim nodes connected to their sources.
**Manifold.** The graph contains files only. The core computes `unresolved` and sends per-target counts (`olvaso.py:700-710,718`) but not which note links to which target, and the client never consumes them. The default Manifold view therefore shows fewer nodes and edges than the same vault in Obsidian.
**Proposal.** Core: extend `graf_api` with `feloldatlan_elek: [[forras_ut, nyers_cel], …]` (de-duplicated per source, normalised like the existing counter key) — pure additions, the `/api/vault/graf` contract stays backward compatible and the ETag/generation cache already covers it (`olvaso.py:722-724`). UI: `GrafAdat` appends virtual nodes (`tipus: 'feloldatlan'`, no path, not openable — click offers "create note" using the existing create-note flow, `02-links-1.3`) when `felulet.graf.letezoCsak === false`; style: muted, dashed ring; the `fok` of real nodes must not change so orphan semantics stay the same. Add the toggle to `GrafVezerlo.svelte` ("Existing files only") and `beallitasok.ts` (`existingOnly` from `graph.json`, which `graf_beallitasok` does not yet export). Decide the default (open question 1). Ambiguous links (`tobbertelmu`) stay out of scope.

### 11-graph-03 — Tags as nodes (should, M, medium)
**Obsidian.** The *Tags* filter toggles tags as nodes, linked to the notes that carry them.
**Manifold.** Tags are only metadata (`graf_meta.py:35-52`).
**Proposal.** Core-side, like 02: a `graf-meta`/`graf` extension that lists tag nodes and note→tag edges from the same `cimke` table (`graf_meta.py:42-48`); UI toggle `cimkek` (off by default) rendering a distinct small shape, clicking a tag node opens search (`tag:#…`) through the existing tag navigation (`03-properties-02`). Keep nested-tag handling simple at first (each full tag a node); hierarchy is an open question.

### 11-graph-04 — Node size, link thickness and text-fade controls (should, S, high)
**Obsidian.** Display section: Text fade threshold, Node size, Link thickness.
**Manifold.** Node-size and link-thickness multipliers exist in the renderer (`rajzolo.ts:221,551`) but only `graph.json` can set them (`beallitasok.ts:74-75`; `GrafFeluliras` has no field, `:42-49`). Text fade is imported (`graf_meta.py:110`) and ignored.
**Proposal.** Add `meretSzorzo`, `vonalSzorzo`, `szovegHalvany` to `GrafFeluliras`/`feluliras`/`effektiv` (with range clamps like `EROK_TARTOMANY`), a "Display" section with three sliders in `GrafVezerlo.svelte` beside the arrows checkbox, and wire the fade value into the label-alpha curve (`rajzolo.ts:732`, `simitas(6.5, 10, r)` → threshold shifted by the setting). Extend `app/tests/graf_beallitasok.test.ts`.

### 11-graph-05 — Node context menu (should, S, high)
**Obsidian.** Right-click a node: a menu of note actions (the help page confirms existence, not the exact items).
**Manifold.** No handler (`rajzolo.ts:786`).
**Proposal.** `contextmenu` event on the canvas → callback `menu(i, x, y)` in the renderer options; `Graf.svelte` opens the shared floating menu (the explorer already has one, `app/src/hej/Fa.svelte:229-247`) with: Open, Open in new tab, Open to the right, Show in file tree (`Felulet.megmutatFaban`), Open local graph here, Copy path. Keyboard: Shift+F10 / ContextMenu key on the selected node (the canvas is already focusable). Items for virtual unresolved nodes (gap 02): Create note.

### 11-graph-06 — Outline collapse and expand (should, S, medium)
**Obsidian.** Parent headings in the outline collapse; there are collapse-all / expand-all controls (confidence: medium).
**Manifold.** Flat list (`Vazlat.svelte:24-30`).
**Proposal.** Build the nesting from `szint` in `Vazlat.svelte`; a disclosure arrow on rows that have children; a header action "Collapse all / Expand all"; keep collapsed state per note path in memory (not persisted) and reset when headings change level. Keep rows as buttons; arrow is a separate button with `aria-expanded`.

### 11-graph-07 — Outline filter (should, S, medium)
**Obsidian.** A search-filter toggle in the outline header filters headings by text (confidence: medium).
**Manifold.** None.
**Proposal.** A text field in `Vazlat.svelte` using the shared accent-insensitive matcher (the same one used by the graph search, `app/src/lib/graf/lekerdezes.ts` `egyszerusit`, or `FuzzyIndex` used in `kiegeszites.ts:276`); ancestors of matches stay visible; Escape clears. Hidden unless the section has more than a few rows (quiet by default).

### 11-graph-08 — Drag headings to rearrange sections (should, M, high)
**Obsidian.** Dragging a heading in the Outline moves the corresponding section in the note.
**Manifold.** None.
**Proposal.** Drag handle on rows; a section is the heading line through the line before the next heading of the same or higher level. The drop computes a single CodeMirror transaction (delete range + insert at the target position) so it is **one undo step**, adjusts nothing else, and refuses when the note is read-only or conflicted (data-safety rules: no write outside the normal save path). Level adjustment on drop (re-parenting a section under a deeper heading) is out of scope for the first version — move the block only. Needs a new test in the `app/tests/` CodeMirror helpers; Reading-mode notes must switch to an editable state first or disable the drag.

### 11-graph-09 — Local-graph depth beyond 3 (could, S, medium)
**Obsidian.** Depth slider (believed 1–5).
**Manifold.** `MAX_MELYSEG = 3` (`modell.ts:41`), step buttons (`Graf.svelte:407-422`).
**Proposal.** Raise the cap to 5 and replace the buttons by a labelled range input; the BFS cost is linear in the visible set. Guard the physics for very large visible sets (existing worker path).

### 11-graph-10 — Time-lapse animation (could, M, high)
**Obsidian.** *Animate* replays the vault growing in creation-time order.
**Manifold.** No creation time in the index (`tar.py:21-36`). Depends on the `btime_ns` proposal in `07-explorer-01`; with it, a play/pause/scrub control that reveals nodes in creation order by masking the visible set (`lathatosag` already produces a mask) and feeding the existing `aktiv` physics message (`Graf.svelte:289`). Respect `prefers-reduced-motion` (jump, do not animate).

### 11-graph-11 — Node size from incoming links (could, S, high)
**Obsidian.** A node grows as more other notes link to it.
**Manifold.** Radius from total degree (`rajzolo.ts:223`, `fok` counts both directions, `modell.ts:148-157`).
**Proposal.** Add `bejovo` (in-degree) to `GrafAdat` from the directed edge list (`iranyitott`) and use it for the radius; keep `fok` for orphan logic and label priority. Single-source-of-truth: derive from existing data only.

### 11-graph-12 — Colour-group opacity (could, S, medium)
**Obsidian.** Group colours may carry an alpha.
**Manifold.** `alfa` is read from `graph.json` and discarded when the groups are mapped (`beallitasok.ts:73`). Carry `alfa` through `SzinCsoport`, apply it to the node fill, add an opacity slider next to the colour input.

### 11-graph-13 — Local graph: incoming / outgoing toggles (could, S, low)
Newer Obsidian versions are believed to offer direction filters on the local graph; not on the help page. If confirmed, extend the BFS in `lathatosag` (`modell.ts:244-249`) with a direction mask using the directed edge list.

### 11-graph-14 — Separate settings for local and global graphs (could, S, low)
`Felulet.graf` is shared (`felulet.svelte.ts:152`). Split into `graf.globalis`/`graf.helyi` with the local one inheriting unset fields; migrate on load (`feluliras`, `beallitasok.ts:84-110`). Low confidence about the Obsidian behaviour.

### 11-graph-15 — Shift+arrow fast pan and mouse-button parity (could, S, high/low)
Help page: Shift with the arrow keys moves faster. Add a larger step when `e.shiftKey` in the keydown handler (`rajzolo.ts:933-948`; today Shift only changes Enter). Middle-click as "open in new tab" (low confidence) belongs with the context-menu work (`rajzolo.ts:786`).

### 11-graph-16 — Breadth of the graph search syntax (could, M, high)
Unsupported operators (`content:`, `line:`, `section:`, `task:`, `match-case:`; `lekerdezes.ts:39`) silently switch the filter off with a warning. `content:` could be served by the core's lexical search (`core/index/kereses.py`) as an extra endpoint returning a path set; the other operators have little value in a graph. Keep today's honest "not supported" message until the endpoint exists.

### 11-graph-17 — Active-heading indication in the Outline (could, S, low)
Highlight the heading containing the cursor (Source/LP) or the topmost visible heading (Reading), without stealing focus. Derive from the same syntax tree and `view.state.selection`; throttle on scroll.

### 11-graph-18 — Outline for non-Markdown views (could, M, low)
PDF table of contents and canvas groups could feed the same list component; defer until the PDF viewer exposes an outline.

### 11-graph-19 — Entry points for the local graph (could, S, high)
Today the local graph exists as a command (`graf.helyi`) only. Add it to the note's tab/file menu and the editor header (the explorer file menu is in `Fa.svelte:240-247`) so users find it without the palette.

---

## 3. Manifold strengths beyond Obsidian (preserve)

1. **Zero idle cost.** The renderer schedules nothing at rest, the physics runs in a Worker and pauses when the page is hidden (`Graf.svelte:1-6,305-310`; test `app/tests/graf-nezet-nyugalom.svelte.test.ts`); content-only saves return `304` through ETag caching (`app/src/lib/vault/graf.svelte.ts:1-14`, `core/index/api.py:27-28`; test `app/tests/graf_store.test.ts:41`).
2. **Layout memory.** Switching tabs keeps positions and zoom; only changed nodes move (`memoria.ts`, `kezdoallas.ts`, `Graf.svelte:140-184`).
3. **Fly-to node search** with fuzzy name matching that can lift a filter to reveal a hidden node (`Graf.svelte:324-366`).
4. **Full keyboard model and ARIA.** Canvas is a focusable application region with a spoken summary, `+ - 0`, arrows, Enter / Shift+Enter, Escape (`Graf.svelte:378-394`, `rajzolo.ts:917-958`); reduced-motion handling (`Graf.svelte:139-143`).
5. **Honest filtering.** Unsupported query elements are named, never silently applied (`GrafVezerlo.svelte:75-77,97-102`), and the graph never invents edges (`modell.ts:3-4`; test `app/tests/graf_modell.test.ts:45`).
6. **`graph.json` import with force mapping** onto relative sliders, an explicit "restore to graph.json" and a read-only guarantee for the vault config (`graf_meta.py:74-113`, `beallitasok.ts:47-56`; test `tests/test_index_graf_meta.py:108`).
7. **Tooltip with path, degree and tags** and a visible status line "N / M nodes · E edges" (`Graf.svelte:461-479`).
8. **Live Outline from the editor's syntax tree**, so headings inside code fences or comments never appear and Setext headings do (`kiegeszites.ts:239-253`), with a module gate.

---

## 4. Open questions

1. **Default of "Existing files only"** — Obsidian shows unresolved nodes by default; showing them by default in Manifold increases noise in large vaults. Match Obsidian, or default to existing-only with a visible toggle?
2. **Nested tags as nodes** — one node per full tag, or a hierarchy (`a`, `a/b`)? I am unsure how Obsidian builds the tag nodes.
3. **Where "Open local graph" opens** and whether the local graph really follows the active note in current versions — please confirm in the running app; gap 01 is `must` on the strength of long-standing behaviour, not the help page.
4. **Excluded files and the graph** — decided in `07-explorer-13`; this audit assumes the core will hide excluded paths from `/api/vault/graf` once that exists.
5. **Outline drag semantics** — move the block only, or re-level the moved section to the drop context (Obsidian behaviour not confirmed)?
6. **Time-lapse (10)** needs a birth-time column; is a mtime fallback acceptable for non-APFS volumes (same question as 07 open question 7)?
7. **Outline as an independent pane** (dockable, separate from the right panel) is a layout question for `06-workspace` S6, not decided here.
