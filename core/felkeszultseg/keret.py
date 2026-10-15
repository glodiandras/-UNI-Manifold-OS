"""CX-009: helyi, szerkeszthető napi tanulási időkeret."""
import json
from .. import tartos
from ..utvonalak import HttpError


def olvas(cfg, alap=45):
    try:
        v = json.loads((cfg.path('state') / 'tanulasi-keret.json').read_text())['napi_perc']
        return v if type(v) is int and 15 <= v <= 480 else alap
    except (OSError, ValueError, KeyError, TypeError):
        return alap


def ir(cfg, d):
    v = d.get('napi_perc') if isinstance(d, dict) else None
    if type(v) is not int or not 15 <= v <= 480:
        raise HttpError(400, 'A napi keret 15 és 480 közötti egész perc legyen.')
    p = cfg.path('state') / 'tanulasi-keret.json'
    p.parent.mkdir(parents=True, exist_ok=True)
    tartos.atomi_ir(p, json.dumps({'napi_perc': v}).encode())
    return {'napi_perc': v}
