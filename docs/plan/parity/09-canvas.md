# 09 — Canvas (JSON Canvas): Obsidian-parity audit

**Subsystem:** the `.canvas` view (`app/src/canvas/`), its write path (`core/vaultio.py`), and the way canvases take part in links, backlinks, search, graph, rename and embeds.
**Reference:** Obsidian 1.8/1.9 desktop, core Canvas plugin only, plus the JSON Canvas 1.0 specification. READ-ONLY audit of `/Volumes/Work/[UNI] Manifold-OS`; every code claim cites `path:line` relative to that root.
**Obsidian sources (fetched 2026-10-17, paraphrased, nothing quoted):** the JSON Canvas 1.0 spec (`jsoncanvas.org/spec/1.0`) and the official Canvas help page (`obsidian.md/help/plugins/canvas`; the old `help.obsidian.md/plugins/canvas` URL now redirects there). Anything the help page does not state is marked with a lower confidence.
**Code read:** `app/src/canvas/{modell,json,iro,geometria,muveletek,elozmeny,forras,tartalom,beagyazas,index,aktiv.svelte}.ts`, `Vaszon.svelte`, `Kartya.svelte`, `Eszkoztar.svelte`, `FajlValaszto.svelte`, `CanvasFul.svelte`, `canvas.css`; `app/src/szerkeszto/beagyazas/rajzol.ts`, `szerkeszto/olvaso/html.ts`, `szerkeszto/Olvaso.svelte`, `szerkeszto/linkek/{kulso,navigacio}.ts`, `hej/Fa.svelte`, `hej/kapcsolatok/Visszahivatkozasok.svelte`, `lib/elrendezes/ikonsav.ts`, `app/index.html`; core `vaultio.py`, `atnevezes.py`, `index/{elemzo,feloldas,indexelo,olvaso,linkek}.py`, `higienia.py`; tests `app/tests/canvas-*.test.ts`, `app/tests/f11-embeds-kulso.test.ts`, `tests/test_atnevezes.py`; docs `docs/dev/ARCHITECTURE.md:218-220`, `docs/dev/DECISIONS-v2.md` (41), `docs/plan/parity/04-embeds.md` (17), `08-search.md` (R25), `06-workspace.md` (S1).

**Legend.** Status: *present* / *partial* / *missing* / *ahead* (stronger than Obsidian — protect it) / *by design* (a deliberate product rule, not a defect). Weight: **must** = blocks daily use, loses data or breaks interchange with Obsidian; **should** = noticed within the first weeks; **could** = polish or rare. Size: S (<1 day), M (1–3 days), L (>3 days). Confidence marks the Obsidian side: **high** = stated by the spec or the help page, or daily-use behaviour I am sure of; **medium** = remembered or paraphrased from the help page, verify in the app before building; **low** = uncertain, no weight above *could* rests on it. Gap ids `09-canvas-NN` point to chapter 2.

---

## 0. Summary

The canvas is Manifold's most Obsidian-faithful subsystem and in several places ahead of Obsidian. It implements the whole JSON Canvas 1.0 data model, keeps unknown keys and the file's own formatting byte for byte, writes through the same single save path as notes (autosave, conflict dialog, external-change reload, exit-save), refuses to save an invalid canvas in the core, and plugs the canvas into links, backlinks, search, graph and the rename planner. Cards render live (notes, images, audio/video), off-screen cards cost nothing, and the whole view is keyboard-reachable.

What is missing is the *authoring convenience layer* an Obsidian user reaches for on day one: dragging notes onto the canvas, copy/paste, right-click menus, "convert to file", re-attaching an edge, snap-to-objects, in-place editing of note cards, and PDF/Bases content inside cards. There is one **must**: task checkboxes in text cards look interactive but write nothing (static reading of the code, no run; confirm with a test first). Result of this audit: **1 must, 14 should, 12 could** (the could-level items are listed in chapter 2 but not in the checklist fragment).

Two statements elsewhere in the repo are stale and should be corrected when this audit is adopted: `docs/plan/NAPLO.md:205` says canvas-card refresh is still open, but `app/src/canvas/tartalom.ts:48,68` wires the per-target refresh and `app/tests/f11-embeds-kulso.test.ts:172-208` tests it; and `docs/plan/f11/CHECKLIST.md` (04-embeds-07) repeats that remainder.

---

## 1. Checklist

### 1.1 File format (JSON Canvas 1.0)

| # | Obsidian / spec behaviour | Manifold today (path:line) | Status | Weight | Size | Conf. | Gap |
|---|---|---|---|---|---|---|---|
| 1 | Root has optional `nodes` and `edges`; an empty file or `{}` is a valid empty canvas | `modell.ts:75-78` (empty text → `{}`), `:44-48,87-88`; new canvas is `{}` `vaultio.py:52`; writer gives the Obsidian-native shape `iro.ts:1-14` | present | – | – | high | – |
| 2 | Every node has `id`, `type`, integer `x y width height`, optional `color` | `modell.ts:15-30,90-101` (non-numbers fatal, non-integers a warning), moves/resizes round to integers `muveletek.ts:40-41,59`, `geometria.ts:205` | present | – | – | high | – |
| 3 | Four node types: `text`, `file` (+`subpath` starting with `#`), `link`, `group` (`label`, `background`, `backgroundStyle`) | all four modelled and drawn `Kartya.svelte:53-157`; `subpath` read `Kartya.svelte:95,128`; unknown types kept and drawn as a titled box `modell.ts:98`, `Kartya.svelte:75` | present (group background: see 17) | – | – | high | 17 |
| 4 | Colour is a preset `"1"`–`"6"` or a hex string | presets mapped to tokens `modell.ts:128-142`, `tokens.css:110-121`; hex accepted only as 3/6 digits `modell.ts:141`; the palette can set presets or clear, never a custom hex `Eszkoztar.svelte:60-91` | partial | should | S | medium | 12 |
| 5 | Edges: `fromNode`/`toNode`, optional sides, ends (`fromEnd` default `none`, `toEnd` default `arrow`), `color`, `label` | `modell.ts:32-42,56-58`; direction writes keep absent defaults absent `muveletek.ts:105-122`; side defaults to the facing side `geometria.ts:127-132,160-183` | present | – | – | high | – |
| 6 | The `nodes` array is the z-order (first = bottom) | render in array order `Vaszon.svelte:902-917`; new group inserted below the first non-group `muveletek.ts:65-72`; no raise/lower | present (z-commands: see 22) | – | – | high | 22 |
| 7 | Unknown keys, unknown node types and extension fields survive an edit | the model *is* the parsed JSON `modell.ts:1-4`; the patcher only replaces changed literals `iro.ts:1-14`; tests `canvas-iro.test.ts:175,189` | ahead | – | – | high | – |
| 8 | A file that is valid per the spec opens | fatal when a node *and* an edge share an `id` (one shared id set) `modell.ts:89-94,106`, although the spec asks for uniqueness per collection; any other deviation is a warning | partial | should | S | medium | 15 |
| 9 | Hand-edited or Obsidian-written files are not reformatted on save | byte-faithful patching in the file's own style (Obsidian-compact, `indent=1/2/tab`), self-check before write `iro.ts:1-14`, `forras.ts:74-94`; tests `canvas-iro.test.ts:105-196`, `canvas-nezet.svelte.test.ts:140-156` | ahead | – | – | high | – |
| 10 | (not in Obsidian) invalid JSON Canvas never reaches disk | core validates on save and answers 400 `vaultio.py:378-381`; the view opens read-only with line/column `modell.ts:83`, `CanvasFul.svelte:100-123` | ahead | – | – | high | – |

### 1.2 Cards

| # | Obsidian behaviour | Manifold today (path:line) | Status | Weight | Size | Conf. | Gap |
|---|---|---|---|---|---|---|---|
| 11 | Text card: create from the bottom bar or by double-clicking the canvas; edit on double-click/Enter; Markdown, links, code | toolbar `Eszkoztar.svelte:96`, double-click `Vaszon.svelte:629-632`, `:258-265`; editor is CodeMirror with Live Preview and `[[` completion `:332-392`; rendered by the Reader renderer `tartalom.ts:35-50` | present | – | – | high | – |
| 12 | Tasks (`- [ ]`) in a text card can be ticked and the change is saved | the shared renderer emits an enabled checkbox with no read-only flag `html.ts:533-548`, `tartalom.ts:36-46`; the only handlers are the Reader's (`Olvaso.svelte:157-159`, ignores embed-flagged boxes) and the embed one (`rajzol.ts:250-265`, only inside `.beagyazas-torzs`); the canvas ignores input clicks `Vaszon.svelte:459,463`, so the box toggles on screen and is never written | missing (misleading) | **must** | S | medium | 01 |
| 13 | Note card (file node): live content, optionally narrowed to a heading or block (`subpath`) | live embed with the core slicer, cycle/depth guard, ≤6 concurrent requests `tartalom.ts:52-70`, `Kartya.svelte:95`; refreshes when the note is saved `tartalom.ts:68`, test `f11-embeds-kulso.test.ts:199-208`; no UI to choose or change the heading/block | partial | should | M | high | 13 |
| 14 | Note card can be edited inside the card | read-only render; double-click/Enter opens the note in a tab `Vaszon.svelte:320-326,638`; note-card checkboxes are disabled with an explanatory title `rajzol.ts:254-258` (`kompakt: true`, `tartalom.ts:64`) | missing (by design so far) | should | L | high | 09 |
| 15 | Media cards: images, audio, video | DPR-bucketed downscaled images `tartalom.ts:73-87`, `Kartya.svelte:78`; native `<audio>/<video>` with core poster `tartalom.ts:89-110` | present (images ahead) | – | – | high | – |
| 16 | PDF in a card shows the document | chip with icon and name only `Kartya.svelte:142-143`; the effect clears the body for every type except md/image/video/audio `:88-98` although the PDF embed viewer exists (`media/pdf/beagyazas.ts`) | partial | should | M | high | 07 |
| 17 | `.base` file in a card shows the Bases view (help page; 1.9) | chip only `Kartya.svelte:142-143`; Manifold already renders `![[x.base]]` (`bazis/beagyazas.ts`, per 04-embeds row 38) | partial | should | M | medium | 08 |
| 18 | Unrecognised file types and nested `.canvas` | chip with icon and name `Kartya.svelte:142-143`; a missing target shows a "not found" message and a dimmed card `Kartya.svelte:140-141` | present | – | – | medium | – |
| 19 | Folder card (drag a folder in → all its files become cards) | none | missing | could | M | medium | 21 |
| 20 | Swap the file of a note/media card | none | missing | could | S | medium | 21 |
| 21 | Web-page card: live page in the card, open/copy/change URL/reload | link card shows host name and URL only `tartalom.ts:113-129`; opens in the system browser through the shell, `http/https/mailto` only `kulso.ts:11-30`; CSP has no `frame-src`, so a page frame cannot load `app/index.html:8-10` | by design (D3: no runtime network) | could | M | high | 23 |
| 22 | Convert a text card to a note ("Convert to file") | none | missing | should | M | high | 05 |
| 23 | Open a card's target: double-click, Enter, toolbar, ⌘/⌘⌥ for tab/split | `Vaszon.svelte:320-326,638,692-695`, `Eszkoztar.svelte:120-122`, `nyitasMod` | present | – | – | high | – |

### 1.3 Edges and groups

| # | Obsidian behaviour | Manifold today (path:line) | Status | Weight | Size | Conf. | Gap |
|---|---|---|---|---|---|---|---|
| 24 | Draw an edge by dragging from a card's edge handle onto another card | side handles `Kartya.svelte:153-157`, drag `Vaszon.svelte:478-481`, create on release `:569-582` | present | – | – | high | – |
| 25 | Releasing on empty space creates a new card there | the release is ignored when no card is under the pointer `Vaszon.svelte:571-573` | missing | should | M | high | 06 |
| 26 | Drag an edge end to another card or side to reconnect; drag away to disconnect | edges are selectable but have no end handles; `fromNode/toNode/sides` can only change by delete + recreate | missing | should | M | high | 06 |
| 27 | Direction: none / one-way / two-way; default arrow at the second card | four buttons `Eszkoztar.svelte:52-57,128-130`, `muveletek.ts:105-122` | present | – | – | high | – |
| 28 | Label: double-click the line; add, edit, remove | `Vaszon.svelte:620-625`, `:401-409`, label drawn at the curve midpoint `:933-942` | present | – | – | high | – |
| 29 | Set colour on cards and edges | `Vaszon.svelte:310-313`, `muveletek.ts:97-101`; presets and clear only | partial | should | S | medium | 12 |
| 30 | Edge curve shape | cubic Bézier along the side normals `geometria.ts:160-183` | present | – | – | medium | – |
| 31 | "Follow connection" jumps to the far card | none | missing | could | S | medium | 22 |
| 32 | Group: create empty or around the selection; rename on double-click; moving it moves its contents | `Vaszon.svelte:281-297,635-637`, `geometria.ts:94-111`; the group is drawn under the cards `muveletek.ts:65-72` | present | – | – | high | – |
| 33 | Group background image and style (cover / ratio / repeat) | fields are in the model type `modell.ts:28-29` and survive saves, but are neither drawn nor editable | missing (data preserved) | could | M | high | 17 |
| 34 | "Jump to group" command | none | missing | could | S | medium | 22 |

### 1.4 Navigation, selection, arranging

| # | Obsidian behaviour | Manifold today (path:line) | Status | Weight | Size | Conf. | Gap |
|---|---|---|---|---|---|---|---|
| 35 | Pan by scrolling, Space-drag, middle-drag | `Vaszon.svelte:465-466,643-668` | present | – | – | high | – |
| 36 | Zoom with ⌘/Ctrl-scroll, pinch, buttons, reset | ⌘/⌃-wheel and WebKit gestures `:656-659,814-825`, `+`/`-` `:698-699`, 100 % button `Eszkoztar.svelte:110`; range 3–300 % `geometria.ts:27-28` | present | – | – | high | – |
| 37 | Zoom also with Space + wheel | only ⌘/⌃ + wheel `Vaszon.svelte:656` | missing | could | S | medium | 22 |
| 38 | Zoom to fit (⇧1) | `Vaszon.svelte:700`, `geometria.ts:69-73`, `Eszkoztar.svelte:114` | present | – | – | high | – |
| 39 | Zoom to selection (⇧2, context menu) | none | missing | should | S | medium | 11 |
| 40 | Select: click, ⇧-click, marquee, ⌘A | `Vaszon.svelte:482-501,519-524,680`; the marquee selects nodes, not edges | present | – | – | high | – |
| 41 | Selecting a card brings it to the front | selection never changes stacking; no raise/lower | missing | could | S | medium | 22 |
| 42 | Arrow keys nudge the selection | `Vaszon.svelte:687-691` (grid step, ⇧ = ×5) | present | – | – | medium | – |
| 43 | Duplicate with Alt-drag; ⇧-drag constrains the axis; ⇧-resize keeps the ratio; Space while dragging turns snapping off | ⌘D duplicates `:681,304-308`; Alt turns grid snapping off `:531,539` (different modifier); no axis lock, no ratio resize | partial | could | S | high | 18 |
| 44 | Copy, cut and paste cards (also across canvases); paste text or a URL creates a card | `⌘C/⌘X/⌘V` fall through (`:682`); no clipboard handling anywhere in `app/src/canvas/` | missing | should | M | high (cards) / medium (clipboard content) | 03 |
| 45 | Right-click menus on the canvas, a card and an edge | no `contextmenu` handler in `app/src/canvas/`; the toolbars cover colour, edit, group, delete and edge direction only | missing | should | M | high | 04 |
| 46 | Snap to grid | grid toggle, persisted per tab `Vaszon.svelte:85,136,741-743`, `geometria.ts:29,49` | present | – | – | high | – |
| 47 | Snap to objects (guides to neighbouring card edges) | none (the only snapping is the 20 px grid) | missing | should | M | medium | 10 |
| 48 | Align left/centre/right/top/middle/bottom, row/column/grid arrange, distribute, justify (help page) | none | missing | could | M | medium | 18 |
| 49 | Undo / redo | 200 snapshot steps, one drag = one step; cleared on external change `elozmeny.ts:6-46`, `Vaszon.svelte:221-239,786-793` | present | – | – | high | – |
| 50 | Read-only toggle in the canvas settings | read-only only when the file is invalid, conflicted or vanished `forras.ts:65-70`; no user switch | partial | could | S | high | 19 |
| 51 | Canvas settings (default card size, label display, wheel behaviour) | none; the module can be switched off in Settings (`tipusok.ts:1`) | missing | could | S | low | 19 |
| 52 | Export as PNG ("Export as image": whole canvas or viewport, zoom, privacy mode) | none; an SVG renderer for the embed exists `beagyazas.ts:39-84` | missing | could | M | high | 20 |
| 53 | Drag notes, media and other files from the explorer / Finder onto the canvas | no `drop`/`dragover` anywhere in `app/src/canvas/`; the tree already sets the vault-drag type (`Fa.svelte`, consumed only by `szerkeszto/csatolmany.ts`); cards are added through a picker `FajlValaszto.svelte` | missing | should | M | high | 02 |
| 54 | Drag a URL from the browser to create a web-page card | none (link cards via toolbar + URL field `Vaszon.svelte:272-279`) | missing | should | S | high | 02 |

### 1.5 Integration with the rest of the vault

| # | Obsidian behaviour | Manifold today (path:line) | Status | Weight | Size | Conf. | Gap |
|---|---|---|---|---|---|---|---|
| 55 | New canvas from the folder menu, the command palette and the ribbon | tree menu `Fa.svelte:447`; palette `index.ts:68` (+14 `canvas.*` commands `:17-32,69-77`); not in the ribbon `ikonsav.ts:23-34` | partial | could | S | high | 26 |
| 56 | New canvas is "Untitled" | file named "Névtelen canvas" `index.ts:35`; a new group is labelled "Csoport" `Vaszon.svelte:288,292,295`, `muveletek.ts:148`; JSON error positions are Hungarian text `json.ts:47` | partial | should | S | high | 14 |
| 57 | `![[board.canvas]]` embeds the canvas | read-only SVG thumbnail (frames + one-line titles), fixed 360 px, click opens `beagyazas.ts:14,39-123`; no card content, no `|WxH` | partial | could | M | medium | 16 (= 04-embeds-17) |
| 58 | Links to `[[x.canvas]]` resolve and open | `navigacio.ts:27`, `olvaso.py:344`; the canvas has its own tab view `index.ts:61-66` | present | – | – | high | – |
| 59 | Links *from* a canvas: file nodes (and wikilinks in text cards) are outgoing links and make backlinks | `elemzo.py:419-441` (links carry the node id), `feloldas.py:158-172`; backlink rows show a canvas badge `Visszahivatkozasok.svelte:33-36`; the status bar counts links for canvases `Allapotsor.svelte:39`; graph colours canvas nodes `Graf.svelte:89` | present (ahead: node id recorded) | – | – | high | – |
| 60 | A backlink from a canvas opens the canvas at that card | opens the file; the recorded `csomopont` is ignored by the UI (`Visszahivatkozasok.svelte:47`) | partial | could | S | low | 25 |
| 61 | Markdown links `[t](n.md)` and `#tags` in text cards count as links/tags | only `[[…]]` is parsed in text nodes `elemzo.py:435`, `feloldas.py:168-172`; rename rewrites only those `atnevezes.py:448-471` | missing | could | M | low | 24 |
| 62 | Canvas text is searchable | file paths, text and group labels go into the FTS content `elemzo.py:419-441`, `indexelo.py:786-789` (08-search R25 lists it as an extra); edge labels are not included | present (edge labels: could) | – | – | low | 25 |
| 63 | Renaming or moving a note updates canvas file nodes and `[[…]]` in text cards | planner with preview, blockers, reference proof and one-click undo `atnevezes.py:448-471`; tests `tests/test_atnevezes.py:121-145` | ahead | – | – | high | – |
| 64 | Hover preview over a wikilink in a card | `elonezetKapcsol` on the canvas root `Vaszon.svelte:827` | present | – | – | medium | – |
| 65 | Clicking a `#tag` or footnote inside a text card | the tag handler lives on the element (`html.ts:240`), but the canvas captures the pointer on card press (`Vaszon.svelte:503`) and its own `click` handler only knows external links and wikilinks (`:601-615`) — probably does nothing; unverified | partial | could | S | low | 24 |
| 66 | Canvas has documentation for the user | only one table row (`docs/user/NOTES-AND-EDITING.md:82`) and the demo canvas | missing | could | S | high | 26 |

---

## 2. Gaps and proposals

All proposals keep the existing layering: the view never touches the file system or resolves links; every file write goes through the core (new notes via `POST /api/vault/uj`, attachments via the import service, canvas text via the `Dokumentum` path); and every canvas edit stays a pure `muveletek.ts` function plus one undo step.

### 09-canvas-01 — Task checkboxes in text cards are dead (must, S, medium)
**Obsidian.** A text card is rendered Markdown (live editor on double-click); ticking a task changes the card's text and the file.
**Manifold.** `szovegRajzol` renders the card with the shared Reader renderer and passes no `csakOlvashato` flag (`tartalom.ts:36-46`), so `feladat()` emits an *enabled* checkbox (`html.ts:538-546`). The canvas ignores presses on inputs (`Vaszon.svelte:459,463`) and has no `change` handler; the Reader's handler is not mounted and would ignore the box anyway (`Olvaso.svelte:157-159`, the box is flagged as embedded). The box flips on screen, nothing is written, and the next redraw un-ticks it. A learner who ticks a to-do on a canvas and sees it revert (or worse, sees it stay ticked until reload) will not trust the tool. Note cards are already safe: they disable the boxes (`rajzol.ts:254-258`).
**Proposal.** Step 1 (S, ship first): pass `csakOlvashato: true` for text cards so the boxes are disabled with the existing "edit in the source" tooltip pattern. Step 2 (S–M): handle `change` on the card body, map the marker offset (`data-jelolo`) to the node's `text`, and write it with `modosit(...)` so it is one undo step and uses the normal save path. Add a test next to `canvas-nezet.svelte.test.ts` before changing anything, to confirm the behaviour described here.

### 09-canvas-02 — Drop notes, files and URLs onto the canvas (should, M, high)
**Obsidian.** Dragging files from the explorer or from other apps adds cards at the drop point (notes, images, audio, PDFs, unknown types); a URL dragged from a browser becomes a web-page card.
**Manifold.** No drop handling exists in `app/src/canvas/`. Cards are added only through the picker (`Vaszon.svelte:727`, `FajlValaszto.svelte`), at the view centre.
**Proposal.** Add `dragover`/`drop` on the canvas root. Vault drags reuse the explorer's drag payload (the same key the editor consumes in `szerkeszto/csatolmany.ts`) and call `ujFajl(path, dropPoint)` (`Vaszon.svelte:267-270`), several files laid out on the grid. Files from outside the vault go through the existing chunked import (`fajlImport` → `POST /api/vault/import`) and then become `file` nodes; a `text/uri-list` that passes `kulsoCim` becomes a `link` node. A folder drag is 21. Keep the drop inert in read-only canvases (`irhato`).

### 09-canvas-03 — Copy, cut and paste (should, M, high)
**Obsidian.** ⌘C/⌘X/⌘V on selected cards and edges, within a canvas and between canvases; pasting plain text or an image from the clipboard creates a card.
**Manifold.** Only ⌘D (`Vaszon.svelte:681,304-308`); other ⌘-keys fall through (`:682`).
**Proposal.** Serialise the selection (nodes, and the edges whose both ends are selected) as a JSON Canvas fragment on the clipboard with a Manifold MIME type plus a plain-text fallback, and reuse `duplikal`'s id remapping (`muveletek.ts:125-145`) for paste, anchored at the pointer or view centre. Pasted plain text → text card, pasted image file → import + file card (as in 02). Compatibility with Obsidian's own clipboard format is unknown (open question 7).

### 09-canvas-04 — Context menus (should, M, high)
**Obsidian.** Right-click on empty canvas (add note/media/web page at the pointer, add group, settings), on a card (colour, convert to file, duplicate, copy, swap, zoom to, delete) and on an edge (direction, label, colour, delete).
**Manifold.** No `contextmenu` handler; the WebKit default menu appears. The floating toolbars (`Eszkoztar.svelte:117-135`) cover only part of it.
**Proposal.** One `lebegoMenu` (the helper the file tree and ribbon use) with three item sets built from existing operations: `ujSzoveg`, `valaszto`, `ujLink`, `ujCsoport`, `szinBeallit`, `duplikalKijelolt`, `torolKijelolt`, `iranyBeallit`, plus the new operations from 03, 05, 11, 21. The menu is also the keyboard route (⇧F10), keeping the canvas accessible.

### 09-canvas-05 — Convert a text card to a note (should, M, high)
**Obsidian.** "Convert to file" turns a text card into a note with the text as content; the card becomes a note card and appears in backlinks.
**Manifold.** None; text cards stay inline forever.
**Proposal.** Ask for a name (default: first line, sanitised by the core's naming rules), create the note with the existing `POST /api/vault/uj` (exclusive create, collision-safe), then replace the node: `modosit` removing `text`, adding `file` and changing `type` in one undo step. Honour `newFileLocation` as the new-note flow does (07-explorer-10). Undo of the canvas does not delete the created note; say so in the confirmation notice and offer "Move to Trash" there. Cards with unsaved editor text must commit first (`szerkesztettKommit`, `Vaszon.svelte:355-357`).

### 09-canvas-06 — Edge editing: reconnect, change side, create a card on release (should, M, high)
**Obsidian.** Dragging an end of a selected edge to another card or side reconnects it; dragging away disconnects; releasing a new edge on empty space opens a menu/creates a card.
**Manifold.** Edges are created once (`Vaszon.svelte:569-582`); on empty space the release is dropped (`:571-573`). Changing an end means delete and redraw, losing label and colour.
**Proposal.** Show two end handles on a selected edge (`el-sav` already positions a toolbar at the midpoint, `:869-873`); dragging reuses the `ujEl` rubber-band and on release applies `modosit(id, {fromNode|toNode, fromSide|toSide})`. Release on empty space in create mode: `ujSzoveg` at that point plus the edge, as one undo step. Dropping on a card side should pick the closest side (`legkozelebbiOldal`, `geometria.ts:135-143`).

### 09-canvas-07 — PDF cards render the PDF (should, M, high)
**Obsidian.** A PDF in a file card is shown as a document.
**Manifold.** Chip with icon and name (`Kartya.svelte:142-143`) although the lazy, virtualised PDF embed viewer exists (`media/pdf/beagyazas.ts`).
**Proposal.** In `Kartya.svelte`'s effect add a `tipus === 'pdf'` branch that mounts the embed viewer sized to the card, with `subpath`/`#page=` honoured, only while `reszletes` is true (the existing LRU and visibility limits already bound the cost, `Vaszon.svelte:103-191`). Respect `modulEngedelyezett('pdf')` as `rajzol.ts:144-146` does.

### 09-canvas-08 — Bases cards render the view (should, M, medium)
**Obsidian.** A `.base` file card shows its default view; another view can be pinned (help page, 1.9).
**Manifold.** Chip only (`Kartya.svelte:142-143`); `![[x.base]]` already mounts a full `BazisNezet` (`bazis/beagyazas.ts`).
**Proposal.** Branch on `tipus === 'base'` and mount the same component with `subpath` as the view name. Bases are read-only here unless the card is selected and the module is enabled. Confirm the pin-a-view UX in Obsidian before building the picker.

### 09-canvas-09 — Edit note cards in place (should, L, high)
**Obsidian.** Double-clicking a note card edits the embedded note right in the card.
**Manifold.** Read-only render; double-click opens the note in a tab (`Vaszon.svelte:638`). This is safe and arguably clearer, but it is not what an Obsidian user expects and it breaks flow when working through several notes on one board.
**Proposal.** Mount the same CodeMirror set used for text cards (`Vaszon.svelte:332-392`) on the *target's* `Dokumentum` (`szerkesztok.dokumentumok.megnyit`, as the embedded-task writer does, `rajzol.ts:272`), honouring conflict, read-only and machine-write locks, with `subpath` restricting the editable range. Decide first whether to do this at all (open question 1); until then, record the open-in-tab behaviour as a deliberate deviation in `docs/dev/DESIGN.md`.

### 09-canvas-10 — Snap to objects (should, M, medium)
**Obsidian.** Moving or resizing a card snaps to the edges and centres of neighbouring cards with guide lines; Space turns snapping off (help page); a global canvas setting enables it.
**Manifold.** Only the 20 px grid (`geometria.ts:29`); Alt disables it (`Vaszon.svelte:531,539`).
**Proposal.** Pure function `snapObjektum(movingBox, others, threshold)` in `geometria.ts` returning the adjusted delta and guide segments, applied in the `mozgat`/`meretez` branches of `mozog` (`Vaszon.svelte:525-539`); guides drawn in the transformed world layer. Setting `snapObjektum` next to `racs` in the per-tab view state (`:136`). Accept both Alt and Space as the "no snapping" modifier.

### 09-canvas-11 — Zoom to selection (should, S, medium)
**Obsidian.** ⇧2 and a menu entry zoom to the selected cards.
**Manifold.** Only "show all" (⇧1, `Vaszon.svelte:700`).
**Proposal.** `mindentMutat(befoglalo(kijeloltNodek), …)` already does the maths (`geometria.ts:53-73`); add `canvas.kijeloles-mutat`, key `@`/⇧2 in `billentyu`, and a toolbar/menu entry. No-op without a selection.

### 09-canvas-12 — Custom colours (should, S, medium)
**Obsidian.** "Set color" offers the six presets plus a custom colour picker; the file stores the hex.
**Manifold.** Presets or none (`Eszkoztar.svelte:60-91`); an existing custom hex is shown as a read-only swatch (`:87-89`) and `szinCss` accepts only `#rgb`/`#rrggbb` (`modell.ts:141`).
**Proposal.** Add a native `<input type="color">` swatch to the palette that writes `#rrggbb` through `szinBeallit`. Keep the preset codes untouched (they map to tokens, so they follow light/dark and contrast). Extend `szinCss` to accept `#rrggbbaa` so imported colours are not silently dropped. Custom hex values are user data and bypass tokens by nature; the token/contrast tests need an allow-list entry for the picker only.

### 09-canvas-13 — Choose or change a note card's heading/block (should, M, medium)
**Obsidian.** A note card can be narrowed to one heading or block of its note (help page).
**Manifold.** `subpath` is rendered (`Kartya.svelte:95,128`, `tartalom.ts:56-70`) and preserved, but the picker only returns a path (`FajlValaszto.svelte:16`) and nothing edits `subpath` afterwards.
**Proposal.** After choosing a note in the picker (and from the card toolbar "Edit link") show the heading/block suggester that `[[note#` uses (02-links) and write `subpath` with `#` prefix as the spec requires; "Whole note" clears the key.

### 09-canvas-14 — Neutral English defaults and raw Hungarian strings (should, S, high)
**Rule.** CLAUDE.md: user-facing text is English through `t()`; defaults are neutral.
**Manifold.** The default new-canvas file name is the Hungarian "Névtelen canvas" (`index.ts:35`, marked `i18n-ignore`), new groups get the label "Csoport" in the user's file (`Vaszon.svelte:288,292,295`, `muveletek.ts:148`), and JSON error positions append Hungarian "sor/oszlop" outside `t()` (`json.ts:47`, shown through `modell.ts:83`).
**Proposal.** Use the translated default through `t()` for the group label (data written at creation time, but derived from the UI language) and rename the new-canvas default to "Untitled" (the same name the note flow uses); parameterise the JSON error with a `t('… line {sor}, column {oszlop}')` message. The name-collision loop (`index.ts:43-55`) stays. Add the ratchet entries.

### 09-canvas-15 — Open every spec-valid file (should, S, medium)
**Spec.** Ids must be unique per collection; the spec does not say a node and an edge may not share an id.
**Manifold.** One shared id set makes a node/edge id clash fatal and the whole canvas read-only (`modell.ts:89-94,106`). Obsidian-generated ids never clash, but other generators (mind-map exporters, scripts) may.
**Proposal.** Track node ids and edge ids in separate sets; keep duplicate ids *within* a collection fatal. Because selection, undo and `modosit` look up by id across both lists (`muveletek.ts:90-93`, `Vaszon.svelte:83,115`), qualify them (`node:` / `edge:` keys in the selection set) or keep the fatal rule and document the deviation. Decide with open question 6.

### Could-level items (not in the checklist fragment)

- **09-canvas-16 — Embedded canvas fidelity (could, M, medium; = 04-embeds-17).** The `![[x.canvas]]` thumbnail draws frames and first lines only, height fixed at 360 px (`beagyazas.ts:14,39-123`). Mount the read-only canvas component above a size threshold; honour `|WxH`.
- **09-canvas-17 — Group background image (could, M, high).** Draw `background`/`backgroundStyle` (cover, ratio, repeat) behind the group and add set/replace/remove through the picker; the keys already survive saves.
- **09-canvas-18 — Arranging aids (could, S–M, medium).** Align/distribute/arrange-in-row/column/grid and justify (help page); Alt-drag to duplicate, ⇧-drag axis lock, ⇧-resize keeping the ratio; accept Space as the no-snap modifier. All are pure functions over `Doboz` in `geometria.ts`.
- **09-canvas-19 — Lock and settings (could, S, high / low).** A user "read-only" toggle per tab (reuse `irhato`, `Vaszon.svelte:108-112`); optional settings for default card size and label display. Only the lock is documented by the help page.
- **09-canvas-20 — Export as image (could, M, high).** PNG of the whole canvas or the viewport at a chosen zoom with a "hide text" privacy option. Derive it from `canvasKep` (`beagyazas.ts:39-84`) rendered through a canvas element; no network or helper process needed.
- **09-canvas-21 — Folder cards and swapping (could, M, medium).** Dropping a folder adds a grid of file cards; "swap file" replaces `file` on a note/media card, keeping size and colour.
- **09-canvas-22 — Navigation extras (could, S, medium).** "Follow connection" (centre the far card), "Jump to group" palette command, Space + wheel zoom (`Vaszon.svelte:656`), raise/lower/bring-to-front (Obsidian raises on selection; the array order is the persisted z-order, so decide whether raising edits the file).
- **09-canvas-23 — Web-page cards under D3 (could, M, high).** Manifold shows host and URL only (`tartalom.ts:113-129`); the CSP forbids frames (`app/index.html:8-10`) and D3 forbids runtime network. This is a deliberate deviation. If previews are ever wanted: an explicit "Load preview" button that asks the core for a bounded, text-only fetch (title and description), never an iframe. Record the deviation in `docs/dev/DESIGN.md`.
- **09-canvas-24 — Text-card links and tags (could, S–M, low).** Verify and fix tag/footnote clicks inside text cards (the pointer capture swallows them, see row 65); index Markdown links and `#tags` in text nodes and include them in the rename planner (the canvas lags behind the note rules from 02-links).
- **09-canvas-25 — Backlink focus and edge-label search (could, S, low).** Use the recorded `csomopont` to open the canvas centred on the linking card; add edge labels to the canvas FTS text (`elemzo.py:424-440`).
- **09-canvas-26 — Ribbon entry and user docs (could, S, high).** Add `canvas.uj` to `IKONSAV_ALAP` (`ikonsav.ts:23-34`; see 06-workspace-12) and a short `docs/user/CANVAS.md` (gestures, shortcuts, what is saved to the file).
- **09-canvas-27 — Polish (could, S, high).** Escape in the new link card's URL field leaves an empty `link` node in the file (`Vaszon.svelte:272-279,401-409`): remove it on cancel. Cards with fractional coordinates keep fractions after a move (`muveletek.ts:43` adds an integer to a float); round to integers as the comment at `muveletek.ts:3-4` promises.

---

## 3. Manifold strengths beyond Obsidian (do not lose)

1. **Byte-faithful write path.** The position-aware parser and patcher change only the edited literals, detect the file's own style (Obsidian-compact or `indent=1/2/tab`), keep key order and the trailing newline, and refuse to write when the result would not parse to the expected model (`json.ts`, `iro.ts:1-14`, `forras.ts:74-94`; tests `canvas-iro.test.ts`). Obsidian rewrites the whole file.
2. **Nothing the app does not understand is lost.** Unknown keys, node types and extension fields are inert pass-through data (`modell.ts:1-4`), and a spec deviation is a visible badge (`CanvasFul.svelte:103-105`), not a refusal, in all but structurally broken files.
3. **One safe save path.** The canvas lives in the shared `Dokumentum`: autosave, hash-based conflict dialog, external-change reload, exit-save, "load the disk version" recovery (`CanvasFul.svelte:57-74`), and a card being edited counts as unsaved so machine writes stay out (`forras.ts:101-111`).
4. **Core-side validation.** An invalid JSON Canvas is rejected with 400 and leaves the file untouched (`vaultio.py:378-381`); invalid files open read-only with the exact line and column.
5. **Rename planner covers canvases.** File nodes and `[[…]]` in text cards are rewritten byte-minimally with a preview, reference proof and one-click undo (`atnevezes.py:448-471`, tests `test_atnevezes.py:121-145`).
6. **Links with provenance.** Canvas links carry the node id (`elemzo.py:429-436`), backlinks mark the canvas source, the graph colours canvases, hygiene counts canvas links as incoming (`higienia.py:311-315`), and canvas text is in the full-text index.
7. **Cheap large canvases.** Off-screen cards are not in the DOM (CX-008, `Vaszon.svelte:195-200`), detailed content is limited to the view plus a 48-card LRU (`:103-191`), note cards load through a six-wide queue with abort (`tartalom.ts:52-70`), images use DPR-sized buckets (`Kartya.svelte:78`), and cards refresh per changed target (`tartalom.ts:48,68`; test `f11-embeds-kulso.test.ts:199-208`).
8. **Keyboard and screen-reader route.** The canvas is `role="application"`, every card is a Tab stop with a descriptive label, Enter edits/opens, arrows nudge, Esc clears, Delete removes, ⌘Z/⌘⇧Z/⌘D/⌘A work, and every toolbar button has a name (`Vaszon.svelte:672-707,879-900`, `Kartya.svelte:106-124`).
9. **Text-card editor.** The card editor is the full note extension set (Live Preview, `[[` completion), with floating menus in `body` so they survive the transformed layer (`Vaszon.svelte:358-385`).
10. **Per-tab view state.** Zoom, pan and the grid choice are restored per tab (`Vaszon.svelte:122-138`), with WebKit pinch support (`:814-825`).
11. **Offline link cards.** No network request is ever made for a web card, which is exactly the D3 rule (`tartalom.ts:113-129`).

---

## 4. Open questions

1. **Editing note cards in place (09):** write into another note from a canvas (through its `Dokumentum`, with conflict and machine-write handling), or keep "open in tab" as a documented deviation?
2. **Web-page cards (23):** accept the host-and-URL card for good, or add an explicit, bounded, text-only "Load preview" through the core?
3. **Dropping outside files (02):** which folder should a dropped Finder file land in — the configured attachment folder (as the editor does) — and is a bulk drop of many files acceptable in one undo step?
4. **Convert to file (05):** naming rule, folder (`newFileLocation`?), and whether undo should offer to trash the created note.
5. **Obsidian behaviour to confirm in the app (medium confidence):** snap-to-objects defaults and guides, the alignment/distribute tools, ⇧2 zoom to selection, the custom colour picker, pinning a Bases view on a card, and whether selecting a card edits the persisted z-order.
6. **Id namespace (15):** accept node/edge id sharing (needs namespaced selection keys) or keep the strict rule and document it?
7. **Clipboard format (03):** is there an Obsidian-compatible clipboard payload worth reading, or is a Manifold-only payload plus plain text enough?
8. **Tag/footnote clicks and checkboxes in text cards (01, 24):** both findings come from reading the code (pointer capture, input handling); run a short component test before the fix to confirm them.
9. **Edge-heavy canvases:** edges are not culled (only cards are, `Vaszon.svelte:195-200,919-931`). Needs a measurement on a synthetic canvas with thousands of edges; not assessed here.
10. **Stale record:** update `docs/plan/NAPLO.md:205` and the 04-embeds-07 remainder in `docs/plan/f11/CHECKLIST.md`: canvas-card refresh is implemented and tested.
