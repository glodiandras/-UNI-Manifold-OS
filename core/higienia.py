"""Jegyzethigiénia-riport (C30a; TERV 5.10): az indexből, modell és vault-írás nélkül, jegyzetenként és összesítve.

Tételfajták (`FAJTAK`): törött és többértelmű link, árva jegyzet, hibás képlet, hibás frontmatter, séma-sértés,
hiányzó forráshorgony, hiányzó média. A link-feloldás **nem itt** történik (L42): az index a beíráskor feloldja a
linkeket (`link.cel`, `link.tobbertelmu`), a riport ezt olvassa. A séma-ellenőrzés a meglévő `Tulajdonsagok`
hívása (újraírás nélkül).

Minden tételnek **stabil azonosítója** van (`<fajta>:<sha1 első 12 jegye>`), amely tartalmi kulcsból épül (nem
sorszámból): a sor eltolódása nem új tétel, a tartalom vagy az út változása igen. A C30b az „új tételek száma”
jelzést erre építi.

Csak olvas: a modul az indexhez a nyilvános `olvaso()` kontextuson át fér, a vaulthoz nem nyúl. A CLI
(`python -m core.higienia`, `bin/mos higienia`) a meglévő index-adatbázist csak olvasva nyitja.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter

from .asszisztens.beallitasok import beallitasok
from .index import indexelo, pdfszoveg
from .index import linkek as index_linkek
from .index.feloldas import nfc
from .tulajdonsagok import _fm_elemez
from .vaultio import NotFound

FAJTAK = ("torott_link", "tobbertelmu_link", "arva_jegyzet", "hibas_keplet", "hibas_frontmatter", "sema_sertes",
          "hianyzo_forrashorgony", "hianyzo_media")

HIBA, FIGYELEM, TAJEKOZTATO = "hiba", "figyelmeztetes", "tajekoztato"
_MEDIA_TIPUSOK = ("kep", "video", "hang", "pdf")
_OLDAL = re.compile(r"^page=(\d+)$")
_IDO = re.compile(r"^t=\d+(?:\.\d+)?$")


# ---------------------------------------------------------------- képlet-próba

_PARANCS = re.compile(r"\\(?:([A-Za-z]+)|.)", re.S)
_KORNYEZET = re.compile(r"\\(begin|end)\s*\{([^{}]*)\}")


def kepletproba(forras: str) -> str | None:
    """Szerkezeti próba egy képletre (a `$…$` nélküli szövegre): üres, kiegyenlítetlen `{}`, páratlan
    `\\left`/`\\right`, nem egyező `\\begin`/`\\end`. Hibaüzenet vagy `None`. **Nem teljes LaTeX-elemzés**: a
    parancsok ismeretét a felület KaTeX-e adja (a core-ban nincs elemző); ez a próba szándékosan konzervatív."""
    if not (forras or "").strip():
        return "üres képlet"
    mely, i, n = 0, 0, len(forras)
    while i < n:
        c = forras[i]
        if c == "\\":
            i += 2                  # `\{`, `\}`, `\\`, `\$`… és a parancsnév első betűje: a zárójelet nem érintik
            continue
        if c == "{":
            mely += 1
        elif c == "}":
            mely -= 1
            if mely < 0:
                return "felesleges záró kapcsos zárójel (})"
        i += 1
    if mely:
        return f"{mely} lezáratlan kapcsos zárójel ({{)"
    szamok = Counter(m.group(1) for m in _PARANCS.finditer(forras) if m.group(1) in ("left", "right"))
    if szamok["left"] != szamok["right"]:
        return "a \\left és a \\right nem párosítható"
    verem: list[str] = []
    for m in _KORNYEZET.finditer(forras):
        if m.group(1) == "begin":
            verem.append(m.group(2))
        elif not verem:
            return f"\\end{{{m.group(2)}}} kezdő \\begin nélkül"
        elif verem.pop() != m.group(2):
            return f"a \\begin és az \\end környezet neve nem egyezik ({m.group(2)})"
    if verem:
        return f"\\begin{{{verem[-1]}}} lezárás nélkül"
    return None


# ---------------------------------------------------------------- riport

def _azonosito(fajta: str, ut: str, kulcs: str) -> str:
    return fajta + ":" + hashlib.sha1((ut + "\0" + kulcs).encode("utf-8")).hexdigest()[:12]


def _kiterjesztes_tipus(cel_nyers: str) -> str:
    return indexelo.tipus(cel_nyers or "")[1]


def alcel_fajta(alcel: str) -> str:
    """A link `#`-utáni részének fajtája: `oldal` (`page=N`), `ido` (`t=N`), `blokk` (`^id`), különben `fejezet`."""
    if alcel.startswith("page="):
        return "oldal"
    if alcel.startswith("t="):
        return "ido"
    return "blokk" if alcel.startswith("^") else "fejezet"


class _Lepteto:
    """A háttérszámítás szünet-pontja (C30a): a `kozbe()` a fázisok között és `LEPES` soronként hívódik. A hívó (a
    szolgáltatás) itt várhat aktív használat alatt, vagy kivétellel megszakíthatja a számítást; a `kozbe` hívásakor
    egyetlen olvasó kapcsolat sincs lefoglalva (a fázisok `fetchall`-lal olvasnak)."""
    LEPES = 512

    def __init__(self, kozbe):
        self.kozbe = kozbe or (lambda: None)
        self.n = 0

    def fazis(self) -> None:
        self.n = 0
        self.kozbe()

    def sor(self) -> None:
        self.n += 1
        if self.n >= self.LEPES:
            self.n = 0
            self.kozbe()


def _kizart(ut: str, elotagok: list[str], reteg: str) -> bool:
    return any(ut.startswith(p) for p in elotagok) or (bool(reteg) and f"/{reteg}/" in "/" + ut)


def _csoportok(lista: list, n: int = 400):
    for i in range(0, len(lista), n):
        yield lista[i:i + n]


class Higienia:
    """`Higienia(cfg, index, tulajdonsagok)`: az `index` az `Index` (vagy a CLI csak olvasó párja: `olvaso()`
    kontextus és `tipusok`), a `tulajdonsagok` a séma-ellenőrző. A beállítások az `[asszisztens]` szakaszból jönnek
    (`asszisztens.beallitasok`)."""

    def __init__(self, cfg, index, tulajdonsagok):
        self.cfg = cfg
        self.index = index
        self.tulajdonsagok = tulajdonsagok

    def riport(self, ut: str | None = None, kozbe=None) -> dict:
        """A teljes riport, vagy az `ut` jegyzeté. Ismeretlen `ut`: `NotFound` (404); az index nem kész: `NemKesz`.
        `kozbe`: szünet-pont a fázisok között és 512 soronként (a háttérszolgáltatás használja; a kivétele megszakít)."""
        if ut is not None:
            ut = nfc(str(ut)).replace("\\", "/").strip().strip("/")
        b = beallitasok(self.cfg)
        lep = _Lepteto(kozbe)
        szuro = " AND f.ut = ?" if ut is not None else ""
        arg = (ut,) if ut is not None else ()
        tetelek: list[dict] = []
        with self.index.olvaso() as c:
            if ut is not None and c.execute("SELECT 1 FROM fajl WHERE ut = ? AND torolve IS NULL AND tipus = 'md'",
                                            (ut,)).fetchone() is None:
                raise NotFound(f"nincs ilyen jegyzet az indexben: {ut}")
            jegyzetek = c.execute("SELECT COUNT(*) FROM fajl f WHERE f.torolve IS NULL AND f.tipus = 'md'" + szuro,
                                  arg).fetchone()[0]
        lep.fazis()
        self._linkek(szuro, arg, tetelek, lep)
        lep.fazis()
        self._arvak(szuro, arg, tetelek, b)
        lep.fazis()
        self._kepletek(szuro, arg, tetelek, lep)
        lep.fazis()
        self._frontmatter(szuro, arg, tetelek, lep)
        tetelek.sort(key=lambda t: (t["ut"], t["sor"] or 0, FAJTAK.index(t["fajta"]), t["azonosito"]))
        szamok = Counter(t["fajta"] for t in tetelek)
        return {
            "kesz": True, "jegyzetek": jegyzetek, "tetelek": tetelek,
            "osszesites": {**{f: szamok.get(f, 0) for f in FAJTAK}, "ossz": len(tetelek),
                           "erintett_jegyzet": len({t["ut"] for t in tetelek})},
            "jegyzetenkent": dict(Counter(t["ut"] for t in tetelek)),
        }

    # -------------------------------------------------- linkek: törött, többértelmű, média, forráshorgony

    def _horgony_adatok(self, c, sorok: list) -> tuple[dict, dict]:
        """A blokk- és fejezet-horgonyos linkek céljainak blokkazonosítói és fejezetei (egy olvasásban, a feldolgozás
        előtt): `({ut: {azon}}, {ut: [(szint, szöveg, sor)]})`."""
        utak = set()
        for ut, fajta, nyers, alcel, _, _, _, _, cel, cel_tipus in sorok:
            if fajta == "wiki" and alcel and alcel_fajta(alcel) in ("blokk", "fejezet"):
                if cel is not None and cel_tipus == "md":
                    utak.add(cel)
                elif cel is None and not (nyers or "").strip():
                    utak.add(ut)
        blokkok: dict[str, set] = {}
        fejezetek: dict[str, list] = {}
        for csoport in _csoportok(sorted(utak)):
            jel = ",".join("?" * len(csoport))
            for ut, azon in c.execute("SELECT f.ut, b.azon FROM blokk b JOIN fajl f ON f.id = b.fajl_id "
                                      f"WHERE f.torolve IS NULL AND f.ut IN ({jel})", csoport):
                blokkok.setdefault(ut, set()).add(azon)
            for ut, szint, szoveg, sor in c.execute("SELECT f.ut, h.szint, h.szoveg, h.sor FROM fejezet h "
                                                    f"JOIN fajl f ON f.id = h.fajl_id WHERE f.torolve IS NULL "
                                                    f"AND f.ut IN ({jel}) ORDER BY f.ut, h.sor", csoport):
                fejezetek.setdefault(ut, []).append((szint, szoveg, sor))
        return blokkok, fejezetek

    def _pdf_lapszamok(self, c, sorok: list) -> dict[str, int]:
        """A `page=N` horgonnyal hivatkozott PDF-ek oldalszáma (C30b, K205 (c)). Az index nem hordozza (a szöveg nélküli lap nem
        szakasz, ezért a séma és a C25b mérése változatlan marad): a kinyerő gyorsítótárából jön, **csak olvasva** — csak azokra a
        PDF-ekre, amelyekre a riportban van oldalhorgonyos link, és csak ha a kinyerés kész, teljes és a fájl azóta nem változott.
        Ismeretlen oldalszámnál a horgonyt nem ítéljük el (a PDF kinyerése még tart / hibás / szkennelt-csonka / nincs gyorsítótár)."""
        utak = sorted({cel for (_, _, _, alcel, _, _, _, _, cel, cel_tipus) in sorok
                       if cel_tipus == "pdf" and cel and alcel and _OLDAL.match(alcel)})
        db_ut = getattr(self.index, "db_ut", None)
        if not utak or db_ut is None:
            return {}
        kulcsok = []
        for csoport in _csoportok(utak):
            jel = ",".join("?" * len(csoport))
            kulcsok += [(r[0], r[1], r[2]) for r in c.execute(
                f"SELECT ut, meret, mtime_ns FROM fajl WHERE torolve IS NULL AND tipus = 'pdf' AND ut IN ({jel})", csoport)
                if r[1] is not None and r[2] is not None]
        return pdfszoveg.lapszamok(db_ut.parent / "pdf-szoveg.sqlite", kulcsok)

    def _linkek(self, szuro, arg, ki, lep) -> None:
        with self.index.olvaso() as c:
            sorok = c.execute(
                "SELECT f.ut, l.fajta, l.cel_nyers, l.alcel, l.beagyazas, l.tulajdonsag, l.sor, l.tobbertelmu, l.cel, "
                "t.tipus FROM link l JOIN fajl f ON f.id = l.forras_id "
                "LEFT JOIN fajl t ON t.ut = l.cel AND t.torolve IS NULL "
                "WHERE f.torolve IS NULL AND f.tipus = 'md' AND l.fajta IN ('wiki', 'md')" + szuro +
                " ORDER BY f.ut, l.sorrend", arg).fetchall()
            blokkok, fejezetek = self._horgony_adatok(c, sorok)
            lapszam = self._pdf_lapszamok(c, sorok)
        szamlalo: Counter = Counter()
        for ut, fajta, nyers, alcel, beag, tul, sor, tobb, cel, cel_tipus in sorok:
            lep.sor()
            nyers = nyers or ""
            alcel = alcel or ""
            kulcs = f"{nyers}|{alcel}|{int(bool(beag))}"
            szamlalo[(ut, kulcs)] += 1
            kulcs += f"|{szamlalo[(ut, kulcs)]}"

            def tetel(fajta_, szint, uzenet, **reszlet):
                ki.append({"azonosito": _azonosito(fajta_, ut, kulcs), "fajta": fajta_, "szint": szint, "ut": ut,
                           "sor": sor, "uzenet": uzenet, "reszlet": {"cel_nyers": nyers, "alcel": alcel or None,
                                                                      **reszlet}})

            def horgony_hiba() -> str | None:
                """A `#`-utáni rész hibája, ha ellenőrizhető; különben `None`."""
                af = alcel_fajta(alcel)
                if af == "oldal":
                    m = _OLDAL.match(alcel)
                    if not (m and int(m.group(1)) >= 1):
                        return "érvénytelen oldalhorgony"
                    n = lapszam.get(cel) if cel_tipus == "pdf" else None       # C30b (K205 (c)): `oldal ≤ oldalszám`
                    return f"az oldal nincs a PDF-ben ({n} oldalas)" if n is not None and int(m.group(1)) > n else None
                if af == "ido":
                    return None if _IDO.match(alcel) else "érvénytelen időhorgony"
                if fajta != "wiki":
                    return None
                celut = ut if (cel is None and not nyers.strip()) else (cel if cel_tipus == "md" else None)
                if celut is None:
                    return None
                if af == "blokk":
                    return None if alcel[1:].strip() in blokkok.get(celut, ()) else "a hivatkozott blokk nincs a célban"
                ok = index_linkek.fejezet_tartomany(fejezetek.get(celut, []), 10 ** 9, alcel) is not None
                return None if ok else "a hivatkozott fejezet nincs a célban"

            if cel is None:
                if not nyers.strip():
                    if alcel and not tul:                  # azonos jegyzetű horgony: `[[#Fejezet]]`, `[[#^blokk]]`
                        hiba = horgony_hiba()
                        if hiba:
                            tetel("hianyzo_forrashorgony", HIBA, f"{hiba[0].upper()}{hiba[1:]}: #{alcel}")
                    continue
                if tul == "Source":
                    tetel("hianyzo_forrashorgony", HIBA, f"A forrás nem található: {nyers}", tulajdonsag="Source")
                elif beag and _kiterjesztes_tipus(nyers) in _MEDIA_TIPUSOK:
                    tetel("hianyzo_media", HIBA, f"A beágyazott média nem található: {nyers}")
                else:
                    tetel("torott_link", HIBA, f"Törött link: {nyers}")
                continue
            if alcel:
                hiba = horgony_hiba()
                if hiba:
                    extra = {"tulajdonsag": tul} if tul else {}
                    tetel("hianyzo_forrashorgony", HIBA, f"{hiba[0].upper()}{hiba[1:]}: {nyers}#{alcel}", cel=cel, **extra)
            if tul == "Source":
                continue
            if tobb:
                tetel("tobbertelmu_link", FIGYELEM, f"Többértelmű link: {nyers}", jelolt=cel)

    # -------------------------------------------------- árva jegyzet

    def _arvak(self, szuro, arg, ki, b) -> None:
        """Árva = nincs bejövő és nincs kimenő **jegyzet↔jegyzet** link (törzs vagy `NN`-féle frontmatter-reláció). A vault
        szerkezeti linkjei (`Canvas`, `Source`; a canvas-ból érkező, `higienia_arva_canvas`) nem számítanak, a kizárt
        utak (napi jegyzet, sablon, gépi kísérőjegyzet, média-réteg) nem jelennek meg."""
        tul = list(b["higienia_arva_tulajdonsag_kizart"])
        tul_szuro = f"(l.tulajdonsag IS NULL OR l.tulajdonsag NOT IN ({','.join('?' * len(tul))}))" if tul else "1"
        forrastipus = "('md', 'canvas')" if b["higienia_arva_canvas"] else "('md')"
        with self.index.olvaso() as c:
            utak = [r[0] for r in c.execute(
                "SELECT f.ut FROM fajl f WHERE f.torolve IS NULL AND f.tipus = 'md'" + szuro +
                " AND NOT EXISTS (SELECT 1 FROM link l JOIN fajl s ON s.id = l.forras_id WHERE l.cel = f.ut "
                f"AND s.id != f.id AND s.torolve IS NULL AND s.tipus IN {forrastipus} AND {tul_szuro})"
                " AND NOT EXISTS (SELECT 1 FROM link l JOIN fajl t ON t.ut = l.cel WHERE l.forras_id = f.id "
                f"AND t.id != f.id AND t.torolve IS NULL AND t.tipus = 'md' AND {tul_szuro})"
                " ORDER BY f.ut", (*arg, *tul, *tul))]
        reteg = str(self.cfg.section("media").get("reteg_mappa", "Média"))
        for ut in utak:
            if _kizart(ut, b["higienia_arva_kizart"], reteg):
                continue
            ki.append({"azonosito": _azonosito("arva_jegyzet", ut, ""), "fajta": "arva_jegyzet", "szint": TAJEKOZTATO,
                       "ut": ut, "sor": None, "uzenet": "Árva jegyzet: nincs bejövő és nincs kimenő jegyzet-link.",
                       "reszlet": {}})

    # -------------------------------------------------- képletek

    def _kepletek(self, szuro, arg, ki, lep) -> None:
        with self.index.olvaso() as c:
            sorok = c.execute(
                "SELECT f.ut, k.sor, k.forras FROM keplet k JOIN fajl f ON f.id = k.fajl_id "
                "WHERE f.torolve IS NULL AND f.tipus = 'md'" + szuro + " ORDER BY f.ut, k.kezd", arg).fetchall()
        szamlalo: Counter = Counter()
        for ut, sor, forras in sorok:
            lep.sor()
            hiba = kepletproba(forras)
            if hiba is None:
                continue
            kulcs = f"{forras}"
            szamlalo[(ut, kulcs)] += 1
            ki.append({"azonosito": _azonosito("hibas_keplet", ut, f"{kulcs}|{szamlalo[(ut, kulcs)]}"),
                       "fajta": "hibas_keplet", "szint": HIBA, "ut": ut, "sor": sor,
                       "uzenet": f"Hibás képlet: {hiba}", "reszlet": {"hiba": hiba, "forras": (forras or "")[:200]}})

    # -------------------------------------------------- frontmatter: formai hiba, érték-típus, séma

    def _frontmatter(self, szuro, arg, ki, lep) -> None:
        ervenytelen: dict[str, list[str]] = {}
        ertekek: dict[str, dict] = {}
        with self.index.olvaso() as c:
            for ut, kulcs in c.execute(
                    "SELECT f.ut, t.kulcs FROM tulajdonsag t JOIN fajl f ON f.id = t.fajl_id "
                    "WHERE f.torolve IS NULL AND f.tipus = 'md' AND t.ervenyes = 0" + szuro + " ORDER BY f.ut, t.sorrend",
                    arg):
                ervenytelen.setdefault(ut, []).append(kulcs)
            for ut, kulcs, ertek in c.execute(
                    "SELECT f.ut, t.kulcs, t.ertek FROM tulajdonsag t JOIN fajl f ON f.id = t.fajl_id "
                    "WHERE f.torolve IS NULL AND f.tipus = 'md' AND t.kulcs IN ('Tags', 'Status')" + szuro, arg):
                try:
                    ertekek.setdefault(ut, {})[kulcs] = json.loads(ertek)
                except (TypeError, ValueError):
                    pass
            jegyzetek = c.execute(
                "SELECT f.ut, f.fm_nyers, f.fm_hiba FROM fajl f WHERE f.torolve IS NULL AND f.tipus = 'md'" + szuro +
                " ORDER BY f.ut", arg).fetchall()
        for ut, fm, fm_hiba in jegyzetek:
            lep.sor()
            if fm_hiba:
                ki.append({"azonosito": _azonosito("hibas_frontmatter", ut, "fm"), "fajta": "hibas_frontmatter",
                           "szint": HIBA, "ut": ut, "sor": 1, "uzenet": f"A frontmatter formai hibás: {fm_hiba}",
                           "reszlet": {"hiba": fm_hiba}})
            for k in ervenytelen.get(ut, []):
                ki.append({"azonosito": _azonosito("hibas_frontmatter", ut, f"ertek|{k}"), "fajta": "hibas_frontmatter",
                           "szint": FIGYELEM, "ut": ut, "sor": 1,
                           "uzenet": f"A(z) „{k}” tulajdonság értéke nem illik a típusához.",
                           "reszlet": {"hiba": None, "kulcs": k}})
            for p in self._sema(ut, fm, ertekek.get(ut, {})):
                ki.append({"azonosito": _azonosito("sema_sertes", ut, f"{p['kod']}|{p['kulcs']}|{p['ertek']}"),
                           "fajta": "sema_sertes", "szint": HIBA if p["szint"] == "hiba" else FIGYELEM, "ut": ut,
                           "sor": 1, "uzenet": p["uzenet"], "reszlet": {"kod": p["kod"], "szint": p["szint"],
                                                                         "kulcs": p["kulcs"], "ertek": p["ertek"]}})

    def _sema(self, ut: str, fm_nyers: str | None, ertekek: dict) -> list[dict]:
        """A meglévő séma-ellenőrzés (`Tulajdonsagok.problemak`), újraírás nélkül. A kulcssorrend (az ismétlődéssel)
        a nyers blokk soronkénti szerkezetéből jön (`_fm_elemez`, YAML-elemzés nélkül), az értékek az index
        `tulajdonsag` tábláiból: a teljes vaulton ez a költséges YAML-újraelemzést spórolja meg (mérés: NAPLO).
        A formai hibát (`yaml_hiba`) a `hibas_frontmatter` fajta viszi."""
        kulcsok: list[str] = []
        if fm_nyers is not None:
            eol = "\r\n" if "\r\n" in fm_nyers else "\n"
            try:
                f = _fm_elemez(f"---{eol}{fm_nyers}{eol}---{eol}")
                kulcsok = f.kulcsok() if f else []
            except Exception:                   # a hibás blokk a saját fajtájában már megjelent
                return []
        return self.tulajdonsagok.problemak(ut, kulcsok, ertekek, van_fm=fm_nyers is not None)


# ---------------------------------------------------------------- CLI

class _OlvasoIndex:
    """Az `Index` csak olvasó párja a CLI-nek: a meglévő adatbázist nyitja, nem indít írót."""

    def __init__(self, cfg):
        from pathlib import Path
        from .index import elemzo
        from .index.olvaso import fajl_olvaso
        self.db_ut = Path(cfg.path("index")) / "vault.sqlite"
        self.tipusok = elemzo.tipusok_olvas(cfg.path("vault"))
        self.olvaso = fajl_olvaso(self.db_ut)


def utvonalak(r) -> None:
    def vegpont(k):
        ut = k.q.get("ut")
        if ut is None:                    # a teljes riport soron belül nem számolódik (51(a)): a háttérszolgáltatás gyorsítótára
            return k.app.asszisztens.szolgalat.teljes_riport()
        return Higienia(k.app.cfg, k.app.index, k.app.tulajdonsagok).riport(ut)
    r.get("/api/higienia", vegpont)


def main(argv: list[str]) -> int:
    import argparse
    from . import config
    from .tulajdonsagok import Tulajdonsagok

    ap = argparse.ArgumentParser(prog="mos higienia", description="Jegyzethigiénia-riport (csak olvas).")
    ap.add_argument("--ut", help="egy jegyzet vault-relatív útja")
    ap.add_argument("--json", action="store_true", help="géppel olvasható kimenet")
    a = ap.parse_args(argv)
    cfg = config.load()
    ix = _OlvasoIndex(cfg)
    try:
        r = Higienia(cfg, ix, Tulajdonsagok(cfg, ix)).riport(a.ut)
    except (indexelo.NemKesz, NotFound) as e:
        print(f"higienia: {e}", file=sys.stderr)
        return 1
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        o = r["osszesites"]
        print(f"{r['jegyzetek']} jegyzet, {o['ossz']} tétel, {o['erintett_jegyzet']} érintett jegyzet")
        for f in FAJTAK:
            if o[f]:
                print(f"  {f}: {o[f]}")
        for t in r["tetelek"]:
            print(f"{t['ut']}:{t['sor'] or '-'} [{t['fajta']}] {t['uzenet']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
