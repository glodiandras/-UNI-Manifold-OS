"""C34 kézi kapu: a belső lemezes mentés VISSZAÁLLÍTHATÓSÁGA — csak olvas, csak a próbamappába ír (a discover nem futtatja).

    bin/mos exec var/venv/bin/python -B tests/kezi/kiadas_mentes.py [--backup ~/Manifold-backup] [--megtart]
    (munkafában: a vault, a `vault.git` és a mentés a fő checkoutból jön — `_kornyezet.munkafa_forras`; a `--backup` kell)

A valódi `{backup}` legújabb bundle-jeit és állapotmásolatát visszaállítja egy ideiglenes próbamappába, és ellenőrzi:

  A. **vault**: a legújabb `vault-*.bundle` a `core.visszaallitas.visszaallit`-tal (a `bin/mos visszaallit` magja) egy üres
     helyre; bundle verify + fsck; minden visszaállított fájl bájtra összevetve a valódi vaulttal. Eltérés/hiány csak a
     bundle óta rögzített (a valódi `vault.git` HEAD-jéig) vagy még nem rögzített változásból állhat.
  B. **kódtár**: a legújabb `mos-kodtar-*.bundle` klónozható, verify + fsck, a kulcsfájlok a HEAD fájában vannak, és a
     HEAD a valódi kódtár őse vagy azonos vele.
  C. **állapot**: a legújabb `mos-allapot-*` minden SQLite-ja megnyitható (`mode=ro`), `quick_check` rendben, a `user_version`
     a mentés forrásáéval azonos (a forrás `immutable=1`-gyel olvasva), a `state/*.json` fájlok JSON-ok, és minden élő
     állapotfájlnak megvan a másolata.
  D. **ritmus**: a legújabb vault- és kódtár-bundle kora; a `mentes.friss` ítélete a valódi HEAD-re; nincs `mentes-hiba.json`.

A valódi vaulthoz, `var/`-hoz és `{backup}`-hoz nem ír (a próbamappa a `{tmp}` alatt, `_kornyezet.probamappa`). Kimenet:
szakaszonként RENDBEN / ELTÉRÉS, az utolsó sor az összesítés; kilépési kód 0/1. A próbamappa törlődik, hacsak nincs `--megtart`.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from core import config, mentes, snapshot, visszaallitas  # noqa: E402
from _kornyezet import cfg_elkulonitve, cfg_masik_var, munkafa_forras, probamappa  # noqa: E402

KULCSFAJLOK = ("bin/mos", "core/mentes.py", "core/doctor.py", "config/os.toml", "config/runtime-pins.env", "CLAUDE.md")


def git_olvas(munkafa_vagy_git: Path, *args: str, git_dir: bool = False) -> subprocess.CompletedProcess:
    env = {**snapshot.hermetikus_env(), "GIT_OPTIONAL_LOCKS": "0"}
    elo = ["--git-dir", str(munkafa_vagy_git)] if git_dir else ["-C", str(munkafa_vagy_git)]
    return subprocess.run(["git", *elo, *args], env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")


def a_vault(cfg, backup: Path, d: Path, riport: dict, alap: dict | None = None) -> list[str]:
    hibak = []
    bundle = mentes.legujabb(snapshot.repos(cfg)["vault"], backup)
    if bundle is None:
        return [f"nincs vault-*.bundle a {backup} alatt"]
    kcfg = cfg_elkulonitve(d, cfg, vault=d / "vault-visszaallitott", vault_git=d / "vault-vissza.git", home=True, alap=alap)
    t0 = time.monotonic()
    r = visszaallitas.visszaallit(kcfg, bundle, "vault")
    ido = time.monotonic() - t0
    valodi = cfg.path("vault")
    vissza = Path(r["munkafa"])
    azonos = elter = hianyzik = 0
    gyanus = []
    for ut in r["irt"]:
        v = valodi / ut
        if not v.is_file():
            hianyzik += 1
            gyanus.append(ut)
        elif v.read_bytes() == (vissza / ut).read_bytes():
            azonos += 1
        else:
            elter += 1
            gyanus.append(ut)
    # a bundle óta rögzített (valódi HEAD-ig) vagy nem rögzített változások megmagyarázzák az eltéréseket
    repo = snapshot.repos(cfg)["vault"]
    magyarazat = set()
    if repo.exists() and gyanus:
        diff = git_olvas(repo.git_dir, "diff", "--name-only", "-z", r["head"], "HEAD", git_dir=True).stdout
        magyarazat |= {x for x in diff.split("\0") if x}
        magyarazat |= set(mentes.nem_rogzitett(repo))
    megmagyarazatlan = [u for u in gyanus if u not in magyarazat]
    riport["vault"] = {"bundle": bundle.name, "head": r["head"][:12], "kovetett_fajl": r["fajlok"], "kiirt": len(r["irt"]),
                       "azonos": azonos, "elter": elter, "hianyzik_a_valodiban": hianyzik, "megmagyarazatlan": len(megmagyarazatlan),
                       "kihagyva": len(r["kihagyva"]), "mp": round(ido, 2)}
    print(f"[A] vault: {bundle.name} → HEAD {r['head'][:12]}, {r['fajlok']} követett fájl, kiírva {len(r['irt'])}, bájtra azonos "
          f"{azonos}, eltér {elter}, a valódi vaultból hiányzik {hianyzik}, megmagyarázatlan {len(megmagyarazatlan)} ({ido:.1f} s)")
    if r["irt"] == [] or azonos == 0:
        hibak.append("a visszaállítás nem írt ki (vagy semmi nem azonos) fájlt")
    if megmagyarazatlan:
        hibak.append(f"{len(megmagyarazatlan)} fájl eltér/hiányzik a valódi vaultból a bundle óta rögzített változáson kívül: "
                     + "; ".join(megmagyarazatlan[:5]))
    if r["status"]:
        hibak.append(f"a visszaállított munkafában nem rögzített változás van: {r['status'][:3]}")
    return hibak


def a_kodtar(cfg, backup: Path, d: Path, riport: dict) -> list[str]:
    hibak = []
    bundle = mentes._legujabb(mentes.KODTAR_NEV, backup)
    if bundle is None:
        return [f"nincs {mentes.KODTAR_NEV}-*.bundle a {backup} alatt"]
    cel = d / "kodtar-vissza"
    p = subprocess.run(["git", "clone", "-q", str(bundle), str(cel)], env=snapshot.hermetikus_env(), capture_output=True, text=True)
    if p.returncode != 0:
        return [f"a kódtár-bundle nem klónozható: {p.stderr.strip()[:200]}"]
    if git_olvas(cel, "bundle", "verify", "-q", str(bundle)).returncode != 0:
        hibak.append("bundle verify bukott")
    fsck = git_olvas(cel, "fsck", "--no-progress", "--connectivity-only")
    if fsck.returncode != 0:
        hibak.append(f"fsck: {(fsck.stderr or fsck.stdout).strip()[:200]}")
    fa = set(git_olvas(cel, "ls-files").stdout.splitlines())
    hiany = [k for k in KULCSFAJLOK if k not in fa]
    if hiany:
        hibak.append(f"a HEAD fájából hiányzik: {', '.join(hiany)}")
    head = git_olvas(cel, "rev-parse", "HEAD").stdout.strip()
    munkafa = mentes.kodtar_munkafa(cfg)
    relacio = "nincs valódi kódtár az összevetéshez"
    if munkafa is not None:
        if git_olvas(munkafa, "cat-file", "-e", head).returncode != 0:
            relacio = "a bundle HEAD-je a valódi kódtárban nincs meg"
            hibak.append(relacio)
        elif git_olvas(munkafa, "merge-base", "--is-ancestor", head, "HEAD").returncode == 0:
            relacio = "őse a valódi HEAD-nek (vagy azonos)"
        else:
            relacio = "a valódi kódtár HEAD-jével elágazott (másik ágon készült a bundle) — a tárgyak megvannak"
    riport["kodtar"] = {"bundle": bundle.name, "head": head[:12], "fajl": len(fa), "relacio": relacio}
    print(f"[B] kódtár: {bundle.name} → HEAD {head[:12]}, {len(fa)} követett fájl, {relacio}")
    return hibak


def sqlite_ellenor(p: Path) -> tuple[str, int]:
    con = sqlite3.connect(f"file:{urllib.parse.quote(str(p))}?mode=ro", uri=True, timeout=5)
    try:
        qc = con.execute("PRAGMA quick_check").fetchone()[0]
        return qc, con.execute("PRAGMA user_version").fetchone()[0]
    finally:
        con.close()


def forras_verzio(p: Path) -> int | None:
    """Az élő forrás `user_version`-je: `immutable=1` (a WAL/SHM-hez nem nyúl), csak olvasva."""
    try:
        con = sqlite3.connect(f"file:{urllib.parse.quote(str(p))}?mode=ro&immutable=1", uri=True, timeout=5)
        try:
            return con.execute("PRAGMA user_version").fetchone()[0]
        finally:
            con.close()
    except sqlite3.Error:
        return None


def az_allapot(cfg, backup: Path, riport: dict) -> list[str]:
    hibak = []
    mappa = mentes.utolso_allapot(backup)
    if mappa is None:
        return [f"nincs {mentes.ALLAPOT_NEV}-* a {backup} alatt"]
    elvart = mentes.allapot_forrasok(cfg)
    lista, hianyzik = [], []
    for rel, forras in elvart:
        masolat = mappa / rel
        if not masolat.is_file():
            hianyzik.append(rel)
            continue
        if masolat.suffix == ".sqlite":
            try:
                qc, ver = sqlite_ellenor(masolat)
            except sqlite3.Error as e:
                hibak.append(f"{rel}: nem nyitható: {e}")
                continue
            if qc != "ok":
                hibak.append(f"{rel}: quick_check = {qc}")
            fv = forras_verzio(forras)
            if fv is not None and fv != ver:
                hibak.append(f"{rel}: user_version {ver} (másolat) ≠ {fv} (forrás)")
            lista.append(f"{rel} v{ver}")
        else:
            try:
                szoveg = masolat.read_text(encoding="utf-8")
                if masolat.suffix == ".jsonl":                  # soronként egy JSON (a bináris mozgásnapló, a füzetnapló)
                    for sor in szoveg.splitlines():
                        if sor.strip():
                            json.loads(sor)
                elif masolat.suffix == ".json":
                    json.loads(szoveg)
                lista.append(rel)
            except (OSError, ValueError) as e:
                hibak.append(f"{rel}: nem JSON: {e}")
    if hianyzik:
        hibak.append(f"az élő állapotfájlnak nincs másolata ({len(hianyzik)}): {', '.join(hianyzik[:20])}"
                     + (" …" if len(hianyzik) > 20 else ""))
    riport["allapot"] = {"mappa": mappa.name, "ellenorizve": lista}
    print(f"[C] állapot: {mappa.name} — {len(lista)}/{len(elvart)} fájl rendben: {', '.join(lista[:20])}"
          + (f" … (+{len(lista) - 20})" if len(lista) > 20 else ""))
    return hibak


def a_ritmus(cfg, backup: Path, riport: dict) -> list[str]:
    hibak = []
    repo = snapshot.repos(cfg)["vault"]
    b = mentes.legujabb(repo, backup)
    kb = mentes._legujabb(mentes.KODTAR_NEV, backup)
    kor = lambda p: "nincs" if p is None else f"{(time.time() - p.stat().st_mtime) / 3600:.1f} óra"   # noqa: E731
    friss = mentes.friss(repo, backup, dirty=False) if repo.exists() else None
    ido_perc = int(cfg.section("mentes").get("ido_perc", 30))
    ora = (time.time() - b.stat().st_mtime) / 60 if b else None
    print(f"[D] ritmus: vault-bundle kora {kor(b)}, kódtár-bundle {kor(kb)}; a legutóbbi vault-bundle a HEAD-et tartalmazza: "
          f"{'igen' if friss else 'NEM' if friss is not None else 'nincs tároló'}")
    hiba = mentes.hiba_olvas(cfg)
    if hiba:
        hibak.append(f"mentes-hiba.json van: {mentes.hiba_szoveg(hiba)}")
    if friss is False and (ora is None or ora > 2 * ido_perc):
        # a futó app a gépi kör végén és `ido_perc` percenként ment; ennél régebbi, a HEAD-et nem tartalmazó bundle lyuk
        hibak.append(f"a legutóbbi vault-bundle ({kor(b)}) nem tartalmazza a HEAD-et, és régebbi {2 * ido_perc} percnél")
    riport["ritmus"] = {"vault_bundle_kora": kor(b), "kodtar_bundle_kora": kor(kb), "friss": friss}
    return hibak


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--backup", help="a valódi belső lemezes mentés mappája (alap: a config {backup}, munkafában kötelező)")
    ap.add_argument("--megtart", action="store_true")
    a = ap.parse_args(argv)
    env = munkafa_forras(dict(os.environ))
    cfg = config.load(env)
    valodi_cfg = cfg                  # az „élő” állapotfájlok elvárt listájához; a próba ideiglenes fájljai a `cfg`-é ({tmp})
    if (REPO / ".git").is_file():
        # munkafában a „valódi” var/ a fő checkouté (a `vault.git` melletti mappa); csak OLVASVA, az ideiglenes mappa nem oda megy
        valodi_cfg = cfg_masik_var(env, cfg.path("vault_git").parent)
    backup = Path(a.backup).expanduser() if a.backup else cfg.path("backup")
    if not backup.is_dir():
        print(f"HIBA: nincs mentési mappa: {backup} (--backup)")
        return 2
    d = probamappa(cfg, "c34-mentes", megtart=a.megtart, szkript="kiadas_mentes.py")
    print(f"[próba] mentés: {backup}  ·  próbamappa: {d}")
    riport: dict = {"backup": str(backup), "ido": dt.datetime.now().isoformat(timespec="seconds")}
    osszes = []
    try:
        for nev, fn in (("A vault", lambda: a_vault(cfg, backup, d, riport)), ("B kódtár", lambda: a_kodtar(cfg, backup, d, riport)),
                        ("C állapot", lambda: az_allapot(valodi_cfg, backup, riport)), ("D ritmus", lambda: a_ritmus(valodi_cfg, backup, riport))):
            try:
                hibak = fn()
            except (visszaallitas.VisszaallitasHiba, snapshot.SnapshotError, OSError, sqlite3.Error) as e:
                hibak = [f"kivétel: {e}"]
            print(f"{'RENDBEN' if not hibak else 'ELTÉRÉS'} · {nev}" + ("" if not hibak else ": " + " | ".join(hibak)))
            osszes += [f"{nev}: {h}" for h in hibak]
        riport["eltérések"] = osszes
        (d / "riport.json").write_text(json.dumps(riport, ensure_ascii=False, indent=1), encoding="utf-8")
    finally:
        if not a.megtart:
            shutil.rmtree(d, ignore_errors=True)
        else:
            print(f"[próba] a próbamappa megmaradt (--megtart): {d} — törlése csak a felhasználó igenjével")
    print("RENDBEN: a mentés visszaállítható" if not osszes else f"ELTÉRÉS: {len(osszes)} lelet")
    return 0 if not osszes else 1


if __name__ == "__main__":
    sys.exit(main())
