"""C31 (1. és 3. pont): az átállás paritás-riportja a VALÓDI vault APFS-klónján — a discover nem futtatja.

    MOS_VAULT="<vault>" MOS_VAULT_GIT="<os>/var/vault.git" MOS_LEGACY="<a régi telepítés gyökere>" \\
    [MOS_REGI_UT="<a régi telepítés abszolút úttagja>"] \\
    PYTHONPATH=. <venv python> -B tests/kezi/atallas_riport.py --state <os>/var/state --backup <backup> [--megtart]

Öt szakasz; a riport a próbamappa `riport.json`-ja és a kimenet utolsó sora (RENDBEN / ELTÉRÉS):
  A. **Legacy-próbák a 2.0 írásai után**: klón (`frame.trial_clone`) + core a klónon (`_kornyezet.elkulonit`); a legacy
     `mfd.py all` (csak olvasó próbák: `READONLY_ALL`) előtte; egy reprezentatív 2.0-írássor a core API-ján át (szerkesztés
     tíz jegyzeten, tulajdonság, új jegyzet útvonalas linkből, napi jegyzet, új `.base`, átnevezés, majd az átnevezés
     visszavonása); a `mfd.py all` utána. Kapu: az új találatok mind a menet saját (`Mos-Forras: pult-*`) commitjainak
     útjain állnak. A legacy `-B`-vel, `PYTHONDONTWRITEBYTECODE=1`-gyel, a cwd és a `--json-out` a próbamappában fut; előtte
     és utána a legacy `modulok/eszkozok` és a valódi vault stat-lenyomata — változásnál ELTÉRÉS.
  B. **Gráf és link**: a `graf_paritas.py` és a `link_feloldas_paritas.py` kapu (alfolyamatban, a kimenetük utolsó sora).
  C. **A pillanatkép-tároló folytonossága** (a klónon): `fsck --connectivity-only`, a commitok száma, a legacy-korszak
     (a C02 klónja, 2026-09-30 előtti) legújabb commitja a HEAD őse, a `Mos-Forras` értékkészlete; a `{backup}` minden
     `vault-*.bundle`-je `bundle verify` a klón ellen.
  D. **A láncok állapotfájljai** (csak olvasva): a médiajobok `state.json`-jai (JSON-e; a `MOS_REGI_UT` úttagot tartalmazó
     régi abszolút út), a bináris mozgásnapló (`binaris_naplo.olvas`), a füzetlánc mappája.
  E. **Visszaállítási próba** (3. pont): a legújabb `vault-*.bundle` a `core.visszaallitas`-szal egy üres helyre a
     próbamappában; minden visszaállított fájl bájtra összevetve a valódi vaulttal; az eltérés csak a bundle óta
     rögzített vagy még nem rögzített változás lehet (a klón tárolójából ellenőrizve).
"""
from __future__ import annotations

import collections
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
KEZI = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(KEZI))
from core import config, frame, snapshot, visszaallitas  # noqa: E402
from _kornyezet import elkulonit, probamappa  # noqa: E402
from sema_proba import Core, legacy_eszkozok  # noqa: E402

LEGACY_KORSZAK_VEGE = "2026-09-30T23:59:59"
MENET_FORMATUM = "%x01%H%x09%(trailers:key=Mos-Forras,valueonly,separator=)"


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def lenyomat(gyoker: Path, kihagy=(".git",)) -> str:
    """Stat-lenyomat (út, méret, mtime_ns) egy fán: a csak-olvasás bizonyítéka."""
    h = hashlib.sha1()
    for d, almappak, fajlok in os.walk(gyoker):
        almappak[:] = sorted(a for a in almappak if a not in kihagy)
        for f in sorted(fajlok):
            try:
                st = os.lstat(os.path.join(d, f))
            except OSError:
                continue
            h.update(f"{os.path.join(d, f)}|{st.st_size}|{st.st_mtime_ns}\n".encode("utf-8", "surrogateescape"))
    st = os.stat(gyoker)
    h.update(f"{st.st_mtime_ns}".encode())
    return h.hexdigest()


def git(git_dir: Path, *args: str, check: bool = True) -> str:
    env = {**snapshot.hermetikus_env(), "GIT_OPTIONAL_LOCKS": "0"}
    p = subprocess.run(["git", "--git-dir", str(git_dir), "-c", "core.quotepath=false", *args], capture_output=True,
                       text=True, encoding="utf-8", errors="replace", env=env)
    if check and p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {p.stderr.strip()}")
    return p.stdout


# ---------------------------------------------------------------- A. legacy-próbák

PROBAK = ["scope", "schema", "links", "orphan", "granularity", "coverage", "canvas", "nn", "style", "media"]   # a legacy READONLY_ALL


def mfd_all(eszkozok: Path, vault: Path, ki: Path) -> dict[str, set]:
    """A legacy `mfd.py all` csak olvasó próbái EGYENKÉNT (a `all` az első összeomló próbánál megállna): próbánként a
    találatok `(tárgy, üzenet)` halmaza; az összeomló próba kulcsa `!<név>` a hiba utolsó sorával."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("MOS_", "MANIFOLD_"))}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    ki_: dict[str, set] = {}
    for nev in PROBAK:
        cel = ki.with_name(f"{ki.stem}-{nev}.json")
        p = subprocess.run([sys.executable, "-B", str(eszkozok / "mfd.py"), nev, "--root", str(vault), "--json-out", str(cel),
                            "--json", "--limit", "1"], capture_output=True, text=True, env=env, cwd=str(ki.parent), timeout=1800)
        if p.returncode != 0 or not cel.is_file():
            ki_[f"!{nev}"] = {("(összeomlott)", (p.stderr.strip().splitlines() or ["?"])[-1][:200])}
            continue
        for r in json.loads(cel.read_text(encoding="utf-8")):
            ki_[nev] = {(nfc(str(t.get("subject", ""))), str(t.get("message", ""))) for t in r.get("tetelek", [])}
    return ki_


def menet(core: Core, vault: Path, git_dir: Path) -> dict:
    """A reprezentatív 2.0-írássor; → {lepesek, hibak}."""
    lepesek, hibak = [], []

    def ok(nev, s, r, vart=(200, 201)):
        (lepesek if s in vart else hibak).append(f"{nev}: {s}" + ("" if s in vart else f" {str(r)[:200]}"))
        return r

    fa = core.get("/api/vault/fa")[1]["fajlok"]
    jeloltek = [f["ut"] for f in fa if f["tipus"] == "md" and "/" in f["ut"]
                and not f["ut"].startswith(("AI0", "_Template", "X01"))]
    szerk = jeloltek[:: max(1, len(jeloltek) // 10)][:10]
    for ut in szerk:
        s, f = core.get("/api/vault/fajl", ut=ut)
        ok(f"szerkesztés {ut}", *core.k("PUT", "/api/vault/fajl", {"ut": ut, "tartalom": f["tartalom"] + "\nC31 próbasor.\n",
                                                                     "alap": f["hash"], "elso": True, "pillanat": True}))
    # tulajdonság: a Tags egy elemmel bővül (a séma értékkészletéből) — a panel útja: modosit → PUT
    ut = szerk[0]
    s, f = core.get("/api/vault/fajl", ut=ut)
    from core.index.maszk import FM_RE
    m = FM_RE.match(f["tartalom"])
    if m:
        r = core.k("POST", "/api/vault/tulajdonsagok/modosit", {"ut": ut, "fm": m.group(0), "forras": "felhasznalo",
                                                                 "muvelet": "beallit", "kulcs": "NN", "ertek": [], "tipus": "multitext"})[1]
        if r.get("ok") and r.get("fm_uj") and r["fm_uj"] != m.group(0):
            ok("tulajdonság", *core.k("PUT", "/api/vault/fajl", {"ut": ut, "tartalom": f["tartalom"].replace(m.group(0), r["fm_uj"], 1),
                                                                  "alap": f["hash"], "elso": False, "pillanat": True}))
        else:
            lepesek.append(f"tulajdonság: nincs változás ({r.get('problemak') or 'ok'})")
    else:
        lepesek.append("tulajdonság: kihagyva (a jegyzetnek nincs frontmatterje)")
    mappa = ut.rsplit("/", 1)[0] if "/" in ut else ""
    s, r = core.k("POST", "/api/vault/uj", {"link": {"cel": f"{mappa.lower()}/C31 próba új jegyzet", "forras": ut}})
    uj = ok("új jegyzet útvonalas linkből", s, r).get("ut")
    ok("napi jegyzet", *core.k("POST", "/api/naplo/ma", {"datum": "2026-10-07"}))
    ok("új .base", *core.k("POST", "/api/vault/uj", {"mappa": mappa, "nev": "C31 próba nézet", "tipus": "base"}))
    if uj:
        cel_mappa = uj.rpartition("/")[0]
        cel = (cel_mappa + "/" if cel_mappa else "") + "C31 próba átnevezett.md"
        s, t = core.k("POST", "/api/vault/atnevezes/terv", {"ut": uj, "uj": cel})
        if s == 200 and t.get("ok"):
            s, a = core.k("POST", "/api/vault/atnevezes", {"ut": uj, "uj": cel, "terv_hash": t["terv_hash"]})
            ok("átnevezés", s, a)
            if s == 200 and a.get("pillanat"):
                kor = None
                for sor in git(git_dir, "log", "-1", "--format=%(trailers:key=Mos-Kor,valueonly)", a["pillanat"]).splitlines():
                    kor = sor.strip() or kor
                ok("az átnevezés visszavonása", *core.k("POST", "/api/pillanat/vault/visszavonas", {"kor": kor}))
        else:
            hibak.append(f"átnevezés terve: {s} {t}")
    return {"lepesek": lepesek, "hibak": hibak}


def menet_utak(git_dir: Path, head0: str) -> set[str]:
    szoveg = git(git_dir, "log", "--name-only", f"--format={MENET_FORMATUM}", f"{head0}..HEAD")
    utak = set()
    for blokk in szoveg.split("\x01")[1:]:
        fej, _, nevek = blokk.partition("\n")
        if fej.split("\t")[-1].strip().startswith("pult-"):
            utak.update(nfc(n) for n in nevek.split("\n") if n)
    return utak


def a_szakasz(cfg, d: Path, vault: Path, git_dir: Path) -> dict:
    esz = legacy_eszkozok(cfg)
    env = elkulonit(d, cfg, vault=vault, vault_git=git_dir, home=True)
    p = subprocess.Popen([str(REPO / "bin" / "mos"), "core", "start"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env)
    try:
        core = Core(json.loads(p.stdout.readline())["port"])
        for _ in range(600):
            s, a = core.get("/api/vault/index")
            if s == 200 and a.get("kesz"):
                break
            time.sleep(0.5)
        else:
            raise SystemExit("az index nem épült fel")
        t0 = time.time()
        elotte = mfd_all(esz, vault, d / "mfd-elotte.json")
        print(f"[riport] A: mfd.py all előtte ({time.time() - t0:.0f} s): "
              + ", ".join(f"{k} {len(v)}" for k, v in elotte.items()), flush=True)
        head0 = git(git_dir, "rev-parse", "HEAD").strip()
        m = menet(core, vault, git_dir)
        print(f"[riport] A: a menet {len(m['lepesek'])} lépés, {len(m['hibak'])} hiba", flush=True)
    finally:
        p.stdin.close()
        try:
            p.wait(timeout=60)
        except subprocess.TimeoutExpired:
            p.kill()
    utana = mfd_all(esz, vault, d / "mfd-utana.json")
    sajat = menet_utak(git_dir, head0)
    uj, magyarazatlan = {}, {}
    for nev in sorted(set(elotte) | set(utana)):
        tobb = utana.get(nev, set()) - elotte.get(nev, set())
        uj[nev] = len(tobb)
        idegen = sorted(f"{s}: {u}" for s, u in tobb if not any(s == x or s.startswith(x) or x in s for x in sajat))
        if idegen:
            magyarazatlan[nev] = idegen[:20]
    eltunt = {n: len(elotte.get(n, set()) - utana.get(n, set())) for n in elotte}
    return {"elotte": {k: len(v) for k, v in elotte.items()}, "utana": {k: len(v) for k, v in utana.items()},
            "uj": uj, "eltunt": eltunt, "menet": m, "menet_utak": sorted(sajat), "magyarazatlan": magyarazatlan}


# ---------------------------------------------------------------- B. gráf és link

def b_szakasz() -> dict:
    ki = {}
    for szkript in ("graf_paritas.py", "link_feloldas_paritas.py"):
        p = subprocess.run([sys.executable, "-B", str(KEZI / szkript)], capture_output=True, text=True, timeout=1800,
                           env={**os.environ, "PYTHONPATH": str(REPO)}, cwd=str(REPO))
        sorok = [s for s in (p.stdout + p.stderr).splitlines() if s.strip()]
        ki[szkript] = {"kod": p.returncode, "utolso": sorok[-6:]}
        print(f"[riport] B: {szkript} → {p.returncode}: {sorok[-1] if sorok else ''}", flush=True)
    return ki


# ---------------------------------------------------------------- C. a tároló folytonossága

def c_szakasz(git_dir: Path, backup: Path) -> dict:
    fsck = subprocess.run(["git", "--git-dir", str(git_dir), "fsck", "--connectivity-only", "--no-progress"],
                          capture_output=True, text=True, env={**snapshot.hermetikus_env(), "GIT_OPTIONAL_LOCKS": "0"})
    sorok = git(git_dir, "log", "--format=%H\t%cI\t%(trailers:key=Mos-Forras,valueonly,separator=)").splitlines()
    commitok = [s.split("\t") for s in sorok if s]
    legacy = [c for c in commitok if c[1] <= LEGACY_KORSZAK_VEGE]
    forrasok = collections.Counter(c[2] or "(nincs)" for c in commitok)
    os_e = bool(legacy) and subprocess.run(["git", "--git-dir", str(git_dir), "merge-base", "--is-ancestor", legacy[0][0], "HEAD"],
                                           env=snapshot.hermetikus_env()).returncode == 0
    bundlek = {}
    for b in sorted(backup.glob("vault-*.bundle")) if backup.is_dir() else []:
        p = subprocess.run(["git", "--git-dir", str(git_dir), "bundle", "verify", "-q", str(b)], capture_output=True, text=True,
                           env=snapshot.hermetikus_env())
        bundlek[b.name] = "rendben" if p.returncode == 0 else p.stderr.strip()[-200:]
    return {"fsck": fsck.returncode, "fsck_kimenet": fsck.stdout.strip()[-400:] + fsck.stderr.strip()[-400:],
            "commitok": len(commitok), "legacy_korszak": len(legacy), "legacy_legujabb": legacy[0][:2] if legacy else None,
            "legacy_a_head_ose": os_e, "legregebbi": commitok[-1][1] if commitok else None,
            "mos_forras": dict(forrasok.most_common()), "bundlek": bundlek}


# ---------------------------------------------------------------- D. állapotfájlok

def _allapot_ala(cfg, kulcs: str, state: Path) -> Path:
    """A konfigurált `kulcs` mappa a `--state` mappa alatt (a mappanév a konfigból jön, nem beégetett)."""
    try:
        return state / cfg.path(kulcs).relative_to(cfg.path("state"))
    except ValueError:                      # a kulcs nem a `{state}` alatt van: a konfigurált út marad
        return cfg.path(kulcs)


def d_szakasz(cfg, state: Path) -> dict:
    from core import binaris_naplo
    regi_ut = os.environ.get("MOS_REGI_UT", "")                  # a régi telepítés abszolút úttagja (nincs alapértéke)
    jobs = sorted(_allapot_ala(cfg, "video_jobs", state).glob("*/state.json"))
    hibas, regi_utas = [], []
    for p in jobs:
        try:
            t = p.read_text(encoding="utf-8")
            json.loads(t)
        except (OSError, ValueError) as e:
            hibas.append(f"{p.parent.name}: {e}")
            continue
        if regi_ut and regi_ut in t:
            regi_utas.append(p.parent.name)
    naplo = state / "binaris-naplo.jsonl"
    nyers_sorok = len(naplo.read_text(encoding="utf-8").splitlines()) if naplo.is_file() else 0
    olvasott = len(binaris_naplo.olvas(naplo))

    def fajlok(m: Path) -> dict:
        if not m.is_dir():
            return {"van": False}
        db, js, rossz = 0, 0, []
        for p in m.rglob("*"):
            if p.is_file():
                db += 1
                if p.suffix == ".json":
                    js += 1
                    try:
                        json.loads(p.read_text(encoding="utf-8"))
                    except (OSError, ValueError):
                        rossz.append(str(p.relative_to(m)))
        return {"van": True, "fajl": db, "json": js, "hibas_json": rossz[:10]}

    return {"media_jobs": len(jobs), "media_hibas": hibas[:10], "media_regi_abszolut_ut": len(regi_utas),
            "binaris_naplo_sor": nyers_sorok, "binaris_naplo_olvasott": olvasott,
            "fuzet": fajlok(_allapot_ala(cfg, "fuzet", state))}


# ---------------------------------------------------------------- E. visszaállítás

def e_szakasz(cfg, d: Path, backup: Path, vault: Path, klon_git: Path) -> dict:
    bundlek = sorted(backup.glob("vault-*.bundle")) if backup.is_dir() else []
    if not bundlek:
        return {"bundle": None, "uzenet": f"nincs vault-bundle: {backup}"}
    b = bundlek[-1]
    hely = d / "visszaallitott"
    hely.mkdir()
    ucfg = config.load(elkulonit(hely, cfg, vault=hely / "Manifold", vault_git=hely / "vault.git"))
    t0 = time.time()
    r = visszaallitas.visszaallit(ucfg, b)
    ido = time.time() - t0
    bhead = r["head"]
    valtozott = set(nfc(x) for x in git(klon_git, "diff", "--name-only", "--no-renames", bhead, "HEAD").splitlines() if x)
    allapot = subprocess.run(["git", "--git-dir", str(klon_git), "--work-tree", str(vault), "status", "--porcelain=v1", "-z",
                              "--untracked-files=no"], capture_output=True, text=True,
                             env={**snapshot.hermetikus_env(), "GIT_OPTIONAL_LOCKS": "0"}).stdout
    nem_rogzitett = {nfc(x[3:]) for x in allapot.split("\0") if len(x) > 3}
    azonos, magyarazott, magyarazatlan = 0, collections.Counter(), []
    for ut in r["irt"]:
        uj = (hely / "Manifold" / ut).read_bytes()
        valodi = vault / ut
        try:
            regi = valodi.read_bytes()
        except OSError:
            regi = None
        if regi == uj:
            azonos += 1
        elif nfc(ut) in valtozott:
            magyarazott["a bundle óta rögzített változás"] += 1
        elif nfc(ut) in nem_rogzitett or regi is None:
            magyarazott["még nem rögzített (vagy törölt) változás"] += 1
        else:
            magyarazatlan.append(ut)
    media = sum(1 for p in vault.rglob("*") if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".png", ".pdf", ".mp4"))
    return {"bundle": b.name, "bundle_meret_mb": round(b.stat().st_size / 1e6, 1), "head": bhead, "ido_s": round(ido, 1),
            "fajlok": r["fajlok"], "kiirva": len(r["irt"]), "bajtra_azonos": azonos, "magyarazott": dict(magyarazott),
            "magyarazatlan": magyarazatlan[:20], "kihagyva": r["kihagyva"][:10], "status": len(r["status"]),
            "media_a_vaultban_nem_resze": media}


# ---------------------------------------------------------------- fő

def main() -> int:
    megtart = "--megtart" in sys.argv

    def arg(nev):
        return Path(sys.argv[sys.argv.index(nev) + 1]).expanduser() if nev in sys.argv else None
    cfg = config.load()
    state = arg("--state") or cfg.path("state")
    backup = arg("--backup") or cfg.path("backup")
    esz = legacy_eszkozok(cfg)
    valodi_vault = cfg.path("vault")
    l_elotte, v_elotte = lenyomat(esz), lenyomat(valodi_vault)
    d = probamappa(cfg, "c31-riport", megtart=megtart, szkript="atallas_riport.py")
    print(f"[riport] próbamappa: {d}", flush=True)
    vault, git_dir = frame.trial_clone(cfg, d)
    riport = {"ido": dt.datetime.now().isoformat(timespec="seconds"), "valodi_vault": str(valodi_vault)}
    try:
        riport["C"] = c_szakasz(git_dir, backup)
        print(f"[riport] C: {riport['C']['commitok']} commit, legacy-korszak {riport['C']['legacy_korszak']}, "
              f"ős: {riport['C']['legacy_a_head_ose']}, fsck {riport['C']['fsck']}, bundle {len(riport['C']['bundlek'])}", flush=True)
        riport["E"] = e_szakasz(cfg, d, backup, valodi_vault, git_dir)
        print(f"[riport] E: {json.dumps({k: v for k, v in riport['E'].items() if k != 'kihagyva'}, ensure_ascii=False)}", flush=True)
        riport["D"] = d_szakasz(cfg, state)
        print(f"[riport] D: {json.dumps(riport['D'], ensure_ascii=False)}", flush=True)
        riport["A"] = a_szakasz(cfg, d, vault, git_dir)
        print(f"[riport] A: új találat {riport['A']['uj']}, megmagyarázatlan {len(riport['A']['magyarazatlan'])}", flush=True)
        riport["B"] = b_szakasz()
    finally:
        riport["csak_olvasas"] = {"legacy": lenyomat(esz) == l_elotte, "vault": lenyomat(valodi_vault) == v_elotte}
        (d / "riport.json").write_text(json.dumps(riport, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    hibak = []
    if not riport["csak_olvasas"]["legacy"]:
        hibak.append("a legacy eszközmappája megváltozott")
    if not riport["csak_olvasas"]["vault"]:
        hibak.append("a valódi vault megváltozott a futás alatt (a felhasználó dolgozott? futtasd újra)")
    if riport["A"]["menet"]["hibak"] or riport["A"]["magyarazatlan"]:
        hibak.append("A: a menet hibája vagy megmagyarázatlan legacy-találat")
    if any(v["kod"] != 0 for v in riport["B"].values()):
        hibak.append("B: gráf- vagy link-kapu")
    c = riport["C"]
    if c["fsck"] != 0 or not c["legacy_a_head_ose"] or any(v != "rendben" for v in c["bundlek"].values()):
        hibak.append("C: a tároló folytonossága")
    if riport["E"].get("magyarazatlan"):
        hibak.append("E: megmagyarázatlan eltérés a visszaállításban")
    print(f"[riport] JSON: {d / 'riport.json'}")
    print("RENDBEN: a paritás-riport tiszta" if not hibak else "ELTÉRÉS: " + "; ".join(hibak))
    if not megtart:
        shutil.copy(d / "riport.json", cfg.path("tmp") / f"c31-riport-{time.strftime('%Y%m%d-%H%M%S')}.json")
        shutil.rmtree(d, ignore_errors=True)
    return 0 if not hibak else 1


if __name__ == "__main__":
    sys.exit(main())
