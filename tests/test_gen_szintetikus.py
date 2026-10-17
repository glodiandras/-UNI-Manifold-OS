"""`tools/gen_szintetikus.py`: the developer tool that makes synthetic gold-set / demo candidates with the user's own API key.

No real network and no Keychain: a scripted fake transport (or a fake opener below the real HTTP layer) stands in, and every
test fails when a socket is touched. Covered: key handling, fixed host / model ids, retry limit, the cost guard (worst case,
crash-safe files, lifetime cap), schema / duplicate / secret / personal-data / language filters, the staging-only output, the
explicit adoption step (approved items only, clean target only, approval state untouched) and the packaging exclusion."""
from __future__ import annotations

import importlib.util
import io
import json
import socket
import subprocess
import sys
import tempfile
import tomllib
import traceback
import unittest
import urllib.error
import urllib.request
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from tests.helpers import REPO

_SPEC = importlib.util.spec_from_file_location("gen_szintetikus", REPO / "tools" / "gen_szintetikus.py")
G = importlib.util.module_from_spec(_SPEC)
sys.modules["gen_szintetikus"] = G
_BC = sys.dont_write_bytecode
sys.dont_write_bytecode = True                       # do not leave a __pycache__ in tools/
try:
    _SPEC.loader.exec_module(G)
finally:
    sys.dont_write_bytecode = _BC

KULCS = "sk-ant-" + "api03-" + "Zq9Xk" * 8          # built at run time: no secret-shaped literal in the repository
MASIK_TITOK = "hf_" + "a1B2" * 9


class HalozatTilosTest(unittest.TestCase):
    """Base class: any socket use fails the test (also when the code under test swallows the error)."""

    def setUp(self):
        self.socket_probak = []

        def tilt(*a, **k):
            self.socket_probak.append(a)
            raise OSError("network is blocked in tests")

        for cel in (mock.patch.object(socket.socket, "connect", tilt), mock.patch.object(socket, "getaddrinfo", tilt),
                    mock.patch.object(socket, "create_connection", tilt)):
            cel.start()
            self.addCleanup(cel.stop)
        self.addCleanup(lambda: self.assertEqual(self.socket_probak, [], "a socket was opened"))
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.gyoker = self.tmp / "repo"
        (self.gyoker / "var").mkdir(parents=True)


# ---------------------------------------------------------------------------------------------------- fakes

def valasz(szoveg, bemenet=1000, kimenet=2000, **kw):
    return G.Valasz(szoveg, {"input_tokens": bemenet, "output_tokens": kimenet}, "end_turn", **kw)


class HamisSzallito:
    """Scripted transport: `forgatokonyv` is a list of Valasz / Exception, or a callable(index, hivas) -> one of them."""

    def __init__(self, forgatokonyv):
        self.forgatokonyv, self.hivasok = forgatokonyv, []

    def kuld(self, modell, rendszer, felhasznalo, max_tokens):
        i = len(self.hivasok)
        self.hivasok.append({"modell": modell, "rendszer": rendszer, "felhasznalo": felhasznalo, "max_tokens": max_tokens})
        x = self.forgatokonyv(i, self.hivasok[-1]) if callable(self.forgatokonyv) else self.forgatokonyv[min(i, len(self.forgatokonyv) - 1)]
        if isinstance(x, BaseException):
            raise x
        return x


def kieg(elotte="Water boils at one hundred degrees Celsius at sea ", utana=" pressure.", elf=("level",)):
    return {"elotte": elotte, "utana": utana, "elfogadhato": list(elf)}


def kod_tetel(**felul):
    ref = "\n".join(["#include <bits/stdc++.h>", "using namespace std;", "", "int main() {", "    int n;", "    cin >> n;",
                     "    long long s = 0;", "    for (int i = 0; i < n; i++) {", "        long long x;", "        cin >> x;",
                     "        s += x;", "    }", "    cout << s << \"\\n\";", "    return 0;", "}", ""])
    lassu = ref.replace("    long long s = 0;", "    long long s = 0;  // brute force")
    leiras = ("# Sum of numbers\n\nA shop records the number of items sold on each of n days. Print the total number of items sold "
              "over all of the days.\n\n## Input\n\nThe first line contains n (1 <= n <= 100000). The second line contains n integers.\n\n"
              "## Output\n\nOne integer: the sum.\n\n## Tests\n\n```teszt Example\n--- bemenet\n3\n1 2 3\n--- kimenet\n6\n```\n\n"
              "```teszt Single\n--- bemenet\n1\n5\n--- kimenet\n5\n```\n")
    bemenet = ("def general(rng, meret):\n    n = 100000 if meret == \"nagy\" else rng.randint(1, 6)\n"
               "    return f\"{n}\\n\" + \" \".join(str(rng.randint(-5, 5)) for _ in range(n)) + \"\\n\"\n\n\n"
               "def ervenyes(s):\n    try:\n        t = s.split()\n        return int(t[0]) == len(t) - 1\n"
               "    except (ValueError, IndexError):\n        return False\n")
    hibak = [{"id": "h1", "fajta": "inicializalas", "sor": 7, "eredeti": "    long long s = 0;", "csere": "    long long s = 1;",
              "magyarazat": "The sum starts at one instead of zero."},
             {"id": "h2", "fajta": "index", "sor": 8, "eredeti": "    for (int i = 0; i < n; i++) {",
              "csere": "    for (int i = 0; i < n - 1; i++) {", "magyarazat": "The loop skips the last number of the input."},
             {"id": "h3", "fajta": "feltetel", "sor": 11, "eredeti": "        s += x;", "csere": "        s -= x;",
              "magyarazat": "Every number is subtracted instead of added."}]
    t = {"cim": "Sum of numbers", "tema": "ciklus_tomb", "nehezseg": 1, "idokorlat_s": 2.0, "leiras_md": leiras, "ref_cpp": ref,
         "lassu_cpp": lassu, "bemenet_py": bemenet, "hibak": hibak}
    t.update(felul)
    return t


def matek_tetel(**felul):
    t = {"tema": "algebra", "szoveg": "Solve over the real numbers: $x^2-5x+6=0$. Give all solutions.",
         "vart": {"tipus": "halmaz", "ertekek": ["2", "3"]}}
    t.update(felul)
    return t


def demo_tetel(**felul):
    t = {"ut": "Mathematics/Probability basics.md",
         "szoveg": "---\ntags:\n  - math/probability\nlevel: 2\n---\n\n# Probability basics\n\nThe probability of an event is a number between "
                   "0 and 1. For a fair die, the chance of rolling a six is $\\frac{1}{6}$. When two events cannot happen together, "
                   "their probabilities add up. The complement of an event has probability $1 - p$.\n\nSee also [[Logarithms]].\n\n#math/probability\n"}
    t.update(felul)
    return t


KIEG3 = kieg(elotte="The area of a square with side three is nine square ", utana=".", elf=["units"])


def opciok(gyoker, sablonok, **kw):
    return G.Opciok(sablonok=list(sablonok), gyoker=gyoker, **kw)


def futtat(gyoker, sablonok, szallito, **kw):
    sorok = []
    kod = G.futtat(opciok(gyoker, sablonok, **kw), szallito=szallito, kimenet=sorok.append)
    return kod, sorok


def futas_mappa_(gyoker):
    mappak = sorted((Path(gyoker) / G.KIMENET_GYOKER_REL).glob("2*"))
    assert len(mappak) == 1, mappak
    return mappak[0]


def jsonl(ut):
    return [json.loads(s) for s in Path(ut).read_text(encoding="utf-8").splitlines() if s.strip()]


def fa_szoveg(gyoker):
    return b"\n".join(p.read_bytes() for p in sorted(Path(gyoker).rglob("*")) if p.is_file() and ".git" not in p.parts)


# ---------------------------------------------------------------------------------------------------- key

class KulcsTest(HalozatTilosTest):
    def test_keychain_parancs_es_kulcs(self):
        hivott = []

        def hamis(argv, **kw):
            hivott.append(argv)
            return subprocess.CompletedProcess(argv, 0, KULCS + "\n", "")

        self.assertEqual(G.kulcs_olvas(False, futtat=hamis, kornyezet={"ANTHROPIC_API_KEY": "x" * 30}), KULCS)
        self.assertEqual(hivott, [["security", "find-generic-password", "-s", "manifold-anthropic", "-w"]])
        self.assertNotIn(KULCS, " ".join(hivott[0]))

    def test_env_csak_kifejezett_kapcsoloval(self):
        env = {"ANTHROPIC_API_KEY": KULCS}
        hianyzo = subprocess.CompletedProcess([], 44, "", "not found")
        with self.assertRaises(G.GenHiba) as m:                     # no switch: the environment is NOT consulted
            G.kulcs_olvas(False, futtat=lambda *a, **k: hianyzo, kornyezet=env)
        self.assertNotIn(KULCS, str(m.exception))
        self.assertEqual(G.kulcs_olvas(True, futtat=lambda *a, **k: self.fail("Keychain read"), kornyezet=env), KULCS)
        with self.assertRaises(G.GenHiba):
            G.kulcs_olvas(True, kornyezet={})

    def test_hibas_kulcs_nem_kerul_az_uzenetbe(self):
        rossz = "not a key\nwith spaces " + KULCS
        with self.assertRaises(G.GenHiba) as m:
            G.kulcs_olvas(True, kornyezet={"ANTHROPIC_API_KEY": rossz})
        self.assertNotIn(KULCS, str(m.exception))
        with self.assertRaises(G.GenHiba) as m:
            G.kulcs_olvas(False, futtat=lambda *a, **k: subprocess.CompletedProcess([], 0, rossz, ""))
        self.assertNotIn(KULCS, str(m.exception))

    def test_a_kulcs_sehol_nincs_a_kimenetben_sikeres_es_bukott_futasnal(self):
        nyers = json.dumps([kieg()])
        for nev, nyito in (("ok", self._ok_nyito(nyers)), ("401", self._hibas_nyito(401, KULCS)),
                           ("halozat", self._halozati_hiba_nyito()), ("500", self._hibas_nyito(500, KULCS))):
            with self.subTest(nev):
                gyoker = self.tmp / nev
                (gyoker / "var").mkdir(parents=True)
                kimenet, hiba = io.StringIO(), io.StringIO()
                sz = G.HttpSzallito(KULCS, nyito=nyito, alvas=lambda s: None)
                with redirect_stdout(kimenet), redirect_stderr(hiba):
                    kod, sorok = futtat(gyoker, ["kiegeszites"], sz)
                self.assertEqual(G.KILEPES_OK if nev == "ok" else G.KILEPES_HALOZAT, kod)
                self.assertNotIn(KULCS, "\n".join(sorok) + kimenet.getvalue() + hiba.getvalue())
                self.assertNotIn(KULCS.encode(), fa_szoveg(gyoker), "the key was written to a file")

    def test_kivetel_es_traceback_nem_tartalmazza_a_kulcsot(self):
        sz = G.HttpSzallito(KULCS, nyito=self._hibas_nyito(401, KULCS), alvas=lambda s: None)
        with self.assertRaises(G.SzallitoHiba) as m:
            sz.kuld("claude-haiku-5-5", "s", "u", 100)
        szoveg = "".join(traceback.format_exception(m.exception)) + str(m.exception) + repr(m.exception) + repr(sz)
        self.assertNotIn(KULCS, szoveg)
        sz = G.HttpSzallito(KULCS, nyito=self._halozati_hiba_nyito(), alvas=lambda s: None)
        with self.assertRaises(G.SzallitoHiba) as m:
            sz.kuld("claude-haiku-5-5", "s", "u", 100)
        self.assertNotIn(KULCS, "".join(traceback.format_exception(m.exception)))
        self.assertNotIn(KULCS, G.titkot_kiszed(f"the key {KULCS} leaked", KULCS))
        self.assertNotIn("api03", G.titkot_kiszed(f"the key {KULCS} leaked"))

    def test_main_nem_ir_tracebacket(self):
        hiba = io.StringIO()
        with mock.patch.object(G, "futtat", side_effect=RuntimeError(KULCS)), redirect_stderr(hiba), redirect_stdout(io.StringIO()):
            kod = G.main(["--szaraz"])
        self.assertEqual(kod, G.KILEPES_HIBA)
        self.assertNotIn(KULCS, hiba.getvalue())
        self.assertNotIn("Traceback", hiba.getvalue())

    # fake openers below the real HTTP layer
    @staticmethod
    def _ok_nyito(torzs):
        valasz_json = json.dumps({"content": [{"type": "text", "text": torzs}], "usage": {"input_tokens": 100, "output_tokens": 200},
                                  "stop_reason": "end_turn"}).encode()

        def nyito(kerelem, timeout=None):
            return _Valasz(valasz_json)

        return nyito

    @staticmethod
    def _hibas_nyito(kod, visszhang):
        def nyito(kerelem, timeout=None):
            raise urllib.error.HTTPError(kerelem.full_url, kod, "err", {}, io.BytesIO(
                json.dumps({"error": {"type": "authentication_error", "message": "bad key " + visszhang}}).encode()))

        return nyito

    @staticmethod
    def _halozati_hiba_nyito():
        def nyito(kerelem, timeout=None):
            raise urllib.error.URLError(f"unreachable while using {KULCS}")

        return nyito


class _Valasz:
    def __init__(self, torzs):
        self._b = io.BytesIO(torzs)

    def read(self, n=-1):
        return self._b.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


# ---------------------------------------------------------------------------------------------------- transport

class SzallitoTest(HalozatTilosTest):
    def _sz(self, nyito, alvasok=None):
        return G.HttpSzallito(KULCS, nyito=nyito, alvas=(alvasok.append if alvasok is not None else (lambda s: None)))

    def test_csak_a_fix_vegpont_a_kert_fejlecekkel(self):
        latott = []

        def nyito(kerelem, timeout=None):
            latott.append((kerelem, timeout))
            return _Valasz(json.dumps({"content": [{"type": "text", "text": "[]"}], "usage": {"input_tokens": 1, "output_tokens": 1}}).encode())

        v = self._sz(nyito).kuld("claude-haiku-5-5", "sys", "user", 321)
        (k, timeout), = latott
        self.assertEqual(k.full_url, "https://api.anthropic.com/v1/messages")
        self.assertEqual(k.get_method(), "POST")
        self.assertEqual(k.get_header("Anthropic-version"), G.API_VERSION)
        self.assertEqual(k.get_header("X-api-key"), KULCS)
        self.assertGreater(timeout, 0)
        body = json.loads(k.data)
        self.assertEqual((body["model"], body["max_tokens"], body["system"]), ("claude-haiku-5-5", 321, "sys"))
        self.assertEqual(v.usage, {"input_tokens": 1, "output_tokens": 1})

    def test_idegen_host_es_http_tilos(self):
        for url in ("https://evil.example/v1/messages", "http://api.anthropic.com/v1/messages", "https://api.anthropic.com.evil.example/v1/messages",
                    "https://api.anthropic.com:8443/v1/messages", "https://api.anthropic.com/v1/other"):
            with self.assertRaises(G.SzallitoHiba, msg=url):
                G.url_ellenoriz(url)
        G.url_ellenoriz(G.API_URL)
        self.assertIsNone(G._NincsAtiranyitas().redirect_request(None, None, 302, "Found", {}, "https://evil.example/"))
        self.assertEqual(G.API_HOST, "api.anthropic.com")

    def test_csak_claude_modell_ismert_arral(self):
        arak = G.arak_betolt()
        for jo in ("claude-haiku-5-5", "claude-sonnet-5-5"):
            self.assertEqual(G.modell_ellenoriz(jo, arak), jo)
        for rossz in ("gpt-4o", "haiku", "claude-", "Claude-haiku-5-5", "claude-haiku 5", "claude-x/../y", "", "claude-nincs-ar-9"):
            with self.assertRaises(G.GenHiba, msg=rossz):
                G.modell_ellenoriz(rossz, arak)
        with self.assertRaises(G.GenHiba):
            G.futtat(opciok(self.gyoker, ["kiegeszites"], modell_olcso="gpt-4o", szaraz=True), kimenet=lambda s: None)

    def test_ujraprobalas_exponencialis_es_korlatos(self):
        szamlalo, alvasok = [], []

        def nyito(kerelem, timeout=None):
            szamlalo.append(1)
            if len(szamlalo) <= 2:
                raise urllib.error.HTTPError(kerelem.full_url, 429 if len(szamlalo) == 1 else 529, "x", {}, io.BytesIO(b"{}"))
            return _Valasz(json.dumps({"content": [{"type": "text", "text": "ok"}], "usage": {}}).encode())

        v = self._sz(nyito, alvasok).kuld("claude-haiku-5-5", "s", "u", 10)
        self.assertEqual((v.szoveg, v.probak, alvasok), ("ok", 3, [1.0, 2.0]))
        for kod in (500, 503):                                     # always failing: 1 + 3 retries, then give up
            szamlalo.clear()
            alvasok.clear()

            def mindig(kerelem, timeout=None, kod=kod):
                szamlalo.append(1)
                raise urllib.error.HTTPError(kerelem.full_url, kod, "x", {}, io.BytesIO(b"{}"))

            with self.assertRaises(G.SzallitoHiba) as m:
                self._sz(mindig, alvasok).kuld("claude-haiku-5-5", "s", "u", 10)
            self.assertEqual(len(szamlalo), 1 + G.MAX_UJRA)
            self.assertEqual(alvasok, [1.0, 2.0, 4.0])
            self.assertFalse(m.exception.vegzetes)

    def test_retry_after_felso_korlattal(self):
        alvasok, n = [], []

        def nyito(kerelem, timeout=None):
            n.append(1)
            if len(n) == 1:
                raise urllib.error.HTTPError(kerelem.full_url, 429, "x", {"retry-after": "9999"}, io.BytesIO(b"{}"))
            return _Valasz(json.dumps({"content": [], "usage": {}}).encode())

        self._sz(nyito, alvasok).kuld("claude-haiku-5-5", "s", "u", 10)
        self.assertEqual(alvasok, [30.0])

    def test_kliens_hiba_nem_probalkozik_ujra(self):
        n = []

        def nyito(kerelem, timeout=None):
            n.append(1)
            raise urllib.error.HTTPError(kerelem.full_url, 400, "x", {}, io.BytesIO(b"{}"))

        with self.assertRaises(G.SzallitoHiba) as m:
            self._sz(nyito).kuld("claude-haiku-5-5", "s", "u", 10)
        self.assertEqual((len(n), m.exception.vegzetes), (1, True))

    def test_valasz_meretkorlat_es_ertelmetlen_valasz(self):
        with self.assertRaises(G.SzallitoHiba):
            self._sz(lambda k, timeout=None: _Valasz(b"x" * (G.MAX_VALASZ_BAJT + 10))).kuld("claude-haiku-5-5", "s", "u", 10)
        with self.assertRaises(G.SzallitoHiba):
            self._sz(lambda k, timeout=None: _Valasz(b"not json")).kuld("claude-haiku-5-5", "s", "u", 10)
        with self.assertRaises(G.SzallitoHiba):                     # oversize request: nothing is sent
            self._sz(lambda k, timeout=None: self.fail("sent")).kuld("claude-haiku-5-5", "s", "u" * (G.MAX_KERES_BAJT + 1), 10)


# ---------------------------------------------------------------------------------------------------- cost guard

class KoltsegTest(HalozatTilosTest):
    def test_a_legrosszabb_eset_kiszamitasa(self):
        ar = G.Ar(2.0, 10.0)
        self.assertAlmostEqual(G.legrosszabb_usd(ar, 1_000_000, 100_000), 2.0 + 1.0)
        self.assertAlmostEqual(G.tenyleges_usd(ar, {"input_tokens": 500_000, "output_tokens": 100_000,
                                                    "cache_read_input_tokens": 500_000}), 2.0 + 1.0)
        self.assertGreaterEqual(G.bemenet_becsles("a" * 1000, "b" * 1000), 1000)

    def test_megall_a_limitnel_es_a_koltsegfajl_megmarad(self):
        sz = HamisSzallito([valasz(json.dumps([kieg()]))])
        kod, sorok = futtat(self.gyoker, ["kiegeszites"], sz, max_usd=0.07)
        self.assertEqual((kod, len(sz.hivasok)), (G.KILEPES_KOLTSEG, 2))          # 0.022 + 0.022 spent, the third would not fit
        self.assertTrue(any("cost guard" in s for s in sorok))
        k = json.loads((futas_mappa_(self.gyoker) / "koltseg.json").read_text())
        self.assertAlmostEqual(k["osszeg_usd"], 0.044, places=6)
        self.assertEqual((k["hivasok"], k["fuggo_usd"], k["bemenet_tok"], k["kimenet_tok"]), (2, 0.0, 2000, 4000))
        self.assertLessEqual(k["osszeg_usd"], 0.07)

    def test_a_legrosszabb_eset_a_hivas_elott_ellenorzodik(self):
        sz = HamisSzallito([valasz("[]")])
        kod, _ = futtat(self.gyoker, ["kiegeszites"], sz, max_usd=0.01)           # worst case ~0.032 > 0.01: nothing is called
        self.assertEqual((kod, sz.hivasok), (G.KILEPES_KOLTSEG, []))

    def test_hivasszam_korlat(self):
        sz = HamisSzallito([valasz("[]", 10, 10)])
        kod, _ = futtat(self.gyoker, ["kiegeszites"], sz, max_hivas=2)
        self.assertEqual((kod, len(sz.hivasok)), (G.KILEPES_KOLTSEG, 2))

    def test_osszeomlas_utan_is_latszik_a_koltseg_es_a_foglalas(self):
        def terv(i, h):
            if i == 0:
                return valasz("[]")
            raise RuntimeError("the process died")

        sz = HamisSzallito(terv)
        with self.assertRaises(RuntimeError):
            futtat(self.gyoker, ["kiegeszites"], sz)
        k = json.loads((futas_mappa_(self.gyoker) / "koltseg.json").read_text())
        self.assertAlmostEqual(k["osszeg_usd"], 0.022, places=6)
        self.assertGreater(k["fuggo_usd"], 0.02)                                   # the interrupted call stays reserved
        osszes = json.loads((self.gyoker / G.KIMENET_GYOKER_REL / "osszes_koltseg.json").read_text())
        self.assertAlmostEqual(osszes["osszeg_usd"], 0.022, places=6)
        self.assertGreater(osszes["fuggo_usd"], 0.02)
        self.assertIn(G._ma(), osszes["napok"])
        self.assertTrue((futas_mappa_(self.gyoker) / "manifest.json").is_file())

    def test_hiba_utan_a_foglalas_felszabadul(self):
        sz = HamisSzallito([G.SzallitoHiba("down", True)])
        kod, _ = futtat(self.gyoker, ["kiegeszites"], sz)
        self.assertEqual(kod, G.KILEPES_HALOZAT)
        k = json.loads((futas_mappa_(self.gyoker) / "koltseg.json").read_text())
        self.assertEqual((k["osszeg_usd"], k["fuggo_usd"]), (0.0, 0.0))

    def test_usage_nelkuli_valasz_a_legrosszabb_esetet_terheli(self):
        sz = HamisSzallito([G.Valasz("[]", None)])
        futtat(self.gyoker, ["kiegeszites"], sz, max_hivas=1)
        k = json.loads((futas_mappa_(self.gyoker) / "koltseg.json").read_text())
        self.assertGreater(k["osszeg_usd"], 0.03)

    def test_osszesitett_plafon_ismetelt_futasokon_at(self):
        osszes = self.gyoker / G.KIMENET_GYOKER_REL / "osszes_koltseg.json"
        osszes.parent.mkdir(parents=True)
        osszes.write_text(json.dumps({"osszeg_usd": 19.99, "fuggo_usd": 0.0, "napok": {}}))
        sz = HamisSzallito([valasz("[]")])
        kod, sorok = futtat(self.gyoker, ["kiegeszites"], sz)
        self.assertEqual((kod, sz.hivasok), (G.KILEPES_KOLTSEG, []))
        self.assertTrue(any("lifetime" in s for s in sorok))
        # repeated small runs add up until the cap stops them
        osszes.write_text(json.dumps({"osszeg_usd": 0.0, "fuggo_usd": 0.0, "napok": {}}))
        hivasok = 0
        for i in range(10):
            sz = HamisSzallito([valasz("[]")])
            kod, _ = futtat(self.gyoker, ["kiegeszites"], sz, futas_id=f"f{i}", max_usd=1.0, osszes_max_usd=0.07)
            hivasok += len(sz.hivasok)
        self.assertEqual(hivasok, 2)
        self.assertLessEqual(json.loads(osszes.read_text())["osszeg_usd"], 0.07)

    def test_serult_osszesito_fajlt_nem_nullazza(self):
        osszes = self.gyoker / G.KIMENET_GYOKER_REL / "osszes_koltseg.json"
        osszes.parent.mkdir(parents=True)
        osszes.write_text("{broken")
        sz = HamisSzallito([valasz("[]")])
        kod, _ = futtat(self.gyoker, ["kiegeszites"], sz)
        self.assertEqual((kod, sz.hivasok), (G.KILEPES_KOLTSEG, []))
        self.assertEqual(osszes.read_text(), "{broken")

    def test_szaraz_futas_nem_hiv_halozatot_nem_olvas_kulcsot_es_nem_ir(self):
        with mock.patch.object(G, "kulcs_olvas", side_effect=AssertionError("key read")), \
                mock.patch.object(G, "HttpSzallito", side_effect=AssertionError("transport built")):
            kod, sorok = futtat(self.gyoker, [], None, szaraz=True)
        self.assertEqual(kod, G.KILEPES_OK)
        self.assertTrue(any(s.startswith("plan: 24 call(s)") for s in sorok), sorok)
        self.assertTrue(any("dry run" in s for s in sorok))
        self.assertFalse((self.gyoker / G.KIMENET_GYOKER_REL).exists())
        kod, sorok = futtat(self.gyoker, [], None, szaraz=True, max_usd=0.5)
        self.assertEqual(kod, G.KILEPES_KOLTSEG)
        self.assertTrue(any("does NOT fit" in s for s in sorok))

    def test_az_alapterv_belefer_az_alapertelmezett_keretbe(self):
        arak, sablonok = G.arak_betolt(), G.sablonok_betolt()
        t = G.terv(G.Opciok(gyoker=self.gyoker), sablonok, arak)
        self.assertEqual(t["hivasok"], 24)
        self.assertTrue(t["belefer"])
        self.assertLess(t["legrosszabb_usd"], G.ALAP_MAX_USD)
        self.assertNotIn("doku_atnezes", [s["sablon"] for s in t["sablonok"]])        # optional: only on request


# ---------------------------------------------------------------------------------------------------- filters

class SzuroTest(HalozatTilosTest):
    def ctx(self, **kw):
        return G.Kontextus(gyoker=self.gyoker, **kw)

    def elutasit(self, cel, tetel, **kw):
        with self.assertRaises(G.Elutasit) as m:
            G.tetel_ellenoriz(cel, tetel, self.ctx(**kw))
        return str(m.exception)

    def test_jo_tetelek_atmennek(self):
        for cel, t in (("kiegeszites", kieg()), ("matek", matek_tetel()), ("kod", kod_tetel()), ("demo", demo_tetel())):
            with self.subTest(cel):
                tiszta = G.tetel_ellenoriz(cel, t, self.ctx())
                self.assertTrue(G.tetel_azon(cel, tiszta).startswith(cel + "-"))

    def test_kiegeszites_sema(self):
        self.assertIn("schema", self.elutasit("kiegeszites", {"elotte": "x" * 20}))
        self.assertIn("schema", self.elutasit("kiegeszites", {**kieg(), "extra": 1}))
        self.assertIn("schema", self.elutasit("kiegeszites", kieg(elf=[])))
        self.assertIn("schema", self.elutasit("kiegeszites", kieg(elf=["a", "a"])))
        self.assertIn("schema", self.elutasit("kiegeszites", "not an object"))
        self.assertIn("size", self.elutasit("kiegeszites", kieg(elotte="word " * 80)))
        self.assertIn("context", self.elutasit("kiegeszites", kieg(elotte="The answer is sea level and nothing else here ", elf=["sea level"])))

    def test_titok_szemelyes_ut_url_szuro(self):
        for nev, elotte in (("secret:sk_kulcs", f"The token is {KULCS} here, remember it "), ("secret:huggingface", f"Use {MASIK_TITOK} as the token "),
                            ("personal:email", "Write to someone@example.org for details about "),
                            ("personal:url", "See https://example.org/page for the details of "),
                            ("personal:ut", "The file lives in /Users/someone/Documents and "),
                            ("personal:ut", "The data is stored in /home/someone/data and "),
                            ("personal:telefon", "Call +36 30 123 4567 about the "),
                            ("personal:ip", "The server answers on 192.168.10.20 for the ")):
            with self.subTest(nev):
                self.assertEqual(self.elutasit("kiegeszites", kieg(elotte=elotte)), nev)
        self.assertEqual(self.elutasit("demo", demo_tetel(szoveg=demo_tetel()["szoveg"] + "\nMail: a.b@example.com\n")), "personal:email")
        k = kod_tetel()
        k["lassu_cpp"] = k["lassu_cpp"] + "// /Users/someone/x\n"
        self.assertEqual(self.elutasit("kod", k), "personal:ut")

    def test_nyelv(self):
        self.assertIn("language", self.elutasit("kiegeszites", kieg(elotte="A viz forrpontja tengerszinten száz fok ")))
        self.assertIn("language", self.elutasit("kiegeszites", kieg(elf=["száz"])))
        self.assertIn("language", self.elutasit("matek", matek_tetel(szoveg="Oldd meg a valós számok halmazán: $x^2-5x+6=0$ egyenletet.")))
        self.assertIn("language", self.elutasit("matek", matek_tetel(szoveg="Oldd meg hogy egy feladat nem kell: $x^2-5x+6=0$ egyenlet")))
        self.assertIsNone(G.angol_e("The sum of the angles of a triangle is one hundred and eighty degrees."))
        self.assertIsNone(G.angol_e("Solve $x^2 = 4$."))
        self.assertIsNotNone(G.angol_e("Hello café"))

    def test_matek_sema(self):
        self.assertIn("topic", self.elutasit("matek", matek_tetel(tema="cooking")))
        self.assertIn("answer type", self.elutasit("matek", matek_tetel(vart={"tipus": "essay", "ertek": "1"})))
        self.assertIn("machine syntax", self.elutasit("matek", matek_tetel(vart={"tipus": "szam", "ertek": "\\frac{1}{2}"})))
        self.assertIn("schema", self.elutasit("matek", matek_tetel(vart={"tipus": "szam"})))
        self.assertIn("schema", self.elutasit("matek", matek_tetel(vart={"tipus": "par", "ertekek": {"x": "1"}})))
        self.assertIn("balanced", self.elutasit("matek", matek_tetel(szoveg="Solve the equation $x^2 - 5x + 6 = 0 over the reals.")))
        G.tetel_ellenoriz("matek", matek_tetel(vart={"tipus": "intervallum", "ertek": "[5, 6)"}), self.ctx())
        G.tetel_ellenoriz("matek", matek_tetel(vart={"tipus": "par", "ertekek": {"x": "10", "y": "7"}}), self.ctx())

    def test_matek_onellenorzes_sympyval_ha_van(self):
        try:
            sys.path.insert(0, str(REPO / "modulok" / "eval"))
            from kozos import matek
        except Exception:                                           # noqa: BLE001
            self.skipTest("[indokolt] no sympy in this interpreter: the syntax-only path is covered above")
        finally:
            sys.path.remove(str(REPO / "modulok" / "eval"))
        ctx = self.ctx(matek=matek)
        G.tetel_ellenoriz("matek", matek_tetel(), ctx)
        self.assertIn("schema", self.elutasit("matek", matek_tetel(vart={"tipus": "szam", "ertek": "2 3 +"}), matek=matek))

    def test_kod_sema_es_biztonsag(self):
        self.assertIn("main()", self.elutasit("kod", kod_tetel(ref_cpp="int x;" * 30)))
        k = kod_tetel()
        k["hibak"][0]["eredeti"] = "    long long s = 7;"
        self.assertIn("not `eredeti`", self.elutasit("kod", k))
        k = kod_tetel()
        k["hibak"][1].update(sor=7, eredeti="    long long s = 0;", csere="    long long s = 2;")
        self.assertIn("different lines", self.elutasit("kod", k))
        k = kod_tetel()
        k["hibak"][2]["csere"] = k["hibak"][2]["eredeti"]
        self.assertIn("replacement", self.elutasit("kod", k))
        self.assertIn("three", self.elutasit("kod", {**kod_tetel(), "hibak": kod_tetel()["hibak"][:2]}))
        self.assertIn("```teszt", self.elutasit("kod", kod_tetel(leiras_md="# Title\n\n" + "A long enough statement without examples. " * 8)))
        for forras in ("#include <fstream>\n" + kod_tetel()["ref_cpp"], kod_tetel()["ref_cpp"].replace("return 0;", "system(\"ls\"); return 0;"),
                       kod_tetel()["ref_cpp"].replace("int n;", "int n; FILE* f = fopen(\"a\", \"r\");")):
            self.assertIn("forbidden", self.elutasit("kod", kod_tetel(ref_cpp=forras)))
        for py in ("import os\n" + kod_tetel()["bemenet_py"], kod_tetel()["bemenet_py"].replace("rng.randint(1, 6)", "open('x').read()"),
                   "def general(rng, meret):\n    return __import__('os').getcwd()\n\n\ndef ervenyes(s):\n    return True\n",
                   "def general(rng):\n    return '1'\n\n\ndef ervenyes(s):\n    return True\n", "def general(:\n" + "x = 1\n" * 12):
            self.assertRegex(self.elutasit("kod", kod_tetel(bemenet_py=py)), "safety|schema")

    def test_demo_sema_es_ismetlodes(self):
        self.assertIn("schema", self.elutasit("demo", demo_tetel(ut="../etc/passwd.md")))
        self.assertIn("schema", self.elutasit("demo", demo_tetel(ut="Mathematics/Deep/Nested.md")))
        self.assertIn("schema", self.elutasit("demo", demo_tetel(szoveg="x" * 400)))
        self.assertIn("schema", self.elutasit("demo", demo_tetel(szoveg=demo_tetel()["szoveg"] + "![[image.png]]")))
        self.assertIn("duplicate", self.elutasit("demo", demo_tetel(), demo_utak=frozenset({"Mathematics/Probability basics.md"})))
        self.assertIn("duplicate", self.elutasit("demo", demo_tetel(), demo_cimek=frozenset({"probability basics"})))
        t = G.tetel_ellenoriz("demo", demo_tetel(), self.ctx(demo_cimek=frozenset({"geometric series"})))
        self.assertTrue(any("Logarithms" in f for f in t.figyelmeztetes))

    def test_json_kinyeres_csonka_valaszbol(self):
        a, b = json.dumps(kieg()), json.dumps(kieg(elotte="The chemical symbol for the element oxygen is the letter "))
        self.assertEqual(len(G.json_tombbol(f"[{a}, {b}]")), 2)
        self.assertEqual(len(G.json_tombbol(f"```json\n[{a}, {b}]\n```")), 2)
        self.assertEqual(len(G.json_tombbol(f"[{a}, {b[:40]}")), 1)               # truncated: the complete object is kept
        self.assertEqual(G.json_tombbol("no json here"), [])
        self.assertEqual(len(G.json_tombbol(json.dumps({"items": [kieg()]}))), 1)

    def test_a_tool_szuroi_megegyeznek_a_repo_titokkeresojevel(self):
        from tests.biztonsag.test_titok_es_ut import TITOK_MINTAK
        self.assertEqual(G.TITOK_MINTAK, TITOK_MINTAK)


class FuttatasTest(HalozatTilosTest):
    def test_kimenet_szuro_dedup_manifest(self):
        jo, jo2 = kieg(), kieg(elotte="The chemical symbol for the element oxygen is the letter ", utana=".", elf=["O"])
        elso = [jo, kieg(elotte="WATER boils at one hundred degrees celsius at sea ", utana=" pressure!"), jo2,
                kieg(elotte="Write to someone@example.org about the ", elf=["x"]), {"elotte": "x"}, kieg(elotte="A víz forráspontja száz fok "),
                kieg(elotte=f"The key {KULCS} is used for the ", elf=["x"])]
        masodik = [jo2, KIEG3]
        sz = HamisSzallito([valasz(json.dumps(elso)), valasz(json.dumps(masodik)), valasz("this is not json at all")])
        kod, sorok = futtat(self.gyoker, ["kiegeszites"], sz, max_hivas=3)
        self.assertEqual(kod, G.KILEPES_KOLTSEG)                                   # 3 calls allowed, the 4th template call is refused
        mappa = futas_mappa_(self.gyoker)
        tetelek, elutasitott = jsonl(mappa / "tetelek.jsonl"), jsonl(mappa / "elutasitott.jsonl")
        self.assertEqual(len(tetelek), 3)
        ok = [e["ok"] for e in elutasitott]
        self.assertEqual(sorted(o.split(":")[0] for o in ok), sorted(["duplicate", "duplicate", "personal", "schema", "language", "secret"]))
        self.assertTrue(all("reszlet" in e for e in elutasitott))
        self.assertNotIn(KULCS, (mappa / "elutasitott.jsonl").read_text())          # a secret-shaped string is masked in the detail
        self.assertEqual(len({t["azonosito"] for t in tetelek}), 3)
        jov = tomllib.loads((mappa / "jovahagyas.toml").read_text())
        self.assertEqual([x["id"] for x in jov["tetel"]], [t["azonosito"] for t in tetelek])
        self.assertTrue(all(x["jovahagyva"] is False for x in jov["tetel"]))
        m = json.loads((mappa / "manifest.json").read_text())
        self.assertEqual(m["tetelek"], [t["azonosito"] for t in tetelek])
        self.assertEqual(m["sablonok"]["kiegeszites"]["sha256"], G.fajl_sha256(G.SABLON_MAPPA / "kiegeszites.toml"))
        self.assertEqual(m["sablonok"]["kiegeszites"]["hibas_valasz"], 1)
        self.assertEqual(m["modellek"], {"olcso": "claude-haiku-5-5", "minoseg": "claude-sonnet-5-5"})
        self.assertEqual((m["koltseg"]["bemenet_tok"], m["koltseg"]["kimenet_tok"]), (3000, 6000))
        self.assertEqual(m["elutasitott_db"], len(elutasitott))
        self.assertIn("stopped by the cost guard", m["allapot"])

    def test_modellvalasztas_osztaly_szerint(self):
        sz = HamisSzallito([valasz("[]", 10, 10)])
        futtat(self.gyoker, ["kiegeszites", "matek"], sz, modell_olcso="claude-haiku-5-5", modell_minoseg="claude-sonnet-5-5", max_hivas=5)
        self.assertEqual([h["modell"] for h in sz.hivasok], ["claude-haiku-5-5"] * 4 + ["claude-sonnet-5-5"])

    def test_a_kerelem_csak_sablon_szoveget_tartalmaz_es_a_tiltasokat(self):
        sz = HamisSzallito([valasz("[]", 10, 10)])
        futtat(self.gyoker, ["matek"], sz, max_hivas=1)
        h = sz.hivasok[0]
        self.assertIn("Hard rules", h["rendszer"])
        self.assertIn("no real person", h["rendszer"])
        self.assertNotIn("<<", h["rendszer"] + h["felhasznalo"])
        self.assertEqual(G.tilos_talalat(h["rendszer"] + h["felhasznalo"]), None)

    def test_csak_a_staging_ala_ir(self):
        sz = HamisSzallito([valasz(json.dumps([kieg()]), 10, 10)])
        futtat(self.gyoker, ["kiegeszites"], sz, max_hivas=1)
        for p in self.gyoker.rglob("*"):
            if p.is_file():
                self.assertTrue(str(p.relative_to(self.gyoker)).startswith(str(G.KIMENET_GYOKER_REL) + "/"), p)

    def test_futas_id_utvonal_kenyszer(self):
        for rossz in ("../x", "a/b", "..", ".", "", ".hidden", "x" * 80, "a\\b", "/etc/passwd", "a b", "x\n", "..\\..\\x"):
            with self.subTest(rossz):
                with self.assertRaises(G.GenHiba):
                    G.futas_mappa(self.gyoker, rossz)
                with self.assertRaises(G.GenHiba):
                    futtat(self.gyoker, ["kiegeszites"], HamisSzallito([valasz("[]")]), futas_id=rossz)
        (self.gyoker / G.KIMENET_GYOKER_REL).mkdir(parents=True)
        (self.tmp / "kivul").mkdir()
        (self.gyoker / G.KIMENET_GYOKER_REL / "link").symlink_to(self.tmp / "kivul")
        with self.assertRaises(G.GenHiba):
            G.futas_mappa(self.gyoker, "link", letezik=True)
        (self.gyoker / G.KIMENET_GYOKER_REL / "van").mkdir()
        with self.assertRaises(G.GenHiba):                                           # no silent reuse of a run folder
            futtat(self.gyoker, ["kiegeszites"], HamisSzallito([valasz("[]")]), futas_id="van")
        self.assertEqual(list((self.tmp / "kivul").iterdir()), [])

    def test_doku_csak_a_repo_oldalait_kuldi_es_nem_modositja(self):
        doku = self.gyoker / "docs" / "user"
        doku.mkdir(parents=True)
        (doku / "ALPHA.md").write_text("# Alpha\n\nOpen a note with the quick switcher.\n")
        (doku / "BETA.md").write_text(f"# Beta\n\nContact me at someone@example.org with {KULCS}\n")
        (doku / "lower.md").write_text("# Skipped by name\n")
        elotte = {p.name: p.read_bytes() for p in doku.iterdir()}
        mod = [{"oldal": "WRONG.md", "tipus": "typo", "hely": "Open a note", "javaslat": "Consider saying 'Open a note' with a verb first."},
               {"oldal": "ALPHA.md", "tipus": "invented", "hely": "x", "javaslat": "A remark with an unknown type should be dropped."}]
        sz = HamisSzallito([valasz(json.dumps(mod), 10, 10)])
        kod, _ = futtat(self.gyoker, ["doku_atnezes"], sz)
        self.assertEqual(kod, G.KILEPES_OK)
        self.assertEqual(len(sz.hivasok), 1)                                         # BETA (secret-shaped) and lower.md were not sent
        self.assertIn("ALPHA.md", sz.hivasok[0]["felhasznalo"])
        self.assertNotIn("someone@example.org", sz.hivasok[0]["felhasznalo"])
        mappa = futas_mappa_(self.gyoker)
        tetelek = jsonl(mappa / "tetelek.jsonl")
        self.assertEqual([t["tetel"]["oldal"] for t in tetelek], ["ALPHA.md"])       # the page comes from the request
        self.assertTrue((mappa / "doku_jelentes.md").is_file())
        self.assertEqual({p.name: p.read_bytes() for p in doku.iterdir()}, elotte)
        with self.assertRaises(G.GenHiba):                                            # suggestions are not adoptable
            G.atvesz(mappa.name, "doku", gyoker=self.gyoker)

    def test_sablonok_ervenyesek(self):
        s = G.sablonok_betolt()
        self.assertEqual(sorted(s), ["demo_jegyzetek", "doku_atnezes", "kiegeszites", "kod", "matek"])
        self.assertEqual({x.cel for x in s.values()}, set(G.CELOK))
        self.assertEqual([n for n, x in s.items() if not x.alapertelmezett], ["doku_atnezes"])
        for x in s.values():
            self.assertIsNone(G.tilos_talalat(x.rendszer + x.felhasznalo), x.nev)
            self.assertIsNone(G.nem_angol_ok(x.rendszer + x.felhasznalo), x.nev)
            self.assertLessEqual(x.max_tokens, 16000)


# ---------------------------------------------------------------------------------------------------- adoption

def git_init(ut):
    subprocess.run(["git", "init", "-q", str(ut)], check=True, capture_output=True)


class AtvetelTest(HalozatTilosTest):
    def setUp(self):
        super().setUp()
        git_init(self.gyoker)
        for r in ("modulok/eval/kiegeszites", "modulok/eval/matek", "modulok/eval/kod", "core"):
            (self.gyoker / r).mkdir(parents=True, exist_ok=True)
        (self.gyoker / "modulok/eval/kiegeszites/arany.json").write_text('{"verzio": "cx-1", "allapot": "vazlat", "tetel": []}')
        (self.gyoker / "modulok/eval/csomag.toml").write_text('[halmaz.matek]\nmappa = "matek"\nellenorizni = "licence"\n')
        self.elemek = [kieg(), kieg(elotte="The chemical symbol for the element oxygen is the letter ", utana=".", elf=["O"]),
                       KIEG3]
        self.futas = self.uj_futas("f1", ["kiegeszites"], [self.elemek])

    def uj_futas(self, futas_id, sablonok, valaszok):
        sz = HamisSzallito([valasz(json.dumps(v), 10, 10) for v in valaszok])
        kod, _ = futtat(self.gyoker, sablonok, sz, futas_id=futas_id, max_hivas=len(valaszok))
        self.assertIn(kod, (G.KILEPES_OK, G.KILEPES_KOLTSEG))
        return futas_id

    def jovahagy(self, futas, db):
        ut = self.gyoker / G.KIMENET_GYOKER_REL / futas / "jovahagyas.toml"
        szoveg = ut.read_text()
        for _ in range(db):
            szoveg = szoveg.replace("jovahagyva = false", "jovahagyva = true", 1)
        ut.write_text(szoveg)

    def atvesz(self, futas, cel="kiegeszites", **kw):
        sorok = []
        kod = G.atvesz(futas, cel, gyoker=self.gyoker, kimenet=sorok.append, **kw)
        return kod, sorok

    CEL = "modulok/eval/kiegeszites/arany_en.json"

    def test_jovahagyas_nelkul_nem_ir(self):
        kod, sorok = self.atvesz(self.futas)
        self.assertEqual(kod, G.KILEPES_OK)
        self.assertFalse((self.gyoker / self.CEL).exists())
        self.assertTrue(any("nothing approved" in s for s in sorok))

    def test_csak_a_jovahagyottat_veszi_at_es_az_allapotot_nem_valtoztatja(self):
        elotte_fajlok = sorted(str(p.relative_to(self.gyoker)) for p in self.gyoker.rglob("*")
                               if p.is_file() and ".git" not in p.parts and "var" not in p.parts)
        self.jovahagy(self.futas, 1)
        jov_szoveg = (self.gyoker / G.KIMENET_GYOKER_REL / self.futas / "jovahagyas.toml").read_text()
        kod, sorok = self.atvesz(self.futas)
        self.assertEqual(kod, G.KILEPES_OK)
        d = json.loads((self.gyoker / self.CEL).read_text())
        self.assertEqual((d["verzio"], d["allapot"], d["jovahagyva"], d["nyelv"], d["jelolt_futasok"]), ("gen-1", "vazlat", None, "en", ["f1"]))
        self.assertEqual(len(d["tetel"]), 1)
        bejovo = tomllib.loads(jov_szoveg)["tetel"]
        self.assertEqual(d["tetel"][0]["id"], "sy-" + bejovo[0]["id"].split("-", 1)[1])
        self.assertEqual(set(d["tetel"][0]), {"id", "elotte", "utana", "elfogadhato"})
        from core.modell import aranycsomag
        self.assertTrue(set(aranycsomag.SAJAT_FELADATOK["kiegeszites"]) <= set(d["tetel"][0]))   # the shipped format
        self.assertTrue(any("state stays 'vazlat'" in s for s in sorok))
        # nothing else changed: the shipped set files and the approval/licence markers are byte-identical
        self.assertEqual((self.gyoker / "modulok/eval/csomag.toml").read_text(), '[halmaz.matek]\nmappa = "matek"\nellenorizni = "licence"\n')
        self.assertEqual(json.loads((self.gyoker / "modulok/eval/kiegeszites/arany.json").read_text())["allapot"], "vazlat")
        self.assertEqual(elotte_fajlok, sorted(str(p.relative_to(self.gyoker)) for p in self.gyoker.rglob("*") if p.is_file()
                                              and ".git" not in p.parts and "var" not in p.parts and p.name != "arany_en.json"))

    def test_masodik_atvetel_hozzafuz_duplikatum_nelkul_es_megorzi_az_allapotot(self):
        self.jovahagy(self.futas, 2)
        self.atvesz(self.futas)
        ut = self.gyoker / self.CEL
        d = json.loads(ut.read_text())
        d["jovahagyva"] = None
        d["megjegyzes"] = "kept"
        ut.write_text(json.dumps(d))
        subprocess.run(["git", "-C", str(self.gyoker), "add", "-A"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.gyoker), "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", "x"],
                       check=True, capture_output=True)
        masik = self.uj_futas("f2", ["kiegeszites"], [self.elemek[1:] + [kieg(elotte="The boiling point of water in kelvin is about ", utana=".", elf=["373"])]])
        self.jovahagy(masik, 2)
        kod, _ = self.atvesz(masik)
        d = json.loads(ut.read_text())
        self.assertEqual((d["verzio"], d["allapot"], d["megjegyzes"], d["jelolt_futasok"]), ("gen-2", "vazlat", "kept", ["f1", "f2"]))
        self.assertEqual(len(d["tetel"]), 3)                                          # two earlier + one new (the repeated item is skipped)
        self.assertEqual(len({t["id"] for t in d["tetel"]}), 3)

    def test_jovahagyott_celhalmazt_nem_modosit(self):
        self.jovahagy(self.futas, 1)
        ut = self.gyoker / self.CEL
        ut.write_text(json.dumps({"verzio": "gen-4", "allapot": "jovahagyott", "jovahagyva": "2026-01-01", "tetel": []}))
        elotte = ut.read_bytes()
        with self.assertRaises(G.GenHiba) as m:
            self.atvesz(self.futas)
        self.assertIn("not a draft", str(m.exception))
        self.assertEqual(ut.read_bytes(), elotte)

    def test_nem_tiszta_celnal_nem_ir(self):
        self.jovahagy(self.futas, 1)
        ut = self.gyoker / self.CEL
        ut.write_text(json.dumps({"verzio": "gen-1", "allapot": "vazlat", "jovahagyva": None, "tetel": []}))   # untracked = not clean
        elotte = ut.read_bytes()
        with self.assertRaises(G.GenHiba) as m:
            self.atvesz(self.futas)
        self.assertIn("not clean", str(m.exception))
        self.assertEqual(ut.read_bytes(), elotte)
        ut.unlink()
        # git unavailable / not a checkout (the check says "not clean"): also refused
        with self.assertRaises(G.GenHiba):
            G.atvesz(self.futas, "kiegeszites", mind=True, gyoker=self.gyoker, tiszta_e=lambda g, r: False)
        self.assertFalse(ut.exists())

    def test_validacios_hiba_eseten_semmi_sem_irodik(self):
        self.jovahagy(self.futas, 3)
        tj = self.gyoker / G.KIMENET_GYOKER_REL / self.futas / "tetelek.jsonl"
        sorok = jsonl(tj)
        sorok[1]["tetel"]["elotte"] = "Write to someone@example.org about the "           # hand-edited after generation
        tj.write_text("\n".join(json.dumps(s) for s in sorok) + "\n")
        with self.assertRaises(G.GenHiba) as m:
            self.atvesz(self.futas)
        self.assertIn("validation failed", str(m.exception))
        self.assertFalse((self.gyoker / self.CEL).exists())
        sorok[1]["tetel"] = self.elemek[1]                                              # valid again but identifier mismatch
        sorok[1]["tetel"]["elotte"] = "The chemical symbol for the element nitrogen is the letter "
        tj.write_text("\n".join(json.dumps(s) for s in sorok) + "\n")
        with self.assertRaises(G.GenHiba):
            self.atvesz(self.futas)
        self.assertFalse((self.gyoker / self.CEL).exists())

    def test_ismeretlen_azonosito_a_jovahagyo_fajlban(self):
        ut = self.gyoker / G.KIMENET_GYOKER_REL / self.futas / "jovahagyas.toml"
        ut.write_text(ut.read_text() + '\n[[tetel]]\nid = "kiegeszites-ffffffffff"\ncel = "kiegeszites"\njovahagyva = true\nosszegzes = "x"\n')
        with self.assertRaises(G.GenHiba):
            self.atvesz(self.futas)
        ut.write_text("[[tetel]]\nid = 5\n")
        with self.assertRaises(G.GenHiba):
            self.atvesz(self.futas)

    def test_mind_jovahagy_es_szaraz(self):
        kod, sorok = self.atvesz(self.futas, mind=True, szaraz=True)
        self.assertEqual(kod, G.KILEPES_OK)
        self.assertFalse((self.gyoker / self.CEL).exists())
        self.assertTrue(any("dry run" in s for s in sorok))
        self.assertTrue(any("approved: 3" in s for s in sorok))
        self.atvesz(self.futas, mind=True)
        self.assertEqual(len(json.loads((self.gyoker / self.CEL).read_text())["tetel"]), 3)
        self.assertTrue((self.gyoker / G.KIMENET_GYOKER_REL / self.futas / "atvett.json").is_file())

    def test_cel_szuro_es_utvonal(self):
        for rossz in ("doku", "nincs", "../x", ""):
            with self.assertRaises(G.GenHiba):
                G.atvesz(self.futas, rossz, gyoker=self.gyoker)
        with self.assertRaises(G.GenHiba):
            G.atvesz("../f1", "kiegeszites", gyoker=self.gyoker)
        with self.assertRaises(G.GenHiba):
            G.atvesz("nincs", "kiegeszites", gyoker=self.gyoker)
        kod, _ = self.atvesz(self.futas, "matek", mind=True)                       # other target: no item of this run belongs to it
        self.assertEqual(kod, G.KILEPES_OK)
        self.assertFalse((self.gyoker / "modulok/eval/matek/arany_en.json").exists())

    def test_matek_kod_es_demo_celhelyek(self):
        futas = self.uj_futas("f3", ["matek"], [[matek_tetel()]])
        self.assertEqual(self.atvesz(futas, "matek", mind=True)[0], G.KILEPES_OK)
        m = json.loads((self.gyoker / "modulok/eval/matek/arany_en.json").read_text())
        self.assertEqual((m["allapot"], len(m["feladatok"]), m["feladatok"][0]["vart"]["tipus"]), ("vazlat", 1, "halmaz"))
        self.assertEqual(self.atvesz(self.uj_futas("f4", ["kod"], [[kod_tetel()]]), "kod", mind=True)[0], G.KILEPES_OK)
        k = json.loads((self.gyoker / "modulok/eval/kod/arany_en.json").read_text())
        self.assertEqual((k["allapot"], len(k["feladatok"][0]["hibak"])), ("vazlat", 3))
        self.assertEqual(self.atvesz(self.uj_futas("f5", ["demo_jegyzetek"], [[demo_tetel()]]), "demo", mind=True)[0], G.KILEPES_OK)
        self.assertEqual(json.loads((self.gyoker / "core/demo_kiegeszito.json").read_text())["allapot"], "vazlat")


# ---------------------------------------------------------------------------------------------------- repository wiring

class CsomagEsRepoTest(unittest.TestCase):
    def test_a_tools_mappa_nem_kerul_a_csomagba(self):
        csomag = REPO / "packaging"
        if str(csomag) not in sys.path:
            sys.path.insert(0, str(csomag))
        import csomag_kozos
        import csomag_tartalom
        self.assertNotIn("tools", csomag_kozos.KOD_RESZEK)
        self.assertNotIn("tools", csomag_tartalom.FELSO_ENGEDELY)
        self.assertIn("tools", csomag_tartalom.KOD_TILTOTT_MAPPA)
        f = csomag_kozos.forras_fajlok(REPO)
        self.assertEqual([x for x in f if x.startswith("tools/") or x.endswith("gen_szintetikus.py")], [])
        mintak = list(csomag_kozos.KIZART_MINTAK) + csomag_kozos.export_ignore_mintak(REPO)
        self.assertTrue(csomag_kozos.kizart("tools/gen_szintetikus.py", mintak))        # also excluded from `git archive`

    def test_a_staging_kimenet_gitignore_olt(self):
        p = subprocess.run(["git", "-C", str(REPO), "check-ignore", "-q", "var/staging/szintetikus/x/tetelek.jsonl"], capture_output=True)
        if p.returncode == 128:
            self.skipTest("[indokolt] not a git checkout")
        self.assertEqual(p.returncode, 0)
        self.assertEqual(G.KIMENET_GYOKER_REL.as_posix(), "var/staging/szintetikus")

    def test_a_tool_es_a_sablonok_nem_tartalmaznak_titkot(self):
        from tests.biztonsag.test_titok_es_ut import TITOK_MINTAK
        import re
        minta = re.compile("|".join(TITOK_MINTAK.values()))
        for p in [*sorted((REPO / "tools").rglob("*")), REPO / "tests" / "test_gen_szintetikus.py"]:
            if p.is_file() and p.suffix in (".py", ".toml", ".md"):
                self.assertIsNone(minta.search(p.read_text(encoding="utf-8")), p)

    def test_arfajl(self):
        arak = G.arak_betolt()
        self.assertTrue({G.ALAP_OLCSO, G.ALAP_MINOSEG} <= set(arak))
        self.assertTrue(all(a.bemenet > 0 and a.kimenet >= a.bemenet for a in arak.values()))
        szoveg = (REPO / "tools" / "gen_arak.toml").read_text(encoding="utf-8")
        self.assertIn("CHECK THESE", szoveg)
        self.assertIn("CONSERVATIVE UPPER", szoveg)
        with tempfile.TemporaryDirectory() as t:
            rossz = Path(t) / "a.toml"
            for tartalom in ('[modell."gpt-4"]\nbemenet_usd_mtok = 1\nkimenet_usd_mtok = 1\n', '[modell."claude-x"]\nbemenet_usd_mtok = -1\nkimenet_usd_mtok = 1\n',
                             '[modell."claude-x"]\nbemenet_usd_mtok = 1\n', ""):
                rossz.write_text(tartalom)
                with self.assertRaises(G.GenHiba):
                    G.arak_betolt(rossz)

    def test_a_cli_kapcsolok(self):
        p = G.parser()
        a = p.parse_args([])
        self.assertEqual((a.max_usd, a.max_hivas, a.osszes_max_usd, a.kulcs_env), (5.0, 60, 20.0, False))
        for rossz in (["--max-usd", "0"], ["--max-usd", "nan"], ["--max-hivas", "-1"], ["--cel", "doku", "--atvesz", "x"]):
            with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
                p.parse_args(rossz)
        with redirect_stderr(io.StringIO()):
            self.assertEqual(G.main(["--atvesz", "x"]), G.KILEPES_HASZNALAT)
            self.assertEqual(G.main(["--cel", "kod"]), G.KILEPES_HASZNALAT)


if __name__ == "__main__":
    unittest.main()
