"""C10 kész-feltétele: az átnevezés/áthelyezés hibátlan a vault APFS-klónján (a discover nem futtatja).

    var/venv/bin/python -B tests/kezi/atnevezes_proba.py        (… --megtart: a klón megmarad)

1. `frame.trial_clone`: a vault és a `vault.git` APFS-klónja a `{tmp}/c10-atnevezes-<idő>/` alá; a core a klónra
   indul, elkülönített index/zár/állapottal. A valódi vaulthoz és a valódi `var/vault.git`-hez nem nyúl: az
   elején és a végén a valódi vault stat-lenyomata és a valódi tároló HEAD-je egyezik.
2. Forgatókönyvek VALÓDI jegyzeteken (a klón gráfjából választva): a legtöbb visszahivatkozású jegyzet; képet
   beágyazó jegyzet; canvasból hivatkozott jegyzet; azonos alapnevű jegyzetek egyike (elrabolt linkek); NFD nevű
   jegyzet áthelyezése; csak kis-nagybetű-csere; (C11a, 21. döntés) a legtöbb kívülről hivatkozott szöveges MAPPA
   átnevezése és áthelyezése, NFD nevű mappa, médiát tartalmazó mappa. Mindegyiknél:
     terv → végrehajtás (a core saját próbájával) → a próba EGYÜTT a szkriptben, függetlenül újra (lemezről:
     minden korábban feloldott link a várt célra old) → a terven kívüli fájlok bájtra azonosak → pontosan egy
     `pult-szerkeszto` gépi commit a várt trailerekkel → VISSZAVONÁS → a klón bájtra és (lemezen álló) névre
     azonos az eredetivel.
3. Riport: `var/runs/atnevezes-<idő>.json`. Kilépési kód 0: minden rendben.
"""
import collections
import hashlib
import http.client
import json
import os
import shutil
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from core import config, frame  # noqa: E402
from core.index import feloldas  # noqa: E402
from _kornyezet import TITOK, elkulonit, probamappa  # noqa: E402

SZOVEGES = (".md", ".canvas", ".base", ".json", ".txt", ".csv", ".yml", ".yaml", ".vtt", ".srt")
PROBA_MAPPA = "Manifold-proba"
nfc = lambda s: unicodedata.normalize("NFC", s)  # noqa: E731


def manifeszt(gyoker: Path) -> dict[str, str]:
    """Nyers (lemezen álló) útvonal → szöveges fájlra sha256, másra méret+mtime."""
    ki = {}
    for d, mappak, fajlok in os.walk(gyoker):
        for f in fajlok:
            p = Path(d) / f
            if not p.is_file():
                continue
            rel = str(p.relative_to(gyoker))
            if f.lower().endswith(SZOVEGES):
                ki[rel] = "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()
            else:
                st = p.stat()
                ki[rel] = f"meta:{st.st_size}:{st.st_mtime_ns}"
    return ki


def lenyomat(gyoker: Path) -> str:
    h = hashlib.sha256()
    for rp, lemez in feloldas.bejaras(gyoker):
        st = os.stat(gyoker / lemez)
        h.update(f"{rp}\0{st.st_size}\0{st.st_mtime_ns}\n".encode())
    return h.hexdigest()


def git_fej(git: Path) -> str:
    return subprocess.run(["git", "--git-dir", str(git), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()


class Core:
    def __init__(self, port: int):
        self.port = port

    def kerd(self, method: str, ut: str, body=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=600)
        c.request(method, ut, body=json.dumps(body) if body is not None else None,
                  headers={"Host": f"127.0.0.1:{self.port}", "X-Manifold": TITOK, "Content-Type": "application/json"})
        r = c.getresponse()
        return r.status, json.loads(r.read() or b"{}")


def forgatokonyvek(vault: Path) -> list[dict]:
    """A klón gráfjából választott esetek: [{nev, regi, uj}]."""
    g = feloldas.graf(vault)
    beje = {rp: lemez for rp, lemez in feloldas.bejaras(vault)}
    bejovo: dict[str, set] = collections.defaultdict(set)
    for s, cs in g["out"].items():
        for c in cs:
            if c != s:
                bejovo[c].add(s)
    md = [f for f in g["files"] if f.lower().endswith(".md") and not f.startswith(PROBA_MAPPA + "/")]
    legtobb = sorted((f for f in md if bejovo[f]), key=lambda f: (-len(bejovo[f]), f))
    szoveg = {}

    def tartalom(f):
        if f not in szoveg:
            szoveg[f] = (vault / beje[f]).read_bytes().decode("utf-8", "replace")
        return szoveg[f]

    def uj_nev(f, szuf=" — átnevezve"):
        mappa, _, nev = f.rpartition("/")
        return (mappa + "/" if mappa else "") + nev[:-3] + szuf + ".md"

    ki = []
    hasznalt: set[str] = set()

    def uj_eset(nev, jeloltek, szuf):
        for f in jeloltek:
            if f not in hasznalt:
                hasznalt.add(f)
                ki.append({"nev": nev, "regi": f, "uj": uj_nev(f, szuf)})
                return

    uj_eset("legtöbb visszahivatkozás", legtobb, " — átnevezve")
    uj_eset("képet beágyazó jegyzet (van bejövő linkje is)",
            [f for f in legtobb if "![[" in tartalom(f) and ".jpg" in tartalom(f).lower()], " (kép)")
    uj_eset("canvasból hivatkozott jegyzet",
            [f for f in legtobb if any(s.lower().endswith(".canvas") for s in bejovo[f])], " (vászon)")
    csop = collections.defaultdict(list)
    for f in md:
        csop[f.rsplit("/", 1)[-1]].append(f)
    dupla = [(n, fs) for n, fs in csop.items() if len(fs) > 1 and any(bejovo[f] for f in fs)]
    if dupla:
        n, fs = max(dupla, key=lambda x: max(len(bejovo[f]) for f in x[1]))
        f = max(fs, key=lambda f: len(bejovo[f]))
        hasznalt.add(f)
        ki.append({"nev": "azonos alapnevű jegyzet áthelyezése (elrabolt linkek)", "regi": f,
                   "uj": f"{PROBA_MAPPA}/{n}"})
    nfd = [f for f in legtobb if nfc(beje[f]) != beje[f] and f not in hasznalt]
    if nfd:
        hasznalt.add(nfd[0])
        ki.append({"nev": "NFD nevű jegyzet áthelyezése", "regi": nfd[0], "uj": f"{PROBA_MAPPA}/{nfd[0].rsplit('/', 1)[-1]}"})
    for f in legtobb:
        nev = f.rsplit("/", 1)[-1]
        if nev[0].swapcase() != nev[0] and f not in hasznalt:
            ki.append({"nev": "csak kis-nagybetű-csere", "regi": f, 
                       "uj": f.rsplit("/", 1)[0] + "/" + nev[0].swapcase() + nev[1:] if "/" in f else nev[0].swapcase() + nev[1:]})
            break
    return ki


def mappak(gyoker: Path) -> set[str]:
    """A mappák (az üresek is) NFC útja, a rejtetteket kihagyva."""
    ki = set()
    for d, ms, _ in os.walk(gyoker):
        ms[:] = [m for m in ms if not m.startswith(".")]
        for m in ms:
            ki.add(nfc(os.path.relpath(os.path.join(d, m), gyoker)))
    return ki


def mappa_forgatokonyvek(vault: Path, api: "Core") -> list[dict]:
    """C11a: a klón mappáiból választott esetek: a legtöbb kívülről hivatkozott, csak szöveges mappa (átnevezés és
    áthelyezés), NFD nevű szöveges mappa, és egy médiát tartalmazó mappa."""
    g = feloldas.graf(vault)
    beje = {rp: lemez for rp, lemez in feloldas.bejaras(vault)}
    mappak_r: dict[str, list[str]] = collections.defaultdict(list)
    for f in g["files"]:
        if f.startswith(PROBA_MAPPA + "/") or f.startswith("."):
            continue
        mappa = f.rsplit("/", 1)[0] if "/" in f else ""
        while mappa:
            mappak_r[mappa].append(f)
            mappa = mappa.rsplit("/", 1)[0] if "/" in mappa else ""
    jeloltek = []
    for m, fs in mappak_r.items():
        if not 2 <= len(fs) <= 200:
            continue
        if not all(f.lower().endswith((".md", ".canvas")) for f in fs):
            continue
        fs_s = set(fs)
        kivulrol = sum(1 for s_, cs in g["out"].items() if s_ not in fs_s for c in set(cs) if c in fs_s)
        jeloltek.append((kivulrol, m, fs))
    jeloltek.sort(key=lambda x: (-x[0], x[1]))
    ki = []
    if jeloltek:
        _, m, _ = jeloltek[0]
        szulo, _, nev = m.rpartition("/")
        ki.append({"nev": "a legtöbb kívülről hivatkozott szöveges mappa átnevezése", "regi": m, "mappa": True,
                   "uj": (szulo + "/" if szulo else "") + nev + " — átnevezve"})
        ki.append({"nev": "ugyanaz a mappa áthelyezése a próbamappába", "regi": m, "mappa": True,
                   "uj": f"{PROBA_MAPPA}/{nev}"})
    for _, m, _ in jeloltek[:15]:                       # a link-átírást is kikényszerítő mappa (útvonalas linkek)
        szulo, _, nev = m.rpartition("/")
        uj = (szulo + "/" if szulo else "") + nev + " — linkekkel"
        kod, terv = api.kerd("POST", "/api/vault/atnevezes/terv", {"ut": m, "uj": uj})
        if kod == 200 and terv.get("ok") and terv.get("modositott_linkek", 0) > 0:
            ki.append({"nev": "mappa átnevezése link-átírással", "regi": m, "mappa": True, "uj": uj})
            break
    nfd = [(k, m, fs) for k, m, fs in jeloltek if nfc(os.path.basename(m)) != os.path.basename(m) or
           any(nfc(beje[f]) != beje[f] for f in fs[:50])]
    if len(nfd) and (not jeloltek or nfd[0][1] != jeloltek[0][1]):
        ki.append({"nev": "lemezen NFD nevű elemeket tartalmazó mappa áthelyezése", "regi": nfd[0][1], "mappa": True,
                   "uj": f"{PROBA_MAPPA}/{os.path.basename(nfd[0][1])}"})
    for m, fs in mappak_r.items():
        if any(f.lower().endswith((".jpg", ".png", ".pdf")) for f in fs) and any(f.lower().endswith(".md") for f in fs):
            ki.append({"nev": "médiát tartalmazó mappa", "regi": m, "mappa": True,
                       "uj": m + " — átnevezve"})
            break
    return ki


def fuggetlen_proba(elotte: dict, utana: dict, lek: dict[str, str]) -> list[str]:
    """A szkript saját referencia-próbája (nem a core kódja): minden korábban feloldott link a várt célra old."""
    hibak = []
    vart_fajlok = {lek.get(x, x) for x in elotte["files"]}
    if set(utana["files"]) != vart_fajlok:
        hibak.append("a fájlhalmaz eltér a vártól")
    for forras, lista in elotte["linkek"].items():
        masik = utana["linkek"].get(lek.get(forras, forras))
        if masik is None or len(masik) != len(lista):
            hibak.append(f"{forras}: a linkek száma/hiánya")
            continue
        for i, ((_, h0), (c1, h1)) in enumerate(zip(lista, masik)):
            if h0 is not None and h1 != lek.get(h0, h0):
                hibak.append(f"{forras}: {i + 1}. link „{c1.strip()[:60]}” → {h1!r}")
    return hibak[:20]


def main() -> int:
    megtart = "--megtart" in sys.argv
    cfg = config.load()
    valodi_vault, valodi_git = cfg.path("vault"), cfg.path("vault_git")
    valodi_elotte, fej_elotte = lenyomat(valodi_vault), git_fej(valodi_git)
    d = probamappa(cfg, "c10-atnevezes", megtart=megtart, szkript="atnevezes_proba.py")
    print(f"[átnevezés] klón: {d}", flush=True)
    vault, git = frame.trial_clone(cfg, d)
    (vault / PROBA_MAPPA).mkdir(exist_ok=True)
    env = elkulonit(d, cfg, vault=vault, vault_git=git, home=True)
    core = subprocess.Popen([str(REPO / "bin" / "mos"), "core", "start"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env)
    hibak: list[str] = []
    riport = {"esetek": []}
    try:
        api = Core(json.loads(core.stdout.readline())["port"])
        for _ in range(240):
            if api.kerd("GET", "/api/vault/index")[1].get("kesz"):
                break
            time.sleep(0.5)
        kezdeti = manifeszt(vault)
        esetek = forgatokonyvek(vault) + mappa_forgatokonyvek(vault, api)
        print(f"[átnevezés] {len(esetek)} forgatókönyv, {len(kezdeti)} fájl a klónban", flush=True)
        for e in esetek:
            nev, regi, uj = e["nev"], e["regi"], e["uj"]
            sor = {"nev": nev, "regi": regi, "uj": uj, "hibak": []}
            riport["esetek"].append(sor)
            h = sor["hibak"]
            (vault / PROBA_MAPPA).mkdir(exist_ok=True)       # a visszavonás az üres mappát is törölheti (git)
            if e.get("blokkolt"):
                kod, terv = api.kerd("POST", "/api/vault/atnevezes/terv", {"ut": regi, "uj": uj})
                if terv.get("ok") or not terv.get("blokkolok"):
                    h.append("a várt blokkolás elmaradt")
                print(f"  {'✗' if h else '✓'} {nev}: {regi} → {uj}: {(terv.get('blokkolok') or ['?'])[0][:80]}")
                hibak += [f"{nev}: {x}" for x in h]
                continue
            eredeti_szovegek = {str(p.relative_to(vault)): p.read_bytes() for p in vault.rglob("*") if p.is_file() and p.suffix.lower() in SZOVEGES}
            elotte_m = manifeszt(vault)
            elotte_d = mappak(vault)
            fej0 = git_fej(git)
            t0 = time.perf_counter()
            kod, terv = api.kerd("POST", "/api/vault/atnevezes/terv", {"ut": regi, "uj": uj})
            t_terv = time.perf_counter() - t0
            if kod != 200 or not terv.get("ok"):
                h.append(f"a terv nem ok: {kod} {terv.get('blokkolok') or terv.get('hiba')}")
                print(f"  ✗ {nev}: {h[-1]}")
                hibak += [f"{nev}: {x}" for x in h]
                continue
            sor.update(fajlok=len(terv["fajlok"]), modositott_linkek=terv["modositott_linkek"],
                       osszes_link=terv["osszes_link"], uj_feloldott=terv["uj_feloldott"], terv_s=round(t_terv, 2))
            elotte_g = feloldas.hivatkozasok(vault)
            t0 = time.perf_counter()
            kod, r = api.kerd("POST", "/api/vault/atnevezes", {"ut": regi, "uj": uj, "terv_hash": terv["terv_hash"]})
            sor["vegrehajtas_s"] = round(time.perf_counter() - t0, 2)
            if kod != 200:
                h.append(f"a végrehajtás {kod}: {r.get('hiba')} {r.get('proba_hibak', '')}")
                print(f"  ✗ {nev}: {h[-1]}")
                hibak += [f"{nev}: {x}" for x in h]
                if manifeszt(vault) != elotte_m:
                    h.append("hibás végrehajtás után a klón állapota eltér az előttitől")
                continue
            # (a) független referencia-próba
            utana_g = feloldas.hivatkozasok(vault)
            lek = {nfc(x["regi"]): nfc(x["uj"]) for x in terv["atnevezesek"]} if terv.get("mappa") else {nfc(regi): nfc(uj)}
            if terv.get("mappa") and len(lek) != terv["mozgo_fajlok"]:
                h.append("a mozgó fájlok listája csonkolt: a független próba nem teljes")
            h += [f"független próba: {x}" for x in fuggetlen_proba(elotte_g, utana_g, lek)]
            # (b) a terven kívüli fájlok bájtra azonosak
            utana_m = manifeszt(vault)
            valt = {nfc(k) for k in set(elotte_m) | set(utana_m) if elotte_m.get(k) != utana_m.get(k)}
            var = {nfc(regi), nfc(uj), *lek, *lek.values(), *map(nfc, [x["ut"] for x in terv["fajlok"]]), *map(nfc, r["modositott"])}
            if terv.get('mappa'):
                # A Finder metaadata (.DS_Store) a teljes könyvtárral mozog, de nem hivatkozási cél.
                var.update(nfc(k) for k in elotte_m if k.startswith(regi + '/'))
                var.update(nfc(uj + k[len(regi):]) for k in elotte_m if k.startswith(regi + '/'))
            if not valt <= var:
                h.append(f"a terven kívül változott: {sorted(valt - var)[:5]}")
            # (c) pontosan egy gépi commit, a várt trailerekkel
            log = subprocess.run(["git", "--git-dir", str(git), "log", "--format=%H%x09%(trailers:key=Mos-Forras,valueonly,separator=)%x09"
                                  "%(trailers:key=Mos-Kor,valueonly,separator=)%x09%(trailers:key=Mos-Tetel,valueonly,separator=)",
                                  f"{fej0}..HEAD"], capture_output=True, text=True).stdout.strip().splitlines()
            gepi = [x.split("\t") for x in log if x.split("\t")[1:2] == ["pult-szerkeszto"]]
            if len(gepi) != 1 or not gepi[0][2].startswith("ATNEV-") or gepi[0][3] != nfc(uj) or gepi[0][0] != r["pillanat"]:
                h.append(f"a commit nem a vártak szerint: {log}")
            # (d) szöveges művelet: git-visszavonás; média/case-only: ellenőrzött visszamozgatás.
            if r.get('visszavonhato', True):
                kod, u = api.kerd("POST", "/api/pillanat/vault/visszavonas", {"sha": r["pillanat"]})
            else:
                sor['visszaut'] = 'kézi visszamozgatás (média/case-only)'
                kod, vt = api.kerd("POST", "/api/vault/atnevezes/terv", {"ut": uj, "uj": regi})
                if kod == 200 and vt.get('ok'):
                    kod, u = api.kerd("POST", "/api/vault/atnevezes", {"ut": uj, "uj": regi, "terv_hash": vt['terv_hash']})
                else:
                    u = vt
                if kod == 200:
                    # A visszamozgatás referenciái az eredetiekre oldanak. Az átírás normalizálhat linkalakot;
                    # ezt a próba után visszatesszük a fixture eredeti bájtjaira, a következő független esethez.
                    h += fuggetlen_proba(elotte_g, feloldas.hivatkozasok(vault), {})
                    vissza = manifeszt(vault)
                    if {k: v for k, v in vissza.items() if not k.lower().endswith(SZOVEGES)} != {
                            k: v for k, v in elotte_m.items() if not k.lower().endswith(SZOVEGES)}:
                        h.append('a visszamozgatás után a média eltér')
                    for rp, adat in eredeti_szovegek.items():
                        if (vault / rp).read_bytes() != adat: (vault / rp).write_bytes(adat)
            if kod != 200:
                h.append(f"a visszaállítás {kod}: {u.get('hiba')}")
            else:
                vissza_m = manifeszt(vault)
                if vissza_m != elotte_m:
                    valt2 = sorted(k for k in set(elotte_m) | set(vissza_m) if elotte_m.get(k) != vissza_m.get(k))[:5]
                    h.append(f"a visszaállítás után eltér: {valt2}")
            # (a próbamappát a szkript hozza létre előre: a git az üressé vált célmappát a visszavonáskor törli — ismert)
            if terv.get("mappa") and (mappak(vault) ^ elotte_d) - {PROBA_MAPPA}:
                h.append(f"a visszavonás után a mappaszerkezet eltér: {sorted((mappak(vault) ^ elotte_d) - {PROBA_MAPPA})[:5]}")
            sor["modositott"] = len(r["modositott"])
            print(f"  {'✗' if h else '✓'} {nev}: {regi} → {uj} | fájl {sor['fajlok']}, link {sor['modositott_linkek']}/{sor['osszes_link']} "
                  f"| terv {sor['terv_s']} s, végrehajtás {sor['vegrehajtas_s']} s", flush=True)
            for x in h:
                print("      ", x)
            hibak += [f"{nev}: {x}" for x in h]
            time.sleep(0.5)             # az index a visszavonás eseményeit felvegye
        if manifeszt(vault) != kezdeti:
            hibak.append("az összes forgatókönyv után a klón eltér a kezdetitől")
    finally:
        core.stdin.close()
        core.wait(timeout=120)
    if lenyomat(valodi_vault) != valodi_elotte or git_fej(valodi_git) != fej_elotte:
        hibak.append("A VALÓDI vault vagy tárolója változott! (a próba nem a klónon dolgozott?)")
    else:
        print("[átnevezés] a valódi vault stat-lenyomata és a valódi vault.git HEAD-je változatlan")
    riport["hibak"] = hibak
    ut = cfg.path("runs") / time.strftime("atnevezes-%Y%m%d-%H%M%S.json")
    ut.parent.mkdir(parents=True, exist_ok=True)
    ut.write_text(json.dumps(riport, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[átnevezés] riport: {ut}")
    if not megtart:
        shutil.rmtree(d)        # a saját var/tmp próbamappánk
    print("RENDBEN" if not hibak else f"HIBA ({len(hibak)})")
    return 1 if hibak else 0


if __name__ == "__main__":
    sys.exit(main())
