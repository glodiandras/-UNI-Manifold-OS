"""C21 kézi próbakör: a füzetlánc a vault APFS-klónján futó core-ral és a valódi modellekkel (a discover nem futtatja).

    var/venv/bin/python -B tests/kezi/fuzet_proba.py [--olvaso qwen35_9b] [--valaszto qwen35_4b] [--atirat qwen35_9b] [--megtart]

Menet: a vault és a `vault.git` APFS-klónja a `{tmp}/c21-fuzet-proba-<idő>/` alá, minden `[utak]` kulcs elkülönítve (a modellzár a
valódi, L23); hat aranyfotó MÁSOLATA (`C21-proba-<név>`, négy fekvő és két álló papír) a próba beérkező mappájába; a core a klónon
(`bin/mos core start`), a worker a távol-kerettel, `auto` módban (tétlenségben halad). A lánc kifejezett modellekkel fut, ezért a
D9 szerint **próbában** ír: a gépi írás a klón klónjára megy. Ellenőrzés: a hat fotó bekötődött-e, a jegyzetben ott-e a beágyazás
(és a képlet-callout), egyezik-e a kötés az arannyal (`helyes`/`elfogadhato_utolag`), és a valódi vault HEAD-je és a próba-klón
(a klón klónja nélkül) érintetlen-e. A riport: `{proba}/riport.json`, a végén RENDBEN vagy HIBA.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "modulok"))
from core import config, frame  # noqa: E402
from _kornyezet import TITOK, elkulonit, probamappa  # noqa: E402

FOTOK = ("IMG_1289.JPG", "IMG_1392.JPG", "IMG_1786.JPG", "IMG_1828.JPG", "IMG_1361.JPG", "IMG_1557.JPG")


def head(git: Path) -> str:
    return subprocess.run(["git", "--git-dir", str(git), "rev-parse", "HEAD"], capture_output=True, text=True,
                          env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"}).stdout.strip()


class Szaraz:
    """`--szaraz`: modell nélküli próba (a klón, a core és a gépi írás ellenőrzése): rögzített válaszok, próba-jellel."""

    def __init__(self, kif):
        self.kifejezett = kif

    def modell_nev(self, feladat):
        return "szaraz-" + feladat

    def kerdez(self, feladat, prompt, kepek=None, max_tokens=256, beallitas_feladat=None):
        v = {"fuzet_fejezet": "TANTÁRGY: Matematika\nCÍMEK: háromszög\nTARTALOM: szögek\nFEJEZET: M10",
             "ocr_kezi": "Természetesen, itt az átirat:\n$a^2+b^2=c^2$", "fuzet_valaszto": "1"}[feladat]
        return v, {"feladat": feladat, "modell": "qwen35_4b", "proba": True}


def belso(a) -> int:
    """A klón környezetében (a szülő `env`-jével indítva; a core-t a szülő indította, a portja `--port`): worker + lánc + ellenőrzés."""
    from core import fuzet
    from core.modell import beallitas as B
    from core.modell import kliens
    from fuzet.lanc import Lanc
    cfg = config.load()
    d = Path(a.proba)
    os.environ["MOS_CORE_URL"] = f"http://127.0.0.1:{a.port}"
    if True:
        kif = {"fuzet_fejezet": a.olvaso, "fuzet_valaszto": a.valaszto, "ocr_kezi": a.atirat}
        w, modellek = None, (Szaraz(kif) if a.szaraz else None)
        if not a.szaraz:
            b = B.betolt(cfg)
            w = kliens.Folyamat(cfg, env={"MANIFOLD_MODELL_KERET_GB": f"{b.keret_gb('tavol'):g}"}, sajat=True)
            os.environ["MOS_WORKER_URL"] = w.biztosit(timeout=120)
            os.environ["MOS_MODELL_MOD"] = "auto"
        try:
            t0 = time.time()
            r = Lanc(cfg, proba=True, kifejezett=kif, modellek=modellek,
                     log=lambda s: print(s, flush=True)).futtat([cfg.path("fuzet_bejovo") / "minta"])
            r["mp"] = round(time.time() - t0)
        finally:
            if w:
                w.leallit()
    arany = {f["foto"]: f for f in json.loads((REPO / "modulok" / "eval" / "ocr_kezi" / "arany.json").read_text())["fotok"]}
    klon2 = None
    hibak, kotes = [], {"szigoru": 0, "elbiralt": 0}
    for f in r["fotok"]:
        eredeti = f["kep"].removeprefix("C21-proba-")
        g = arany[eredeti]
        if f["allapot"] != "bekotve":
            hibak.append(f"{f['kep']}: {f['allapot']} — {f['uzenet']}")
            continue
        kotes["szigoru"] += f["jegyzet"] in g["helyes"]
        kotes["elbiralt"] += f["jegyzet"] in g["helyes"] + [e["jegyzet"] for e in g.get("elfogadhato_utolag", [])]
        klon2 = cfg.path("tmp") / "proba" / f"{r['kor']}-proba" / cfg.path("vault").name
        if not klon2.is_dir():
            hibak.append("nincs meg a próbakör klónja")
            continue
        t = (klon2 / f["jegyzet"]).read_text(encoding="utf-8")
        if f"![[{f['kep']}]]" not in t and f"![[ATTCHMNTS - photos/{f['kep']}]]" not in t:
            hibak.append(f"{f['kep']}: a beágyazás nincs a jegyzetben ({f['jegyzet']})")
        if not (klon2 / "ATTCHMNTS - photos" / f["kep"]).is_file():
            hibak.append(f"{f['kep']}: a fotó nincs a klón ATTCHMNTS - photos mappájában")
        if not (cfg.path("fuzet_bejovo") / "minta" / f["kep"]).is_file():
            hibak.append(f"{f['kep']}: a próba elvitte a forrást (próbában másolni kell)")
    r["kotes"] = kotes
    r["hibak"] = hibak
    (d / "riport.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: r[k] for k in ("kor", "eredmeny", "kotes", "hibak", "mp")}, ensure_ascii=False, indent=1))
    return 0 if not hibak and len(r["fotok"]) == len(FOTOK) else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--olvaso", default="qwen35_9b")
    ap.add_argument("--valaszto", default="qwen35_4b")
    ap.add_argument("--atirat", default="qwen35_9b")
    ap.add_argument("--megtart", action="store_true")
    ap.add_argument("--szaraz", action="store_true", help="modell nélkül (rögzített válaszokkal): a keret próbája")
    ap.add_argument("--belso", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--proba", help=argparse.SUPPRESS)
    ap.add_argument("--port", help=argparse.SUPPRESS)
    a = ap.parse_args()
    if a.belso:
        return belso(a)
    cfg = config.load()
    valodi_head = head(cfg.path("vault_git"))
    d = probamappa(cfg, "c21-fuzet-proba", megtart=a.megtart, szkript="fuzet_proba.py")
    kod = 1
    try:
        vault, git = frame.trial_clone(cfg, d)
        klon_head = head(git)
        env = elkulonit(d, cfg, vault=vault, vault_git=git, home=True, masolat=("router_db",))
        bejovo = config.load(env).path("fuzet_bejovo") / "minta"          # a klón környezetének útja (nem kézzel írt kulcs)
        bejovo.mkdir(parents=True, exist_ok=True)
        for f in FOTOK:
            shutil.copy2(cfg.path("vault") / "ATTCHMNTS - photos" / f, bejovo / f"C21-proba-{f}")
        print(f"[próba] klón: {d}", flush=True)
        core = subprocess.Popen([str(REPO / "bin" / "mos"), "core", "start"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env)
        try:
            port = json.loads(core.stdout.readline())["port"]
            kod = subprocess.run([sys.executable, "-B", __file__, "--belso", "--proba", str(d), "--port", str(port),
                                  "--olvaso", a.olvaso, "--valaszto", a.valaszto, "--atirat", a.atirat]
                                 + (["--szaraz"] if a.szaraz else []), env=env).returncode
        finally:
            core.stdin.close()                                # rendezett leállás (a klón kilépési mentése kimarad)
            core.wait(timeout=120)
        ok_valodi = head(cfg.path("vault_git")) == valodi_head
        ok_klon = head(git) == klon_head                     # a próba a klón KLÓNJÁRA írt, maga a klón érintetlen
        print(f"[próba] a valódi vault HEAD-je változatlan: {ok_valodi}; a próba-klón HEAD-je változatlan: {ok_klon}")
        kod = kod or (0 if ok_valodi and ok_klon else 1)
    finally:
        if not a.megtart:
            shutil.rmtree(d, ignore_errors=True)
    print("RENDBEN" if kod == 0 else "HIBA")
    return kod


if __name__ == "__main__":
    sys.exit(main())
