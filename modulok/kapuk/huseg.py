"""A közös forráshűség-kapu: *állítás → forrásmondat → egyezés-vizsgálat küszöbbel*.

`ellenoriz(forras, allitas, idezet, profil)` egy állítást vet össze azzal az idézettel, amelyre a láncok szerint épül.
A szabályok (a `Verdikt.okok` megnevezi, melyik bukott):

1. **hossz** — az idézet szószáma a profil tartományában;
2. **kötött** — az idézet a forrásban áll (szószintű pontos egyezés, utána betűszintű csúszóablak a `kuszob`-ig);
3. **támogatott** — az állítás tartalmi töveinek legalább `tamogatas_kuszob` része a *bizonyítékban* áll (a talált
   forrásrész; vagy a kibővített mondat; vagy a mondat, a jegyzet és a fejezetek címe — `bizonyitek`);
4. **kényes tokenek** — minden szám és minden tulajdonnév (nagybetűs szó, amely mondaton belül vagy máshol a jegyzetben
   nagybetűs) az állításban a bizonyítékban is szerepel: ez fogja meg a szám- és névcserét, amit a lefedettség nem;
5. **tagadás** — az állítás nem vezet be tagadást, amely a bizonyítékban nincs (`bevezetett`), vagy a tagadás jelenléte
   egyezik (`paritas`), vagy nincs vizsgálat (`ki`).

A kapu **lexikai** és modellt nem hív: az átfogalmazott hamis állítást, a szinonima/ellentét cserét és a mondaton belüli
névcserét nem látja (`docs/C22-KAPU-MERES.md`). A fogyasztó az `allitas`-t maga állítja össze (összefoglaló: az állítás
mondata; kártya és kvíz: a válasz, a kérdés pedig `kontextus`: csak a számai és nevei számítanak; vault-válasz: a válasz mondata). A küszöböket az `os.toml` `[kapuk]` szakasza
adja, a C18 `szoveg` halmazán mérve; `[kapuk.<fogyasztó>]` felülírhatja (ma a hossz-határokat).
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields

from . import tokenek
from .forras import ForrasSzoveg, Talalat, kepletek_nelkul

BIZONYITEKOK = ("idezet", "mondat", "mondat+cim")
TAGADAS_MODOK = ("bevezetett", "paritas", "ki")
FOGYASZTOK = ("osszefoglalo", "kartya", "kviz", "valasz")


@dataclass(frozen=True)
class Profil:
    nev: str = "alap"
    idezet_min_szo: int = 4
    idezet_max_szo: int | None = 45
    idezet_kuszob: float = 0.85          # az idézet hasonlósága a forráshoz (1,0: szó szerint)
    tamogatas_kuszob: float = 0.5        # az állítás tartalmi töveinek aránya a bizonyítékban
    bizonyitek: str = "mondat+cim"
    kenyes: bool = True
    tagadas: str = "bevezetett"
    mondat_max_karakter: int = 600       # a bizonyítékul vett mondat hossza (fölötte a talált rész)

    def __post_init__(self):
        if self.bizonyitek not in BIZONYITEKOK:
            raise ValueError(f"[kapuk] bizonyitek: {', '.join(BIZONYITEKOK)} lehet, nem {self.bizonyitek!r}")
        if self.tagadas not in TAGADAS_MODOK:
            raise ValueError(f"[kapuk] tagadas: {', '.join(TAGADAS_MODOK)} lehet, nem {self.tagadas!r}")
        for k in ("idezet_kuszob", "tamogatas_kuszob"):
            v = getattr(self, k)
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 1:
                raise ValueError(f"[kapuk] {k}: 0 és 1 közötti szám kell, nem {v!r}")
        if self.idezet_min_szo < 1 or (self.idezet_max_szo is not None and self.idezet_max_szo < self.idezet_min_szo):
            raise ValueError("[kapuk] idezet_min_szo/idezet_max_szo: 1 ≤ min ≤ max kell")


_MEZOK = {f.name for f in fields(Profil)} - {"nev"}
_NEM_PROFIL = {"kihagyott_szakaszok"}            # a `[kapuk]` szakasz kulcsa, de nem a profilé: a `forras.kihagyott_szakaszok(cfg)` olvassa


def profil(cfg, nev: str | None = None) -> Profil:
    """A profil az `os.toml` `[kapuk]` szakaszából, a `[kapuk.<nev>]` felülírásával. Ismeretlen kulcs vagy érték hiba."""
    szakasz = cfg.section("kapuk")
    adat = {k: v for k, v in szakasz.items() if not isinstance(v, dict) and k not in _NEM_PROFIL}
    if nev:
        adat.update(cfg.section("kapuk", nev))
    ismeretlen = sorted(set(adat) - _MEZOK)
    if ismeretlen:
        raise ValueError(f"[kapuk{'.' + nev if nev else ''}]: ismeretlen kulcs: {', '.join(ismeretlen)}")
    return Profil(nev=nev or "alap", **adat)


@dataclass
class Verdikt:
    ok: bool
    okok: list[str] = field(default_factory=list)       # a bukott szabályok: hossz | kotott | tamogatas | kenyes | tagadas
    hely: tuple[int, int] | None = None                 # a találat a `ForrasSzoveg.szoveg`-ben
    szakasz: int | None = None                          # a találat szakaszának sorszáma
    hasonlosag: float = 0.0
    szoszam: int = 0                                    # az idézet szavai
    lefedettseg: float | None = None                    # az állítás tövei közül a bizonyítékban állók aránya
    hianyzo: list[str] = field(default_factory=list)    # a bizonyítékból hiányzó számok és nevek (tövek)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "okok": list(self.okok), "hely": list(self.hely) if self.hely else None,
                "szakasz": self.szakasz, "hasonlosag": self.hasonlosag, "szoszam": self.szoszam,
                "lefedettseg": self.lefedettseg, "hianyzo": list(self.hianyzo)}


@dataclass
class BizonyitekMeres:
    """Az állítás és egy bizonyíték-változat nyers mérése (küszöbtől független)."""
    lefedettseg: float
    hianyzo_szamok: list[str]
    hianyzo_nevek: list[str]
    tagado: bool


@dataclass
class Meres:
    """Az állítás és az idézet nyers mérése a forráson: a küszöbök nélküli jellemzők (a `dont` ezekből dönt, a mérés a
    küszöbrácsot ezeken járja be újraszámolás nélkül)."""
    szoszam: int
    talalat: Talalat | None                              # a legjobb találat bármilyen hasonlósággal
    allitas_tagado: bool
    elemek: int                                          # a lefedettség nevezője: az állítás töveinek (vagy jeleinek) száma
    bizonyitek: dict[str, BizonyitekMeres] = field(default_factory=dict)       # a BIZONYITEKOK szerint


def bizonyitek_szoveg(forras: ForrasSzoveg, t: Talalat, mod: str, mondat_max: int = 600) -> str:
    """Amihez az állítást mérjük: a talált rész, a kibővített mondat, vagy a mondat a jegyzet és a fejezetek címével."""
    if mod == "idezet":
        return t.szoveg
    mondat = forras.mondat(t.hely[0], t.hely[1], max_k=mondat_max)
    if mod == "mondat":
        return mondat
    return " ".join(x for x in (mondat, forras.cim, *forras.szakaszok[t.szakasz].ut) if x)


def merj(forras: ForrasSzoveg, allitas: str, idezet: str, mondat_max_karakter: int = 600, kontextus: str = "") -> Meres:
    """Az állítás és az idézet nyers mérése: a találat (küszöb nélkül) és bizonyíték-változatonként a lefedettség, a
    hiányzó számok és nevek, a tagadás. A `kontextus` (pl. a kérdés) szavai nem számítanak a lefedettségbe, de a
    képleteken kívüli számai és tulajdonnevei a bizonyítékban is állnak. Modellt nem hív, a forrást nem módosítja."""
    allitas = allitas or ""
    tovek = tokenek.tovek(allitas)
    elemek = tovek or tokenek.jelek(allitas)            # tartalmi szó nélküli (képletes, számos) állításnál a jelek
    m = Meres(szoszam=len(tokenek.szavak(idezet or "")), talalat=forras.keres(idezet, 0.0),
              allitas_tagado=tokenek.tagado(allitas), elemek=len(elemek))
    if m.talalat is None:
        return m
    # a kontextus (a kérdés) képletei kiesnek: a „(a+b)^2” kitevője a megelőző mondatból jön, nem a bizonyítékból; a sortörés
    # mondathatár (a kontextus első szava mondatkezdő)
    teljes = f"{allitas}\n{kepletek_nelkul(kontextus or '')}"
    szamok = tokenek.szamok(teljes)
    nevek = {tokenek.to(w) for w, kezdo in tokenek.nagybetus(teljes)
             if len(w) >= 3 and (not kezdo or tokenek.to(w) in forras.nevtovek())} - tokenek.FUGGVENYSZOK
    for mod in BIZONYITEKOK:
        biz = bizonyitek_szoveg(forras, m.talalat, mod, mondat_max_karakter)
        biz_tovek = tokenek.tovek(biz, stop=False)
        fedett = tokenek.lefedett(tovek, biz_tovek) if tovek else elemek & tokenek.jelek(biz)
        m.bizonyitek[mod] = BizonyitekMeres(
            lefedettseg=len(fedett) / len(elemek) if elemek else 0.0,
            hianyzo_szamok=sorted(szamok - tokenek.szamok(biz)), hianyzo_nevek=sorted(nevek - tokenek.lefedett(nevek, biz_tovek)),
            tagado=tokenek.tagado(biz))
    return m


def dont(m: Meres, p: Profil) -> Verdikt:
    """A mérés és a profil küszöbei szerinti ítélet. Csak a bukott szabályok kerülnek az `okok`-ba; ha az idézet nincs a
    forrásban, a többi szabály nem értelmezhető (nincs bizonyíték), és csak a `kotott` (esetleg a `hossz`) szerepel."""
    v = Verdikt(ok=False, szoszam=m.szoszam)
    if m.szoszam < p.idezet_min_szo or (p.idezet_max_szo is not None and m.szoszam > p.idezet_max_szo):
        v.okok.append("hossz")
    t = m.talalat
    if t is None or t.hasonlosag < p.idezet_kuszob:
        v.okok.append("kotott")
        return v
    v.hely, v.szakasz, v.hasonlosag = t.hely, t.szakasz, t.hasonlosag
    b = m.bizonyitek[p.bizonyitek]
    v.lefedettseg = b.lefedettseg
    if not m.elemek or b.lefedettseg < p.tamogatas_kuszob:
        v.okok.append("tamogatas")
    if p.kenyes:
        v.hianyzo = b.hianyzo_szamok + b.hianyzo_nevek
        if v.hianyzo:
            v.okok.append("kenyes")
    if p.tagadas != "ki" and ((m.allitas_tagado and not b.tagado) or (p.tagadas == "paritas" and b.tagado and not m.allitas_tagado)):
        v.okok.append("tagadas")
    v.ok = not v.okok
    return v


def ellenoriz(forras: ForrasSzoveg, allitas: str, idezet: str, profil: Profil | None = None, kontextus: str = "") -> Verdikt:
    """Az állítás és az idézet vizsgálata a forráson (`merj` + `dont`)."""
    p = profil or Profil()
    return dont(merj(forras, allitas, idezet, p.mondat_max_karakter, kontextus), p)
