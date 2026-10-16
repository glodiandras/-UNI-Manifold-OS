"""A lépés-token és a szerkesztői írási végpontok kapuja (C29.8, T137; CLAUDE.md 28(a)): a feladat lépés-folyamata saját
tokent kap (`MOS_LEPES_TOKEN`), amelyet a `gepi_kliens` az `X-Manifold` fejlécben küld — a lépés a felületi API-titkot (35. döntés)
nem kapja meg, így a token az ő hitelesítője; a core ilyen kérésnél minden nem olvasó végpontot elutasít (403), kivéve a gépi írást és
a tiszta, nem író számoló végpontokat — így a 28(a) („gép csak a gépi-írás szolgáltatáson át ír”) nem csupán konvenció."""
import ast
import os
import re
import unittest
from pathlib import Path
from unittest import mock

from core import lepes_kapu, server, tasks
from tests.helpers import REPO, alg_core, tmpdir

# A döntéstábla: a core minden nem-GET végpontja VAGY a lépés-folyamat számára engedett (`lepes_kapu.ENGEDELYEZETT`), VAGY itt, tiltottként
# szerepel. Egy új író végpont, amely egyik helyen sincs, bukó teszt: a hozzáadó dönti el, hívhatja-e egy lánc.
TILTOTT = {
    ('POST', '/api/vault/tulajdonsagok/tipus'),  # F11: explicit felhasználói vault-típusválasztás.
    ('PUT', '/api/beallitasok'),  # F5: Setup/privacy/modules are user choices, never machine-step actions.
    # CX: csak a felület indíthatja ezeket, gépi lépés nem.
    ('POST', '/api/vault/import'),
    ('POST', '/api/vault/mappa'),
    ('POST', '/api/vault/kuka'),
    ('PUT', '/api/felkeszultseg/keret'),
    ('POST', '/api/asszisztens/kiegeszites'),
    ('POST', '/api/asszisztens/kiegeszites/elvet'),
    ('POST', '/api/asszisztens/kiegeszites/elfogad'),
    ('POST', '/api/asszisztens/mintak/tanit'),
    ('POST', '/api/asszisztens/mintak/torles'),
    # J1–J3: a tanuló mag és a javaslat-kártya a felület művelete ({state}-et ír, a vaultot nem); gépi lépés nem hívja
    ('POST', '/api/asszisztens/tanul'),
    ('POST', '/api/asszisztens/tanult/torles'),
    ('POST', '/api/asszisztens/kartya'),
    ('POST', '/api/asszisztens/kartya/dontes'),

    ("POST", "/api/aktivitas"), ("POST", "/api/emlekezteto/utkozes/latva"), ("POST", "/api/feladatok"),
    ("POST", r"/api/feladatok/([\w.-]+)/leallitas"), ("POST", "/api/naplo/ma"), ("POST", r"/api/naptar/javaslat/(\d+)/elvet"),
    ("POST", r"/api/naptar/javaslat/(\d+)/jovahagy"), ("POST", "/api/naptar/kategoria"), ("POST", "/api/naptar/szinkron"),
    ("POST", "/api/pdf/kiemeles"), ("POST", "/api/pdf/kiemeles/torol"), ("POST", r"/api/pillanat/(\w+)/visszavonas"),
    ("POST", "/api/tracker/esemenyek"), ("POST", "/api/tracker/export"), ("POST", "/api/tracker/torles"),
    ("POST", "/api/vault/atnevezes"), ("POST", "/api/vault/elozmeny/visszaallit"), ("POST", "/api/vault/uj"),
    ("POST", "/api/sablon/uj"),                              # C32b: új jegyzet sablonból = vault-író, a lépés nem hívja
    ("PUT", "/api/felulet/allapot"), ("PUT", "/api/vault/fajl"), ("PUT", "/api/vezerlo/kapcsolok"),
    # a cloud-main végpontjai (Mac-integráció 2026-10-07): mind felületi művelet, a lépés-folyamat nem hívja (default-deny)
    ("POST", "/api/asszisztens/dontes"), ("POST", "/api/asszisztens/emlitesek"), ("POST", "/api/asszisztens/higienia/latva"),
    ("POST", "/api/asszisztens/statisztika/torles"), ("POST", "/api/asszisztens/szokas/dontes"),
    ("POST", "/api/cpp/ellenoriz"), ("POST", "/api/cpp/feladat"), ("POST", "/api/cpp/formaz"), ("POST", "/api/cpp/megszakit"),
    ("POST", "/api/cpp/ai"), ("POST", "/api/cpp/ai/megszakit"), ("POST", "/api/cpp/ai/tipp"),   # C36b: csak a felület kattintása
    ("POST", "/api/grafikon/elemzes"), ("POST", "/api/kviz/jelol"), ("POST", "/api/kviz/kitoltes"), ("POST", "/api/kviz/megoldas"),
    ("POST", "/api/kereses/kerdezz"),                       # C25b: a felület kérdése; a lépés nem hívja (default-deny)
    ("POST", "/api/kereses/hasonlosag"),                    # C25c: nem ír, de a C30b felületé; a lépés nem hívja (default-deny)
    ("POST", "/api/grafikon/tiltolista/levesz"),             # C35b: a felhasználó leveszi a tiltólistáról; a lépés nem hívja
    # C24b: tiszta, nem író számoló (a margójel), de csak a felület hívja — a megoldás-lépés a homokozót maga futtatja (default-deny)
    ("POST", "/api/matek/levezetes"),
    # C21: a füzetfotó feltöltése (a beérkező mappába) és a képlet-OCR (a vágólap + a modell) felületi művelet; a lépés nem hívja
    ("POST", "/api/fuzet/bejovo"), ("POST", "/api/keplet-ocr"),
    ("POST", "/api/video/bejovo"),                                      # C20b: a behúzott videó feltöltése (felületi művelet)
    # C23b: az értékelés, a visszavonás, az export és az import a felület művelete; a kártya-lépés a gépi írással ír (default-deny)
    ("POST", "/api/kartya/valasz"), ("POST", "/api/kartya/visszavon"), ("POST", "/api/kartya/export"), ("POST", "/api/kartya/import"),
    # C26b: a kontextus-csomag és a külső AI válaszának feldolgozása csak olvas, de a felület művelete (a lépés nem hívja: default-deny)
    ("POST", "/api/osszefoglalas/kontextus"), ("POST", "/api/osszefoglalas/valasz"),
    # C28b: a szöveges értékelés nem ír, de modellt hív és a felület kattintása; a lépés nem hívja (default-deny)
    ("POST", "/api/felkeszultseg/ertekeles"),
}


class DontesTablaTest(unittest.TestCase):
    def nem_get(self):
        return {(m, u) for m, u, _ in server.regiszter_epit().vegpontok() if m not in ("GET", "HEAD")}

    def test_minden_nem_olvaso_vegpont_dontest_kap(self):
        dontott = lepes_kapu.ENGEDELYEZETT | TILTOTT
        self.assertEqual(self.nem_get() - dontott, set(),
                         "új író végpont: döntsd el, hívhatja-e a lépés-folyamat (28(a)), és vedd fel a `lepes_kapu.ENGEDELYEZETT` "
                         "vagy a tábla `TILTOTT` halmazába")
        self.assertEqual(dontott - self.nem_get(), set(), "elavult sor a döntéstáblában")
        self.assertEqual(lepes_kapu.ENGEDELYEZETT & TILTOTT, set())

    def test_a_gepi_iras_es_a_tiszta_szamolok_engedettek_a_szerkesztoi_iras_nem(self):
        for m, u in (("POST", "/api/gepi-iras"), ("POST", "/api/vault/tulajdonsagok/modosit"), ("POST", "/api/vault/bazis/lekerdez"),
                     ("POST", "/api/vault/atnevezes/terv"), ("POST", "/api/vault/feloldas"), ("POST", "/api/sablon/kiertekel"),
                     ("POST", "/api/vault/tulajdonsagok/osszefesul"), ("GET", "/api/vault/fajl"), ("HEAD", "/api/vault/fajl")):
            self.assertTrue(lepes_kapu.engedelyezett(m, u), (m, u))
        for m, u in (("PUT", "/api/vault/fajl"), ("POST", "/api/vault/uj"), ("POST", "/api/vault/atnevezes"), ("POST", "/api/sablon/uj"),
                     ("POST", "/api/vault/elozmeny/visszaallit"), ("POST", "/api/pillanat/vault/visszavonas"),
                     ("POST", "/api/pdf/kiemeles"), ("POST", "/api/feladatok"), ("PUT", "/api/felulet/allapot"), ("PUT", "/api/beallitasok")):
            self.assertFalse(lepes_kapu.engedelyezett(m, u), (m, u))


class ForraskodTest(unittest.TestCase):
    """A lánc-kód (`modulok/`, `core/probafeladat.py`) nem hivatkozik szerkesztői író végpontra, és nem importálja a vaultot író
    core-modulokat — a vaultba a `gepi_kliens` a gépi írás szolgáltatásán át ír (28(a))."""
    TILTOTT_UTAK = ("/api/vault/fajl", "/api/vault/uj", "/api/vault/atnevezes", "/api/vault/elozmeny", "/api/pdf/kiemeles",
                    "/api/naplo/ma", "/api/pillanat/", "/api/vault/tulajdonsagok/tipus")
    TILTOTT_MODULOK = {"vaultio", "atnevezes", "elozmeny", "pdfkiemeles", "naplo", "snapshot", "frame", "tulajdonsagok", "tulajdonsag_tipusok"}
    # Szűk, megnevezett kivételek (Mac-integráció 2026-10-07): (1) író kód nélküli állandó: a H1-előtag regexe (L46) egyetlen helyen
    # él, a kvíz és a forráshűség-kapu csak a mintát olvassa; (2) a videólánc (47. döntés) a SAJÁT ytdlp pillanatkép-tárát rögzíti
    # (`var/ytdlp.git`, a kód és a staging), nem a vaultot — a vaultba a lánc nem ír (47(c)).
    ENGEDETT_NEVEK = {("vaultio", "_H1_ELOTAG")}
    ENGEDETT_FAJL_MODUL = {("modulok/ytdlp/lanc.py", "frame"), ("modulok/ytdlp/lanc.py", "snapshot")}
    # (3) a pillanatkép-napló OLVASÁSA (`GET /api/pillanat/<tár>/naplo`; a C35b tiltólistája a visszavonásokat innen látja) nem írás
    OLVASO_UT = re.compile(r"/api/pillanat/[^/\s`]*/naplo\b")

    @classmethod
    def _tiltott_szoveg(cls, szoveg: str) -> bool:
        return any(u in cls.OLVASO_UT.sub("", szoveg) for u in cls.TILTOTT_UTAK)

    @classmethod
    def talalatok(cls, forras: str, nev: str = "<teszt>") -> list[str]:
        ki = []
        fa = ast.parse(forras, filename=nev)
        kezelt = set()                                    # az f-sztring darabjai együtt ítélendők (a `{tar}` helyén bármi)
        for n in ast.walk(fa):
            if isinstance(n, ast.JoinedStr):
                darabok = [d.value if isinstance(d, ast.Constant) else "x" for d in n.values]
                kezelt.update(id(d) for d in n.values)
                if cls._tiltott_szoveg("".join(darabok)):
                    ki.append(f"{nev}:{n.lineno} végpont: {''.join(darabok)[:60]}")
        for n in ast.walk(fa):
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in kezelt and cls._tiltott_szoveg(n.value):
                ki.append(f"{nev}:{n.lineno} végpont: {n.value[:60]}")
            if isinstance(n, ast.ImportFrom):
                mod = (n.module or "")
                nevek = [a.name for a in n.names if (nev, a.name) not in cls.ENGEDETT_FAJL_MODUL]
                if (mod == "core" or (n.level and not mod)) and any(a in cls.TILTOTT_MODULOK for a in nevek):
                    ki.append(f"{nev}:{n.lineno} import: {', '.join(nevek)}")
                utolso = mod.split(".")[-1]
                if utolso in cls.TILTOTT_MODULOK and (mod.startswith("core.") or n.level) and \
                        not all((utolso, a.name) in cls.ENGEDETT_NEVEK for a in n.names):
                    ki.append(f"{nev}:{n.lineno} import: {mod}")
            if isinstance(n, ast.Import):
                for a in n.names:
                    if a.name.startswith("core.") and a.name.split(".")[-1] in cls.TILTOTT_MODULOK:
                        ki.append(f"{nev}:{n.lineno} import: {a.name}")
        return ki

    def test_a_kereso_felismeri_a_tiltott_hivatkozast(self):
        self.assertTrue(self.talalatok("u = '/api/vault/fajl?ut=x'"))
        self.assertTrue(self.talalatok("from core import vaultio"))
        self.assertTrue(self.talalatok("from core.vaultio import Vault"))
        self.assertTrue(self.talalatok("import core.atnevezes"))
        self.assertTrue(self.talalatok("from core.vaultio import _H1_ELOTAG, Vault"))
        self.assertEqual(self.talalatok("from core.vaultio import _H1_ELOTAG"), [])
        self.assertEqual(self.talalatok("u = f'/api/pillanat/{tar}/naplo?n=5'"), [])
        self.assertTrue(self.talalatok("u = f'/api/pillanat/{tar}/visszavonas'"))
        self.assertTrue(self.talalatok("u = '/api/pillanat/vault/visszavonas'"))
        self.assertTrue(self.talalatok("from core import frame", "modulok/kviz/x.py"))
        self.assertEqual(self.talalatok("from core import frame, snapshot", "modulok/ytdlp/lanc.py"), [])
        self.assertEqual(self.talalatok("from core import gepi_kliens\nu = '/api/gepi-iras'"), [])

    def test_a_lanc_kod_nem_ir_a_szerkesztoi_uton(self):
        fajlok = sorted((REPO / "modulok").rglob("*.py")) + [REPO / "core" / "probafeladat.py"]
        self.assertGreaterEqual(len(fajlok), 2)
        ki = []
        for p in fajlok:
            ki += self.talalatok(p.read_text(encoding="utf-8"), str(p.relative_to(REPO)))
        self.assertEqual(ki, [], "a lánc-kód a gépi-írás szolgáltatáson át ír (core/gepi_kliens.py), nem a szerkesztői úton")



class KornyezetTest(unittest.TestCase):
    """K149 (Audit 3 A3-12): a lépés környezete a core `os.environ`-jából csak a fehérlistát örökli (`lepes_kapu.orokolheto`)."""

    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, _ = alg_core(self._t.name)
        self.q = tasks.Queue(self.cfg, start_delay=3600)
        self.addCleanup(self.q.close)

    def env(self, kornyezet, jogok=lepes_kapu.JOGOK_GEPI, extra=None, token="lepes-token-0123456789"):
        with mock.patch.dict(os.environ, kornyezet):
            return self.q._env("F-20261007-0001", Path("/stop"), extra, token, jogok)

    def test_a_titkok_es_a_fehérlistan_kivuli_valtozok_nem_jutnak_at(self):
        e = self.env({"MOS_API_TITOK": "felulet-titka-0123456789", "TITKOS_X": "1", "MOS_VALAMI_TOKEN": "t", "MOS_JELSZO": "j",
                      "AWS_SECRET_ACCESS_KEY": "a", "GITHUB_TOKEN": "g", "DYLD_INSERT_LIBRARIES": "/x.dylib", "NODE_OPTIONS": "--x",
                      "MOS_LEPES_TOKEN": "orokolt"})
        for k in ("MOS_API_TITOK", "TITKOS_X", "MOS_VALAMI_TOKEN", "MOS_JELSZO", "AWS_SECRET_ACCESS_KEY", "GITHUB_TOKEN",
                  "DYLD_INSERT_LIBRARIES", "NODE_OPTIONS"):
            self.assertNotIn(k, e, k)
        self.assertEqual(e["MOS_LEPES_TOKEN"], "lepes-token-0123456789", "a lépés a saját tokenjét kapja, nem az örököltet")

    def test_a_fehérlista_atjut(self):
        e = self.env({"MOS_VAULT": "/v", "MOS_STATE": "/s", "LC_ALL": "hu_HU.UTF-8", "LANG": "hu_HU.UTF-8", "HTTPS_PROXY": "http://p:1",
                      "https_proxy": "http://p:1", "SSL_CERT_FILE": "/etc/ssl/cert.pem", "MANIFOLD_MODELL_ZAR": "/z.lock",
                      "XDG_CACHE_HOME": "/c", "TMPDIR": "/t", "PATH": "/usr/bin:/bin", "HOME": "/h"})
        for k, v in (("MOS_VAULT", "/v"), ("MOS_STATE", "/s"), ("LC_ALL", "hu_HU.UTF-8"), ("HTTPS_PROXY", "http://p:1"),
                     ("https_proxy", "http://p:1"), ("SSL_CERT_FILE", "/etc/ssl/cert.pem"), ("MANIFOLD_MODELL_ZAR", "/z.lock"),
                     ("XDG_CACHE_HOME", "/c"), ("TMPDIR", "/t"), ("PATH", "/usr/bin:/bin"), ("HOME", "/h"), ("LANG", "hu_HU.UTF-8")):
            self.assertEqual(e.get(k), v, k)

    def test_a_rogzitett_es_az_extra_kulcsok(self):
        e = self.env({"PYTHONPATH": "/kulso"}, extra={"MOS_WORKER_URL": "http://127.0.0.1:2", "MOS_API_TITOK": "extra-titok-0123456789"})
        self.assertEqual(e["MOS_WORKER_URL"], "http://127.0.0.1:2")
        self.assertNotIn("MOS_API_TITOK", e, "az `extra`-ból sem")
        self.assertEqual(e["MOS_FELADAT"], "F-20261007-0001")
        self.assertEqual(e["MANIFOLD_STOP_FAJL"], "/stop")
        self.assertEqual(e["HF_HUB_OFFLINE"], "1")
        self.assertEqual(e["PYTHONPATH"], str(self.cfg.root) + os.pathsep + "/kulso")

    def test_a_nincs_es_az_ismeretlen_jogkeszlet_se_tokent_se_core_cimet(self):
        for jogok in (lepes_kapu.JOGOK_NINCS, "admin", None, ""):
            e = self.env({"MOS_CORE_PORT": "1", "MOS_LEPES_TOKEN": "orokolt"}, jogok, extra={"MOS_CORE_URL": "http://127.0.0.1:1"})
            for k in ("MOS_LEPES_TOKEN", "MOS_CORE_URL", "MOS_CORE_PORT"):
                self.assertNotIn(k, e, (jogok, k))
        e = self.env({"MOS_CORE_PORT": "1"}, extra={"MOS_CORE_URL": "http://127.0.0.1:1"})
        self.assertEqual(e["MOS_CORE_URL"], "http://127.0.0.1:1")

    def test_titok_jellegu_es_orokolheto(self):
        for n in ("MOS_API_TITOK", "MOS_LEPES_TOKEN", "MOS_X_SECRET", "mos_jelszo", "MANIFOLD_PASSWORD"):
            self.assertTrue(lepes_kapu.titok_jellegu(n), n)
            self.assertFalse(lepes_kapu.orokolheto(n), n)
        for n in ("MOS_VAULT", "MOS_ROOT", "MOS_KEZI_RIPORT", "MOS_NAPTAR_SEGED", "MANIFOLD_MODELL_KERET_GB"):
            self.assertTrue(lepes_kapu.orokolheto(n), n)
        for n in ("VIRTUAL_ENV", "DYLD_LIBRARY_PATH", "UV_CACHE_DIR", "NODE_OPTIONS", "TITKOS_X", "GIT_DIR"):
            self.assertFalse(lepes_kapu.orokolheto(n), n)


if __name__ == "__main__":
    unittest.main()
