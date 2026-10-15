"""A core HTTP- és WS-felülete folyamaton belül (a szerver szálon, a stdin egy cső) — álgyökéren.

Amit őriz: az API-hitelesítés (Host, X-Manifold), a feladat-végpontok, a WS-kézfogás és -események a
független `websockets` klienssel, az idegen Origin elutasítása, és hogy a stdin lezárása a futó
feladat tételének végét megvárja, a sorban állót pedig tartósan megtartja.
"""
import http.client
import json
import os
import socket
import sys
import threading
import time
import unittest
from unittest import mock

from core import server, tasks
from tests.helpers import API_TITOK, alg_core, tmpdir

try:
    from websockets.sync.client import connect as ws_connect
    from websockets.exceptions import InvalidStatus
except ImportError:  # a venv nélkül (rendszer-Python) a WS-kliens tesztjei kimaradnak
    ws_connect = None


def ws_csatlakozik(port: int, titok: str | None = API_TITOK, **kw):
    """WS-kapcsolat a core-hoz: a böngésző nem tud fejlécet küldeni, ezért a titok az alprotokollban megy (`mos.<titok>`)."""
    return ws_connect(f"ws://127.0.0.1:{port}/ws", subprotocols=[f"mos.{titok}"] if titok is not None else None, **kw)


class _Kimenet:
    def __init__(self):
        self.sorok, self.jel = [], threading.Event()

    def write(self, s):
        self.sorok.append(s)
        self.jel.set()

    def flush(self):
        pass


class _Szerver(unittest.TestCase):
    """A core a szálon, álgyökéren; az `elokeszit` az indulás előtt fut (az indulási helyreállítás tesztjeinek)."""

    def elokeszit(self):
        pass

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        self.elokeszit()
        self.addCleanup(lambda: [tasks.REGISTRY.pop(k) for k in list(tasks.REGISTRY) if k.startswith("t_")])
        r, w = os.pipe()
        self.stdin_w, self.stdin_r = os.fdopen(w, "wb"), os.fdopen(r, "rb")
        ki = _Kimenet()
        self.szal = threading.Thread(target=server.start, args=(self.cfg,),
                                     kwargs={"stdin": self.stdin_r, "out": ki, "start_delay": 0}, daemon=True)
        self.szal.start()
        self.assertTrue(ki.jel.wait(5))
        self.kezfogas = json.loads(ki.sorok[0])
        self.port = self.kezfogas["port"]
        self.addCleanup(self._leall)

    def _leall(self):
        if not self.stdin_w.closed:
            self.stdin_w.close()
        self.szal.join(20)
        self.stdin_r.close()

    def k(self, method, path, body=None, fejlec=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = {"Host": f"127.0.0.1:{self.port}", "X-Manifold": API_TITOK, "Content-Type": "application/json", **(fejlec or {})}
        c.request(method, path, body=json.dumps(body) if body is not None else None, headers=h)
        r = c.getresponse()
        t = r.read()
        return r.status, (json.loads(t) if t and r.getheader("Content-Type", "").startswith("application/json") else t)

    def var(self, fid, allapotok=("kesz", "hiba", "megallitva"), mp=15):
        t0 = time.time()
        while time.time() - t0 < mp:
            d = self.k("GET", f"/api/feladatok/{fid}")[1]
            if d["allapot"] in allapotok:
                return d
            time.sleep(0.05)
        return d



class CoreApiTest(_Szerver):
    def test_hitelesites(self):
        self.assertEqual(self.k("GET", "/api/allapot", fejlec={"X-Manifold": "0"})[0], 403)
        self.assertEqual(self.k("GET", "/api/allapot", fejlec={"Host": "evil.hu"})[0], 403)
        kod, d = self.k("GET", "/api/allapot")
        self.assertEqual(kod, 200)
        self.assertEqual(d["pid"], os.getpid())
        self.assertEqual(d["tarolok"], [])                                   # az álvaultnak még nincs tárolója
        self.assertEqual(self.k("GET", "/api/nincs")[0], 404)
        self.assertEqual(self.k("POST", "/api/feladatok", {"tipus": "nincs"})[0], 400)
        self.assertEqual(self.k("POST", "/api/feladatok", {"tipus": "mentes", "prioritas": "x"})[0], 400)

    def test_api_titok_hitelesites(self):
        """35. döntés (T071): a statikus `X-Manifold: 1` helyett a core induláskor sorsolt titka kell; minden más fejléc 403."""
        for rossz in ("1", "", API_TITOK[:-1], API_TITOK + "x", API_TITOK.upper(), "0"):
            for ut in ("/api/allapot", "/health", "/api/vault/fa"):
                self.assertEqual(self.k("GET", ut, fejlec={"X-Manifold": rossz})[0], 403, (rossz, ut))
        self.assertEqual(self.k("POST", "/api/aktivitas", {"forras": "x"}, {"X-Manifold": "1"})[0], 403)
        self.assertEqual(self.k("GET", "/api/allapot")[0], 200)
        self.assertEqual(self.k("GET", "/health")[0], 200)

    def test_kezfogas_titokkal(self):
        """A kézfogás-sor a titkot is hordozza: a héj ebből injektálja a felületbe (a `/` lap titok nélkül is elérhető)."""
        self.assertEqual(self.kezfogas["titok"], API_TITOK)
        self.assertEqual(set(self.kezfogas), {"port", "pid", "titok"})

    @unittest.skipIf(ws_connect is None, "nincs websockets (a venvben van)")
    def test_ws_titok(self):
        """A böngésző WS-e nem küldhet fejlécet: a titok az alprotokollban megy (`mos.<titok>`), a válasz visszaküldi."""
        for titok in (None, "1", "rossz-titok", API_TITOK + "x", API_TITOK[:-1]):
            with self.assertRaises(InvalidStatus, msg=str(titok)) as cm:
                ws_csatlakozik(self.port, titok)
            self.assertEqual(cm.exception.response.status_code, 403, titok)
        with ws_csatlakozik(self.port) as ws:
            self.assertEqual(ws.subprotocol, f"mos.{API_TITOK}")
            self.assertEqual(json.loads(ws.recv(timeout=5))["tipus"], "hello")

    def test_hibas_szamparameterek_400(self):
        """L2 (audit): a hibás `n`, `tol`, `limit` 400, nem 500."""
        from core import snapshot
        (self.v / "A.md").write_text("# A\n", encoding="utf-8")
        repo = snapshot.repos(self.cfg)["vault"]
        repo.init()
        repo.commit("alap", {"Mos-Forras": "kezi"})
        tasks.register(tasks.TaskType("t_ok", "próba", lambda c, p, s: (
            [tasks.Step("egy", [sys.executable, "-c", "print('ok')"], "/")], "", [])))
        fid = self.k("POST", "/api/feladatok", {"tipus": "t_ok"})[1]["id"]
        for ut in ("/api/pillanat/vault/naplo?n=abc", "/api/pillanat/vault/naplo?n=-5", f"/api/feladatok/{fid}?tol=x",
                   f"/api/feladatok/{fid}?tol=-1", "/api/vault/kereses?q=a&limit=x", "/api/vault/kereses?q=a&limit=0"):
            kod, d = self.k("GET", ut)
            self.assertEqual(kod, 400, (ut, d))
        self.assertEqual(self.k("GET", "/api/pillanat/vault/naplo?n=3")[0], 200)

    def test_negativ_content_length_400(self):
        """L2 (audit): negatív `Content-Length` → 400 azonnal (eddig a szál a kapcsolat végéig olvasott)."""
        s = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        s.sendall((f"POST /api/aktivitas HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\nX-Manifold: {API_TITOK}\r\n"
                   "Content-Length: -1\r\n\r\n{}").encode())
        valasz = s.recv(4096)
        s.close()
        self.assertIn(b" 400 ", valasz.split(b"\r\n", 1)[0])

    def test_atnev_kor_visszavonhato(self):
        """L1 (audit): az átnevezés `ATNEV-…` köre `kor`-ral is visszavonható (a `KOR_ID` ismeri az előtagot)."""
        from core import snapshot
        (self.v / "A.md").write_text("# A\n", encoding="utf-8")
        repo = snapshot.repos(self.cfg)["vault"]
        repo.init()
        repo.commit("alap", {"Mos-Forras": "kezi"})
        (self.v / "A.md").write_text("# A\nátírva\n", encoding="utf-8")
        repo.commit("átnevezés", {snapshot.TRAILER_RUN: "ATNEV-20261001-120000"}, ["A.md"])
        kod, d = self.k("POST", "/api/pillanat/vault/visszavonas", {"kor": "ATNEV-20261001-120000"})
        self.assertEqual(kod, 200, d)
        self.assertEqual((self.v / "A.md").read_text(encoding="utf-8"), "# A\n")

    def test_visszaallitas_kor_visszavonhato(self):
        """C11b: a `VISSZA-…` kör (fájl-visszaállítás egy verzióra) `kor`-ral is visszavonható."""
        from core import snapshot
        (self.v / "A.md").write_text("# A\n", encoding="utf-8")
        repo = snapshot.repos(self.cfg)["vault"]
        repo.init()
        repo.commit("alap", {"Mos-Forras": "kezi"})
        (self.v / "A.md").write_text("# A\nvisszaállítva\n", encoding="utf-8")
        repo.commit("visszaállítás", {snapshot.TRAILER_RUN: "VISSZA-20261002-120000"}, ["A.md"])
        kod, d = self.k("POST", "/api/pillanat/vault/visszavonas", {"kor": "VISSZA-20261002-120000"})
        self.assertEqual(kod, 200, d)
        self.assertEqual((self.v / "A.md").read_text(encoding="utf-8"), "# A\n")

    def test_feladat_vegpontok(self):
        tasks.register(tasks.TaskType("t_ok", "próba", lambda c, p, s: (
            [tasks.Step("egy", [sys.executable, "-c", "print('[manifold-progress] 50%'); print('szia')"], "/")], "", [])))
        kod, f = self.k("POST", "/api/feladatok", {"tipus": "t_ok", "prioritas": 3})
        self.assertEqual(kod, 201)
        self.assertEqual(f["prioritas"], 3)
        d = self.var(f["id"])
        self.assertEqual(d["allapot"], "kesz")
        self.assertIn("szia", d["sorok"])
        self.assertEqual(self.k("GET", "/api/feladatok")[1]["feladatok"][0]["id"], f["id"])
        self.assertEqual(self.k("POST", f"/api/feladatok/{f['id']}/leallitas", {})[0], 400)   # már nem fut

    @unittest.skipIf(ws_connect is None, "nincs websockets (a venvben van)")
    def test_ws_esemenyek(self):
        tasks.register(tasks.TaskType("t_ok", "próba", lambda c, p, s: (
            [tasks.Step("egy", [sys.executable, "-c", "print('ok')"], "/")], "", [])))
        with ws_csatlakozik(self.port) as ws:
            self.assertEqual(json.loads(ws.recv(timeout=5))["tipus"], "hello")
            ws.ping().wait(5)                                                  # ping → pong
            fid = self.k("POST", "/api/feladatok", {"tipus": "t_ok"})[1]["id"]
            allapotok = []
            while "kesz" not in allapotok:
                e = json.loads(ws.recv(timeout=10))
                if e["tipus"] == "feladat" and e["feladat"]["id"] == fid:
                    allapotok.append(e["feladat"]["allapot"])
            self.assertEqual(allapotok[0], "sorban")
            self.assertIn("fut", allapotok)

    @unittest.skipIf(ws_connect is None, "nincs websockets (a venvben van)")
    def test_ws_idegen_origin(self):
        with self.assertRaises(InvalidStatus) as cm:
            ws_csatlakozik(self.port, origin="http://evil.hu")
        self.assertEqual(cm.exception.response.status_code, 403)
        with ws_csatlakozik(self.port, origin=f"http://127.0.0.1:{self.port}") as ws:
            self.assertEqual(json.loads(ws.recv(timeout=5))["tipus"], "hello")

    def test_ws_nyers_keret(self):
        """Független ellenőrzés a könyvtár nélkül: kézfogás-kulcs (RFC 6455 példája) és maszkolt close."""
        s = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        s.sendall((f"GET /ws HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                   f"Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Protocol: mos.{API_TITOK}\r\n\r\n").encode())
        valasz = b""
        while b"\r\n\r\n" not in valasz:
            valasz += s.recv(4096)
        self.assertIn(b"101 Switching Protocols", valasz)
        self.assertIn(b"Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=", valasz)
        self.assertIn(f"Sec-WebSocket-Protocol: mos.{API_TITOK}".encode(), valasz)      # a választott alprotokollt vissza kell küldeni
        s.sendall(bytes([0x88, 0x82, 1, 2, 3, 4, 0x03 ^ 1, 0xE8 ^ 2]))   # close 1000, maszkolva
        s.settimeout(5)
        adat = valasz.split(b"\r\n\r\n", 1)[1]
        while True:
            b = s.recv(4096)
            if not b:
                break
            adat += b
        self.assertIn(bytes([0x88, 0x02, 0x03, 0xE8]), adat)
        s.close()

    def test_stdin_zaras_a_tetel_vegen_all_meg_a_sor_megmarad(self):
        lanc = ("import os,time\nfor i in range(100):\n    if os.path.exists(os.environ['MANIFOLD_STOP_FAJL']):"
                " print('megállt', i); break\n    print('tétel', i, flush=True); time.sleep(0.1)\n")
        tasks.register(tasks.TaskType("t_lanc", "lánc", lambda c, p, s: (
            [tasks.Step("lánc", [sys.executable, "-c", lanc], "/")], "", []), frozenset(["modell"]), True))
        futo = self.k("POST", "/api/feladatok", {"tipus": "t_lanc"})[1]["id"]
        var = self.k("POST", "/api/feladatok", {"tipus": "t_lanc"})[1]["id"]
        self.var(futo, allapotok=("fut",))
        t0 = time.time()                                # T085: a lánc tényleg fut (az első tétel kinyomtatva), nem fix idő
        while time.time() - t0 < 15 and not any(
                s.startswith("tétel") for s in self.k("GET", f"/api/feladatok/{futo}")[1].get("sorok", [])):
            time.sleep(0.05)
        self.stdin_w.close()
        self.szal.join(20)
        self.assertFalse(self.szal.is_alive())
        q = tasks.Queue(self.cfg, start_delay=3600)
        self.addCleanup(q.close)
        self.assertEqual(q.get(futo)["allapot"], "megallitva")
        self.assertTrue(any(s.startswith("megállt") for s in q.detail(futo)["sorok"]))
        self.assertEqual(q.get(var)["allapot"], "sorban")                     # tartós: a következő indításkor fut


    def test_aktivitas_es_modellallapot(self):
        from core.modell.aktivitas import Aktivitas
        self.assertEqual(self.k("POST", "/api/aktivitas", {"forras": "billentyu"}), (200, {"ok": True}))
        a = Aktivitas(self.cfg.path("run") / "aktivitas", rendszer=False)
        self.assertEqual(a.allapot(), "aktiv")
        kod, d = self.k("GET", "/api/modell")
        self.assertEqual(kod, 200)
        self.assertEqual(d["router"], [])                                    # üresen indul (C19 tölti)
        self.assertIsNone(d["worker"])                                       # a megnyitás nem indít workert (D8)

    def test_modellfeladat_workert_indit_es_a_leallas_leallitja(self):
        # C33 (T182): a lépés a worker munkamenet-titkát az env-ben kapja; a régi `1` 403
        kod = ("import os, json, urllib.request as u, urllib.error as E; c = os.environ['MOS_WORKER_URL'] + '/health'; "
               "r = u.Request(c, headers={'X-Manifold': os.environ['MOS_WORKER_TITOK']}); "
               "print('worker', json.load(u.urlopen(r))['ok'], os.environ['MOS_MODELL_MOD'])\n"
               "try:\n u.urlopen(u.Request(c, headers={'X-Manifold': '1'})); print('regi titok elfogadva')\n"
               "except E.HTTPError as e:\n print('regi titok', e.code)")
        tasks.register(tasks.TaskType("t_modell", "modell", lambda c, p, s: (
            [tasks.Step("egy", [sys.executable, "-c", kod], "/")], "", []), frozenset({"modell"})))
        fid = self.k("POST", "/api/feladatok", {"tipus": "t_modell"})[1]["id"]
        d = self.var(fid)
        self.assertEqual(d["allapot"], "kesz", d["sorok"])
        self.assertIn("worker True interaktiv", d["sorok"])
        self.assertIn("regi titok 403", d["sorok"])
        pidf = self.cfg.path("run") / "worker.pid"
        self.assertTrue(pidf.exists())
        self.assertEqual(pidf.stat().st_mode & 0o777, 0o600)                 # T182: a titkot más fiók nem olvassa
        self.assertIsNotNone(self.k("GET", "/api/modell")[1]["worker"])
        self.stdin_w.close()
        self.szal.join(30)
        self.assertFalse(pidf.exists())                                       # a worker a core-ral leállt


class NincsModellTest(unittest.TestCase):
    def test_a_core_nem_tolt_be_ml_konyvtarat(self):
        import subprocess
        # a modellréteg core-oldali része és a worker indulása is ML nélkül (a háttér lustán tölt, L22)
        kod = ("import sys, core.server, core.tasks, core.vaultio, core.snapshot, core.frame, core.modell.kliens, "
               "core.modell.aktivitas, core.modell.kapu, core.modell.router, core.modell.worker, "
               "core.index.indexelo, core.index.kereses, core.index.figyelo, core.bazis.api; "
               "print(sorted(m for m in sys.modules if m.split('.')[0] in "
               "('mlx', 'mlx_lm', 'mlx_vlm', 'torch', 'transformers', 'huggingface_hub', 'numpy')))")
        p = subprocess.run([sys.executable, "-B", "-c", kod], capture_output=True, text=True,
                           cwd=str(tasks.Path(__file__).resolve().parent.parent))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout.strip(), "[]")


def megszakadt_allapot(teszt) -> None:
    """Az indulási helyreállítás tesztjeinek kiinduló állapota: elakadt `index.lock` és egy megszakadt átnevezés naplója
    (az A.md már az új tartalommal áll, a régi bájtok a naplóban)."""
    from core import snapshot
    (teszt.v / "A.md").write_text("# A\n", encoding="utf-8")
    teszt.repo = snapshot.repos(teszt.cfg)["vault"]
    teszt.repo.init()
    teszt.repo.commit("alap", {"Mos-Forras": "kezi"})
    (teszt.repo.git_dir / "index.lock").write_text("")
    # egy megszakadt átnevezés naplója: az A.md már az új tartalommal áll, a régi bájtok a naplóban
    import hashlib
    naplo = teszt.cfg.path("run") / "atnevezes"
    (naplo / "eredeti").mkdir(parents=True)
    (naplo / "eredeti" / "0.bin").write_bytes(b"# A\n")
    (teszt.v / "A.md").write_text("# A átírva\n", encoding="utf-8")
    (naplo / "terv.json").write_text(json.dumps({
        "verzio": 1, "kor": "ATNEV-20261001-120000", "regi": "B.md", "uj": "C.md", "regi_lemez": "B.md",
        "uj_lemez": "C.md", "fajlok": [{"ut": "A.md", "lemez": "A.md", "eredeti": "0.bin",
                                       "uj_sha1": hashlib.sha1(b"# A \xc3\xa1t\xc3\xadrva\n").hexdigest()}]}))


@unittest.skipIf(ws_connect is None, "nincs websockets (a venvben van)")
class IndulasTest(_Szerver):
    """K1: az elakadt index.lock induláskor a kör-zár alatt eltűnik, és az első WS-kapcsolat hírt kap róla."""

    def elokeszit(self):
        megszakadt_allapot(self)

    def test_index_lock_takaritas_es_hello(self):
        self.assertFalse((self.repo.git_dir / "index.lock").exists())
        with ws_csatlakozik(self.port) as ws:
            h = json.loads(ws.recv(timeout=5))
        self.assertEqual(h["tipus"], "hello")
        self.assertTrue(any("index.lock" in u for u in h["figyelmeztetesek"]))
        self.assertTrue(any("B.md → C.md" in u for u in h["figyelmeztetesek"]))      # H3
        self.assertEqual((self.v / "A.md").read_text(encoding="utf-8"), "# A\n")
        with ws_csatlakozik(self.port) as ws:          # egyszer kézbesítve
            self.assertEqual(json.loads(ws.recv(timeout=5))["figyelmeztetesek"], [])


@unittest.skipIf(ws_connect is None, "nincs websockets (a venvben van)")
class VaultNelkulIndulasTest(_Szerver):
    """T002 (2. audit): a symlinkelt `var/`-ú munkafa core-ja a valódi `{run}`-t kapja, a vault útja viszont nem vault
    (nincs `.obsidian`). Az indulási helyreállítás ilyenkor nem fut: se index.lock-takarítás, se átnevezés-visszaállítás,
    és a hello nem hordoz hamis „visszaállt” üzenetet; a napló érintetlen marad a valódi app indulásáig."""

    def elokeszit(self):
        megszakadt_allapot(self)
        (self.v / ".obsidian").rmdir()

    def test_nincs_indulasi_helyreallitas(self):
        with ws_csatlakozik(self.port) as ws:
            h = json.loads(ws.recv(timeout=5))
        self.assertEqual(h["tipus"], "hello")
        self.assertEqual(h["figyelmeztetesek"], [])
        self.assertEqual((self.v / "A.md").read_text(encoding="utf-8"), "# A átírva\n")
        self.assertTrue((self.cfg.path("run") / "atnevezes" / "terv.json").is_file())
        self.assertTrue((self.repo.git_dir / "index.lock").exists())


class ApiTitokSorsolasTest(unittest.TestCase):
    """35. döntés (T071): a titkot a core sorsolja (a `MOS_API_TITOK` rögzítheti: újraindításnál a héj, a tesztek)."""

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)

    def app(self, **env):
        with mock.patch.dict(os.environ, env, clear=False):
            if "MOS_API_TITOK" not in env:
                os.environ.pop("MOS_API_TITOK", None)
            a = server.App(self.cfg, start_delay=0)
        self.addCleanup(a.queue.close, 0)
        self.addCleanup(a.index.leallit)
        return a

    def test_veletlen_es_inditasonkent_mas(self):
        a, b = self.app(), self.app()
        for t in (a.api_titok, b.api_titok):
            self.assertGreaterEqual(len(t), 32)
            self.assertRegex(t, r"^[A-Za-z0-9_.-]+$")           # érvényes HTTP-token: alprotokoll-névnek is jó
        self.assertNotEqual(a.api_titok, b.api_titok)
        self.assertNotEqual(a.api_titok, API_TITOK)

    def test_kornyezeti_valtozo_rogzit_es_ervenytelen_nem_fogadhato_el(self):
        self.assertEqual(self.app(MOS_API_TITOK="rogzitett-titok-0123456789").api_titok, "rogzitett-titok-0123456789")
        for rossz in ("rovid", "szóköz van benne 0123456789", "pont,vessző;0123456789", "ékezetes-é-0123456789"):
            with self.assertRaises(ValueError, msg=rossz):
                self.app(MOS_API_TITOK=rossz)

    def test_a_lepesek_nem_kapjak_a_felulet_titkat(self):
        """T137 (C29.8): a lépés a core címét kapja, a felületi API-titkot NEM (a hitelesítője a lépés-token); az `MOS_API_TITOK`-kal
        indított core (a héj újraindítás után így indítja) sem adja tovább a saját környezetéből."""
        a = self.app(MOS_API_TITOK="rogzitett-titok-0123456789")
        t = tasks.TaskType("t_x", "próba", lambda c, p, s: ([], "", []), frozenset())
        env = a.feladat_env(t)
        self.assertIn("MOS_CORE_URL", env)
        self.assertNotIn("MOS_API_TITOK", env)
        with mock.patch.dict(os.environ, {"MOS_API_TITOK": a.api_titok}):
            lepes_env = a.queue._env("F-20261004-0001", self.cfg.path("run") / "stop", env, "lepes-token-0123456789")
        self.assertNotIn("MOS_API_TITOK", lepes_env)
        self.assertEqual(lepes_env["MOS_LEPES_TOKEN"], "lepes-token-0123456789")

    def test_m3_az_automatikus_feladatot_a_worker_is_megkapja(self):
        """M3 (C19): az automatikus feladat indulásakor a core a feladat azonosítóját a workernek is jelzi (az kéréseit `auto`
        módban futtatja); a kézi feladatét nem, és workert ehhez nem indít."""
        a = self.app()
        self.assertIs(a.queue.indulas_horog.__func__, type(a)._worker_automatikus)
        auto = tasks.TaskType("t_auto", "próba", lambda c, p, s: ([], "", []), frozenset(), automatikus=True)
        kezi = tasks.TaskType("t_kezi", "próba", lambda c, p, s: ([], "", []), frozenset({"modell"}))
        hivasok = []
        a.worker.url = "http://127.0.0.1:1"
        with mock.patch("core.server.kliens.automatikus", lambda u, fid: hivasok.append((u, fid))):
            a._worker_automatikus(kezi, "F-1")
            a._worker_automatikus(auto, "F-2")
        self.assertEqual(hivasok, [("http://127.0.0.1:1", "F-2")])


if __name__ == "__main__":
    unittest.main()
