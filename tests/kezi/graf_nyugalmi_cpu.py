"""C13 kézi mérés: a gráfnézet nyugalmi CPU-használata a valódi Manifold.app-ban (a discover nem futtatja).

    var/venv/bin/python -B tests/kezi/graf_nyugalmi_cpu.py [--eset graf|alap|osztas|rejtett] [--lehul 60] [--mp 60] [--megtart]

A vault APFS-klónján (mint a `memoria_meres.py`) indítja a valódi `Manifold.app`-ot úgy, hogy a felület mentett állapota
már tartalmazza a gráffület; a valódi vaulthoz nem nyúl. A `ps pcpu` élettartam-átlag, ezért itt a **CPU-idő
különbségéből** számolunk: `ps time` a héjra, a core-ra és a héjjal együtt indult `com.apple.WebKit.*` folyamatokra,
`--lehul` másodperc várakozás (az index és a fizika lehűl) után `--mp` másodpercig, 5 s-os ablakokban. A mérés alatt
az egér ne mozogjon az ablak fölött, és más alkalmazás ne indítson WKWebView-t.

Esetek:
  graf      a gráf az aktív fül (globális nézet) — a kapu: az átlagos CPU 0 körül
  alap      csak egy jegyzet nyitva (viszonyítási alap: a héj, a core és a WebKit saját nyugalmi CPU-ja)
  osztas    a gráf a bal panelen, egy jegyzet a jobbon
  rejtett   a gráffül nyitva, de egy másik fül az aktív (a gráf nem is jön létre)
A gráf járuléka = `graf` − `alap`. Ugyanezt mutatja a `window.__grafMeres()`: nyugalomban a képkockák és az
ütemezések száma nem nő (a böngészőpanelben ellenőrizve; a WKWebView-ban a CPU-idő a mérce).
"""
import argparse
import json
import os
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

JEGYZET = "F02 - Dinamika/Elmélet/02 - Newton II. törvénye.md"
GRAF = {"tipus": "graf", "mod": "globalis"}


def ful(azon: str, ut=None, nezet=None) -> dict:
    f = {"id": azon, "ut": ut}
    if nezet:
        f["nezet"] = nezet
    return f


def allapot(eset: str) -> dict:
    """A felület mentett állapota az esethez."""
    if eset == "graf":
        mt = {"gyoker": {"tipus": "panel", "id": "pm", "fulek": [ful("fg", None, GRAF)], "aktiv": "fg"}, "aktivPanelId": "pm"}
    elif eset == "alap":
        mt = {"gyoker": {"tipus": "panel", "id": "pm", "fulek": [ful("fj", JEGYZET, {"mod": "elo"})], "aktiv": "fj"},
              "aktivPanelId": "pm"}
    elif eset == "osztas":
        mt = {"gyoker": {"tipus": "osztas", "id": "om", "irany": "sor", "arany": 0.5,
                         "a": {"tipus": "panel", "id": "pa", "fulek": [ful("fg", None, GRAF)], "aktiv": "fg"},
                         "b": {"tipus": "panel", "id": "pb", "fulek": [ful("fj", JEGYZET, {"mod": "elo"})], "aktiv": "fj"}},
              "aktivPanelId": "pb"}
    elif eset == "rejtett":
        mt = {"gyoker": {"tipus": "panel", "id": "pm", "fulek": [ful("fg", None, GRAF), ful("fj", JEGYZET, {"mod": "elo"})],
                         "aktiv": "fj"}, "aktivPanelId": "pm"}
    else:
        raise SystemExit(f"ismeretlen eset: {eset}")
    return {"verzio": 1, "tema": "rendszer", "szerkesztoMod": "elo", "oldalsav": {"szelesseg": 264, "nyitva": True},
            "jobbPanel": {"szelesseg": 288, "nyitva": False, "visszahivatkozasok": True, "emlitesek": False,
                          "kimeno": False, "vazlat": True},
            "munkaterulet": mt, "legutobbiFajlok": [JEGYZET], "legutobbiParancsok": []}


PS = re.compile(r"^\s*(\d+)\s+(\d+)\s+([\d:.,]+)\s+(\w+ \w+ +\d+ [\d:]+ \d+)\s+(.*)$")


def cpu_ido(s: str) -> float:
    """`ps time` ([[h:]m:]s.cc) másodpercben."""
    mp = 0.0
    for r in s.replace(",", ".").split(":"):
        mp = mp * 60 + float(r)
    return mp


def folyamatok() -> list[dict]:
    ki = subprocess.run(["ps", "-axo", "pid=,ppid=,time=,lstart=,command="], capture_output=True, text=True).stdout
    out = []
    for sor in ki.splitlines():
        m = PS.match(sor)
        if m:
            kezd = datetime.strptime(re.sub(r"\s+", " ", m.group(4)), "%a %b %d %H:%M:%S %Y").timestamp()
            out.append({"pid": int(m.group(1)), "ppid": int(m.group(2)), "ido": cpu_ido(m.group(3)), "kezd": kezd, "cmd": m.group(5)})
    return out


def csoportok(ps: list[dict], pid: int, t0: float) -> dict[int, tuple[str, float]]:
    """pid → (csoport, összes CPU-idő): a héj, a core (a héj gyermekei) és a héjjal együtt indult WebKit-segédek."""
    ki = {}
    for p in ps:
        if p["pid"] == pid:
            ki[p["pid"]] = ("hej", p["ido"])
        elif p["ppid"] == pid:
            ki[p["pid"]] = ("core", p["ido"])
        elif "com.apple.WebKit." in p["cmd"] and p["kezd"] >= t0 - 1:
            k = "webcontent" if "WebContent" in p["cmd"] else "networking" if "Networking" in p["cmd"] else "gpu"
            ki[p["pid"]] = (k, p["ido"])
    return ki


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eset", default="graf")
    ap.add_argument("--lehul", type=int, default=60)
    ap.add_argument("--mp", type=int, default=60)
    ap.add_argument("--megtart", action="store_true")
    a = ap.parse_args()
    cfg = config.load()
    d = probamappa(cfg, "c13-cpu", megtart=a.megtart, szkript="graf_nyugalmi_cpu.py")
    vault, git = frame.trial_clone(cfg, d)
    (d / "felulet.json").write_text(json.dumps(allapot(a.eset), ensure_ascii=False), encoding="utf-8")
    env = elkulonit(d, cfg, vault=vault, vault_git=git, home=False)
    print(f"[cpu] eset: {a.eset} · klón: {d}", flush=True)
    app = REPO / "Manifold.app" / "Contents" / "MacOS" / "Manifold"
    t0 = time.time()
    p = subprocess.Popen([str(app)], env=env)
    print(f"[cpu] app: pid {p.pid} — {a.lehul} s lehűlés, utána {a.mp} s mérés (az egér ne mozogjon az ablak fölött)", flush=True)
    ablakok: list[dict] = []
    try:
        time.sleep(a.lehul)
        elozo, elozo_t = csoportok(folyamatok(), p.pid, t0), time.time()
        vege = time.time() + a.mp
        while time.time() < vege and p.poll() is None:
            time.sleep(5)
            most, most_t = csoportok(folyamatok(), p.pid, t0), time.time()
            ido = {}
            for pid, (cs, t) in most.items():
                regi = elozo.get(pid)
                ido[cs] = ido.get(cs, 0.0) + (t - regi[1] if regi else t)      # új folyamat teljes ideje is számít
            dt = most_t - elozo_t
            ablakok.append({k: round(100 * v / dt, 2) for k, v in ido.items()} | {"osszes": round(100 * sum(ido.values()) / dt, 2)})
            elozo, elozo_t = most, most_t
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
            for gyok, mappak, fajlok in os.walk(d):      # a klón írásvédett fájljai (git-objektumok) is törlődjenek
                for n in [*mappak, *fajlok]:
                    try:
                        os.chmod(os.path.join(gyok, n), 0o700)
                    except OSError:
                        pass
            shutil.rmtree(d, ignore_errors=True)
    if not ablakok:
        print("[cpu] nincs minta (az app idő előtt kilépett)")
        return 1
    kulcsok = sorted({k for w in ablakok for k in w if k != "osszes"})
    atlag = {k: round(sum(w.get(k, 0) for w in ablakok) / len(ablakok), 2) for k in [*kulcsok, "osszes"]}
    csucs = max(w["osszes"] for w in ablakok)
    print(f"[cpu] {a.eset}: {len(ablakok)} ablak (5 s) · ÁTLAG {atlag['osszes']}% · CSÚCS-ablak {csucs}% · bontás {atlag}")
    for i, w in enumerate(ablakok):
        print(f"       {i * 5:3d}–{i * 5 + 5:3d} s: {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
