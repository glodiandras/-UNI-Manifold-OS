"""A gépi írás szolgáltatása (`core/gepi_iras.py`, C16.5) álvaulton: a három művelet, az ellenőrzések, egy gépi
commit útlistával, visszavonás tételre és körre bájtra, megszakadt írás utáni indulás, próbamód."""
import fcntl
import json
import os
import subprocess
import sys
import unicodedata
import unittest
from pathlib import Path

from core import frame, gepi_iras, snapshot, vaultio
from core.gepi_iras import szakasz_beszur
from core.modell import kalibracio
from core.tulajdonsagok import Tulajdonsagok
from core.utvonalak import HttpError
from tests import csak_darwin
from tests.helpers import REPO, alg_core, env, ir, tmpdir, vault_sema
from tests.index_segedek import index_indit

NINCS = object()                         # a `modell` kulcs kihagyása a kérésből (C29.8, T043)
FM = "---\nTags:\nSource:\nStatus:\nNN:\nCanvas:\n---\n"
NFD = unicodedata.normalize("NFD", "Öröklés.md")
SEMA_NELKULI = "CLAUDE.md"                                    # a séma alól kivett (ügynök-hordozó) fájl; a név számít, a mélység nem
UGYNOK_UTAK = ["Sub/CLAUDE.md", "T01/Mélyebb/agents.MD", "Memory.md", "T01/sub/memory.md"]
H1_KIVETEL = vault_sema()["h1"]["kivetel_utvonalak"][0] + "Napi log.md"      # a H1-szabály alól kivett útvonal
KULONLEGES = ["T01/a -> b.md", "T01/tab\tnév.md", 'T01/idéz"őjel.md', "T01/Mi?.md", "T01/szög[let].md", "T01/" + NFD]
ALAP = {
    "T01/a.md": FM + "# A\n\n## Gyakorlás\nelső sor\n\n## Más\nvége\n",
    "T01/crlf.md": "# C\r\n\r\n## Gyakorlás\r\nsor\r\n",
    "T01/kesz.md": "---\nTags:\nSource:\nStatus: Completed\nNN:\nCanvas:\n---\n# Kész\n",
    SEMA_NELKULI: "# ügynök\n",
    **{n: "# K\n\n## Gyakorlás\nx\n" for n in KULONLEGES},
}


def lenyomat(gyoker) -> dict:
    ki = {}
    for d, mappak, fajlok in os.walk(gyoker):
        mappak[:] = [m for m in mappak if m != ".obsidian"]
        for f in fajlok:
            p = os.path.join(d, f)
            ki[os.path.relpath(p, gyoker)] = Path(p).read_bytes()
        if not mappak and not fajlok:
            ki[os.path.relpath(d, gyoker) + "/"] = b""
    return ki


class Alap(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, self.root, self.v = alg_core(self._t.name)
        for rp, t in ALAP.items():
            ir(self.v, rp, t, "wb" if isinstance(t, bytes) else "w")
        (self.v / "T01/crlf.md").write_bytes(ALAP["T01/crlf.md"].encode())
        self.repo = snapshot.repos(self.cfg)["vault"]
        self.repo.init()
        self.repo.commit("alap", {"Mos-Forras": "kezi"})
        self.esemenyek, self.sajat, self.mentetlen = [], [], set()
        self.V = vaultio.Vault(self.cfg)
        self.G = gepi_iras.GepiIras(self.cfg, self.V, Tulajdonsagok(self.cfg, None),
                                    publish=lambda e, **k: self.esemenyek.append(e),
                                    sajat=lambda rp, h: self.sajat.append((rp, h)),
                                    mentetlen=lambda: self.mentetlen, varakozas_mp=0.3)

    def keres(self, *muveletek, kor="KARTYA-20261003-101500", tetel="t1", **tobbi):
        ki = {"kor": kor, "tetel": tetel, "forras": "mos-kartya", "uzenet": "kártyák", "modell": None,        # determinisztikus írás
              "muveletek": list(muveletek), **tobbi}
        if ki["modell"] is NINCS:
            del ki["modell"]
        return ki

    def aranyverzio(self, feladat: str, verzio: str) -> None:
        """Az álgyökér `{modulok}/eval/<feladat>/feladat.py`-ja: az aranyhalmaz aktuális verziója (`halmaz.Verziok`); a D9
        írás-kapu csak az ezen mért kalibrált sort fogadja el."""
        mappa = self.cfg.path("modulok") / "eval" / feladat
        mappa.mkdir(parents=True, exist_ok=True)
        (mappa / "feladat.py").write_text(f'ROUTER_FELADAT = "{feladat}"\nVERZIO = "{verzio}"\n', encoding="utf-8")

    def olvas(self, rp) -> bytes:
        return (self.v / rp).read_bytes()

    def hash(self, rp) -> str:
        return vaultio.sha1(self.olvas(rp))

    def hiba(self, kod, *muveletek, **tobbi) -> HttpError:
        elotte, fej = lenyomat(self.v), self.repo.git("rev-parse", "HEAD").stdout
        with self.assertRaises(Exception) as cm:
            self.G.ir(self.keres(*muveletek, **tobbi))
        e = cm.exception
        tenyleges = (e.code if isinstance(e, HttpError) else 404 if isinstance(e, vaultio.NotFound)
                     else 409 if isinstance(e, vaultio.Conflict) else 400 if isinstance(e, vaultio.Invalid) else None)
        self.assertEqual(tenyleges, kod, repr(e))
        self.assertEqual(lenyomat(self.v), elotte)                      # az elutasított tétel semmit nem írt
        self.assertFalse((self.cfg.path("run") / gepi_iras.NAPLO).exists())
        self.assertNotIn("Mos-Kor: KARTYA", self.repo.git("log", "--format=%B", f"{fej.strip()}..HEAD").stdout)
        return e


class MuveletTest(Alap):
    def test_harom_muvelet_egy_commit_utlistaval(self):
        ir(self.v, "X01/nap.md", "a gazda írta\n")                       # nem rögzített kézi változás máshol
        r = self.G.ir(self.keres(
            {"tipus": "uj", "ut": "ATTCHMNTS - quizes/A — Kvíz 2026-10-03 1015.md", "osztaly": "kviz",
             "tartalom": "---\nSource:\nKviz:\nModell:\nKeszult:\n---\n# A — Kvíz 2026-10-03 1015\n"},
            {"tipus": "csere", "ut": "T01/kesz.md", "alap": self.hash("T01/kesz.md"),
             "tartalom": ALAP["T01/kesz.md"] + "gépi sor\n"},
            {"tipus": "beszuras", "ut": "T01/a.md", "szakasz": "Gyakorlás", "szoveg": "![[A — Kvíz 2026-10-03 1015]]"},
            dontes="kesz", feladat="F-20261003-101500-1"))
        self.assertTrue(r["ok"] and r["valtozas"] and not r["ismetles"] and not r["proba"])
        utak = ["ATTCHMNTS - quizes/A — Kvíz 2026-10-03 1015.md", "T01/kesz.md", "T01/a.md"]
        self.assertEqual(r["utak"], utak)
        self.assertEqual(self.olvas("T01/a.md").decode(), FM + "# A\n\n## Gyakorlás\nelső sor\n![[A — Kvíz 2026-10-03 1015]]\n\n## Más\nvége\n")
        log = self.repo.log(3)
        self.assertEqual(log[0].sha, r["sha"])
        self.assertEqual(sorted(self.repo.changed_files(r["sha"])), sorted(utak))      # csak az útlista
        self.assertRegex(log[0].trailers.pop("Mos-Keres"), r"^[0-9a-f]{16}$")          # a kérés ujjlenyomata (T095)
        self.assertEqual(log[0].trailers, {"Mos-Kor": "KARTYA-20261003-101500", "Mos-Tetel": "t1",
                                           "Mos-Forras": "mos-kartya", "Mos-Dontes": "kesz",
                                           "Mos-Feladat": "F-20261003-101500-1"})
        self.assertEqual(log[1].trailers["Mos-Forras"], "kezi")                          # a gazda változása külön
        self.assertEqual(self.repo.changed_files(log[1].sha), ["X01/nap.md"])
        self.assertEqual(self.repo.dirty_paths(), [])
        # az index a csere ELŐTT megkapta a saját írás hash-ét; esemény fájlonként és egy a tételről
        self.assertEqual(dict(self.sajat), r["hash"])
        self.assertEqual([e["ut"] for e in self.esemenyek if e["tipus"] == "vault_iras"], utak)
        (g,) = [e for e in self.esemenyek if e["tipus"] == "gepi_iras"]
        self.assertEqual(g, {"tipus": "gepi_iras", "kor": "KARTYA-20261003-101500", "tetel": "t1", "utak": utak,
                             "sha": r["sha"], "forras": "mos-kartya", "uzenet": "kártyák",
                             "feladat": "F-20261003-101500-1", "proba": False})

    def test_gazda_szerkesztese_ugyanabban_a_fajlban_kulon_marad(self):
        """L14: a nem rögzített kézi változás a gépi írás előtt külön commitba kerül; a visszavonás azt adja vissza."""
        kezi = (ALAP["T01/a.md"] + "a gazda új sora\n").encode()
        (self.v / "T01/a.md").write_bytes(kezi)
        r = self.G.ir(self.keres({"tipus": "beszuras", "ut": "T01/a.md", "szakasz": "Más", "szoveg": "gépi"}))
        self.assertEqual(self.repo.log(2)[1].trailers["Mos-Forras"], "kezi")
        self.repo.undo_commit(r["sha"])
        self.assertEqual(self.olvas("T01/a.md"), kezi)

    @csak_darwin("NFD-nevű fájl (a Linux fájlrendszere nem normalizál: az NFD és NFC név két külön fájl)")
    def test_kulonleges_nevek(self):
        """Meglévő különleges nevű fájlok: beszúrás és csere, a lemezen álló (NFD) név marad, visszavonás bájtra."""
        elotte = lenyomat(self.v)
        muveletek = [{"tipus": "beszuras", "ut": n, "szakasz": "Gyakorlás", "szoveg": "gépi"} for n in KULONLEGES[:3]]
        muveletek += [{"tipus": "csere", "ut": unicodedata.normalize("NFC", n), "tartalom": "# K\n\ncsere\n",
                       "alap": self.hash(n)} for n in KULONLEGES[3:]]
        r = self.G.ir(self.keres(*muveletek))
        self.assertEqual(sorted(self.repo.changed_files(r["sha"])),
                         sorted(unicodedata.normalize("NFC", n) for n in KULONLEGES))
        self.assertIn(NFD, os.listdir(self.v / "T01"))
        self.assertEqual(self.olvas("T01/Mi?.md"), b"# K\n\ncsere\n")
        self.assertEqual(self.repo.dirty_paths(), [])
        self.repo.undo_commit(r["sha"])
        self.assertEqual(lenyomat(self.v), elotte)

    def test_uj_fajl_ekezetes_mappaval_es_visszavonas(self):
        elotte = lenyomat(self.v)
        ut = "Új mappa/Belső/Árvíztűrő — jegyzet's & co.md"
        r = self.G.ir(self.keres({"tipus": "uj", "ut": ut, "tartalom": FM + "# Árvíztűrő — jegyzet's & co\n", "osztaly": "normal"}))
        self.assertEqual(self.olvas(ut), (FM + "# Árvíztűrő — jegyzet's & co\n").encode())
        self.assertEqual([n for n in os.listdir(self.v / "Új mappa/Belső") if n.startswith(".")], [])   # nincs tmp
        self.repo.undo_commit(r["sha"])
        self.assertEqual(lenyomat(self.v), elotte)                      # a fájl és az új mappák is eltűntek

    def test_ismetles_nem_duplaz(self):
        k = self.keres({"tipus": "beszuras", "ut": "T01/a.md", "szakasz": "Gyakorlás", "szoveg": "egyszer"})
        r1 = self.G.ir(k)
        r2 = self.G.ir(k)
        self.assertEqual((r2["sha"], r2["ismetles"], r2["valtozas"]), (r1["sha"], True, False))
        self.assertEqual(self.olvas("T01/a.md").decode().count("egyszer"), 1)
        # ugyanaz a szöveg másik tételben: nincs változás, nincs commit, nincs esemény
        n = len(self.esemenyek)
        r3 = self.G.ir(self.keres(*k["muveletek"], tetel="t2"))
        self.assertEqual((r3["sha"], r3["valtozas"], r3["utak"]), (None, False, []))
        self.assertEqual(len(self.esemenyek), n)

    def test_kisbetus_ut_is_gepi_commit_a_lemezen_allo_nevvel(self):
        """T018: a `t01/A.md` kérés ugyanazt a fájlt írta, mint a `T01/a.md`, de a git pathspec nem találta: a gép szövege „kézi”
        commitba került, a válasz hamis 503 volt."""
        r = self.G.ir(self.keres({"tipus": "beszuras", "ut": "t01/A.md", "szakasz": "Gyakorlás", "szoveg": "kisbetűs"}))
        self.assertEqual(r["utak"], ["T01/a.md"])
        self.assertIn("kisbetűs", self.olvas("T01/a.md").decode())
        c = self.repo.log(1)[0]
        self.assertEqual((c.sha, c.trailers["Mos-Forras"]), (r["sha"], "mos-kartya"))
        self.assertEqual(self.repo.changed_files(r["sha"]), ["T01/a.md"])
        self.assertEqual(self.repo.dirty_paths(), [])
        self.assertEqual([e["ut"] for e in self.esemenyek if e["tipus"] == "vault_iras"], ["T01/a.md"])

    def test_kisbetus_ut_a_mentetlen_halmazt_sem_kerulheti_meg(self):
        self.mentetlen = {"T01/a.md"}
        e = self.hiba(409, {"tipus": "csere", "ut": "t01/A.md", "alap": self.hash("T01/a.md"), "tartalom": FM + "# A\n"})
        self.assertTrue(e.data.get("nyitott"))
        self.mentetlen = {"t01/a.md"}                                       # a felület kisbetűs jelentése is egyezik
        self.hiba(409, {"tipus": "csere", "ut": "T01/a.md", "alap": self.hash("T01/a.md"), "tartalom": FM + "# A\n"})

    def test_ket_uj_kozos_uj_mappaval_es_kozos_uj_szulovel(self):
        """T019: két új fájl közös, még nem létező ős-mappával `FileExistsError`-ral (500) elhasalt — minden többfájlos gépi
        író (füzet-import, kártyacsomag, átirat) értelmes hiba nélkül."""
        from core.gepi_iras import _keres
        tart = lambda n: FM + f"# {n}\n"                                    # a H1 a fájlnév (T044)  # noqa: E731
        k = self.keres({"tipus": "uj", "ut": "_Proba/Kozos/A.md", "osztaly": "normal", "tartalom": tart("A")},
                       {"tipus": "uj", "ut": "_Proba/Kozos/B.md", "osztaly": "normal", "tartalom": tart("B")},
                       {"tipus": "uj", "ut": "_Proba/Szulo/X/C.md", "osztaly": "normal", "tartalom": tart("C")},
                       {"tipus": "uj", "ut": "_Proba/Szulo/Y/D.md", "osztaly": "normal", "tartalom": tart("D")})
        fajlok = self.G._terv(_keres(k))
        mappak = [m for f in fajlok for m in f.mappak]
        self.assertEqual(len(mappak), len(set(mappak)), "egy mappát csak egy művelet birtokolhat")
        r = self.G.ir(k)
        self.assertEqual(r["utak"], ["_Proba/Kozos/A.md", "_Proba/Kozos/B.md", "_Proba/Szulo/X/C.md", "_Proba/Szulo/Y/D.md"])
        for ut in r["utak"]:
            self.assertEqual(self.olvas(ut).decode(), tart(ut.rsplit("/", 1)[1][:-3]))
        self.repo.undo_commit(r["sha"])
        self.assertFalse(any((self.v / u).exists() for u in r["utak"]))

    def test_mas_tartalmu_ismetles_409_utkozes(self):
        """T095: ugyanaz a (kör, tétel, feladat) más tartalommal eddig csendben „ok / ismétlés” volt — a második írás
        elveszett volna. Most 409 `utkozes`; az azonos tartalmú ismétlés továbbra is az első commitot adja."""
        k1 = self.keres({"tipus": "beszuras", "ut": "T01/a.md", "szakasz": "Gyakorlás", "szoveg": "első"})
        r1 = self.G.ir(k1)
        with self.assertRaises(HttpError) as cm:
            self.G.ir(self.keres({"tipus": "beszuras", "ut": "T01/a.md", "szakasz": "Gyakorlás", "szoveg": "MÁSIK"}))
        self.assertEqual(cm.exception.code, 409)
        self.assertTrue(cm.exception.data.get("utkozes"))
        self.assertNotIn("MÁSIK", self.olvas("T01/a.md").decode())
        self.assertEqual(self.repo.log(1)[0].sha, r1["sha"])                       # nincs új commit
        self.assertEqual(self.repo.log(1)[0].trailers["Mos-Keres"], self.repo.log(1)[0].trailers["Mos-Keres"])
        self.assertEqual(self.G.ir(k1)["ismetles"], True)                          # azonos tartalom: marad az ismétlés

    def test_regi_commit_trailer_nelkul_egyezonek_szamit(self):
        """A `Mos-Keres` előtti (C16.5–C29.5) commitoknak nincs ujjlenyomatuk: az ismétlésük nem ütközés."""
        k = self.keres({"tipus": "beszuras", "ut": "T01/a.md", "szakasz": "Gyakorlás", "szoveg": "egyszer"})
        r1 = self.G.ir(k)
        # a commit-üzenetből eltávolítva a Mos-Keres (a régi alak)
        c = self.repo.log(1)[0]
        uzenet = self.repo.git("show", "-s", "--format=%B", c.sha).stdout
        uj = "".join(l for l in uzenet.splitlines(True) if not l.startswith("Mos-Keres:"))
        self.repo.git("commit", "--amend", "-q", "--no-verify", "-F", "-", input=uj)
        r2 = self.G.ir(k)
        self.assertTrue(r2["ismetles"])

    def test_visszavonas_korre_ket_tetel(self):
        elotte = lenyomat(self.v)
        self.G.ir(self.keres({"tipus": "beszuras", "ut": "T01/a.md", "szakasz": "Gyakorlás", "szoveg": "egy"}))
        self.G.ir(self.keres({"tipus": "beszuras", "ut": "T01/a.md", "szakasz": "Gyakorlás", "szoveg": "kettő"},
                             {"tipus": "uj", "ut": "T01/uj.md", "tartalom": FM + "# uj\n", "osztaly": "normal"},
                             tetel="t2"))
        self.assertEqual(len(self.repo.log(run="KARTYA-20261003-101500")), 2)
        self.repo.undo_run("KARTYA-20261003-101500")
        self.assertEqual(lenyomat(self.v), elotte)

    def test_crlf_marad(self):
        self.G.ir(self.keres({"tipus": "beszuras", "ut": "T01/crlf.md", "szakasz": "Gyakorlás", "szoveg": "új\nkét sor"},
                             {"tipus": "uj", "ut": "T01/v.canvas", "tartalom": '{"nodes":[],"edges":[]}'}))
        self.assertEqual(self.olvas("T01/crlf.md"), "# C\r\n\r\n## Gyakorlás\r\nsor\r\núj\r\nkét sor\r\n".encode())


class EllenorzesTest(Alap):
    def test_hibas_keres_400(self):
        m = {"tipus": "beszuras", "ut": "T01/a.md", "szakasz": "Gyakorlás", "szoveg": "x"}
        for tobbi in ({"kor": "kartya-1"}, {"kor": "SZERK-20261003-101500"}, {"kor": "KARTYA-20261003-101500-proba"},
                      {"forras": "kezi"}, {"forras": "pult-szerkeszto"}, {"forras": "Nagy Betű"}, {"tetel": ""},
                      {"tetel": "két\nsor"}, {"proba": "igen"}, {"feladat": "nem-feladat"}, {"modell": {"modell": "x"}},
                      {"modell": NINCS}, {"modell": "szöveg"}, {"modell": {"feladat": "nincs_ilyen_feladat", "modell": "x"}},
                      {"modell": {"feladat": "szoveg", "modell": "x", "proba": "igen"}},
                      {"muveletek": []}, {"muveletek": [m, dict(m)]}, {"muveletek": [dict(m, tipus="torles")]},
                      {"muveletek": [dict(m, hova="kozepe")]}, {"muveletek": [dict(m, szoveg=" \n")]}):
            with self.subTest(tobbi):
                self.hiba(400, **{"muveletek": [m], **tobbi})

    def test_ut_es_tipus(self):
        kulso = Path(self._t.name) / "kulso"
        kulso.mkdir()
        (kulso / "x.md").write_text("# kint\n", encoding="utf-8")
        os.symlink(kulso, self.v / "link")
        for ut in ("../kint.md", ".obsidian/app.md", "T01/.rejtett.md", "link/x.md", "T01/kep.png", "T01/x.pdf", ""):
            with self.subTest(ut):
                self.hiba(400, {"tipus": "uj", "ut": ut, "tartalom": "x"})
        self.hiba(400, {"tipus": "beszuras", "ut": "link/x.md", "szakasz": "kint", "szoveg": "x", "letrehoz": True})
        self.assertEqual((kulso / "x.md").read_text(encoding="utf-8"), "# kint\n")
        self.hiba(400, {"tipus": "uj", "ut": "T01/Mi?.canvas", "tartalom": "{}"})          # új fájlban tiltott jel
        self.hiba(400, {"tipus": "uj", "ut": "T0|2/x.md", "tartalom": FM, "osztaly": "normal"})
        self.hiba(400, {"tipus": "uj", "ut": "T01/v.canvas", "tartalom": '{"nodes": ['})   # hibás JSON Canvas
        self.hiba(409, {"tipus": "uj", "ut": "t01/A.MD", "tartalom": FM, "osztaly": "normal"})   # létezik (kisbetűvel is)
        self.hiba(404, {"tipus": "csere", "ut": "T01/nincs.md", "tartalom": "x", "alap": "0" * 40})
        self.hiba(404, {"tipus": "beszuras", "ut": "T01/a.md", "szakasz": "Nincs ilyen", "szoveg": "x"})
        self.hiba(400, {"tipus": "beszuras", "ut": SEMA_NELKULI, "szakasz": "ügynök", "szoveg": "x"})

    def test_ugynok_hordozo_fajl_barmely_melysegben_tiltott(self):
        """A kapu a fájlnevet nézi (nem a pontos utat): beágyazott `CLAUDE.md` / `AGENTS.md` / `MEMORY.md`, bármilyen kis-nagybetűvel
        sem írható géppel — sem új fájlként, sem cserével, sem szakasz alá beszúrással."""
        for ut in UGYNOK_UTAK:
            with self.subTest(ut):
                self.hiba(400, {"tipus": "uj", "ut": ut, "tartalom": "# ügynök\n"})
                self.hiba(400, {"tipus": "csere", "ut": ut, "tartalom": "x", "alap": "0" * 40})
                self.hiba(400, {"tipus": "beszuras", "ut": ut, "szakasz": "ügynök", "szoveg": "x", "letrehoz": True})

    def test_alap_hash_utkozes(self):
        e = self.hiba(409, {"tipus": "csere", "ut": "T01/a.md", "tartalom": "x", "alap": "0" * 40})
        self.assertEqual(e.data, {"ut": "T01/a.md", "hash": self.hash("T01/a.md")})
        self.hiba(400, {"tipus": "csere", "ut": "T01/a.md", "tartalom": "x"})               # vakon nem ír
        self.hiba(409, {"tipus": "beszuras", "ut": "T01/a.md", "szakasz": "Más", "szoveg": "x", "alap": "0" * 40})

    def test_sema_status_es_osztaly(self):
        uj = lambda t, o="normal", ut="T01/uj.md": {"tipus": "uj", "ut": ut, "tartalom": t, "osztaly": o}  # noqa: E731
        self.assertTrue(self.hiba(400, uj(FM.replace("Status:", "Status: Completed"))).data["sema"])   # gép nem tölti
        self.hiba(400, uj("# frontmatter nélkül\n"))                                   # bejegyzetlen jegyzetfajta
        self.hiba(400, uj("---\nSource:\nKviz:\nModell:\nKeszult:\n---\n", "kviz"))    # az út szerint normal
        self.hiba(400, uj(FM, None))                                                   # az osztályt meg kell nevezni
        self.hiba(400, uj(FM, "normal", "ATTCHMNTS - quizes/x.md"))                    # az út szerint kviz
        e = self.hiba(400, uj(FM.replace("Tags:", "Tags:\n  - Nincs-ilyen")))
        self.assertEqual(e.data["problemak"][0]["kod"], "ertekkeszlet")
        self.hiba(400, uj("---\nTags:\nicon: x\nSource:\nStatus:\nNN:\nCanvas:\n---\n"))
        # csere: a Status nem változhat, új sértés nem jöhet; a meglévő érték maradhat
        cs = lambda t: {"tipus": "csere", "ut": "T01/kesz.md", "tartalom": t, "alap": self.hash("T01/kesz.md")}  # noqa: E731
        self.hiba(400, cs(ALAP["T01/kesz.md"].replace("Completed", "Review")))
        self.hiba(400, cs(ALAP["T01/kesz.md"].replace("Status: Completed", "Status:")))
        self.hiba(400, cs(ALAP["T01/kesz.md"].replace("NN:", "NN:\nicon: x")))
        self.assertTrue(self.G.ir(self.keres(cs(ALAP["T01/kesz.md"] + "törzs\n")))["valtozas"])

    def test_nyitott_mentetlen_dokumentum(self):
        self.mentetlen.add("T01/a.md")
        e = self.hiba(409, {"tipus": "uj", "ut": "T01/uj.md", "tartalom": FM + "# uj\n", "osztaly": "normal"},
                      {"tipus": "beszuras", "ut": "T01/a.md", "szakasz": "Más", "szoveg": "gépi"})
        self.assertEqual((e.data["nyitott"], e.data["utak"]), (True, ["T01/a.md"]))
        self.mentetlen.clear()
        self.assertTrue(self.G.ir(self.keres({"tipus": "beszuras", "ut": "T01/a.md", "szakasz": "Más", "szoveg": "g"}))["ok"])

    def test_foglalt_kor_zar(self):
        lock = frame.lock_path(self.cfg)
        lock.parent.mkdir(parents=True, exist_ok=True)
        with open(lock, "a+") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            e = self.hiba(409, {"tipus": "beszuras", "ut": "T01/a.md", "szakasz": "Más", "szoveg": "gépi"})
            self.assertTrue(e.data["foglalt"])

    def test_git_hiba_nincs_iras(self):
        (self.repo.git_dir / "index.lock").write_text("")                # elakadt zár: a kézi commit elbukik
        e = self.hiba(503, {"tipus": "beszuras", "ut": "T01/a.md", "szakasz": "Más", "szoveg": "gépi"})
        self.assertTrue(e.data["pillanat_hiba"])
        (self.repo.git_dir / "index.lock").unlink()
        ures = gepi_iras.GepiIras(self.cfg, vaultio.Vault(self.cfg), self.G.tul)
        os.rename(self.repo.git_dir, self.repo.git_dir.with_name("el.git"))
        with self.assertRaises(HttpError) as cm:
            ures.ir(self.keres({"tipus": "beszuras", "ut": "T01/a.md", "szakasz": "Más", "szoveg": "gépi"}))
        self.assertEqual(cm.exception.code, 503)
        self.assertEqual(self.olvas("T01/a.md").decode(), ALAP["T01/a.md"])

    def test_hiba_a_masodik_muveletnel_visszaall(self):
        """Az első két művelet lemezre kerül, a harmadik írása ütközik: minden visszaáll, commit és napló nincs."""
        eredeti = self.G._fajl_ir

        def ir_hibaval(f, lepesek):
            if f.ut == "T01/kesz.md":
                f.p.write_bytes(b"valaki kozben atirta\n")               # az írás pillanatában más is írt
            return eredeti(f, lepesek)
        self.G._fajl_ir = ir_hibaval
        elotte = lenyomat(self.v)
        with self.assertRaises(vaultio.Conflict):
            self.G.ir(self.keres(
                {"tipus": "uj", "ut": "Új/uj.md", "tartalom": FM + "# uj\n", "osztaly": "normal"},
                {"tipus": "beszuras", "ut": "T01/a.md", "szakasz": "Más", "szoveg": "gépi"},
                {"tipus": "csere", "ut": "T01/kesz.md", "tartalom": ALAP["T01/kesz.md"] + "x\n",
                 "alap": self.hash("T01/kesz.md")}))
        elotte["T01/kesz.md"] = b"valaki kozben atirta\n"
        self.assertEqual(lenyomat(self.v), elotte)
        self.assertFalse((self.cfg.path("run") / gepi_iras.NAPLO).exists())
        self.assertEqual(self.repo.log(run="KARTYA-20261003-101500"), [])

    def test_d9_elavult_aranyverzion_kalibralt_modell_nem_ir_elesben(self):
        """Lelet 7: a D9 írás-kapu is csak az aranyhalmaz AKTUÁLIS verzióján mért kalibrált sort fogadja el (mint a router)."""
        t = kalibracio.Tabla(self.cfg.path("router_db"))
        t.rogzit("szoveg", "jo-modell", 0.9, "v1", kalibralt=True)
        t.close()
        m = {"tipus": "beszuras", "ut": "T01/a.md", "szakasz": "Más", "szoveg": "gépi"}
        self.aranyverzio("szoveg", "v2")                                  # az arany közben új verziót kapott
        e = self.hiba(400, m, modell={"feladat": "szoveg", "modell": "jo-modell"})
        self.assertTrue(e.data["kalibralatlan"])
        self.aranyverzio("szoveg", "v1")                                  # az aktuális verzión mért sor írhat
        self.assertTrue(self.G.ir(self.keres(m, modell={"feladat": "szoveg", "modell": "jo-modell"}))["valtozas"])

    def test_d9_kalibralatlan_modell(self):
        self.aranyverzio("szoveg", "v1")
        t = kalibracio.Tabla(self.cfg.path("router_db"))
        t.rogzit("szoveg", "jo-modell", 0.9, "v1", kalibralt=True)
        t.rogzit("szoveg", "mert-modell", 0.5, "v1", kalibralt=False)
        t.close()
        m = {"tipus": "beszuras", "ut": "T01/a.md", "szakasz": "Más", "szoveg": "gépi"}
        for modell in ("mert-modell", "ismeretlen"):
            e = self.hiba(400, m, modell={"feladat": "szoveg", "modell": modell})
            self.assertTrue(e.data["kalibralatlan"])
        self.assertTrue(self.G.ir(self.keres(m, modell={"feladat": "szoveg", "modell": "jo-modell"}))["valtozas"])


class AuditKapukTest(Alap):
    """C29.8a (2. audit): a gépi írás kapui — a H1-szabály (T044), a Status-tilalom változatai (T127), az új hiányzó kulcs
    (T133) és a forrás alakja (T135). Mind a javítás ELŐTT bukott."""

    @staticmethod
    def uj(tartalom, ut="T01/Új jegyzet.md", osztaly="normal"):
        return {"tipus": "uj", "ut": ut, "tartalom": tartalom, "osztaly": osztaly}

    def cs(self, ut, tart):
        return {"tipus": "csere", "ut": ut, "tartalom": tart, "alap": self.hash(ut)}

    # ---- T044
    def test_h1_szabaly_uj_jegyzetnel(self):
        e = self.hiba(400, self.uj(FM + "# Valami más\n"))                  # ma: 200, a fájlnévtől eltérő H1-gyel ír
        self.assertTrue(e.data["sema"])
        self.assertEqual(e.data["problemak"][0]["kod"], "h1")
        e = self.hiba(400, self.uj(FM + "H1 nélkül\n"))
        self.assertEqual(e.data["problemak"][0]["kod"], "h1_hiany")
        kv = "---\nSource:\nKviz:\nModell:\nKeszult:\n---\n"
        self.hiba(400, self.uj(kv + "# Alma\n", "ATTCHMNTS - quizes/Alma — Kvíz 2026-10-03 1015.md", "kviz"))   # nem a kvíz-minta
        self.hiba(400, self.uj(kv + "# Béla — Kvíz 2026-10-03 1015\n", "ATTCHMNTS - quizes/Alma — Kvíz 2026-10-03 1015.md", "kviz"))
        r = self.G.ir(self.keres(
            self.uj(FM + "# Új jegyzet\n"),                                                    # H1 == fájlnév
            self.uj(FM + "# Elsőként\n", "T01/07 - Elsőként.md"),                                # a sorszám-előtag nélkül
            self.uj(FM + "# Bármi más\n", H1_KIVETEL),                                            # kivétel-útvonal
            self.uj(kv + "# Alma — Kvíz 2026-10-03 1015\n", "ATTCHMNTS - quizes/Alma — Kvíz 2026-10-03 1015.md", "kviz")))
        self.assertTrue(r["ok"] and r["valtozas"])

    def test_h1_csere_es_beszuras_csak_az_uj_sertest_tiltja(self):
        ir(self.v, "T01/Más cím.md", FM + "# Egészen más\n\n## Gyakorlás\nx\n")        # már előtte sértett: marad
        self.assertTrue(self.G.ir(self.keres(self.cs("T01/Más cím.md", FM + "# Egészen más\n\n## Gyakorlás\nx\ny\n")))["valtozas"])
        self.hiba(400, self.cs("T01/Más cím.md", FM + "# Megint más\n"), tetel="t2")      # új H1-sértés (más H1)
        self.hiba(400, self.cs("T01/Más cím.md", FM + "H1 nélkül\n"), tetel="t3")        # a H1 elvesztése is új sértés
        # beszúrás: a H1 nélküli (már sértett) jegyzetbe a szakasz alá beszúrt új H1 más sértést hoz: új sértés
        ir(self.v, "T01/H1 nélkül.md", FM + "## Gyakorlás\nx\n")
        self.hiba(400, {"tipus": "beszuras", "ut": "T01/H1 nélkül.md", "szakasz": "Gyakorlás", "szoveg": "# Másik fejléc"}, tetel="t5")

    # ---- T127
    def test_status_tilalom_kis_nagybetus_kulccsal_es_torlessel(self):
        tart = "---\nTags:\nSource:\nstatus: Completed\nNN:\nCanvas:\n---\n# kk\n"
        ir(self.v, "T01/kk.md", tart)
        self.hiba(400, self.cs("T01/kk.md", tart.replace("status: Completed", "status: Review")))   # ma: átmegy
        self.hiba(400, self.cs("T01/kk.md", tart.replace("status: Completed\n", "")))               # törlés
        self.hiba(400, self.cs("T01/kk.md", tart.replace("status: Completed", "STATUS: Completed")))  # átnevezés
        self.assertTrue(self.G.ir(self.keres(self.cs("T01/kk.md", tart + "törzs\n")))["valtozas"])    # a Status változatlan: mehet

    # ---- T133
    def test_hianyos_jegyzetben_ujabb_kulcs_torlese_400(self):
        tart = "---\nTags:\nSource:\nNN:\nCanvas:\n---\n# hianyos\n"                          # nincs Status
        ir(self.v, "T01/hianyos.md", tart)
        for kulcs in ("Tags", "Source", "NN", "Canvas"):
            self.hiba(400, self.cs("T01/hianyos.md", tart.replace(f"{kulcs}:\n", "")))              # ma: átmegy
        self.assertTrue(self.G.ir(self.keres(self.cs("T01/hianyos.md", tart + "törzs\n")))["valtozas"])

    # ---- T043 (a D9-kapu nem a kérés önkéntes mezőjén múlik; a 28(g) pontosítása)
    def test_modell_kulcs_kotelezo_es_a_feladat_a_routeré(self):
        m = {"tipus": "beszuras", "ut": "T01/a.md", "szakasz": "Más", "szoveg": "gépi"}
        e = self.hiba(400, m, modell=NINCS)                         # ma: a `modell` nélküli kérés átmegy, élesben ír
        self.assertIn("modell", str(e))
        self.hiba(400, m, modell={"feladat": "nincs_ilyen_feladat", "modell": "jo-modell"})     # nem a `[router] feladatok` eleme
        self.assertEqual(self.olvas("T01/a.md").decode(), ALAP["T01/a.md"])
        self.assertTrue(self.G.ir(self.keres(m, modell=None))["valtozas"])                       # a determinisztikus írás kifejezett null-lal

    def test_proba_jelzesu_modell_kimenete_elesben_nem_irhato(self):
        """A worker válasza `proba: true`, ha a modell kifejezett kérésre (kalibrálatlanul is) futott: az ilyen kimenet éles
        írásra tilos, akkor is, ha a (feladat, modell) pár történetesen kalibrált; próba-kérésben (klónon) rendben van."""
        self.aranyverzio("szoveg", "v1")
        t = kalibracio.Tabla(self.cfg.path("router_db"))
        t.rogzit("szoveg", "jo-modell", 0.9, "v1", kalibralt=True)
        t.close()
        m = {"tipus": "beszuras", "ut": "T01/a.md", "szakasz": "Más", "szoveg": "gépi"}
        e = self.hiba(400, m, modell={"feladat": "szoveg", "modell": "jo-modell", "proba": True})
        self.assertTrue(e.data["kalibralatlan"])
        self.assertTrue(self.G.ir(self.keres(m, modell={"feladat": "szoveg", "modell": "jo-modell", "proba": False}))["valtozas"])

    # ---- T135
    def test_forras_alakja(self):
        m = {"tipus": "beszuras", "ut": "T01/a.md", "szakasz": "Más", "szoveg": "gépi"}
        for forras in ("kezi-x", "pult-x", "pult", "kezi", "kartya", "mos-", "mos-X", "mos kartya", "mos-" + "a" * 37):
            with self.subTest(forras):
                self.hiba(400, m, forras=forras)
        r = self.G.ir(self.keres(m, forras="mos-" + "a" * 36))
        self.assertEqual(self.repo.log(1)[0].trailers["Mos-Forras"], "mos-" + "a" * 36)
        self.assertTrue(r["ok"])


class IndexTest(Alap):
    def test_az_index_nem_latja_kulsonek(self):
        ix, _ = index_indit(self.cfg)
        self.addCleanup(ix.leallit)
        valt = []
        ix.publish = lambda e, **k: valt.append(e)

        def kozzetesz(e, **k):
            self.esemenyek.append(e)
            if e["tipus"] == "vault_iras":
                ix.sajat_iras(e["ut"], e["hash"])
        g = gepi_iras.GepiIras(self.cfg, self.V, self.G.tul, publish=kozzetesz, sajat=ix.vart_iras)
        g.ir(self.keres({"tipus": "beszuras", "ut": "T01/a.md", "szakasz": "Más", "szoveg": "[[kesz]]"},
                        {"tipus": "uj", "ut": "T01/uj.md", "tartalom": FM + "# uj\n", "osztaly": "normal"}))
        ix.frissit([], var=5)
        erintett = [e for e in valt if e["tipus"] == "vault_valtozas"]
        self.assertEqual({u for e in erintett for u in e["utak"]}, {"T01/a.md", "T01/uj.md"})
        self.assertEqual([u for e in erintett for u in e["kulso"]], [])
        self.assertEqual(ix.jegyzet("T01/a.md")["linkek"][0]["cel"], "T01/kesz.md")     # az index friss


CRASH = """
import os, sys
sys.path.insert(0, sys.argv[1])
from core import config, gepi_iras, snapshot, vaultio
from core.tulajdonsagok import Tulajdonsagok
cfg = config.load()
snapshot.Repo.commit_machine = lambda *a, **k: os._exit(9)      # a folyamat az írások után, a commit előtt hal meg
g = gepi_iras.GepiIras(cfg, vaultio.Vault(cfg), Tulajdonsagok(cfg, None))
g.ir({"kor": "KARTYA-20261003-101500", "tetel": "t1", "forras": "mos-kartya", "modell": None, "muveletek": [
    {"tipus": "uj", "ut": "Uj/Belso/uj.md", "tartalom": sys.argv[2], "osztaly": "normal"},
    {"tipus": "beszuras", "ut": "T01/a.md", "szakasz": "Más", "szoveg": "gépi"},
    {"tipus": "beszuras", "ut": "T01/crlf.md", "szakasz": "Gyakorlás", "szoveg": "gépi"}]})
"""


class MegszakadtTest(Alap):
    def _crash(self):
        p = subprocess.run([sys.executable, "-B", "-c", CRASH, str(REPO), FM + "# uj\n"], capture_output=True, text=True,
                           env=env(MOS_ROOT=str(self.root), HOME=str(Path(self._t.name) / "home")))
        self.assertEqual(p.returncode, 9, p.stderr)
        self.assertTrue((self.cfg.path("run") / gepi_iras.NAPLO / "terv.json").is_file())
        self.assertTrue((self.v / "Uj/Belso/uj.md").is_file())           # az írások megtörténtek
        self.assertIn(b"g\xc3\xa9pi", self.olvas("T01/a.md"))

    def test_indulas_visszaallit(self):
        elotte = lenyomat(self.v)
        self._crash()
        with frame.indulasi_zar(self.cfg) as van:
            self.assertTrue(van)
            (uzenet,) = gepi_iras.helyreallit(self.cfg)
        self.assertIn("megszakadt", uzenet)
        self.assertEqual(lenyomat(self.v), elotte)                      # bájtra, az új fájl és mappái nélkül
        self.assertFalse((self.cfg.path("run") / gepi_iras.NAPLO).exists())
        self.assertEqual(gepi_iras.helyreallit(self.cfg), [])
        self.assertEqual(self.repo.log(run="KARTYA-20261003-101500"), [])
        # a tétel újra futtatható
        self.assertTrue(self.G.ir(self.keres({"tipus": "beszuras", "ut": "T01/a.md", "szakasz": "Más", "szoveg": "g"}))["ok"])

    def test_kozben_atirt_fajlt_nem_bant(self):
        self._crash()
        (self.v / "T01/a.md").write_bytes(b"a gazda kozben atirta\n")
        (self.v / "Uj/Belso/uj.md").write_bytes(b"ezt is\n")
        (uzenet,) = gepi_iras.helyreallit(self.cfg)
        self.assertIn("T01/a.md", uzenet)
        self.assertEqual(self.olvas("T01/a.md"), b"a gazda kozben atirta\n")
        self.assertEqual(self.olvas("Uj/Belso/uj.md"), b"ezt is\n")
        self.assertEqual(self.olvas("T01/crlf.md"), ALAP["T01/crlf.md"].encode())      # ez visszaállt
        megtartva = [d for d in self.cfg.path("run").iterdir() if d.name.startswith("gepi-iras-megtartva-")]
        self.assertEqual(len(megtartva), 1)
        self.assertEqual(len(list((megtartva[0] / "eredeti").iterdir())), 3)

    def test_nem_letezo_vaulton_a_naplo_erintetlen(self):
        """T002 (2. audit): nem létező vaulton (symlinkelt `var/`-ú munkafa) a helyreállítás nem nyúl a naplóhoz,
        és nem ad hamis „visszaállt” üzenetet; a valódi vaulton később még visszaáll."""
        elotte = lenyomat(self.v)
        self._crash()
        elmozgatva = self.v.with_name("Manifold-elmozgatva")
        self.v.rename(elmozgatva)
        self.assertEqual(gepi_iras.helyreallit(self.cfg), [])
        self.assertTrue((self.cfg.path("run") / gepi_iras.NAPLO / "terv.json").is_file())
        elmozgatva.rename(self.v)
        (uzenet,) = gepi_iras.helyreallit(self.cfg)
        self.assertIn("visszaállt", uzenet)
        self.assertEqual(lenyomat(self.v), elotte)

    def test_az_uzenet_nem_allit_visszaallast_ha_semmi_nem_allt_vissza(self):
        """T002: a napló kész, de az írások még meg sem történtek (egy módosított és egy új fájl terve): nincs mit
        visszaállítani, az üzenet ezt mondja, és a napló törlődik."""
        d = self.cfg.path("run") / gepi_iras.NAPLO
        (d / "eredeti").mkdir(parents=True)
        (d / "eredeti" / "0.bin").write_bytes(ALAP["T01/a.md"].encode())
        (d / "terv.json").write_text(json.dumps({"kor": "KARTYA-20261003-101500", "tetel": "t1", "feladat": None, "fajlok": [
            {"ut": "T01/a.md", "lemez": "T01/a.md", "eredeti": "0.bin", "uj_fajl": False, "uj_sha1": "0" * 40, "mappak": []},
            {"ut": "Uj/uj.md", "lemez": "Uj/uj.md", "eredeti": "0.bin", "uj_fajl": True, "uj_sha1": "0" * 40,
             "mappak": ["Uj"]}]}))
        elotte = lenyomat(self.v)
        (uzenet,) = gepi_iras.helyreallit(self.cfg)
        self.assertEqual(lenyomat(self.v), elotte)
        self.assertNotIn("visszaállt", uzenet)
        self.assertIn("nem kellett", uzenet)
        self.assertFalse(d.exists())

    def test_commit_utan_maradt_naplo_csak_torlodik(self):
        r = self.G.ir(self.keres({"tipus": "beszuras", "ut": "T01/a.md", "szakasz": "Más", "szoveg": "gépi"}))
        d = self.cfg.path("run") / gepi_iras.NAPLO
        (d / "eredeti").mkdir(parents=True)
        (d / "eredeti" / "0.bin").write_bytes(ALAP["T01/a.md"].encode())
        (d / "terv.json").write_text(json.dumps({"kor": r["kor"], "tetel": "t1", "feladat": None, "fajlok": [
            {"ut": "T01/a.md", "lemez": "T01/a.md", "eredeti": "0.bin", "uj_fajl": False,
             "uj_sha1": r["hash"]["T01/a.md"], "mappak": []}]}))
        utana = self.olvas("T01/a.md")
        self.assertEqual(gepi_iras.helyreallit(self.cfg), [])
        self.assertEqual(self.olvas("T01/a.md"), utana)
        self.assertFalse(d.exists())


class ProbaTest(Alap):
    def test_proba_a_klonon_az_eles_erintetlen(self):
        elotte, fej = lenyomat(self.v), self.repo.git("rev-parse", "HEAD").stdout
        m = [{"tipus": "beszuras", "ut": "T01/a.md", "szakasz": "Más", "szoveg": "próba"},
             {"tipus": "uj", "ut": "T01/uj.md", "tartalom": FM + "# uj\n", "osztaly": "normal"}]
        try:
            r = self.G.ir(self.keres(*m, proba=True, modell={"feladat": "szoveg", "modell": "kalibralatlan"}))
        except HttpError as e:
            if "klón" in str(e):
                self.skipTest(f"[indokolt] APFS-klón nem készíthető itt: {e}")
            raise
        self.assertEqual((r["kor"], r["proba"]), ("KARTYA-20261003-101500-proba", True))
        self.assertEqual(lenyomat(self.v), elotte)                      # az éles vault bájtra érintetlen
        self.assertEqual(self.repo.git("rev-parse", "HEAD").stdout, fej)
        self.assertFalse((self.cfg.path("run") / "kor.lock").exists())
        klon = Path(r["proba_mappa"])
        self.assertEqual(klon, self.cfg.path("tmp") / "proba" / "KARTYA-20261003-101500-proba")
        self.assertIn("próba", (klon / "Manifold/T01/a.md").read_text(encoding="utf-8"))
        krepo = snapshot.Repo("vault", klon / "Manifold", klon / "vault.git")
        self.assertEqual(krepo.log(1)[0].trailers["Mos-Kor"], "KARTYA-20261003-101500-proba")
        self.assertEqual(krepo.log(1)[0].sha, r["sha"])
        (g,) = [e for e in self.esemenyek if e["tipus"] == "gepi_iras"]
        self.assertTrue(g["proba"])
        self.assertEqual([e for e in self.esemenyek if e["tipus"] == "vault_iras"], [])
        # a kör második tétele ugyanarra a klónra megy
        r2 = self.G.ir(self.keres({"tipus": "beszuras", "ut": "T01/uj.md", "szakasz": "uj", "szoveg": "2"}, tetel="t2",
                                  proba=True))
        self.assertEqual(r2["proba_mappa"], r["proba_mappa"])
        self.assertEqual(len(krepo.log(run="KARTYA-20261003-101500-proba")), 2)
        # B-javító 8: a klón jelölt — a doctor látja, és a kor-alapú takarítás csak jelölt mappát töröl
        jel = json.loads((klon / frame.PROBA_JELOLO).read_text(encoding="utf-8"))
        self.assertEqual((jel["szkript"], jel["kor"], jel["pid"]), ("gepi_iras", "KARTYA-20261003-101500-proba", os.getpid()))

    def _klon_mappa(self, nev: str, nap: float, pid: int | None, jelolt: bool = True) -> Path:
        import datetime as dt
        d = self.cfg.path("tmp") / "proba" / nev
        (d / "vault.git").mkdir(parents=True)
        if jelolt:
            (d / frame.PROBA_JELOLO).write_text(json.dumps({
                "szkript": "gepi_iras", "kor": nev, "pid": pid, "megtart": False,
                "letrehozva": (dt.datetime.now() - dt.timedelta(days=nap)).isoformat(timespec="seconds")}), encoding="utf-8")
        return d

    def test_regi_gepi_proba_klon_takaritasa(self):
        """B-javító 8: a `[vault] proba_klon_max_nap`-nál (7) régebbi, jelölt, gazdátlan gépi próbaklón törlődik; a friss,
        a jelöletlen, a kivételként megadott és az élő másik folyamaté marad."""
        halott = subprocess.Popen([sys.executable, "-c", "pass"])
        halott.wait()
        regi = self._klon_mappa("A-20260901-100000-proba", 10, halott.pid)
        friss = self._klon_mappa("B-20261013-100000-proba", 1, halott.pid)
        jelotlen = self._klon_mappa("C-20260901-100000-proba", 10, None, jelolt=False)
        kiveve = self._klon_mappa("D-20260901-100000-proba", 10, os.getpid())
        elo = self._klon_mappa("E-20260901-100000-proba", 10, os.getppid())
        torolt = frame.proba_klon_takaritas(self.cfg, kiveve=[kiveve])
        self.assertEqual(torolt, ["A-20260901-100000-proba"])
        self.assertFalse(regi.exists())
        self.assertTrue(friss.is_dir() and jelotlen.is_dir() and kiveve.is_dir() and elo.is_dir())
        self.cfg.data["vault"]["proba_klon_max_nap"] = 0                # 0: soha
        self.assertEqual(frame.proba_klon_takaritas(self.cfg), [])


class SzakaszTest(unittest.TestCase):
    def test_vege_es_eleje(self):
        t = "# A\n\n## Gy\nx\ny\n\n\n## Más\nz"
        self.assertEqual(szakasz_beszur(t, "Gy", "új"), "# A\n\n## Gy\nx\ny\núj\n\n\n## Más\nz")
        self.assertEqual(szakasz_beszur(t, "Gy", "új", "eleje"), "# A\n\n## Gy\núj\nx\ny\n\n\n## Más\nz")
        self.assertEqual(szakasz_beszur(t, "Más", "új"), "# A\n\n## Gy\nx\ny\n\n\n## Más\nz\núj\n")
        self.assertEqual(szakasz_beszur(t, "## Más", "új", "eleje"), "# A\n\n## Gy\nx\ny\n\n\n## Más\núj\nz")
        self.assertEqual(szakasz_beszur("## Üres", "Üres", "új"), "## Üres\núj\n")
        self.assertEqual(szakasz_beszur("## Üres\n\n## B\n", "Üres", "új"), "## Üres\núj\n\n## B\n")

    def test_alszakasz_a_szakasz_resze(self):
        t = "## Gy\nx\n### Al\ny\n## Más\n"
        self.assertEqual(szakasz_beszur(t, "Gy", "új"), "## Gy\nx\n### Al\ny\núj\n## Más\n")
        self.assertEqual(szakasz_beszur(t, "Al", "új"), "## Gy\nx\n### Al\ny\núj\n## Más\n")

    def test_kodblokk_es_frontmatter_nem_fejezet(self):
        t = "---\nTags:\n# Gy\n---\n```\n## Gy\n```\n\n## Gy\nvalódi\n"
        self.assertEqual(szakasz_beszur(t, "Gy", "új"), t + "új\n")

    def test_ismetlodo_hianyzo_letrehoz(self):
        with self.assertRaises(HttpError) as cm:
            szakasz_beszur("## Gy\n\n## Gy\n", "Gy", "x")
        self.assertEqual(cm.exception.code, 409)
        self.assertEqual(szakasz_beszur("# Gy\n\n## Gy\n", "## Gy", "x"), "# Gy\n\n## Gy\nx\n")     # a szint egyértelműsít
        with self.assertRaises(vaultio.NotFound):
            szakasz_beszur("# A\n", "Gy", "x")
        self.assertEqual(szakasz_beszur("# A\nszöveg\n\n", "Gy", "x", letrehoz=True), "# A\nszöveg\n\n## Gy\nx\n")
        self.assertEqual(szakasz_beszur("", "### Gy", "x", letrehoz=True), "### Gy\nx\n")
        self.assertEqual(szakasz_beszur("---\nTags:\n---\n", "Gy", "x", letrehoz=True), "---\nTags:\n---\n\n## Gy\nx\n")

    def test_mar_ott_all_valtozatlan(self):
        t = "## Gy\n![[a]]\n![[b]]\n"
        self.assertIs(szakasz_beszur(t, "Gy", "![[a]]"), t)
        self.assertEqual(szakasz_beszur(t, "Gy", "![[a]]\n![[c]]"), "## Gy\n![[a]]\n![[b]]\n![[a]]\n![[c]]\n")

    def test_crlf_es_vegyes(self):
        self.assertEqual(szakasz_beszur("## Gy\r\nx\r\n", "Gy", "a\nb"), "## Gy\r\nx\r\na\r\nb\r\n")
        with self.assertRaises(vaultio.Invalid):
            szakasz_beszur("## Gy\r\nx\ny\r\n", "Gy", "a")


if __name__ == "__main__":
    unittest.main()
