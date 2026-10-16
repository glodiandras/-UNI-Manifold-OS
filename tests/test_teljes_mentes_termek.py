"""F3 (§5): a külső teljes mentés termék-elrendezésben és a hordozható szabályok változatlansága. A külön kötet szabálya a vault
és a `{var}` kötetéhez mér (nem a kódfáéhoz; a tesztek az `st_dev`-et cserélik), a `{os}` gyökér termékben nincs a mentésben, a
kihagyott utak mintái gyökerenként érvényesek (`.manifold/var/{tmp,run,runs,cache,index}` bárhol), a cél munkaterenként külön mappa
(`<cél>/Manifold Backups/<munkater_id>/Manifold-<idő>/`), a jegyzék `munkater_id` és `elrendezes` mezőt kap. Kizárólag álrendszeren."""
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from core import config, snapshot, tasks, teljes_mentes as m
from tests.helpers import alg_bundle, alg_core, ir, tmpdir

ID_A = "a" * 32
ID_B = "b" * 32


class Sor:
    def __init__(self):
        self.kuldott, self.fugg = [], False

    def fuggo(self, tipus):
        return self.fugg

    def submit(self, tipus, params):
        self.kuldott.append((tipus, params))
        self.fugg = True
        return {}


def kotetek(**dev_utak):
    """Hamis `_kotet`: a megadott útelőtagok (név → (út, st_dev)) szerint ad eszközszámot, minden más 1. A leghosszabb előtag nyer."""
    def _kotet(p):
        p = Path(p).resolve()
        legjobb = (0, 1)
        for ut, dev in dev_utak.values():
            ut = Path(ut).resolve()
            if (p == ut or ut in p.parents) and len(ut.parts) >= legjobb[0]:
                legjobb = (len(ut.parts), dev)
        return legjobb[1]
    return patch.object(m, "_kotet", _kotet)


class TermekAlap(unittest.TestCase):
    """Termék-elrendezés: `X.app/Contents/Resources/manifold`, ál-HOME, a vault a `{tmp}`-ben, `.manifold/` a munkatér."""

    def setUp(self):
        self.t = tmpdir()
        self.addCleanup(self.t.cleanup)
        self.tp = Path(self.t.name)
        self.root = alg_bundle(self.t.name)
        self.home = self.tp / "home"
        self.cel = self.tp / "külső lemez"
        self.cel.mkdir()

    def munkater(self, nev: str = "Jegyzetek", munkater_id: str = ID_A, settings: str | None = None) -> config.Config:
        vault = self.tp / nev
        ir(vault, ".manifold/workspace.toml", f'[workspace]\nid = "{munkater_id}"\n')
        if settings is not None:
            ir(self.home, "Library/Application Support/Manifold/settings.toml", settings)
        cfg = config.load({"MOS_ROOT": str(self.root), "HOME": str(self.home), "MOS_VAULT": str(vault)})
        cfg.path("var").mkdir(parents=True, exist_ok=True)
        ir(vault, "A.md", f"# {nev}\n")
        ir(vault, "Média/kép.png", b"\x89PNG", "wb")
        repo = snapshot.repos(cfg)["vault"]
        repo.init()
        repo.commit("alap", {"Mos-Forras": "kezi"})
        return cfg

    def ment(self, cfg, **kw) -> dict:
        return m.ment(cfg, self.cel, proba=True, log=lambda _: None, **kw)

    def elemek(self, r) -> set[str]:
        return {e["ut"] for e in m.ellenoriz(Path(r["ut"]))["elemek"]}


class KotetSzabaly(TermekAlap):
    """A külön kötet szabálya: a vault és a `{var}` (ha a vaulton kívül van) kötetéhez mér."""

    def test_adat_kotet_termekben_a_var_a_vault_alatt_egy_kotet(self):
        cfg = self.munkater()
        vault, var = cfg.path("vault"), cfg.path("var")
        self.assertTrue(var.is_relative_to(vault))
        with kotetek(vault=(vault, 7), var=(var, 9)):                       # a `{var}` a vault alatt: nem külön gyökér
            self.assertEqual(m.adat_kotet(cfg), {7})
        with kotetek():
            self.assertEqual(len(m.adat_kotet(cfg)), 1)

    def test_adat_kotet_hordozhatoban_a_var_a_vaulton_kivul_kulon_kotet(self):
        cfg, root, v = alg_core(self.t.name)
        with kotetek(vault=(v, 7), var=(cfg.path("var"), 9)):
            self.assertEqual(m.adat_kotet(cfg), {7, 9})
        with kotetek(vault=(v, 7), var=(cfg.path("var"), 7)):
            self.assertEqual(m.adat_kotet(cfg), {7})

    def test_kulso_kotet_csak_a_vaulttol_es_a_vartol_kulonbozo_kotet(self):
        cfg, root, v = alg_core(self.t.name)
        cel = self.cel
        with kotetek(vault=(v, 7), var=(cfg.path("var"), 9), cel=(cel, 3)):
            self.assertTrue(m.kulso_kotet(cfg, cel))
        with kotetek(vault=(v, 7), var=(cfg.path("var"), 9), cel=(cel, 7)):
            self.assertFalse(m.kulso_kotet(cfg, cel))                       # a vault kötete
        with kotetek(vault=(v, 7), var=(cfg.path("var"), 9), cel=(cel, 9)):
            self.assertFalse(m.kulso_kotet(cfg, cel))                       # a `{var}` kötete
        with kotetek(vault=(v, 7), var=(cfg.path("var"), 9), cel=(cel, 7)), \
                patch.object(m, "adat_kotet", lambda c: set()):
            self.assertFalse(m.kulso_kotet(cfg, cel))                       # ismeretlen adatkötet: zárva hibázik

    def test_a_kodfa_kotete_nem_szamit(self):
        """A régi szabály a `cfg.root` kötetéhez mért; a termék csomagja (más kötet) a vault/`{var}` védelmét nem szólhatja le."""
        cfg = self.munkater()
        with kotetek(vault=(cfg.path("vault"), 7), root=(self.root, 3), cel=(self.cel, 3)):
            self.assertTrue(m.kulso_kotet(cfg, self.cel))                   # a csomaggal azonos kötet, a vaulttól más: külső
        with kotetek(vault=(cfg.path("vault"), 7), root=(self.root, 3), cel=(self.cel, 7)):
            self.assertFalse(m.kulso_kotet(cfg, self.cel))                  # a vaulttal azonos: nem külső, bármi is a csomag

    def test_ment_csak_kulon_kotetre_megy_a_proba_kapcsolo_nelkul(self):
        cfg = self.munkater()
        with kotetek(vault=(cfg.path("vault"), 7), cel=(self.cel, 7)):
            with self.assertRaisesRegex(m.MentesHiba, "külön kötet"):
                m.ment(cfg, self.cel, log=lambda _: None)
        with kotetek(vault=(cfg.path("vault"), 7), cel=(self.cel, 3)):
            r = m.ment(cfg, self.cel, log=lambda _: None)
        self.assertTrue(r["kulso"])
        self.assertTrue(m.allapot(cfg)["ellenorzott"])                       # külső mentés: az állapotfájl a `{state}`-be megy

    def test_a_tervezo_a_vault_kotetehez_mer(self):
        cfg = self.munkater()
        terv = tasks.REGISTRY["teljes_mentes"].plan
        with kotetek(vault=(cfg.path("vault"), 7), cel=(self.cel, 7)):
            with self.assertRaises(tasks.Invalid):
                terv(cfg, {"cel": str(self.cel)}, "stop")
        with kotetek(vault=(cfg.path("vault"), 7), cel=(self.cel, 3)):
            lepesek, cel, _ = terv(cfg, {"cel": str(self.cel)}, "stop")
        self.assertEqual(cel, str(self.cel.resolve()))
        self.assertEqual(lepesek[0].argv[-3:], ["core.teljes_mentes", "ment", str(self.cel.resolve())])

    def test_a_tervezo_hordozhatoban_is_a_vault_kotetehez_mer_nem_a_gyokerhez(self):
        cfg, root, v = alg_core(self.t.name)
        terv = tasks.REGISTRY["teljes_mentes"].plan
        with kotetek(root=(root, 5), vault=(v, 7), var=(cfg.path("var"), 5), cel=(self.cel, 5)):
            with self.assertRaises(tasks.Invalid):
                terv(cfg, {"cel": str(self.cel)}, "stop")                   # a `{var}` kötetével azonos
        with kotetek(root=(root, 5), vault=(v, 7), var=(cfg.path("var"), 5), cel=(self.cel, 4)):
            terv(cfg, {"cel": str(self.cel)}, "stop")

    def test_a_tervezo_elutasitja_a_mentendo_rendszerben_levo_celt(self):
        cfg = self.munkater()
        be = cfg.path("vault") / "mentesek"
        be.mkdir()
        with kotetek(vault=(cfg.path("vault"), 7), cel=(be, 3)):
            with self.assertRaises(tasks.Invalid):
                tasks.REGISTRY["teljes_mentes"].plan(cfg, {"cel": str(be)}, "stop")

    def test_a_lemezfigyelo_a_vault_kotetehez_mer(self):
        cfg = self.munkater()
        cfg.data["teljes_mentes"] = {"figyelo_be": True, "cel": str(self.cel), "figyelo_ora": 24}
        sor, most = Sor(), 1_000_000.0
        f = m.LemezFigyelo(cfg, sor, ora=lambda: most + 200, indulasi_kesleltetes_mp=0, log=lambda _: None)
        with kotetek(vault=(cfg.path("vault"), 7), cel=(self.cel, 7)):
            self.assertFalse(f.tick())                                      # nem külső lemez
        with kotetek(vault=(cfg.path("vault"), 7), cel=(self.cel, 3)):
            self.assertTrue(f.tick())
        self.assertEqual(sor.kuldott, [("teljes_mentes", {"cel": str(self.cel)})])

    def test_valodi_stat_csere_is_mukodik(self):
        """A kötet-azonosítót a `Path.stat` adja: a meglévő tesztek ezt cserélik (itt a vault kötete lesz más)."""
        cfg, root, v = alg_core(self.t.name)
        valodi = Path.stat

        adat = {v.resolve(), cfg.path("var").resolve()}

        def stat(p, *a, **k):
            s = valodi(p, *a, **k)
            if Path(p).resolve() in adat:
                return os.stat_result((s.st_mode, s.st_ino, s.st_dev + 1, *tuple(s)[3:]))
            return s
        with patch.object(Path, "stat", stat):
            self.assertEqual(m.adat_kotet(cfg), {valodi(v).st_dev + 1})
            self.assertTrue(m.kulso_kotet(cfg, self.cel))                    # a cél a (hamis) adatkötettől más kötet
        self.assertFalse(m.kulso_kotet(cfg, self.cel))                       # valódi eszközszámokkal ugyanaz a kötet


class TermekMentes(TermekAlap):
    def test_nincs_os_gyoker_nincs_kodtar_es_aktiv_os(self):
        cfg = self.munkater()
        self.assertNotIn("os", m.forrasok(cfg))
        r = self.ment(cfg)
        jegy = m.ellenoriz(Path(r["ut"]))
        self.assertNotIn("os", jegy["gyokerek"])
        utak = self.elemek(r)
        self.assertFalse([u for u in utak if u.startswith("adat/os")])
        self.assertNotIn("aktiv-os.toml", utak)
        self.assertNotIn("kodtar.bundle", utak)
        self.assertIsNone(jegy["kodtar"])

    def test_hordozhatoban_az_os_gyoker_es_az_aktiv_os_toml_marad(self):
        cfg, root, v = alg_core(self.t.name)
        ir(v, "A.md", "# A\n")
        repo = snapshot.repos(cfg)["vault"]
        repo.init()
        repo.commit("alap", {"Mos-Forras": "kezi"})
        self.assertIn("os", m.forrasok(cfg))
        r = self.ment(cfg)
        jegy = m.ellenoriz(Path(r["ut"]))
        self.assertEqual((jegy["elrendezes"], jegy["munkater_id"]), ("hordozhato", None))
        self.assertIn("os", jegy["gyokerek"])
        utak = self.elemek(r)
        self.assertIn("aktiv-os.toml", utak)
        self.assertNotIn("settings.toml", utak)
        self.assertTrue(Path(r["ut"]).parent == self.cel)                   # hordozhatóban a v2 elrendezés: közvetlenül a célban
        self.assertEqual(r["mappa"], r["cel"])

    def test_a_vault_a_var_val_egyutt_kerul_be_az_atmeneti_mappak_nelkul(self):
        cfg = self.munkater()
        var = cfg.path("var")
        for rp in ("tmp/proba/K-1/Jegyzetek/A.md", "tmp/felkesz.bin", "run/core.lock", "runs/core.log", "runs/F-1.log",
                   "cache/vault-kepek/kicsi.jpg", "index/vault.sqlite", "index/vektor.bin",
                   "state/felulet.json", "state/mély/állapot.json", "fuzet/bejovo/fotó.heic", "szemelyes/adat.json"):
            ir(var, rp, b"x", "wb")
        ir(var, "ytdlp/staging/yt/video.mp4", b"v", "wb")
        ir(var, "archive/video-eredeti/eredeti.mkv", b"e", "wb")
        utak = self.elemek(self.ment(cfg))
        vk = "adat/vault/.manifold/var"
        for tilos in ("tmp", "run", "runs", "cache", "index", "ytdlp/staging", "archive"):
            self.assertFalse([u for u in utak if u == f"{vk}/{tilos}" or u.startswith(f"{vk}/{tilos}/")], tilos)
        for kell in ("state/felulet.json", "state/mély/állapot.json", "fuzet/bejovo/fotó.heic", "szemelyes/adat.json"):
            self.assertIn(f"{vk}/{kell}", utak, kell)
        self.assertIn("adat/vault/A.md", utak)
        self.assertIn("adat/vault/.manifold/workspace.toml", utak)
        self.assertTrue([u for u in utak if u.startswith(f"{vk}/vault.git/")])        # a pillanatkép-tároló a mentésben van

    def test_a_beagyazott_masolat_atmeneti_mappai_is_kimaradnak(self):
        """Gyökerenként számolt minta: egy másolat/beágyazott vault `.manifold/var/tmp` klónjai bármely mélységben kimaradnak."""
        cfg = self.munkater()
        vault = cfg.path("vault")
        for rp in ("Régi/Másolat/.manifold/var/tmp/proba/K-9/A.md", "Régi/Másolat/.manifold/var/runs/core.log",
                   "Régi/Másolat/.manifold/var/state/felulet.json", "Régi/Másolat/B.md", "tmp/sajat-jegyzet.md"):
            ir(vault, rp, b"x", "wb")
        utak = self.elemek(self.ment(cfg))
        self.assertFalse([u for u in utak if "/.manifold/var/tmp" in u or "/.manifold/var/runs" in u])
        self.assertIn("adat/vault/Régi/Másolat/B.md", utak)
        self.assertIn("adat/vault/Régi/Másolat/.manifold/var/state/felulet.json", utak)
        self.assertIn("adat/vault/tmp/sajat-jegyzet.md", utak)                         # a felhasználó `tmp` mappája nem minta

    def test_kizart_mintak_gyokerenkent(self):
        cfg = self.munkater()
        gyokerek = m.forrasok(cfg)
        mintak = m._kizart_mintak(cfg, gyokerek)
        self.assertEqual(set(mintak), set(gyokerek))
        self.assertIn((".manifold", "var", "tmp"), mintak["vault"])
        self.assertIn((".manifold", "var", "cache"), mintak["vault"])                 # termékben a `cache` kulcs a `{install}` alatt van
        self.assertIn((".manifold", "var", "index"), mintak["vault"])
        self.assertFalse([x for x in mintak["vault"] if len(x) < 2])
        cfg2, root, v = alg_core(self.t.name + "/h")
        mintak2 = m._kizart_mintak(cfg2)
        self.assertIn(("var", "tmp"), mintak2["os"])
        self.assertIn(("var", "cache"), mintak2["os"])
        self.assertFalse(mintak2.get("vault"))                                        # hordozhatóban a vaultban nincs kihagyott út

    def test_a_termek_konfiguracio_masolata_settings_es_workspace_toml(self):
        cfg = self.munkater(settings="[mentes]\nido_perc = 45\n")
        r = self.ment(cfg)
        utak = self.elemek(r)
        self.assertIn("settings.toml", utak)
        self.assertIn("workspace.toml", utak)
        self.assertNotIn("aktiv-os.toml", utak)
        self.assertEqual((Path(r["ut"]) / "workspace.toml").read_bytes(),
                         (cfg.path("workspace") / "workspace.toml").read_bytes())
        self.assertIn(b"ido_perc = 45", (Path(r["ut"]) / "settings.toml").read_bytes())

    def test_settings_nelkul_csak_a_workspace_toml(self):
        cfg = self.munkater()
        utak = self.elemek(self.ment(cfg))
        self.assertNotIn("settings.toml", utak)
        self.assertIn("workspace.toml", utak)

    def test_szimbolikus_link_workspace_toml_nem_masolodik(self):
        cfg = self.munkater()
        wt = cfg.path("workspace") / "workspace.toml"
        szoveg = wt.read_text(encoding="utf-8")
        valodi = cfg.path("workspace") / "valodi.toml"
        valodi.write_text(szoveg, encoding="utf-8")
        wt.unlink()
        wt.symlink_to(valodi.name)                                            # a vaulton belüli link: a bejárás elfogadja
        utak = self.elemek(self.ment(cfg))
        self.assertIn("adat/vault/.manifold/workspace.toml", utak)             # a vault fájlja linkként a mentésben van
        self.assertNotIn("workspace.toml", utak)                               # a felső szintű másolat viszont nem készül


class TermekCel(TermekAlap):
    def test_a_cel_munkaterenkent_kulon_mappa(self):
        cfg = self.munkater()
        r = self.ment(cfg)
        ut = Path(r["ut"])
        self.assertEqual(ut.parent, self.cel.resolve() / "Manifold Backups" / ID_A)
        self.assertTrue(m.VALTOZAT_MINTA.match(ut.name))
        self.assertTrue((ut / m.KESZ).is_file())
        self.assertEqual((r["cel"], r["mappa"]), (str(self.cel.resolve()), str(ut.parent)))
        self.assertEqual([p.name for p in self.cel.iterdir()], ["Manifold Backups"])  # a célban más nem keletkezik (a zárfájl a munkatér mappájában)
        self.assertTrue((ut.parent / m.CEL_ZAR).is_file())

    def test_a_jegyzek_munkater_id_es_elrendezes(self):
        cfg = self.munkater()
        jegy = m.ellenoriz(Path(self.ment(cfg)["ut"]))
        self.assertEqual((jegy["munkater_id"], jegy["elrendezes"], jegy["verzio"]), (ID_A, "termek", m.FORMATUM))

    def test_a_ritkitas_munkaterenkent_a_masik_munkater_valtozata_marad(self):
        a = self.munkater("A-vault", ID_A, settings="[teljes_mentes]\nmegtartott = 2\n")
        b = self.munkater("B-vault", ID_B)
        self.assertEqual(a.section("teljes_mentes")["megtartott"], 2)
        rb = self.ment(b)
        ra = [self.ment(a) for _ in range(3)]
        # a közös ritkítás (összesen 2) a B változatát is kitörölné; munkaterenként: A két legújabbja, B egyetlen változata
        self.assertEqual([p.name for p in m.kesz_valtozatok(Path(ra[0]["mappa"]))], [Path(r["ut"]).name for r in ra[1:]])
        self.assertEqual([p.name for p in m.kesz_valtozatok(Path(rb["mappa"]))], [Path(rb["ut"]).name])
        self.assertEqual(sorted(p.name for p in (self.cel / "Manifold Backups").iterdir()), [ID_A, ID_B])
        self.assertEqual(len(ra[-1]["torolt_valtozatok"]), 1)

    def test_az_inkrementalis_link_a_munkater_sajat_elozo_valtozatabol_jon(self):
        cfg = self.munkater()
        elso = self.ment(cfg)
        masodik = self.ment(cfg)
        self.assertGreater(masodik["linkelt"], 0)
        self.assertEqual(json.loads((Path(masodik["ut"]) / "jegyzek.json").read_text())["elozo"], Path(elso["ut"]).name)
        self.assertEqual(m.ellenoriz(Path(masodik["ut"]))["verzio"], m.FORMATUM)

    def test_a_valtozat_a_celbol_a_munkater_mappajabol_es_a_valtozatbol_is_feloldhato(self):
        cfg = self.munkater()
        r = self.ment(cfg)
        ut = Path(r["ut"]).resolve()
        self.assertEqual(m._valtozat(Path(r["mappa"])), ut)
        self.assertEqual(m._valtozat(ut), ut)
        self.assertEqual(m._valtozat(self.cel), ut)                           # egyetlen munkatér a célban: az övé

    def test_tobb_munkater_a_celban_a_felhasznalo_valaszt(self):
        a, b = self.munkater("A-vault", ID_A), self.munkater("B-vault", ID_B)
        self.ment(a)
        self.ment(b)
        with self.assertRaisesRegex(m.MentesHiba, "több munkatér"):
            m._valtozat(self.cel)
        self.assertTrue(m._valtozat(self.cel / "Manifold Backups" / ID_B).name.startswith("Manifold-"))

    def test_a_vaultba_vagy_a_munkater_alatti_cel_elutasitva(self):
        cfg = self.munkater()
        for cel in (cfg.path("vault") / "mentesek", cfg.path("var") / "mentesek", cfg.path("vault")):
            cel.mkdir(parents=True, exist_ok=True)
            with self.assertRaisesRegex(m.MentesHiba, "nem lehet a mentendő rendszerben"):
                m.ment(cfg, cel, proba=True, log=lambda _: None)
        self.assertFalse((cfg.path("vault") / "mentesek" / "Manifold Backups").exists())

    def test_termekben_munkater_nelkul_nincs_mentes(self):
        cfg = self.munkater()
        cfg.workspace_id = None
        with self.assertRaisesRegex(m.MentesHiba, "munkatér kell"):
            self.ment(cfg)
        self.assertEqual(list(self.cel.iterdir()), [])
        cfg.workspace_id = "../../x"                                          # az azonosító útszegmens: csak ID_MINTA mehet át
        with self.assertRaisesRegex(m.MentesHiba, "munkatér kell"):
            self.ment(cfg)

    def test_a_mentes_ellenorzott_es_visszaallithato_uj_celba_hiba_nelkul(self):
        """A termék kulcs szerinti visszaállítása az F8; a mostani `visszaallit` nem dobhat és a vault bájtra megvan."""
        cfg = self.munkater()
        r = self.ment(cfg)
        uj = self.tp / "visszaallitott"
        k = m.visszaallit(Path(r["ut"]), uj)
        self.assertTrue(k["ok"])
        self.assertEqual((uj / "Manifold" / "A.md").read_bytes(), (cfg.path("vault") / "A.md").read_bytes())
        self.assertEqual((uj / "Manifold" / "Média" / "kép.png").read_bytes(), b"\x89PNG")
        self.assertTrue((uj / "workspace.toml").is_file())


if __name__ == "__main__":
    unittest.main()
