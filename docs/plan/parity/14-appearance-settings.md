# 14 — Appearance and Settings: Obsidian parity audit

**Subsystem:** the Settings window (sections, search, save model), the Appearance controls (theme, fonts, font size, zoom, line width, table and code-block look), spellcheck, language, startup behaviour, file exclusions and settings portability.
**Reference:** Obsidian 1.8/1.9 desktop, core only (Settings, Appearance, Editor, Files & links, Hotkeys, Core plugins, Community plugins). Obsidian behaviour was taken from the official help pages (`obsidian.md/help/appearance`, `obsidian.md/help/settings`, fetched 2026-10-17) and paraphrased. The help pages do not list every option (font families, font size, quick font size adjustment, inline title, translucency and similar were confirmed from the Settings page's section summary or from memory). Rows resting on memory carry `confidence: low` or `medium`, and no **must** rests on them.
**Code read** (paths relative to the repository root): `app/src/beallitasok/{Beallitasok.svelte,allapot.svelte.ts,index.ts}`, `app/src/lib/beallitasok/{allapot.svelte.ts,tipusok.ts}`, `app/src/App.svelte`, `app/src/main.ts`, `app/src/alapParancsok.ts`, `app/src/hej/Hej.svelte`, `app/src/lib/elrendezes/{tema.ts,nagyitas.ts,felulet.svelte.ts}`, `app/src/lib/i18n/{nyelv.svelte.ts,en/beallitasok.json}`, `app/src/lib/munkater/nyelv.svelte.ts`, `app/src/styles/{tokens.css,alap.css}`, `app/src/szerkeszto/{beallitas.ts,szerkeszto.css,megjelenites.css,Szerkeszto.svelte,FajlCim.svelte}`, `app/src/szerkeszto/notion/tablazat/szerkeszto.ts`, `app/src/kod/szerkeszto.ts`, `app/src/hej/Fa.svelte`; core: `core/termek_beallitasok.py`, `core/importalas.py`, `core/indito.py`; shell: `shell/Sources/{AppController.swift,InditoAblak.swift,HelyiMenu.swift}`; tests: `app/tests/{beallitasok.svelte.test.ts,beallitasok-app.svelte.test.ts,szerkeszto-beallitasok.test.ts,f11-betumeret.test.ts,tokenek.test.ts,kontraszt.test.ts,csend.test.ts}`. Reference documents: `docs/PLAN.md:208-226` (§11), `docs/plan/f5/F5-DESIGN.md`, `docs/plan/NAPLO.md` (F5, F7), `docs/plan/parity/{05-editing,06-workspace,07-explorer}.md`.

**Legend.** Status: *present* / *partial* / *missing* / *ahead* (Manifold is stronger than Obsidian) / *deviation* (intentional, see section 4; not a gap) / *non-goal* (Obsidian feature Manifold deliberately does not offer). Weight: **must** = a daily Obsidian habit whose absence blocks switching or breaks a product rule; **should** = clearly noticeable, with no equivalent workaround; **could** = polish or optional. (`docs/plan/f11/DESIGN.md` gives no separate must/should definition; this is the definition used by the 07 audit.) Size: S (<1 day), M (1-3 days), L (>3 days). Gap ids `14-appearance-NN` point to section 2.

**Overall picture.** Settings and Appearance are the most complete area audited so far. F5 delivered a real Settings window with the Obsidian section structure, a revisioned conflict-safe store, shortcuts, modules and the privacy and developer groups; F7 added the privacy and developer sections. Theme (system, light, dark), editor font size, UI zoom, readable line length, spellcheck, tab size, startup choice and the Obsidian `appearance.json` import are all present and tested. The remaining gaps are narrow: **no font-family choice** (the only route to it in Obsidian, apart from themes, is CSS, which Manifold deliberately does not offer), a spellcheck toggle that does not reach table-cell inputs, no auto-pair toggles, and unenforced file exclusions even though PLAN §11 lists them. There is no **must**, five **should** gaps and thirteen **could** gaps. Themes, CSS snippets, accent colour and community plugins are deliberate deviations, not gaps.

---

## 1. Checklist

### A. Appearance

| # | Obsidian behaviour | Manifold today (path:line) | Status | Weight | Size | Confidence | Gap |
|---|---|---|---|---|---|---|---|
| 1 | Base colour scheme: System / Light / Dark, default follows the OS | `megjelenes.tema` `tipusok.ts:11`, select `Beallitasok.svelte:140`; applied `App.svelte:117-118` → `tema.ts:9-14` (`data-tema`; system removes the attribute and `color-scheme: light dark` follows the OS, `tokens.css:10,228-234`) | present | – | – | high | – |
| 2 | The native window chrome follows the scheme | `hejnek({tipus:'tema'})` → `AppController.swift:489-495` (`NSApp.appearance` aqua / darkAqua / nil) | present | – | – | high | – |
| 3 | No wrong-theme flash at startup | `main.ts:22` applies the saved theme before first paint; the shared settings value is applied again after load (`App.svelte:110-125`) | present | – | – | medium (no visual check made) | – |
| 4 | Switch scheme from the command palette | theme commands `alapParancsok.ts:48-62` persist through the same settings API (`beallitasok.svelte.test.ts:179-199`) | present | – | – | high | – |
| 5 | Accent colour (picker, Reset) | fixed burgundy; Settings says so (`Beallitasok.svelte:143`, `en/beallitasok.json:78`); accent never marks state (`tokens.css:33-43`) | deviation | – | – | high | – (section 4) |
| 6 | Community themes: browse, install, switch | none; `.obsidian/themes` is copied by the importer but not applied; import flags unsupported appearance keys as `nem_tamogatott` (`importalas.py:641-644`) | deviation | – | – | high | – (section 4) |
| 7 | CSS snippets (enable, reload, open folder) | none; the token guard forbids component-level literals (`tokenek.test.ts:115-170`) | deviation | – | – | high | – (section 4) |
| 8 | Interface font | fixed token `--betu-rendszer` (`tokens.css:142`); no setting; `App.svelte:119` sets only `--betu-torzs` | missing | could | S | high | 03 |
| 9 | Text font (note body in editor and reading view) | the same token is used for note text (`szerkeszto.css:16`); no separate note-font token and no setting | missing | should | M | high | 01 |
| 10 | Monospace font (code blocks, inline code, Source mode) | fixed `--betu-mono` (`tokens.css:143`, used at `szerkeszto.css:140,327,428,448,722`); no setting | missing | should | S | high | 02 |
| 11 | Base font size slider (10-30 px) | `megjelenes.betumeret`, number input 12-28 (`Beallitasok.svelte:141`; range checked in the UI `:71` and the core `termek_beallitasok.py:97`); sets `--betu-torzs` (`App.svelte:119`); headings scale with it, chrome stays fixed (`megjelenites.css:6-14`, `f11-betumeret.test.ts`) | present (range and control differ) | could | S | low (Obsidian's exact range from memory) | 08 |
| 12 | Quick font size adjustment (Ctrl + scroll in the editor) | none; ⌘= / ⌘- change UI zoom, not font size | missing | could | S | low | 08 |
| 13 | Zoom level (Appearance slider, plus ⌘= ⌘- ⌘0) | `nezet.nagyit` ⌘= / ⌘- / ⌘0 `alapParancsok.ts:190-192`, CSS `zoom` on the root `nagyitas.ts:4-8`, range 0.8-1.6 `felulet.svelte.ts:19`, persisted in `var/state/felulet.json`, applied `Hej.svelte:32`. No control or readout in Settings (`nagyitasSzazalek` `nagyitas.ts:10` has no caller) | present (no readout) | could | S | high | 07 |
| 14 | Readable line length toggle | `szerkeszto.olvashato_szelesseg` `Beallitasok.svelte:126`; live in the editor and reading view (`beallitas.ts:53`, `szerkeszto.css:36-54`, `szerkeszto-beallitasok.test.ts:46`); width fixed at `--olvasasi-szelesseg: 44rem` (`tokens.css:170`) | present | – | – | high | – |
| 15 | Line width value | core Obsidian has only the toggle; the width itself is changed by theme CSS or a plugin. Manifold has one token value | missing (non-core in Obsidian) | could | S | medium | 09 |
| 16 | Show inline title / show tab title bar | the file title input is always rendered (`Szerkeszto.svelte:422`, `FajlCim.svelte`); tab bar always shown | missing | could | S | medium | 10 |
| 17 | Ribbon (show, configure) | covered by `06-workspace-12`; not duplicated | present elsewhere | – | – | high | – |
| 18 | Native menus, window frame style, hardware acceleration, translucency, custom app icon (Advanced) | the macOS shell always uses native menus and chrome (`AppController.swift`); the rest has no equivalent and no user need on a native WKWebView app | deviation | – | – | medium | – (section 4) |
| 19 | Table appearance | no Obsidian setting (theme-level). Tables are styled from tokens: `szerkeszto.css:483-495`; interactive table widget `notion.css:297-455` | ahead (token-based, mode-consistent) | – | – | high | – |
| 20 | Code-block appearance and syntax colours | no Obsidian setting (theme-level). Code colours are `--kod-*` tokens in both schemes (`tokens.css:85-91`), shared by blocks, YAML and the code workbench (`szerkeszto.css:374-396`) | ahead | – | – | high | – |
| 21 | Appearance changes apply immediately | Settings uses a draft with Save and a discard prompt (`Beallitasok.svelte:34,68-78,194`); the theme command applies at once. The two paths differ | partial | could | S | medium | 11 |
| 22 | Reduced motion / contrast | `prefers-reduced-motion` zeroes all durations (`tokens.css:236-243`); WCAG AA contrast of every token pair in both schemes (`kontraszt.test.ts:86`). No Obsidian equivalent | ahead | – | – | high | – |

### B. Settings structure

| # | Obsidian behaviour | Manifold today (path:line) | Status | Weight | Size | Confidence | Gap |
|---|---|---|---|---|---|---|---|
| 23 | Settings opens with ⌘, and from the app menu and the palette | `beallitasok.megnyit` `index.ts:7` (`Mod+,`); every section also has a palette command (`index.ts:8`); native menu item (F5 gate, `06-workspace-27`) | present | – | – | high | – |
| 24 | Sidebar of sections: General, Editor, Files and links, Appearance, Hotkeys, Core plugins, Community plugins, About | `SZAKASZOK` `allapot.svelte.ts:3-36`: Options group (General, Editor, Files & links, Appearance, Hotkeys, Modules), AI, Learning, Backup, Privacy, About, Developer (hidden unless Developer mode, `:28-34,38-39`). Matches PLAN §11 (`PLAN.md:215`) | present (superset) | – | – | high | – |
| 25 | A search box over all settings | Obsidian has none over the whole dialog (only inside Hotkeys, Core plugins and Installed plugins) — confidence medium. Manifold has the Hotkeys filter (`Beallitasok.svelte:149`) but no filter for the 26-item Modules list | partial | could | S | medium | 13 |
| 26 | Hotkeys: list, search, assign, remove, conflict warning, reset | `Beallitasok.svelte:147-154`: filter, capture, Backspace clears, per-command reset, conflict and reserved-key errors (`billentyu-utkozes.test.ts`, `beallitasok.svelte.test.ts:162-179`); `06-workspace-20` verified | present | – | – | high | – |
| 27 | Core plugins: enable or disable, search | Modules section: 26 toggles that really gate palette, keys and views, data preserved (`Beallitasok.svelte:144-146`, `beallitasok.svelte.test.ts:148-161`) | present (no filter, gap 13) | – | – | high | – |
| 28 | Community plugins and Restricted mode | none by design; the Obsidian importer reports installed or enabled community plugins as unsupported (`importalas.py:673-679,778`) | non-goal | – | – | high | – (section 4) |
| 29 | About: version, updates, credits | About section with build details (`Beallitasok.svelte:168-173`); update checks belong to F9 and are not duplicated | present | – | – | medium | – |
| 30 | Edits saved safely, conflicts handled | revisioned PUT with SHA-256 revision, 409 on conflict, `.toml.elozo` backup (`termek_beallitasok.py:260-300`), unsaved-draft prompt, focus trap, WS refresh (`beallitasok.svelte.test.ts:36-146`) | ahead | – | – | high | – |
| 31 | Privacy and developer groups | F7: Network, Telemetry, Data, Integrations, Permissions and Developer sections (`allapot.svelte.ts:27-40`); verified as present, not re-audited here | present | – | – | high | – |

### C. Editor and Files & links settings that touch the look and feel

| # | Obsidian behaviour | Manifold today (path:line) | Status | Weight | Size | Confidence | Gap |
|---|---|---|---|---|---|---|---|
| 32 | Default editing mode: Live Preview or Source | `szerkeszto.mod` `Beallitasok.svelte:125` | present | – | – | high | – |
| 33 | Default view for new tabs: editing or **reading** | no Reading option; reading is a per-note toggle | missing | could | S | high | 15 |
| 34 | Spellcheck toggle | `szerkeszto.helyesiras` `Beallitasok.svelte:127` → `beallitas.ts:52` (live, tested `szerkeszto-beallitasok.test.ts:46`). Language is automatic from macOS (the native menu offers suggestions and Learn Spelling, `HelyiMenu.swift:3-6`) | present | – | – | high | – |
| 35 | Spellcheck in every text area when on, none when off | the table-cell editor forces `input.spellcheck = true` regardless of the setting (`notion/tablazat/szerkeszto.ts:368`); no other `spellcheck` reference in the editor tree is `true` | partial | should | S | high | 04 |
| 36 | Tab size and indent with tabs or spaces | tab width 1-8 `Beallitasok.svelte:128`; indent unit fixed to a tab (`beallitas.ts:144`); no spaces option | partial | could | S | medium | 16 |
| 37 | Auto-pair brackets and Markdown syntax (two toggles) | always on (`closeBrackets()`, `autoParokBovitmeny()` `beallitas.ts:135-137`); no setting | missing | should | S | high | 05 |
| 38 | Line numbers, indentation guides, RTL, strict line breaks, show frontmatter | none in the note editor (line numbers exist only in the code workbench, `kod/szerkeszto.ts:90`) | missing | could | S each | medium / low | 14, 16 |
| 39 | New-note location, attachment folder, link format, wikilinks on or off | `Beallitasok.svelte:130-138` (`uj_mappa`, `csatolmany_mappa`, link format, wikilinks); location honoured by Cmd+N (`07-explorer-10` verified) | present | – | – | high | – |
| 40 | Automatically update internal links on rename | always on, with a plan and undo (`07-explorer` section 3) | deviation | – | – | high | – |
| 41 | Deleted files: system trash / `.trash` / permanent; confirm deletion | the Settings page shows one sentence (`en/beallitasok.json:71`: system Trash); always confirms (`07-explorer-20` is the code-side gap, nice) | deviation (data-safety) | – | – | high | – |
| 42 | **Excluded files** (`userIgnoreFilters`) hide files from search, graph, quick switcher, unlinked mentions | no setting and no enforcement (`grep userIgnoreFilters` finds only the 07 audit). PLAN §11 lists "excluded files" under Files & links (`PLAN.md:215`). The Settings copy says "Existing exclusion rules are preserved" (`en/beallitasok.json:71`) although they are only copied, not applied | missing | should | M | medium (tree behaviour; see 07-explorer-13) | 06 |
| 43 | Detect all file extensions | read from the vault's `app.json` (`fajlok.mindenKiterjesztes`) and toggled in the tree (`Fa.svelte:37-39,482`, command `fa.minden-fajl` `alapParancsok.ts:186`); no Settings control | partial | could | S | high | 12 |
| 44 | Config folder override, URI callbacks, rebuild vault cache | `.manifold` is fixed by design; rebuild lives in Health (F7) | non-goal / elsewhere | – | – | medium | – |

### D. Language, startup, portability

| # | Obsidian behaviour | Manifold today (path:line) | Status | Weight | Size | Confidence | Gap |
|---|---|---|---|---|---|---|---|
| 45 | Interface language | English only in the first release (PLAN P2); `NYELVEK = ['hu','en']` exists but `hu` is an identity dictionary and no UI selects it (`nyelv.svelte.ts:9-12,35-40`). The Settings "Language" row is a **content-language hint** for templates and generated text (`en/beallitasok.json:42,46`, `termek_beallitasok.py:276`) | deviation (v1) | could | M | high | 18 |
| 46 | Startup: reopen the last vault or show the vault manager | `altalanos.inditas` (`utolso` / `valaszto`) is read by the launcher (`indito.py:81-87`, `InditoAblak.swift:159`); tabs and layout restore from `felulet.json` | present | – | – | high | – |
| 47 | Settings travel with the vault | product mode: `<vault>/.manifold/workspace.toml`; portable mode: install `settings.toml` (`termek_beallitasok.py:116-124`, `ARCHITECTURE.md:195`). Device-local state (zoom, sidebar, sort, open folders) is in `var/state/felulet.json` and does not travel (like Obsidian's per-device workspace) | present | – | – | high | – |
| 48 | Import another vault's appearance and editor settings | Obsidian importer maps `theme`, `baseFontSize`, readable line length, spellcheck, tab size, live preview and link format (`importalas.py:150-159`), reports every other key as not carried over (`:641-644`), reports `hotkeys.json` as unsupported (`:660-661`) | present (hotkeys not mapped, gap 17) | could | M | high | 17 |
| 49 | Copy settings to another vault or machine | copying `workspace.toml` is blocked by the identity check (`beallitas.munkater_csere`, `termek_beallitasok.py:54,121`); no export or import of a settings profile | missing | could | M | low | 19 |

---

## 2. Gaps and proposals

All proposals keep the layering: the UI never reads the filesystem, settings are written only through `PUT /api/beallitasok`, new settings are added to `Beallitasok` (`tipusok.ts`), `ALAP` and the validators in `core/termek_beallitasok.py`, and every visual value goes through a token.

### 14-appearance-01 — Text font (should, M, high)
**Obsidian.** Appearance → Fonts → Text font: a user-chosen font family for note text.
**Manifold.** One token, `--betu-rendszer`, serves chrome and notes (`tokens.css:142`, `szerkeszto.css:16`). The importer reports the Obsidian font keys as not carried over. Because themes and snippets are deliberately absent, a setting is the only way to change the note font.
**Proposal.** Add `megjelenes.betu_szoveg` (string, `''` = default). Add a new token `--betu-jegyzet: var(--betu-rendszer)` used by the editor, reading view and embeds, and override it from `App.svelte:119` the way `--betu-torzs` is set. Core validation: at most 120 characters, family names only (letters, digits, space, hyphen, quotes, comma); reject `;{}()\\` and `url`, so no network or injected CSS. Offer the installed families through a small shell bridge call (`NSFontManager.availableFontFamilies`) or fall back to free text with the default as fallback. Tests: validator, token override, `tokenek.test.ts` stays green (no literal font in components).

### 14-appearance-02 — Monospace font (should, S after 01, high)
**Obsidian.** Appearance → Fonts → Monospace font (code blocks, inline code, Source mode).
**Manifold.** Fixed `--betu-mono` (`tokens.css:143`).
**Proposal.** `megjelenes.betu_mono`, same validation and runtime override of `--betu-mono`. The code workbench inherits it. A numerals and tabular alignment check belongs in the test (monospace for tables of numbers).

### 14-appearance-03 — Interface font (could, S, high)
**Proposal.** `megjelenes.betu_ui` overriding `--betu-rendszer` for chrome only; default stays the system font. Low value on macOS (system font is the norm), so it follows 01 and 02.

### 14-appearance-04 — Spellcheck setting reaches table-cell inputs (should, S, high)
**Obsidian.** Turning spellcheck off disables it in the editor, including table cells.
**Manifold.** The setting reaches the CodeMirror content (`beallitas.ts:52`) but the table-cell input sets `input.spellcheck = true` unconditionally (`notion/tablazat/szerkeszto.ts:368`). A user who turned spellcheck off still gets red underlines in tables.
**Proposal.** Use `this.view.contentDOM.spellcheck` (already a live attribute) when creating the input, so one setting governs both. Test: extend `szerkeszto-beallitasok.test.ts` with a table-cell editor opened after `helyesiras = false`. Other bespoke inputs (property values, the file title) default to the browser behaviour; check them in the same change.

### 14-appearance-05 — Auto-pair toggles (should, S, high)
**Obsidian.** Editor → Auto pair brackets and Auto pair Markdown syntax, both switchable.
**Manifold.** `closeBrackets()` and `autoParokBovitmeny()` are unconditional (`beallitas.ts:135-137`). The tracking of generated closing characters is a strength (F11 checkpoint 1), but there is no way to turn it off.
**Proposal.** `szerkeszto.auto_par_zarojel` and `szerkeszto.auto_par_jeloles` (default true), applied through the existing `opciokKapcsolo` compartment (`beallitas.ts:46-56`) so toggling reconfigures live without touching the document or undo history, as `szerkesztoOpciok` already does for the other options.

### 14-appearance-06 — Excluded files (should, M, medium)
**Obsidian.** Files & links → Excluded files: path prefixes or patterns hidden from search, graph view, quick switcher and unlinked mentions (the file tree behaviour is the open question in `07-explorer` question 6).
**Manifold.** Not honoured. The index has only fixed skips (`feloldas.py:38`, `indexelo.py:63-67`). PLAN §11 promises the setting. Vaults imported from Obsidian arrive with `userIgnoreFilters` in `app.json`, and the Settings copy says exclusion rules are "preserved", which a user can read as "applied". Excluded notes also feed the assistant and similarity features.
**Proposal.** Core: read `userIgnoreFilters` (prefix or `/regex/`, bounded count and length) into `fajlok.kizart` (list of strings) in `termek_beallitasok.py`, validated like other path settings. The indexer marks matching files `kizart`; search, quick switcher, graph, unlinked mentions and the AI context builders skip them; the tree dims them (the 07-13 suggestion). Settings: a list editor under Files & links with add and remove and a live count of matched files. Until it is enforced, reword `kuka_leiras` so it does not imply enforcement. Requires coordination with the 08-search owner.

### 14-appearance-07 — Zoom readout and control in Appearance (could, S, high)
**Manifold.** ⌘= / ⌘- / ⌘0 work and persist, but nothing shows the current factor and Settings has no control. `nagyitasSzazalek` (`nagyitas.ts:10`) is unused.
**Proposal.** An Appearance row "Interface zoom" with the percentage and − / + / Reset buttons calling `felulet.nagyit` (`alapParancsok.ts:190-192`). Not part of the Save draft: zoom is device-local state, so the row applies immediately and says so.

### 14-appearance-08 — Font-size ergonomics (could, S, low)
**Obsidian.** A slider (about 10-30 px) in Appearance and a Ctrl + scroll quick adjustment; both from memory.
**Manifold.** A 12-28 number input and no live value.
**Proposal.** Replace the number input by a range slider with the live value and a Reset; widen the range to 10-30 in the UI check (`Beallitasok.svelte:71`) and the core (`termek_beallitasok.py:97`) after confirming the heading-scale test (`f11-betumeret.test.ts`) still holds at 10. Optional ⌘ + scroll in the editor only, behind a setting.

### 14-appearance-09 — Reading-width steps (could, S, medium)
**Proposal.** `szerkeszto.szelesseg: 'keskeny'|'alap'|'szeles'` (narrow 40rem, default 44rem, wide 56rem) mapped to token values (`--olvasasi-szelesseg-*` in `tokens.css`), set on the editor root next to `data-olvashato-szelesseg` (`beallitas.ts:53`). Keep the existing boolean as "off". Obsidian core has only the toggle, so this is above parity and could be dropped.

### 14-appearance-10 — Show inline title (could, S, medium)
**Proposal.** `megjelenes.cim_sor` (default true) gating `FajlCim` (`Szerkeszto.svelte:422`). The file title is also the rename control (`FajlCim.svelte:12-29`), so hiding it must leave the rename command (F2) and tab rename available.

### 14-appearance-11 — Live apply of appearance changes in the dialog (could, S, medium)
**Obsidian.** Appearance changes take effect immediately.
**Manifold.** Theme and font size change only after Save, while the palette command applies at once. Users comparing themes must save each time.
**Proposal.** While the Settings dialog is open, apply `vazlat.megjelenes` as a preview (theme, size, fonts) and revert in `elvetMegsem` or on discard; Save keeps the current atomic path. The draft, discard prompt and conflict handling stay unchanged.

### 14-appearance-12 — "Detect all file extensions" in Settings (could, S, high)
**Proposal.** Show the vault-level flag (and the device override `felulet.oldalsav.mindenFajl`, `Fa.svelte:37-39`) as a toggle under Files & links with a note on which source wins. No new storage.

### 14-appearance-13 — Filter box for the Modules list (could, S, medium)
**Proposal.** An input above the 26 toggles (`Beallitasok.svelte:144-146`) reusing the label list `MODUL_NEVEK`, as the Hotkeys filter does (`:149`). Obsidian filters its core-plugin list the same way. A dialog-wide search is not an Obsidian feature and is not proposed.

### 14-appearance-14 — Line numbers in the note editor (could, S, medium)
**Proposal.** `szerkeszto.sorszamok` (default false) using CodeMirror `lineNumbers()` in the options compartment, as the code workbench already does (`kod/szerkeszto.ts:90`). Live Preview hides syntax, so numbers may be shown for Source mode only; decide with 05-editing.

### 14-appearance-15 — Default view "Reading" for new tabs (could, S, high)
**Proposal.** Extend `szerkeszto.mod` to `'elo'|'forras'|'olvaso'` (or a separate `uj_ful_mod`), applied where a note opens in a new tab (`felulet.szerkesztoMod`, `App.svelte:122`). The reading mode already exists.

### 14-appearance-16 — Remaining Editor display toggles (could, S each, low)
Indentation guides, RTL text, strict line breaks, show frontmatter, indent with spaces. Strict line breaks changes how an imported note renders and is currently reported as not carried over; confirm the default against `01-rendering` before adding. Indent unit is fixed to a tab (`beallitas.ts:144`).

### 14-appearance-17 — Import Obsidian hotkeys (could, M, high)
**Manifold.** `hotkeys.json` is copied and reported as unsupported (`importalas.py:650-651`).
**Proposal.** Map the small set of core command ids that have a Manifold counterpart (quick switcher, palette, new note, search, toggle mode) into `billentyuk`, validated by `regiszter.billentyuketEllenoriz`; list the unmapped ones in the import report. Low value until users complain; Obsidian ids differ from Manifold ids.

### 14-appearance-18 — Interface language selector (could, M, high)
**Status.** Decided out of scope for the first release (PLAN P2, F5 design: "UI stays English"); the content-language hint (`altalanos.nyelv`) must not be confused with it.
**Proposal for later.** Expose `NYELVEK` (`nyelv.svelte.ts:9`) as a General row once a full `hu` dictionary exists (many Settings keys are ids such as `beallitasok.cim`, so the identity `hu` dictionary would show raw ids). Not counted as a defect.

### 14-appearance-19 — Settings profile export and import (could, M, low)
**Proposal.** Export the non-identity part of `Beallitasok` (appearance, editor, files, shortcuts, modules; no workspace id, no paths, no privacy grants) to a JSON file and import it through `PUT /api/beallitasok` with the same validation. Useful when moving between machines; Obsidian users rely on copying `.obsidian`, which Manifold's identity check intentionally blocks for `workspace.toml`.

---

## 3. Where Manifold is already ahead of Obsidian (keep)

1. **Settings store.** Revisioned, locked, atomic writes with a recoverable `.toml.elozo` copy, a 409 conflict flow, a draft with a discard prompt, WS refresh that never overwrites an open draft (`termek_beallitasok.py:260-300`, `beallitasok.svelte.test.ts:36-146`). Obsidian writes JSON files without conflict detection.
2. **Token-only visual system.** One `tokens.css`, `light-dark()` pairs, a guard that rejects literals and unknown tokens (`tokenek.test.ts`), and WCAG AA checks for every foreground and background pair in both schemes (`kontraszt.test.ts:86`). Themes cannot silently break contrast.
3. **Quiet mode.** One switch that fades chrome while typing and never hides error, unsaved or disconnected indicators (`csend.test.ts`, `tokens.css:216-218`). Obsidian has no equivalent.
4. **Errors never rely on colour.** Accent and error are both red-family; every error carries an icon and words (`tokens.css:72-74`).
5. **Heading scale tied to the font size** while the chrome stays on the 4 px grid (`megjelenites.css:6-14`, `f11-betumeret.test.ts`).
6. **Native window follows the theme** through the shell bridge, plus a launcher with its own Appearance choice (`AppController.swift:489-495`, `PLAN.md:210`).
7. **Modules really gate features.** Disabling a module blocks palette, keys and direct invocation while preserving data (`beallitasok.svelte.test.ts:148-161`); Obsidian core plugins are on or off per feature without a data guarantee.
8. **Import transparency.** Every unmapped `.obsidian/*.json` key and every unsupported plugin is listed in the preview (`importalas.py:641-679,778`).
9. **Reduced motion honoured globally** (`tokens.css:236-243`).
10. **Shortcut capture validation.** Modifier required, reserved keys protected, conflicts named before Save (`Beallitasok.svelte:84-94`).

## 4. Intentional deviations and non-goals (not gaps)

| Obsidian feature | Manifold decision | Why |
|---|---|---|
| Accent colour picker | Burgundy is the single accent; Settings states it (`Beallitasok.svelte:143`) | CLAUDE.md design rule; the accent never signals state |
| Community themes and CSS snippets | Not offered; token overrides only through the typed settings above | Tokens-only guard (`tokenek.test.ts`), contrast guarantee, no remote code or assets (D3) |
| Community plugins and Restricted mode | Non-goal; the importer warns when a vault depends on them | Sandboxed execution rule; first-party modules replace core plugins |
| Syntax-highlight themes, per-element colours | One `--kod-*` token set for both schemes | Same as themes |
| Native menus, window frame, translucency, hardware acceleration, custom app icon | Native macOS shell, no switches | A fixed native shell has no equivalent choice |
| Automatically update links on rename (toggle) | Always on, planned and undoable | Data safety (07 audit, section 3) |
| Deleted-files target (permanent delete, `.trash`) and "confirm deletion" toggle | System Trash only, always confirmed | Trash instead of delete (CLAUDE.md data safety); 07-explorer-20 tracks the code side |
| Interface language | English only in v1 | PLAN P2; see 14-appearance-18 |
| Config folder override, URI callbacks | `.manifold` fixed; no URI callbacks | Workspace identity and path-root immutability (F5 design) |

## 5. Open questions

1. **Font families.** Is a bridge call listing installed families acceptable, or should the first version take free text with validation only? A list is friendlier; free text needs no shell change.
2. **Excluded files in the tree.** Does Obsidian dim or hide excluded files in the file explorer (`07-explorer` question 6)? The answer decides the tree part of 14-appearance-06.
3. **Zoom versus font size.** Obsidian's Appearance has both a font size and a zoom factor; Manifold has both but only font size in Settings. Should zoom stay a device-local state outside the Save draft (proposed in 07)?
4. **Font-size range.** Confirm Obsidian's real slider bounds and Ctrl + scroll behaviour on a current install before widening the range (14-appearance-08).
5. **Settings search.** Confirm that no global settings search exists in Obsidian 1.9; `06-workspace-27` records one in the dialog, the help page does not.
6. **Strict line breaks default** (14-appearance-16): coordinate with `01-rendering`.

## 6. Verification notes

- Every "missing" row was checked against the code: no `fontFamily` / `betu_szoveg` settings (grep of `app/src`, `core`), no `userIgnoreFilters` consumer, no `lineNumbers` outside `app/src/kod/`, no `strictLineBreaks`, `trashOption`, `defaultViewMode` consumer, no `nagyitasSzazalek` caller, no Settings control for `showUnsupportedFiles`.
- Refuted candidate gaps: startup choice (consumed by the launcher, `indito.py:81-87`), spellcheck language (macOS automatic with native suggestions, `HelyiMenu.swift:3-6`), zoom (shipped, `06-workspace-28`), theme apply before first paint (`main.ts:22`), Obsidian appearance import (`importalas.py:150-159`), hotkeys UI (`Beallitasok.svelte:147-154`).
- No visual inspection was made; theme and contrast claims rest on the token and contrast tests.
