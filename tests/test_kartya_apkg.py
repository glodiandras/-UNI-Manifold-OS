"""C23a: `.apkg` export és import (`modulok/kartya/apkg.py`, `html.py`; `docs/C23-TERV.md` 4. fejezet).

A kész-feltétel: export → import **ugyanazt a kártyahalmazt és állapotot** adja (a napló is). Mellette a csomag
elrendezése (LEGACY_2), egy teszten belül épített idegen séma-11 pakli (Basic, reversed, cloze, SM-2) és egy LATEST
(`collection.anki21b`, zstd + protobuf média) pakli importja. Álvaulton és ál-`var/`-ban."""
import json
import sqlite3
import tempfile
import unittest
import zipfile
from compression import zstd
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core import tanulas_db
from modulok.kartya import apkg, html, szinkron, utemezo
from modulok.kartya import formatum as f
from tests.helpers import alg_core, ir, tmpdir

T0 = datetime(2026, 10, 4, 10, 0, 0, tzinfo=timezone.utc)
MAPPA = "ATTCHMNTS - cards"


def _db_kartyak(cfg) -> dict[str, dict]:
    with tanulas_db.olvaso(cfg) as c:
        return {r["azon"]: dict(r) for r in c.execute("SELECT * FROM kartya")}


def _db_naplo(cfg) -> set[tuple]:
    with tanulas_db.olvaso(cfg) as c:
        return {tuple(r) for r in c.execute("SELECT kartya, mikor, jegy, ms FROM valasz WHERE visszavonva IS NULL")}


class KorutTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, _, self.v = alg_core(str(Path(self._t.name) / "a"))
        self.cfg2, _, _ = alg_core(str(Path(self._t.name) / "b"))
        self.sched = utemezo.utemezo(self.cfg, fuzz=False)
        kartyak = [
            f.Kartya("Mi a $q$ hányados?", "Az **egymást** követő tagok *hányadosa*:\n$$q = \\frac{a_{n+1}}{a_n}$$",
                     "c-00000001", "Mértani sorozat#^m-3f2a"),
            f.Kartya("Tanulásban?", "igen, `kód` is", "c-00000002", "Mértani sorozat#^m-3f2b"),
            f.Kartya("Ismétlésben?", "a < b & c > d", "c-00000003"),
            f.Kartya("Újratanulásban?", "kép: ![[abra.png]]", "c-00000004"),
            f.Kartya("Felfüggesztve?", "igen", "c-00000005"),
        ]
        ir(self.v, f"{MAPPA}/Mértani sorozat — kártyák.md", f.ir(kartyak, ["Mértani sorozat"]))
        ir(self.v, "abra.png", b"\x89PNG\r\n\x1a\nkep", "wb")
        szinkron.szinkron(self.cfg, most=T0)
        v = lambda azon, jegy, t: utemezo.valaszol(self.cfg, azon, jegy, ms=1234, most=t, sched=self.sched)  # noqa: E731
        v("c-00000002", 3, T0)                                          # tanulás, 2. lépés
        v("c-00000003", 4, T0)                                          # ismétlés
        v("c-00000003", 3, T0 + timedelta(days=5, minutes=7))
        v("c-00000004", 4, T0)
        v("c-00000004", 1, T0 + timedelta(days=9, hours=3))            # újratanulás
        v("c-00000005", 4, T0)
        v("c-00000001", 3, T0 + timedelta(hours=2))
        utemezo.visszavon(self.cfg, "c-00000001")                      # a visszavont válasz nem megy át
        with tanulas_db.iro(self.cfg) as c:
            c.execute("UPDATE kartya SET felfuggesztve = 1 WHERE azon = 'c-00000005'")
        self.cel = Path(self._t.name) / "ki" / "manifold.apkg"
        self.kartyak = apkg.gyujt(self.cfg)
        self.jel = apkg.export(self.cel, self.kartyak, most=T0 + timedelta(days=12), lepesszam=(2, 1),
                               media={"abra.png": self.v / "abra.png"})

    def test_kartyahalmaz_allapot_es_naplo_ugyanaz(self):
        pakli = apkg.beolvas(self.cel, (2, 1))
        self.assertEqual(pakli["kihagyva"], {})
        jel = apkg.importal(self.cfg2, pakli, most=T0 + timedelta(days=13))
        self.assertEqual((jel["uj"], jel["frissult"]), (5, 0))
        a, b = _db_kartyak(self.cfg), _db_kartyak(self.cfg2)
        self.assertEqual(set(a), set(b))
        for azon in a:
            for m in ("kerdes", "valasz", "forras", "felfuggesztve", "allapot"):
                self.assertEqual(b[azon][m], a[azon][m], f"{azon}.{m}")
            if a[azon]["allapot"] != utemezo.UJ:              # az új kártyának nincs ütemezett állapota
                for m in utemezo.MEZOK:
                    self.assertEqual(b[azon][m], a[azon][m], f"{azon}.{m}")
            self.assertEqual(b[azon]["eredet"], "apkg")
        self.assertEqual({(x[0], x[1], x[2], x[3]) for x in _db_naplo(self.cfg2)}, _db_naplo(self.cfg))
        self.assertEqual(a["c-00000003"]["allapot"], 2)
        self.assertEqual(a["c-00000004"]["allapot"], 3)
        self.assertEqual(a["c-00000002"]["allapot"], 1)

    def test_ujraimport_nem_duplikal(self):
        pakli = apkg.beolvas(self.cel, (2, 1))
        apkg.importal(self.cfg2, pakli)
        jel = apkg.importal(self.cfg2, apkg.beolvas(self.cel, (2, 1)))
        self.assertEqual((jel["uj"], jel["frissult"], jel["valtozatlan"], jel["naplo_uj"]), (0, 0, 5, 0))

    def test_a_frissebb_allapot_nyer(self):
        apkg.importal(self.cfg2, apkg.beolvas(self.cel, (2, 1)))
        s2 = utemezo.utemezo(self.cfg2, fuzz=False)
        utemezo.valaszol(self.cfg2, "c-00000003", 3, most=T0 + timedelta(days=40), sched=s2)
        frissebb = _db_kartyak(self.cfg2)["c-00000003"]
        jel = apkg.importal(self.cfg2, apkg.beolvas(self.cel, (2, 1)))
        self.assertEqual(jel["frissult"], 0)
        self.assertEqual(_db_kartyak(self.cfg2)["c-00000003"]["utolso"], frissebb["utolso"])

    def test_csomag_elrendezese(self):
        with zipfile.ZipFile(self.cel) as z:
            self.assertEqual(z.namelist()[:3], ["meta", "collection.anki21", "collection.anki2"])
            self.assertEqual(z.read("meta"), b"\x08\x02")
            self.assertEqual(z.getinfo("meta").compress_type, zipfile.ZIP_STORED)
            self.assertEqual(json.loads(z.read("media")), {"0": "abra.png"})
            self.assertEqual(z.read("0"), b"\x89PNG\r\n\x1a\nkep")
            with tempfile.TemporaryDirectory() as tmp:
                for nev, kartya in (("collection.anki21", 5), ("collection.anki2", 0)):
                    p = Path(tmp) / nev
                    p.write_bytes(z.read(nev))
                    c = sqlite3.connect(p)
                    try:
                        self.assertEqual(c.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                        self.assertEqual(c.execute("SELECT ver FROM col").fetchone()[0], 11)
                        self.assertEqual(c.execute("SELECT COUNT(*) FROM cards").fetchone()[0], kartya)
                        conf = json.loads(c.execute("SELECT conf FROM col").fetchone()[0])
                        self.assertEqual((conf["schedVer"], conf["sched2021"]), (2, True))
                        modell = next(iter(json.loads(c.execute("SELECT models FROM col").fetchone()[0]).values()))
                        self.assertEqual([m["name"] for m in modell["flds"]], ["Front", "Back", "Forrás"])
                        if kartya:
                            guid, flds, csum = c.execute("SELECT guid, flds, csum FROM notes ORDER BY id").fetchone()
                            self.assertEqual(guid, "mosc-00000001")
                            self.assertEqual(flds.split("\x1f")[0], "Mi a \\(q\\) hányados?")
                            self.assertEqual(csum, int(__import__("hashlib").sha1("Mi a \\(q\\) hányados?".encode())
                                                       .hexdigest()[:8], 16))
                            queue = dict(c.execute("SELECT n.guid, c.queue FROM cards c JOIN notes n ON n.id = c.nid"))
                            self.assertEqual(queue, {"mosc-00000001": 0, "mosc-00000002": 1, "mosc-00000003": 2,
                                                     "mosc-00000004": 1, "mosc-00000005": -1})
                            data = json.loads(c.execute("SELECT c.data FROM cards c JOIN notes n ON n.id = c.nid "
                                                        "WHERE n.guid = 'mosc-00000003'").fetchone()[0])
                            self.assertEqual(set(data), {"s", "d", "dr", "lrt"})
                            self.assertEqual(c.execute("SELECT COUNT(*) FROM revlog").fetchone()[0], 6)
                    finally:
                        c.close()
        self.assertEqual((self.jel["kartyak"], self.jel["media"], self.jel["naplo"]), (5, 1, 6))

    def test_beolvas_semmit_nem_ir(self):
        apkg.beolvas(self.cel)
        self.assertFalse(tanulas_db.ut(self.cfg2).exists())


def _pb_varint(x: int) -> bytes:
    ki = bytearray()
    while True:
        b, x = x & 0x7F, x >> 7
        ki.append(b | (0x80 if x else 0))
        if not x:
            return bytes(ki)


def _pb(szam: int, ertek) -> bytes:
    if isinstance(ertek, int):
        return _pb_varint(szam << 3) + _pb_varint(ertek)
    ertek = ertek.encode() if isinstance(ertek, str) else ertek
    return _pb_varint(szam << 3 | 2) + _pb_varint(len(ertek)) + ertek


def _idegen_gyujtemeny(ut: Path, v18: bool = False) -> None:
    """Egy „valódi” Anki-gyűjtemény a teszthez: Basic, Basic (and reversed), Cloze; FSRS-es és SM-2-es kártya."""
    crt = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp())
    c = sqlite3.connect(ut)
    c.create_collation("unicase", lambda a, b: (a.casefold() > b.casefold()) - (a.casefold() < b.casefold()))
    c.executescript(apkg.SEMA11)
    modellek = {"10": {"name": "Basic", "type": 0, "flds": [{"name": "Front", "ord": 0}, {"name": "Back", "ord": 1}]},
                "11": {"name": "Basic (and reversed card)", "type": 0,
                       "flds": [{"name": "Front", "ord": 0}, {"name": "Back", "ord": 1}]},
                "12": {"name": "Cloze", "type": 1, "flds": [{"name": "Text", "ord": 0}, {"name": "Extra", "ord": 1}]}}
    paklik = {"1": {"name": "Default"}, "5": {"name": "Történelem::1848"}}
    if v18:
        c.executescript("""
            CREATE TABLE notetypes (id integer NOT NULL PRIMARY KEY, name text NOT NULL COLLATE unicase,
              mtime_secs integer NOT NULL, usn integer NOT NULL, config blob NOT NULL);
            CREATE TABLE fields (ntid integer NOT NULL, ord integer NOT NULL, name text NOT NULL COLLATE unicase,
              config blob NOT NULL, PRIMARY KEY (ntid, ord)) without rowid;
            CREATE TABLE decks (id integer PRIMARY KEY NOT NULL, name text NOT NULL COLLATE unicase,
              mtime_secs integer NOT NULL, usn integer NOT NULL, common blob NOT NULL, kind blob NOT NULL);""")
        for mid, m in modellek.items():
            c.execute("INSERT INTO notetypes VALUES (?,?,0,0,?)", (int(mid), m["name"], _pb(1, m["type"]) + _pb(3, ".card{}")))
            for fl in m["flds"]:
                c.execute("INSERT INTO fields VALUES (?,?,?,x'')", (int(mid), fl["ord"], fl["name"]))
        for did, d in paklik.items():
            c.execute("INSERT INTO decks VALUES (?,?,0,0,x'',x'')", (int(did), d["name"].replace("::", "\x1f")))
        c.execute("INSERT INTO col VALUES (1,?,0,0,18,0,0,0,'','','','','')", (crt,))
    else:
        c.execute("INSERT INTO col VALUES (1,?,0,0,11,0,0,0,'{}',?,?,'{}','{}')", (crt, json.dumps(modellek), json.dumps(paklik)))
    c.executemany("INSERT INTO notes VALUES (?,?,?,0,0,'',?,'',0,0,'')", [
        (1, "Gx#1", 10, "Mikor volt <b>Mohács</b>?\x1f1526<br>augusztus 29."),
        (2, "Gx#2", 11, "Petőfi\x1fköltő"),
        (3, "Gx#3", 12, "{{c1::Kossuth}} kormányzó\x1f"),
        (4, "Gx#4", 10, "SM-2 kérdés\x1fválasz <img src=\"kep.png\">")])
    lrt = crt + 100 * 86400 + 3600
    c.executemany("INSERT INTO cards VALUES (?,?,5,?,0,0,?,?,?,?,2500,1,0,0,0,0,0,?)", [
        (11, 1, 0, 2, 2, 110, 10, json.dumps({"s": 12.5, "d": 4.25, "dr": 0.9, "lrt": lrt})),
        (21, 2, 0, 0, 0, 1, 0, ""), (22, 2, 1, 0, 0, 2, 0, ""),
        (31, 3, 0, 0, 0, 3, 0, ""),
        (41, 4, 0, 2, 2, 120, 15, "")])
    c.executemany("INSERT INTO revlog VALUES (?,?,0,?,1,0,2500,?,1)", [
        (lrt * 1000, 11, 3, 4200), (lrt * 1000 - 86400000, 41, 0, 0), (lrt * 1000 - 3600000, 41, 2, 900)])
    c.commit()
    c.close()


class IdegenPakliTest(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.addCleanup(self._t.cleanup)
        self.cfg, _, _ = alg_core(self._t.name)
        self.tmp = Path(self._t.name)

    def ellenoriz(self, pakli: dict) -> None:
        k = {(x["guid"], x["ord"]): x for x in pakli["kartyak"]}
        self.assertEqual(set(k), {("Gx#1", 0), ("Gx#2", 0), ("Gx#2", 1), ("Gx#4", 0)})
        self.assertEqual(pakli["kihagyva"], {"cloze": 1})
        self.assertEqual((k[("Gx#1", 0)]["kerdes"], k[("Gx#1", 0)]["valasz"]), ("Mikor volt **Mohács**?", "1526\naugusztus 29."))
        self.assertEqual((k[("Gx#2", 1)]["kerdes"], k[("Gx#2", 1)]["valasz"]), ("költő", "Petőfi"))     # reversed
        self.assertEqual(k[("Gx#4", 0)]["valasz"], "válasz ![[kep.png]]")
        a = k[("Gx#1", 0)]["allapot"]
        lrt = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=100, hours=1)
        self.assertEqual((a["allapot"], a["stabilitas"], a["nehezseg"], a["utolso"]), (2, 12.5, 4.25, lrt.isoformat()))
        self.assertEqual(a["esedekes"], (datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=110, hours=1)).isoformat())
        self.assertEqual(k[("Gx#4", 0)]["allapot"]["allapot"], utemezo.UJ)            # SM-2: nincs s/d → új
        self.assertEqual([n["jegy"] for n in k[("Gx#4", 0)]["naplo"]], [2])            # a 0-s (kézi) sor kimarad
        self.assertEqual(k[("Gx#1", 0)]["pakli"], "Történelem::1848")
        self.assertIsNone(k[("Gx#1", 0)]["azon"])

    def test_legacy2_meta_nelkul(self):
        gy = self.tmp / "gy.anki21"
        _idegen_gyujtemeny(gy)
        csomag = self.tmp / "idegen.apkg"
        with zipfile.ZipFile(csomag, "w") as z:
            z.write(gy, "collection.anki21")
            z.writestr("media", json.dumps({"0": "kep.png"}))
            z.writestr("0", b"kep")
        pakli = apkg.beolvas(csomag)
        self.assertEqual(pakli["verzio"], apkg.LEGACY2)
        self.assertEqual(pakli["media"], ["kep.png"])
        self.ellenoriz(pakli)

    def test_latest_zstd_protobuf(self):
        gy = self.tmp / "gy.anki21b"
        _idegen_gyujtemeny(gy, v18=True)
        csomag = self.tmp / "uj.apkg"
        media = _pb(1, _pb(1, "kep.png") + _pb(2, 3) + _pb(3, b"\x00" * 20))
        with zipfile.ZipFile(csomag, "w") as z:
            z.writestr("meta", b"\x08\x03")
            z.writestr("collection.anki21b", zstd.compress(gy.read_bytes()))
            z.writestr("collection.anki2", b"")
            z.writestr("media", zstd.compress(media))
            z.writestr("0", zstd.compress(b"kep"))
        pakli = apkg.beolvas(csomag)
        self.assertEqual(pakli["verzio"], apkg.LATEST)
        self.assertEqual(pakli["media"], ["kep.png"])
        self.ellenoriz(pakli)

    def test_idegen_import_uj_azonosito_es_idempotens(self):
        gy = self.tmp / "gy.anki21"
        _idegen_gyujtemeny(gy)
        csomag = self.tmp / "idegen.apkg"
        with zipfile.ZipFile(csomag, "w") as z:
            z.writestr("meta", b"\x08\x02")
            z.write(gy, "collection.anki21")
        pakli = apkg.beolvas(csomag)
        jel = apkg.importal(self.cfg, pakli, most=T0)
        self.assertEqual((jel["uj"], jel["naplo_uj"]), (4, 2))
        azonositok = {(k["guid"], k["ord"]): k["azon"] for k in pakli["kartyak"]}
        self.assertTrue(all(f.AZON_RE.fullmatch(a) for a in azonositok.values()))
        self.assertEqual(len(set(azonositok.values())), 4)
        masodik = apkg.beolvas(csomag)
        jel = apkg.importal(self.cfg, masodik, most=T0)
        self.assertEqual((jel["uj"], jel["naplo_uj"]), (0, 0))
        self.assertEqual({(k["guid"], k["ord"]): k["azon"] for k in masodik["kartyak"]}, azonositok)
        szoveg = f.ir([f.Kartya(k["kerdes"].replace("\n", " "), k["valasz"], k["azon"]) for k in masodik["kartyak"]])
        self.assertEqual(len(f.ervenyes(f.elemez(szoveg))), 4)                    # a kísérőjegyzet megírható (C23b)

    def test_ismeretlen_verzio(self):
        csomag = self.tmp / "rossz.apkg"
        with zipfile.ZipFile(csomag, "w") as z:
            z.writestr("meta", b"")
        with self.assertRaises(apkg.ApkgHiba):
            apkg.beolvas(csomag)


class HtmlTest(unittest.TestCase):
    PELDAK = ["Mi a $q$ hányados?", "**félkövér** és *dőlt*, `kód <b>`", "a < b & c > d",
              "két\nsor", "$$a\nb$$", "kép: ![[abra.png]]", "x ^2 és 3*4*5"]

    def test_korut_a_reszhalmazon(self):
        for md in self.PELDAK:
            self.assertEqual(html.html_md(html.md_html(md)), md, md)

    def test_md_html(self):
        self.assertEqual(html.md_html("Mi a $q$?"), "Mi a \\(q\\)?")
        self.assertEqual(html.md_html("$$x<1$$"), "\\[x&lt;1\\]")
        self.assertEqual(html.md_html("[[Cél#fej|szép]] és [[mappa/Másik]]"), "szép és Másik")
        self.assertEqual(html.md_html("![[al/kep.png|200]]"), '<img src="kep.png">')

    def test_html_md_anki_alakok(self):
        self.assertEqual(html.html_md("első<div>második</div><div><span style='x'>harmadik</span></div>"),
                         "első\nmásodik\nharmadik")
        self.assertEqual(html.html_md("a&nbsp;b &amp; <strong>c</strong>"), "a b & **c**")

    def test_kepek(self):
        self.assertEqual(html.kepek("![[a.png]] és ![[b.png|30]] ![[a.png]]"), ["a.png", "b.png"])


if __name__ == "__main__":
    unittest.main()
