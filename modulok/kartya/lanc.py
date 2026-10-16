"""A kártya-lánc I/O-ja (C23b; `docs/C23-TERV.md` 5. fejezet; CLAUDE.md 28., 45., 56. döntés, D9): a jegyzet olvasása a core-tól,
a modell a workeren át, az írás a gépi-írás szolgáltatáson át. A kapuk a `generalas.py`-ban, a forrás módosítása a `horgony.py`-ban.

    futtat(cfg, ut, gepi=gepi_kliens, worker=Worker(cfg), automatikus=False, proba=False) → összegzés

**Egy jegyzet = egy tétel = egy gépi commit** (`Mos-Forras: mos-kartya`, kör `KARTYA-…`): a kísérőjegyzet (`uj` a `kartya`
sémaosztállyal, vagy `csere` alap-hash-sel a meglévő végére fűzve) és a forrás egyetlen `csere`-je (a `^m-…` horgonyok és a
`## Gyakorlás` beágyazó sora együtt). A nyitott, mentetlen dokumentum 409-et ad; a gépi kliens a határidőig újrapróbál, utána a
jegyzet kimarad (az automatika később újra sorra veszi). Utána a kártyamappa → `tanulas.sqlite` szinkron (eredet `gep`) és az
automatika-tár `kesz` jele.

**D9**: a modell a `szoveg` router-feladat kalibrált modellje (a C19 szerint a kártya ennek a kalibrációjával fut; a `kartya` saját
router-feladata nincs mérve) — a worker routere választ; kalibrált modell nélkül élesben nincs kártya. A kifejezett modell (próba)
és a `proba` az írást az APFS-klónra viszi (`proba: true`), a tanulási adatbázishoz és az automatika-tárhoz ekkor nem nyúl.
"""
from __future__ import annotations

import os
from datetime import date

from core import rejtett

from . import formatum, generalas, horgony, szinkron

FELADAT = "szoveg"
FORRAS = "mos-kartya"
KOR_ELOTAG = "KARTYA"
FOGYASZTO = "kartya"


class Megall(Exception):
    """A kártyák nem készülhetnek el — az üzenet a felhasználónak szól (a feladatsor hibaként mutatja)."""


class Worker:
    """A worker a `core.modell.kliens`-en át; a kérés-beállítás (gondolkodás, token-keret) a regiszterből, a mérés szabályával
    (`core.modell.eval.keres_beallitas`, a `szoveg` feladat): az éles kérés ugyanaz, mint a mért."""

    def __init__(self, cfg):
        from core.modell import beallitas as B
        from core.modell import kliens
        self.kliens, self.b = kliens, B.betolt(cfg)
        self.u = kliens.url(cfg)
        self.utolso: dict | None = None

    def valaszt(self) -> dict:
        return self.kliens.keres(self.u, "/router/valaszt", {"feladat": FELADAT})

    def hivo(self, modell: str, kifejezett: bool):
        from core.modell import eval as E

        def hiv(prompt: str, max_tokens: int) -> str:
            k = E.keres_beallitas(self.b, self.b.modell(modell), FELADAT,
                                  {"tipus": "chat", "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens})
            uzenetek = k.pop("messages")
            k.pop("tipus", None)
            r = self.kliens.chat(self.u, uzenetek, feladat=FELADAT, modell=modell if kifejezett else None, **k)
            self.utolso = r
            return r["choices"][0]["message"]["content"]
        return hiv


def forras_cel(ut: str, vault_utak) -> str:
    """A forrás link-célja: az alapnév, ha a vaultban egyedi, különben az út `.md` nélkül (13. döntés: kis-nagybetű-független)."""
    ut = formatum.nfc(ut)
    alap = os.path.splitext(os.path.basename(ut))[0]
    db = sum(1 for u in vault_utak if os.path.splitext(os.path.basename(formatum.nfc(u)))[0].casefold() == alap.casefold())
    return alap if db <= 1 else ut[:-3]


def _celja(link: str) -> str:
    return formatum.nfc(link.split("#", 1)[0].split("|", 1)[0].strip()).casefold()


def kisero_keres(elemzesek: dict, ut: str) -> str | None:
    """A forrás meglévő kísérőjegyzete: amelyiknek a `Source`-a a forrásra mutat (az alapnévre vagy az útra)."""
    jel = {formatum.nfc(ut[:-3]).casefold(), formatum.nfc(os.path.splitext(os.path.basename(ut))[0]).casefold()}
    for k_ut in sorted(elemzesek):
        if any(_celja(s) in jel for s in elemzesek[k_ut].source):
            return k_ut
    return None


def vault_md_utak(cfg) -> list[str]:
    """A vault `.md` útjai (csak olvas; rejtett mappa nélkül)."""
    vault = str(cfg.path("vault"))
    ki = []
    for d, mappak, fajlok in os.walk(vault):
        mappak[:] = [m for m in rejtett.metsz(mappak) if not m.startswith(".")]     # I6: minden pontos mappa kimarad
        for f in fajlok:
            if f.lower().endswith(".md"):
                ki.append(formatum.nfc(os.path.relpath(os.path.join(d, f), vault)))
    return ki


def meglevo_kerdesek(cfg) -> tuple[tuple[str, ...], frozenset[str]]:
    """A tanulási adatbázis kérdései (a törölteké is) és a sírkövek: a generálás ezek ellen szűr."""
    from core import tanulas_db
    with tanulas_db.olvaso(cfg) as c:
        if c is None:
            return (), frozenset()
        return (tuple(r[0] for r in c.execute("SELECT kerdes FROM kartya WHERE kerdes != ''")),
                frozenset(r[0] for r in c.execute("SELECT ujjlenyomat FROM sirko")))


def _uj_mondatok(cfg, ut: str) -> set[str] | None:
    """Az automatika-tár szerint utoljára feldolgozott változathoz képest új mondatok (`None`: nincs alap → minden)."""
    import json

    from core import automatika
    sor = automatika.Tar(cfg).sor(FOGYASZTO, ut)
    if not sor or not sor.get("alap"):
        return None
    return set(json.loads(sor["alap"]))


def futtat(cfg, ut: str, *, gepi, worker, automatikus: bool = False, proba: bool = False, modell: str | None = None,
           kijeloles: str | None = None, kor: str | None = None, allj=lambda: False, naplo=lambda s: None) -> dict:
    """Kártyák egy jegyzetből: → `{allapot, kartyak, statisztika, kisero, …}`. Az `allapot`: `kesz` | `nincs_teendo` |
    `nincs_kartya`. `kijeloles`: a „Kártyák ebből” kijelölt szövege — csak abból kérdez (a horgony és a beágyazás a teljes
    jegyzetbe kerül; az automatika-tár ilyenkor nem jelöli feldolgozottnak a jegyzetet). Hiba: `Megall` (érthető üzenet) vagy a
    gépi kliens `GepiHiba`-ja."""
    from core import automatika

    b = generalas.beallitas(cfg)
    d = gepi.olvas(ut)
    ut, md, alap_hash = d["ut"], d["tartalom"], d["hash"]
    cim = formatum.nfc(os.path.splitext(os.path.basename(ut))[0])

    uj = None
    if automatikus:
        alap = _uj_mondatok(cfg, ut)
        if alap is not None:
            uj = set(automatika.mondatok(md)) - alap
    resz = bool(kijeloles and kijeloles.strip())
    alap_md = kijeloles if resz else md        # „Kártyák ebből” kijelölésből: csak abból kérdez
    n = generalas.mennyiseg(alap_md, b, automatikus=automatikus, csak=uj)
    if resz and n == 0 and generalas.mondatai(alap_md, b.kihagyott_szakaszok):
        n = 1                                  # a kifejezett kijelölésből legalább egy kártyát kérünk
    proba_allapot = proba or resz              # a részleges futás nem jelöli feldolgozottnak a jegyzetet
    if n == 0:
        if not proba_allapot:
            automatika.Tar(cfg).kesz(FOGYASZTO, ut, md, hash_=alap_hash)
        return {"allapot": "nincs_teendo", "ut": ut, "kartyak": 0, "ok": "nincs tényes (új) mondat"}

    # D9: a modell a router kalibrált `szoveg` modellje, vagy a kifejezett (próba) modell
    if modell is None:
        try:
            dont = worker.valaszt()
        except Exception as exc:  # noqa: BLE001 — a worker hibája üzenetként
            if getattr(exc, "kod", None) == 409:
                raise Megall(f"A `{FELADAT}` feladatra nincs kalibrált modell: élesen nem készül kártya. Próbához adj meg "
                             f"modellt (a kimenet a vault klónjára kerül). ({exc})") from None
            raise
        if not dont.get("modell"):
            raise Megall(f"A kártyák modellje most nem futhat: {dont.get('indok') or 'a távol-keretre vár'}.")
        m = dont["modell"]
    else:
        m = modell
        proba = True
    hivo = worker.hivo(m, kifejezett=modell is not None)

    vault_utak = vault_md_utak(cfg)
    cel = forras_cel(ut, vault_utak)
    elemzesek = szinkron.olvas_mappa(cfg)
    kisero = kisero_keres(elemzesek, ut)
    db_kerdes, sirkovek = meglevo_kerdesek(cfg)
    meglevo = tuple(k.kerdes for k in elemzesek[kisero].kartyak) if kisero else ()
    eredm = generalas.general(alap_md, cim, hivo, hivo, n, meglevo=meglevo + db_kerdes, sirkovek=sirkovek, forras_link=cel,
                              b=b, p=generalas.profil(cfg), log=naplo, allj=allj)
    if not eredm.kartyak:
        if not proba_allapot:
            automatika.Tar(cfg).kesz(FOGYASZTO, ut, md, hash_=alap_hash)
        return {"allapot": "nincs_kartya", "ut": ut, "kartyak": 0, "statisztika": eredm.statisztika,
                "elvetett": eredm.elvetett[:20]}
    jel = gepi.modell_jel(worker.utolso)
    proba = proba or jel["proba"]

    # a forrás: horgonyok + a `## Gyakorlás` beágyazó sora, egy szövegben
    uj_md, blokkok = horgony.horgonyoz(md, [k.idezet for k in eredm.kartyak])
    mappa = szinkron.mappa(cfg)
    if kisero:
        kisero_ut = kisero
        nev = os.path.splitext(os.path.basename(kisero))[0]
    else:
        nev = formatum.kiseronev(ut, vault_utak, utotag=cfg.section("kartya").get("utotag", formatum.UTOTAG))
        kisero_ut = f"{mappa}/{nev}.md"
    from core import gyakorlas
    from core.gepi_iras import szakasz_beszur
    try:
        uj_md = szakasz_beszur(uj_md, gyakorlas.FEJEZET, gyakorlas.beagyazo_sor(nev), "vege", True)
    except Exception as exc:  # noqa: BLE001 — pl. két `## Gyakorlás` szakasz: a beágyazás elmarad, a kártyák elkészülnek
        naplo(f"[kártya] a beágyazó sor nem került be ({exc})")

    foglalt = {k.azon for e in elemzesek.values() for k in e.kartyak if k.azon} | szinkron.foglalt_azonositok(cfg)
    kartyak = []
    for k, blokk in zip(eredm.kartyak, blokkok):
        a = formatum.uj_azon(foglalt)
        foglalt.add(a)
        kartyak.append(formatum.Kartya(kerdes=k.kerdes, valasz=k.valasz, azon=a, forras=horgony.link(cel, blokk, k.horgony)))
    if kisero:
        kd = gepi.olvas(kisero_ut)
        tartalom = kd["tartalom"].rstrip("\n") + "\n\n" + "\n\n".join(formatum.ir_kartya(k) for k in kartyak) + "\n"
        kisero_muv = gepi.csere(kisero_ut, tartalom, kd["hash"])
    else:
        tartalom = formatum.ir(kartyak, source=[cel], modell=jel["modell"], keszult=date.today().isoformat())
        kisero_muv = gepi.uj(kisero_ut, tartalom, osztaly="kartya")
    muveletek = [kisero_muv]
    if uj_md != md:
        muveletek.append(gepi.csere(ut, uj_md, alap_hash))
    kor = kor or gepi.uj_kor(KOR_ELOTAG)
    r = gepi.ir(kor, tetel=ut, forras=FORRAS, muveletek=muveletek, modell=jel, proba=proba,
                uzenet=f"kártyák: {cim} ({len(kartyak)})"[:200])
    ki = {"allapot": "kesz", "ut": ut, "kartyak": len(kartyak), "kisero": kisero_ut, "modell": jel["modell"], "proba": r.get("proba"),
          "sha": r.get("sha"), "kor": r.get("kor"), "statisztika": eredm.statisztika}
    if not r.get("proba"):
        szinkron.szinkron(cfg, {formatum.nfc(kisero_ut): formatum.elemez(tartalom)}, teljes=False, eredet="gep")
        if not resz:
            automatika.Tar(cfg).kesz(FOGYASZTO, ut, uj_md, hash_=(r.get("hash") or {}).get(ut, alap_hash), kimenet=kisero_ut)
    return ki
