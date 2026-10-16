"""A modell-letöltő (core/letoltes.py): választás, jóváhagyás, napló — hálózat nélkül, álkönyvtárban."""

import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from core import letoltes

LISTA = """
[modell.meglevo]
repo = "a/meglevo"
meret_gb = 1.0
megvan = true

[modell.egy]
repo = "a/egy"
meret_gb = 0.5
kor = "elso"
minta = ["*.json"]

[modell.ketto]
repo = "a/ketto"
meret_gb = 0.25
kor = "opcionalis"
konvertalas = true
"""


class LetoltesTeszt(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="mos-letoltes-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)     # L4: a teszt maga után takarít
        (self.tmp / "letoltes.toml").write_text(LISTA, encoding="utf-8")
        self.modellek = letoltes.jeloltek_betoltese(self.tmp / "letoltes.toml")
        self.env = mock.patch.dict(os.environ, {
            "MOS_LETOLTES": str(self.tmp / "letoltes.toml"),
            "MOS_MODELS": str(self.tmp / "models"),
            "MOS_RUNS": str(self.tmp / "runs"),
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_valasztas(self):
        self.assertEqual(letoltes.valasztas(self.modellek, []), ["egy"])
        self.assertEqual(letoltes.valasztas(self.modellek, ["mind"]), ["egy", "ketto"])
        self.assertEqual(letoltes.valasztas(self.modellek, ["ketto", "opcionalis"]), ["ketto"])
        self.assertEqual(letoltes.valasztas(self.modellek, ["meglevo"]), [])
        with self.assertRaises(letoltes.LetoltesHiba):
            letoltes.valasztas(self.modellek, ["nincs"])

    def test_nem_valasz_nem_tolt_le(self):
        with mock.patch("core.letoltes.letolt") as l, redirect_stdout(io.StringIO()) as out:
            kod = letoltes.main(["mind"], bemenet=lambda _: "n")
        self.assertEqual(kod, 1)
        l.assert_not_called()
        self.assertIn("0.75 GB", out.getvalue())

    def test_lista_nem_tolt_le(self):
        with mock.patch("core.letoltes.letolt") as l, redirect_stdout(io.StringIO()):
            self.assertEqual(letoltes.main(["--lista"]), 0)
        l.assert_not_called()

    def test_letolt_mintaval_es_naplo_hibanal_folytat(self):
        hivasok = []

        def al_letolto(repo_id, allow_patterns, cache_dir, max_workers, token, revision=None):
            hivasok.append((repo_id, allow_patterns, cache_dir))
            self.assertEqual(token, "hf_x")
            if repo_id == "a/egy":
                raise OSError("nincs hálózat")

        naplo = self.tmp / "runs" / "n.json"
        with redirect_stdout(io.StringIO()), mock.patch("sys.stderr", io.StringIO()):
            e = letoltes.letolt(self.modellek, ["egy", "ketto"], self.tmp / "hub", naplo,
                                   letolto=al_letolto, token="hf_x")
        self.assertEqual(hivasok[0], ("a/egy", ["*.json"], str(self.tmp / "hub")))
        self.assertEqual(hivasok[1][1], None)
        self.assertTrue(e["egy"].startswith("hiba"))
        self.assertEqual(e["ketto"], "kész")
        self.assertEqual(json.loads(naplo.read_text())["ketto"]["eredmeny"], "kész")

    def test_rogzitett_revizio_toltodik_es_ellenorzott(self):
        """C19 (T141): a `revizio` a letöltő `revision=`-je; ha a letöltött pillanatkép nem az, hiba."""
        rev = "a" * 40
        modellek = {"egy": {**self.modellek["egy"], "revizio": rev}, "ketto": {**self.modellek["ketto"], "revizio": rev}}
        hivasok = []

        def al_letolto(repo_id, allow_patterns, cache_dir, max_workers, token, revision=None):
            hivasok.append(revision)
            return f"{cache_dir}/models--x/snapshots/{rev if repo_id == 'a/egy' else 'b' * 40}"

        with redirect_stdout(io.StringIO()), mock.patch("sys.stderr", io.StringIO()):
            e = letoltes.letolt(modellek, ["egy", "ketto"], self.tmp / "hub", self.tmp / "n.json", letolto=al_letolto)
        self.assertEqual(hivasok, [rev, rev])
        self.assertEqual(e["egy"], "kész")
        self.assertIn("nem a rögzített revízió", e["ketto"])

    def test_revizio_ellenorzes_a_gyorsitotaron(self):
        """C19 (T141): a doctor eltérései (a helyi refs/main, a pillanatkép, a kalibrált sor pillanatképe)."""
        from core.modell import revizio as R
        a, b = "a" * 40, "b" * 40
        models = self.tmp / "models"

        def gyorsitotar(repo, main, *snapshotok):
            d = R.repo_mappa(models, repo)
            (d / "refs").mkdir(parents=True)
            (d / "refs" / "main").write_text(main)
            for s in snapshotok:
                (d / "snapshots" / s).mkdir(parents=True)
        gyorsitotar("x/jo", a, a)
        gyorsitotar("x/main", b, a, b)
        gyorsitotar("x/hianyzik", b, b)
        gyorsitotar("x/nincsrev", a, a)
        lista = {"jo": {"repo": "x/jo", "revizio": a}, "main": {"repo": "x/main", "revizio": a},
                 "hianyzik": {"repo": "x/hianyzik", "revizio": a}, "nincsrev": {"repo": "x/nincsrev"},
                 "nincs_letoltve": {"repo": "x/semmi", "revizio": a}}
        self.assertEqual({e["modell"]: e["fajta"] for e in R.ellenoriz(lista, models)},
                         {"main": "main_elter", "hianyzik": "hianyzo_pillanatkep", "nincsrev": "nincs_revizio"})
        self.assertEqual(R.mert_pillanatkep(models, "x/main", a), a)
        self.assertEqual(R.mert_pillanatkep(models, "x/hianyzik", a), b)
        sorok = [{"feladat": "szoveg", "modell": "jo", "kalibralt": 1, "snapshot": a},
                 {"feladat": "szoveg", "modell": "main", "kalibralt": 1, "snapshot": b},
                 {"feladat": "szoveg", "modell": "nincsrev", "kalibralt": 1, "snapshot": ""}]
        rossz = R.kalibracio_elteres(sorok, {"jo": a, "main": a})
        self.assertEqual(len(rossz), 1)
        self.assertIn("main", rossz[0])

    def test_a_valodi_lista_minden_modellje_rogzitett_revizioju(self):
        import tomllib
        from core.modell import revizio
        with open(Path(__file__).resolve().parents[1] / "config" / "models.toml", "rb") as f:
            lista = tomllib.load(f)["modell"]
        self.assertEqual([n for n, m in lista.items() if not revizio.SHA.match(m.get("revizio", ""))], [])

    def test_igen_utan_a_models_ala_tolt(self):
        with mock.patch("core.letoltes.letolt", return_value={"egy": "kész"}) as l, \
                redirect_stdout(io.StringIO()):
            kod = letoltes.main([], bemenet=lambda _: "i")
        self.assertEqual(kod, 0)
        self.assertEqual(l.call_args.args[2], self.tmp / "models" / "hub")

    def test_token_rejtetten_bekerve_es_csak_atadva(self):
        with mock.patch("core.letoltes.letolt", return_value={"egy": "kész"}) as l, \
                redirect_stdout(io.StringIO()) as out:
            kod = letoltes.main(["--token", "--igen"], jelszokero=lambda _: "hf_titok")
        self.assertEqual(kod, 0)
        self.assertEqual(l.call_args.kwargs["token"], "hf_titok")
        self.assertNotIn("hf_titok", out.getvalue())
        self.assertNotIn("hf_titok", "".join(p.read_text() for p in (self.tmp / "runs").glob("*") if p.is_file()))

    def test_rossz_token_elutasitva(self):
        with mock.patch("core.letoltes.letolt") as l, redirect_stdout(io.StringIO()), \
                mock.patch("sys.stderr", io.StringIO()):
            self.assertEqual(letoltes.main(["--token", "--igen"], jelszokero=lambda _: "abc"), 2)
        l.assert_not_called()


if __name__ == "__main__":
    unittest.main()
