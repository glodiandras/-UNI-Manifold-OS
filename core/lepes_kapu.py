"""A lépés-folyamatok kapuja (C29.8, T137; CLAUDE.md 28(a) „a gép csak a gépi-írás szolgáltatáson át ír”; 35. döntés).

A feladatsor minden lépés-folyamata saját, egyszer használatos tokent kap (`MOS_LEPES_TOKEN`; a `Queue._execute` sorsolja, a lépés végén
törli), és **a felületi API-titkot nem kapja meg** (`Queue._env` kiveszi, a core saját környezetéből is). A lépés hitelesítője a token: a
`core/gepi_kliens.py` az `X-Manifold` fejlécben küldi (a felület és a kézi próba a titkot küldi, ugyanabban a fejlécben). A core
(`server._hitelesit`) a kérést a következők szerint fogadja:

- a felületi API-titok: teljes jogú (a felület, a kézi próbák);
- érvényes lépés-token: az olvasó végpontok (`GET`, `HEAD`) mennek, az írók közül csak a gépi írás és az `ENGEDELYEZETT` tiszta, nem író
  számolók (a tulajdonság- és Bases-számoló, az átnevezés terve, a feloldás, a sablon kiértékelése); **minden más** — a szerkesztői
  írás (`PUT /api/vault/fajl`, `POST /api/vault/uj`, az átnevezés, a visszaállítás/visszavonás, a PDF-kiemelés…), a feladat-indítás, a
  felületi állapot — 403;
- bármi más (hiányzó, ismeretlen, lejárt token): 403.

A lépés tehát a titok nélkül sem szerkesztői írást, sem feladat-indítást nem tud kérni, akkor sem, ha szándékosan kerüli a klienst. A
`tests/test_lepes_kapu.py` döntéstáblája minden új író végpontot döntésre kényszerít (engedett vagy tiltott).

**Lépésenkénti jogkészlet (K149, Audit 3 A3-12).** A lépés-leírás (`tasks.Step.jogok`, a DB-ben a `lepesek` elemének `jogok` kulcsa)
dönti el, kap-e a lépés tokent:

- `"gepi"` (az alap; a kulcs nélküli, régebben mentett lépés is ez): token, a fenti jogokkal, és a core címe (`MOS_CORE_URL`);
- `"nincs"`: **se token, se a core címe** (`MOS_CORE_URL`, `MOS_CORE_PORT`): a lépés a core API-ját nem éri el. A hálózati, távoli
  tartalmat futtató lépés ilyen (a `video_letoltes`: a yt-dlp és az általa indított node; 47(c): a lánc a vaultba nem ír, a core-t nem
  hívja);
- bármi más (elírás, sérült DB-sor): zárva hibázik, mint a `"nincs"`.

**Fehérlistás környezet.** A lépés a core `os.environ`-jából csak a `KORNYEZET_NEVEK` és a `KORNYEZET_ELOTAGOK` szerinti változókat örökli
(a rendszer alapjai, a nyelv, a proxy és a tanúsítvány, a `MOS_*` útvonal-felülírások (L49), a `MANIFOLD_*` modellzár- és keret-felülírás
(L23/L24), a `PYTHONPATH`, a `XDG_*` gyorsítótár), a titok-jellegű nevet (`titok_jellegu`: `MOS_API_TITOK`, `MOS_LEPES_TOKEN`, és minden
`TITOK`/`TOKEN`/`JELSZO`/`SECRET`/`PASSWORD` részt tartalmazó név) akkor sem. Ami ezen kívül kell egy lépésnek, azt a feladattípus az
`env_extra` horgon át, nevesítve adja.
"""
from __future__ import annotations

import re

KORNYEZETI_VALTOZO = "MOS_LEPES_TOKEN"

# A lépés jogkészlete (a `tasks.Step.jogok` értékei)
JOGOK_GEPI = "gepi"            # token az `ENGEDELYEZETT` jogokkal + a core címe (az alap)
JOGOK_NINCS = "nincs"          # se token, se a core címe
JOGOK_ALAP = JOGOK_GEPI
JOGOK = frozenset({JOGOK_GEPI, JOGOK_NINCS})

# A core címét hordozó változók: a token nélküli lépés ezeket sem kapja
CORE_CIM_VALTOZOK = ("MOS_CORE_URL", "MOS_CORE_PORT")

# A lépés környezetének fehérlistája (`tasks.Queue._env`): pontos nevek…
KORNYEZET_NEVEK = frozenset({
    "PATH", "HOME", "USER", "LOGNAME", "SHELL", "LANG", "TMPDIR", "TZ", "TERM",
    "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "no_proxy", "all_proxy",
    "SSL_CERT_FILE", "SSL_CERT_DIR",
    "PYTHONPATH",              # a `bin/mos` a kódtárat teszi elé; a `_env` a gyökeret mindig elé fűzi
})
# …és előtagok
KORNYEZET_ELOTAGOK = (
    "LC_",                     # a nyelvi beállítás (LC_ALL, LC_CTYPE…)
    "MOS_",                    # az útvonal-felülírások (L49: MOS_VAULT, MOS_STATE…), a próbakapcsolók; a titok-jellegűek nem
    "MANIFOLD_",               # a modellzár és a keret felülírása (L23/L24: MANIFOLD_MODELL_ZAR — a klón ugyanazt a zárat fogja)
    "XDG_",                    # a `bin/mos` a gyorsítótárat a var/cache alá teszi (XDG_CACHE_HOME): a yt-dlp gyorsítótára ne a home-ba
)
_TITOK_RESZEK = re.compile(r"TITOK|TOKEN|JELSZO|SECRET|PASSWORD|PASSWD", re.IGNORECASE)


def token_jar(jogok: object) -> bool:
    """Kap-e a lépés lépés-tokent (és a core címét): csak a `"gepi"` jogkészlet; a `"nincs"` és minden ismeretlen érték nem (zárva hibázik)."""
    return jogok == JOGOK_GEPI


def titok_jellegu(nev: str) -> bool:
    """Titkot hordozhat-e a változó a neve szerint: az ilyet a lépés a fehérlistás előtag mellett sem örökli."""
    return bool(_TITOK_RESZEK.search(nev))


def orokolheto(nev: str) -> bool:
    """Átjut-e a core környezetének változója a lépés környezetébe: fehérlistás név vagy előtag, és nem titok-jellegű."""
    if titok_jellegu(nev):
        return False
    return nev in KORNYEZET_NEVEK or nev.startswith(KORNYEZET_ELOTAGOK)

# (metódus, pontos út): amit a lépés-folyamat a nem olvasó végpontok közül hívhat
ENGEDELYEZETT = frozenset({
    ("POST", "/api/gepi-iras"),                              # a gép egyetlen írási útja (28(a))
    ("POST", "/api/vault/tulajdonsagok/elemez"),             # tiszta számolók: nem írnak
    ("POST", "/api/vault/tulajdonsagok/modosit"),
    ("POST", "/api/vault/tulajdonsagok/osszefesul"),         # C32b: a sablon-frontmatter összefésülése (tiszta számoló)
    ("POST", "/api/vault/bazis/lekerdez"),
    ("POST", "/api/vault/bazis/modosit"),
    ("POST", "/api/vault/atnevezes/terv"),
    ("POST", "/api/vault/feloldas"),
    ("POST", "/api/sablon/kiertekel"),
})


def engedelyezett(metodus: str, ut: str) -> bool:
    """Hívhatja-e a lépés-folyamat (érvényes tokennel) a végpontot: az olvasók és az `ENGEDELYEZETT` igen, minden más nem."""
    return metodus in ("GET", "HEAD") or (metodus, ut) in ENGEDELYEZETT
