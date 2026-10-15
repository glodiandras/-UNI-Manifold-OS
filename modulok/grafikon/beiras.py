"""A ```plot blokk automatikus beírása (C35b-mag; CLAUDE.md 5. és 28. döntés, `docs/PLOT-FORMATUM.md`).

A **determinisztikus ág**: a C35a felismerője által `biztos`-nak ítélt képlet alá a kész blokkot a **gépi-írás szolgáltatáson**
át írja (`core/gepi_kliens.py`; a lánc a vaultba közvetlenül nem nyúl). A modell itt nincs; a modell-ág `modell_ag.py`.

- `terv(szoveg, javaslatok, tiltott)` — **tiszta**: mely képletek alá kerül blokk, és miért marad ki a többi.
- `beszur(szoveg, beszurasok)` — **tiszta**: az új jegyzetszöveg (sortörés-hű; a blokk a képlet UTÁN, üres sorral elválasztva).
- `Beiro.jegyzet(ut)` — egy jegyzet: olvas (`hash`), felismer, tervez, **egy `csere` művelet alap-hash-sel = egy tétel = egy gépi
  commit** (`Mos-Forras: mos-plot`; a jegyzet összes új blokkja egy commitban, így a „Visszavonás” a jegyzet blokkjait együtt viszi);
  a beírt blokkokat a `Beirasok` naplóba jegyzi (a törlés későbbi felismeréséhez). Próbamódban (`proba=True`, D9: APFS-klón)
  napló nem készül.
- `torles_ellenorzes(...)` — a naplóból: a felhasználó által törölt blokk képlete a tiltólistára kerül (visszavonás, kézi
  szerkesztés, átrendezés nem).

Amit **nem** csinál (a „bizonytalan jobb, mint a téves” elv): nem ír táblázat-, idézet-, lista- vagy behúzott sor alá (a blokk ott
széttörné a szerkezetet); nem ír kódblokkba és frontmatterbe; képletenként egyszer ír (azonos kulcsú ismétlődő képlet alá
csak az elsőhöz); jegyzetenként legfeljebb `max_db` blokkot; kézzel írt blokkhoz nem nyúl (ha 3 soron belül már van plot blokk,
a javaslat `blokk_kovetkezik`); a tiltólistás képlet alá nem ír; `Status`-t, frontmattert nem érint (a csere csak a törzset
bővíti, a séma-kaput a szolgáltatás tartja).

A `kliens` egy `core.gepi_kliens`-szerű objektum (`olvas`, `ir`, `uj_kor`, `csere`, `GepiHiba`); a `felismero` egy
`szöveg → javaslat-szótárak` hívható (élesben `grafikon.felismer_jegyzet` a CAS-homokozón át) — így a teszt álhívóval fut.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from . import formatum as F
from . import jegyzet as J
from . import tiltolista as T

FORRAS = "mos-plot"                      # a gépi commit `Mos-Forras` trailere
KOR_ELOTAG = "PLOT"
MAX_DB = 8                               # egy jegyzetbe egy futásban legfeljebb ennyi blokk
_LISTA = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s")
_RAJZELEM = (F.Fuggveny, F.Parameteres, F.Egyenlotlenseg)

# a kihagyás okai (a riportban és a CLI-ben magyarul)
OKOK = {
    "nem_biztos": "a felismerés nem `biztos` (a bizonytalan a modell-ágra marad)",
    "nincs_hely": "a képletnek nincs jegyzetbeli sora",
    "van_blokk": "a képlet alatt már van plot blokk",
    "tiltolista": "a képlet a tiltólistán van (a felhasználó törölte a blokkját)",
    "kulcs_elteres": "a javaslat kulcsa nem egyezik a képlet kulcsával",
    "rossz_blokk": "a javaslat blokkja nem kanonikus vagy nem rajzol semmit",
    "kodban": "a képlet sora kódblokkban vagy a frontmatterben áll",
    "nem_beszurhato_sor": "táblázat-, idézet-, lista- vagy behúzott sor alá nem írunk",
    "ismetlodo": "ugyanez a képlet már kapott blokkot ebben a jegyzetben",
    "tul_sok": "a jegyzetenkénti blokk-korlát betelt",
}


@dataclass(frozen=True)
class Beszuras:
    kulcs: str
    veg_sor: int                         # a képlet utolsó sora (1-től): a blokk ez után kerül
    blokk: str                           # a teljes kerített blokk, záró újsorral
    torzs: str                           # a blokk két kerítés közti kanonikus szövege
    fajta: str = ""
    keplet: str = ""
    mod: str = "eles"                    # `proba`: a modell-ág blokkja, kalibrálatlan modellből (D9: csak APFS-klónra írható)


def kodos_sorok(szoveg: str) -> set[int]:
    """A frontmatter és a kerített kódblokkok sorai (1-től; a kerítések is; a ```math nem kód). Ide nem szúrunk be."""
    sorok = (szoveg or "").splitlines()
    ki: set[int] = set()
    i = 0
    if sorok and sorok[0].rstrip() == "---":
        for j in range(1, len(sorok)):
            if sorok[j].rstrip() in ("---", "..."):
                ki.update(range(1, j + 2))
                i = j + 1
                break
    while i < len(sorok):
        m = F._KERITES.match(sorok[i])
        if not m or (m.group(1)[0] == "`" and "`" in m.group(2)):
            i += 1
            continue
        jel = m.group(1)
        j = i + 1
        while j < len(sorok):
            z = F._KERITES.match(sorok[j])
            if z and z.group(1)[0] == jel[0] and len(z.group(1)) >= len(jel) and not z.group(2).strip():
                break
            j += 1
        if m.group(2).strip().lower() != "math":          # a ```math kerítés képlet, nem kód: a blokk a záró kerítés UTÁN kerül
            ki.update(range(i + 1, min(j, len(sorok) - 1) + 2))
        i = j + 1
    return ki


def _beszurhato(sor: str) -> bool:
    s = sor.rstrip("\r\n")
    return not (s[:1] in (" ", "\t") or s.lstrip().startswith((">", "|")) or _LISTA.match(s))


def _blokk_torzs(blokk: str) -> str | None:
    """A javaslat blokkjának kanonikus törzse, ha a blokk hibátlan és rajzol valamit; különben `None`."""
    hely = F.blokkok(blokk)
    if len(hely) != 1 or not hely[0].lezart or hely[0].abra.hibak:
        return None
    abra = hely[0].abra
    if not any(isinstance(e, _RAJZELEM) for e in abra.elemek) or any(isinstance(e, F.Ismeretlen) for e in abra.elemek):
        return None
    torzs = F.szerializal(abra)
    return torzs if F.blokk(abra) == blokk else None


def terv(szoveg: str, javaslatok: list[dict], tiltott=frozenset(), max_db: int = MAX_DB) -> tuple[list[Beszuras], list[dict]]:
    """→ (beszúrások, kihagyottak `{kulcs, sor, ok, szoveg}`). Tiszta függvény: nem olvas, nem ír, modellt nem hív."""
    sorok = (szoveg or "").splitlines()
    kod = kodos_sorok(szoveg)
    blokkok = F.blokkok(szoveg or "")
    hely = {}
    for i, k in J.jeloltek(szoveg or ""):                       # (sor, képlet) → karakterhely: a tároló végének kereséséhez
        hely.setdefault(((szoveg or "").count("\n", 0, max(i, 0)) + 1, k), i)
    kesz: list[Beszuras] = []
    latott: set[str] = set()
    ki: list[dict] = []

    def kihagy(j: dict, ok: str):
        ki.append({"kulcs": j.get("kulcs", ""), "sor": j.get("sor"), "ok": ok, "szoveg": OKOK[ok]})

    for j in javaslatok:
        if j.get("bizonyossag") != "biztos" or not j.get("blokk"):
            kihagy(j, "nem_biztos")
        elif j.get("sor") is None or j.get("veg_sor") is None or not 1 <= j["veg_sor"] <= len(sorok):
            kihagy(j, "nincs_hely")
        elif (veg := J.tarolo_veg_sor(szoveg, hely.get((j["sor"], j.get("forras_keplet"))), j.get("forras_keplet") or "")) is None \
                or not 1 <= veg <= len(sorok):
            kihagy(j, "nincs_hely")
        elif j.get("blokk_kovetkezik") or J.van_blokk_alatta(blokkok, veg):
            kihagy(j, "van_blokk")
        elif j["kulcs"] in tiltott:
            kihagy(j, "tiltolista")
        elif j["kulcs"] in latott:
            kihagy(j, "ismetlodo")
        elif T.kulcs_szoveg(j.get("forras_keplet") or "") != j["kulcs"]:
            kihagy(j, "kulcs_elteres")
        elif (torzs := _blokk_torzs(j["blokk"])) is None or (
                j.get("abra") is not None and "_mod" not in j and F.abra_szotar(F.elemez(torzs)) != j["abra"]):
            kihagy(j, "rossz_blokk")            # a blokk a felismerő saját ábrájával is egyezzen (a modell-ág blokkja kivétel)
        elif any(s in kod for s in range(j["sor"], veg + 1)):
            kihagy(j, "kodban")
        elif not all(_beszurhato(sorok[s - 1]) for s in range(j["sor"], veg + 1)):
            kihagy(j, "nem_beszurhato_sor")
        elif len(kesz) >= max_db:
            kihagy(j, "tul_sok")
        else:
            latott.add(j["kulcs"])
            kesz.append(Beszuras(j["kulcs"], veg, j["blokk"], torzs, j.get("fajta", ""), j.get("forras_keplet", ""),
                                 j.get("_mod", "eles")))
    return kesz, ki


def beszur(szoveg: str, beszurasok: list[Beszuras]) -> str:
    """A blokkok beszúrása a képlet utolsó sora után, alulról felfelé (a sorszámok nem csúsznak). A sortörés a jegyzeté (CRLF-hű)."""
    nl = "\r\n" if "\r\n" in szoveg else "\n"
    sorok = szoveg.splitlines(keepends=True)
    for b in sorted(beszurasok, key=lambda x: x.veg_sor, reverse=True):
        i = b.veg_sor                                        # a képlet utolsó sora a `sorok[i - 1]`; a beszúrás a `sorok[i]` elé
        if not sorok[i - 1].endswith(("\n", "\r")):
            sorok[i - 1] += nl
        resz = nl + b.blokk.replace("\n", nl)
        if i < len(sorok) and sorok[i].strip():
            resz += nl
        sorok.insert(i, resz)
    return "".join(sorok)


class Beiro:
    """Egy jegyzet automatikus beírása a gépi-írás szolgáltatáson át (lásd a modul docstringjét).

    `modell`: opcionális `hivo(prompt, max_tokens) -> szöveg` (modell-ág, `modell_ag.py`) a `bizonytalan` javaslatokra; `kalibralt`:
    a `grafikon` router-feladat kalibrált-e (D9). Kalibrálatlan modell (vagy referenciával nem egyeztetett blokk) kimenete csak
    `proba: true` írással — APFS-klónra, napló nélkül — kerülhet a vaultba; a modell nélküli ág változatlan."""

    def __init__(self, kliens, felismero: Callable[[str], list[dict]], tiltolista, beirasok, proba: bool = False,
                 max_db: int = MAX_DB, varakozas_mp: float = 30.0, modell=None, kalibralt: bool = False, homokozo=None,
                 modell_jel: dict | None = None):
        self.kliens, self.felismero, self.tiltolista, self.beirasok = kliens, felismero, tiltolista, beirasok
        self.proba, self.max_db, self.varakozas_mp = proba, max_db, varakozas_mp
        self.modell, self.kalibralt, self.homokozo = modell, kalibralt, homokozo
        # D9 (C29.8, 28(g)): a gépi írás `modell` kulcsa kötelező. A modell nélküli ág determinisztikus (`None`); a modell-ág
        # blokkja a worker válaszából képzett jelet (`gepi_kliens.modell_jel`) viszi — jel nélkül a modell kimenete csak próba.
        self.modell_jel = modell_jel
        self._modell_kulcsok: set = set()
        self._jel = modell_jel
        self.fuggoben = 0                                    # a modellre váró (nem elérhető modell) képletek száma a legutóbbi jegyzetnél

    def _modell_ag(self, javaslatok: list[dict], tiltott) -> tuple[list[dict], list[dict]]:
        """A `bizonytalan` javaslatok → (a modell blokkjával kiegészített javaslatok, a modell-ág naplója). A modell kalibráltsága és
        gépi-írás jele (D9) a hívó attribútuma (`kalibralt`, `jel`), a hívás UTÁN olvasva — a worker-kötés lusta (`modell_hivo.Hivo`)."""
        from . import modell_ag
        ki, naplo = [], []
        for j in javaslatok:
            if self.modell is None or j.get("bizonyossag") != "bizonytalan" or j.get("kulcs") in tiltott or j.get("blokk_kovetkezik"):
                ki.append(j)
                continue
            e = modell_ag.javasol(j, self.modell, homokozo=self.homokozo)
            if e["allapot"] in ("modell_var", "modell_hiba"):
                self.fuggoben += 1                           # később újrapróbáljuk: a jegyzet nem számít feldolgozottnak
            kalibralt = bool(getattr(self.modell, "kalibralt", self.kalibralt))
            jel = getattr(self.modell, "jel", None) or self.modell_jel
            mod = modell_ag.iras_mod(e, kalibralt)
            if mod == "eles" and jel is None:
                mod = "proba"                                # D9 (C29.8): modell-jel nélkül a modell kimenete élesben nem írható
            naplo.append({"kulcs": j.get("kulcs"), "sor": j.get("sor"), "allapot": e["allapot"], "ok": e["ok"],
                          "egyeztetes": e["egyeztetes"], "mod": mod})
            if mod:
                self._modell_kulcsok.add(j.get("kulcs"))
                self._jel = jel
            ki.append({**j, "bizonyossag": "biztos", "blokk": e["blokk"], "_mod": "proba" if self.proba else mod} if mod else j)
        return ki, naplo

    def _ir(self, K, ut: str, kor: str, uj: str, hash_: str, proba: bool, blokkok=()) -> dict:
        modell = self._jel if any(b.kulcs in self._modell_kulcsok for b in blokkok) else None
        return K.ir(kor, tetel=ut, forras=FORRAS, proba=proba, uzenet=f"grafikon a képlet alá: {ut}"[:200],
                    varakozas_mp=self.varakozas_mp, muveletek=[K.csere(ut, uj, hash_)], modell=modell)

    def jegyzet(self, ut: str, kor: str | None = None, szoveg: str | None = None) -> dict:
        """→ `{allapot, ut, beirt, kihagyva, …}`; `allapot`: `kesz` (írt) | `nincs_teendo` | `elhalasztva` (a jegyzet nyitva van
        mentetlenül, vagy a kör-zár foglalt: a következő futás újrapróbálja) | `utkozes` (közben megváltozott) | `elutasitva`
        (a szolgáltatás kapuja: séma) | `nincs_jegyzet` | `nem_ellenorizheto` (a CAS-homokozó nem érhető el: nem írunk, és a
        jegyzet nem számít feldolgozottnak)."""
        K = self.kliens
        try:
            d = K.olvas(ut)
        except K.GepiHiba as e:
            if e.kod == 404:
                return {"allapot": "nincs_jegyzet", "ut": ut, "beirt": [], "kihagyva": []}
            raise
        elozo = d["tartalom"]
        self.fuggoben = 0
        javaslatok = self.felismero(elozo if szoveg is None else szoveg)
        if any(j.get("allapot") == "nem_ellenorizheto" for j in javaslatok):
            return {"allapot": "nem_ellenorizheto", "ut": ut, "beirt": [], "kihagyva": [],
                    "ok": next(j["ok"] for j in javaslatok if j.get("allapot") == "nem_ellenorizheto")}
        tiltott = self.tiltolista.kulcsok()
        javaslatok, modell_naplo = self._modell_ag(javaslatok, tiltott)
        beszurasok, kihagyva = terv(elozo, javaslatok, tiltott, self.max_db)
        ki = {"allapot": "nincs_teendo", "ut": ut, "beirt": [], "kihagyva": kihagyva, "modell": modell_naplo,
              "fuggoben": self.fuggoben, "tartalom": elozo, "hash_utan": d["hash"]}
        if not beszurasok:
            return ki
        eles = [b for b in beszurasok if b.mod == "eles"]
        probak = [b for b in beszurasok if b.mod == "proba"]
        kor = kor or K.uj_kor(KOR_ELOTAG)
        beirt, sha, allapot, v = [], None, "nincs_teendo", {}
        try:
            if probak:                                       # előbb a klón: az eredeti szövegből indul (a hash egyezik)
                self._ir(K, ut, K.uj_kor(KOR_ELOTAG), beszur(elozo, probak), d["hash"], True, probak)
                ki["proba_beirt"] = [{"ut": ut, "kulcs": b.kulcs} for b in probak]
                allapot = "kesz"
            if eles:
                v = self._ir(K, ut, kor, beszur(elozo, eles), d["hash"], self.proba, eles)
                beirt = [{"ut": ut, "kulcs": b.kulcs, "blokk": b.torzs, "sha": v.get("sha")} for b in eles]
                if v.get("valtozas") and not self.proba and v.get("sha"):
                    self.beirasok.hozzaad(beirt)
                sha = v.get("sha")
                if v.get("valtozas"):
                    allapot = "kesz"
        except K.GepiHiba as e:
            if e.kod == 409 and (e.adat.get("nyitott") or e.adat.get("foglalt")):
                return {**ki, "allapot": "elhalasztva", "ok": str(e)}
            if e.kod == 409:
                return {**ki, "allapot": "utkozes", "ok": str(e)}
            if e.kod == 400:
                return {**ki, "allapot": "elutasitva", "ok": str(e), "sema": bool(e.adat.get("sema"))}
            raise
        return {**ki, "allapot": allapot, "beirt": beirt, "sha": sha, "proba": self.proba,
                "hash_utan": ((v.get("hash") or {}).get(ut) if eles and v.get("valtozas") and not self.proba else None) or d["hash"]}


# ------------------------------------------------------------------ a törlés felismerése → tiltólista

def visszavont_shak(kliens, tar: str = "vault", n: int = 500) -> set[str]:
    """A pillanatkép-napló visszavonó commitjainak célja (`Mos-Visszavon: <sha>`): a gépi commit visszavonása nem tiltólistáz.
    Feltevés (a C29.8 interfésze nincs ezen az ágon): a `GET /api/pillanat/<tár>/naplo` a `trailerek` mezőben adja a trailereket."""
    v = kliens._keres(f"/api/pillanat/{tar}/naplo?n={int(n)}")
    return {c["trailerek"]["Mos-Visszavon"] for c in v.get("commitok", []) if (c.get("trailerek") or {}).get("Mos-Visszavon")}


def torles_ellenorzes(kliens, tiltolista, beirasok, visszavont: set[str]) -> list[dict]:
    """A gépi beírások naplójából: törölt blokk → a képlet kulcsa a tiltólistára (a rekord ezzel lezárul).
    → `[{ut, kulcs, dontes}]` rekordonként. Ami `megvan`/`szerkesztve`/`athelyezve`, a naplóban marad (a törlés később is
    felismerhető); ami `torolve`, `visszavonva` vagy `keplet_eltunt`, a naplóból kikerül. `nincs_jegyzet` (átnevezés, törlés,
    olvasási hiba): a rekord marad — az átnevezés-követés a C35b maradéka (NAPLO)."""
    ki = []
    for r in beirasok.lista():
        try:
            szoveg = kliens.olvas(r["ut"])["tartalom"]
        except kliens.GepiHiba as e:
            if e.kod != 404:
                raise
            szoveg = None
        sha = str(r.get("sha") or "")
        vissza = bool(sha) and any(h.startswith(sha) or sha.startswith(h) for h in map(str, visszavont) if h)
        dontes = T.torles_dontes(r, szoveg, vissza)
        if dontes == T.TORLES:
            tiltolista.felvesz(r["kulcs"], r["ut"])
        if dontes in (T.TORLES, T.VISSZAVONVA, T.KEPLET_ELTUNT):
            beirasok.torol(r["ut"], r["kulcs"])
        ki.append({"ut": r["ut"], "kulcs": r["kulcs"], "dontes": dontes})
    return ki
