"""C36b: a C++ AI-réteg motor-oldala — a prompt és az elemzés (modell nélkül), a teszt-blokk írója, és az élő út álmodellel a
VALÓDI eszközláncon és `sandbox-exec`-en: a modell kódja (referencia, generátor, megoldás) csak a program-homokozóban fut; egy
tiltott műveletet (idegen fájl írása, hálózat, fork) próbáló generátor sem jut ki (53(b)).

A homokozós tesztek `[indokolt]` kihagyással futnak, ha nincs eszköztár (`bin/mos cpp telepit --igen`)."""
import os
import socket
import sys
import threading
import unittest
from pathlib import Path

from core import config
from core import cpp_teszt as T
from modulok.cpp import ai, ai_ellenorzes as AE, ai_futas, eszkoztar
from tests.helpers import alg_gyoker, tmpdir

MACOS = sys.platform == "darwin"
VALODI = config.load()
_E = eszkoztar.Eszkoztar(VALODI)
VAN = MACOS and _E.kesz() and _E.sdk_tbd_igazitva()
OK_SKIP = "[indokolt] nincs C++ eszköztár vagy sandbox-exec (bin/mos cpp telepit --igen; csak macOS)"

MAGYAR = ("A ciklus az utolsó elemet kihagyja, mert a feltétel n - 1-nél megáll, így a sorozat végén álló szakaszt nem "
          "számolja bele az eredménybe. Ezért kisebb értéket kapunk a vártnál.")
ANGOL = "The loop skips the last element because the condition stops at n - 1, so the final run is not counted."


class PromptEsElemzesTest(unittest.TestCase):
    def test_minden_mod_promptja_szamozott_koddal(self):
        for mod in ai.MODOK:
            p = ai.prompt(mod, "# Feladat\nösszeg", "int main() {\n  return 0;\n}\n",
                          {"fajta": "teszt", "bemenet": "1 2\n", "vart": "3\n", "kapott": "4\n"})
            self.assertIn("1 | int main() {", p)
            self.assertIn("3 | }", p)
            if mod in ("hiba", "tipp", "megoldas"):
                self.assertIn("Várt kimenet:\n3", p)
            else:
                self.assertNotIn("Várt kimenet", p)
        self.assertIn("HIBA: <sorszám> <fajta>", ai.prompt("hiba", "x", "y"))
        with self.assertRaises(ValueError):
            ai.prompt("ismeretlen", "x", "y")

    def test_bizonyitek_szovegek(self):
        self.assertIn("nem fordul le", ai.bizonyitek_szoveg({"fajta": "fordito", "diagnosztika": [{"sor": 3, "uzenet": "x"}]}))
        self.assertIn("időkorlátot", ai.bizonyitek_szoveg({"fajta": "ido", "leiras": "egy nagy bemeneten"}))
        hosszu = ai.bizonyitek_szoveg({"fajta": "teszt", "bemenet": "1 " * 1000, "vart": "1", "kapott": ""})
        self.assertIn("levágva", hosszu)
        self.assertIn("(üres)", hosszu)

    def test_hiba_valasz(self):
        v = ai.hiba_valasz("<think>gondolkodom: HIBA: 99 index</think>" + MAGYAR + "\nHIBA: 10 index")
        self.assertEqual((v["sor"], v["fajta"]), (10, "index"))
        self.assertNotIn("HIBA:", v["magyarazat"])
        self.assertEqual(ai.hiba_valasz("szöveg\nHIBA: a 7. sor feltetel")["sor"], 7)
        self.assertEqual(ai.hiba_valasz("HIBA: 7 rejtely")["fajta"], "egyeb")
        self.assertEqual(ai.hiba_valasz("nincs zárósor")["sor"], None)
        self.assertEqual(ai.hiba_valasz(None)["sor"], None)

    def test_tipp_valasz(self):
        v = ai.tipp_valasz("1. IRÁNY: nézd a ciklust.\n2. ALGORITMUS: a végét is be kell járni.\n3. HELY: a 10. sorban a feltétel.")
        self.assertTrue(v["sorrend_ok"])
        self.assertEqual(v["hely_sor"], 10)
        self.assertEqual(v["kod_szintek"], [])
        k = ai.tipp_valasz("1. IRÁNY: x\n2. ALGORITMUS: itt a kód:\n```cpp\nfor(;;);\n```\n3. HELY: sor 4")
        self.assertEqual(k["kod_szintek"], [1])
        self.assertEqual(k["hely_sor"], 4)
        self.assertFalse(ai.tipp_valasz("3. HELY: a\n1. IRÁNY: b\n2. ALGORITMUS: c")["sorrend_ok"])

    def test_teszt_es_stressz_valasz(self):
        v = ai.teszt_valasz("```bemenet\n1\n5\n```\n```\n2\n1 1\n```\n```cpp\n#include <x>\nint main(){}\n```")
        self.assertEqual(v["bemenetek"], ["1\n5\n", "2\n1 1\n"])
        self.assertIn("int main", v["referencia"])
        s = ai.stressz_valasz("```cpp\nint main(){ /* lassú */ }\n```\n```cpp\nint main(int argc, char** argv){}\n```")
        self.assertIn("argv", s["generator"])                     # fordított sorrend: megcserélve
        c = ai.stressz_valasz("```cpp referencia\nint main(){}\n```\n```cpp generator\nint main(int c,char**v){}\n```")
        self.assertIn("char**v", c["generator"])

    def test_magyar_arany_es_atfedes(self):
        self.assertGreaterEqual(ai.magyar_arany(MAGYAR), 0.3)
        self.assertLess(ai.magyar_arany(ANGOL), 0.1)
        self.assertEqual(ai.magyar_arany("```cpp\nint main\n```"), 0.0)
        ref = "#include <bits/stdc++.h>\n    for (int i = 1; i < n; i++) {\n    x++;\n"
        self.assertEqual(ai.atfedes("írd: for(int i=1;i<n;i++){", ref), 1)
        self.assertEqual(ai.atfedes("semmi", ref), 0)


class TesztBlokkTest(unittest.TestCase):
    def test_visszaolvashato(self):
        for bem, ki in (("3\n1 2 3\n", "6\n"), ("", "x"), ("a ``` b\n", "```\n"), ("---\n--- valami\n", "ok\n")):
            blokk = T.teszt_blokk("Szélső eset", bem, ki)
            t = T.tesztek("# J\n\n" + blokk)
            self.assertEqual(len(t), 1, blokk)
            self.assertIsNone(t[0].hiba)
            self.assertEqual(t[0].cim, "Szélső eset")
            self.assertEqual(t[0].bemenet.rstrip("\n"), bem.rstrip("\n"))
            self.assertEqual(t[0].kimenet.rstrip("\n"), ki.rstrip("\n"))

    def test_szakaszjelzo_a_tartalomban(self):
        with self.assertRaises(ValueError):
            T.teszt_blokk(None, "--- kimenet\n", "1\n")


class BizonyitekTest(unittest.TestCase):
    def test_esemenyekbol(self):
        b = ai_futas.bizonyitek_esemenyekbol({"ok": False, "diagnosztika": [
            {"szint": "warning", "sor": 2, "uzenet": "w"}, {"szint": "error", "sor": 5, "uzenet": "e"}]}, [], [])
        self.assertEqual(b["fajta"], "fordito")
        self.assertEqual(b["diagnosztika"], [{"sor": 5, "uzenet": "e"}])
        self.assertEqual(ai_futas.bizonyitek_sorai(b), {5})
        t = [T.Teszt(1, 1, None, "1\n", "2\n", None), T.Teszt(2, 9, None, "3\n", "4\n", None)]
        b = ai_futas.bizonyitek_esemenyekbol({"ok": True}, [
            {"sorszam": 1, "allapot": "atment"},
            {"sorszam": 2, "allapot": "szanitizer", "stdout_kivonat": "", "jelentes": {"leiras": "heap", "sor": 7}}], t)
        self.assertEqual((b["fajta"], b["bemenet"], b["vart"]), ("szanitizer", "3\n", "4\n"))
        self.assertEqual(ai_futas.bizonyitek_sorai(b), {7})
        self.assertIsNone(ai_futas.bizonyitek_esemenyekbol({"ok": True}, [{"sorszam": 1, "allapot": "atment"}], t))

    def test_leiras_frontmatter_es_beagyazas_nelkul(self):
        s = ai_futas._leiras("---\nTags:\n  - I\n---\n# Cím\nszöveg\n![[x.cpp]]\n")
        self.assertEqual(s, "# Cím\nszöveg")


HIBAS = """#include <bits/stdc++.h>
using namespace std;

int main() {
    int n;
    cin >> n;
    long long s = 0;
    for (int i = 1; i < n; i++) {
        long long x;
        cin >> x;
        s += x;
    }
    cout << s << "\\n";
    return 0;
}
"""
JO = HIBAS.replace("for (int i = 1; i < n; i++)", "for (int i = 0; i < n; i++)")
LASSU = """#include <bits/stdc++.h>
int main() { int n; std::cin >> n; long long s = 0; for (int i = 0; i < n; i++) { long long x; std::cin >> x; s += x; }
std::cout << s << "\\n"; }
"""
GENERATOR = """#include <bits/stdc++.h>
int main(int argc, char** argv) { std::mt19937 r(atoi(argv[1])); int n = r() % 5 + 1; std::cout << n << "\\n";
for (int i = 0; i < n; i++) std::cout << (int)(r() % 7) - 3 << " "; std::cout << "\\n"; }
"""
JEGYZET = """---
Tags:
---
# Összeg

Add össze az n számot.

```teszt Példa
--- bemenet
3
1 2 3
--- kimenet
6
```

![[osszeg.cpp]]
"""


def tiltott_generator(cel: Path, port: int) -> str:
    """Egy „generátor”, amely idegen fájlt ír, hálózatra csatlakozik és forkol, majd érvényes bemenetet ad: a homokozóban a
    tiltott műveletek elbuknak (a fájl nem jön létre, a kapcsolat nem épül fel, a gyermek nem fut)."""
    return f"""#include <bits/stdc++.h>
#include <unistd.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
int main(int argc, char** argv) {{
    FILE* f = fopen("{cel}", "w");
    if (f) {{ fputs("kijutott", f); fclose(f); }}
    int s = socket(AF_INET, SOCK_STREAM, 0);
    sockaddr_in a{{}};
    a.sin_family = AF_INET;
    a.sin_port = htons({port});
    a.sin_addr.s_addr = inet_addr("127.0.0.1");
    if (s >= 0) connect(s, (sockaddr*)&a, sizeof a);
    pid_t p = fork();
    if (p == 0) {{ FILE* g = fopen("{cel}.fork", "w"); if (g) fclose(g); _exit(0); }}
    std::cout << "2\\n1 1\\n";
}}
"""


class AlModell:
    def __init__(self, valasz: str):
        self.valasz, self.hivasok = valasz, []

    def __call__(self, keres, jelzes):
        self.hivasok.append(keres)
        jelzes(1)
        return self.valasz, "almodell"


@unittest.skipUnless(VAN, OK_SKIP)
class EloUtTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._t = tmpdir()
        cls.t = Path(os.path.realpath(cls._t.name))
        root = alg_gyoker(str(cls.t)).resolve()
        cls.cfg = config.load({"MOS_ROOT": str(root), "HOME": str(cls.t / "home"), "MOS_LLVM": str(VALODI.path("llvm")),
                               "MOS_SDK": str(VALODI.path("sdk")), "MOS_RUNTIME": str(VALODI.path("runtime"))})
        cls.jegyzet = cls.t / "osszeg.md"
        cls.jegyzet.write_text(JEGYZET, encoding="utf-8")
        cls.hibas = cls.t / "hibas.cpp"
        cls.hibas.write_text(HIBAS, encoding="utf-8")
        cls.jo = cls.t / "jo.cpp"
        cls.jo.write_text(JO, encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls._t.cleanup()

    def fut(self, mod, valasz, cpp=None, megerosit=False):
        esem: list[dict] = []
        m = AlModell(valasz)
        r = ai_futas.AIFutas(self.cfg, esemeny=esem.append, modell_hivo=m).fut(mod, cpp or self.hibas, self.jegyzet,
                                                                                megerosit=megerosit)
        return r, esem, m

    def eredmeny(self, esem):
        return next(e for e in esem if e["szakasz"] == "eredmeny")

    def test_hiba_a_bizonyitekkal(self):
        r, esem, m = self.fut("hiba", MAGYAR + "\nHIBA: 8 index")
        self.assertTrue(r["ok"], esem)
        prompt = m.hivasok[0]["messages"][0]["content"]
        self.assertIn("Várt kimenet:\n6", prompt)
        self.assertNotIn("![[osszeg.cpp]]", prompt)
        e = self.eredmeny(esem)
        self.assertEqual((e["sor"], e["fajta"]), (8, "index"))
        self.assertFalse(e["ellenorzott"])                        # a teszt bizonyítéka sort nem nevez meg

    def test_minden_atment_nincs_modellhivas(self):
        r, esem, m = self.fut("hiba", "HIBA: 1 index", cpp=self.jo)
        self.assertTrue(r["ok"])
        self.assertEqual(m.hivasok, [])
        self.assertTrue(self.eredmeny(esem)["nincs_hiba"])

    def test_forditasi_hiba_sora_ellenorzott(self):
        rossz = self.t / "rossz.cpp"
        rossz.write_text(HIBAS.replace("s += x;", "s += y;"), encoding="utf-8")
        r, esem, _ = self.fut("hiba", MAGYAR + "\nHIBA: 11 egyeb", cpp=rossz)
        self.assertTrue(self.eredmeny(esem)["ellenorzott"])

    def test_tipp_kodos_szint_kiszurve(self):
        _, esem, _ = self.fut("tipp", "1. IRÁNY: a ciklus.\n2. ALGORITMUS:\n```cpp\nfor(int i=0;i<n;i++)\n```\n3. HELY: a 8. sorban.")
        e = self.eredmeny(esem)
        self.assertTrue(e["szintek"][1]["kiszurve"])
        self.assertIsNone(e["szintek"][1]["szoveg"])
        self.assertEqual(e["hely_sor"], 8)

    def test_megoldas_megerosites_nelkul_nem_fut(self):
        r, esem, m = self.fut("megoldas", "```cpp\n" + JO + "```")
        self.assertEqual(r["kod"], "megerosites_kell")
        self.assertEqual(m.hivasok, [])

    def test_megoldas_homokozoban_ellenorizve(self):
        _, esem, _ = self.fut("megoldas", "Javítottam a ciklust.\n```cpp\n" + JO + "```", megerosit=True)
        e = self.eredmeny(esem)
        self.assertTrue(e["ellenorzott"])
        self.assertEqual((e["atment_db"], e["ossz"]), (1, 1))
        self.assertEqual(self.hibas.read_text(encoding="utf-8"), HIBAS)       # a .cpp-be semmi nem íródik (53(d))

    def test_szelso_tesztek_ellenorzott_referenciaval(self):
        _, esem, _ = self.fut("teszt", "```bemenet\n1\n5\n```\n```bemenet\n2\n-1 1\n```\n```cpp\n" + LASSU + "```")
        e = self.eredmeny(esem)
        self.assertTrue(e["ellenorzott"])
        self.assertEqual([x["allapot"] for x in e["esetek"]], ["elteres", "elteres"])
        self.assertEqual(e["esetek"][0]["vart"].strip(), "5")
        t = T.tesztek(e["esetek"][0]["blokk"])
        self.assertEqual((t[0].bemenet.strip(), t[0].kimenet.strip()), ("1\n5", "5"))

    def test_rossz_referencia_nem_ad_vart_kimenetet(self):
        rossz_ref = LASSU.replace("s += x;", "s -= x;")
        _, esem, _ = self.fut("teszt", "```bemenet\n1\n5\n```\n```cpp\n" + rossz_ref + "```")
        e = self.eredmeny(esem)
        self.assertFalse(e["ellenorzott"])
        self.assertIsNone(e["esetek"][0]["vart"])
        self.assertIsNone(e["esetek"][0]["blokk"])

    def test_stressz_ellenpelda(self):
        _, esem, _ = self.fut("stressz", "```cpp\n" + GENERATOR + "```\n```cpp\n" + LASSU + "```")
        e = self.eredmeny(esem)
        self.assertIsNotNone(e["ellenpelda"], e)
        self.assertTrue(e["ellenorzott"])
        self.assertIn("Stressz-ellenpélda", e["ellenpelda"]["blokk"])

    def test_tiltott_muveletes_generator_nem_jut_ki(self):
        cel = self.t / "kint" / "kijutott.txt"
        cel.parent.mkdir(exist_ok=True)
        figyelo = socket.socket()
        figyelo.bind(("127.0.0.1", 0))
        figyelo.listen(1)
        figyelo.settimeout(0.2)
        kapcsolat = []

        def fogad():
            try:
                c, _ = figyelo.accept()
                kapcsolat.append(c)
            except OSError:
                pass
        szal = threading.Thread(target=fogad)
        szal.start()
        try:
            _, esem, _ = self.fut("stressz", "```cpp\n" + tiltott_generator(cel, figyelo.getsockname()[1]) + "```\n```cpp\n"
                                  + LASSU + "```")
        finally:
            szal.join()
            figyelo.close()
        self.assertFalse(cel.exists(), "a generátor a homokozón kívülre írt")
        self.assertFalse(Path(str(cel) + ".fork").exists(), "a generátor gyermeke futott")
        self.assertEqual(kapcsolat, [], "a generátor hálózatra csatlakozott")
        e = self.eredmeny(esem)
        self.assertIsNotNone(e)

    def test_tiltott_muveletek_a_futtato_alatt(self):
        """Ugyanaz a három tiltott művelet közvetlenül a `Futtato` alatt: a program maga jelenti, mi sikerült."""
        cel = self.t / "kint" / "futtato.txt"
        cel.parent.mkdir(exist_ok=True)
        kod = f"""#include <bits/stdc++.h>
#include <unistd.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
int main() {{
    FILE* f = fopen("{cel}", "w");
    std::cout << (f ? "FAJL_OK" : "FAJL_TILTVA") << "\\n";
    int s = socket(AF_INET, SOCK_STREAM, 0);
    sockaddr_in a{{}};
    a.sin_family = AF_INET;
    a.sin_port = htons(9);
    a.sin_addr.s_addr = inet_addr("1.1.1.1");
    std::cout << (s >= 0 && connect(s, (sockaddr*)&a, sizeof a) == 0 ? "HALO_OK" : "HALO_TILTVA") << "\\n";
    pid_t p = fork();
    if (p == 0) _exit(0);
    std::cout << (p > 0 ? "FORK_OK" : "FORK_TILTVA") << "\\n";
}}
"""
        with AE.Futtato(self.cfg) as f:
            p = f.fordit(kod, "tiltott")
            self.assertTrue(p.ok, p.osszegzes())
            r = f.futtat(p, "", idokorlat_s=5)
        self.assertEqual(r["stdout"].split(), ["FAJL_TILTVA", "HALO_TILTVA", "FORK_TILTVA"], r)
        self.assertFalse(cel.exists())

    def test_nincs_eszkoztar_zarva_hibazik(self):
        cfg = config.load({"MOS_ROOT": str(self.cfg.root), "HOME": str(self.t / "home"), "MOS_LLVM": str(self.t / "nincs"),
                           "MOS_SDK": str(self.t / "nincs"), "MOS_RUNTIME": str(VALODI.path("runtime"))})
        esem: list[dict] = []
        m = AlModell("x")
        r = ai_futas.AIFutas(cfg, esemeny=esem.append, modell_hivo=m).fut("teszt", self.hibas, self.jegyzet)
        self.assertEqual(r["kod"], "nincs_eszkoztar")
        self.assertEqual(m.hivasok, [])


if __name__ == "__main__":
    unittest.main()
