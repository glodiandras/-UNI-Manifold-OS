"""Az `[asszisztens]` beállítások (a `config/os.toml`-ból, alapértékekkel): a hiányzó vagy hibás típusú kulcs az alapot adja."""
from __future__ import annotations

from .. import kiserok

# A kizárt útelőtagok kód-alapja semleges: a sablonmappa és a gépi kísérőmappák (`beallitasok(cfg)` a `[sablon] mappa`-t és a
# `[vault] kisero_elotag`-ot mindig hozzáteszi); a vault saját mappáit (napló, log) az os.toml `[asszisztens]` listái adják —
# a v2-konvenció a `config/presets/v2-kompat.toml`-ban.
_KIZART_ALAP = ["_Template/", kiserok.ALAP_ELOTAG]
_KIZART_KULCSOK = ("higienia_arva_kizart", "emlites_kizart", "kartya_kizart")

ALAP: dict = {
    # --- jegyzethigiénia
    "higienia_arva_canvas": True,         # a canvas-ból érkező link „bejövő linknek” számít-e (K176: igen — a tantárgyi canvas szerkezeti kapcsolat)
    "higienia_arva_kizart": _KIZART_ALAP,     # útelőtagok
    "higienia_arva_tulajdonsag_kizart": ["Canvas", "Source"],     # ezek a frontmatter-linkek nem kapcsolatok
    "higienia_min_koz_mp": 60.0,          # két teljes számítás között legalább ennyi idő
    "higienia_tick_mp": 10.0,             # a háttérszál ellenőrzési üteme
    "higienia_uj_max": 20,                # a „Ma” oldalra kerülő új tételek száma
    # --- linkeletlen említés
    "emlites_min_hossz": 4,               # ennél rövidebb név nem javasolható
    "emlites_max": 50,
    "emlites_cim_alak": True,             # K177: a szótár a címrészt is tartalmazza (az `NN - ` előtag és a ` — Feladattár` nélkül)
    "emlites_cim_min_szo": 2,             # a címrész-egyezés bárhol ennyi szótól; az egyszavas csak ugyanabban a tantárgy-mappában
    "emlites_cim_egyszavas_max_db": 10,   # …és csak ha a szót legfeljebb ennyi jegyzet tartalmazza (ritka a vaultban)
    "emlites_kizart": _KIZART_ALAP,     # ezekre a jegyzetekre nem javasol linket
    "emlites_szotar_frissites_mp": 2.0,   # a névszótár legfeljebb ennyi időnként épül újra
    "emlites_hasonlosag_kuszob": 0.55,    # C30b: a jegyzet és a javasolt cél hasonlósága (C25c) ennél kisebb → nincs javaslat (mérés: tests/kezi/hasonlosag_meres.py)
    # --- szokásminta
    "szokas_ablak_het": 8,
    "szokas_min_het": 4,                  # ennyi hét kell az ablakból
    "szokas_min_perc": 20,                # ennyi aktív perc számít „tanult” napnak
    "szokas_napszak": True,               # C30b: a minta napszakkal is (a `tr_aktiv_ora`-ból), ha van elég adat
    # --- statisztika és küszöb
    "kuszob_ablak_nap": 30,
    "kuszob_min_db": 10,                  # ennél kevesebb döntésből nincs következtetés
    "kuszob_alacsony": 0.15,              # ez alatti elfogadási arány → szigorúbb küszöb
    "kuszob_nema_db": 20,
    "kuszob_nema": 0.05,                  # ez alatti arány ennyi döntés után → a fajta nem javasol
    "kuszob_szigoru_szorzo": 1.5,
    # --- önhangoló gyakoriság (J1; core/asszisztens/hangolo.py)
    "hangolas_felezes_nap": 21.0,         # a döntések súlya ennyi nap alatt feleződik (az elnémult fajta lassan visszatérhet)
    "hangolas_nema_db": 5,                # ennyi (súlyozott) döntés után…
    "hangolas_nema_arany": 0.15,          # …ez alatti elfogadási arány → a helyzet (kétszer annyiból a fajta) néma
    # --- javaslat-kártya (J3; core/asszisztens/mintatar.py)
    "kartya_alap_mp": 90.0,               # két kártya között legalább ennyi idő (a hangolás szorzójával)
    "kartya_min_testver": 3,              # a szerkezeti minta legalább ennyi testvérjegyzetből (azonos mappa)
    "kartya_szerkezet_arany": 0.6,        # a testvérek legalább ekkora részében álló szakaszcím hiánya javasolható
    "kartya_muvelet_min_db": 3,           # egy művelet (címke, sablon, link) ennyi ismétlés után lesz tanult minta
    "kartya_tartalom_kuszob": 0.75,       # a kapcsolódó jegyzet hasonlósága (C25c vektortár) legalább ennyi
    "kartya_elutasitott_nap": 30,         # az elutasított javaslat ennyi napig nem tér vissza
    "kartya_kizart": _KIZART_ALAP,     # ezekben nincs kártya
    "tantargy_nevek": {},                 # `[pdf.tags]` címke → a javaslat szövegében látszó név (a munkatér adja; üres: a címke látszik)
}


def beallitasok(cfg) -> dict:
    """Az alapértékek a konfig `[asszisztens]` szakaszával felülírva; a típus-eltérő érték az alapot hagyja."""
    ki = {k: (dict(v) if isinstance(v, dict) else list(v) if isinstance(v, list) else v) for k, v in ALAP.items()}
    for k, v in (cfg.section("asszisztens") or {}).items():
        if k not in ALAP:
            continue
        alap = ALAP[k]
        if isinstance(alap, bool):
            if isinstance(v, bool):
                ki[k] = v
        elif isinstance(alap, (int, float)):
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                ki[k] = type(alap)(v)
        elif isinstance(alap, list):
            if isinstance(v, list) and all(isinstance(x, str) for x in v):
                ki[k] = list(v)
        elif isinstance(alap, dict):
            if isinstance(v, dict):
                ki[k] = {str(a): str(b) for a, b in v.items()}
    # a sablonmappa és a gépi kísérőmappák sosem javaslat-források (a konfigurált lista mögé, ha még nincsenek benne)
    sablon = str((cfg.section("sablon") or {}).get("mappa") or "_Template").strip("/") + "/"
    for k in _KIZART_KULCSOK:
        ki[k] = [*ki[k], *(x for x in (sablon, kiserok.kisero_elotag(cfg)) if x not in ki[k])]
    return ki
