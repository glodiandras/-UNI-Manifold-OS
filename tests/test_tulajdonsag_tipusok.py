"""F11: explicit vault-wide property types, CAS, snapshots and no-follow config writes."""
import concurrent.futures
import json
import os
import threading
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

from core import frame, modulkapu, snapshot, tulajdonsag_tipusok as tipusok, vaultio
from core.utvonalak import HttpError
from tests.helpers import alg_core, ir, tmpdir
from tests.test_index_api import IndexApiAlap


class TipusokTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tmpdir()
        self.addCleanup(self.tmp.cleanup)
        self.cfg, self.root, self.v = alg_core(self.tmp.name)
        self.vault = vaultio.Vault(self.cfg)
        self.fajl = self.v / tipusok.UT
        self.jegyzet = ir(self.v, "Note.md", "---\nscore: '12' # keep this comment\n---\n# Note\nBody\n")
        self.repo = snapshot.repos(self.cfg)["vault"]
        self.repo.init()
        self.repo.commit("Baseline")

    def beallit(self, kulcs="score", tipus="number", rev=None):
        return tipusok.beallit(self.vault, {"kulcs": kulcs, "tipus": tipus,
                                          "rev": rev if rev is not None else tipusok.olvas(self.vault)["rev"]})

    def hibas(self, kod, f):
        with self.assertRaises(HttpError) as e:
            f()
        self.assertEqual(e.exception.kod, kod)
        return e.exception

    def test_hianyzo_fajl_letrejon_jegyzet_bajthuen_megmarad_es_visszavonhato(self):
        elotte = self.jegyzet.read_bytes()
        self.assertEqual(tipusok.olvas(self.vault), {"rev": tipusok.HIANY_REV, "types": {}})
        r = self.beallit()
        self.assertTrue(r["git"])
        self.assertRegex(r["kor"], r"^TIPUS-")
        self.assertEqual(r["types"], {"score": "number"})
        self.assertEqual(self.jegyzet.read_bytes(), elotte)
        self.assertEqual(self.repo.changed_files(r["pillanat"]), [tipusok.UT])
        self.repo.undo_commit(r["pillanat"])
        self.assertFalse(self.fajl.exists())
        self.assertEqual(self.jegyzet.read_bytes(), elotte)

    def test_ismeretlen_adat_megmarad_es_elozo_pontos_bajtok_snapshotban(self):
        eredeti = b'{"future": {"enabled": true}, "types": {"score":"text", "other": {"future": 1}}}\r\n'
        self.fajl.write_bytes(eredeti)
        rev = tipusok.olvas(self.vault)["rev"]
        r = self.beallit(rev=rev)
        self.assertEqual(r["types"], {"score": "number"})
        adat = json.loads(self.fajl.read_bytes())
        self.assertEqual(adat["future"], {"enabled": True})
        self.assertEqual(adat["types"]["other"], {"future": 1})
        self.assertEqual(self.repo.git_bytes("show", f'{r["pillanat"]}^:{tipusok.UT}').stdout, eredeti)
        self.repo.undo_commit(r["pillanat"])
        self.assertEqual(self.fajl.read_bytes(), eredeti)

    def test_elavult_rev_nem_ir_felul_es_nem_noop(self):
        rev = tipusok.olvas(self.vault)["rev"]
        self.beallit(rev=rev)
        b = self.fajl.read_bytes()
        self.hibas("tulajdonsag_tipus.utkozes", lambda: self.beallit(rev=rev))
        self.assertEqual(self.fajl.read_bytes(), b)

    def test_azonos_tipus_nem_ir_es_nem_keszit_uj_snapshotot(self):
        self.beallit()
        st, fej = self.fajl.stat(), self.repo.log(1)[0].sha
        r = self.beallit()
        self.assertFalse(r["valtozas"])
        self.assertEqual(self.fajl.stat().st_mtime_ns, st.st_mtime_ns)
        self.assertEqual(self.repo.log(1)[0].sha, fej)

    def test_hibas_json_duplikalt_vagy_nem_veges_adat_sosem_irhato_felul(self):
        for b in (b'', b'[]', b'{', b'{"types":null}', b'{"types":[]}', b'\xff',
                  b'{"types":{},"types":{}}', b'{"future":{"x":1,"x":2}}',
                  b'{"other":NaN}', b'{"other":Infinity}'):
            with self.subTest(b=b):
                self.fajl.write_bytes(b)
                self.hibas("tulajdonsag_tipus.hibas_json", lambda: tipusok.olvas(self.vault))
                self.hibas("tulajdonsag_tipus.hibas_json", lambda: self.beallit(rev=tipusok.HIANY_REV))
                self.assertEqual(self.fajl.read_bytes(), b)

    def test_ismeretlen_json_szamok_teljes_pontossaga_megmarad(self):
        self.fajl.write_bytes(b'{"future":[9007199254740993.5,1e999,1.234567890123456789],"types":{}}')
        elotte = json.loads(self.fajl.read_bytes(), parse_float=Decimal)
        self.beallit()
        utana = json.loads(self.fajl.read_bytes(), parse_float=Decimal)
        self.assertEqual(utana["future"], elotte["future"])

    def test_korabbrol_elerheto_cache_nem_keruli_meg_a_munkater_cserekaput(self):
        self.cfg.elrendezes = "termek"
        self.cfg.workspace_id = "a" * 32
        self.cfg.utak["workspace"] = self.v / ".manifold"
        ir(self.v, ".manifold/workspace.toml", '[workspace]\nid = "' + self.cfg.workspace_id + '"\n')
        tipusok.olvas(self.vault)
        self.assertTrue(self.vault._elerheto)
        (self.v / ".manifold").rename(self.v / ".manifold-old")
        ir(self.v, ".manifold/workspace.toml", '[workspace]\nid = "' + "b" * 32 + '"\n')
        self.hibas("tulajdonsag_tipus.munkater_csere", lambda: self.beallit(rev="hianyzik"))
        self.assertFalse(self.fajl.exists())

    def test_tul_nagy_fajl_es_uj_adat_is_korlatozott(self):
        self.fajl.write_bytes(b" " * (tipusok.MAX_BAJT + 1))
        self.hibas("tulajdonsag_tipus.tul_nagy", lambda: tipusok.olvas(self.vault))
        self.fajl.unlink()
        with mock.patch.object(tipusok, "MAX_BAJT", 10):
            self.hibas("tulajdonsag_tipus.tul_nagy", self.beallit)
        self.assertFalse(self.fajl.exists())

    def test_beepitett_tipusok_es_szigoru_keresvalidacio(self):
        for kulcs, tipus in (("tags", "text"), ("Tag", "aliases"), ("ALIASES", "number"),
                             ("alias", "date"), ("score", "tags"), ("score", "aliases")):
            self.hibas("tulajdonsag_tipus.rogzitett", lambda: self.beallit(kulcs, tipus))
        for k in ("", "1number", "a:b", "a\nb", "a/b", "a" * 257, "\ud800"):
            self.hibas("tulajdonsag_tipus.kulcs", lambda: self.beallit(k))
        for d in ({}, {"kulcs":"score", "tipus":"number", "rev":"bad"},
                  {"kulcs":"score", "tipus":[], "rev":"hianyzik"},
                  {"kulcs":"score", "tipus":"number", "rev":"hianyzik", "extra":1}):
            with self.assertRaises(HttpError):
                tipusok.beallit(self.vault, d)
        self.beallit("tags", "tags")
        self.beallit("Aliases", "aliases")

    def test_kulcs_unicode_normalizalas_es_jegyzeten_kivuli_nyilvantartas(self):
        r = self.beallit("  E\u0301rte\u0301k ", "text")
        self.assertEqual(r["types"], {"Érték": "text"})

    def test_symlink_types_fajl_es_mappa_nem_kovetheto(self):
        kulso = Path(self.tmp.name) / "outside"
        kulso.mkdir()
        cel = ir(kulso, "types.json", '{"types":{}}')
        self.fajl.symlink_to(cel)
        self.hibas("tulajdonsag_tipus.nem_biztonsagos", lambda: tipusok.olvas(self.vault))
        self.hibas("tulajdonsag_tipus.nem_biztonsagos", lambda: self.beallit(rev="hianyzik"))
        self.fajl.unlink()
        (self.v / ".obsidian").rmdir()
        (self.v / ".obsidian").symlink_to(kulso, target_is_directory=True)
        self.hibas("tulajdonsag_tipus.mappa", lambda: tipusok.olvas(self.vault))
        self.assertEqual(cel.read_text(), '{"types":{}}')

    def test_nem_regularis_fifo_nem_akasztja_meg_az_olvasot(self):
        os.mkfifo(self.fajl)
        self.hibas("tulajdonsag_tipus.nem_biztonsagos", lambda: tipusok.olvas(self.vault))

    def test_kulso_iras_a_tmp_irasa_kozben_cas_utkozes_es_takaritas(self):
        kulso = b'{"types":{"other":"date"}}'
        eredeti_fsync = tipusok.fsync_teljes
        def fsync(fd):
            self.fajl.write_bytes(kulso)
            eredeti_fsync(fd)
        with mock.patch.object(tipusok, "fsync_teljes", side_effect=fsync):
            self.hibas("tulajdonsag_tipus.utkozes", self.beallit)
        self.assertEqual(self.fajl.read_bytes(), kulso)
        self.assertEqual(list(self.fajl.parent.glob("*.manifold-tmp")), [])

    def test_mappacsere_tmp_iras_kozben_nem_ir_kulso_helyre(self):
        kulso = Path(self.tmp.name) / "outside"
        kulso.mkdir()
        cel = ir(kulso, "types.json", '{"types":{}}')
        eredeti_fsync = tipusok.fsync_teljes
        def csere(fd):
            (self.v / ".obsidian").rename(self.v / ".obsidian-old")
            (self.v / ".obsidian").symlink_to(kulso, target_is_directory=True)
            eredeti_fsync(fd)
        with mock.patch.object(tipusok, "fsync_teljes", side_effect=csere):
            self.hibas("tulajdonsag_tipus.utkozes", self.beallit)
        self.assertEqual(cel.read_text(), '{"types":{}}')
        self.assertFalse((self.v / ".obsidian-old/types.json").exists())
        self.assertEqual(list((self.v / ".obsidian-old").glob("*.manifold-tmp")), [])

    def test_ket_egyideju_felhasznalo_kozul_egyik_nyer_a_masik_nem_irja_felul(self):
        rev = tipusok.olvas(self.vault)["rev"]
        kapu = threading.Barrier(2)
        def iras(kulcs):
            kapu.wait(5)
            try:
                return self.beallit(kulcs, rev=rev)
            except HttpError as e:
                return e
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            eredmenyek = list(pool.map(iras, ("first", "second")))
        self.assertEqual(sum(isinstance(r, dict) for r in eredmenyek), 1)
        self.assertEqual([r.kod for r in eredmenyek if isinstance(r, HttpError)], ["tulajdonsag_tipus.utkozes"])
        self.assertEqual(len(tipusok.olvas(self.vault)["types"]), 1)

    def test_elozetes_snapshot_nelkul_nincs_iras(self):
        with mock.patch.object(self.vault, "repo", return_value=None):
            self.hibas("tulajdonsag_tipus.pillanat_nincs", self.beallit)
        with mock.patch.object(snapshot.Repo, "commit", side_effect=snapshot.SnapshotError("failed")):
            self.hibas("tulajdonsag_tipus.pillanat_hiba", self.beallit)
        self.assertFalse(self.fajl.exists())

    def test_kizart_regi_tipusfajl_nem_irhato_snapshot_nelkul(self):
        self.fajl.write_text('{"types":{}}')
        self.repo.git("config", "core.excludesFile", str(ir(self.root, "ignore", ".obsidian/types.json\n")))
        self.hibas("tulajdonsag_tipus.pillanat_hiba", self.beallit)
        self.assertEqual(self.fajl.read_text(), '{"types":{}}')

    def test_kizart_uj_tipusfajlt_sem_hozunk_letre_snapshot_nelkul(self):
        self.repo.git("config", "core.excludesFile", str(ir(self.root, "ignore", ".obsidian/types.json\n")))
        self.hibas("tulajdonsag_tipus.pillanat_hiba", self.beallit)
        self.assertFalse(self.fajl.exists())

    def test_utana_snapshot_hibanal_a_sikeres_fajliras_es_elozmeny_megmarad(self):
        regi = b'{"types":{"score":"text"}}\r\n'
        self.fajl.write_bytes(regi)
        with mock.patch.object(snapshot.Repo, "commit_machine", side_effect=snapshot.SnapshotError("failed")):
            r = self.beallit()
        self.assertFalse(r["git"])
        self.assertIn("snapshot failed", r["figyelmeztetes"])
        self.assertEqual(tipusok.olvas(self.vault)["types"], {"score": "number"})
        self.assertEqual(self.repo.git_bytes("show", f"HEAD:{tipusok.UT}").stdout, regi)

    def test_kis_de_mely_json_nem_bovul_negyzetesen_es_megmarad(self):
        nyers = '{"x":' * 220 + '{"unicode":"' + "ő" * 6000 + '"}' + '}' * 220
        self.fajl.write_text(nyers)
        self.beallit()
        self.assertLess(self.fajl.stat().st_size, 40000)

    def test_decimal_extrem_kitevo_kontrollalt_hiba(self):
        b = b'{"other":1e999999999999999999999999}'
        self.fajl.write_bytes(b)
        self.hibas("tulajdonsag_tipus.hibas_json", lambda: tipusok.olvas(self.vault))
        self.assertEqual(self.fajl.read_bytes(), b)

    def test_csere_utani_fsync_hiba_nem_hamis_sikertelen_mentes(self):
        regi = b'{"types":{"score":"text"}}'
        self.fajl.write_bytes(regi)
        eredeti = tipusok.fsync_teljes
        hivasok = []
        def fsync(fd):
            hivasok.append(fd)
            if len(hivasok) == 2:
                raise OSError("directory fsync failed")
            eredeti(fd)
        with mock.patch.object(tipusok, "fsync_teljes", side_effect=fsync):
            r = self.beallit()
        self.assertEqual(tipusok.olvas(self.vault)["rev"], r["rev"])
        self.assertEqual(r["types"], {"score": "number"})
        self.assertFalse(r["tartos"])
        self.assertTrue(r["git"])
        self.assertIn("durability is uncertain", r["figyelmeztetes"])
        self.assertEqual(self.repo.git_bytes("show", f'{r["pillanat"]}^:{tipusok.UT}').stdout, regi)

    def test_kor_zar_foglalt_es_modulkapu_nem_kerulheto_meg(self):
        with frame.run_lock(self.cfg), mock.patch.object(frame, "felhasznaloi_turelem", return_value=0):
            self.hibas("tulajdonsag_tipus.foglalt", self.beallit)
        cfg = mock.Mock()
        cfg.section.return_value = {"tulajdonsagok": False}
        for ut in ("/api/vault/tulajdonsagok/tipus", "/api/vault/tulajdonsagok/tipusok"):
            self.hibas("modul.kikapcsolva", lambda: modulkapu.ellenoriz(cfg, ut))
        modulkapu.ellenoriz(cfg, "/api/vault/tulajdonsagok/elemez")

    def test_keso_index_nem_hamis_sikertelen_mentes(self):
        index = mock.Mock()
        index.frissit.return_value = False
        r = tipusok.beallit(self.vault, {"kulcs":"score", "tipus":"number", "rev":"hianyzik"}, index)
        self.assertFalse(r["index_kesz"])
        self.assertIn("index has not finished", r["figyelmeztetes"])
        self.assertEqual(tipusok.olvas(self.vault)["rev"], r["rev"])


class TipusApiTest(IndexApiAlap):
    def test_http_type_cas_ujraindexeles_es_visszavonas(self):
        repo = snapshot.repos(self.cfg)["vault"]
        repo.init()
        statusz, r = self.get("/api/vault/tulajdonsagok/tipusok")
        self.assertEqual(statusz, 200)
        statusz, mentett = self.k("POST", "/api/vault/tulajdonsagok/tipus", {"kulcs":"score", "tipus":"number", "rev":r["rev"]})
        self.assertEqual(statusz, 200, mentett)
        self.assertTrue(mentett["git"])
        statusz, elemzes = self.k("POST", "/api/vault/tulajdonsagok/elemez", {"ut":"Cél.md", "fm":"---\nscore: tomorrow\n---\n"})
        self.assertEqual(statusz, 200)
        prop = next(p for p in elemzes["tulajdonsagok"] if p["kulcs"] == "score")
        self.assertEqual((prop["tipus"], prop["ervenyes"], prop["ertek"]), ("number", False, "tomorrow"))
        statusz, _ = self.k("POST", "/api/vault/tulajdonsagok/tipus", {"kulcs":"score", "tipus":"text", "rev":r["rev"]})
        self.assertEqual(statusz, 409)
        statusz, vissza = self.k("POST", "/api/pillanat/vault/visszavonas", {"sha": mentett["pillanat"]})
        self.assertEqual(statusz, 200, vissza)
        self.assertEqual(self.get("/api/vault/tulajdonsagok/tipusok")[1]["types"], {})
