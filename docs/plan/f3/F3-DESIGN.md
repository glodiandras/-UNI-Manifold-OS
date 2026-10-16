# F3 — Config + workspace: final design (judged merge of design-1 and design-2)

Date: 2026-10-16. Inputs: `docs/plan/f3/design-1.md` (data-safety first), `docs/plan/f3/design-2.md` (operations first), checked
against the code of this repo (citations `path:line` are to this repo after F2). This document replaces both designs as
the F3 contract. Identifiers stay Hungarian without accents; user-facing text is English.

## 0. Verdict

| Criterion (0–10) | D1 | D2 | Reason |
|---|---|---|---|
| (a) Data safety, fidelity to proven write paths | **8** | 7 | D1 keeps every write path and pins resolved paths for the trial clone, children and steps. It also adds a golden equivalence gate and a copy-only migration. Its "vaultkivul unchanged" would refuse the default card export, and its journal quarantine rests on a wrong premise (§1). D2 has the right invariants (I1–I8), the vaultkivul fix and `binaris_naplo`/FSEvents exclusions, but it adds risk: a relative `core.worktree`, an asynchronous first commit (mixed commit), `kodtar=""` (cwd probe) and a worker lease that changes D4 |
| (b) Fitness for the Obsidian-like product | 6 | **8** | D2: launcher dry-run with result codes, demo, `formatum`/`olvaso_min` for downgrades, per-vault module switches, `.gitignore "var/"` so a user's own git can track settings, README in `.manifold`. D1 is correct but thinner (no format/downgrade story, no demo) |
| (c) Installer / operations realism | 7 | **8** | D2: App Translocation, install-update pre-copies, stable Health `kod`/`javitas` ids, sync-folder state in the registry (not in the untrusted vault). D1: realistic minimal `bin/mos`, bundle auto-detect, cloud-sync handling, but no update/format story |
| (d) Implementable in phases by agents with tests | **8** | 6 | D1: stage-A gate (golden test), disjoint WPs, concrete tests. D2: product is the default in a checkout, which breaks the 50 test files and 47 `core/`+`modulok/` call sites that run `config.load()` on the repo root (CI/fresh checkout). D2 also ports `bin/mos` fully, puts 13 files in WP2 and adds a TOML writer that F3 does not need |
| (e) The developer's v2 layout keeps working via config | **8** | 5 | D1: auto-detected portable mode, byte-identical paths, preset mechanism. Weak points: it keeps `vault = {work}/Manifold` (the [UNI] checkout resolves to the real vault), its `os.d` layer leaks into real-root tests, and a shared `~/Manifold-backup` gets only a NAPLO note. D2: needs a marker file. Without it the mode is product. It removes `{work}` although `v2-kompat.toml` uses it (→ `ConfigError`) and moves the portable model lock. Its "no `.manifold` in a v2-managed vault" insight is adopted |
| **Total** | **37** | 34 | D1 is the skeleton. D2 supplies product, operations and invisibility details |

## 1. Claims checked against the code (they decided the merge)

| Claim | Verdict | Consequence |
|---|---|---|
| D1 C1: 111 test files use `alg_gyoker`/`alg_core`, 71 call `config.load(…)` mostly with an explicit dict (`tests/helpers.py:15-29,70-78`) | ✔ — and **50 test files + 47 sites in `core/`/`modulok/` call `config.load()` on the process env** (the real repo root under `bin/mos`) | layout must be auto-detected (non-bundle root ⇒ portable); tests must not see the developer's own layer |
| D1 C2: the trial clone env is built from unexpanded templates (`core/gepi_iras.py:536-540`) | ✔ | with `var` derived from `{vault}`, the clone would get a different state dir → pin **resolved** paths |
| D1 C3/C4 + D2: `cp -c -R <vault>` into `{tmp}` (`core/frame.py:273-291`); `SKIP_DIRS` lacks `.manifold` (`core/index/feloldas.py:38`, `indexelo._ervenyes:63-67`); `binaris_naplo.KIHAGY` (`core/binaris_naplo.py:55`) | ✔ | clone without `.manifold`; every vault walker prunes it (31 files contain `os.walk`/`rglob`) |
| D1 C6: bundle rotation by glob (`core/snapshot.py:787-789`, `core/mentes.py:89`) | ✔ | per-workspace folders + a guard that never deletes foreign bundles |
| D1 C7: a moved/copied vault would snapshot or replay against the old folder | ✘ mostly | every Manifold git call passes `GIT_WORK_TREE` from config (`core/snapshot.py:157-161`); rename and machine-write journals are vault-relative (`core/atnevezes.py:104-105`, `core/gepi_iras.py:360-364`). A stale `core.worktree` only misleads external tools. **Do not quarantine journals of a copy** (they describe the copied bytes; recovery on the copy is correct) |
| D1 C8: three volume checks compare with `cfg.root` (`core/teljes_mentes.py:337,615`, `core/tasks.py:139`) | ✔ | compare with the vault (and `{var}` when outside it) |
| D1: "`vaultkivul` unchanged is intended" | ✘ | the default card export goes to `{szemelyes}/export/*.apkg` (`core/kartya_api.py:336-343`); under `<vault>/.manifold/var` it would be refused. Adopt D2's fix inside `vaultkivul` (§3.6) |
| D2: relative `core.worktree` makes moves free | unnecessary | `GIT_WORK_TREE` already wins; keep absolute, re-run the idempotent `Repo.init()` on open when it differs |
| D2: `[mentes] kodtar = ""` | ✘ introduces a bug | `Path(cfg.expand(""))` is the cwd (`core/mentes.py:137-139`); keep `"{os}"` (a bundle has no `.git` → `None`) |
| D2: first commit of an opened vault as a queued task | ✘ | the first editor frame would commit the whole vault under an editor message (mixed commit, L13/L16). The first commit is synchronous, before the commit point, with progress |
| D2: the worker is adopted via the pid file and lost when its core quits (`core/modell/kliens.py:256-271`) | ✔ | F3: install-level pid/lock + one retry after respawn; the lease is deferred |
| Vault-specific state in the code tree: `[pillanat.vault] kivetelek` (`config/os.toml:75`), `[sema] vault` (`:94`), `ytdlp` worktree in `{modulok}` (`:24`) | ✔ (only D2 moves `kivetelek`) | product overrides per workspace |
| F2 keys still carry the developer's values as explicit defaults: `[vault] kisero_elotag` (`config/os.toml:65`), `[video] tema_minta` (`:911`), `kizart_mappak` (`:909`), `[naptar.szotar]` (`:203`), `[asszisztens] kartya_kizart` (`:992`) | ✔ | WP6 flips them to neutral; `v2-kompat` preset keeps them |
| Doctor: `SAJAT_MINTA` no longer bans `/Applications` (`core/doctor.py:23`) but `HOME_NEM_ENGEDETT` still bans `Library/Application Support` (`:366-367`); volume and var-symlink rules assume `{os}/var` (`:735-753`) | ✔ | product mode in WP5 |

## 2. Layout and layering

### 2.1 Roots and layouts

| Root | Meaning | Portable (`hordozhato`) = v2 | Product (`termek`) |
|---|---|---|---|
| `{os}` | code, read-only | the checkout (`MOS_ROOT` or the parent of `core/`) | `Manifold.app/Contents/Resources/manifold` |
| `{install}` | one per machine (models, calibration, locks, registry, backups root) | `= {var}` (so every install path equals the v2 path) | `{home}/Library/Application Support/Manifold` |
| `{vault}` | the Markdown folder | **no default any more**: `MOS_VAULT` or the install layer `[utak] vault` (F2 deferred item: a checkout no longer resolves to the real vault) | `MOS_VAULT` (shell, from the launcher/registry) |
| `{workspace}` | per-vault config dir | `{vault}/.manifold`, **read only if it exists; a portable core never creates it** | `{vault}/.manifold` |
| `{var}` | per-workspace state, on the vault's volume | `{os}/var` | `{workspace}/var`; `{install}/workspaces/{workspace_id}/var` when the registry says `allapot = "telepites"` (sync folders, §3.7) |
| `{workspace_id}` | table placeholder (not an `[utak]` key) | from `workspace.toml` if present, else unset | `[workspace] id` (32 hex) |

Layout: `config.elrendezes(root, env)` → `MOS_ELRENDEZES` (`hordozhato|termek`, else `ConfigError`). Otherwise `termek` iff
`root` matches `*.app/Contents/Resources/manifold`, else `hordozhato`. Fake test roots stay portable without edits. A portable
layout inside an `.app` is refused unless Developer mode (`core/fejleszto.aktiv`).
**Invariant I1 (product):** every writable `[utak]` key resolves outside `{os}`; `load` raises `ConfigError(kod="iras_a_kodba")` otherwise.

### 2.2 Layers (later wins; tables deep-merge, scalars and arrays replace)

1. **S** `config/os.toml` (shipped) with `[elrendezes.termek]` deltas merged first in product. The base tables hold the
   portable (= v2) values, so `Config(root, raw_data, env)` keeps resolving v2 paths.
2. **P(I)** presets named by the install layer (`[telepites] presetek`), filtered by the install allow-list.
3. **I** `{install}/settings.toml`, overridable by `MOS_SETTINGS` (path; empty string = no install layer). In portable mode this is `{os}/var/settings.toml` (inside the gitignored `var/`, so nothing personal enters the repo).
4. **P(W)** presets named by `[workspace] presetek`, filtered by the workspace allow-list.
5. **W** `{workspace}/workspace.toml` (only if it exists). This layer is **untrusted**, because vaults are shared, synced and downloaded.
6. **E** `MOS_<UTAK>` as today (`core/config.py:56-57`) plus `MOS_ELRENDEZES`, `MOS_WORKSPACE_ID`, `MOS_SETTINGS`.

Presets live in `{os}/config/presets/<nev>.toml` (name `^[a-z0-9-]+$`); a sibling `<nev>.schema.json` may provide a schema.
A TOML syntax error in I or W is **fatal for that workspace** (`ConfigError(kod="settings_toml_hibas"|"workspace_toml_hibas")`;
a silently dropped W layer would change schema and write rules under the user). A key that a layer may not set, or that
fails validation, is ignored and recorded in `cfg.elutasitott` (shown by doctor/Health; never fatal).

### 2.3 Which layer may set which key (`config.RETEG_JOG`, data, reviewed key by key in WP1)

| Layer | May set | Never |
|---|---|---|
| **S** (os.toml) | everything | — |
| **I** settings.toml (machine + person) | `utak.backup_gyoker`, `utak.models`; `modellgazda.min_szabad_szazalek`; `keret.*`, `aktivitas.*`; `mentes.{ido_perc, allapot_*, megtartott_bundle (≥3), megtartott_migracio}`; `teljes_mentes.{cel, figyelo_be, figyelo_ora, megtartott}`; `naptar.{automatikus, szinkron_perc, tanulas_naptar}`; `adatvedelem.*`, `felulet.*`, `modulok.*`; `munkaterek."<id>".fuzet.mappak` (folders **outside** a vault, per workspace); `telepites.presetek`; every W key (as a machine default below W). **Portable only:** `utak.{vault, backup, llvm, sdk}`, plain `fuzet.mappak`, `modellgazda.zar`, `hordozhato.idegen_zarak` | `[utak]` code/state paths, `[pillanat.*]`, `[homokozo]`, `[router]`, `[meres*]`, `[modellek.*]`, `[kalibracio.*]`, `[kapuk]` thresholds, `[core]`, `[feladatsor]`, `[index]`, `[sema] vault/alap`, `[mentes] kodtar`, `[elrendezes.*]` |
| **W** workspace.toml (travels with the folder) | `workspace.{id, formatum, olvaso_min, nev, nyelv, presetek, obsidian_letrehozva}`; `vault.kisero_elotag`; `naplo.*`; `sablon.*`; `kartya.{mappa, utotag}`; `kviz.mappa`; `osszefoglalas.{mappa, utotag}`; `fuzet.{cel_mappa, elmelet_mappa, szakasz}`; `media.*`; `pdf.tags.*`; `video.{vault_mappa, tema_minta, kizart_mappak}`; `naptar.szotar.*`; `asszisztens.{*_kizart, tantargy_nevek}`; `kapuk.kihagyott_szakaszok`; `felkeszultseg.*` weights; `sema.mod`; `modulok.*` (per-vault switches, Obsidian's `core-plugins.json`) | anything above, any absolute path, `allapot` (the state location is decided by the registry on this machine, never by the vault) |

Validation (both I and W): type equals the base value's type (new keys only under `pdf.tags.*`, `naptar.szotar.*`,
`asszisztens.tantargy_nevek.*`); strings ≤ 512 characters; lists ≤ 256 items; regex keys ≤ 200 characters and must compile. Vault-relative
path values (`naplo.ut`, `*.mappa`, `sablon.mappa`, `fuzet.cel_mappa`, `media.*`, `video.vault_mappa`, `*_kizart` items) are
NFC, not absolute, no `..`, **no dot segment** (so no `.manifold/…` or `.obsidian/…` target). `workspace.id` matches
`ID_MINTA = ^[0-9a-f]{32}$` (it becomes a path segment). Preset names must name an existing file.

### 2.4 `[utak]` (base = portable = F2 values; product deltas in `[elrendezes.termek.utak]`)

| Key | Base (portable, = v2) | Product delta |
|---|---|---|
| `vault` | **removed** (from E or I) | from E only |
| `work` | `{os}/..` | `{vault}/..` |
| `var` | `{os}/var` | `{workspace}/var` (registry: `{install}/workspaces/{workspace_id}/var`) |
| `install` (new) | `{var}` | `{home}/Library/Application Support/Manifold` |
| `workspace` (new) | `{vault}/.manifold` | — |
| `install_run` / `install_state` / `install_logs` (new) | `{install}/run` / `{install}/state` / `{install}/runs` | — / — / `{install}/logs` |
| `state tmp runs run szemelyes index vault_git ytdlp_git feladatok_db tanulas_db automatika_db video_bejovo fuzet_bejovo binaris_naplo fuzet video_jobs felulet` | unchanged `{var}/…`, `{state}/…` | — (they follow `{var}`) |
| `models` / `cache` / `router_db` / `venv` | `{install}/models` / `{install}/cache` / `{install}/router.sqlite` / `{install}/venv` (= v2 strings) | — / — / — / `{os}/runtime/venv` (F9 may change) |
| `vault_kepek` | `{var}/cache/vault-kepek` (= `{cache}/vault-kepek` in v2) | — |
| `backup_gyoker` (new) / `backup` | `{install}/backups` / `{home}/Manifold-backup` | — / `{backup_gyoker}/{workspace_id}` |
| `ytdlp` (staging, archive follow it) / `archive` | `{modulok}/ytdlp` / `{os}/archive` | `{var}/ytdlp` / `{var}/archive` |
| `naptar_seged`, `hej_cli` | `{os}/Manifold.app/Contents/MacOS/Manifold` | `{os}/../../MacOS/Manifold` (the shell also sets `MOS_NAPTAR_SEGED`/`MOS_HEJ_CLI` = `Bundle.main.executablePath`) |
| `llvm`, `sdk` | `{runtime}/llvm`, `{runtime}/sdk` | `{install}/toolchains/llvm`, `…/sdk` |
| `modulok runtime app_dist ffmpeg node sandbox_exec` | unchanged | — (read-only, inside the bundle) |

Other S changes: `[pillanat.vault] kizar += [".manifold/"]` (existing repos get it through `write_exclude` at the next
`Repo.init`/startup); product `[pillanat.vault] kivetelek = "{workspace}/pillanat-kivetelek.json"` (missing file = `{}`);
`[sema] alap = "{os}/config/schema-default.json"` and product `[sema] vault = "{workspace}/schema.json"` (resolution chain:
workspace file → schema of the first named preset → `alap`); `[modellgazda] zar = "{install_state}/modell.lock"` (portable:
`var/state/modell.lock`, identical); `[mentes] kodtar = "{os}"` unchanged.

### 2.5 Config API (`core/config.py`)

```python
ELRENDEZESEK = ("hordozhato", "termek")
ID_MINTA = re.compile(r"^[0-9a-f]{32}$")
RETEG_JOG: dict[str, tuple[str, ...]]           # "telepites" | "telepites_hordozhato" | "munkater" -> dotted globs
class ConfigError(ValueError):                  # F4 error contract
    def __init__(self, uzenet: str, *, kod: str = "konfig_hiba", param: dict | None = None)
def elrendezes(root: Path, env: Mapping[str, str]) -> str
def reteg_ellenoriz(reteg: str, valtozasok: dict, alap: dict) -> list[tuple[str, str]]   # reused by F5 Settings writes
def load(environment: dict[str, str] | None = None, *, munkater: bool = True) -> Config
#  1 S + [elrendezes.<e>] → 2 I (+P(I)) → resolve {vault} → 3 W (+P(W)) → workspace_id → 4 registry allapot → Config
#  product & munkater & vault resolved & no workspace.toml & no MOS_WORKSPACE_ID → ConfigError(kod="nem_workspace")
class Config:                                   # __init__(root, data, environment, source=None) unchanged
    elrendezes: str; workspace_id: str | None   # from data["_meta"], so Config(root, cfg.data, env) reproduces cfg
    retegek: dict[str, str]                     # "naplo.ut" -> "os" | "os:termek" | "telepites" | "preset:v2-kompat" | "munkater" | "env"
    elutasitott: list[tuple[str, str, str]]     # (layer, key, reason kod)
    utak: dict[str, Path]                       # only resolvable keys (iteration-safe for teljes_mentes, rogzit, _klon)
    feloldatlan: dict[str, str]                 # key -> kod ("nincs_vault" | "nincs_workspace")
    def path(self, kulcs) -> Path               # raises ConfigError(kod=feloldatlan[kulcs]) for deferred keys
    def forras(self, *kulcs_ut: str) -> str     # provenance for Settings (⌘,) in F5
```

`load` still expands every key whose roots are present, so a typo fails at load. Only keys that depend on a missing
vault/workspace are deferred (portable: `vault`, `workspace`; product without a workspace: the whole `{var}` family). The worker
and `mos workspace lista` call `load(munkater=False)`.

### 2.6 Process roots: one resolution, pinned (`core/gyokerek.py`, `bin/mos`, shell)

```python
# core/gyokerek.py (new)
def folyamat_env(cfg) -> dict[str, str]   # HF_HOME={models}, HF_HUB_OFFLINE/TRANSFORMERS_OFFLINE=1 (setdefault), XDG_CACHE_HOME={cache},
                                          # UV_CACHE_DIR/PIP_CACHE_DIR={cache}/uv|pip, TMPDIR={tmp} (vault volume; fallback {install}/tmp
                                          # when no workspace), PYTHONDONTWRITEBYTECODE=1
def biztosit_mappak(cfg) -> None          # mkdir {tmp},{cache},{install_run},{install_logs}; .metadata_never_index in {var} and {install}
def rogzit(cfg, environ) -> None          # MOS_<KEY>=<absolute> for every resolved [utak] key + MOS_ELRENDEZES + MOS_WORKSPACE_ID
def portable_init(root, *, vault, presetek=(), backup=None, idegen_zarak=(), igen=False) -> Path   # writes {os}/var/settings.toml
def main(argv) -> int                     # `shell` (shlex-quoted export lines; unresolved keys omitted) | `json` | `portable-init`
```

- **`core/__main__.py start`:** `cfg = config.load()` → `rogzit(cfg, os.environ)` → `biztosit_mappak(cfg)` →
  `os.environ.update(folyamat_env(cfg))` → `server.start(cfg=cfg, …)`. Steps (`MOS_*` allow-list, `core/lepes_kapu.py:58`), the
  worker, CLI children and the D9 clone resolve the **same absolute paths**. A path changed in Settings applies at the next
  open; F5 shows "restart required".
- **`gepi_iras._klon`:** env = `{MOS_<k>: str(p) for k, p in cfg.utak.items()}` + the four clone overrides + `MOS_ELRENDEZES`,
  `MOS_WORKSPACE_ID`; `Config(cfg.root, cfg.data, env)` (merged data, no layer re-read).
- **`bin/mos`** (minimal diff, stays bash; the full `bin/mos.py` port is deferred, see §11): lines 35–52 (`HF_HOME`, `XDG`,
  `UV/PIP`, `TMPDIR`, `mkdir var/…`, Spotlight marker) become `eval "$("$PY" -B -m core.gyokerek shell)"` for Python commands.
  `VAR="${MOS_VAR:-$MOS_HOME/var}"` is used only by `runtime fetch|install` and `app *`, which are portable-only and run with no Python. `python_kereses`:
  `$MOS_PYTHON` → `${MOS_VENV:-$VAR/venv}/bin/python` → main-checkout venv → `$RT/python/bin/python3`. `test`/`perf` export
  `MOS_SETTINGS=` (tests never see the developer's layer). New dispatch: `workspace` → `core.workspace`, `portable init` →
  `core.gyokerek portable-init`. Worktree mode unchanged.
- **Shell:** `RootLocator.locate` → `(root, termek)`; candidates `MOS_ROOT` → `Bundle.main.resourceURL/manifold` (termek) →
  the `.app`'s parent (portable). `CoreProcess.init(root:vault:termek:port:titok:)` adds `MOS_VAULT`, `MOS_ELRENDEZES=termek`,
  `MOS_HEJ_CLI`, `MOS_NAPTAR_SEGED`. New `Telepites.swift`: `installURL`, read-only `workspaces.json` (`utolso` is the product
  vault until the F5 launcher), `athelyezett` (`/AppTranslocation/`). The handshake gains additive `vault`, `munkater_id`,
  `elrendezes`; the unmount watcher (`AppController.swift:114,418`) watches the **vault** from the handshake, not the root.

## 3. Workspaces

### 3.1 On disk

```
<vault>/.obsidian/                    created if missing (empty, as Obsidian does); never written into afterwards
<vault>/.manifold/workspace.toml      W layer; written LAST at creation (the commit point)
<vault>/.manifold/schema.json         optional (absent = preset schema or shipped default)
<vault>/.manifold/pillanat-kivetelek.json   optional
<vault>/.manifold/.gitignore          "var/" — a user's own git/Obsidian-Git may track settings, never state
<vault>/.manifold/README.txt          "Manifold's settings and data for this folder. Delete it to remove Manifold; notes are untouched."
<vault>/.manifold/var/                = {var}: vault.git state run runs tmp index cache szemelyes ytdlp archive *.sqlite
                                      .metadata_never_index; Time Machine exclusion on tmp/ cache/ index/ only
{install}/ settings.toml workspaces.json router.sqlite models/ toolchains/ run/ state/ logs/ backups/<id>/ workspaces/<id>/var/ demo/
```

```toml
[workspace]
id = "9f1c…"          # uuid4 hex, never derived from a path or name
formatum = 1          # format this file and the state were last migrated to
olvaso_min = 1        # oldest format a reader must understand (additive migrations keep it low → downgrade works)
nev = "Physics notes"
nyelv = "en"          # content language (P2)
presetek = []
obsidian_letrehozva = false
```

### 3.2 `core/workspace.py` (new)

```python
FORMATUM = 1; FORMATUM_MAX = 1
@dataclass(frozen=True)
class Felmeres:                       # launcher dry run, JSON
    vault: str; letezik: bool; ures: bool; irhato: bool; fajlrendszer: str; helyi: bool      # statfs f_fstypename, MNT_LOCAL
    szinkron: str | None              # "icloud" | "cloudstorage" | "dropbox" | None
    kis_nagy_erzekeny: bool; szabad_bajt: int; md_db: int; obsidian: dict                     # app/templates/daily-notes values
    meglevo_id: str | None; reszleges: bool; formatum: int | None
    eredmeny: str                     # "mehet" | "figyelmeztet" | "tilos"
    akadaly: list[str]; figyelmeztetes: list[str]; letrehozando: list[str]                   # stable kod strings
def felmer(vault: Path, alap: Config, *, uj: bool = False) -> Felmeres
def letrehoz(vault: Path, alap: Config, *, nev=None, nyelv="en", presetek=(), uj_mappa=False, demo=False,
             haladas=lambda d: None) -> dict
def nyit(cfg: Config) -> list[str]    # core start, product, after the locks and BEFORE App() recovery (§3.4)
def eltavolit(vault: Path, alap: Config, kuka) -> dict   # "Remove Manifold data"
def azonosit(vault: Path) -> str | None
class Regiszter:                      # {install}/workspaces.json, tartos.atomi_ir under {install_run}/workspaces.lock; Python is the only writer
    def __init__(self, install: Path); def olvas(self) -> dict; def felvesz(self, **e); def frissit(self, id, **e); def elfelejt(self, id)
# CLI: python -m core.workspace felmer|letrehoz|lista|elfelejt|eltavolit <vault> [--json] [--igen]   (default felmer)
```

**`akadaly` (tilos):** the vault is inside `{os}` or `{install}`; it is inside a workspace or contains one; it is not writable;
`uj_mappa` and the parent is missing (never create under an unmounted `/Volumes/X`); a network volume (`!MNT_LOCAL`: `flock`
is unreliable); another Manifold installation is running on it (best effort: a sibling `*/var/run/core.lock` whose content
names this vault and whose `flock` is busy, probed read-only); `olvaso_min > FORMATUM_MAX`.
**`figyelmeztetes`:** a non-APFS volume (reduced mode: the D9 trial clone answers 503, which is existing behaviour); a sync folder (§3.7); low free space; a large vault (the first snapshot takes time).

### 3.3 Create (every step idempotent; the commit point is step 6)

1. `felmer`; stop on `tilos`.
2. `uj_mappa` → `mkdir`; create `.obsidian/` only if missing and record it.
3. `.manifold/` + `.gitignore` + `README.txt` + `var/{state,tmp,run,runs,cache,index}` + `var/.metadata_never_index`, and
   `var/letrehozas.json` with the new id. A resumed create reuses that id. For a sync folder, `var` goes under `{install}/workspaces/<id>/var`.
4. `cfg = config.load({…, "MOS_VAULT": v, "MOS_WORKSPACE_ID": id[, "MOS_VAR": …]})` (allowed only while `workspace.toml` is absent).
5. Under `frame.run_lock(cfg)`: `snapshot.repos(cfg)["vault"].init()`, which writes `info/exclude` with `.manifold/` (`core/snapshot.py:202-233`).
   Then **synchronously** `commit("Workspace created", {"Mos-Forras": "kezi"})` (a repo without HEAD is handled).
   `haladas` reports progress; the launcher shows it. Read the W seed from `.obsidian/{templates,daily-notes}.json` (read only;
   `app.json` stays live-read by `csatolmany`/`vaultio`).
6. **Commit point:** `tartos.atomi_ir(.manifold/workspace.toml)`. Before it exists, `felmer` reports `reszleges` and `letrehoz` resumes.
7. Registry entry: `id, vault, kanonikus (F_GETPATH), kotet_uuid, inode(.manifold), allapot ("vault"|"telepites"), nev,
   letrehozva, megnyitva, demo`. The registry is an index only; losing it loses the recent list.

**Undo (`eltavolit`):** `.manifold/` (and `{install}/workspaces/<id>`) go to the Trash through the shell's `--kuka`; `.obsidian/` is removed
only if it was created **and** is still empty; the registry entry is dropped. Vault files are untouched (invariant I7: deleting
`.manifold` returns a byte-identical Obsidian vault; tested). **Demo:** `letrehoz({install}/demo/Manifold Demo, demo=True)`
(content in F8); "Reset demo" uses the Trash.

### 3.4 Open (`workspace.nyit`, product, at core start)

- Format: `olvaso_min > FORMATUM_MAX` → refuse (`workspace_ujabb`); `formatum < FORMATUM` → migration runner (§7.4; none in F3).
- Identity vs registry: same id at the same canonical path → ok. Same id, old path gone → **moved**: update the registry and
  re-run `Repo.init()` when `core.worktree` differs. Same id, and the old path still holds the same id → **copied**: new id
  (atomic rewrite of `workspace.toml`) and a new registry entry. History stays; journals stay and recover on the copy. The old
  volume is not mounted → treat as moved (if it later reappears, its next open detects the copy and re-keys it, so the state
  converges). F5 may turn these into questions.
- **Gate:** the `.obsidian` gate stays as it is (`core/vaultio.py:182-188`, `core/frame.py:128-132`, `core/server.py:244,268`), and
  creation guarantees `.obsidian` exists. In product, `Vault.root` additionally compares `.manifold/workspace.toml`'s id with
  `cfg.workspace_id` **on the unavailable→available transition only** (a swapped disk with the same name stays "unavailable",
  `kod: workspace_csere`). T002 semantics are unchanged.

### 3.5 Registry and core announcements

`{"formatum":1,"utolso":"<id>","munkaterek":{"<id>":{…§3.3 step 7…}}}`. The Swift shell reads it; Python writes it.
`elfelejt` never deletes files. A running-core index for the launcher (`cores/<id>.json`) is F5.

### 3.6 `.manifold` is invisible (invariant I6)

| Place | Change |
|---|---|
| new `core/rejtett.py` (WP1) | `KIHAGYOTT_MAPPAK = frozenset({".obsidian", ".trash", ".git", ".manifold", "node_modules"})`; `metsz(almappak)` |
| `core/index/feloldas.py:38` `SKIP_DIRS`, `indexelo._ervenyes` | from `rejtett` (index, link resolution, watcher filter) |
| `core/index/figyelo.py:110-124` | `FSEventStreamSetExclusionPaths([<vault>/.manifold])` (ctypes); the polling fallback (`_pillanat`, :165) prunes |
| `core/binaris_naplo.py:55` `KIHAGY` | from `rejtett` |
| every other vault walker (`atnevezes`, `csatolmany`, `video_api`, `sablon`, `felkeszultseg/__main__`, `modulok/{fuzet/lanc, kartya/lanc, kartya/szinkron, osszefoglalas/futtat, grafikon/automatika, ytdlp/egyezes, ytdlp/elhelyezes}`) | `rejtett.metsz` or proof that it prunes all dot folders; ratchet test |
| `[pillanat.vault] kizar` | `.manifold/` |
| `core/vaultio.py` `norm_path` | none (dot segments already 400, `:160`); test that `.manifold/…` is refused |
| `core/frame.py` `trial_clone` | new `apfs_clone_vault(src, dst, kihagy=(".manifold",))`: `mkdir dst`, `cp -c -R` per top-level entry; identical to v2 without `.manifold` |
| `core/vaultkivul.py` `vaultban_van` | a target under `<vault>/.manifold/var` (text **or** `samefile` ancestor) counts as **outside**; everything else unchanged and still fail-closed. No caller edits; `teljes_mentes` still refuses such targets through its own root check (`core/teljes_mentes.py:335`) |

### 3.7 Non-APFS and sync folders

`{var}` must share the vault's volume (`st_dev` check in `felmer` and doctor). Non-APFS local volume → reduced mode (no trial
clone → D9 machine writes refused with a clear `kod`; no copy fallback, `core/tartos.py:138-146`). Network volume → `tilos`.
Vault inside iCloud Drive / `~/Library/CloudStorage` / Dropbox: the registry sets `allapot = "telepites"` →
`{install}/workspaces/<id>/var`. That folder is on the same internal volume, so `clonefile` and atomic rename still work
(verified by `st_dev`, else reduced mode). `.manifold/workspace.toml` still syncs (Obsidian-like settings sync); history is per Mac (stated in the dry run).

## 4. Locks

| Lock | v2 | Portable (identical paths) | Product |
|---|---|---|---|
| `core.lock` (one core) | `{run}/core.lock` | `var/run/core.lock` | `<vault>/.manifold/var/run/core.lock` (same inode for every path spelling and for two macOS users); content `pid · workspace_id · vault` |
| vault guard (new) | — | `{install_run}/vaults/<k>.lock` | same; `k = sha256(F_GETPATH(vault))[:32]` (fallback `st_dev:st_ino`). Catches sync-folder workspaces (whose `{run}` is in install) |
| foreign cores (new) | — | `[hordozhato] idegen_zarak` (I layer): other installs' `core.lock` paths, probed **read-only** (`O_RDONLY`, `LOCK_SH\|LOCK_NB`, released at once) — e.g. the v2 checkout; busy → refuse | `felmer` best-effort sibling probe (§3.2) |
| `kor.lock` | `{run}` | same | per workspace |
| `modell.lock` (L23) | `{state}/modell.lock` | `var/state/modell.lock` | `{install_state}/modell.lock`; `MANIFOLD_MODELL_ZAR` still wins |
| `worker.lock` / `worker.pid`, `worker.log` | `{run}`, `{runs}` | `var/run`, `var/runs` | `{install_run}`, `{install_logs}` |
| `workspaces.lock` | — | `var/run` | `{install_run}` |

`server.start`: `core.lock` → vault guard → foreign probe; if any is busy, release the held ones and send the unchanged
`{"foglalt":true,"pid","vault"}` handshake (exit 75). Then, in product, `workspace.nyit`. A configuration error sends
`{"hiba":<kod>,"param":…}` (exit 78) instead of a traceback. `visszaallitas._core_fut` probes `core.lock` and the vault
guard (read-only). The worker reads install sections only (`load(munkater=False)`); it keeps D4: it is the child of the core
that started it, and other cores adopt it through the pid file. **New:** if an adopted worker disappears mid-request
(`KliensHiba` on a connection error), the client re-spawns once and retries the request once. A shared lease is deferred to the
multi-window work (F5/F6).

## 5. Backups

- **Internal (`mentes.py`):** product `backup = {backup_gyoker}/{workspace_id}` (per-workspace rotation comes from the folder;
  `backup_gyoker` is an install key, so a user-chosen disk gets per-workspace subfolders). Owner marker
  `{backup}/.manifold-mentes.json` (`munkater_id`, `vault`, `letrehozva`) written into an empty folder; in both layouts:
  - own marker → normal rotation;
  - **foreign marker** → no rotation, `mentes-hiba.json` warning, Health `mentes_idegen_mappa`;
  - **no marker and not empty** (legacy, e.g. `~/Manifold-backup` shared by v2 and [UNI] portable today) → write, but
    `snapshot.bundle_keszit` deletes an old bundle only if **every head in it exists in this repository** (`git bundle
    list-heads` + `git cat-file -e`), and `mos-allapot-*` rotation is off. Health tells the user to choose a separate folder.
  - `allapot_forrasok` adds `workspace.toml`, `schema.json`; `kodtar` stays `{os}` (bundle: no `.git` → skipped, `core/mentes.py:137-139`).
  - Health `mentes_azonos_lemez` when the backup root and the vault share a disk.
- **External (`teljes_mentes.py`, `tasks.py`):** `adat_kotet(cfg) -> set[int]` = `st_dev` of the vault and of `{var}` (if outside
  it) replaces the three `cfg.root` comparisons. Product: `forrasok` drops the `os` root (reinstallable); `{var}` under the vault is
  walked with the vault (SQLite detected per file, `:145,286`); `_kizart_mintak` is computed **per root**, so
  `.manifold/var/{tmp,run,runs,cache,index}` are excluded wherever they live; `router_db` stays a root. Product target:
  `<cel>/Manifold Backups/<workspace_id>/Manifold-<ts>/` (per-workspace `_ritkit`); `jegyzek.json` gains `munkater_id`,
  `elrendezes`; `aktiv-os.toml` is replaced by copies of `settings.toml`/`workspace.toml`. Restore keeps the v2 sibling
  layout for portable; the key-mapped product restore (vault → chosen empty folder, `router_db` → install only if absent, then
  `workspace.nyit`) is F8.

## 6. Doctor in product mode (`core/doctor.py`; F7 builds Health on it)

`ellenoriz(cfg, environment, home, futo_python=None, *, termek: bool | None = None)` (default `cfg.elrendezes == "termek"`).
`Eredmeny` gains `kod` (stable), `osztaly` (`"termek"|"fejleszto"`), `javitas` (fix id or `None`); `--json` output.

| | Checks |
|---|---|
| Portable only | `bin/mos` root check; `var` symlink (`:742-753`); pyvenv/shebang/requirements/runtime pins; `HOME_NEM_ENGEDETT` as today |
| Product replaces | root → bundle integrity (`epites.json`) and `bundle_athelyezett`; I1 (nothing resolved writable under `{os}`); `HOME_NEM_ENGEDETT` minus `Library/Application Support/Manifold`; volume rule (`:735-740`) → `{var}`, `{tmp}`, `{fuzet_bejovo}`, `{video_bejovo}`, `{staging}` share the vault's `st_dev` |
| New (both) | `workspace.toml` valid and registered (`regiszter_ervenytelen_ut`, fix `regiszter_takarit`); format (`workspace_ujabb`/migration due); `core.worktree == vault`; `.manifold/` in `info/exclude`; `kotet_nem_apfs`, `kotet_halozati`, `szinkron_mappa`; free space (vault, install); `cfg.elutasitott` (`workspace_kulcs_tiltott`); `{install}` writable; lock locations install-level; stale `core.lock`/`worker.pid` (fix `zar_takarit` only when the pid is dead and the flock free); foreign/legacy backup folder; backup freshness; portable: `vault` unset (`nincs_vault`: "run `bin/mos portable init`") |

## 7. Portable mode and migration

### 7.1 Portable mode (the developer's SSD)

Auto-selected for any non-bundle root. With `install = var = {os}/var`, every v2 path is unchanged. The golden test (WP1)
proves it. These also stay as they are: worktree mode, `runtime/`, `bin/mos runtime …`, `~/Manifold-backup` (now
protected by the legacy-folder rule) and the `{os}/var/state/modell.lock` path.

**Developer setup (once, documented in the NAPLO):**
`bin/mos portable init --vault /Volumes/<ssd>/<vault> --preset v2-kompat --idegen-zar "<v2 checkout>/var/run/core.lock"
[--backup "{home}/Manifold-backup/<name>"]` writes `{os}/var/settings.toml` (gitignored by `var/`). `{work}` stays defined, so
the F2 preset's `{work}/…` folders resolve. No `.manifold/` is created in a vault that v2 still manages: v2's `SKIP_DIRS` and
snapshot `kizar` do not know it, so v2 would commit it and index the trial clones. The workspace layer applies in portable mode only after
the explicit F8 v2-import. To share one model per machine with a product install, the init can set `[modellgazda] zar` to the
product lock. It must **never** point at the v2 tree (read-only), and `models` never at v2's `var/models` (offline HF writes
`.no_exist` markers).

**Tests:** `alg_gyoker(tmp, *, preset="v2-kompat")` (default on) writes the fake `var/settings.toml`
(`[utak] vault = "{work}/Manifold"`, `[telepites] presetek`) and copies `config/presets/` and the schema files. All 111
fixture sites keep v2 values with no edits. The real-root `config.load()` sites under `bin/mos test` see only S
(`MOS_SETTINGS=`), so a developer's personal layer cannot change test results. Product tests use a new
`alg_bundle(tmp)` (fake `X.app/Contents/Resources/manifold` + fake HOME).

### 7.2 Neutral defaults (F2 deferred items, WP6)

The developer's values move from `config/os.toml` into `config/presets/v2-kompat.toml` (+ `v2-kompat.schema.json` from
today's `vault-sema.json`), so `os.toml` and `config/schema-default.json` become neutral:
`[naplo] ut = "Daily/YYYY-MM-DD"`; `kisero_elotag` gets a neutral product value (WP6 proposes `"Manifold - "`, giving
`Manifold - Cards`, `Manifold - Quizzes`, …; the companion schema classes are derived from it, never listed separately);
empty `kizart` lists. The `[pdf.tags]` subject map and its code twins (`fuzet/katalogus.TANTARGYAK`, `ytdlp/integralas.TARGY_TERKEP`)
are also cleared, as are `tema_minta`, `[naptar.szotar]` and the schema values `tags_ertekkeszlet`/`konyv-jegyzet`/`X01`. The golden test
with the preset must stay byte-identical; that is the WP6 acceptance gate.

### 7.3 v2 state → workspace migration (designed now, implemented in F8 under the v2-import)

`core/migracio_var.py` (D1 §8, adopted): `terv(regi, uj) -> list[Lepes]` (mode `klon|masol|sqlite(.backup)|git(cp -c -R +
fsck)|hivatkozas|kihagy`), `vegrehajt` (copy-only, sources opened read-only; the old `core.lock` and `kor.lock` are held through
read-only fds), `ellenoriz` (sha256, `integrity_check` + row counts, HEAD + fsck), `visszavon`. Copy into
`.manifold/var.uj-<ts>`, verify, `rename` → `.manifold/var`; `workspace.toml` with `[migracio] regi_var` is the commit point; journal
`{install}/migracio/<ts>/`. `models` are referenced by default (install `settings.toml`), and backups are not copied. Split-brain:
a portable core refuses to start when the vault's `workspace.toml` has `regi_var` equal to its own `{var}`, and a product core
probes `<regi_var>/run/core.lock` read-only. The old `var/` is never written, so a rollback resumes portable mode exactly.

### 7.4 Format migrations

`workspace.toml` `formatum`/`olvaso_min` are written in F3; the runner (`MIGRACIOK: dict[int, Lepes]`, pre-copy via
`mentes.allapot_masolat`/`migracio_elott` + vault bundle, `formatum` written last, automatic restore on error) ships with the first
real migration. Install-level update checks (`verzio.json`, pre-copies of `settings.toml`/`workspaces.json`/`router.sqlite`) are F9.

## 8. Function-level change list

| File | Change | WP |
|---|---|---|
| `core/config.py` | `ELRENDEZESEK`, `ID_MINTA`, `RETEG_JOG`, `ConfigError(kod, param)`, `elrendezes`, `reteg_ellenoriz`, `_toml_olvas`, `_melyegyesit`, `_presetek`, layered `load(…, munkater=True)`, `Config`: `_meta`, `utak`/`feloldatlan`, `path` kod, `forras`, I1 check | 1 |
| `core/gyokerek.py` (new) | `folyamat_env`, `biztosit_mappak`, `rogzit`, `portable_init`, `main` | 1 |
| `core/rejtett.py` (new) | `KIHAGYOTT_MAPPAK`, `metsz` | 1 |
| `core/__main__.py` | `start` pins roots before `server.start(cfg=…)` | 1 |
| `core/gepi_iras.py` | `GepiIras._klon` env from resolved paths (WP1); companion mirror `:818-821` from `kiserok` (WP6) | 1, 6 |
| `config/os.toml` | `[utak]` re-root + `[elrendezes.termek]`, `.manifold/` exclude, `kivetelek`, `[sema] alap`, `[modellgazda] zar` (WP1); W sections neutral (WP6) | 1, 6 |
| `bin/mos` | `gyokerek shell` eval, `VAR`, `python_kereses`, `MOS_SETTINGS=` for test/perf, `workspace`/`portable` dispatch | 1 |
| `tests/helpers.py`, `tests/kezi/_kornyezet.py` | `alg_gyoker(preset=…)`, `alg_bundle`; isolate `install*`, `workspace`, `backup_gyoker` (the model lock stays shared through `MANIFOLD_MODELL_ZAR`) | 1 |
| `core/workspace.py` (new) | §3.2 | 2 |
| `core/frame.py` | `apfs_clone_vault`; `trial_clone` uses it | 2 |
| `core/vaultio.py` | `Vault.root`: product identity check on the availability transition | 2 |
| `core/vaultkivul.py` | `vaultban_van`: `.manifold/var` exception | 2 |
| `core/index/{feloldas,figyelo}.py`, `core/binaris_naplo.py`, `core/{atnevezes,csatolmany,video_api}.py`, `modulok/{fuzet/lanc,kartya/lanc,kartya/szinkron,osszefoglalas/futtat}.py` | `rejtett` prune; FSEvents exclusion | 2 |
| `core/server.py` | `_core_zar` content; `_vault_or`; `_idegen_zarak`; `start` order + `workspace.nyit`; handshake fields; exit 78 | 3 |
| `core/visszaallitas.py` | `_core_fut` probes both locks | 3 |
| `core/modell/beallitas.py`, `worker.py`, `kliens.py` | `run` → `install_run`; `pidfajl`; worker log → `install_logs`; retry-once after an adopted worker vanishes | 3 |
| `shell/Sources/{RootLocator,CoreProcess,AppController}.swift`, new `Telepites.swift` | §2.6 | 3 |
| `core/mentes.py` | `_tulajdonos(cfg) -> "sajat"\|"ures"\|"idegen"\|"orokolt"`, rotation policy, `allapot_forrasok` | 4 |
| `core/snapshot.py` | `bundle_keszit(…, torolheto: Callable[[Path], bool] \| None = None)` (heads guard) | 4 |
| `core/teljes_mentes.py`, `core/tasks.py` | `adat_kotet`; `forrasok`; per-root `_kizart_mintak`; product target and jegyzek; `LemezFigyelo.tick`; `_teljes_mentes_terv` | 4 |
| `core/doctor.py` | §6 | 5 |
| new `core/kiserok.py` | `kisero_elotag(cfg)`, `kisero_mappa(cfg, fajta)`, `tartalmi_ut(cfg, rp)`, `subject_of(cfg, rp)` | 6 |
| `core/tulajdonsagok.py` | `[sema] mod = ki\|tanacsado\|szigoru`, `null` value sets, schema resolution chain, companion classes derived from `kiserok` | 6 |
| convention sites (F2 deferred list): `core/{automatika,kviz_api,kartya_api,osszefoglalas_api,atirat,videolanc,fuzet_feladat,naplo,sablon,gyakorlas,pdfkiemeles,naptar}.py`, `core/index/hibrid/{hasonlo,darabolas}.py`, `core/asszisztens/{beallitasok,emlites}.py`, `core/felkeszultseg/kalibracio.py` (`--rogzit` refused in product), `modulok/{kartya,kviz,osszefoglalas}/formatum.py`, `modulok/ytdlp/{elhelyezes,integralas,egyezes}.py`, `modulok/fuzet/{katalogus,modszer}.py`, `modulok/grafikon/automatika.py`, `app/src/{kartya,kviz,osszefoglalas}/allando.ts` | read `kiserok`/config; walkers in these files use `rejtett` | 6 |
| `config/presets/v2-kompat.toml` (+ `.schema.json`), `config/schema-default.json` (new), `config/vault-sema.json` (removed after the move) | §7.2 | 6 |

## 9. Implementation plan

**Stage A (alone):** WP1. **Stage B (parallel, disjoint files):** WP2–WP6. Before stage B starts, WP2 publishes the signatures
of `workspace.nyit`/`azonosit` as a stub, so WP3 can code against them. **Integration (one agent):** end-to-end fresh-install test, the ratchet
enabled for all files, full suites, Swift build in both configurations, NAPLO F3 entry.

| WP | Agent | Files (exclusive) | Tests to add | Effort |
|---|---|---|---|---|
| **WP1 Roots + layered config** | opus | `core/config.py`, `core/gyokerek.py`, `core/rejtett.py`, `core/__main__.py`, `core/gepi_iras.py` (`_klon` only), `config/os.toml` (§2.4), `bin/mos`, `tests/helpers.py`, `tests/kezi/_kornyezet.py`, `tests/adat/konfig/f2-hordozhato.json` | `test_konfig_egyenertek` (**gate**: resolved `[utak]` + all sections of `alg_gyoker(preset="v2-kompat")` equal the golden JSON generated from the F2 tree **before any edit**; differences only from an explicit list of new keys); `test_konfig_retegek` (order, provenance, allow-lists incl. a hostile `workspace.toml` setting `[homokozo]`, `[utak]`, `[router]`, `[kalibracio]`, dot-segment paths; type/length/regex; TOML error fatal; `ID_MINTA`; `MOS_SETTINGS=`; lazy `nincs_vault`/`nincs_workspace`); `test_gyokerek` (layout detection, I1 on `alg_bundle`, `rogzit`, `shell` output with spaces in paths, `portable_init`); `test_proba_klon_env` (clone env = resolved paths); `test_mos_es_shell` addition (no write under a `chmod -R a-w` fake bundle) | L, 2 d |
| **WP2 Workspace lifecycle + invisibility** | opus | `core/workspace.py`, `core/frame.py`, `core/vaultio.py`, `core/vaultkivul.py`, `core/index/feloldas.py`, `core/index/figyelo.py`, `core/binaris_naplo.py`, `core/atnevezes.py`, `core/csatolmany.py`, `core/video_api.py`, `modulok/fuzet/lanc.py`, `modulok/kartya/{lanc,szinkron}.py`, `modulok/osszefoglalas/futtat.py` | `tests/fresh_install/test_workspace_letrehozas.py` (**PLAN F3 gate**: empty folder → `.obsidian` + `.manifold` + live repo + first `kezi` commit; existing Obsidian vault byte-identical outside `.obsidian`/`.manifold`; crash after each step → resume; deleting `.manifold` restores it byte for byte (I7); nested/inside-install/network refused); `test_manifold_lathatatlan` (a planted full clone under `.manifold/var/tmp/proba/` is invisible to index, links, watcher, hygiene, binary log, card sync, video match; `norm_path` refuses `.manifold/…`; `git status` ignores it); `test_proba_klon_manifold` (no recursion); `test_workspace_masolat_mozgatas` (move with a pending rename journal; copy → new id); `test_regiszter`; `test_vaultkivul` (card export default allowed, `teljes_mentes` target under `.manifold` refused); `test_rejtett_bejaras` ratchet (files of WP4–WP6 skipped `[indokolt]` until integration) | L, 2.5 d |
| **WP3 Locks + startup + shell** | opus | `core/server.py`, `core/visszaallitas.py`, `core/modell/{beallitas,worker,kliens}.py`, `shell/Sources/{RootLocator,CoreProcess,AppController,Telepites}.swift` | `test_zarak_telepites` (two workspaces, one install: one model lock, one `worker.pid`; a case-variant path to the same vault → exit 75; a foreign `core.lock` held → refuse; `visszaallitas` sees a core on the vault guard); `tests/multi_user/test_ket_core.py` (two subprocess cores: disjoint trees, the other core's secret → 403, foreign vault path refused, shared worker); `test_kliens_atvett_worker` (retry once); `test_core_start_hiba` (`{"hiba":kod}`, exit 78); Swift build both configs | L, 2 d |
| **WP4 Backups** | sonnet | `core/mentes.py`, `core/snapshot.py` (`bundle_keszit` only), `core/teljes_mentes.py`, `core/tasks.py` (`_teljes_mentes_terv` only) | `test_mentes_munkater` (per-id folders; own/foreign/legacy marker; legacy rotation never deletes a bundle with unknown heads; `backup_gyoker` inside the vault refused); `test_teljes_mentes_termek` (volume rule vs vault/`{var}` with monkeypatched `st_dev`, per-root excludes, no `os` root, target layout, jegyzek fields) | M, 1.5 d |
| **WP5 Doctor product mode** | sonnet | `core/doctor.py` | `test_doctor_termek` (`alg_bundle` + fake install: every §6 row, `kod` stability, `--json`); `test_doctor` keeps the portable rules | M, 1.5 d |
| **WP6 Workspace conventions + neutral defaults** | sonnet (may split into a `core/` agent and a `modulok/`+`app/` agent on disjoint files) | `config/os.toml` (W sections only), `config/presets/*`, `config/schema-default.json`, `config/vault-sema.json`, `core/kiserok.py`, `core/tulajdonsagok.py`, `core/gepi_iras.py` (companion lines only), the convention sites of §8, `tests/preset_v2/` (the ~40 convention-defining tests move here) | golden test with preset unchanged (**gate**); `test_alapertekek_semleges` (a neutral `vaultgyar` vault: no schema violations by default, no companion magic, daily note under `Daily/`); `test_tulajdonsagok_mod` (`ki`/`tanacsado`/`szigoru`, `null` value sets); `test_kiserok` (one source; renamed companion root honoured by automation, similar notes, machine-write classes) | L, 2.5 d |

**Integration:** `tests/fresh_install/test_alap.py` (bundle-shaped root, fake HOME, no `var/`: `workspace letrehoz` → core
subprocess → save a note → snapshot → backup → restore). Remove the ratchet skips, then run `MOS_SZIGORU=1 bin/mos test`, `bin/mos app test`,
`MOS_DEVELOPER_BUILD=1 bash shell/build.sh` plus the default build, and write the NAPLO F3 entry.

## 10. Tests that must stay green throughout

Full `MOS_SZIGORU=1 bin/mos test` and `bin/mos app test` after each WP merge. The following are watched in particular:

- data paths: `test_gepi_iras*`, `test_frame*`, `test_snapshot*`, `test_vaultio*`, `test_atnevezes*`;
- backup and restore: `test_visszaallitas`, `test_mentes*`, `test_teljes_mentes*`, `test_kiadas_mentes`;
- lifecycle: `test_eletciklus`, `test_leallas`, `test_core_api`;
- step gate: `test_lepes_kapu` (no new secret-like variable without a `TITOK/TOKEN/SECRET` name);
- environment and config: `test_kezi_kornyezet`, `test_doctor`, `test_tulajdonsagok`, `test_kartya*`, `test_index*`, and the golden `test_konfig_egyenertek` from WP1 on.

## 11. Risks

| # | Risk | Mitigation |
|---|---|---|
| K1 | A walker misses `.manifold`, so trial clones get indexed, linked or turned into cards | `rejtett` constant, FSEvents exclusion, planted-clone behaviour test, ratchet |
| K2 | Trial-clone recursion, or the clone gets a different state dir | `apfs_clone_vault`; resolved-path env; equivalence test |
| K3 | A hostile or shared `workspace.toml` redirects tools, lowers D9 or targets `.manifold` | `RETEG_JOG`, type/length/regex/path checks, `ID_MINTA`; the state location comes from the registry only; rejections visible |
| K4 | Settings change mid-session → core and steps see different `{run}` (L13) | `rogzit` pins absolute paths; path keys apply at reopen |
| K5 | Copy/move: two workspaces with one id share backups and registry | registry check at every open, re-key on copy, owner marker on the backup folder |
| K6 | v2 and [UNI] portable share `~/Manifold-backup` (true today) | legacy rule: never delete a bundle with unknown heads, no state rotation, Health hint; `portable init --backup` |
| K7 | Split brain: v2 and [UNI] (portable or product) on one vault | no default vault; no `.manifold` in a v2-managed vault; `idegen_zarak` read-only probe; `felmer` sibling probe; `regi_var` guards after F8 |
| K8 | Sync-folder vault corrupts SQLite/git; `workspace.toml` conflict copies across Macs | state in `{install}/workspaces/<id>/var`; only small settings sync; doctor `szinkron_mappa` |
| K9 | Test drift: the neutral flip or the developer's layer changes test results | golden gate; `alg_gyoker(preset=…)`; `MOS_SETTINGS=` under `bin/mos test`; audit the one `config.load({**os.environ, …})` test |
| K10 | Lazy keys move a typo's failure to first use | only vault/workspace-dependent keys are deferred, everything else expands at load |
| K11 | Worker lifetime tied to the first core | adopt via pid file + retry once; lease in F5/F6 |
| K12 | Non-APFS or network volume | reduced mode or `tilos`; no copy fallback (unchanged `tartos`) |
| K13 | Space in `Application Support` (bash, `sandbox-exec -D`, git `core.worktree`) | `fresh_install` and `test_gyokerek` run with that path |
| K14 | `ytdlp` worktree moves from `{modulok}` to `{var}` in product (v2 mixed code and data) | I1 test; WP1 greps the chain for reads of code under `{ytdlp}`; portable unchanged |
| K15 | Slow first snapshot of a large opened vault | synchronous with progress before the commit point; the launcher shows it; resume after a crash |
| K16 | Two model locks when v2, portable and product run on one Mac | documented; `portable init` can share the product lock; never the v2 tree |
| K17 | `kezi` scripts isolate the new install keys and load a second model | `_kornyezet` keeps `MANIFOLD_MODELL_ZAR` real while isolating `install_run` |

## 12. Deviations from PLAN §10 to record in the NAPLO

- `bin/mos` → `bin/mos.py` is **not** ported in F3. `bin/mos` stops hard-coding `var/` (via `core.gyokerek`), which is the data-path
  goal. A 1:1 port of the 300-line dispatcher moves no data and adds regression risk. It is moved to F9, next to the packaging work.
- The v2 → workspace state migration (§7.3) is designed here and implemented with the F8 v2-import.
- The settings writer (`beallitas_iras`, used by ⌘, Settings), the running-core index, and the worker lease move to F5. The Health API moves to F7. Install update checks move to F9.
