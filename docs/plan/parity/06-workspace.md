# 06 – Workspace parity audit: tabs, split panes, sidebars, status bar, command palette, quick switcher

Scope: the Manifold workspace shell compared with Obsidian 1.8/1.9 desktop (core features and core plugins only).
Read-only audit of `/Volumes/Work/[UNI] Manifold-OS`; every claim is cited as `path:line` relative to that root.
Files read: `app/src/hej/{Hej,Fulsor,Osztas,Panel,Oldalsav,JobbPanel,Allapotsor,Ikonsav,Atmeretezo,Elvalaszto}.svelte`,
`app/src/hej/nezetek/{UjFul,Helyorzo}.svelte`, `app/src/lib/elrendezes/*`, `app/src/atfedes/{Paletta,Valto}.svelte`,
`app/src/lib/ui/{ListaValaszto,Atfedes,Billentyu,IkonGomb}.svelte`, `app/src/lib/parancsok/*`, `app/src/alapParancsok.ts`,
`app/src/lib/fokusz/*`, `app/src/lib/kereses/fuzzy.ts`, `app/src/lib/vault/fajlok.svelte.ts`, `app/src/App.svelte`,
`app/src/main.ts`, `shell/Sources/AppController.swift` (menus), and the reference docs `docs/dev/ARCHITECTURE.md`,
`docs/dev/DESIGN.md`, `docs/plan/audit/03-felulet.md`.

Obsidian behaviour is stated from memory of the desktop app; where I am not sure a comparison is marked
**confidence: low/medium** in the gap entry. Nothing below proposes removing a Manifold behaviour; section 3 lists what
must be preserved.

Severity: **must** = daily-use Obsidian behaviour users miss immediately · **should** = noticeable · **nice** = polish.
Effort: **S** < 1 day · **M** 1–3 days · **L** > 3 days.

---

## 0. Summary

The workspace model is solid and already covers most of the Obsidian daily loop: tabs with ⌘T/⌘W/⌘⇧T, ⌃⇥, ⌘1–9,
drag-reorder and drag-between-groups, nested splits with persisted ratios, a per-tab back/forward history, a layout that
is saved through the core and restored before first paint, a single command registry behind the palette, hotkeys,
buttons and the macOS menu, and a quick switcher with the same modifier conventions as Obsidian (↵ / ⌘↵ / ⌥⌘↵).

What users will miss immediately (**must**): a settings window on ⌘, (settings are scattered over ⌘P commands and the
overview page), `⌘N` "create new note" (no hotkey anywhere; the new-tab page has no "create" action), creating a note
from the quick switcher when there is no match (⇧↵), and the word/character count in the status bar.

Noticeable (**should**): tab pinning, a tab context menu (close others / to the right / split / reveal), dragging a tab
onto a pane edge to split, "close other tabs"-style group commands, linked tab groups, aliases in the quick switcher,
visible back/forward arrows, named workspace layouts, hotkey customisation, UI zoom (⌘= / ⌘- / ⌘0), the backlinks count
in the status bar, and a richer/configurable ribbon.

Polish (**nice**): stacked tabs, tab-list dropdown, pinned palette commands, hover-reveal of the collapsed right panel,
dropping a file from the tree onto a tab bar, rearrangeable sidebar views, pop-out windows, mouse back/forward buttons,
sidebar width cap, help shortcut.

Gap count: 31 (4 must · 14 should · 13 nice). Strengths to preserve: 18 (section 3).

---

## 1. Checklist

Status: **present** / **partial** / **missing** / **n/a** (not an Obsidian core feature, or not applicable).
"Gap" refers to section 2.

### 1.1 Tabs

| # | Obsidian behaviour | Manifold today (path:line) | Status | Severity | Effort | Gap |
|---|---|---|---|---|---|---|
| T1 | New tab ⌘T; "+" button at the end of the tab bar | `ful.uj` Mod+T `app/src/alapParancsok.ts:129`; "+" `app/src/hej/Fulsor.svelte:147` (quiet mode: hover/focus only, `data-csend-rejt`); model `app/src/lib/elrendezes/munkaterulet.svelte.ts:182-189` | present | – | – | – |
| T2 | Close tab ⌘W; middle-click; ✕ on hover and on the active tab | `ful.bezar` Mod+W `alapParancsok.ts:130`; middle-click `Fulsor.svelte:111-113`; ✕ `Fulsor.svelte:134-143`; Delete/Backspace on a focused tab `Fulsor.svelte:48-51`; model `munkaterulet.svelte.ts:198-214` | present | – | – | – |
| T3 | Undo close tab ⌘⇧T, restored into its original group at its old position | `ful.ujranyit` Mod+Shift+T `alapParancsok.ts:126`; stack of 20 closed tabs with panel+index `munkaterulet.svelte.ts:88-95, 204-210`; per-tab history survives the close (`mult` kept, `:206-210`) | present | – | – | – |
| T4 | Pin tab (tab menu "Pin" / command "Toggle pin"): a pinned tab is never replaced, opening a file from it goes to a new tab; pin icon on the tab | None. `megnyit('aktiv')` always replaces the active tab's file `munkaterulet.svelte.ts:140-146`; `Ful` has no pinned field `:4-11`; `Fulsor.svelte` shows no pin | missing | should | S | 06-workspace-01 |
| T5 | Drag a tab to reorder within its group, with an insertion indicator | HTML5 drag `Fulsor.svelte:59-87, 97-99, 108-110`; indicator `:205-222`; model `munkaterulet.svelte.ts:249-261` | present | – | – | – |
| T6 | Drag a tab onto another group's tab bar to move it; an emptied group collapses | same code path (`athelyez` cross-panel, source collapses `munkaterulet.svelte.ts:260`) | present | – | – | – |
| T7 | Drag a tab onto the left/right/top/bottom edge of a pane to create a new split there | Only the tab bar is a drop target (`Fulsor.svelte:97-99`); `Panel.svelte` has no edge drop zones | missing | should | M | 06-workspace-02 |
| T8 | Drag a file from the file explorer onto a tab bar / pane to open it there | `Fulsor.svelte:74` accepts only `application/x-manifold-ful`; the tree emits `application/x-manifold-vault` + `text/plain` `app/src/hej/Fa.svelte:273-274` (`app/src/szerkeszto/csatolmany.ts:7`), consumed by the editor as a link, not by the shell | missing | nice | S | 06-workspace-03 |
| T9 | Tab context menu: Close, Close others, Close tabs to the right, Close all, Pin, Split right/down, Link with tab, Open/Move to new window, Reveal in navigation, Copy path, Rename | No `oncontextmenu` in `Fulsor.svelte` or `Panel.svelte` (the tree has one, `Fa.svelte:412`); F2 rename exists (`vault.atnevezes` `app/src/szerkeszto/linkek/atnevezes.ts:190`); "Megmutatás a fájlfában" exists as a ⌘P command `alapParancsok.ts:86-95` | missing | should | S | 06-workspace-04 |
| T10 | Tab-list dropdown (chevron at the right end of the tab bar) listing the group's tabs | None | missing | nice | S | 06-workspace-05 |
| T11 | Next/previous tab ⌃⇥ / ⌃⇧⇥; Go to tab 1–8 ⌘1–⌘8; last tab ⌘9 | `alapParancsok.ts:131-140`; `munkaterulet.svelte.ts:217-229` | present | – | – | – |
| T12 | Tab title = file basename (no `.md`); hover tooltip = full path; icon for non-note views | `Fulsor.svelte:35, 123, 127-131`; `fajlNev` `app/src/lib/vault/fajlok.svelte.ts:28-31` | present | – | – | – |
| T13 | Many tabs: tabs shrink to a minimum, then the bar scrolls | `Fulsor.svelte:162-182` (`flex: 0 1 200px`, `min-width: 88px`, `overflow-x: auto`, scrollbar hidden) | present | – | – | – |
| T14 | New-tab page: "No file is open" with Create new note (⌘N), Go to file (⌘O), See recent files, Close | `app/src/hej/nezetek/UjFul.svelte:9-15`: Ma, Napi jegyzet ⇧⌘D, Fájl megnyitása ⌘O, Parancsok ⌘P, Fül bezárása ⌘W. No "new note" entry; `Mod+N` is bound nowhere (grep of `app/src`); `fa.uj-jegyzet` has no hotkey `alapParancsok.ts:113-124` | partial | must | S | 06-workspace-06 |
| T15 | Double-click on empty tab-bar space opens a new tab (confidence: medium) | None (`Fulsor.svelte:90-148`) | missing | nice | S | 06-workspace-05 |
| T16 | Closing the last tab of the root group leaves an empty "new tab" | `munkaterulet.svelte.ts:299-304` | present | – | – | – |
| T17 | ⌘-click / middle-click a file or link opens it in a new tab; ⌘⌥-click opens to the right | `nyitasMod` `app/src/szerkeszto/linkek/navigacio.ts:31-35`; tree `Fa.svelte:95`, tree menu `Fa.svelte:240-242`; right panel `app/src/hej/JobbPanel.svelte:112-118` | present | – | – | – |

### 1.2 Tab groups and splits

| # | Obsidian behaviour | Manifold today (path:line) | Status | Severity | Effort | Gap |
|---|---|---|---|---|---|---|
| G1 | Split right / Split down; the new group starts with a copy of the current tab and takes focus | `panel.oszt-jobbra` ⇧⌘2, `panel.oszt-le` ⌥⌘↓ `alapParancsok.ts:141-142`; `oszt` `munkaterulet.svelte.ts:232-239` | present | – | – | – |
| G2 | Nested splits (any direction, any depth); ratios persisted with the layout | Binary tree `OsztasCs` `munkaterulet.svelte.ts:27-38`; recursive render `app/src/hej/Osztas.svelte:14-31`; ratio clamped 0.15–0.85 `:59`; depth ≤ 12 on load `:353`; serialised `:290-295` | present (binary, not n-ary – see open question Q4) | – | – | – |
| G3 | Resize a split by dragging the divider | `app/src/hej/Elvalaszto.svelte:13-24` (+ keyboard ←→/↑↓ 5 % `:26-32`, ARIA separator `:37-52`) | present | – | – | – |
| G4 | A group whose last tab closes is removed and its sibling takes the space | `uresPanel` `munkaterulet.svelte.ts:299-311` | present | – | – | – |
| G5 | The active group is visually distinct; clicking or focusing a pane activates it | `app/src/hej/Panel.svelte:15, 25-28`; `Fulsor.svelte:200-203` | present | – | – | – |
| G6 | Commands: Close all other tabs, Close tabs to the right, Close this tab group, Close all tabs in group; Focus on tab group to the left/right/above/below | Only `panel.kovetkezo` / `panel.elozo` in tree order and without a hotkey `alapParancsok.ts:143-144` (`panelLep` `munkaterulet.svelte.ts:242-246`) | partial | should | S | 06-workspace-07 |
| G7 | Linked tab groups ("Link with tab…"): linked groups open the same file and scroll together (e.g. editing + reading view) | None (no link relation in `munkaterulet.svelte.ts`) | missing | should | M | 06-workspace-08 |
| G8 | Stacked tabs ("Stack tabs" per group, sliding-panes layout) | None | missing | nice | L | 06-workspace-09 |
| G9 | Maximize / minimize a pane (confidence: low – I believe this is not in Obsidian core; community plugins provide it) | None | n/a | nice | S | 06-workspace-10 |
| G10 | Pop-out windows: "Open in new window", "Move to new window", ⌘⇧W closes a window | Single window; the shell refuses a second instance on the same vault `shell/Sources/AppController.swift:378-382`; Window menu has no "New window" `:364-373` | missing | nice | L | 06-workspace-11 |

### 1.3 Sidebars and ribbon

| # | Obsidian behaviour | Manifold today (path:line) | Status | Severity | Effort | Gap |
|---|---|---|---|---|---|---|
| S1 | Ribbon: quick switcher, graph, new canvas, daily note, command palette, insert template; bottom: settings gear, help, vault switcher. Icons can be hidden/reordered (right-click → configure); the ribbon itself can be hidden (confidence: medium on hide/reorder) | `app/src/hej/Ikonsav.svelte:9-17`: sidebar toggle, search ⇧⌘F, new note, Manifold overview ⇧⌘M, presence dot. Fixed list, no settings/graph/daily-note/switcher icon, cannot be hidden | partial | should | M | 06-workspace-12 |
| S2 | Toggle left sidebar (collapse chevron in the ribbon; no default hotkey – confidence: medium) | `hej.oldalsav` ⌥⌘1 `alapParancsok.ts:97`; buttons `app/src/hej/Oldalsav.svelte:83-90`, `app/src/hej/Allapotsor.svelte:64-71`, `Ikonsav.svelte:10`; macOS Nézet menu `AppController.swift:349-362` | present (Manifold has a default hotkey – strength) | – | – | – |
| S3 | Toggle right sidebar (icon top-right; no default hotkey – confidence: medium) | `hej.jobb-panel` ⌥⌘2 `alapParancsok.ts:98`; `JobbPanel.svelte:160-166`; `Allapotsor.svelte:92-99` | present | – | – | – |
| S4 | Resize sidebars by dragging their inner edge; no hard maximum width (confidence: medium) | `app/src/hej/Hej.svelte:41-63` + `app/src/hej/Atmeretezo.svelte:27-47` (keyboard `:49-59`); widths clamped 200–480 / 220–480 `app/src/lib/elrendezes/felulet.svelte.ts:10-11` | present (capped) | nice | S | 06-workspace-13 |
| S5 | A collapsed sidebar can be revealed by hovering its edge (confidence: medium) | Left: 8 px edge zone, quiet mode only `app/src/lib/elrendezes/csend.svelte.ts:56-58, 163-167`; right: only F6 / command (`JobbPanel.svelte:38-41`, `csend.svelte.ts:81`) | partial | nice | S | 06-workspace-14 |
| S6 | Sidebar views are tabs (Files / Search / Bookmarks left; Backlinks / Outgoing links / Outline / Tags / Properties right); any view can be dragged to the other sidebar, split vertically inside a sidebar, or into the main area | Left: fixed Files/Tags text tabs `Oldalsav.svelte:37-40, 67-91`; right: fixed stack of collapsible sections `JobbPanel.svelte:173-195`; search is a modal window (`app/src/atfedes/KeresoAblak.svelte`, `alapParancsok.ts:45-53`) | partial | nice | L | 06-workspace-15 |
| S7 | Sidebar state persisted: width, collapsed, active view, section state | `felulet.svelte.ts:29-30, 56-57, 217-235`; `Oldalsav` tabs with arrow keys `Oldalsav.svelte:43-49` | present | – | – | – |
| S8 | Sidebar keyboard access (none specific in Obsidian) | F6 / ⇧F6 region cycling incl. hidden regions `app/src/lib/fokusz/fokusz.ts:66-93`, `alapParancsok.ts:145-146` | present (strength) | – | – | – |

### 1.4 Status bar

| # | Obsidian behaviour | Manifold today (path:line) | Status | Severity | Effort | Gap |
|---|---|---|---|---|---|---|
| B1 | Word count + character count of the active note (core plugin "Word count", enabled by default; selection-aware) | None. Items: sidebar toggle, connection warning, presence, index state / note count, notifications, right-panel toggle `Allapotsor.svelte:64-102`; count source `fajlok.svelte.ts:48` | missing | must | S | 06-workspace-16 |
| B2 | "N backlinks" item (core Backlinks plugin; confidence: medium) | Count only in the right panel section header `JobbPanel.svelte:144, 173` | partial | should | S | 06-workspace-17 |
| B3 | Sync status icon (Obsidian Sync, paid) | n/a. Nearest equivalents: core connection `Allapotsor.svelte:73-75`, snapshot/backup state in the Rendszer section (`/api/vezerlo/rendszer`, `docs/dev/ARCHITECTURE.md:281`) | n/a | nice | S | 06-workspace-18 |
| B4 | Status bar always visible | Quiet mode: overlay at the bottom, shown only when it "has something to say", mouse at the bottom edge, or focus (`csend.svelte.ts:32-47`; `Allapotsor.svelte:34-47, 123-140`); quiet mode off: always visible | present (different – see Q9) | – | – | – |

### 1.5 Command palette

| # | Obsidian behaviour | Manifold today (path:line) | Status | Severity | Effort | Gap |
|---|---|---|---|---|---|---|
| P1 | ⌘P opens; fuzzy matching across words | `hej.paletta` Mod+P `alapParancsok.ts:32`; `app/src/atfedes/Paletta.svelte:26-52`; `app/src/lib/kereses/fuzzy.ts:1-7, 235-274` (accent-insensitive, typo-tolerant) | present | – | – | – |
| P2 | Hotkey chips right-aligned in each row | `Paletta.svelte:86`; `app/src/lib/ui/Billentyu.svelte:8`; `app/src/lib/parancsok/billentyuk.ts:103-107` | present | – | – | – |
| P3 | Pinned commands (Settings → Command palette → Pinned) shown first with a pin icon | None – only recency `felulet.svelte.ts:65, 213-215`, `Paletta.svelte:30-43` | missing | nice | S | 06-workspace-19 |
| P4 | Recently used commands first on an empty query (confidence: low – Obsidian may show only pinned) | `Paletta.svelte:30-43` (20 most recent, persisted `felulet.svelte.ts:13`) | present (strength) | – | – | – |
| P5 | Only commands available in the current context are listed | `elerheto` predicate `app/src/lib/parancsok/regiszter.ts:23, 86-97` | present | – | – | – |
| P6 | Hotkeys customisable (Settings → Hotkeys; conflicts shown) | Fixed at registration; conflict throws `regiszter.ts:58-66`; display `billentyuk.ts:103-107` | missing | should | M | 06-workspace-20 |
| P7 | Esc / click outside closes; focus returns to the editor | `app/src/lib/ui/Atfedes.svelte:29-34, 63-65, 74`; `Paletta.svelte:58-69` | present | – | – | – |
| P8 | ↑↓ navigation, footer hints | `app/src/lib/ui/ListaValaszto.svelte:72-86`; footer `Paletta.svelte:88-92` | present | – | – | – |

### 1.6 Quick switcher

| # | Obsidian behaviour | Manifold today (path:line) | Status | Severity | Effort | Gap |
|---|---|---|---|---|---|---|
| Q1 | ⌘O; fuzzy on file name and path; recent files first on an empty query | `hej.valto` Mod+O `alapParancsok.ts:33`; `app/src/atfedes/Valto.svelte:20-48`; index = basename + folder `fajlok.svelte.ts:64-67` | present | – | – | – |
| Q2 | Aliases (frontmatter `aliases`) are matched and shown as separate rows pointing at the note | Not indexed. The data exists: `GET /api/vault/aliasok` `app/src/lib/vault/linkek.svelte.ts:144`, used by `[[` completion `app/src/szerkeszto/linkek/kiegeszites.ts:96-101` | missing | should | S | 06-workspace-21 |
| Q3 | ↵ open in active tab; ⌘↵ open in new tab; ⌘⌥↵ open to the right (split) | `ListaValaszto.svelte:6-9, 66-70`; `Valto.svelte:62-65`; footer `:84-90` | present | – | – | – |
| Q4 | ⇧↵ creates a note with the typed name; with no match the first row offers "create" | None – empty state text only `Valto.svelte:50-56`; `Modositok` has no shift flag `ListaValaszto.svelte:6-9` | missing | must | S | 06-workspace-22 |
| Q5 | Unresolved link targets listed as creatable entries; settings "Show existing only", "Show attachments", "Show all file types" (confidence: medium on defaults) | All file types always listed (PDF, media, …) with type icons `Valto.svelte:79-83`; no unresolved targets, no filter | partial | nice | M | 06-workspace-23 |
| Q6 | Folder path shown muted on the right | `Valto.svelte:82` | present | – | – | – |

### 1.7 Navigation, layouts, settings

| # | Obsidian behaviour | Manifold today (path:line) | Status | Severity | Effort | Gap |
|---|---|---|---|---|---|---|
| N1 | Navigate back / forward ⌘⌥← / ⌘⌥→, history per tab | `alapParancsok.ts:127-128`; `munkaterulet.svelte.ts:64, 76-86` (50 entries `:143`) | present | – | – | – |
| N2 | ← → arrows in the view header; long-press / right-click shows the history list (confidence: medium on the list) | None – hotkeys only; the editor header has breadcrumb + mode toggle (`app/src/szerkeszto/Szerkeszto.svelte`), no arrows | missing | should | S | 06-workspace-24 |
| N3 | Mouse buttons 4/5 and trackpad swipe navigate back/forward (confidence: medium) | None (`Fulsor.svelte:111-113` handles only middle-click) | missing | nice | S | 06-workspace-25 |
| N4 | Layout (tabs, splits, sidebars) restored on start exactly as left | `app/src/main.ts:16-21`; `felulet.svelte.ts:248-255, 99-154`; late load merge `:161-173`; save `App.svelte:86-91`. Plus: the overview tab is always (re)opened `main.ts:19` | present (with a forced overview tab – Q1) | – | – | – |
| N5 | Workspaces core plugin: save / load / delete named layouts, "Manage workspace layouts" | None (a single layout in `felulet.json`, `felulet.svelte.ts:43`) | missing | should | M | 06-workspace-26 |
| N6 | Settings window ⌘, ; App menu "Settings…" | None. Preferences are ⌘P commands (theme `alapParancsok.ts:147-149`, quiet `:111`, system notifications `:152-160`) and overview sections (`docs/plan/audit/03-felulet.md:220-246`); the shell App menu has no Settings item `AppController.swift:320-331` | missing | must | L | 06-workspace-27 |
| N7 | Zoom in / out / reset ⌘= ⌘- ⌘0 (persisted) | None (no zoom command or shell page-zoom; grep of `app/src`, `shell/Sources`) | missing | should | S | 06-workspace-28 |
| N8 | Help F1 / "Open help" (confidence: medium) | None | missing | nice | S | 06-workspace-29 |
| N9 | Theme: light / dark / system | `alapParancsok.ts:147-149`; `app/src/lib/elrendezes/tema.ts` | present | – | – | – |
| N10 | Reveal active file in navigation (no default hotkey) | `fa.megmutat` `alapParancsok.ts:86-95`; `felulet.svelte.ts:198-207` | present | – | – | – |
| N11 | Tab view state (scroll position) restored with the layout (confidence: medium on cursor) | Per-tab `nezet` state (mode, top line, cursor) ≤ 2 KB `munkaterulet.svelte.ts:8-13, 337-345`; written by the editor `Szerkeszto.svelte:63-65, 180, 195-196` | present (strength) | – | – | – |
| N12 | Dragging the file-tree node onto an editor inserts a link; dragging onto the workspace opens | link insertion exists (`csatolmany.ts:7`); open-by-drop missing (T8) | partial | nice | S | 06-workspace-03 |
| N13 | Tab titles for renamed/moved files follow the rename; deleted files' tabs show "file missing" | `utatNevez` incl. history and closed tabs `munkaterulet.svelte.ts:281-288`; deleted → empty tab with a suspicious-shrink guard `fajlok.svelte.ts:38-41, 89-95`, `App.svelte:49` | present | – | – | – |
| N14 | Window/app menus mirror the main commands | Nézet menu built from registry ids `AppController.swift:349-362`; ⌘W deliberately left to the page `:363-365` | present | – | – | – |

---

## 2. Gaps and proposals

Each proposal stays inside the existing architecture: commands go through `regiszter` (`app/src/lib/parancsok/regiszter.ts`),
workspace mutations through `Munkaterulet` (`app/src/lib/elrendezes/munkaterulet.svelte.ts`), persistence through
`Felulet.sorosit()` → `PUT /api/felulet/allapot` (`app/src/lib/elrendezes/felulet.svelte.ts:217-235, 348-355`;
`docs/dev/ARCHITECTURE.md:194`; the core only validates "JSON object ≤ 256 KiB", so new keys need no core change,
`docs/plan/audit/03-felulet.md:222`). UI strings follow the current Hungarian identifiers; wording is not part of this audit.

### 06-workspace-01 · Tab pinning — should · S · confidence high
- **Obsidian**: tab menu "Pin" / command "Toggle pin"; a pinned tab keeps its file: opening another file from it goes to a new tab; the tab shows a pin icon; pin state is saved in the layout; "Close" on a pinned tab is allowed.
- **Manifold**: no pin concept. `megnyit('aktiv')` rewrites the active tab (`munkaterulet.svelte.ts:140-146`); `Ful` has `id / ut / nezet` only (`:4-11`).
- **Proposal**: add `rogzitett?: boolean` to `Ful` and accept it in `ervenyes()` (`:348-371`). In `megnyit()` treat a pinned active tab like a view tab (`!nezetFul(this.aktivFul)` branch, `:140`) so the file opens in a new tab after it. Add `rogzit(panelId, fulId)` + command `ful.rogzit` ("Fül rögzítése / feloldása", category Fül, no default hotkey) in `app/src/alapParancsok.ts`. In `Fulsor.svelte` render a small pin icon instead of ✕ for pinned tabs (hover still shows ✕), add it to the context menu (gap 04). Serialised automatically through `sorosit()`.

### 06-workspace-02 · Drag a tab onto a pane edge to split — should · M · confidence high
- **Obsidian**: while dragging a tab over a pane, the four edges highlight; dropping creates a split in that direction with the dragged tab.
- **Manifold**: only the tab bar accepts `application/x-manifold-ful` (`Fulsor.svelte:73-87`); `Panel.svelte` has no `ondragover/ondrop`.
- **Proposal**: in `Panel.svelte` add an overlay (`position: absolute; inset: 0`, visible only while a tab drag is in flight — track via a module-level `$state` set in `huzasKezd`/`dragend` of `Fulsor.svelte`) with four edge zones (`--t-8` wide) and a centre zone (= move into this group, reuse `athelyez`). Add `Munkaterulet.athelyezOsztasba(fulId, celPanelId, irany: 'sor'|'oszlop', ele: boolean)`: remove the tab from its source (`:249-255`), wrap `cel` in a new `OsztasCs` via `csere` (`:313-322`), put the tab in a new `ujPanel([ful])`, collapse an emptied source (`uresPanel`). Dropping on the tab bar keeps the current behaviour. Cover in `app/tests/munkaterulet.svelte.test.ts` next to the existing `athelyez` case (`:89-101`).

### 06-workspace-03 · Open a file by dropping it from the tree onto a tab bar / pane — nice · S · confidence medium
- **Obsidian**: dragging a note from Files onto a tab bar opens it in that group; onto the editor body inserts a link.
- **Manifold**: the tree sets `application/x-manifold-vault` (`Fa.svelte:273-274`); the editor consumes it as link/attachment; the tab bar ignores it (`Fulsor.svelte:74`).
- **Proposal**: in `Fulsor.svelte` `felett`/`ejt` also accept `VAULT_HUZAS` (import from `app/src/szerkeszto/csatolmany.ts:7`) and call `m.aktival(panel.id)` + `m.megnyit(ut, 'ujful')`. Combine with gap 02's edge zones so a tree drop on an edge opens in a new split.

### 06-workspace-04 · Tab context menu and tab "more options" — should · S · confidence high
- **Obsidian**: right-click on a tab (and the ⋯ in the view header): Close, Close others, Close tabs to the right, Close all, Pin/Unpin, Split right, Split down, Link with tab, Open in new window, Move to new window, Reveal in navigation, Copy path / Copy Obsidian URL, Rename, Delete file.
- **Manifold**: nothing on the tab (`Fulsor.svelte:103-144`); the equivalents exist only as commands or not at all.
- **Proposal**: `oncontextmenu` (and ⇧F10 on the focused tab, as the tree does, `docs/dev/ARCHITECTURE.md:190`) in `Fulsor.svelte`, reusing the tree's menu helper (`Fa.svelte:412` `sorMenu` → the shared `lebegoMenu` of `app/src/szerkeszto/notion/menu.ts`). Items call registry commands so the palette gets them too: `ful.bezar`, new `ful.bezar-tobbi`, `ful.bezar-jobbra`, `ful.bezar-mind` (gap 07), `ful.rogzit` (gap 01), `panel.oszt-jobbra`, `panel.oszt-le`, `fa.megmutat`, `vault.atnevezes`, new `ful.ut-masol` (clipboard via `app/src/szerkeszto/vagolap.ts`). The commands need a target tab: give `Munkaterulet.bezar()` siblings `bezarTobbi(panelId, fulId)`, `bezarJobbra(panelId, fulId)`, `bezarMind(panelId)`.

### 06-workspace-05 · Tab-list dropdown and double-click-to-new-tab — nice · S · confidence high (dropdown) / medium (double-click)
- **Obsidian**: a chevron at the right end of each tab bar lists the group's tabs (click to activate) plus "Close all"; double-clicking empty tab-bar space opens a new tab.
- **Manifold**: neither (`Fulsor.svelte:90-148`).
- **Proposal**: in `Fulsor.svelte` add a `ChevronDown` `IkonGomb` after "+" (hidden with `data-csend-rejt` like "+") opening a `lebegoMenu` with `panel.fulek` (title + icon, active marked) and `ful.bezar-mind`; add `ondblclick` on `.fulek` with `e.target === e.currentTarget` → `m.ujFul(panel.id)`.

### 06-workspace-06 · ⌘N "Create new note" and the new-tab page — must · S · confidence high
- **Obsidian**: ⌘N creates "Untitled" in the default new-note location and opens it with the title selected; the new-tab page offers "Create new note (⌘N)"; ⌘⇧N? not a default (ignore).
- **Manifold**: `fa.uj-jegyzet` opens an inline name field in the tree (`alapParancsok.ts:113-124`, `felulet.faUjJegyzet` `felulet.svelte.ts:88`) and has no hotkey; `Mod+N` is unbound; `UjFul.svelte:9-15` has no create entry.
- **Proposal**: bind `fa.uj-jegyzet` to `Mod+N` (`alapParancsok.ts:114-124`; the registry rejects duplicates at startup, `regiszter.ts:58-63`, and `app/tests/billentyu-utkozes.test.ts` guards it) and add `{ id: 'fa.uj-jegyzet', nev: 'Új jegyzet', akkord: 'Mod+N' }` to `UjFul.svelte:9-15`. Optionally a second command `fajl.uj-azonnal` that calls `POST /api/vault/uj {mappa, nev: 'Névtelen', tipus: 'md'}` (`docs/dev/ARCHITECTURE.md:70`) in the active note's folder and opens it with `megnyit(ut, 'aktiv')` + `FajlCim` focused (`app/src/szerkeszto/FajlCim.svelte`), which is closer to Obsidian's ⌘N feel; keep the tree variant as the quiet-mode default.

### 06-workspace-07 · Tab-group commands and directional focus — should · S · confidence high
- **Obsidian**: "Close all other tabs", "Close tabs to the right", "Close this tab group", "Close all tabs in group"; "Focus on tab group to the left/right/above/below" (no default hotkeys for the focus commands, confidence medium).
- **Manifold**: only `panel.kovetkezo/elozo` in tree order, no hotkey (`alapParancsok.ts:143-144`, `munkaterulet.svelte.ts:242-246`).
- **Proposal**: add to `Munkaterulet`: `bezarTobbi`, `bezarJobbra`, `bezarMind`, `panelBezar(panelId)` (= `bezarMind` then `uresPanel`), and `panelIrany(irany: 'bal'|'jobb'|'fel'|'le')` computed from the rendered panels' `getBoundingClientRect()` relative to the active one (geometry in the component layer: `Panel.svelte` can expose `data-panel-id`; the command reads the DOM, then calls `aktival`). Register `ful.bezar-tobbi`, `ful.bezar-jobbra`, `ful.bezar-mind`, `panel.bezar`, `panel.fokusz-bal/jobb/fel/le` (category Panel) in `alapParancsok.ts`; suggested hotkeys `Mod+Alt+Shift+ArrowLeft/Right/Up/Down` with `szerkesztoNyer: true` only if CodeMirror binds them (check `app/src/szerkeszto/beallitas.ts`).

### 06-workspace-08 · Linked tab groups — should · M · confidence high
- **Obsidian**: "Link with tab…" pairs two groups: opening a file in one opens it in the other, and scroll follows (editing + reading side by side). Linked groups show a link icon in the tab bar.
- **Manifold**: no relation between panels.
- **Proposal**: `kapcsolt?: string` on `PanelCs` (a group id; both panels share it), set by a new command `panel.osszekapcsol` (picker of other panels via `ListaValaszto`) and the tab menu (gap 04). In `Munkaterulet.megnyit()` after setting the file, mirror to every panel with the same `kapcsolt` (open or switch to the file there, `mod: 'aktiv'`). Scroll sync: the editor already tracks the top line (`Szerkeszto.svelte:180, 184`); add a lightweight `szerkesztok` broadcast (`app/src/szerkeszto/szerkesztok.svelte.ts`) keyed by `kapcsolt` so a linked editor calls its existing `gorget()`; defer scroll sync to a second step if needed. Serialise through `sorosit()`; `ervenyes()` must accept the optional string.

### 06-workspace-09 · Stacked tabs — nice · L · confidence high
- **Obsidian**: per group "Stack tabs": tabs become sliding cards with vertical title strips, several visible at once.
- **Manifold**: none.
- **Proposal**: `halmozott?: boolean` on `PanelCs`; `Panel.svelte` renders all `fulek` views in a horizontally scrolling flex row with sticky rotated headers; `Fulsor.svelte` becomes the header strip. Because `Panel.svelte` mounts only the active view (`:44-48`, `{#key}`), stacking needs every view mounted — editor state caching already exists per tab (`szerkesztok.tarol`, `Szerkeszto.svelte:196`). Large; schedule after 01–08.

### 06-workspace-10 · Maximize / minimize pane — nice · S · confidence low
- **Obsidian**: I believe there is no core maximize; community plugins add it. Listed because the brief asks for it.
- **Manifold**: none.
- **Proposal (optional)**: `nagyitott?: string` (panel id) on `Munkaterulet` kept **out** of `sorosit()`; `Osztas.svelte` renders only the subtree containing it (or hides siblings with `display: none` so views keep state); command `panel.nagyit` ("Panel nagyítása / visszaállítása"). Cheap; not required for parity.

### 06-workspace-11 · Pop-out windows — nice · L · confidence high
- **Obsidian**: "Open in new window" / "Move to new window"; each window is an independent workspace root; ⌘⇧W closes the window.
- **Manifold**: one window; the shell exits when another core runs on the vault (`AppController.swift:378-382`) and the state file is single (`felulet.svelte.ts:1-3`).
- **Proposal**: a second `WKWebView` window in the shell sharing the same core, with the page loading `#ablak=<id>` and the `Munkaterulet` keyed per window inside `felulet.json` (`munkaterulet` → `ablakok: {id: …}`), the first window being the owner of sidebars. Requires the `Mento` to merge rather than overwrite (`felulet.svelte.ts:274-346`). Out of scope for the first parity round.

### 06-workspace-12 · Ribbon parity and configuration — should · M · confidence high (icons) / medium (hide & reorder)
- **Obsidian**: ribbon icons for quick switcher, graph, new canvas, daily note, command palette, templates; bottom: settings, help, vault switcher; right-click to hide icons, drag to reorder; "Show ribbon" toggle in Appearance.
- **Manifold**: four fixed buttons + presence (`Ikonsav.svelte:9-17`); daily note (`naplo.napi` ⇧⌘D, `app/src/ma/index.ts:26`), graph (`graf` module commands), quick switcher and palette exist as commands but not as icons; no settings icon (gap 27).
- **Proposal**: drive the ribbon from a list of registry ids stored in `felulet.json` (`ikonsav: {rejtett: string[], sorrend: string[]}` in `Felulet`, defaults = today's four + `hej.valto`, `graf.megnyit` (check the id in `app/src/graf/index.ts`), `naplo.napi`, `hej.paletta`, bottom: `hej.beallitasok` from gap 27). Render with `IkonGomb` using `Parancs.ikon`/`nev`/`billentyu` from `regiszter.kap(id)` so tooltips and hotkeys stay in sync. Right-click → `lebegoMenu` with "Ikon elrejtése" and "Ikonsáv elrejtése" (`felulet.ikonsav.rejtve`; `Hej.svelte:91` grid column becomes 0). Drag reorder can reuse the tab-bar drag code.

### 06-workspace-13 · Sidebar width cap — nice · S · confidence medium
- **Obsidian**: sidebars can be dragged very wide (no fixed max).
- **Manifold**: 480 px max for both (`felulet.svelte.ts:10-11`), enforced in `Atmeretezo` (`:25`) and on load (`:112, 118`).
- **Proposal**: raise `max` to e.g. 50 % of the window (compute in `Hej.svelte` from `innerWidth` and pass to `Atmeretezo`), keep the persisted clamp as a sanity limit (e.g. 1200).

### 06-workspace-14 · Hover-reveal of the collapsed right panel — nice · S · confidence medium
- **Obsidian**: hovering the collapsed sidebar's edge reveals it as an overlay (both sides).
- **Manifold**: left edge only (`csend.svelte.ts:56-58, 163-167`); right only via F6 (`JobbPanel.svelte:38-41`).
- **Proposal**: add `egerJobb(x, most, szelesseg, ablakSzelesseg)` next to `egerBal` in `csend.svelte.ts` and toggle `csend.jobbAtfedes` in `mozog()` symmetrically (`:158-167`); the overlay CSS already exists (`JobbPanel.svelte:217-232`). Add a case to `app/tests/csend.test.ts`.

### 06-workspace-15 · Rearrangeable sidebar views — nice · L · confidence high
- **Obsidian**: every sidebar view is a leaf: tabs within a sidebar, drag to the other sidebar, split a sidebar vertically, drag a view into the main area.
- **Manifold**: fixed left tabs (`Oldalsav.svelte:37-40`) and a fixed right stack (`JobbPanel.svelte:173-195`). The right stack with counts and persistent open state is arguably better for its content (see strength 3.11).
- **Proposal (long-term)**: model each sidebar as a `PanelCs` of view-tabs (`nezet.tipus = 'fa' | 'cimkek' | 'visszahivatkozasok' | …`) rendered by the same `Osztas/Panel` tree, registered in `nezetek` (`app/src/lib/elrendezes/nezetek.svelte.ts:30-40`). Keep the stacked section layout as the default right-sidebar view ("Kapcsolatok") so nothing is lost. Decide in Q2/Q3 whether this is wanted at all.

### 06-workspace-16 · Word and character count in the status bar — must · S · confidence high
- **Obsidian**: "N words, M characters" for the active note; with a selection, the selection's counts.
- **Manifold**: none (`Allapotsor.svelte:72-78`).
- **Proposal**: new pure helper `app/src/lib/szoveg/szoszam.ts` (`Intl.Segmenter('hu', {granularity: 'word'})` with `isWordLike`, characters = code points) with unit tests; the status bar reads `szerkesztok.aktiv` (`app/src/szerkeszto/szerkesztok.svelte.ts`) → the CodeMirror doc / selection, debounced 300 ms (the doc already exposes `valtozat()`, used in `JobbPanel.svelte:82`). Render as an `.elem` before the index text (`Allapotsor.svelte:76-77`), `tabular-nums` is already set (`:119`). Quiet mode: do **not** make the count a "mondanivaló" (`csend.svelte.ts:32-41`) – it appears with the bar on hover/focus (Q9); offer a ⌘P toggle `allapotsor.szoszam` persisted in `felulet.json`.

### 06-workspace-17 · Backlinks count in the status bar — should · S · confidence medium
- **Obsidian**: "N backlinks" status item (Backlinks core plugin); click opens the backlinks pane.
- **Manifold**: count only in the right-panel section header (`JobbPanel.svelte:144, 173`), computed from `GET /api/vault/visszahivatkozasok?ut=` (`app/src/lib/vault/kapcsolatok.svelte.ts:82`).
- **Proposal**: lift the `Kapcsolatok` instance out of `JobbPanel.svelte:34` into `kornyezet()` (`app/src/lib/kornyezet.ts`) so both the panel and `Allapotsor.svelte` read `k.visszahivatkozasok`; the panel's "load only when visible" rule (`JobbPanel.svelte:54-63`) must then be driven by "panel visible OR status bar visible". Clicking the item runs `hej.jobb-panel` + sets `felulet.jobbPanel.visszahivatkozasok = true`.

### 06-workspace-18 · Save / snapshot / backup state in the status bar — nice · S · confidence medium (Obsidian Sync is paid, so this is an analogue, not parity)
- **Obsidian**: Sync icon with state; nothing for local vaults.
- **Manifold**: the editor corner shows "Mentve" (`app/src/szerkeszto/MentesJelzes.svelte`), snapshots live in Előzmények (`JobbPanel.svelte:185-187`), backup state in Rendszer (`docs/plan/audit/03-felulet.md:206-217`).
- **Proposal**: optional `.elem` with the last snapshot / last backup age from `GET /api/vezerlo/rendszer` (`docs/dev/ARCHITECTURE.md:281`, already polled by `hej/vezerlo/Rendszer.svelte`); a stale backup counts as "mondanivaló" (warning) in `allapotsorMondanivalo()`.

### 06-workspace-19 · Pinned palette commands — nice · S · confidence high
- **Obsidian**: Settings → Command palette → "Pinned commands"; pinned ones appear first with a pin icon.
- **Manifold**: recency only (`Paletta.svelte:30-43`).
- **Proposal**: `kituzottParancsok: string[]` in `FeluletMentes`/`Felulet` (next to `legutobbiParancsok`, `felulet.svelte.ts:45, 65`), sorted before recent in `talalatok` (`Paletta.svelte:34-42`) and given a bonus in the fuzzy branch (`:47-50`). Toggle with a pin button in the row (`sor` snippet `:83-87`, pointer only) and a command `paletta.kituz` on the highlighted row (needs `ListaValaszto` to expose the active item – add an `onmasodlagos` callback for `Mod+Shift+Enter`, `ListaValaszto.svelte:72-86`).

### 06-workspace-20 · Hotkey customisation — should · M · confidence high
- **Obsidian**: Settings → Hotkeys: search, assign/remove, conflicts flagged, "restore default".
- **Manifold**: hotkeys are literals in each module's registration (`alapParancsok.ts`, `app/src/szerkeszto/index.ts:84-202`, …); `regiszter.regisztral` normalises and refuses conflicts (`regiszter.ts:58-66`); the Hungarian-layout rules live in `billentyuk.ts:1-6, 70-87`.
- **Proposal**: `billentyuk: Record<string, string | null>` in `felulet.json` (command id → chord, `null` = unbound). `Regiszter` gets `felulir(map)` that rebuilds `akkordok` from `parancsok` + overrides (an override that conflicts with a non-overridden default evicts the default's chord and reports it). Display (`Parancs.billentyu`, `Billentyu.svelte`, `IkonGomb.svelte:33-34`) must read the effective chord — expose `regiszter.akkord(id)` and use it in `Paletta.svelte:86`. Editing UI belongs in the settings window (gap 27); until then a palette-only flow is possible (`parancs.billentyu-beallit` → record the next keydown). CodeMirror-owned chords (`szerkesztoNyer`, `regiszter.ts:29-31`) stay outside this map in the first step.

### 06-workspace-21 · Aliases in the quick switcher — should · S · confidence high
- **Obsidian**: alias rows ("alias → note") are matched and shown; opening goes to the note.
- **Manifold**: `fajlok.kereso()` indexes basename + folder only (`fajlok.svelte.ts:64-67`); aliases are already available (`GET /api/vault/aliasok`, `linkek.svelte.ts:144`) and used in `[[` completion (`kiegeszites.ts:96-101`).
- **Proposal**: in `Valto.svelte` build the `FuzzyIndex` from `fajlok.lista` **plus** one `Jelolt` per alias (`{ertek: {info, alias}, nev: alias, ut: fajlNev(ut)}`) exactly as `fajlJeloltek` does; dedupe by `ut` keeping the best score; render the alias row with a `CornerDownRight`-style icon and the note name muted. Fetch aliases through `linkek.aliasok()` on open (cached, invalidated on `vault_valtozas` as it is today).

### 06-workspace-22 · Create a note from the quick switcher — must · S · confidence high
- **Obsidian**: ⇧↵ creates a note named after the query; if nothing matches, the first row reads "Create new note: <query>" (↵ creates); ⌘⇧↵? not core (ignore).
- **Manifold**: empty state text only (`Valto.svelte:50-56`); `Modositok` has `uj`/`oszt` only (`ListaValaszto.svelte:6-9, 69`).
- **Proposal**: extend `Modositok` with `letrehoz: e.shiftKey` (`ListaValaszto.svelte:66-70`) and add a `letrehozSor` snippet rendered as the last (or only) row when the trimmed query is non-empty and no exact name match exists. On select: `POST /api/vault/uj {mappa, nev, tipus: 'md'}` (`docs/dev/ARCHITECTURE.md:70`) into the active note's folder (fallback: vault root or `[sablon]` default – Q6), then `felulet.munkaterulet.megnyit(ut, mod)` honouring ⌘/⌥⌘, and `felulet.fajlNyitva(ut)`. Reuse the creation + error path of `jegyzetLetrehoz` (`app/src/szerkeszto/linkek/navigacio.ts`, used in `JobbPanel.svelte:135-142`). Footer hint `<Billentyu akkord="Shift+Enter" /> új jegyzet` (`Valto.svelte:84-90`).

### 06-workspace-23 · Unresolved links and file-type scope in the switcher — nice · M · confidence medium
- **Obsidian**: unresolved link targets are listed (creatable) unless "Show existing only"; "Show attachments" / "Show all file types" default off, so the default list is notes (+ canvases).
- **Manifold**: every file type always (`Valto.svelte:79-83`); no unresolved targets.
- **Proposal**: keep "all types" as the default (strength 3.9) but add a persisted filter `valto: {csakJegyzet: boolean, feloldatlan: boolean}` in `felulet.json`, toggled with a small segmented control under the input (or ⌘P commands). Unresolved targets: the core already resolves links (`/api/vault/jegyzet` → `linkek[].cel = null`, `docs/dev/ARCHITECTURE.md:158`); an aggregate `GET /api/vault/feloldatlan` (new core endpoint, index-only) would feed rows that use gap 22's create path with the link's expected location (`POST /api/vault/uj {link: {cel, forras}}`, `ARCHITECTURE.md:70`).

### 06-workspace-24 · Back/forward arrows in the view header with a history list — should · S (arrows) · M (list) · confidence high / medium
- **Obsidian**: ← → in the tab's view header; disabled when empty; right-click/long-press shows the history list.
- **Manifold**: hotkeys only (`alapParancsok.ts:127-128`); `Munkaterulet.mult` is private (`munkaterulet.svelte.ts:64`).
- **Proposal**: expose `elozmenyAllapot(fulId): {vissza: number, elore: number}` (and a read-only list) on `Munkaterulet`; add two `IkonGomb`s (`ArrowLeft/ArrowRight`, `data-csend-rejt`) at the start of the active panel's tab bar in `Fulsor.svelte` (only on the active panel, like Obsidian), `disabled` when the stack is empty, running `navigacio.vissza/elore`. Long-press/right-click → `lebegoMenu` of the entries (title from `fajlNev`), selecting jumps n steps (`navigal` called n times).

### 06-workspace-25 · Mouse back/forward buttons and trackpad swipe — nice · S · confidence medium
- **Obsidian**: mouse buttons 4/5 navigate; two-finger swipe in the editor navigates (Electron default).
- **Manifold**: no handler (`Fulsor.svelte:111-113` only middle-click).
- **Proposal**: in `csendTelepit`-style global listeners (`App.svelte:93-112`), `auxclick`/`pointerup` with `e.button === 3 | 4` → `regiszter.futtat('navigacio.vissza'|'elore', 'egyeb')`. Swipe: WKWebView's `allowsBackForwardNavigationGestures` must stay **off** (it would navigate the page); emulate with `wheel` deltaX accumulation guarded by `szerkesztheto()` not being horizontally scrollable – optional.

### 06-workspace-26 · Named workspace layouts — should · M · confidence high
- **Obsidian**: Workspaces core plugin: save current layout under a name, load, delete, "Manage workspace layouts" modal; layouts include sidebars.
- **Manifold**: one layout, auto-saved (`felulet.svelte.ts:43, 217-235`).
- **Proposal**: `elrendezesek: {nev: string, munkaterulet: …, oldalsav: {nyitva, nezet}, jobbPanel: {nyitva}}[]` in `FeluletMentes` (bounded, e.g. 20 × the 2 KB-per-tab cap). Commands `elrendezes.ment` (name prompt via `ListaValaszto` with a free-text row), `elrendezes.betolt` (picker) and `elrendezes.torol`. Loading = `this.munkaterulet.betolt(snapshot)` (`munkaterulet.svelte.ts:104-110`, already validates) + sidebar flags; the editor remounts per `{#key}` (`Panel.svelte:45`). No core change (same `PUT /api/felulet/allapot`).

### 06-workspace-27 · Settings window on ⌘, — must · L · confidence high
- **Obsidian**: ⌘, opens a modal with a left category list (Options: General, Editor, Files and links, Appearance, Hotkeys, Core plugins, …) and a search box; the App menu has "Settings…".
- **Manifold**: no settings surface; preferences are ⌘P commands and overview sections (`docs/plan/audit/03-felulet.md:186-246`); `felulet.json` already holds the user-level values (`felulet.svelte.ts:24-46`); core-level switches use `kapcsolok.json` (`03-felulet.md:236`); the shell App menu has no item (`AppController.swift:320-331`).
- **Proposal**: follow `03-felulet.md:238-246`: a `beallitasok` **view tab** registered in `nezetek` (`App.svelte:54-55` pattern, like `manifold`/`dolgozat`) opened by `hej.beallitasok` on `Mod+,` (`billentyuk.ts:45-58` already accepts a single-character key `,`; verify `esemenybol` maps `e.key === ','`, `:77-78`) and via `megnyitNezet('beallitasok')` so only one instance exists (`munkaterulet.svelte.ts:161-180`). Content: category list (Általános, Szerkesztő, Megjelenés, Billentyűk [gap 20], Parancspaletta [gap 19], Ikonsáv [gap 12], Gyorsváltó [gap 23], Értesítések, Asszisztens/Tracker switches from `hej/vezerlo/Kapcsolok.svelte`), a search box filtering rows, each row calling the existing registry command or writing `felulet`. Shell: add "Beállítások…" with `keyEquivalent: ","` to the App menu calling `window.manifold.parancs('hej.beallitasok')` (`AppController.swift:375-378`). Obsidian uses a modal; a tab fits the quiet-mode design (DESIGN.md:7-9) and the `Atfedes` sizing (`Atfedes.svelte:94-102`) is too small for a settings page – decide in Q5.

### 06-workspace-28 · UI zoom ⌘= / ⌘- / ⌘0 — should · S · confidence high
- **Obsidian**: Zoom in / Zoom out / Reset zoom, persisted per vault.
- **Manifold**: none; `zoom` appears only in plot/graph code (grep).
- **Proposal**: `nagyitas: number` (0.8–1.6) in `felulet.json`; commands `nezet.nagyit`, `nezet.kicsinyit`, `nezet.nagyitas-alap` with `Mod+=`, `Mod+-`, `Mod+0` (digits use `event.code`, `billentyuk.ts:73-74`; `=`/`-` go through `e.key.length === 1`, `:78`; confirm on the Hungarian layout that ⌘- is reachable, DESIGN.md:135). Apply with `document.documentElement.style.zoom` (WebKit supports CSS `zoom`; alternatively the shell's `webView.pageZoom` via `hejnek({tipus: 'nagyitas'})`, `app/src/lib/core/hej.ts`). The 4-px grid rule (DESIGN.md:11) argues for `pageZoom` in the shell so tokens stay integral at 1.0 and scale uniformly otherwise.

### 06-workspace-29 · Help shortcut — nice · S · confidence medium
- **Obsidian**: F1 / ribbon "Help" opens the help vault.
- **Manifold**: none.
- **Proposal**: `hej.sugo` on `F1` opening `README.md`/`docs` in the default browser through the shell (`hejnek({tipus: 'kulso-link'})` – the external-link path from E3, `docs/dev/ARCHITECTURE.md:190`).

### 06-workspace-30 · Tab bar shows no pinned/linked/stacked state icons — nice · S · confidence high
Follows from gaps 01/08/09; listed so the `Fulsor.svelte` row model (`:103-144`) is extended once: icon slot before the title for pin/link, and the ⋯ affordance for gap 04 on the active tab (`data-csend-rejt`).

### 06-workspace-31 · Startup always re-opens the Manifold overview tab — nice · S · confidence high (behavioural difference, product decision – Q1)
- **Obsidian**: restores exactly the saved layout; no forced tab.
- **Manifold**: `main.ts:19` calls `megnyitNezet('manifold')` on every start (CX-007), and `kesoBetoltes` re-adds it (`felulet.svelte.ts:164-167`).
- **Proposal**: keep as default but make it a `felulet.json` flag (`indulas: {attekinto: boolean}`) exposed in settings (gap 27) so Obsidian-style "exactly as left" is available.

---

## 3. Manifold strengths beyond Obsidian (preserve)

1. **Quiet mode (Csend és elérés, C38)** – auto-hiding status-bar overlay that only appears with something to say, edge-reveal of the hidden sidebar, typing fade of chrome, nothing reachable by hover only (`app/src/lib/elrendezes/csend.svelte.ts:32-58, 120-185`; `docs/dev/DESIGN.md:320-342`; guarded by `app/tests/csend.test.ts`). Obsidian has no equivalent; every proposal above must respect `data-csend-rejt` / `data-csend-terulet`.
2. **Full keyboard + ARIA workspace** – tab bar is a real `tablist` with ←→/Home/End/Delete (`Fulsor.svelte:42-57, 90-100`), splits and sidebar edges are focusable `separator`s resizable from the keyboard (`Elvalaszto.svelte:26-32, 37-52`; `Atmeretezo.svelte:49-59, 64-79`), F6/⇧F6 region cycling including hidden regions (`fokusz.ts:66-93`), palette/switcher as combobox+listbox with `aria-activedescendant` (`ListaValaszto.svelte:1-3, 91-108`), `aria-keyshortcuts` on buttons (`IkonGomb.svelte:33-34`). Obsidian's workspace is largely mouse-first.
3. **Per-tab persisted view state** – mode, top line and cursor per tab, ≤ 2 KB, validated on load (`munkaterulet.svelte.ts:8-13, 337-345`; `Szerkeszto.svelte:63-65, 180, 195-196`), plus an in-memory CodeMirror state cache per tab (undo history survives tab switches).
4. **Per-tab back/forward with 50 entries that survives close/reopen and renames** (`munkaterulet.svelte.ts:64-95, 143, 206-210, 281-288`).
5. **Layout persistence through the core with no-clobber guarantees** – load before first paint (`main.ts:16-21`), lockout when the load failed, late merge that keeps files opened meanwhile (`felulet.svelte.ts:95-97, 161-173, 261-270`), debounced save with keepalive and exponential retry (`:274-346`), tests `app/tests/felulet-betoltes.test.ts:23-133`. Obsidian's `workspace.json` is overwritten on every change.
6. **Single command registry** – palette, hotkeys, buttons, new-tab page and the macOS Nézet menu all run the same ids (`regiszter.ts:14-33, 105-128`; `AppController.swift:349-362`; `UjFul.svelte:9-15`); hotkey conflicts fail at startup (`:58-66`, `app/tests/billentyu-utkozes.test.ts`); availability predicates; command errors surface as notifications (`:108-116`); usage observers feed the tracker (`:37-53`).
7. **Hungarian-layout-aware chords** – letters by label, digits by physical key, Option-rewritten letters by code (`billentyuk.ts:1-6, 70-87`); must remain the single authority when hotkeys become editable (gap 20).
8. **Palette recency + typo-tolerant, accent-insensitive fuzzy** (`Paletta.svelte:30-52`; `fuzzy.ts:1-7, 78-105`). Obsidian's palette is exact-fuzzy without recency (confidence low on recency).
9. **Quick switcher scope** – all file types with type icons, folder path as secondary match, recent-first, modifier open modes identical to Obsidian (`Valto.svelte:20-48, 62-65, 79-83`).
10. **Default hotkeys where Obsidian has none** – ⌥⌘1/⌥⌘2 sidebars, ⇧⌘2/⌥⌘↓ splits (`alapParancsok.ts:97-98, 141-142`; confidence medium that Obsidian ships none).
11. **Right panel as a stacked, counted section list** – backlinks, unlinked mentions with one-click linking, outgoing links with "create", outline, git-backed history, hygiene, similar notes, all with persistent open state and lazy loading only while visible (`JobbPanel.svelte:54-63, 173-195`; `felulet.svelte.ts:30, 57`). Obsidian splits these across separate views.
12. **Status bar extras** – core connection warning, index building/error state, note count, notification history with unread badge (`Allapotsor.svelte:64-102`; `csend.svelte.ts:32-41`). Obsidian notices have no history.
13. **Rename/delete robustness** – tabs, history and closed-tab stack retarget on rename incl. folder prefixes (`munkaterulet.svelte.ts:281-288`; `felulet.svelte.ts:190-195`); deleted files empty their tabs, with a guard against a transiently unavailable vault (`fajlok.svelte.ts:38-41, 89-95`; `App.svelte:49`).
14. **Overlay focus discipline** – focus trap, opener gets focus back after the closing animation, scope stack so only `atfedesben` hotkeys run under a modal (`Atfedes.svelte:21-40, 74`; `app/src/lib/fokusz/hatokor.ts`; `kezelo.ts:15`).
15. **Reduced-motion-aware transitions and tokenised timing** (`app/src/lib/elrendezes/mozgas.ts:3-11`; sidebar overlay `@starting-style`, `Oldalsav.svelte:117-132`).
16. **No layout shift on start** – sidebar widths final at first paint, the shell shows the window only on `kesz` (`Hej.svelte:1-3`; `main.ts:24-28`; DESIGN.md:10).
17. **Actionable new-tab page** with hotkey chips (`UjFul.svelte:9-30`).
18. **Single-instance safety** – a second core on the same vault is refused with a message instead of a corrupted state (`AppController.swift:378-382`); keep when considering pop-out windows (gap 11).

---

## 4. Open questions

- **Q1 – Forced overview tab on start** (`main.ts:19`, `felulet.svelte.ts:164-167`): keep as the product's "home" or make it a setting (gap 31)? Obsidian users expect "exactly as left".
- **Q2 – Search as a modal (E3) vs. a sidebar view**: Obsidian keeps search results beside the editor while reading them; Manifold's `KeresoAblak` closes on open. Is a persistent left-sidebar "Keresés" tab wanted back, or is the modal + quiet mode the deliberate answer? (Affects gap 15.)
- **Q3 – Rearrangeable sidebars (gap 15)**: is the fixed stacked right panel a design decision to keep (strength 3.11)? If yes, drop gap 15 and only add the missing items (backlinks count, hover-reveal).
- **Q4 – Binary vs n-ary splits**: a three-column layout is two nested binary splits (`munkaterulet.svelte.ts:27-38`), so resizing the first divider rescales both other columns. Obsidian's n-ary split resizes neighbours only. Accept, or extend `OsztasCs` to `gyerekek: Csomopont[]` + `aranyok` (M, touches `Osztas.svelte`, `Elvalaszto.svelte`, `ervenyes()`)?
- **Q5 – Settings as a tab or a modal** (gap 27): `03-felulet.md:238-246` suggests a view tab; Obsidian uses a modal; the existing `Atfedes` is sized for lists (`Atfedes.svelte:94-102`). A tab keeps quiet mode and ⌘W semantics; a modal matches ⌘, muscle memory.
- **Q6 – Default location for notes created from the switcher / ⌘N** (gaps 06, 22): Obsidian has "Default location for new notes" (vault root / current folder / specified). Manifold's tree creates in the focused folder; `[sablon]` config exists (`03-felulet.md:236`). Which rule, and should it live in `felulet.json` or `os.toml`?
- **Q7 – Pin semantics vs. "already open" reuse**: `megnyit('aktiv')` jumps to an existing tab holding the file (`munkaterulet.svelte.ts:137-139`); with pinning, should a pinned tab holding the file be activated (Obsidian: yes) even when the user is in another group?
- **Q8 – History persistence across restarts**: `mult` is not serialised (`munkaterulet.svelte.ts:64, 290-295`). I am not certain whether Obsidian persists per-leaf history (confidence low); if parity requires it, add `elozmeny` to `Ful` under the 2 KB cap.
- **Q9 – Status-bar counts under quiet mode**: a word count that is hidden by default (overlay only on hover/focus) may read as "missing". Options: show counts in the editor header strip instead (`Szerkeszto.svelte` fejléc, also hover-revealed), or make the status bar's "mondanivaló" rule configurable.
- **Q10 – Hotkey remapping scope** (gap 20): include CodeMirror-owned chords (`szerkesztoNyer`, `regiszter.ts:29-31`, `app/src/szerkeszto/beallitas.ts`) in the override map, or keep editor keymaps fixed in the first version?
- **Q11 – Pop-out windows vs. single-instance lock** (gap 11, strength 3.18): is multi-window a goal at all for a quiet-mode product on one SSD?
- **Q12 – Sidebar width cap** (gap 13): is 480 px a deliberate reading-width decision (DESIGN.md:8) or incidental?
