"""F8: the demo workspace generator and its start/reset (`core/demo.py`, `core/demo_*.py`, launcher `demo` / `demo_reset`).

Everything is synthetic and temporary: a fake product install (`termek_telepites`), a fake HOME, no real vault, no model, no network.
The seven demo flows (open+search, links, properties/Bases, cards+quiz, maths, code, PDF) run on the generated library in
`test_demo_folyamatok.py`.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import unittest
import urllib.request
from pathlib import Path

import yaml

from core import config, demo, demo_tanulas, doku, indito, munkater_futo, naptar, snapshot, szemelyes_db, tanulas_db, workspace
from core.asszisztens.allapot import Allapot
from core.index import maszk
from core.utvonalak import HttpError
from tests.fresh_install import lenyomat
from tests.helpers import REPO, env, tmpdir
from tests.multi_user import termek_cfg, termek_telepites

LINK = re.compile(r"!?\[\[([^\]|#\n]+)(?:#[^\]|\n]*)?(?:\|[^\]\n]*)?\]\]")
MAGYAR = re.compile("[áéíóöőúüűÁÉÍÓÖŐÚÜŰ]")
# the format words the product's own card / quiz / PDF-highlight formats fix (parser keywords), the only Hungarian allowed
FORMATUM_SZAVAK = ("kártyák", "Kvíz", "kérdés", "Megoldás", "Magyarázat", "jegyzetben", "kiemelések", "oldal")
MAGYAR_MINTA_JEGYZET = "Writing in two languages.md"       # the shipped bilingual sample paragraph
TILTOTT = ("/Users/", "/Volumes/", "/private/", "glodi", "gmail", "ATTCHMNTS", "X01 -", "AI01", "AI02", "Prjct", "Zanza", "zanza", "ropdolgozat",
           "Notebooks - digitalized", "Rendezetlen", "D13 -", "Manifold-OS", "v2-kompat", "Tantárgy", "Dolgozatok", "Napló")


def szoveges(tart: dict[str, bytes]) -> dict[str, str]:
    return {u: b.decode("utf-8") for u, b in tart.items() if u.rsplit(".", 1)[-1] in ("md", "py", "js", "cpp", "base", "canvas", "json")}


class TartalomTest(unittest.TestCase):
    """The pure content: no workspace needed."""

    @classmethod
    def setUpClass(cls):
        cls.tart = demo.tartalom(demo.SEED)
        cls.szoveg = szoveges(cls.tart)

    def test_determinisztikus_ugyanaz_a_seed_ugyanazt_a_bajtot_adja(self):
        self.assertEqual(demo.tartalom(demo.SEED), self.tart)
        masik = demo.tartalom(demo.SEED + 1)
        self.assertEqual(set(masik), set(self.tart), "the seed changes sampled content, not the file set")
        self.assertNotEqual(masik, self.tart)
        self.assertEqual({u for u in self.tart if self.tart[u] != masik[u]} <= {u for u in self.tart if u.startswith(("Daily/", "Manifold -", "Maps/", "Attachments/Orbits"))}, True)

    def test_jegyzetek_szama_es_tipusai(self):
        n = demo.jegyzet_db(self.tart)
        self.assertTrue(50 <= n <= 100, n)
        self.assertLessEqual(len([u for u in self.tart if u.endswith(".md") and not u.startswith("Manifold Guide/")]), 100)
        md = {u: t for u, t in self.szoveg.items() if u.endswith(".md")}
        self.assertGreaterEqual(len([u for u in md if u.startswith("Daily/")]), 10, "daily notes")
        self.assertTrue(re.search(r"(?m)^- \[ \] ", "\n".join(md.values())) and re.search(r"(?m)^- \[x\] ", "\n".join(md.values())), "tasks, open and done")
        self.assertTrue(re.search(r"📅 \d{4}-\d{2}-\d{2}", "\n".join(md.values())), "dated tasks")
        self.assertGreaterEqual(sum(1 for t in md.values() if "\n$$" in t or "$" in t), 12, "LaTeX notes")
        self.assertGreaterEqual(sum(1 for t in md.values() if t.startswith("---\n")), 40, "notes with properties")
        self.assertGreaterEqual(len([u for u in self.tart if u.startswith("Attachments/") and u.endswith(".png")]), 4, "diagram notes")
        self.assertIn("```plot", md["Mathematics/Quadratic equations.md"])
        for ut in ("Maps/Learning map.canvas", "Bases/Reading list.base", "Bases/Projects.base", "Attachments/Orbits primer.pdf",
                   ".obsidian/types.json", "Attachments/Orbits primer – kiemelések.md"):
            self.assertIn(ut, self.tart)

    def test_utmutato_16_oldal_es_a_hivatkozasok_a_demon_belul_oldodnak(self):
        oldalak = sorted(u for u in self.tart if u.startswith("Manifold Guide/"))
        self.assertEqual(len(oldalak), 16)
        self.assertEqual(len(doku.OLDALAK), 16)
        self.assertEqual({u: self.tart[u] for u in oldalak}, doku.munkater_fajlok())
        nevek = {u.rsplit("/", 1)[-1][:-3] for u in self.tart if u.endswith(".md")}
        fejlecek = {u: set(doku.fejlecek(self.szoveg[u]).values()) for u in oldalak}
        for u in oldalak:
            t = maszk.mask_code(self.szoveg[u])
            for cel in LINK.findall(t):
                self.assertIn(cel.strip(), nevek, f"{u}: [[{cel}]] does not resolve inside the demo")
            for cel, alcel in re.findall(r"\[\[([^\]|#\n]+)#([^\]|\n]+)", t):
                fajl = f"Manifold Guide/{cel.strip()}.md"
                if fajl in fejlecek:
                    self.assertIn(alcel.strip().rstrip("\\"), fejlecek[fajl], f"{u}: heading {alcel!r} of {cel!r}")
        self.assertIn("[[Getting started]]", self.szoveg["Welcome.md"])

    def test_kod_matek_forrasok_haromnyelven(self):
        nyelvek = {u.rsplit(".", 1)[-1] for u in self.tart if u.startswith("Programming/code/")}
        self.assertEqual(nyelvek, {"py", "js", "cpp"})
        feladatok = [u for u in self.szoveg if u.startswith("Programming/") and u.endswith(").md")]
        self.assertEqual(len(feladatok), len(demo_tanulas.KOD_FELADATOK))
        for u in feladatok:
            self.assertIn("```teszt", self.szoveg[u])
            self.assertRegex(self.szoveg[u], r"!\[\[[\w-]+\.(py|js|cpp)\]\]")

    def test_nincs_szemelyes_adat_es_fejleszoi_nyom(self):
        for u, b in self.tart.items():
            szoveg = b.decode("latin-1") if u.endswith((".png", ".pdf")) else b.decode("utf-8")
            for t in TILTOTT:
                if t in ("Tantárgy", "Dolgozatok", "Napló") and u.endswith((".png", ".pdf")):
                    continue
                self.assertNotIn(t, szoveg, f"{u}: {t}")
            self.assertFalse(re.search(r"(?<![\w.])/(Users|Volumes|home|private|var|tmp|Library)/", szoveg), u)
            self.assertFalse(re.search(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", szoveg), f"{u}: e-mail address")
            for url in re.findall(r"https?://[^\s)\"'>\]]+", szoveg):
                self.assertTrue(url.startswith("https://example.com"), f"{u}: {url}")

    def test_a_felhasznaloi_szoveg_angol(self):
        for u, t in self.szoveg.items():
            if u == MAGYAR_MINTA_JEGYZET:
                continue
            kiegyszerusitett = t
            for w in FORMATUM_SZAVAK:
                kiegyszerusitett = kiegyszerusitett.replace(w, "")
            kiegyszerusitett = (kiegyszerusitett.replace("–", "").replace("—", "").replace("📅", ""))
            self.assertIsNone(MAGYAR.search(kiegyszerusitett), f"Hungarian text in {u}: {MAGYAR.search(kiegyszerusitett)}")
            if u.endswith(".md") and not u.startswith(("Manifold - ", "Attachments/")):
                self.assertIsNone(MAGYAR.search(u), u)

    def test_minden_link_feloldhato_egy_szandekos_kivetellel(self):
        fajlok = set(self.tart)
        nevek = {u.rsplit("/", 1)[-1] for u in fajlok} | {u.rsplit("/", 1)[-1][:-3] for u in fajlok if u.endswith(".md")}
        aliasok = set()
        for u, t in self.szoveg.items():
            if u.endswith(".md") and t.startswith("---\n") and not u.startswith("_Template/"):
                fm = yaml.safe_load(t.split("---\n", 2)[1]) or {}
                aliasok |= {a for a in fm.get("aliases", []) or []}
        nincs = set()
        for u, t in self.szoveg.items():
            if not u.endswith(".md") or u.startswith("_Template/"):
                continue
            torzs = maszk.mask_code(t)
            for cel in LINK.findall(torzs):
                cel = cel.strip()
                ok = (cel + ".md" in fajlok or cel in fajlok) if "/" in cel else (cel in nevek or cel in aliasok)
                if not ok:
                    nincs.add(cel)
        self.assertEqual(nincs, {"Fractals"}, "the only deliberately unresolved link")

    def test_kartyak_es_kvizek_a_termek_formatumaban_es_forrashuen(self):
        from modulok.kartya import formatum as F
        from modulok.kviz import formatum as FM
        osszes = 0
        for u, b in self.tart.items():
            if u.startswith("Manifold - Cards/"):
                e = F.elemez(b.decode())
                self.assertEqual(e.hibak, [], u)
                osszes += len(F.ervenyes(e))
                for k in e.kartyak:
                    forras, _, horgony = k.forras.partition("#^")
                    self.assertRegex(self.szoveg[forras + ".md"], rf"\^{re.escape(horgony)}\s*$|\^{re.escape(horgony)}\n", f"anchor of {k.kerdes}")
            if u.startswith("Manifold - Quizzes/"):
                e = FM.elemez(b.decode())
                self.assertEqual(e.hibak, [], u)
                self.assertGreaterEqual(len(e.kviz.kerdesek), 3)
                for q in e.kviz.kerdesek:
                    self.assertIn(q.idezet, self.szoveg[e.kviz.forras + ".md"], f"quote must be a verbatim sentence: {q.kerdes}")
                    self.assertEqual(len(set(q.valaszok)), 4)
        self.assertGreaterEqual(osszes, 15)
        azonok = [m for u, b in self.tart.items() if u.startswith("Manifold - Cards/") for m in re.findall(r"\^(c-[0-9a-f]{8})", b.decode())]
        self.assertEqual(len(azonok), len(set(azonok)), "card ids are unique")

    def test_canvas_base_tipusok_es_pdf_ervenyesek(self):
        c = json.loads(self.szoveg["Maps/Learning map.canvas"])
        azonok = {n["id"] for n in c["nodes"]}
        self.assertGreaterEqual(len(c["nodes"]), 8)
        self.assertEqual(len(azonok), len(c["nodes"]))
        for n in c["nodes"]:
            if n["type"] == "file":
                self.assertIn(n["file"], self.tart)
        for e in c["edges"]:
            self.assertTrue({e["fromNode"], e["toNode"]} <= azonok)
        for u in ("Bases/Reading list.base", "Bases/Projects.base"):
            b = yaml.safe_load(self.szoveg[u])
            self.assertTrue(b["views"] and b["filters"])
        self.assertEqual(set(json.loads(self.szoveg[".obsidian/types.json"])["types"].values()) - {"text", "multitext", "number", "checkbox", "date", "datetime"}, set())
        pdf = self.tart["Attachments/Orbits primer.pdf"]
        self.assertTrue(pdf.startswith(b"%PDF-1.4") and pdf.rstrip().endswith(b"%%EOF"))
        for png in (b for u, b in self.tart.items() if u.endswith(".png")):
            self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_pdf_es_png_olvashato(self):
        try:
            import pymupdf
        except ImportError:                                                         # pragma: no cover
            self.skipTest("[indokolt] no PyMuPDF in this interpreter (run with bin/mos test)")
        d = pymupdf.open(stream=self.tart["Attachments/Orbits primer.pdf"], filetype="pdf")
        self.assertEqual(d.page_count, 3)
        self.assertIn("ellipse", d[0].get_text())
        for u, b in self.tart.items():
            if u.endswith(".png"):
                p = pymupdf.Pixmap(b)
                self.assertEqual((p.width, p.height), (400, 260), u)

    def test_naptar_es_ai_memoria_adat_rogzitett(self):
        most = dt.datetime(2026, 10, 16, 8, 0, tzinfo=dt.timezone.utc)
        a, b = demo_tanulas.naptar_adat(most), demo_tanulas.naptar_adat(most)
        self.assertEqual(a, b)
        self.assertGreaterEqual(len(a["esemenyek"]), 10)
        self.assertEqual(len({e["azon"] for e in a["esemenyek"]}), len(a["esemenyek"]))
        m = demo_tanulas.asszisztens_memoria()
        self.assertGreaterEqual(len(m["kiegeszites_mintak"]), 3)
        self.assertGreaterEqual(len(m["muveletek"]), 3)


class MunkaterAlap(unittest.TestCase):
    def setUp(self):
        self.t = tmpdir()
        self.addCleanup(self.t.cleanup)
        self.root, self.home = termek_telepites(self.t.name)
        self.alap = config.load({"MOS_ROOT": str(self.root), "HOME": str(self.home), "MOS_SETTINGS": ""}, munkater=False)

    def ker(self, muvelet, **adat):
        return indito.muvelet({"muvelet": muvelet, **adat}, self.alap)

    def demo_nyit(self):
        w = self.ker("demo")["munkater"]
        v = Path(w["vault"])
        return w, v, termek_cfg(self.root, self.home, v)


class IndulasTest(MunkaterAlap):
    def test_try_demo_letrehozza_a_demo_munkatert_a_regiszterben_jelolve(self):
        w, v, cfg = self.demo_nyit()
        self.assertEqual(Path(v), Path(self.alap.path("install")) / "demo" / "Manifold Demo")
        e = workspace.Regiszter(self.alap.path("install")).olvas()["munkaterek"][w["id"]]
        self.assertTrue(e["demo"])
        j = demo.jelolo_olvas(v)
        self.assertEqual((j["verzio"], j["seed"], j["id"]), (demo.VERZIO, demo.SEED, w["id"]))
        self.assertEqual(set(j["fajlok"]), set(demo.tartalom(demo.SEED, cfg)))
        for rel, b in demo.tartalom(demo.SEED, cfg).items():
            self.assertEqual((v / rel).read_bytes(), b, rel)
        self.assertTrue(demo.demo_munkater(cfg))
        s = demo.allapot(cfg)
        self.assertEqual((s["demo"], s["modositott"], s["hianyzo"], s["hozzaadott"]), (True, 0, 0, 0))
        self.assertTrue(50 <= len(list(v.rglob("*.md"))) <= 100)

    def test_utmutato_a_demo_munkateren_nem_ir_felul_es_a_reset_visszaallitja(self):
        w, v, cfg = self.demo_nyit()
        oldalak = sorted(p.name for p in (v / "Manifold Guide").glob("*.md"))
        self.assertEqual(len(oldalak), 16)
        (v / "Manifold Guide" / "Getting started.md").write_text("my edit")
        (v / "Manifold Guide" / "Search.md").unlink()
        self.ker("demo")
        self.assertEqual((v / "Manifold Guide" / "Getting started.md").read_text(), "my edit")
        self.assertFalse((v / "Manifold Guide" / "Search.md").exists())
        self.ker("demo_reset", elfogad=True)
        for nev, adat in doku.munkater_fajlok().items():
            self.assertEqual((v / nev).read_bytes(), adat, nev)

    def test_idempotens_ujranyitas_semmit_nem_ir_nem_hoz_vissza_nem_commitol(self):
        w, v, cfg = self.demo_nyit()
        repo = snapshot.repos(cfg)["vault"]
        commitok = [c.sha for c in repo.log(50)]
        elotte = lenyomat(v)
        self.assertEqual(self.ker("demo")["munkater"], w)
        self.assertEqual(lenyomat(v), elotte)
        self.assertEqual([c.sha for c in repo.log(50)], commitok)
        (v / "Welcome.md").write_text("User changed this")
        (v / "Mathematics/Geometric series.md").unlink()
        self.ker("demo")
        self.assertEqual((v / "Welcome.md").read_text(), "User changed this")
        self.assertFalse((v / "Mathematics/Geometric series.md").exists())
        s = demo.allapot(cfg)
        self.assertEqual((s["modositott"], s["hianyzo"]), (1, 1))

    def test_ket_fuggetlen_telepites_ugyanazt_a_bajtot_adja(self):
        w, v, cfg = self.demo_nyit()
        t2 = tmpdir()
        self.addCleanup(t2.cleanup)
        root2, home2 = termek_telepites(t2.name)
        alap2 = config.load({"MOS_ROOT": str(root2), "HOME": str(home2), "MOS_SETTINGS": ""}, munkater=False)
        v2 = Path(indito.muvelet({"muvelet": "demo"}, alap2)["munkater"]["vault"])
        self.assertNotEqual(w["id"], workspace.azonosit(v2), "different workspaces, same library")
        a, b = lenyomat(v), lenyomat(v2)
        for rel in [r for r in a if r.startswith(".obsidian/") and r != ".obsidian/types.json"]:
            a.pop(rel), b.pop(rel, None)
        self.assertEqual(a, b)

    def test_a_demo_nem_hasznal_halozatot_es_nem_kerit_modellt(self):
        def tilos(*a, **k):
            raise AssertionError("the demo must not use the network")
        regi = (socket.socket.connect, socket.create_connection, urllib.request.urlopen)
        socket.socket.connect, socket.create_connection, urllib.request.urlopen = tilos, tilos, tilos
        self.addCleanup(lambda: (setattr(socket.socket, "connect", regi[0]), setattr(socket, "create_connection", regi[1]),
                                 setattr(urllib.request, "urlopen", regi[2])))
        w, v, cfg = self.demo_nyit()
        install = Path(self.alap.path("install"))
        self.assertEqual([p for p in install.rglob("*") if p.is_dir() and p.name in ("models", "downloads")], [])
        self.assertFalse(list(install.rglob("*.safetensors")) or list(install.rglob("*.gguf")))

    def test_ai_memoria_es_naptar_minta_a_demo_allapotaban(self):
        w, v, cfg = self.demo_nyit()
        d = Allapot(cfg).olvas()
        self.assertGreaterEqual(len(d["kiegeszites_mintak"]), 3)
        self.assertGreaterEqual(len(d["muveletek"]), 3)
        with szemelyes_db.olvaso(cfg) as c:
            ma = dt.datetime.now().astimezone()
            esemenyek = naptar.esemenyek(c, ma - dt.timedelta(days=5), ma + dt.timedelta(days=20), cfg)
            self.assertGreaterEqual(len(esemenyek), 10)
            self.assertIn("dolgozat", {e["fajta"] for e in esemenyek})
            self.assertIn("hatarido", {e["fajta"] for e in esemenyek})
            self.assertEqual({e["kategoria"] for e in esemenyek} - {"tanulas", "hatarido", "orarend", "szabadido"}, set())

    def test_valodi_cli_ndjson(self):
        e = env(MOS_ROOT=str(self.root), HOME=str(self.home), PYTHONPATH=str(REPO))
        p = subprocess.run([sys.executable, "-B", "-m", "core.indito"], input=json.dumps({"muvelet": "demo"}), text=True, capture_output=True,
                           env=e, cwd=REPO, timeout=120)
        self.assertEqual(p.returncode, 0, p.stderr)
        sorok = [json.loads(s) for s in p.stdout.splitlines() if s.strip()]
        self.assertTrue(sorok[-1]["ok"])
        self.assertTrue((Path(sorok[-1]["munkater"]["vault"]) / "Welcome.md").is_file())


class BiztonsagTest(MunkaterAlap):
    def felhasznalo(self):
        v = Path(self.t.name) / "My Notes"
        w = self.ker("letrehoz", vault=str(v), uj_mappa=True, elfogad=True)["munkater"]
        (v / "Private.md").write_text("# Private\n\nMy own note.\n")
        return w, v, termek_cfg(self.root, self.home, v)

    def test_a_generator_es_a_reset_felhasznaloi_munkateren_visszautasitva_nem_ir(self):
        w, v, cfg = self.felhasznalo()
        elotte = lenyomat(v, kihagy=())
        self.assertFalse(demo.demo_munkater(cfg))
        self.assertEqual(demo.allapot(cfg), {"ok": True, "demo": False})
        for fv in (lambda: demo.general(cfg), lambda: demo.alaphelyzet(cfg, megerosit=True)):
            with self.assertRaises(HttpError) as hk:
                fv()
            self.assertEqual((hk.exception.code, hk.exception.kod), (403, "demo.nem_demo"))
        self.assertEqual(lenyomat(v, kihagy=()), elotte)

    def test_hamis_jelolo_sem_tesz_demova_egy_felhasznaloi_munkatert(self):
        w, v, cfg = self.felhasznalo()
        (v / ".manifold" / demo.JELOLO).write_text(json.dumps({"verzio": 2, "id": w["id"], "fajlok": {}}))
        self.assertFalse(demo.demo_munkater(cfg), "marker alone is not enough: the registry flag and the demo folder are needed")
        with self.assertRaises(HttpError):
            demo.alaphelyzet(cfg, megerosit=True)
        self.assertEqual((v / "Private.md").read_text(), "# Private\n\nMy own note.\n")

    def test_reset_megerosites_nelkul_nem_nyul_semmihez(self):
        w, v, cfg = self.demo_nyit()
        (v / "Welcome.md").write_text("edited")
        elotte = lenyomat(v, kihagy=())
        for m in (False, None, "true", 1):
            with self.assertRaises(HttpError) as hk:
                demo.alaphelyzet(cfg, megerosit=m)
            self.assertEqual((hk.exception.code, hk.exception.kod), (400, "demo.megerosites"))
        with self.assertRaises(HttpError):
            self.ker("demo_reset")
        self.assertEqual(lenyomat(v, kihagy=()), elotte)

    def test_symlinkes_demo_mappa_nem_kovetett(self):
        w, v, cfg = self.demo_nyit()
        kulso = Path(self.t.name) / "outside"
        kulso.mkdir()
        (v / "Mathematics" / "Geometric series.md").unlink()
        shutil.rmtree(v / "Reference")
        os.symlink(kulso, v / "Reference")
        with self.assertRaises(ValueError):
            demo._ut_biztos(v, "Reference/Tags overview.md")
        elotte = lenyomat(v, kihagy=())
        with self.assertRaises(HttpError) as hk:
            demo.alaphelyzet(cfg, megerosit=True)         # refused before anything is touched; never writes outside
        self.assertEqual((hk.exception.code, hk.exception.kod), (409, "demo.nem_biztonsagos_ut"))
        self.assertEqual(list(kulso.iterdir()), [])
        self.assertEqual(lenyomat(v, kihagy=()), elotte)

    def test_utvonal_ellenorzes_tiltja_a_kitorest(self):
        w, v, cfg = self.demo_nyit()
        for rossz in ("../x.md", "/abs.md", "a//b.md", "a/./b.md", "a\\b.md", ""):
            with self.assertRaises(ValueError, msg=rossz):
                demo._ut_biztos(v, rossz)

    def test_reset_a_futo_core_alatt_az_inditobol_409(self):
        import fcntl
        w, v, cfg = self.demo_nyit()
        cfg.path("run").mkdir(parents=True, exist_ok=True)
        with open(cfg.path("run") / "core.lock", "w") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            munkater_futo.bejelent(cfg, 12345)
            with self.assertRaises(HttpError) as hk:
                self.ker("demo_reset", elfogad=True)
            self.assertEqual((hk.exception.code, hk.exception.kod), (409, "demo.fut"))
        munkater_futo.elfelejt(cfg)


class AlaphelyzetTest(MunkaterAlap):
    def test_reset_visszaallit_felreteszi_nem_torol_es_visszavonhato(self):
        w, v, cfg = self.demo_nyit()
        (v / "Welcome.md").write_text("User changed this")
        (v / "Mathematics/Geometric series.md").unlink()
        (v / "Mathematics/My own note.md").write_text("# Mine\n\nKeep me.\n")
        (v / "Brand new folder").mkdir()
        (v / "Brand new folder/Idea.md").write_text("an idea")
        (v / ".obsidian/app.json").write_text('{"x": 1}')
        r = self.ker("demo_reset", elfogad=True)
        self.assertTrue(r["ok"])
        self.assertEqual((r["visszaallitva"], r["ujra_letrehozva"]), (1, 1))
        self.assertEqual(sorted(r["felretett"]), ["Brand new folder/Idea.md", "Mathematics/My own note.md"])
        for rel, b in demo.tartalom(demo.SEED, cfg).items():
            self.assertEqual((v / rel).read_bytes(), b, rel)
        self.assertFalse((v / "Mathematics/My own note.md").exists())
        felrerakva = v / r["visszahelye"]
        self.assertEqual((felrerakva / "Mathematics/My own note.md").read_text(), "# Mine\n\nKeep me.\n")
        self.assertEqual((felrerakva / "Brand new folder/Idea.md").read_text(), "an idea")
        self.assertFalse((v / "Brand new folder").exists(), "emptied folders of the user are tidied, never the generator's")
        self.assertEqual((v / ".obsidian/app.json").read_text(), '{"x": 1}', "unrelated hidden settings stay")
        self.assertEqual(demo.allapot(cfg)["modositott"], 0)
        repo = snapshot.repos(cfg)["vault"]
        uzenetek = [c.subject for c in repo.log(10)]
        self.assertIn("Before demo reset", uzenetek)
        self.assertIn("Demo workspace reset", uzenetek)
        elotte_sha = r["pillanatkep"]["elotte"]
        self.assertTrue(elotte_sha)
        self.assertIn("User changed this", repo.git("show", f"{elotte_sha}:Welcome.md").stdout, "the pre-reset snapshot holds the user's version")
        r2 = self.ker("demo_reset", elfogad=True)
        self.assertEqual((r2["visszaallitva"], r2["ujra_letrehozva"], r2["felretett"]), (0, 0, []))

    def test_reset_nullazza_a_tanulast_es_a_mintakat_de_nem_a_tartalmat(self):
        w, v, cfg = self.demo_nyit()
        from core import tanulas_db
        with tanulas_db.iro(cfg) as c:
            c.execute("INSERT INTO kartya (azon, jegyzet, kerdes, valasz, letrehozva, allapot, stabilitas, esedekes) VALUES "
                      "('c-x', 'x.md', 'q', 'a', '2026-10-01', 2, 3.0, '2026-10-20')")
            c.execute("INSERT INTO valasz (kartya, mikor, jegy) VALUES ('c-x', '2026-10-02', 3)")
        Allapot(cfg).modosit(lambda d: d.update(kiegeszites_mintak=[], muveletek={}))
        self.ker("demo_reset", elfogad=True)
        with tanulas_db.olvaso(cfg) as c:
            self.assertEqual(c.execute("SELECT count(*) FROM valasz").fetchone()[0], 0)
            self.assertEqual(c.execute("SELECT allapot, stabilitas, esedekes FROM kartya WHERE azon='c-x'").fetchone()[:], (0, None, None))
        self.assertGreaterEqual(len(Allapot(cfg).olvas()["kiegeszites_mintak"]), 3)

    def test_felhasznaloi_munkater_a_demo_resetjekor_erintetlen(self):
        felh = Path(self.t.name) / "My Notes"
        self.ker("letrehoz", vault=str(felh), uj_mappa=True, elfogad=True)
        (felh / "Private.md").write_text("# Private\n\nMine.\n")
        elotte = lenyomat(felh, kihagy=())
        w, v, cfg = self.demo_nyit()
        (v / "Welcome.md").write_text("x")
        self.ker("demo_reset", elfogad=True)
        self.assertEqual(lenyomat(felh, kihagy=()), elotte)

    def test_reset_a_hianyzo_demora_ertheto_hibat_ad(self):
        with self.assertRaises(HttpError) as hk:
            self.ker("demo_reset", elfogad=True)
        self.assertEqual((hk.exception.code, hk.exception.kod), (404, "demo.nincs"))


if __name__ == "__main__":
    unittest.main()
