# 13 — Command palette, quick switcher, hotkeys, page preview, status bar, file recovery, format converter: Obsidian parity audit

**Subsystem:** the keyboard-first navigation layer: the command palette (⌘P), the quick switcher (⌘O), hotkey assignment and conflict handling, hover page preview, the word/character count in the status bar, note version history (the Manifold counterpart of Obsidian's File recovery) and the one-off Format converter.
**Reference:** Obsidian 1.8/1.9 desktop, core plugins only (Command palette, Quick switcher, Page preview, Word count, File recovery, Format converter) plus *Settings → Hotkeys*. The Obsidian behaviour was re-read from the official help pages (`obsidian.md/help/plugins/command-palette`, `/quick-switcher`, `/page-preview`, `/word-count`, `/file-recovery`, `/format-converter`, `/hotkeys`, `/status-bar`), restated in my own words. Where the help pages are silent and I rely on memory, the row is marked `confidence: low` or `medium`; no **must** rests on such a claim.
**Code read** (paths relative to `/Volumes/Work/[UNI] Manifold-OS`): `app/src/atfedes/{Paletta,Valto}.svelte`, `app/src/lib/ui/{ListaValaszto,Billentyu}.svelte`, `app/src/lib/parancsok/{regiszter,billentyuk,kezelo}.ts`, `app/src/lib/kereses/fuzzy.ts`, `app/src/alapParancsok.ts`, `app/src/beallitasok/Beallitasok.svelte`, `app/src/lib/elrendezes/felulet.svelte.ts`, `app/src/hej/Allapotsor.svelte`, `app/src/hej/kapcsolatok/{Elozmenyek,ElozmenyDiff}.svelte`, `app/src/lib/vault/elozmeny.ts`, `app/src/szerkeszto/linkek/elonezet.ts`, `core/elozmeny.py`, `core/snapshot.py` (`fajl_naplo`), `core/importalas.py`, `core/index/elemzo.py`, `shell/Sources/AppController.swift` (menus), and the tests `app/tests/{atfedes,fuzzy,parancsok,i18n-paletta,beallitasok.svelte,billentyu-utkozes,f11-workspace.svelte,elonezet}.test.ts`, `tests/test_elozmeny.py`.

**Legend.** Status: *present* / *partial* / *missing* / *ahead* (Manifold does more or safer than Obsidian) / *n.a.* (not an Obsidian core behaviour). Weight: **must** = daily Obsidian habit users miss at once · **should** = noticeable · **could** = polish. Size: S (<1 day) · M (1–3 days) · L (>3 days). Gap identifiers `13-palette-NN` point to section 2. Items already owned by the 06-workspace, 07-explorer or 08-search audits are referenced, never duplicated.

**Overview.** This subsystem is the strongest part of the Manifold shell. One registry feeds the palette, the hotkeys, the buttons and the macOS menu; the fuzzy matcher is accent-insensitive and typo-tolerant; the switcher already covers aliases, create-from-query (↵ / ⇧↵), ⌘↵ and ⌥⌘↵; hotkeys are customisable with conflict rejection; hover preview, word count and backlink count are in place; and note history is a git-backed, revert-based, undoable restore with a diff view that is safer than Obsidian's overwrite. The audit finds **no must-level gap** (the must items of this area — ⌘N, create from the switcher, word count, hotkey customisation, aliases — are already `Verified` in 06-workspace). It finds **six should-level gaps**: Obsidian hotkeys are dropped on import, the settings validator reserves only two chords although the native menu owns many more, the switcher has no `#`/`^` syntax, deleted notes have no history entry point, history stops at 50 (UI) / 200 (core) versions, and `.canvas`/`.base` notes have no history in the UI. Six could-level items round it off.

---

## 1. Checklist

### 1.1 Command palette

| # | Obsidian behaviour | Manifold today (path:line) | Status | Weight | Size | Confidence | Gap |
|---|---|---|---|---|---|---|---|
| 1 | ⌘P opens the palette; the same key closes it; ribbon icon | `alapParancsok.ts:66` (`hej.paletta`, `Mod+P`, `atfedesben: true`), toggle `:50-52`; ribbon via 06-workspace-12 | present | – | – | high | – |
| 2 | Type part of a command name, ↑↓ to move, ↵ to run | `ListaValaszto.svelte:75-89` (↑↓, ⌃N/⌃P, PageUp/Down, ↵, Esc), `Paletta.svelte:63-70` | present (ahead: ⌃N/⌃P, PageUp/Down) | – | – | high | – |
| 3 | Fuzzy matching ("scf" finds "Save current file") | `fuzzy.ts:1-8` (word start > substring > typo-tolerant > subsequence with word-start letters), `Paletta.svelte:27-29,46-52`; `fuzzy.test.ts:57-65` (`msor` → *Mértani sorozat*) | present (ahead: accent-insensitive, Damerau–Levenshtein typo tolerance) | – | – | high | – |
| 4 | Category prefix in each row ("Plugin: Command") | `Paletta.svelte:85` (`kategoria` + `::after ':'`) | present | – | – | high | – |
| 5 | Hotkey shown next to the command; reflects a user-set hotkey | `Paletta.svelte:87`; `regiszter.ts:149-159` rewrites `p.billentyu` and notifies, `Paletta.svelte:20` re-renders | present | – | – | high | – |
| 6 | Recent commands first (since 1.8.3); once typing, shorter names outrank recent | `felulet.svelte.ts:16,411` (20 entries), `Paletta.svelte:32-44` (empty query: recents first), `:47-51` (typing: recency is a +5…+20 score bonus, not a shorter-name rule); `atfedes.test.ts:162` | present (rule differs slightly) | – | – | high | – |
| 7 | Pinned commands stay on top; managed in settings | none (`legutobbiParancsok` only, `felulet.svelte.ts:101,156`) | missing | could | S | high | 06-workspace-19 (owned there, nice) |
| 8 | Only commands valid in the current context are listed | `regiszter.ts:117-123,161-164` (`elerheto`, module gate `parancsEngedelyezett`); `beallitasok.svelte.test.ts` (disabled modules hide commands) | present | – | – | high | – |
| 9 | Command arguments | Obsidian core has none (the help page does not describe any); Manifold `Parancs.futtat` takes none (`regiszter.ts:41`) | n.a. | – | – | medium | – |
| 10 | Command failure is visible | `regiszter.ts:176-185` (notification with the command name on sync and async failure) | ahead | – | – | high | – |
| 11 | Focus returns to the invoking editor before the command runs | `Paletta.svelte:59-70` (`fokuszban()` + `focus()` before `futtat`); `atfedes.test.ts:134` | ahead | – | – | high | – |
| 12 | Palette labels follow the UI language, search runs on the localised name | `regiszter.ts:44-52` (`parancsNev`/`parancsKategoria`), `Paletta.svelte:28`; `i18n-paletta.test.ts:62,79` | ahead | – | – | high | – |

### 1.2 Quick switcher

| # | Obsidian behaviour | Manifold today (path:line) | Status | Weight | Size | Confidence | Gap |
|---|---|---|---|---|---|---|---|
| 13 | ⌘O opens; fuzzy match on note name | `alapParancsok.ts:67` (`Mod+O`), `Valto.svelte:36-39,63-69`, folder shown muted (`:120`) | present | – | – | high | – |
| 14 | Aliases are matched and shown | `Valto.svelte:22,28-39,119-120` (alias row, note name muted); `f11-workspace.svelte.test.ts:123,134` | present | – | – | high | 06-workspace-21 (Verified) |
| 15 | Empty query lists recent notes; ↓ ↵ toggles between the last two | `Valto.svelte:46-61` (recents, then newest-modified); the current file is row 0 (`felulet.svelte.ts:406-408`), so ↓ ↵ reopens the previous note; `atfedes.test.ts:38` | present | – | – | medium | – |
| 16 | ↵ with no match creates a note named after the query | `Valto.svelte:80-93`, `ListaValaszto.svelte:82` (`onbevitel`); `f11-workspace.svelte.test.ts:153` | present | – | – | high | 06-workspace-22 (Verified) |
| 17 | ⇧↵ creates even when similar notes exist | `Valto.svelte:89-93`, footer button `:126`; `f11-workspace.svelte.test.ts:153-168` | present | – | – | high | 06-workspace-22 |
| 18 | ⌘↵ opens in a new tab (⇧↵ is *not* "new pane" in Obsidian: it forces creation) | `ListaValaszto.svelte:69-73` (`uj`/`oszt`), `Valto.svelte:99-102`; `atfedes.test.ts:71` | present (ahead: ⌥⌘↵ split) | – | – | high | – |
| 19 | Explicit folder in the typed name (`Folder/Note`) | `ujJegyzetCel` rejects traversal, `#`, `\`, `[ ]` (`f11-workspace.svelte.test.ts:182-188`) | present (ahead: validated by the core) | – | – | high | – |
| 20 | Heading search `Note#Heading` and block search `Note^id` | none: `#` is rejected as an invalid name and shows the "valid note name" error (`Valto.svelte:81,123`; `f11-workspace.svelte.test.ts:188`). Building blocks exist: `/api/vault/fejezetek` (`core/index/api.py:32`, `linkek.svelte.ts:238-241`), block parsing of another note (`kiegeszites.ts:332-350`), anchor jump `szerkesztok.ugras` (`navigacio.ts:108-112`) | missing | should | M | **low** (not in the help page) | 13-palette-03 |
| 21 | Unresolved link targets offered; "Show existing only"; attachment / file-type scope | all file types, no unresolved targets (`Valto.svelte:36-39`) | missing | could | M | medium | 06-workspace-23 (owned there, nice) |
| 22 | Excluded-files patterns rank files lower | no excluded-files setting | missing | could | M | medium | 07-explorer-13 (owned there) |
| 23 | Result row icon / type | `Valto.svelte:118` (`fajlIkon`) | ahead | – | – | high | – |
| 24 | Match highlighting | `Valto.svelte:119` (`Kiemelt`) | present | – | – | high | – |
| 25 | Quick switcher remains usable on a large vault | `fuzzy.test.ts:105` (near-linear cost); limit 50 (`Valto.svelte:19`); no measurement on a 20k-note vault | present (unmeasured) | – | – | medium | – |

### 1.3 Hotkeys

| # | Obsidian behaviour | Manifold today (path:line) | Status | Weight | Size | Confidence | Gap |
|---|---|---|---|---|---|---|---|
| 26 | Settings → Hotkeys: find a command, assign a key, remove it | `Beallitasok.svelte:147-155` (name filter `:36`, key-capture field `:84-94`, Backspace clears `:87`, per-row reset `:152`); `Hotkeys` page in `docs/user/HOTKEYS.md` | present | – | – | high | 05-editing-05 / 06-workspace-20 (Verified) |
| 27 | A command can have several hotkeys | one chord per command: `Record<string,string>` (`regiszter.ts:64,149`, `Beallitasok.svelte:91`) | missing | could | M | high | 13-palette-07 |
| 28 | Filter the list to commands that have hotkeys | name filter only (`Beallitasok.svelte:36,149`); no "has hotkey" / "customised" / "conflicting" filter, no search by chord | missing | could | S | medium | 13-palette-08 |
| 29 | Conflicting assignments | rejected before saving with the name of the other command (`regiszter.ts:129-148`, message `:145`), working layout untouched (`beallitasok.svelte.test.ts:168-169`); registration conflicts throw at startup (`regiszter.ts:88`) | ahead (safer: no silent double binding). Missing: a one-click "replace" | could | S | medium | 13-palette-08 |
| 30 | System shortcuts (copy, paste, …) are separate and cannot be reassigned | settings validation reserves only `Mod+,` and `Mod+Shift+o` (`regiszter.ts:137,144`; test `beallitasok.svelte.test.ts:175`); the native menu also owns ⌘Z ⇧⌘Z ⌘X ⌘C ⌘V ⌘A ⌘H ⌥⌘H ⌘M ⌘Q ⌃⌘F (`AppController.swift:557-605`) | partial | should | S | medium (not exercised in a running app) | 13-palette-02 |
| 31 | Reset to default | per-command reset only (`Beallitasok.svelte:152`); no "reset all" | partial | could | S | medium | 13-palette-08 |
| 32 | Hotkeys follow the physical key, shown as on a US layout | letters follow the key label, digits follow the code (`billentyuk.ts:3-5,71-88`); a deliberate Hungarian-layout rule | n.a. (design decision) | – | – | high | – |
| 33 | Multi-step key sequences (chords) | not an Obsidian core feature (the hotkeys page does not describe them); Manifold has none (`kezelo.ts:7-23` matches one chord per event) | n.a. | – | – | medium | – |
| 34 | Editing shortcuts (undo, indent, line operations) are commands and can be rebound | formatting commands are registry commands and rebindable; CodeMirror-owned chords (`szerkesztoNyer`, `regiszter.ts:38-40`; keymaps listed in `billentyu-utkozes.test.ts:31-50`) are fixed | partial | could | M | medium | 13-palette-12 |
| 35 | Hotkeys keep working while a modal is open only where meant | `kezelo.ts:15` (`atfedesben`), `parancsok.test.ts:154` | ahead | – | – | high | – |
| 36 | Hotkeys of an existing Obsidian vault carry over when switching | the importer reads `.obsidian/hotkeys.json` and lists it as "not supported" (`core/importalas.py:650-651`) | missing | should | M | high | 13-palette-01 |
| 37 | Default key table is documented | generated `docs/user/HOTKEYS.md` (`core/doku_gyorsbillentyu.py:1-20`), guarded by a test | ahead | – | – | high | – |
| 38 | Default hotkeys do not collide with the editor | `billentyu-utkozes.test.ts:1-6` (registry vs CodeMirror keymaps, explicit exception list) | ahead | – | – | high | – |

### 1.4 Page preview, word count, status bar, format converter

| # | Obsidian behaviour | Manifold today (path:line) | Status | Weight | Size | Confidence | Gap |
|---|---|---|---|---|---|---|---|
| 39 | Hover an internal link to preview it (⌘ held in the editor); works in explorer, search, backlinks | `elonezet.ts:3,137-154` (⌘/Ctrl, ~300 ms, Esc, leave); attached in editor/Reading, `Fa.svelte:70`, `KeresoTartalom.svelte:55`, backlink/outgoing/mention panes, canvas; `elonezet.test.ts:41-84` | present | – | – | high | 02-links-09 (Verified) |
| 40 | Setting to turn preview off or to require ⌘ everywhere | no setting; ⌘/Ctrl is required in every location (`elonezet.ts:46-47`); Obsidian's default outside the editor is hover without a key (memory) | missing | could | S | medium | 13-palette-11 |
| 41 | Word and character count of the active note | `Allapotsor.svelte:27,105-110` (`tp('{n} szó')`, `tp('{n} karakter')`); `f11-workspace.svelte.test.ts:190-209` | present | – | – | high | 06-workspace-16 (Verified) |
| 42 | Counts are CJK-aware | `Intl.Segmenter` word segmentation, grapheme characters (`f11-workspace.svelte.test.ts:190-192`) | ahead | – | – | high | – |
| 43 | Selection count | `Allapotsor.svelte:106-109` ("Selection:" prefix, whole-note total in the tooltip) | present | – | – | medium | – |
| 44 | Status bar also shows backlinks count (and the editor mode) | backlinks `Allapotsor.svelte:36-48`; mode toggle lives in the editor header (06-workspace audit) | present | – | – | medium | 06-workspace-17 (Verified) |
| 45 | Format converter: one command migrates `alias`→`aliases`, `tag`→`tags`, `cssclass`→`cssclasses` across the vault | no migration command. The index already **reads** singular `alias`/`tag` (`core/index/elemzo.py:42-43,172-178,359`), so nothing breaks; `cssclass` is unused anywhere in the repo | partial | could | M | high | 13-palette-10 |

### 1.5 File recovery / version history

| # | Obsidian behaviour | Manifold today (path:line) | Status | Weight | Size | Confidence | Gap |
|---|---|---|---|---|---|---|---|
| 46 | Periodic snapshots of every edited note (default ≥5 min apart) | snapshots at defined save points (first save, closing save, explicit "Snapshot of the note" command, machine and rename rounds) in the vault's git store (`core/elozmeny.py:1-14`; `szerkeszto/index.ts:194-199`); no interval setting | present (different model, no data loss) | – | – | high | – |
| 47 | Retention (default 7 days) and a Clear-history action | nothing is deleted; history is permanent and the Clear action is intentionally absent (CLAUDE.md data-safety rules) | ahead (by policy) | – | – | high | – |
| 48 | Browse snapshots of a note | right-panel **History** (`JobbPanel.svelte:204-205`, `Elozmenyek.svelte:138-156`), palette command (`alapParancsok.ts:124-135`), kind label per snapshot (`core/elozmeny.py:23-43`); core tests `tests/test_elozmeny.py:31-66` | present | – | – | high | – |
| 49 | Diff ("Show changes") between versions | `ElozmenyDiff.svelte:102-104` (against previous / against current, merge view) | present | – | – | high | – |
| 50 | Restore replaces the file | revert-commit restore with a confirmation (`ElozmenyDiff.svelte:118-131`), the current text saved first (`Elozmenyek.svelte:94`), "Undo" on the notification (`:107`); `tests/test_elozmeny.py:106-122` | ahead | – | – | high | – |
| 51 | Copy a snapshot's text without restoring | no copy button; text selectable in the diff only | missing | could | S | high | 13-palette-09 |
| 52 | Snapshots of renamed notes stay reachable | follows renames (`snapshot.py:709-716`, `--follow`); old-name versions restorable (`tests/test_elozmeny.py:49,163`) | ahead | – | – | high | – |
| 53 | Recover a deleted note by typing its name | history is unavailable for a path missing from disk and from `HEAD` (`core/elozmeny.py:60-66` → 404); the only recovery path is the macOS Trash | missing | should | M | medium | 13-palette-04 |
| 54 | Reach older snapshots | UI loads 50 (`elozmeny.ts:39`, `Elozmenyek.svelte:38`); the core caps every call at 200 (`core/elozmeny.py:20,71,91,108`); no paging | partial | should | S–M | high | 13-palette-05 |
| 55 | Works for `.md` and `.canvas` | UI gates on `.md` only (`Elozmenyek.svelte:27,141`, `alapParancsok.ts:128`); the core log and restore are path-generic; the canvas has only an in-session undo stack (`canvas/elozmeny.ts:1-4`) | partial | should | S | medium (core with JSON text not exercised in a test) | 13-palette-06 |
| 56 | Restore is blocked while the note has a conflict or unsaved state | `Elozmenyek.svelte:85-98` (conflict / vanished / read-only block with an explanation; unsaved text saved first) | ahead | – | – | high | – |
| 57 | Frontend regression test for the history panel | none: no `Elozmenyek`/`ElozmenyDiff` component test under `app/tests` (core is covered by `tests/test_elozmeny.py`) | partial | – | – | high | covered inside 13-palette-05/06 as acceptance tests |

---

## 2. Gaps and proposals

Every proposal stays in the existing layers: the UI never touches the filesystem, vault writes go through the core, and machine writes use `core/gepi_iras.py`.

### 13-palette-01 — Import Obsidian hotkeys (should, M, confidence high)
**Obsidian.** *Settings → Hotkeys* stores assignments in `.obsidian/hotkeys.json`, keyed by Obsidian command ids (for example `editor:toggle-bold`).
**Manifold.** The Obsidian importer reads the file and reports it as "not supported" (`core/importalas.py:650-651`), so a user who customised their keys starts over.
**Proposal.** Add a small, reviewed table `obsidian command id → Manifold id` (about 40 core commands: bold, italic, link, task toggle, open switcher/palette/search, new tab, close tab, back/forward, toggle left/right panel, open settings, reveal file …) in `core/importalas.py`. Convert each chord (`Mod`/`Ctrl`/`Shift`/`Alt` + key) to the canonical `Mod+Shift+x` form the registry uses (`billentyuk.ts:61-68`), write the result through the existing settings key `billentyuk` and show it in the import preview: applied, skipped because the Manifold command does not exist, skipped because the chord is reserved or collides (reuse `billentyuketEllenoriz`, `regiszter.ts:129-148`, on the whole layout so one bad entry never blocks the rest). Keep the unmapped ids in `nem_atvett` with a reason. Obsidian's `Mod` means ⌘ on macOS, so no translation is needed. Acceptance: a test with a synthetic `hotkeys.json` covering mapped, unknown, conflicting and reserved entries; the import is still one undoable run.

### 13-palette-02 — Reserved-chord validation matches the native menu (should, S, confidence medium)
**Obsidian.** System shortcuts such as copy are separate from the hotkey list and cannot be reassigned.
**Manifold.** The settings validator refuses only `Mod+,` and `Mod+Shift+o` (`regiszter.ts:137,144`). The Swift menu also binds ⌘Z, ⇧⌘Z, ⌘X, ⌘C, ⌘V, ⌘A, ⌘H, ⌥⌘H, ⌘M, ⌘Q and ⌃⌘F (`AppController.swift:557-605`). A command assigned to one of those is accepted, saved and then probably never fires, because macOS handles menu key equivalents before the web view sees the key. The NAPLO sentence "reserved native actions are validated" is true for only two of them.
**Proposal.** Move the reserved set into one exported constant (`RESERVED_CHORDS` in `billentyuk.ts`) with the reason per chord, use it in `billentyuketEllenoriz`, and add a test that extracts the `keyEquivalent`/modifier pairs from `AppController.swift` (same technique as `billentyu-utkozes.test.ts` and `core/doku_gyorsbillentyu.py`) and fails if the Swift menu gains a chord missing from the constant. Show the existing "reserved" message. Verify first in the running app whether ⌘C remapped to a command is really dead (the confidence is medium because it was read, not run).

### 13-palette-03 — Switcher `Note#Heading` / `Note^block` syntax (should, M, confidence low)
**Obsidian.** The help page for the core switcher does not describe heading or block search. My memory of heading/block suggestions is for the link suggester (`[[Note#`), and heading search in the switcher is known to me mainly from the Quick Switcher++ community plugin. Treat the exact Obsidian behaviour as unconfirmed.
**Manifold.** A `#` in the query makes the name invalid (`ujJegyzetCel` returns `null`, `f11-workspace.svelte.test.ts:188`; the footer shows the "valid note name" error, `Valto.svelte:123`). There is no way to jump to a heading from the keyboard-first switcher, although `[[##` already searches headings vault-wide (`kiegeszites.ts:91`, `core/index/api.py:32`) and `[[Note#^` lists blocks of another note (`kiegeszites.ts:332-350`).
**Proposal.** In `Valto.svelte` parse the query before searching: `Note#text` → fuzzy-match `Note`, then list that note's headings (from `/api/vault/jegyzet`, or `fejezetekMind` filtered by note); `Note^text` → block list built with the existing `masikAllapot`/`blokkok` parser; a leading `#text` → vault-wide headings via `linkek.fejezetekMind`. Selecting a row opens the note and jumps with `szerkesztok.ugras` (`navigacio.ts:108-112`); ⌘↵/⌥⌘↵ keep working. Show a footer hint (`#` headings, `^` blocks). Because the creation name cannot contain `#`, the existing validation is untouched. Before building, check the real Obsidian behaviour on a test install (the owner does measurements); if core Obsidian lacks it, downgrade to could.

### 13-palette-04 — History for deleted and renamed-away notes (should, M, confidence medium)
**Obsidian.** File recovery lets you type a file name, including one that no longer exists, and restore a snapshot as a new note.
**Manifold.** `Elozmeny._el` returns 404 when the path is absent from disk and from `HEAD` (`core/elozmeny.py:60-66`), and the panel is always bound to an open note. A deleted note is recoverable only from the macOS Trash. The git store still contains every version.
**Proposal.** Core: `GET /api/vault/elozmeny/torolt?q=` lists paths whose last commit is a delete (`git log --diff-filter=D --name-only`), newest first, bounded and fuzzy-filterable; `POST /api/vault/elozmeny/visszahoz {ut, sha}` writes the last pre-delete content as a new file through the existing create path (collision-safe name, same snapshot trailer family as `Mos-Visszaallit`). UI: a palette command "Recover deleted note…" opening a switcher-style list (reuse `ListaValaszto`), then the existing diff dialog in read-only mode with a "Restore as new note" button. The restore stays a normal, undoable snapshot. Acceptance: core test (delete → list → restore → content byte-identical); UI test for the list and the empty state.

### 13-palette-05 — History depth beyond 50 / 200 versions (should, S–M, confidence high)
**Manifold.** The panel requests 50 entries and offers no "load more" (`elozmeny.ts:39`, `Elozmenyek.svelte:38`). Independently, the core scans at most 200 log entries in `naplo`, `valtozat` and `visszaallit` (`core/elozmeny.py:20,71,91,108`), so a version older than the 200th cannot be diffed or restored even through the API. A frequently edited note can exceed that within weeks.
**Proposal.** Core: cursor paging (`before=<sha>`) for `naplo`, and look the requested `sha` up with `git log --follow` bounded by that sha rather than by the head window, so `valtozat`/`visszaallit` work for any reachable version (keep a hard per-call page size). UI: "Show older versions" at the end of the list, keeping scroll position. Add component tests for `Elozmenyek.svelte`/`ElozmenyDiff.svelte` (list, paging, restore confirmation, blocked states) — today only the core is tested (row 57).

### 13-palette-06 — History for `.canvas`, `.base` and other text notes (should, S, confidence medium)
**Obsidian.** File recovery covers `.md` and `.canvas`.
**Manifold.** The panel and the command are limited to `.md` (`Elozmenyek.svelte:27,141`, `alapParancsok.ts:128`), although the log, the diff source and the revert are path-generic (`core/elozmeny.py`, `core/snapshot.py:709-747`) and canvas/base files are written through the snapshotting vault writer (`core/vaultio.py:3,40-50`). A broken canvas edit has only the in-session undo stack (`canvas/elozmeny.ts`).
**Proposal.** Replace the `.md` test by "writable text type" (`IRHATO`: `.md`, `.base`, `.canvas`), show the JSON text in the diff (the 8 MiB limit and the `szoveg_ok` fallbacks already exist, `core/elozmeny.py:86-102`), and verify with a core test that a `.canvas` revision round-trips byte-exact. After restore the open canvas/base view must reload from disk (`dok.kulsoValtozas()` equivalent for those views); that reload is the real work and the reason this is S only if the views already handle external change.

### 13-palette-07 — Several hotkeys per command (could, M, confidence high)
**Obsidian.** A command can carry more than one hotkey.
**Manifold.** The registry maps one chord per command (`regiszter.ts:62-64`) and the settings store is `Record<string,string>`. **Proposal.** Store `string[]` with a migration that wraps the old string; `akkordok` already maps chord → id, so lookups need no change; the settings row gets a "+" and per-chord "×"; the palette shows the first chord. Low demand, so keep it could.

### 13-palette-08 — Hotkey list ergonomics and conflict replacement (could, S, confidence medium)
**Manifold.** Name filter only (`Beallitasok.svelte:36`); no filter for "has a hotkey", "customised" or "conflicts"; no search by pressing the chord; no "reset all"; a conflict is a hard error naming the other command (`regiszter.ts:145`). **Proposal.** Three toggle chips above the list, a "Reset all" button (with confirmation, draft only until Save), and on conflict an inline "Replace" action that unbinds the other command in the same draft. Everything stays in the draft that Save already validates as a whole.

### 13-palette-09 — Copy a snapshot's text (could, S, confidence high)
**Obsidian.** *Copy* puts the snapshot text on the clipboard without touching the note. **Manifold.** The diff dialog offers only restore and close (`ElozmenyDiff.svelte:118-131`). **Proposal.** A "Copy this version" button in the footer using the existing clipboard helper (`szerkeszto/vagolap.ts`) with a short confirmation; it is the safe way to take one paragraph from an old version.

### 13-palette-10 — Frontmatter key migration (Format converter) (could, M, confidence high)
**Obsidian.** The Format converter rewrites deprecated `alias`, `tag` (comma-separated string) and `cssclass` keys into `aliases`, `tags`, `cssclasses` across the whole vault.
**Manifold.** The indexer already accepts both spellings (`core/index/elemzo.py:42-43,172-178,359`), so reading is unaffected; but the notes keep the old keys, the property editor shows them as separate keys, and exporting to other tools sees mixed forms. `cssclass` has no meaning in Manifold.
**Proposal.** A palette command "Normalise legacy frontmatter keys…" that first shows a dry-run list (note, old key, new key) and then applies it through the machine-write service in one snapshot round, so a single undo reverts it. Convert `alias`/`tag` only; leave `cssclass` untouched. Not needed for daily use, hence could.

### 13-palette-11 — Page-preview settings (could, S, confidence medium)
**Obsidian.** The plugin can be switched off, and the ⌘-to-hover requirement can be enforced for all locations (by default, outside the editor, hovering is enough). **Manifold.** ⌘/Ctrl is required everywhere (`elonezet.ts:46-47`) and there is no switch. **Proposal.** Two settings, "Link preview" (on/off) and "Require ⌘ in side panes" (default on, preserving today's behaviour), read by `elonezetKapcsol`/`elonezetUtakra`. Low risk, low value.

### 13-palette-12 — Rebinding editor-owned shortcuts (could, M, confidence medium)
**Obsidian.** Undo, indent and line operations are ordinary commands in the hotkey list. **Manifold.** CodeMirror keymaps (history, default, fold, search, completion, `indentWithTab`) are fixed, and `szerkesztoNyer` commands defer to them (`regiszter.ts:38-40`, `kezelo.ts:17`). **Proposal.** Wrap the handful that users actually remap (undo/redo, move line, duplicate line, indent/outdent) as registry commands calling the CM command functions, and drop them from the fixed keymap; the collision test (`billentyu-utkozes.test.ts`) already knows how to enumerate both sides. Relevant only to people who remap editing keys, hence could (see the note in 06-workspace-20).

---

## 3. Manifold strengths beyond Obsidian (keep)

1. **One command registry** behind palette, hotkeys, buttons, the new-tab page and the macOS menu; ids are stable, names are localised at display time (`regiszter.ts:1-52`, `Paletta.svelte:28`).
2. **Matcher quality.** Accent-insensitive, Damerau–Levenshtein typo tolerance, word-start subsequence, a near-linear cost test (`fuzzy.ts:1-8`, `fuzzy.test.ts:22-105`), shared by palette and switcher.
3. **Safe command execution.** Sync and async failures surface as a named notification (`regiszter.ts:176-185`); focus returns to the invoking editor before a command that needs it (`Paletta.svelte:59-70`); modal-aware hotkeys via `atfedesben` (`kezelo.ts:15`).
4. **Hotkey validation as a whole layout.** Malformed, conflicting or reserved layouts are rejected before they replace the working map (`regiszter.ts:129-159`; `beallitasok.svelte.test.ts:150-176`), and the default table is generated and test-guarded (`core/doku_gyorsbillentyu.py`, `billentyu-utkozes.test.ts`).
5. **Switcher.** Alias rows, create-from-query with a validated explicit folder, ⌘↵ and ⌥⌘↵, ⌃N/⌃P, type icons, alias API failure that never blocks name search (`Valto.svelte`, `f11-workspace.svelte.test.ts:123-188`).
6. **Version history is revert-based and undoable.** The current text is saved first, restore is a new commit with a one-click undo notification, conflict/vanished/read-only states block with an explanation, renames are followed, CRLF is preserved byte for byte (`Elozmenyek.svelte:82-135`, `core/elozmeny.py:1-14,104-133`, `tests/test_elozmeny.py`). There is no Clear-history action by design.
7. **Word count** is Unicode-aware (graphemes, `Intl.Segmenter`), handles overlapping multi-selections once, and stays out of the way in quiet mode (`f11-workspace.svelte.test.ts:190-209`).
8. **Hover preview** is available in the editor, Reading view, explorer, search, link panes and canvas (`elonezet.ts`, `Fa.svelte:70`, `KeresoTartalom.svelte:55`).

---

## 4. Open questions

1. **Switcher `#`/`^` (13-palette-03):** does core Obsidian's switcher support heading/block search, or is that Quick Switcher++ only? Needs a check on a real install before any implementation; the help page is silent.
2. **Native key equivalents (13-palette-02):** confirm in the running app that a registry command bound to ⌘C/⌘V/⌘Z is dead, and whether the intended UX is "reject at assignment" (proposed) or "allow and warn".
3. **Deleted-note recovery (13-palette-04):** is the Trash-only path acceptable for the product, given that a vault restored from backup would already contain the history? If yes, downgrade to could.
4. **History size policy:** history is permanent and unbounded. Should Settings show the snapshot-store size (the Rendszer panel is the natural place) even though Clear/retention are intentionally absent?
5. **Recent-command ranking while typing:** Obsidian ranks shorter names above recent commands; Manifold gives a recency bonus (`Paletta.svelte:47-51`). Keep Manifold's rule?
6. **Pinned commands:** 06-workspace-19 rates them nice. With recents already first, is that still right, or should pins join the F11 checklist as should?
7. **Chord sequences:** deliberately out of scope (Obsidian has none); revisit only if the hotkey layout runs out of free ⌘-combinations on a Hungarian keyboard.
