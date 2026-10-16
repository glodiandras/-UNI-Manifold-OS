"""Core error bodies keep status/data while publishing English fallbacks and stable codes.

Original Python exception text remains compatible; wire presentation may change.
"""
import errno
import json
import unittest
from pathlib import Path
from unittest import mock

from core import atnevezes, server, tasks, utvonalak, vaultio
from core.utvonalak import HttpError, hiba_torzs, kodos
from tests.test_core_api import _Szerver


class HttpErrorTorzsTest(unittest.TestCase):
    def test_a_regi_hivasok_torzse_valtozatlan(self):
        e = HttpError(409, "a kör-zár foglalt", foglalt=True)
        self.assertEqual(e.torzs(), {"hiba": "a kör-zár foglalt", "foglalt": True})
        self.assertEqual((e.code, e.data, e.kod, e.param), (409, {"foglalt": True}, None, None))
        self.assertEqual(HttpError(404, "nincs ilyen").torzs(), {"hiba": "nincs ilyen"})
        # ugyanaz, mint a régi szerver-képlet: {"hiba": str(e), **e.data}
        for x in (e, HttpError(409, "ütközés", utkozes=True, fajlok=["a.md"]), HttpError(400, "hibás")):
            self.assertEqual(x.torzs(), {"hiba": str(x), **x.data})

    def test_a_regi_kod_kulcsszo_a_torzsbe_kerul_es_az_attributumba_is(self):
        e = HttpError(400, "nincs .cpp megoldás", kod="nincs_cpp")
        self.assertEqual(e.torzs(), {"hiba": "No C++ solution file was found.", "kod": "nincs_cpp"})
        self.assertEqual((e.kod, e.data), ("nincs_cpp", {"kod": "nincs_cpp"}))     # a régi `e.data["kod"]` olvasók működnek
        f = HttpError(409, "mentetlen változás van a fájlban", kod="mentetlen", utak=["a.cpp"])
        self.assertEqual(f.torzs(), {"hiba": "The file has unsaved changes. Save it first.", "kod": "mentetlen", "utak": ["a.cpp"]})

    def test_kod_es_param_a_hiba_utan_az_adat_elott(self):
        e = HttpError(503, "a vault nem érhető el", kod="vault.nem_elerheto", param={"vault": "Napló", "n": 3, "kesz": True, "x": None}, lemez_hiba=True)
        t = e.torzs()
        self.assertEqual(t, {"hiba": "The vault is not available.", "kod": "vault.nem_elerheto",
                             "param": {"vault": "Napló", "n": 3, "kesz": True, "x": None}, "lemez_hiba": True})
        self.assertEqual(list(t), ["hiba", "kod", "param", "lemez_hiba"])
        self.assertEqual((e.kod, e.param), ("vault.nem_elerheto", t["param"]))

    def test_a_param_json_biztos_alakra_kerul(self):
        e = HttpError(400, "hibás út", kod="ut.hibas", param={"ut": Path("a/b.md"), "ok": ValueError("x"), 5: "szám-kulcs"})
        self.assertEqual(e.torzs()["param"], {"ut": "a/b.md", "ok": "x", "5": "szám-kulcs"})
        json.dumps(e.torzs(), ensure_ascii=False)       # nem dob

    def test_param_kod_nelkul_es_ures_param(self):
        self.assertEqual(HttpError(400, "x", param={"a": 1}).torzs(), {"hiba": "x", "param": {"a": 1}})
        self.assertEqual(HttpError(400, "x", kod="k", param={}).torzs(), {"hiba": "x", "kod": "k", "param": {}})
        self.assertNotIn("param", HttpError(400, "x", kod="k").torzs())

    def test_a_param_nem_a_hivo_szotara(self):
        param = {"a": 1}
        e = HttpError(400, "x", kod="k", param=param)
        param["b"] = 2
        self.assertEqual(e.param, {"a": 1})


def _dob(*a, **kw):
    def kezelo(k):
        raise HttpError(*a, **kw)
    return kezelo


def _dob_kivetel(kivetel):
    def kezelo(k):
        raise kivetel
    return kezelo


def _regi_resz(torzs: dict) -> dict:
    """A törzs a `kod`/`param` nélkül: ez a rész a bevezetés előtt is ugyanaz volt."""
    return {k: v for k, v in torzs.items() if k not in ("hiba", "kod", "param")}


def _jol_formalt(testcase, torzs: dict) -> None:
    testcase.assertIsInstance(torzs.get("hiba"), str)
    testcase.assertEqual("param" in torzs, "kod" in torzs and isinstance(torzs.get("param"), dict))
    if "kod" in torzs:
        testcase.assertIsInstance(torzs["kod"], str)
        testcase.assertRegex(torzs["kod"], r"^[a-z0-9_]+(\.[a-z0-9_]+)*$")


class SzerverHibaTorzsTest(_Szerver):
    """A valódi szerver `_kezel` hibatérképén át: a törzs a `HttpError.torzs()`, a státusz a `code`."""

    def elokeszit(self):
        eredeti = server.regiszter_epit

        def epit():
            r = eredeti()
            r.get("/api/proba/kod", _dob(423, "The operation lock is busy.", kod="zar.foglalt", param={"kor": "K3", "db": 2}))
            r.get("/api/proba/regi", _dob(409, "ütközés", utkozes=True, fajlok=["a.md"]))
            r.get("/api/proba/cppkod", _dob(400, "nincs .cpp megoldás", kod="nincs_cpp"))
            r.get("/api/proba/semmi", _dob(404, "nincs ilyen"))
            r.get("/api/proba/inv-kod", _dob_kivetel(kodos(tasks.Invalid("a prioritás egész szám legyen"), "feladat.prioritas", n=3, ut=Path("a.md"))))
            r.get("/api/proba/inv-regi", _dob_kivetel(vaultio.Invalid("régi, kód nélküli hiba")))
            r.get("/api/proba/nf-kod", _dob_kivetel(kodos(vaultio.NotFound("nincs ilyen jegyzet: a.md"), "vault.nincs_fajl", ut="a.md")))
            r.get("/api/proba/utkozes", _dob_kivetel(kodos(vaultio.Conflict("a jegyzet közben megváltozott", sha="abc"), "vault.jegyzet_valtozott")))
            r.get("/api/proba/utkozes-regi", _dob_kivetel(vaultio.Conflict("a jegyzet közben megváltozott", sha="abc")))
            r.get("/api/proba/zarva", _dob_kivetel(kodos(tasks.Closed("a core leáll"), "core.leall")))
            statusz, adat = vaultio.lemez_hiba(PermissionError(errno.EACCES, "Permission denied", "/private/example/note.md"))
            uzenet = adat.pop("hiba")
            r.get("/api/proba/atnevezes-lemez", _dob_kivetel(atnevezes.Hiba(statusz, uzenet, **adat)))
            return r

        p = mock.patch.object(server, "regiszter_epit", epit)
        p.start()
        self.addCleanup(p.stop)

    def test_a_kod_es_a_param_a_torzsben(self):
        status, torzs = self.k("GET", "/api/proba/kod")
        self.assertEqual(status, 423)
        self.assertEqual(torzs, {"hiba": "The operation lock is busy.", "kod": "zar.foglalt", "param": {"kor": "K3", "db": 2}})

    def test_a_regi_hibak_torzse_nem_valtozott(self):
        """A `HttpError` régi hívásai: ugyanaz a státusz és törzs. A szerver saját hibái (`http.*`) a magyar mondat mellé kódot kapnak."""
        self.assertEqual(self.k("GET", "/api/proba/regi"), (409, {"hiba": "The operation conflicts with the current state. Refresh and try again.", "kod": "http.utkozes", "param": {}, "utkozes": True, "fajlok": ["a.md"]}))
        self.assertEqual(self.k("GET", "/api/proba/cppkod"), (400, {"hiba": "No C++ solution file was found.", "kod": "nincs_cpp"}))
        self.assertEqual(self.k("GET", "/api/proba/semmi"), (404, {"hiba": "The requested item was not found.", "kod": "http.nem_talalhato", "param": {}}))
        self.assertEqual(self.k("GET", "/api/nincs-ilyen-vegpont"), (404, {"hiba": "There is no such endpoint.", "kod": "http.nincs_vegpont"}))
        self.assertEqual(self.k("GET", "/api/allapot", fejlec={"X-Manifold": "0"})[1],
                         {"hiba": "The X-Manifold header is missing or not valid.", "kod": "http.x_manifold"})

    def test_a_kivetelek_hibaterkepe_additiv_kod_es_param_mezovel(self):
        """A `vaultio`/`tasks` kivételei külön ágon mennek; a `kodos()` a `kod`/`param` mezőt a törzsbe írja, a magyar `hiba` marad."""
        status, torzs = self.k("GET", "/api/proba/inv-kod")
        self.assertEqual((status, torzs), (400, {"hiba": "The priority must be a whole number.", "kod": "feladat.prioritas", "param": {"n": 3, "ut": "a.md"}}))
        self.assertEqual(self.k("GET", "/api/proba/inv-regi"), (400, {"hiba": "The request is invalid.", "kod": "http.keres_hibas", "param": {}}))
        self.assertEqual(self.k("GET", "/api/proba/nf-kod"), (404, {"hiba": "There is no such file: a.md", "kod": "vault.nincs_fajl", "param": {"ut": "a.md"}}))
        self.assertEqual(self.k("GET", "/api/proba/zarva"), (503, {"hiba": "Manifold is shutting down.", "kod": "core.leall", "param": {}}))

    def test_az_utkozes_torzse_megtartja_a_regi_mezoket(self):
        regi = self.k("GET", "/api/proba/utkozes-regi")
        self.assertEqual(regi, (409, {"hiba": "The operation conflicts with the current state. Refresh and try again.", "kod": "http.utkozes", "param": {}, "utkozes": True, "sha": "abc"}))
        uj = self.k("GET", "/api/proba/utkozes")
        self.assertEqual(uj[0], 409)
        self.assertEqual(uj[1], {"hiba": "The note changed since it was loaded (Obsidian, sync or a task wrote it).", "kod": "vault.jegyzet_valtozott", "param": {}, "utkozes": True, "sha": "abc"})
        self.assertEqual(_regi_resz(uj[1]), _regi_resz(regi[1]))

    def test_a_tobbi_vegpont_hibatorzse_jol_formalt_es_additiv(self):
        """A partíciók fokozatosan adnak kódot a saját hibáikhoz: a törzs `hiba` szövege és a régi mezői megmaradnak, a kód csak bővít."""
        status, torzs = self.k("POST", "/api/feladatok", {"tipus": "nincs"})
        self.assertEqual(status, 400)
        self.assertEqual(set(torzs) - {"kod", "param"}, {"hiba"})
        _jol_formalt(self, torzs)
        status, torzs = self.k("GET", "/api/vault/fajl?ut=nincs.md")
        self.assertEqual(status, 404)
        self.assertEqual(set(torzs) - {"kod", "param"}, {"hiba"})
        _jol_formalt(self, torzs)

    def test_az_atnevezes_lemezhibaja_megorzi_a_http_statuszt_es_a_hibakodot(self):
        statusz, adat = self.k("GET", "/api/proba/atnevezes-lemez")
        self.assertEqual(statusz, 503)
        self.assertEqual(adat["kod"], "lemez.eacces")
        self.assertEqual(adat["param"], {"errno": "EACCES"})
        self.assertEqual((adat["lemez_hiba"], adat["errno"]), (True, "EACCES"))
        self.assertIn("not writable", adat["hiba"])
        self.assertNotIn("/private/example", json.dumps(adat))


class HibaTorzsFuggvenyTest(unittest.TestCase):
    def test_az_atnevezes_statusza_nem_utkozik_a_forditasi_koddal(self):
        statusz, adat = vaultio.lemez_hiba(OSError(errno.ENOSPC, "No space left on device"))
        uzenet = adat.pop("hiba")
        e = atnevezes.Hiba(statusz, uzenet, **adat)
        self.assertEqual(e.kod, 507)
        self.assertEqual(e.adat, adat)
        self.assertEqual((e.hiba_kod, e.hiba_param), ("lemez.enospc", {"errno": "ENOSPC"}))
        self.assertEqual(hiba_torzs(e, alap_kod="atnevezes.sikertelen", **e.adat), {"hiba": uzenet, **adat})

    def test_kodos_a_kivetelre_teszi_a_kodot_es_visszaadja_ugyanazt(self):
        e = tasks.Invalid("magyar")
        self.assertIs(kodos(e, "a.b", n=1, ut=Path("x/y")), e)
        self.assertEqual((e.hiba_kod, e.hiba_param), ("a.b", {"n": 1, "ut": "x/y"}))
        self.assertEqual(str(e), "magyar")

    def test_hiba_torzs_kod_nelkul_a_regi_alak(self):
        self.assertEqual(hiba_torzs(vaultio.Invalid("x")), {"hiba": "x"})
        self.assertEqual(hiba_torzs(vaultio.Conflict("x"), utkozes=True), {"hiba": "x", "utkozes": True})

    def test_hiba_torzs_kodos_kivetelre(self):
        self.assertEqual(hiba_torzs(kodos(vaultio.Invalid("x"), "k.l", a=2)), {"hiba": "x", "kod": "k.l", "param": {"a": 2}})
        self.assertEqual(hiba_torzs(kodos(vaultio.Invalid("x"), "k.l"), utkozes=True), {"hiba": "x", "utkozes": True, "kod": "k.l", "param": {}})


class SzerverRegiszterTest(unittest.TestCase):
    def test_a_regiszter_hibatorzse_a_modul_osztalyabol(self):
        """A szerver a regiszter `HttpError` osztályát használja (a régi név alias): egy osztály, egy törzs-képlet."""
        self.assertIs(server.HttpError, utvonalak.HttpError)


if __name__ == "__main__":
    unittest.main()
