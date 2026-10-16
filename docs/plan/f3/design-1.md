# F3 design 1 — Config + workspace, data-safety & compatibility first

Angle: **change the proven write paths as little as possible**. Every v2 path must resolve **byte-identically** in portable
mode, so the 3 982 Python tests stay green without edits. The product layout is a second *layout* of the same `[utak]`
keys, not a rewrite. New behaviour (workspace creation, migration) is **copy-only, journaled and dry-run first**, with
a single commit point. Sources: PLAN §0/§1.2/§4/§6/§7/§9, audit 02 §1/§4.4/§6/§7, audit 04 §1.2/§7/§8, audit 06
§A1/§A5/§B1/§B4, NAPLO F2.

Findings from the code that the design must handle (they are not all in the audits):

| # | Fact (code) | Consequence |
|---|---|---|
| C1 | `tests/helpers.alg_gyoker` copies the **real** `config/os.toml` into a fake root, (111 test files use it), and 71 test files call `config.load(…)` directly, mostly with an explicit dict such as `{"MOS_ROOT":…, "HOME":…}` (the process env is then ignored) | the layout must be chosen **without new env vars**, and the default for a non-bundle root must be v2 |
| C2 | `gepi_iras._klon` builds the D9 trial env from **unexpanded templates** in `cfg.table` (`MOS_VAR="{os}/var"`), and overrides only `MOS_VAULT/VAULT_GIT/RUN/YTDLP_GIT` | if `var` is derived from `{vault}`, the trial would get a *different* state dir. The trial env must pin **resolved** paths |
| C3 | `frame.trial_clone` runs `cp -c -R <vault> {tmp}/proba/<kor>/…` | with `{tmp}` inside `<vault>/.manifold/var`, the copy goes into its own subtree. Clone the vault **without `.manifold`** |
| C4 | `core/index/feloldas.SKIP_DIRS = {".obsidian",".trash",".git","node_modules"}`; `indexelo` walks every other dot folder | `.manifold/var/tmp/proba/*/` (full vault clones) would be indexed and become link targets. `.manifold` must be skipped by **every** vault walker (31 files in `core/`+`modulok/` use `os.walk`/`rglob`; not all walk the vault) |
| C5 | Steps inherit `os.environ` (allowlist `MOS_*`) and call `config.load()` again | the root selection must travel **only through env**; a settings file edited mid-run must not move `{run}`/`{tmp}` under a running core (two lock rooms mean L13) |
| C6 | Bundle rotation is a glob in `{backup}` (`snapshot.bundle_keszit`, `keep>0`); `[teljes_mentes]` versions are `cel/Manifold-<ts>` | two workspaces sharing a folder delete each other's backups. The v2 checkout and an [UNI] portable checkout **already share `~/Manifold-backup`** |
| C7 | `vault.git/config core.worktree` is absolute (`snapshot.Repo.init`) and the `{run}` journals hold vault paths | a copied or moved vault that carries `.manifold/var` would snapshot or replay against the **old** folder |
| C8 | Three volume checks compare against `cfg.root` (`teljes_mentes.ment:337`, `LemezFigyelo.tick:615`, `tasks._teljes_mentes_terv:139`) | in a bundle, an internal-disk target counts as "external". Compare against the vault instead |

## 1. Three roots and the layered config

### 1.1 Roots and layouts

| Root (placeholder) | Meaning | Portable (`hordozhato`, v2) | Product (`termek`) |
|---|---|---|---|
| `{os}` | code, read-only | `MOS_ROOT` or the parent of `core/` (unchanged) | `Manifold.app/Contents/Resources/manifold` |
| `{install}` | one per machine | `{var}` (so every install path equals the v2 path) | `{home}/Library/Application Support/Manifold` |
| `{workspace}` | per vault: holds `workspace.toml` and `schema.json` | `{vault}/.manifold` (only read; absent in tests) | `{vault}/.manifold` |
| `{var}` | per-workspace state on the vault's volume | `{os}/var` | `{workspace}/var` (or `{install}/workspaces/{workspace_id}/var`, §3.6) |
| `{vault}` | the Markdown folder | `{work}/Manifold` (v2 default; a missing folder keeps the gate closed) | **no default**: `MOS_VAULT` is required, otherwise `ConfigError` (an empty template would resolve to `.` = cwd) |

The layout is chosen by `config.elrendezes(root, env)`. It returns `MOS_ELRENDEZES` if set (`hordozhato|termek`, anything
else is a `ConfigError`). Otherwise it returns `termek` when `root` matches `*.app/Contents/Resources/<dir>`, and
`hordozhato` in every other case. Fake test roots (`{tmp}/work/os`) therefore stay portable with no edits (C1).

### 1.2 `[utak]` re-rooting (`config/os.toml`)

The base `[utak]` table keeps **every existing key**. Paths are rewritten over the roots so that, with `install = {var}`,
portable mode yields exactly the F2 strings. `[elrendezes.hordozhato.utak]` and `[elrendezes.termek.utak]` hold only the
keys that differ. They are merged over `[utak]` before any other layer.

| Key | Base formula (both layouts) | Portable override | Product override |
|---|---|---|---|
| `state tmp runs run szemelyes index vault_git ytdlp_git feladatok_db tanulas_db automatika_db video_bejovo fuzet_bejovo binaris_naplo fuzet video_jobs felulet` | unchanged (`{var}/…`, `{state}/…`) | — | — |
| `models` / `router_db` / `cache` | `{install}/models` / `{install}/router.sqlite` / `{install}/cache` | = `{var}/…` (same as v2) | Application Support |
| `vault_kepek` | `{var}/cache/vault-kepek` (per workspace; equals `{cache}/vault-kepek` in portable) | — | — |
| `install_run` / `install_state` / `install_runs` (new) | `{install}/run` / `{install}/state` / `{install}/runs` | = `var/run`, `var/state`, `var/runs` | AS `run/`, `state/`, `logs/` |
| `venv` | `{install}/venv` | `var/venv` | `{os}/runtime/venv` (bundle) |
| `ytdlp`, `staging`, `ytdlp_archivum`, `archive` | — | v2 values (`{modulok}/ytdlp`, `{os}/archive`) | `{var}/ytdlp`, `{var}/video/staging`, `{var}/video/archive`, `{var}/archive` |
| `backup_gyoker` (new) / `backup` | — / — | — / `{home}/Manifold-backup` | `{install}/backups` / `{backup_gyoker}/{workspace_id}` |
| `naptar_seged`, `hej_cli` | — | `{os}/Manifold.app/Contents/MacOS/Manifold` | `{os}/../../MacOS/Manifold` |
| `work` | — | `{os}/..` | `{vault}/..` |
| `install`, `workspace`, `var`, `vault` | — | see 1.1 | see 1.1 |

Other changes in `os.toml`:
- `[modellgazda] zar = "{install_state}/modell.lock"` (portable: `var/state/modell.lock`, identical).
- `[pillanat.vault] kizar` gains `".manifold/"`. Existing repositories receive it through `biztosit_kornyezet → write_exclude` at startup.
- `{workspace_id}` is a table placeholder, not an `[utak]` key. `Config.__init__` adds it from `data["workspace"]["id"]`. It never enters `cfg.utak`, so `teljes_mentes` cannot treat it as a path.

### 1.3 Layers and merge (`core/config.py`)

Precedence, lowest to highest: `os.toml` → `config/os.d/*.toml` (sorted, full trust) → `[elrendezes.<mod>]` →
**install** `{install}/settings.toml` → **presets** named in `workspace.toml` (`config/presets/<nev>.toml`, name
`^[a-z0-9-]+$`) → **workspace** `{workspace}/workspace.toml` → **env** (`MOS_<UTAK>`, as today). Tables deep-merge;
scalars and arrays replace. `MOS_CONFIG` keeps its v2 meaning: it replaces the base file.

```python
ELRENDEZESEK = ("hordozhato", "termek")
ID_MINTA = re.compile(r"^[0-9a-f]{32}$")
def elrendezes(root: Path, env: Mapping[str, str]) -> str
def load(environment: dict[str, str] | None = None) -> Config       # signature unchanged
# phase 1: base + os.d + layout → provisional table → resolve {install}
# phase 2: install layer (ENGEDELY_TELEPITES) → resolve {vault}, {workspace}; termek and empty vault → ConfigError
# phase 3: presets + workspace layer (ENGEDELY_MUNKATER); workspace_id = MOS_WORKSPACE_ID or [workspace] id,
#          ID_MINTA-checked (it is used in a path); termek and no id → ConfigError("workspace not initialised")
# phase 4: [workspace] allapot_hely == "telepites" → utak.var = "{install}/workspaces/{workspace_id}/var"
class Config:                                     # __init__(root, data, environment, source) unchanged (gepi_iras builds one)
    elrendezes: str                               # data["_elrendezes"]
    retegek: dict[str, str]                       # "naplo.ut" -> "os" | "os.d/50-x.toml" | "telepites" | "preset:x" | "munkater" | "env"
    elutasitott: list[tuple[str, str, str]]       # (layer, key, reason): shown by doctor/Health, never fatal
```

The merged result is written into `data["utak"]` and `data[<section>]`. `Config(root, cfg.data, env)` therefore
reproduces the same config: the D9 trial path in `gepi_iras` keeps working.

### 1.4 Which keys belong to which layer (enforced by `_reteg_szur`)

| Layer | Allowed (dotted patterns) | Notes |
|---|---|---|
| **os / os.d / env** | everything | the only source of `[pillanat.*]`, `[homokozo]`, `[router]`, `[meres]`, `[modellek.*]`, `[kalibracio.*]` (the D9 threshold must never be lowered by a user file), `[core]`, `[feladatsor]`, `[index]`, `[elrendezes.*]`, `[sema] vault`, `[mentes] kodtar`, and `[utak]` except the two below |
| **install** `settings.toml` (the user, machine-wide) | `utak.backup_gyoker`, `utak.models`, `mentes.{ido_perc,allapot_*,megtartott_bundle≥3}`, `teljes_mentes.{cel,figyelo_be,figyelo_ora,megtartott}`, `modellgazda.min_szabad_szazalek`, `keret.*`, `aktivitas.*`, `felulet.*`, `modulok.*`, `adatvedelem.*`, `munkaterek."<id>".fuzet.mappak` | paths **outside** the vault live here only, keyed by workspace id (F2 `[fuzet] mappak`) |
| **workspace** `workspace.toml` + its presets (**untrusted**: vaults are shared and synced) | `workspace.*`, `migracio.regi_var`, `vault.kisero_elotag`, `naplo.*`, `sablon.*`, `kartya.{mappa,utotag}`, `kviz.mappa`, `osszefoglalas.{mappa,utotag}`, `fuzet.{cel_mappa,elmelet_mappa,szakasz}`, `media.*`, `pdf.tags.*`, `video.{vault_mappa,tema_minta,kizart_mappak}`, `naptar.szotar.*`, `asszisztens.{*_kizart,tantargy_nevek}`, `kapuk.kihagyott_szakaszok`, `sema.mod` | strings ≤ 512 characters; vault-relative paths pass a `norm_path`-like check (no `..`, not absolute); regexes ≤ 200 characters and must compile. The type must match the base value. A rejected key is ignored and reported |

A shared vault's `workspace.toml` therefore cannot redirect `sandbox_exec`, `ffmpeg`, `vault_git` or `backup`. It
cannot lower calibration either. The F5 Settings endpoints (`GET/POST /api/beallitasok`) will reuse these lists and
`cfg.retegek`. F3 needs no general TOML writer, because `workspace.toml` is written from a fixed template.

### 1.5 Environment variables

| Variable | Status | Set by |
|---|---|---|
| `MOS_ROOT`, `MOS_CONFIG`, `MOS_<UTAK>` (`MOS_VAULT`, `MOS_INSTALL`, `MOS_WORKSPACE`, …), `MANIFOLD_MODELL_ZAR` | unchanged meaning | shell / `bin/mos` / tests |
| `MOS_ELRENDEZES` | new, optional (auto-detected) | shell in a bundle; tests of product mode |
| `MOS_WORKSPACE_ID` | new; only `core.workspace letrehoz` (before the commit point) and pinned children | core |
| pinned `MOS_<UTAK>` (absolute), `MOS_ELRENDEZES`, `MOS_WORKSPACE_ID` | new behaviour, §2.3 | `core/__main__.py start` |

## 2. bin/mos and the shell give the core its roots (no hard-coded `var/`)

### 2.1 New `core/gyokerek.py`: the single source of process paths

```python
def folyamat_env(cfg: Config) -> dict[str, str]
    # HF_HOME={models}, HF_HUB_OFFLINE/TRANSFORMERS_OFFLINE=1 (setdefault), XDG_CACHE_HOME={cache},
    # UV_CACHE_DIR={cache}/uv, PIP_CACHE_DIR={cache}/pip, TMPDIR={tmp} (stays on the vault volume, as in v2),
    # PYTHONDONTWRITEBYTECODE=1
def biztosit_mappak(cfg: Config) -> None   # mkdir {tmp},{cache},{install_run}; .metadata_never_index in {var} and {install}
def rogzit(cfg: Config, environ: MutableMapping[str, str]) -> None
    # MOS_<KEY>=str(cfg.path(key)) for every [utak] key, plus MOS_ELRENDEZES and MOS_WORKSPACE_ID
def main(argv) -> int                      # `shell`: shlex-quoted `export` lines; `json`: the same as a dict
```

### 2.2 `bin/mos` (minimal diff; stays bash, works from the bundle)

- `VAR="${MOS_VAR:-$MOS_HOME/var}"` is used only by `runtime fetch/install` and `app *`, which run before a Python
  exists (portable only).
- `python_kereses`: `$MOS_PYTHON` → `${MOS_VENV:-$VAR/venv}/bin/python` → main-checkout venv → `$RT/python/bin/python3`.
- Lines 35–52 (hard-coded `HF_HOME`, `XDG_CACHE_HOME`, `UV/PIP`, `TMPDIR`, `mkdir var/…`, Spotlight marker) are replaced
  by `eval "$("$PY" -B -m core.gyokerek shell)"` for every Python command. Nothing writes under `$MOS_HOME` any more,
  except `runtime`/`app` in portable mode.
- Worktree mode (`.git` file, `MOS_BACKUP=var/backup`) is unchanged. New dispatch lines: `workspace` →
  `core.workspace`, `migral` → `core.migracio_var`.
- The `bin/mos.py` rewrite in PLAN §10 is **deferred**: porting the runtime installer adds risk without moving any data
  path.

### 2.3 Core start pins its roots (C5)

`core/__main__.py start`: `cfg = config.load()` → `gyokerek.rogzit(cfg, os.environ)` → `biztosit_mappak(cfg)` →
`os.environ.update(folyamat_env(cfg))` → `server.start(cfg=cfg, …)`. Steps, the worker and the trial clone then
resolve the **same absolute paths** even if `settings.toml` changes during the session. Path keys changed in Settings
take effect at the next workspace open (F5 shows "restart required"). In-process tests do not go through `__main__`.

`gepi_iras._klon` (C2): the env becomes `{f"MOS_{n.upper()}": str(self.cfg.path(n)) for n in utak}` plus the four
existing clone overrides. In v2 no `[utak]` key depends on `{vault}`, so this is equivalent; in product it is correct.

### 2.4 Shell

- `RootLocator.locate` → `(root: URL, termek: Bool)`. Candidates: `MOS_ROOT` → `Bundle.main.resourceURL/manifold`
  (`termek = true`) → the `.app`'s parent (portable, unchanged). `isValid` is unchanged (the bundle ships `bin/mos`).
- `CoreProcess.init(root:vault:port:titok:)` additionally sets `MOS_VAULT` (when given) and `MOS_ELRENDEZES=termek`
  (for a bundle). Until the F5 launcher exists, the product vault is the registry's `utolso` (a Swift JSON read of
  `workspaces.json`).
- The handshake gains the additive fields `vault`, `munkater_id`, `elrendezes`; the Swift parser already ignores
  unknown keys. The unmount watcher (`gyokertErint`, audit 04 H6) is fed the **vault** path from the handshake instead
  of the root.

## 3. Workspaces

### 3.1 Layout inside a vault

```
<vault>/.obsidian/                  created if missing (Obsidian compatibility); never written into if it exists
<vault>/.manifold/workspace.toml    [workspace] formatum=1, id (32 hex), nev, letrehozva, presetek=[], allapot_hely="vault",
                                    obsidian_letrehozva=bool; workspace keys imported once from .obsidian (§3.3)
<vault>/.manifold/schema.json       optional; [sema] munkater = "{workspace}/schema.json" wins over the shipped default
<vault>/.manifold/.gitignore        "*": a user's own git or Obsidian-Git never commits our state
<vault>/.manifold/var/{vault.git,state,run,runs,tmp,index,cache,…}   = {var} (v2 subpaths)
```

### 3.2 `core/workspace.py` (new; the name is fixed by PLAN §4, identifiers are Hungarian)

```python
@dataclass(frozen=True)
class Felmeres:                       # dry-run result, JSON for the launcher
    vault: str; letezik: bool; ures: bool; irhato: bool; fajlrendszer: str   # statfs f_fstypename
    felhoben: str | None              # "icloud" | "cloudstorage" | "dropbox" | None (path heuristics)
    kis_nagy_erzekeny: bool; szabad_bajt: int; md_db: int; obsidian: dict
    meglevo_id: str | None; reszleges: bool   # .manifold/var exists without workspace.toml (an interrupted create)
    akadaly: list[str]; figyelmeztetes: list[str]; letrehozando: list[str]
def felmer(vault: Path, alap: Config) -> Felmeres
def letrehoz(vault: Path, alap: Config, *, nev: str | None = None, uj_mappa: bool = False, log=…) -> dict
def nyit(cfg: Config) -> list[str]                # startup check before App(): copy/move detection (§3.5)
def azonosit(vault: Path) -> str | None
def regiszter(install: Path) -> dict; def regiszter_ir(install: Path, fn) -> dict   # under {install_run}/workspaces.lock
# CLI: python -m core.workspace felmer|letrehoz|lista|elfelejt <vault> [--json] [--igen]   (default: felmer)
```

**Blocking (`akadaly`):** the vault is inside `{os}` or `{install}`; it is inside another workspace or contains one (nested vaults would be snapshotted twice); not writable; `uj_mappa` with a missing parent (no folder is ever created under an unmounted `/Volumes/X`); `allapot_hely="telepites"` on another volume.

**Warnings:** a non-APFS volume means reduced mode, because D9 trial clones fail (`gepi_iras` already answers 503); a
cloud-synced folder (§3.6); low free space.

**`letrehoz` steps.** Each step is idempotent, so a rerun after a crash completes the work. The commit point is step 6.
1. `felmer`; stop on any `akadaly`.
2. `uj_mappa` → `mkdir`. Create `.obsidian/` only if missing, and record that it was created.
3. `.manifold/.gitignore`, `.manifold/var/{state,tmp,run,runs,cache,index}`, `var/.metadata_never_index`.
4. `cfg = config.load({…, "MOS_VAULT": v, "MOS_WORKSPACE_ID": uj_id})`. Then, under `frame.run_lock(cfg)`:
   `snapshot.repos(cfg)["vault"].init()` (writes `info/exclude` with `.manifold/`) and
   `repo.commit("Workspace created", {"Mos-Forras": "kezi"})` (`commit()` already handles a repository without HEAD).
5. Import from `.obsidian` (§3.3), in memory only.
6. **Commit point:** `tartos.atomi_ir(.manifold/workspace.toml)`. Until it exists, the folder is not a workspace;
   `felmer` reports `reszleges` and `letrehoz` resumes.
7. Registry entry. The registry is only an index; `workspace.toml` is the source of truth.

**Undo ("Remove Manifold data")** moves `.manifold/` to the Trash through the shell's `--kuka`, removes `.obsidian/`
only if it was created and is still empty, and drops the registry entry. The vault's own files are untouched.

### 3.3 Obsidian values (B4)

`templates.json` `folder` becomes `[sablon] mappa`; `daily-notes.json` `folder/format/template` becomes `[naplo] ut/sablon`.
They are read **once** at creation. `.obsidian/app.json` stays live-read by `csatolmany`/`vaultio` (unchanged). Nothing is
ever written into `.obsidian`.

### 3.4 Registry `{install}/workspaces.json` (atomic write, `{install_run}/workspaces.lock`)

`{"formatum":1, "utolso":"<id>", "munkaterek":{"<id>":{"vault":"/abs", "kanonikus":"<F_GETPATH>", "nev":"…",
"letrehozva":"…", "megnyitva":"…", "allapot_hely":"vault", "regi_var":null}}}`. If the file is lost, only the
"recent" list is lost.

### 3.5 The gate, exclusions, and copy/move safety

- **`.obsidian` gate: unchanged.** `Vault.root`, `frame.vault_letezik`, `tmp_maradekok`, doctor and `binaris_naplo`
  keep checking for `.obsidian`, and creation guarantees it exists. In product mode, `config.load` additionally requires
  `workspace.toml`; without it the shell shows the launcher instead of starting a core. An unmounted drive behaves as in
  v2: missing path, gate closed.
- **Snapshots:** `.manifold/` is in `[pillanat.vault] kizar`; `norm_path` already blocks dot segments in the API.
- **Walkers (C4):**
  - `feloldas.SKIP_DIRS |= {".manifold"}` covers the index, link resolution and FSEvents filtering (`_ervenyes`).
  - Each vault-walking `os.walk/rglob` site (of the 31 files) gets a shared `vaultio.REJTETT_MAPPAK` prune, or a proof that it already
    prunes all dot folders.
  - A ratchet test fails on any new vault walk that skips neither.
- **Trial clone (C3):** `frame.trial_clone` uses a new `apfs_clone_vault(src, dst, kihagy=(".manifold",))`, which
  creates `dst` and runs `cp -c -R` per top-level entry. Without `.manifold` the result is identical to v2.
- **`vaultkivul`: unchanged.** `.manifold` counts as inside the vault, so exports, external-backup targets and (new
  check in `mentes`) a user-chosen `backup_gyoker` inside the vault are refused. That is the intended behaviour.
- **Copy/move (C7), `workspace.nyit(cfg)`.** It runs in `server.start` after the core lock and **before** `App()`
  starts recovery; product mode only. If the registry knows `id` at another canonical path:
  - **Copy:** the original still exists with the same id. The copy gets a new id (atomic rewrite), its
    `.manifold/var/run/` journals are renamed to `run.masolat-<ts>/` (quarantined, never replayed), and
    `Repo.init()` resets `core.worktree`.
  - **Move:** the original is gone. Update the registry and run `Repo.init()`.

  In portable mode a `core.worktree` mismatch is only a doctor warning; v2 behaviour is kept.

### 3.6 Cloud-synced vaults

SQLite and git under iCloud or Dropbox sync are a corruption risk. If `felmer` reports the vault is cloud-synced
**and** `{install}` is on the same volume, the default becomes `allapot_hely="telepites"`, i.e.
`{install}/workspaces/<id>/var`. That keeps the same volume, so `clonefile` and atomic rename still work. On a
different volume the result is a warning plus reduced mode.

## 4. Locks

| Lock | v2 | Portable (identical) | Product |
|---|---|---|---|
| `core.lock` (single core) | `{run}/core.lock` | `var/run/core.lock` | `<vault>/.manifold/var/run/core.lock`, keyed by the vault through the inode |
| vault guard (new) | — | `{install_run}/vault-<k>.lock` | `{install_run}/vault-<k>.lock`; `k = sha256(F_GETPATH(vault))[:32]` (canonical case, survives remounts); catches `allapot_hely="telepites"` and two path spellings |
| `kor.lock` (writer frame) | `{run}` | same | per workspace |
| `modell.lock` (one model per machine, L23) | `{state}/modell.lock` | `var/state/modell.lock` | `{install_state}/modell.lock` |
| `worker.lock` / `worker.pid` (one worker) | `{run}/worker.*` | `var/run/worker.*` | `{install_run}/worker.*` |
| `workspaces.lock` | — | `var/run/…` | `{install_run}/…` |

Code changes: **`server._core_zar`** takes `{run}/core.lock`, then the vault guard; if the second is busy it releases the first and returns the same `{"foglalt":true,"pid","vault"}` handshake (exit 75, shell unchanged); the lock content gains the workspace id. **`visszaallitas._core_fut`** probes both locks (`LOCK_SH|LOCK_NB`, read-only). **`modell/beallitas`** default `zar`; **`worker.py:359-372`** and **`kliens.pidfajl`** use `install_run`; `worker.log` goes to `install_runs`.

The worker is workspace-agnostic: it only reads install-layer sections (enforced by §1.4).

**Two cores at once:** separate port, secret, `{run}`, `kor.lock` and task queue; shared models, `router.sqlite` (WAL),
model lock and worker. The worker belongs to the core that started it. When that core exits, the others restart it on
demand (existing T183 path). V1 may still open one workspace per window and process (R8).

## 5. Backups

- **Internal (`mentes.py`): no rotation logic changes.**
  - Product: `backup = {backup_gyoker}/{workspace_id}`, so per-workspace rotation follows from the folder.
    `backup_gyoker` is install-level, so a user-chosen target ("Time Machine disk") still gets per-workspace
    subfolders.
  - New owner marker `{backup}/.manifold-mentes.json` (`munkater_id`, `vault`). Written when the folder is empty; a
    **foreign** marker means `keep=0` (no rotation) plus a `mentes-hiba.json` warning. A legacy folder without a
    marker keeps v2 rotation, so portable mode is unchanged.
  - Doctor (read-only) warns when the newest `vault-*.bundle` holds heads that are missing from this `vault.git`
    (C6: `~/Manifold-backup` shared by v2 and [UNI]).
- **External (`teljes_mentes.py`, `tasks.py`):**
  - New `adat_kotet(cfg) = cfg.path("vault").stat().st_dev` replaces the three `cfg.root` comparisons (C8). In
    portable mode code and vault share the SSD, so behaviour is identical.
  - Product: `forrasok` drops the `os` root (the read-only bundle is reinstallable). `router_db` stays an extra root.
    `{var}` sits under the vault root and its transient keys are excluded by absolute path (`p in kihagyott`, as
    today).
  - Product versions go to `cel/<workspace_id>/Manifold-<ts>`, so `_ritkit` and `kesz_valtozatok` are per workspace.
    `jegyzek.json` gains `munkater_id` and `elrendezes`.
  - Restore keeps the v2 sibling layout. A key-mapped product restore (vault → chosen folder, `router_db` → install
    only if absent) is F8.
- **`visszaallitas`:** unchanged apart from §4.

## 6. Doctor and health in product mode

`ellenoriz(cfg, environment, home, futo_python=None, *, termek: bool | None = None)`, where `termek` defaults to
`cfg.elrendezes == "termek"`. Every `Eredmeny` gains `osztaly: "termek" | "fejleszto"`; the CLI prints both, F7 Health
filters.

| | Checks |
|---|---|
| **Skipped in product** | `bin/mos` root check (replaced by bundle integrity, `epites.json`); var symlink; pyvenv and shebangs; requirements lock, runtime pins, `@napi-rs`; the `SAJAT_MINTA` ban on `/Applications/Manifold.app`; `HOME_NEM_ENGEDETT` for `Library/Application Support/Manifold` |
| **Kept** | volume (now also: `{tmp}`, `{fuzet_bejovo}`, `{video_bejovo}`, `{staging}` share the vault's `st_dev`); vault; repositories; schema; backups; index; models; calendar; Spotlight on `{var}` and `{install}`; core running; trial clones |
| **New** | `workspace.toml` valid and its id registered; `core.worktree == vault`; `.manifold/` in `info/exclude`; cloud-synced vault warning; free space on the vault and install volumes; keys rejected by a layer (`cfg.elutasitott`); `{install}` writable; lock locations install-level; foreign backup bundles (§5) |

## 7. Portable mode (the developer's SSD)

Portable mode is chosen automatically for any non-bundle root, or with `MOS_ELRENDEZES=hordozhato`. With
`install = {var}` every v2 path is unchanged: `var/` next to the code, the vault next to `{os}`,
`~/Manifold-backup`, worktree mode, `runtime/` and `bin/mos runtime …`. The developer's personal conventions come
through configuration only:

- `config/os.d/` is git-ignored except its README. `bin/mos preset v2-kompat` (WP5) copies
  `config/presets/v2-kompat.toml` to `config/os.d/50-v2-kompat.toml`, which loads at full trust as the base layer. This
  layer may carry `[fuzet] mappak` with `{work}` paths.
- A workspace layer also applies in portable mode if the real vault later gets `.manifold/workspace.toml`, for example
  through the F8 v2-import.
- **Neutralising `os.toml` (deferred F2 items) becomes a mechanical step** after this design lands:
  1. move the values into `v2-kompat.toml`;
  2. `alg_gyoker(tmp, preset="v2-kompat")` copies it into `{fake}/config/os.d/` (default on);
  3. the ~40 convention-defining tests move to `tests/preset_ai01/`.

  All 71 + 111 fixture sites keep v2 values with no edits (C1).

## 8. Migrating an existing `var/` to the new layout (dry-run, reversible)

This migration moves the layout only. Moving settings and the schema into `workspace.toml` is the v2-import (F8), which
builds on it.

`core/migracio_var.py` (new):

```python
@dataclass
class Lepes: kulcs: str; forras: str; cel: str; mod: str; bajt: int; megj: str
#   mod ∈ {"klon" (cp -c, same volume), "masol", "sqlite" (ro + .backup()), "git" (cp -c -R + fsck), "hivatkozas", "kihagy"}
def terv(regi: Config, uj: Config) -> list[Lepes]       # diff of resolved [utak] paths; tmp/run/cache are skipped
def vegrehajt(lepesek, naplo: Path, *, log) -> dict      # copy-only; the source is opened read-only
def ellenoriz(lepesek) -> list[str]                       # sha256 per file; sqlite integrity_check + row counts; git HEAD + fsck
def visszavon(naplo: Path) -> dict
# CLI: bin/mos migral terv|vegrehajt|visszavon --vault V [--install I] [--modellek-masol] [--json] [--igen]   (default: terv)
```

**Steps.**
1. **Preconditions:** no core on the target; the source `core.lock` and `kor.lock` are taken **exclusively through
   read-only fds** for the whole run, so a portable core cannot start mid-copy and nothing is written to the old `var/`;
   `worker.lock` free; the target is not a workspace, or is `reszleges` (resume); free space checked (a same-volume
   clone costs ~0 bytes).
2. Copy everything into `.manifold/var.uj-<ts>/`, verify it, then `rename` it to `.manifold/var` (atomic, same volume).
3. **Install items:** `router.sqlite` copied with `.backup()`; `models` by default a reference (install `settings.toml
   [utak] models = "<old>/models"`, 15–50 GB not duplicated; `--modellek-masol` copies); backup bundles are not copied
   (the old `~/Manifold-backup` stays as it is).
4. `Repo.init()`, then `workspace.toml` with `[migracio] regi_var` (**commit point**), then the registry entry.

**Journal:** `{install}/migracio/<ts>/{terv.json,naplo.jsonl}`, appended atomically per step.

**Rollback:** before the commit point, `.manifold/var.uj-*` is renamed to `.manifold.visszavont-<ts>`. After it,
`.manifold` is renamed the same way and the registry entry is removed. Nothing is deleted. The old `var/` is never
written, so after a rollback portable mode resumes exactly where it was.

**Split-brain guards (read-only):**
- A **portable** core refuses to start when `<vault>/.manifold/workspace.toml` has `regi_var` equal to its own `{var}`.
  The override is `MOS_REGI_VAR_ENGED=1`.
- A **product** core probes `<regi_var>/run/core.lock` with a shared lock and refuses while v2 or [UNI] portable is
  running on that vault.

## 9. Implementation plan (disjoint files; WP1 first, then 2–5 in parallel, then 6)

| WP | Files (owner only) | Tests to add | Effort |
|---|---|---|---|
| **WP1 Config layers** (opus) | `core/config.py`, new `core/gyokerek.py`, `core/__main__.py`, `config/os.toml` ([utak] re-root, `[elrendezes.*]`, `.manifold/` exclude, `zar`), `config/os.d/README.md`, `.gitignore`, `tests/helpers.py`, `tests/kezi/_kornyezet.py` (the AST guard must isolate the new keys) | `test_konfig_egyenertek` (golden: resolved `[utak]` + sections of a fake root equal `tests/adat/konfig/f2-hordozhato.json`, generated from the **F2 tree before any edit**; new keys only from an explicit list); `test_konfig_retegek` (order, allowlists, type mismatch, `ID_MINTA`, empty `vault` in termek → error, bundle auto-detect, `rogzit`, `os.d`) | L, 2 d. **Gate:** golden test green before anything else merges |
| **WP2 Workspace + exclusions** (opus) | new `core/workspace.py`; `core/frame.py` (`apfs_clone_vault`); `core/gepi_iras.py` (`_klon` env only); `core/index/feloldas.py`; `core/vaultio.py` (`REJTETT_MAPPAK` constant); the remaining walker sites in `core/` and `modulok/` | `test_munkater_letrehozas` (empty folder; existing Obsidian vault byte-identical outside `.obsidian/.manifold`; idempotent rerun; crash after each step → resume; nested/inside-install refused; first commit `kezi`; `git status` ignores `.manifold`); `test_bejaras_manifold` (a planted full clone under `.manifold/var/tmp/proba/` is invisible to index, links, hygiene, binary log, card sync, video match); `test_proba_klon_manifold` (no recursion, clone without `.manifold`, trial env = resolved paths); copy/move detection | L, 2 d |
| **WP3 Locks + startup** (opus) | `core/server.py` (`_core_zar`, vault guard, handshake fields, `workspace.nyit` call); `core/visszaallitas.py`; `core/modell/{beallitas,worker,kliens}.py` | `test_zarak_telepites` (two workspaces, one install: one model lock, shared `worker.pid`, `core.lock` per vault, a case-variant path to the same vault → 75); `tests/multi_user/test_ket_core.py` (subprocess `core_pelda()` ×2: disjoint trees, the other core's secret → 403, foreign vault path refused) | M, 1 d |
| **WP4 Backups** (sonnet) | `core/mentes.py`, `core/teljes_mentes.py`, `core/tasks.py` (`_teljes_mentes_terv`) | `test_mentes_munkater` (per-id folders, owner marker: foreign → no rotation, legacy → v2 rotation; `backup_gyoker` in the vault refused; `adat_kotet` with a monkeypatched `st_dev`; product `cel/<id>`, no `os` root) | M, 1 d |
| **WP5 Doctor + entry points** (opus) | `core/doctor.py`, `bin/mos`, `shell/Sources/{RootLocator,CoreProcess,AppController}.swift` | `test_doctor_termek`; `test_mos_es_shell` additions (`core.gyokerek shell` output, no writes under a read-only fake bundle `chmod -R a-w`); `tests/fresh_install/test_alap.py` (bundle-shaped root, fake HOME, no `var/`: `workspace letrehoz` → core subprocess → note → snapshot → backup → restore) | M–L, 1.5 d |
| **WP6 var migration** (opus, after WP2) | new `core/migracio_var.py` (the `bin/mos` dispatch line is added by WP5) | `tests/migracio/test_var_migracio.py` (dry-run writes nothing: tree hashes of source and target; execute + verify; crash at each step → resume or rollback; old `var/` byte-identical afterwards; split-brain guards) | L, 2 d |

**Keep green throughout:**
- the full `MOS_SZIGORU=1 bin/mos test` and `bin/mos app test`;
- in particular `test_visszaallitas`, `test_mentes*`, `test_teljes_mentes*`, `test_gepi_iras*`, `test_frame*`,
  `test_eletciklus`, `test_leallas`, `test_lepes_kapu` (no new non-`MOS_` variable carries a secret),
  `test_kezi_kornyezet`, `test_doctor` and `test_core_api`.

**Integration gate:** the full suite plus `fresh_install`, `multi_user` and `migracio`, with a NAPLO entry. The
convention-site work (schema mode, `subject_of()`, companions from one source, the `os.toml` neutral flip in §7) is a
follow-up WP7 on top of WP1; it must not change resolved values until the `os.d` fixture lands.

## 10. Risks

| # | Risk | Mitigation |
|---|---|---|
| K1 | A walker misses `.manifold`, so trial clones are indexed, linked or turned into cards | `SKIP_DIRS`, the shared constant, a ratchet test and a planted-clone behaviour test (WP2) |
| K2 | Trial-clone recursion or a changed trial state dir (C2, C3) | `apfs_clone_vault`; pinned resolved env; equivalence test against the v2 clone tree |
| K3 | An untrusted `workspace.toml` (shared vault) redirects tools or lowers D9 | per-layer allowlists, type, length and regex checks, `ID_MINTA`; rejected keys are reported, never applied |
| K4 | Settings changed mid-run give the core and its steps different `{run}` (L13) | `gyokerek.rogzit` pins absolute paths at core start; path keys apply only at reopen |
| K5 | A copied or moved vault carries a stale `core.worktree` and journals (C7, H12) | `workspace.nyit` before recovery: new id, journal quarantine, `Repo.init`; doctor check |
| K6 | Backup rotation collisions (C6), including v2 and [UNI] sharing `~/Manifold-backup` today | per-id folders, owner marker (product), doctor foreign-bundle warning; NAPLO note telling the developer to set a separate `MOS_BACKUP` for [UNI] portable now |
| K7 | Split-brain: v2 (or portable) and product run on one vault | read-only lock probe of `regi_var`; portable refusal via `regi_var`; documented. v2 code itself cannot be taught |
| K8 | Cloud-synced vault corrupts SQLite or git | detection; `allapot_hely="telepites"` on the same volume; otherwise reduced mode with a warning |
| K9 | Fixture drift: tests copy `os.toml` (C1) | auto layout = portable; the golden equivalence test gates WP1; the `os.d` mechanism handles the later neutral flip |
| K10 | `F_GETPATH` is unavailable or fails, giving a weak vault key | fall back to `st_dev:st_ino`; the in-vault `core.lock` remains the primary guard in product |
| K11 | The worker's lifetime is tied to the first core | existing T183 respawn; F6 may later make the worker a shell child |
| K12 | Non-APFS vault (exFAT, SMB): `clonefile` or `renamex_np` unsupported | warning from `felmer` and doctor; D9 trial answers 503 (existing); a no-fallback copy stays forbidden (`tartos`) |
| K13 | Install path contains a space (`Application Support`) | covered by `fresh_install` (sandbox `-D` parameters, git `core.worktree`, `bin/mos` quoting) |
