"""PDF-kiemelések (C16): a kiemelés-fájl formátumának egyetlen helye — elemző és író.

A kiemelések a PDF mellett, egy Obsidianban is olvasható jegyzetben élnek: `<PDF-törzs> – kiemelések.md`
(CLAUDE.md, C16-döntés). A frontmatter a vault sémája (L33): `Tags` a mappa tárgybetűjéből (`[pdf] tags`),
`Source` a kiemelt oldalak `"[[X.pdf#page=N]]"` listája, üres `Status`/`NN`/`Canvas` (a Status-t gép nem tölti).
A törzsben oldalanként egy `## N. oldal` fejezet, kiemelésenként egy blokk:

    %%manifold-kiemeles k-1a2b3c 0.1203,0.2210,0.4512,0.0180;0.1203,0.2410,0.3000,0.0180%%
    > a kijelölt szöveg
    > — [[X.pdf#page=N]] ^k-1a2b3c

A `%%…%%` megjegyzés (Obsidianban rejtett) hordozza a kiemelés azonosítóját és a téglalapjait (a lap
szélességéhez és magasságához viszonyított `x,y,szélesség,magasság` törtek, a nagyítástól függetlenek); a
`^k-…` blokkazonosítóval a kiemelésre link mutathat. A jelölő nélküli idézet közönséges szöveg: a felhasználó
Obsidianban írt sorai érintetlenek, az író csak a saját blokkjait szúrja be vagy törli (a többi bájt azonos).

Írás csak a meglévő úton: új fájl a `Vault.create`-tel, a meglévő a `Vault.write`-tal (hash-alapú ütközés,
atomi csere, a szerkesztés előtti kézi commit és egy `Mos-Forras: pult-szerkeszto` pillanatkép). A frontmatter
`Source` listáját a tulajdonság-szerkesztő számolója (`Tulajdonsagok.modosit`) írja át, soronkénti cserével.
"""
from __future__ import annotations

import math
import re
import secrets

from . import kiserok
from .index.maszk import FM_RE
from .utvonalak import HttpError
from .vaultio import _H1_ELOTAG, Conflict, Invalid, NotFound, nfc, norm_path

UTOTAG = " – kiemelések"
MAX_SZOVEG = 5000
MAX_TEGLALAP = 400
MAX_OLDAL = 100_000

JELOLO = re.compile(r"^%%manifold-kiemeles (k-[0-9a-f]{4,16}) ([0-9.,;]*)%%[ \t]*$")
OLDAL_FEJ = re.compile(r"^## (\d+)\. oldal[ \t]*$")
_HORGONY = re.compile(r"#page=(\d+)")
_ZARO = re.compile(r"^> — (\[\[[^\]]*\]\])(?: \^(k-[0-9a-f]{4,16}))?[ \t]*$")
_BLOKK_ELEJE = re.compile(r"^(#{1,6}\s|>|[-+*]\s|\d+[.)]\s|=+\s*$|-{3,}\s*$|```|~~~|\||<)")


# ---------------------------------------------------------------------- utak és alapadatok

def fajl_ut(pdf: str) -> str:
    """A PDF kiemelés-fájljának vault-relatív útja (a PDF mappájában)."""
    mappa, _, nev = pdf.rpartition("/")
    torzs = nev[:-4] if nev.lower().endswith(".pdf") else nev
    return f"{mappa}/{torzs}{UTOTAG}.md" if mappa else f"{torzs}{UTOTAG}.md"


def cimke(cfg, pdf: str) -> str | None:
    """A tárgy-címke a PDF legfelső mappájának első betűjéből (`[pdf.tags]`, az egyetlen forrás: `kiserok.subject_of`), vagy None."""
    return kiserok.subject_of(cfg, pdf)


def h1(pdf: str) -> str:
    nev = pdf.rsplit("/", 1)[-1]
    torzs = nev[:-4] if nev.lower().endswith(".pdf") else nev
    return _H1_ELOTAG.sub("", torzs) + UTOTAG


def vaz(pdf: str, tag: str | None) -> str:
    """Az új kiemelés-fájl váza (frontmatter + H1); a `Source` a beszúrás után töltődik."""
    tags = f"Tags:\n  - {kiserok.yaml_cimke(tag)}\n" if tag else "Tags:\n"      # a címke a munkatér beállításából jön: nyersen nem írjuk
    return f"---\n{tags}Source:\nStatus:\nNN:\nCanvas:\n---\n\n# {h1(pdf)}\n"


# ---------------------------------------------------------------------- elemzés

def teglalapok_szoveg(tl: list) -> str:
    return ";".join(",".join(f"{v:.4f}".rstrip("0").rstrip(".") if v else "0" for v in t) for t in tl)


def _teglalapok(s: str) -> list[list[float]]:
    ki = []
    for resz in s.split(";"):
        try:
            t = [float(x) for x in resz.split(",")]
        except ValueError:
            continue
        if len(t) == 4 and all(math.isfinite(x) for x in t):
            ki.append(t)
    return ki


def elemez(szoveg: str) -> list[dict]:
    """A kiemelések a fájl sorrendjében: `{id, oldal, szoveg, teglalapok, sor}` (a `sor` a jelölő sora, 0-tól).
    Az oldal a záró sor `#page=N` horgonyából, különben a fölötte álló `## N. oldal` fejezetből jön; oldal nélkül
    a blokk kimarad. A jelölő nélküli idézet nem kiemelés."""
    sorok = szoveg.replace("\r\n", "\n").split("\n")
    ki, fejezet, i = [], None, 0
    while i < len(sorok):
        m = OLDAL_FEJ.match(sorok[i])
        if m:
            fejezet = int(m.group(1))
        j = JELOLO.match(sorok[i])
        if not j:
            i += 1
            continue
        idezet, n = [], i + 1
        while n < len(sorok) and sorok[n].startswith(">"):
            idezet.append(sorok[n])
            n += 1
        oldal, szov = fejezet, []
        for s in idezet:
            z = _ZARO.match(s)
            if z:
                h = _HORGONY.search(z.group(1))
                if h:
                    oldal = int(h.group(1))
                continue
            szov.append(s[1:].strip())
        if oldal:
            ki.append({"id": j.group(1), "oldal": oldal, "szoveg": _visszaalakit(" ".join(t for t in szov if t)),
                       "teglalapok": _teglalapok(j.group(2)), "sor": i})
        i = n
    return ki


# ---------------------------------------------------------------------- szöveg → blokk

def normal_szoveg(s: str) -> str:
    """A kijelölt PDF-szöveg egy bekezdésként: sorvégi elválasztás összevonva (`szó-\\nrész` → `szórész`), a
    szóközök és sortörések egy szóközre, a vezérlőkarakterek nélkül."""
    s = nfc(s).replace("­", "")
    s = re.sub(r"(\w)-[ \t]*\r?\n[ \t]*(\w)", r"\1\2", s)
    s = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", s)
    return " ".join(s.split())


def _escape(s: str) -> str:
    """A szöveg idézet-sorként: ne nyisson Markdown-blokkot, linket, megjegyzést vagy blokkazonosítót."""
    s = s.replace("%%", "%​%").replace("[[", "[​[").replace("]]", "]​]")
    s = re.sub(r"\s\^(?=[A-Za-z0-9-]+$)", " \\^", s)
    if _BLOKK_ELEJE.match(s):
        s = "\\" + s
    return s


def _visszaalakit(s: str) -> str:
    s = s.replace("​", "")
    if s.startswith("\\") and _BLOKK_ELEJE.match(s[1:]):
        s = s[1:]
    return s.replace(" \\^", " ^")


def blokk(kid: str, oldal: int, szoveg: str, teglalapok: list, cel: str) -> list[str]:
    return [f"%%manifold-kiemeles {kid} {teglalapok_szoveg(teglalapok)}%%",
            f"> {_escape(szoveg)}",
            f"> — [[{cel}#page={oldal}]] ^{kid}"]


def _blokk_vege(sorok: list[str], i: int) -> int:
    n = i + 1
    while n < len(sorok) and sorok[n].startswith(">"):
        n += 1
    return n


def _sorok(szoveg: str) -> tuple[str, list[str], bool]:
    eol = "\r\n" if "\r\n" in szoveg else "\n"
    sorok = szoveg.replace("\r\n", "\n").split("\n")
    vegen = len(sorok) > 1 and sorok[-1] == ""
    if vegen:
        sorok.pop()
    return eol, sorok, vegen


def beszur(szoveg: str, kid: str, oldal: int, szov: str, tl: list, cel: str) -> str:
    """Az új blokk a `## N. oldal` fejezetbe, a lapon a téglalapok teteje szerinti olvasási sorrendben; ha a
    fejezet nincs, az oldalszám szerinti helyére (a nagyobb oldalszámú fejezet elé, különben a végére). A többi
    sor érintetlen."""
    eol, sorok, _ = _sorok(szoveg)
    uj = blokk(kid, oldal, szov, tl, cel)
    teteje = min(t[1] for t in tl)
    fejek = [(i, int(m.group(1))) for i, s in enumerate(sorok) if (m := OLDAL_FEJ.match(s))]
    sajat = next((i for i, o in fejek if o == oldal), None)
    if sajat is None:
        utana = next((i for i, o in fejek if o > oldal), None)
        if utana is None:
            while sorok and sorok[-1] == "":
                sorok.pop()
            sorok += ["", f"## {oldal}. oldal", ""] + uj
        else:
            sorok[utana:utana] = ([] if utana == 0 or sorok[utana - 1] == "" else [""]) + \
                [f"## {oldal}. oldal", ""] + uj + [""]
        return eol.join(sorok) + eol
    vege = next((i for i, _ in fejek if i > sajat), len(sorok))
    for k in elemez("\n".join(sorok)):
        if sajat < k["sor"] < vege and min((t[1] for t in k["teglalapok"]), default=0.0) > teteje:
            sorok[k["sor"]:k["sor"]] = uj + [""]
            return eol.join(sorok) + eol
    v = vege
    while v > sajat + 1 and sorok[v - 1] == "":
        v -= 1
    utan = [] if v == len(sorok) or sorok[v] == "" else [""]
    sorok[v:v] = [""] + uj + utan
    return eol.join(sorok) + eol


def torol(szoveg: str, kid: str) -> str:
    """A kiemelés blokkja (jelölő + idézet) törölve, a keletkező dupla üres sor összevonva; ha a fejezete kiürült,
    a fejezet is. A többi sor érintetlen."""
    eol, sorok, vegen = _sorok(szoveg)
    i = next((n for n, s in enumerate(sorok) if (m := JELOLO.match(s)) and m.group(1) == kid), None)
    if i is None:
        raise NotFound(f"nincs ilyen kiemelés: {kid}")
    del sorok[i:_blokk_vege(sorok, i)]
    hely = _osszevon(sorok, i)
    fej = next((k for k in range(min(hely, len(sorok)) - 1, -1, -1) if OLDAL_FEJ.match(sorok[k])), None)
    if fej is not None:
        vege = next((x for x in range(fej + 1, len(sorok)) if sorok[x].startswith("#")), len(sorok))
        if all(not s.strip() for s in sorok[fej + 1:vege]):
            del sorok[fej:vege]
            _osszevon(sorok, fej)
    return eol.join(sorok) + (eol if vegen else "")


def _osszevon(sorok: list[str], i: int) -> int:
    """A törlés helyén (`i`) maradt két üres sor egy lesz; a fájl végén nem marad üres sor. Az új hely."""
    while i > 0 and sorok[i - 1] == "" and (i >= len(sorok) or sorok[i] == ""):
        del sorok[i - 1]
        i -= 1
    while sorok and sorok[-1] == "" and i >= len(sorok):
        sorok.pop()
        i = len(sorok)
    return i


# ---------------------------------------------------------------------- a kezelő

class PdfKiemelesek:
    def __init__(self, app):
        self.app = app

    @property
    def vault(self):
        return self.app.vault

    def _pdf(self, pdf) -> str:
        pdf = norm_path(pdf)
        if not pdf.lower().endswith(".pdf"):
            raise Invalid(f"nem PDF: {pdf}")
        self.vault.media_path(pdf)          # létezik, kiszolgálható (rejtett szegmens nélkül)
        return pdf

    def _cel(self, pdf: str, forras: str) -> str:
        """A PDF link-szövege a kiemelés-fájlból (a core feloldója, L42); index nélkül a fájlnév."""
        try:
            return self.app.index.link_cel(pdf, forras)["cel"]
        except Exception:
            return pdf.rsplit("/", 1)[-1]

    def _olvas(self, ut: str) -> dict | None:
        try:
            return self.vault.read(ut)
        except NotFound:
            return None

    def lista(self, pdf) -> dict:
        pdf = self._pdf(pdf)
        ut = fajl_ut(pdf)
        r = self._olvas(ut)
        if r is None:
            return {"pdf": pdf, "fajl": None, "hash": None, "kiemelesek": []}
        return {"pdf": pdf, "fajl": r["ut"], "hash": r["hash"],
                "kiemelesek": [{k: v for k, v in x.items() if k != "sor"} for x in elemez(r["tartalom"])]}

    @staticmethod
    def _ellenoriz(oldal, szoveg, teglalapok) -> tuple[int, str, list]:
        if not isinstance(oldal, int) or isinstance(oldal, bool) or not 1 <= oldal <= MAX_OLDAL:
            raise Invalid("az `oldal` 1-nél nem kisebb egész")
        if not isinstance(szoveg, str):
            raise Invalid("hiányzik a `szoveg`")
        szoveg = normal_szoveg(szoveg)
        if not szoveg or len(szoveg) > MAX_SZOVEG:
            raise Invalid(f"a kiemelt szöveg 1–{MAX_SZOVEG} karakter")
        if not isinstance(teglalapok, list) or not 1 <= len(teglalapok) <= MAX_TEGLALAP:
            raise Invalid("a `teglalapok` legalább egy téglalap listája")
        tl = []
        for t in teglalapok:
            if not (isinstance(t, list) and len(t) == 4 and all(isinstance(x, (int, float)) and not isinstance(x, bool)
                                                                  and math.isfinite(x) for x in t)):
                raise Invalid("a téglalap négy szám: x, y, szélesség, magasság")
            x, y, w, h = (min(1.0, max(0.0, float(v))) for v in t)
            if w <= 0 or h <= 0:
                continue
            tl.append([round(x, 4), round(y, 4), round(w, 4), round(h, 4)])
        if not tl:
            raise Invalid("a téglalapok mérete nulla")
        return oldal, szoveg, tl

    def _source(self, ut: str, tartalom: str, pdf: str, cel: str) -> str:
        """A `Source` lista a fájl kiemeléseiből: a PDF oldal-horgonyai oldalszám szerint, utánuk a más
        bejegyzések változatlanul. A frontmatter-blokkot a tulajdonság-számoló írja át."""
        oldalak = sorted({k["oldal"] for k in elemez(tartalom)})
        m = FM_RE.match(tartalom)
        fm = m.group(0) if m else None
        regi = []
        if fm is not None:
            el = self.app.tulajdonsagok.elemez(ut, fm)
            ertek = next((t["ertek"] for t in el.get("tulajdonsagok", []) if t["kulcs"] == "Source"), None)
            regi = ertek if isinstance(ertek, list) else ([ertek] if isinstance(ertek, str) and ertek else [])
        sajat = re.compile(r"^\[\[" + re.escape(cel) + r"#page=\d+(?:\|[^\]]*)?\]\]$", re.I)
        tobbi = [e for e in regi if not (isinstance(e, str) and sajat.match(e.strip()))]
        uj = [f"[[{cel}#page={o}]]" for o in oldalak] + tobbi
        if uj == regi:
            return tartalom
        e = self.app.tulajdonsagok.modosit(ut, fm, "beallit", "Source", uj, "multitext", megerosit=True,
                                           forras="felhasznalo")
        if not e.get("ok") or e.get("fm_uj") is None:
            ok = "; ".join(p.get("uzenet", "") for p in e.get("problemak", [])) or "ismeretlen ok"
            raise Invalid(f"a Source mező nem írható: {ok}")
        return e["fm_uj"] + (tartalom[m.end():] if m else tartalom)

    def hozzaad(self, d: dict) -> dict:
        pdf = self._pdf(d.get("ut"))
        oldal, szoveg, tl = self._ellenoriz(d.get("oldal"), d.get("szoveg"), d.get("teglalapok"))
        ut = fajl_ut(pdf)
        cel = self._cel(pdf, ut)
        r = self._olvas(ut)
        if r is not None and d.get("alap") and d["alap"] != r["hash"]:
            raise Conflict("a kiemelés-fájl a betöltés óta megváltozott", hash=r["hash"], jel=r.get("jel"))
        alap_szoveg = r["tartalom"] if r else vaz(pdf, cimke(self.vault.cfg, pdf))
        if r and r.get("kodolas_hiba"):
            raise Invalid("a kiemelés-fájl nem érvényes UTF-8; Obsidianban vagy forrásmódban javítható")
        meglevo = {k["id"] for k in elemez(alap_szoveg)}
        kid = next(k for k in (f"k-{secrets.token_hex(3)}" for _ in range(100)) if k not in meglevo)
        uj = beszur(alap_szoveg, kid, oldal, szoveg, tl, cel)
        uj = self._source(ut, uj, pdf, cel)
        if r is None:
            mappa, _, nev = ut.rpartition("/")
            w = self.vault.create({"mappa": mappa, "nev": nev[:-3], "tartalom": uj})
        else:
            w = self.vault.write({"ut": r["ut"], "tartalom": uj, "alap": r["hash"], "elso": True, "pillanat": True})
        return {"ok": True, "id": kid, "fajl": w["ut"], "hash": w["hash"], "cel": cel, "oldal": oldal,
                "szoveg": szoveg, "teglalapok": tl, "figyelmeztetes": w.get("figyelmeztetes")}

    def torles(self, d: dict) -> dict:
        pdf = self._pdf(d.get("ut"))
        kid = d.get("id")
        if not isinstance(kid, str) or not re.fullmatch(r"k-[0-9a-f]{4,16}", kid):
            raise Invalid("érvénytelen kiemelés-azonosító")
        ut = fajl_ut(pdf)
        r = self._olvas(ut)
        if r is None:
            raise NotFound("a PDF-hez nincs kiemelés-fájl")
        if d.get("alap") and d["alap"] != r["hash"]:
            raise Conflict("a kiemelés-fájl a betöltés óta megváltozott", hash=r["hash"], jel=r.get("jel"))
        uj = self._source(r["ut"], torol(r["tartalom"], kid), pdf, self._cel(pdf, ut))
        w = self.vault.write({"ut": r["ut"], "tartalom": uj, "alap": r["hash"], "elso": True, "pillanat": True})
        return {"ok": True, "fajl": w["ut"], "hash": w["hash"]}


def utvonalak(r) -> None:
    def kezelo(k):
        return getattr(k.app, "pdf_kiemelesek", None) or _sajat(k.app)

    def _sajat(app):
        app.pdf_kiemelesek = PdfKiemelesek(app)
        return app.pdf_kiemelesek

    def lista(k):
        if not k.q.get("ut"):
            raise HttpError(400, "hiányzik az `ut`", kod="pdf.ut_hianyzik")
        return kezelo(k).lista(k.q.get("ut"))

    r.get("/api/pdf/kiemelesek", lista)
    r.post("/api/pdf/kiemeles", lambda k: kezelo(k).hozzaad(k.torzs()))
    r.post("/api/pdf/kiemeles/torol", lambda k: kezelo(k).torles(k.torzs()))
