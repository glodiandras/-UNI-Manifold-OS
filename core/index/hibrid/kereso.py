"""A hibrid keresés: lexikai ág (FTS5 `bm25`, a meglévő index) + vektor-ág (a vektortár) RRF-fel, opcionális rerankerrel.

**Két kérdésfajta.** Az *operátoros* kérdés (a ⌘⇧F nyelve: `path:`, `tag:`, `line:`, regex, tagadás, `OR`, idézőjel) a
lexikai `kereses.keres`-en megy: az ő találatai a szűrt jelölthalmaz (a sor-kiemelésekkel és a `legalabb` jelzéssel), a
vektor-ág csak ezen belül rangsorol, a szabad szavak (`szo`, `kif`, a tagadottak nélkül) alapján. A *természetes nyelvű*
kérdés lexikai ága a tövek VAGY-kérdése (`normal.fts_kerdes`), `bm25` szerint.

**Visszaesés.** Beágyazó vagy vektortár nélkül (vagy ha a tár más modell vektorait tartja) a válasz a lexikai
`kereses.keres` válasza változatlanul, `mod: "lexikai"` és az ok (`ok`) megjelölésével — a `legalabb` jelzés így mindkét
módban megmarad. A hibrid válasz `legalabb`-ja igaz, ha bármelyik ág elérte a jelöltkorlátját (lehet több találat).

A darabszintű jelöltek (`darab_jeloltek`) a „Kérdezz a vaulttól” bemenete: vektor-darabok és a lexikailag legjobb
jegyzetek darabjai, a darabokon számolt BM25-tel és RRF-fel; darabonként a kérdés töveinek fedése és a koszinusz is
(a „van-e elég forrás” modell nélküli jele).
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields

from ...vaultio import Invalid
from .. import kereses
from . import frissites, normal, rangsor
from .vektortar import DarabSor, Vektortar
from ...hibakod import kodol

MODOK = ("hibrid", "lexikai")


@dataclass(frozen=True)
class Beallitas:
    """A `[kereses.hibrid]` szakasz. A súlyok és a `k` kalibrálatlan induló értékek (K160 méri)."""
    rrf_k: float = 60.0
    lexikai_suly: float = 1.0
    vektor_suly: float = 1.0
    jelolt_n: int = 100              # ágonként ennyi jelölt jegyzet
    darab_n: int = 200               # a vektor-ág ennyi darabot kér
    lexikai_jegyzet_darab: int = 10  # a darabszintű jelöltekhez: a lexikailag legjobb ennyi jegyzet minden darabja
    vektor: bool = False             # a vektor-ág (és a vektorindex automatikus építése); M12, C25b mérés
    rerank: bool = False             # M12: csak ha a C18 halmazán mérhetően javít (K160)
    rerank_n: int = 20
    kihagyott: tuple[str, ...] | None = field(default=None, compare=False)   # nem a `[kereses.hibrid]` kulcsa: a `[kapuk] kihagyott_szakaszok` (None: az alap)


_MEZOK = {f.name for f in fields(Beallitas)} - {"kihagyott"}


def kihagyott_szakaszok(cfg) -> tuple[str, ...] | None:
    """A darabolás kihagyott szakaszai (`[kapuk] kihagyott_szakaszok`); a kapumodul nélkül `None` (a darabolás alapja)."""
    try:
        from modulok.kapuk.forras import kihagyott_szakaszok as lista          # lusta import: a core nem esik el rajta
    except ImportError:
        return None
    return lista(cfg)


def beallitas(cfg) -> Beallitas:
    adat = {k: v for k, v in dict(cfg.section("kereses", "hibrid")).items() if not isinstance(v, dict)}
    ismeretlen = sorted(set(adat) - _MEZOK)
    if ismeretlen:
        raise ValueError(f"[kereses.hibrid]: ismeretlen kulcs: {', '.join(ismeretlen)}")
    return Beallitas(**adat, kihagyott=kihagyott_szakaszok(cfg))


@dataclass(frozen=True)
class Jelolt:
    """Egy darab a vault-válasz jelöltjei között."""
    darab: DarabSor
    pont: float                      # RRF (vagy a reranker pontja, ha az futott)
    fedes: float                     # a kérdés töveinek aránya a darabban (címmel, címsor-úttal)
    hasonlosag: float | None         # koszinusz a kérdés-vektorral (vektor-ág nélkül `None`)
    agak: dict


def szabad_szoveg(q: str) -> str:
    """Az operátoros kérdés szabad szavai (`szo`, `kif`; a tagadottak és az operátorok értékei nélkül)."""
    try:
        e = kereses.elemez(q)
    except Invalid:
        return ""
    ki: list[str] = []

    def bejar(x):
        f = x[0]
        if f in ("szo", "kif", "reszszo"):
            ki.append(x[1])
        elif f in ("es", "vagy"):
            for y in x[1]:
                bejar(y)
        elif f == "op" and x[1] in kereses.ALOP_OPERATOROK and isinstance(x[2], tuple):
            bejar(x[2])
    bejar(e)
    return " ".join(s for s in ki if s.strip())


def rerank_szoveg(d: DarabSor) -> str:
    """A reranker bemenete egy darabra: a beágyazott szöveg alakja (`cím › fejezet`, üres sor, szöveg)."""
    return " › ".join((d.cim, *d.fejezet)) + "\n\n" + d.szoveg


def _darabsor(d) -> DarabSor:
    """Az indexből frissen darabolt `darabolas.Darab` a tár sor-alakjában (azonosító nélkül: `id = -1`)."""
    return DarabSor(-1, d.ut, d.sorszam, d.sor_kezd, d.sor_veg, tuple(d.fejezet),
                    tuple((b.sor_kezd, b.sor_veg, b.blokk, b.szoveg) for b in d.bekezdesek), d.szoveg)


class HibridKereso:
    """`index_olvaso`: kontextuskezelő-gyár a `vault.sqlite` olvasó kapcsolatához (az `IndexOlvaso.olvaso`). A beágyazó és a
    reranker hívható (`frissites.Beagyazo`, `rangsor.Reranker`); nélkülük a kereső lexikai."""

    def __init__(self, index_olvaso, tar: Vektortar | None = None, beagyazo=None, reranker=None,
                 beall: Beallitas | None = None, regex_idokorlat: float = kereses.REGEX_IDOKORLAT_MP, kizart=None):
        self.index_olvaso = index_olvaso
        self.kizart = kizart             # `index.kizaras.Kizaras` vagy None: a kizárt fájl nem találat (14-appearance-06)
        self.tar, self.beagyazo, self.reranker = tar, beagyazo, reranker
        self.b = beall or Beallitas()
        self.regex_idokorlat = regex_idokorlat

    def _kiz(self, ut: str) -> bool:
        return bool(self.kizart) and self.kizart.kizart(ut)

    # ------------------------------------------------------------------ állapot

    def miert_lexikai(self) -> str | None:
        """Ha a hibrid mód nem érhető el, az oka (különben `None`)."""
        if self.beagyazo is None:
            return "nincs_beagyazo"
        if self.tar is None:
            return "nincs_vektortar"
        k = self.tar.modell_kulcs()
        if not k:
            return "ures_vektortar"
        if k.get("nev") != self.beagyazo.nev or int(k.get("dim") or 0) != int(self.beagyazo.dim) \
                or k.get("elotag") != self.beagyazo.elotag:
            return "mas_modell_vektorai"
        return None

    # ------------------------------------------------------------------ lexikai ág

    def _lexikai(self, c, q: str, kornyezet: int = 0) -> dict:
        """`{utak, legalabb, osszes, szuro, szabad, talalatok}`: a lexikai ág jegyzetei (legjobb elöl)."""
        if normal.operatoros(q):
            r = kereses.keres(c, q, self.b.jelolt_n, self.regex_idokorlat, kornyezet, self.kizart)
            utak = [t["ut"] for t in r["talalatok"]]
            return {"utak": utak, "legalabb": r["legalabb"], "osszes": r["osszes"], "szuro": set(utak),
                    "szabad": szabad_szoveg(q), "talalatok": {t["ut"]: t for t in r["talalatok"]}}
        fts = normal.fts_kerdes(q)
        if fts is None:                               # csak töltelékszó: a lexikai kereső dönt (a szókezdet-illesztéssel)
            r = kereses.keres(c, q, self.b.jelolt_n, self.regex_idokorlat, kornyezet, self.kizart)
            utak = [t["ut"] for t in r["talalatok"]]
            return {"utak": utak, "legalabb": r["legalabb"], "osszes": r["osszes"], "szuro": None, "szabad": q,
                    "talalatok": {t["ut"]: t for t in r["talalatok"]}}
        sorok = c.execute("SELECT f.ut, bm25(fts, 2.0, 10.0, 1.0) FROM fts JOIN fajl f ON f.id = fts.rowid "
                          "WHERE fts MATCH ? AND f.torolve IS NULL ORDER BY bm25(fts, 2.0, 10.0, 1.0), f.ut LIMIT ?",
                          (fts, self.b.jelolt_n + 1 + (0 if not self.kizart else 4 * self.b.jelolt_n))).fetchall()
        sorok = [r for r in sorok if not self._kiz(r[0])]
        legalabb = len(sorok) > self.b.jelolt_n
        sorok = sorok[:self.b.jelolt_n]
        return {"utak": [r[0] for r in sorok], "legalabb": legalabb, "osszes": len(sorok), "szuro": None, "szabad": q,
                "talalatok": {r[0]: {"ut": r[0], "pont": round(-r[1], 4), "talalatok": []} for r in sorok}}

    # ------------------------------------------------------------------ jegyzetszintű keresés

    def keres(self, q: str, limit: int = 20, mod: str = "hibrid", kornyezet: int = 0) -> dict:
        if not isinstance(q, str) or not q.strip():
            raise kodol(Invalid("üres keresés"), "hibrid.kereso.ures_kereses")
        if mod not in MODOK:
            raise kodol(Invalid(f"ismeretlen keresési mód: {mod} ({' | '.join(MODOK)})"), "hibrid.kereso.ismeretlen_keresesi_mod_mod_join", {"mod": mod, "join": ' | '.join(MODOK)})
        limit = max(1, min(int(limit), 1000))
        ok = "kert_lexikai" if mod == "lexikai" else self.miert_lexikai()
        if ok is not None:
            with self.index_olvaso() as c:
                r = kereses.keres(c, q, limit, self.regex_idokorlat, kornyezet, self.kizart)
            return {**r, "mod": "lexikai", "ok": ok}
        with self.index_olvaso() as c:
            lex = self._lexikai(c, q, kornyezet)
        if not lex["szabad"].strip():
            talalatok = [dict(lex["talalatok"][u], agak={"lexikai": i}) for i, u in enumerate(lex["utak"][:limit], 1)]
            return {"q": q, "mod": "lexikai", "ok": "nincs_szabad_szo", "osszes": lex["osszes"],
                    "legalabb": lex["legalabb"], "talalatok": talalatok}
        qv = self.beagyazo([lex["szabad"]], "kerdes")[0]
        vek = [(i, p) for i, p in self.tar.keres(qv, self.b.darab_n, lex["szuro"]) if p > 0]     # a merőleges nem jel
        darabok = {d.id: d for d in self.tar.darabok([i for i, _ in vek])}
        jegyzetek = rangsor.jegyzetre((darabok[i].ut, i, p) for i, p in vek if i in darabok and not self._kiz(darabok[i].ut))
        legjobb = {u: (d, p) for u, d, p in jegyzetek}
        fuzott = rangsor.rrf({"lexikai": lex["utak"], "vektor": [u for u, _, _ in jegyzetek]}, self.b.rrf_k,
                             {"lexikai": self.b.lexikai_suly, "vektor": self.b.vektor_suly})
        sorrend = [(u, p, h, None) for u, p, h in fuzott]
        if self.b.rerank and self.reranker is not None:
            szoveg = {u: (rerank_szoveg(darabok[legjobb[u][0]]) if u in legjobb else self.legjobb_szoveg(u, lex["szabad"]))
                      for u, _, _ in fuzott[:self.b.rerank_n]}
            try:
                rr = rangsor.rerankel(lex["szabad"], [(u, szoveg.get(u, "")) for u, _, _ in fuzott], self.reranker,
                                      self.b.rerank_n)
                adat = {u: (p, h) for u, p, h in fuzott}
                sorrend = [(u, adat[u][0], adat[u][1], rp) for u, rp in rr]
            except ValueError:
                pass                                   # hibás reranker-válasz: a fúziós sorrend marad
        talalatok = []
        for u, p, h, rp in sorrend[:limit]:
            t = {"ut": u, "pont": p, "agak": h, "talalatok": lex["talalatok"].get(u, {}).get("talalatok", [])}
            if rp is not None:
                t["rerank"] = round(rp, 6)
            if u in legjobb:
                d = darabok[legjobb[u][0]]
                t["darab"] = {"sor_kezd": d.sor_kezd, "sor_veg": d.sor_veg, "fejezet": list(d.fejezet),
                              "szoveg": d.szoveg[:400], "hasonlosag": legjobb[u][1]}
            talalatok.append(t)
        return {"q": q, "mod": "hibrid", "ok": None, "osszes": len(fuzott),
                "legalabb": bool(lex["legalabb"] or len(vek) >= self.b.darab_n), "talalatok": talalatok}

    def legjobb_szoveg(self, ut: str, q: str) -> str:
        """A reranker szövege egy jegyzetre (C25b): a kérdéshez lexikailag (BM25) legjobb darabja a címmel és a címsor-úttal.
        A jegyzet első darabja rossz képviselő (a C25b mérésén a reranker így a FTS-sorrendet rontotta: recall@5 0,86 → 0,70)."""
        darabok = self.tar.darabok(ut=ut) if self.tar is not None else []
        if not darabok:
            with self.index_olvaso() as c:
                darabok = [_darabsor(x) for x in frissites.jegyzet_darabjai(c, ut, kihagyott=self.b.kihagyott)]
        if not darabok:
            return ut.rsplit("/", 1)[-1]
        q_tovek = normal.tovek(q)
        pont = rangsor.bm25(q_tovek, {i: normal.tovek(" ".join((*d.fejezet, d.szoveg))) for i, d in enumerate(darabok)})
        i = max(range(len(darabok)), key=lambda i: (pont.get(i, 0.0), -i))
        return rerank_szoveg(darabok[i])

    # ------------------------------------------------------------------ darabszintű jelöltek (vault-válasz)

    def darab_jeloltek(self, kerdes: str, n: int = 8) -> list[Jelolt]:
        """A kérdéshez legjobb `n` darab (lásd a modul leírását). Beágyazó nélkül csak a lexikai ág fut."""
        if not isinstance(kerdes, str) or not kerdes.strip():
            raise kodol(Invalid("üres kérdés"), "hibrid.kereso.ures_kerdes")
        q_tovek = normal.tovek(kerdes)
        jeloltek: dict[tuple[str, int], DarabSor] = {}
        hasonlosag: dict[tuple[str, int], float] = {}
        vek_rend: list[tuple[str, int]] = []
        if self.miert_lexikai() is None:
            qv = self.beagyazo([kerdes], "kerdes")[0]
            vek = [(i, p) for i, p in self.tar.keres(qv, self.b.darab_n) if p > 0]
            pont = dict(vek)
            for d in self.tar.darabok([i for i, _ in vek]):
                if self._kiz(d.ut):
                    continue
                kulcs = (d.ut, d.sorszam)
                jeloltek[kulcs] = d
                hasonlosag[kulcs] = pont[d.id]
                vek_rend.append(kulcs)
        with self.index_olvaso() as c:
            lex = self._lexikai(c, kerdes)
            for ut in lex["utak"][:self.b.lexikai_jegyzet_darab]:
                tarbeli = self.tar.darabok(ut=ut) if self.tar is not None else []
                for d in tarbeli or [_darabsor(x) for x in frissites.jegyzet_darabjai(c, ut, kihagyott=self.b.kihagyott)]:
                    jeloltek.setdefault((d.ut, d.sorszam), d)
        if not jeloltek:
            return []
        tovek = {k: normal.tovek(" ".join((d.cim, *d.fejezet, d.szoveg))) for k, d in jeloltek.items()}
        bm = rangsor.bm25(q_tovek, tovek)
        lex_rend = sorted(bm, key=lambda k: (-bm[k], k))
        fuzott = rangsor.rrf({"lexikai": lex_rend, "vektor": vek_rend}, self.b.rrf_k,
                             {"lexikai": self.b.lexikai_suly, "vektor": self.b.vektor_suly})
        sorrend = [(k, p, h) for k, p, h in fuzott]
        if self.b.rerank and self.reranker is not None:
            try:
                rr = rangsor.rerankel(kerdes, [(k, rerank_szoveg(jeloltek[k])) for k, _, _ in fuzott], self.reranker,
                                      self.b.rerank_n)
                agak = {k: h for k, _, h in fuzott}
                sorrend = [(k, p if p is not None else 0.0, agak[k]) for k, p in rr]
            except ValueError:
                pass
        return [Jelolt(jeloltek[k], p, round(rangsor.fedes(q_tovek, tovek[k]), 4), hasonlosag.get(k), h)
                for k, p, h in sorrend[:n]]
