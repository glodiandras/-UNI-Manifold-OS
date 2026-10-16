"""K308 (55(b), 83. döntés javaslata): az `.apkg` médiájának importja — a kicsomagolás korlátai (soha `extractall`, zip-slip, méret,
összméret, LATEST sha1, fehérlista), a gépi írás `behoz` művelete (szűk forrás és cél, beágyazás, felülírás nélkül, próba a klónba,
visszagörgetés, helyreállítás), és az éles import (egy kör, a jegyzet és a médiája egy tételben, ütközés ` 1` utótaggal és a hivatkozás
átírásával, a bájtra azonos fájl újrahasznosítása, visszavonás az archívumba).

Szintetikus LEGACY_2 és LATEST (zstd: a stdlib `compression.zstd`) csomagok; álvault és ál-`var/`: a valódi vaulthoz és `var/`-hoz
egyik teszt sem nyúl."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from compression import zstd

from core import binaris_naplo, gepi_iras, snapshot, vaultio
from core.tulajdonsagok import Tulajdonsagok
from core.utvonalak import HttpError
from modulok.kartya import apkg
from modulok.kartya import formatum as F
from tests.helpers import alg_core, ir, tmpdir
from tests.test_kartya_api import Alap as ApiAlap
from tests.test_kartya_apkg import _idegen_gyujtemeny, _pb

PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 4
PNG2 = b"\x89PNG\r\n\x1a\n" + bytes(reversed(range(256))) * 4
MP3 = b"ID3\x03\x00" + os.urandom(2048)


def _gyujtemeny(ut: Path, v18: bool = False, kepek=("kep.png",)) -> None:
    """A `_idegen_gyujtemeny` pakli + egy Basic jegyzet, amely a `kepek` mindegyikét `<img>`-ként hivatkozza."""
    _idegen_gyujtemeny(ut, v18=v18)
    c = sqlite3.connect(ut)
    c.create_collation("unicase", lambda a, b: (a.casefold() > b.casefold()) - (a.casefold() < b.casefold()))
    mezo = "Képes kérdés " + "".join(f'<img src="{k}">' for k in kepek) + "\x1fképes válasz"
    c.execute("INSERT INTO notes VALUES (9,'Gx#9',10,0,0,'',?,'',0,0,'')", (mezo,))
    c.execute("INSERT INTO cards VALUES (91,9,5,0,0,0,0,0,9,0,2500,0,0,0,0,0,0,'')")
    c.commit()
    c.close()


def legacy2(ut: Path, gy: Path, media: dict[str, bytes], extra: dict[str, bytes] | None = None, jegyzek: dict | None = None) -> Path:
    """LEGACY_2 csomag: `collection.anki21` + JSON `media` (`{"0": név}`) + a számozott fájlok (deflate)."""
    with zipfile.ZipFile(ut, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(gy, "collection.anki21")
        z.writestr("media", json.dumps(jegyzek if jegyzek is not None else {str(i): n for i, n in enumerate(media)}))
        for i, b in enumerate(media.values()):
            z.writestr(str(i), b)
        for n, b in (extra or {}).items():
            z.writestr(n, b)
    return ut


def latest(ut: Path, gy: Path, bejegyzesek: list[tuple[str, bytes, dict]]) -> Path:
    """LATEST csomag: `meta` 3, zstd-s `collection.anki21b`, zstd-s protobuf `MediaEntries` (név, méret, sha1), zstd-s fájlok.
    A `bejegyzesek` harmadik eleme felülírhatja: `sha1` (bájt vagy None = hiányzik), `meret`, `nyers` (a zip-bejegyzés bájtjai)."""
    jegyzek = b""
    with zipfile.ZipFile(ut, "w") as z:
        z.writestr("meta", b"\x08\x03")
        z.writestr("collection.anki21b", zstd.compress(gy.read_bytes()))
        z.writestr("collection.anki2", b"")
        for i, (nev, b, mod) in enumerate(bejegyzesek):
            sha1 = mod.get("sha1", hashlib.sha1(b).digest())
            e = _pb(1, nev) + _pb(2, mod.get("meret", len(b))) + (_pb(3, sha1) if sha1 is not None else b"")
            jegyzek += _pb(1, e)
            z.writestr(str(i), mod.get("nyers", zstd.compress(b)))
        z.writestr("media", zstd.compress(jegyzek))
    return ut


class KicsomagolasTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.tmp = Path(self._t.name)
        self.gy = self.tmp / "gy.anki21"
        _gyujtemeny(self.gy)
        self.gy18 = self.tmp / "gy.anki21b"
        _gyujtemeny(self.gy18, v18=True)
        self.cel = self.tmp / "ki"

    def okok(self, ki) -> dict[str, str]:
        return {x["nev"]: x["ok"] for x in ki["kihagyva"]}

    def test_legacy2_fehérlista_es_zip_slip(self):
        jegyzek = {"0": "kep.png", "1": "hang.mp3", "2": "rossz.svg", "3": "szkript.html", "4": "../kint.png", "5": "x.exe",
                   "../../kint2": "ok2.png"}
        csomag = self.tmp / "a.apkg"
        with zipfile.ZipFile(csomag, "w") as z:
            z.write(self.gy, "collection.anki21")
            z.writestr("media", json.dumps(jegyzek))
            for k, b in (("0", PNG), ("1", MP3), ("2", b"<svg/>"), ("3", b"<script>"), ("4", PNG), ("5", b"MZ"),
                         ("../../kint2", PNG2), ("../../../tamadas.png", PNG)):
                z.writestr(k, b)
        ki = apkg.media_kicsomagol(csomag, self.cel)
        nevek = {f["nev"]: f for f in ki["fajlok"]}
        self.assertEqual(set(nevek), {"kep.png", "hang.mp3", "ok2.png"})
        self.assertEqual(nevek["kep.png"]["fajl"].read_bytes(), PNG)
        self.assertEqual(nevek["kep.png"]["sha256"], hashlib.sha256(PNG).hexdigest())
        self.assertEqual(nevek["ok2.png"]["fajl"].read_bytes(), PNG2)
        okok = self.okok(ki)
        self.assertEqual(okok["rossz.svg"], "tiltott_kiterjesztes")
        self.assertEqual(okok["szkript.html"], "tiltott_kiterjesztes")
        self.assertEqual(okok["x.exe"], "tiltott_kiterjesztes")
        self.assertEqual(okok["(1 bejegyzés)"], "nem_biztonsagos_nev")              # a `../kint.png` név a jegyzékből kiesett
        # a kicsomagolt fájlok nevei sorszámok, a csomag szövege útként sehol nem szerepel (zip-slip kizárva)
        self.assertTrue(all(p.parent == self.cel and p.name.endswith(".bin") for p in self.cel.iterdir()))
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir()), sorted(["gy.anki21", "gy.anki21b", "ki", "a.apkg"]))
        self.assertFalse((self.tmp.parent / "tamadas.png").exists())
        self.assertFalse((self.tmp.parent / "kint2").exists())

    def test_csak_a_hivatkozott_nevek_es_a_duplikalt_nev(self):
        csomag = legacy2(self.tmp / "b.apkg", self.gy, {}, extra={"0": PNG, "1": PNG2},
                         jegyzek={"0": "kep.png", "1": "KEP.png"})
        ki = apkg.media_kicsomagol(csomag, self.cel, {"kep.png", "KEP.png"})
        self.assertEqual([f["nev"] for f in ki["fajlok"]], ["kep.png"])
        self.assertEqual(self.okok(ki), {"KEP.png": "duplikalt_nev"})               # kis-nagybetűtől független névütközés a csomagon belül
        ki = apkg.media_kicsomagol(csomag, self.tmp / "ki2", {"KEP.png"})
        self.assertEqual([f["nev"] for f in ki["fajlok"]], ["KEP.png"])

    def test_fajlonkenti_es_osszes_meret(self):
        csomag = legacy2(self.tmp / "c.apkg", self.gy, {"a.png": PNG, "b.png": PNG2, "nagy.png": b"\x00" * 5000})
        with mock.patch.object(apkg, "MEDIA_FAJL_MAX", 3000), mock.patch.object(apkg, "MEDIA_OSSZ_MAX", 1500):
            ki = apkg.media_kicsomagol(csomag, self.cel)
        self.assertEqual([f["nev"] for f in ki["fajlok"]], ["a.png"])
        self.assertEqual(self.okok(ki), {"b.png": "osszmeret", "nagy.png": "tul_nagy"})
        self.assertEqual(len(list(self.cel.iterdir())), 1)                            # a kimaradt fájl nem maradt a tmp-ben

    def test_latest_sha1_meret_es_zstd_bomba(self):
        bomba = b"\x00" * 50_000
        csomag = latest(self.tmp / "d.apkg", self.gy18, [
            ("jo.png", PNG, {}),
            ("rossz_sha.png", PNG2, {"sha1": b"\x00" * 20}),
            ("nincs_sha.png", PNG2, {"sha1": None}),
            ("rossz_meret.png", PNG2, {"meret": 7}),
            ("bomba.png", bomba, {"meret": 10}),                                          # a deklaráció hazudik: a kimeneti plafon fogja meg
            ("serult.png", PNG, {"nyers": b"\x28\xb5\x2f\xfd" + b"\xff" * 40}),
        ])
        with mock.patch.object(apkg, "MEDIA_FAJL_MAX", 20_000):
            ki = apkg.media_kicsomagol(csomag, self.cel)
        self.assertEqual(ki["verzio"], apkg.LATEST)
        self.assertEqual([(f["nev"], f["fajl"].read_bytes()) for f in ki["fajlok"]], [("jo.png", PNG)])
        self.assertEqual(self.okok(ki), {"rossz_sha.png": "sha1_elter", "nincs_sha.png": "sha1_hianyzik",
                                         "rossz_meret.png": "meret_elter", "bomba.png": "tul_nagy", "serult.png": "serult"})
        self.assertEqual(len(list(self.cel.iterdir())), 1)

    def test_nevek_es_hivatkozasok(self):
        self.assertEqual(apkg.vault_nev("kép #1 [a].png"), "kép 1 a.png")
        self.assertEqual(apkg.vault_nev("a:b?.jpg"), "ab.jpg")
        self.assertIsNone(apkg.vault_nev(".rejtett.png"))
        self.assertIsNone(apkg.vault_nev("#[].png"))
        self.assertLessEqual(len(apkg.vault_nev("é" * 200 + ".png").encode()), apkg.NEV_MAX)
        self.assertEqual(apkg.hivatkozas_kulcs("a&b.png"), "a&b.png")
        self.assertEqual(apkg.hivatkozas_kulcs("x[1].png"), "x1.png")                  # a `html.fajlnev` alakja
        szoveg = "![[kep.png]] és ![[kep.png|100]] és ![[k%C3%A9p2.png]] és ![[mas.png]]"
        self.assertEqual(apkg.hivatkozas_csere(szoveg, {"kep.png": "kep 1.png", "kép2.png": "kép2.png"}),
                         "![[kep 1.png]] és ![[kep 1.png|100]] és ![[kép2.png]] és ![[mas.png]]")


FM_KISERO = F.ir([F.Kartya("k?", "v", "c-0000cccc", None)], [], modell="", keszult="2026-10-14")


class BehozTest(unittest.TestCase):
    """A gépi írás `behoz` művelete közvetlenül (`GepiIras`), álvaulton."""

    KISERO = "ATTCHMNTS - cards/Teszt — kártyák.md"

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        ir(self.v, "T01 - Történelem/x.md", "---\nTags:\nSource:\nStatus:\nNN:\nCanvas:\n---\n# x\n")
        self.repo = snapshot.repos(self.cfg)["vault"]
        self.repo.init()
        self.repo.commit("alap", {"Mos-Forras": "kezi"})
        self.V = vaultio.Vault(self.cfg)
        self.G = gepi_iras.GepiIras(self.cfg, self.V, Tulajdonsagok(self.cfg, None), varakozas_mp=0.3)
        self.gyoker = gepi_iras.behoz_gyoker(self.cfg) / "import1"
        self.gyoker.mkdir(parents=True)

    def forras(self, nev="0.bin", b=PNG) -> Path:
        p = self.gyoker / nev
        p.write_bytes(b)
        return p

    def app_json(self, ertek: str) -> None:
        (self.v / ".obsidian" / "app.json").write_text(json.dumps({"attachmentFolderPath": ertek}), encoding="utf-8")

    def keres(self, *muveletek, forras="mos-kartya", proba=False, kor="KARTYA-20261014-120000", tetel=None):
        return {"kor": kor, "tetel": tetel or self.KISERO, "forras": forras, "modell": None, "proba": proba,
                "muveletek": list(muveletek)}

    def jegyzet(self, *nevek):
        return {"tipus": "uj", "ut": self.KISERO, "osztaly": "kartya",
                "tartalom": FM_KISERO + "".join(f"\n![[{n}]]\n" for n in nevek)}

    def behoz(self, p: Path, ut="kep.png"):
        return {"tipus": "behoz", "forras": str(p), "ut": ut, "sha256": binaris_naplo.kivonat(p)}

    def test_behoz_rekord_es_visszavonas_az_archivumba(self):
        p = self.forras()
        r = self.G.ir(self.keres(self.jegyzet("kep.png"), self.behoz(p)))
        self.assertEqual(r["behozva"], ["kep.png"])
        self.assertEqual((self.v / "kep.png").read_bytes(), PNG)
        self.assertFalse(p.exists())                                                   # a saját tmp fájlunk költözött (nem másolat)
        self.assertEqual(self.repo.changed_files(r["sha"]), [self.KISERO])            # a média a pillanatképben nincs (14.)
        rec = binaris_naplo.olvas(binaris_naplo.naplo_ut(self.cfg))[-1]
        self.assertEqual((rec["commit"], rec["tipus"], rec["fajlok"], rec["sha256"], rec["meret"]),
                         (r["sha"], "apkg", ["kep.png"], {"kep.png": hashlib.sha256(PNG).hexdigest()}, {"kep.png": len(PNG)}))
        self.repo.undo_commit(r["sha"])
        v = binaris_naplo.visszavonas_utan(self.cfg, self.repo, r["sha"], None, log=lambda s: None)
        self.assertEqual(len(v["mozgatva"]), 1, v)
        self.assertFalse((self.v / "kep.png").exists())
        archiv = Path(v["mozgatva"][0][1])
        self.assertEqual(archiv.read_bytes(), PNG)                                     # nem törlődött: az archívumban
        self.assertTrue(archiv.is_relative_to(self.cfg.path("apkg_visszavont")))
        self.assertTrue((self.cfg.path("apkg_visszavont") / "INDOK.md").is_file())
        v2 = binaris_naplo.visszavonas_utan(self.cfg, self.repo, r["sha"], None, log=lambda s: None)
        self.assertEqual((v2["mozgatva"], v2["hianyzik"]), ([], ["kep.png"]))         # idempotens

    def test_atirt_fajl_a_visszavonaskor_a_helyen_marad(self):
        p = self.forras()
        r = self.G.ir(self.keres(self.jegyzet("kep.png"), self.behoz(p)))
        (self.v / "kep.png").write_bytes(PNG2)
        self.repo.undo_commit(r["sha"])
        v = binaris_naplo.visszavonas_utan(self.cfg, self.repo, r["sha"], None, log=lambda s: None)
        self.assertEqual(v["mozgatva"], [])
        self.assertEqual(v["marad"][0][0], "kep.png")
        self.assertEqual((self.v / "kep.png").read_bytes(), PNG2)

    def test_attachmentfolderpath_relativ_es_mappa(self):
        self.app_json("./")
        p = self.forras()
        with self.assertRaises(vaultio.Invalid):                                       # a gyökér nem a jegyzet csatolmány-mappája
            self.G.ir(self.keres(self.jegyzet("kep.png"), self.behoz(p)))
        r = self.G.ir(self.keres(self.jegyzet("kep.png"), self.behoz(p, "ATTCHMNTS - cards/kep.png")))
        self.assertTrue((self.v / "ATTCHMNTS - cards" / "kep.png").is_file(), r)
        self.app_json("Mellékletek/Képek")
        p2 = self.forras("1.bin", PNG2)
        r = self.G.ir(self.keres({"tipus": "uj", "ut": "ATTCHMNTS - cards/Más — kártyák.md", "osztaly": "kartya",
                                  "tartalom": FM_KISERO.replace("c-0000cccc", "c-0000dddd") + "\n![[k2.png|200]]\n"},
                                 self.behoz(p2, "Mellékletek/Képek/k2.png"), tetel="masik"))
        self.assertEqual((self.v / "Mellékletek" / "Képek" / "k2.png").read_bytes(), PNG2, r)

    def test_elutasitasok(self):
        p = self.forras()
        esetek = {
            "idegen forrás": (self.keres(self.jegyzet("kep.png"), self.behoz(p), forras="mos-fuzet"), vaultio.Invalid),
            "nincs beágyazva": (self.keres(self.jegyzet("mas.png"), self.behoz(p)), vaultio.Invalid),
            "más mappa": (self.keres(self.jegyzet("kep.png"), self.behoz(p, "T01 - Történelem/kep.png")), vaultio.Invalid),
            "svg": (self.keres(self.jegyzet("kep.svg"), self.behoz(p, "kep.svg")), vaultio.Invalid),
            "szöveg nélkül": (self.keres(self.behoz(p)), vaultio.Invalid),
            "tiltott név": (self.keres(self.jegyzet("k#p.png"), self.behoz(p, "k#p.png")), vaultio.Invalid),
        }
        for nev, (k, hiba) in esetek.items():
            with self.subTest(nev), self.assertRaises(hiba):
                self.G.ir(k)
        kint = Path(self._t.name) / "kint.bin"                                         # a kicsomagoló gyökerén kívüli forrás
        kint.write_bytes(PNG)
        with self.assertRaises(vaultio.Invalid):
            self.G.ir(self.keres(self.jegyzet("kep.png"), self.behoz(kint)))
        (self.gyoker / "link.bin").symlink_to(kint)                                    # symlink a gyökér alatt
        with self.assertRaises(vaultio.NotFound):
            self.G.ir(self.keres(self.jegyzet("kep.png"), {**self.behoz(kint), "forras": str(self.gyoker / "link.bin")}))
        rossz_sha = {**self.behoz(p), "sha256": "0" * 64}
        with self.assertRaises(vaultio.Conflict):
            self.G.ir(self.keres(self.jegyzet("kep.png"), rossz_sha))
        self.assertTrue(p.is_file())
        self.assertFalse((self.v / "kep.png").exists())
        self.assertFalse((self.v / self.KISERO).exists())

    def test_nem_ir_felul_kis_nagybetu_es_nfd(self):
        ir(self.v, "KÉP.png", b"regi", mod="wb")
        p = self.forras()
        for ut in ("KÉP.png", "kép.png", "kép.png"):
            with self.subTest(ut), self.assertRaises(vaultio.Conflict):
                self.G.ir(self.keres(self.jegyzet(ut), self.behoz(p, ut)))
        self.assertEqual((self.v / "KÉP.png").read_bytes(), b"regi")
        self.assertTrue(p.is_file())

    def test_proba_a_klonba_masol(self):
        p = self.forras()
        r = self.G.ir(self.keres(self.jegyzet("kep.png"), self.behoz(p), proba=True))
        self.assertTrue(r["proba"])
        self.assertFalse((self.v / "kep.png").exists())                               # az éles vault érintetlen
        self.assertTrue(p.is_file())                                                   # a forrás marad (másolat)
        self.assertEqual((Path(r["proba_mappa"]) / self.v.name / "kep.png").read_bytes(), PNG)
        self.assertEqual(binaris_naplo.olvas(binaris_naplo.naplo_ut(self.cfg)), [])     # próbában nincs bináris rekord

    def test_hiba_utan_a_media_visszakoltozik(self):
        p = self.forras()
        with mock.patch.object(gepi_iras.GepiIras, "_fajl_ir", side_effect=OSError("lemez")), self.assertRaises(OSError):
            self.G.ir(self.keres(self.jegyzet("kep.png"), self.behoz(p)))
        self.assertEqual(p.read_bytes(), PNG)                                          # vissza a kicsomagoló mappába
        self.assertFalse((self.v / "kep.png").exists())
        self.assertFalse((self.cfg.path("run") / gepi_iras.NAPLO).exists())

    def test_helyreallitas_az_archivumba_ha_a_tmp_eltunt(self):
        (self.v / "kep.png").write_bytes(PNG)
        d = self.cfg.path("run") / gepi_iras.NAPLO
        (d / "eredeti").mkdir(parents=True)
        uj = FM_KISERO.encode()
        (d / "eredeti" / "0.bin").write_bytes(uj)
        (self.v / self.KISERO).parent.mkdir(parents=True, exist_ok=True)
        (self.v / self.KISERO).write_bytes(uj)
        terv = {"verzio": 1, "kor": "KARTYA-20261014-120000", "tetel": self.KISERO, "forras": "mos-kartya", "feladat": None,
                "fajlok": [{"ut": self.KISERO, "lemez": self.KISERO, "eredeti": "0.bin", "uj_fajl": True,
                            "uj_sha1": vaultio.sha1(uj), "mappak": []}],
                "mozgasok": [{"ut": "kep.png", "lemez": "kep.png", "forras": str(self.gyoker / "eltunt" / "0.bin"),
                              "sha256": hashlib.sha256(PNG).hexdigest(), "masolat": False, "klon": False, "behoz": True}]}
        (d / "terv.json").write_text(json.dumps(terv), encoding="utf-8")
        uzenetek = gepi_iras.helyreallit(self.cfg)
        self.assertIn("was restored", uzenetek[0])
        self.assertFalse((self.v / "kep.png").exists())
        self.assertFalse((self.v / self.KISERO).exists())
        archivalt = list((self.cfg.path("apkg_visszavont") / "KARTYA-20261014-120000").iterdir())
        self.assertEqual([a.read_bytes() for a in archivalt], [PNG])                   # nem törlődött


class ImportApiTest(ApiAlap):
    """Az éles import a core API-ján át (`POST /api/kartya/import`), a médiával."""

    def csomag(self, media: dict[str, bytes], kepek=("kep.png",), nev="m.apkg") -> Path:
        gy = Path(self._t.name) / f"{nev}.anki21"
        _gyujtemeny(gy, kepek=kepek)
        return legacy2(Path(self._t.name) / nev, gy, media)

    def import_(self, csomag: Path, proba=False):
        kod, d = self.k("POST", "/api/kartya/import", {"fajl": str(csomag), "proba": proba})
        self.assertEqual(kod, 200, d)
        return d

    def kisero(self) -> str:
        return (self.v / "ATTCHMNTS - cards" / "1848 — kártyák.md").read_text(encoding="utf-8")

    def tmp_ures(self):
        g = gepi_iras.behoz_gyoker(self.cfg)
        self.assertEqual(list(g.iterdir()) if g.exists() else [], [])

    def test_proba_csak_terv(self):
        csomag = self.csomag({"kep.png": PNG, "felesleg.png": PNG2})
        d = self.import_(csomag, proba=True)
        mj = d["media_jelentes"]
        self.assertEqual([x["nev"] for x in mj["hozzaadva"]], ["kep.png"])
        self.assertEqual(mj["osszesites"], {"nem_hivatkozott": 1})
        self.assertEqual(d["media_nem_importalt"], 1)
        self.assertFalse((self.v / "kep.png").exists())
        self.assertFalse((self.v / "ATTCHMNTS - cards" / "1848 — kártyák.md").exists())
        self.tmp_ures()

    def test_eles_import_egy_tetel_es_visszavonas(self):
        csomag = self.csomag({"kep.png": PNG, "felesleg.png": PNG2})
        elotte = len(self.repo.log())
        d = self.import_(csomag)
        self.assertEqual((self.v / "kep.png").read_bytes(), PNG)                       # a csatolmány-mappa alapja a gyökér ("/")
        self.assertFalse((self.v / "felesleg.png").exists())                           # a nem hivatkozott nem kerül be (I40)
        self.assertIn("![[kep.png]]", self.kisero())
        self.assertEqual(d["irasok"][0]["media"], ["kep.png"])
        self.assertEqual(len(self.repo.log()) - elotte, 1)                             # egy kör, egy tétel, egy commit
        c = self.repo.log(1)[0]
        self.assertEqual(c.trailers.get("Mos-Forras"), "mos-kartya")
        self.tmp_ures()
        kod, v = self.k("POST", "/api/pillanat/vault/visszavonas", {"kor": d["irasok"][0]["kor"]})
        self.assertEqual(kod, 200, v)
        self.assertEqual(v["media"]["visszakoltoztetve"], 1)
        self.assertFalse((self.v / "kep.png").exists())
        self.assertFalse((self.v / "ATTCHMNTS - cards" / "1848 — kártyák.md").exists())
        archivalt = list(self.cfg.path("apkg_visszavont").rglob("kep.png"))
        self.assertEqual([a.read_bytes() for a in archivalt], [PNG])

    def test_utkozes_atnevez_es_atirja_a_hivatkozast(self):
        ir(self.v, "M10 - Sorozatok/kep.png", b"mas tartalom", mod="wb")
        csomag = self.csomag({"kep.png": PNG})
        d = self.import_(csomag)
        mj = d["media_jelentes"]
        self.assertEqual(mj["atnevezve"], [{"nev": "kep.png", "ut": "kep 1.png", "ok": "utkozes"}])
        self.assertEqual((self.v / "kep 1.png").read_bytes(), PNG)
        self.assertEqual((self.v / "M10 - Sorozatok" / "kep.png").read_bytes(), b"mas tartalom")   # nem írtuk felül
        szoveg = self.kisero()
        self.assertIn("![[kep 1.png]]", szoveg)
        self.assertNotIn("![[kep.png]]", szoveg)

    def test_azonos_fajl_ujrahasznosul(self):
        ir(self.v, "kep.png", PNG, mod="wb")
        d = self.import_(self.csomag({"kep.png": PNG}))
        mj = d["media_jelentes"]
        self.assertEqual((mj["mar_megvan"], mj["hozzaadva"], d["irasok"][0]["media"]), ([{"nev": "kep.png", "ut": "kep.png"}], [], []))
        self.assertIn("![[kep.png]]", self.kisero())
        self.assertEqual(binaris_naplo.olvas(binaris_naplo.naplo_ut(self.cfg)), [])     # a meglévő fájl nem kerül a rekordba

    def test_latest_csatolmany_mappa_a_jegyzet_mellett(self):
        (self.v / ".obsidian" / "app.json").write_text(json.dumps({"attachmentFolderPath": "./"}), encoding="utf-8")
        gy = Path(self._t.name) / "l.anki21b"
        _gyujtemeny(gy, v18=True, kepek=("kép[1].png", "rossz.svg"))
        csomag = latest(Path(self._t.name) / "l.apkg", gy, [("kép[1].png", PNG, {}), ("rossz.svg", b"<svg/>", {}),
                                                            ("kep.png", PNG2, {"sha1": b"\x01" * 20})])
        d = self.import_(csomag)
        mj = d["media_jelentes"]
        self.assertEqual(mj["atnevezve"], [{"nev": "kép[1].png", "ut": "ATTCHMNTS - cards/kép1.png", "ok": "nev_tisztitva"}])
        self.assertEqual({x["nev"]: x["ok"] for x in mj["kihagyva"]}, {"rossz.svg": "tiltott_kiterjesztes", "kep.png": "sha1_elter"})
        self.assertEqual((self.v / "ATTCHMNTS - cards" / "kép1.png").read_bytes(), PNG)
        self.assertFalse((self.v / "ATTCHMNTS - cards" / "kep.png").exists())            # a hibás sha1-ű SM-2 kártya képe nem jött be
        self.assertIn("![[kép1.png]]", self.kisero())

    def test_a_vegpont_nem_fogad_behozt(self):
        g = gepi_iras.behoz_gyoker(self.cfg) / "kezzel"
        g.mkdir(parents=True)
        (g / "0.bin").write_bytes(PNG)
        kod, d = self.k("POST", "/api/gepi-iras", {
            "kor": "KARTYA-20261014-130000", "tetel": "t", "forras": "mos-kartya", "modell": None,
            "muveletek": [{"tipus": "uj", "ut": "ATTCHMNTS - cards/X — kártyák.md", "osztaly": "kartya",
                           "tartalom": FM_KISERO + "\n![[kep.png]]\n"},
                          {"tipus": "behoz", "forras": str(g / "0.bin"), "ut": "kep.png", "sha256": hashlib.sha256(PNG).hexdigest()}]})
        self.assertEqual(kod, 400, d)
        self.assertFalse((self.v / "kep.png").exists())


if __name__ == "__main__":
    unittest.main()
