# 12 — Templates, daily notes, note composer: Obsidian parity audit

**Subsystem:** Templates (folder, variables, insert), Daily notes (path, template, open, navigation), Note composer (merge / extract), Unique note creator, Random note, and the `/` "Template…" entry point.
**Reference:** Obsidian desktop 1.8–1.12 core plugins as documented on the official help site (Templates, Daily notes, Note composer, Unique note, Random note), read 2026-10-17. Where the help page is silent and the behaviour comes from memory or the community, the row carries `confidence: medium/low`; no *must* rests on such a claim.
**Code read** (paths from the repo root): `core/sablon.py`, `core/naplo.py`, `core/ma.py`, `core/workspace.py:288-320`, `core/importalas.py:160-175,636-660`, `core/termek_beallitasok.py`, `config/os.toml:208-224`, `app/src/ma/{index,naplo,sablon,sablonUj,SablonValaszto,Ma}.*`, `app/src/szerkeszto/notion/{sablonok,perjel}.ts`, `app/src/beallitasok/Beallitasok.svelte`, `app/src/lib/elrendezes/ikonsav.ts`, `app/src/hej/nezetek/UjFul.svelte`; tests `tests/test_sablon.py`, `tests/test_naplo.py`, `tests/test_ma_api.py`, `tests/migracio/test_obsidian_import.py`, `app/tests/ma-naplo.test.ts`, `app/tests/ma-sablon-*.test.ts`. The F11 NAPLO checkpoints contain no daily-note-specific work; the daily/template stack is the C15/C32b delivery plus the F5 settings wiring (`docs/plan/NAPLO.md:162-163`).
**Not duplicated here:** ribbon icons for daily note / insert template (06-workspace-12, `06-workspace.md` S1), the `/` menu as a whole (05-editing-14, `05-editing.md` #35), ⌘N and new-note location (06-workspace-06, 07-explorer-10), hotkey customisation (05-editing-05, F5).

**Legend.** Status: *present* / *partial* / *missing* / *ahead* (Manifold exceeds Obsidian) / *n.a.* (not Obsidian core). Priority: **must** = daily Obsidian habit users miss immediately, or a silent wrong result; **should** = noticeable; **could** = polish or rarely used core plugin. Size: S < 1 day, M 1–3 days, L > 3 days. Gap IDs `12-templates-NN` point to chapter 2. (`docs/plan/f11/DESIGN.md` contains no must/should definition; this file uses the same severity wording as audits 05–07.)

**Overall.** The template engine and the daily note are already well built: one evaluator (`core/sablon.py`) shared by insert, new-from-template and daily creation; atomic creation through `Vault.create`; frontmatter merge on insert; a one-step undo; an Obsidian-compatible variable set with extras. What is missing is (a) two correctness problems that hit real users silently — the Obsidian daily-notes import dropping the common root-folder case, and Hungarian month/day names for everyone by default; (b) the small commands and settings around the engine (insert date/time, next/previous day, open on startup, formats in Settings); (c) the whole Note composer plugin. Two *must*, nine *should*, three *could*.

---

## 1. Checklist

| # | Obsidian behaviour | Manifold today (path:line) | Status | Priority | Size | Confidence | Gap |
|---|---|---|---|---|---|---|---|
| 1 | **Template folder** setting; templates are the notes in it | `[sablon] mappa` (`os.toml:210-211`); Settings → Files "Templates folder" (`Beallitasok.svelte:46-47`, validated `termek_beallitasok.py:111`); `templates.json#folder` is imported (`workspace.py:307-309`) | present | – | – | high | – |
| 2 | Choosing a template: searchable list of the folder's notes | `GET /api/sablon/lista` walks the folder recursively, skips hidden (`sablon.py:210-225`); overlay with accent-insensitive filter (`SablonValaszto.svelte:30-34`, `ListaValaszto`) | present | – | – | high | – |
| 3 | **Templates: Insert template** command; bindable hotkey (no default) | `sablon.beszur` "Insert template…" (`ma/index.ts:41-51`), gated on a writable non-Reading editor (`ma/naplo.ts:53-57`); every registry command is bindable in Settings → Hotkeys (`Beallitasok.svelte:139-147`) | present | – | – | high | – |
| 4 | `{{title}}` = title of the active note | `sablon.py:175-176`; insert passes the open note's name (`ma/naplo.ts:73`); new-from-template passes the *new* note's name (`sablon.py:271`) | present | – | – | high | – |
| 5 | `{{date}}` (`YYYY-MM-DD`) / `{{time}}` (`HH:mm`), `{{date:FORMAT}}` | `sablon.py:177-180`; empty format = default (`{{date:}}`); defaults overridable via `[sablon] datum/ido` (`os.toml:212-213`) and imported from `templates.json#dateFormat/timeFormat` (`importalas.py:160-163`) | present (config only) | – | – | high | 06 |
| 6 | Moment.js format language for `{{date:…}}`, `{{time:…}}`, daily-note names | subset: `YYYY YY MMMM MMM MM M DDDD DDD DD D Do dddd ddd dd d E HH H hh h mm m ss s A a WW W` + `[escape]` (`sablon.py:66`); anything else passes through **literally** (`sablon.py:14-15`) | partial | should | S | medium | 07 |
| 7 | Month/weekday names follow the app language (default English) | names come from `[sablon] nyelv`, shipped default `hu` (`os.toml:214`, `sablon.py:38,78,203`); Settings → language "Automatic" writes `""` which falls back to `hu` too (`termek_beallitasok.py:278`); the workspace language (`workspace.py:715`, default `en`) is not consulted | partial | **must** | S | high | 02 |
| 8 | **Templates: Insert current date / Insert current time** commands (use the plugin's date/time formats) | no commands. The `/` menu has "Date: today/tomorrow/yesterday", fixed ISO text, ignores `[sablon] datum`, no time (`sablonok.ts:262-285`) | missing | should | S | high | 03 |
| 9 | Insert at the cursor; one undo step | cursor-relative, selection replaced, `{{cursor}}` lands the caret, single transaction so ⌘Z is one step (`ma/sablon.ts:33-71`, `ma/naplo.ts:103-106`) | present (ahead: `{{cursor}}`) | – | – | high | – |
| 10 | Template **properties** merged into the target note's properties (1.4+) | core merge: new keys added, lists united, existing values kept, schema-violating keys held for confirmation (`ma/naplo.ts:87-137`, `/api/vault/tulajdonsagok/osszefesul`) | present (ahead: schema-aware) | – | – | medium | – |
| 11 | **Slash commands** "Insert template" | `/Template…` opens the same picker (`sablonok.ts:226-237`, `perjel.ts:145`, `ma/index.ts:60-63`) | present (see 05-editing-14) | – | – | high | – |
| 12 | Ribbon "Insert template" | `ikonsav.ts` lists `sablon.uj-jegyzet` only, no `sablon.beszur` | partial → 06-workspace-12 | – | – | high | – |
| 13 | **Daily notes: Open today's daily note** (command, ribbon icon, bindable) | `naplo.napi` ⌘⇧D (`ma/index.ts:22-30`), ribbon (`ikonsav.ts:30`), Ma page buttons (`Ma.svelte:143-165`), new-tab page (`UjFul.svelte:13`) | present | – | – | high | – |
| 14 | Creates the note if missing, opens it if it exists; never overwrites | `naplo.py:89-107` (existing file → path only; lost create race → open); module gate `napi` (`modulkapu.py:9`) | present | – | – | high | – |
| 15 | **Date format** drives the file name and subfolders (`YYYY/MMMM/YYYY-MMM-DD`) | one path key `[naplo] ut`, e.g. `[Daily]/YYYY-MM-DD` (`naplo.py:25,49-52`); Settings "Daily note path" (`Beallitasok.svelte:47,132-133`); missing folders created (`naplo.py:102`) | present (single combined key) | – | – | high | – |
| 16 | **New file location** for daily notes | folded into the path key (literal folders in `[brackets]`) | present | – | – | high | – |
| 17 | **Template file location** for daily notes (any note) | `[naplo] sablon` is a *name* inside the template folder, default "Napi jegyzet" (`naplo.py:27,77-86`); no Settings field; a name that does not resolve silently falls back to the built-in scaffold | partial | should | S | high | 06, 08 |
| 18 | Template applied only when the note is created; `{{date}}` in it is the *note's* date | `naplo.py:96-98` (date replaced with the requested day) | present | – | – | high | – |
| 19 | Import of `.obsidian/daily-notes.json` (folder, format, template) | only when `folder` is **non-empty** and has no `[`/`]`; format-only, root-folder and nested-template configs yield `{}` (`workspace.py:302-320`, condition at `:311`; executed check: `{'folder':'','format':'YYYY-MM-DD','template':'Templates/Daily.md'}` → `{}`) | partial | **must** | S | high | 01 |
| 20 | **Open daily note on startup** (Daily notes setting) | none; startup option is only "last workspace / picker" (`Beallitasok.svelte:117`) | missing | should | S | medium | 05 |
| 21 | **Next / previous daily note** | missing. Not an Obsidian *core* command (Calendar / Periodic Notes plugins). The core API already takes any date: `POST /api/naplo/ma {datum}` (`naplo.py:89-111`), `GET /api/ma?datum=` (`ma.py:223-224,249-250`); the UI never passes one (`ma/naplo.ts:29`, `ma/modell.svelte.ts` calls `/api/ma` bare) | missing (n.a. in core) | should | S | medium | 04 |
| 22 | Built-in daily note is **empty** unless a template is set | built-in scaffold has frontmatter `Tags: [Napló]`, `Source`, `Status`, `NN`, `Canvas`, H1 `# Napló` (`naplo.py:71-74`); template name default "Napi jegyzet" (`naplo.py:27`) | partial (differs) | should | S | high | 09 |
| 23 | **Note composer: Merge current file with another file…** (Enter = append, ⇧Enter = prepend, ⌘Enter = new note; links updated; confirm) | nothing | missing | should | L | high | 11 |
| 24 | **Note composer: Extract current selection…** (replaced by link / embed / nothing; template; same destination keys) | nothing | missing | should | M | high | 10 |
| 25 | Composer settings: text after extraction, template (`{{content}}`, `{{fromTitle}}`, `{{newTitle}}`, `{{date:…}}`), confirm before merge | nothing | missing | should (part of 10/11) | – | high | 10, 11 |
| 26 | **Unique note creator**: "Create new unique note", timestamp name (`YYYYMMDDHHmm`), next free minute on collision, optional template | nothing | missing | could | S | high (help page); default format medium | 12 |
| 27 | **Random note**: command + ribbon dice, opens a random note | nothing (`grep` for random/véletlen in `app/src`, `core` finds only unrelated uses) | missing | could | S | high | 13 |
| 28 | Weekly / monthly / quarterly notes | not core Obsidian (Periodic Notes plugin) | n.a. | could | M | medium | 14 |
| 29 | **New note from a template** in one step | `sablon.uj-jegyzet` palette command, tree folder menu, ribbon; name asked in the tree, schema check with "Create anyway" (`sablon.py:251-284`, `ma/sablonUj.ts`, `Fa.svelte:232`) | ahead | – | – | high | – |
| 30 | Calendar-aware "today" page | the Ma page: daily note card, calendar events, due tasks, flashcards, exam cards for one day (`ma.py:223-240`, `Ma.svelte`) | ahead | – | – | high | – |

---

## 2. Gaps and proposals

All proposals keep the layering: evaluation and file creation in the core, the UI only places text and opens notes; writes go through `Vault.create` / the existing atomic save path; no hardcoded paths; user text via `t()` / `kod` + English fallback.

### 12-templates-01 — Daily-notes import drops the common configurations (must, S, high)
**Obsidian.** `daily-notes.json` stores `folder` (empty string = vault root, the default), `format`, `template` (a vault path to any note).
**Manifold.** `_w_mag` builds the workspace layer only `if mappa and forma and "[" not in mappa and "]" not in mappa` (`workspace.py:311`); otherwise nothing is imported, **including the template**. A vault whose daily notes live in the root (the Obsidian default), or that only sets `format` (e.g. `YYYY/MM/YYYY-MM-DD`), gets no `[naplo]` entry and Manifold then creates `Daily/YYYY-MM-DD.md` — a different location from the user's existing notes, silently. Verified by calling `workspace._w_mag` with such dicts (both return `{}`). The template part also flattens the path to a bare name (`Path(...).name`, `:313`).
**Proposal.** Build `naplo.ut` as `<escaped folder segments>/<format>` or just `<format>` when the folder is empty; escape `[`/`]` in folder names instead of skipping (moment escape `[…]` cannot contain `]`, so refuse only that case and report it in the import preview via `nem_atvett`, `importalas.py:642-650`); keep the template as a vault path (see 08). Tests in `tests/migracio/test_obsidian_import.py` for: empty folder, nested format, folder with brackets, template outside the template folder.

### 12-templates-02 — Month and weekday names default to Hungarian (must, S, high)
**Obsidian.** `{{date:MMMM}}`, `dddd`, folder formats such as `YYYY/MMMM` use the app language (English by default).
**Manifold.** `[sablon] nyelv` ships as `hu` (`os.toml:214`); Settings "Automatic" stores `""` (`termek_beallitasok.py:278`), which `datum_formatum` treats as unknown and maps to `hu` (`sablon.py:78`). The workspace language (`workspace.py:715`, default `en`) is never read. An English user following Obsidian's own example `YYYY/MMMM/YYYY-MMM-DD` gets `2026/október/2026-okt.-17`; both the daily-note folder and inserted text are affected. The test pins the Hungarian default (`tests/test_sablon.py:177-179`).
**Proposal.** Resolve the language in `sablon.beallitasok`: explicit `[sablon] nyelv` → workspace `nyelv` → English; ship `os.toml` without the `hu` default (the neutral-defaults rule, CLAUDE.md); unknown locales fall back to English, not Hungarian. Keep the `hu` tables. Update the tests (`en` default, `hu` via workspace language).

### 12-templates-03 — Insert current date / time commands (should, S, high)
**Obsidian.** "Templates: Insert current date" and "…time", formatted by the plugin's Date format / Time format; bindable.
**Manifold.** No command. The `/` menu offers three fixed ISO dates (`sablonok.ts:262-285`), ignoring `[sablon] datum`, with no time entry.
**Proposal.** Two registry commands `sablon.datum-beszur`, `sablon.ido-beszur` that call `POST /api/sablon/kiertekel`-style evaluation of `{{date}}` / `{{time}}` (add a small core route or reuse `kiertekel` with an inline template; the formats stay single-sourced) and insert at all selections in one transaction. Make the `/` date entries use the same formatter and add "Time: now". Gate on the `sablonok` module.

### 12-templates-04 — Previous / next daily note (should, S, medium)
**Obsidian.** Not core (Calendar / Periodic Notes), but part of the daily-note loop and requested for this audit.
**Manifold.** Backend ready (`datum` accepted by `/api/naplo/ma` and `/api/ma`), no UI.
**Proposal.** Commands `naplo.vorige` / `naplo.kovetkezo` (names in English: "Open previous daily note", "Open next daily note"): derive the reference day from the active note by reversing the path format (match the active path against `napi_ut` for the neighbouring dates — a pure core helper `naplo.nap_az_utbol(cfg, ut)`), else today; the target is the calendar day ∓ 1, or the nearest existing note in that direction (open question 1). Add ‹ › buttons and a date picker on the Ma page (`Ma.svelte:72`, pass `datum` to `maAdat.frissit`).

### 12-templates-05 — Open daily note on startup (should, S, medium)
**Obsidian.** Daily notes setting "Open daily note on startup" (confidence medium: not on the fetched help page).
**Manifold.** Startup choice is "last workspace / picker" only (`Beallitasok.svelte:117`).
**Proposal.** `fajlok.napi_inditaskor: bool` (default off) in the settings schema (`termek_beallitasok.py:28`); after the workspace restores, call `napiJegyzetNyit` once per app launch (not per window), after layout restore so it does not clobber restored tabs. Test: harness opening the shell state twice.

### 12-templates-06 — Template and daily settings in the Settings UI (should, S, high)
**Obsidian.** Templates: Date format, Time format (+ folder). Daily notes: Date format, New file location, Template file location.
**Manifold.** Only "Templates folder" and "Daily note path" are in Settings (`Beallitasok.svelte:46-47`); `datum`, `ido`, `nyelv`, `[naplo] sablon` are file-config only and the settings writer persists only `sablon.mappa/nyelv` and `naplo.ut` (`termek_beallitasok.py:274-278`).
**Proposal.** Add `fajlok.sablon_datum`, `sablon_ido`, `napi_sablon` (path, validated to lie in the template folder or any vault `.md`) with a live preview line ("Preview: 2026-10-17") computed by the core; add them to the writer map. Keep the token help text (`beallitasok.napi_leiras`) and mention `[literal]`.

### 12-templates-07 — Moment token coverage (should, S, medium)
**Obsidian.** Moment.js: also `Q Qo Mo DDDo do w wo ww gggg GGGG e S… X x Z ZZ L LL LLL LLLL LT LTS`.
**Manifold.** The subset in `sablon.py:66`; unknown letters pass through literally, so `gggg-[W]ww` (Periodic-Notes style weekly names, popular in daily-note paths) silently yields `gggg-W` + `w`.
**Proposal.** Add the missing tokens (week-of-year per locale `w/ww` with Monday/ISO start, `gggg/GGGG`, `Q/Qo`, `Mo/do/DDDo`, `X/x`, `Z/ZZ`, `S…`, `LT`, `L…` per locale). Unsupported remainder should be reported in the Settings preview (06) instead of passing through. Extend `tests/test_sablon.py`.

### 12-templates-08 — Daily-note template by path, with a visible fallback (should, S, high)
**Obsidian.** The daily template is any note, chosen by path; a missing template simply gives an empty note and a notice.
**Manifold.** `[naplo] sablon` is a name resolved inside the template folder (`naplo.py:77-86`); if it does not exist (`NotFound`/`Invalid` swallowed) the built-in scaffold is used with no message. Two same-named templates in different subfolders are indistinguishable; a template outside the folder cannot be used; the import flattens paths (see 01).
**Proposal.** Accept a vault-relative path (keep bare names as shorthand for backward compatibility); when a configured template does not resolve, create the note from the neutral scaffold (09) **and** notify "Daily template not found: …".

### 12-templates-09 — Neutral built-in daily scaffold (should, S, high)
**Obsidian.** Without a template the daily note is empty.
**Manifold.** The fallback scaffold is the developer's vault convention: `Tags: [Napló]`, `Source`, `Status`, `NN`, `Canvas`, H1 `# Napló`, and the default template name "Napi jegyzet" (`naplo.py:3-4,27,71-74`; `[naplo] canvas` in `os.toml:221`). This conflicts with the product rules "defaults are neutral" and "user-facing text is English" (CLAUDE.md); the neutral-defaults test (`tests/test_alapertekek_semleges.py`) does not cover this text.
**Proposal.** Default scaffold: `# {{title}}\n\n{{cursor}}\n` (or empty plus cursor). Keep today's scaffold as an importable **sample template** shipped for the v2-import tool / the `v2-kompat` preset only. Default template name in English ("Daily note"). Update `tests/test_naplo.py` (`test_a_status_ures_es_a_sema_sorrendje_all`, `test_a_canvas_csak_letezo_havira_mutat`) to run with the preset.

### 12-templates-10 — Note composer: extract selection (should, M, high)
**Obsidian.** "Extract current selection…" (palette and editor context menu): choose destination (Enter = append, ⇧Enter = prepend, ⌘Enter = new note); the selection is replaced by a link, an embed, or nothing; optional template with `{{content}}`, `{{fromTitle}}`, `{{newTitle}}`, `{{date:…}}`.
**Manifold.** Not present. Building blocks exist: note creation `Vault.create` (atomic, one machine commit), destination picker pattern (`Atnevezes.svelte` folder list, quick switcher), link-format-aware insertion (F5/04-embeds-09), template engine (`sablon.kiertekel`).
**Proposal.** Core `POST /api/komponalo/kivon {forras, tartomany:{from,to,hash}, cel, hely:'veg'|'eleje'|'uj', sablon?}`: validates the source hash (CAS like embedded task edits), writes the destination first (create or append through the machine-write path), then returns the replacement text; the editor applies source-replacement + link in one transaction after the destination write is confirmed (destination written first = no data loss on failure). Settings: "Text after extraction" (link / embed / nothing), extraction template path. Also expose "Extract section under this heading" using the existing heading range (`core/index/linkek.py:97`) — a Manifold extra. Tests: failure between the two writes, stale hash, name collision.

### 12-templates-11 — Note composer: merge notes (should, L, high)
**Obsidian.** "Merge current file with another file…" appends/prepends the source to the destination (or creates a new note), removes the source, updates all links to it; "Confirm before merging" (default on).
**Manifold.** Not present. Reusable: the rename/move planner with link rewriting, reference probe and single-snapshot undo (`core/atnevezes.py:364-393,596-640`, strengths 1 in `07-explorer.md`), Trash with unsaved-document guard (`core/csatolmany.py:296-343`), merge of frontmatter (`/api/vault/tulajdonsagok/osszefesul`).
**Proposal.** Plan/execute pair like rename: `POST /api/komponalo/osszefuz/terv` returns the resulting destination text (frontmatter merged with the property rules above, body appended/prepended, embed/heading anchors of the source listed), the files whose links change, and blockers (unsaved source/destination, read-only); `…/vegrehajt` writes destination, rewrites links `[[Source]]` → `[[Destination]]` (anchors become `#Source` headings only if a heading was added — decide, open question 3), sends the source to the Trash (never hard-delete), all under one undo snapshot. UI: overlay with the plan like `Atnevezes.svelte`, "Confirm before merging" not needed because the plan *is* the confirmation. Largest item in this audit: link and embed rewriting must be proven on synthetic vaults.

### 12-templates-12 — Unique note creator (could, S, high)
**Obsidian.** "Create new unique note": name = timestamp (default `YYYYMMDDHHmm`, help-page example `202401010945`); if taken, the next free timestamp; optional template.
**Manifold.** Absent. `[sablon]` format helper and `Vault.create` collision handling exist.
**Proposal.** `POST /api/naplo/egyedi {sablon?}` with `[sablon] egyedi_formatum`; collisions step the minute forward as Obsidian does (open question 4: or add a suffix, which the community requests). Palette command only.

### 12-templates-13 — Random note (could, S, high)
**Obsidian.** Command "Open random note" and a dice ribbon icon.
**Manifold.** Absent. The tree already holds the Markdown file list in memory (`app/src/lib/vault/fajlok.svelte.ts`).
**Proposal.** `vault.veletlen-jegyzet` command choosing from the file list (md only, excluding the template folder), open in the active tab; no core change.

### 12-templates-14 — Periodic notes (weekly / monthly) (could, M, medium)
**Obsidian.** Not core. Listed for completeness: the daily stack (`naplo.py`) is date-only; the Ma page's monthly canvas key (`[naplo] canvas`) is a one-off.
**Proposal.** Generalise `napi_ut` to named periods only if requested; out of scope for parity.

---

## 3. Manifold strengths beyond Obsidian (keep)

1. **One evaluator for everything**: insert, new-from-template and daily creation share `sablon.kiertekel` (`sablon.py:156-185`); a single pass, so substituted text is never re-evaluated; UTF-16 caret offsets for CodeMirror; tested (`tests/test_sablon.py`, 27 tests).
2. **`{{cursor}}`** places the caret after insertion/creation (`sablon.py:168-174`, `ma/naplo.ts:38`).
3. **Frontmatter-aware insertion**: template properties merge into the note's properties (new keys, list union, existing values kept), with schema-violating keys held behind a "Write anyway" notification (`ma/naplo.ts:87-137`) — one undo step.
4. **New note from template** with a schema check and "Create anyway" confirmation, created atomically with a machine commit (`sablon.py:251-284`, `ma/sablonUj.ts`).
5. **Safe daily-note creation**: atomic create, missing month/year folders created through the guarded writer, NFC/NFD-safe folders, lost-race detection, never overwrites (`naplo.py:89-107`, `tests/test_naplo.py:60-114,156-210`).
6. **Daily note in context**: the Ma page combines the daily note card, calendar events, due tasks, flashcards and exam preparation for the day (`ma.py:223-240`), with a default hotkey (⌘⇧D), ribbon icon and new-tab entry; Obsidian ships no default hotkey and no overview.
7. **Obsidian import for templates/daily settings** with an explicit "not imported" report (`importalas.py:636-660`) — to be completed by 01.
8. **Extra variable forms**: whitespace inside braces, case-insensitive names, `{{date:}}` default (`sablon.py:69`), Hungarian short month names matching moment's `hu` locale.

---

## 4. Open questions

1. **Previous/next day when the target does not exist**: open the existing neighbour only (skip gaps, like Calendar-style "previous existing"), or create the adjacent calendar day? Obsidian core has no precedent.
2. **Daily path model**: keep the single combined path key (simple, already shipped) or expose Obsidian's separate "Date format" + "New file location" fields in Settings?
3. **Merge and anchors**: when note B is merged into A, should existing `[[B#Heading]]` links be rewritten to `[[A#Heading]]` (requires the heading to remain) and `[[B]]` to `[[A#B]]` (requires adding a heading)? Obsidian rewrites to the destination note only (confidence low on anchor behaviour).
4. **Unique note collisions**: step the timestamp forward (Obsidian behaviour, requested to change by the community) or append a counter?
5. **Language rule for `{{date}}` names**: follow the workspace content language (`workspace.nyelv`) or the UI language? They differ for users who run an English UI with Hungarian notes.
6. **Daily template outside the template folder**: allowed (Obsidian) or confined to the template folder (`sablon.olvas` guard, `sablon.py:228-238`)? Allowing it widens the read surface; the path gate (`norm_path`, in-vault only) would still apply.
