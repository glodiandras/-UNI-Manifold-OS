"""CX-011: rövid magyar folytatások mechanikus előszűrése.
12 saját készítésű, egyértelmű iskolai mondatkörnyezet; a mérés nem általános tudás- vagy stílusminősítés.
A rögzítés előtt a válaszok és a késleltetés kézi ellenőrzése is szükséges. Ugyanaz a prompt, mint élesben.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

ITT = Path(__file__).resolve().parent
REPO = ITT.parents[2]
for _p in (str(REPO), str(ITT.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.kiegeszites_modell import keres, prompt_lenyomat  # noqa: E402
from kozos import arany as A  # noqa: E402

P = ITT / 'arany.json'
ARANY = A.betolt(ITT)
ROUTER_FELADAT = 'kiegeszites'
# A verzió: az aranyfájl `verzio`/`allapot` mezője (jóváhagyásig `-vazlat`, K382: vázlaton kalibrált jel nem adható), a kérés
# lenyomata (prompt, `keres()`, token-keret, hőmérséklet: `prompt_lenyomat`) és a fájl tartalma (a tétel változása új verzió).
VERZIO = ROUTER_FELADAT + '-' + A.verzio({**ARANY, 'verzio': ARANY['verzio'] + '.p' + hashlib.sha256(
    (prompt_lenyomat('folytat') + A.sha256(P)).encode()).hexdigest()[:8]})


def tetelek(cfg):
    for t in ARANY['tetel']:
        # az éles `folytat` kérés ugyanez (`kiegeszites_modell.keres`), a regiszter mérés-beállításával kiegészítve
        yield {'id': t['id'], 'keres': keres('folytat', t['elotte'], t['utana']), 'vart': t}


def formatum_ok(valasz, vart):
    return isinstance(valasz, str) and 0 < len(valasz.strip()) <= 240 and '```' not in valasz and vart['elotte'] not in valasz


def norm(s):
    return re.sub(r'[\s$*{}]', '', s.lower())


def pontoz(rekordok):
    jo = sum(formatum_ok(r.get('valasz'), r['vart']) and
             any(norm(v).rstrip('.。') == norm(r['valasz']).rstrip('.。') for v in r['vart']['elfogadhato']) for r in rekordok)
    return {'pontszam': jo / len(rekordok) if rekordok else 0, 'jo': jo, 'osszes': len(rekordok),
            'korlat': '12 kötött folytatás; a tényszerűséget és természetességet kézzel is ellenőrizni kell.'}
