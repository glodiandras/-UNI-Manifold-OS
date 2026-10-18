"""A Bases függvényei (`core/bazis/fuggvenyek.py`, C12 2. lépés): a `Functions.md` minden függvénye táblázatos
esetekkel — normál, üres és rossz típusú bemenet."""
import math
import unittest
from datetime import datetime

from core.bazis import ertekek as e
from core.bazis.ertekek import Cimke, Datum, Fajl, FutasHiba, Html, Idotartam, Ikon, Kep, Link
from core.bazis.kifejezes import KifejezesHiba
from tests.bazis_segedek import MOST, ertek, sor, tabla


def D(s: str) -> Datum:
    return e.datum_szovegbol(s)


S = sor("A/Jegyzet.md",
        {"price": 4.5, "Status": "Done", "NN": ["[[Cél]]", "[[Másik]]"], "szoveg": "Hello World", "lista": [3, 1, 2, 2],
         "ures": None, "szamok": [1, 2, 3, 4], "tags": ("tags", ["Book", "math/algebra"])},
        cimkek=["Book", "math/algebra", "inline", "BOOK"], ctime=datetime(2026, 8, 30, 7, 0, 0),
        linkek=[{"cel_nyers": "Cél", "alias": "mutat"}, {"cel_nyers": "Nincs ilyen"},
                {"cel_nyers": "kep.png", "beagyazas": True}])
SOROK = [S, sor("Cél.md", {"Ora": 2}), sor("Másik.md", {"Ora": 5}), sor("B/Más.md", linkek=["Jegyzet"]),
         sor("kep.png", tipus="kep")]
T = tabla(SOROK)


class FuggvenyTest(unittest.TestCase):
    def tabla_esetek(self, esetek, sor_=S, t=T):
        for kif, vart in esetek:
            with self.subTest(kif):
                v = ertek(kif, sor_, t)
                if isinstance(vart, float) and not math.isnan(vart):
                    self.assertAlmostEqual(v, vart)
                else:
                    self.assertEqual(v, vart)

    def hibak(self, kifejezesek, sor_=S, t=T):
        for kif in kifejezesek:
            with self.subTest(kif):
                with self.assertRaises((FutasHiba, KifejezesHiba)):
                    ertek(kif, sor_, t)


class GlobalisTest(FuggvenyTest):
    def test_esetek(self):
        self.tabla_esetek([
            ('escapeHTML("<a href=\'x\'>&</a>")', "&lt;a href=&#x27;x&#x27;&gt;&amp;&lt;/a&gt;"),
            ('date("2025-01-01 04:03:00")', D("2025-01-01 04:03:00")),
            ('date("2025-01-01")', D("2025-01-01")),
            ('date("2025-01-01").format("YYYY-MM-DD HH:mm")', "2025-01-01 00:00"),
            ('duration("1d")', Idotartam(0, e.NAP_MS)),
            ("duration('1d') * 2", Idotartam(0, 2 * e.NAP_MS)),
            ("now() + (duration('1d') * 2) - now()", 2 * e.NAP_MS),
            ('html("<b>x</b>")', Html("<b>x</b>")),
            ('icon("arrow-right")', Ikon("arrow-right")),
            ('list("v")', ["v"]), ("list([1, 2])", [1, 2]), ("list(null)", []), ("list(NN).length", 2),
            ("list(price)", [4.5]),
            ("max(1, 5, 3)", 5), ("min(4, 2.5, 3)", 2.5), ("max(null, 3)", 3), ("max(null)", None),
            ("max([1, 9, 4])", 9), ("min(price, 10)", 4.5),
            ("now()", MOST), ("today()", Datum(MOST.ertek.replace(hour=0), False)),
            ('number("3.4")', 3.4), ("number(true)", 1), ("number(false)", 0), ('number(" 7 ")', 7), ("number(null)", None),
            ("number(price)", 4.5), ('number("1e3")', 1000),
            ("0 <= random() && random() < 1", True),
            ('if(false, link(1), 2)', 2), ('if(true, 1)', 1), ('if(false, 1)', None), ('if(price, "van", "nincs")', "van"),
            ('if(ures, "van", "nincs")', "nincs"), ('if(0, 1, 2)', 2), ('if("", 1, 2)', 2), ('if([], 1, 2)', 1),
        ])

    def test_link_es_file(self):
        self.tabla_esetek([
            ('link("Cél")', Link("Cél", None, "Cél.md")),
            ('link("[[Cél|mutat]]")', Link("Cél", "mutat", "Cél.md")),
            ('link("Cél", "szöveg")', Link("Cél", "szöveg", "Cél.md")),
            ('link("Cél#Fejezet")', Link("Cél", None, "Cél.md", "Fejezet")),
            ('link("Nincs ilyen")', Link("Nincs ilyen", None, None)),
            ('link("https://obsidian.md")', Link("https://obsidian.md", None, None, None, True)),
            ('link("https://obsidian.md", "oldal")', Link("https://obsidian.md", "oldal", None, None, True)),
            ('link("Másik").asFile().name', "Másik.md"),
            ('file("Cél").name', "Cél.md"), ('file("B/Más.md").name', "Más.md"), ('file("Nincs")', None),
            ('file(link("Cél")).path', "Cél.md"), ("file(file).path", "A/Jegyzet.md"),
            ('link("Cél", icon("plus"))', Link("Cél", Ikon("plus"), "Cél.md")),
            ('link(file("Cél"))', Link("Cél.md", None, "Cél.md")),
        ])

    def test_image(self):
        self.tabla_esetek([
            ('image("#ff0000")', Kep(szin="#ff0000")), ('image("#abc")', Kep(szin="#abc")),
            ('image("https://x.hu/a.png")', Kep(url="https://x.hu/a.png")), ('image("[[kep.png]]")', Kep(ut="kep.png")),
            ('image("kep.png")', Kep(ut="kep.png")), ('image(file("kep.png"))', Kep(ut="kep.png")),
            ('image("nincs.png")', None), ("image(null)", None),
        ])

    def test_hibak(self):
        self.hibak(['date("holnap")', "date(5)", 'duration("x")', "duration(1)", "link(1)", "link()", "link(1, 2, 3)",
                    "file(1)", "html([1])", 'max(1, "a")', 'min("a")', "max()", "number(\"x\")", "number([1])",
                    "number(\"\")", "escapeHTML(null)", "now(1)", "icon(null)", "if(1)", "if(1, 2, 3, 4)",
                    "nincs_ilyen(1)", "image(5)", "list()"])


class BarmelyTipusTest(FuggvenyTest):
    def test_esetek(self):
        self.tabla_esetek([
            ("1.isTruthy()", True), ("0.isTruthy()", False), ('"".isTruthy()', False), ("[].isTruthy()", True),
            ("ures.isTruthy()", False), ("null.isTruthy()", False),
            ('"example".isType("string")', True), ('true.isType("boolean")', True), ("1.isType(\"number\")", True),
            ('[1].isType("list")', True), ('{"a": 1}.isType("object")', True), ('now().isType("date")', True),
            ('link("Cél").isType("link")', True), ('file.isType("file")', True), ('"a".isType("number")', False),
            ('ures.isType("null")', True), ('"a".isType("link")', False), ('/a/.isType("regexp")', True),
            ("123.toString()", "123"), ("true.toString()", "true"), ("[1, 2].toString()", "1,2"),
            ("ures.toString()", ""), ("price.toString()", "4.5"), ('date("2024-01-01").toString()', "2024-01-01"),
        ])

    def test_ures_ertek_metodusai(self):
        self.tabla_esetek([("ures.isEmpty()", True), ("nincs_ilyen_tulajdonsag.isEmpty()", True)])
        self.hibak(["ures.lower()", "ures.contains(1)", "null.length.abs()"])


class DatumTest(FuggvenyTest):
    def test_esetek(self):
        most = 'date("2025-05-27 13:45:09")'
        self.tabla_esetek([
            (most + ".year", 2025), (most + ".month", 5), (most + ".day", 27), (most + ".hour", 13),
            (most + ".minute", 45), (most + ".second", 9), (most + ".millisecond", 0),
            (most + ".date()", D("2025-05-27")), (most + '.date().format("YYYY-MM-DD HH:mm:ss")', "2025-05-27 00:00:00"),
            (most + '.format("YYYY-MM-DD")', "2025-05-27"), (most + '.format("dddd D MMM, h:mm a")', "Tuesday 27 May, 1:45 pm"),
            (most + ".time()", "13:45:09"), (most + ".isEmpty()", False),
            ('(now() - "3d").relative()', "3 days ago"), ('(now() + "2h").relative()', "in 2 hours"),
            ("now().date().isEmpty()", False), ("today().hour", 0), ("now().hour", 12),
            ('date("2024-01-31") + "1M"', D("2024-02-29")), ('date("2025-01-01") + "1y"', D("2026-01-01")),
            ('(date("2025-03-01") - date("2025-02-01")) / 86400000', 28),
            ('date("2025-01-01") < date("2025-01-02")', True), ('date("2025-01-01") >= date("2025-01-02")', False),
            ('file.mtime > now() - "1 year"', True), ('file.mtime > now() - "1 day"', False),
            ('date("2024-12-01") + "1M" + "4h" + "3m"', D("2025-01-01 04:03:00")),
            ('now() - date("2025-10-02 12:00:00") > "x"', False),
        ])

    def test_hibak(self):
        self.hibak(['"2024-01-01".year.foo()', 'now().format()', 'now().format(1, 2)', 'now().nincs()', 'now().format(null)'])


class SzovegTest(FuggvenyTest):
    def test_esetek(self):
        self.tabla_esetek([
            ('"hello".contains("ell")', True), ('"hello".contains("x")', False), ('"hello".contains(null)', False),
            ('"hello".contains(1)', False), ('"a1".contains(1)', True),
            ('"hello".containsAll("h", "e")', True), ('"hello".containsAll("h", "x")', False),
            ('"hello".containsAny("x", "y", "e")', True), ('"hello".containsAny("x")', False),
            ('"hello".endsWith("lo")', True), ('"hello".endsWith("he")', False),
            ('"hello".startsWith("he")', True), ('"hello".startsWith("lo")', False),
            ('"".isEmpty()', True), ('"Hello world".isEmpty()', False),
            ('"HeLLo".lower()', "hello"), ('"Árvíztűrő".lower()', "árvíztűrő"),
            ('"a:b:c:d".replace(/:/, "-")', "a-b:c:d"), ('"a:b:c:d".replace(/:/g, "-")', "a-b-c-d"),
            ('"John Smith".replace(/(\\w+) (\\w+)/, "$2, $1")', "Smith, John"), ('"aXbX".replace("X", "-")', "a-b-"),
            ('"abc".replace(/B/i, "[$&]")', "a[b]c"), ('"abc".replace(/b/, "$$")', "a$c"),
            ('"123".repeat(2)', "123123"), ('"x".repeat(0)', ""),
            ('"hello".reverse()', "olleh"),
            ('"hello".slice(1, 4)', "ell"), ('"hello".slice(1)', "ello"), ('"hello".slice(-3)', "llo"),
            ('"hello".slice(2, 100)', "llo"), ('"hello".slice(3, 1)', ""),
            ('"a,b,c,d".split(",", 3)', ["a", "b", "c"]), ('"a,b,c,d".split(/,/, 3)', ["a", "b", "c"]),
            ('"a,b".split(",")', ["a", "b"]), ('"ab".split("")', ["a", "b"]), ('"abc".split(/b/)', ["a", "c"]),
            ('"hello world".title()', "Hello World"), ('"HELLO wORLD".title()', "Hello World"),
            ('"  hi  ".trim()', "hi"), ('"hello".length', 5), ('"árvíz".length', 5), ('"".length', 0),
            ("szoveg.lower().contains(\"world\")", True), ('"a" + "b" + 1', "ab1"),
            ('"abc"[1]', "b"), ('"abc"[5]', None),
        ])

    def test_hibak(self):
        self.hibak(['"a".nincs()', '"a".contains()', '"a".slice()', '"a".slice("x")', '"a".repeat(-1)', '"a".repeat("x")',
                    '"a".replace("a")', '"a".split()', '"a".contains([1])', '"a".abs()', '"a".round(1)',
                    '"x".repeat(1000000000)', "price.lower()"])


class SzamTest(FuggvenyTest):
    def test_esetek(self):
        self.tabla_esetek([
            ("(-5).abs()", 5), ("(5).abs()", 5), ("(2.1).ceil()", 3), ("(-2.1).ceil()", -2), ("(2.9).floor()", 2),
            ("(-2.1).floor()", -3), ("5.isEmpty()", False), ("0.isEmpty()", False),
            ("(2.5).round()", 3), ("(2.3333).round(2)", 2.33), ("(-2.5).round()", -2), ("(1234).round(-2)", 1200),
            ("(3.14159).toFixed(2)", "3.14"), ("(5).toFixed(2)", "5.00"), ("(2.5).toFixed(0)", "3"), ("(0).toFixed(1)", "0.0"),
            ("price.round()", 5), ("(price / 3).toFixed(3)", "1.500"), ("(1 / 3).round(3)", 0.333),
            ("price * 2 + 1", 10), ("(10 % 4)", 2), ("-price", -4.5), ("1 / 0", math.inf), ("-1 / 0", -math.inf),
        ])
        self.assertTrue(math.isnan(ertek("0 / 0", S, T)))

    def test_hibak(self):
        self.hibak(["(1).toFixed()", "(1).toFixed(101)", '(1).toFixed("x")', "(1).round(\"x\")", "(1).nincs()",
                    "(1).length.abs()", "(1).abs(2)", '5.contains(1)', "5.lower()"])


class ListaTest(FuggvenyTest):
    def test_esetek(self):
        self.tabla_esetek([
            ("[1,2,3].contains(2)", True), ("[1,2,3].contains(4)", False), ('["a"].contains("A")', False),
            ("[1,2,3].containsAll(2, 3)", True), ("[1,2,3].containsAll(2, 4)", False),
            ("[1,2,3].containsAny(3, 4)", True), ("[1,2,3].containsAny(5, 4)", False),
            ("[1,2,3,4].filter(value > 2)", [3, 4]), ("[1,2,3,4].filter(index % 2 == 0)", [1, 3]),
            ("[1,2,3,4].filter(false)", []), ("[1,2,3,4].map(value + 1)", [2, 3, 4, 5]),
            ("[1,2,3].map(value * index)", [0, 2, 6]), ("[1,2,3].reduce(acc + value, 0)", 6),
            ("[1,2,3].reduce(acc + value)", None), ("[].reduce(acc + value, 7)", 7),
            ("[3,1,2].reduce(if(acc == null || value > acc, value, acc), null)", 3),
            ('["a","b"].reduce(acc + value, "")', "ab"), ("[1,[2,3],4].flat()", [1, 2, 3, 4]),
            ("[1,2,3].isEmpty()", False), ("[].isEmpty()", True), ('[1,2,3].join(",")', "1,2,3"),
            ('[1,2,3].join(" - ")', "1 - 2 - 3"), ("[1,2].join()", "1,2"), ("[1,2,3].reverse()", [3, 2, 1]),
            ("[1,2,3,4].slice(1,3)", [2, 3]), ("[1,2,3,4].slice(2)", [3, 4]), ("[1,2,3,4].slice(-2)", [3, 4]),
            ("[3,1,2].sort()", [1, 2, 3]), ('["c","a","b"].sort()', ["a", "b", "c"]), ("[2,null,1].sort()", [None, 1, 2]),
            ("[1,2,2,3,1].unique()", [1, 2, 3]), ('["a","A"].unique()', ["a", "A"]), ("[1,2,3].length", 3),
            ("[10,20][1]", 20), ("[10,20][5]", None), ("[10,20][-1]", None), ("[10,20][0.5]", None),
            ("lista.unique().sort()", [1, 2, 3]),
            ("[1,2,3,4].sum()", 10), ("[].sum()", 0), ("[1,null,3].sum()", 4), ("[1,2,3,4].mean()", 2.5), ("[].mean()", None),
            ("[1,2,3,4].mean().round(1)", 2.5), ("[3,1,2].median()", 2), ("[4,1,2,3].median()", 2.5), ("[].median()", None),
            ("[2,4,4,4,5,5,7,9].stddev()", 2), ("[3,1,2].min()", 1), ("[3,1,2].max()", 3), ("[null,\"a\"].max()", None),
            ('[date("2024-02-01"), date("2024-01-01")].min()', D("2024-01-01")),
            ('[date("2024-02-01"), date("2024-01-01")].max()', D("2024-02-01")), ("szamok.filter(value > 1).map(value * 2).reduce(acc + value, 0)", 18),
            ("[[1, 2], [3]].map(value.length)", [2, 1]), ("[1,2,3].map(value + formulaszerű)", [None, None, None]),
            ("[1,2,3].filter(value > list(1).length)", [2, 3]),
        ])

    def test_beagyazott_lusta_ertek_nem_szivarog(self):
        self.tabla_esetek([("[1,2].map([10,20].map(value + 1))", [[11, 21], [11, 21]]),
                           ("[1,2].map([10,20].map(value + index))", [[10, 21], [10, 21]])])

    def test_hibak(self):
        self.hibak(["[1].nincs()", "[1].contains()", "[1].filter()", "[1].filter(1, 2)", "[1].map()", "[1].reduce()",
                    "[1].slice()", '"a".filter(true)', "5.map(value)", "ures.map(value)",
                    "[1,2].reduce(value.foo(), 0)"])


class LinkEsFajlTest(FuggvenyTest):
    def test_link(self):
        self.tabla_esetek([
            ('link("Más").asFile().name', "Más.md"), ('link("Nincs").asFile()', None),
            ('link("Más").linksTo(file("Jegyzet"))', True), ('link("Cél").linksTo(file("Jegyzet"))', False),
            ('link("Más").linksTo("Jegyzet")', True), ('link("Nincs").linksTo("Jegyzet")', False),
            ('NN.map(value.asFile().name)', ["Cél.md", "Másik.md"]), ('NN[0].asFile().properties.Ora', 2),
            ("NN.map(value.asFile().properties.Ora).reduce(acc + value, 0)", 7),
        ])

    def test_fajl_mezok(self):
        self.tabla_esetek([
            ("file.name", "Jegyzet.md"), ("file.basename", "Jegyzet"), ("file.path", "A/Jegyzet.md"),
            ("file.folder", "A"), ("file.ext", "md"), ("file.size", 100), ("file.file.name", "Jegyzet.md"),
            ('file("kep.png").ext', "png"), ('file("kep.png").basename', "kep"), ('file("Cél").folder', ""),
            ("file.mtime.year", 2026), ("file.ctime.year", 2026),
            ("file.properties.Status", "Done"), ("file.properties.status", "Done"), ("file.properties.price", 4.5),
            ('file.properties.keys().contains("Status")', True), ("file.properties.nincs", None),
            ("file.tags", [Cimke("#Book"), Cimke("#math/algebra"), Cimke("#inline")]),
            ("file.tags.length", 3), ('file.tags == ["Book", "math/algebra", "inline"]', True),
            ('file.tags.contains("book")', True), ('file.tags.map(value.lower())', ["#book", "#math/algebra", "#inline"]),
            ('file.tags.join(", ")', "#Book, #math/algebra, #inline"),
            ("file.links.length", 2), ("file.links.map(value.asFile().name)", ["Cél.md", None]),
            ("file.embeds.length", 1), ("file.embeds.map(value.asFile().name)", ["kep.png"]),
            ("file.backlinks.map(value.name)", ["Más.md"]), ("file.backlinks.length", 1),
            ('file("Cél").backlinks.map(value.path)', ["A/Jegyzet.md"]), ('file("kep.png").backlinks.length', 1),
            ("file.nincs_ilyen", None),
        ])

    def test_fajl_metodusok(self):
        self.tabla_esetek([
            ('file.hasTag("book")', True), ('file.hasTag("Book")', True), ('file.hasTag("#book")', True),
            ('file.hasTag("math")', True), ('file.hasTag("math/algebra")', True), ('file.hasTag("mat")', False),
            ('file.hasTag("x", "inline")', True), ('file.hasTag("x", "y")', False), ('file.hasTag("algebra")', False),
            ('file("Cél").hasTag("book")', False),
            ('file.hasLink("Cél")', True), ('file.hasLink(link("Cél"))', True), ('file.hasLink(file("Cél"))', True),
            ('file.hasLink("Másik")', False), ('file.hasLink("Nincs ilyen")', True), ('file.hasLink("nincs ILYEN")', True),
            ('file.hasLink("kep.png")', True), ('file.hasLink("Cél.md")', True), ('file.hasLink("")', False),
            ('file("B/Más.md").hasLink("Jegyzet")', True), ('file("B/Más.md").hasLink(file)', True),
            ('file.hasProperty("Status")', True), ('file.hasProperty("status")', True), ('file.hasProperty("nincs")', False),
            ('file("Cél").hasProperty("Ora")', True), ('file("kep.png").hasProperty("Ora")', False),
            ('file.inFolder("A")', True), ('file.inFolder("/A/")', True), ('file.inFolder("B")', False),
            ('file.inFolder("")', True), ('file("B/Más.md").inFolder("B")', True), ('file.inFolder("A/B")', False),
            ('file("Cél").inFolder("A")', False),
            ("file.asLink()", Link("A/Jegyzet.md", None, "A/Jegyzet.md")),
            ('file.asLink("szöveg")', Link("A/Jegyzet.md", "szöveg", "A/Jegyzet.md")),
        ])

    def test_alma_fajl_kozvetlen_mezoi_this_nelkul(self):
        self.tabla_esetek([("file.name == \"Jegyzet.md\" && file.ext == \"md\"", True),
                           ("file.path.startsWith(\"A/\")", True), ("file.basename.length", 7)])

    def test_hibak(self):
        self.hibak(["file.hasLink()", "file.hasLink(1)", "file.hasTag()",
                    "file.nincs()", 'link("Cél").nincs()', "file.asLink(1, 2)", "file.hasProperty(null)"])


class ObjektumRegexTest(FuggvenyTest):
    def test_esetek(self):
        self.tabla_esetek([
            ("{}.isEmpty()", True), ('html(1)', Html("1")), ('file.inFolder(1)', False), ('[1,2].join(1)', "112"),
            ('/1/.matches(1)', True), ('{"a": 1}.isEmpty()', False), ('{"a": 1, "b": 2}.keys()', ["a", "b"]),
            ('{"a": 1, "b": 2}.values()', [1, 2]), ('{"a": 1}.a', 1), ('{"a": 1}["a"]', 1), ('{"a": 1}.nincs', None),
            ("file.properties.isEmpty()", False), ("note.isEmpty()", False), ("note.keys().length", 8),
            ('/abc/.matches("abcde")', True), ('/^abc$/.matches("abcde")', False), ('/ABC/i.matches("xabcx")', True),
            ('/a.c/.matches("a\\nc")', False), ('/a.c/s.matches("a\\nc")', True), ('/\\d+/.matches("a12")', True),
            ('/x/.matches("")', False),
        ])

    def test_hibak(self):
        self.hibak(["{}.nincs()", "{}.keys(1)", '/a/.matches()', '/a/.nincs()', "/(/", "/a/.matches([1])",
                    '"x".replace(/(/, "")'])

    def test_katasztrofalis_regex_idokorlatos(self):
        import time
        t0 = time.monotonic()
        with self.assertRaises(FutasHiba):
            ertek('/(a|aa)+$/.matches("' + "a" * 60 + 'b")', S, T)
        self.assertLess(time.monotonic() - t0, 3)


if __name__ == "__main__":
    unittest.main()
