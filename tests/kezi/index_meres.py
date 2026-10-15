"""C06 kész-feltételei: teljes újraindexelés < 30 s (valódi vault); egy módosítás < 200 ms alatt látszik
az API-ban (a valódi vault APFS-klónján).

    bin/mos exec var/venv/bin/python -B tests/kezi/index_meres.py [--n 20] [--megtart]   (a discover nem futtatja)

1. Teljes építés a valódi vaulton, CSAK OLVASVA, ideiglenes DB-be (`{tmp}` alatt): háromszor, az idő és
   a DB mérete; utána az újraindulás (csak stat-vizsgálat) ideje.
2. APFS-klón (`cp -c -R`) a vaultról a `{tmp}/c06-meres-<idő>/` alá; a core a klónra indul (külön
   index, futások, feladatsor, nem létező `vault.git`: nincs pillanatkép). `n` módosítás véletlen
   jegyzetekben (egy egyedi szó hozzáfűzése, mint egy külső szerkesztő), és az idő, amíg a
   `/api/vault/kereses` megtalálja. A valódi vaulthoz nem nyúl; a próbamappa a végén törlődik.
"""
import http.client
import json
import os
import random
import shutil
import statistics
import subprocess
import sys
import threading
import time
import urllib.parse
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from core import config, server  # noqa: E402
from _kornyezet import TITOK, cfg_elkulonitve, probamappa  # noqa: E402
from core.index import feloldas, indexelo  # noqa: E402


class _Ki:
    def __init__(self):
        self.sorok, self.jel = [], threading.Event()

    def write(self, s):
        self.sorok.append(s)
        self.jel.set()

    def flush(self):
        pass


def epites(cfg, d: Path) -> None:
    for i in range(3):
        ix = indexelo.Index(cfg_elkulonitve(d / f"epites-{i}", cfg))       # a valódi vault csak olvasva
        ix.figyelo_fajta, ix.lekerdezes_mp = "lekerdezes", 3600
        t0 = time.perf_counter()
        ix.indit()
        ix.var(300)
        t = time.perf_counter() - t0
        a = ix.allapot()
        ix.leallit()
        meret = sum(p.stat().st_size for p in (d / f"epites-{i}" / "index").iterdir()) / 1e6
        print(f"  teljes építés {i + 1}: {t:.2f} s  ({a['fajlok']} fájl, {a['jegyzetek']} jegyzet, DB {meret:.0f} MB)")
    ix = indexelo.Index(cfg_elkulonitve(d / "epites-0", cfg))
    ix.figyelo_fajta, ix.lekerdezes_mp = "lekerdezes", 3600
    t0 = time.perf_counter()
    ix.indit()
    ix.var(300)
    print(f"  újraindulás (csak stat): {time.perf_counter() - t0:.2f} s")
    ix.leallit()


def latszas(cfg, d: Path, n: int) -> list[float]:
    klon = d / "Manifold"
    t0 = time.perf_counter()
    subprocess.run(["cp", "-c", "-R", str(cfg.path("vault")), str(klon)], check=True)
    print(f"  APFS-klón: {time.perf_counter() - t0:.1f} s")
    kcfg = cfg_elkulonitve(d, cfg, vault=klon)       # a pillanatkép-tároló nem él, a naptár-segéd nincs, a mentés a próbamappába
    r, w = os.pipe()
    stdin_w, stdin_r = os.fdopen(w, "wb"), os.fdopen(r, "rb")
    ki = _Ki()
    szal = threading.Thread(target=server.start, args=(kcfg,), kwargs={"stdin": stdin_r, "out": ki}, daemon=True)
    szal.start()
    ki.jel.wait(10)
    port = json.loads(ki.sorok[0])["port"]

    def get(vegpont, **q):
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        c.request("GET", vegpont + "?" + urllib.parse.urlencode(q),
                  headers={"Host": f"127.0.0.1:{port}", "X-Manifold": TITOK})
        return json.loads(c.getresponse().read())

    try:
        t0 = time.perf_counter()
        while not get("/api/vault/index").get("kesz"):
            time.sleep(0.05)
        print(f"  a core indexe a klónon: {time.perf_counter() - t0:.2f} s")
        jegyzetek = [lemez for rp, lemez in feloldas.bejaras(klon) if rp.endswith(".md")]
        rnd = random.Random(6)
        idok = []
        for i in range(n):
            p = klon / rnd.choice(jegyzetek)
            szo = f"zc06meres{i}x{rnd.randrange(10**6)}"
            time.sleep(0.3)                                  # nem egy kötegben: mindegyik külön esemény
            t0 = time.perf_counter()
            with open(p, "a", encoding="utf-8") as fh:
                fh.write(f"\n{szo}\n")
            while get("/api/vault/kereses", q=szo).get("osszes") != 1:
                if time.perf_counter() - t0 > 10:
                    raise RuntimeError(f"10 s alatt sem látszik: {p}")
                time.sleep(0.002)
            idok.append((time.perf_counter() - t0) * 1000)
        return idok
    finally:
        stdin_w.close()
        szal.join(30)
        stdin_r.close()


def main() -> int:
    n = int(sys.argv[sys.argv.index("--n") + 1]) if "--n" in sys.argv else 20
    cfg = config.load()
    d = probamappa(cfg, "c06-meres", megtart="--megtart" in sys.argv, szkript="index_meres.py")
    try:
        print("1. teljes újraindexelés (valódi vault, csak olvasva)")
        epites(cfg, d)
        print(f"2. módosítás → látszik az API-ban (APFS-klón, {n} módosítás)")
        idok = latszas(cfg, d, n)
        print(f"  medián {statistics.median(idok):.0f} ms, max {max(idok):.0f} ms, min {min(idok):.0f} ms")
        return 0 if max(idok) < 200 else 1
    finally:
        if "--megtart" not in sys.argv:
            shutil.rmtree(d)                                 # a saját var/tmp próbamappánk
        else:
            print(f"megtartva: {d}")


if __name__ == "__main__":
    sys.exit(main())
