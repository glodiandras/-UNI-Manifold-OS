"""A core indulásának és leállásának keményítése (A-javító, 2026-10-14; audit CONFIRMED leletek).

- D8: a kézfogás nem vár a forrásujjlenyomatra, az indulási helyreállításra és a kapu jeleire (háttérszál);
- CX-001: az ujjlenyomat a git által látott forrásfájlokból, darabolva (nem olvassa be a staging videóit);
- leállás: a komponensek hibája nem akasztja el a kilépést és a kilépési mentést; a stdin-zárás után a még futó feladat
  `leallas_fokozas_mp` múlva azonnal leáll; a folyó médiaküldés nem tartja vissza a kilépést;
- a feladatsor: legnagyobb futásidő, a DB-zárás a futó munkásszál alatt, az árva lépés rendezése háttérben, `LC_ALL=C`;
- az index: a halott író szálra nem vár a mentés; a köteg átmeneti hibája nem marad tartós;
- a git-hívások időkorlátja, a `chat` időkorlátja, a worker azonnali leállítása, a `backup` a kör-zár alatt, az API-titok
  nem marad a környezetben.
"""
import json
import os
import socket
import subprocess
import sys
import threading
import time
import types
import unittest
from pathlib import Path
from unittest import mock

from core import epites, frame, server, snapshot, tasks
from core.modell import kliens
from tests.helpers import alg_core, tmpdir


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, env=snapshot.hermetikus_env())


class _Kimenet:
    def __init__(self):
        self.sorok, self.jel = [], threading.Event()

    def write(self, s):
        self.sorok.append(s)
        self.jel.set()

    def flush(self):
        pass


# ------------------------------------------------------------------ CX-001: az ujjlenyomat forrása

class UjjlenyomatTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.root = Path(self._t.name) / "kodtar"
        for f in ("core/a.py", "modulok/m/b.py", "app/src/x.ts", "app/svelte.config.js", "app/tsconfig.json",
                  "shell/Sources/A.swift"):
            (self.root / f).parent.mkdir(parents=True, exist_ok=True)
            (self.root / f).write_text("eredeti", encoding="utf-8")

    def _git_tar(self):
        (self.root / ".gitignore").write_text("modulok/m/staging/\n.DS_Store\n__pycache__/\n", encoding="utf-8")
        _git(self.root, "init", "-q")
        _git(self.root, "add", "-A")

    def test_git_tarban_a_kizart_staging_es_ds_store_nem_szamit(self):
        self._git_tar()
        alap = epites.ujjlenyomat(self.root, "mag")
        staging = self.root / "modulok/m/staging"
        staging.mkdir(parents=True)
        (staging / "video.mp4").write_bytes(b"\0" * 1024)
        (self.root / "core/.DS_Store").write_bytes(b"x")
        self.assertEqual(epites.ujjlenyomat(self.root, "mag"), alap, "a staging és a .DS_Store nem forrás")
        with mock.patch.object(epites, "_bejart_fajlok", side_effect=AssertionError("git-tárban nincs bejárás")):
            epites.ujjlenyomat(self.root, "mag")
        (self.root / "core/a.py").write_text("módosított", encoding="utf-8")
        self.assertNotEqual(epites.ujjlenyomat(self.root, "mag"), alap)

    def test_git_tarban_a_nem_kovetett_de_nem_kizart_uj_forras_is_szamit(self):
        self._git_tar()
        alap = epites.ujjlenyomat(self.root, "mag")
        (self.root / "core/uj.py").write_text("x", encoding="utf-8")
        self.assertNotEqual(epites.ujjlenyomat(self.root, "mag"), alap)

    def test_a_felulet_resze_a_svelte_config_es_a_tsconfig(self):
        alap = epites.ujjlenyomat(self.root, "felulet")
        for f in ("app/svelte.config.js", "app/tsconfig.json"):
            (self.root / f).write_text("módosított " + f, encoding="utf-8")
            uj = epites.ujjlenyomat(self.root, "felulet")
            self.assertNotEqual(uj, alap, f)
            alap = uj

    def test_tartalek_bejaras_kihagyja_a_stagingot_es_a_rejtett_fajlokat(self):
        alap = epites.ujjlenyomat(self.root, "mag")           # nincs git-tár: tartalék bejárás
        for rel in ("modulok/m/staging/v.mp4", "modulok/m/archive/v.mp4", "core/__pycache__/a.pyc", "core/.DS_Store",
                    "modulok/m/.pytest_cache/x"):
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_bytes(b"x" * 10)
        self.assertEqual(epites.ujjlenyomat(self.root, "mag"), alap)

    def test_tartalek_bejaras_a_meretplafon_folott_csak_a_meretet_nezi(self):
        nagy = self.root / "modulok/m/nagy.bin"
        with open(nagy, "wb") as fh:
            fh.truncate(epites.FAJL_MAX_BAJT + 1)               # ritka fájl: nem foglal helyet
        alap = epites.ujjlenyomat(self.root, "mag")
        with open(nagy, "r+b") as fh:
            fh.seek(10)
            fh.write(b"x")
        self.assertEqual(epites.ujjlenyomat(self.root, "mag"), alap, "a tartalom nem olvasódik")
        with open(nagy, "r+b") as fh:
            fh.truncate(epites.FAJL_MAX_BAJT + 2)
        self.assertNotEqual(epites.ujjlenyomat(self.root, "mag"), alap)

    def test_masik_tar_kizart_almappajaban_a_tartalek_jon_nem_ures_lista(self):
        kulso = Path(self._t.name) / "kulso"
        kulso.mkdir()
        (kulso / ".gitignore").write_text("belso/\n", encoding="utf-8")
        _git(kulso, "init", "-q")
        belso = kulso / "belso"
        (belso / "core").mkdir(parents=True)
        (belso / "core/a.py").write_text("x", encoding="utf-8")
        self.assertIsNone(epites._git_fajlok(belso, epites.RESZEK["mag"]))
        ures = epites.ujjlenyomat(Path(self._t.name) / "nincs", "mag")
        self.assertNotEqual(epites.ujjlenyomat(belso, "mag"), ures)

    def test_a_futo_mag_ismeretlen_amig_szamolodik(self):
        r = epites.allapot(self.root, {"mag": None, "felulet": "", "hej": ""})
        self.assertEqual(r["futo_ismeretlen"], ["mag"])
        self.assertNotIn("futó mag", [x["resz"] for x in r["reszek"]])
        r = epites.allapot(self.root, {"mag": epites.ujjlenyomat(self.root, "mag")})
        self.assertNotIn("futo_ismeretlen", r)
        self.assertEqual([x["friss"] for x in r["reszek"] if x["resz"] == "futó mag"], [True])

    def test_a_vegpont_a_futo_mag_hianyat_ismeretlenkent_adja(self):
        utak = {}
        epites.utvonalak(types.SimpleNamespace(get=lambda u, f: utak.__setitem__(u, f)))
        k = types.SimpleNamespace(app=types.SimpleNamespace(cfg=types.SimpleNamespace(root=self.root), epites_mag=None),
                                  q={"futo": "1"})
        self.assertEqual(utak["/api/rendszer/epites"](k)["futo_ismeretlen"], ["mag"])


# ------------------------------------------------------------------ a core indulása és leállása (szálon, álgyökéren)

class _Core(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        self.addCleanup(lambda: [tasks.REGISTRY.pop(k) for k in list(tasks.REGISTRY) if k.startswith("t_")])

    def indit(self, varj=5.0):
        r, w = os.pipe()
        self.stdin_w, self.stdin_r = os.fdopen(w, "wb"), os.fdopen(r, "rb")
        self.addCleanup(self.stdin_r.close)
        self.ki = _Kimenet()
        self.szal = threading.Thread(target=server.start, args=(self.cfg,),
                                     kwargs={"stdin": self.stdin_r, "out": self.ki, "start_delay": 0}, daemon=True)
        t0 = time.monotonic()
        self.szal.start()
        self.assertTrue(self.ki.jel.wait(varj), "nincs kézfogás")
        self.kezfogas_mp = time.monotonic() - t0
        self.addCleanup(self._leall)

    def _leall(self):
        if not self.stdin_w.closed:
            self.stdin_w.close()
        self.szal.join(30)


class IndulasD8Test(_Core):
    def test_a_kezfogas_nem_var_a_lassu_indulasi_munkara(self):
        """A lassú ujjlenyomat (pl. egy nagy fájl a mag útjain) és a lassú helyreállítás a kézfogás után, háttérben fut."""
        kesz = threading.Event()

        def lassu_ujjlenyomat(root, resz):
            time.sleep(2.0)
            kesz.set()
            return "f" * 64

        eredeti_tmp = server.App.tmp_takaritas_hatter

        def lassu_tmp(app):
            time.sleep(1.5)                 # a vault bejárása egy nagy, hideg vaulton
            eredeti_tmp(app)

        with mock.patch.object(server.epites, "ujjlenyomat", side_effect=lassu_ujjlenyomat), \
                mock.patch.object(server.App, "tmp_takaritas_hatter", lassu_tmp):
            self.indit()
            self.assertLess(self.kezfogas_mp, 1.0, "a kézfogás a lassú indulási munkára várt")
            self.assertTrue(kesz.wait(15), "az ujjlenyomat a háttérben elkészül")
        self.stdin_w.close()
        self.szal.join(30)
        self.assertFalse(self.szal.is_alive())


class LeallasTest(_Core):
    def test_egy_komponens_hibaja_nem_akasztja_a_kilepest_es_a_mentest(self):
        mentesek = []

        def hibas(*a, **k):
            raise RuntimeError("szándékos leállítási hiba")

        with mock.patch.object(server.naptar_szolgalat.NaptarSzolgalat, "leallit", hibas), \
                mock.patch.object(server.mentes, "kilepeskor", lambda cfg, idokeret=None: mentesek.append(idokeret)):
            self.indit()
            self.stdin_w.close()
            self.szal.join(30)
        self.assertFalse(self.szal.is_alive(), "a core kilépett")
        self.assertEqual(mentesek, [None], "a kilépési mentés lefutott (egyszer)")

    def test_a_stdin_zaras_utan_a_meg_futo_feladat_fokozva_leall(self):
        self.cfg.data.setdefault("core", {})["leallas_fokozas_mp"] = 1
        tasks.register(tasks.TaskType("t_lassu", "t_lassu", lambda cfg, p, stop: (
            [tasks.Step("alszik", [sys.executable, "-c", "import time; print('indul', flush=True); time.sleep(60)"],
                        str(self.root))], "", [])))
        self.indit()
        import http.client
        from tests.helpers import API_TITOK
        port = json.loads(self.ki.sorok[0])["port"]
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        c.request("POST", "/api/feladatok", body=json.dumps({"tipus": "t_lassu"}),
                  headers={"Host": f"127.0.0.1:{port}", "X-Manifold": API_TITOK, "Content-Type": "application/json"})
        r = c.getresponse()
        self.assertEqual(r.status, 201)
        fid = json.loads(r.read())["id"]
        naplo = self.cfg.path("runs") / "feladatok" / f"{fid}.log"
        t0 = time.monotonic()
        while not (naplo.exists() and "indul" in naplo.read_text(encoding="utf-8")) and time.monotonic() - t0 < 15:
            time.sleep(0.05)
        t0 = time.monotonic()
        self.stdin_w.close()
        self.szal.join(30)
        self.assertFalse(self.szal.is_alive())
        self.assertLess(time.monotonic() - t0, 15, "a nem kulturált feladat nem tarthatja vissza a kilépést")
        self.assertIn("azonnali leállítás", naplo.read_text(encoding="utf-8"))


class MediaKuldesTest(unittest.TestCase):
    def test_a_leallas_megszakitja_a_folyo_mediakuldest(self):
        app = types.SimpleNamespace(_lock=threading.Lock(), _ws=set(), _media=set(), closing=False)
        a, b = socket.socketpair()
        self.addCleanup(a.close)
        self.addCleanup(b.close)
        hibak = []

        def kuld():
            try:
                with server.App.media_kuldes(app, a):
                    while True:
                        a.sendall(b"x" * 65536)        # a túloldal nem olvas: a küldés elakad
            except OSError as e:
                hibak.append(e)

        t = threading.Thread(target=kuld, daemon=True)
        t.start()
        time.sleep(0.3)
        self.assertTrue(t.is_alive(), "a küldés elakadt")
        server.App.close_ws(app)
        t.join(5)
        self.assertFalse(t.is_alive(), "a close_ws lezárta a socketet")
        self.assertEqual(len(hibak), 1)
        self.assertEqual(app._media, set())
        with self.assertRaises(server.HttpError):          # leálláskor új küldés nem indul
            with server.App.media_kuldes(app, b):
                pass


# ------------------------------------------------------------------ feladatsor

class FeladatsorTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, _ = alg_core(self._t.name)
        self.addCleanup(lambda: [tasks.REGISTRY.pop(k) for k in list(tasks.REGISTRY) if k.startswith("t_")])

    def _tipus(self, nev, kod):
        tasks.register(tasks.TaskType(nev, nev, lambda cfg, p, stop: (
            [tasks.Step("lépés", [sys.executable, "-c", kod], str(self.root))], "", [])))

    def _var(self, q, fid, mp=20):
        t0 = time.monotonic()
        while time.monotonic() - t0 < mp:
            d = q.get(fid)
            if d and d["allapot"] in tasks.LEZART:
                return d
            time.sleep(0.05)
        return q.get(fid)

    def test_a_legnagyobb_futasido_utan_a_feladat_hibaval_leall(self):
        self.cfg.data.setdefault("feladatsor", {})["max_futas_tipus_mp"] = {"t_orok": 0.5}
        self._tipus("t_orok", "import time; time.sleep(60)")
        q = tasks.Queue(self.cfg, start_delay=0)
        self.addCleanup(q.close, 0)
        self.assertEqual(q.max_futas_mp("t_orok"), 0.5)
        self.assertEqual(q.max_futas_mp("mentes"), 3600)
        fid = q.submit("t_orok", {})["id"]
        d = self._var(q, fid)
        self.assertEqual(d["allapot"], "hiba")
        self.assertIn("legnagyobb futásidő", d["hiba"])

    def test_a_db_zarasa_a_futo_munkasszal_alatt_nem_dob_kivetelt(self):
        self._tipus("t_fut", "import time; print('indul', flush=True); time.sleep(1.5)")
        q = tasks.Queue(self.cfg, start_delay=0)
        fid = q.submit("t_fut", {})["id"]
        t0 = time.monotonic()
        while q.get(fid)["allapot"] != "fut" and time.monotonic() - t0 < 10:
            time.sleep(0.02)
        hibak = []
        regi = threading.excepthook
        threading.excepthook = lambda a: hibak.append(a.exc_value)
        try:
            q.close(timeout=0)
            t0 = time.monotonic()
            while q._running and time.monotonic() - t0 < 10:
                time.sleep(0.05)
            time.sleep(0.2)
        finally:
            threading.excepthook = regi
        self.assertEqual(q._running, {}, "a munkásszál a zárás után is rendben véget ért")
        self.assertEqual(hibak, [])
        q2 = tasks.Queue(self.cfg, start_delay=3600)
        self.addCleanup(q2.close, 0)
        self.assertEqual(q2.get(fid)["allapot"], "megszakadt", "a `fut`-ban maradt sor a következő indulásnál lezárul")

    def test_a_ps_nyelvfuggetlen(self):
        kapott = {}

        def run(argv, **k):
            kapott.update(k)
            return subprocess.CompletedProcess(argv, 0, "x\n", "")

        with mock.patch.object(tasks.subprocess, "run", run):
            tasks._ps("lstart", 1)
        self.assertEqual(kapott["env"]["LC_ALL"], "C")

    def test_az_arva_rendezes_nem_tartja_fel_a_sor_letrehozasat(self):
        q = tasks.Queue(self.cfg, start_delay=3600)
        q._db.execute("INSERT INTO feladat (id, tipus, cim, allapot, letrehozva, lepes_pid, lepes_inditva, lepes_argv0) "
                      "VALUES ('F-arva', 'mentes', 'x', 'fut', '2026-10-14T00:00:00', 999999, 'nem egyezik', 'x')")
        q.close(0)
        horog = []

        def lassu_horog(fid):
            time.sleep(1.5)
            horog.append(fid)

        t0 = time.monotonic()
        q = tasks.Queue(self.cfg, start_delay=3600, leallitas_horog=lassu_horog)
        self.addCleanup(q.close, 0)
        self.assertLess(time.monotonic() - t0, 1.0)
        self.assertEqual(q.get("F-arva")["allapot"], "megszakadt", "a DB-állapot szinkron áll be")
        self.assertTrue(q.arva_var(10))
        self.assertEqual(horog, ["F-arva"])


# ------------------------------------------------------------------ index

class IndexIroSzalTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        from tests.index_segedek import alvault
        self.cfg, self.v = alvault(self._t.name)

    def test_a_halott_iro_szalra_a_mentes_nem_var(self):
        from core.index import indexelo
        with mock.patch.object(indexelo.tar, "nyit", side_effect=RuntimeError("nem nyílik")):
            ix = indexelo.Index(self.cfg, publish=lambda e, **k: None)
            ix.indit()
            self.assertTrue(ix.var(10))
            ix._szal.join(5)
        self.addCleanup(ix.leallit)
        self.assertFalse(ix._szal.is_alive())
        t0 = time.monotonic()
        ix.sajat_iras("A.md", "0" * 64)
        self.assertFalse(ix.frissit(["A.md"]))
        self.assertLess(time.monotonic() - t0, 0.5)

    def test_a_koteg_atmeneti_hibaja_a_kovetkezo_sikeres_kotegnel_lekerul(self):
        from tests.index_segedek import index_indit, var_ra
        esemenyek = []
        ix, esemenyek = index_indit(self.cfg)
        self.addCleanup(ix.leallit)
        eredeti = ix._koteg
        hibak = [RuntimeError("átmeneti")]

        def koteg(k):
            if hibak:
                raise hibak.pop()
            return eredeti(k)

        ix._koteg = koteg
        ix.jelez(["A.md"])
        self.assertTrue(var_ra(lambda: ix.allapot_d["hiba"] is not None, 10))
        ix.jelez(["A.md"])
        self.assertTrue(var_ra(lambda: ix.allapot_d["hiba"] is None, 10), "a sikeres köteg törli az átmeneti hibát")


# ------------------------------------------------------------------ git-időkorlát, chat-időkorlát, worker, backup, titok

class GitIdokorlatTest(unittest.TestCase):
    def test_a_lógó_git_magyar_snapshoterror(self):
        with tmpdir() as t:
            munkafa = Path(t) / "v"
            munkafa.mkdir()
            repo = snapshot.Repo("vault", munkafa, Path(t) / "v.git")
            repo.init()
            with self.assertRaises(snapshot.SnapshotError) as cm:
                repo.git("status", timeout=0.0001)
            self.assertIn("időtúllépés", str(cm.exception))
            with self.assertRaises(snapshot.SnapshotError):
                repo.git_bytes("status", timeout=0.0001)


class ChatIdokorlatTest(unittest.TestCase):
    def test_a_chat_idokorlata_modonkent(self):
        kapott = []
        with mock.patch.object(kliens, "keres", lambda u, ut, body=None, timeout=None: kapott.append(timeout) or {}), \
                mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MOS_MODELL_MOD", None)
            kliens.chat("http://x", [], feladat="szoveg")
            kliens.chat("http://x", [], feladat="szoveg", mod="auto")
            kliens.chat("http://x", [], feladat="szoveg", timeout=5)
        self.assertEqual(kapott, [kliens.CHAT_IDOKORLAT_MP, kliens.CHAT_IDOKORLAT_AUTO_MP, 5])
        self.assertTrue(all(t and t > 0 for t in kapott))

    def test_az_idokorlat_konfigkulcsbol(self):
        cfg = types.SimpleNamespace(section=lambda nev: {"chat_idokorlat_mp": 123, "chat_idokorlat_auto_mp": 456}
                                    if nev == "modellgazda" else {})
        self.assertEqual(kliens.chat_idokorlat("interaktiv", cfg), 123)
        self.assertEqual(kliens.chat_idokorlat("auto", cfg), 456)
        self.assertGreaterEqual(kliens.chat_idokorlat("interaktiv"), 600, "a gondolkodó modellek tétele ~600 s")

    def _ujraproba(self, hibak, health):
        hivasok = []

        def keres(u, ut, body=None, timeout=None):
            hivasok.append(ut)
            if hibak:
                raise hibak.pop(0)
            return {"ok": 1}

        with mock.patch.object(kliens, "keres", keres), mock.patch.object(kliens, "health", health):
            try:
                return kliens.chat_keres("http://x", {"messages": [], "mod": "auto"}, timeout=1), hivasok
            except kliens.KliensHiba as e:
                return e, hivasok

    def test_elveszett_valasz_utan_tetlen_workernel_egy_ujraproba(self):
        tetlen = lambda u, timeout=5: {"ok": True, "fut": None, "fuggo": []}      # noqa: E731
        r, h = self._ujraproba([kliens.KliensHiba(503, "timed out", {"kapcsolat": True})], tetlen)
        self.assertEqual((r, len(h)), ({"ok": 1}, 2))
        # a második hiba után nincs harmadik próba
        r, h = self._ujraproba([kliens.KliensHiba(503, "x", {"kapcsolat": True})] * 2, tetlen)
        self.assertIsInstance(r, kliens.KliensHiba)
        self.assertEqual(len(h), 2)

    def test_dolgozo_vagy_halott_workernel_es_http_hibanal_nincs_ujraproba(self):
        dolgozik = lambda u, timeout=5: {"ok": True, "fut": {"mod": "auto"}, "fuggo": []}     # noqa: E731

        def halott(u, timeout=5):
            raise kliens.KliensHiba(503, "nem érhető el", {"kapcsolat": True})

        for health in (dolgozik, halott):
            r, h = self._ujraproba([kliens.KliensHiba(503, "timed out", {"kapcsolat": True})], health)
            self.assertIsInstance(r, kliens.KliensHiba)
            self.assertEqual(len(h), 1)
        tetlen = lambda u, timeout=5: {"ok": True, "fut": None, "fuggo": []}      # noqa: E731
        r, h = self._ujraproba([kliens.KliensHiba(503, "a modellgazda leáll")], tetlen)     # a worker válaszolt: nem kapcsolathiba
        self.assertIsInstance(r, kliens.KliensHiba)
        self.assertEqual(len(h), 1)

    def test_a_meres_is_az_idokorlatos_utat_hasznalja(self):
        from core.modell import eval as E
        kapott = []
        with mock.patch.object(kliens, "chat_keres", lambda u, body, **k: kapott.append(body) or
                               {"choices": [{"message": {"content": "v"}}]}):
            self.assertEqual(E._hiv("http://x", "m", {"messages": []}, None, "auto")[0], "v")
        self.assertEqual(kapott[0]["mod"], "auto")


class WorkerAzonnalTest(unittest.TestCase):
    def test_az_azonnali_leallitas_nem_var_a_folyo_hivasra(self):
        f = kliens.Folyamat.__new__(kliens.Folyamat)
        f._lock = threading.Lock()
        f.url = "http://127.0.0.1:1"
        f.proc = subprocess.Popen([sys.executable, "-c", "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                                   "time.sleep(60)"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        p = f.proc
        self.addCleanup(lambda: p.poll() is None and p.kill())
        t0 = time.monotonic()
        f.leallit(azonnal=True)
        self.assertLess(time.monotonic() - t0, 5)
        self.assertIsNotNone(p.poll())


class BackupKorZarTest(unittest.TestCase):
    def test_a_backup_a_kor_zar_alatt_fut(self):
        from core import __main__ as fo
        with tmpdir() as t:
            cfg, root, _ = alg_core(t)
            foglalt = []

            def ment(c, log=None):
                try:
                    with frame.run_lock(c, wait=False):
                        foglalt.append(False)
                except frame.Busy:
                    foglalt.append(True)
                return []

            with mock.patch.dict(os.environ, {"MOS_ROOT": str(root), "HOME": str(Path(t) / "home")}), \
                    mock.patch("core.mentes.ment", ment):
                self.assertEqual(fo.backup(), 0)
            self.assertEqual(foglalt, [True])


class ApiTitokKornyezetTest(unittest.TestCase):
    def test_a_titok_kikerul_a_core_kornyezetebol(self):
        from core import __main__ as fo
        kapott = {}

        def start(**k):
            kapott.update(k, env=os.environ.get("MOS_API_TITOK"))
            return 0

        with mock.patch.dict(os.environ, {"MOS_API_TITOK": "rogzitett-titok-0123456789"}), \
                mock.patch.object(server, "start", start):
            self.assertEqual(fo.main(["start"]), 0)
            self.assertNotIn("MOS_API_TITOK", os.environ)
        self.assertEqual(kapott["api_titok"], "rogzitett-titok-0123456789")
        self.assertIsNone(kapott["env"])
        self.assertEqual(server.api_titok_sorsol("rogzitett-titok-0123456789"), "rogzitett-titok-0123456789")


class TmpTakaritasTest(unittest.TestCase):
    def test_a_core_indulasa_utani_friss_tmp_marad(self):
        with tmpdir() as t:
            cfg, root, v = alg_core(t)
            regi = v / ".a.md.deadbeef.manifold-tmp"
            regi.write_text("x")
            os.utime(regi, (time.time() - 60, time.time() - 60))
            hatar = time.time() - 1
            friss = v / ".b.md.0123abcd.manifold-tmp"
            friss.write_text("y")
            uzenetek = frame.tmp_takaritas(cfg, elotte=hatar)
            self.assertFalse(regi.exists())
            self.assertTrue(friss.exists(), "egy folyó mentés friss ideiglenes fájlja nem maradék")
            self.assertEqual(len(uzenetek), 1)


if __name__ == "__main__":
    unittest.main()
