"""C11a kézi mérés: a Manifold összes folyamatának memóriája és CPU-ja egy nagy fotós jegyzet megnyitásakor
(a discover nem futtatja).

    var/venv/bin/python -B tests/kezi/memoria_meres.py [--cimke elotte] [--mp 90] [--jegyzet "<út>.md"] [--megtart]

A vault APFS-klónján (mint a `proba_app.py`) indítja a valódi `Manifold.app`-ot úgy, hogy a felület állapota
már a megadott jegyzettel nyitott fület tartalmaz (alapból a Kézi kör F1 leletének 26 fotós jegyzete), így
nem kell kattintgatni; a valódi vaulthoz nem nyúl. Mintát vesz 0,5 s-onként `ps`-sel: a héj, a core és a
héj indítása óta induló `com.apple.WebKit.*` segédfolyamatok (WebContent, Networking, GPU) összegzett RSS-e
és CPU-ja. A mintavétel alatt a jegyzetet lapozni kell (görgetés a képeken): a CSV és az összegzés a
`{tmp}`-be, illetve a kimenetre kerül. Egyszerre csak egy Manifold-példány fusson (a valódi vaulton futó
legyen bezárva), és más alkalmazás ne indítson WKWebView-t a mérés alatt.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from core import config, frame  # noqa: E402
from _kornyezet import elkulonit, probamappa, gyermek_pidek, megvar_kilepest  # noqa: E402

NEWTON = "F02 - Dinamika/Elmélet/02 - Newton II. törvénye.md"


def allapot(jegyzet: str) -> dict:
    """A felület mentett állapota: egy panel, benne egy fül a jegyzettel, Live Preview."""
    return {"verzio": 1, "tema": "rendszer", "szerkesztoMod": "elo", "oldalsav": {"szelesseg": 264, "nyitva": True},
            "jobbPanel": {"szelesseg": 288, "nyitva": False, "visszahivatkozasok": True, "emlitesek": False,
                          "kimeno": False, "vazlat": True},
            "munkaterulet": {"gyoker": {"tipus": "panel", "id": "pmeres", "fulek": [
                {"id": "fmeres", "ut": jegyzet, "nezet": {"mod": "elo"}}], "aktiv": "fmeres"},
                "aktivPanelId": "pmeres"},
            "legutobbiFajlok": [jegyzet], "legutobbiParancsok": []}


PS = re.compile(r"^\s*(\d+)\s+(\d+)\s+(\d+)\s+([\d.,]+)\s+(\w+ \w+ +\d+ [\d:]+ \d+)\s+(.*)$")


def folyamatok() -> list[dict]:
    ki = subprocess.run(["ps", "-axo", "pid=,ppid=,rss=,pcpu=,lstart=,command="], capture_output=True, text=True).stdout
    out = []
    for sor in ki.splitlines():
        m = PS.match(sor)
        if m:
            kezd = datetime.strptime(re.sub(r"\s+", " ", m.group(5)), "%a %b %d %H:%M:%S %Y").timestamp()
            out.append({"pid": int(m.group(1)), "ppid": int(m.group(2)), "rss": int(m.group(3)) / 1024,
                        "cpu": float(m.group(4).replace(",", ".")), "kezd": kezd, "cmd": m.group(6)})
    return out


def sajat(ps: list[dict], pid: int, t0: float) -> dict[str, list[dict]]:
    """A mért csoportok: a héj, a core (a héj gyermekei) és a héjjal együtt indult WebKit-segédek."""
    csop = {"hej": [], "core": [], "webcontent": [], "networking": [], "gpu": []}
    for p in ps:
        if p["pid"] == pid:
            csop["hej"].append(p)
        elif p["ppid"] == pid:
            csop["core"].append(p)
        elif "com.apple.WebKit." in p["cmd"] and p["kezd"] >= t0 - 1:
            k = "webcontent" if "WebContent" in p["cmd"] else "networking" if "Networking" in p["cmd"] else "gpu"
            csop[k].append(p)
    return csop


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cimke", default="meres")
    ap.add_argument("--mp", type=int, default=90)
    ap.add_argument("--jegyzet", default=NEWTON)
    ap.add_argument("--megtart", action="store_true")
    a = ap.parse_args()
    cfg = config.load()
    d = probamappa(cfg, "c11a-meres", megtart=a.megtart, szkript="memoria_meres.py")
    vault, git = frame.trial_clone(cfg, d)
    (d / "felulet.json").write_text(json.dumps(allapot(a.jegyzet), ensure_ascii=False), encoding="utf-8")
    env = elkulonit(d, cfg, vault=vault, vault_git=git, home=False)
    print(f"[mérés] klón: {d}", flush=True)
    app = REPO / "Manifold.app" / "Contents" / "MacOS" / "Manifold"
    t0 = time.time()
    p = subprocess.Popen([str(app)], env=env)
    print(f"[mérés] app: pid {p.pid} — {a.mp} s-ig mintázok; LAPOZD végig a jegyzetet (görgetés a képeken)", flush=True)
    sorok, csucs, osszeg_cpu, n = [], 0.0, 0.0, 0
    cpu_csucs = 0.0
    vege = t0 + a.mp
    try:
        while time.time() < vege and p.poll() is None:
            csop = sajat(folyamatok(), p.pid, t0)
            rss = {k: sum(x["rss"] for x in v) for k, v in csop.items()}
            cpu = sum(x["cpu"] for v in csop.values() for x in v)
            ossz = sum(rss.values())
            sorok.append({"t": round(time.time() - t0, 1), "osszes_mb": round(ossz, 1), "cpu": round(cpu, 1),
                          **{k: round(v, 1) for k, v in rss.items()}})
            csucs, cpu_csucs = max(csucs, ossz), max(cpu_csucs, cpu)
            osszeg_cpu += cpu
            n += 1
            time.sleep(0.5)
    finally:
        gyerekek = gyermek_pidek(p.pid)          # a core a héj gyermeke: a leállása (lezáró mentés) a törlés előtt fejeződjék be
        if p.poll() is None:
            p.terminate()
            try:
                p.wait(timeout=30)
            except subprocess.TimeoutExpired:
                p.kill()
        if not megvar_kilepest(gyerekek):
            print("[figyelem] a core 90 s alatt sem lépett ki; a próbamappa törlése elmarad", flush=True)
            a.megtart = True
        if not a.megtart:
            shutil.rmtree(d, ignore_errors=True)
    kulcsok = ["t", "osszes_mb", "cpu", "hej", "core", "webcontent", "networking", "gpu"]
    kimenet = cfg.path("tmp") / f"memoria-{a.cimke}.csv"
    kimenet.write_text("\n".join([",".join(kulcsok)] + [",".join(str(s[k]) for k in kulcsok) for s in sorok]), encoding="utf-8")
    if sorok:
        utolso = sorok[-1]
        print(f"[mérés] {a.cimke}: minta {n} db · első {sorok[0]['osszes_mb']} MB · CSÚCS {csucs:.0f} MB · "
              f"utolsó {utolso['osszes_mb']} MB (WebContent {utolso['webcontent']}, héj {utolso['hej']}, core {utolso['core']}) · "
              f"CPU csúcs {cpu_csucs:.0f}% · CPU átlag {osszeg_cpu / n:.0f}%  → {kimenet}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
