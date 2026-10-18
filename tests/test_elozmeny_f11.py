"""F11 / 13-palette-04, -05, -06: a jegyzet-előzmények lapozása és konfigurálható plafonja, a törölt jegyzetek visszahozása, és az
előzmény a `.canvas` / `.base` fájloknak is. Szintetikus vault temp könyvtárban; a visszaállítás a meglévő pillanatkép-szolgáltatáson
megy (új commit, `git revert`-jellegű visszavonás — reset/clean soha)."""
import json
import os
import unittest

from core import elozmeny, snapshot, utvonalak, vaultio
from core.utvonalak import HttpError
from tests.helpers import alg_core, ir, tmpdir


class Alap(unittest.TestCase):
    def setUp(self):
        self._tmp = tmpdir()
        self.addCleanup(self._tmp.cleanup)
        self.cfg, self.root, self.vault = alg_core(self._tmp.name)
        self.repo = snapshot.repos(self.cfg)["vault"]
        self.repo.init()
        self.jelek = []
        self.e = elozmeny.Elozmeny(self.cfg, jelez=self.jelek.append)

    def pillanat(self, szoveg, ut="J.md", kor="SZERK-20261002-100000"):
        if isinstance(szoveg, bytes):
            ir(self.vault, ut, szoveg, "wb")
        else:
            ir(self.vault, ut, szoveg)
        return self.repo.commit_machine(f"szerk {ut}", {"Mos-Kor": kor, "Mos-Tetel": ut, "Mos-Forras": "pult-szerkeszto"}, [ut])

    def torol(self, ut):
        os.remove(self.vault / ut)
        return self.repo.commit_machine(f"törölve {ut}", {"Mos-Kor": "KOR-20261002-110000", "Mos-Tetel": ut}, [ut])

    def olvas(self, ut="J.md"):
        return (self.vault / ut).read_bytes()

    def beallit(self, **kv):
        self.cfg.data.setdefault("elozmeny", {}).update(kv)


class Lapozas(Alap):
    def setUp(self):
        super().setUp()
        self.beallit(lap=25)
        self.shak = [self.pillanat(f"v{i}\n") for i in range(60)]       # a legrégebbi az első

    def test_lapok_kurzorral_a_teljes_tortenet_pontosan_egyszer(self):
        l1 = self.e.naplo("J.md")
        self.assertEqual((len(l1["bejegyzesek"]), l1["lap"], l1["tovabb"]), (25, 25, True))
        self.assertEqual(l1["kovetkezo"], l1["bejegyzesek"][-1]["sha"])
        l2 = self.e.naplo("J.md", elotte=l1["kovetkezo"])
        l3 = self.e.naplo("J.md", elotte=l2["kovetkezo"])
        self.assertEqual((len(l2["bejegyzesek"]), l2["tovabb"], len(l3["bejegyzesek"]), l3["tovabb"], l3["kovetkezo"]),
                         (25, True, 10, False, None))
        minden = [b["sha"] for l in (l1, l2, l3) for b in l["bejegyzesek"]]
        self.assertEqual(minden, list(reversed(self.shak)))
        self.assertEqual(len(set(minden)), 60)
        # a lap utolsó eleme a következő lap első elemét kapja „előzőnek” (a diff-hez), a legrégebbi a hozzáadás
        self.assertEqual(l1["bejegyzesek"][-1]["elozo"]["sha"], l2["bejegyzesek"][0]["sha"])
        self.assertEqual((l3["bejegyzesek"][-1]["statusz"], l3["bejegyzesek"][-1]["elozo"]), ("A", None))
        # csak a legelső lap legelső eleme a jelenlegi változat
        self.assertEqual([b["visszaallithato"] for b in l1["bejegyzesek"][:2]], [False, True])
        self.assertTrue(l2["bejegyzesek"][0]["visszaallithato"])

    def test_a_lapmeret_es_a_plafon_konfiguralhato(self):
        self.beallit(lap=7, lap_max=12)
        l = self.e.naplo("J.md")
        self.assertEqual((len(l["bejegyzesek"]), l["lap"]), (7, 7))
        self.assertEqual(len(self.e.naplo("J.md", n=500)["bejegyzesek"]), 12, "a kért n a lap_max-ra vágódik")
        self.assertEqual(len(self.e.naplo("J.md", n=3)["bejegyzesek"]), 3)
        self.beallit(lap="rossz", lap_max=-1)
        self.assertEqual(len(self.e.naplo("J.md")["bejegyzesek"]), 50, "érvénytelen beállítás az alapra esik")
        self.assertEqual(len(self.e.naplo("J.md", n=500)["bejegyzesek"]), 60, "a plafon alapja 200: az összes (60) belefér")

    def test_hibas_es_idegen_kurzor(self):
        for rossz, kod in (("nem-sha", 400), ("0" * 40, 404)):
            with self.assertRaises(HttpError, msg=rossz) as c:
                self.e.naplo("J.md", elotte=rossz)
            self.assertEqual(c.exception.code, kod)
        self.pillanat("m\n", ut="M.md")
        idegen = self.e.naplo("M.md")["bejegyzesek"][0]["sha"]
        with self.assertRaises(HttpError) as c:
            self.e.naplo("J.md", elotte=idegen)
        self.assertEqual(c.exception.code, 404)

    def test_a_kezdo_ablakon_tuli_valtozat_is_elerheto_es_visszaallithato(self):
        """Az eddigi fix 200-as ablak helyett a keresés a plafonig bővül: a kis kezdő ablakon (8) kívüli változat diffje és
        visszaállítása is megy."""
        elozo, elozmeny.KEZDO_ABLAK = elozmeny.KEZDO_ABLAK, 8
        self.addCleanup(setattr, elozmeny, "KEZDO_ABLAK", elozo)
        for i in range(20):
            self.pillanat(f"u{i}\n")
        legregebbi = self.shak[0]
        v = self.e.valtozat("J.md", legregebbi)
        self.assertEqual((v["szoveg"], v["elozo"], v["elozo_ok"]), ("v0\n", None, "nincs"))
        kozepso = self.shak[10]
        self.assertEqual(self.e.valtozat("J.md", kozepso)["elozo"], "v9\n")
        r = self.e.visszaallit("J.md", kozepso)
        self.assertTrue(r["ok"])
        self.assertEqual(self.olvas(), b"v10\n")
        self.assertEqual(self.repo.dirty(), [])

    def test_a_melyseg_plafon_vedi_a_keresest(self):
        self.beallit(max_melyseg=20)
        with self.assertRaises(HttpError) as c:
            self.e.valtozat("J.md", self.shak[0])
        self.assertEqual(c.exception.code, 404)
        self.assertEqual(self.e.valtozat("J.md", self.shak[-3])["szoveg"], "v57\n")


class Torolt(Alap):
    def test_torolt_lista_visszahozas_eredeti_helyre_bajtra_pontosan(self):
        self.pillanat("egy\r\nsor\r\n", ut="Mappa/Jegyzet.md")
        utolso = self.pillanat("kettő\r\nsor\r\n", ut="Mappa/Jegyzet.md")
        torles = self.torol("Mappa/Jegyzet.md")
        t = self.e.torolt()
        self.assertEqual([(x["ut"], x["sha"], x["ut_van"]) for x in t["torolt"]], [("Mappa/Jegyzet.md", torles, False)])
        v = self.e.torolt_valtozat("Mappa/Jegyzet.md", torles)
        self.assertEqual((v["szoveg"], v["szoveg_ok"]), ("kettő\r\nsor\r\n", None))
        r = self.e.visszahoz("Mappa/Jegyzet.md", torles)
        self.assertEqual((r["ok"], r["ut"], r["uj_nev"]), (True, "Mappa/Jegyzet.md", False))
        self.assertEqual(self.olvas("Mappa/Jegyzet.md"), b"k" + "ettő".encode() + b"\r\nsor\r\n")
        log = self.repo.log(1)[0]
        self.assertEqual((log.sha, log.trailers["Mos-Forras"], log.trailers["Mos-Visszaallit"], log.trailers["Mos-Tetel"]),
                         (r["sha"], "pult-elozmeny", torles, "Mappa/Jegyzet.md"))
        self.assertEqual(self.repo.dirty(), [])
        self.assertEqual(self.jelek[-1], ["Mappa/Jegyzet.md"])
        self.assertEqual(self.e.torolt()["torolt"], [], "a visszahozott fájl már nem törölt")
        self.assertEqual(self.e.naplo("Mappa/Jegyzet.md")["bejegyzesek"][0]["tipus"], "visszaallitas")
        # maga is visszavonható (a git-revert útvonal: nincs reset/clean)
        self.repo.undo_commit(r["sha"])
        self.assertFalse((self.vault / "Mappa/Jegyzet.md").exists())
        self.assertEqual([x["ut"] for x in self.e.torolt()["torolt"]], ["Mappa/Jegyzet.md"])
        self.assertTrue(utolso)

    def test_utkozes_az_eredeti_helyen_409_es_semmi_nem_iroodik(self):
        self.pillanat("régi\n")
        torles = self.torol("J.md")
        ir(self.vault, "J.md", "új, idegen tartalom\n")
        t = self.e.torolt()["torolt"]
        self.assertEqual([(x["ut"], x["ut_van"]) for x in t], [("J.md", True)])
        elotte = self.repo.log(1)[0].sha
        with self.assertRaises(HttpError) as c:
            self.e.visszahoz("J.md", torles)
        self.assertEqual((c.exception.code, c.exception.kod), (409, "elozmeny.visszahoz_utkozes"))
        self.assertEqual(self.olvas(), "új, idegen tartalom\n".encode())
        self.assertEqual(self.repo.log(1)[0].sha, elotte)

    def test_utkozes_kis_nagybetu_es_normalizalas_nelkul_is_eszlelve(self):
        self.pillanat("régi\n", ut="Jegyzet.md")
        torles = self.torol("Jegyzet.md")
        ir(self.vault, "jegyzet.md", "másik\n")                  # csak a kis-nagybetű különbözik
        with self.assertRaises(HttpError) as c:
            self.e.visszahoz("Jegyzet.md", torles)
        self.assertEqual(c.exception.code, 409)

    def test_uj_nev_utkozesmentes_es_validalt(self):
        self.pillanat("régi\n")
        torles = self.torol("J.md")
        ir(self.vault, "J.md", "idegen\n")
        r1 = self.e.visszahoz("J.md", torles, "uj")
        self.assertEqual(r1["ut"], "J (visszaállítva).md")
        self.assertTrue(r1["uj_nev"])
        self.assertEqual(self.olvas("J (visszaállítva).md"), "régi\n".encode())
        self.assertEqual(self.olvas("J.md"), b"idegen\n")
        # az idegen J.md a visszaállítás előtti kézi commitba került: a régi törlés már nem „törölt” bejegyzés
        self.assertEqual(self.e.torolt()["torolt"], [])

    def test_uj_nev_sorszamozott_es_megadott_nev(self):
        self.pillanat("régi\n")
        torles = self.torol("J.md")
        ir(self.vault, "J (visszaállítva).md", "foglalt\n")
        r = self.e.visszahoz("J.md", torles, "uj")
        self.assertEqual(r["ut"], "J (visszaállítva) 2.md")
        self.assertEqual(self.olvas("J (visszaállítva) 2.md"), "régi\n".encode())
        self.assertEqual(self.olvas("J (visszaállítva).md"), "foglalt\n".encode())
        torles2 = self.torol("J (visszaállítva) 2.md")
        r3 = self.e.visszahoz("J (visszaállítva) 2.md", torles2, "uj", "Saját név.md")
        self.assertEqual(r3["ut"], "Saját név.md")
        torles3 = self.torol("Saját név.md")
        for rossz in ("../x", "a/b", "ké#p", ".rejtett", "", "a:b", "x" * 300):
            with self.assertRaises(HttpError, msg=rossz) as c:
                self.e.visszahoz("Saját név.md", torles3, "uj", rossz)
            self.assertEqual(c.exception.code, 400, rossz)

    def test_hianyzo_mappa_ujra_letrejon(self):
        self.pillanat("tartalom\n", ut="Egy/Ketto/J.md")
        torles = self.torol("Egy/Ketto/J.md")
        os.rmdir(self.vault / "Egy" / "Ketto")
        os.rmdir(self.vault / "Egy")
        self.e.visszahoz("Egy/Ketto/J.md", torles)
        self.assertEqual(self.olvas("Egy/Ketto/J.md"), b"tartalom\n")

    def test_atnevezes_nem_torles_es_az_ujra_letrehozott_nem_szerepel(self):
        self.pillanat("a\n", ut="Regi.md")
        os.rename(self.vault / "Regi.md", self.vault / "Uj.md")
        self.repo.commit_machine("átnevezve", {"Mos-Kor": "ATNEV-20261002-120000", "Mos-Tetel": "Uj.md"}, ["Regi.md", "Uj.md"])
        self.pillanat("b\n", ut="Ujra.md")
        self.torol("Ujra.md")
        self.pillanat("c\n", ut="Ujra.md")
        self.assertEqual(self.e.torolt()["torolt"], [])

    def test_csak_irhato_tipusok_es_szuro_es_sorrend(self):
        self.pillanat("a\n", ut="Árvíz terv.md")
        self.pillanat("nyers\n", ut="Szoveg.txt")
        self.pillanat("x\n", ut="Tabla.base")
        self.pillanat("b\n", ut="Mas.md")
        t_arviz, t_png, t_base, t_mas = (self.torol(u) for u in ("Árvíz terv.md", "Szoveg.txt", "Tabla.base", "Mas.md"))
        self.assertEqual([x["ut"] for x in self.e.torolt()["torolt"]], ["Mas.md", "Tabla.base", "Árvíz terv.md"])
        self.assertEqual([x["ut"] for x in self.e.torolt("arviz TERV")["torolt"]], ["Árvíz terv.md"])
        self.assertEqual(len(self.e.torolt(n=2)["torolt"]), 2)
        with self.assertRaises(HttpError) as c:
            self.e.visszahoz("Szoveg.txt", t_png)
        self.assertEqual(c.exception.code, 400)
        self.assertTrue(t_arviz and t_base and t_mas)

    def test_idegen_vagy_hibas_sha_es_ut(self):
        self.pillanat("a\n")
        torles = self.torol("J.md")
        for ut, sha, kod in (("J.md", "abc", 400), ("J.md", "0" * 40, 404), ("M.md", torles, 404)):
            with self.assertRaises(HttpError, msg=(ut, sha)) as c:
                self.e.visszahoz(ut, sha)
            self.assertEqual(c.exception.code, kod, (ut, sha))
        for ut in ("../kulso.md", ".obsidian/x.md", "/abs/utvonal.md"):         # a vault közös út-szűrője (`norm_path`)
            with self.assertRaises((HttpError, vaultio.Invalid), msg=ut):
                self.e.visszahoz(ut, torles)
        self.assertFalse((self.vault / "J.md").exists())

    def test_foglalt_vault_iro_409_es_nem_valtoztat(self):
        self.pillanat("a\n")
        torles = self.torol("J.md")
        e = elozmeny.Elozmeny(self.cfg, busy=lambda: True)
        with self.assertRaises(HttpError) as c:
            e.visszahoz("J.md", torles)
        self.assertEqual(c.exception.code, 409)
        self.assertFalse((self.vault / "J.md").exists())

    def test_commit_hiba_eseten_a_most_irt_fajl_nem_marad(self):
        self.pillanat("a\n")
        torles = self.torol("J.md")
        eredeti = snapshot.Repo.commit_machine

        def hibas(repo, *a, **k):
            raise snapshot.SnapshotError("[vault] git commit: elakadt index.lock")

        snapshot.Repo.commit_machine = hibas
        self.addCleanup(setattr, snapshot.Repo, "commit_machine", eredeti)
        with self.assertRaises(HttpError) as c:
            self.e.visszahoz("J.md", torles)
        self.assertEqual(c.exception.code, 400)
        self.assertFalse((self.vault / "J.md").exists())


class CanvasEsBase(Alap):
    CANVAS_1 = json.dumps({"nodes": [{"id": "a", "type": "text", "text": "egy", "x": 0, "y": 0, "width": 200, "height": 80}], "edges": []}, indent="\t")
    CANVAS_2 = json.dumps({"nodes": [{"id": "a", "type": "text", "text": "kettő", "x": 40, "y": 0, "width": 200, "height": 80}], "edges": []}, indent="\t")
    BASE_1 = 'filters:\n  and:\n    - file.hasTag("start")\r\nviews:\n  - type: table\n    name: All\n'

    def test_canvas_naplo_diff_szoveg_es_bajtra_pontos_visszaallitas(self):
        elso = self.pillanat(self.CANVAS_1, ut="Tabla.canvas")
        self.pillanat(self.CANVAS_2, ut="Tabla.canvas")
        n = self.e.naplo("Tabla.canvas")
        self.assertEqual([b["statusz"] for b in n["bejegyzesek"]], ["M", "A"])
        v = self.e.valtozat("Tabla.canvas", elso)
        self.assertEqual((v["szoveg"], v["szoveg_ok"]), (self.CANVAS_1, None))
        self.assertEqual(json.loads(v["szoveg"])["nodes"][0]["text"], "egy")
        self.e.visszaallit("Tabla.canvas", elso)
        self.assertEqual(self.olvas("Tabla.canvas"), self.CANVAS_1.encode())
        self.assertEqual(self.jelek[-1], ["Tabla.canvas"])
        self.assertEqual(self.repo.dirty(), [])

    def test_base_crlf_es_utf8_bajtra_marad(self):
        elso = self.pillanat(self.BASE_1.encode(), ut="Lista.base")
        self.pillanat("filters: {}\n", ut="Lista.base")
        self.e.visszaallit("Lista.base", elso)
        self.assertEqual(self.olvas("Lista.base"), self.BASE_1.encode())
        self.assertEqual(self.e.naplo("Lista.base")["bejegyzesek"][0]["tipus"], "visszaallitas")

    def test_torolt_canvas_es_base_visszahozhato(self):
        self.pillanat(self.CANVAS_2, ut="Tabla.canvas")
        self.pillanat(self.BASE_1.encode(), ut="Lista.base")
        tc, tb = self.torol("Tabla.canvas"), self.torol("Lista.base")
        self.assertEqual({x["ut"] for x in self.e.torolt()["torolt"]}, {"Tabla.canvas", "Lista.base"})
        self.e.visszahoz("Tabla.canvas", tc)
        self.e.visszahoz("Lista.base", tb)
        self.assertEqual(self.olvas("Tabla.canvas"), self.CANVAS_2.encode())
        self.assertEqual(self.olvas("Lista.base"), self.BASE_1.encode())


class Vegpontok(Alap):
    def test_a_vegpontok_regisztraltak(self):
        r = utvonalak.Regiszter()
        elozmeny.utvonalak(r)
        for m, ut in (("GET", "/api/vault/elozmeny"), ("GET", "/api/vault/elozmeny/valtozat"), ("POST", "/api/vault/elozmeny/visszaallit"),
                      ("GET", "/api/vault/elozmeny/torolt"), ("GET", "/api/vault/elozmeny/torolt/valtozat"),
                      ("POST", "/api/vault/elozmeny/visszahoz")):
            self.assertIsNotNone(r.keres(m, ut), (m, ut))


if __name__ == "__main__":
    unittest.main()
