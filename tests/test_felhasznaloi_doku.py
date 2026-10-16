"""A beépített felhasználói dokumentáció kapui (F8): a 16 oldal létezik, angol és fejlesztői szó nélküli, a belső hivatkozások és a
„Learn more” célok feloldhatók, a gyorsbillentyű-oldal a parancsregiszterből generált táblázattal egyezik, és a dokumentáció
betölthető a (demo) munkatérbe.

- **Jegyzék**: `core/doku.OLDALAK` ↔ `docs/user/*.md` (pontosan 16, a H1 a jegyzék címe, elég hosszú, összekötött oldalak).
- **Szókincs-ratchet**: a felhasználói szövegben nincs fejlesztői szleng (döntésszám, fázisjelölő, v2, parancssori eszköz, belső
  modulnév), nincs magyar ékezetes betű, nincs személyes vagy beégetett abszolút út. Új tiltott szó a `TILTOTT`-ba kerül.
- **Hivatkozások**: minden `](FÁJL.md#horgony)` létező fájlra és létező fejlécre mutat; a `LEARN_MORE` célok is; minden Health
  ellenőrzésnek (`core/egeszseg.ELLENORZESEK`) van „Learn more” oldala.
- **Gyorsbillentyűk**: a `HOTKEYS.md` `table:begin` … `table:end` közötti része egyezik a forrásból generálttal
  (`core/doku_gyorsbillentyu`), minden regisztrált billentyű szerepel benne, a nevek angolok. Újragenerálás:
  `python -m core.doku_gyorsbillentyu --iras`.
- **Betöltés**: `core/doku.munkater_fajlok` / `masol_munkaterbe`: wikilinkké alakított hivatkozások, felülírás nélküli másolás.
A tesztek a repó szövegfájljait olvassák (és egy ideiglenes mappát írnak): szerver, hálózat, valódi vault nincs."""
import re
import tempfile
import unittest
from pathlib import Path

from core import config, doku, doku_gyorsbillentyu as gyb, egeszseg
from tests.helpers import REPO
from tests.test_dokumentacio import billentyu_glif, regisztralt_billentyuk, relativ_celok

USER = REPO / "docs" / "user"
EN_MIN_SZO = 150                    # egy oldal tartalmi szavainak alsó határa (a generált táblázat és a kód nélkül)

# Fejlesztői szó a felhasználói szövegben: (név, minta, kis-nagybetű-független-e). A fázisjelölők közül az F7–F11 tiltott (az F1–F6
# funkcióbillentyű lehet: az F2 átnevez, az F6 régiót vált).
TILTOTT = (
    ("döntés- vagy kérdésszám (D9, K29, T148)", r"\b[DKT]\d{1,3}\b", False),
    ("fázis- vagy alrendszer-jelölő (C07, F8, CX-004)", r"\bC\d{2}[a-z]?\d?\b|\bCX-\d+\b|\bF(?:7|8|9|1[01])\b|\bphase\s+\d", False),
    ("v2 vagy az eredeti termék neve", r"\bv2\b|Manifold-OS|Manifold OS", True),
    ("belső fájl- vagy parancsnév", r"\bbin/mos\b|\bmos\s+(?:test|doctor|runtime)\b|MOS_[A-Z]+|NAPLO|PLAN\.md|CHECKLIST|ARCHITECTURE\.md|\.toml\b", True),
    ("fejlesztői eszköz", r"\b(?:pytest|vitest|unittest|npm|svelte|eslint|ratchet|lint|CI)\b", True),
    ("belső architektúra-szó", r"\bcore\b|(?<!Knowledge )\bworker\b|\b(?:endpoint|backend|frontend|daemon|stub|mock|fixture|refactor|hardcod\w*|gold set|golden)\b", True),
    ("jelöletlen munkajegyzet", r"\b(?:TODO|FIXME|TBD|WIP|lorem ipsum|placeholder)\b", True),
    ("git-szó", r"\bgit\b|\bcommit(?:s|ted)?\b|\bbranch\b|\brevert\b", True),
    ("snake_case azonosító", r"\b[a-z]+_[a-z0-9_]+\b", False),
    ("camelCase azonosító", r"\b[a-z]+[A-Z][A-Za-z]+\b", False),
    ("magyar ékezetes betű", r"[áéíóöőúüűÁÉÍÓÖŐÚÜŰ]", True),
    ("beégetett vagy személyes út", r"/Users/|/Volumes/|~/|C:\\|glodi|@[a-z0-9-]+\.(?:com|edu|hu)", True),
)
# A termék és a platform saját, kis-nagybetűs szavai: a camelCase-minta nem tiltja őket
ENGEDETT_SZO = {"macOS", "iCloud", "iPhone", "iPad", "iOS", "iPadOS", "watchOS", "tvOS"}


def oldalak() -> list[tuple[doku.Oldal, str]]:
    return [(o, (USER / o.fajl).read_text(encoding="utf-8")) for o in doku.OLDALAK]


def felhasznaloi_szoveg(szoveg: str) -> str:
    """A ratchet tárgya: ami a felhasználó előtt megjelenik. A kódblokkok (példa-fájlformátum) és a kódként jelölt részek, a
    HTML-megjegyzések (generálás-jelölők) és a hivatkozások célja (fájlnevek) kimaradnak."""
    szoveg = re.sub(r"<!--.*?-->", "", szoveg, flags=re.S)
    szoveg = re.sub(r"^(```+|~~~+).*?^\1[ \t]*$", "", szoveg, flags=re.M | re.S)
    szoveg = re.sub(r"`[^`\n]*`", "", szoveg)
    return re.sub(r"\]\([^)\n]*\)", "]", szoveg)


def tiltott_talalatok(szoveg: str) -> list[str]:
    ki = []
    for nev, minta, kisnagy_fuggetlen in TILTOTT:
        for m in re.finditer(minta, szoveg, re.I if kisnagy_fuggetlen else 0):
            if m.group(0) not in ENGEDETT_SZO:
                ki.append(f"{nev}: „{m.group(0)}”")
    return ki


class Jegyzek(unittest.TestCase):
    def test_pontosan_16_oldal_van_es_a_jegyzek_egyezik_a_fajlokkal(self):
        self.assertEqual(len(doku.OLDALAK), 16)
        self.assertEqual(sorted(p.name for p in USER.iterdir()), sorted(o.fajl for o in doku.OLDALAK),
                         "a docs/user tartalma és a core/doku.OLDALAK jegyzéke eltér")
        self.assertEqual(len({o.azonosito for o in doku.OLDALAK}), 16)
        self.assertEqual(len({o.cim for o in doku.OLDALAK}), 16)

    def test_a_kotelezo_temak_megvannak(self):
        cimek = {o.cim for o in doku.OLDALAK}
        for kell in ("Getting started", "Workspaces", "Notes & editing", "Links & backlinks", "Properties & tags", "Search",
                     "Files & explorer", "Layouts & tabs", "Hotkeys", "Settings & modules", "AI & models", "Privacy & data",
                     "Health & troubleshooting", "Import & migration", "Code workbench", "Demo workspace"):
            self.assertIn(kell, cimek)

    def test_minden_oldal_egy_h1_a_jegyzek_cimevel(self):
        for o, szoveg in oldalak():
            with self.subTest(oldal=o.fajl):
                h1 = re.findall(r"^# (.+)$", doku._kod_nelkul(szoveg), re.M)
                self.assertEqual(h1, [o.cim], "az oldalnak pontosan egy H1-je van, a jegyzék címe")

    def test_minden_oldal_tartalmas(self):
        for o, szoveg in oldalak():
            with self.subTest(oldal=o.fajl):
                prozas = felhasznaloi_szoveg(re.sub(r"\|.*\|", "", szoveg))
                self.assertGreaterEqual(len(re.findall(r"\b\w+\b", prozas)), EN_MIN_SZO, f"{o.fajl}: túl rövid oldal")

    def test_az_oldalak_osszekotottek(self):
        """Minden oldalról legalább két másik oldal érhető el, és minden oldalra mutat másik oldal."""
        celok = {o.fajl: set() for o in doku.OLDALAK}
        for o, szoveg in oldalak():
            for cel in set(relativ_celok(szoveg)):
                if cel in celok and cel != o.fajl:
                    celok[o.fajl].add(cel)
        for fajl, ki in celok.items():
            with self.subTest(oldal=fajl):
                self.assertGreaterEqual(len(ki), 2, "kevesebb mint két másik oldalra hivatkozik")
        bejovo = {cel for ki in celok.values() for cel in ki}
        self.assertEqual({o.fajl for o in doku.OLDALAK} - bejovo, set(), "ezekre az oldalakra nem mutat más oldal")


class Szokincs(unittest.TestCase):
    """Ratchet: nincs fejlesztői szó, magyar betű, személyes vagy beégetett út a felhasználói szövegben."""

    def test_a_ratchet_kinyeroje_maga_is_tesztelt(self):
        rossz = ("A D9 kapu és a K29 sor (F8) a v2-ből jön; futtasd: bin/mos test. A core worker és az endpoint. "
                 "Itt a git commit. A my_value és a viewModel azonosító. Ő hívta: /Users/valaki. Ékezet: árvíztűrő.")
        talalat = " | ".join(tiltott_talalatok(felhasznaloi_szoveg(rossz)))
        for jel in ("D9", "K29", "F8", "v2", "bin/mos", "core", "worker", "endpoint", "git", "commit", "my_value", "viewModel", "/Users/", "á"):
            self.assertIn(jel, talalat, jel)
        jo = ("Press ⌘P for the command palette. F6 moves the focus; Search, Health and Models are pages. "
              "Code: `bin/mos test` is code.\n```\nbin/mos test\n```\n[Search](SEARCH.md) <!-- core -->")
        self.assertEqual(tiltott_talalatok(felhasznaloi_szoveg(jo)), [])

    def test_a_felhasznaloi_szovegben_nincs_tiltott_szo(self):
        for o, szoveg in oldalak():
            with self.subTest(oldal=o.fajl):
                self.assertEqual(tiltott_talalatok(felhasznaloi_szoveg(szoveg)), [])

    def test_a_kodpeldak_sem_hordoznak_szemelyes_utat(self):
        for o, szoveg in oldalak():
            with self.subTest(oldal=o.fajl):
                for minta in ("/Users/", "/Volumes/", "glodi", "Manifold-OS", "var/venv"):
                    self.assertNotIn(minta, szoveg)

    def test_nincs_magyar_szoveg_a_kod_peldakban_sem_a_fajlformatum_kulcsain_kivul(self):
        """A `teszt` blokk szakaszjelzői (`--- bemenet` …) a fájlformátum része és ékezet nélküliek; más magyar betű nincs sehol."""
        for o, szoveg in oldalak():
            with self.subTest(oldal=o.fajl):
                self.assertIsNone(re.search(r"[áéíóöőúüűÁÉÍÓÖŐÚÜŰ]", szoveg))

    def test_a_mappaban_csak_a_16_oldal_van(self):
        self.assertEqual([p.name for p in USER.iterdir() if not p.name.endswith(".md")], [])


def horgonyok(szoveg: str) -> set[str]:
    return set(doku.fejlecek(szoveg))


class Hivatkozasok(unittest.TestCase):
    def test_minden_belso_hivatkozas_letezo_fajlra_es_fejlecre_mutat(self):
        oldalszovegek = {o.fajl: szoveg for o, szoveg in oldalak()}
        for o, szoveg in oldalszovegek.items():
            kod_nelkul = re.sub(r"`[^`\n]*`", "", doku._kod_nelkul(szoveg))
            for cel, hely in re.findall(r"\]\(([^)#\s]+)(?:#([^)\s]*))?\)", kod_nelkul):
                if re.match(r"https?:|mailto:", cel):
                    continue
                with self.subTest(oldal=o, cel=cel, hely=hely):
                    self.assertIn(cel, oldalszovegek, f"{o}: a hivatkozás nem a 16 oldal egyikére mutat: {cel}")
                    if hely:
                        self.assertIn(hely, horgonyok(oldalszovegek[cel]), f"{o}: nincs ilyen fejléc a(z) {cel} oldalon: #{hely}")

    def test_nincs_kulso_hivatkozas_es_nincs_kep_a_repon_kivul(self):
        for o, szoveg in oldalak():
            with self.subTest(oldal=o.fajl):
                kod_nelkul = re.sub(r"`[^`\n]*`", "", doku._kod_nelkul(szoveg))
                self.assertIsNone(re.search(r"\]\((?:https?:|file:|//)", kod_nelkul), "a dokumentáció nem hivatkozik külső címre")
                self.assertNotIn("](../", kod_nelkul)

    def test_a_learn_more_celok_leteznek(self):
        szovegek = {o.azonosito: szoveg for o, szoveg in oldalak()}
        for tema, (azonosito, hely) in doku.LEARN_MORE.items():
            with self.subTest(tema=tema):
                self.assertIn(azonosito, szovegek)
                self.assertIn(hely, horgonyok(szovegek[azonosito]), f"{tema}: nincs `{hely}` fejléc a(z) {azonosito} oldalon")
                fajl, horgony = doku.learn_more(tema)
                self.assertEqual((USER / fajl).is_file(), True)
                self.assertEqual(horgony, hely)
        with self.assertRaises(KeyError):
            doku.learn_more("nincs-ilyen-tema")

    def test_minden_health_ellenorzesnek_van_learn_more_oldala(self):
        kodok = [kod for kod, _ in egeszseg.ELLENORZESEK]
        self.assertGreaterEqual(len(kodok), 7)
        for kod in kodok:
            with self.subTest(ellenorzes=kod):
                self.assertIn(f"health.{kod}", doku.LEARN_MORE, "új Health-ellenőrzés: kell hozzá fejléc a HEALTH-AND-TROUBLESHOOTING.md-ben")

    def test_a_horgony_es_a_fejlec_kinyero(self):
        self.assertEqual(doku.horgony("Search index"), "search-index")
        self.assertEqual(doku.horgony("Trial and calibrated models"), "trial-and-calibrated-models")
        self.assertEqual(doku.horgony("Notes & editing"), "notes--editing")
        self.assertEqual(doku.fejlecek("# A\n```\n# nem fejléc\n```\n## B c ##\n"), {"a": "A", "b-c": "B c"})


class Gyorsbillentyuk(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.szoveg = (USER / "HOTKEYS.md").read_text(encoding="utf-8")
        cls.szt = gyb.szotar()

    def test_a_hotkeys_tabla_egyezik_a_regiszterbol_generalttal(self):
        elvart = gyb.beilleszt(self.szoveg, gyb.tabla(self.szt))
        self.assertEqual(self.szoveg, elvart, "a docs/user/HOTKEYS.md táblázata elavult: python -m core.doku_gyorsbillentyu --iras")
        self.assertTrue(gyb.naprakesz())

    def test_minden_regisztralt_billentyu_szerepel_a_dokumentumban(self):
        regiszter = regisztralt_billentyuk()
        self.assertGreaterEqual(len(regiszter), 25)
        generalt = {s.billentyu for s in gyb.sorok(self.szt)}
        self.assertEqual(sorted(regiszter - generalt), [], "a generátor nem találja a regiszter ezen billentyűit")
        for b in sorted(regiszter):
            with self.subTest(billentyu=b):
                self.assertIn(billentyu_glif(b), self.szoveg)

    def test_a_generalt_nevek_angolok_es_a_billentyuk_egyediek(self):
        sorok = gyb.sorok(self.szt)
        self.assertGreaterEqual(len(sorok), 40)
        self.assertEqual(len({s.billentyu for s in sorok}), len(sorok))
        self.assertEqual(len({s.glif for s in sorok}), len(sorok), "két billentyű ugyanazt a glifet kapná")
        for s in sorok:
            with self.subTest(billentyu=s.billentyu):
                self.assertIsNone(re.search(r"[áéíóöőúüű]", s.nev + s.kategoria, re.I), "magyar parancs- vagy kategórianév")
                self.assertNotIn("{", s.nev)
                self.assertTrue(s.nev.strip() and s.kategoria.strip())

    def test_a_glif_egyezik_a_teszt_kozos_glifjevel(self):
        for b in sorted(regisztralt_billentyuk()):
            self.assertEqual(gyb.billentyu_glif(b), billentyu_glif(b))
        self.assertEqual(gyb.billentyu_glif("Mod+="), "⌘=")
        self.assertEqual(gyb.billentyu_glif("Mod+,"), "⌘,")
        self.assertEqual(gyb.billentyu_glif("Mod+Alt+ArrowLeft"), "⌥⌘←")

    def test_a_kinyero_a_harom_alakot_ismeri(self):
        szt = {"Parancs": "Command", "Kat": "Category", "Szerkesztő": "Editor", "Félkövér": "Bold", "Feladat": "Toggle task",
               "{n}. fül": "Tab {n}", "Utolsó fül": "Last tab", "Fül": "Tab"}
        forras = (
            "{ id: 'a.b', nev: tk('Parancs'), kategoria: tk('Kat'), billentyu: 'Mod+Shift+X', futtat: () => {} },\n"
            "{\n  id: 'c.d',\n  nev: tk('Parancs'),\n  kategoria: 'Kat',\n  // megjegyzés\n  billentyu: 'Alt+Enter',\n},\n"
            "formaz('felkover', tk('Félkövér'), '**', 'Mod+B'),\n"
            "notion('feladat-valt', tk('Feladat'), feladatValt, { billentyu: 'Mod+Enter', elerheto: () => true }),\n"
            "{ id: `ful.n${i + 1}`, billentyu: `Mod+${i + 1}`, },\n"
            "<Gomb billentyu=\"Mod+Q\" /> { jel: '*', billentyu: '⌘I' }")
        sorok = {s.billentyu: s for s in gyb.sorok_szovegbol(forras, szt)}
        self.assertEqual(sorok["Mod+Shift+X"], gyb.Sor("Mod+Shift+X", "Command", "Category"))
        self.assertEqual(sorok["Alt+Enter"], gyb.Sor("Alt+Enter", "Command", "Category"))
        self.assertEqual(sorok["Mod+B"], gyb.Sor("Mod+B", "Bold", "Editor"))
        self.assertEqual(sorok["Mod+Enter"], gyb.Sor("Mod+Enter", "Toggle task", "Editor"))
        self.assertEqual((sorok["Mod+1"].nev, sorok["Mod+9"].nev), ("Tab 1", "Last tab"))
        self.assertNotIn("Mod+Q", sorok)         # Svelte-attribútum, nem regiszter-parancs
        self.assertEqual(len(sorok), 13)         # 2 + 1 + 1 + 9 tabszám; a glif-billentyű (⌘I) kimarad
        with self.assertRaises(gyb.HianyzoFordites):
            gyb.sorok_szovegbol("{ id: 'x.y', nev: tk('Ismeretlen ékezetes'), kategoria: tk('Kat'), billentyu: 'Mod+Z' }", szt)

    def test_a_regiszter_valtozasa_elavulttatja_a_tablat(self):
        uj = gyb.tabla(self.szt) + "\n### Extra\n\n| Shortcut | Command |\n|---|---|\n| ⌘Q | Új |\n"
        self.assertNotEqual(gyb.beilleszt(self.szoveg, uj), self.szoveg)
        with self.assertRaises(ValueError):
            gyb.beilleszt("nincs jelölő", uj)

    def test_a_hotkeys_oldal_megmondja_a_billentyu_atirasat(self):
        self.assertIn("Settings › Hotkeys", self.szoveg)
        self.assertIn("## Changing a shortcut", self.szoveg)


class Betoltes(unittest.TestCase):
    def test_a_mappa_a_gyokerbol_oldodik_fel(self):
        self.assertEqual(doku.mappa(), config.os_root() / "docs" / "user")
        self.assertEqual(doku.mappa().resolve(), USER.resolve())

    def test_az_oldalak_olvashatok_azonosito_es_fajlnev_szerint(self):
        self.assertTrue(doku.olvas("search").startswith("# Search"))
        self.assertEqual(doku.olvas("SEARCH.md"), doku.olvas("search"))
        with self.assertRaises(KeyError):
            doku.olvas("nincs")

    def test_a_munkater_alak_wikilinkeket_hasznal_es_nem_hordoz_megjegyzest(self):
        fajlok = doku.munkater_fajlok()
        self.assertEqual(len(fajlok), 16)
        nevek = {Path(ut).stem: ut for ut in fajlok}
        self.assertEqual(len(nevek), 16, "két oldal ugyanazt a fájlnevet kapná")
        self.assertTrue(all(ut.startswith("Manifold Guide/") and ut.endswith(".md") for ut in fajlok))
        self.assertTrue(all("&" not in ut for ut in fajlok))
        for ut, adat in fajlok.items():
            szoveg = adat.decode("utf-8")
            with self.subTest(ut=ut):
                self.assertNotIn("<!--", szoveg)
                self.assertEqual(relativ_celok(szoveg), [], "maradt Markdown-hivatkozás a fájlokra")
                kod_nelkul = re.sub(r"`[^`\n]*`", "", doku._kod_nelkul(szoveg))
                for cel in re.findall(r"\[\[([^\]|#\\]+)(?:#[^\]|\\]*)?(?:\\?\|[^\]]*)?\]\]", kod_nelkul):
                    self.assertIn(cel, nevek, f"{ut}: a wikilink nem oldódik fel: {cel}")
                for sor in kod_nelkul.splitlines():
                    if sor.lstrip().startswith("|") and "[[" in sor:       # táblázatsorban a wikilink-álnév `|`-ja védett
                        self.assertIsNone(re.search(r"\[\[[^\]]*[^\\]\|[^\]]*\]\]", sor), f"{ut}: védetlen | a táblázatban: {sor}")

    def test_a_munkater_alak_nem_hoz_letre_veletlen_cimket_jelolest_vagy_linket(self):
        """A demo-ban a kódon kívüli `#szó`, `%%`, `==x==`, `$x$`, `^blokk` valódi Markdown lenne (címke, megjegyzés, kiemelés)."""
        for ut, adat in doku.munkater_fajlok().items():
            kod_nelkul = re.sub(r"\[\[[^\]]*\]\]", "", re.sub(r"`[^`\n]*`", "", doku._kod_nelkul(adat.decode("utf-8"))))
            with self.subTest(ut=ut):
                self.assertEqual(re.findall(r"(?<![\w&])#[A-Za-z][\w/-]*|\^[a-z0-9-]+\b|%%|==[^=\n]+==|\$[^$\n]+\$", kod_nelkul), [])

    def test_a_wikilink_fejlecek_leteznek_a_celoldalon(self):
        fajlok = doku.munkater_fajlok()
        fejlecek = {Path(ut).stem: set(doku.fejlecek(adat.decode("utf-8")).values()) for ut, adat in fajlok.items()}
        db = 0
        for ut, adat in fajlok.items():
            kod_nelkul = re.sub(r"`[^`\n]*`", "", doku._kod_nelkul(adat.decode("utf-8")))
            for cel, fej in re.findall(r"\[\[([^\]|#\\]+)#([^\]|\\]+)", kod_nelkul):
                db += 1
                self.assertIn(fej, fejlecek[cel], f"{ut}: nincs `{fej}` fejléc a(z) {cel} oldalon")
        self.assertGreater(db, 0, "a példa-minta legalább egy fejlécre mutató linket vár")

    def test_a_tablazatos_wikilink_alias_pipeja_vedett(self):
        os_doku = doku.munkater_szoveg("| Readiness | [Ready](SETTINGS-AND-MODULES.md#modules) |\nSzöveg [Ready](SETTINGS-AND-MODULES.md#modules).")
        self.assertIn("[[Settings and modules#Modules\\|Ready]]", os_doku)
        self.assertIn("[[Settings and modules#Modules|Ready]].", os_doku)
        self.assertIn("[[Search]]", doku.munkater_szoveg("[Search](SEARCH.md)"))
        self.assertEqual(doku.munkater_szoveg("[x](nem-oldal.md) [y](https://a.b)"), "[x](nem-oldal.md) [y](https://a.b)")

    def test_a_masolat_nem_ir_felul_es_a_felulir_visszaallit(self):
        with tempfile.TemporaryDirectory() as tmp:
            cel = Path(tmp) / "Guide"
            irt = doku.masol_munkaterbe(cel)
            self.assertEqual(len(irt), 16)
            self.assertEqual(sorted(p.name for p in cel.iterdir()), sorted(Path(u).name for u in doku.munkater_fajlok()))
            szerkesztett = cel / "Getting started.md"
            szerkesztett.write_text("a felhasználó szerkesztése\n", encoding="utf-8")
            torolt = cel / "Search.md"
            torolt.unlink()
            masodik = doku.masol_munkaterbe(cel)
            self.assertEqual([p.name for p in masodik], ["Search.md"], "csak a hiányzó fájl jön létre")
            self.assertEqual(szerkesztett.read_text(encoding="utf-8"), "a felhasználó szerkesztése\n")
            doku.masol_munkaterbe(cel, felulir=True)
            self.assertEqual(szerkesztett.read_bytes(), doku.munkater_fajlok("")["Getting started.md"])
            self.assertEqual([p for p in cel.iterdir() if p.name.startswith(".")], [], "maradt ideiglenes fájl")

    def test_a_cli_listaja_16_sor(self):
        import contextlib
        import io
        ki = io.StringIO()
        with contextlib.redirect_stdout(ki):
            self.assertEqual(doku.main(["lista"]), 0)
        self.assertEqual(len(ki.getvalue().splitlines()), 16)
        ki = io.StringIO()
        with contextlib.redirect_stdout(ki):
            self.assertEqual(doku.main(["learn", "health.index"]), 0)
        self.assertEqual(ki.getvalue().strip(), "HEALTH-AND-TROUBLESHOOTING.md#search-index")


if __name__ == "__main__":
    unittest.main()
