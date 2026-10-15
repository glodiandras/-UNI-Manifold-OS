"""Ismételhető soak-készlet (C33, T206, A2-soak1-7): a 8 órás „nincs memórianövekedés” cél mérője, rövid futásra is.

    bin/mos exec <python> -B tests/kezi/soak.py --perc 30 [--minta-mp 30] [--leallas | --nincs-leallas] [--kimenet DIR]

A 2. audit soak-szkriptjeinek (`soak.py`, `leallas_repro.py`, `h6_repro.py`, `burst_repro.py`) rendezett utódja:

1. **Álvault** (szintetikus, ~200 jegyzet linkekkel, Bases-fájl, képek) a próbamappában; a SAJÁT core a közös elkülönítő
   segéddel (`_kornyezet.elkulonit`): minden `[utak]` kulcs a próbamappába, a valódi vaulthoz és `var/`-hoz nem nyúl.
2. **Vegyes terhelés** `--perc` percig: szerkesztő-mentések (ütközéssel is), gépi írás és kör/sha szerinti visszavonás,
   átnevezés oda-vissza, külső írás (Finder/Obsidian mintájára), olvasók (keresés, gráf ETag-gel, graf-meta, Bases, fa,
   visszahivatkozás, média Range és kicsinyítés, előzmények, Ma, állapot), tracker-kötegek, WS-kapcsolatok.
3. **Minták** `--minta-mp`-enként (JSONL): RSS, fd (típusonként), szálak, gyermekfolyamatok, WAL-méretek, a kicsinyített képek
   gyorsítótára, a git-commitok száma, a `.manifold-tmp` maradékok; műveletenként a késleltetés.
4. **Összegzés küszöbökkel** (PASS/FAIL): fd és szál a bemelegedés utáni első mintához képest ±20% (+ kis abszolút ráhagyás);
   az RSS második felének trendje ≤ `--rss-meredekseg` MB/óra és a csúcs ≤ 600 MB; műveletenként a késleltetés mediánja az
   utolsó ötödben legfeljebb kétszerese az elsőnek (+5 ms); váratlan 5xx nincs; `.manifold-tmp` nem marad; `git fsck` tiszta.
5. **Három leállás-próba** (friss core-ral, ugyanazon az álvaulton): (a) stdin-zárás beragadt kliensekkel (félbehagyott
   törzs, félbehagyott fejléc, nem olvasó WS) — kilép ≤ 15 s; (b) csak SIGTERM egy félbehagyott törzzsel — kilép ≤ 15 s
   (a H6 vészkijárata 10 s); (c) H6: stdin-zárás egy futó, hosszú lépés közben, majd SIGTERM — kilép ≤ 15 s, és a lépés
   folyamata nem él tovább.

A kimenet a `{runs}/soak-<idő>/` alá (vagy `--kimenet`): `mintak.jsonl`, `naplo.txt`, `osszegzes.json`. Kilépési kód 0: PASS.
Csak a saját core-jának PID-jét állítja le (nincs széles `pkill`).
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import random
import re
import signal
import socket
import statistics
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import config, frame, snapshot  # noqa: E402
from _kornyezet import TITOK, elkulonit, probamappa  # noqa: E402

q = lambda s: urllib.parse.quote(s, safe="")  # noqa: E731
FM = "---\nTags: Mathematics\nSource:\nStatus:\nNN:\nCanvas:\n---\n"
SZAVAK = "alfa beta gamma delta derivalt integral matrix vektor halmaz fuggveny hatarertek sorozat".split()
# A kör-zárért versengő műveletek (gépi írás, átnevezés, visszavonás, pillanatképes mentés) késleltetése a párhuzamos terhelés
# zárvárakozása, nem szivárgás: ezek csak a jelentésben állnak, a stabilitás-kapuban nem. Az előzmények (egy fájl története)
# a commitok számával szándékosan nő.
ZAR_KOTOTT = {"gepi", "atnevezes", "atnev-terv", "atnev-visszavonas", "visszavonas-kor", "visszavonas-sha", "mentes-pillanat"}
TORTENETTEL_NO = {"elozmeny"}
NEM_KAPU = ZAR_KOTOTT | TORTENETTEL_NO | {"kulso-iras", "ws-churn"}
RSS_MIN_PERC = 10                     # az RSS-trend csak ennél hosszabb második félre értékelhető (a bemelegedés torzít)


class Soak:
    def __init__(self, a: argparse.Namespace):
        self.a = a
        self.cfg = config.load()
        self.d = probamappa(self.cfg, "c33-soak", megtart=a.megtart)
        self.vault = self.d / "Manifold"
        self.git = self.d / "vault.git"
        self.extra = {"MOS_PROBA_FELADAT": "1"}        # a H6-próba lépése (csak a klónon/álvaulton létező típus)
        # a feladatsor (és a D8-as indulási szünet) itt rövid: a H6-próba lépése azonnal induljon, és a háttér-karbantartás
        # (a kicsinyített képek takarítása, T177) a terhelés alatt is lefusson — a konfig másolata a próbamappában
        konfig = (REPO / "config" / "os.toml").read_text(encoding="utf-8")
        konfig = re.sub(r"(?m)^(indulasi_szunet_mp\s*=\s*)\d+", r"\g<1>3", konfig)
        (self.d / "os.toml").write_text(konfig, encoding="utf-8")
        self.extra["MOS_CONFIG"] = str(self.d / "os.toml")
        env = elkulonit(self.d, self.cfg, vault=self.vault, vault_git=self.git, home=True)
        env.update(self.extra)
        self.pcfg = config.load(env)
        # az Asszisztens (automatikus modell-feladatok) a soak alatt ki: modellt a soak nem tölt (a router-tábla úgyis üres)
        allapot = self.pcfg.path("state")
        allapot.mkdir(parents=True, exist_ok=True)
        (allapot / "kapcsolok.json").write_text(json.dumps({"asszisztens": False, "tracker": True}), encoding="utf-8")
        self.ki = Path(a.kimenet) if a.kimenet else self.cfg.path("runs") / time.strftime("soak-%Y%m%d-%H%M%S")
        self.ki.mkdir(parents=True, exist_ok=True)
        self.naplo = open(self.ki / "naplo.txt", "a", buffering=1, encoding="utf-8")
        self.mintak_f = open(self.ki / "mintak.jsonl", "a", buffering=1, encoding="utf-8")
        self.stat: dict[str, list] = defaultdict(list)
        self.zar = threading.Lock()
        self.hibak: dict[str, int] = defaultdict(int)
        self.hiba_mintak: dict[str, list[str]] = {}
        self.stop = threading.Event()
        self.mintak: list[dict] = []
        self.port = self.pid = self.token = None
        self.proc: subprocess.Popen | None = None
        self.n = defaultdict(int)
        self.gepi_shak: list[tuple[str, str]] = []
        self.etag: dict[str, str] = {}
        self.t0 = time.time()

    # ------------------------------------------------------------------ napló, álvault, core
    def kiir(self, *a) -> None:
        s = time.strftime("%H:%M:%S ") + " ".join(str(x) for x in a)
        print(s, flush=True)
        self.naplo.write(s + "\n")

    def alvault(self) -> None:
        (self.vault / ".obsidian").mkdir(parents=True)
        rnd = random.Random(1)
        for mappa in "ABCDE":
            for i in range(30):
                p = self.vault / mappa / f"{mappa}{i:02d}.md"
                p.parent.mkdir(parents=True, exist_ok=True)
                linkek = " ".join(f"[[{rnd.choice('ABCDE')}{rnd.randrange(30):02d}]]" for _ in range(4))
                p.write_text(FM + f"# {mappa}{i:02d}\n\n{linkek} [[R]]\n\n" + " ".join(rnd.choice(SZAVAK) for _ in range(300)) + "\n",
                             encoding="utf-8")
        for mappa, db, szakasz in (("Szerk", 20, "Napló"), ("Gep", 5, "Gyakorlás"), ("Kulso", 10, None)):
            (self.vault / mappa).mkdir()
            for i in range(db):
                (self.vault / mappa / f"{mappa[0].lower()}{i:02d}.md").write_text(
                    FM + f"# {mappa[0].lower()}{i:02d}\n\n" + (f"## {szakasz}\n\n" if szakasz else "") + "kezdet\n", encoding="utf-8")
        (self.vault / "Atnev").mkdir()
        (self.vault / "Atnev/R.md").write_text(FM + "# R\n\nátnevezendő\n", encoding="utf-8")
        (self.vault / "Nezet.base").write_text('filters:\n  and:\n    - file.hasLink(link("R"))\nviews:\n  - type: table\n'
                                               '    name: T\n    order:\n      - file.name\n', encoding="utf-8")
        (self.vault / "Kep").mkdir()
        try:
            from PIL import Image
            for i in range(4):
                Image.new("RGB", (2400, 1800), (40 * i, 100, 150)).save(self.vault / f"Kep/p{i}.jpg", quality=80)
        except ImportError:
            pass
        (self.vault / "Kep/vid.mp4").write_bytes(os.urandom(6 * 1024 * 1024))
        repo = snapshot.repos(self.pcfg)["vault"]
        repo.init()
        repo.commit("alap", {"Mos-Forras": "kezi"})

    def core_indit(self, nev: str) -> None:
        self.stderr = open(self.ki / f"core-{nev}.log", "ab")
        env = elkulonit(self.d, self.cfg, vault=self.vault, vault_git=self.git, home=True)
        env.update(self.extra)
        self.proc = subprocess.Popen([sys.executable, "-B", "-m", "core", "start"], cwd=str(REPO), env=env,
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr)
        k = json.loads(self.proc.stdout.readline())
        self.port, self.pid = k["port"], k["pid"]
        for _ in range(600):
            try:
                if self.req("GET", "/api/vault/index")[1].get("kesz"):
                    break
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.05)
        self.token = self.req("GET", "/api/allapot")[1]["media_token"]
        self.kiir(f"core ({nev}) indult: port {self.port}, pid {self.pid}")

    # ------------------------------------------------------------------ HTTP / WS
    def req(self, metodus: str, ut: str, body=None, timeout: float = 60, fejlec: dict | None = None):
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode()
        r = urllib.request.Request(f"http://127.0.0.1:{self.port}{ut}", data=data, method=metodus,
                                   headers={"X-Manifold": TITOK, "Content-Type": "application/json", **(fejlec or {})})
        try:
            with urllib.request.urlopen(r, timeout=timeout) as v:
                raw = v.read()
                return v.status, (json.loads(raw or b"{}") if "json" in v.headers.get("Content-Type", "") else raw), v.headers
        except urllib.error.HTTPError as e:
            try:
                b = json.loads(e.read() or b"{}")
            except ValueError:
                b = {}
            if e.code >= 500:
                with self.zar:
                    minta = self.hiba_mintak.setdefault(f"{metodus} {ut.split('?')[0]} {e.code}", [])
                    if len(minta) < 5:
                        minta.append(str(b.get("hiba", b))[:300])
            return e.code, b, e.headers

    def raw_get(self, ut: str, fejlec: dict | None = None) -> int:
        r = urllib.request.Request(f"http://127.0.0.1:{self.port}{ut}", headers=fejlec or {})
        try:
            with urllib.request.urlopen(r, timeout=60) as v:
                v.read()
                return v.status
        except urllib.error.HTTPError as e:
            return e.code

    def ws(self, olvas: bool = True, rcvbuf: int | None = None) -> "WS":
        return WS(self.port, olvas, rcvbuf)

    # ------------------------------------------------------------------ mérés
    def meres(self, muv: str, fn) -> object:
        t0 = time.perf_counter()
        try:
            kod = fn()
        except Exception as e:  # noqa: BLE001
            kod = "EXC:" + type(e).__name__
            with self.zar:
                self.hibak[f"{muv}:{type(e).__name__}:{str(e)[:80]}"] += 1
        with self.zar:
            self.stat[muv].append((time.time(), (time.perf_counter() - t0) * 1000, kod))
        return kod

    def hurok(self, fn, szunet: float) -> threading.Thread:
        def f():
            while not self.stop.is_set():
                try:
                    fn()
                except Exception as e:  # noqa: BLE001
                    with self.zar:
                        self.hibak[f"hurok:{fn.__name__}:{type(e).__name__}:{str(e)[:100]}"] += 1
                    time.sleep(0.5)
                self.stop.wait(szunet)
        t = threading.Thread(target=f, name=fn.__name__, daemon=True)
        t.start()
        return t

    # ------------------------------------------------------------------ terhelők
    def szerkeszto(self) -> None:
        rp = f"Szerk/s{random.randrange(20):02d}.md"
        k, d, _ = self.req("GET", "/api/vault/fajl?ut=" + q(rp))
        if k != 200:
            self.meres("mentes-olvas", lambda: k)
            return
        rossz = random.random() < 0.1
        elso, pill = random.random() < 0.3, random.random() < 0.3
        self.n["szerk"] += 1
        uj = d["tartalom"] + f"sor {self.n['szerk']} {time.time()}\n"
        muv = "mentes-utkozes" if rossz else ("mentes-pillanat" if (elso or pill) else "mentes")
        self.meres(muv, lambda: self.req("PUT", "/api/vault/fajl", {"ut": rp, "tartalom": uj, "alap": "0" * 40 if rossz else d["hash"],
                                                                    "elso": elso, "pillanat": pill})[0])

    def gepi(self) -> None:
        self.n["gepi"] += 1
        n = self.n["gepi"]
        rp = f"Gep/g{n % 5:02d}.md"
        k, d, _ = self.req("GET", "/api/vault/fajl?ut=" + q(rp))
        if k != 200:
            return
        kor = frame.new_id("SOAK")
        muvelet = ([{"tipus": "csere", "ut": rp, "alap": d["hash"], "tartalom": d["tartalom"] + f"gépi {n}\n"}] if n % 2 else
                   [{"tipus": "beszuras", "ut": rp, "szakasz": "Gyakorlás", "szoveg": f"beszúrt {n}"}])
        box = {}

        def f():
            kk, r, _ = self.req("POST", "/api/gepi-iras", {"kor": kor, "tetel": f"t{n}", "forras": "mos-soak", "modell": None,
                                                            "muveletek": muvelet})
            box["r"] = r
            return kk
        if self.meres("gepi", f) == 200 and box["r"].get("sha"):
            self.gepi_shak.append((box["r"]["sha"], kor))
            if n % 3 == 0:
                sha, kk = self.gepi_shak.pop()
                if n % 6 == 0:
                    self.meres("visszavonas-kor", lambda: self.req("POST", "/api/pillanat/vault/visszavonas", {"kor": kk})[0])
                else:
                    self.meres("visszavonas-sha", lambda: self.req("POST", "/api/pillanat/vault/visszavonas", {"sha": sha})[0])

    def atnev(self) -> None:
        self.n["atnev"] += 1
        regi, uj = ("Atnev/R.md", "Atnev/R2.md") if (self.vault / "Atnev/R.md").exists() else ("Atnev/R2.md", "Atnev/R.md")
        k, t, _ = self.req("POST", "/api/vault/atnevezes/terv", {"ut": regi, "uj": uj})
        if k != 200 or not t.get("ok"):
            self.meres("atnev-terv", lambda: k)
            return
        box = {}

        def f():
            kk, r, _ = self.req("POST", "/api/vault/atnevezes", {"ut": regi, "uj": uj, "terv_hash": t["terv_hash"]})
            box["r"] = r
            return kk
        if self.meres("atnevezes", f) == 200 and self.n["atnev"] % 3 == 0 and box["r"].get("pillanat"):
            self.meres("atnev-visszavonas",
                       lambda: self.req("POST", "/api/pillanat/vault/visszavonas", {"sha": box["r"]["pillanat"]})[0])

    def kulso(self) -> None:
        self.n["kulso"] += 1
        n = self.n["kulso"]
        t0 = time.perf_counter()
        try:
            with open(self.vault / f"Kulso/k{n % 10:02d}.md", "a", encoding="utf-8") as fh:
                fh.write(f"külső sor {n}\n")
            if n % 5 == 0:
                # (a link nem az átnevezett R-re mutat: a terv fájljait a külső író nem törli az átnevezés ablakában —
                # az az ütközés a T106 köre, a 409/visszaállítás útja a tesztkészletben)
                (self.vault / f"Kulso/tmp{n % 50}.md").write_text(f"# tmp {n}\n[[A{n % 30:02d}]]\n", encoding="utf-8")
            if n % 7 == 0:
                for x in (self.vault / "Kulso").glob("tmp*.md"):
                    if random.random() < 0.3:
                        x.unlink()
            if n % 11 == 0:                     # T173: üres mappa kívülről
                m = self.vault / f"Ures{n % 3}"
                m.rmdir() if m.exists() else m.mkdir()
            if n % 25 == 0:                     # a kép mtime-váltása → új gyorsítótár-kulcs, a régi árva (T177)
                try:
                    from PIL import Image
                    Image.new("RGB", (2400, 1800), (n % 255, 100, 150)).save(self.vault / f"Kep/p{n % 4}.jpg", quality=80)
                except ImportError:
                    pass
            kod = 200
        except OSError as e:
            kod = "EXC:" + type(e).__name__
        with self.zar:
            self.stat["kulso-iras"].append((time.time(), (time.perf_counter() - t0) * 1000, kod))

    def etagos(self, nev: str, ut: str):
        def f():
            k, _, h = self.req("GET", ut, fejlec={"If-None-Match": self.etag[ut]} if ut in self.etag else None)
            if k == 200 and h.get("ETag"):
                self.etag[ut] = h["ETag"]
            return k
        self.meres(nev, f)

    def olvaso(self) -> None:
        r = random.random()
        if r < 0.15:
            szo = random.choice(["integral", "matrix", "sor", "gépi", "derivalt hatarertek"])
            self.meres("kereses", lambda: self.req("GET", "/api/vault/kereses?q=" + q(szo) + "&limit=50")[0])
        elif r < 0.25:
            self.etagos("graf", "/api/vault/graf")
        elif r < 0.32:
            self.etagos("graf-meta", "/api/vault/graf-meta")
        elif r < 0.42:
            szoveg = (self.vault / "Nezet.base").read_text(encoding="utf-8")
            self.meres("bazis", lambda: self.req("POST", "/api/vault/bazis/lekerdez", {"szoveg": szoveg, "ez": "Nezet.base"})[0])
        elif r < 0.50:
            self.meres("fa", lambda: self.req("GET", "/api/vault/fa")[0])
        elif r < 0.56:
            cel = "Atnev/R.md" if (self.vault / "Atnev/R.md").exists() else "Atnev/R2.md"
            self.meres("visszahiv", lambda: self.req("GET", "/api/vault/visszahivatkozasok?ut=" + q(cel))[0])
        elif r < 0.64:
            a = random.randrange(6 * 1024 * 1024 - 1)
            self.meres("media-range", lambda: self.raw_get(f"/media/{self.token}/Kep/vid.mp4", {"Range": f"bytes={a}-{a + 262143}"}))
        elif r < 0.72:
            w = random.choice([300, 400, 700, 800, 1500])
            self.meres("media-w", lambda: self.raw_get(f"/media/{self.token}/Kep/p{random.randrange(4)}.jpg?w={w}"))
        elif r < 0.78:
            ut = q(f"Gep/g{random.randrange(5):02d}.md")
            self.meres("elozmeny", lambda: self.req("GET", f"/api/vault/elozmeny?ut={ut}&n=50")[0])
        elif r < 0.83:
            self.meres("pillanat-naplo", lambda: self.req("GET", "/api/pillanat/vault/naplo?n=20")[0])
        elif r < 0.88:
            self.meres("ma", lambda: self.req("GET", "/api/ma")[0])
        elif r < 0.92:
            self.meres("allapot", lambda: self.req("GET", "/api/allapot")[0])
        else:
            ut = q(f"A/A{random.randrange(30):02d}.md")
            self.meres("jegyzet", lambda: self.req("GET", "/api/vault/jegyzet?ut=" + ut)[0])

    def tracker(self) -> None:
        nap = time.strftime("%Y-%m-%d")
        body = {"aktiv": [{"nap": nap, "ut": f"Szerk/s{random.randrange(20):02d}.md", "mp": 30}],
                "karakter": [{"nap": nap, "ut": "Szerk/s01.md", "beszurt": 40, "torolt": 3}],
                "parancsok": [{"id": "szerkeszto.mentes", "forras": "billentyu", "db": 2}],
                "kesleltetes": {"gepeles": {"3": [10, 7.5]}, "mentes": {"5": [2, 30.0]}}}
        self.meres("tracker", lambda: self.req("POST", "/api/tracker/esemenyek", body)[0])

    def ws_churn(self) -> None:
        self.n["ws"] += 1
        rst = self.n["ws"] % 4 == 0

        def f():
            w = self.ws()
            time.sleep(0.15)
            w.zar(rst=rst)
            return 200
        self.meres("ws-churn", f)

    # ------------------------------------------------------------------ minták
    def _ps(self, *a) -> str:
        return subprocess.run(["ps", *a, "-p", str(self.pid)], capture_output=True, text=True).stdout

    def minta(self, cimke: str = "") -> dict:
        lsof = subprocess.run(["lsof", "-n", "-P", "-p", str(self.pid)], capture_output=True, text=True).stdout.splitlines()[1:]
        tip: dict[str, int] = defaultdict(int)
        for s in lsof:
            m = s.split()
            if len(m) > 4:
                tip[m[4]] += 1
        try:
            rss = int(self._ps("-o", "rss=").strip()) / 1024
        except ValueError:
            rss = None
        szal = len(self._ps("-M").splitlines()) - 1
        gyerek = len(subprocess.run(["pgrep", "-P", str(self.pid)], capture_output=True, text=True).stdout.split())

        def meret(p: Path):
            try:
                return p.stat().st_size
            except OSError:
                return None

        def mappa(p: Path):
            n = b = 0
            if p.exists():
                for x in p.rglob("*"):
                    if x.is_file():
                        n += 1
                        b += x.stat().st_size
            return [n, b]
        idx = self.pcfg.path("index")
        with self.zar:
            muv = sum(len(v) for v in self.stat.values())
        m = {"t": round(time.time() - self.t0), "cimke": cimke, "rss_mb": rss, "fd": len(lsof), "fd_tipus": dict(tip),
             "szal": szal, "gyerek": gyerek, "muveletek": muv,
             "wal": {"index": meret(idx / "vault.sqlite-wal"), "pos": meret(self.pcfg.path("szemelyes") / "pos.sqlite-wal")},
             "kepcache": mappa(self.pcfg.path("vault_kepek")), "tmp_vaultban": len(list(self.vault.rglob("*.manifold-tmp"))),
             "commitok": int(subprocess.run(["git", "--git-dir", str(self.git), "rev-list", "--count", "HEAD"], capture_output=True,
                                            text=True, env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"}).stdout.strip() or 0)}
        self.mintak.append(m)
        self.mintak_f.write(json.dumps(m, ensure_ascii=False) + "\n")
        self.kiir(f"[minta {m['t']}s {cimke}] rss={rss:.0f} MB fd={m['fd']} szál={szal} gyerek={gyerek} műv={muv} "
                  f"commit={m['commitok']} kepcache={m['kepcache']} wal={m['wal']}")
        return m

    def mintavevo(self) -> None:
        while not self.stop.wait(self.a.minta_mp):
            try:
                self.minta("terheles")
            except Exception as e:  # noqa: BLE001
                self.kiir("minta hiba:", repr(e))

    # ------------------------------------------------------------------ összegzés
    def osszegzes(self) -> dict:
        ki: dict = {"perc": self.a.perc, "mintak": len(self.mintak), "muveletek": {}, "ellenorzesek": [], "hibak": dict(self.hibak)}

        def ell(nev, ok, reszlet):
            ki["ellenorzesek"].append({"nev": nev, "ok": bool(ok), "reszlet": reszlet})
        bem = [m for m in self.mintak if m["cimke"] == "terheles"]
        if len(bem) >= 2:
            alap, veg = bem[0], bem[-1]
            for k, raha in (("fd", 8), ("szal", 4)):
                hatar = alap[k] * 1.2 + raha
                ell(f"{k} ±20%", veg[k] <= hatar and veg[k] >= alap[k] * 0.8 - raha, f"első {alap[k]}, utolsó {veg[k]}, határ {hatar:.0f}")
            fel = bem[len(bem) // 2:]
            if len(fel) >= 2 and (fel[-1]["t"] - fel[0]["t"]) < RSS_MIN_PERC * 60:
                ki["rss_trend"] = "nem értékelhető (a második fél rövidebb, mint {} perc)".format(RSS_MIN_PERC)
            elif len(fel) >= 2:
                xs = [m["t"] / 3600 for m in fel]
                ys = [m["rss_mb"] for m in fel]
                mx = statistics.fmean(xs)
                my = statistics.fmean(ys)
                nev = sum((x - mx) ** 2 for x in xs) or 1e-9
                meredek = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / nev
                ell("RSS-trend (2. fél)", meredek <= self.a.rss_meredekseg, f"{meredek:+.1f} MB/óra (határ {self.a.rss_meredekseg})")
            csucs = max(m["rss_mb"] for m in self.mintak)
            ell("RSS-csúcs", csucs <= 600, f"{csucs:.0f} MB (határ 600)")
            ell("nincs .manifold-tmp a vaultban", veg["tmp_vaultban"] == 0, f"{veg['tmp_vaultban']}")
        with self.zar:
            stat = {k: list(v) for k, v in self.stat.items()}
        varatlan_5xx = 0
        for muv, v in sorted(stat.items()):
            ms = [x[1] for x in v]
            kodok: dict[str, int] = defaultdict(int)
            for x in v:
                kodok[str(x[2])] += 1
                if isinstance(x[2], int) and x[2] >= 500:
                    varatlan_5xx += 1
            h = max(1, len(ms) // 5)
            # a második ötöd a viszonyítás (az első a bemelegedés: hideg gyorsítótárak, az index első olvasásai)
            masodik, utolso = statistics.median(ms[h:2 * h] or ms[:h]), statistics.median(ms[-h:])
            ki["muveletek"][muv] = {"n": len(v), "p50": round(statistics.median(ms), 1),
                                    "p95": round(sorted(ms)[max(0, int(len(ms) * 0.95) - 1)], 1), "max": round(max(ms), 1),
                                    "elso5": round(statistics.median(ms[:h]), 1), "masodik5": round(masodik, 1),
                                    "utolso5": round(utolso, 1), "kodok": dict(kodok)}
            if len(v) >= 50 and muv not in NEM_KAPU:
                hatar = max(2.5 * masodik, masodik + 25)
                ell(f"késleltetés stabil: {muv}", utolso <= hatar,
                    f"2. ötöd {masodik:.1f} ms, utolsó ötöd {utolso:.1f} ms (határ {hatar:.0f})")
        ell("nincs váratlan 5xx", varatlan_5xx == 0, f"{varatlan_5xx} db")
        ki["hiba_mintak"] = dict(self.hiba_mintak)
        ki["pass"] = all(e["ok"] for e in ki["ellenorzesek"])
        return ki

    # ------------------------------------------------------------------ leállás-próbák
    def _var_kilepes(self, mp: float) -> float | None:
        t0 = time.time()
        try:
            self.proc.wait(mp)
            return round(time.time() - t0, 2)
        except subprocess.TimeoutExpired:
            return None

    def _beragadt(self) -> list:
        r = []
        s = socket.create_connection(("127.0.0.1", self.port))
        s.sendall(f"POST /api/tracker/esemenyek HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\nX-Manifold: {TITOK}\r\n"
                  f"Content-Type: application/json\r\nContent-Length: 100\r\n\r\n{{\"aktiv\"".encode())
        r.append(s)
        s = socket.create_connection(("127.0.0.1", self.port))
        s.sendall(f"GET /api/allapot HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\nX-Manif".encode())
        r.append(s)
        return r

    def _leall_kenyszer(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.kiir(f"a saját core (pid {self.pid}) leállítása SIGKILL-lel")
            os.kill(self.pid, signal.SIGKILL)
            self.proc.wait()

    def leallas_probak(self) -> list[dict]:
        ki = []
        # (a) stdin-zárás beragadt kliensekkel
        self.core_indit("leallas-a")
        ragadt = self._beragadt() + self._beragadt()
        lassu = [self.ws(olvas=False, rcvbuf=1024) for _ in range(3)]
        for i in range(30):                                  # eseményáradat a nem olvasó WS-ek felé
            self.req("PUT", "/api/vault/fajl", {"ut": "Kulso/esemeny.md", "tartalom": f"x{i}\n" * 2000})
        self.proc.stdin.close()
        # a rendezett leállás legfeljebb `KEREL_VARAKOZAS_MP` (35 s) várja a folyamatban lévő kéréseket (T003): a határ ennél 5 s-mal több
        ido = self._var_kilepes(40)
        ki.append({"nev": "stdin-zárás beragadt kliensekkel", "ok": ido is not None, "ido_mp": ido})
        self._leall_kenyszer()
        for s in ragadt:
            s.close()
        for w in lassu:
            w.zar(rst=True)
        # (b) csak SIGTERM egy félbehagyott törzzsel
        self.core_indit("leallas-b")
        ragadt = self._beragadt()
        os.kill(self.pid, signal.SIGTERM)
        ido = self._var_kilepes(15)
        ki.append({"nev": "SIGTERM félbehagyott törzzsel", "ok": ido is not None, "ido_mp": ido})
        self._leall_kenyszer()
        for s in ragadt:
            s.close()
        # (c) H6: stdin-zárás egy futó, hosszú lépés közben, majd SIGTERM
        self.core_indit("leallas-c")
        k, f, _ = self.req("POST", "/api/feladatok", {"tipus": "proba", "parameterek": {"darab": 1, "mp": 60}})
        lepes_pid = None
        for _ in range(200):
            gy = subprocess.run(["pgrep", "-P", str(self.pid)], capture_output=True, text=True).stdout.split()
            jelolt = [p for p in gy if "probafeladat" in subprocess.run(["ps", "-o", "command=", "-p", p], capture_output=True,
                                                                           text=True).stdout]
            if jelolt:
                lepes_pid = int(jelolt[0])
                break
            time.sleep(0.1)
        self.proc.stdin.close()
        time.sleep(1.0)
        os.kill(self.pid, signal.SIGTERM)
        ido = self._var_kilepes(15)
        el = False
        if lepes_pid:
            try:
                os.kill(lepes_pid, 0)
                el = True
            except OSError:
                el = False
        ki.append({"nev": "H6: stdin-zárás futó lépés közben, majd SIGTERM", "ok": ido is not None and not el and lepes_pid is not None,
                   "ido_mp": ido, "lepes_pid": lepes_pid, "lepes_el": el, "feladat": k})
        self._leall_kenyszer()
        if el and lepes_pid:
            os.kill(lepes_pid, signal.SIGKILL)
        return ki

    # ------------------------------------------------------------------ fő
    def fut(self) -> int:
        self.alvault()
        self.core_indit("terheles")
        figyelo = self.ws()
        self.minta("start")
        threading.Thread(target=self.mintavevo, daemon=True).start()
        szalak = [self.hurok(self.szerkeszto, 0.15), self.hurok(self.szerkeszto, 0.3), self.hurok(self.gepi, 0.4),
                  self.hurok(self.atnev, 2.0), self.hurok(self.kulso, 0.3), self.hurok(self.olvaso, 0.05),
                  self.hurok(self.olvaso, 0.1), self.hurok(self.tracker, 2.0), self.hurok(self.ws_churn, 0.5)]
        try:
            vege = time.time() + self.a.perc * 60
            while time.time() < vege and self.proc.poll() is None:
                time.sleep(1)
            if self.proc.poll() is not None:
                self.kiir(f"A CORE MEGHALT a terhelés alatt (kód {self.proc.returncode})")
            self.stop.set()
            for t in szalak:
                t.join(30)
            self.minta("vege")
            figyelo.zar()
            ossz = self.osszegzes()
            ossz["ws_uzenetek"] = figyelo.db
            ossz["core_el"] = self.proc.poll() is None
            if not ossz["core_el"]:
                ossz["pass"] = False
            self.proc.stdin.close()
            ossz["leallas_terheles_utan_mp"] = self._var_kilepes(45)
            self._leall_kenyszer()
            g = subprocess.run(["git", "--git-dir", str(self.git), "fsck", "--strict"], capture_output=True, text=True,
                               env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})
            ossz["ellenorzesek"].append({"nev": "git fsck", "ok": g.returncode == 0, "reszlet": (g.stdout + g.stderr)[-300:]})
            if self.a.leallas:
                ossz["leallas"] = self.leallas_probak()
                ossz["ellenorzesek"] += [{"nev": "leállás: " + x["nev"], "ok": x["ok"], "reszlet": f"{x.get('ido_mp')} s"}
                                         for x in ossz["leallas"]]
            ossz["pass"] = all(e["ok"] for e in ossz["ellenorzesek"]) and ossz.get("core_el", True)
        finally:
            self.stop.set()
            self._leall_kenyszer()
        (self.ki / "osszegzes.json").write_text(json.dumps(ossz, ensure_ascii=False, indent=2), encoding="utf-8")
        for e in ossz["ellenorzesek"]:
            self.kiir(f"{'PASS' if e['ok'] else 'FAIL'}  {e['nev']}: {e['reszlet']}")
        for muv, s in ossz["muveletek"].items():
            self.kiir(f"  {muv:18s} n={s['n']:6d} p50={s['p50']:7.1f} p95={s['p95']:7.1f} max={s['max']:8.1f} "
                      f"első5={s['elso5']:6.1f} 2.ötöd={s['masodik5']:6.1f} utolsó5={s['utolso5']:6.1f} kódok={s['kodok']}")
        for k, v in ossz.get("hiba_mintak", {}).items():
            self.kiir(f"  5xx-minta {k}: {v}")
        if "rss_trend" in ossz:
            self.kiir(f"  RSS-trend: {ossz['rss_trend']}")
        self.kiir(("SOAK PASS" if ossz["pass"] else "SOAK FAIL") + f" — {self.ki}")
        if not self.a.megtart:
            subprocess.run(["chmod", "-R", "u+w", str(self.d)])
            subprocess.run(["rm", "-rf", str(self.d)])          # a saját var/tmp próbamappája
        return 0 if ossz["pass"] else 1


class WS:
    """Minimális WS-kliens a core-hoz (az alprotokollban a titok: `mos.<titok>`)."""

    def __init__(self, port: int, olvas: bool = True, rcvbuf: int | None = None):
        self.s = socket.socket()
        if rcvbuf:
            self.s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, rcvbuf)
        self.s.connect(("127.0.0.1", port))
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall((f"GET /ws HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                        f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Protocol: mos.{TITOK}\r\n\r\n").encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            x = self.s.recv(1)
            if not x:
                raise ConnectionError("WS kézfogás: bontva")
            buf += x
        if b" 101 " not in buf.split(b"\r\n")[0]:
            raise ConnectionError(buf[:80])
        self.db = 0
        self.zart = False
        if olvas:
            threading.Thread(target=self._olvas, daemon=True).start()

    def _pont(self, n: int) -> bytes:
        b = b""
        while len(b) < n:
            x = self.s.recv(n - len(b))
            if not x:
                raise ConnectionError
            b += x
        return b

    def _olvas(self) -> None:
        try:
            while not self.zart:
                h = self._pont(2)
                n = h[1] & 0x7F
                if n == 126:
                    n = struct.unpack(">H", self._pont(2))[0]
                elif n == 127:
                    n = struct.unpack(">Q", self._pont(8))[0]
                self._pont(n)
                self.db += 1
                if h[0] & 0x0F == 8:
                    break
        except (OSError, ConnectionError):
            pass

    def zar(self, rst: bool = False) -> None:
        self.zart = True
        try:
            if rst:
                self.s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
            else:
                mask = os.urandom(4)
                p = struct.pack(">H", 1000)
                self.s.sendall(bytes([0x88, 0x80 | len(p)]) + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(p)))
            self.s.close()
        except OSError:
            pass


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="soak.py", description="Ismételhető soak-készlet (C33, T206).")
    ap.add_argument("--perc", type=float, default=30, help="a terhelés hossza percben (alap 30; a 8 órás cél: 480)")
    ap.add_argument("--minta-mp", type=float, default=30, help="mintavétel másodpercenként (alap 30)")
    ap.add_argument("--rss-meredekseg", type=float, default=30.0, help="az RSS második felének megengedett trendje MB/óra")
    ap.add_argument("--leallas", dest="leallas", action="store_true", default=True)
    ap.add_argument("--nincs-leallas", dest="leallas", action="store_false", help="a három leállás-próba kimarad")
    ap.add_argument("--kimenet", help="a kimeneti mappa (alap: {runs}/soak-<idő>/)")
    ap.add_argument("--megtart", action="store_true", help="a próbamappa (álvault, core-állapot) megmarad")
    a = ap.parse_args(argv)
    if a.perc <= 0 or a.minta_mp <= 0:
        print("a --perc és a --minta-mp pozitív", file=sys.stderr)
        return 2
    return Soak(a).fut()


if __name__ == "__main__":
    sys.exit(main())
