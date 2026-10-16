# 04 – Embeds and transclusion — Obsidian-parity audit

Scope: the Manifold subsystem "Embeds and transclusion" (`![[…]]`, media embeds, attachments) compared with Obsidian 1.8/1.9 desktop, core features and core plugins only. READ-ONLY audit of `/Volumes/Work/[UNI] Manifold-OS`; every claim cites `path:line` relative to that root. Reference docs used: `docs/dev/ARCHITECTURE.md:200-206,248-255`, `docs/dev/DESIGN.md:194-199,283`, `docs/plan/audit/03-felulet.md`.

Files read: `app/src/szerkeszto/beagyazas/{rajzol,widget,regiszter,nagyito}.ts`, `app/src/szerkeszto/elo/blokkok.ts`, `app/src/szerkeszto/olvaso/html.ts`, `app/src/szerkeszto/Olvaso.svelte`, `app/src/szerkeszto/linkek/{adat,navigacio,elonezet,szerkeszto,kiegeszites}.ts`, `app/src/szerkeszto/csatolmany.ts`, `app/src/szerkeszto/helyiMenu.ts`, `app/src/szerkeszto/szerkeszto.css`, `app/src/media/{index,beszuras,aktiv.svelte,atirat}.ts`, `app/src/media/Lejatszo.svelte`, `app/src/media/media.css`, `app/src/media/pdf/beagyazas.ts`, `app/src/canvas/beagyazas.ts`, `app/src/bazis/beagyazas.ts`, `app/src/kod/beagyazas.ts`, `app/src/hej/Fa.svelte`, `app/src/lib/vault/linkek.svelte.ts`, `app/src/lib/core/hej.ts`, `app/index.html`, `core/media.py`, `core/kepek.py`, `core/mediatipus.py`, `core/csatolmany.py`, `core/vaultio.py`, `core/index/olvaso.py`, `core/index/linkek.py`.

Confidence marks the Obsidian side: **high** = documented/daily-use behaviour I am sure of; **medium** = behaviour I remember but could not verify; **low** = uncertain, verify before acting.

---

## 0. Executive summary

Manifold's embed engine is architecturally sound and in several places ahead of Obsidian: one renderer serves Live Preview, Reader, hover preview and canvas cards (`app/src/szerkeszto/beagyazas/rajzol.ts:1-7`); resolution and slicing live only in the core (`core/index/olvaso.py:450-488`, L42); images are served as DPR-aware downscaled variants with an original-size lightbox (`core/kepek.py:1-24`, `app/src/szerkeszto/beagyazas/nagyito.ts:1-5`); videos get an ffmpeg poster (`core/kepek.py:254-337`); PDFs embed as a lazy, virtualised, page-navigable viewer (`app/src/media/pdf/beagyazas.ts:1-6`); note-class embeds can be interactive (quiz, card deck, summary — `app/src/szerkeszto/beagyazas/regiszter.ts:37-45`).

The gaps that Obsidian users will hit on day one are few but concrete:

1. **Markdown image syntax `![alt](path)` is not rendered at all** — Reader shows a `[kép: …]` placeholder (`app/src/szerkeszto/olvaso/html.ts:243-248`), Live Preview has no `Image` decoration (`app/src/szerkeszto/elo/blokkok.ts:52-146`). Same for **external `![](https://…)` images**, which the app CSP additionally forbids (`app/index.html:9`).
2. **PDF `#height=N`** (Obsidian's documented syntax) is not parsed (`app/src/szerkeszto/linkek/adat.ts:59-69`); Manifold uses `|N` instead (`docs/dev/DESIGN.md:196`).
3. In Live Preview the **embed widget disappears while the cursor is on its line** (`app/src/szerkeszto/elo/blokkok.ts:133`); Obsidian keeps the rendered embed and reveals the markup above it.
4. `|300x200` **height is silently discarded** by CSS (`app/src/szerkeszto/szerkeszto.css:803-809` vs `app/src/szerkeszto/beagyazas/rajzol.ts:209-210`).
5. **Checkboxes inside an embedded note do not write to the embedded file**; in the Reader they are even wired to the host document's offsets (`app/src/szerkeszto/Olvaso.svelte:93-110`).
6. Embeds **do not refresh when the embedded note's content changes** (`app/src/lib/vault/linkek.svelte.ts:60-65`, `app/src/szerkeszto/beagyazas/widget.ts:30-39`).
7. Attachment insertion ignores `useMarkdownLinks` / `newLinkFormat` and names pasted images after the clipboard file (`image.png`) instead of `Pasted image YYYYMMDDHHMMSS.png` (`app/src/szerkeszto/csatolmany.ts:62-68,77-80`).

Everything else in the focus checklist is present, often with extra polish that must be preserved (section 3).

### Focus checklist at a glance

| Focus item | Status | Where | Gap id |
|---|---|---|---|
| `![[note]]` | **present** | `app/src/szerkeszto/beagyazas/rajzol.ts:127-171`, `core/index/olvaso.py:450-488` | — |
| `![[note#heading]]` (incl. nested `A#B`) | **present** | `core/index/linkek.py:52-73`, `core/index/olvaso.py:480-483` | — |
| `![[note#^block]]` (list item with children) | **present** | `core/index/linkek.py:76-99`, `core/index/olvaso.py:475-479` | — |
| Image embeds with size | **partial** — width OK, `WxH` height dropped; markdown `![alt\|300](src)` missing | `rajzol.ts:203-234`, `szerkeszto.css:803-809`, `olvaso/html.ts:243-248` | 04-embeds-01, -05 |
| Audio/video embeds | **present** (+ `#t=`, poster, width) | `rajzol.ts:239-268`, `core/kepek.py:277-337` | — |
| PDF embeds `#page=` / `#height=` | **partial** — `#page=` yes, `#height=` no (`\|N` instead) | `app/src/media/pdf/beagyazas.ts:113-114,147`, `linkek/adat.ts:59-69` | 04-embeds-03 |
| Nested embed depth limit | **present** (6) + circular detection | `rajzol.ts:20,29-34,79-83` | — |
| Embed editing in place | **partial** — click → cursor to source yes; widget vanishes on active line; no inline editing of embedded note (Obsidian core has none either) | `widget.ts:53-67`, `elo/blokkok.ts:133` | 04-embeds-04 |
| External URLs | **missing** (`![](https://…)` not rendered; CSP blocks remote `img-src`) | `olvaso/html.ts:243-248`, `app/index.html:9` | 04-embeds-02 |
| Attachment paste/drag (`attachmentFolderPath`) | **present**; naming and link-format settings missing | `csatolmany.ts:74-102`, `core/csatolmany.py:109-137,158-239` | 04-embeds-08, -09, -13 |
| Image resize syntax | **partial** (`\|300` yes, `\|300x200` height bug, markdown form missing) | as above | 04-embeds-01, -05 |
| Embed title bar and open link | **present** (visible header link; ⌘ new tab, ⌘⌥ split) | `rajzol.ts:137-152`, `pdf/beagyazas.ts:123-144` | — |

---

## 1. Checklist table

Legend — Status: present / partial / missing / n/a. Severity: must / should / nice. Effort: S (<1 day) / M (1–3 days) / L (>3 days). "Conf." = confidence about the Obsidian behaviour.

### 1.1 Note transclusion

| # | Obsidian behaviour | Manifold today (path:line) | Status | Sev. | Eff. | Conf. |
|---|---|---|---|---|---|---|
| 1 | `![[note]]` renders the whole note (frontmatter/properties hidden) in an embed box; the embedded note's links resolve relative to the embedded file. | Core slices the text without frontmatter (`core/index/olvaso.py:468-472`); the UI renders it with the Reader renderer and `ut: adat.ut` so links carry `data-forras` of the embedded note (`app/src/szerkeszto/beagyazas/rajzol.ts:153-164`, `app/src/szerkeszto/olvaso/html.ts:265-277`). | present | — | — | high |
| 2 | `![[note#Heading]]` embeds the heading line plus its section up to the next heading of the same or higher level; `![[note#A#B]]` nests; matching is case-insensitive and ignores some punctuation/markup. | `fejezet_tartomany` starts at the heading line, ends before the next ≤-level heading, walks `A#B` (`core/index/linkek.py:52-73`); normalisation in `alcel_norm` (`core/index/linkek.py:45-49`); hooked at `core/index/olvaso.py:480-483`. | present | — | — | high |
| 3 | `![[note#^id]]` embeds the block; a list item is embedded with its children; the `^id` is hidden in the render. | `blokk_tartomany` returns start→id line, extends over deeper-indented children (`core/index/linkek.py:76-99`); the Reader strips the trailing `^id` (`app/src/szerkeszto/olvaso/html.ts:336-338`). | present | — | — | high |
| 4 | Missing heading/block → "Unable to find section …" message in the embed. | `alcel_hiba` from the core (`core/index/olvaso.py:484-485`), rendered as "Nem található: file#alcel" (`rajzol.ts:130-136`). | present | — | — | high |
| 5 | Unresolved `![[missing]]` → empty embed showing the name; clicking it creates the note. | "Nem található" + a **Létrehozás** button (not for media extensions); the location is decided by the core (`rajzol.ts:101-123`, `app/src/szerkeszto/linkek/navigacio.ts:45-67`, `POST /api/vault/uj`). | present | — | — | medium |
| 6 | Embed box has a (theme-hidden) title bar and an "Open link" icon on hover; ⌘-click opens in new tab. | Visible header `name › anchor` acting as a link (`rajzol.ts:137-152`), `nyitasMod` gives ⌘ → new tab, ⌘⌥ → split (`navigacio.ts:31-35`); PDF embed has an explicit "Megnyitás" button opening at the current page (`app/src/media/pdf/beagyazas.ts:120-121,144`). | present | — | — | medium |
| 7 | Circular embed: Obsidian stops rendering (exact message/limit unknown). | Explicit "Körkörös beágyazás: A → B → A" message with path, `MAX_MELYSEG = 6` (`rajzol.ts:20,29-34,79-83`). | present | — | — | low |
| 8 | Embeds nested in lists, callouts, blockquotes render. | Live Preview iterates into `ListItem`/`Blockquote`/`Paragraph`/`Task` (`app/src/szerkeszto/elo/blokkok.ts:26,54-65,139-141`); Reader renders inline `Embed` nodes anywhere (`olvaso/html.ts:279-295`). Embeds inside **table cells** are not decorated in Live Preview because `Table` returns `false` (`blokkok.ts:66-80`). | partial | nice | S | medium |
| 9 | An embed in the middle of a line still renders the note content inline. | Mid-line note embed becomes a link **chip** by design (`rajzol.ts:76-77,282-299`, `widget.ts:1-2`); images/videos stay rendered. | partial | nice | S | medium |
| 10 | In Live Preview the embed stays rendered when the cursor is on its line; the `![[…]]` markup is revealed above the widget. | The replace decoration is dropped entirely while the line is active, so the widget collapses to raw text and the layout jumps (`blokkok.ts:133`). | partial | must | S | medium |
| 11 | Clicking the embed content in Live Preview puts the cursor on the embed's source line. | Mousedown anywhere outside own controls moves the selection to the widget start (`widget.ts:53-67`). | present | — | — | high |
| 12 | Editing the embedded note's text inline — not in Obsidian core. | Not in Manifold either (`app/src/kod/beagyazas.ts:1-4` notes the editable embed is out of scope); note-class embeds (quiz, card deck) are interactive instead (`regiszter.ts:37-45`). | n/a | — | — | medium |
| 13 | Task checkboxes inside an embedded note are clickable and write to the embedded file. | Reader: `feladat()` always emits `data-jelolo` with an offset **in the embedded text** (`olvaso/html.ts:444-455`); `Olvaso.svelte` applies it to the **host** document after a shape check (`app/src/szerkeszto/Olvaso.svelte:93-110,131-139`) — a wrong-target write is possible when offsets coincide. Live Preview: the widget ignores events for `input` (`widget.ts:16,62,79-81`), so the box toggles visually only. | missing | should | M | medium |
| 14 | The embed re-renders when the embedded note changes (another pane, sync, external edit). | `linkek.verzio` only bumps on structural changes (new/deleted/mass) (`app/src/lib/vault/linkek.svelte.ts:60-65`); `BeagyazasWidget.eq` keys on that version (`widget.ts:30-39`); the editor dispatches `linkVerzioValt` only then (`app/src/szerkeszto/Szerkeszto.svelte:263-267`); the Reader re-renders only on its own document (`Olvaso.svelte:118-123`). Content edits of the target do not refresh the embed. | missing | should | M | high |
| 15 | Hover preview (Page preview core plugin) for links/embeds with ⌘. | `elonezet.ts` reuses the embed renderer in `kompakt` mode (`app/src/szerkeszto/linkek/elonezet.ts:1-5,53-88`). | present | — | — | high |
| 16 | `![[note\|alias]]` alias is ignored for note embeds. | Alias ignored for notes (only `meretAliasbol` on media) (`rajzol.ts:205-206`). | present | — | — | medium |

### 1.2 Images

| # | Obsidian behaviour | Manifold today (path:line) | Status | Sev. | Eff. | Conf. |
|---|---|---|---|---|---|---|
| 17 | `![[img.png]]` renders; `![[img.png\|alt text]]` sets alt. | `<img>` with alt from alias (`rajzol.ts:203-206`); served via tokenised `/media/<token>/<path>` (`app/src/lib/vault/linkek.svelte.ts:89-94`, `core/media.py:22-58`). | present | — | — | high |
| 18 | `![[img.png\|300]]` sets width; `![[img.png\|300x200]]` sets width **and** height. | `meretAliasbol` parses both (`app/src/szerkeszto/linkek/adat.ts:51-56`); `img.width`/`img.height` attributes set (`rajzol.ts:209-210`) but `.beagyazas-kep { height: auto }` overrides the height attribute (`app/src/szerkeszto/szerkeszto.css:803-809`). | partial | should | S | high |
| 19 | Markdown image syntax `![alt](local/path.png)` and `![alt\|300](local/path.png)` render (path URL-decoded, resolved like a link). | Reader emits a `[kép: alt]` placeholder (`olvaso/html.ts:243-248`, styled `szerkeszto.css:720-724`); Live Preview has no `Image` case (`elo/blokkok.ts:52-146`); the link layer explicitly skips `Image` (`app/src/szerkeszto/linkek/szerkeszto.ts:44`). | missing | must | M | high |
| 20 | `![](https://example.com/a.png)` renders a remote image. | Same placeholder as #19; additionally the page CSP is `img-src 'self' data: blob:` (`app/index.html:8-9`), so remote images cannot load even if rendered. | missing | must | M | high |
| 21 | Clicking an image in Live Preview places the cursor; Reading view does nothing (no lightbox in core). | Click/Enter/Space opens a lightbox with the original file (`rajzol.ts:198-201,219-231`, `nagyito.ts:20-65`); clicking outside the `<img>` moves the cursor (`widget.ts:16,62-66`). A deliberate divergence worth keeping. | partial | nice | S | high |
| 22 | Right-click on an image: context menu with "Open in default app", "Show in system explorer", copy/rename items. | Context menu has only cut/copy/paste plus registered commands (`app/src/szerkeszto/helyiMenu.ts:3-9,42`); the shell exposes only the `helyiMenu` capability (`app/src/lib/core/hej.ts:38`). | missing | nice | M | medium |
| 23 | Images lazy-load; no server-side downscaling (full bitmap decoded). | `loading=lazy`, `decoding=async`, DPR-aware `?w=` bucket (`rajzol.ts:207-218`, `nagyito.ts:10-15`, `core/kepek.py:37,76-78,108-134`). | present (stronger) | — | — | high |
| 24 | Broken image shows alt text. | Error → "A kép nem tölthető be: name" message (`rajzol.ts:212-215`). | present | — | — | high |
| 25 | SVG embeds render as images. | SVG served with `sandbox; default-src 'none'` CSP and `nosniff` (`core/media.py:101-102`). | present (safer) | — | — | high |
| 26 | HEIC/HEIF: Obsidian (Chromium) does not decode. | `.heic`/`.heif` are served (`core/mediatipus.py:21-22`) and WebKit decodes them natively; the downscaler leaves them original (`core/kepek.py:38`). | present (stronger) | — | — | medium |
| 27 | HTML `<img src>` in a note renders. | HTML blocks are shown as raw monospace text (`szerkeszto.css:743-748`). Belongs to the HTML-rendering subsystem; listed for completeness. | missing | nice | L | high |

### 1.3 Audio and video

| # | Obsidian behaviour | Manifold today (path:line) | Status | Sev. | Eff. | Conf. |
|---|---|---|---|---|---|---|
| 28 | `![[audio.mp3]]` → `<audio controls>`. | `<audio controls preload=metadata>` + optional `#t=` (`rajzol.ts:260-268`); Range/206 serving (`core/media.py:72-115`). | present | — | — | high |
| 29 | `![[video.mp4]]` → `<video controls>`; no poster. | `<video controls playsinline>` with ffmpeg poster (`?poster=1&t=`) and `#t=0.001` first-frame trick (`rajzol.ts:236-258`, `core/kepek.py:277-337`, `core/media.py:28-41`). | present (stronger) | — | — | high |
| 30 | `#t=` media fragment on embeds — unsure whether core honours it. | `#t=243`, `#t=12:40`, `#t=1:02:03` parsed (`linkek/adat.ts:58-65`), applied to src and `currentTime` (`rajzol.ts:244-254`); same anchor opens the player tab at that time (`navigacio.ts:87-93`, `app/src/media/Lejatszo.svelte:52-60,161-172`). | present | — | — | low |
| 31 | `![[video.mp4\|400]]` width — unsure in core. | Width alias applied to `<video>` (`rajzol.ts:245-246`). | present | — | — | low |
| 32 | Extension coverage: mp3/wav/m4a/ogg/3gp/flac; mp4/webm/ogv (Chromium codecs). | Allow-list in one place (`core/mediatipus.py:19-28`), includes mov/mkv/m4v/opus/aac/avif/bmp/tiff; the UI tab matcher mirrors it (`app/src/media/index.ts:16-18`). | present | — | — | high |

### 1.4 PDF

| # | Obsidian behaviour | Manifold today (path:line) | Status | Sev. | Eff. | Conf. |
|---|---|---|---|---|---|---|
| 33 | `![[doc.pdf]]` embeds the PDF viewer; `![[doc.pdf#page=3]]` opens at page 3. | pdf.js embed, `#page=` as start page (`app/src/media/pdf/beagyazas.ts:111-118,292,320`), registered as the `pdf` renderer (`app/src/media/index.ts:66`); iframe fallback without the module (`rajzol.ts:270-280`). | present | — | — | high |
| 34 | `![[doc.pdf#height=400]]` sets the embed height; combinable `#page=3&height=400`. | `mediaHorgony` parses only `page=` and `t=` (`linkek/adat.ts:58-69`); height comes from the **alias** `\|N` (`pdf/beagyazas.ts:113,147`, `rajzol.ts:273-276`, documented in `docs/dev/DESIGN.md:196,283`). `#page=3&height=400` → page 3 only, height ignored. | missing | must | S | high |
| 35 | Embedded viewer has toolbar (page navigation, zoom, search) and selectable text. | Header: page field, ‹ ›, "Megnyitás"; pages are canvases only (no text layer, no zoom/search in the embed) (`pdf/beagyazas.ts:123-144,206-232`). | partial | nice | M | low |
| 36 | PDF embed loads immediately; height default tall. | Lazy on visibility, pages virtualised, canvases released off-screen, resize-aware (`pdf/beagyazas.ts:4-6,185-204,302-331,335-341`); default 520 px (`pdf/beagyazas.ts:15`). | present (stronger) | — | — | medium |

### 1.5 Other file types

| # | Obsidian behaviour | Manifold today (path:line) | Status | Sev. | Eff. | Conf. |
|---|---|---|---|---|---|---|
| 37 | `![[board.canvas]]` renders the canvas read-only. | Static SVG thumbnail of the canvas with a header link (`app/src/canvas/beagyazas.ts:1-2,92-99`; registered `app/src/canvas/index.ts:65`). | partial | nice | M | medium |
| 38 | `![[file.base]]` / `![[file.base#View]]` renders the Bases view (1.9). | Full `BazisNezet` mounted with `nezet: link.alcel` (`app/src/bazis/beagyazas.ts:1-7,55-70`). | present | — | — | medium |
| 39 | Unsupported file (`.docx`, `.txt`, …) embeds as a file box with "open in default app". | Type `egyeb` → link chip (`rajzol.ts:175-188,282-299`); `.cpp` gets its own renderer (`app/src/kod/beagyazas.ts:1-4`). | partial | nice | S | medium |
| 40 | Renderer extension point — n/a (plugins). | `beagyazasRenderelok` by type and `jegyzetOsztalyRenderelok` by note class (`regiszter.ts:31-82`). | present (stronger) | — | — | — |

### 1.6 Attachments (paste / drop / settings)

| # | Obsidian behaviour | Manifold today (path:line) | Status | Sev. | Eff. | Conf. |
|---|---|---|---|---|---|---|
| 41 | Pasting an image from the clipboard saves it to the attachment folder and inserts `![[…]]`. | `paste` handler uploads `clipboardData.files` in 4 MiB chunks and inserts at the mapped cursor (`app/src/szerkeszto/csatolmany.ts:23-45,56-72,74-92`); the core writes it collision-safely and commits a snapshot (`core/csatolmany.py:158-239,251-272`). | present | — | — | high |
| 42 | The pasted file is named `Pasted image YYYYMMDDHHMMSS.png`. | The clipboard `File.name` is used (`csatolmany.ts:38`), typically `image.png`; collisions get ` 1`, ` 2` suffixes (`core/csatolmany.py:223-226`). | missing | should | S | high |
| 43 | Dragging files from Finder into the editor copies them to the attachment folder and inserts embeds at the drop point. | `drop` handler, `posAtCoords` insertion (`csatolmany.ts:93-101`). | present | — | — | high |
| 44 | Dragging a file from the file explorer into the editor inserts `[[…]]` / `![[…]]`. | File tree sets `application/x-manifold-vault` (files only) (`app/src/hej/Fa.svelte:273-274,413`); editor inserts the shortest unambiguous target from `GET /api/vault/linkcel` (`csatolmany.ts:60-68`). | present | — | — | high |
| 45 | `attachmentFolderPath` modes: vault root, fixed folder, same folder (`./`), subfolder (`./x`); the folder is created on demand. | All four handled in `csatolmany.mappa` (`core/csatolmany.py:109-137`); `mkdir(parents=True)` (`core/csatolmany.py:211`); the setting is read-only (`core/csatolmany.py:112`). | present | — | — | high |
| 46 | Inserted link format follows "Use [[Wikilinks]]" (`useMarkdownLinks`) and "New link format" (`newLinkFormat`: shortest/relative/absolute). | Always a wikilink of the core's shortest form (`csatolmany.ts:62-67`, `app/src/media/beszuras.ts:37,52`); the core reads only `attachmentFolderPath` and `newFileLocation` (`core/csatolmany.py:114`, `core/vaultio.py:403-406`). | missing | should | M | high |
| 47 | Which dropped/pasted files get the `!` embed prefix (images, audio, video, pdf). | A hard-coded regex `png|jpg|jpeg|gif|webp|heic|pdf|mp4|mov|mp3|wav|svg` (`csatolmany.ts:67`) that disagrees with `ISMERT_KITERJESZTES` (`navigacio.ts:22`) and `MEDIA_TIPUS` (`core/mediatipus.py:19-28`): avif/bmp/tiff/m4v/webm/mkv/m4a/flac/ogg/opus/aac are inserted as plain `[[…]]`. | partial | nice | S | high |
| 48 | "Insert attachment" command (file picker). | No such command; import happens only via paste/drop or dropping onto the file tree (`Fa.svelte:318`). | missing | nice | S | medium |
| 49 | Pasting a URL while text is selected creates `[selection](url)` (1.5+). | Implemented, with angle-bracketed URL (`csatolmany.ts:83-91`). | present | — | — | medium |
| 50 | Large files: Obsidian copies synchronously. | Chunked, resumable upload up to 20 GiB with busy-lock retry and insertion-point mapping during upload (`csatolmany.ts:19-32,47-55`, `core/csatolmany.py:18,192-205`). | present (stronger) | — | — | high |

---

## 2. Gaps and proposals

All proposals stay inside the existing architecture: resolution/slicing in the core (`core/index/olvaso.py`), one UI renderer (`app/src/szerkeszto/beagyazas/rajzol.ts`), decorations in `app/src/szerkeszto/elo/blokkok.ts`, media via `GET /media/<token>/<path>` (`core/media.py`), uploads via `POST /api/vault/import` (`core/csatolmany.py`).

### 04-embeds-01 — Markdown image syntax `![alt](path)` is not rendered (must, M, high)

**Today.** Reader: `[kép: alt]` placeholder (`app/src/szerkeszto/olvaso/html.ts:243-248`). Live Preview: no `Image` case (`app/src/szerkeszto/elo/blokkok.ts:52-146`); the Lezer parser already produces `Image` nodes (used at `app/src/szerkeszto/linkek/szerkeszto.ts:44`).

**Proposal.**
1. `app/src/szerkeszto/linkek/adat.ts`: add `kepAdat(n: SyntaxNode, olvas)` returning a `LinkAdat`-shaped object for `Image` nodes: `cel` = URL-decoded path (strip `<…>`), `alcel` from a `#…` suffix, `alias` = the alt text with Obsidian's `alt|300` / `alt|300x200` split (reuse `meretAliasbol`), `beagyazas: true`, plus `kulso: boolean` when the target has a scheme (`kulsoCim` in `linkek/kulso.ts`).
2. `app/src/szerkeszto/olvaso/html.ts:243`: for a local target call `beagyazasElem(kepAdat(...), {...})` exactly as the `Embed` case does (`html.ts:279-295`); the core resolves the decoded path through the same `GET /api/vault/beagyazas` (`core/index/olvaso.py:450-461`, which runs `feloldo.resolve`), so vault-relative and note-relative paths behave like Obsidian.
3. `app/src/szerkeszto/elo/blokkok.ts:128`: add a sibling `case 'Image'` producing `BeagyazasWidget` (block when the line is only the image, inline otherwise) — identical to the `Embed` branch.
4. `rajzol.ts:203-234` needs no change for local images; the only addition is the alt/size split from the markdown alt.
5. Tests: extend `app/tests/beagyazas.test.ts` (`media` describe, lines 122-224) with markdown-image cases.

### 04-embeds-02 — External image URLs `![](https://…)` (must, M, high)

**Today.** Not rendered (same placeholder as 01) and blocked by `img-src 'self' data: blob:` (`app/index.html:9`).

**Proposal.** Two options; decide in open question Q1.
- *(a) Direct load, Obsidian-like:* relax the meta CSP to `img-src 'self' https: data: blob:` (`app/index.html:9`); in `rajzol.ts` add a `kulsoKep` renderer (no `?w=` bucket, no lightbox token URL, `referrerpolicy="no-referrer"`), used by the `Image` case of 01 when `kulso` is set. Effort S on top of 01.
- *(b) Core proxy with privacy control:* new route `GET /media/<token>/kulso?url=` in `core/media.py` (same token check as `media()` at `core/media.py:22-27`) that fetches with a size/time cap, allow-listed schemes, and caches in `{vault_kepek}` next to the downscaled images (`core/kepek.py:108-134` pattern, `.forras` sidecar so `takarit` reclaims it). CSP stays unchanged. Effort M.

Either way `widget.ts` `SAJAT_VEZERLO` (`widget.ts:16`) already treats `img.beagyazas-kep` as its own control; keep that class on the remote `<img>`.

### 04-embeds-03 — PDF `#height=N` and `#page=N&height=N` (must, S, high)

**Today.** `mediaHorgony` parses `t=` and `page=` only (`app/src/szerkeszto/linkek/adat.ts:58-69`); height is taken from the alias `|N` (`app/src/media/pdf/beagyazas.ts:113,147`; iframe fallback `rajzol.ts:273-276`).

**Proposal.** Extend `mediaHorgony` to return `{ t?, page?, height? }` and to accept `&`-separated pairs (`page=3&height=400`, also `height=400&page=3`). In `pdf/beagyazas.ts:147` use `horgony.height ?? meret?.szelesseg ?? default`; same in `rajzol.ts:276`. Keep `|N` as a Manifold extension (DESIGN.md:196 documents it) so nothing is lost. Add vectors to `app/tests/pdf-beagyazas-doboz.test.ts`. The core is unaffected (`core/index/olvaso.py:452-453` passes `alcel` through verbatim).

### 04-embeds-04 — Embed widget disappears while the cursor is on its line (must, S, medium)

**Today.** `if (aktiv(...)) return false;` drops the decoration (`app/src/szerkeszto/elo/blokkok.ts:133`), so a 500 px image collapses to one line of text and the view jumps while editing around it.

**Proposal.** When the line is active, keep the markup visible and append the rendered embed below it with `Decoration.widget({ widget: new BeagyazasWidget(adat, forras, linkek.verzio, true), block: true, side: 1 }).range(sor.to)` — the same pattern the math block uses for its live preview (`blokkok.ts:84-87`, `KepletElonezetWidget`). For inline embeds keep the current reveal. `BeagyazasWidget.eq` (`widget.ts:30-39`) already keys on target/anchor/alias, so the DOM is reused between the replace and the side widget if the constructor gets the same data; otherwise add an `aktiv` flag to `eq`.

### 04-embeds-05 — `|300x200` height is discarded (should, S, high)

**Today.** `img.height` is set (`rajzol.ts:210`) but `.beagyazas-kep { height: auto }` wins (`szerkeszto.css:803-809`).

**Proposal.** Either set `img.style.height = \`${meret.magassag}px\`` (and `object-fit: cover` or leave Obsidian's distortion — Obsidian sets both attributes and lets the browser stretch), or change the CSS to `.beagyazas-kep:not([height]) { height: auto }`. Add a case in `app/tests/beagyazas.test.ts:123` ("kép: méret és alt-szöveg").

### 04-embeds-06 — Checkboxes inside embedded notes do not write the embedded file (should, M, medium)

**Today.** Reader: `feladat()` emits `data-jelolo` = offset *in the embedded text* (`olvaso/html.ts:444-455`); `Olvaso.svelte:93-110` interprets it against the **host** editor state — the shape guard at `:104-108` prevents most mis-writes but not a coincidental `[ ]` at that offset. Live Preview: `widget.ts:16,62` lets the native click through, nothing is written.

**Proposal.**
1. `html.ts` `RenderOpciok` (`html.ts:40`) already carries `beagyazas`; in `feladat()` add `data-jelolo-ut = o.ut` and, for embedded content, `data-jelolo-sor` computed from `BeagyazasAdat.kezd` (`core/index/olvaso.py:486-487` returns the slice's first line) so the mark maps to an absolute line/offset in the embedded file.
2. `Olvaso.svelte:93` and a new `change` listener in `widget.ts` (`kont.addEventListener('change', …)`): if `data-jelolo-ut !== own path`, open that file's `Dokumentum` (`szerkesztok.dokumentumok.megnyit(ut)`, as the "Linkelés" flow does per `docs/dev/ARCHITECTURE.md:200`) and dispatch the one-character change there; the Dokumentum's normal save path (`core/vaultio.py` `write`, 409 on conflict) applies.
3. Until then, the Reader should at least ignore `data-jelolo` for embedded content (one-line fix in `Olvaso.svelte:95`).

### 04-embeds-07 — Embeds do not refresh when the embedded note changes (should, M, high)

**Today.** `vault_valtozas` with only known paths does not invalidate (`app/src/lib/vault/linkek.svelte.ts:60-65`); `BeagyazasWidget.eq` compares `verzio` (`widget.ts:30-39`); the editor dispatches `linkVerzioValt` only on `linkek.verzio` (`Szerkeszto.svelte:263-267`); the Reader re-renders only on its own document (`Olvaso.svelte:118-123`); canvas cards likewise (`app/src/canvas/tartalom.ts:42,59-61`).

**Proposal.** Add `tartalomVerzio = $state(0)` to `LinkSzolgaltatas`, bumped in `figyel()` whenever `utak` contains a `.md`/`.canvas`/`.base` path (no cache to clear — `beagyazas()` is uncached, `linkek.svelte.ts:136-140`). `BeagyazasWidget` records the resolved `adat.ut` after load; `eq` additionally compares a `tartalomVerzio` captured at construction, and `blokkMezo.update` (`blokkok.ts:150-162`) rebuilds on a new `tartalomValt` effect. To avoid re-fetching every embed on every save, the widget can keep a `Set` of resolved paths and skip when the changed paths do not intersect (the WS event already lists `utak`). Reader: subscribe the same way in `Olvaso.svelte` and call `rajzol()`.

### 04-embeds-08 — Pasted image naming (should, S, high)

**Today.** `fajl.name` from the clipboard is sent (`csatolmany.ts:38,77-80`); the core only de-duplicates (`core/csatolmany.py:184,223-226`).

**Proposal.** In the `paste` handler, when a clipboard file has a generic/empty name (`image.png`, `blob`), rename it client-side to `Pasted image YYYYMMDDHHMMSS.<ext>` (Obsidian's format, local time) before `fajlImport`. No core change (`nev_ellenor`, `core/csatolmany.py:103-106`, accepts it).

### 04-embeds-09 — `useMarkdownLinks` / `newLinkFormat` ignored when inserting (should, M, high)

**Today.** Inserted text is always `![[shortest]]` (`csatolmany.ts:62-67`, `app/src/media/beszuras.ts:37,52`) from `GET /api/vault/linkcel` (`linkek.svelte.ts:131-134`); the core reads only `attachmentFolderPath` (`core/csatolmany.py:114`) and `newFileLocation` (`core/vaultio.py:403-406`).

**Proposal.** Extend `GET /api/vault/linkcel` (`core/index/api.py`, `linkek.rovid_cel`) to also return `{ markdown: bool, szoveg: "[[…]]" | "[…](…)" }` computed from `.obsidian/app.json` (`useMarkdownLinks`, `newLinkFormat` → shortest/relative/absolute, percent-encoding for the markdown form). The UI inserts `szoveg` (prefixing `!` for media). Keep `cel` for existing callers (`beszuras.ts`, `kiegeszites.ts`). Reading the setting follows the existing read-only rule (`core/csatolmany.py:109-112`). Also drop the `<…>` wrapper in the URL-over-selection paste (`csatolmany.ts:88`) unless the URL contains spaces, to match Obsidian's output.

### 04-embeds-10 — Mid-line note embed is a chip, not content (nice, S, medium)

**Today.** Deliberate (`rajzol.ts:76-77`, `widget.ts:1-2`, `docs/dev/DESIGN.md:196`). Obsidian renders the whole note inline (which usually looks broken). Recommendation: keep the chip, document it as an intentional divergence; optionally render inline when the embedded slice is a single block (`BeagyazasAdat.kezd === veg`).

### 04-embeds-11 — Unsupported file types: chip instead of a file box (nice, S, medium)

**Today.** `egyeb` → `chip` (`rajzol.ts:186,282-299`). Obsidian shows a boxed file embed with the name and opens it in the default app. Proposal: a small `fajl` renderer in `rajzol.ts` (name + size from `/api/vault/fa` info) with an "Open in default app" action once the shell bridge exists (see 14); until then the chip is acceptable.

### 04-embeds-12 — "Insert attachment" command (nice, S, medium)

**Today.** No command; only paste/drop (`csatolmany.ts:74-102`) and tree drop (`Fa.svelte:318`). Proposal: register `szerkeszto.csatolmany` in `app/src/szerkeszto/index.ts` (`parancsok()`), opening an `<input type=file multiple>` and calling the plugin's `beszur(files, null, head)` (expose it via a `ViewPlugin` lookup or a facet).

### 04-embeds-13 — Media-extension lists disagree (nice, S, high)

**Today.** Three lists: `csatolmany.ts:67`, `navigacio.ts:22`, `core/mediatipus.py:19-28` (plus `app/src/media/index.ts:16-18`). Proposal: have `POST /api/vault/import` return `tipus` (`core/csatolmany.py:263`, from `mediatipus.tipus(rp)`), and derive the `!` prefix from it; or export one `MEDIA_KITERJESZTES` regex from `navigacio.ts` and use it in `csatolmany.ts`.

### 04-embeds-14 — Image/embed context menu (nice, M, medium)

**Today.** `helyiMenu.ts:3-9,42` offers cut/copy/paste + commands; the shell bridge has one capability (`hej.ts:38`). Proposal: add `megmutat` (reveal in Finder) and `alapertelmezett` (open in default app) capabilities to `window.manifold`, and menu items when the target is `img.beagyazas-kep` / `.beagyazas-media` (copy image via `navigator.clipboard.write` with the `/media` blob, copy path, reveal, open).

### 04-embeds-15 — Embeds inside table cells in Live Preview (nice, S, medium)

**Today.** `Table` returns `false` (`blokkok.ts:66-80`), so `![[img|50]]` in a cell is raw text unless the table widget renders it. Proposal: let `TablaWidget`/`TablaSzerkesztoWidget` render cells with `dokumentumRenderel` (which handles `Embed`, `html.ts:279-295`) — verify in `app/src/szerkeszto/notion/tablazat/`.

### 04-embeds-16 — Embedded PDF viewer features (nice, M, low)

**Today.** Canvas pages, page field, ‹ ›, open (`pdf/beagyazas.ts:123-144`). Obsidian's embedded viewer (I believe) also offers zoom and text selection. Proposal (only if confirmed): reuse `PdfFul`'s text layer and ⌘-wheel zoom in the embed; keep the lazy/virtualised design.

### 04-embeds-17 — Canvas embed is a static thumbnail (nice, M, medium)

**Today.** SVG thumbnail with a header link (`app/src/canvas/beagyazas.ts:1-2,92-99`). Obsidian renders the real canvas read-only. Proposal: mount the canvas component in read-only mode above a size threshold, keep the SVG for `kompakt` previews and canvas cards (`tartalom.ts:59-61` passes `kompakt: true`).

### 04-embeds-18 — HTML `<img>`/`<iframe>` not rendered (nice, L, high)

Cross-reference only: HTML blocks are raw text (`szerkeszto.css:743-748`). Belongs to the HTML-rendering parity audit; sanitised `<img>` would then flow through the same `/media` resolution as 01.

---

## 3. Manifold strengths beyond Obsidian — preserve

| Strength | Where | Why it matters |
|---|---|---|
| One embed renderer for Live Preview, Reader, hover preview and canvas cards; renderer registries by type and by note class | `app/src/szerkeszto/beagyazas/rajzol.ts:1-7`, `regiszter.ts:31-82`, `elonezet.ts:66-74`, `app/src/canvas/tartalom.ts:59-61` | Consistency; new file types plug in without touching the editor |
| Resolution and slicing exclusively in the core (L42), shared with graph/backlinks/rename | `core/index/olvaso.py:450-488`, `core/index/linkek.py:45-99`, `docs/dev/ARCHITECTURE.md:200` | No UI/core drift; heading/block rules tested once |
| DPR-aware downscaled images (400/800/1600 buckets), EXIF/ICC preserved, LRU cache with orphan cleanup; original only on demand | `core/kepek.py:1-24,37,108-168,184-251`, `app/src/szerkeszto/beagyazas/nagyito.ts:10-15`, `rajzol.ts:216-218` | A 26-photo note no longer costs gigabytes; Obsidian decodes full bitmaps |
| Accessible lightbox for the original (Esc, focus trap, focus return, `role=dialog`) | `nagyito.ts:20-65`, `szerkeszto.css:815-858` | Obsidian core has no image viewer |
| Video poster via pinned ffmpeg + first-frame trick; `#t=` in seconds, `mm:ss`, `h:mm:ss`; width alias | `core/kepek.py:254-337`, `rajzol.ts:236-258`, `linkek/adat.ts:58-65` | Visible preview before play; precise timecode links; `⇧⌘I` inserts `[[v.mp4#t=760\|12:40]]` (`app/src/media/beszuras.ts:49-53,156-184`) |
| PDF embed: lazy on visibility, virtualised pages, canvas memory released off-screen, page field + ‹ ›, "open at this page", resize-aware; iframe fallback | `app/src/media/pdf/beagyazas.ts:1-6,120-144,185-232,302-341`, `rajzol.ts:270-280` | Many PDF embeds per note stay cheap |
| Circular-embed detection with the chain shown; depth cap 6; "too deep" message | `rajzol.ts:20,29-34,79-83`, tests `app/tests/beagyazas.test.ts:87-121` | Clear diagnostics instead of silent truncation |
| Missing target: "Létrehozás" button; core decides the location per Obsidian's `newFileLocation` | `rajzol.ts:101-123`, `navigacio.ts:45-67`, `core/vaultio.py:403-406` | One click to create, consistent with Obsidian's setting |
| Interactive note-class embeds (quiz, card deck, summary) and `.cpp` embeds with run badge | `regiszter.ts:37-45`, `app/src/kviz/index.ts:49`, `app/src/kartya/index.ts:62`, `app/src/osszefoglalas/index.ts:15`, `app/src/kod/beagyazas.ts:1-4` | Transclusion as a live study surface, not just text |
| Bases embed with `#View`, canvas embed, both with open-link headers | `app/src/bazis/beagyazas.ts:55-70`, `app/src/canvas/beagyazas.ts:92-99` | Parity with Obsidian 1.9 Bases embeds already in place |
| Media security: token URL, extension allow-list with fixed Content-Type, `nosniff`, SVG sandbox CSP, Range/206, ETag/304 | `core/media.py:1-7,22-58,61-115`, `core/vaultio.py:257-267`, `core/mediatipus.py:18-28` | Obsidian serves `app://` files without a sandbox |
| HEIC/HEIF, MOV, M4V, Opus, AAC served and decoded natively by WebKit | `core/mediatipus.py:19-28` | iPhone photos/videos work without conversion (Chromium-based Obsidian cannot decode HEIC) |
| Attachment import: chunked/resumable up to 20 GiB, busy-lock retry, collision-safe naming, snapshot commit with `Mos-Forras`, index refresh; insertion point tracked while the upload runs; drop onto a tree folder | `app/src/szerkeszto/csatolmany.ts:19-45,47-72`, `core/csatolmany.py:18,158-272`, `app/src/hej/Fa.svelte:318` | Large media never block the editor; every import is undoable through the snapshot store |
| Keyboard-reachable embed headers and lightbox (`tabIndex`, `role=link`, Enter/Space) | `rajzol.ts:137-151,219-231`, `pdf/beagyazas.ts:123-135` | a11y beyond Obsidian's hover icon |
| Request queue for many embeds (canvas cards ≤ 6 concurrent), abort on destroy, `estimatedHeight` for stable scrolling | `regiszter.ts:27-28`, `widget.ts:71-77`, `rajzol.ts:63-64` | Big notes/canvases stay responsive |
| `![[`/`[[` completion knows embeds, headings and blocks (writes the block id in the same transaction) | `app/src/szerkeszto/linkek/kiegeszites.ts:491-496,524-531`, `docs/dev/ARCHITECTURE.md:200` | Parity with Obsidian's suggester plus one-step block ids |

---

## 4. Open questions

1. **External images (04-embeds-02):** relax the CSP and load remote images directly (Obsidian's behaviour, exposes the user to tracking pixels) or proxy/cache through the core (`core/media.py`) with a privacy switch? The vault is a study corpus with few remote images, so the proxy may be the better default.
2. **PDF height (04-embeds-03):** after `#height=` lands, keep `|N` as a Manifold alias (DESIGN.md:196) or deprecate it? Recommendation: keep both; `#height=` wins when both are present.
3. **Inline note embeds (04-embeds-10):** confirm the chip is an intentional divergence and record it in `docs/dev/DESIGN.md` §12.
4. **Image click (row 21):** keep lightbox-on-click in Live Preview (users coming from Obsidian expect cursor placement)? Option: lightbox on click, cursor on ⌥-click; or cursor on click and lightbox on double-click.
5. **Checkbox writes in embeds (04-embeds-06):** write through the target's `Dokumentum` (UI, conflict-aware) or add a tiny core endpoint (`POST /api/vault/feladat {ut, sor, allapot}`) so the Reader and canvas cards can toggle without opening a document? The gépi-írás lock (`core/csatolmany.py:45-56` shows the pattern) must be respected either way.
6. **Link format (04-embeds-09):** the vault convention (AI01) is wikilinks; is honouring `useMarkdownLinks` worth it, or should Manifold only honour `newLinkFormat` (shortest/relative/absolute)?
7. **Pasted image name:** Obsidian's English `Pasted image …` even in a Hungarian vault? Recommended: identical to Obsidian so vaults stay interchangeable.
8. **Obsidian facts to verify by testing (low confidence rows):** exact embed depth limit and message; `#t=` support on core audio/video embeds; width alias on video; toolbar/text-selection features of the embedded PDF viewer; default embedded PDF height.
9. **Live refresh (04-embeds-07):** should the refresh be debounced per path (a note edited in a split pane saves on every keystroke-debounce) and should the Reader re-render only the affected embed node rather than the whole document?
