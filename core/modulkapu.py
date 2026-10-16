"""F5 module switches: presentation and public feature routes share durable settings."""
from .utvonalak import HttpError

UTAK = {
    "/api/kviz": "kviz", "/api/kartya": "kartya", "/api/osszefoglalas": "osszefoglalas",
    "/api/matek": "matek", "/api/cpp": "kod", "/api/fuzet": "fuzet", "/api/video": "video",
    "/api/felkeszultseg": "felkeszultseg", "/api/naptar": "naptar", "/api/emlekezteto": "naptar", "/api/tracker": "tracker",
    "/api/asszisztens": "asszisztens", "/api/bazis": "bazis", "/api/vault/bazis": "bazis", "/api/grafikon": "matek",
    "/api/vault/sablon": "sablonok", "/api/sablon": "sablonok", "/api/naplo": "napi", "/api/ma": "napi",
    "/api/vault/graf": "graf", "/api/vault/graf-meta": "graf", "/api/vault/graf-beallitasok": "graf",
    "/api/vault/kereses": "kereses", "/api/kereses": "kereses",
    "/api/vault/visszahivatkozasok": "hivatkozasok", "/api/vault/emlitesek": "hivatkozasok",
}
KULON_UTAK = {"/api/kereses/kerdezz": "kerdezz", "/api/kereses/valasz": "kerdezz",
              "/api/kereses/hasonlosag": "asszisztens",
              "/api/vault/tulajdonsagok/tipusok": "tulajdonsagok",
              "/api/vault/tulajdonsagok/tipus": "tulajdonsagok"}
FELADATOK = {"kartya": "kartya", "kviz": "kviz", "osszefoglalas": "osszefoglalas", "matek": "matek",
             "grafikon": "matek", "cpp": "kod", "fuzet": "fuzet", "video": "video", "atirat": "video"}


def engedett(cfg, modul):
    return not modul or cfg.section("modulok").get(modul, True) is not False


def feladat_modul(tipus):
    return next((m for p, m in FELADATOK.items() if tipus == p or tipus.startswith(p + "_") or tipus.startswith(p + ".")), None)


def ellenoriz(cfg, ut):
    modul = next((m for p, m in UTAK.items() if ut == p or ut.startswith(p + "/")), None)
    # Shared search infrastructure also serves independent Assistant / Ask tools.
    # Their own switches govern those entry points; the raw note/index endpoints
    # stay available so disabling a view cannot make Markdown files unreadable.
    modul = KULON_UTAK.get(ut, modul)
    if not engedett(cfg, modul):
        raise HttpError(409, "This module is turned off. Enable it in Settings → Modules to use it.",
                        kod="modul.kikapcsolva", param={"modul": modul})
