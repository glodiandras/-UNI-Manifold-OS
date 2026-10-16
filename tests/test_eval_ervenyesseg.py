"""C18.1: a mérés érvényességi kapuja — mérés-másolatokon és szintetikus válaszokon.

A `tests/adat/c18_1/*.jsonl.gz` három futás fájlja (id, verzió, válasz, usage, mp), mind **szintetikus**: a phi4_mini_reasoning
matek_ellenorzo (20/20 levágva a `<think>`-ben) és a glm_ocr ocr_keplet (levágás-mentes) alakját a `keszit_szintetikus.py`, a
qwen3_vl_4b ocr_kezi (sok levágott, sor- és farok-hurkos) alakját a `keszit_ocr_kezi.py` állítja elő kitalált, semleges szövegből
(füzetfotóból, jegyzetből vagy valódi modell-futásból származó adat nincs a termékben). A sorokban nincs `keres_beallitas`: a
keretet a teszt adja.
"""
import gzip
import importlib.util
import json
import unittest

from core.modell import ervenyesseg as E
from tests.helpers import REPO

ADAT = REPO / "tests" / "adat" / "c18_1"


def masolat(nev: str) -> list[dict]:
    with gzip.open(ADAT / f"{nev}.jsonl.gz", "rt", encoding="utf-8") as f:
        return [json.loads(s) for s in f if s.strip()]


def vizsgal(nev: str, max_tokens: int) -> dict:
    rek = masolat(nev)
    return E.vizsgal(rek, 0.10, max_tokens={r["id"]: max_tokens for r in rek})


class ValodiMeresTest(unittest.TestCase):
    def test_phi4_gondolkodasban_levagva_ervenytelen(self):
        e = vizsgal("phi4_mini_reasoning-matek_ellenorzo", 1200)
        self.assertEqual((e["n"], e["levagott"], e["rossz"], e["ervenyes"]), (20, 20, 20, False))

    def test_qwen3_vl_hurkos_ocr_ervenytelen(self):
        # a szintetikus fixture összetétele (keszit_ocr_kezi.py): 97 sor, 78 levágott, ebből 32 sor-hurok és 6 farok-hurok
        e = vizsgal("qwen3_vl_4b-ocr_kezi", 1500)
        self.assertEqual((e["n"], e["levagott"], e["ervenyes"]), (97, 78, False))
        self.assertEqual(e["hurok"], 38)                         # 32 sor-hurok + 6 farok-ismétlődés
        self.assertEqual(sum(E.sorhurok(r["valasz"]) for r in masolat("qwen3_vl_4b-ocr_kezi")), 32)
        self.assertEqual((e["ures"], e["hiba"]), (0, 0))
        self.assertEqual(e["rossz"], 78)                         # a hurkos sorok mind a levágottak közt vannak
        self.assertGreater(e["rossz_arany"], 0.8)

    def test_a_szintetikus_fixture_a_generator_kimenete_es_nincs_benne_valodi_adat(self):
        spec = importlib.util.spec_from_file_location("keszit_ocr_kezi", ADAT / "keszit_ocr_kezi.py")
        gen = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gen)
        rek = masolat("qwen3_vl_4b-ocr_kezi")
        self.assertEqual(rek, gen.rekordok())                    # a lemezen álló fájl a determinisztikus generátor kimenete
        self.assertEqual({tuple(sorted(r)) for r in rek}, {("id", "mp", "usage", "valasz", "verzio")})
        self.assertEqual({r["verzio"] for r in rek}, {gen.VERZIO})
        self.assertEqual(len({r["id"] for r in rek}), gen.OSSZES)
        self.assertEqual(len(rek), gen.OSSZES)
        for r in rek:
            self.assertEqual(set(r["usage"]), {"prompt_tokens", "completion_tokens", "generation_tps"})
            self.assertNotIn("/", r["id"])

    def test_a_ket_masik_fixture_is_a_generator_kimenete(self):
        spec = importlib.util.spec_from_file_location("keszit_szintetikus", ADAT / "keszit_szintetikus.py")
        gen = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gen)
        kepletek, gondolkodasok = gen.rekordok()
        self.assertEqual(masolat("glm_ocr-ocr_keplet"), kepletek)
        self.assertEqual(masolat("phi4_mini_reasoning-matek_ellenorzo"), gondolkodasok)
        for r in kepletek + gondolkodasok:
            self.assertNotRegex(r["id"], r"IMG_|/")                  # nincs valódi fotónév

    def test_levagas_mentes_futas_ervenyes(self):
        e = vizsgal("glm_ocr-ocr_keplet", 200)
        self.assertEqual((e["n"], e["levagott"], e["hurok"], e["rossz"], e["ervenyes"]), (164, 0, 0, 0, True))

    def test_a_rekord_sajat_kerete_az_erosebb(self):
        rek = [{**r, "keres_beallitas": {"max_tokens": 7200}} for r in masolat("phi4_mini_reasoning-matek_ellenorzo")]
        self.assertEqual(E.vizsgal(rek, 0.10, max_tokens={r["id"]: 1200 for r in rek})["levagott"], 0)


class SzabalyTest(unittest.TestCase):
    def r(self, valasz, **kw):
        return {"id": kw.pop("id", "t"), "valasz": valasz, "keres_beallitas": {"max_tokens": 100}, **kw}

    def test_sorhurok_a_felhasznalo_szabalya(self):
        self.assertTrue(E.sorhurok("\n".join(["13,9 cm"] * 15 + [f"sor {i}" for i in range(10)])))
        self.assertFalse(E.sorhurok("\n".join(["13,9 cm"] * 15)))                   # 20 sor alatt nem
        self.assertFalse(E.sorhurok("\n".join(f"sor {i}" for i in range(40))))

    def test_farok_periodus_az_ismetlodo_mondat(self):
        mondat = "A marxizmus revíziójának elemei a forradalom és a vegyes tulajdon. "
        self.assertIsNotNone(E.farok_periodus("Bevezetés. " * 3 + mondat * 8))
        szoveg = ("Caesar Kr. e. 49-ben átlépte a Rubicont, és ezzel polgárháború kezdődött. A senatus Pompeiust "
                  "bízta meg a köztársaság védelmével, aki Görögországba vonult vissza. Pharszalosznál Caesar döntő "
                  "győzelmet aratott, Pompeius Egyiptomba menekült, ahol megölték. Caesar ezután diktátorként "
                  "reformokat vezetett be: naptárreform, földosztás a veteránoknak, a senatus létszámának növelése. "
                  "Kr. e. 44 márciusának idusán összeesküvők gyilkolták meg a curiában.")
        self.assertIsNone(E.farok_periodus(szoveg))
        self.assertIsNone(E.farok_periodus(mondat))                                # rövid válasz nem vizsgálható

    def test_ures_hiba_levagas_becsles_es_kuszob(self):
        rek = [self.r("<think>sok gondolat</think>  ", id="a"), self.r(None, id="b", hiba="400: rossz kép"),
               self.r("x" * 160, id="c"), self.r("y" * 160, id="d", usage={"completion_tokens": 40})]
        rek += [self.r(f"jó válasz {i}", id=f"j{i}", usage={"completion_tokens": 5}) for i in range(16)]
        e = E.vizsgal(rek, 0.10)
        self.assertEqual((e["ures"], e["hiba"], e["levagott"], e["levagott_becsult"]), (1, 1, 1, 1))
        self.assertEqual((e["rossz"], e["rossz_arany"], e["ervenyes"]), (3, 0.15, False))
        self.assertTrue(E.vizsgal(rek[1:], 0.15)["ervenyes"] is True)              # 2/19 ≤ 15%
        self.assertEqual(e["tetelek"]["levagott"], ["c"])
        self.assertIsNone(e["formatum_hiba"])

    def test_ures_meres_ervenytelen_es_a_formatum_csak_jelentes(self):
        self.assertFalse(E.vizsgal([], 0.10)["ervenyes"])
        rek = [self.r("nincs ítélet", id=str(i), usage={"completion_tokens": 3}) for i in range(5)]
        e = E.vizsgal(rek, 0.10, formatum_ok=lambda v, vart: "ÍTÉLET" in v)
        self.assertEqual((e["formatum_hiba"], e["ervenyes"]), (5, True))
        self.assertIn("formátumhiba 5", E.osszegzes(e))


if __name__ == "__main__":
    unittest.main()
