"""A link-feloldás és a gráf — **egy helyen** (LEGACY-SZERZODESEK L42; CLAUDE.md 1. / 13. döntés).

Eredet: a legacy `mfd` portja (legacy `2fbe596`: `modulok/eszkozok/mfd.py:342-502`, `vaultlib.py:16,81-98,193-206`).
A C10.6 óta a feloldás és a maszk az **Obsidian viselkedését** követi, nem a legacyét; a gráf, a backlink, a
jegyzetnézet, az átnevezés és a felület mind ezt használja, saját feloldás sehol nem készül.

Ami a legacyvel azonos maradt:
- a bejárás: `os.walk`, a pontos fájl és a `SKIP_DIRS` mappa kimarad; a nyers (lemezen álló, gyakran NFD)
  relatív utak szerint rendezve, azután NFC-re alakítva;
- a `.md` szöveges módban olvasva (`utf-8`, `errors="replace"`, a `\\r\\n` és a `\\r` → `\\n`);
- a `WIKI_RE` nem kéri a záró `]]`-t;
- a canvas szigorú UTF-8 + JSON; a hiba szövege `str(e)[:80]`;
- a feloldás sorrendje (az Obsidian `getLinkpathDest`-je), kis-nagybetűre pontos egyezésnél.

Ami eltér (a 13. döntés; a `tests/legacy_szabaly.py` linkenként méri és osztályozza):
- **K** — a feloldás kis-nagybetűtől független: ha a pontos menet nem talál, ugyanaz a sorrend NFC + kisbetűs
  alakon fut (az ékezet számít); a pontos kis-nagybetűs találat így mindig előnyt kap;
- **S** — a végződés-illesztés szegmenshatáron vág (az `[[x/A]]` nem oldódik a `yx/A.md`-re);
- **M** — a maszk a `maszk.link_maszk`: `~~~` kerítés, több-backtickes soron belüli kód, képlet (`$…$`, `$$…$$`);
  a frontmatterben nincs maszk;
- **U** — az md-link célja URL-dekódolva oldódik fel (a 36. döntés, C31): a `<…>` burok lekerül, a `%XX` a JS
  `decodeURI` szerint dekódolódik (a fenntartott jelek — `; / ? : @ & = + $ , #` — kódolva maradnak, a hibás kódolású
  cél nem belső link), az NBSP szóköz (az Obsidian 1.14.4 md-link-elemzője, statikus olvasás). Az egyetlen hely:
  `md_reszek` / `md_cel`; az index, az átnevezés és a gráf mind ezt hívja. Az átnevezés a kódolt alakot írja vissza
  (`md_kodol`: az Obsidian `generateMarkdownLink`-jének szabálya).
"""
from __future__ import annotations

import collections
import json
import os
import posixpath
import re
import unicodedata

from .. import rejtett, utkapu
from .maszk import link_maszk, mask_code  # noqa: F401 — a `mask_code` innen is elérhető (a maszk helye: `maszk.py`)

SKIP_DIRS = rejtett.KIHAGYOTT_MAPPAK     # I6 (F3): egy forrás minden vault-bejárónak — benne a `.manifold` (próbaklónok, állapot)

WIKI_RE = re.compile(r"!?\[\[([^\]\|\#]*)")
MD_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
KULSO = ("http:", "https:", "mailto:", "#")

_FENNTARTOTT = frozenset(";/?:@&=+$,#")          # a JS `decodeURI` ezeket kódolva hagyja
_HEX2 = re.compile(r"[0-9A-Fa-f]{2}")
_MD_KODOLANDO = re.compile(r"[\\\x00\x08\x0b\x0c\x0e-\x1f ]")   # az Obsidian `hd()`-je: `\`, vezérlőjelek, szóköz


def decode_uri(s: str) -> str:
    """A JS `decodeURI` (ECMA-262 Decode, `reservedURISet`): a `%XX`-sorozatok UTF-8-ként dekódolódnak, kivéve ha a jel
    fenntartott (`; / ? : @ & = + $ , #`) — az kódolva marad. Hibás sorozat (nem hex, csonka, érvénytelen UTF-8):
    `ValueError` (a JS-ben `URIError`)."""
    if "%" not in s:
        return s
    ki, i, n = [], 0, len(s)
    while i < n:
        c = s[i]
        if c != "%":
            ki.append(c)
            i += 1
            continue
        if not _HEX2.fullmatch(s[i + 1:i + 3]):
            raise ValueError(f"hibás %-kódolás: {s[i:i + 3]!r}")
        b = int(s[i + 1:i + 3], 16)
        if b < 0x80:
            ki.append(s[i:i + 3] if chr(b) in _FENNTARTOTT else chr(b))
            i += 3
            continue
        k = 2 if b & 0xE0 == 0xC0 else 3 if b & 0xF0 == 0xE0 else 4 if b & 0xF8 == 0xF0 else 0
        if not k:
            raise ValueError("érvénytelen UTF-8 kezdőbájt")
        bajtok, j = [b], i + 3
        for _ in range(k - 1):
            if s[j:j + 1] != "%" or not _HEX2.fullmatch(s[j + 1:j + 3]):
                raise ValueError("csonka UTF-8 sorozat")
            bajtok.append(int(s[j + 1:j + 3], 16))
            j += 3
        ki.append(bytes(bajtok).decode("utf-8"))              # UnicodeDecodeError ⊂ ValueError
        i = j
    return "".join(ki)


def md_reszek(nyers: str) -> tuple[str, str] | None:
    """Egy md-link (`[szöveg](nyers)`) belső célja: (cél, horgony) a feloldáshoz, vagy None, ha nem belső link (külső
    séma, `#`-kezdet, hibás %-kódolás). A `<…>` burok lekerül, a dekódolás a `decode_uri`, az NBSP szóköz."""
    t = (nyers or "").strip()
    if t.startswith("<") and t.endswith(">"):
        t = t[1:-1].strip()
    if t.startswith(KULSO):
        return None
    try:
        t = decode_uri(t).replace("\xa0", " ")
    except ValueError:
        return None
    cel, _, horgony = t.partition("#")
    return cel, horgony


def md_cel(nyers: str) -> str | None:
    """Az md-link célja a feloldáshoz (`md_reszek` első tagja), vagy None."""
    r = md_reszek(nyers)
    return r[0] if r else None


def md_kodol(cel: str) -> str:
    """Az md-link célja írásra (az átnevezés): az Obsidian `generateMarkdownLink`-jének `hd()`-je — a `\\`, a vezérlőjelek és
    a szóköz `%XX`; az ékezet és minden más marad (statikus olvasás, 1.14.4)."""
    return _MD_KODOLANDO.sub(lambda m: "".join(f"%{b:02X}" for b in m.group(0).encode("utf-8")), cel)


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def szoveg(b: bytes) -> str:
    """Egy `.md` szövege a legacy olvasása szerint (`open(…, encoding="utf-8", errors="replace").read()`)."""
    return b.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")


def bejaras(root) -> list[tuple[str, str]]:
    """A vault fájljai a legacy `walk` szerint: [(NFC relatív út, nyers relatív út)], a nyers út szerint
    rendezve (a legacy az abszolút utakat rendezte; a közös előtag miatt ez ugyanaz a sorrend)."""
    root = os.fspath(root)
    out = []
    for dp, dn, fn in os.walk(root):
        rejtett.metsz(dn)
        for f in fn:
            if not f.startswith(".") and utkapu.belul(root, os.path.join(dp, f)):     # T098: vaulton kívülre mutató symlink nem fájl
                out.append(os.path.join(dp, f))
    out.sort()
    return [(nfc(os.path.relpath(p, root)), os.path.relpath(p, root)) for p in out]


def jegyzet_celok(txt: str) -> list[str]:
    """Egy `.md` link-céljai a gráf szabálya szerint: a kódon és képleten kívüli `[[…]]` és `![[…]]` célja
    (cső és horgony nélkül), valamint a belső md-linkek célja (`md_cel`: burok nélkül, URL-dekódolva, a `#` előtt)."""
    txt = link_maszk(txt)
    return WIKI_RE.findall(txt) + [c for c in map(md_cel, MD_RE.findall(txt)) if c is not None]


def canvas_celok(j: dict) -> list[str]:
    """Egy canvas (a beolvasott JSON) link-céljai: a fájlnode-ok útja és a szövegnode-ok `[[…]]`-jei."""
    out = []
    for node in j.get("nodes", []):
        if node.get("file"):
            out.append(node["file"])
        out.extend(m.group(1) for m in canvas_wiki(node.get("text") or ""))
    return out


def canvas_wiki(szoveg: str):
    """Egy canvas-szövegnode wikilinkjei (`WIKI_RE`-találatok a szöveg eltolásaival): a jegyzet maszkjával, de
    frontmatter nélkül (a node szövege nem jegyzet). Az index és az átnevezés is ezt használja."""
    return WIKI_RE.finditer(link_maszk(szoveg, frontmatter=False))


def celkulcs(target: str) -> str:
    """A cél **kisbetűs** alapneve a feloldás előfeldolgozása után: az inkrementális újrafeloldás kulcsa. A
    feloldás eredménye csak azoktól a fájloktól függ, amelyeknek a kisbetűs alapneve a kulcs vagy a kulcs + `.md`."""
    s = _elokeszit(target)
    return kis(os.path.basename(s)) if s else ""


def kis(s: str) -> str:
    """A kis-nagybetűtől független egyeztetés alakja (az Obsidian `toLowerCase`-e; az ékezet megmarad)."""
    return s.lower()


def _elokeszit(target: str) -> str:
    """A cél a feloldás előtt: NFC, szóközök nélkül; a `[[cél\\|alias]]` záró `\\`-e az alias-cső escape-je."""
    s = nfc((target or "").strip())
    if s.endswith("\\"):
        s = s[:-1].rstrip()
    return s.replace("\\", "/").lstrip("/")


def _vegzodik(ut: str, cel: str) -> bool:
    """Az `ut` a `cel`-lal végződik, szegmenshatáron."""
    return ut == cel or ut.endswith("/" + cel)


class Feloldo:
    """A link-feloldó inkrementális alakban: `resolve(cél, forrás) → (út | None, alapnév, többértelmű)`.

    A sorrend (az Obsidian `getLinkpathDest`-je): (1) a jelölt a cél alapnevével egyező fájl, ha nincs ilyen, az
    alapnév + `.md`; (2) egyetlen jelölt és mappa nélküli cél → az a fájl; (3) a teljes út egyezése; (4) több, a
    céllal (szegmenshatáron) végződő jelöltnél előre kerül, amelynek az útja a forrás mappájával kezdődik, mindkét
    csoporton belül a rövidebb (majd a kisebb) út nyer.

    Két menet: előbb kis-nagybetűre **pontosan**; ha így nincs találat, ugyanez kisbetűs alakon. Ami pontosan
    feloldódik, azt a második menet nem befolyásolja. Az `alapnév` a talált fájl alapneve."""

    def __init__(self, files=()):
        self.fileset: set[str] = set()
        self.by_base: dict[str, list[str]] = collections.defaultdict(list)
        self.by_low: dict[str, list[str]] = collections.defaultdict(list)
        for rp in files:
            self.hozzaad(rp)

    def hozzaad(self, rp: str) -> None:
        if rp not in self.fileset:
            self.fileset.add(rp)
            b = os.path.basename(rp)
            self.by_base[b].append(rp)
            self.by_low[kis(b)].append(rp)

    def elvesz(self, rp: str) -> None:
        if rp in self.fileset:
            self.fileset.discard(rp)
            b = os.path.basename(rp)
            for tabla, k in ((self.by_base, b), (self.by_low, kis(b))):
                tabla[k].remove(rp)
                if not tabla[k]:
                    del tabla[k]

    def _menet(self, full: str, src: str, pontos: bool):
        alak = (lambda x: x) if pontos else kis
        tabla = self.by_base if pontos else self.by_low
        full = alak(full)
        base = os.path.basename(full)
        cands = tabla.get(base, [])
        if not cands:
            full, base = full + ".md", base + ".md"
            cands = tabla.get(base, [])
        if not cands:
            return None
        if full == base and len(cands) == 1:
            return cands[0], False
        teljes = [c for c in cands if alak(c) == full]
        if teljes:
            return min(teljes, key=lambda c: (len(c), c)), False
        vegu = [c for c in cands if _vegzodik(alak(c), full)]
        if not vegu:
            return None
        o = alak(os.path.dirname(src))
        elol = sorted((c for c in vegu if alak(c).startswith(o)), key=lambda c: (len(c), c))
        hatul = sorted((c for c in vegu if not alak(c).startswith(o)), key=lambda c: (len(c), c))
        return (elol + hatul)[0], len(vegu) > 1

    def resolve(self, target: str, src: str) -> tuple[str | None, str | None, bool]:
        s = _elokeszit(target)
        if not s:
            return None, None, False
        # Kifejezett relatív link: a forrás mappájából, kizárólag a vaulton belül.
        # Nem eshet át a végződéses keresésre: ../Other/A nem jelenthet egy másik A fájlt.
        if s.startswith(("./", "../")):
            cel = posixpath.normpath(posixpath.join(posixpath.dirname(src), s))
            if cel in (".", "..") or cel.startswith("../") or cel.startswith("/"):
                return None, None, False
            for nev in (cel, cel + ".md"):
                if nev in self.fileset:
                    return nev, posixpath.basename(nev), False
                egyezo = sorted(u for u in self.by_low.get(kis(posixpath.basename(nev)), ()) if kis(u) == kis(nev))
                if egyezo:
                    return egyezo[0], posixpath.basename(egyezo[0]), len(egyezo) > 1
            return None, None, False
        r = self._menet(s, src, True) or self._menet(s, src, False)
        if r is None:
            return None, None, False
        return r[0], os.path.basename(r[0]), r[1]


def canvas_olvas(full) -> tuple[dict | None, str | None]:
    """Egy canvas a legacy olvasásával: (JSON | None, hiba | None). A hiba szövege `str(e)[:80]`.
    A nem objektum gyökerű JSON is hiba (a legacy ezen elszállt volna)."""
    try:
        with open(full, encoding="utf-8") as fh:
            j = json.load(fh)
    except Exception as e:  # noqa: BLE001 — a legacy minden hibát canvas-hibaként rögzít
        return None, str(e)[:80]
    if not isinstance(j, dict) or not all(isinstance(n, dict) for n in j.get("nodes", []) or []):
        return None, "a canvas nem JSON Canvas-objektum"
    return j, None


def fajl_celok(root, rp: str, lemez_rp: str | None = None) -> tuple[list[str], str | None]:
    """Egy fájl gráf-céljai a legacy olvasásával: (célok, canvas-hiba | None). Más fájlnak nincs célja."""
    full = os.path.join(os.fspath(root), lemez_rp or rp)
    low = rp.lower()
    if low.endswith(".md"):
        with open(full, "rb") as fh:
            return jegyzet_celok(szoveg(fh.read())), None
    if low.endswith(".canvas"):
        j, hiba = canvas_olvas(full)
        return (canvas_celok(j), None) if j is not None else ([], hiba)
    return [], None


def graf(root) -> dict:
    """A vault gráfja közvetlenül a lemezről, a legacy `obsidian_graf` alakjában (index nélkül).

    `files` (NFC relatív utak), `out` (forrás → célok halmaza, önhurokkal), `unresolved` (feloldatlan cél
    → darab), `tobbertelmu` (alapnév → darab), `canvas_hiba` ([(út, hiba)]). Csak olvas."""
    lista = bejaras(root)
    files = [rp for rp, _ in lista]
    f = Feloldo(files)
    out: dict[str, set] = collections.defaultdict(set)
    unresolved: collections.Counter = collections.Counter()
    tobbertelmu: collections.Counter = collections.Counter()
    canvas_hiba = []
    for rp, lemez in lista:
        celok, hiba = fajl_celok(root, rp, lemez)
        if hiba is not None:
            canvas_hiba.append((rp, hiba))
            continue
        for t in celok:
            hit, base, tobb = f.resolve(t, rp)
            if tobb:
                tobbertelmu[base] += 1
            if hit:
                out[rp].add(hit)
            elif (t or "").strip():
                unresolved[nfc(t.strip())] += 1
    return {"files": files, "out": out, "unresolved": unresolved, "tobbertelmu": tobbertelmu,
            "canvas_hiba": canvas_hiba}


def graf_kanonikus(g: dict) -> bytes:
    """A gráf determinisztikus JSON-bájtjai (a paritásteszt ezt hasonlítja): a `files` sorrendje és a
    `canvas_hiba` sorrendje megmarad, a halmazok és a számlálók rendezve; csak nem üres élhalmaz."""
    d = {
        "files": list(g["files"]),
        "out": {k: sorted(v) for k, v in sorted(g["out"].items()) if v},
        "unresolved": sorted(dict(g["unresolved"]).items()),
        "tobbertelmu": sorted(dict(g["tobbertelmu"]).items()),
        "canvas_hiba": [list(x) for x in g["canvas_hiba"]],
    }
    return json.dumps(d, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def canvas_bajtbol(b: bytes) -> tuple[dict | None, str | None]:
    """A `canvas_olvas` bájtokból: (JSON | None, hiba | None); ugyanaz a szigorú UTF-8 + JSON és hibaszöveg."""
    try:
        j = json.loads(b.decode("utf-8"))
    except Exception as e:  # noqa: BLE001 — mint a `canvas_olvas`
        return None, str(e)[:80]
    if not isinstance(j, dict) or not all(isinstance(n, dict) for n in j.get("nodes", []) or []):
        return None, "a canvas nem JSON Canvas-objektum"
    return j, None


def hivatkozasok(root, tovabbi=None) -> dict:
    """A „teljes referencia-próba” alapja (C10, a legacy I30 szabálya): a vault MINDEN linkje a lemezről,
    az indextől függetlenül, a gráf szabályával. → `files` (NFC utak, rendezve), `linkek` (forrás → [(nyers cél,
    feloldott út | None)] a szövegsorrendben), `hash` (a `.md` és `.canvas` fájlok sha1-je, bájtból).
    A `tovabbi(rp, bájtok) → [cél]` visszahívás (C12b) további link-célokat ad egy forráshoz — a `.base` fájlok és a
    ```` ```base ```` blokkok kifejezéseiben állókat; a jegyzet saját linkjei után kerülnek a listára. Megadásakor a
    `.base` fájlok is bekerülnek a `linkek` és a `hash` közé. (A feloldás nem importál `bazis`-t: a hívó adja.)
    Csak olvas."""
    import hashlib
    lista = bejaras(root)
    files = [rp for rp, _ in lista]
    f = Feloldo(files)
    linkek: dict[str, list] = {}
    hash_: dict[str, str] = {}
    for rp, lemez in lista:
        low = rp.lower()
        if not low.endswith((".md", ".canvas")) and not (tovabbi is not None and low.endswith(".base")):
            continue
        with open(os.path.join(os.fspath(root), lemez), "rb") as fh:
            b = fh.read()
        hash_[rp] = hashlib.sha1(b).hexdigest()
        if low.endswith(".md"):
            celok = jegyzet_celok(szoveg(b))
            if tovabbi is not None:
                celok += tovabbi(rp, b)
        elif low.endswith(".canvas"):
            j, hiba = canvas_bajtbol(b)
            celok = canvas_celok(j) if j is not None else []
        else:
            celok = tovabbi(rp, b)
        linkek[rp] = [(t, f.resolve(t, rp)[0]) for t in celok]
    return {"files": files, "linkek": linkek, "hash": hash_}
