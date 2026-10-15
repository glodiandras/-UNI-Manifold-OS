"""Az indulási helyreállítás és a szándéknapló kezelése (C29.6, 2. audit T016, T093, T094, T101, T105): a megmaradt napló
nem törlődik némán; foglalt kör-zárnál az indulás nem marad el csendben; a saját ideiglenes fájlok takarítódnak; a
helyreállítás a teljes történetben keresi a kört. A „core meghalt” állapotot a `tests/osszeomlas.py` állvány adja."""
import fcntl
import json
import threading
import unittest

from core import atnevezes, frame, gepi_iras, server, snapshot, vaultio
from core.tulajdonsagok import Tulajdonsagok
from tests import osszeomlas as o
from tests.helpers import tmpdir
from tests.index_segedek import index_indit


def gepi_keres(a: o.Allvany, tartalom: str, kor="KARTYA-20261004-103000"):
    alap = vaultio.sha1(a.elotte["T01/a.md"])          # a kliens az ELŐTTE állapotot látta (a félkész írás nem az övé)
    return {"kor": kor, "tetel": "t2", "forras": "mos-kartya", "uzenet": "másik tétel", "modell": None,
            "muveletek": [{"tipus": "csere", "ut": "T01/a.md", "alap": alap, "tartalom": tartalom}]}


def kezi_commitok_tartalma(a: o.Allvany, ut: str) -> list[str]:
    """A `Mos-Forras: kezi` commitok utáni `ut` tartalmak (a félkész gépi tartalom nem kerülhet közéjük, L13)."""
    ki = []
    for c in a.repo.log(50):
        if c.trailers.get("Mos-Forras") == "kezi":
            p = a.repo.git("show", f"{c.sha}:{ut}", check=False)
            if p.returncode == 0:
                ki.append(p.stdout)
    return ki


class MegmaradtNaploTest(unittest.TestCase):
    """T016: a `_naplo_ir` eddig `rmtree`-vel törölte a meg nem állt naplót (és előtte a kézi commit a félkész gépi
    tartalmat „kézi” commitba tette). Most előbb helyreállít vagy félretesz; ha a napló nem oldható fel: 409."""

    def test_gepi_ir_a_megmaradt_naplot_elobb_helyreallitja(self):
        with tmpdir() as t:
            a = o.Allvany(t)
            self.assertEqual(a.futtat("gepi", "gepi.egy_fajl_irva").returncode, 137)
            self.assertIn(b"g\xc3\xa9pi sor", (a.v / "T01/a.md").read_bytes())             # a félkész írás a vaultban áll
            g = gepi_iras.GepiIras(a.cfg, vaultio.Vault(a.cfg), Tulajdonsagok(a.cfg, None), varakozas_mp=1.0)
            r = g.ir(gepi_keres(a, "---\nTags:\nSource:\nStatus:\nNN:\nCanvas:\n---\n# A\n\nmásik tétel\n"))
            # a kliens az eredeti hash-sel dolgozott (alap): a helyreállítás után az írás sikerült, nem ütközés
            self.assertTrue(r["ok"] and r["valtozas"])
            self.assertFalse(any("gépi sor" in x for x in kezi_commitok_tartalma(a, "T01/a.md")),
                             "a félkész gépi tartalom kézi commitba került")
            self.assertFalse((a.cfg.path("run") / gepi_iras.NAPLO).exists())
            self.assertEqual(a.tmp_maradek(), [])

    def test_gepi_oldhatatlan_naplo_409_es_a_naplo_megmarad(self):
        with tmpdir() as t:
            a = o.Allvany(t)
            self.assertEqual(a.futtat("gepi", "gepi.egy_fajl_irva").returncode, 137)
            g = gepi_iras.GepiIras(a.cfg, vaultio.Vault(a.cfg), Tulajdonsagok(a.cfg, None), varakozas_mp=1.0)

            def rossz(cfg):
                raise OSError("nem olvasható napló")

            regi = gepi_iras.helyreallit
            gepi_iras.helyreallit = rossz
            try:
                with self.assertRaises(Exception) as cm:
                    g.ir(gepi_keres(a, "# másik\n"))
            finally:
                gepi_iras.helyreallit = regi
            self.assertEqual(getattr(cm.exception, "code", None), 409, repr(cm.exception))
            self.assertTrue((a.cfg.path("run") / gepi_iras.NAPLO / "terv.json").is_file(), "a napló nem törölhető némán")

    def test_atnevezes_a_megmaradt_naplot_elobb_helyreallitja(self):
        with tmpdir() as t:
            a = o.Allvany(t)
            self.assertEqual(a.futtat("atnevezes", "atnevezes.fajl_irva").returncode, 137)
            part = o.lenyomat(a.v)
            self.assertNotEqual(part, a.elotte)                                          # félig átírt vault
            ix, _ = index_indit(a.cfg)
            self.addCleanup(ix.leallit)
            A = atnevezes.Atnevezes(a.cfg, vaultio.Vault(a.cfg), ix)
            terv = A.terv("X/Szoveg.md", "X/Szoveg2.md")                                   # a félkész linkektől független
            self.assertTrue(terv["ok"], terv["blokkolok"])
            A.vegrehajt("X/Szoveg.md", "X/Szoveg2.md", terv["terv_hash"])
            vart = dict(a.elotte)
            vart["X/Szoveg2.md"] = vart.pop("X/Szoveg.md")
            self.assertEqual(o.lenyomat(a.v), vart, "a megmaradt napló helyreállítása és az új átnevezés után az eredeti + az új")
            self.assertEqual([c for c in kezi_commitok_tartalma(a, "Hivo1.md") if "Új név" in c], [],
                             "a félkész átírás kézi commitba került")
            self.assertFalse((a.cfg.path("run") / atnevezes.NAPLO).exists())

    def test_atnevezes_oldhatatlan_naplo_409(self):
        with tmpdir() as t:
            a = o.Allvany(t)
            self.assertEqual(a.futtat("atnevezes", "atnevezes.fajl_irva").returncode, 137)
            ix, _ = index_indit(a.cfg)
            self.addCleanup(ix.leallit)
            A = atnevezes.Atnevezes(a.cfg, vaultio.Vault(a.cfg), ix)
            terv = A.terv("X/Szoveg.md", "X/Szoveg2.md")
            regi = atnevezes.helyreallit

            def rossz(cfg):
                raise OSError("nem olvasható napló")

            atnevezes.helyreallit = rossz
            try:
                with self.assertRaises(atnevezes.Hiba) as cm:
                    A.vegrehajt("X/Szoveg.md", "X/Szoveg2.md", terv["terv_hash"])
            finally:
                atnevezes.helyreallit = regi
            self.assertEqual(cm.exception.kod, 409)
            self.assertTrue((a.cfg.path("run") / atnevezes.NAPLO / "terv.json").is_file())


class FoglaltKorZarTest(unittest.TestCase):
    """T093 (H3 maradéka): foglalt kör-zárnál az indulási helyreállítás eddig csendben kimaradt, üzenet és újrapróba nélkül."""

    def test_foglalt_zarnal_uzenet_majd_helyreallitas_a_zar_felszabadulasakor(self):
        with tmpdir() as t:
            a = o.Allvany(t)
            self.assertEqual(a.futtat("atnevezes", "atnevezes.fajl_irva").returncode, 137)
            app = server.App(a.cfg, start_delay=0)
            app.helyreallitas_ujra_mp = 0.1
            self.addCleanup(app.queue.close, 0)
            self.addCleanup(app.index.leallit)
            zar = frame.lock_path(a.cfg)
            zar.parent.mkdir(parents=True, exist_ok=True)
            with open(zar, "a+") as fh:
                fcntl.flock(fh, fcntl.LOCK_EX)                                          # egy másik folyamat fogja a zárat
                app.indulas()
                self.assertTrue(any("kimaradt" in u and "kör-zár" in u for u in app.indulasi_uzenetek), app.indulasi_uzenetek)
                self.assertNotEqual(o.lenyomat(a.v), a.elotte, "a zár alatt a helyreállítás nem futhat")
                fcntl.flock(fh, fcntl.LOCK_UN)
            app.helyreallitas_szal.join(20)
            self.assertFalse(app.helyreallitas_szal.is_alive())
            self.assertEqual(o.lenyomat(a.v), a.elotte)
            self.assertTrue(any("visszaállt" in u for u in app.indulasi_uzenetek), app.indulasi_uzenetek)

    def test_szabad_zarnal_nincs_ujraprobalo_szal(self):
        with tmpdir() as t:
            a = o.Allvany(t)
            app = server.App(a.cfg, start_delay=0)
            self.addCleanup(app.queue.close, 0)
            self.addCleanup(app.index.leallit)
            app.indulas()
            self.assertIsNone(app.helyreallitas_szal)


class TmpTakaritasTest(unittest.TestCase):
    def test_csak_a_pontos_mintaju_sajat_tmp_torlodik(self):
        with tmpdir() as t:
            a = o.Allvany(t)
            sajat = [a.v / "T01" / ".a.md.deadbeef.manifold-tmp", a.v / ".gyoker.md.0123abcd.manifold-tmp",
                     a.v / "Mappa" / ".Egy.md.ffffffff.manifold-tmp"]
            marad = [a.v / "T01" / "kezzel.manifold-tmp",                                   # nem pontos alak
                     a.v / "T01" / ".kezzel.manifold-tmp",
                     a.v / "T01" / ".a.md.NEMHEX00.manifold-tmp",
                     a.v / ".obsidian" / ".x.md.deadbeef.manifold-tmp",                     # rejtett mappa: nem a miénk
                     a.v / "T01" / ".a.md.deadbeef.txt"]
            for p in sajat + marad:
                p.write_bytes(b"x")
            self.assertEqual(sorted(frame.tmp_maradekok(a.cfg)), sorted(sajat))
            uzenetek = a.indulas()
            self.assertTrue(any("3 ideiglenes fájl" in u for u in uzenetek), uzenetek)
            for p in sajat:
                self.assertFalse(p.exists(), p)
            for p in marad:
                self.assertTrue(p.exists(), p)
            self.assertEqual(a.indulas(), [])

    def test_nem_letezo_vaulton_nem_takarit(self):
        with tmpdir() as t:
            a = o.Allvany(t)
            p = a.v / "T01" / ".a.md.deadbeef.manifold-tmp"
            p.write_bytes(b"x")
            (a.v / ".obsidian").rename(a.v / ".obsidian-elrejtve")
            self.assertEqual(frame.tmp_takaritas(a.cfg), [])
            self.assertTrue(p.exists())


class TeljesTortenetTest(unittest.TestCase):
    def test_a_rogzitett_atnevezes_nem_fordul_vissza_a_huszadik_commit_utan_sem(self):
        """T094: a helyreállítás a kört csak az utolsó 20 commitban kereste; egy rögzített, de naplóval maradt átnevezést
        (a commit után, a napló törlése előtt halt meg a core) 20 újabb commit után visszafordított."""
        with tmpdir() as t:
            a = o.Allvany(t)
            regi = atnevezes._naplo_torol
            atnevezes._naplo_torol = lambda cfg: None                                    # a napló a commit után is megmarad
            try:
                ix, _ = index_indit(a.cfg)
                A = atnevezes.Atnevezes(a.cfg, vaultio.Vault(a.cfg), ix)
                terv = A.terv("Cél.md", "Új név.md")
                A.vegrehajt("Cél.md", "Új név.md", terv["terv_hash"])
                ix.leallit()
            finally:
                atnevezes._naplo_torol = regi
            utana = o.lenyomat(a.v)
            for i in range(25):
                (a.v / "X" / "Szoveg.md").write_text(f"szám {i}\n", encoding="utf-8")
                a.repo.commit(f"kézi {i}", {"Mos-Forras": "kezi"})
            utana = o.lenyomat(a.v)
            self.assertTrue((a.cfg.path("run") / atnevezes.NAPLO / "terv.json").is_file())
            self.assertEqual(atnevezes.helyreallit(a.cfg), [])                             # csak a napló törlődik
            self.assertEqual(o.lenyomat(a.v), utana)
            self.assertFalse((a.cfg.path("run") / atnevezes.NAPLO).exists())

    def test_kor_commitok_pontos_trailer_osszevetes(self):
        with tmpdir() as t:
            a = o.Allvany(t)
            for kor in ("ATNEV-20261004-100000", "ATNEV-20261004-1000001"):
                (a.v / "X" / "Szoveg.md").write_text(kor, encoding="utf-8")
                a.repo.commit("x", {"Mos-Kor": kor, "Mos-Forras": "kezi"})
            self.assertEqual(len(a.repo.kor_commitok("ATNEV-20261004-100000")), 1)
            self.assertEqual(a.repo.kor_commitok("ATNEV-20261004-10"), [])


if __name__ == "__main__":
    unittest.main()
