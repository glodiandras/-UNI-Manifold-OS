"""Az összefoglaló promptjai — **egyetlen szövegforrás** a kalibráláshoz és az éles lánchoz (C26b, 1. pont).

A jegyzet-szintű prompt törzse (`_TORZS`) a C18 `szoveg` aranyhalmaz összefoglaló-tételének promptja **bájtra azonosan**: a
`modulok/eval/szoveg/feladat.py` a `jegyzet_prompt`-ot hívja (a kalibrációs ujjlenyomat nem változott: a `tests/
test_osszefoglalas_promptok.py` rögzíti), az éles lánc a darabokra szabott `darab_prompt`-ot (ugyanaz a szabály, ugyanaz a JSON-alak,
a kért állítások száma és a jegyzet címe paraméter). A szöveg változtatása `PROMPT_VERZIO`-t emel (az érvényesség-kapu ujjlenyomata,
`core/modell/ervenyesseg.py`): a kalibrált és az éles prompt ne térhessen el egymástól.
"""
PROMPT_VERZIO = "ossz-1"

_TORZS = (
    "Foglald össze az alábbi {mit} magyarul, {k} állításban. Minden állítás egy önálló mondat a saját "
    "szavaiddal, és mindegyik mellé add meg azt a SZÓ SZERINTI idézetet a jegyzetből (egyetlen összefüggő "
    "részlet, legfeljebb 40 szó), amely alátámasztja. Csak azt állítsd, ami a jegyzetben áll.\n"
    'Csak JSON-t adj vissza, ebben az alakban: [{{"allitas": "…", "idezet": "…"}}]\n\n{fejlec}\n{szoveg}')


def jegyzet_prompt(szoveg: str, k: str = "6–10") -> str:
    """A teljes jegyzetre szóló prompt: a C18 `szoveg` aranyhalmaz összefoglaló-tételének promptja (a kalibráció ezt mérte)."""
    return _TORZS.format(mit="jegyzetet", k=k, fejlec="JEGYZET:", szoveg=szoveg)


def darab_prompt(k: int, cim: str, szoveg: str) -> str:
    """Az éles lánc egy darabjára (egy modellhívás): `k` állítás a jegyzetrészletből, a jegyzet címével."""
    return _TORZS.format(mit="jegyzetrészletet", k=k, fejlec=f"JEGYZET ({cim}):", szoveg=szoveg)


MAPPA_PROMPT = (
    "Az alábbi számozott állítások egy mappa jegyzeteiből származnak. Foglald össze a mappa tartalmát legfeljebb {k} "
    "új állításban magyarul. Minden új állítás egy önálló mondat, és mindegyikhez add meg, melyik számozott állításra "
    "épül (a szám, pl. \"J2.3\"). Csak azt állítsd, ami a számozott állításokban áll.\n"
    'Csak JSON-t adj vissza, ebben az alakban: [{{"allitas": "…", "forras": "J2.3"}}]\n\nÁLLÍTÁSOK:\n{allitasok}')

KONTEXTUS_FEJ = (
    "Az alábbi jegyzetekből dolgozz{kerdes_resz}. Csak a megadott jegyzetek szövegében álló dolgokat állíthatod.\n"
    "Minden állításhoz add meg a jegyzet azonosítóját (pl. J1) és a jegyzet SZÓ SZERINTI mondatát idézetként "
    "(4–45 szó, egyetlen összefüggő részlet). Az idézet nélküli állítást a fogadó rendszer eldobja.\n"
    'Csak JSON-t adj vissza, ebben az alakban: [{{"allitas": "…", "forras": "J1", "idezet": "…"}}]')
