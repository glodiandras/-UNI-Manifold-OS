"""A videólánc feladattípusa (C20a; docs/C20-TERV.md): `video_letoltes` — linkek letöltése a stagingbe.

A core nem importál `modulok/`-ot: ez a modul csak a feladatot (a lépés parancssorát) írja le; a lépés `python -m modulok.ytdlp lepes letoltes`
(alfolyamat: yt-dlp letöltés, konvertálás, staging-írás, pillanatkép az ytdlp tárba). **A lánc a vaultba nem ír, modellt nem tölt be**; a
hálózatot csak a letöltés használja (D3). A lépés jogkészlete `"nincs"` (K149, `core/lepes_kapu.py`): se lépés-token, se a core címe
nem kerül a környezetébe, és a környezet a lépés-kapu fehérlistájából épül. Kézzel indított feladat (a vezérlő Bevitel szakasza, `POST /api/feladatok`), nem automatikus.

Paraméterek: `{"urlek": ["https://…", …], "proba": false}`. A `proba: true` a stagingot és az archívumot a `{tmp}/video-proba/<idő>` alá
teszi, pillanatkép nélkül (kézi próba). Érvénytelen kérés → `tasks.Invalid` (400): nem http(s) vagy hitelesítést tartalmazó link,
helyi/privát cím (a core a saját helyi címén ne tudjon letöltetni), túl sok link, hiányzó ffmpeg.

**A helyi-cím szűrő (Javító 3, A3-13)** nem a gazdanév szövegét nézi: a számformákat (`127.1`, `0`, `2130706433`, `0x7f000001`, `0177.0.0.1`,
`127.0.0.1.`, teljes szélességű számjegyek) az `inet_aton` szabályai szerint IP-címmé olvassa, a nevet feloldja (`getaddrinfo`), és a
feloldott **minden** címét ellenőrzi (IPv4-mapped IPv6 is; csak globális cím jó); a feloldási hiba zárva hibázik. Ez a kérés időpontjában
ellenőriz; az átirányítást és a DNS-újrakötést a lépés folyamatának hálózat-őre fogja meg (`modulok/ytdlp/halozat_orzo.py`).
"""
from __future__ import annotations

import ipaddress
import os
import re
import socket
import sys
import time
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit

from . import kiserok, lepes_kapu, tasks
from .config import Config

TIPUS = "video_letoltes"
URL_MAX = 2000
_VEZERLO = re.compile(r"[\x00-\x20\x7f]")


_NEV_VEGEK = (".localhost", ".local", ".internal", ".lan", ".home.arpa")
_TIZEDES = re.compile(r"[1-9][0-9]*")
_OKTALIS = re.compile(r"0[0-7]*")
_HEX_SZAM = re.compile(r"0[xX][0-9a-fA-F]*")


def _felold(host: str) -> list[str]:
    """A gazdanév összes (A és AAAA) címe a rendszer feloldójával (a tesztek ezt cserélik)."""
    return sorted({ai[4][0] for ai in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)})


def _ipv4_regi_alak(host: str) -> ipaddress.IPv4Address | None:
    """Az `inet_aton` alakjai: `a`, `a.b`, `a.b.c`, `a.b.c.d`; a részek tizedes, oktális (`0…`) vagy hexa (`0x…`) számok, az utolsó a maradék
    bitek. A `127.1`, `2130706433`, `0x7f000001`, `0177.0.0.1` mind loopback — az `ipaddress.ip_address` ezeket nem érti. Nem szám: `None`."""
    reszek = host.split(".")
    if not 1 <= len(reszek) <= 4:
        return None
    szamok = []
    for r in reszek:
        if _HEX_SZAM.fullmatch(r):
            szamok.append(int(r, 16) if len(r) > 2 else 0)
        elif _OKTALIS.fullmatch(r):
            szamok.append(int(r, 8))
        elif _TIZEDES.fullmatch(r):
            szamok.append(int(r))
        else:
            return None
    *elso, utolso = szamok
    if any(n > 255 for n in elso) or utolso >= 256 ** (4 - len(elso)):
        return None
    ertek = utolso
    for i, n in enumerate(elso):
        ertek += n << (8 * (3 - i))
    return ipaddress.IPv4Address(ertek)


def _nem_nyilvanos(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Csak a globálisan útválasztott, nem multicast cím nyilvános (loopback, privát, link-local, CGNAT, dokumentációs, nem megadott: mind nem)."""
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return not ip.is_global or ip.is_multicast


def _helyi_cim(host: str) -> bool:
    """Helyi, privát vagy nem ellenőrizhető cél: ilyet nem töltünk le. A gazdanevet normalizálja (NFKC, záró pont, szögletes zárójel, IDNA
    pontok), a számformákat IP-nek olvassa, a nevet feloldja és MINDEN címét ellenőrzi; a feloldási hiba (nincs ilyen név) zárva hibázik."""
    h = unicodedata.normalize("NFKC", host.strip())
    h = re.sub("[\u3002\uff0e\uff61]", ".", h).strip("[]").split("%", 1)[0].lower().rstrip(".")
    if not h:
        return True
    if h in ("localhost", "ip6-localhost") or h.endswith(_NEV_VEGEK):
        return True
    ip = _ipv4_regi_alak(h)
    if ip is None:
        try:
            ip = ipaddress.ip_address(h)
        except ValueError:
            ip = None
    if ip is not None:
        return _nem_nyilvanos(ip)
    try:
        cimek = _felold(h)
    except (OSError, UnicodeError):
        return True
    if not cimek:
        return True
    try:
        return any(_nem_nyilvanos(ipaddress.ip_address(c.split("%", 1)[0])) for c in cimek)
    except ValueError:
        return True


def urlek_ellenoriz(urlek, max_link: int) -> list[str]:
    """A kérésben kapott linkek ellenőrzése és sorrendtartó deduplikálása (`tasks.Invalid`, magyar üzenettel)."""
    if not isinstance(urlek, list) or not urlek:
        raise tasks.Invalid("Adj meg legalább egy videólinket.")
    ki: list[str] = []
    for u in urlek:
        if not isinstance(u, str):
            raise tasks.Invalid("A link szöveg kell legyen.")
        u = u.strip()
        if not u or len(u) > URL_MAX or _VEZERLO.search(u):
            raise tasks.Invalid(f"Érvénytelen link: {u[:60]!r}")
        r = urlsplit(u)
        if r.scheme.lower() not in ("http", "https") or not r.hostname:
            raise tasks.Invalid(f"Csak http(s) link adható meg: {u[:80]}")
        if r.username or r.password:
            raise tasks.Invalid("A link nem tartalmazhat felhasználónevet vagy jelszót.")
        if _helyi_cim(r.hostname):
            raise tasks.Invalid(f"Helyi vagy privát címről nem töltök le: {r.hostname}")
        if u not in ki:
            ki.append(u)
    if len(ki) > max_link:
        raise tasks.Invalid(f"Egy feladatban legfeljebb {max_link} link adható meg ({len(ki)} érkezett).")
    return ki


def _max_link(cfg: Config, p: dict) -> int:
    """Egy letöltési feladat linkjeinek felső határa. Egyedi linkeknél `[video] max_link` (20); a bejárásból kiválasztott listánál
    (`bejaras: true`, 84. döntés) `[video] bejaras_max` (50), e fölött csak `megerosit: true`-val, legfeljebb `[video] bejaras_plafon`
    (200, a bejáró `crawl.max_items`-e)."""
    v = cfg.section("video")
    if p.get("bejaras"):
        if not isinstance(p.get("bejaras"), bool) or not isinstance(p.get("megerosit", False), bool):
            raise tasks.Invalid("A `bejaras` és a `megerosit` igaz vagy hamis lehet.")
        alap = int(v.get("bejaras_max", 50))
        if p.get("megerosit"):
            return int(v.get("bejaras_plafon", 200))
        n = len(p.get("urlek") or []) if isinstance(p.get("urlek"), list) else 0
        if n > alap:
            raise tasks.Invalid(f"{n} videó a bejárásból: {alap} fölött a letöltést külön meg kell erősíteni.")
        return alap
    return int(v.get("max_link", 20))


def _terv(cfg: Config, p: dict, stop: str):
    if not isinstance(p, dict):
        raise tasks.Invalid("A paraméterek JSON-objektum kellenek.")
    urlek = urlek_ellenoriz(p.get("urlek"), _max_link(cfg, p))
    ff = cfg.path("ffmpeg")
    if not ff.is_file():
        raise tasks.Invalid(f"Hiányzik az ffmpeg ({ff}): bin/mos runtime fetch ffmpeg — a home-beli és a PATH-os ffmpeg tiltott.")
    argv = [sys.executable, "-B", "-m", "modulok.ytdlp", "lepes", "letoltes"]
    figyelmeztetes: list[str] = []
    if p.get("proba"):
        argv += ["--proba-gyoker", str(cfg.path("tmp") / "video-proba" / time.strftime("%Y%m%d-%H%M%S"))]
        figyelmeztetes.append("Próbamód: a staging és az archívum a var/tmp alá kerül, pillanatkép nincs.")
    for u in urlek:
        argv += ["--url", u]
    if stop and not p.get("proba"):
        argv += ["--ki", str(letoltes_eredmeny(Path(stop).parent, Path(stop).stem))]     # F4: a letöltött mappák listája
    cim = f"Videó letöltése" if len(urlek) == 1 else f"Videók letöltése ({len(urlek)} link)"
    # K149 (A3-12): a lépés távoli tartalmat futtat (yt-dlp, a JS-kihíváshoz node) és a core API-ját nem hívja (a lánc a vaultba nem ír,
    # 47(c); az ytdlp tárat a `core.frame` folyamatbeli zárával rögzíti) — nem kap lépés-tokent, és a core címét sem
    return [tasks.Step(cim, argv, str(cfg.root), jogok=lepes_kapu.JOGOK_NINCS)], f"{len(urlek)} videólink letöltése a stagingbe (a vaultba nem ír).", figyelmeztetes


# ------------------------------------------------------------------ 84. döntés (javasolt): egy oldal összes videója — a felfedezés

BEJARAS = "video_bejaras"


def bejaras_fajl(cfg: Config, url: str):
    """A bejárás eredményének helye (`{state}/video-bejaras/<sha1>.json`): a lépés ide ír, a `GET /api/video/bejaras` innen olvas, a
    `bin/mos video letoltes --bejaras` is ezt használja. A kulcs a kért kezdő-link (szóközök és a záró `/` nélkül)."""
    import hashlib
    kulcs = hashlib.sha1(str(url).strip().rstrip("/").encode("utf-8")).hexdigest()[:16]
    return cfg.path("state") / "video-bejaras" / f"{kulcs}.json"


def _bejaras_terv(cfg: Config, p: dict, stop: str):
    """`{url}` → egy lépés (`lepes bejaras`): a kezdőoldal alatti videóoldalak felderítése (robots.txt, késleltetés, a gazdagépen és a
    kezdő úton belül). **Semmit nem tölt le**: a listát a felület mutatja, a letöltés a kiválasztott linkekre külön `video_letoltes`
    feladat (`bejaras: true`). Hálózatot használ (a jóváhagyott letöltés előkészítése, D3), a lépés jogkészlete `"nincs"`, mint a letöltésé."""
    if not isinstance(p, dict):
        raise tasks.Invalid("A paraméterek JSON-objektum kellenek.")
    (url,) = urlek_ellenoriz([p.get("url")] if isinstance(p.get("url"), str) else None, 1)
    argv = [sys.executable, "-B", "-m", "modulok.ytdlp", "lepes", "bejaras", "--url", url, "--ki", str(bejaras_fajl(cfg, url))]
    return ([tasks.Step("Az oldal videóinak felderítése", argv, str(cfg.root), jogok=lepes_kapu.JOGOK_NINCS)],
            f"A {urlsplit(url).hostname} oldal bejárása: a videóoldalak listája (letöltés nélkül).", [])


# ------------------------------------------------------------------ C20b: a bevitel a vaultba

INTEGRALAS = "video_integralas"
CSOPORT = re.compile(r"[A-Za-z0-9_-]{1,64}")
_atadva: set[str] = set()

# 86. döntés (javasolt): a kényszerített célmappa (téma). A minta a `[video] tema_minta` kulcsból jön; üresen a semleges alap
# (`kiserok.tema_minta_alap`: minden látható gyökérmappa, a kísérő- és sablonmappák nélkül). Az 1. csoport (ha van) a tárgy-betű
# (a `[pdf.tags]` kulcsa), a 2. (ha van) a kétjegyű sorszám (a `00` a tárgy vizuális mappája, nem téma). A tiltott karakterek a
# `vaultio._TILTOTT_NEV`-éi.
_TEMAMAPPA_TILTOTT = re.compile(r'[\\/:*?"<>|#^\[\]\x00-\x1f]')


class TemamappaHiba(ValueError):
    """A megadott célmappa (téma) nem használható; az üzenet magyar, a felhasználónak szól."""


def tema_minta(cfg: Config) -> re.Pattern:
    """A téma-mappa mintája a `[video] tema_minta` kulcsból; üresen a semleges alap (`kiserok.tema_minta_alap(cfg)`). Az 1. csoport
    (ha van) a tárgy-betű (a `[pdf.tags]` kulcsa), a 2. (ha van) a kétjegyű sorszám (a `00` a tárgy vizuális mappája, nem téma)."""
    nyers = cfg.section("video").get("tema_minta") or kiserok.tema_minta_alap(cfg)
    try:
        return re.compile(str(nyers))
    except re.error as e:
        raise TemamappaHiba(f"A [video] tema_minta nem érvényes reguláris kifejezés: {e}") from None


def temamappa_ellenoriz(vault, nev, cimkek: dict, minta: re.Pattern | None = None) -> str:
    """A `--tema-mappa` és a Bevitel „Célmappa (téma)” mezőjének egyetlen ellenőrzése (a core feladat-terve és a lánc is ezt hívja).

    → az NFC-alakú mappanév. Szabály: egyetlen, a vault gyökerében álló mappanév (perjel nincs), a vault téma-mintája
    (`minta`, a `[video] tema_minta`; ha 2. csoportja csupa nulla, az vizuális mappa, nem téma), az 1. csoport (a tárgy-betű, ha
    a mintának van) a `[pdf.tags]` egyik tárgya (így a forrásleíró jegyzet `Tags`-e sémaérvényes), tiltott karakter (`\\ / : * ? " < > | # ^ [ ]`, vezérlőjel) nélkül,
    legfeljebb 200 bájt. Ha már létezik, mappa kell legyen (nem fájl, nem symlink), és nem állhat mellette ugyanez a név más
    kis-nagybetűvel (az APFS kis-nagybetű-független). Ha nem létezik, a gépi írás az első `uj` művelettel hozza létre, ugyanabban a
    tételben (a meglévő út: `GepiIras._m_uj`, felülírás nélkül)."""
    if not isinstance(nev, str):
        raise TemamappaHiba("A célmappa neve szöveg kell legyen.")
    n = unicodedata.normalize("NFC", nev.strip())
    if not n:
        raise TemamappaHiba("Add meg a célmappa nevét.")
    if "/" in n or n.startswith(".") or _TEMAMAPPA_TILTOTT.search(n) or len(n.encode("utf-8")) > 200:
        raise TemamappaHiba(f"A célmappa a vault gyökerében álló egyetlen mappanév lehet, tiltott karakter nélkül: {n[:80]}")
    minta = minta or re.compile(kiserok.tema_minta_alap(None))
    m = minta.match(n)
    if not m:
        raise TemamappaHiba(f"A célmappa neve a vault téma-mintája (`{minta.pattern}`) szerint legyen: {n[:80]}")
    if minta.groups >= 2 and m.group(2) and m.group(2).strip("0") == "":
        raise TemamappaHiba(f"A „…{m.group(2)} - ” mappa a tárgy vizuális mappája, nem téma: {n[:80]}")
    if minta.groups >= 1 and m.group(1) is not None and m.group(1) not in (cimkek or {}):
        raise TemamappaHiba(f"A(z) „{m.group(1)}” betűnek nincs tárgy-címkéje a [pdf.tags]-ben: a célmappa egy tárgy témája legyen.")
    if vault is not None:
        gy = Path(vault)
        p = gy / n
        if os.path.lexists(p) and (p.is_symlink() or not p.is_dir()):
            raise TemamappaHiba(f"A(z) „{n}” már létezik, de nem mappa.")
        try:
            masik = [x for x in os.listdir(gy) if unicodedata.normalize("NFC", x).lower() == n.lower()
                     and unicodedata.normalize("NFC", x) != n]
        except OSError:
            masik = []
        if masik:
            raise TemamappaHiba(f"Már van ilyen mappa más kis-nagybetűvel: {masik[0]}")
    return n


def temamappak(vault, minta: re.Pattern | None = None) -> list[str]:
    """A vault gyökerének téma-mappái (a „Célmappa (téma)” mező javaslatai): a minta szerinti, nem vizuális, nem symlink mappák."""
    try:
        nevek = os.listdir(vault)
    except OSError:
        return []
    ki = []
    for x in nevek:
        n = unicodedata.normalize("NFC", x)
        m = (minta or re.compile(kiserok.tema_minta_alap(None))).match(n)
        p = os.path.join(vault, x)
        if m and not (m.re.groups >= 2 and m.group(2) and m.group(2).strip("0") == "") and os.path.isdir(p) and not os.path.islink(p):
            ki.append(n)
    return sorted(ki)


def _integralas_terv(cfg: Config, p: dict, stop: str):
    """`{mappak?: [staging-relatív forrásmappa], csoport?: <behúzott csoport>, tema_mappa?: str, proba?: bool}` → egy lépés
    (`lepes integral`). A `tema_mappa` (86. döntés, javasolt) a kényszerített célmappa: csak kijelölt forrással (`mappak`/`csoport`).

    A lépés lépés-tokent kap (`"gepi"`): a vaultba csak a gépi-írás szolgáltatáson át ír, tételenként (28(a)); a hálózatot nem
    használja (a worker és a core helyi). A `mappak` a staging alá kell essen (`..` és abszolút út tilos)."""
    if not isinstance(p, dict):
        raise tasks.Invalid("A paraméterek JSON-objektum kellenek.")
    if not isinstance(p.get("proba", False), bool):
        raise tasks.Invalid("A `proba` igaz vagy hamis lehet.")
    if not cfg.path("ffmpeg").is_file():
        raise tasks.Invalid("Hiányzik az ffmpeg: bin/mos runtime fetch ffmpeg")
    argv = [sys.executable, "-B", "-m", "modulok.ytdlp", "lepes", "integral"]
    staging = cfg.path("staging")
    mappak = p.get("mappak") or []
    if not isinstance(mappak, list) or len(mappak) > 200:
        raise tasks.Invalid("A `mappak` legfeljebb 200 elemű lista.")
    for m in mappak:
        if not isinstance(m, str) or not m.strip() or m.startswith("/") or ".." in m.split("/") or "\x00" in m:
            raise tasks.Invalid(f"A forrásmappa a staging alatti relatív út lehet: {str(m)[:80]}")
        if not (staging / m).is_dir():
            raise tasks.Invalid(f"Nincs ilyen staging-forrásmappa: {m}")
        argv += ["--mappa", str(staging / m)]
    csoport = p.get("csoport")
    if csoport is not None:
        if not isinstance(csoport, str) or not CSOPORT.fullmatch(csoport) or not (cfg.path("video_bejovo") / csoport).is_dir():
            raise tasks.Invalid("A `csoport` a behúzott videók csoport-azonosítója.")
        argv += ["--csoport", str(cfg.path("video_bejovo") / csoport)]
    tm = p.get("tema_mappa")
    if tm is not None:
        if not (mappak or csoport):
            raise tasks.Invalid("Célmappával csak kijelölt staging-forrás vihető be (`mappak` vagy `csoport`), nem az összes várakozó.")
        try:
            tm = temamappa_ellenoriz(cfg.path("vault"), tm, dict(cfg.section("pdf").get("tags") or {}), tema_minta(cfg))
        except TemamappaHiba as e:
            raise tasks.Invalid(str(e)) from None
        argv += ["--tema-mappa", tm]
    figyelm = []
    if p.get("proba"):
        argv.append("--proba")
        figyelm.append("Próbamód: az írás a vault APFS-klónjára megy, a staging nem változik.")
    video_mappa = kiserok.kisero_mappa(cfg, "video")
    reteg = cfg.section("media").get("reteg_mappa") or "Média"
    osszeg = (f"A staging várakozó videói a vaultba kerülnek: a videó az „{video_mappa}” alá (APFS-klón), a felirat, a "
              f"proveniencia és a forrásleíró jegyzet a téma „{reteg}” rétegébe, a kötések `#t=` horgonya a jegyzetek Source mezőjébe "
              "(videónként egy gépi írás, visszavonható).")
    if tm is not None:
        osszeg = (f"A kijelölt staging-videók a(z) „{tm}” mappába kerülnek (a téma-modell nem fut): a videó az „{video_mappa}” "
                  f"alá, a felirat, a proveniencia és a forrásleíró jegyzet a „{tm}/{reteg}” rétegbe (a hiányzó mappát a gépi írás hozza "
                  "létre), kötés csak a mappa saját jegyzeteihez (videónként egy gépi írás, visszavonható).")
    return [tasks.Step("Videók bevitele a vaultba", argv, str(cfg.root))], osszeg, figyelm


def letoltes_eredmeny(logdir, fid: str) -> Path:
    """A `video_letoltes` feladat eredményfájlja (`<feladatnapló-mappa>/<feladat>.letoltes.json`): a lépés ide írja a letöltött (vagy
    már meglévő) linkek staging-relatív forrásmappáit (`{"mappak": […]}`), a `letoltes_utan` innen adja a bevitelnek (F4)."""
    return Path(logdir) / f"{fid}.letoltes.json"


def _letoltott_mappak(queue, fid: str) -> list[str]:
    """A letöltés eredményfájljának mappái (a staging alatti, létező, relatív utak); hiányzó vagy hibás fájl: üres lista."""
    import json
    try:
        d = json.loads(letoltes_eredmeny(queue.logdir, fid).read_text(encoding="utf-8"))
    except (OSError, ValueError, AttributeError):
        return []
    staging = queue.cfg.path("staging")
    ki: list[str] = []
    for m in (d.get("mappak") if isinstance(d, dict) else None) or []:
        if (isinstance(m, str) and m.strip() and not m.startswith("/") and ".." not in m.split("/") and "\x00" not in m
                and (staging / m).is_dir() and m not in ki):
            ki.append(m)
    return ki[:200]


def letoltes_utan(queue, f: dict) -> dict | None:
    """C20b: a „Letöltés és bevitel” (`video_letoltes` `{bevitel: true}`) sikeres végén a bevitel sorba kerül (a letöltés lépése a
    core-t nem éri el, K149: ezt a core teszi) — **csak a saját letöltés forrásmappáival** (`mappak`, a lépés eredményfájljából), nem
    a staging összes várakozó tételével; hibával végződött letöltés után nem, és üres lista mellett sem (F4, 2026-10-14). Próbamódban
    nem; ugyanarra a feladatra egyszer."""
    if f.get("tipus") != TIPUS or f.get("id") in _atadva or f.get("allapot") != "kesz":
        return None
    p = f.get("parameterek") or {}
    if not p.get("bevitel") or p.get("proba"):
        return None
    _atadva.add(f.get("id"))
    mappak = _letoltott_mappak(queue, str(f.get("id")))
    if not mappak:
        print("[videó] a letöltés után nincs bevihető forrásmappa (az eredményfájl hiányzik vagy üres); a bevitel kézzel indítható",
              file=sys.stderr, flush=True)
        return None
    try:
        return queue.submit(INTEGRALAS, {"mappak": mappak})
    except Exception as e:  # noqa: BLE001 — a letöltés eredménye megvan; a bevitel kézzel is indítható
        print(f"[videó] a bevitel nem indult el a letöltés után: {e}", file=sys.stderr, flush=True)
        return None


def regisztral() -> None:
    """A feladattípusok felvétele (idempotens; a `vezerlo.utvonalak` hívja, mint a próbafeladatét)."""
    tasks.register(tasks.TaskType(TIPUS, "Videók letöltése", _terv, resources=frozenset(), graceful_stop=True, automatikus=False))
    tasks.register(tasks.TaskType(BEJARAS, "Az oldal videóinak felderítése", _bejaras_terv, resources=frozenset(), graceful_stop=True,
                                  automatikus=False))
    tasks.register(tasks.TaskType(INTEGRALAS, "Videók bevitele a vaultba", _integralas_terv, resources=frozenset({"modell", "vault"}),
                                  graceful_stop=True, automatikus=False))
