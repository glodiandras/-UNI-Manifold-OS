"""Jegyzetenkénti előzmények (C11b): a fájl naplója az átnevezéseket követve, a változat szövege a diffhez, és a
visszaállítás egy verzióra revert-commitként (bájtra azonos eredmény, visszavonható, foglalt zárnál 409)."""
import os
import unicodedata
import unittest

from core import elozmeny, frame, snapshot
from core.utvonalak import HttpError
from tests import csak_darwin
from tests.helpers import alg_core, ir, tmpdir


class Alap(unittest.TestCase):
    def setUp(self):
        self._tmp = tmpdir()
        self.addCleanup(self._tmp.cleanup)
        self.cfg, self.root, self.vault = alg_core(self._tmp.name)
        self.repo = snapshot.repos(self.cfg)["vault"]
        self.repo.init()
        self.e = elozmeny.Elozmeny(self.cfg)

    def pillanat(self, szoveg, ut="J.md", kor="SZERK-20261002-100000", uzenet="szerk"):
        ir(self.vault, ut, szoveg)
        return self.repo.commit_machine(uzenet, {"Mos-Kor": kor, "Mos-Tetel": ut, "Mos-Forras": "pult-szerkeszto"}, [ut])

    def olvas(self, ut="J.md"):
        return (self.vault / ut).read_bytes()


class Naplo(Alap):
    def test_lista_legujabb_elol_cimkekkel(self):
        self.pillanat("egy\n", kor="SZERK-20261002-100000")
        ir(self.vault, "J.md", "kettő kézzel\n")
        self.repo.commit("kézi változások a szerkesztés előtt", {"Mos-Forras": "kezi"})
        self.pillanat("három\n", kor="FUZET-20261002-110000")
        n = self.e.naplo("J.md")
        self.assertEqual([b["tipus"] for b in n["bejegyzesek"]], ["fuzet", "kezi", "szerk"])
        self.assertEqual(n["bejegyzesek"][1]["cimke"], "Kézi változás (Obsidian, Finder, …)")
        self.assertEqual(n["bejegyzesek"][0]["kor"], "FUZET-20261002-110000")
        self.assertEqual(n["bejegyzesek"][0]["elozo"]["sha"], n["bejegyzesek"][1]["sha"])
        self.assertIsNone(n["bejegyzesek"][-1]["elozo"])
        self.assertEqual(n["bejegyzesek"][-1]["statusz"], "A")

    def test_mas_jegyzet_commitja_nem_szerepel(self):
        self.pillanat("a\n", ut="J.md")
        self.pillanat("b\n", ut="M.md")
        self.assertEqual(len(self.e.naplo("J.md")["bejegyzesek"]), 1)

    def test_atnevezest_koveti(self):
        self.pillanat("egy\n", ut="Regi.md")
        os.rename(self.vault / "Regi.md", self.vault / "Uj.md")
        self.repo.commit_machine("átnevezve", {"Mos-Kor": "ATNEV-20261002-120000", "Mos-Tetel": "Uj.md"}, ["Regi.md", "Uj.md"])
        self.pillanat("kettő\n", ut="Uj.md", kor="SZERK-20261002-130000")
        b = self.e.naplo("Uj.md")["bejegyzesek"]
        self.assertEqual([(x["statusz"], x["ut_akkor"]) for x in b], [("M", "Uj.md"), ("R", "Uj.md"), ("A", "Regi.md")])
        self.assertEqual(b[1]["regi_ut"], "Regi.md")
        self.assertEqual(b[1]["tipus"], "atnev")
        self.assertEqual([x["visszaallithato"] for x in b], [False, True, True])    # 39. döntés: a régi néven álló is

    def test_visszavonas_es_visszaallitas_cimke(self):
        self.pillanat("a\n")
        sha = self.pillanat("b\n")
        self.repo.undo_commit(sha)
        self.assertEqual(self.e.naplo("J.md")["bejegyzesek"][0]["tipus"], "visszavonas")

    def test_nincs_tarolo_404(self):
        for s in (self.cfg,):
            import shutil
            shutil.rmtree(self.repo.git_dir)
        with self.assertRaises(HttpError) as c:
            self.e.naplo("J.md")
        self.assertEqual(c.exception.code, 404)


class Valtozat(Alap):
    def test_szoveg_es_elozo(self):
        self.pillanat("egy\n")
        sha = self.pillanat("kettő\nhárom\n")
        v = self.e.valtozat("J.md", sha)
        self.assertEqual((v["szoveg"], v["elozo"]), ("kettő\nhárom\n", "egy\n"))
        elso = self.e.naplo("J.md")["bejegyzesek"][-1]["sha"]
        v = self.e.valtozat("J.md", elso)
        self.assertEqual((v["szoveg"], v["elozo"], v["elozo_ok"]), ("egy\n", None, "nincs"))

    def test_crlf_bajtra_marad(self):
        self.pillanat("a\r\nb\r\n")
        sha = self.pillanat("a\r\nc\r\n")
        self.assertEqual(self.e.valtozat("J.md", sha)["szoveg"], "a\r\nc\r\n")

    def test_nem_utf8_es_nagy(self):
        ir(self.vault, "B.md", b"\xff\xfe\x00", "wb")
        sha = self.repo.commit_machine("bin", {"Mos-Kor": "SZERK-20261002-100000"}, ["B.md"])
        self.assertEqual(self.e.valtozat("B.md", sha)["szoveg_ok"], "kodolas")
        self.assertEqual(self.repo.fajl_valtozat(sha, "B.md", max_bajt=1)[1], "nagy")

    def test_ismeretlen_commit_404(self):
        self.pillanat("a\n")
        self.pillanat("b\n", ut="M.md")
        sha_m = self.e.naplo("M.md")["bejegyzesek"][0]["sha"]
        with self.assertRaises(HttpError) as c:
            self.e.valtozat("J.md", sha_m)
        self.assertEqual(c.exception.code, 404)


class Visszaallitas(Alap):
    def test_revert_commit_bajtra_azonos(self):
        elso = self.pillanat("egy\r\nsor\r\n")
        self.pillanat("kettő\n")
        self.pillanat("három\n")
        r = self.e.visszaallit("J.md", elso)
        self.assertTrue(r["ok"])
        self.assertEqual(self.olvas(), b"egy\r\nsor\r\n")
        log = self.repo.log(1)[0]
        self.assertEqual(log.sha, r["sha"])
        self.assertEqual(log.trailers["Mos-Forras"], "pult-elozmeny")
        self.assertEqual(log.trailers["Mos-Visszaallit"], elso)
        self.assertEqual(log.trailers["Mos-Tetel"], "J.md")
        self.assertRegex(log.trailers["Mos-Kor"], r"^VISSZA-\d{8}-\d{6}-[0-9a-f]{6}$")
        self.assertEqual(self.e.naplo("J.md")["bejegyzesek"][0]["tipus"], "visszaallitas")
        self.assertEqual(self.repo.dirty(), [])          # a munkafa és az index tiszta (nincs reset/checkout)

    def test_maga_is_visszavonhato(self):
        elso = self.pillanat("egy\n")
        self.pillanat("kettő\n")
        r = self.e.visszaallit("J.md", elso)
        self.repo.undo_commit(r["sha"])
        self.assertEqual(self.olvas(), "kettő\n".encode())

    def test_kezi_valtozas_elotte_kulon_commitba(self):
        elso = self.pillanat("egy\n")
        self.pillanat("kettő\n")
        ir(self.vault, "Mas.md", "kézzel írt\n")
        self.e.visszaallit("J.md", elso)
        log = self.repo.log(3)
        self.assertEqual(log[1].trailers.get("Mos-Forras"), "kezi")
        self.assertIn("Mas.md", self.repo.changed_files(log[1].sha))
        self.assertNotIn("Mas.md", self.repo.changed_files(log[0].sha))

    def test_mas_fajlhoz_nem_nyul(self):
        elso = self.pillanat("egy\n")
        self.pillanat("m1\n", ut="M.md")
        self.pillanat("kettő\n")
        self.pillanat("m2\n", ut="M.md")
        self.e.visszaallit("J.md", elso)
        self.assertEqual(self.olvas("M.md"), b"m2\n")

    def test_a_jelenlegi_valtozat_nem_allithato(self):
        self.pillanat("egy\n")
        sha = self.pillanat("kettő\n")
        with self.assertRaises(HttpError) as c:
            self.e.visszaallit("J.md", sha)
        self.assertEqual(c.exception.code, 400)

    def _atnevezve(self):
        """Regi.md (v1 CRLF, v2) → átnevezve Uj.md → v3: a v1 és v2 a régi néven áll a történetben."""
        v1 = self.pillanat("egy\r\nsor\r\n", ut="Regi.md")
        self.pillanat("kettő\n", ut="Regi.md")
        os.rename(self.vault / "Regi.md", self.vault / "Uj.md")
        self.repo.commit_machine("átnevezve", {"Mos-Kor": "ATNEV-20261002-120000", "Mos-Tetel": "Uj.md"}, ["Regi.md", "Uj.md"])
        self.pillanat("három\n", ut="Uj.md")
        return v1

    def test_regi_nevu_valtozat_az_uj_utra_allithato_vissza(self):
        """39. döntés (T075, K50): az átnevezés előtti változat a JELENLEGI útra íródik új tartalom-írásként; a régi fájl
        nem támad fel; bájtra azonos (a CRLF is); a gépi commit `Mos-Visszaallit` trailert visel; maga is visszavonható."""
        v1 = self._atnevezve()
        r = self.e.visszaallit("Uj.md", v1)
        self.assertTrue(r["ok"])
        self.assertEqual(self.olvas("Uj.md"), b"egy\r\nsor\r\n")
        self.assertFalse((self.vault / "Regi.md").exists(), "a régi út nem támadhat fel")
        c = self.repo.log(1)[0]
        self.assertEqual(c.sha, r["sha"])
        self.assertEqual(self.repo.changed_files(c.sha), ["Uj.md"])
        self.assertEqual((c.trailers["Mos-Forras"], c.trailers["Mos-Visszaallit"], c.trailers["Mos-Tetel"]),
                         ("pult-elozmeny", v1, "Uj.md"))
        self.assertEqual(self.e.naplo("Uj.md")["bejegyzesek"][0]["tipus"], "visszaallitas")
        self.assertEqual(self.repo.dirty(), [])
        self.repo.undo_commit(r["sha"])                                         # maga is visszavonható
        self.assertEqual(self.olvas("Uj.md"), "három\n".encode())
        self.assertFalse((self.vault / "Regi.md").exists())

    def test_regi_nevu_valtozat_a_jelenlegi_tartalommal_azonos(self):
        v1 = self._atnevezve()
        self.e.visszaallit("Uj.md", v1)
        with self.assertRaises(HttpError) as c:
            self.e.visszaallit("Uj.md", v1)
        self.assertEqual(c.exception.code, 400)
        self.assertIn("jelenlegi változat", str(c.exception))

    def test_regi_nevu_visszaallitas_commit_hibajanal_a_tartalom_megmarad(self):
        v1 = self._atnevezve()
        eredeti = snapshot.Repo.commit_machine

        def hibas(repo, *a, **k):
            raise snapshot.SnapshotError("[vault] git commit: elakadt index.lock")

        snapshot.Repo.commit_machine = hibas
        self.addCleanup(setattr, snapshot.Repo, "commit_machine", eredeti)
        with self.assertRaises(HttpError) as c:
            self.e.visszaallit("Uj.md", v1)
        self.assertEqual(c.exception.code, 400)
        self.assertEqual(self.olvas("Uj.md"), "három\n".encode(), "a hibás commit után a jelenlegi tartalom marad")

    def test_regi_ut_404_nem_tamaszt_fel_regi_fajlt(self):
        """T104: a közben átnevezett jegyzet régi útjára kért napló/visszaállítás 404; a régi fájl nem támad fel az új mellett."""
        v1 = self._atnevezve()
        for hivas in (lambda: self.e.naplo("Regi.md"), lambda: self.e.visszaallit("Regi.md", v1),
                      lambda: self.e.valtozat("Regi.md", v1)):
            with self.assertRaises(HttpError) as c:
                hivas()
            self.assertEqual(c.exception.code, 404)
            self.assertIn("átnevezték", str(c.exception))
        self.assertFalse((self.vault / "Regi.md").exists())
        self.assertEqual(self.olvas("Uj.md"), "három\n".encode())

    def test_az_index_megkapja_a_valtozott_utakat(self):
        """T102: a visszaállítás a visszavonáshoz hasonlóan azonnal értesíti az indexet (a figyelő megvárása nélkül)."""
        jelek = []
        e = elozmeny.Elozmeny(self.cfg, jelez=jelek.append)
        elso = self.pillanat("egy\n")
        self.pillanat("kettő\n")
        e.visszaallit("J.md", elso)
        self.assertEqual(jelek, [["J.md"]])
        v1 = self._atnevezve()
        e.visszaallit("Uj.md", v1)
        self.assertEqual(jelek[-1], ["Uj.md"])

    def test_foglalt_kor_zar_409_es_nem_valtoztat(self):
        elso = self.pillanat("egy\n")
        self.pillanat("kettő\n")
        with frame.run_lock(self.cfg):
            with self.assertRaises(HttpError) as c:
                self.e.visszaallit("J.md", elso)
        self.assertEqual(c.exception.code, 409)
        self.assertEqual(self.olvas(), "kettő\n".encode())

    def test_vault_iro_feladat_409(self):
        elso = self.pillanat("egy\n")
        self.pillanat("kettő\n")
        e = elozmeny.Elozmeny(self.cfg, busy=lambda: True)
        with self.assertRaises(HttpError) as c:
            e.visszaallit("J.md", elso)
        self.assertEqual(c.exception.code, 409)

    @csak_darwin("NFD-nevű fájl (a Linux fájlrendszere nem normalizál: az NFD és NFC név két külön fájl)")
    def test_nfd_nev_a_lemezen_megmarad(self):
        nfd = unicodedata.normalize("NFD", "Értékes.md")
        nfc = unicodedata.normalize("NFC", "Értékes.md")
        ir(self.vault, nfd, "egy\n")
        elso = self.repo.commit_machine("a", {"Mos-Kor": "SZERK-20261002-100000"}, [nfc])
        ir(self.vault, nfd, "kettő\n")
        self.repo.commit_machine("b", {"Mos-Kor": "SZERK-20261002-100100"}, [nfc])
        self.e.visszaallit(nfc, elso)
        self.assertIn(nfd, os.listdir(self.vault))
        self.assertEqual((self.vault / nfd).read_bytes(), b"egy\n")

    def test_rovid_sha_nem_fogadott(self):
        self.pillanat("egy\n")
        self.pillanat("kettő\n")
        with self.assertRaises(HttpError):
            self.e.visszaallit("J.md", "abc")


if __name__ == "__main__":
    unittest.main()
