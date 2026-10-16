# 01 — Obsidian-parity audit: Live Preview, Source mode and Reading view rendering

Scope: the Manifold Markdown note view (`app/src/szerkeszto/`): the three modes (Live Preview = `elo`, Source = `forras`, Reading view = `olvaso`), the shared Lezer parser (`markdown/`), the renderers (`renderelok/`), the Reader DOM builder (`olvaso/`), the embed engine (`beagyazas/`) and the CSS that styles them. Baseline: Obsidian 1.8/1.9 desktop, core features and core plugins only. Method: static reading of the code at the cited paths (all relative to `/Volumes/Work/[UNI] Manifold-OS`); nothing was run. Reference docs: `docs/dev/ARCHITECTURE.md:196-204` (editor, Notion layer, links/embeds, media), `docs/dev/DESIGN.md:86-91,174-204` (typography, editor, Notion layer, links), `docs/plan/audit/03-felulet.md:81,220-238` (UI map, `felulet.json` settings).

Legend. Status: **present** / **partial** / **missing** (and **n/a** when Obsidian core has no such behaviour). Severity: **must** = daily-use Obsidian behaviour users miss immediately; **should** = noticeable; **nice** = polish. Effort: S < 1 day, M 1–3 days, L > 3 days. Confidence marks how sure the Obsidian side of the comparison is (high / medium / low); low means "verify in Obsidian before building".

Product rule applied throughout: nothing Manifold already does may be lost — section 3 lists what must be preserved while closing gaps.

---

## 1. Checklist

### 1.1 Modes, frame, settings

| # | Obsidian behaviour | Manifold today (path:line) | Status | Sev. | Eff. | Conf. |
|---|---|---|---|---|---|---|
| A1 | Three views: Live Preview, Source mode, Reading view; ⌘E toggles edit/read, ⇧⌘E (via command) LP/Source | `Szerkeszto.svelte:49,204-222` (`mod`, `modBeallit`), commands `index.ts:148-165` (⌘E `szerkeszto.olvaso`, ⇧⌘E `szerkeszto.forras`); header button `Szerkeszto.svelte:345-355` | present | — | — | high |
| A2 | Switching modes keeps the reading position | `Szerkeszto.svelte:206-221` (top line → `Olvaso.gorget`/`scrollIntoView`), `Olvaso.svelte:40-59` (`felsoPozicio`/`gorget` on `data-from`), `olvaso/html.ts:657-661` | present | — | — | high |
| A3 | "Default editing mode" (LP or Source) remembered | `lib/elrendezes/felulet.svelte.ts:22-23,66,147,218` (`szerkesztoMod` in `felulet.json`), `Szerkeszto.svelte:58-61,210` | present | — | — | high |
| A4 | "Default view for new tabs" can be Reading view | `Szerkeszto.svelte:58-61` only knows `elo`/`forras` as defaults; `olvaso` only per tab (`ful.nezet.mod`) | missing | nice | S | high |
| A5 | Source mode: raw Markdown, syntax still styled (heading sizes, bold…), no widgets | `beallitas.ts:87-89` (`forrasMod` = class only), `beallitas.ts:122` (`stilusPlugin` in both modes), `elo/sorok.ts:76-219`; no `blokkMezo`/`elonezetPlugin` in Source (`beallitas.ts:83-85`); test `app/tests/szerkeszto-elo.test.ts:112` | present | — | — | high |
| A6 | Readable line length (toggle, default on) | always on: `szerkeszto.css:34-42` (`max-width: var(--olvasasi-szelesseg)` = 44 rem, `styles/tokens.css:170`), Reader `.tipo` `styles/alap.css:155-160`; no toggle anywhere (`felulet.svelte.ts:24-47` has no such key) | partial | should | S | high |
| A7 | Show line numbers (gutter, toggle, default off) | none in the Markdown editor (`beallitas.ts:105-146`); exists only in the C++ editor `kod/szerkeszto.ts:52` | missing | nice | S | high |
| A8 | Indentation guides for nested lists (default on) | none (`szerkeszto.css` has no list-line class; `elo/sorok.ts:289-297` only swaps the bullet) | missing | nice | S | high |
| A9 | Font size setting (Appearance → Font size) and ⌘+/⌘− zoom | fixed tokens `styles/tokens.css:144-158` (`--betu-torzs: 16px`), `DESIGN.md:89`; no user setting | missing | should | S | high |
| A10 | Inline title (file name as H1 above the body, editable, toggle) | `Szerkeszto.svelte:363` + `FajlCim.svelte:31-45`: editable file-name input, H2 size (`--betu-h2`), renames via core plan (`FajlCim.svelte:18-23`); always on | partial | nice | S | high |
| A11 | Properties in document: visible / hidden / source | LP: properties widget replaces YAML `tulajdonsagok/elo.svelte.ts:72-81`; Source: raw YAML; Reader: panel `Szerkeszto.svelte:364-374` + raw box hidden `szerkeszto.css:981-984`; no "hidden/source" choice | partial | nice | S | high |
| A12 | Typewriter / focus mode | Obsidian core has neither (community plugins). Manifold has "csend mód" (chrome fades while typing) `lib/elrendezes/csend.svelte.ts:1-5`, `styles/alap.css:233-260`, `Szerkeszto.svelte:327-328` | n/a (Manifold ahead) | — | — | high |
| A13 | ⌘F find inside Reading view | `index.ts:204`: `szerkeszto.kereses` disabled when `mod() === 'olvaso'`; `Olvaso.svelte` has no search | missing | should | S | high |

### 1.2 Block elements

| # | Obsidian behaviour | Manifold today (path:line) | Status | Sev. | Eff. | Conf. |
|---|---|---|---|---|---|---|
| B1 | Headings H1–H6 (ATX + setext), `#` hidden in LP, closing `#` hidden, sized by level | parser: commonmark `beallitas.ts:80`; LP hide `elo/sorok.ts:306-317`, setext underline hidden `elo/blokkok.ts:118-127`; sizes `szerkeszto.css:54-98`, Reader `styles/alap.css:163-204`, `olvaso/html.ts:357-367` | present | — | — | high |
| B2 | Heading folding (fold arrow on hover, LP and Reading view; "Fold heading" default on; fold all/unfold all commands) | none: no `foldGutter`/`foldService`/`foldKeymap` in `beallitas.ts:105-146`; only the C++ editor folds `kod/szerkeszto.ts:54,69`; Reader has no collapse (`olvaso/html.ts:357-367`) | missing | should | M | high |
| B3 | Lists: `-`/`*`/`+` bullets, ordered with start number, nesting by indent | LP bullet widget `elo/sorok.ts:289-297`, `elo/widgetek.ts:323-339`; Reader `olvaso/html.ts:423-442` (`start` 426-430); indent unit = tab, width 4 `beallitas.ts:116-117` | present | — | — | high |
| B4 | Wrapped list lines hang under the text, not under the bullet (LP) | `beallitas.ts:114` `EditorView.lineWrapping` with no per-line indent decoration; no `text-indent` in `szerkeszto.css`/`notion.css` | missing | should | S | high |
| B5 | List (indent) folding — "Fold indent", LP and Reading | none (see B2) | missing | should | S (after B2) | high |
| B6 | Task lists: `- [ ]`, checkbox in LP and Reading, click toggles the file, done = struck/muted, custom states `[/]` `[-]` | parser `markdown/feladat.ts:8,29-31,41-42`; LP `elo/sorok.ts:298-305`, `elo/widgetek.ts:274-306` (writes `x`/space); Reader `olvaso/html.ts:444-460`, `Olvaso.svelte:94-111` (staleness guard); style `szerkeszto.css:172-185`; test `app/tests/szerkeszto-olvaso.test.ts:64` | present | — | — | high |
| B7 | Tables (GFM, alignment row, inline Markdown in cells); LP table editor (1.5+): in-place cell editing, row/column menus, add row/col | parser `markdown/tablazat.ts:76-133` (+ math-aware split 36-45); Reader `olvaso/html.ts:370-421` (alignment 373-384); LP visual editor always `elo/blokkok.ts:66-80`, `notion/tablazat/szerkeszto.ts:1-9` (cells, Tab/Enter, handles, align, "+"); nested-in-list fallback `elo/widgetek.ts:84-122` | present | — | — | high |
| B8 | Table cell shows rendered Markdown while editing | Manifold edits the raw cell source in an `<input>` (`notion/tablazat/szerkeszto.ts:1-3`) | partial | nice | M | medium |
| B9 | Callouts `> [!type]`: 13 type families with Obsidian colours/icons, aliases, unknown type → note look with capitalised title, title may contain inline Markdown, nestable | `renderelok/callout.ts:35-64` (note, abstract/summary/tldr, info, todo, tip/hint/important, success/check/done, question/help/faq, warning/caution/attention, failure/fail/missing, danger/error, bug, example, quote/cite), unknown 93-102; detection `markdown/callout.ts:7,26-49`; LP `elo/sorok.ts:116-133,270-285`, widgets `elo/widgetek.ts:438-494`; Reader `olvaso/html.ts:521-550` (title Markdown 533-536); colours `szerkeszto.css:260-287`, tokens `styles/tokens.css:93-106`; tests `app/tests/szerkeszto-elemzo.test.ts:171-181` | present | — | — | high |
| B10 | Foldable callouts `[!type]-` / `[!type]+`, chevron, body hidden, fold state is view state (not written) | LP `elo/hajtas.ts:7-27`, `elo/blokkok.ts:56-65`, `elo/widgetek.ts:420-434`; Reader `<details>` `olvaso/html.ts:526-528`; test `app/tests/szerkeszto-elo.test.ts:104` | present | — | — | high |
| B11 | Blockquotes, nested depth | LP `elo/sorok.ts:70-74,116-133,286-288`, `szerkeszto.css:201-207`; Reader `olvaso/html.ts:577-583`, `szerkeszto.css:629-634` | present | — | — | high |
| B12 | Fenced + indented code blocks with syntax highlighting (both views) | parser `codeLanguages: languages` `beallitas.ts:80`, `syntaxHighlighting(classHighlighter)` `beallitas.ts:121`; LP lines `elo/sorok.ts:134-157`; Reader `renderelok/kodszin.ts:9-43`, `olvaso/html.ts:490-519`; token colours (both themes) `szerkeszto.css:341-365`, `styles/tokens.css:84-91` | present | — | — | high |
| B13 | Code block copy button (Reading view; hover) | Reader `olvaso/html.ts:468-487,507-511`; **also in LP** (`elo/widgetek.ts:386-408` header replaces the opening fence, reads live code 410-417) | present (ahead) | — | — | medium (LP side in Obsidian) |
| B14 | Code block language label | Obsidian default theme shows none; Manifold shows it in both views (`olvaso/html.ts:509-510`, `elo/widgetek.ts:398-400`) | n/a (ahead) | — | — | medium |
| B15 | Line numbers inside code blocks | Obsidian core: none; Manifold: none | n/a | — | — | high |
| B16 | Math block `$$…$$` (own lines), rendered when not active; inside lists/quotes | parser `markdown/matek.ts:40-78,130-137` (container-aware 63), quotes stripped `markdown/fa.ts:25-43`; LP `elo/blokkok.ts:81-89`; Reader `olvaso/html.ts:590-592,176-184`; test `app/tests/szerkeszto-elemzo.test.ts:74-85` | present | — | — | high |
| B17 | Horizontal rule `---`/`***` | LP widget `elo/blokkok.ts:96-100`, `elo/widgetek.ts:126-150`, source dimmed `elo/sorok.ts:176-178`; Reader `olvaso/html.ts:596-598`; CSS `szerkeszto.css:462-479` | present | — | — | high |
| B18 | Frontmatter: Properties editor in LP and Reading, raw YAML in Source, invalid YAML shown raw with an error | parser `markdown/frontmatter.ts:11-44`; LP widget `tulajdonsagok/elo.svelte.ts:26-59,72-81` + cursor guard 111-119; Reader `Szerkeszto.svelte:364-374`; Source raw `szerkeszto.css:412-430`; tests `app/tests/tulajdonsagok-elo.svelte.test.ts:78-157` | present | — | — | high |
| B19 | Footnotes `[^id]` / `[^id]: …`: superscript number in both views, list at the bottom of Reading view with back-links, numbered by first reference | parser `markdown/labjegyzet.ts:8-9,17-70`; LP ref widget `elo/sorok.ts:381-386`, def lines dimmed 168-170; Reader `olvaso/html.ts:296-312,601-605,622-646`, jump `Olvaso.svelte:75-85`; test `app/tests/szerkeszto-olvaso.test.ts:136` | present | — | — | high |
| B20 | Inline footnotes `^[text]` | not parsed: `markdown/labjegyzet.ts:8-9` only `[^label]` forms | missing | should | S | high |
| B21 | HTML blocks (`<div>`, `<details>`, `<center>`, `<img>`…) rendered (sanitised) in Reading view and LP | Reader prints the raw source in a mono box `olvaso/html.ts:606-611`, `szerkeszto.css:743-748`; LP leaves source `elo/sorok.ts:253` | missing | should | M | high |
| B22 | `%% comment %%` (inline and multi-line): hidden in Reading view, muted in LP | not in the parser (`markdown/elemzo.ts:18-28`); shown as plain text in all views. Only the block model knows it (`notion/blokkmodell.ts:8-16,91,102-104`) | missing | must | S | high |
| B23 | HTML comment `<!-- -->` muted in LP, hidden in Reading | LP `elo/sorok.ts:179-183`; Reader `olvaso/html.ts:57,612-615` | present | — | — | high |
| B24 | Mermaid code block rendered in both views, follows theme | `renderelok/mermaid.ts:18-85` (lazy, `securityLevel: 'strict'`, tokens 30-45, re-render on theme change 74-76); registration `index.ts:265`; LP `elo/blokkok.ts:101-113`; Reader `olvaso/html.ts:494-506` | present | — | — | high |
| B25 | ```` ```query ```` embedded search results (core Search) | no `query` renderer (`index.ts:265-266`: only `mermaid`, `plot`; Bases registers `base` `bazis/index.ts:19`) | missing | nice | M | high |
| B26 | Block ids `^id`: dimmed at line end in LP, hidden in Reading | LP `elo/sorok.ts:393-416`, `szerkeszto.css:109-112`; Reader `olvaso/html.ts:336-345`; tests `app/tests/elo-html.test.ts:46`, `szerkeszto-olvaso.test.ts:155` | present | — | — | high |

### 1.3 Inline elements

| # | Obsidian behaviour | Manifold today (path:line) | Status | Sev. | Eff. | Conf. |
|---|---|---|---|---|---|---|
| C1 | Bold / italic / strikethrough, markers hidden in LP | `elo/sorok.ts:25-28,318-322`; Reader `olvaso/html.ts:215-220`; CSS `szerkeszto.css:114-124` | present | — | — | high |
| C2 | `==highlight==` | parser `markdown/jeloles.ts:11-38`; LP `elo/sorok.ts:29,321`; Reader `olvaso/html.ts:221-222`; CSS `szerkeszto.css:126-129,701-706` | present | — | — | high |
| C3 | Inline code | `elo/sorok.ts:30,323-325`; Reader `olvaso/html.ts:223-229` | present | — | — | high |
| C4 | Inline math `$…$` and inline display `$$…$$` | parser `markdown/matek.ts:84-120` (index-identical rule); LP `elo/sorok.ts:329-334`, `elo/blokkok.ts:90-95`; Reader `olvaso/html.ts:230-233` | present | — | — | high |
| C5 | Wikilinks `[[note#heading\|alias]]`: brackets hidden in LP, alias shown, click opens (⌘ new tab), unresolved link → create | parser `markdown/wikilink.ts:12-57`; LP `elo/sorok.ts:335-354`, click `linkek/szerkeszto.ts:1-3`; Reader `olvaso/html.ts:265-278`, `Olvaso.svelte:61-73`; create on unresolved `linkek/navigacio.ts:1-3` | present | — | — | high |
| C6 | Unresolved wikilink styled dimmer (`is-unresolved`) | no resolution-based styling (`elo/sorok.ts:33-34` one `cm-wikilink` class; Reader `olvaso/html.ts:267`); resolution is core-only (`lib/vault/linkek.svelte.ts:104-115` `feloldas`) | missing | nice | M | high |
| C7 | Markdown link `[text](url)`: LP shows only the link text (url hidden), click opens | LP keeps the full `[text](url)` visible; `elo/sorok.ts:231-391` has no `Link`/`LinkMark`/`URL` hiding (only dimming via `JELOLO_NEVEK` 40-56); click works `linkek/szerkeszto.ts:39-54`; Reader fine `olvaso/html.ts:234-242` | partial | should | S | high |
| C8 | Markdown link to a note `[t](Note.md)` / `[t](<Other note.md>)` navigates like a wikilink | Reader: relative URL → `kulsoCim` returns `null` → plain text `linkek/kulso.ts:11-23`, `olvaso/html.ts:186-194`; LP: `kulsoLinkAt` same rule `linkek/szerkeszto.ts:39-54` | missing | should | M | high |
| C9 | Reference-style links `[text][id]` + `[id]: url` | `LinkReference` hidden `olvaso/html.ts:59,612-615`; `linkSzoveg` only reads a `URL` child 196-211 → rendered as non-clickable text | missing | nice | S | medium |
| C10 | Autolinks `<https://…>` and bare URLs clickable | Reader `olvaso/html.ts:250-264`; LP `elo/sorok.ts:32`, `linkek/szerkeszto.ts:39-54` | present | — | — | high |
| C11 | External link indicator (small arrow icon after external links in Reading view) | none (`szerkeszto.css:708-718`) | missing | nice | S | high |
| C12 | `#tag` rendered as a clickable tag pill in LP and Reading (click → search `tag:`) | not parsed (`markdown/elemzo.ts:18-28`); no decoration/element; plain text everywhere. Core has `GET /api/vault/cimkek` (`ARCHITECTURE.md:235`) and `tag:` search syntax (`DESIGN.md:222`) | missing | must | S | high |
| C13 | Escapes `\*` (backslash hidden), entities `&amp;` | LP `elo/sorok.ts:326-328`; Reader `olvaso/html.ts:313-316,329-332` | present | — | — | high |
| C14 | Inline HTML (sanitised; tags with attributes, e.g. `<span style>`, `<a href>`, `<img src>`, `<font color>`, `<kbd>`) | allow-list of 14 attribute-less text tags only: `markdown/html.ts:6,9-13`; LP `elo/sorok.ts:355-380`; Reader `olvaso/html.ts:120-141,317-318`; tests `app/tests/elo-html.test.ts:12-33`, `szerkeszto-olvaso.test.ts:50` | partial | should | M (with B21) | high |
| C15 | Single newline = line break (Strict line breaks off by default); toggle | Reader `olvaso/html.ts:88-103` (`\n` → `<br>`), `DESIGN.md:178`; no toggle | partial | nice | S | high |
| C16 | Hard break (two spaces / `\`) | Reader `olvaso/html.ts:319-322` | present | — | — | high |
| C17 | `<br>` inline → real break in LP | `elo/sorok.ts:360-363`, `elo/widgetek.ts:309-321` | present | — | — | high |

### 1.4 Embeds and media

| # | Obsidian behaviour | Manifold today (path:line) | Status | Sev. | Eff. | Conf. |
|---|---|---|---|---|---|---|
| D1 | `![[note]]`, `![[note#Heading]]`, `![[note#^block]]` embeds in both views, with a title bar and open link; recursion guard | `beagyazas/rajzol.ts:127-171` (title 137-152, body via Reader renderer 153-164), circular/depth 29-34,79-83; LP block/inline `elo/blokkok.ts:128-138`, `beagyazas/widget.ts:18-82`; core `GET /api/vault/beagyazas` (`ARCHITECTURE.md:250`); tests `app/tests/beagyazas.test.ts:50-112` | present | — | — | high |
| D2 | Mid-paragraph `![[note]]` renders as an inline embed (full content) | Manifold renders a link chip for notes mid-line (`beagyazas/rajzol.ts:76-77,282-299`); images/video stay media | partial | nice | S | medium |
| D3 | Images `![[img.png\|300]]`, `![[img.png\|300x200]]`, alias as alt | `linkek/adat.ts:51-56`, `beagyazas/rajzol.ts:203-234`; served `GET /media/<token>/<út>?w=` (`ARCHITECTURE.md:202,254`); test `app/tests/beagyazas.test.ts:123-159` | present | — | — | high |
| D4 | Image alignment (`\|left`, `\|right`) | not core in Obsidian (theme/CSS snippets); Manifold: none | n/a | — | — | high |
| D5 | Markdown-syntax images to vault files: `![alt](attachments/a.png)`, `![alt\|300](a.png)` | Reader: placeholder text `[kép: alt]` `olvaso/html.ts:243-249`, `szerkeszto.css:720-724`; LP: raw source (no `Image` case in `elo/sorok.ts:231-391`); test documents this `app/tests/szerkeszto-olvaso.test.ts:40` | missing | must | M | high |
| D6 | External images `![](https://…)` and `<img src="https://…">` | blocked by CSP `app/index.html:8-9` (`img-src 'self' data: blob:`); cover image already documents the limit `tulajdonsagok/Boritokep.svelte:3-4,29-31`; same placeholder as D5 | missing | should | M | high |
| D7 | Click image → zoom/lightbox | Obsidian core: none; Manifold lightbox `beagyazas/rajzol.ts:198-201,222-231`, `beagyazas/nagyito.ts`, `szerkeszto.css:816-858` | n/a (ahead) | — | — | high |
| D8 | Video / audio embeds | `beagyazas/rajzol.ts:239-268` (+ `#t=` start, poster, first frame) | present (ahead: `#t=`) | — | — | medium (Obsidian core lacks `#t=`) |
| D9 | PDF embed `![[doc.pdf#page=3]]` | fallback iframe `beagyazas/rajzol.ts:270-280`; registered pdf.js box with page navigation `media/pdf/beagyazas.ts:1-6,353`; test `app/tests/beagyazas.test.ts:214` | present | — | — | high |
| D10 | PDF embed height `![[doc.pdf#height=400]]` | only `\|N` alias sets height (`beagyazas/rajzol.ts:273-276`); `mediaHorgony` parses `t=`/`page=` only (`linkek/adat.ts:58-69`) | missing | nice | S | high |
| D11 | Canvas / Base embeds (1.9) | registered renderers `canvas/index.ts:65`, `bazis/index.ts:19-20`; chip fallback `beagyazas/rajzol.ts:85-91` | present | — | — | high |
| D12 | ⌘-hover link preview (Page preview) in both views | `linkek/elonezet.ts:1-5,18-19`; Reader hook `Olvaso.svelte:113-116`; LP `linkek/szerkeszto.ts:1-3` | present | — | — | high |
| D13 | Footnote hover preview | none (`olvaso/html.ts:296-312` only jumps) | missing | nice | S | low |

### 1.5 Cross-cutting

| # | Obsidian behaviour | Manifold today (path:line) | Status | Sev. | Eff. | Conf. |
|---|---|---|---|---|---|---|
| E1 | Dark/light parity of all rendered elements | every colour is a `light-dark()` token `styles/tokens.css:84-108`; KaTeX inherits text colour, `errorColor: var(--hiba)` `renderelok/katex.ts:29-41`; Mermaid re-renders from tokens on theme change `renderelok/mermaid.ts:30-45,74-76`, `renderelok/tema.ts:4-34`; contrast table `DESIGN.md:53-82`; checkboxes `accent-color` `szerkeszto.css:172-179` | present | — | — | high |
| E2 | Math engine: MathJax (Obsidian) vs KaTeX (Manifold); some MathJax-only macros/environments | `renderelok/katex.ts:8-23` bridges `\to` in text and bare `_\max`-style operators; `strict: 'ignore'`, `throwOnError: false` 29-41; vault-wide gate `tests/kezi/kepletek.py` (`ARCHITECTURE.md:196`) | partial | nice | S | medium |
| E3 | Large notes stay responsive | Reader renders math/code/renderers lazily `olvaso/lusta.ts:4-57` (800 px lookahead), parse budget `Olvaso.svelte:30`; LP widgets reuse DOM by `eq` and reserve height `elo/widgetek.ts:1-2,55-57,115-117,263-265` | present | — | — | high |
| E4 | Security: HTML never injected raw | `olvaso/html.ts:1-2` (no `innerHTML` except KaTeX `trust:false` and Mermaid strict), CSP `app/index.html:8-9`, SVG sandbox on media (`ARCHITECTURE.md:202`) | present (stricter than Obsidian) | — | — | high |

---

## 2. Gaps and how to close them

Each proposal stays inside the existing architecture: parser extensions go into `app/src/szerkeszto/markdown/` and the `OBSIDIAN_BOVITESEK` list (`markdown/elemzo.ts:18-28`) so that Live Preview, Reading view and the formula script keep one parser; LP decorations go into `elo/sorok.ts` (line/inline) or `elo/blokkok.ts` (block widgets); Reader DOM goes into `olvaso/html.ts`; anything that needs vault knowledge asks the core (link resolution only in the core, L42 — `ARCHITECTURE.md:200`). Settings persist through `Felulet` → `felulet.json` (`lib/elrendezes/felulet.svelte.ts:24-47,218-230`, `GET/PUT /api/felulet/allapot`, `ARCHITECTURE.md:194`).

### 01-rendering-01 — `%% comments %%` (must, S, high)

- Obsidian: `%%…%%` is a comment; inline or spanning lines. Hidden in Reading view; shown muted in LP (and in Source).
- Manifold: not parsed (`markdown/elemzo.ts:18-28`), so the text leaks into the Reader and is formatted like normal text in LP. The block model already treats a `%%…%%` run as one unit (`notion/blokkmodell.ts:8-16,102-104`) and the media inserter escapes `%%` (`media/beszuras.ts:29`), so the product already assumes comment semantics.
- Proposal: new `markdown/megjegyzes.ts` with (a) an inline parser (`parseInline`, `before: 'Emphasis'`) producing `ObsidianComment` / `CommentMark` for same-paragraph `%%…%%` (mirror the `kepletVege` style scan in `markdown/matek.ts:84-106`; no comment inside code/math because those are parsed earlier), and (b) a block parser (`parseBlock`, `after: 'FencedCode'`, container-aware via `tarolobanMarad` `markdown/belso.ts:14-18`) for a `%%` line that closes on a later `%%` line; add to `OBSIDIAN_BOVITESEK`. LP: add the node to `JELOLO`-style dimming in `elo/sorok.ts:179-183` (next to `CommentBlock`) and to `LEVEL` in `elo/aktivBlokk.ts:16-37`; keep the text visible (Obsidian does). Reader: return early in `olvaso/html.ts:213-327` (`sorbanElem`) and `:568-620` (`blokk`) like `CommentBlock`. Keep `%%manifold-kiemeles …%%` marker lines (`notion/blokkmodell.ts:91`) hidden in the Reader as a welcome side effect, but confirm with the PDF-highlight owner (open question 4). Exclude `KOD_NEVEK`-style contexts from the block-id dimming (`elo/sorok.ts:416`) by adding the new node name.

### 01-rendering-02 — Inline `#tags` (must, S, high)

- Obsidian: `#tag`, `#nested/tag`, Unicode letters, `_`/`-`; rendered as a pill in LP (outside the active line) and Reading; click opens Search with `tag:#tag`.
- Manifold: plain text (`markdown/elemzo.ts:18-28`; no `Tag` node, no CSS). The vault's AI01 convention keeps tags in the `Tags` property (`tulajdonsagok/Tulajdonsagok.svelte:1-11`), but Obsidian users expect body tags to work.
- Proposal: `markdown/cimke.ts` inline parser (`before: 'Emphasis'`): `#` not preceded by a word char, followed by `[\p{L}\p{N}_/-]+` with at least one non-digit (Obsidian rule), not inside code/math (parsed earlier). Node `Hashtag` with `HashtagMark`. LP: `Decoration.mark({class:'cm-cimke'})` in `JELOLES` (`elo/sorok.ts:25-38`) and a `mousedown` handler in `linkek/szerkeszto.ts` (next to `kulsoLinkAt`, `:39-54`) that opens the search overlay with `tag:` (the search window already parses `tag:` — `DESIGN.md:222`). Reader: `olvaso/html.ts:213-327` → `<a class="cimke" data-cimke>` and a click branch in `Olvaso.svelte:61-73`. Style: a pill from `--hatter-hover`/`--akcent-szoveg` (no new token). Core: nothing needed for rendering; `GET /api/vault/cimkek` (`ARCHITECTURE.md:235`) can later feed a tag-completion.

### 01-rendering-03 — Markdown-syntax images to vault files (must, M, high)

- Obsidian: `![alt](attachments/a.png)`, `![alt|300](a.png)`, `![alt](<file with spaces.png>)` render in LP and Reading, with `|size` in the alt text, resolved relative to the note and (fallback) by the Obsidian link rule.
- Manifold: Reader prints `[kép: alt]` (`olvaso/html.ts:243-249`), LP shows raw source (no `Image` branch in `elo/sorok.ts`).
- Proposal: in `olvaso/html.ts` `case 'Image'` build a `LinkAdat`-like object from the `URL` child (decode `%20`, strip `<>`), split `|size` out of the alt with `meretAliasbol` (`linkek/adat.ts:51-56`) and call `beagyazasElem` (`beagyazas/rajzol.ts:46-53`) with `cel` = the path; the core resolves it through `GET /api/vault/beagyazas?forras=&cel=` (`ARCHITECTURE.md:250`) — verify the core accepts a relative path with extension as `cel` (open question 2). LP: in `elo/blokkok.ts:128-138` extend the `Embed` branch to `Image` nodes whose URL is not `http(s):` (block widget when alone on the line, inline otherwise) via `BeagyazasWidget` (`beagyazas/widget.ts:18-82`). Keep `kep-helyorzo` only for the unsupported external case until 04 lands. Update `app/tests/szerkeszto-olvaso.test.ts:40`.

### 01-rendering-04 — External images (should, M, high)

- Obsidian: `![](https://…)` and `<img src="https://…">` load from the network.
- Manifold: CSP `img-src 'self' data: blob:` (`app/index.html:8-9`) and the cover image comment (`tulajdonsagok/Boritokep.svelte:3-4`) make this a deliberate boundary.
- Proposal (needs a product decision, open question 1): either (a) relax CSP to `img-src 'self' data: blob: https:` and render `<img>` directly from the `Image` branch (03) with `referrerpolicy="no-referrer"` and `loading="lazy"`, or (b) keep the CSP and add a core proxy `GET /media/<token>/kulso?url=` (only `https:`, size/time limits, cache under `var/cache`) so the UI stays origin-locked; the UI change is identical to 03 (`beagyazas/rajzol.ts:203-234` with a `src` from `linkek.mediaUrl`-style helper). Reader placeholder stays as the offline/error state. Same switch would unlock the external `cover` image.

### 01-rendering-05 — Heading folding (should, M, high)

- Obsidian: fold arrow on hover in the gutter for every heading (LP and Source), the section collapses to the heading; "Fold heading" setting; "Fold all headings and lists" / "Unfold all" commands; Reading view headings collapse too; fold state kept per file in the workspace.
- Manifold: no fold service in the Markdown editor (`beallitas.ts:105-146`); the C++ editor already wires `foldGutter`/`foldKeymap` (`kod/szerkeszto.ts:54,69`) so the dependency exists.
- Proposal: add `foldService.of()` in `beallitas.ts` that returns the range from the end of the heading line to the start of the next heading of equal/higher level (walk `ATXHeading*`/`SetextHeading*` via `syntaxTree`), `foldGutter({ openText, closedText })` styled from tokens (hidden until hover, like Obsidian) and `foldKeymap`; commands `szerkeszto.hajt-mind`/`szerkeszto.kibont-mind` in `index.ts:80-230`. Make `blokkMezo`/`stilusPlugin` tolerate folded ranges (they already iterate `visibleRanges`, `elo/sorok.ts:100,244`). Persist fold ranges per tab in `ful.nezet` (`Szerkeszto.svelte:63-65,174-182`, 2 KB cap per `ARCHITECTURE.md:196`) using `foldState` mapping. Reader: in `olvaso/html.ts:357-367` give headings a `button.hajto` and wrap the section (`data-from`…next heading) so `Olvaso.svelte` can toggle `hidden`; reuse the callout chevron style (`szerkeszto.css:240-258`).

### 01-rendering-06 — List (indent) folding (should, S after 05, high)

- Obsidian: list items with children fold ("Fold indent"), in LP and Reading view.
- Proposal: extend the fold service from 05 with `ListItem` nodes that contain a nested `BulletList`/`OrderedList` (fold from the end of the first line to `ListItem.to`); Reader: `olvaso/html.ts:423-442` adds the chevron on `li` elements that contain a nested list.

### 01-rendering-07 — Readable line length toggle (should, S, high)

- Obsidian: Settings → Editor → Readable line length (default on); off = full width.
- Manifold: fixed 44 rem (`szerkeszto.css:34-42`, `styles/alap.css:155-160`, `FajlCim.svelte:43`, `Szerkeszto.svelte:462-466`).
- Proposal: a `felulet.olvashatoSorhossz` boolean (`lib/elrendezes/felulet.svelte.ts:24-47`, serialised `:218-230`), a ⌘P command "Olvasható sorhossz be/ki" next to the view commands (`index.ts:148-165`), and a `data-teljes-szelesseg` attribute on `.szerkeszto` (`Szerkeszto.svelte:326`) that sets `--olvasasi-szelesseg: none`/`100%` for `.cm-content`, `.md`, `.fajlcim` and the properties panel. No new token.

### 01-rendering-08 — Markdown link `[text](url)` not collapsed in LP (should, S, high)

- Obsidian LP: only the link text is shown (underlined), the `(url)` and brackets appear when the cursor enters the link.
- Manifold: `elo/sorok.ts:231-391` never hides `LinkMark`/`URL`; the whole `[text](url)` stays visible (only dimmed by `JELOLO`, `:40-56`).
- Proposal: add `case 'Link'` in `elonezet()` (`elo/sorok.ts:248`): when `!sorAktiv(n.from)` push `ELREJT` for the opening `[`, and from `]` to the end of the node (covering `(`, `URL`, optional title, `)`); keep `cm-link` mark from `JELOLES` (`:31`). Skip when the parent is `Image` (handled by 03). Mirror for `Autolink` (`<` `>` marks) if Obsidian hides them (verify; low confidence on that detail).

### 01-rendering-09 — Markdown links to notes do not navigate (should, M, high)

- Obsidian: `[t](Note.md)`, `[t](folder/Note.md)`, `[t](<Note with spaces.md>)`, `[t](Note.md#Heading)` open the note; URL-encoded paths too. Vaults with "Use [[Wikilinks]]" off are written this way.
- Manifold: relative targets are rejected by `kulsoCim` (`linkek/kulso.ts:11-23`) in both views (`olvaso/html.ts:234-242`, `linkek/szerkeszto.ts:39-54`), so they are plain text.
- Proposal: in `kulsoLinkAt`/`linkSzoveg`, when `kulsoCim` returns `null` and the target has no scheme, decode it and build a `LinkAdat` (`cel` = path without `.md`, `alcel` = fragment) and route it through `linkMegnyit` (`linkek/navigacio.ts:1-3`), which already asks the core (`POST /api/vault/feloldas`, `ARCHITECTURE.md:248`; `GET /api/vault/beagyazas` for the hover preview). Reader: set `data-cel`/`data-forras` on the `<a>` exactly as the wikilink branch does (`olvaso/html.ts:265-278`) so `Olvaso.svelte:61-73` handles it. Check that the core index counts Markdown links as links for backlinks (open question 3).

### 01-rendering-10 — Inline footnotes `^[text]` (should, S, high)

- Obsidian: `^[inline note]` becomes a numbered footnote whose body is the inline text; listed at the bottom with the others.
- Manifold: `markdown/labjegyzet.ts:8-9` recognises only `[^id]`.
- Proposal: in `labjegyzet.ts` add an inline parser for `^[` … `]` (balanced brackets, single paragraph) producing `FootnoteInline` with `FootnoteMark` + inline children; LP: treat like `FootnoteReference` in `elo/sorok.ts:381-386` with an auto label (`i1`, `i2`…); Reader: in `olvaso/html.ts:296-312` register the inline body in `o.labjegyzetek` (synthesise a definition node or store a DOM fragment) and number it in order of appearance (`:622-646`).

### 01-rendering-11 — Broader (sanitised) HTML: blocks, attributes, `<img>`, `<details>`, `<span style>` (should, M, high)

- Obsidian: HTML blocks and inline HTML render after DOMPurify sanitising (`<div>`, `<center>`, `<details><summary>`, `<span style="color:…">`, `<font color>`, `<img src width>`, `<a href>`, `<table>`, `<iframe>` from a few video hosts).
- Manifold: 14 attribute-less inline tags (`markdown/html.ts:6-13`); HTML blocks printed raw (`olvaso/html.ts:606-611`); LP ignores `HTMLBlock` (`elo/sorok.ts:253`). The "no innerHTML" rule (`olvaso/html.ts:1-2`, `markdown/html.ts:2-3`) is a security decision to keep.
- Proposal (keeps the rule): parse the HTML text with `DOMParser` (already used for entities, `olvaso/html.ts:329-332`) and copy nodes into a fresh tree through an allow-list walker: block tags `div p span center details summary section figure figcaption table thead tbody tr th td ul ol li blockquote pre code hr h1-h6 img a kbd abbr cite q`; attributes `class title align width height colspan rowspan open start`, `style` restricted to a whitelist of safe properties (`color`, `background-color`, `font-*`, `text-align`, `width`, `margin*`, `padding*`), `href` only through `kulsoJeloles` (`olvaso/html.ts:186-194`), `src` only for vault paths rewritten to `linkek.mediaUrl` (`lib/vault/linkek.svelte.ts:91-94`) or external after 04. Mermaid already ships DOMPurify (`renderelok/mermaid.ts:1-3`), so an alternative is `DOMPurify.sanitize(html, {RETURN_DOM_FRAGMENT: true, ALLOWED_TAGS…})` — this is still not `innerHTML` on the page. Reader: use the walker in `SorIro.html` (`:120-141`) for inline tags with attributes and in `blokk` for `HTMLBlock`; LP: render `HTMLBlock` as a block widget in `elo/blokkok.ts` when not active (new `HtmlWidget` in `elo/widgetek.ts`), and extend `engedettCimke` to carry attributes for inline tags (`elo/sorok.ts:355-380`). Update `app/tests/elo-html.test.ts:12-33` and `szerkeszto-olvaso.test.ts:50`.

### 01-rendering-12 — ⌘F in Reading view (should, S, high)

- Obsidian: Ctrl/Cmd+F opens the find bar in Reading view as well; matches highlighted and navigable.
- Manifold: command disabled in `olvaso` (`index.ts:204`).
- Proposal: in `Olvaso.svelte` add a small find bar (reuse the CodeMirror search-panel styling `szerkeszto.css:513-583`), implement with `TreeWalker` over text nodes + `CSS.highlights` (`::highlight()`; WebKit 17.2+) or wrapped `<mark>`; Enter/⇧Enter cycle, Esc closes; enable `szerkeszto.kereses` for `olvaso` and dispatch to the component through `SzerkesztoPeldany` (`Szerkeszto.svelte:224-251`).

### 01-rendering-13 — Hanging indent for wrapped list lines in LP (should, S, high)

- Obsidian LP: continuation lines of a wrapped list item align under the item text (also for `> ` quotes and `- [ ]` tasks).
- Manifold: `EditorView.lineWrapping` (`beallitas.ts:114`) with no indent decoration, so continuation lines return to the left edge.
- Proposal: in `stilusok()` (`elo/sorok.ts:78-205`) for `ListItem` first lines compute the marker width (indent + `ListMark` + space, tasks + `[ ] `) and emit `Decoration.line` with `style: text-indent: -Nch; padding-left: Nch` (`N` in `ch` of the measured prefix; use `--t-*`-free values, this is content geometry not a token). Same for `cm-idezet` lines (`szerkeszto.css:201-207` already pads; make the padding depth-aware for wrapped text). Reader is fine (`<li>`).

### 01-rendering-14 — Font size / zoom (should, S, high)

- Obsidian: Appearance → Font size (default 16) and ⌘+/⌘−/⌘0 zoom.
- Manifold: fixed tokens (`styles/tokens.css:144-158`, `DESIGN.md:86-91`).
- Proposal: a `felulet.betuMeret` (12–24, default 16) persisted like `szerkesztoMod` (`lib/elrendezes/felulet.svelte.ts:24-47,218-230`); apply as `--betu-torzs` override on `<html>` (headings are already px tokens: express `--betu-h1…h5` as multiples of `--betu-torzs` in `tokens.css:150-154` so they scale); commands "Betűméret: nagyobb/kisebb/alap" in `alapParancsok.ts` with ⌘=/⌘−/⌘0 (check the héj menu does not already bind them). Keep the UI chrome (`--betu-ui`) unscaled, as Obsidian does.

### 01-rendering-15 — Indentation guides (nice, S, high)

- Obsidian: thin vertical lines for nested list levels in LP and Reading (setting, default on).
- Proposal: with the indent data from 13, emit a `background-image: repeating-linear-gradient` per nesting level on list lines (the blockquote already does this, `szerkeszto.css:201-207`); Reader: `.md ul ul`, `.md ol ol` `border-left` from `--keret`. Toggle via `felulet` like 07.

### 01-rendering-16 — Line numbers gutter toggle (nice, S, high)

- Proposal: `lineNumbers()` in a Compartment in `beallitas.ts:105-146` driven by a `felulet.sorszamok` flag (default off, as Obsidian); style the gutter with `--szoveg-halvany` on `--hatter`; keep `.cm-content` centred (the gutter must not shift the 44 rem column; see `szerkeszto.css:34-42`).

### 01-rendering-17 — Strict line breaks toggle (nice, S, high)

- Obsidian: off by default (newline = `<br>`); on = CommonMark (newline ignored).
- Manifold: always `<br>` (`olvaso/html.ts:88-103`, `DESIGN.md:178`).
- Proposal: `felulet.szigoruSortores` flag; `SorIro.szoveg` emits a space instead of `<br>` when set; LP is unaffected (lines are lines). Mention in the setting that embeds/exports follow it.

### 01-rendering-18 — Default view for new tabs: Reading (nice, S, high)

- Proposal: extend `SzerkesztoMod` or add `felulet.alapNezet: 'szerkesztes' | 'olvaso'`; `kezdoMod()` (`Szerkeszto.svelte:58-61`) returns `olvaso` when set and the tab has no own `nezet.mod`; keep `szerkesztoMod` as the editing default.

### 01-rendering-19 — Properties in document: hidden / source (nice, S, high)

- Proposal: `felulet.tulajdonsagokMegjelenes: 'lathato' | 'rejtett' | 'forras'`; `diszites()` (`tulajdonsagok/elo.svelte.ts:72-81`) returns a `Decoration.replace` without widget (hidden) or no decoration (source, raw YAML like Source mode); the Reader panel (`Szerkeszto.svelte:364-374`) follows the same flag.

### 01-rendering-20 — PDF embed `#height=N` (nice, S, high)

- Proposal: extend `mediaHorgony` (`linkek/adat.ts:58-69`) to parse `height=N` (and `page=N&height=N` combos: split on `&`), use it in `media/pdf/beagyazas.ts` and the iframe fallback (`beagyazas/rajzol.ts:276`); keep `|N` as an alias.

### 01-rendering-21 — Reference-style links (nice, S, medium)

- Proposal: in `dokumentumRenderel` (`olvaso/html.ts:650-666`) first collect `LinkReference` nodes (`LinkLabel` → `URL`/`LinkTitle`) into a map on `RenderOpciok`; in `linkSzoveg` (`:196-211`) resolve a `Link` without `URL` child through its `LinkLabel` (or the link text for collapsed references). LP: treat like 08 (hide `[id]`).

### 01-rendering-22 — Unresolved wikilink styling (nice, M, high)

- Proposal: a `ViewPlugin` in `linkek/szerkeszto.ts` that batches the visible `Wikilink` targets to `linkek.feloldas` (`lib/vault/linkek.svelte.ts:104-115`, cached, invalidated by `linkek.verzio` — already dispatched as `linkVerzioValt`, `Szerkeszto.svelte:264-267`) and adds `cm-wikilink-feloldatlan` (lower opacity, dotted underline); Reader: the same lookup after render, toggling a class on `.wikilink[data-cel]`.

### 01-rendering-23 — External link indicator (nice, S, high)

- Proposal: `.md .link[data-url]::after` and `.cm-elonezet .cm-link::after` with the Lucide `ExternalLink`/`ArrowUpRight` mask (the pattern used for error icons, `DESIGN.md:78`), 0.8 em, `--szoveg-halvany`.

### 01-rendering-24 — ```` ```query ```` blocks (nice, M, high)

- Proposal: register a `KodRenderelo` (`renderelok/regiszter.ts:38-49`) `nyelv: 'query'` that calls `GET /api/kereses/hibrid?q=&mod=lexikai` (`ARCHITECTURE.md:312`) and renders the result cards with the search window's markup (`DESIGN.md:222`); `becsultMagassag` ~ 240 px; not `interaktiv` (click = open result; use `ignoreEvent` for links). Works in both views automatically (`elo/blokkok.ts:101-113`, `olvaso/html.ts:494-506`).

### 01-rendering-25 — `cssclasses` frontmatter (nice, S, low on importance)

- Proposal: read `cssclasses` from the properties (`GET /api/vault/jegyzet`, `ARCHITECTURE.md:158`, or `fmBlokk`) and add them to `.szerkeszto` (`Szerkeszto.svelte:326`); only useful once user CSS snippets exist, so low priority.

### 01-rendering-26 — Mid-line note embed as chip (nice, S, medium)

- Obsidian renders an inline embed with the full content; Manifold shows a chip (`beagyazas/rajzol.ts:76-77,282-299`). Proposal: a setting or a size threshold (render inline when the slice is one block); keep the chip for long notes. Verify Obsidian's exact behaviour first.

### 01-rendering-27 — KaTeX coverage vs MathJax (nice, S, medium)

- Proposal: add the KaTeX `mhchem` and `copy-tex` extensions (`katex/contrib`) in `renderelok/katex.ts`, extend `KATEX_MAKROK` as the vault gate (`tests/kezi/kepletek.py`) reports new cases, and show the KaTeX error message as a tooltip on the red fallback (`errorColor`, `katex.ts:34`). Switching to MathJax is not recommended (bundle size, speed); document the known differences in `docs/dev/DESIGN.md` §10.

### 01-rendering-28 — Footnote hover preview (nice, S, low)

- Proposal: reuse the hover-preview popover (`linkek/elonezet.ts`) for `[data-labjegyzet]` elements with the footnote `<li>` content; verify in Obsidian 1.8 before building.

### 01-rendering-29 — Inline title size and toggle (nice, S, high)

- `FajlCim.svelte:43-45` uses `--betu-h2`; Obsidian's inline title is H1-sized and can be hidden. Proposal: `--betu-h1` + `--suly-cim`, plus a `felulet.belsoCim` flag; keep the inline rename (strength).

### 01-rendering-30 — Table editor: rendered cell while editing (nice, M, medium)

- Proposal: replace the `<input>` in `notion/tablazat/szerkeszto.ts` with a one-line nested CodeMirror using `markdownNyelv()` + `stilusPlugin` (both exported from `beallitas.ts:79-81,122`), or keep the input and show a rendered preview below on focus. Low priority; current behaviour is explicit and tested (`app/tests/notion-tablazat.test.ts`).

### 01-rendering-31 — Tables nested in list items fall back to a read-only widget (nice, S, high)

- `elo/blokkok.ts:67-78`: when `TablaSzerkesztoWidget.keszit` cannot parse the indented lines, `TablaWidget` is used (click → source). Proposal: strip the common list prefix before `keszit` and re-add it in `szerializal` (`notion/tablazat/modell.ts`), the same way the `>` prefix is already handled (`DESIGN.md:190`).

---

## 3. Manifold strengths beyond Obsidian — preserve while closing gaps

| Strength | Where | Why it matters |
|---|---|---|
| One parser for editor, Reader and the formula script; Obsidian-faithful rules (math rule identical to the core index, math-aware tables, task state = any single char, L39 frontmatter) | `markdown/elemzo.ts:1-7,18-31`, `markdown/matek.ts:1-9`, `markdown/tablazat.ts:1-6`, `markdown/feladat.ts:1-3`, tests `app/tests/szerkeszto-elemzo.test.ts:74-196` | Rendering can never diverge between views; counts match the index |
| Live KaTeX preview **under** the active `$$` block while typing | `elo/blokkok.ts:86-87`, `elo/widgetek.ts:65-80`, `szerkeszto.css:389-392` | Obsidian shows only the source while editing |
| Copy button and language label on code blocks in **Live Preview** too; the opening fence becomes the header, the closing fence is hidden | `elo/widgetek.ts:386-417`, `elo/blokkok.ts:114-116` | Cleaner than Obsidian's visible fences |
| Visual table editor with row/column handles, menus, alignment and "+" edges; byte-identical when untouched | `notion/tablazat/szerkeszto.ts:1-9`, `DESIGN.md:190` | At or above Obsidian 1.5's table editor |
| Notion layer on plain Markdown: `/` menu, block drag handle with structural moves, floating formatting toolbar | `notion/perjel.ts:1-4`, `notion/blokkfogo.ts:1-5`, `notion/eszkoztar.ts:1-8`, `notion/index.ts:14-16` | Not in Obsidian core |
| Quiet mode ("csend"): chrome fades while typing, everything reachable by hover/⌘P | `lib/elrendezes/csend.svelte.ts:1-5`, `styles/alap.css:233-260` | Obsidian core has no focus mode |
| Image pipeline: width-bucketed downscaled variants (`?w=`), lazy decode, lightbox on click, retina aware | `beagyazas/rajzol.ts:190-234`, `beagyazas/nagyito.ts`, `ARCHITECTURE.md:202`, tests `app/tests/beagyazas.test.ts:136-188` | Faster notes with photos; Obsidian has no lightbox |
| Media anchors: video/audio `#t=` start time, poster frame, PDF embed with an in-note pdf.js viewer (page field, ‹ ›, open) | `beagyazas/rajzol.ts:239-280`, `media/pdf/beagyazas.ts:1-6` | Obsidian core lacks `#t=` and the embedded navigator |
| Extensible renderer registries used by modules: code-block renderers (Mermaid, `plot` JSXGraph interactive, Bases), embed types (canvas, base, PDF, `.cpp` with test badge), note-class embeds (quiz, cards, summary), callout types | `renderelok/regiszter.ts:1-12,51-70`, `beagyazas/regiszter.ts:1-5,37-45`, `renderelok/callout.ts:1-6,80-86`, registrations `index.ts:265-266`, `kod/index.ts:28`, `bazis/index.ts:19-20`, `kviz/index.ts:49`, `kartya/index.ts:62` | Obsidian needs community plugins for all of these |
| Interactive rendered blocks edit their own source in one transaction with in-place DOM update (no scroll/focus loss) | `elo/widgetek.ts:183-270`, `renderelok/regiszter.ts:26-49` | Beyond Obsidian's static code-block post-processors |
| Theme-token Mermaid and plot colours, re-rendered on theme switch; all colours `light-dark()` pairs with a contrast table | `renderelok/mermaid.ts:30-45,74-76`, `renderelok/tema.ts`, `styles/tokens.css:84-108`, `DESIGN.md:53-82` | Obsidian's Mermaid theme is coarser |
| Properties widget in LP with a cursor guard (the caret can never land inside the hidden YAML) and raw-with-error fallback | `tulajdonsagok/elo.svelte.ts:1-7,111-119,72-81`, tests `app/tests/tulajdonsagok-elo.svelte.test.ts:112-157` | Avoids a classic Obsidian frontmatter-corruption path |
| Inline file title that renames the file with link updates | `FajlCim.svelte:11-28` | Obsidian's inline title renames but the link-update plan/preview is Manifold's |
| Reader checkbox write-back guarded against stale positions; Reader ↔ editor scroll sync via `data-from` | `Olvaso.svelte:94-111`, `olvaso/html.ts:650-666` | Robustness |
| Lazy Reader rendering (math, highlighting, renderers only near the viewport), widget height estimates, DOM reuse by `eq` | `olvaso/lusta.ts:1-3,13`, `elo/widgetek.ts:1-2` | Long notes stay smooth |
| Security posture stricter than Obsidian: no `innerHTML` for Markdown, KaTeX `trust:false`, Mermaid strict + DOMPurify, CSP, SVG sandbox on media, external links only via the shell with scheme allow-list | `olvaso/html.ts:1-2`, `renderelok/katex.ts:36`, `renderelok/mermaid.ts:1-3`, `app/index.html:8-9`, `linkek/kulso.ts:1-8` | Keep when widening HTML (gap 11) and images (gap 04) |
| Keyboard/accessibility details in the Reader: footnote links and wikilinks focusable with `role=link`, aria labels on checkboxes and copy buttons | `olvaso/html.ts:270-276,302-309,470-472`, `Olvaso.svelte:87-92` | — |
| Hungarian default callout titles and CodeMirror phrases through one table (ready for the English move) | `renderelok/callout.ts:35-64`, `beallitas.ts:48-76` | — |
| Live outline from the syntax tree in the right panel, updated while typing | `hej/kapcsolatok/Vazlat.svelte:1-4`, `linkek/kiegeszites.ts:171-185` | Equivalent to Obsidian's Outline, no re-parse |

---

## 4. Open questions

1. **External content policy (gaps 04, 11).** Is relaxing `img-src` acceptable for a locked local app, or must every external byte go through a core proxy? The cover-image comment (`tulajdonsagok/Boritokep.svelte:3-4`) suggests the CSP is a deliberate decision; the answer also decides `<iframe>` (YouTube) support, which Obsidian allows and this audit left out of the proposals.
2. **Core resolution of path-style targets (gaps 03, 09).** Does `GET /api/vault/beagyazas` / `POST /api/vault/feloldas` accept a relative path with extension (`attachments/a.png`, `../Other.md`, URL-encoded) as `cel`, resolved from the source note's folder first and then by the Obsidian shortest-path rule? If not, a small core change is needed before the UI work.
3. **Markdown links in the index.** Does `core/index/linkek.py` count `[t](Note.md)` as a link (backlinks, rename plan, graph)? If not, gap 09 only fixes navigation and the index needs the same rule.
4. **`%%manifold-kiemeles …%%` marker lines (gap 01).** Hiding every `%%` comment in the Reader also hides the PDF-highlight marker lines, which is probably desired; confirm with the C16/C29.7a owner, and decide whether LP should keep them visible (muted) or special-case them.
5. **Folding persistence (gaps 05/06).** Obsidian stores fold state per file in `workspace.json`. `Ful.nezet` is capped at 2 KB (`ARCHITECTURE.md:196`); is a per-file fold list acceptable there, or should the core hold it (`GET/PUT /api/felulet/allapot`)?
6. **Inline tags vs the AI01 `Tags` property (gap 02).** The protocol keeps tags in frontmatter; should body tags also feed the core index (`GET /api/vault/cimkek`) or only render and search?
7. **Settings surface.** Gaps 07, 14, 15, 16, 17, 18, 19 each add a `felulet.json` flag and a ⌘P command; `03-felulet.md:186-247` notes there is no settings system yet. Should these wait for the Settings page, or ship as ⌘P toggles first (the existing pattern for theme and quiet mode)?
8. **Math engine.** Stay on KaTeX (with `mhchem`) and document differences, or evaluate MathJax 4 for full Obsidian fidelity at the cost of bundle size and speed?
9. **Low-confidence Obsidian details to verify before building:** Obsidian LP copy button presence (B13), autolink bracket hiding in LP (gap 08), footnote hover preview (gap 28), mid-line note embed rendering (gap 26), reference-style link support (gap 21).
