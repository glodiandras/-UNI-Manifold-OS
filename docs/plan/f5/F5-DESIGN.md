# F5 implementation contract

The existing Swift → Svelte → Python architecture stays. Workspace creation and open use `core.workspace`; notes and existing Obsidian configuration are preserved. All tests use synthetic folders. The v2 checkout and the real vault remain read-only.

## Ownership

- Coordinator: core launcher JSON service, validated settings writer/API, configuration defaults, server/module enforcement, editor/file-setting integration, running-core announcements, integration tests and phase log.
- Shell agent: native launcher, asynchronous helper client, native menus and lifecycle integration, Swift localization and native tests. No core files.
- Settings agent: `app/src/beallitasok`, shared frontend settings store/client/types, App integration, command/module UI gating, Settings tests, `en/beallitasok.json`. Coordinate App integration of Setup with its agent.
- Setup agent: `app/src/setup`, shared UI components, Setup tests and `en/setup.json`. Export `Setup.svelte`, receiving the shared settings store; Settings agent mounts it from App. No changes to the common store or App without coordination.

## Launcher service, before any core starts

`bin/mos indito` reads one bounded JSON object on stdin. `muvelet`: `lista`, `felmer`, `letrehoz`, `megnyit`, `elfelejt`, `demo`. Optional inputs: `vault`, `nev`, `id`, `uj_mappa`, `elfogad`.

stdout is NDJSON: optional `{haladas:{lepes,...}}` events, then `{ok:true,...}` or `{ok:false,kod,param,hiba:<English>}` (nonzero exit). Never parse stderr as JSON. A helper operation runs off the main thread and the launcher stays responsive.

- `lista`: `{ok:true,munkaterek:[{id,nev,vault,demo,elerheto,megnyitva,fut,pid}],utolso,inditas:"utolso"|"valaszto"}`. No secret tokens in announcements.
- `felmer`: `{ok:true,felmeres:<workspace.Felmeres>,uzenetek:[English human-readable warnings/blockers],valtozasok:[English descriptions]}`. Read-only, including for existing folders. Native UI shows this before converting a note folder.
- `letrehoz`: requires `elfogad:true` after the preview; uses `workspace.letrehoz`, emits its progress, returns `{ok:true,munkater:{id,nev,vault}}`. `uj_mappa:true` creates a new folder only under an existing parent.
- `megnyit`: verifies and registers an existing workspace; returns the same `munkater` shape. The core repeats identity/lock validation at start.
- `elfelejt`: removes only the registration; never a folder.
- `demo`: creates/reopens the app-owned `<install>/demo/Manifold Demo` starter workspace using the existing demo exception. F8 expands the sample library; F5 must already open a usable offline starter with linked Markdown examples. Existing demo notes are never overwritten.

Explicit `MOS_VAULT` and existing developer/selftest startup retain their behavior. Product startup without a valid remembered workspace opens the launcher. Native File menu offers the launcher again; switching must flush unsaved editor state and stop the old core before starting another one. Failure/cancel retains the current editor. No simultaneous second editor/core is introduced in F5; shared-worker lease work remains F6 with the documented multi-window work, avoiding a change to the worker ownership contract here.

## Shared settings API

`GET /api/beallitasok` → `{verzio:1,rev:string,ertek:Beallitasok,munkater:{id,nev,vault},setup_szukseges:boolean,ujrainditas:string[]}`.

`PUT /api/beallitasok`, body `{rev:string,valtozas:Partial<Beallitasok>}` → the same shape. Deep partial merge; unknown keys/types/ranges/unsafe relative paths are rejected. A stale revision gives HTTP409, preserving the external edit. Config writes are locked, durable and atomic, use the existing layer allow-list, retain unrelated TOML settings and never change workspace identity. Path roots are immutable here. The API reports reopen requirements instead of silently changing pinned process paths. A `beallitasok` WS event carries the response after success.

`Beallitasok` (identifiers stay Hungarian without accents):

```ts
interface Beallitasok {
  altalanos: { nyelv: 'auto'|'hu'|'en'; inditas: 'utolso'|'valaszto' };
  szerkeszto: { mod: 'elo'|'forras'; olvashato_szelesseg: boolean; helyesiras: boolean; tab_meret: number; perjel: boolean };
  fajlok: { uj_mappa: string; csatolmany_mappa: string; sablon_mappa: string; napi_ut: string; link_formatum: 'rovid'|'relativ' };
  megjelenes: { tema: 'rendszer'|'vilagos'|'sotet'; betumeret: number; csend: boolean };
  modulok: Record<ModulId, boolean>;
  adatvedelem: { asszisztens: boolean; tracker: boolean; ertesitesek: boolean; naptar: boolean };
  billentyuk: Record<string,string>;
  setup: { kesz: boolean; elmeny: 'diak'|'tudasmunka'|'fejleszto'|'kutato'|'egyeni' };
}
```

`ModulId`: `hivatkozasok`, `vazlat`, `tulajdonsagok`, `gyorsvalto`, `kereses`, `perjel`, `cimkek`, `sablonok`, `napi`, `canvas`, `bazis`, `graf`, `pdf`, `media`, `kartya`, `kviz`, `osszefoglalas`, `matek`, `kod`, `fuzet`, `video`, `kerdezz`, `asszisztens`, `naptar`, `felkeszultseg`, `tracker`.

Defaults preserve current functionality: all modules on, editor live preview/readable width/spellchecking/slash menu on, tab size2, system appearance/font16/quiet off, assistant/tracker/notifications on. Calendar permission is requested only through an explicit action. Setup is shown automatically only for a product workspace that has not completed it. Setup and Settings use one client/store and the same atomic API, including the final Setup commit. Note-language recognition stays automatic regardless of the optional content-language hint (`auto` means no hint); UI stays English.

Settings sidebar follows PLAN§11. F5 controls must work; later model installation, update, privacy diagnostics and migration tools are linked to existing functionality where available, and are not presented as working downloads or repairs. No dead controls or fake progress. Escape/focus trapping/focus restoration and visible save/error/conflict states are required. Every Settings section is reachable from a command; Cmd+, opens Settings without conflicting with editor shortcuts.

## Validation

Core API tests: first install, restart persistence, conflicts, validation, symlink/containment, module enforcement and unchanged note bytes. Native tests: launcher state/JSON boundary, progress/error handling and preserved selftest startup. UI: real Settings and Setup flows (skip AI, automatic content language, privacy, finish/reopen), module and shortcut changes, failures/conflicts/focus. Full Python/UI suites plus builds, NAPLO and a local commit close F5. F8's large demo/import and F6's model download/calibration remain separate phases.

## Implemented integration decisions

- `fajlok.uj_mappa = "."` preserves Obsidian's current-note-folder preference; empty means workspace root. Attachment paths also support `.` and `./Assets`. Imported `.obsidian/app.json` remains read-only. Missing configured note folders are created only with the new note, through the existing exclusive writer and snapshot path.
- Relative link output uses explicit `./` or `../`, verified by the one shared resolver. Explicit relative targets cannot fall through to suffix matching or escape the vault. The default shortest-unique format remains unchanged.
- Index cache migration5 invalidates only source caches containing explicit relative targets so old unresolved graph/backlink rows are recomputed even when note bytes have not changed. The relative lookup uses indexed basename candidates. Creation from missing relative links resolves from the source directory before the existing path validation.
- CodeMirror options use a compartment. Spellcheck, tab width, readable width, slash menu and the Properties module change live while preserving text, selection and undo. Disabling optional embedded tools leaves a link or source representation; no note content is rewritten.
- Chooser starts pass a one-use `MOS_MUNKATER_VALTAS=1`. Config clears the old workspace-dependent pins using the dependency graph, while retaining the selected vault and installation roots. The core removes the flag after resolving and pinning its new roots so worker/trial-clone configurations retain their own pins. Explicit CLI startup and rollback keep their original behavior.
- Startup preference is stored in the last workspace's settings; `lista` reads it without starting a core. This avoids a second installation-settings transaction during Setup. A missing last workspace still opens the picker.
- The TOML writer preserves unrelated semantic values, including dates, arrays and Unicode keys; table formatting/comments may be rewritten. The exact previous bytes remain recoverable in `.toml.elozo`. A stale revision or failed final replacement does not replace the current settings or in-memory configuration.
- Queued jobs and stored module data are retained when a module is disabled. Admission blocks new work, while a transaction already running is allowed to finish. Calendar background sync requires the visible calendar choice in product mode; OS permission remains an explicit native request.
