"""C31 (2. és 7. pont; 2. audit T066): az átállás Obsidian-próbavaultjai és az ellenőrző lista — a felhasználó kezére.

    PYTHONPATH=. <venv python> -B tests/kezi/atallas_probavault.py <üres könyvtár> [--notion]

A könyvtárba (a valódi vaulthoz nem nyúl; a `{tmp}` alatt ajánlott, a megnyitás és a törlés a felhasználóé) öt
próbavault kerül, mindegyik saját `.obsidian` mappával (Obsidian: „Open folder as vault”), és a gyökérben az
`ELLENORZO.md` (lépésenként: mit nyiss meg, mit nézz, mit írj vissza):

  1 - C31 próbavault/   30 jegyzet a 2.0 saját íróival (a tulajdonság-író `_sorok`, a napi jegyzet váza, a PDF-kiemelés,
                        a kártya-, kvíz- és összefoglaló-formátum, a gyakorlás-beágyazás, a `plot` blokk), 5 canvas, egy
                        JS-paritás `.base`, a sablon-, YAML-, md-link-, új-jegyzet-, blokkazonosító- és feloldás-esetek
                        (T155–T160, T072, a statikus olvasás eltérései); a K10, K17, K25 anyaga.
  2 - K04 Link-próba/   a C10.6 P00–P14 próbája (`obsidian_link_proba.FAJLOK`) — a maszk-kapcsolók és a `%%` kérdése.
  3 - K04 Notion-próba/ a C09 tíz esete (a vitest írja; csak `--notion` mellett, mert a felület tesztkészletét futtatja).
  4 - K11 Bases/        a C12 paritás-próbavaultja (`bazis_proba.general`: 40 jegyzet, 5 `.base`, 9 nézet) — K11, K12.
  5 - K42 Forrás-mappa/ a K42 próbája (`k42_proba.general`).

A generátor determinisztikus (rögzített dátumok), csak a megadott könyvtárba ír, és a gépi teszt
(`tests/test_atallas_probavault.py`) álkönyvtárba futtatja.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import zlib
from datetime import datetime
from pathlib import Path

KEZI = Path(__file__).resolve().parent
REPO = KEZI.parents[1]
for p in (str(REPO), str(KEZI)):
    if p not in sys.path:
        sys.path.insert(0, p)

from core import gyakorlas, naplo, pdfkiemeles, sablon, tulajdonsagok  # noqa: E402
from modulok.grafikon import formatum as plot  # noqa: E402
from modulok.kartya import formatum as kartya  # noqa: E402
from modulok.kviz import formatum as kviz  # noqa: E402
from modulok.osszefoglalas import formatum as ossz  # noqa: E402

FO = "1 - C31 próbavault"
NAP = datetime(2026, 10, 7, 9, 30)

# ---------------------------------------------------------------- segédek


def _ir(gyoker: Path, rp: str, tartalom) -> None:
    p = gyoker / rp
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(tartalom, bytes):
        p.write_bytes(tartalom)
    else:
        p.write_text(tartalom, encoding="utf-8")


def _obsidian(gyoker: Path, app: dict | None = None, **egyeb) -> None:
    _ir(gyoker, ".obsidian/app.json", json.dumps(app or {"alwaysUpdateLinks": False}, ensure_ascii=False, indent=2))
    for nev, adat in egyeb.items():
        _ir(gyoker, f".obsidian/{nev}.json", json.dumps(adat, ensure_ascii=False, indent=2))


def _fm(*parok) -> str:
    """Frontmatter a 2.0 tulajdonság-írójával (`tulajdonsagok._sorok`: ugyanaz, amit a panel ír — K10)."""
    sorok = []
    for kulcs, ertek in parok:
        sorok += tulajdonsagok._sorok(kulcs, ertek)
    return "---\n" + "\n".join(sorok) + "\n---\n"


def _png() -> bytes:
    """1×1-es, érvényes PNG."""
    import struct

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00\x5a\x18\x28")) + chunk(b"IEND", b""))


def _pdf(oldalak: list[str]) -> bytes:
    """Kis, érvényes PDF oldalanként egy szövegsorral (a K25 kiemelés-próbájához; a `#page=N` link célja)."""
    objektumok = ["<< /Type /Catalog /Pages 2 0 R >>", None, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for szoveg in oldalak:
        tartalom = f"BT /F1 18 Tf 72 720 Td ({szoveg}) Tj ET".encode("latin-1")
        objektumok.append(f"<< /Length {len(tartalom)} >>\nstream\n{tartalom.decode('latin-1')}\nendstream")
        objektumok.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> "
                          f"/Contents {len(objektumok)} 0 R >>")
        kids.append(f"{len(objektumok)} 0 R")
    objektumok[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"
    ki, eltolas = bytearray(b"%PDF-1.4\n"), []
    for i, o in enumerate(objektumok, 1):
        eltolas.append(len(ki))
        ki += f"{i} 0 obj\n{o}\nendobj\n".encode("latin-1")
    xref = len(ki)
    ki += f"xref\n0 {len(objektumok) + 1}\n0000000000 65535 f \n".encode()
    for e in eltolas:
        ki += f"{e:010d} 00000 n \n".encode()
    ki += f"trailer\n<< /Size {len(objektumok) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(ki)


# ---------------------------------------------------------------- 1. a fő próbavault

MAPPA = "M01 - Matematika"
TORI = "T01 - Történelem"


def _jegyzetek() -> dict[str, str]:
    """A 30 jegyzet (a 2.0 írói és a vault sémája szerint) — a fő próbavault törzse."""
    j: dict[str, str] = {}
    norm = lambda tags, src=None, nn=None, canvas=None: _fm(("Tags", tags), ("Source", src or []), ("Status", None),  # noqa: E731
                                                             ("NN", nn or []), ("Canvas", canvas))
    # 01–06: alap jegyzetek linkekkel, fejezetekkel, blokkokkal
    j[f"{MAPPA}/01 - Mértani sorozat.md"] = norm(["Mathematics"], nn=['[[02 - Számtani sorozat]]'], canvas="[[Sorozatok.canvas]]") + (
        "\n# Mértani sorozat\n\nA mértani sorozatban a szomszédos tagok hányadosa állandó. ^m-def1\n\n"
        "## Képlet\n\n$$a_n = a_1 \\cdot q^{n-1}$$\n\n```plot\nx in [-1, 6]\ny in [-1, 40]\ny = 2^x  \"2^x\"\n```\n\n"
        "## Összeg\n\nAz első n tag összege $S_n = a_1 \\frac{q^n - 1}{q - 1}$, ha $q \\ne 1$. ^m-osszeg\n\n"
        "Lásd még: [[02 - Számtani sorozat#Képlet]] és [[03 - Határérték|a határérték]].\n\n"
        f"{gyakorlas.FEJEZET}\n\n{gyakorlas.beagyazo_sor('01 - Mértani sorozat — kártyák')}\n"
        f"{gyakorlas.beagyazo_sor('Mértani sorozat — Kvíz 2026-10-07 0930')}\n")
    j[f"{MAPPA}/02 - Számtani sorozat.md"] = norm(["Mathematics"], nn=['[[01 - Mértani sorozat]]']) + (
        "\n# Számtani sorozat\n\n## Képlet\n\n$a_n = a_1 + (n-1)d$\n\n> [!note] Megjegyzés\n> A különbség állandó. ^m-kul\n")
    j[f"{MAPPA}/03 - Határérték.md"] = norm(["Mathematics"]) + (
        "\n# Határérték\n\n| Sorozat | Határérték |\n|---|---|\n| $1/n$ | 0 |\n| $(1+1/n)^n$ | $e$ |\n\n"
        "```python\n# kódban álló link: [[Nem link]]\nprint('x')\n```\n\n- [ ] Gyakorolni 📅 2026-10-10\n- [x] Elolvasni ✅ 2026-10-06\n")
    j[f"{MAPPA}/04 - Függvények.md"] = norm(["Mathematics"]) + (
        "\n# Függvények\n\n$$f(x) = x^2 - 4x + 3$$\n\n```plot\nx in [-2, 6]\ny in [-2, 8]\ny = x^2 - 4*x + 3  \"f\"\n"
        "y = 0\n```\n\nA zérushelyek: 1 és 3. ![[abra.png]]\n")
    j[f"{TORI}/01 - Ókori Róma.md"] = norm(["History"], src=["[[Tankönyv.pdf#page=1]]"]) + (
        "\n# Ókori Róma\n\nRóma alapítása a hagyomány szerint i. e. 753. ^t-alapitas\n\n%%Egysoros megjegyzés: [[Rejtett link]]%%\n\n"
        "%%\nTöbb bekezdéses megjegyzés első bekezdése.\n\nMásodik bekezdés [[Rejtett link 2]].\n%%\n\n"
        "Lásd: [[02 - Görög poliszok]], ![[Tankönyv.pdf#page=2]].\n")
    j[f"{TORI}/02 - Görög poliszok.md"] = norm(["History"]) + (
        "\n# Görög poliszok\n\n- Athén #demokrácia\n  - Periklész\n- Spárta #katonai/állam\n\n1. első\n2. második\n")
    # 07–10: K10 — a panel írói minden típussal
    j["K10 - Tulajdonságok/Típusok.md"] = _fm(
        ("Tags", ["Mathematics"]), ("Source", ["[[01 - Mértani sorozat]]", "[[Tankönyv.pdf#page=2]]"]), ("Status", None),
        ("NN", ["[[02 - Számtani sorozat]]"]), ("Canvas", "[[Sorozatok.canvas]]"), ("Datum", "2026-10-07"),
        ("Idopont", "2026-10-07T09:30"), ("Kesz", True), ("Pontszam", 4.5), ("Uj tulajdonsag", "szöveg értékkel"),
        ("Lista", ["egy", "kettő", "három"])) + "\n# Típusok\n\nA K10 próbája: a frontmatter a 2.0 tulajdonság-írójával készült.\n"
    j["K10 - Tulajdonságok/Ures es idezett.md"] = _fm(
        ("Tags", ["History"]), ("Source", []), ("Status", None), ("NN", []), ("Canvas", None),
        ("Szoveg", "a: b"), ("Hashtag", "# nem megjegyzés"), ("Szamszeru", "123"), ("Igaz", "true")) + "\n# Üres és idézett\n"
    # T157 — más olvasónak szám/bool: 2.0 idézett vs nyers alak egymás mellett
    t157 = ["0x1F", "0o7", "0b101", "1_000", "yes", "No", "on", "10:30"]
    j["T157 - YAML skalárok/Idézett (2.0).md"] = _fm(*[(f"Ertek{i + 1}", s) for i, s in enumerate(t157)]) + (
        "\n# Idézett (2.0)\n\nA 2.0 írója (C31) ezeket idézőjelbe teszi; a Tulajdonságok nézetben mind **szöveg** legyen.\n")
    j["T157 - YAML skalárok/Nyers (összevetés).md"] = (
        "---\n" + "\n".join(f"Ertek{i + 1}: {s}" for i, s in enumerate(t157)) + "\n---\n\n# Nyers (összevetés)\n\n"
        "Kézzel írt, idézőjel nélküli alak: írd fel, melyik érték lesz **szám** vagy **jelölő** a Tulajdonságok nézetben.\n")
    # K17 — napi jegyzet (a 2.0 beépített váza, kiértékelve)
    havi = "X01 - Napló & To-Do/2026-10/2026-10.canvas"
    j["X01 - Napló & To-Do/2026-10/Napló/2026-10-07.md"] = sablon.kiertekel(
        naplo.alapvaz("2026-10.canvas"), "2026-10-07", NAP).szoveg + "Mai bejegyzés.\n"
    # T156 — sablon: a 2.0 kimenete ugyanarra a napra (a sablon maga a _Template alatt)
    j["_Template/C31 sablonpróba.md"] = ("# {{title}}\n\nDATE: {{DATE}}\nÜres formátum: {{date:}}\nRövid hónap: {{date:MMM}}\n"
                                         "Szóközös: {{ date }}\nIdő: {{time:HH.mm}}\nKurzor: {{cursor}}\n")
    j["T156 - Sablon/A 2.0 kimenete (2026-10-07 09.30).md"] = (
        "# A 2.0 kimenete\n\nA `_Template/C31 sablonpróba` a 2.0 motorjával, 2026-10-07 09:30-ra (a dátum a te napodon más):\n\n"
        "```text\n" + sablon.kiertekel(j["_Template/C31 sablonpróba.md"], "Sablonpróba", NAP).szoveg + "```\n")
    # T072 + statikus olvasás: md-linkek és feloldási esetek
    j["Linkek/Cél X.md"] = "# Cél X\n\n## Fej\n\nA cél.\n"
    j["Linkek/a%23b.md"] = "# a%23b\n\nKülönös név: százalékjel a fájlnévben.\n"
    j["Linkek/md-linkek.md"] = (
        "# md-linkek (T072, 36. döntés)\n\n"
        "1. kódolt: [egy](C%C3%A9l%20X.md)\n2. burok: [kettő](<Cél X.md>)\n3. horgonnyal: [három](C%C3%A9l%20X.md#Fej)\n"
        "4. kódolt százalék a névben: [négy](a%2523b.md)\n5. relatív: [öt](../Linkek/C%C3%A9l%20X.md)\n"
        "6. séma: [hat](obsidian://open?vault=x)\n7. hibás kódolás: [hét](C%C3l.md)\n8. nyers szóköz: [nyolc](Cél X.md)\n")
    j["Feloldás/Rövid/Cél.md"] = "# Rövid/Cél (rövidebb út, más kis-nagybetű)\n"
    j["Feloldás/Hosszabb mappa neve/cél.md"] = "# Hosszabb mappa neve/cél (pontos kis-nagybetű)\n"
    j["Feloldás/yx/A.md"] = "# yx/A\n"
    j["Feloldás/Források/Kis-nagybetű.md"] = "# K\n\n[[cél]]\n"
    j["Feloldás/Források/Szegmens.md"] = "# S\n\n[[x/A]]\n"
    j["Feloldás/Források/Relatív.md"] = "# R\n\n[[../Rövid/Cél]] és [[./Testvér]]\n"
    j["Feloldás/Források/Testvér.md"] = "# Testvér\n"
    # T158 — feloldatlan linkek (kattintásra új jegyzet)
    j["Új jegyzet/Kattints.md"] = ("# Kattints (T158)\n\n- [[m01 - matematika/Új útvonalas]]\n- [[Nem létező mappa/Al/Új mélyen]]\n"
                                    "- [[Csak név (új)]]\n")
    # T160 — blokkazonosítók nem szöveges blokkban
    j["Blokkok/Nem szöveges.md"] = (
        "# Blokkazonosító nem szöveges blokkban (T160)\n\n```js\nconst a = 1;\n```\n\n^b-kod\n\n"
        "> [!example] Callout kódkerítéssel a végén\n> ```\n> x = 1\n> ```\n\n^b-callout\n\n"
        "| a | b |\n|---|---|\n| 1 | 2 |\n\n^b-tabla\n\n$$\nx^2\n$$\n\n^b-keplet\n\n"
        "- listaelem szöveggel ^b-lista\n- ```\n  kód a listaelemben\n  ```\n")
    j["Blokkok/Hivatkozó.md"] = ("# Hivatkozó\n\n- [[Nem szöveges#^b-kod]]\n- [[Nem szöveges#^b-callout]]\n- [[Nem szöveges#^b-tabla]]\n"
                                  "- [[Nem szöveges#^b-keplet]]\n- [[Nem szöveges#^b-lista]]\n")
    # T161 — HTML-konténer és lezáratlan kerítés
    j["Blokkok/HTML és nyitott kerítés.md"] = (
        "# HTML-konténer\n\n<details>\n<summary>Lenyitható</summary>\n\nBelső bekezdés.\n\n</details>\n\n"
        "Utána álló bekezdés.\n\n```\nlezáratlan kerítés a fájl végéig\n")
    # T155 — Bases JS-paritás (a .base külön)
    for nev, kezd, veg, a, b, ab in (("Tavasz", "2026-03-28", "2026-03-30", 5, 2, 99), ("Ősz", "2026-10-24", "2026-10-26", 7, 3, 99),
                                     ("Nyár", "2026-07-01", "2026-07-03", 1, 1, 99)):
        j[f"JS-paritás/{nev}.md"] = (f"---\nKezd: {kezd}\nVeg: {veg}\na: {a}\nb: {b}\na-b: {ab}\nTized: 0.1\n---\n\n# {nev}\n")
    return j


JS_BASE = """filters:
  and:
    - file.inFolder("JS-paritás")
formulas:
  orak: (Veg - Kezd) / 3600000
  kotojel: a-b
  tized_30: Tized.toFixed(30)
  zona: Kezd.format("YYYY-MM-DD Z ZZ")
views:
  - type: table
    name: JS
    order:
      - file.name
      - formula.orak
      - formula.kotojel
      - formula.tized_30
      - formula.zona
    sort:
      - property: file.name
        direction: ASC
"""

JS_VART = {   # a 2.0 kiértékelője szerint (TZ = Europe/Budapest)
    "Nyár": {"orak": 48, "kotojel": 99, "zona": "2026-07-01 +02:00 +0200"},
    "Tavasz": {"orak": 47, "kotojel": 99, "zona": "2026-03-28 +01:00 +0100"},
    "Ősz": {"orak": 49, "kotojel": 99, "zona": "2026-10-24 +02:00 +0200"},
    "*": {"tized_30": "0.100000000000000005551115123126"},
}


def _canvasok() -> dict[str, str]:
    def c(nodes, edges=()):
        return json.dumps({"nodes": nodes, "edges": list(edges)}, ensure_ascii=False, indent="\t") + "\n"
    return {
        "Sorozatok.canvas": c([
            {"id": "a1", "type": "file", "file": f"{MAPPA}/01 - Mértani sorozat.md", "x": 0, "y": 0, "width": 400, "height": 300},
            {"id": "a2", "type": "file", "file": f"{MAPPA}/02 - Számtani sorozat.md", "subpath": "#Képlet", "x": 500, "y": 0,
             "width": 400, "height": 300, "color": "4"},
            {"id": "a3", "type": "text", "text": "Összevetés: [[01 - Mértani sorozat]] ↔ [[02 - Számtani sorozat]]\n\n**félkövér**",
             "x": 0, "y": 400, "width": 400, "height": 160}],
            [{"id": "e1", "fromNode": "a1", "fromSide": "right", "toNode": "a2", "toSide": "left", "label": "rokon"}]),
        "Színek.canvas": c([{"id": f"s{i}", "type": "text", "text": f"Szín {i}", "x": 120 * i, "y": 0, "width": 100, "height": 60,
                              "color": str(i)} for i in range(1, 7)]
                           + [{"id": "s7", "type": "text", "text": "Egyedi szín", "x": 0, "y": 100, "width": 100, "height": 60,
                               "color": "#5a1828"}]),
        "Csoport.canvas": c([
            {"id": "g1", "type": "group", "label": "Történelem", "x": -20, "y": -20, "width": 900, "height": 400},
            {"id": "g2", "type": "file", "file": f"{TORI}/01 - Ókori Róma.md", "x": 0, "y": 0, "width": 400, "height": 300},
            {"id": "g3", "type": "file", "file": "Tankönyv.pdf", "x": 450, "y": 0, "width": 400, "height": 300}]),
        "Linkek.canvas": c([
            {"id": "l1", "type": "link", "url": "https://obsidian.md", "x": 0, "y": 0, "width": 400, "height": 300},
            {"id": "l2", "type": "file", "file": "abra.png", "x": 450, "y": 0, "width": 200, "height": 200},
            {"id": "l3", "type": "text", "text": "Kódban nem link: `[[Nem link]]`; link: [[Linkek/Cél X]]",
             "x": 0, "y": 350, "width": 400, "height": 100}],
            [{"id": "e2", "fromNode": "l3", "toNode": "l1", "toEnd": "none", "color": "1"}]),
        "X01 - Napló & To-Do/2026-10/2026-10.canvas": c([
            {"id": "n1", "type": "file", "file": "X01 - Napló & To-Do/2026-10/Napló/2026-10-07.md", "x": 0, "y": 0,
             "width": 400, "height": 300}]),
    }


def _kiseroek(j: dict[str, str]) -> dict[str, str]:
    """A kártya-, kvíz- és összefoglaló-kísérőjegyzet a 2.0 formátum-moduljaival (45., 48., 49. döntés)."""
    forras = f"{MAPPA}/01 - Mértani sorozat"
    k = kartya.ir([kartya.Kartya("Mi állandó a mértani sorozatban?", "A szomszédos tagok hányadosa.", azon="c-1a2b3c4d",
                                 forras="01 - Mértani sorozat#^m-def1"),
                   kartya.Kartya("Mennyi az első n tag összege?", "$S_n = a_1 \\frac{q^n - 1}{q - 1}$ (ha $q \\ne 1$)",
                                 azon="c-5e6f7a8b", forras="01 - Mértani sorozat#^m-osszeg")],
                  source=[forras], modell="(próba)", keszult="2026-10-07 0930")
    q = kviz.Kviz(azon="KVIZ-20261007-093000-c31abc", forras=forras, cim="Mértani sorozat", modell="(próba)",
                  keszult="2026-10-07 0930", kerdesek=[
                      kviz.Kerdes("k1", "Mi állandó a mértani sorozatban?",
                                  ["A különbség", "A hányados", "Az összeg", "A szorzat"], 1,
                                  magyarazat="A definíció szerint a hányados.",
                                  idezet="A mértani sorozatban a szomszédos tagok hányadosa állandó.", horgony="^m-def1")])
    o = ossz.Osszefoglalo(azon="OSSZ-20261007-093000-c31abc", szint="jegyzet", forrasok=[forras], cim="Mértani sorozat",
                          modell="(próba)", keszult="2026-10-07 0930", allitasok=[
                              ossz.Allitas("A szomszédos tagok hányadosa állandó.", ossz.Horgony(forras, "^m-def1"),
                                           "A mértani sorozatban a szomszédos tagok hányadosa állandó.")])
    return {
        "ATTCHMNTS - cards/01 - Mértani sorozat — kártyák.md": k,
        f"ATTCHMNTS - quizes/{kviz.fajlnev(q)}.md": kviz.ir(q),
        "ATTCHMNTS - summaries/01 - Mértani sorozat — összefoglaló.md": ossz.ir(o),
    }


def _kiemelesek() -> tuple[str, str]:
    """K25: a 2.0 PDF-kiemelés-fájlja (a `core/pdfkiemeles` vázával és beszúrásával), két oldalon egy-egy kiemeléssel."""
    pdf = "Tankönyv.pdf"
    t = pdfkiemeles.vaz(pdf, "History")
    t = pdfkiemeles.beszur(t, "k-a1b2c3", 1, "Az első oldal kiemelt mondata.", [[0.1, 0.1, 0.5, 0.05]], pdf)
    t = pdfkiemeles.beszur(t, "k-d4e5f6", 2, "A második oldal kiemelése.", [[0.1, 0.2, 0.6, 0.05]], pdf)
    return pdfkiemeles.fajl_ut(pdf), t


def fo_vault(cel: Path) -> dict:
    j = _jegyzetek()
    j.update(_kiseroek(j))
    ut, t = _kiemelesek()
    j[ut] = t
    j["C31 JS-paritás.base"] = JS_BASE
    j.update(_canvasok())
    for rp, t in j.items():
        _ir(cel, rp, t)
    _ir(cel, "abra.png", _png())
    _ir(cel, "Tankönyv.pdf", _pdf(["Az elso oldal kiemelt mondata.", "A masodik oldal kiemelese."]))
    _obsidian(cel, {"alwaysUpdateLinks": False}, templates={"folder": "_Template"},
              types={"Datum": "date", "Idopont": "datetime", "Kesz": "checkbox", "Pontszam": "number", "Kezd": "date",
                     "Veg": "date", "a": "number", "b": "number", "a-b": "number", "Tized": "number"})
    md = [rp for rp in j if rp.endswith(".md")]
    return {"jegyzet": len(md), "canvas": sum(rp.endswith(".canvas") for rp in j), "base": 1,
            "plot": sum(t.count("```plot") for t in j.values())}


# ---------------------------------------------------------------- 2–5. a K-próbák

def k04_link(cel: Path) -> int:
    import obsidian_link_proba as olp
    _obsidian(cel)
    for rp, t in olp.FAJLOK.items():
        _ir(cel, rp, t)
    return len(olp.FAJLOK)


def k04_notion(cel: Path) -> int:
    _obsidian(cel)
    r = subprocess.run([str(REPO / "bin" / "mos"), "app", "test", "tests/notion-obsidian.test.ts"],
                       env={**os.environ, "MOS_NOTION_OBSIDIAN": str(cel)}, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"a Notion-próba vitestje hibával állt meg:\n{r.stdout[-2000:]}{r.stderr[-2000:]}")
    return len(list(cel.glob("*.md")))


def _app_json_ha_nincs(cel: Path) -> None:
    if not (cel / ".obsidian" / "app.json").exists():
        _ir(cel, ".obsidian/app.json", json.dumps({"alwaysUpdateLinks": False}, indent=2))


def k11_bases(cel: Path) -> dict:
    import bazis_proba
    ki = bazis_proba.general(cel)
    _app_json_ha_nincs(cel)
    return ki


def k42(cel: Path) -> list[str]:
    import k42_proba
    ki = k42_proba.general(cel)
    _app_json_ha_nincs(cel)
    return ki


ELLENORZO = """# C31 — Obsidian-ellenőrző lista (az átállás kézi kapuja)

Ezt a mappát a `tests/kezi/atallas_probavault.py` generálta ({ido}). Minden alább álló mappát **külön vaultként** nyiss meg
az Obsidianban („Open folder as vault”), és a választ a sor végén álló kérdésre írd vissza (a futtató chat a NAPLO-ba és a
KEZI-TEENDOK K212-es tételébe rögzíti). A valódi vaultodhoz semmi nem nyúl; a mappa törlése a tiéd.

A „2.0” oszlop azt írja, mit **vár** a 2.0 (a C31 statikus olvasása szerint az Obsidian 1.14.4 is ezt adja, ha nincs
megjelölve másként). Eltérésnél egy sor elég: „Nº: Obsidian ezt mutatja: …”.

## 1 - C31 próbavault

| Nº | Mit nyiss meg | Mit nézz | 2.0 |
|---|---|---|---|
| 1 | `M01 - Matematika/01 - Mértani sorozat` | olvasható; a ```` ```plot ```` blokk sima kódblokk; a `## Gyakorlás` két beágyazása megnyílik | kódblokk, két beágyazás |
| 2 | ugyanott a Tulajdonságok nézet | `Tags`, `NN` (link), `Canvas` (a `Sorozatok.canvas`-ra old fel) | 3 tulajdonság olvasható |
| 3 | `ATTCHMNTS - cards/…kártyák`, `…quizes/…`, `…summaries/…` | olvashatók, a `[!card]`/`[!success]-` callout lenyílik, a `[[…#^m-def1]]` a bekezdésre ugrik | igen |
| 4 | `T01 - Történelem/01 - Ókori Róma` | a két `%%…%%` megjegyzés rejtett (olvasó nézetben); a **Kimenő linkek** panelen szerepel-e a `Rejtett link` / `Rejtett link 2`? (**K04 `%%` kérdése**) | a 2.0 ma: linknek veszi |
| 5 | `K10 - Tulajdonságok/Típusok` | a Tulajdonságok nézet: lista, idézett wikilinkek, dátum, dátum+idő, jelölő, szám, új tulajdonság mind a típusának megfelelően; egy érték módosítása után a fájl kulcssorrendje marad (K10) | igen |
| 6 | `T157 - YAML skalárok/Idézett (2.0)` és `Nyers (összevetés)` | az „Idézett” mind szöveg; a „Nyers”-ben melyik **szám**/**jelölő**? | statikus: `0x1F`=31, `0o7`=7 szám; a többi szöveg |
| 7 | `X01 - Napló & To-Do/2026-10/Napló/2026-10-07` | `Napló` címke, üres `Source`/`Status`/`NN`, a `Canvas` a `2026-10.canvas`-ra old fel (K17) | igen |
| 8 | Templates beállítás: a sablonmappa `_Template` (a `templates.json` már ezt mondja; a Templates core plugint kapcsold be, ha ki van) → új jegyzetbe „Insert template” → `C31 sablonpróba` | vesd össze a `T156 - Sablon/A 2.0 kimenete` szövegével (a dátum a te napod) | `{{DATE}}` cserélődik; `{{date:}}` = alapformátum; `MMM` = `okt.`; a `{{ date }}` és a `{{cursor}}` az Obsidianban szöveg marad (2.0-eltérés) |
| 9 | `Tankönyv – kiemelések` | a `%%manifold-kiemeles …%%` sor rejtett; a `> — [[Tankönyv.pdf#page=2]]` a PDF 2. oldalára nyit; a Tulajdonságok a `Tags`/`Source` listát mutatja (K25) | igen |
| 10 | `Linkek/md-linkek` → Kimenő linkek panel | melyik a **feloldott** (1–8)? | 1, 2, 3, 4 (`a%23b`), 5, 8: feloldott; 6 külső; 7 nem link (a 8. a CommonMark szerint nem link — ha az Obsidian sem látja, az a 2.0 ismert eltérése) |
| 11 | `Feloldás/Források/Kis-nagybetű` → kattints a `[[cél]]`-ra | melyik nyílik: `Rövid/Cél` vagy `Hosszabb mappa neve/cél`? | 2.0: `Hosszabb mappa neve/cél` (pontos kis-nagybetű előbb); statikus olvasás: az Obsidian `Rövid/Cél` (**K**) |
| 12 | `Feloldás/Források/Szegmens` → `[[x/A]]` | feloldott-e (a `yx/A`-ra)? | 2.0: nem; statikus olvasás: az Obsidian igen (**S**) |
| 13 | `Feloldás/Források/Relatív` → a két link | feloldottak-e? | 2.0: nem; statikus olvasás: az Obsidian igen (**R**) |
| 14 | **T158**: `Új jegyzet/Kattints` → kattints mindhárom linkre (utána töröld a létrejött jegyzeteket) | hol jön létre a jegyzet? | `M01 - Matematika/Új útvonalas`; `Nem létező mappa/Al/Új mélyen` (a mappák létrejönnek); `Csak név (új)` a gyökérben (az `app.json` nem állít `newFileLocation`-t) |
| 15 | `Blokkok/Hivatkozó` → az öt link | mind a megfelelő blokkra ugrik-e (T160)? A `Blokkok/Nem szöveges` utolsó listaeleméhez a 2.0 nem ír azonosítót (a menüpont tiltva) | mind ugrik |
| 16 | `Blokkok/HTML és nyitott kerítés` | a `<details>` lenyitható, a belső bekezdés benne van; a nyitott kerítés a fájl végéig kód | igen |
| 17 | `C31 JS-paritás.base` (`JS` nézet) → CSV-export | az `orak`, `kotojel`, `tized_30`, `zona` oszlop soronként | lásd a táblát lent (**T155**; a `kotojel`: ha az Obsidian 3/4/0-t ad, a kötőjel kivonás, és a 2.0 `KOTOJELES_AZONOSITO` kapcsolója `False`-ra áll) |
| 18 | a 5 canvas (`Sorozatok`, `Színek`, `Csoport`, `Linkek`, a havi) | megnyílnak, a színek (1–6 + egyedi), a csoport, az él címkéje és a nyíl nélküli él helyes; mentés nélkül bezárva a fájl változatlan | igen |

A 17. sor 2.0-ja (Europe/Budapest időzóna):

| file.name | orak | kotojel | tized_30 | zona |
|---|---|---|---|---|
{js_sorok}

## 2 - K04 Link-próba

A C10.6 P00–P14 próbája: a mappa `Olvass el` jegyzete szerint (a maszk-kapcsolók: `maszk.BEHUZOTT_KOD`, `maszk.HTML_MEGJEGYZES`).
Írd vissza a Kimenő linkek panelen látott P-számokat. **K04 kérdés**: a behúzott kódblokk és a HTML-megjegyzés `[[…]]`-je
link-e; és a `%%megjegyzés%%`-ben álló link (1. vault, 4. sor) számítson-e linknek a 2.0 gráfjában.

## 3 - K04 Notion-próba

{notion}

## 4 - K11 Bases

A K11 menete: a 9 nézet CSV-exportja egy mappába, majd
`var/venv/bin/python -B tests/kezi/bazis_paritas.py "<ez a mappa>/4 - K11 Bases" <CSV-mappa>`. A K12: egy nézet típusa
Kanbanra (`type: kanban`, `groupBy`) — a statikus olvasás szerint az Obsidian 1.14.4 nézet-típusa is `kanban`; nézd meg,
hogy a 2.0-ban készült Kanban mindkét irányban a helyes oszlopokkal nyílik-e.

## 5 - K42 Forrás-mappa

Nyisd meg az `A/x` jegyzetet, kattints a `[[J]]`-re: az `AB/J` vagy a `B/J` nyílik? (A statikus olvasás szerint az
Obsidian szöveg-előtaggal vizsgálja a forrás mappáját, tehát `AB/J` — ugyanaz, mint a 2.0.)

## Ami nem ebben a mappában van

- **K15** (gráf-színezés): a valódi vaultodon, az Obsidian gráfnézete és a 2.0 gráfnézete egymás mellett (néhány tucat
  csúcs a 11 színcsoportból).
"""


def general(cel, notion: bool = False) -> dict:
    cel = Path(cel)
    if cel.exists() and any(cel.iterdir()):
        raise SystemExit(f"a cél nem üres: {cel}")
    cel.mkdir(parents=True, exist_ok=True)
    ki = {"fo": fo_vault(cel / FO), "k04_link": k04_link(cel / "2 - K04 Link-próba")}
    ki["k04_notion"] = k04_notion(cel / "3 - K04 Notion-próba") if notion else None
    ki["k11"] = k11_bases(cel / "4 - K11 Bases")
    ki["k42"] = k42(cel / "5 - K42 Forrás-mappa")
    js = [f"| {n} | {v['orak']} | {v['kotojel']} | {JS_VART['*']['tized_30']} | {v['zona']} |"
          for n, v in sorted(JS_VART.items()) if n != "*"]
    notion_szoveg = ("A C09 tíz esete: minden esethez `— előtte`, `— utána` és `— kanonikus` jegyzet; a három nézete azonos-e."
                     if notion else "Nem készült (a generátor `--notion` nélkül futott): `bin/mos exec var/venv/bin/python -B "
                     "tests/kezi/notion_obsidian.py` külön elkészíti.")
    szoveg = (ELLENORZO.replace("{ido}", datetime.now().strftime("%Y-%m-%d %H:%M")).replace("{js_sorok}", "\n".join(js))
              .replace("{notion}", notion_szoveg))
    _ir(cel, "ELLENORZO.md", szoveg)
    return ki


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        print(__doc__)
        return 2
    ki = general(Path(args[0]).expanduser().resolve(), notion="--notion" in argv)
    print(json.dumps(ki, ensure_ascii=False, default=str))
    print(f"[próba] kész: {Path(args[0]).expanduser().resolve()} — az ELLENORZO.md szerint")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
