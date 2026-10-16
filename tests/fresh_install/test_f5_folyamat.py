"""F5 fresh-install gate across the real launcher CLI and HTTP core.

Only a read-only fake application, fake HOME and synthetic Obsidian notes are
used. No model, real vault or external service is opened.
"""
from __future__ import annotations

import http.client
import json
import os
import subprocess
import sys
import time
import tomllib
import unittest
import urllib.parse
from pathlib import Path

from tests.fresh_install import lenyomat, obsidian_vault
from tests.fresh_install.test_alap import _csak_olvashato, _irhato
from tests.helpers import REPO, alg_bundle, tmpdir
from tests.multi_user import elso_sor, termek_env


TITOK = "f5-fresh-install-test-secret-0123456789"


class F5FrissTelepitesTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.t = Path(self._t.name)
        self.root = alg_bundle(self._t.name)
        self.home = self.t / "home"
        self.install = self.home / "Library" / "Application Support" / "Manifold"
        self.vault = obsidian_vault(self.t / "Existing Obsidian notes")
        self.eredeti = lenyomat(self.vault, kihagy=())
        _csak_olvashato(self.root)
        self.addCleanup(_irhato, self.root)
        self.kod_eredeti = lenyomat(self.root, kihagy=())

    def _env(self):
        return termek_env(self.root, self.home, self.vault, MOS_API_TITOK=TITOK)

    def _indito(self, keres: dict, *, siker=True):
        p = subprocess.run([sys.executable, "-B", "-m", "core.indito"], cwd=REPO, env=self._env(),
                           input=json.dumps(keres), capture_output=True, text=True, timeout=120)
        sorok = [json.loads(sor) for sor in p.stdout.splitlines() if sor.strip()]
        self.assertTrue(sorok, p.stderr)
        self.assertEqual(p.returncode == 0, siker, p.stdout + p.stderr)
        self.assertEqual(sorok[-1].get("ok"), siker, sorok)
        self.assertNotIn(TITOK, p.stdout, "the launcher never receives an API secret")
        return sorok[-1], sorok[:-1]

    def _core(self):
        p = subprocess.Popen([sys.executable, "-B", "-m", "core", "start"], cwd=REPO, env=self._env(),
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.addCleanup(self._leallit, p)
        sor = elso_sor(p)
        self.assertTrue(sor, "the core did not announce its HTTP handshake")
        return p, json.loads(sor)

    @staticmethod
    def _leallit(p):
        if p.poll() is None:
            if p.stdin and not p.stdin.closed:
                p.stdin.close()
            try:
                p.wait(timeout=60)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait(timeout=10)
        for f in (p.stdin, p.stdout):
            if f and not f.closed:
                f.close()

    @staticmethod
    def _ker(port, metodus, ut, torzs=None):
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
        try:
            c.request(metodus, ut, body=None if torzs is None else json.dumps(torzs),
                      headers={"Host": f"127.0.0.1:{port}", "X-Manifold": TITOK, "Content-Type": "application/json"})
            r = c.getresponse()
            return r.status, json.loads(r.read() or b"null")
        finally:
            c.close()

    def _beallitas(self, port, rev, valtozas):
        kod, adat = self._ker(port, "PUT", "/api/beallitasok", {"rev": rev, "valtozas": valtozas})
        self.assertEqual(kod, 200, adat)
        return adat

    def _futo(self, id, p, port):
        mappa = self.install / "run" / "cores"
        fajlok = list(mappa.glob("*.json"))
        self.assertEqual([f.name for f in fajlok], [f"{id}.json"])
        nyers = fajlok[0].read_text(encoding="utf-8")
        self.assertNotIn(TITOK, nyers)
        adat = json.loads(nyers)
        self.assertEqual(set(adat), {"id", "pid", "port", "vault", "zar"})
        self.assertEqual((adat["id"], adat["pid"], adat["port"], adat["vault"]), (id, p.pid, port, os.path.realpath(self.vault)))
        lista, _ = self._indito({"muvelet": "lista"})
        self.assertEqual(len(lista["munkaterek"]), 1)
        self.assertEqual((lista["munkaterek"][0]["id"], lista["munkaterek"][0]["fut"], lista["munkaterek"][0]["pid"]), (id, True, p.pid))

    def _leallt(self, id, p):
        self._leallit(p)
        self.assertEqual(p.returncode, 0)
        self.assertFalse((self.install / "run" / "cores" / f"{id}.json").exists())
        lista, _ = self._indito({"muvelet": "lista"})
        self.assertEqual((lista["munkaterek"][0]["fut"], lista["munkaterek"][0]["pid"]), (False, None))

    def test_inditotol_a_mentesen_at_az_ujrainditasig(self):
        # The preview and the missing-confirmation failure cannot change a note folder.
        elozetes, haladas = self._indito({"muvelet": "felmer", "vault": str(self.vault)})
        self.assertFalse(haladas)
        self.assertNotEqual(elozetes["felmeres"]["eredmeny"], "tilos", elozetes)
        self.assertTrue(elozetes["valtozasok"])
        self.assertEqual(lenyomat(self.vault, kihagy=()), self.eredeti)
        elutasitott, _ = self._indito({"muvelet": "letrehoz", "vault": str(self.vault)}, siker=False)
        self.assertEqual(elutasitott["kod"], "indito.megerosites")
        self.assertEqual(lenyomat(self.vault, kihagy=()), self.eredeti)

        kesz, haladas = self._indito({"muvelet": "letrehoz", "vault": str(self.vault), "nev": "Example workspace", "elfogad": True})
        id = kesz["munkater"]["id"]
        self.assertRegex(id, r"^[0-9a-f]{32}$")
        self.assertTrue(all(set(e) == {"haladas"} for e in haladas), haladas)
        self.assertIn("pillanatkep", [e["haladas"]["lepes"] for e in haladas])
        self.assertEqual(lenyomat(self.vault), self.eredeti)

        p, kezfogas = self._core()
        port = kezfogas["port"]
        self.assertEqual((kezfogas["elrendezes"], kezfogas["munkater_id"]), ("termek", id))
        self._futo(id, p, port)
        kod, beallitas = self._ker(port, "GET", "/api/beallitasok")
        self.assertEqual(kod, 200, beallitas)
        self.assertTrue(beallitas["setup_szukseges"])
        self.assertEqual(beallitas["ertek"]["altalanos"]["nyelv"], "auto")
        self.assertEqual(beallitas["munkater"]["nev"], "Example workspace")

        # One final Setup save persists choices and completion without rewriting any notes.
        elso_rev = beallitas["rev"]
        beallitas = self._beallitas(port, elso_rev, {
            "altalanos": {"nyelv": "auto", "inditas": "valaszto"},
            "szerkeszto": {"mod": "forras", "tab_meret": 4},
            "fajlok": {"uj_mappa": "Notes", "csatolmany_mappa": "Attachments"},
            "megjelenes": {"tema": "sotet", "betumeret": 18},
            "modulok": {"kartya": False, "video": False},
            "adatvedelem": {"asszisztens": False, "tracker": False, "ertesitesek": False, "naptar": False},
            "setup": {"kesz": True, "elmeny": "fejleszto"},
        })
        self.assertFalse(beallitas["setup_szukseges"])
        self.assertEqual(lenyomat(self.vault), self.eredeti)
        w = self.vault / ".manifold" / "workspace.toml"
        self.assertEqual(tomllib.loads(w.read_text(encoding="utf-8"))["workspace"]["id"], id)
        self.assertTrue(w.with_suffix(".toml.elozo").is_file())
        settings_bajtok = w.read_bytes()
        kod, hiba = self._ker(port, "PUT", "/api/beallitasok", {"rev": elso_rev, "valtozas": {"setup": {"kesz": False}}})
        self.assertEqual((kod, hiba.get("kod")), (409, "beallitas.utkozes"), hiba)
        self.assertEqual(w.read_bytes(), settings_bajtok)

        # The schema endpoint uses the live language hint, including reset to Automatic.
        beallitas = self._beallitas(port, beallitas["rev"], {"altalanos": {"nyelv": "hu"}})
        kod, sema = self._ker(port, "GET", "/api/vault/sema")
        self.assertEqual((kod, sema.get("nyelv")), (200, "hu"), sema)
        beallitas = self._beallitas(port, beallitas["rev"], {"altalanos": {"nyelv": "auto"}})
        kod, sema = self._ker(port, "GET", "/api/vault/sema")
        self.assertEqual((kod, sema.get("nyelv")), (200, ""), sema)

        # A disabled module is blocked at the public route, and can be re-enabled without restarting.
        kod, hiba = self._ker(port, "GET", "/api/kartya/allapot")
        self.assertEqual((kod, hiba.get("kod")), (409, "modul.kikapcsolva"), hiba)
        self.assertEqual(hiba["param"]["modul"], "kartya")
        beallitas = self._beallitas(port, beallitas["rev"], {"modulok": {"kartya": True}})
        kod, kartya = self._ker(port, "GET", "/api/kartya/allapot")
        self.assertEqual(kod, 200, kartya)

        # No model is needed to create, edit, search and snapshot a new Markdown note.
        kod, uj = self._ker(port, "POST", "/api/vault/uj", {"nev": "Fresh note", "mappa": "Notes", "mappa_keszit": True})
        self.assertEqual((kod, uj.get("git")), (201, True), uj)
        self.assertTrue(uj["pillanat"])
        ut = "Notes/Fresh note.md"
        kod, jegyzet = self._ker(port, "GET", "/api/vault/fajl?ut=" + urllib.parse.quote(ut))
        self.assertEqual(kod, 200, jegyzet)
        szoveg = "# Fresh note\n\nFreshinstallfivetoken connects to [[Kezdőlap]].\n"
        kod, mentett = self._ker(port, "PUT", "/api/vault/fajl", {"ut": ut, "tartalom": szoveg, "alap": jegyzet["hash"], "elso": True, "pillanat": True})
        self.assertEqual((kod, mentett.get("git")), (200, True), mentett)
        self.assertTrue(mentett["pillanat"])
        hatarido = time.monotonic() + 20
        while True:
            kod, kereses = self._ker(port, "GET", "/api/vault/kereses?q=Freshinstallfivetoken")
            if kod == 200 and any(t["ut"] == ut for t in kereses.get("talalatok", [])):
                break
            self.assertLess(time.monotonic(), hatarido, kereses)
            time.sleep(0.1)
        kod, naplo = self._ker(port, "GET", "/api/pillanat/vault/naplo?n=10")
        self.assertEqual(kod, 200, naplo)
        self.assertIn(mentett["pillanat"], [c["sha"] for c in naplo["commitok"]])
        elvart = {**self.eredeti, "Notes/": None, ut: szoveg.encode("utf-8")}
        self.assertEqual(lenyomat(self.vault), elvart)
        self._leallt(id, p)

        # Restart sees completed Setup and all saved options; the launcher respects the saved chooser preference.
        lista, _ = self._indito({"muvelet": "lista"})
        self.assertEqual(lista["inditas"], "valaszto")
        p2, kezfogas2 = self._core()
        self._futo(id, p2, kezfogas2["port"])
        kod, ujra = self._ker(kezfogas2["port"], "GET", "/api/beallitasok")
        self.assertEqual(kod, 200, ujra)
        self.assertFalse(ujra["setup_szukseges"])
        self.assertEqual(ujra["ertek"], beallitas["ertek"])
        kod, hiba = self._ker(kezfogas2["port"], "GET", "/api/video/allapot")
        self.assertEqual((kod, hiba.get("kod")), (409, "modul.kikapcsolva"), hiba)
        self._leallt(id, p2)
        self.assertEqual(lenyomat(self.vault), elvart, "existing notes and .obsidian bytes remain intact")
        self.assertEqual(lenyomat(self.root, kihagy=()), self.kod_eredeti)
        self.assertFalse((self.root / "var").exists(), "no mutable application-bundle state")


if __name__ == "__main__":
    unittest.main()
