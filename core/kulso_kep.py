"""04-embeds-02 / 01-rendering-04: külső kép (`![](https://…)`) letöltése **kifejezett felhasználói kattintásra** (D3).

A felület a külső képet alapból nem tölti be (nincs kérés, a CSP `img-src` nem lazul); a helyőrző „Download image” gombja a
`POST /api/vault/import {url, forras}` kérést küldi (a végpont a gépi lépésnek tiltott, `tests/test_lepes_kapu.py`). A letöltést a
core végzi, nem a webview:

- séma-fehérlista: csak `https`, alapport (443), felhasználónév/jelszó nélkül, vezérlőkarakter nélkül, legfeljebb `URL_MAX` hosszan;
- SSRF-védelem: a gazdanév minden feloldott címe globális kell legyen (a `videolanc` számforma-olvasójával: `127.1`, `0x7f000001`
  is loopback); a kapcsolat **az ellenőrzött IP-re** megy (TLS SNI és tanúsítvány a gazdanévre), így a DNS-újrakötés nem kerüli meg;
  az átirányítást (legfeljebb `MAX_ATIRANYITAS`) ugyanez az ellenőrzés követi, privát célra nem lép;
- korlátok: `MAX_BAJT` méret (a `Content-Length` és a ténylegesen olvasott bájtok szerint), `IDOKORLAT_MP` teljes időkorlát;
- típus: a `Content-Type` `image/*` (vagy `application/octet-stream`), a tartalom képmagic szerint PNG/JPEG/GIF/WebP/AVIF/BMP/SVG,
  a kiterjesztés a magicből jön (nem a linkből); tömörített átviteli kódolás tiltott;
- írás: a `csatolmany.bajt_import` (a beállított csatolmány-mappa, rejtett ideiglenes fájl, kör-zár, ütközésmentes név,
  pillanatkép-commit, index) — azonos tartalmú meglévő fájlt nem duplikál.

A jegyzet linkjét a core nem írja át: az a felület kifejezett „Use local file” választása a dokumentum CAS-os mentési útján.
Proxy-beállítást nem követ (a `http.client` közvetlen kapcsolatot nyit); süti, hitelesítés, Referer nem megy ki.
"""
from __future__ import annotations

import http.client
import ipaddress
import re
import socket
import ssl
import time
import unicodedata
from urllib.parse import unquote, urljoin, urlsplit

from . import csatolmany, vaultio, videolanc
from .utvonalak import HttpError

URL_MAX = 2000
MAX_BAJT = 20 * 1024 * 1024
IDOKORLAT_MP = 20.0
KAPCSOLODAS_MP = 10.0
MAX_ATIRANYITAS = 3
DARAB = 64 * 1024
USER_AGENT = "Manifold (explicit image download)"
_VEZERLO = re.compile(r"[\x00-\x20\x7f]")
_TIPUSOK = ("image/", "application/octet-stream", "binary/octet-stream")
_KEP_KITERJESZTES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif", ".bmp", ".svg", ".jfif", ".pjpeg", ".pjp"}
_NEV_TILTOTT = re.compile(r'[\\/:*?"<>|#^\[\]%\x00-\x1f\x7f]')
_SVG = re.compile(rb'^(?:<\?xml[^>]{0,200}>\s*)?(?:<!--.*?-->\s*)*(?:<!DOCTYPE\s+svg[^>]{0,500}>\s*)?(?:<!--.*?-->\s*)*<svg[\s>]',
                  re.S | re.I)


def _hiba(http_kod: int, magyar: str, kod: str, **param) -> HttpError:
    return HttpError(http_kod, magyar, kod=kod, param=param or None)


# ---------------------------------------------------------------- URL és cím


def url_ellenoriz(url) -> str:
    """A letöltendő link: csak `https`, alapport, hitelesítés és vezérlőkarakter nélkül (`HttpError` 400)."""
    if not isinstance(url, str) or not url.strip():
        raise HttpError(400, 'Hiányzik a kép linkje.', kod="kulso_kep.url_hianyzik")
    url = url.strip()
    if len(url) > URL_MAX or _VEZERLO.search(url):
        raise HttpError(400, 'Érvénytelen képlink.', kod="kulso_kep.url_hibas")
    try:
        r = urlsplit(url)
        port = r.port
    except ValueError:
        raise HttpError(400, 'Érvénytelen képlink.', kod="kulso_kep.url_hibas") from None
    if r.scheme.lower() != "https" or not r.hostname:
        raise HttpError(400, 'Csak https-képlink tölthető le.', kod="kulso_kep.csak_https")
    if r.username is not None or r.password is not None or "@" in r.netloc:
        raise HttpError(400, 'A képlink nem tartalmazhat felhasználónevet vagy jelszót.', kod="kulso_kep.hitelesites")
    if port not in (None, 443):
        raise HttpError(400, 'A képlink csak az alapértelmezett https-portot használhatja.', kod="kulso_kep.port")
    return url


def _felold(host: str) -> list[str]:
    """A gazdanév címei (a tesztek cserélik; valódi kérés nélkül)."""
    return videolanc._felold(host)


def nyilvanos_cimek(host: str) -> list[str]:
    """A gazdanév ellenőrzött, globális címei. Helyi/privát/link-local/CGNAT/multicast cím, helyi névvég (`.local`, `localhost` …),
    feloldási hiba vagy üres válasz: `HttpError` 403/502 (zárva hibázik)."""
    h = unicodedata.normalize("NFKC", host.strip())
    h = re.sub("[。．｡]", ".", h).strip("[]").split("%", 1)[0].lower().rstrip(".")
    tiltott = HttpError(403, 'Helyi vagy privát címről nem töltök le képet.', kod="kulso_kep.helyi_cim")
    if not h or h in ("localhost", "ip6-localhost") or h.endswith(videolanc._NEV_VEGEK):
        raise tiltott
    ip = videolanc._ipv4_regi_alak(h)
    if ip is None:
        try:
            ip = ipaddress.ip_address(h)
        except ValueError:
            ip = None
    if ip is not None:
        if videolanc._nem_nyilvanos(ip):
            raise tiltott
        return [str(ip.ipv4_mapped if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped else ip)]
    try:
        cimek = _felold(h)
    except (OSError, UnicodeError):
        raise HttpError(502, 'A kép kiszolgálója nem található.', kod="kulso_kep.nincs_kiszolgalo") from None
    if not cimek:
        raise HttpError(502, 'A kép kiszolgálója nem található.', kod="kulso_kep.nincs_kiszolgalo")
    try:
        ipk = [ipaddress.ip_address(c.split("%", 1)[0]) for c in cimek]
    except ValueError:
        raise tiltott from None
    if any(videolanc._nem_nyilvanos(i) for i in ipk):
        raise tiltott
    return [str(i) for i in ipk]


# ---------------------------------------------------------------- kép


def kep_tipus(b: bytes) -> str | None:
    """A képformátum a tartalom elejéből (kiterjesztés pont nélkül), vagy `None`."""
    if b.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if b.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if b[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "webp"
    if b[4:8] == b"ftyp" and b[8:12] in (b"avif", b"avis"):
        return "avif"
    if b[:2] == b"BM" and len(b) >= 26 and int.from_bytes(b[2:6], "little") == len(b):
        return "bmp"
    if _SVG.match(b[:4096].lstrip(b"\xef\xbb\xbf").lstrip()):
        return "svg"
    return None


def fajlnev(url: str, kiterjesztes: str) -> str:
    """A mentett fájl neve a link utolsó útszakaszából (dekódolva, a vaultban tiltott jelek nélkül), a kiterjesztés a magicé."""
    szakasz = unquote(urlsplit(url).path.rsplit("/", 1)[-1])
    szakasz = unicodedata.normalize("NFC", szakasz)
    eleje, pont, veg = szakasz.rpartition(".")
    torzs = eleje if pont and f".{veg.lower()}" in _KEP_KITERJESZTES else szakasz
    torzs = _NEV_TILTOTT.sub("-", torzs).strip(" .-")[:80].strip(" .-") or "image"
    return f"{torzs}.{kiterjesztes}"


# ---------------------------------------------------------------- hálózat


def _ssl_kontextus() -> ssl.SSLContext:
    """A certifi CA-készlete, ha elérhető (a python.org macOS-buildje nem hoz sajátot), különben a rendszeré."""
    try:
        import certifi
    except ImportError:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


class _RogzitettHttps(http.client.HTTPSConnection):
    """HTTPS-kapcsolat az előre ellenőrzött IP-re; a TLS SNI és a tanúsítvány-ellenőrzés a gazdanévre szól."""

    def __init__(self, host: str, ip: str, timeout: float):
        super().__init__(host, 443, timeout=timeout, context=_ssl_kontextus())
        self._ip = ip

    def connect(self):
        sock = socket.create_connection((self._ip, 443), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def _kapcsolat(host: str, ip: str, timeout: float):
    """Egy kapcsolat (a tesztek cserélik: valódi hálózati kérés tesztben nincs)."""
    return _RogzitettHttps(host, ip, timeout)


def _keres(url: str, hatarido: float):
    """Egy GET a már ellenőrzött linkre, az ellenőrzött IP-k egyikén. → (válasz, kapcsolat)."""
    r = urlsplit(url)
    cimek = nyilvanos_cimek(r.hostname or "")
    ut = (r.path or "/") + (f"?{r.query}" if r.query else "")
    utolso: Exception | None = None
    for ip in cimek[:4]:
        marad = hatarido - time.monotonic()
        if marad <= 0:
            break
        k = _kapcsolat(r.hostname, ip, min(marad, KAPCSOLODAS_MP))
        try:
            k.request("GET", ut, headers={"User-Agent": USER_AGENT, "Accept": "image/*", "Accept-Encoding": "identity"})
            return k.getresponse(), k
        except ssl.SSLCertVerificationError:
            k.close()
            raise HttpError(502, 'A kép kiszolgálójának tanúsítványa nem ellenőrizhető.', kod="kulso_kep.tanusitvany") from None
        except (OSError, http.client.HTTPException) as e:
            k.close()
            utolso = e
    if isinstance(utolso, (socket.timeout, TimeoutError)) or time.monotonic() >= hatarido:
        raise HttpError(504, 'A kép letöltése túllépte az időkorlátot.', kod="kulso_kep.idotullepes")
    raise HttpError(502, 'A kép kiszolgálója nem érhető el.', kod="kulso_kep.nem_elerheto")


def _olvas(valasz, hatarido: float) -> bytes:
    hossz = valasz.getheader("Content-Length")
    if hossz is not None:
        try:
            if int(hossz) > MAX_BAJT:
                raise _hiba(413, 'A kép túl nagy.', "kulso_kep.tul_nagy", max_mib=MAX_BAJT // (1024 * 1024))
        except ValueError:
            raise HttpError(502, 'A kiszolgáló hibás választ adott.', kod="kulso_kep.hibas_valasz") from None
    reszek, osszes = [], 0
    while True:
        if time.monotonic() >= hatarido:
            raise HttpError(504, 'A kép letöltése túllépte az időkorlátot.', kod="kulso_kep.idotullepes")
        try:
            d = valasz.read(DARAB)
        except (socket.timeout, TimeoutError):
            raise HttpError(504, 'A kép letöltése túllépte az időkorlátot.', kod="kulso_kep.idotullepes") from None
        except (OSError, http.client.HTTPException):
            raise HttpError(502, 'A kép letöltése megszakadt.', kod="kulso_kep.megszakadt") from None
        if not d:
            break
        osszes += len(d)
        if osszes > MAX_BAJT:
            raise _hiba(413, 'A kép túl nagy.', "kulso_kep.tul_nagy", max_mib=MAX_BAJT // (1024 * 1024))
        reszek.append(d)
    return b"".join(reszek)


def letolt_bajtok(url: str, idokorlat: float = IDOKORLAT_MP) -> tuple[bytes, str, str]:
    """A kép bájtjai, a magicből kapott kiterjesztés és a végső (átirányítás utáni) link. Minden hiba `HttpError`."""
    url = url_ellenoriz(url)
    hatarido = time.monotonic() + idokorlat
    for _ in range(MAX_ATIRANYITAS + 1):
        valasz, k = _keres(url, hatarido)
        try:
            if valasz.status in (301, 302, 303, 307, 308):
                hova = valasz.getheader("Location")
                if not hova:
                    raise HttpError(502, 'A kiszolgáló hibás választ adott.', kod="kulso_kep.hibas_valasz")
                url = url_ellenoriz(urljoin(url, hova))
                continue
            if valasz.status != 200:
                raise _hiba(502, 'A kiszolgáló nem adta ki a képet.', "kulso_kep.http_hiba", statusz=valasz.status)
            tipus = (valasz.getheader("Content-Type") or "").split(";", 1)[0].strip().lower()
            if not tipus.startswith(_TIPUSOK):
                raise HttpError(415, 'A link nem képre mutat.', kod="kulso_kep.nem_kep")
            if (valasz.getheader("Content-Encoding") or "identity").strip().lower() != "identity":
                raise HttpError(415, 'A link nem képre mutat.', kod="kulso_kep.nem_kep")
            bajtok = _olvas(valasz, hatarido)
        finally:
            k.close()
        kiterj = kep_tipus(bajtok)
        if kiterj is None:
            raise HttpError(415, 'A link nem képre mutat.', kod="kulso_kep.nem_kep")
        return bajtok, kiterj, url
    raise HttpError(502, 'Túl sok átirányítás.', kod="kulso_kep.atiranyitas")


def letolt(app, d: dict) -> dict:
    """`POST /api/vault/import {url, forras}`: a kép letöltése és importja a `forras` jegyzet csatolmány-mappájába.
    → `{ok, kesz, ut, meglevo, figyelmeztetes, url}`."""
    forras = d.get("forras")
    if not isinstance(forras, str) or not forras.strip():
        raise HttpError(400, 'Hiányzik a forrásjegyzet.', kod="kulso_kep.forras_hianyzik")
    url = url_ellenoriz(d.get("url"))
    forras = vaultio.norm_path(forras)
    if not app.vault.lemezen(forras).is_file():         # a forrás létezik, a mappa érvényes — még a hálózat előtt
        raise HttpError(404, 'Nincs ilyen fájl vagy mappa.', kod="csatolmany.nincs_fajl")
    csatolmany.csatolmany_mappa(app.vault, forras)
    bajtok, kiterj, vegso = letolt_bajtok(url)
    r = csatolmany.bajt_import(app, bajtok, fajlnev(vegso, kiterj), forras)
    return {**r, "url": url}
