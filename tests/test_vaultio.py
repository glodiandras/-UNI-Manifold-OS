"""A fájlírás-API (`core/vaultio.py`) — a legacy pult írási tesztjeinek portja, álvaulton.

Amit ezek a tesztek őriznek (L45–L46):
  - rejtett és vaulton kívüli út nem olvasható és nem írható;
  - a mentés soha nem ír vakon felül: ha a fájl a betöltés óta változott, ütközés (409), a fájl érintetlen;
  - pillanatkép: a szerkesztés első mentése előtt kézi commit, a lezáráskor saját commit
    (Mos-Forras: pult-szerkeszto), visszavonható; ha kör fut (kör-zár) vagy vault-író feladat fut,
    git-művelet nincs, a fájl mégis mentődik;
  - a lemezen álló (NFD) név megmarad, a CRLF-es fájl CRLF marad;
  - az új jegyzet a séma szerint jön létre (H1 a sorszám-előtag nélkül), meglévőt nem ír felül.
"""
import fcntl
import http.client
import json
import os
import subprocess
import sys
import threading
import time
import unicodedata
import unittest
import urllib.parse

from core import frame, snapshot, vaultio
from core.utvonalak import HttpError
from tests import csak_darwin
from tests.helpers import API_TITOK, REPO, alg_core, env, ir, tmpdir


class Alap(unittest.TestCase):
    RP = "T01 - Történelem/Görög.md"

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        ir(self.v, "T01 - Történelem/Ókor.md", "# Ókor\n[[Róma]]\n")
        ir(self.v, self.RP, "# Görög\n")
        ir(self.v, "M03 - Algebra/M03.canvas", "{}")
        ir(self.v, "F02 - Fizika/Magányos.md", "# senki nem hivatkozik rá\n")
        ir(self.v, ".rejtett.md", "# nem látszik\n")
        self.repo = snapshot.repos(self.cfg)["vault"]
        self.repo.init()
        self.repo.commit("alap", {"Mos-Forras": "kezi"})
        self.esemenyek = []
        self.V = vaultio.Vault(self.cfg, publish=lambda e, **k: self.esemenyek.append(e))

    def _nyit(self, rp=RP):
        return self.V.read(rp)["hash"]

    def _commitok(self):
        return self.repo.log(20)


class OlvasasTest(Alap):
    def test_ut_vedelem(self):
        kint = self.v.parent / "kint.md"
        kint.write_text("titok", encoding="utf-8")
        os.symlink(kint, self.v / "link.md")
        for rossz in ("../kint.md", ".obsidian/app.json", "T01 - Történelem/../../kint.md", "", "a/./b.md", ".rejtett.md"):
            with self.assertRaises(vaultio.Invalid, msg=rossz):
                self.V.read(rossz)
        with self.assertRaises(vaultio.Invalid):
            self.V.read("link.md")                               # szimbolikus link a vaulton kívülre
        with self.assertRaises(vaultio.NotFound):
            self.V.read("nincs.md")
        with self.assertRaises(vaultio.Invalid):
            self.V.write({"ut": "../kint.md", "tartalom": "x", "alap": "0"})
        self.assertEqual(kint.read_text(encoding="utf-8"), "titok")

    def test_olvasas_hash_es_jel(self):
        d = self.V.read(self.RP)
        self.assertEqual(d["tartalom"], "# Görög\n")
        self.assertEqual(d["hash"], vaultio.sha1(b"# G\xc3\xb6r\xc3\xb6g\n"))
        self.assertFalse(d["kodolas_hiba"])

    def test_ervenytelen_utf8_jelet_kap(self):
        """A hibás bájtsor cserekarakterrel olvasható, de jelet kap: a szerkesztő csak olvasásra nyitja (C08)."""
        (self.v / "T01 - Történelem/Latin1.md").write_bytes(b"# R\xf3ma\n")
        d = self.V.read("T01 - Történelem/Latin1.md")
        self.assertTrue(d["kodolas_hiba"])
        self.assertEqual(d["tartalom"], "# R\ufffdma\n")
        self.assertEqual(d["hash"], vaultio.sha1(b"# R\xf3ma\n"))


class MentesTest(Alap):
    def test_ment_es_a_szerkesztes_lezarasa_pillanatkep(self):
        alap = self._nyit()
        (self.v / "F02 - Fizika/Magányos.md").write_text("# a gazda Obsidianban írta\n", encoding="utf-8")
        r = self.V.write({"ut": self.RP, "tartalom": "# Görög\n\nÚj sor.\n", "alap": alap, "elso": True})
        self.assertEqual((self.v / self.RP).read_text(encoding="utf-8"), "# Görög\n\nÚj sor.\n")
        self.assertTrue(r["git"])
        self.assertTrue(r["elotte"])                          # a függő kézi változás külön kézi commitba került
        self.assertEqual(self._commitok()[0].trailers.get("Mos-Forras"), "kezi")
        self.assertIn("F02 - Fizika/Magányos.md", self.repo.changed_files(r["elotte"]))
        self.assertIsNone(r["pillanat"])
        r2 = self.V.write({"ut": self.RP, "tartalom": "# Görög\n\nÚj sor, javítva.\n", "alap": r["hash"], "pillanat": True})
        c = self._commitok()[0]
        self.assertEqual(r2["pillanat"], c.sha)
        self.assertEqual(c.trailers["Mos-Forras"], "pult-szerkeszto")
        self.assertEqual(c.trailers["Mos-Tetel"], self.RP)
        self.assertTrue(c.run.startswith("SZERK-"))
        self.assertEqual(self.repo.changed_files(c.sha), [self.RP])
        self.repo.undo_commit(c.sha)                           # egy kattintással visszavonható
        self.assertEqual((self.v / self.RP).read_text(encoding="utf-8"), "# Görög\n")
        self.assertFalse(list(self.v.rglob("*.manifold-tmp")))
        self.assertEqual(self.esemenyek[-1]["tipus"], "vault_iras")

    def test_utkozes_nem_ir_felul(self):
        alap = self._nyit()
        (self.v / self.RP).write_text("# Görög\n\nAz Obsidian közben ezt írta.\n", encoding="utf-8")
        with self.assertRaises(vaultio.Conflict) as cm:
            self.V.write({"ut": self.RP, "tartalom": "# az enyém\n", "alap": alap, "elso": True, "pillanat": True})
        self.assertEqual(cm.exception.data["hash"], vaultio.sha1((self.v / self.RP).read_bytes()))
        self.assertIn("Az Obsidian közben", (self.v / self.RP).read_text(encoding="utf-8"))
        with self.assertRaises(vaultio.Invalid):
            self.V.write({"ut": self.RP, "tartalom": "# vakon\n"})           # alapváltozat nélkül nem ír
        # „az enyémet mentem": a lemezen lévőre építve — az előbb kézi commitba kerül, nem vész el
        r = self.V.write({"ut": self.RP, "tartalom": "# az enyém\n", "alap": cm.exception.data["hash"], "elso": True})
        self.assertIn("Az Obsidian közben", self.repo.git("show", f"{r['elotte']}:{self.RP}").stdout)

    def test_kor_alatt_git_nelkul_ment(self):
        alap = self._nyit()
        lock = self.cfg.path("run") / "kor.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        elotte = len(self._commitok())
        with open(lock, "a+") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)                      # egy kör fut
            r = self.V.write({"ut": self.RP, "tartalom": "# Görög\n\nkör közben\n", "alap": alap, "elso": True, "pillanat": True})
            fcntl.flock(fh, fcntl.LOCK_UN)
        self.assertFalse(r["git"])
        self.assertIsNone(r["pillanat"])
        self.assertIn("pillanatkép nélkül", r["uzenet"])
        self.assertEqual(len(self._commitok()), elotte)
        self.assertIn("kör közben", (self.v / self.RP).read_text(encoding="utf-8"))
        foglalt = vaultio.Vault(self.cfg, busy=lambda: True)     # vault-író feladat fut
        r2 = foglalt.write({"ut": self.RP, "tartalom": "# Görög\n\nfeladat közben\n", "alap": r["hash"], "pillanat": True})
        self.assertFalse(r2["git"])
        self.assertEqual(len(self._commitok()), elotte)

    @csak_darwin("NFD-nevű fájl (a Linux fájlrendszere nem normalizál: az NFD és NFC név két külön fájl)")
    def test_nfd_nev_es_crlf_megmarad(self):
        nfd = unicodedata.normalize("NFD", "Öröklés.md")
        ir(self.v, f"T01 - Történelem/{nfd}", "# Öröklés\r\n\r\nElső.\r\n")
        rp = "T01 - Történelem/Öröklés.md"
        r = self.V.write({"ut": rp, "tartalom": "# Öröklés\n\nMásodik.\n", "alap": self._nyit(rp)})
        nevek = os.listdir(self.v / "T01 - Történelem")
        self.assertIn(nfd, nevek)
        if nfd != unicodedata.normalize("NFC", nfd):
            self.assertNotIn(unicodedata.normalize("NFC", nfd), nevek)
        self.assertEqual((self.v / "T01 - Történelem" / nfd).read_bytes(), "# Öröklés\r\n\r\nMásodik.\r\n".encode())
        self.assertEqual(r["hash"], vaultio.sha1((self.v / "T01 - Történelem" / nfd).read_bytes()))

    def test_csak_jegyzet_mentheto(self):
        ir(self.v, "T01 - Történelem/x.txt", "{}")
        with self.assertRaises(vaultio.Invalid):
            self.V.write({"ut": "T01 - Történelem/x.txt", "tartalom": "{}", "alap": "x"})

    def test_nem_valtozott(self):
        r = self.V.write({"ut": self.RP, "tartalom": "# Görög\n", "alap": self._nyit(), "pillanat": True})
        self.assertEqual(r["uzenet"], "nem változott")
        self.assertIsNone(r["pillanat"])


class GitHibaTest(Alap):
    """K1 (audit): elakadt `index.lock` (SIGKILL, áramszünet egy commit közben) mellett is ment a szerkesztő.
    A git-hiba nem akaszthatja meg a fájlírást: a mentés pillanatkép nélkül ír, és jelzi (`git: false`,
    üzenet, `pillanat_hiba` WS-esemény) — ugyanaz az ág, mint a foglalt kör-zárnál."""

    def setUp(self):
        super().setUp()
        self.lock = self.repo.git_dir / "index.lock"
        self.lock.write_text("")

    def _hibaesemeny(self):
        return [e for e in self.esemenyek if e["tipus"] == "pillanat_hiba"]

    def test_elso_mentes_git_hibanal_is_ir(self):
        alap = self._nyit()
        r = self.V.write({"ut": self.RP, "tartalom": "# Görög\n\nelső\n", "alap": alap, "elso": True})
        self.assertEqual((self.v / self.RP).read_text(encoding="utf-8"), "# Görög\n\nelső\n")
        self.assertFalse(r["git"])
        self.assertIsNone(r["elotte"])
        self.assertIn("pillanatkép nélkül", r["uzenet"])
        self.assertTrue(r["figyelmeztetes"])
        self.assertEqual(self._hibaesemeny()[-1]["ut"], self.RP)

    def test_lezaro_mentes_a_fajliras_sikere_a_valasz(self):
        alap = self._nyit()
        r = self.V.write({"ut": self.RP, "tartalom": "# Görög\n\nlezárva\n", "alap": alap, "pillanat": True})
        self.assertEqual(r["hash"], vaultio.sha1((self.v / self.RP).read_bytes()))
        self.assertIsNone(r["pillanat"])
        self.assertFalse(r["git"])
        self.assertTrue(self._hibaesemeny())
        # a kliens alap-hash-e friss: a következő mentés nem hamis 409
        r2 = self.V.write({"ut": self.RP, "tartalom": "# Görög\n\ntovább\n", "alap": r["hash"], "elso": True})
        self.assertTrue(r2["ok"])

    def test_uj_jegyzet_git_hibanal(self):
        r = self.V.create({"mappa": "T01 - Történelem", "nev": "Új"})
        self.assertTrue((self.v / r["ut"]).is_file())
        self.assertIsNone(r["pillanat"])
        self.assertFalse(r["git"])

    def test_git_rendben_figyelmeztetes_nincs(self):
        self.lock.unlink()
        r = self.V.write({"ut": self.RP, "tartalom": "# Görög\n\nx\n", "alap": self._nyit(), "elso": True,
                          "pillanat": True})
        self.assertTrue(r["git"])
        self.assertIsNone(r["figyelmeztetes"])
        self.assertFalse(self._hibaesemeny())


class KanonikusUtTest(Alap):
    """T018: az APFS kis-nagybetűre és normalizálásra érzéketlen, a git pathspec, a mentetlen-halmaz és az index nem: a
    `jegyzetek/a.md` kérés ugyanazt a fájlt írta, mint a `Jegyzetek/A.md`, de a szöveg „kézi” commitba került (a válasz hamis
    503, az index fantom-sorokat kapott). Most minden út a lemezen álló, NFC nevekre kanonizálódik."""

    def test_kanonikus_szegmensenkent(self):
        self.assertEqual(self.V.kanonikus("t01 - történelem/görög.md"), "T01 - Történelem/Görög.md")
        self.assertEqual(self.V.kanonikus("T01 - Történelem/Új fájl.md"), "T01 - Történelem/Új fájl.md")     # nincs meg: marad
        self.assertEqual(self.V.kanonikus("t01 - történelem/ÚJ.md"), "T01 - Történelem/ÚJ.md")               # a szülő kanonizálódik
        self.assertEqual(self.V.kanonikus("t01 - történelem/görög.md", utolso=False), "T01 - Történelem/görög.md")
        self.assertEqual(self.V.kanonikus("Nincs/Ilyen/Mappa.md"), "Nincs/Ilyen/Mappa.md")

    @csak_darwin("NFD-nevű fájl (a Linux fájlrendszere nem normalizál: az NFD és NFC név két külön fájl)")
    def test_nfd_a_lemezen_nfc_a_kanonikus(self):
        nfd = unicodedata.normalize("NFD", "Öröklés.md")
        ir(self.v, f"T01 - Történelem/{nfd}", "# Ö\n")
        k = self.V.kanonikus("t01 - történelem/öröklés.md")
        self.assertEqual(k, "T01 - Történelem/" + unicodedata.normalize("NFC", "Öröklés.md"))
        self.assertEqual(self.V.read(k)["ut"], k)

    def test_olvasas_es_mentes_a_lemezen_allo_nevet_adja_es_a_commit_nem_kezi(self):
        d = self.V.read("t01 - történelem/görög.md")
        self.assertEqual(d["ut"], self.RP)
        r = self.V.write({"ut": "t01 - történelem/GÖRÖG.md", "tartalom": "# Görög\n\nmentve\n", "alap": d["hash"],
                          "elso": True, "pillanat": True})
        self.assertEqual(r["ut"], self.RP)
        self.assertTrue(r["git"] and r["pillanat"], r)
        self.assertIsNone(r["figyelmeztetes"])
        self.assertEqual(self.repo.changed_files(r["pillanat"]), [self.RP])
        c = self.repo.log(1)[0]
        self.assertEqual((c.trailers["Mos-Forras"], c.trailers["Mos-Tetel"]), (vaultio.FORRAS, self.RP))
        self.assertEqual(self.repo.dirty_paths(), [])
        self.assertEqual([e["ut"] for e in self.esemenyek if e["tipus"] == "vault_iras"], [self.RP])

    def test_letrehozas_kisbetus_mappaval(self):
        r = self.V.create({"mappa": "t01 - történelem", "nev": "Új"})
        self.assertEqual(r["ut"], "T01 - Történelem/Új.md")
        self.assertEqual(self.repo.changed_files(r["pillanat"]), ["T01 - Történelem/Új.md"])


class VezerloKarakteresUtTest(Alap):
    """T017 (L13): a vezérlőkarakteres (újsoros, U+2028, …) út a commit-metaadatot hamisítaná: a `norm_path` elutasítja."""

    def test_vezerlokarakteres_ut_ervenytelen(self):
        for rossz in ("a\nb.md", "a\u2028b.md", "a\u2029b.md", "a\x7fb.md", "a\x85b.md", "a\x1eb.md", "a\x0bb.md",
                      "T01 - Történelem/Mos-Kor: X\n.md"):
            with self.assertRaises(vaultio.Invalid, msg=repr(rossz)):
                vaultio.norm_path(rossz)
            with self.assertRaises(vaultio.Invalid, msg=repr(rossz)):
                self.V.read(rossz)
        self.assertEqual(vaultio.norm_path("T01 - Történelem/Ókor.md"), "T01 - Történelem/Ókor.md")
        self.assertEqual(vaultio.norm_path("T01/tab\tnév.md"), "T01/tab\tnév.md")      # a tabulátor nem sortörő: marad (M1)


class TaroloHianyTest(Alap):
    """T024 (2. audit): ha a vault elérhető, de a pillanatkép-tároló (`vault.git`) nem él, a mentés eddig némán `git: true`-t
    mondott — pedig nincs visszavonás, előzmény és bundle. Most: figyelmeztetés + `pillanat_hiba` esemény, `git: false`."""

    def setUp(self):
        super().setUp()
        import shutil
        shutil.rmtree(self.repo.git_dir)

    def _hibaesemeny(self):
        return [e for e in self.esemenyek if e["tipus"] == "pillanat_hiba"]

    def test_lezaro_mentes_tarolo_nelkul_jelez(self):
        r = self.V.write({"ut": self.RP, "tartalom": "# Görög\n\nmentve\n", "alap": self._nyit(), "elso": True, "pillanat": True})
        self.assertEqual((self.v / self.RP).read_text(encoding="utf-8"), "# Görög\n\nmentve\n")
        self.assertFalse(r["git"])
        self.assertIn("nincs élő pillanatkép-tároló", r["figyelmeztetes"])
        self.assertIn("pillanatkép nélkül", r["uzenet"])
        self.assertEqual(len(self._hibaesemeny()), 1)
        self.assertEqual(self._hibaesemeny()[0]["ut"], self.RP)

    def test_kozbenso_automentes_nem_zajos(self):
        """Az `elso`/`pillanat` nélküli (gépelés közbeni) mentésnél nincs pillanatkép-elvárás: nincs értesítés-áradat."""
        r = self.V.write({"ut": self.RP, "tartalom": "# Görög\n\nközben\n", "alap": self._nyit()})
        self.assertTrue(r["ok"])
        self.assertIsNone(r["figyelmeztetes"])
        self.assertEqual(self._hibaesemeny(), [])

    def test_uj_jegyzet_tarolo_nelkul_jelez(self):
        r = self.V.create({"mappa": "T01 - Történelem", "nev": "Új"})
        self.assertTrue((self.v / r["ut"]).is_file())
        self.assertFalse(r["git"])
        self.assertIn("nincs élő pillanatkép-tároló", r["figyelmeztetes"])
        self.assertEqual(len(self._hibaesemeny()), 1)


class VaultElerhetoTest(Alap):
    """M5 (1. audit), a core fele: a vault elérhetőségének VÁLTÁSA egyetlen `vault_elerheto` WS-esemény (polling nélkül:
    a `Vault` használata észleli) — a felület (C29.7b) ebből tudja, hogy az SSD eltűnt."""

    def _elerheto(self):
        return [e["elerheto"] for e in self.esemenyek if e["tipus"] == "vault_elerheto"]

    def test_valtaskor_egy_esemeny(self):
        self.V.read(self.RP)
        self.assertEqual(self._elerheto(), [])                               # elérhető → elérhető: nincs esemény
        obsidian = self.v / ".obsidian"
        obsidian.rename(self.v / ".obsidian-elrejtve")
        for _ in range(2):
            with self.assertRaises(vaultio.Invalid):
                self.V.read(self.RP)
        self.assertEqual(self._elerheto(), [False])                          # kétszeri hiba, egy esemény
        (self.v / ".obsidian-elrejtve").rename(obsidian)
        self.V.read(self.RP)
        self.V.read(self.RP)
        self.assertEqual(self._elerheto(), [False, True])


class IndulasiTakaritasTest(Alap):
    """K1: induláskor az elakadt `index.lock` a kör-zár alatt eltűnik (a 2.0 minden git-írása a kör-zár alatt
    fut, a legacy befagyasztva: a zárat birtokolva a lock csak elakadt lehet)."""

    def test_elakadt_index_lock_torlodik(self):
        lock = self.repo.git_dir / "index.lock"
        lock.write_text("")
        uzenetek = frame.indulasi_takaritas(self.cfg)
        self.assertFalse(lock.exists())
        self.assertTrue(any("index.lock" in u for u in uzenetek))
        self.assertEqual(frame.indulasi_takaritas(self.cfg), [])

    def test_foglalt_kor_zarnal_marad(self):
        lock = self.repo.git_dir / "index.lock"
        lock.write_text("")
        kor = self.cfg.path("run") / "kor.lock"
        kor.parent.mkdir(parents=True, exist_ok=True)
        with open(kor, "a+") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            frame.indulasi_takaritas(self.cfg)
            fcntl.flock(fh, fcntl.LOCK_UN)
        self.assertTrue(lock.exists())


class FelulirTest(Alap):
    """C29.7b (T116 core-fele): az ütközés-felülírás (`felulir`) foglalt kör-zárnál nem ír pillanatkép nélkül; az
    idempotens mentés."""

    def _kor_zar(self):
        """Egy másik folyamat (egy kör) tartja a kör-zárat: a fájlkezelő, amit az `flock` elenged."""
        lock = self.cfg.path("run") / "kor.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        fh = open(lock, "a+")
        self.addCleanup(fh.close)
        fcntl.flock(fh, fcntl.LOCK_EX)
        return fh

    def test_felulir_foglalt_kor_zarnal_423_es_nem_ir(self):
        self._nyit()
        (self.v / self.RP).write_text("# Görög\n\nAz Obsidian közben ezt írta.\n", encoding="utf-8")
        lemez = vaultio.sha1((self.v / self.RP).read_bytes())
        bajt = (self.v / self.RP).read_bytes()
        self.V.kor_zar_varakozas_mp = 0.3
        self._kor_zar()
        with self.assertRaises(HttpError) as cm:
            self.V.write({"ut": self.RP, "tartalom": "# az enyém\n", "alap": lemez, "elso": True, "felulir": True})
        self.assertEqual(cm.exception.code, 423)
        self.assertTrue(cm.exception.data["foglalt"])
        self.assertEqual((self.v / self.RP).read_bytes(), bajt, "a külső változat nem írható felül pillanatkép nélkül")
        self.assertFalse(list(self.v.rglob("*.manifold-tmp")))
        self.assertFalse([e for e in self.esemenyek if e["tipus"] == "vault_iras"])

    def test_felulir_kivarja_a_kor_zar_felszabadulasat(self):
        """A kör-zár a várakozás alatt szabadul: az írás pillanatképpel megy, a külső változat kézi commitba kerül."""
        self._nyit()
        (self.v / self.RP).write_text("# Görög\n\nAz Obsidian közben ezt írta.\n", encoding="utf-8")
        lemez = vaultio.sha1((self.v / self.RP).read_bytes())
        self.V.kor_zar_varakozas_mp = 5
        fh = self._kor_zar()
        t = threading.Timer(0.3, lambda: fcntl.flock(fh, fcntl.LOCK_UN))
        t.start()
        self.addCleanup(t.cancel)
        r = self.V.write({"ut": self.RP, "tartalom": "# az enyém\n", "alap": lemez, "elso": True, "felulir": True})
        self.assertTrue(r["git"])
        self.assertIn("Az Obsidian közben", self.repo.git("show", f"{r['elotte']}:{self.RP}").stdout)
        self.assertEqual((self.v / self.RP).read_text(encoding="utf-8"), "# az enyém\n")

    def test_sima_mentes_foglalt_kor_zarnal_nem_var_es_nem_423(self):
        """`felulir` nélkül (sima szerkesztés) a 18. döntés áll: a mentés nem függ a git/kör-zár állapotától."""
        alap = self._nyit()
        self.V.kor_zar_varakozas_mp = 5
        self._kor_zar()
        t0 = time.monotonic()
        r = self.V.write({"ut": self.RP, "tartalom": "# Görög\n\nmenet közben\n", "alap": alap, "elso": True})
        self.assertLess(time.monotonic() - t0, 2)
        self.assertFalse(r["git"])
        self.assertEqual((self.v / self.RP).read_text(encoding="utf-8"), "# Görög\n\nmenet közben\n")

    def test_azonos_tartalom_elavult_alappal_nem_utkozes(self):
        """Idempotens mentés: az elveszett válasz utáni újraküldés (az `alap` már elavult, a tartalom a lemezen áll) no-op."""
        alap = self._nyit()
        r1 = self.V.write({"ut": self.RP, "tartalom": "# Görög\n\nÚj.\n", "alap": alap})
        r2 = self.V.write({"ut": self.RP, "tartalom": "# Görög\n\nÚj.\n", "alap": alap})      # az `alap` elavult
        self.assertEqual(r2["hash"], r1["hash"])
        self.assertEqual(r2["uzenet"], "nem változott")
        with self.assertRaises(vaultio.Conflict):                                              # más tartalommal továbbra is ütközés
            self.V.write({"ut": self.RP, "tartalom": "# Görög\n\nMás.\n", "alap": alap})


class Egyideju(Alap):
    """M4 (audit): két egyidejű mentés ugyanarra a fájlra — a közös tmp-név miatt az egyik `FileNotFoundError`-ral
    (500) állt meg. Most útvonalankénti zár és egyedi tmp-név: az egyik ment, a másik tisztán ütközik (409)."""

    def test_ket_egyideju_mentes(self):
        import threading
        for kor in range(25):
            alap = self._nyit()
            akadaly, eredmeny = threading.Barrier(2), []

            def ment(i):
                akadaly.wait()
                try:
                    self.V.write({"ut": self.RP, "tartalom": f"# Görög\n\n{kor}-{i}\n", "alap": alap})
                    eredmeny.append("ok")
                except vaultio.Conflict:
                    eredmeny.append("409")
                except Exception as e:  # noqa: BLE001
                    eredmeny.append(f"{type(e).__name__}: {e}")

            szalak = [threading.Thread(target=ment, args=(i,)) for i in range(2)]
            [t.start() for t in szalak]
            [t.join() for t in szalak]
            self.assertEqual(sorted(eredmeny), ["409", "ok"], f"{kor}. kör: {eredmeny}")
        self.assertFalse([p for p in self.v.rglob("*") if p.name.endswith(".manifold-tmp")])

    def test_hosszu_nev_tmp_neve_is_belefer(self):
        """L9: a tmp-név nem nőhet 255 bájt fölé (a `.<név>.manifold-tmp` egy 245 bájtos névnél túlnőtt)."""
        rp = "T01 - Történelem/" + "h" * 240 + ".md"
        ir(self.v, rp, "# hosszú\n")
        r = self.V.write({"ut": rp, "tartalom": "# hosszú\n\nmentve\n", "alap": self._nyit(rp)})
        self.assertTrue(r["ok"])
        self.assertEqual((self.v / rp).read_text(encoding="utf-8"), "# hosszú\n\nmentve\n")


class UjJegyzetTest(Alap):
    def test_uj_jegyzet_a_sema_szerint(self):
        r = self.V.create({"mappa": "T01 - Történelem", "nev": "05 - Másodfokú egyenlet"})
        self.assertEqual(r["ut"], "T01 - Történelem/05 - Másodfokú egyenlet.md")
        t = (self.v / r["ut"]).read_text(encoding="utf-8")
        self.assertEqual(t, "# Másodfokú egyenlet\n")
        self.assertEqual(self.repo.log(1)[0].trailers["Mos-Forras"], "pult-szerkeszto")
        with self.assertRaises(vaultio.Invalid):                # meglévőt nem ír felül (kis-nagybetű is)
            self.V.create({"mappa": "T01 - Történelem", "nev": "05 - másodfokú egyenlet"})
        self.assertEqual((self.v / r["ut"]).read_text(encoding="utf-8"), t)
        for rossz in ("", ".rejtett", "a/b", "kérdés?", "x#y", "[[x]]"):
            with self.assertRaises(vaultio.Invalid, msg=rossz):
                self.V.create({"mappa": "T01 - Történelem", "nev": rossz})
        with self.assertRaises(vaultio.NotFound):
            self.V.create({"mappa": "Nincs ilyen mappa", "nev": "x"})
        self.assertEqual(self.V.create({"nev": "Gyökérben"})["ut"], "Gyökérben.md")
        self.assertEqual((self.v / "Gyökérben.md").read_text(encoding="utf-8"), "# Gyökérben\n")


class LinkJegyzetTest(Alap):
    """C31 (2. audit T158): a feloldatlan link új jegyzetének helyét a core dönti, az Obsidian 1.14.4 szerint
    (`createNewMarkdownFileFromLinktext`; az út nélküli cél a vault `app.json` `newFileLocation`-je szerint)."""

    def uj(self, cel, forras="T01 - Történelem/Ókor.md"):
        return self.V.create({"link": {"cel": cel, "forras": forras}})["ut"]

    def app_json(self, adat: dict):
        ir(self.v, ".obsidian/app.json", json.dumps(adat))

    def test_utvonalas_cel_a_gyokerhez_kepest_kis_nagybetu_fuggetlen_mappaval(self):
        self.assertEqual(self.uj("t01 - TÖRTÉNELEM/Spárta"), "T01 - Történelem/Spárta.md")
        self.assertEqual(self.uj("/F02 - Fizika/Erő.md"), "F02 - Fizika/Erő.md")
        self.assertEqual((self.v / "F02 - Fizika/Erő.md").read_text(encoding="utf-8"), "# Erő\n")

    def test_hianyzo_mappa_letrejon(self):
        self.assertEqual(self.uj("Új tárgy/Alfejezet/Első"), "Új tárgy/Alfejezet/Első.md")
        self.assertTrue((self.v / "Új tárgy/Alfejezet/Első.md").is_file())
        self.assertEqual(self.uj("t01 - történelem/Új mappa/X"), "T01 - Történelem/Új mappa/X.md")

    def test_ut_nelkuli_cel_az_obsidian_alapja_szerint_a_gyokerbe(self):
        self.assertEqual(self.uj("Róma"), "Róma.md")                     # nincs newFileLocation: root
        r = self.V.create({"link": {"cel": "f02 - fizika/Szim.cpp", "forras": "T01 - Történelem/Ókor.md"}, "tipus": "cpp"})
        self.assertEqual(r["ut"], "F02 - Fizika/Szim.cpp")                # C36a-UI: a hiányzó `x.cpp` C++ forrás

    def test_ut_nelkuli_cel_a_new_file_location_szerint(self):
        self.app_json({"newFileLocation": "current"})
        self.assertEqual(self.uj("Róma"), "T01 - Történelem/Róma.md")
        self.app_json({"newFileLocation": "folder", "newFileFolderPath": "F02 - Fizika"})
        self.assertEqual(self.uj("Athén"), "F02 - Fizika/Athén.md")
        self.app_json({"newFileLocation": "folder", "newFileFolderPath": "Nincs ilyen"})
        self.assertEqual(self.uj("Párizs"), "Párizs.md")                 # a nem létező mappa: gyökér (Obsidian)

    def test_nem_jegyzet_cel_es_meglevo_hiba(self):
        for rossz in ("kep.png", "doc.pdf", "x.canvas", "", "  "):
            with self.assertRaises(vaultio.Invalid, msg=rossz):
                self.uj(rossz)
        with self.assertRaises(vaultio.Invalid):
            self.uj("t01 - történelem/görög")                            # meglévő (kis-nagybetűtől függetlenül)
        with self.assertRaises(vaultio.Invalid):
            self.V.create({"link": {"cel": "X"}, "mappa": "F02 - Fizika"})


class BaseIrasTest(Alap):
    """C12: az adatbázis-nézet (`.base`) ugyanazon az úton, ugyanazzal az ütközésvizsgálattal és pillanatképpel
    íródik, mint a jegyzet; a többi szöveges fájl (a `.canvas`-on kívül, C14) továbbra is csak olvasható."""
    BP = "T01 - Történelem/Olvasmányok.base"
    ALAP = "views:\n  - type: table\n    name: Táblázat\n"

    def setUp(self):
        super().setUp()
        ir(self.v, self.BP, self.ALAP)
        self.repo.commit("a base is bekerül", {"Mos-Forras": "kezi"})

    def test_olvasas_es_mentes_pillanatkeppel(self):
        r0 = self.V.read(self.BP)
        self.assertEqual((r0["tartalom"], r0["kodolas_hiba"]), (self.ALAP, False))
        uj = self.ALAP + "    limit: 5\n"
        r = self.V.write({"ut": self.BP, "tartalom": uj, "alap": r0["hash"], "elso": True})
        self.assertEqual((self.v / self.BP).read_text(encoding="utf-8"), uj)
        self.assertEqual(r["uzenet"], "mentve")
        r2 = self.V.write({"ut": self.BP, "tartalom": uj + "    imageFit: contain\n", "alap": r["hash"], "pillanat": True})
        c = self._commitok()[0]
        self.assertEqual(r2["pillanat"], c.sha)
        self.assertEqual((c.trailers["Mos-Forras"], c.trailers["Mos-Tetel"]), ("pult-szerkeszto", self.BP))
        self.assertIn("adatbázis-nézet szerkesztve", self.repo.git("log", "-1", "--format=%s").stdout)
        self.repo.undo_commit(c.sha)                           # egy kattintással visszavonható
        self.assertEqual((self.v / self.BP).read_text(encoding="utf-8"), self.ALAP)
        self.assertFalse(list(self.v.rglob("*.manifold-tmp")))
        self.assertEqual(self.esemenyek[-1]["ut"], self.BP)

    def test_utkozes_nem_ir_felul(self):
        h = self.V.read(self.BP)["hash"]
        (self.v / self.BP).write_text("views: []\n", encoding="utf-8")
        with self.assertRaises(vaultio.Conflict):
            self.V.write({"ut": self.BP, "tartalom": self.ALAP + "    limit: 1\n", "alap": h, "elso": True, "pillanat": True})
        self.assertEqual((self.v / self.BP).read_text(encoding="utf-8"), "views: []\n")

    def test_csak_a_md_a_base_es_a_canvas_irhato(self):
        for rp in ("T01 - Történelem/x.json", "T01 - Történelem/x.txt", "x.yaml"):
            with self.assertRaises(vaultio.Invalid, msg=rp):
                self.V.write({"ut": rp, "tartalom": "{}", "alap": "x"})
        r = self.V.write({"ut": self.BP, "tartalom": self.ALAP, "alap": self.V.read(self.BP)["hash"]})
        self.assertEqual(r["uzenet"], "nem változott")
        up = "T01 - Történelem/Nagy.BASE"
        ir(self.v, up, self.ALAP)
        self.assertTrue(self.V.write({"ut": up, "tartalom": self.ALAP + "    limit: 2\n", "alap": self.V.read(up)["hash"]})["ok"])

    def test_uj_base(self):
        r = self.V.create({"mappa": "T01 - Történelem", "nev": "Könyvek", "tipus": "base"})
        self.assertEqual(r["ut"], "T01 - Történelem/Könyvek.base")
        self.assertEqual((self.v / r["ut"]).read_text(encoding="utf-8"), vaultio.UJ_BASE)
        from core.bazis import modell
        self.assertEqual(vaultio.UJ_BASE, modell.UJ_SZOVEG)
        self.assertEqual(self.repo.log(1)[0].trailers["Mos-Forras"], "pult-szerkeszto")
        self.assertEqual(self.repo.changed_files(r["pillanat"]), [r["ut"]])
        self.assertEqual(self.V.create({"mappa": "T01 - Történelem", "nev": "Más.base", "tipus": "base"})["ut"],
                         "T01 - Történelem/Más.base")
        with self.assertRaises(vaultio.Invalid):                # meglévőt nem ír felül (kis-nagybetű is)
            self.V.create({"mappa": "T01 - Történelem", "nev": "könyvek", "tipus": "base"})
        # ugyanaz a név `.md`-ként más fájl
        self.assertEqual(self.V.create({"mappa": "T01 - Történelem", "nev": "Könyvek"})["ut"], "T01 - Történelem/Könyvek.md")
        for rossz in ("txt", "pdf", 5):
            with self.assertRaises(vaultio.Invalid, msg=rossz):
                self.V.create({"mappa": "T01 - Történelem", "nev": "x", "tipus": rossz})
        for nev in ("", ".rejtett", "a/b", "x#y"):
            with self.assertRaises(vaultio.Invalid, msg=nev):
                self.V.create({"mappa": "T01 - Történelem", "nev": nev, "tipus": "base"})


class CanvasIrasTest(Alap):
    """C14: a canvas ugyanazon az úton, ugyanazzal az ütközésvizsgálattal és pillanatképpel íródik, mint a
    jegyzet; érvénytelen JSON Canvas nem kerül a lemezre."""
    CP = "M03 - Algebra/M03.canvas"
    UJ = '{\n\t"nodes":[\n\t\t{"id":"a1","type":"text","text":"Ölelés","x":0,"y":0,"width":250,"height":60}\n\t],\n\t"edges":[]\n}'

    def test_mentes_pillanatkeppel_es_visszavonas(self):
        r0 = self.V.read(self.CP)
        r = self.V.write({"ut": self.CP, "tartalom": self.UJ, "alap": r0["hash"], "elso": True})
        self.assertEqual((self.v / self.CP).read_bytes(), self.UJ.encode("utf-8"))
        r2 = self.V.write({"ut": self.CP, "tartalom": self.UJ.replace('"x":0', '"x":20'), "alap": r["hash"],
                           "pillanat": True})
        c = self._commitok()[0]
        self.assertEqual(r2["pillanat"], c.sha)
        self.assertEqual((c.trailers["Mos-Forras"], c.trailers["Mos-Tetel"]), ("pult-szerkeszto", self.CP))
        self.assertIn("canvas szerkesztve a pultban", self.repo.git("log", "-1", "--format=%s").stdout)
        self.repo.undo_commit(c.sha)                           # a szerkesztés egésze egy lépésben vissza
        self.assertEqual((self.v / self.CP).read_bytes(), b"{}")
        self.assertFalse(list(self.v.rglob("*.manifold-tmp")))
        self.assertEqual(self.esemenyek[-1]["ut"], self.CP)

    def test_valtozatlan_tartalom_nem_ir(self):
        r = self.V.write({"ut": self.CP, "tartalom": "{}", "alap": self.V.read(self.CP)["hash"], "elso": True,
                          "pillanat": True})
        self.assertEqual(r["uzenet"], "nem változott")
        self.assertIsNone(r["pillanat"])

    def test_ervenytelen_json_nem_kerul_a_lemezre(self):
        h = self.V.read(self.CP)["hash"]
        for rossz in ('{"nodes":[', "[]", '{"nodes":[1]}', ""):
            with self.assertRaises(vaultio.Invalid, msg=rossz):
                self.V.write({"ut": self.CP, "tartalom": rossz, "alap": h})
        self.assertEqual((self.v / self.CP).read_bytes(), b"{}")
        self.assertFalse(list(self.v.rglob("*.manifold-tmp")))

    def test_utkozes_nem_ir_felul(self):
        h = self.V.read(self.CP)["hash"]
        (self.v / self.CP).write_text('{"nodes":[]}', encoding="utf-8")
        with self.assertRaises(vaultio.Conflict):
            self.V.write({"ut": self.CP, "tartalom": self.UJ, "alap": h, "elso": True, "pillanat": True})
        self.assertEqual((self.v / self.CP).read_text(encoding="utf-8"), '{"nodes":[]}')

    @csak_darwin("NFD-nevű fájl (a Linux fájlrendszere nem normalizál: az NFD és NFC név két külön fájl)")
    def test_nfd_nev_megmarad(self):
        nfd = unicodedata.normalize("NFD", "Ábrák.canvas")
        (self.v / "M03 - Algebra" / nfd).write_text("{}", encoding="utf-8")
        rp = "M03 - Algebra/Ábrák.canvas"
        self.V.write({"ut": rp, "tartalom": self.UJ, "alap": self.V.read(rp)["hash"]})
        nevek = os.listdir(self.v / "M03 - Algebra")
        self.assertIn(nfd, nevek)
        self.assertEqual((self.v / "M03 - Algebra" / nfd).read_text(encoding="utf-8"), self.UJ)

    def test_uj_canvas(self):
        r = self.V.create({"mappa": "M03 - Algebra", "nev": "Térkép", "tipus": "canvas"})
        self.assertEqual(r["ut"], "M03 - Algebra/Térkép.canvas")
        self.assertEqual((self.v / r["ut"]).read_bytes(), b"{}")
        self.assertIn("új canvas a pultban", self.repo.git("log", "-1", "--format=%s").stdout)
        self.assertEqual(self.repo.changed_files(r["pillanat"]), [r["ut"]])
        self.assertEqual(self.V.create({"mappa": "M03 - Algebra", "nev": "Más.canvas", "tipus": "canvas"})["ut"],
                         "M03 - Algebra/Más.canvas")
        with self.assertRaises(vaultio.Invalid):
            self.V.create({"mappa": "M03 - Algebra", "nev": "térkép", "tipus": "canvas"})


class CppIrasTest(Alap):
    """C36a: a C++ megoldás (`.cpp`) ugyanazon az úton, ugyanazzal az ütközésvizsgálattal és pillanatképpel olvasható és íródik, mint
    a jegyzet. A gépi írás kapuja (`SZOVEGES`) nem bővül: gép `.cpp`-t nem ír (a C36b javaslata a szerkesztőn át megy)."""
    CP = "D08 - Algo/Összeg.cpp"
    ALAP = "int main() {\n    return 0;\n}\n"

    def setUp(self):
        super().setUp()
        ir(self.v, self.CP, self.ALAP)
        self.repo.commit("a cpp is bekerül", {"Mos-Forras": "kezi"})

    def test_olvasas_es_mentes_pillanatkeppel(self):
        r0 = self.V.read(self.CP)
        self.assertEqual((r0["tartalom"], r0["kodolas_hiba"]), (self.ALAP, False))
        uj = self.ALAP.replace("0", "1")
        r = self.V.write({"ut": self.CP, "tartalom": uj, "alap": r0["hash"], "elso": True})
        self.assertEqual((self.v / self.CP).read_text(encoding="utf-8"), uj)
        self.assertEqual(r["uzenet"], "mentve")
        r2 = self.V.write({"ut": self.CP, "tartalom": uj + "// vége\n", "alap": r["hash"], "pillanat": True})
        c = self._commitok()[0]
        self.assertEqual(r2["pillanat"], c.sha)
        self.assertEqual((c.trailers["Mos-Forras"], c.trailers["Mos-Tetel"]), ("pult-szerkeszto", self.CP))
        self.assertIn("C++ forrás szerkesztve", self.repo.git("log", "-1", "--format=%s").stdout)
        self.repo.undo_commit(c.sha)                           # egy kattintással visszavonható: a szerkesztés előtti állapot
        self.assertEqual((self.v / self.CP).read_text(encoding="utf-8"), self.ALAP)
        self.assertFalse(list(self.v.rglob("*.manifold-tmp")))
        self.assertEqual(self.esemenyek[-1]["ut"], self.CP)

    def test_utkozes_nem_ir_felul(self):
        h = self.V.read(self.CP)["hash"]
        (self.v / self.CP).write_text("// külső\n", encoding="utf-8")
        with self.assertRaises(vaultio.Conflict):
            self.V.write({"ut": self.CP, "tartalom": self.ALAP + "//\n", "alap": h, "elso": True, "pillanat": True})
        self.assertEqual((self.v / self.CP).read_text(encoding="utf-8"), "// külső\n")

    def test_a_crlf_es_a_nagybetus_kiterjesztes(self):
        crlf = "T01 - Történelem/Crlf.cpp"
        (self.v / crlf).write_bytes(b"int main() {\r\n}\r\n")
        r0 = self.V.read(crlf)
        self.V.write({"ut": crlf, "tartalom": "int main() {\n    return 0;\n}\n", "alap": r0["hash"]})
        self.assertEqual((self.v / crlf).read_bytes(), b"int main() {\r\n    return 0;\r\n}\r\n")
        nagy = "T01 - Történelem/Nagy.CPP"
        ir(self.v, nagy, self.ALAP)
        self.assertTrue(self.V.write({"ut": nagy, "tartalom": self.ALAP + "//\n", "alap": self.V.read(nagy)["hash"]})["ok"])

    def test_nem_utf8_cpp_csak_olvashato_jelzessel(self):
        rossz = "T01 - Történelem/Rossz.cpp"
        (self.v / rossz).write_bytes(b"// \xff\xfe\nint x;\n")
        self.assertTrue(self.V.read(rossz)["kodolas_hiba"])

    def test_a_tobbi_forraskod_tovabbra_sem_olvashato_sem_irhato(self):
        for rp in ("T01 - Történelem/x.h", "T01 - Történelem/x.hpp", "T01 - Történelem/x.c", "T01 - Történelem/x.py"):
            ir(self.v, rp, "x")
            with self.assertRaises(vaultio.Invalid, msg=rp):
                self.V.read(rp)
            with self.assertRaises(vaultio.Invalid, msg=rp):
                self.V.write({"ut": rp, "tartalom": "y", "alap": "x"})

    def test_a_gepi_iras_kapuja_nem_bovul(self):
        self.assertNotIn(".cpp", vaultio.SZOVEGES)
        self.assertIn(".cpp", vaultio.IRHATO)
        self.assertIn(".cpp", vaultio.OLVASHATO)

    def test_uj_cpp(self):
        from core import cpp_teszt
        r = self.V.create({"mappa": "T01 - Történelem", "nev": "Másolat", "tipus": "cpp"})
        self.assertEqual(r["ut"], "T01 - Történelem/Másolat.cpp")
        self.assertEqual((self.v / r["ut"]).read_text(encoding="utf-8"), cpp_teszt.cpp_vaz())
        self.assertEqual(self.repo.log(1)[0].trailers["Mos-Forras"], "pult-szerkeszto")
        self.assertIn("új C++ forrás", self.repo.git("log", "-1", "--format=%s").stdout)
        self.assertEqual(self.repo.changed_files(r["pillanat"]), [r["ut"]])
        self.assertEqual(self.V.create({"mappa": "T01 - Történelem", "nev": "Más.cpp", "tipus": "cpp"})["ut"],
                         "T01 - Történelem/Más.cpp")                       # a név végi `.cpp` levágódik
        with self.assertRaises(vaultio.Invalid):                           # meglévőt nem ír felül (kis-nagybetű is)
            self.V.create({"mappa": "T01 - Történelem", "nev": "másolat", "tipus": "cpp"})
        # ugyanaz a név `.md`-ként más fájl: a jegyzet és a megoldása azonos nevű
        self.assertEqual(self.V.create({"mappa": "T01 - Történelem", "nev": "Másolat"})["ut"], "T01 - Történelem/Másolat.md")

    def test_uj_cpp_tartalommal_a_tartalom_csak_md_vagy_cpp(self):
        r = self.V.create({"mappa": "T01 - Történelem", "nev": "Sajat", "tipus": "cpp", "tartalom": "int x;\n"})
        self.assertEqual((self.v / r["ut"]).read_text(encoding="utf-8"), "int x;\n")
        for tipus in ("base", "canvas"):
            with self.assertRaises(vaultio.Invalid, msg=tipus):
                self.V.create({"mappa": "T01 - Történelem", "nev": "X" + tipus, "tipus": tipus, "tartalom": "x"})

    def test_a_tipus_hibauzenete_a_cpp_t_is_nevezi(self):
        with self.assertRaises(vaultio.Invalid) as cm:
            self.V.create({"mappa": "T01 - Történelem", "nev": "x", "tipus": "py"})
        self.assertIn("cpp", str(cm.exception))

    def test_az_irhato_fajlok_hibauzenete_a_cpp_t_is_nevezi(self):
        with self.assertRaises(vaultio.Invalid) as cm:
            self.V.write({"ut": "x.json", "tartalom": "{}", "alap": "x"})
        self.assertIn(".cpp", str(cm.exception))

    def test_a_nagy_cpp_nem_toltheto_be(self):
        nagy = "T01 - Történelem/Nagy.cpp"
        (self.v / nagy).write_bytes(b"x" * (vaultio.MAX_SZOVEG + 1))
        with self.assertRaises(vaultio.Invalid):
            self.V.read(nagy)


class HttpTest(Alap):
    """A 409 HTTP-n (a legacy `test_mentes_utkozes_409` portja), a core alfolyamatként az álgyökéren."""

    def setUp(self):
        super().setUp()
        self.p = subprocess.Popen([sys.executable, "-B", "-m", "core", "start"], cwd=REPO, stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, env=env(MOS_ROOT=str(self.root), PYTHONPATH=str(REPO),
                                                                  HOME=str(self.root.parent / "home")))
        self.addCleanup(lambda: (self.p.kill(), self.p.wait()) if self.p.poll() is None else None)
        self.addCleanup(lambda: [f.close() for f in (self.p.stdout, self.p.stdin) if not f.closed])
        self.port = json.loads(self.p.stdout.readline())["port"]

    def _k(self, method, path, body=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request(method, path, body=json.dumps(body) if body is not None else None,
                  headers={"Host": f"127.0.0.1:{self.port}", "X-Manifold": API_TITOK, "Content-Type": "application/json"})
        r = c.getresponse()
        return r.status, json.loads(r.read())

    def test_mentes_utkozes_409(self):
        rp = "T01 - Történelem/Görög.md"
        kod, d = self._k("GET", "/api/vault/fajl?ut=" + urllib.parse.quote(rp))
        self.assertEqual(kod, 200)
        alap = d["hash"]
        (self.v / rp).write_text("# kívülről\n", encoding="utf-8")
        kod, d = self._k("PUT", "/api/vault/fajl", {"ut": rp, "tartalom": "# enyém\n", "alap": alap})
        self.assertEqual(kod, 409)
        self.assertTrue(d["utkozes"])
        self.assertEqual(d["hash"], vaultio.sha1("# kívülről\n".encode()))
        self.assertEqual((self.v / rp).read_text(encoding="utf-8"), "# kívülről\n")
        kod, d = self._k("PUT", "/api/vault/fajl", {"ut": rp, "tartalom": "# enyém\n", "alap": d["hash"],
                                                      "elso": True, "pillanat": True})
        self.assertEqual((kod, (self.v / rp).read_text(encoding="utf-8")), (200, "# enyém\n"))
        # visszavonás HTTP-n: bájtra vissza
        kod, u = self._k("POST", "/api/pillanat/vault/visszavonas", {"sha": d["pillanat"]})
        self.assertEqual(kod, 200, u)
        self.assertEqual((self.v / rp).read_text(encoding="utf-8"), "# kívülről\n")
        kod, u = self._k("POST", "/api/pillanat/vault/visszavonas", {"kor": "KOR-20260924-074608-proba"})
        self.assertEqual(kod, 400)
        kod, n = self._k("GET", "/api/pillanat/vault/naplo?n=3")
        self.assertEqual(n["commitok"][0]["trailerek"]["Mos-Visszavon"], d["pillanat"])
        self.assertEqual(self._k("GET", "/api/vault/fajl?ut=nincs.md")[0], 404)
        self.assertEqual(self._k("GET", "/api/vault/fajl?ut=../x.md")[0], 400)

    def test_felulir_foglalt_kor_zarnal_423_http(self):
        """T116 (C29.7b): a kör-zárat egy másik folyamat tartja → az ütközés-felülírás 423 `foglalt`, a fájl érintetlen."""
        kod, d = self._k("GET", "/api/vault/fajl?ut=" + urllib.parse.quote(self.RP))
        (self.v / self.RP).write_text("# kívülről\n", encoding="utf-8")
        lemez = vaultio.sha1((self.v / self.RP).read_bytes())
        lock = self.cfg.path("run") / "kor.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        with open(lock, "a+") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            kod, h = self._k("PUT", "/api/vault/fajl", {"ut": self.RP, "tartalom": "# enyém\n", "alap": lemez,
                                                          "elso": True, "felulir": True})
            self.assertEqual((kod, h.get("foglalt")), (423, True), h)
            self.assertEqual((self.v / self.RP).read_text(encoding="utf-8"), "# kívülről\n")
            fcntl.flock(fh, fcntl.LOCK_UN)
        kod, h = self._k("PUT", "/api/vault/fajl", {"ut": self.RP, "tartalom": "# enyém\n", "alap": lemez,
                                                      "elso": True, "felulir": True})
        self.assertEqual(kod, 200, h)

    def test_visszavonas_utkozes_409(self):
        alap = self._k("GET", "/api/vault/fajl?ut=" + urllib.parse.quote(self.RP))[1]["hash"]
        d = self._k("PUT", "/api/vault/fajl", {"ut": self.RP, "tartalom": "# gépi\n", "alap": alap, "pillanat": True})[1]
        (self.v / self.RP).write_text("# a gazda felülírta\n", encoding="utf-8")
        self.repo.commit("kézi", {"Mos-Forras": "kezi"})
        kod, u = self._k("POST", "/api/pillanat/vault/visszavonas", {"sha": d["pillanat"]})
        self.assertEqual(kod, 409)
        self.assertIn(self.RP, u["fajlok"])
        self.assertEqual((self.v / self.RP).read_text(encoding="utf-8"), "# a gazda felülírta\n")


if __name__ == "__main__":
    unittest.main()
