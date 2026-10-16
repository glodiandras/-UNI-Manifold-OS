"""F9 security audit §2: path traversal and symlink escape on the vault APIs (docs/plan/audit/07-f9-biztonsag.md).

Every vault endpoint that takes a path is probed over real HTTP with the same set of hostile paths: `..` segments (also with
backslashes and inside a valid prefix), absolute paths, NUL and control characters, hidden segments (`.obsidian`, `.git`), a
note that is a symlink to a file outside the vault, and a folder that is a symlink to a folder outside the vault. Expected:
a 4xx answer, the outside secret never in a response, nothing outside the vault created or changed, and the secret never copied
INTO the vault (exfiltration through rename / upload / history restore)."""
from __future__ import annotations

import base64
import hashlib
import os
import urllib.parse

from tests.biztonsag import TITOK_SZOVEG, Szerver, fa


def _q(s: str) -> str:
    return urllib.parse.quote(s, safe="")


class UtvonalBejarasTest(Szerver):

    def elokeszit(self):
        (self.v / "Notes" / "kifele.md").symlink_to(self.kint / "titok.md")             # a note that is a link to outside
        (self.kint / "kep.png").write_bytes(b"\x89PNG\r\n\x1a\n" + TITOK_SZOVEG.encode())
        (self.v / "Notes" / "kep.png").symlink_to(self.kint / "kep.png")                # a media file that is a link to outside
        (self.v / "Kimenet").symlink_to(self.kint, target_is_directory=True)            # a folder that is a link to outside
        self.repo.commit("links", {"Mos-Forras": "kezi"})

    def rossz_utak(self) -> list[str]:
        k = str(self.kint)
        return ["../kint/titok.md", "Notes/../../kint/titok.md", "Notes\\..\\..\\kint\\titok.md", k + "/titok.md",
                "/etc/hosts", "//etc/hosts", "Notes/kifele.md", "Kimenet/titok.md", "Notes/A.md\x00.png", "Notes/A.md\n.md",
                ".obsidian/app.json", "Notes/.hidden.md", "./Notes/A.md/..", "Notes/A.md/../../../kint/titok.md",
                "‥/kint/titok.md", "Kimenet", ""]

    def _valasz_ok(self, kod, valasz, cimke, *, olvaso_200=False):
        """4xx and no leak. `olvaso_200`: a pure suggestion reader may answer 200 as long as the outside content does not leak."""
        if not (olvaso_200 and kod == 200):
            self.assertTrue(400 <= kod < 500, f"{cimke}: {kod} {valasz!r}"[:400])
        self.nem_szivarog(valasz, cimke)

    def vault_nem_kapta_meg(self):
        for rp, b in fa(self.v).items():
            if isinstance(b, bytes) and not rp.startswith(".obsidian"):
                self.assertNotIn(TITOK_SZOVEG.encode(), b, f"the outside secret was copied into the vault: {rp}")

    def test_olvasas(self):
        for ut in self.rossz_utak():
            for vegpont in ("/api/vault/fajl", "/api/vault/elozmeny", "/api/vault/tulajdonsagok/kulcsok"):
                kod, d = self.k("GET", f"{vegpont}?ut={_q(ut)}")
                self._valasz_ok(kod, d, f"GET {vegpont} {ut!r}", olvaso_200=not vegpont.endswith("fajl"))
                # the key suggestions and the history LIST (git log metadata) may answer 200: they never return file content
        kod, d = self.k("GET", "/api/vault/fajl?ut=Notes/A.md")
        self.assertEqual(kod, 200, d)                                    # the control: a normal note reads
        self.kint_erintetlen()

    def test_iras_es_uj_jegyzet(self):
        alap = hashlib.sha1((self.kint / "titok.md").read_bytes()).hexdigest()
        for ut in self.rossz_utak():
            kod, d = self.k("PUT", "/api/vault/fajl", {"ut": ut, "tartalom": "pwned\n", "alap": alap, "elso": True, "pillanat": True})
            self._valasz_ok(kod, d, f"PUT {ut!r}")
        for mappa in ("../kint", "Kimenet", "Notes/../../kint", ".obsidian", "Notes/kifele.md"):
            kod, d = self.k("POST", "/api/vault/uj", {"nev": "uj", "mappa": mappa, "mappa_keszit": True})
            self._valasz_ok(kod, d, f"uj mappa={mappa!r}")
        # An absolute folder is read as vault-relative (`norm_path` strips the leading `/`): it can only land INSIDE the vault.
        kod, d = self.k("POST", "/api/vault/uj", {"nev": "uj", "mappa": str(self.kint), "mappa_keszit": True})
        if kod < 300:
            self.assertTrue((self.v / d["ut"]).resolve().is_relative_to(self.v.resolve()), d)
        else:
            self._valasz_ok(kod, d, "uj absolute folder")
        for nev in ("../../kint/uj", "../uj", "/tmp/uj", "a/../../uj", ".rejtett"):
            kod, d = self.k("POST", "/api/vault/uj", {"nev": nev, "mappa": "Notes"})
            if kod < 300:                                               # a name is a name: it may only land inside Notes/
                self.assertTrue((self.v / d["ut"]).resolve().is_relative_to(self.v.resolve() / "Notes"), d)
                self.assertFalse(d["ut"].count("/") > 1 or ".." in d["ut"], d)
            else:
                self._valasz_ok(kod, d, f"uj nev={nev!r}")
        self.kint_erintetlen()
        self.assertEqual((self.kint / "titok.md").read_text(encoding="utf-8"), f"# secret\n{TITOK_SZOVEG}\n")

    def test_atnevezes_ki_es_be(self):
        parok = [("Notes/A.md", "../kint/A.md"), ("Notes/A.md", "Kimenet/A.md"), ("Notes/A.md", str(self.kint / "A.md")),
                 ("Kimenet/titok.md", "Notes/lopott.md"), ("Notes/kifele.md", "Notes/lopott2.md"),
                 ("../kint/titok.md", "Notes/lopott3.md"), ("Notes", "../kint/Notes"), ("Kimenet", "Bent")]
        for ut, uj in parok:
            kod, terv = self.k("POST", "/api/vault/atnevezes/terv", {"ut": ut, "uj": uj})
            if kod == 200:
                kod, d = self.k("POST", "/api/vault/atnevezes", {"ut": ut, "uj": uj, "terv_hash": terv.get("terv_hash")})
                self._valasz_ok(kod, d, f"atnevezes {ut!r} → {uj!r} (plan was accepted: {terv.get('blokkolok')})")
            else:
                self._valasz_ok(kod, terv, f"terv {ut!r} → {uj!r}")
        self.kint_erintetlen()
        self.vault_nem_kapta_meg()

    def test_media_es_csatolmany(self):
        token = self.k("GET", "/api/allapot")[1]["media_token"]
        for ut in ("Notes/kep.png", "Kimenet/kep.png", "../kint/kep.png", "Notes/..%2f..%2fkint/kep.png", "%2e%2e/kint/kep.png",
                   ".obsidian/app.json", str(self.kint / "kep.png")):
            kod, b = self.k("GET", f"/media/{token}/" + urllib.parse.quote(ut, safe="/%"))
            self._valasz_ok(kod, b, f"media {ut!r}")
        adat = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\0" * 16).decode()
        for torzs in ({"nev": "../../x.png", "mappa": "Notes"}, {"nev": "x.png", "mappa": "../kint"},
                      {"nev": "x.png", "mappa": "Kimenet"}, {"nev": "x.png", "forras": "Kimenet/titok.md"},
                      {"nev": "x.png", "forras": "Notes/kifele.md"}, {"nev": "x.png", "mappa": str(self.kint)}):
            kod, d = self.k("POST", "/api/vault/import", {**torzs, "adat": adat, "vege": True})
            if kod < 300 and d.get("ut"):
                self.assertTrue((self.v / d["ut"]).resolve().is_relative_to(self.v.resolve()), (torzs, d))
                self.assertNotIn("..", d["ut"])
            else:
                self._valasz_ok(kod, d, f"import {torzs}")
        self.kint_erintetlen()

    def test_elozmeny_visszaallitas_nem_ir_kifele(self):
        sha = self.repo.git("rev-parse", "HEAD").stdout.strip()
        for ut in ("Notes/kifele.md", "Kimenet/titok.md", "../kint/titok.md"):
            kod, d = self.k("POST", "/api/vault/elozmeny/visszaallit", {"ut": ut, "sha": sha})
            self._valasz_ok(kod, d, f"elozmeny {ut!r}")
            kod, d = self.k("GET", f"/api/vault/elozmeny/valtozat?ut={_q(ut)}&sha={sha}")
            # a committed symlink's history version is its target TEXT (git stores the link, not the file): no content leak
            self._valasz_ok(kod, d, f"valtozat {ut!r}", olvaso_200=ut == "Notes/kifele.md")
        kod, d = self.k("GET", f"/api/vault/elozmeny/valtozat?ut=Notes/A.md&sha={_q('--output=' + str(self.kint / 'x'))}")
        self._valasz_ok(kod, d, "valtozat with an option as sha")
        self.kint_erintetlen()

    def test_utvonal_kodolas_nem_kerul_meg_a_hitelesitest(self):
        """The request path is authenticated after percent-decoding; odd spellings of `/api/` either authenticate or 404."""
        for ut in ("//api/vault/fajl?ut=Notes/A.md", "/API/vault/fajl?ut=Notes/A.md", "/%61pi/vault/fajl?ut=Notes/A.md",
                   "/api//vault/fajl?ut=Notes/A.md", "/./api/vault/fajl?ut=Notes/A.md", "/api/vault/./fajl?ut=Notes/A.md",
                   "/app/../api/vault/fajl?ut=Notes/A.md"):
            kod, d = self.k("GET", ut, fejlec={"X-Manifold": "wrong"})
            self.assertIn(kod, (403, 404), (ut, d))
            self.assertNotIn(b"alpha body", d if isinstance(d, bytes) else str(d).encode(), ut)

    def test_nem_letezo_szulo_es_hosszu_ut(self):
        for ut in ("Notes/" + "x" * 300 + ".md", "Notes/" + "/".join(["d"] * 200) + "/a.md"):
            kod, d = self.k("GET", f"/api/vault/fajl?ut={_q(ut)}")
            self._valasz_ok(kod, d, "long path")
        self.assertFalse(os.path.exists(self.v / "d"))
