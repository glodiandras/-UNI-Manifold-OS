"""Dokumentum-konzisztencia (T192, 2. audit; F2: fejlesztői és felhasználói rész): a regiszter és a dokumentáció nem csúszhat szét.

**Fejlesztői dokumentáció** (`docs/dev/`):
- minden regisztrált végpont (`server.regiszter_epit()`) szerepel az útvonal-tábla tesztben (`KERESEK`) ÉS a
  `docs/dev/ARCHITECTURE.md`-ben `METÓDUS /út` alakban (kódként: `` `GET /api/…` ``);
- a `docs/dev/DECISIONS-v2.md` döntésszámai folytonosak (1-től; egy kimaradt vagy ütköző szám bukik), a D1–D12 tábla teljes.

**Felhasználói dokumentáció** (`README.md`, angol termék-README; `docs/user/`, ha már van):
- a README-ben hivatkozott konfigurációs kulcsok léteznek az `os.toml`-ban, a felsorolt `bin/mos` parancsok léteznek a
  `bin/mos`-ban, a relatív hivatkozások fájlokra mutatnak, és nincs benne fejlesztői (személyes) út;
- a felület minden regisztrált billentyűje szerepel a `docs/user/HOTKEYS.md`-ben (ha a fájl még nincs: `[indokolt]` kihagyás).
A tesztek a dokumentum szövegét és a regisztert olvassák: szerverindítás, hálózat, valódi `var/` nincs."""
import re
import tomllib
import unittest

from core import server
from tests.helpers import REPO
from tests.test_utvonalak import KERESEK, lefedetlen

DEV = REPO / "docs" / "dev"
USER = REPO / "docs" / "user"
HOTKEYS = USER / "HOTKEYS.md"
INDOKOLT_FELHASZNALOI = "[indokolt] a felhasználói dokumentáció az F8-ban készül"

ARCHITECTURE = (DEV / "ARCHITECTURE.md").read_text(encoding="utf-8")
DONTESEK = (DEV / "DECISIONS-v2.md").read_text(encoding="utf-8")
README = (REPO / "README.md").read_text(encoding="utf-8")

METODUS = r"(?:GET|POST|PUT|HEAD|DELETE)"
# A minta-végpontok közül ami regex-ből nem származtatható egyértelműen: (metódus, minta) → a dokumentum alakja, vagy
# `None`: indokolt kivétel (nem funkció-végpont)
KIVETEL = {
    ("GET", "/media/.*"): ("GET", "/media/{}/{}"),     # a dokumentumban: `GET|HEAD /media/<token>/<út>`
    ("GET", "/api/vault/.*"): None,                      # az ismeretlen /api/vault/… út 404-e (catch-all), nem végpont
}


def kanonikus(metodus: str, ut: str, minta: bool):
    """A regisztrált végpont dokumentum-alakja: a minta csoportjai (`(\\w+)`, `(\\d+)`, `([\\w.-]+)`) → `{}`."""
    if minta:
        if (metodus, ut) in KIVETEL:
            return KIVETEL[(metodus, ut)]
        ut = re.sub(r"\((?:\?P<\w+>)?[^()]*\)", "{}", ut)
    return metodus, ut


def dokumentum_vegpontjai(szoveg: str) -> set[tuple[str, str]]:
    """A dokumentum kód-szakaszaiból (`` `…` ``) a `METÓDUS /út` alakok; az `<x>` és `{x}` helyőrző `{}`, a lekérdezés
    (`?…`) és a törzs levágva, a `GET|HEAD` mindkét metódust adja."""
    ki = set()
    for kod in re.findall(r"`([^`\n]+)`", szoveg):
        kod = kod.replace("\\|", "|")
        m = re.match(rf"({METODUS}(?:[|/]{METODUS})*)\s+(/[^\s?`]*)", kod)
        if not m:
            continue
        ut = re.sub(r"<[^<>]*>|\{[^{}]*\}", "{}", m.group(2)).rstrip(".,;:")
        for metodus in re.split(r"[|/]", m.group(1)):
            ki.add((metodus, ut))
    return ki


# ================================================================== fejlesztői dokumentáció (docs/dev)

class VegpontDokumentacio(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.regiszter = server.regiszter_epit()
        cls.vegpontok = cls.regiszter.vegpontok()

    def test_minden_regisztralt_vegpont_szerepel_a_keresek_tablaban(self):
        self.assertEqual(lefedetlen(self.regiszter, KERESEK), [],
                         "ezek a végpontok nincsenek a tests/test_utvonalak.py KERESEK/ELVART táblájában")

    def test_minden_regisztralt_vegpont_szerepel_az_architecture_ben(self):
        doku = dokumentum_vegpontjai(ARCHITECTURE)
        hianyzo = []
        for metodus, ut, minta in self.vegpontok:
            k = kanonikus(metodus, ut, minta)
            if k is not None and k not in doku:
                hianyzo.append(f"{k[0]} {k[1]}" + (f"   (minta: {ut})" if minta else ""))
        self.assertEqual(hianyzo, [], "ezek a végpontok nincsenek a docs/dev/ARCHITECTURE.md-ben `METÓDUS /út` alakban "
                                      "(kódként, pl. `GET /api/…`)")

    def test_a_kivetelek_valodi_vegpontok_es_indokoltak(self):
        van = {(m, u) for m, u, minta in self.vegpontok if minta}
        self.assertEqual(set(KIVETEL) - van, set(), "a KIVETEL olyan mintát nevez meg, amely nincs regisztrálva")

    def test_a_kinyero_a_dokumentum_alakjait_ismeri(self):
        s = ("| `GET\\|HEAD /media/<token>/<út>` | x |\n`GET /api/vault/kereses?q=&limit=` `POST /api/vault/uj {mappa, nev}` "
             "`GET/PUT /api/x` `GET /api/feladatok/{id}?tol=N` és `nem végpont` meg `GET` egyedül")
        self.assertEqual(dokumentum_vegpontjai(s), {
            ("GET", "/media/{}/{}"), ("HEAD", "/media/{}/{}"), ("GET", "/api/vault/kereses"), ("POST", "/api/vault/uj"),
            ("GET", "/api/x"), ("PUT", "/api/x"), ("GET", "/api/feladatok/{}")})
        self.assertEqual(kanonikus("GET", r"/api/pillanat/(\w+)/naplo", True), ("GET", "/api/pillanat/{}/naplo"))
        self.assertEqual(kanonikus("POST", r"/api/naptar/javaslat/(\d+)/jovahagy", True), ("POST", "/api/naptar/javaslat/{}/jovahagy"))
        self.assertEqual(kanonikus("GET", "/health", False), ("GET", "/health"))


class DontesSzamok(unittest.TestCase):
    def test_a_dontesszamok_folytonosak(self):
        """`docs/dev/DECISIONS-v2.md` 1. szakasz: `| N |` sorok 1-től folytonosan; a D1–D12 tábla külön szakaszban van, a
        dátumok sorrendje nem számít (a 15–17. sor utólag került be)."""
        szakasz = DONTESEK.split("## 1. Rögzített döntések", 1)[1].split("\n## 2.", 1)[0]
        szamok = [int(m.group(1)) for m in re.finditer(r"^\| (\d+) \|", szakasz, re.M)]
        self.assertGreaterEqual(len(szamok), 43)
        self.assertEqual(szamok, list(range(1, len(szamok) + 1)), "hiányzó vagy ütköző döntésszám a DECISIONS-v2.md-ben")

    def test_a_legacy_dontesek_d1_d12_teljesek(self):
        szakasz = DONTESEK.split("## 2. A legacy döntései", 1)[1].split("\n## 3.", 1)[0]
        self.assertEqual([int(m.group(1)) for m in re.finditer(r"^\| D(\d+) \|", szakasz, re.M)], list(range(1, 13)))


# ================================================================== felhasználói dokumentáció (README, docs/user)

GLIF_MOD = (("Ctrl", "⌃"), ("Alt", "⌥"), ("Shift", "⇧"), ("Mod", "⌘"))     # a macOS sorrendje: ⌃⌥⇧⌘
GLIF_KULCS = {"ArrowRight": "→", "ArrowLeft": "←", "ArrowDown": "↓", "ArrowUp": "↑", "Enter": "↩"}


def billentyu_glif(billentyu: str) -> str:
    """`Mod+Shift+F` → `⇧⌘F` (a billentyű-tábla alakja)."""
    *modositok, kulcs = billentyu.split("+")
    return "".join(g for nev, g in GLIF_MOD if nev in modositok) + GLIF_KULCS.get(kulcs, kulcs)


def regisztralt_billentyuk() -> set[str]:
    """A felület parancsregiszterének (`billentyu: '…'`) ASCII-alakú billentyűi, forrásból olvasva."""
    ki = set()
    for p in (REPO / "app" / "src").rglob("*"):
        if p.suffix in (".ts", ".svelte"):
            for m in re.finditer(r"billentyu:\s*'([A-Za-z0-9+]+)'", p.read_text(encoding="utf-8")):
                ki.add(m.group(1))
    return ki


def konfig_kulcsok(szoveg: str) -> list[tuple[str, str]]:
    """A dokumentumban `` `[szakasz] kulcs` `` alakban hivatkozott `os.toml`-kulcsok."""
    return re.findall(r"`\[([\w.]+)\] (\w+)`", szoveg)


def bin_mos_hivasok(szoveg: str) -> list[tuple[str, str | None]]:
    """A dokumentumban kódként (kódblokk-sor vagy `` `…` ``) álló `bin/mos <parancs> [<alparancs>]` hívások."""
    sorok = []
    blokkban = False
    for sor in szoveg.splitlines():
        if sor.lstrip().startswith("```"):
            blokkban = not blokkban
            continue
        if blokkban:
            sorok.append(sor.split("#", 1)[0].strip())
    sorok += re.findall(r"`([^`\n]*)`", szoveg)
    ki = []
    for sor in sorok:
        reszek = sor.split()
        if len(reszek) < 2 or reszek[0] != "bin/mos" or not re.fullmatch(r"[a-z]+", reszek[1]):
            continue
        alparancs = reszek[2] if len(reszek) > 2 and re.fullmatch(r"[a-z][a-z-]*", reszek[2]) else None
        ki.append((reszek[1], alparancs))
    return ki


def relativ_celok(szoveg: str) -> list[str]:
    return re.findall(r"\]\((?!https?:|mailto:)([^)#\s]+)", szoveg)


class FelhasznaloiDokumentacioKinyerok(unittest.TestCase):
    """A kinyerők maguk is tesztelve vannak (a dokumentumtól függetlenül, inline mintán)."""

    def test_a_billentyu_glif_alakja(self):
        self.assertEqual(billentyu_glif("Mod+Shift+F"), "⇧⌘F")
        self.assertEqual(billentyu_glif("Mod+Alt+ArrowRight"), "⌥⌘→")
        self.assertEqual(billentyu_glif("Ctrl+Shift+Tab"), "⌃⇧Tab")
        self.assertEqual(billentyu_glif("F6"), "F6")
        self.assertEqual(billentyu_glif("Mod+Enter"), "⌘↩")

    def test_a_konfig_kulcs_kinyero(self):
        self.assertEqual(konfig_kulcsok("a `[meres] ervenyes_kuszob` és a `[modellek.x] ram_gb` meg `nem kulcs`"),
                         [("meres", "ervenyes_kuszob"), ("modellek.x", "ram_gb")])

    def test_a_bin_mos_kinyero(self):
        s = ("```bash\nbin/mos runtime fetch      # online\nbin/mos test\nbin/mos app test --verbose\n```\n"
             "A `bin/mos doctor` ellenőriz; `bin/mos models pull <név>`; nem hívás: `bin/mosaic x`, `mos test`.")
        self.assertEqual(bin_mos_hivasok(s), [("runtime", "fetch"), ("test", None), ("app", "test"),
                                              ("doctor", None), ("models", "pull")])

    def test_a_relativ_cel_kinyero(self):
        self.assertEqual(relativ_celok("[a](docs/A.md) [b](https://x.y/z) [c](B.md#fej) [d](mailto:a@b.c)"), ["docs/A.md", "B.md"])


class FelhasznaloiDokumentacio(unittest.TestCase):
    def test_a_readme_nem_hordoz_fejleszto_utat(self):
        for minta in ("/Users/", "/Volumes/", "Manifold-OS v2"):
            with self.subTest(minta=minta):
                self.assertNotIn(minta, README, "a README fejlesztői (személyes) útra hivatkozik")

    def test_a_readme_konfiguracios_kulcsai_leteznek_az_os_toml_ban(self):
        os_toml = tomllib.loads((REPO / "config" / "os.toml").read_text(encoding="utf-8"))
        for szakasz, kulcs in konfig_kulcsok(README):
            adat = os_toml
            for resz in szakasz.split("."):
                adat = adat.get(resz, {})
            with self.subTest(kulcs=f"[{szakasz}] {kulcs}"):
                self.assertIn(kulcs, adat, f"a README `[{szakasz}] {kulcs}` kulcsa nincs az os.toml-ban")

    def test_a_readme_bin_mos_parancsai_leteznek(self):
        bin_mos = (REPO / "bin" / "mos").read_text(encoding="utf-8")
        hivasok = bin_mos_hivasok(README)
        self.assertGreaterEqual(len(hivasok), 5, "a README fejlesztői szakasza `bin/mos` parancsokat sorol")
        for parancs, alparancs in sorted(set(hivasok), key=lambda x: (x[0], x[1] or "")):
            with self.subTest(parancs=f"{parancs} {alparancs or ''}".strip()):
                self.assertRegex(bin_mos, rf"(?m)^\s+(?:[a-z]+\|)*{parancs}(?:\|[a-z]+)*\)",
                                 f"a README `bin/mos {parancs}` parancsa nincs a bin/mos-ban")
                if alparancs:
                    self.assertRegex(bin_mos, rf"\b{alparancs}\b", f"a README `bin/mos {parancs} {alparancs}` alparancsa nincs a bin/mos-ban")

    def test_a_readme_relativ_hivatkozasai_fajlokra_mutatnak(self):
        celok = relativ_celok(README)
        self.assertGreaterEqual(len(celok), 1)
        for cel in sorted(set(celok)):
            with self.subTest(cel=cel):
                self.assertTrue((REPO / cel).exists(), f"a README hivatkozása nem létező fájlra mutat: {cel}")

    def test_minden_regisztralt_billentyu_szerepel_a_hotkeys_dokumentumban(self):
        if not HOTKEYS.is_file():
            self.skipTest(INDOKOLT_FELHASZNALOI)
        billentyuk = regisztralt_billentyuk()
        self.assertGreaterEqual(len(billentyuk), 25, "a kinyerő nem talál billentyűket (megváltozott a regiszter alakja?)")
        szoveg = HOTKEYS.read_text(encoding="utf-8")
        hianyzo = sorted(b for b in billentyuk if billentyu_glif(b) not in szoveg)
        self.assertEqual(hianyzo, [], "ezek a billentyűk a regiszterben vannak, de a HOTKEYS.md-ben nem (⌃⌥⇧⌘ sorrend)")

    def test_a_felhasznaloi_dokumentumok_hivatkozasai_leteznek(self):
        lapok = sorted(USER.glob("*.md")) if USER.is_dir() else []
        if not lapok:
            self.skipTest(INDOKOLT_FELHASZNALOI)
        for lap in lapok:
            for cel in sorted(set(relativ_celok(lap.read_text(encoding="utf-8")))):
                with self.subTest(lap=lap.name, cel=cel):
                    self.assertTrue((lap.parent / cel).exists(), f"{lap.name} hivatkozása nem létező fájlra mutat: {cel}")


if __name__ == "__main__":
    unittest.main()
