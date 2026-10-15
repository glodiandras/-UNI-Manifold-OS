"""Dokumentum-konzisztencia (T192, 2. audit): a regiszter és a dokumentáció nem csúszhat szét.

- minden regisztrált végpont (`server.regiszter_epit()`) szerepel az útvonal-tábla tesztben (`KERESEK`) ÉS a
  `docs/ARCHITECTURE.md`-ben `METÓDUS /út` alakban (kódként: `` `GET /api/…` ``);
- a CLAUDE.md döntésszámai folytonosak (1-től; a C29 összefésülése után egy kimaradt vagy ütköző szám bukik).
- a README (C34) a kódot tükrözi: minden regisztrált billentyű szerepel benne, a hivatkozott konfigurációs kulcsok léteznek az
  `os.toml`-ban, a felsorolt `bin/mos` parancsok léteznek, és a relatív hivatkozások fájlokra mutatnak.
A tesztek a dokumentum szövegét és a regisztert olvassák: szerverindítás, hálózat, valódi `var/` nincs."""
import re
import tomllib
import unittest

from core import server
from tests.helpers import REPO
from tests.test_utvonalak import KERESEK, lefedetlen

ARCHITECTURE = (REPO / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
CLAUDE = (REPO / "CLAUDE.md").read_text(encoding="utf-8")
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
        self.assertEqual(hianyzo, [], "ezek a végpontok nincsenek a docs/ARCHITECTURE.md-ben `METÓDUS /út` alakban "
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
        """CLAUDE.md 1. szakasz: `| N |` sorok 1-től folytonosan (a C29 összefésülése után a 32. és a C29.5 döntései
        is); a D1–D12 tábla külön szakaszban van, a dátumok sorrendje nem számít (a 15–17. sor utólag került be)."""
        szakasz = CLAUDE.split("## 1. Rögzített döntések", 1)[1].split("\n## 2.", 1)[0]
        szamok = [int(m.group(1)) for m in re.finditer(r"^\| (\d+) \|", szakasz, re.M)]
        self.assertGreaterEqual(len(szamok), 43)
        self.assertEqual(szamok, list(range(1, len(szamok) + 1)), "hiányzó vagy ütköző döntésszám a CLAUDE.md-ben")

    def test_a_legacy_dontesek_d1_d12_teljesek(self):
        szakasz = CLAUDE.split("## 2. A legacy döntései", 1)[1].split("\n## 3.", 1)[0]
        self.assertEqual([int(m.group(1)) for m in re.finditer(r"^\| D(\d+) \|", szakasz, re.M)], list(range(1, 13)))


# ------------------------------------------------------------------ README (C34)

GLIF_MOD = (("Ctrl", "⌃"), ("Alt", "⌥"), ("Shift", "⇧"), ("Mod", "⌘"))     # a macOS sorrendje: ⌃⌥⇧⌘
GLIF_KULCS = {"ArrowRight": "→", "ArrowLeft": "←", "ArrowDown": "↓", "ArrowUp": "↑", "Enter": "↩"}


def billentyu_glif(billentyu: str) -> str:
    """`Mod+Shift+F` → `⇧⌘F` (a README alakja)."""
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


class ReadmeKonzisztencia(unittest.TestCase):
    def test_a_billentyu_glif_alakja(self):
        self.assertEqual(billentyu_glif("Mod+Shift+F"), "⇧⌘F")
        self.assertEqual(billentyu_glif("Mod+Alt+ArrowRight"), "⌥⌘→")
        self.assertEqual(billentyu_glif("Ctrl+Shift+Tab"), "⌃⇧Tab")
        self.assertEqual(billentyu_glif("F6"), "F6")
        self.assertEqual(billentyu_glif("Mod+Enter"), "⌘↩")

    def test_minden_regisztralt_billentyu_szerepel_a_readme_ben(self):
        billentyuk = regisztralt_billentyuk()
        self.assertGreaterEqual(len(billentyuk), 25, "a kinyerő nem talál billentyűket (megváltozott a regiszter alakja?)")
        hianyzo = sorted(b for b in billentyuk if billentyu_glif(b) not in README)
        self.assertEqual(hianyzo, [], "ezek a billentyűk a regiszterben vannak, de a README billentyű-táblájában nem (⌃⌥⇧⌘ sorrend)")

    def test_a_readme_konfiguracios_kulcsai_leteznek_az_os_toml_ban(self):
        os_toml = tomllib.loads((REPO / "config" / "os.toml").read_text(encoding="utf-8"))
        kulcsok = re.findall(r"`\[([\w.]+)\] (\w+)`", README)
        self.assertGreaterEqual(len(kulcsok), 4)
        for szakasz, kulcs in kulcsok:
            adat = os_toml
            for resz in szakasz.split("."):
                adat = adat.get(resz, {})
            with self.subTest(kulcs=f"[{szakasz}] {kulcs}"):
                self.assertIn(kulcs, adat, f"a README `[{szakasz}] {kulcs}` kulcsa nincs az os.toml-ban")

    def test_a_readme_bin_mos_parancsai_leteznek(self):
        bin_mos = (REPO / "bin" / "mos").read_text(encoding="utf-8")
        szakasz = README.split("## 7. Parancsok", 1)[1].split("\n## 8.", 1)[0]
        parancsok = {m.group(1) for sor in szakasz.splitlines() if sor.startswith("| `")
                     for m in re.finditer(r"`([a-z]+)(?: [^`]*)?`", sor.split("|")[1])}
        self.assertGreaterEqual(len(parancsok), 18)
        for p in sorted(parancsok):
            with self.subTest(parancs=p):
                self.assertRegex(bin_mos, rf"(?m)^\s+(?:[a-z]+\|)*{p}(?:\|[a-z]+)*\)", f"a README `bin/mos {p}` parancsa nincs a bin/mos-ban")

    def test_a_readme_relativ_hivatkozasai_fajlokra_mutatnak(self):
        celok = re.findall(r"\]\((?!https?:)([^)#\s]+)", README)
        self.assertGreaterEqual(len(celok), 8)
        for cel in sorted(set(celok)):
            with self.subTest(cel=cel):
                self.assertTrue((REPO / cel).exists(), f"a README hivatkozása nem létező fájlra mutat: {cel}")

    def test_a_readme_a_kapcsolokat_es_a_kiveteleket_megnevezi(self):
        for szo in ("Asszisztens", "Tracker", "local.manifold-os.app.plist", "~/Manifold-backup", "docs/KIADAS.md"):
            with self.subTest(szo=szo):
                self.assertIn(szo, README)


class SegedszkriptekTiszta(unittest.TestCase):
    """A `tools/` alatti szkriptek és leírások nem hordozhatnak feloldatlan merge- vagy stash-konfliktusjelölőt, a shell
    szkriptek szintaktikailag épek, és nincs bennük beégetett vault/legacy út (CLAUDE.md §4)."""

    JELOLO = re.compile(r"^(?:<{7}(?: .*)?|={7}|>{7}(?: .*)?)$", re.MULTILINE)

    def _fajlok(self):
        return sorted(p for p in (REPO / "tools").rglob("*") if p.is_file() and p.suffix in {".sh", ".md", ".py", ".toml", ".txt"})

    def test_nincs_konfliktusjelolo_a_tools_alatt(self):
        fajlok = self._fajlok()
        self.assertGreaterEqual(len(fajlok), 5)
        for p in fajlok:
            with self.subTest(fajl=str(p.relative_to(REPO))):
                self.assertIsNone(self.JELOLO.search(p.read_text(encoding="utf-8")), "feloldatlan konfliktusjelölő")

    def test_a_jelolo_felismerese(self):
        self.assertTrue(self.JELOLO.search("a\n<<<<<<< Updated upstream\nb\n=======\nc\n>>>>>>> Stashed changes\n"))
        self.assertIsNone(self.JELOLO.search("| a | b |\n|---|---|\n# ======== cím\n"))

    def test_a_shell_szkriptek_szintaxisa_ep(self):
        import subprocess
        for p in (p for p in self._fajlok() if p.suffix == ".sh"):
            with self.subTest(fajl=str(p.relative_to(REPO))):
                r = subprocess.run(["bash", "-n", str(p)], capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr)

    def test_nincs_beegetett_legacy_ut_a_kodban(self):
        for p in (p for p in self._fajlok() if p.suffix == ".sh"):
            kod = "\n".join(s for s in p.read_text(encoding="utf-8").splitlines() if not s.lstrip().startswith("#"))
            with self.subTest(fajl=str(p.relative_to(REPO))):
                self.assertNotIn("Manifold-OS legacy", kod)


if __name__ == "__main__":
    unittest.main()
