"""F8 gate: Obsidian vault → new Manifold workspace (`core/importalas.py`).

Every test checks that the SOURCE stays byte- and metadata-identical (`ujjlenyomat`), whatever happens: preview, import, repeated
import, interrupted import, resumed import, undo. Synthetic vaults in temp dirs only."""
from __future__ import annotations

import os
import time
import tomllib
import types
import unicodedata
import unittest
from pathlib import Path
from unittest import mock

from core import importalas as imp
from core import termek_beallitasok, utvonalak, workspace
from core.utvonalak import HttpError
from tests.fresh_install import termek_alap
from tests.helpers import tmpdir
from tests.migracio import BINARIS, JEGYZETEK, Kuka, obsidian_vault, tartalom, ujjlenyomat


def _vart_masolat(forras: Path) -> dict[str, bytes | None]:
    """What the destination must hold (besides `.manifold/`): the source without the skipped entries."""
    ki = {}
    for rp, b in tartalom(forras, kihagy=(".git", ".trash")).items():
        nev = Path(rp.rstrip("/")).name
        if nev == ".DS_Store" or rp.startswith(".hidden") or nev == "Shortcut.md":
            continue
        ki[rp] = b
    return ki


class _Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.t = Path(self._t.name)
        self.root, self.home, self.alap = termek_alap(self._t.name)
        self.forras = obsidian_vault(self.t / "My Vault")
        self.cel = self.t / "Imported"
        self.kuka = Kuka(self.t / "Trash")
        self.lenyomat = ujjlenyomat(self.forras)

    def tearDown(self):
        # the gate: the source is byte-identical (and its metadata unchanged) after every test
        self.assertEqual(ujjlenyomat(self.forras), self.lenyomat, "the import changed the source")

    def elonezet(self, **opciok):
        return imp.obsidian_elonezet(self.forras, self.cel, self.alap, opciok or None)

    def importal(self, **k):
        t = self.elonezet()
        return imp.obsidian_importal(self.forras, self.cel, self.alap, terv_hash=t["terv_hash"], **k)

    def tcfg(self):
        from tests.fresh_install import termek_cfg
        return termek_cfg(self.root, self.home, self.cel)


class ElonezetTest(_Alap):
    def test_az_elonezet_semmit_nem_ir_es_mindent_jelent(self):
        # A terv determinisztikus; a teljes választ azonos lemezkapacitás mellett hasonlítjuk össze.
        with mock.patch("core.workspace.shutil.disk_usage", return_value=types.SimpleNamespace(free=1 << 40)):
            r = self.elonezet()
            ismetelt = self.elonezet()
        self.assertFalse(self.cel.exists())
        self.assertFalse((self.alap.path("install") / "imports").exists(), "the preview must not create a journal")
        self.assertEqual(r["eredmeny"], "figyelmeztet", r["akadaly"])
        self.assertEqual(r["akadaly"], [])
        self.assertIn("nem_tamogatott_pluginok", r["figyelmeztetes"])
        self.assertIn("kihagyott_elemek", r["figyelmeztetes"])
        o = r["osszesites"]
        self.assertEqual((o["md_db"], o["canvas_db"], o["base_db"], o["csatolmany_db"]), (7, 1, 1, 2))
        self.assertEqual(o["masolando_db"], o["fajl_db"])
        okok = {k["ut"]: k["ok"] for k in r["kihagyott"]}
        self.assertEqual(okok[".git"], "git")
        self.assertEqual(okok[".trash"], "obsidian_kuka")
        self.assertEqual(okok[".hidden-note.md"], "rejtett")
        self.assertEqual(okok["Shortcut.md"], "symlink")
        self.assertEqual(okok[".DS_Store"], "rendszer")
        self.assertIn("Empty folder", [f for f in imp._terv(self.forras, self.cel, self.alap).mappak])
        # links: counted on the code-masked text, the format comes from app.json
        l = r["linkek"]
        self.assertEqual((l["wikilink_db"], l["beagyazas_db"], l["markdown_link_db"], l["frontmatter_db"]), (2, 2, 1, 2))
        self.assertEqual(l["beallitas"], {"wikilinkek": False, "link_formatum": "relativ"})
        self.assertEqual(r["atiras"], [], "no rewriting option exists: content goes over unchanged")
        # the .obsidian mapping
        b = {x["kulcs"]: x for x in r["obsidian"]["beallitasok"]}
        self.assertEqual((b["beallitasok.fajlok.link_formatum"]["ertek"], b["beallitasok.fajlok.link_formatum"]["mod"]),
                         ("relativ", "ir"))
        self.assertEqual(b["beallitasok.fajlok.wikilinkek"]["ertek"], False)
        self.assertEqual(b["beallitasok.szerkeszto.tab_meret"]["ertek"], 4)
        self.assertEqual(b["beallitasok.megjelenes.betumeret"]["ertek"], 18)
        self.assertEqual(b["beallitasok.megjelenes.tema"]["ertek"], "sotet")
        self.assertEqual(b["sablon.datum"]["ertek"], "DD.MM.YYYY")
        self.assertEqual((b["sablon.mappa"]["ertek"], b["sablon.mappa"]["mod"]), ("Templates", "munkater"))
        self.assertEqual(b["naplo.ut"]["ertek"], "[Journal]/YYYY-MM-DD")
        self.assertEqual(b["naplo.sablon"]["ertek"], "Templates/Daily.md")      # vault-relatív út, nem csonkolt név (12-templates-01/08)
        self.assertEqual(b["beallitasok.fajlok.csatolmany_mappa"]["mod"], "kozvetlen")
        self.assertEqual(b["tulajdonsag_tipusok"]["ertek"], 2)
        nem = {x["forras"] for x in r["obsidian"]["nem_atvett"]}
        self.assertIn(".obsidian/app.json#alwaysUpdateLinks", nem)
        self.assertIn(".obsidian/appearance.json#cssTheme", nem)
        self.assertIn(".obsidian/daily-notes.json#autorun", nem)
        self.assertIn(".obsidian/graph.json", nem)
        self.assertNotIn(".obsidian/templates.json#dateFormat", nem)
        mag = {p["id"]: p for p in r["obsidian"]["mag_pluginok"]}
        self.assertEqual((mag["backlink"]["allapot"], mag["backlink"]["modul"]), ("tamogatott", "hivatkozasok"))
        self.assertEqual(mag["audio-recorder"]["allapot"], "nem_tamogatott")
        self.assertEqual(mag["file-explorer"]["allapot"], "beepitett")
        self.assertEqual(r["obsidian"]["kozossegi_pluginok"],
                         [{"id": "example-plugin", "be": True, "allapot": "nem_tamogatott"}])
        self.assertIn("mappa", r["letrehozando"])
        self.assertNotIn("obsidian", r["letrehozando"])
        self.assertTrue(r["id"].startswith("obs-"))
        self.assertEqual(r, ismetelt, "the preview is deterministic under identical capacity")

    def test_a_szabad_hely_friss_meres_a_terv_es_hash_valtozasa_nelkul(self):
        """A háttérben változó szabad hely nem módosítja a tervet, amíg mindkét mérés elegendő helyet jelez."""
        with mock.patch("core.workspace.shutil.disk_usage", side_effect=[
            types.SimpleNamespace(free=1 << 40), types.SimpleNamespace(free=(1 << 40) + 4096),
        ]) as meres:
            elso, masodik = self.elonezet(), self.elonezet()
        self.assertEqual(meres.call_count, 2)
        self.assertEqual((elso["szabad_bajt"], masodik["szabad_bajt"]), (1 << 40, (1 << 40) + 4096))
        self.assertEqual(elso["terv_hash"], masodik["terv_hash"])
        self.assertEqual({k: v for k, v in elso.items() if k != "szabad_bajt"},
                         {k: v for k, v in masodik.items() if k != "szabad_bajt"},
                         "only the live capacity reading may change; every semantic preview field stays identical")
        self.assertFalse(self.cel.exists())
        self.assertEqual(ujjlenyomat(self.forras), self.lenyomat)

    def test_opciok_a_kuka_es_az_obsidian_mappa(self):
        r = self.elonezet(kuka_mappa=True, obsidian_mappa=False)
        okok = {k["ut"]: k["ok"] for k in r["kihagyott"]}
        self.assertNotIn(".trash", okok)
        self.assertEqual(okok[".obsidian"], "opcio")
        self.assertEqual(r["obsidian"]["beallitasok"], [])
        self.assertNotEqual(r["terv_hash"], self.elonezet()["terv_hash"])
        with self.assertRaises(HttpError) as e:
            self.elonezet(ismeretlen=True)
        self.assertEqual(e.exception.kod, "import.ervenytelen_keres")

    def test_akadalyok(self):
        belul = imp.obsidian_elonezet(self.forras, self.forras / "Inside", self.alap)
        self.assertIn("cel_a_forrasban", belul["akadaly"])
        self.assertEqual(belul["eredmeny"], "tilos")
        kivul = imp.obsidian_elonezet(self.forras, self.t, self.alap)
        self.assertIn("forras_a_celban", kivul["akadaly"])
        nincs = imp.obsidian_elonezet(self.t / "missing", self.cel, self.alap)
        self.assertIn("forras_nem_mappa", nincs["akadaly"])
        with self.assertRaises(HttpError) as e:
            imp.obsidian_importal(self.forras, self.forras / "Inside", self.alap)
        self.assertEqual((e.exception.code, e.exception.kod), (409, "import.tilos"))
        self.assertFalse((self.forras / "Inside").exists())

    def test_nem_ures_idegen_cel_utkozes_es_semmi_nem_irodik(self):
        self.cel.mkdir()
        (self.cel / "Home.md").write_text("Something else\n", encoding="utf-8")
        (self.cel / "Ideas.md").write_bytes((self.forras / "Ideas.md").read_bytes())
        elotte = ujjlenyomat(self.cel)
        r = self.elonezet()
        self.assertIn("cel_nem_ures", r["akadaly"])
        self.assertIn("fajl_utkozes", r["akadaly"])
        muvelet = {f["ut"]: f["muvelet"] for f in r["fajlok"]}
        self.assertEqual((muvelet["Home.md"], muvelet["Ideas.md"]), ("utkozes", "megvan"))
        self.assertIn({"ut": "Home.md", "ok": "cel_elter"}, r["utkozesek"])
        with self.assertRaises(HttpError) as e:
            imp.obsidian_importal(self.forras, self.cel, self.alap, terv_hash=r["terv_hash"])
        self.assertEqual(e.exception.kod, "import.utkozes")
        self.assertEqual(ujjlenyomat(self.cel), elotte)

    def test_munkater_cel_tilos(self):
        masik = self.t / "Existing"
        masik.mkdir()
        workspace.letrehoz(masik, self.alap)
        r = imp.obsidian_elonezet(self.forras, masik, self.alap)
        self.assertIn("cel_munkater", r["akadaly"])

    def test_nev_utkozesek_kis_nagy_es_normalizalas(self):
        f = [imp._Fajl("Note.md", "jegyzet", 1, 0), imp._Fajl("note.md", "jegyzet", 1, 0),
             imp._Fajl(unicodedata.normalize("NFD", "Ő.md"), "jegyzet", 1, 0), imp._Fajl("Ő.md", "jegyzet", 1, 0)]
        ki = {(u["ut"], u["ok"]) for u in imp._nev_utkozesek(f, [], erzekeny=False)}
        self.assertEqual(ki, {("note.md", "kis_nagy"), ("Ő.md", "normalizalas")})
        self.assertEqual([u["ok"] for u in imp._nev_utkozesek(f, [], erzekeny=True)], ["normalizalas"])


class ImportTest(_Alap):
    def test_import_bajtra_azonos_munkater_beallitasok_es_idempotens(self):
        r = self.importal()
        self.assertEqual(r["allapot"], "kesz")
        self.assertFalse(r["ismetles"])
        # byte identity of everything copied, `.obsidian/` included; nothing else in the destination
        self.assertEqual(tartalom(self.cel), _vart_masolat(self.forras))
        self.assertTrue((self.cel / "Empty folder").is_dir())
        self.assertEqual((self.cel / ".obsidian" / "types.json").read_bytes(), (self.forras / ".obsidian" / "types.json").read_bytes())
        nfd = unicodedata.normalize("NFD", "Projects/Résumé.md")
        self.assertEqual((self.cel / nfd).read_bytes(), JEGYZETEK[nfd].encode())
        self.assertEqual((self.cel / "Attachments/chart.pdf").read_bytes(), BINARIS["Attachments/chart.pdf"])
        self.assertEqual(os.stat(self.cel / "Ideas.md").st_mtime_ns, os.stat(self.forras / "Ideas.md").st_mtime_ns)
        self.assertFalse(list(self.cel.rglob("*.manifold-tmp")))
        # the workspace and its settings
        id = workspace.azonosit(self.cel)
        self.assertEqual(id, r["munkater_id"])
        w = tomllib.loads((self.cel / ".manifold" / "workspace.toml").read_text(encoding="utf-8"))
        self.assertEqual(w["sablon"]["mappa"], "Templates")
        self.assertEqual(w["sablon"]["datum"], "DD.MM.YYYY")
        self.assertEqual(w["naplo"]["ut"], "[Journal]/YYYY-MM-DD")
        self.assertEqual(w["beallitasok"]["fajlok"]["link_formatum"], "relativ")
        ertek = termek_beallitasok.olvas(self.tcfg())["ertek"]
        self.assertEqual(ertek["fajlok"]["csatolmany_mappa"], "Attachments")
        self.assertEqual((ertek["fajlok"]["link_formatum"], ertek["fajlok"]["wikilinkek"]), ("relativ", False))
        self.assertEqual((ertek["szerkeszto"]["tab_meret"], ertek["szerkeszto"]["helyesiras"]), (4, False))
        self.assertEqual((ertek["megjelenes"]["betumeret"], ertek["megjelenes"]["tema"]), (18, "sotet"))
        self.assertEqual(ertek["fajlok"]["sablon_mappa"], "Templates")
        # the journal
        a = imp.allapot(r["id"], self.alap)
        self.assertEqual(a["allapot"], "kesz")
        naplo = imp._obsidian_naplo(self.alap, r["id"])
        sorok = naplo.sorok()
        self.assertEqual(len([s for s in sorok if s["m"] == "fajl"]), r["masolt_db"])
        # repeat: idempotent, nothing written
        cel_elotte = ujjlenyomat(self.cel)
        naplo_elotte = (naplo.mappa / imp.NAPLO).read_bytes()
        r2 = imp.obsidian_importal(self.forras, self.cel, self.alap)
        self.assertTrue(r2["ismetles"])
        self.assertEqual(ujjlenyomat(self.cel), cel_elotte)
        self.assertEqual((naplo.mappa / imp.NAPLO).read_bytes(), naplo_elotte)
        self.assertEqual(self.elonezet()["eredmeny"], "kesz")
        self.assertEqual([x["id"] for x in imp.lista(self.alap)], [r["id"]])

    def test_valtozott_forras_utan_a_regi_terv_nem_fut(self):
        t = self.elonezet()
        os.utime(self.forras / "Ideas.md", ns=(1_700_000_000_000_000_000, 1_700_000_000_000_000_000))
        self.lenyomat = ujjlenyomat(self.forras)
        with self.assertRaises(HttpError) as e:
            imp.obsidian_importal(self.forras, self.cel, self.alap, terv_hash=t["terv_hash"])
        self.assertEqual(e.exception.kod, "import.terv_valtozott")
        self.assertFalse(self.cel.exists())

    def test_megszakadt_import_folytathato(self):
        eredeti = imp._fajl_masol
        db = {"n": 0}

        def hibas(*a, **k):
            db["n"] += 1
            if db["n"] == 4:
                raise OSError(28, "No space left on device")
            return eredeti(*a, **k)

        with mock.patch.object(imp, "_fajl_masol", hibas), self.assertRaises(HttpError) as e:
            self.importal()
        self.assertEqual(e.exception.kod, "import.masolas_hiba")
        id = self.elonezet()["id"]
        a = imp.allapot(id, self.alap)
        self.assertEqual((a["allapot"], a["hiba"]["kod"]), ("hiba", "import.masolas_hiba"))
        self.assertFalse(list(self.cel.rglob("*.manifold-tmp")))
        self.assertIsNone(workspace.azonosit(self.cel))
        t = self.elonezet()
        self.assertEqual(t["allapot"], "hiba")
        self.assertEqual(t["akadaly"], [])
        self.assertEqual(t["osszesites"]["megvan_db"], 3)
        r = imp.obsidian_importal(self.forras, self.cel, self.alap, terv_hash=t["terv_hash"])
        self.assertEqual((r["allapot"], r["megvolt_db"], r["masolt_db"]), ("kesz", 3, t["osszesites"]["masolando_db"]))
        self.assertEqual(tartalom(self.cel), _vart_masolat(self.forras))

    def test_megszakadt_futas_ideiglenes_fajljat_a_folytatas_takaritja(self):
        """A killed process leaves its `.manifold-tmp` (journaled before it was created): the resumed run removes it."""
        eredeti = imp._fajl_masol
        db = {"n": 0}

        def hibas(*a, **k):
            db["n"] += 1
            if db["n"] == 3:
                raise OSError(5, "I/O error")
            return eredeti(*a, **k)

        with mock.patch.object(imp, "_fajl_masol", hibas), self.assertRaises(HttpError):
            self.importal()
        id = self.elonezet()["id"]
        naplo = imp._obsidian_naplo(self.alap, id)
        arva = self.cel / ".Plan.md.0badcafe.manifold-tmp"
        arva.write_bytes(b"half written")
        naplo.sor({"m": "tmp", "ut": arva.name})
        r = self.importal()
        self.assertEqual(r["allapot"], "kesz")
        self.assertFalse(arva.exists())
        self.assertFalse(list(self.cel.rglob("*.manifold-tmp")))
        self.assertEqual(tartalom(self.cel), _vart_masolat(self.forras))

    def test_klon_nelkuli_masolas_bajtot_es_idoket_tart(self):
        """Another volume (no APFS clone): the hashed stream copy keeps bytes, mtime and birth time."""
        def nincs_klon(src, dst):
            raise OSError(imp.errno.EXDEV, "cross-device")

        with mock.patch.object(imp.tartos, "klon_excl", nincs_klon):
            r = self.importal()
        self.assertEqual(r["allapot"], "kesz")
        self.assertEqual(tartalom(self.cel), _vart_masolat(self.forras))
        for rp in ("Ideas.md", "Attachments/chart.pdf"):
            f, c = os.stat(self.forras / rp), os.stat(self.cel / rp)
            self.assertEqual(c.st_mtime_ns, f.st_mtime_ns)
            if hasattr(f, "st_birthtime"):
                self.assertLessEqual(c.st_birthtime, max(f.st_birthtime, f.st_mtime) + 1)


class VisszaforditasTest(_Alap):
    def test_teljes_visszaforditas_a_kukaba_es_ujraimport(self):
        r = self.importal()
        id = r["munkater_id"]
        reg = workspace.Regiszter(self.alap.path("install"))
        self.assertIn(id, reg.olvas()["munkaterek"])
        v = imp.visszafordit(r["id"], self.alap, kuka=self.kuka)
        self.assertEqual((v["allapot"], v["megtartva"]), ("visszaforditva", []))
        self.assertFalse(self.cel.exists())
        self.assertIn(self.cel / ".manifold", self.kuka.utak)
        self.assertIn(self.cel, self.kuka.utak)
        self.assertNotIn(id, reg.olvas()["munkaterek"])
        # nothing was deleted: the Trash holds the imported tree
        kukaban = [p for p in self.kuka.mappa.iterdir() if p.name.endswith("-Imported")][0]
        self.assertEqual(tartalom(kukaban), _vart_masolat(self.forras))
        self.assertTrue(imp.visszafordit(r["id"], self.alap, kuka=self.kuka)["ismetles"])
        # a new import after the undo starts a fresh journal and works
        r2 = self.importal()
        self.assertEqual(r2["allapot"], "kesz")
        self.assertEqual(tartalom(self.cel), _vart_masolat(self.forras))
        self.assertTrue(list(imp._obsidian_naplo(self.alap, r["id"]).mappa.glob("naplo-*.jsonl")))

    def test_visszaforditas_megtartja_a_modositott_es_az_idegen_fajlt(self):
        r = self.importal()
        (self.cel / "Ideas.md").write_text("Edited after the import\n", encoding="utf-8")
        (self.cel / "Projects" / "New.md").write_text("Written after the import\n", encoding="utf-8")
        v = imp.visszafordit(r["id"], self.alap, kuka=self.kuka)
        self.assertEqual(v["allapot"], "reszben_visszaforditva")
        self.assertEqual({(m["ut"], m["ok"]) for m in v["megtartva"]},
                         {("Ideas.md", "modositott"), ("Projects/New.md", "idegen")})
        maradt = {p.relative_to(self.cel).as_posix() for p in self.cel.rglob("*") if p.is_file()}
        self.assertEqual(maradt, {"Ideas.md", "Projects/New.md"})
        self.assertFalse((self.cel / ".manifold").exists())
        self.assertFalse((self.cel / "Attachments").exists(), "an emptied folder the import created is removed")
        self.assertEqual(imp.allapot(r["id"], self.alap)["allapot"], "reszben_visszaforditva")

    def test_megszakadt_import_visszaforditasa(self):
        eredeti = imp._fajl_masol
        db = {"n": 0}

        def hibas(*a, **k):
            db["n"] += 1
            if db["n"] == 5:
                raise OSError(5, "I/O error")
            return eredeti(*a, **k)

        with mock.patch.object(imp, "_fajl_masol", hibas), self.assertRaises(HttpError):
            self.importal()
        id = self.elonezet()["id"]
        v = imp.visszafordit(id, self.alap, kuka=self.kuka)
        self.assertEqual(v["allapot"], "visszaforditva")
        self.assertFalse(self.cel.exists())

    def test_futo_core_mellett_nem_fordit_vissza(self):
        r = self.importal()
        elotte = ujjlenyomat(self.cel)
        with mock.patch.object(workspace, "_core_zar_fut", return_value=True), self.assertRaises(HttpError) as e:
            imp.visszafordit(r["id"], self.alap, kuka=self.kuka)
        self.assertEqual(e.exception.kod, "import.munkater_hasznalatban")
        self.assertEqual(ujjlenyomat(self.cel), elotte)
        self.assertTrue(workspace.azonosit(self.cel))
        self.assertEqual(self.kuka.utak, [])


class _Busz:
    def __init__(self):
        self.esemenyek = []

    def publish(self, e):
        self.esemenyek.append(e)


class HttpTest(_Alap):
    def setUp(self):
        super().setUp()
        self.r = utvonalak.Regiszter()
        imp.utvonalak(self.r)
        self.app = types.SimpleNamespace(cfg=self.alap, bus=_Busz())

    def hiv(self, metodus, ut, torzs=None, q=None):
        kezelo, m = self.r.keres(metodus, ut)
        return kezelo(utvonalak.Kerees(self.app, None, ut, q or {}, m, torzs=torzs))

    def test_http_elonezet_import_allapot_lista_visszafordit(self):
        t = self.hiv("POST", "/api/import/obsidian/elonezet", {"forras": str(self.forras), "cel": str(self.cel)})
        with self.assertRaises(HttpError) as e:
            self.hiv("POST", "/api/import/obsidian", {"forras": str(self.forras), "cel": str(self.cel), "terv_hash": "x" * 64})
        self.assertEqual(e.exception.kod, "import.terv_valtozott")
        with self.assertRaises(HttpError) as e:
            self.hiv("POST", "/api/import/obsidian", {"forras": str(self.forras), "cel": str(self.cel)})
        self.assertEqual(e.exception.code, 400)
        v = self.hiv("POST", "/api/import/obsidian", {"forras": str(self.forras), "cel": str(self.cel),
                                                     "terv_hash": t["terv_hash"]})
        self.assertIsInstance(v, utvonalak.Valasz)
        self.assertEqual((v.kod, v.obj["allapot"]), (202, "fut"))
        hatarido = time.monotonic() + 60
        while time.monotonic() < hatarido:
            with imp._FUTO_ZAR:
                szal = imp._FUTO.get(t["id"])
            if szal is None:
                break
            szal.join(0.2)
        vege = [e for e in self.app.bus.esemenyek if e.get("allapot")]
        self.assertEqual(vege[-1]["allapot"], "kesz", vege)
        self.assertTrue(any(e.get("lepes") == "masolas" and e.get("kesz_db") == e.get("osszes_db")
                            for e in self.app.bus.esemenyek))
        self.assertTrue(all(e["tipus"] == "import" and e["id"] == t["id"] for e in self.app.bus.esemenyek))
        a = self.hiv("GET", "/api/import/allapot", q={"id": t["id"]})
        self.assertEqual(a["allapot"], "kesz")
        self.assertEqual([x["id"] for x in self.hiv("GET", "/api/import")["importok"]], [t["id"]])
        with self.assertRaises(HttpError) as e:
            self.hiv("GET", "/api/import/allapot", q={"id": "../../etc"})
        self.assertEqual(e.exception.code, 400)
        with mock.patch.object(imp, "_kuka_gyar", return_value=self.kuka):
            vf = self.hiv("POST", "/api/import/visszafordit", {"id": t["id"]})
        self.assertEqual(vf["allapot"], "visszaforditva")
        self.assertFalse(self.cel.exists())

    def test_http_v2_csak_developer_modban(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MOS_FEJLESZTOI_NEZET", None)
            with mock.patch.object(imp, "_fejleszto_mod", return_value=False), self.assertRaises(HttpError) as e:
                self.hiv("POST", "/api/import/v2/elonezet", {"forras": str(self.t)})
        self.assertEqual((e.exception.code, e.exception.kod), (403, "import.fejleszto_mod"))


if __name__ == "__main__":
    unittest.main()
