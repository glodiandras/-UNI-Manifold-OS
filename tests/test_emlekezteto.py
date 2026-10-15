"""Emlékeztetők (C29): a jegyzet `📅` feladatai az ál-EventKit „Manifold” listájába, kétirányú kipipálás, a jegyzet nyer
ütközésnél, védelmek. Álvaulton, ál-segéddel, a valódi gépi-írás szolgáltatással és pillanatkép-tárolóval — a valódi
vaulthoz, naptárhoz és emlékeztetőkhöz a teszt nem nyúl."""
import sqlite3
import unittest
from unittest import mock
from datetime import datetime, timedelta, timezone

from core import emlekezteto, gepi_iras, naptar, snapshot, szemelyes_db, vaultio
from core.emlekezteto import Emlekezteto, sor_atallit
from core.index import elemzo
from core.naptar_seged import Seged
from core.naptar_szolgalat import NaptarSzolgalat
from core.tulajdonsagok import Tulajdonsagok
from tests.helpers import alg_core, ir, tmpdir
from tests.index_segedek import index_indit
from tests.naptar_segedek import AlSeged

TZ = timezone(timedelta(hours=2))
MOST = datetime(2026, 10, 3, 12, 0, tzinfo=TZ)
UT = "X01 - Napló & To-Do/Tennivalók.md"
JEGYZET = ("# Tennivalók\n\n- [ ] Matek házi 📅 2026-10-05\n- [x] Kész dolog 📅 2026-10-04\n- [ ] Dátum nélkül\n"
           "- [ ] Távoli 📅 2027-12-01\n- [ ] Régi 📅 2026-08-01\n")


class Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.al = AlSeged(self._t.name)
        self.cfg, self.root, self.v = alg_core(self._t.name, **self.al.env())
        ir(self.v, UT, JEGYZET)
        self.repo = snapshot.repos(self.cfg)["vault"]
        self.repo.init()
        self.repo.commit("alap", {"Mos-Forras": "kezi"})
        self.ix, _ = index_indit(self.cfg)
        self.addCleanup(self.ix.leallit)
        self.esemenyek, self.mentetlen = [], set()

        def publish(e, **k):
            self.esemenyek.append(e)
            if e.get("tipus") == "vault_iras":
                self.ix.sajat_iras(e["ut"], e["hash"])

        self.vault = vaultio.Vault(self.cfg)
        self.gepi = gepi_iras.GepiIras(self.cfg, self.vault, Tulajdonsagok(self.cfg, None), publish=publish,
                                       sajat=self.ix.vart_iras, mentetlen=lambda: self.mentetlen, varakozas_mp=0.3)
        self.em = Emlekezteto(self.cfg, self.ix, self.vault, self.gepi, Seged(self.cfg),
                              publish=lambda e, **k: self.esemenyek.append(e), mikor=lambda: MOST)

    # ---- segédek
    def rems(self) -> list[dict]:
        return list(self.al.olvas()["emlekeztetok"].values())

    def rem(self, cim: str) -> dict:
        return next(r for r in self.rems() if r["cim"] == cim)

    def hivasok(self, parancs: str) -> int:
        return self.al.olvas().get("hivasok", []).count(parancs)

    def jegyzet(self) -> str:
        return (self.v / UT).read_text(encoding="utf-8")

    def jegyzet_ir(self, szoveg: str) -> None:
        (self.v / UT).write_text(szoveg, encoding="utf-8")
        self.ix.frissit([UT])

    def sorok(self) -> dict:
        c = sqlite3.connect(szemelyes_db.ut(self.cfg))
        c.row_factory = sqlite3.Row
        try:
            return {r["szoveg"]: dict(r) for r in c.execute("SELECT * FROM emlekezteto")}
        finally:
            c.close()

    def utkozesek(self) -> list[dict]:
        c = sqlite3.connect(szemelyes_db.ut(self.cfg))
        c.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in c.execute("SELECT * FROM emlekezteto_utkozes ORDER BY id")]
        finally:
            c.close()

    def telefonon(self, kinek, **mezok):
        def f(d):
            for r in d["emlekeztetok"].values():
                if r["cim"] == kinek:
                    r.update(mezok)
        self.al.modosit(f)


class LetrehozasTest(Alap):
    def test_csak_az_ablakban_levo_nyitott_feladat_kap_emlekeztetot(self):
        e = self.em.szinkron()
        self.assertEqual((e["allapot"], e["uj"]), ("ok", 1))
        self.assertEqual([r["cim"] for r in self.rems()], ["Matek házi"])       # kész, dátum nélküli, távoli, régi: nem
        r = self.rem("Matek házi")
        self.assertEqual((r["hatarido"], r["ora"], r["kesz"], r["lista"]), ("2026-10-05", "09:00", False, "Manifold"))
        self.assertTrue(r["riasztas"])
        self.assertIn(UT, r["jegyzet"])
        s = self.sorok()["Matek házi"]
        self.assertEqual((s["allapot"], s["rem_azon"], s["jegyzet_kesz"], s["rem_kesz"]), ("aktiv", r["azon"], 0, 0))

    def test_ismetles_nem_ir_ujra(self):
        self.em.szinkron()
        e = self.em.szinkron()
        self.assertEqual((e["uj"], e["torolt"], e["kesz_emlekezteto"], e["kesz_jegyzet"], e["utkozes"]), (0, 0, 0, 0, 0))
        self.assertEqual(self.hivasok("emlekezteto-ir"), 1)
        self.assertEqual(len(self.rems()), 1)

    def test_ketszer_szereplo_azonos_feladat_ket_emlekezteto(self):
        self.jegyzet_ir(JEGYZET + "- [ ] Matek házi 📅 2026-10-06\n")
        self.em.szinkron()
        self.assertEqual(sorted(r["hatarido"] for r in self.rems() if r["cim"] == "Matek házi"), ["2026-10-05", "2026-10-06"])

    def test_engedely_nelkul_nem_ir(self):
        self.al.modosit(lambda d: d.update(emlekezteto="megtagadva"))
        self.assertEqual(self.em.szinkron()["allapot"], "megtagadva")
        self.assertEqual(self.hivasok("emlekezteto-ir"), 0)
        self.assertFalse(szemelyes_db.ut(self.cfg).exists())

    def test_kikapcsolva_es_index_nem_kesz(self):
        self.cfg.data["emlekezteto"]["be"] = False
        self.assertEqual(self.em.szinkron()["allapot"], "ki")
        self.cfg.data["emlekezteto"]["be"] = True
        self.ix.allapot_d["kesz"] = False
        self.assertEqual(self.em.szinkron()["allapot"], "index")
        self.assertEqual(self.hivasok("emlekeztetok"), 0)


class KipipalasTest(Alap):
    def test_jegyzetben_kipipalt_az_emlekeztetoben_is_kesz(self):
        self.em.szinkron()
        self.jegyzet_ir(self.jegyzet().replace("- [ ] Matek házi", "- [x] Matek házi"))
        e = self.em.szinkron()
        self.assertEqual(e["kesz_emlekezteto"], 1)
        r = self.rem("Matek házi")
        self.assertTrue(r["kesz"])
        self.assertIsNotNone(r["kesz_ido"])
        self.assertEqual(self.em.szinkron()["kesz_emlekezteto"], 0)              # a második kör már nem ír
        self.jegyzet_ir(self.jegyzet().replace("- [x] Matek házi", "- [ ] Matek házi"))     # visszanyitás
        self.em.szinkron()
        self.assertFalse(self.rem("Matek házi")["kesz"])

    def test_telefonon_kipipalt_a_jegyzetbe_kerul_gepi_irassal(self):
        self.em.szinkron()
        self.telefonon("Matek házi", kesz=True, kesz_ido="2026-10-03T12:00:00+02:00")
        e = self.em.szinkron()
        self.assertEqual((e["kesz_jegyzet"], e["utkozes"]), (1, 0))
        self.assertIn("- [x] Matek házi 📅 2026-10-05 ✅ 2026-10-03\n", self.jegyzet())
        self.assertEqual(self.jegyzet().count("\n"), JEGYZET.count("\n"))      # csak egy sor változott
        # gépi commit, útlistával, a funkció forrásával; a felhasználó más fájlja érintetlen
        log = self.repo.log(3)
        self.assertEqual(log[0].trailers.get("Mos-Forras"), "mos-emlekezteto")
        self.assertEqual(self.repo.changed_files(log[0].sha), [UT])
        self.assertTrue(any(x.get("tipus") == "gepi_iras" for x in self.esemenyek))
        self.assertEqual(self.em.szinkron()["kesz_jegyzet"], 0)                 # utána nincs több írás
        self.assertEqual(self.sorok()["Matek házi"]["jegyzet_kesz"], 1)
        # a telefonon visszanyitva: a ✅ dátum eltűnik
        self.telefonon("Matek házi", kesz=False, kesz_ido=None)
        self.assertEqual(self.em.szinkron()["kesz_jegyzet"], 1)
        self.assertIn("- [ ] Matek házi 📅 2026-10-05\n", self.jegyzet())

    def test_visszavonas_a_jegyzetet_visszaallitja(self):
        self.em.szinkron()
        self.telefonon("Matek házi", kesz=True)
        self.em.szinkron()
        self.repo.undo_commit(self.repo.log(1)[0].sha, snapshot.exclusions(self.cfg, "vault"))
        self.assertEqual(self.jegyzet(), JEGYZET)

    def test_kesz_datum_kikapcsolhato(self):
        self.cfg.data["emlekezteto"]["kesz_datum"] = False
        self.em.szinkron()
        self.telefonon("Matek házi", kesz=True)
        self.em.szinkron()
        self.assertIn("- [x] Matek házi 📅 2026-10-05\n", self.jegyzet())

    def test_nyitott_mentetlen_dokumentumba_nem_ir_majd_ujraproba(self):
        self.em.szinkron()
        self.telefonon("Matek házi", kesz=True)
        self.mentetlen.add(UT)
        e = self.em.szinkron()
        self.assertEqual((e["kesz_jegyzet"], e["kesobb"]), (0, 1))
        self.assertEqual(self.jegyzet(), JEGYZET)
        self.mentetlen.clear()
        self.assertEqual(self.em.szinkron()["kesz_jegyzet"], 1)
        self.assertIn("- [x] Matek házi", self.jegyzet())

    def test_crlf_jegyzet_bajthu(self):
        (self.v / UT).write_bytes(JEGYZET.replace("\n", "\r\n").encode())
        self.ix.frissit([UT])
        self.em.szinkron()
        self.telefonon("Matek házi", kesz=True)
        self.em.szinkron()
        b = (self.v / UT).read_bytes()
        self.assertIn("- [x] Matek házi 📅 2026-10-05 ✅ 2026-10-03\r\n".encode(), b)
        self.assertEqual(b.count(b"\r\n"), JEGYZET.count("\n"))
        self.assertNotIn(b"\n\n", b.replace(b"\r\n", b""))


class UtkozesTest(Alap):
    def test_telefonon_atirt_cim_es_hataridő_visszaall_es_jelzett(self):
        self.em.szinkron()
        self.telefonon("Matek házi", cim="Másik cím", hatarido="2026-10-09")
        e = self.em.szinkron()
        self.assertEqual(e["utkozes"], 1)
        r = next(iter(self.rems()))
        self.assertEqual((r["cim"], r["hatarido"]), ("Matek házi", "2026-10-05"))        # a jegyzet nyert
        u = self.utkozesek()
        self.assertEqual((len(u), u[0]["fajta"], u[0]["szoveg"], u[0]["ut"]), (1, "szerkesztve", "Matek házi", UT))
        self.assertTrue(any(x.get("tipus") == "emlekezteto_utkozes" and x["fajta"] == "szerkesztve" for x in self.esemenyek))
        self.assertEqual(self.em.szinkron()["utkozes"], 0)                          # egyszer jelez
        self.assertEqual(self.jegyzet(), JEGYZET)                                   # a jegyzet érintetlen

    def test_a_jegyzetben_atirt_hatarido_az_emlekeztetot_koveti_utkozes_nelkul(self):
        self.em.szinkron()
        self.jegyzet_ir(self.jegyzet().replace("Matek házi 📅 2026-10-05", "Matek házi 📅 2026-10-08"))
        e = self.em.szinkron()
        self.assertEqual((e["utkozes"], e["uj"], e["torolt"]), (0, 0, 0))
        self.assertEqual(self.rem("Matek házi")["hatarido"], "2026-10-08")
        self.assertEqual(self.sorok()["Matek házi"]["hatarido"], "2026-10-08")

    def test_ha_a_sor_nem_azonosithato_a_jegyzet_nyer(self):
        self.em.szinkron()
        # az index még a régi állapotot látja, a lemezen a feladat már nincs: elavult index
        regi = emlekezteto.feladat_lista(self.ix)
        (self.v / UT).write_text(JEGYZET.replace("- [ ] Matek házi 📅 2026-10-05\n", ""), encoding="utf-8")
        self.telefonon("Matek házi", kesz=True)
        with mock.patch.object(emlekezteto, "feladat_lista", lambda ix: regi):
            e = self.em.szinkron()
        self.assertEqual((e["kesz_jegyzet"], e["utkozes"]), (0, 1))
        self.assertEqual(self.utkozesek()[0]["fajta"], "sor_nincs")
        self.assertFalse(self.rem("Matek házi")["kesz"])                             # az emlékeztető visszaállt

    def test_utkozes_lattamozasa(self):
        self.em.szinkron()
        self.telefonon("Matek házi", cim="Más")
        self.em.szinkron()
        a = self.em.allapot()
        self.assertEqual(len(a["utkozesek"]), 1)
        self.assertIsNone(a["utkozesek"][0]["latva"])
        self.assertEqual(self.em.utkozes_latva(), 1)
        self.assertIsNotNone(self.em.allapot()["utkozesek"][0]["latva"])


class EltuntesTest(Alap):
    def test_eltunt_feladat_nyitott_tukre_torlodik(self):
        self.em.szinkron()
        self.jegyzet_ir(self.jegyzet().replace("- [ ] Matek házi 📅 2026-10-05\n", ""))
        e = self.em.szinkron()
        self.assertEqual(e["torolt"], 1)
        self.assertEqual(self.rems(), [])
        self.assertEqual(self.sorok()["Matek házi"]["allapot"], "torolve")

    def test_a_kesz_emlekezteto_megmarad_ha_a_feladat_eltunik(self):
        self.em.szinkron()
        self.telefonon("Matek házi", kesz=True)
        self.jegyzet_ir(self.jegyzet().replace("- [ ] Matek házi 📅 2026-10-05\n", ""))
        self.em.szinkron()
        self.assertEqual([r["cim"] for r in self.rems()], ["Matek házi"])
        self.assertEqual(self.sorok()["Matek házi"]["allapot"], "torolve")

    def test_torles_korlat_visszatartja_a_tomeges_torlest(self):
        self.jegyzet_ir(JEGYZET + "- [ ] Egy 📅 2026-10-06\n- [ ] Kettő 📅 2026-10-07\n")
        self.em.szinkron()
        self.assertEqual(len(self.rems()), 3)
        self.cfg.data["emlekezteto"]["torles_max"] = 2
        self.jegyzet_ir("# üres\n")                                                  # pl. a vault nem látszik rendesen
        e = self.em.szinkron()
        self.assertEqual(e["torolt"], 0)
        self.assertEqual(len(self.rems()), 3)
        self.em.szinkron()
        visszatartva = [u for u in self.utkozesek() if u["fajta"] == "torles_visszatartva"]
        self.assertEqual(len(visszatartva), 1)                                      # nem ismétlődik, amíg nem láttamozott

    def test_kezzel_torolt_emlekezteto_nem_ter_vissza(self):
        self.em.szinkron()
        self.al.modosit(lambda d: d["emlekeztetok"].clear())
        self.em.szinkron()
        self.em.szinkron()
        self.assertEqual(self.rems(), [])
        self.assertEqual(self.sorok()["Matek házi"]["allapot"], "kezi_torolt")
        self.assertEqual(self.jegyzet(), JEGYZET)

    def test_torolt_lista_ujraepul(self):
        self.em.szinkron()
        self.al.modosit(lambda d: (d["listak"].clear(), d["emlekeztetok"].clear()))
        e = self.em.szinkron()
        self.assertEqual(e["uj"], 1)
        self.assertEqual([r["cim"] for r in self.rems()], ["Matek házi"])
        self.assertEqual(self.al.olvas()["listak"]["Manifold"]["azon"][:5], "LISTA")


class SzolgalatTest(Alap):
    """Az ütemező (`naptar_szolgalat`): a teljes kör, a 30 s-os ütem csak az emlékeztető-összevetést futtatja."""

    def setUp(self):
        super().setUp()
        self.sz = NaptarSzolgalat(self.cfg, self.ix, self.vault, self.gepi, publish=lambda e, **k: self.esemenyek.append(e),
                                  mikor=lambda: MOST, indulasi_kesleltetes_mp=0)

    def test_teljes_kor_es_allapot(self):
        a = self.sz.kor("kezi")
        self.assertEqual((a["seged"], a["esemeny_engedely"], a["emlekezteto_engedely"], a["hiba"]), (True, "engedelyezve", "engedelyezve", None))
        self.assertEqual(a["emlekezteto_allapot"]["tukor"]["aktiv"], 1)
        self.assertEqual((a["naptar"]["allapot"], a["emlekezteto_kor"]["uj"]), ("engedelyezve", 1))
        self.assertEqual(self.hivasok("olvas"), 1)

    def test_az_utem_csak_valtozasra_hiv_segedet(self):
        self.sz.kor("kezi")
        b = naptar.beallitasok(self.cfg)
        olvas, lehuzas = self.hivasok("olvas"), self.hivasok("emlekeztetok")
        self.sz._tick(b)                                               # nincs változás, a lehúzás ideje sem jött el
        self.assertEqual((self.hivasok("olvas"), self.hivasok("emlekeztetok")), (olvas, lehuzas))
        self.jegyzet_ir(self.jegyzet() + "- [ ] Új feladat 📅 2026-10-06\n")
        self.sz._tick(b)                                               # a feladatok változtak: csak az emlékeztető-kör
        self.assertEqual(self.hivasok("olvas"), olvas)
        self.assertEqual(self.hivasok("emlekeztetok"), lehuzas + 1)
        self.assertEqual(sorted(r["cim"] for r in self.rems()), ["Matek házi", "Új feladat"])

    def test_engedely_nelkul_es_seged_nelkul(self):
        self.al.modosit(lambda d: d.update(esemeny="megtagadva", emlekezteto="megtagadva"))
        a = self.sz.kor("kezi")
        self.assertEqual((a["esemeny_engedely"], a["emlekezteto_engedely"]), ("megtagadva", "megtagadva"))
        self.assertEqual(self.rems(), [])
        cfg2, _, _ = alg_core(self._t.name + "/masik")
        sz2 = NaptarSzolgalat(cfg2, self.ix, self.vault, self.gepi, mikor=lambda: MOST)
        a = sz2.kor("kezi")
        self.assertEqual((a["seged"], "nincs naptár-segéd" in a["hiba"]), (False, True))
        self.assertFalse(szemelyes_db.ut(cfg2).exists())               # segéd nélkül semmi nem íródik az adatbázisba
        self.assertEqual(sz2.engedely()["esemeny"], None)

    def test_engedely_lekerdezes_es_hiba(self):
        self.assertEqual(self.sz.engedely(), {"esemeny": "engedelyezve", "emlekezteto": "engedelyezve"})
        self.al.modosit(lambda d: d.update(hiba_parancs="olvas", hiba_uzenet="összeomlott"))
        a = self.sz.kor("kezi")
        self.assertEqual(a["hiba"], "összeomlott")
        self.assertEqual(self.em.allapot()["be"], True)


class SorAtallitTest(unittest.TestCase):
    def feladat(self, txt, szoveg, hatarido, elofordulas=0):
        return {"szoveg": szoveg, "hatarido": hatarido, "elofordulas": elofordulas}

    def test_alap_es_kesz_datum(self):
        txt = "# C\n\n- [ ] A 📅 2026-10-05\n"
        uj = sor_atallit(txt, self.feladat(txt, "A", "2026-10-05"), True, "2026-10-03")
        self.assertEqual(uj, "# C\n\n- [x] A 📅 2026-10-05 ✅ 2026-10-03\n")
        vissza = sor_atallit(uj, self.feladat(uj, "A", "2026-10-05"), False, "2026-10-04")
        self.assertEqual(vissza, txt)

    def test_kodblokk_es_elofordulas(self):
        txt = "```\n- [ ] A 📅 2026-10-05\n```\n- [ ] A 📅 2026-10-05\n- [ ] A 📅 2026-10-05\n"
        uj = sor_atallit(txt, self.feladat(txt, "A", "2026-10-05", 1), True, None)
        self.assertEqual(uj, "```\n- [ ] A 📅 2026-10-05\n```\n- [ ] A 📅 2026-10-05\n- [x] A 📅 2026-10-05\n")

    def test_dataview_datum_es_behuzas(self):
        txt = "- [ ] fő\n    - [ ] al [due:: 2026-10-05]\n"
        uj = sor_atallit(txt, self.feladat(txt, "al", "2026-10-05"), True, "2026-10-03")
        self.assertEqual(uj, "- [ ] fő\n    - [x] al [due:: 2026-10-05] ✅ 2026-10-03\n")

    def test_nincs_ilyen_feladat(self):
        txt = "- [ ] A 📅 2026-10-05\n"
        self.assertIsNone(sor_atallit(txt, self.feladat(txt, "B", "2026-10-05"), True, None))
        self.assertIsNone(sor_atallit(txt, self.feladat(txt, "A", "2026-10-06"), True, None))     # a határidő megváltozott
        self.assertIsNone(sor_atallit(txt, self.feladat(txt, "A", "2026-10-05", 1), True, None))
        self.assertIsNone(sor_atallit("- [-] A 📅 2026-10-05\n", self.feladat("", "A", "2026-10-05"), True, None))

    def test_a_kulcs_stabil_es_az_ut_a_resze(self):
        a = emlekezteto.kulcs_szamol("x.md", "A", 0)
        self.assertEqual(a, emlekezteto.kulcs_szamol("x.md", "A", 0))
        self.assertNotEqual(a, emlekezteto.kulcs_szamol("y.md", "A", 0))
        self.assertNotEqual(a, emlekezteto.kulcs_szamol("x.md", "A", 1))


if __name__ == "__main__":
    unittest.main()
