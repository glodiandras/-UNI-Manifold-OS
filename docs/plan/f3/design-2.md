# F3 design 2 — Obsidian-like workspaces, portability and operations first

Date: 2026-10-16. Scope: PLAN §10 F3 ("Konfig + workspace"), seen from the operations side: the workspace folder carries its
own config and state (`<vault>/.manifold`, as `.obsidian` does for Obsidian), many workspaces per install, a read-only
bundle, two cores at once, one worker and one model lock per machine, per-workspace backups, health checks, safe updates,
and the developer's v2 SSD layout kept alive as **portable mode**. Citations are to this repo (`path:line`).

## 0. Invariants (each one gets a test; nothing below may weaken CLAUDE.md non-negotiables)

| # | Invariant | Why |
|---|---|---|
| I1 | Every writable `[utak]` path resolves **outside `{os}`** in product mode; `config.load` fails otherwise | read-only, signed bundle; App Translocation |
| I2 | `{tmp}`, staging, inboxes, `vault.git` and the trial-clone root are on the **vault's volume** (checked by `st_dev`) | atomic rename / `clonefile` (`core/tartos.py`, `core/frame.py:272-291`) |
| I3 | All processes of one workspace (core, CLI, task steps, trial-clone Config, worker client) resolve the **same roots** | one ring lock `{run}/kor.lock`, one intent log |
| I4 | One core per vault (lock keyed by the vault itself); one worker and one model lock per **install** | L23, R8 |
| I5 | The workspace layer can never weaken a safety setting (sandbox, D9 calibration, network, paths, model limits) | a copied or downloaded vault is untrusted input |
| I6 | `.manifold/` is invisible to the vault API, the index, the watcher, snapshots and the binary-move log | it is machine state, like `.git` |
| I7 | Deleting `<vault>/.manifold` returns the folder to a plain Obsidian vault, byte for byte (PLAN §6) | no lock-in |
| I8 | Backups of two workspaces never share a rotation directory | `core/mentes.py:88-90` rotates by glob |

## 1. The three roots and the layered config

### 1.1 Roots and modes

| Placeholder | Product (`termek`) | Portable (`hordozhato`) | Source |
|---|---|---|---|
| `{os}` | `Manifold.app/Contents/Resources/manifold` (read-only) | the checkout | `MOS_ROOT`, else package location (`core/config.py:26-29`) |
| `{install}` | `{home}/Library/Application Support/Manifold` | `{os}/var` | `MOS_INSTALL` → marker `[gyokerek] install` → default |
| `{vault}` | the chosen folder | marker `[gyokerek] vault` | `MOS_VAULT` → `--workspace` (CLI) → registry `utolso` (CLI only) |
| `{workspace}` | `{vault}/.manifold` (config dir) | `{vault}/.manifold`, or `{os}/var/workspace` when the vault is shared with a running v2 (§7) | `MOS_WORKSPACE` → marker → default |
| `{ws_var}` | `{workspace}/var`; `{install}/workspaces/<id>/var` for sync-folder vaults (§3.7) | `{os}/var` | registry entry `allapot` (install layer, never the vault) |
| `{hej}` | `{os}/../../MacOS/Manifold` when `{os}` ends in `.app/Contents/Resources/manifold` | `{os}/Manifold.app/Contents/MacOS/Manifold` | `MOS_HEJ` → derived (fixes audit 04 H5) |
| `{workspace_id}`, `{workspace_dir}` | from `workspace.toml` (`<slug(name)>-<id[:8]>`) | same | read, never configured |

Mode: `MOS_MOD` → `hordozhato` if `MOS_HORDOZHATO=<marker>` or `{os}/manifold-portable.toml` exists → else `termek`.
Portable is refused when `{os}` is inside an `.app` bundle (sealed code) unless `MOS_FEJLESZTO=1`.

### 1.2 Layers (later wins; deep merge of tables, arrays **replace**)

`config/os.toml` (S, shipped) ← install `{install}/settings.toml` (I; in portable mode the marker file itself, which may
`include` presets such as `config/presets/v2-kompat.toml`) ← `{workspace}/workspace.toml` (W) ← env (E: `MOS_<UTAK-KULCS>`
as today, `core/config.py:56-57`, plus the root variables of §1.5). Missing I/W files are empty layers; a **TOML error in a
layer is fatal for that workspace** (core start exits with `kod: workspace_toml_hibas` / `settings_toml_hibas`; the Health
fix keeps a copy and resets), never silently dropped — a dropped W layer would change schema and write rules under the user.

### 1.3 Which layer owns which key (enforced by `config.RETEG_JOG`; a violation is ignored + a Health item `workspace_kulcs_tiltott`)

| Layer | May set | Examples |
|---|---|---|
| S only | `[utak]` code paths, `[core]`, `[pillanat.*] kizar`, `[homokozo]`, `[router]`, `[meres*]`, `[modellek.*]`, `[kalibracio.*]` (F6), `[kapuk]` thresholds, `[index]`, `[feladatsor]`, `[grafikon]`, `[matek]` | sandbox, D9, gates |
| I (+S) | writable `[utak]` overrides (`models`, `backup_gyoker`, `llvm`, `sdk`, `cache`), `[modellgazda]`/`[keret]` (RAM profile), `[mentes]`/`[teljes_mentes]` (retention, target), `[naptar]` sync switches, privacy switches (`[asszisztens] be`, tracker, notifications), `[fuzet] mappak` (folders **outside** the vault), `[modulok]` defaults, `[workspace_alap]` (new-workspace template) | machine and person |
| W (+I+S) | vault conventions only: `[workspace]`, `[sablon]`, `[naplo]`, `[vault] kisero_elotag`, `[kartya\|kviz\|osszefoglalas] mappa/utotag`, `[fuzet] cel_mappa/szakasz/elmelet_mappa`, `[media]`, `[pdf.tags]`, `[video] tema_minta/kizart_mappak/vault_mappa`, `[naptar.szotar*]`, `[asszisztens] *_kizart/tantargy_nevek`, `[kapuk] kihagyott_szakaszok`, `[felkeszultseg]` weights, `[sema] mod`, `[modulok]` (per-vault module switches, Obsidian's `core-plugins.json`) | travels with the folder |
| E | `MOS_<UTAK>` and the root variables | tests, shell, portable |

### 1.4 `[utak]` rewrite (`config/os.toml:10-53`) — product defaults; portable reproduces today's paths exactly

```toml
[utak]
ws_var        = "{workspace}/var"        # overridden by the registry (sync folders) or the portable marker
install_run   = "{install}/run"          # worker.lock, worker.pid, modell.lock, cores/<id>.json, regiszter.lock
install_logs  = "{install}/logs"         # worker.log, telepites.log
var = "{ws_var}"                         # alias kept for old readers (doctor, tests) — do not use in new code
state = "{ws_var}/state"      run = "{ws_var}/run"      runs = "{ws_var}/runs"      tmp = "{ws_var}/tmp"
index = "{ws_var}/index"      szemelyes = "{ws_var}/szemelyes"                       vault_git = "{ws_var}/vault.git"
ytdlp = "{ws_var}/ytdlp"      ytdlp_git = "{ws_var}/ytdlp.git"   archive = "{ws_var}/archive"   # state, not code (audit 02 §7.4)
vault_kepek = "{ws_var}/cache/vault-kepek"                       # per workspace: keys are vault-relative paths
models = "{install}/models"   cache = "{install}/cache"   router_db = "{install}/router.sqlite"
venv = "{install}/venv"                                          # portable only; product uses {runtime}/site-packages
llvm = "{install}/toolchains/llvm"   sdk = "{install}/toolchains/sdk"
backup_gyoker = "{install}/backups"   backup = "{backup_gyoker}/{workspace_dir}"     # I8
naptar_seged = "{hej}"   hej_cli = "{hej}"   modulok = "{os}/modulok"   runtime = "{os}/runtime"   app_dist = "{os}/app/dist"
# removed: work, the `vault = {work}/Manifold` default (F2 deferred item: a checkout no longer resolves to a real vault)
```

Also: `[pillanat.vault] kizar += [".manifold/"]`; `kivetelek = "{workspace}/pillanat-kivetelek.json"` (optional);
`[sema] vault = "{workspace}/schema.json"`, `alap = "{os}/config/schema-default.json"` (fallback, F6/WP6);
`[mentes] kodtar = ""` (portable marker sets `"{os}"`; `mentes.kodtar_munkafa` must map `""` to None — today `Path("")` would probe the cwd, `core/mentes.py:138-139`); `[modellgazda] zar = "{install_run}/modell.lock"`
(`core/modell/beallitas.py:18` today `{state}/modell.lock`).

### 1.5 Config API (`core/config.py`, new `core/gyokerek.py`)

```python
# core/gyokerek.py — pure, no I/O except stat/reads; shared by bin/mos.py, the core, the worker, tests
Mod = Literal["termek", "hordozhato"]
@dataclass(frozen=True)
class Gyokerek: mod: Mod; os: Path; install: Path; vault: Path | None; workspace: Path | None; ws_var: Path | None
                hej: Path | None; workspace_id: str | None; athelyezett: bool   # App Translocation (path contains /AppTranslocation/)
def felold(env: Mapping[str, str]) -> Gyokerek
def kornyezet(g: Gyokerek) -> dict[str, str]         # MOS_MOD/ROOT/INSTALL/VAULT/WORKSPACE/WORKSPACE_ID + HF_HOME, XDG_CACHE_HOME,
                                                      # UV/PIP_CACHE_DIR, TMPDIR, PATH (+{runtime}/git/bin) — replaces bin/mos:35-52
# core/config.py
class Config:                                         # keeps Config(root, data, environment, source) for old callers
    mod: Mod; gyokerek: Gyokerek; retegek: list[Reteg]       # Reteg(nev: "os"|"install"|"workspace"|"env", ut: Path|None, data)
    utak: Mapping[str, Path]                          # LAZY: a workspace key without a workspace → ConfigError(kod="nincs_workspace")
    def path(self, kulcs) -> Path; def section(self, *k) -> dict; def expand(self, t) -> str
    def forras(self, *kulcs_ut: str) -> str           # which layer set this key (Settings ⌘, in F5 shows it)
    def klon(self, **utak: str) -> "Config"            # same roots + overrides; replaces the hand-built env in core/gepi_iras.py:535-540
def load(environment=None, *, workspace: bool = True) -> Config
def load_install(environment=None) -> Config           # = load(workspace=False): the worker, the launcher CLI, install migrations
class ConfigError(ValueError): kod: str; param: dict  # F4 error contract
```

Eager `self.utak` (`core/config.py:58`) becomes a lazy mapping so the worker and `mos workspace list` run without a workspace.
`MOS_CONFIG` stays as a developer-only replacement of the S layer. Writing layers is F5, but F3 adds the writer they will use:
`core/beallitas_iras.py: ir(cfg, reteg, valtozasok: dict, *, elozo_sha: str) -> str` (own minimal TOML serializer, stdlib has
no writer; atomic `tartos.atomi_ir`; optimistic concurrency because two cores share `settings.toml`; W writes reject non-W keys).

## 2. Entry points get their roots; no hard-coded `var/`

- **`bin/mos`** shrinks to a ~40-line bash shim: resolve itself (`bin/mos:6-13`), pick the interpreter
  (`MOS_PYTHON` → `{os}/runtime/python/bin/python3` with `{os}/runtime/site-packages` → portable `{os}/var/venv` → worktree
  main checkout), then `exec "$py" -B "$MOS_HOME/bin/mos.py" "$@"`. `runtime fetch/install` and `app` stay in bash (portable only:
  they need no Python, and the bundle has no network step). Worktree mode (`bin/mos:19-31`) is kept: own `var/`, a symlinked
  `var/` is still an error.
- **`bin/mos.py`** (new): `gyokerek.felold(os.environ)` → `os.environ.update(gyokerek.kornyezet(g))` → `mkdir` of `{tmp}`, `{cache}`
  and `.metadata_never_index` in `{ws_var}` and `{install}/cache` (from config, not `$MOS_HOME/var`) → dispatch table (the
  `case` of `bin/mos:196-297` ported 1:1; developer commands still behind `core.fejleszto`). New global flag
  `--workspace PATH|ID` and new commands: `mos workspace list|create|open|check|forget|rekey --json`, `mos portable init`.
- **Shell.** `RootLocator.locate` (`shell/Sources/RootLocator.swift:13-18`): `MOS_ROOT` → `Bundle.main.resourceURL/manifold` →
  the `.app`'s parent (portable). New `Telepites.swift`: `installURL` = `FileManager … applicationSupportDirectory/Manifold`,
  `regiszter()` reads `workspaces.json` (read-only; Python is the only writer), `athelyezett` = path contains `/AppTranslocation/`
  → launcher banner "Move Manifold to Applications" (works anyway: code is read from Resources, state is outside).
  `CoreProcess.init(root:vault:workspaceId:port:titok:)` (`CoreProcess.swift:55-62`) adds `MOS_MOD=termek`, `MOS_INSTALL`,
  `MOS_VAULT`, `MOS_WORKSPACE_ID`, `MOS_HEJ=Bundle.main.executablePath`; in portable mode only `MOS_ROOT`. The unmount watcher
  (`AppController.swift:112-114, 414-417`) watches the **vault's** volume (and `{ws_var}`'s), not the code root (audit 04 H6).
- Children inherit roots through the existing `MOS_*` whitelist (`core/lepes_kapu.py:56-61`), so task steps need no change; the
  trial clone uses `cfg.klon(vault=…, vault_git=…, run=…)`; the worker gets `gyokerek.kornyezet` **minus** the workspace vars.

## 3. Workspace lifecycle (`core/workspace.py`, `core/telepites.py`, `core/workspace_migracio.py`)

### 3.1 Layout

```
<vault>/                                 Markdown, attachments, .obsidian/ (created if missing, never written afterwards)
<vault>/.manifold/
  workspace.toml                          W layer (id, formatum, name, content language, conventions)
  schema.json                             optional; absent = {os}/config/schema-default.json
  .gitignore                              "var/" — for users who keep their vault in their own git (obsidian-git)
  README.txt                              "Manifold's settings and data for this folder; delete to remove Manifold, notes are untouched"
  var/  (= {ws_var})                      vault.git  index/  state/  run/  runs/  tmp/  szemelyes/  ytdlp/  archive/  cache/
        .metadata_never_index             Spotlight off; Time Machine exclusion xattr on tmp/, cache/, index/ only
{install}/  settings.toml  workspaces.json  verzio.json  router.sqlite  models/  toolchains/  run/  logs/  backups/<workspace_dir>/
            workspaces/<id>/var/          only for sync-folder vaults (§3.7)
```

```toml
# workspace.toml
[workspace]
id = "9f1c…"            # uuid4 hex; never derived from a path or a name
formatum = 1            # written last by every migration
olvaso_min = 1          # oldest format a reader must understand (additive migrations keep it low → app downgrade works)
nev = "Physics notes"
nyelv = "en"            # content language (P2)
[naplo]
ut = "Daily/YYYY-MM-DD"
```

### 3.2 Create / open (launcher: Create · Open folder · Try demo)

`terv(vault: Path, *, uj: bool) -> Terv` — dry run for the launcher (PLAN §6 step 2): writable?, filesystem (`statfs`:
apfs / hfs / exfat / smbfs / nfs / File Provider), `MNT_LOCAL`, free space, `.md` count, `.obsidian` present, sync folder,
existing `.manifold` (and its id/format), what will be created; `Terv.eredmeny ∈ {mehet, figyelmeztet, tilos}` + `kod`s.

`letrehoz(vault, *, nev, nyelv, preset=None, demo=False) -> Workspace`:
1. new: `mkdir` the vault; open: nothing in the vault is touched except steps 2–4.
2. `.obsidian/` if missing (empty dir, as Obsidian does; keeps Obsidian round-trip and today's helpers working).
3. Build `.manifold.uj-<hex>/` (workspace.toml from `config/workspace-default.toml` + preset, .gitignore, README.txt, `var/`),
   seed W keys from `.obsidian/{app,templates,daily-notes}.json` (audit 06 B4; read only), `fsync`, `rename` → `.manifold`
   (atomic; a leftover `.manifold.uj-*` is removed by the next `terv`).
4. `Repo.init()` with a **relative** `core.worktree` (`../../..`; git accepts a path relative to the git dir) — the folder can
   then be moved or copied without rewriting `vault.git/config` (`core/snapshot.py:221` writes an absolute path today; new
   `Repo.init(relativ: bool = False)`; the trial clone keeps absolute).
5. First commit (`Mos-Forras: kezi`, text only via the existing `kizar` + media list): synchronous for a new/empty vault; for an
   opened vault a queued "Initial snapshot" task with progress; until it lands, machine writes answer 503 as today
   (`core/gepi_iras.py:544-548`) and the editor commits through the normal frame.
6. `Regiszter.felvesz(...)`; return.

`megnyit(vault, *, dontes=None) -> Workspace | Kerdes` on every open: read `workspace.toml`; `formatum > FORMATUM_MAX` and
`olvaso_min > FORMATUM_MAX` → refuse (`kod: workspace_ujabb`); lower → migrate (§3.8); compare with the registry:
same id at the same path → ok; same id, old path gone → **moved** (update path; nothing else to fix thanks to the relative
worktree; legacy absolute worktree is rewritten by the idempotent `Repo.init`); same id and the old path still holds the
same id → **copied** → `Kerdes("masolat")`, `dontes="uj_azonosito"` runs `ujrakulcsol()` (new id, new `workspace_dir`, keeps the
copied history); old volume not mounted → ambiguous → `Kerdes("masolat_vagy_athelyezes")`. Pending intent logs survive a move:
recovery resolves them against `cfg.path("vault")` at recovery time (`core/atnevezes.py:105`, `core/gepi_iras.py:362`); a move
test pins this.

Demo: `letrehoz({install}/demo/Manifold Demo, demo=True)` (F8 fills it); "Reset demo" moves the old one to the Trash
(shell `--kuka`), never deletes.

### 3.3 Registry (`{install}/workspaces.json`, `core/telepites.py: class Regiszter`)

`{"formatum":1, "utolso":"<id>", "workspaces":[{"id","nev","ut","kotet_uuid","inode","allapot":"vault"|"install"|"<abs>",
"utoljara","demo"}]}`. One writer (Python, `tartos.atomi_ir` under `{install_run}/regiszter.lock`); the shell only reads.
`forget` never deletes files. Running cores announce themselves in `{install_run}/cores/<id>.json` (pid, port, start; no
secret), removed on exit, stale when the pid is dead or the core lock is free — the launcher uses it to focus the open window.

### 3.4 The `.obsidian` gate becomes an identity gate

New `workspace.jelen(cfg) -> bool`: product — `{workspace}/workspace.toml` exists **and** its id equals `cfg.workspace_id`
(catches a swapped SSD with the same volume name, which `.obsidian` cannot); portable with an outside `{workspace}` — `.obsidian`
plus `kotet_uuid`/`inode` recorded in `{workspace}/workspace.toml`. Callers switch to it: `Vault.root` (`core/vaultio.py:178-184`),
`frame.vault_letezik` (`core/frame.py:128-132`), `frame.tmp_maradekok` (`:164`), the startup branch in `core/server.py:244, 268`,
`core/doctor.py:162`. T002 semantics (no recovery on a missing vault) are unchanged.

### 3.5 Making `.manifold` invisible (I6) — concrete bugs this prevents

| Place | Change | Failure without it |
|---|---|---|
| `core/index/feloldas.py:38` `SKIP_DIRS` | add `.manifold` | the D9 trial clone under `.manifold/var/tmp/proba/<kor>/` would be **indexed as duplicate notes** |
| `core/binaris_naplo.py:55` `KIHAGY` | add `.manifold` | the binary-move log walks `vault.git` objects and SQLite files |
| `core/index/figyelo.py:112-122` | `FSEventStreamSetExclusionPaths([<vault>/.manifold])` | `_FILE_EVENTS` (`:22`) = one event per file of every trial clone and WAL write |
| `config/os.toml` `[pillanat.vault] kizar` | `.manifold/` | vault.git would commit its own state |
| `core/frame.py:280-291` `trial_clone` | clone the vault's top-level entries except `.manifold/var` (`cp -c -R` per entry; `.manifold/workspace.toml` is cloned so the gate holds in the clone) | `cp -R` of the vault into its own subtree |
| `core/vaultkivul.py:15` | `vaultban_van(cel, vault, *, allapot: Path \| None = None)`: a target under `allapot` (`{ws_var}`, same samefile walk, still fail-closed) is "outside"; `teljes_mentes` passes none | the default card export `{szemelyes}/export/*.apkg` (`core/kartya_api.py:336-344`, `modulok/kartya/__main__.py:62-66`) and `modulok/kapuk/__main__.py:30` would be refused |
| `core/vaultio.py` `norm_path` | none (hidden segments already rejected) — add a test that `.manifold/...` is 400 | — |

### 3.6 Non-APFS and sync folders

`{ws_var}` must share the vault's volume (I2). Vault on exFAT/HFS+/network: open in **reduced mode** (no trial clone → D9
machine writes stay `proba`-less, i.e. refused with a clear `kod: proba_klon_nem_tamogatott`; `flock` on network volumes is
unreliable → refuse unless `MNT_LOCAL`). Vault inside iCloud Drive / Dropbox / OneDrive / Google Drive (File Provider path or
known roots): `vault.git` and SQLite must not sync → registry `allapot = "install"` → `{install}/workspaces/<id>/var` (same
internal volume as `~/Library/Mobile Documents` and CloudStorage, so I2 holds; checked, else reduced mode). `.manifold/workspace.toml`
still lives in the vault and syncs (Obsidian-like settings sync); history is then per Mac (documented).

### 3.7 Migration and update safety

- **Workspace** (`core/workspace_migracio.py`): `MIGRACIOK: dict[int, Lepes]`, `Lepes(cel: int, additiv: bool, fut: Callable[[Config], None])`.
  `migral(cfg)`: under the core lock and the ring lock → pre-copy to `{backup}/mos-migracio-ws-v<N>-<ts>/` (`mentes.allapot_masolat`
  + `mentes.migracio_elott` per SQLite + `vault.git` bundle) → steps → `formatum` (and `olvaso_min` only for non-additive steps)
  written last. Exception → restore the copied files, leave `formatum`, Health `workspace_migracio_hiba` with "Restore pre-update
  copy". Migrations never edit Markdown; vault content changes go through the machine-write service as a revertable commit.
- **Install** (`core/telepites.py: frissites_ellenor(cfg)`), on the first launcher/core start of a new build (`epites.json`
  `verzio`, `install_formatum`, `workspace_formatum_max`, frozen at build time): `{install_run}/telepites.lock` → copy
  `settings.toml`, `workspaces.json`, `router.sqlite` (`VACUUM INTO`) to `{install}/backups/_install/elotte-<verzio>-<ts>/` →
  migrate → append `{install}/verzio.json` history. Downgrade: an older app opens a workspace iff `olvaso_min ≤` its max, else it
  offers the pre-migration copy (`mos workspace restore-migration <id>`).

## 4. Locks and two cores at once

| Lock | Today | F3 | Notes |
|---|---|---|---|
| core (single instance) | `{run}/core.lock` = per var (`core/server.py:945-967`) | `{workspace}/core.lock` — **in the vault's `.manifold`**, so two cores reaching the same vault through any path (symlink, two vars, portable + product) hit the same inode; content `pid · workspace_id · vault` | exit 75 handshake unchanged; refuse when the volume is not `MNT_LOCAL` |
| ring | `{run}/kor.lock` | unchanged (`{ws_var}/run`) | per workspace |
| worker | `{run}/worker.{lock,pid}` (`core/modell/worker.py:361-372`, `kliens.py:35`), log `{runs}` (`kliens.py:277`) | `{install_run}/worker.{lock,pid}`, `{install_logs}/worker.log`; the worker uses `config.load_install()` | one per machine |
| model | `{state}/modell.lock` (`beallitas.py:18`) | `{install_run}/modell.lock` (`MANIFOLD_MODELL_ZAR` still wins) | one model per machine (L23) |

New `core/zarak.py`: `core_zar(cfg) -> tuple[IO | None, dict | None]`, `core_fut(cfg) -> bool` (used by `server.start` and by
`core/visszaallitas.py:40-53`, which today probes `{run}/core.lock` and would miss a core on another var), `install_ut(cfg, nev)`.

**Shared worker lifetime.** Today the worker is the starting core's child and dies with it (D4); a second core adopts it via
the pid file (`kliens.py:260-270`) and loses it mid-request when the first core quits. F3: each core holding a worker client
takes a shared lease `flock(LOCK_SH)` on `{install_run}/worker-berlet/<core-pid>.lock`; on stdin EOF the worker exits only when
no lease is held (else it detaches and exits after the last lease + `[modellgazda] tetlen_kilepes_mp`, default 120 s). Requests
carry `X-Manifold-Workspace` for logs only (the worker holds no workspace state; routing reads the install `router.sqlite`).
Per-core things stay per workspace: port, API secret, task queue (`feladatok.sqlite`), index, `felulet.json`, `core.log`.
Fallback if the lease work slips: the adopting core restarts the worker on `KliensHiba` (today's `el()` path) and the task retries once.

## 5. Backups per workspace

- Internal backup: `backup = {backup_gyoker}/{workspace_dir}` — every name in `core/mentes.py` (bundles, `mos-allapot-*`,
  `mos-migracio-*`) is already relative to `cfg.path("backup")`, so per-workspace rotation (I8) is a config change. Target root
  configurable in the I layer (`[utak] backup_gyoker`, Settings › Backup in F5). `allapot_forrasok` adds `workspace.toml` and
  `schema.json`. `kodtar` only in portable mode (no `.git` in a bundle; already skipped, `core/mentes.py:135-140`). Health
  `mentes_azonos_lemez` when backup root and vault share a disk ("add an external backup").
- Full backup (`core/teljes_mentes.py`): roots = `vault` (contains `.manifold`) + `ws_var` if outside the vault + `router_db`;
  the `os` root only in portable mode (`:85`). `_kizart_mintak` (`:111-121`) computed **per root**, so `.manifold/var/{tmp,run,
  runs,cache,index}` and `tmp/proba` are excluded wherever they live. Volume check against the vault and `{ws_var}`, not the code:
  `cel.st_dev not in {vault.st_dev, ws_var.st_dev}` at `:337`, `:615` and `core/tasks.py:139`. Target layout
  `<cel>/Manifold Backups/<workspace_dir>/Manifold-<stamp>/`; `aktiv-os.toml` (`:409-411`) → `aktiv-settings.toml`. Restore maps
  keys to targets: vault → a user-chosen empty folder (its `.manifold` comes with it), `router_db` → `{install}` only if absent,
  then `workspace.megnyit()` registers it; the `Manifold-OS`/`Manifold` sibling names (`:505, 527`) remain for portable restores.

## 6. Doctor → Health product mode (`core/doctor.py`; F7 builds the UI on top)

`ellenoriz(cfg, environment, home, futo_python=None)` branches on `cfg.mod`; every result gets a stable `kod` and `javitas`
id (for `POST /api/egeszseg/javit` later) and `--json` output. Product checks: bundle root valid and **not** translocated
(`bundle_athelyezett`), nothing writable under `{os}` resolved (I1), runtime python + `site-packages` present, no absolute
shebang/`pyvenv.cfg` pointing outside the bundle, portable git runs (`{runtime}/git/bin/git --exec-path` inside the bundle,
else system git with `git_rendszer` info), `{install}` writable + free space, model store size, registry paths that vanished
(`regiszter_ervenytelen_ut`, fix `regiszter_takarit`), workspace format (`workspace_ujabb` / migration needed), identity gate,
vault filesystem (`kotet_nem_apfs`, `kotet_halozati`, `szinkron_mappa`), `{ws_var}` on the vault volume (replaces
`core/doctor.py:735-740`), stale `core.lock` / `worker.pid` (fix `zar_takarit`, only when the pid is dead and the flock free),
backup freshness. Rules that become portable-only: `var` symlink (`:742-753`), `SAJAT_MINTA` (`:23`; `/Applications` is fine),
`HOME_NEM_ENGEDETT` (`:366-367`) minus `Library/Application Support/Manifold`, `{os}/var/.metadata_never_index`, venv checks.

## 7. Portable mode (the developer's SSD layout)

Marker `{os}/manifold-portable.toml` (gitignored, `export-ignore`; it *is* the I layer). `mos portable init [--vault P]
[--v2-kompat] [--kulso-workspace]` writes it from `config/presets/portable-v2.toml`:

```toml
include = ["config/presets/v2-kompat.toml"]   # F2 preset: [fuzet] mappak, [naptar.szotar] dolgozat
[gyokerek]
install = "{os}/var"
vault = "/Volumes/<ssd>/<vault>"              # written by `mos portable init`, never in the repo
workspace = "{os}/var/workspace"              # keeps .manifold OUT of a vault that v2 still manages (see below)
[utak]
ws_var = "{os}/var"
backup = "{home}/Manifold-backup"             # v2's flat folder (one workspace)
[mentes]
kodtar = "{os}"
```

With it every `[utak]` key resolves to today's v2 path (`{os}/var/state`, `{os}/var/run`, `{os}/var/models`, …); only the model
lock moves to `{os}/var/run/modell.lock` (a v2 instance on the same Mac uses its own lock, so the developer runs one of them at
a time or points `MANIFOLD_MODELL_ZAR` at a shared path). **Why `--kulso-workspace` is the default for a v2-shared vault:** v2's
`SKIP_DIRS` and snapshot `kizar` do not know `.manifold`; a product `.manifold/var` inside that vault would be committed by v2's
`vault.git` and its trial clones indexed by v2. Moving `.manifold` into the vault is a later, explicit step of the v2-import
tool (F8). The model store may point at a separate store or an APFS clone, **never** at v2's `var/models` (offline HF still
writes `.no_exist` markers; v2 is read-only). Tests use the same mechanism: `tests/helpers.alg_gyoker` writes a marker with
`install = "{os}/var"`, `ws_var = "{os}/var"`, `vault = "{os}/../Manifold"`, so the ~4 000 existing tests see unchanged paths.

## 8. Implementation plan (stage A alone, then stage B in parallel on disjoint files)

| WP | Stage / agent | Files (exclusive) | Tests (new · must stay green) | Effort |
|---|---|---|---|---|
| **WP1 Roots + layered config** | A · opus | `core/config.py`, new `core/gyokerek.py`, new `core/beallitas_iras.py`, `config/os.toml` (`[utak]`, `[pillanat.vault]`, `[sema]`, `[mentes] kodtar`, `[modellgazda] zar`), new `config/{settings-default,workspace-default}.toml`, new `config/presets/portable-v2.toml`, `tests/helpers.py`, `.gitignore`, `.gitattributes` | new `test_gyokerek` (modes, bundle/translocation, I1 on a fake `X.app/Contents/Resources/manifold`), `test_config_retegek` (merge, array replace, `forras()`, W allow-list incl. a malicious `workspace.toml` setting `[homokozo]`, `[utak]`, `[router]` → ignored, lazy `nincs_workspace`, `klon()`) · `test_config` (update the v2-layout assertions), whole suite via the helpers marker | L (2 d) |
| **WP2 Workspace lifecycle** | B · opus | new `core/workspace.py`, `core/telepites.py`, `core/workspace_migracio.py`; `core/snapshot.py` (relative worktree), `core/frame.py`, `core/vaultio.py`, `core/index/feloldas.py`, `core/index/figyelo.py`, `core/binaris_naplo.py`, `core/vaultkivul.py`, `core/kartya_api.py`, `modulok/kartya/__main__.py`, `modulok/kapuk/__main__.py` | new `tests/fresh_install/test_workspace_letrehozas` (PLAN F3 gate: empty folder → `.obsidian` + `.manifold` + live repo + first commit; existing Obsidian vault untouched byte for byte; deleting `.manifold` restores it — I7), `test_workspace_mozgatas` (move with a pending rename intent), `test_workspace_masolat`, `test_workspace_migracio` (failure restores), `test_regiszter`, `test_manifold_lathatatlan` (index, watcher, snapshot, binaris_naplo, `norm_path`, trial clone) · `test_snapshot`, `test_frame`, `test_gepi_iras`, `test_vaultio`, `test_kartya*`, `test_visszaallitas` | L (2.5 d) |
| **WP3 Entry points + locks** | B · opus | `bin/mos`, new `bin/mos.py`, `core/__main__.py`, `core/server.py` (core lock, gate, `cores/<id>.json`), new `core/zarak.py`, `core/gepi_iras.py` (`cfg.klon`), `core/modell/{beallitas,zar,worker,kliens}.py` | new `tests/multi_user/test_ket_core` (two workspaces → two cores, one worker, one model lock; same vault via two paths → second gets exit 75), `test_worker_berlet`, `test_mos_py` (CLI dispatch parity with the old `case`, env from config, no `$MOS_HOME/var` writes in product mode) · `test_lepes_kapu`, `test_modell_*`, `test_core_*`, `test_mos_es_shell` | L (2 d) |
| **WP4 Backups + restore** | B · sonnet | `core/mentes.py`, `core/teljes_mentes.py`, `core/visszaallitas.py` (uses `zarak.core_fut`), `core/tasks.py` (volume check `:127-144`) | new `test_mentes_workspace` (two workspaces, separate rotation — I8), `test_teljes_mentes_termek` (volume rule vs vault, per-root excludes, restore into a new folder + register) · `test_mentes`, `test_teljes_mentes`, `test_kiadas_mentes`, `test_visszaallitas` | M (1.5 d) |
| **WP5 Health + shell** | B · opus | `core/doctor.py`, `shell/Sources/{RootLocator,CoreProcess,AppController}.swift`, new `shell/Sources/Telepites.swift`, `shell/Info.plist` (nothing new beyond F2) | `test_doctor` split into `_hordozhato` (today's rules) and `_termek` (fake bundle + fake install); Swift build in both configurations; `test_c33_core` with a rebuilt app | M (1.5 d) |
| **WP6 Workspace conventions** (PLAN F3 second agent) | B · sonnet | `config/os.toml` **W sections only** (`[naplo]`, `[asszisztens] *_kizart`, `[video] kizart_mappak`, `[pdf.tags]` → neutral; developer values into `config/presets/v2-kompat.toml`), `config/vault-sema.json` → `config/schema-default.json` (+ preset), `core/tulajdonsagok.py` (`mod: ki/tanacsado/szigoru`, fallback file), `subject_of()` and companion folders from one source (F2 deferred list), `core/felkeszultseg/kalibracio.py` (`--rogzit` writes the W layer via `beallitas_iras`, not `os.toml`) | preset tests (`tests/preset_v2/`) reproduce v2 behaviour with the preset; defaults tests on a neutral vault · `test_tulajdonsagok`, `test_gepi_iras`, `test_felkeszultseg_*` | L (2.5 d) |

Order: WP1 merges first (it defines `Config`, roots and the helper marker; stage B agents code against its signatures). In
stage B the only shared surface is `config/os.toml`, split by section (WP6 owns W sections; WP1 is finished). After stage B a
single integrator runs `MOS_SZIGORU=1 bin/mos test` + `bin/mos app test`, rebuilds the shell, writes the NAPLO F3 entry.

## 9. Risks

| Risk | Mitigation |
|---|---|
| The suite is wired to the v2 layout (`tests/helpers.py:15-29, 70-78`) | portable marker in `alg_gyoker`; product-mode tests are new and opt in |
| Lazy `utak` changes error timing (a typo surfaces at first use, not at load) | `config.load` still expands every key whose roots are present; only workspace keys are deferred without a workspace |
| W allow-list too tight (a legitimate per-vault key rejected) or too loose (I5) | allow-list is data (`RETEG_JOG`), reviewed key by key against §1.3; violations are visible in Health, not silent |
| Shared worker lease changes D4 ("the worker dies with its core") | lease only extends life while another core holds one; `--sajat` eval workers keep exclusive behaviour; fallback in §4 |
| Relative `core.worktree` with older git or tools reading `vault.git/config` | git ≥ 2.x supports it; doctor compares the *resolved* worktree; trial clones stay absolute |
| Copy detection false positives on removable volumes | `kotet_uuid` + `inode`; ambiguous case asks instead of guessing |
| Sync-folder vaults lose the "folder carries its history" property | stated in the launcher dry-run and docs; backups still per workspace |
| `ytdlp` state moved out of `{modulok}` (worktree mixed code + data in v2) | WP2/WP3 grep for writes under `{modulok}`; product-mode test that nothing is written under `{os}` (I1) |
| Sandbox profiles assume a venv prefix | `PY_PREFIX`/`PY_BASE` from `{runtime}`; `test_homokozo` in product mode on a fake bundle (WP3) |
| Two cores writing `settings.toml` | optimistic concurrency in `beallitas_iras` (sha check), reload on change in F5 |
| Personal values leaking into the repo via the marker | marker gitignored + `export-ignore`; `mos portable init` writes paths only into the marker |
