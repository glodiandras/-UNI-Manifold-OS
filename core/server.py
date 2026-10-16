"""A core HTTP (JSON) + WebSocket szervere, csak 127.0.0.1-en (ARCHITECTURE 2.).

Életciklus (a C02 kézfogása): indításkor egy JSON-sor a stdoutra (`{"port": N, "pid": P}`). A stdin
lezárulásakor a feladatsor új feladatot nem fogad, a futó feladatok a folyamatban lévő tétel végén
állnak meg (a sorban állók a DB-ben maradnak), a WS-kapcsolatok zárulnak, és a szerver a folyamatban
lévő kérések végén leáll. SIGTERM (a héj második ⌘Q-ja, H6): ugyanez, de a futó lépések azonnal állnak le,
és 10 s után a folyamat mindenképp kilép; a folyamatban lévő írás így is befejeződik. A SIGTERM a **már futó
rendezett leállást is kényszerré fokozza** (T003): a lépések azonnal állnak le, a 10 s-os `os._exit` élesedik, és
az `os._exit` előtt a kör-zárat legfeljebb 15 s-ig várjuk, hogy egy futó átnevezést ne vágjon el. A stdin-zárás után
`[core] leallas_fokozas_mp` (20 s) múlva a még futó feladat azonnal leáll (A-javító, 2026-10-14). A kézfogás-sor előtt csak
olcsó munka fut (D8): az indulási helyreállítás, az index és a forrásujjlenyomat a kézfogás után, háttérben.

Egypéldányos zár (T027; F3-DESIGN §4): a core a teljes élettartamára fogja a `{run}/core.lock`-ot (`fcntl.flock`; tartalma
`pid <pid> · <munkatér-azonosító | -> · <vault>`; termékben `<vault>/.manifold/var/run` alatt, így minden útírásra és két
macOS-fióknak is ugyanaz az inode) és a vault-őrt (`{install_run}/vaults/<k>.lock`, `k = sha256(F_GETPATH(vault))[:32]`: a
telepítés alatti állapotú, szinkronizált mappás munkatér is ugyanarra a vaultra fut össze), majd csak olvasva megpróbálja a
`[hordozhato] idegen_zarak` zárait (más telepítések `core.lock`-ja, pl. a v2-checkouté). Ha bármelyik foglalt, a már
fogottakat elengedi, az első stdout-sor `{"foglalt": true, "pid": N, "vault": "…"}`, a kilépési kód 75 — a héj ebből tudja,
hogy másik példány fut, és nem indít második ablakot. Utána, termékben, a `workspace.nyit` (formátum, áthelyezés, másolat).
Konfigurációs hibánál (`config.ConfigError`) az első sor `{"hiba": <kod>, "param": …, "uzenet": …}`, a kilépési kód 78 (nem
traceback). A sikeres kézfogás a `port`, `pid`, `titok` mellett a `vault` (kanonikus út), `munkater_id` és `elrendezes` mezőt
is hordozza: a héj a vault kötetének lecsatolását figyeli.

Biztonság (a legacy mintája, L29): a `Host` csak helyi cím lehet; minden `/api/*` kérésben
`X-Manifold: <API-titok>` (a core induláskor sorsolja, T071); a `/ws` `Origin`-je csak a saját origin lehet (vagy hiányzik), és a titkot
az alprotokoll hordozza (`Sec-WebSocket-Protocol: mos.<titok>`). Választás: standard
könyvtár (`ThreadingHTTPServer` + saját RFC 6455), lásd a NAPLO C03-bejegyzését.
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import (__version__, atirat, atnevezes, binaris_naplo, config, corenaplo, cpp_utvonal, elozmeny, events, felulet, frame, fuzet, fuzet_api, fuzet_figyelo, gepi_iras, grafikon_api, lepes_kapu, ma, media, mentes, naplo, naptar_api,
               naptar_szolgalat, sablon, pdfkiemeles, snapshot, tasks, tracker, tulajdonsagok, utvonalak, vaultio, video_api, videolanc,
               websocket)
from .bazis import api as bazis_api
from .felkeszultseg import api as felkeszultseg_api
from .index import api as index_api
from .index import indexelo
from .modell import aktivitas as modell_aktivitas
from .modell import api as modell_api
from .modell import beallitas as modell_beallitas
from .modell import jelek as modell_jelek
from .modell import halmaz
from .modell import kalibracio, kapu, kliens
from . import vezerlo
from . import higienia
from .hibakod import angol_uzenet, json_param
from .asszisztens import api as asszisztens_api
from .asszisztens import homlokzat as asszisztens_homlokzat
from . import kviz_api
from . import kereses_api
from . import matek_api
from . import automatika, kartya_api, osszefoglalas_api
from . import kepek

URES_LAP = (
    "<!doctype html><html lang=\"hu\"><head><meta charset=\"utf-8\"><title>Manifold</title>"
    "<meta name=\"color-scheme\" content=\"light dark\"></head><body></body></html>"
).encode()
HELYI_GAZDAK = {"127.0.0.1", "localhost", "[::1]"}
MAX_TORZS = 16 * 1024 * 1024
KOR_ID = frame.KOR_MINTA           # L12; a C16.5 óta új lánc új előtagot hozhat
KEZELO_IDOKORLAT_MP = 30           # T003: egy kapcsolat egy socket-művelete (olvasás/írás) legfeljebb ennyit vár
KEREL_VARAKOZAS_MP = 35            # a rendezett leállás ennyit vár a folyamatban lévő kérésekre (> KEZELO_IDOKORLAT_MP)
KENYSZER_MP = 10                   # SIGTERM után ennyi múlva a folyamat mindenképp kilép (H6)
KOR_ZAR_VARAKOZAS_MP = 15          # … de előbb ennyit vár a kör-zárra: futó átnevezést/írást ne vágjon el (K1-A2-iras-10)
KENYSZER_MENTES_MP = 1.0           # K44: a második ⌘Q ágán a belső lemezes bundle-próba időkerete
LEALLAS_FOKOZAS_MP = 20.0          # a stdin-zárás (rendezett leállás) után ennyi múlva a még futó feladat azonnal leáll
INDULAS_VARAKOZAS_MP = 10.0        # a leállás legfeljebb ennyit vár a még futó indulási háttérmunkára (kör-zár, index)
CORE_ZAR_KILEPES = 75              # EX_TEMPFAIL: másik core fut ugyanezen a vaulton (T027)
KONFIG_HIBA_KILEPES = 78           # EX_CONFIG: a konfiguráció vagy a munkatér nem nyitható meg (`{"hiba": kod}` sor)


HttpError = utvonalak.HttpError      # a kezelők kivétele; a regiszterben (utvonalak.py) él, itt a régi név marad
hiba_torzs = utvonalak.hiba_torzs


def rss_mb(pid: int | None = None) -> float | None:
    """A folyamat jelenlegi rezidens memóriája MB-ban (`ps`)."""
    p = subprocess.run(["ps", "-o", "rss=", "-p", str(pid or os.getpid())], capture_output=True, text=True)
    try:
        return round(int(p.stdout.strip()) / 1024, 1)
    except ValueError:
        return None


def automatikus_tiltott(t: tasks.TaskType) -> str | None:
    """80(a) „AI csak gombra”: a feladatsor kapuja az automatikus feladattípusokra.

    Magától csak a `vektorindex` futhat (keresési vektorok, a vaultba nem ír). Minden más `automatikus=True` típus — a kártya, az
    összefoglaló, a grafikon-beírás és a füzetmappa (`fuzet_automatikus`) automatikus párja — beküldéskor elutasított, a sorban maradt
    régi példánya pedig `torolve` lesz; a kézi párjuk (nem automatikus típus) érintetlen. → indok (magyar), vagy None, ha szabad."""
    if t.automatikus and t.id != "vektorindex":
        return (f"A(z) „{t.id}” automatikus feladat nem indulhat: tartalmat generáló AI csak kifejezett, kézi paranccsal fut "
                "(80(a) döntés). Használd a megfelelő kézi parancsot (pl. „Kártyák ebből”).")
    return None


# A végpontokat regisztráló modulok (mindegyiknek van `utvonalak(r)` függvénye); a sorrend a mintaillesztés sorrendje
from . import epites, csatolmany, teljes_mentes, termek_beallitasok, modulkapu, munkater_futo, egeszseg, adatvedelem, demo
from . import doku, importalas

UTVONAL_MODULOK = (termek_beallitasok, egeszseg, adatvedelem, demo, doku, importalas, epites, csatolmany, teljes_mentes, vaultio, atnevezes, tulajdonsagok, elozmeny, felulet, tasks, media, index_api, bazis_api, modell_api,
                   sablon, naplo, ma, atirat, pdfkiemeles, gepi_iras, tracker, naptar_api,
                   grafikon_api, higienia, asszisztens_api, kviz_api, felkeszultseg_api, cpp_utvonal, kereses_api,
                   matek_api, fuzet_api, kartya_api, osszefoglalas_api, video_api)


_TITOK_MINTA = re.compile(r"^[A-Za-z0-9_.-]{16,128}$")


def api_titok_sorsol(rogzitett: str | None = None) -> str:
    """Az API titka: a `rogzitett` (a `python -m core start` a `MOS_API_TITOK`-ot olvasás után kiveszi a környezetből, és így
    adja át), különben a `MOS_API_TITOK` (a héj újraindításkor ugyanazt adja vissza, hogy a lap titka érvényes maradjon; a
    tesztek és a kézi próbák rögzítik), különben `secrets.token_urlsafe(32)`. A titok csak betű, szám, `_`, `.`, `-` lehet
    (16–128 karakter): HTTP-token, így a WS-alprotokoll nevének is jó."""
    t = rogzitett or os.environ.get("MOS_API_TITOK")
    if not t:
        return secrets.token_urlsafe(32)
    if not _TITOK_MINTA.match(t):
        raise ValueError("MOS_API_TITOK: csak betű, szám, _ . - lehet, 16–128 karakter")
    return t


class App:
    """A core állapota: config, esemény-busz, feladatsor, vault-API, nyitott WS-kapcsolatok."""

    def __init__(self, cfg: config.Config, start_delay: float | None = None, api_titok: str | None = None):
        self.cfg = cfg
        halmaz.sajat_gyoker_beallit(cfg.path("install") / "eval-sajat")   # F6: a saját aranyhalmaz a router verziójában
        self.indulas_ido = time.time()      # a korábbi munkamenet maradékai ennél régebbiek (`frame.tmp_takaritas`)
        # CX-001: a futó mag ujjlenyomata — a kézfogás UTÁN, háttérszálon számolódik (`epites_szamol`, D8); addig None
        # (a `/api/rendszer/epites` „még nem ismert”-ként adja)
        self.epites_mag: str | None = None
        # 35. döntés (T071): az API titka — a statikus `X-Manifold: 1` helyett a core induláskor sorsolja; a kézfogás-sor a héjnak
        # adja, a héj a felületbe injektálja, a lépések a környezetükben kapják. Egy sandboxolt helyi kliens, másik macOS-fiók vagy
        # böngésző-bővítmény a statikus fejléccel olvasná és írná a vaultot; a titkot nem találhatja ki
        self.api_titok = api_titok_sorsol(api_titok)
        self.bus = events.Bus()
        # a modellréteg core-oldali része (C05): aktivitásjel, kapu, a worker gyermekfolyamata — ML nélkül
        self.mb = modell_beallitas.betolt(cfg)
        # C29.8 (T132, L11): a kapu jeleit (memória, tétlenség) külön szál méri; a kapu a sor zárja alatt csak olvas
        self.jelek = modell_jelek.Jelek()
        self.aktivitas = modell_aktivitas.Aktivitas.beallitasbol(self.mb, hid=self.jelek.hid)
        szunet = cfg.section("feladatsor").get("indulasi_szunet_mp", 180) if start_delay is None else start_delay
        self.indulasi_szunet = float(szunet)
        self.kapu = kapu.Kapu(self.aktivitas, self.mb.gazda["min_szabad_szazalek"], szunet, jelek=self.jelek)
        self.worker = kliens.Folyamat(cfg)
        self._figyelo: threading.Thread | None = None
        # 34. döntés: bundle minden gépi kör (vault-író feladat) végén és tétlenségben 30 percenként, ha a HEAD változott
        self.mentes_utemezo = mentes.Utemezo(cfg, aktivitas=self.aktivitas)
        self.queue = tasks.Queue(cfg, publish=self._feladat_publish, start_delay=start_delay,
                                 tiltott=automatikus_tiltott,
                                 admit=vezerlo.admit_lanc(cfg, self.kapu), env_extra=self.feladat_env,
                                 leallitas_horog=self._worker_megszakit, indulas_horog=self._worker_automatikus)
        # CX-012: a teljes (külső) mentés lemezfigyelője — opcionális (`[teljes_mentes] figyelo_be`, alapból ki), a D8-szünet után
        self.teljes_mentes_figyelo = teljes_mentes.LemezFigyelo(cfg, self.queue)
        # C25c: a PDF-szöveg kinyerése (gyermekfolyamatban) a kapu alatt: a D8-szünet után, aktív használatban nem, kevés memóriánál nem
        # C33 (T175): ha az index tétlenségben észleli, hogy a vault eltűnt / visszajött, a `Vault` egyetlen `vault_elerheto` eseménye megy
        self.index = indexelo.Index(cfg, publish=self.bus.publish, pdf_kapu=self.kapu.automatikus_szabad,
                                    elerheto=lambda ok: self.vault._elerheto_jelez(ok))
        # C16.5 (28. döntés): a futó vault-író feladat nem tiltja a mentés pillanatképét, az átnevezést és a
        # visszavonást — a lépések csak a gépi-írás szolgáltatáson át írnak, a kizárás a kör-zár, tételenként
        self.vault = vaultio.Vault(cfg, publish=self._vault_esemeny, sajat=self.index.vart_iras)
        self.atnevezes = atnevezes.Atnevezes(cfg, self.vault, self.index, publish=self.bus.publish,
                                             mentetlen=self.mentetlen_utak)
        self.tulajdonsagok = tulajdonsagok.Tulajdonsagok(cfg, self.index)
        self.bazisok = bazis_api.Bazisok(cfg, self.index)
        self.elozmeny = elozmeny.Elozmeny(cfg, jelez=self._index_jelez)
        self._ws: set[websocket.Connection] = set()
        self._media: set = set()             # a folyó médiaküldések socketjei: a leállás lezárja őket (`close_ws`)
        self._lock = threading.Lock()
        # a felület kapcsolatonként jelenti a mentetlen dokumentumait (WS `mentetlen`): a gép ezekbe nem ír (C16.5)
        self._mentetlen: dict[websocket.Connection, set[str]] = {}
        # T107 (C29.7b): a bontott kapcsolat halmaza türelmi ideig megmarad — a WS-kiesés alatt a felület szövege még él,
        # a gép ne írjon mellé (28(c)); az új kapcsolat teljes halmaza vagy a lejárat felszabadítja
        self._turelem: list[tuple[float, set[str]]] = []
        self.mentetlen_turelem_mp = float(cfg.section("core").get("mentetlen_turelem_mp", 15))
        self._ora = time.monotonic
        # C27 (30. döntés): a tracker a pos.sqlite egyetlen írója; a gyűjtője hibatűrő, soha nem akaszt
        self.tracker = tracker.Tracker(cfg)
        # C36a: a C++ munkafelület — a motor gyermekfolyamat (modulok/cpp); az eredmény WS-esemény (cpp_futas)
        self.cpp = cpp_utvonal.Szolgalat(cfg, self.vault, self.index, self.bus.publish, self.tracker, self.mentetlen_utak)
        self.gepi = gepi_iras.GepiIras(cfg, self.vault, self.tulajdonsagok, publish=self._vault_esemeny,
                                       sajat=self.index.vart_iras, mentetlen=self.mentetlen_utak,
                                       jelzo=self.tracker.gepi_iras,
                                       esemeny_jelzo=self._gepi_esemeny)
        # C29 (32. döntés): naptár és emlékeztetők — háttérszál az app futása alatt; a jegyzet módosítása a gépi írás
        # szolgáltatáson át megy (in-process hívás ugyanarra a `GepiIras.ir`-re)
        self.naptar = naptar_szolgalat.NaptarSzolgalat(cfg, self.index, self.vault, self.gepi, tracker=self.tracker,
                                                       publish=self.bus.publish,
                                                       indulasi_kesleltetes_mp=None if start_delay is None else start_delay)
        # C30a: az Asszisztens modell nélküli magja — a higiénia-riport háttérszála (D8-késleltetéssel, aktív használat alatt
        # szünetel), említések, heti szokásminta, elfogadási statisztika; a vaultba nem ír, modellt nem tölt
        self.asszisztens = asszisztens_homlokzat.Asszisztens(
            cfg, self.index, self.tulajdonsagok, self.tracker, self.aktivitas, publish=self.bus.publish,
            indulasi_kesleltetes_mp=szunet)
        from . import kiegeszites_modell
        self.asszisztens.kiegeszites.general = (lambda elotte, utana, azon, mod='folytat', kijeloles='':
                                                kiegeszites_modell.general(self, elotte, utana, azon, mod, kijeloles))
        self.asszisztens.mintatar.hasonlok = self._hasonlo_jegyzetek     # J3: a kártya tartalmi jelöltje (C25c, modell nélkül)
        self.asszisztens.kiegeszites.megszakit = lambda azon: self._worker_megszakit('KIEG-' + azon)
        # C21: a füzetmappa figyelője — csak stat, D8-késleltetéssel; új fotónál `fuzet_automatikus` feladatot küld (a kapu alatt fut)
        self.fuzet_figyelo = fuzet_figyelo.Figyelo(cfg, self.queue, publish=self.bus.publish,
                                                   indulasi_kesleltetes_mp=None if start_delay is None else start_delay)
        # C23b: a kártyamappa → tanulas.sqlite szinkron (a vault változásaira) és a közös automatika-ütemező (T149): a fogyasztók
        # (80(a): csak a vektorindex; a kártya/összefoglaló/grafikon automatikus fogyasztója `be = true`-ra sem indul, CX-011) feladatát küldi be — a D8-szünet után
        self.kartya_szinkron = kartya_api.KartyaSzinkron(cfg, self.bus, indulasi_kesleltetes_mp=min(20.0, float(szunet)))
        automatika.alap_fogyasztok(cfg)
        self.automatika = automatika.Utemezo(cfg, self.index, self.queue, self.bus,
                                             kapcsolo=lambda: vezerlo.kapcsolok(cfg)["asszisztens"],
                                             indulasi_kesleltetes_mp=szunet)
        # a média-URL-ek tokenje (C10): az <img>/<video>/<iframe> nem küldhet X-Manifold fejlécet, ezért az
        # URL maga hitelesít; a token csak az API-n (fejléces kérésre) és a WS-en át jön
        self.media_token = secrets.token_urlsafe(24)
        self.closing = False
        self.port = 0
        # az indulási helyreállítás üzenetei (elakadt index.lock, megszakadt átnevezés): az első WS-kapcsolat
        # `hello`-ja viszi a felületnek, utána ürül
        self.indulasi_uzenetek: list[str] = []
        self.helyreallitas_szal: threading.Thread | None = None
        self.indulas_szal: threading.Thread | None = None       # a kézfogás utáni indulási munka (`indulasi_hatter`)
        # az útvonal-regiszter: a modulok maguk regisztrálják a végpontjaikat (C11a; az építés közös: `regiszter_epit`)
        self.utvonalak = regiszter_epit()

    helyreallitas_ujra_mp = 2.0             # foglalt kör-zárnál ennyi időnként próbálja újra az indulási helyreállítást (T093)
    helyreallitas_ujra_max_mp = 600.0       # … és legfeljebb ennyi ideig

    def indulas(self, tmp_takarit: bool = True) -> None:
        """Indulási helyreállítás a kör-zár alatt, az index előtt (K1, H3). Csak valódi vaulton (`.obsidian`): a
        symlinkelt `var/`-ú munkafa core-ja a valódi `{run}`-t kapja, a vaultja viszont nem létezik (T002). Foglalt
        kör-zárnál (egy másik folyamat éppen a vaultot írja) a helyreállítás nem marad el csendben (T093): az üzenet a
        `hello`-ba kerül, és egy háttérszál a zár felszabadulásakor lefuttatja.

        `tmp_takarit=False` (A-javító, 2026-10-14, D8): a core indulása a kézfogás ELŐTT csak a gyors, naplóvezérelt részt
        futtatja (elakadt `index.lock`, megszakadt visszavonás, átnevezés, gépi írás — ezeknek a felület első mentése előtt
        kell lezárulniuk); a teljes vault bejárását igénylő ideiglenesfájl-takarítás a kézfogás után, háttérben jön
        (`tmp_takaritas_hatter`)."""
        with frame.indulasi_zar(self.cfg) as van:
            if van and not frame.vault_letezik(self.cfg):
                print(f"[indulás] a vault nem található ({self.cfg.path('vault')}, nincs .obsidian): az indulási "
                      "helyreállítás kimarad", file=sys.stderr, flush=True)
            elif van:
                self.indulasi_uzenetek += self._helyreallitas_zarban(tmp_takarit=tmp_takarit)
            else:
                self.indulasi_uzenetek.append(
                    "Startup recovery is waiting because another process holds the operation lock. Recovery will run "
                    "when the lock is released; remnants of an interrupted write may remain in the vault until then.")
                self._helyreallitas_ujra()
        hiba = mentes.hiba_olvas(self.cfg)      # T023: az előző kilépési/időzített mentés hibája nem maradhat néma
        if hiba:
            self.indulasi_uzenetek.append(
                f"The previous local backup failed ({hiba.get('ido', '?')}) for: {', '.join(hiba['hibak'])}. "
                "Your text is still on the vault volume, but the local backup is older than the latest changes. "
                f"Error details are preserved at: {self.cfg.path('state') / mentes.HIBA_FAJL}. "
                "The next successful backup (on exit or every 30 minutes while idle) will clear this warning.")
        for u in self.indulasi_uzenetek:
            print(f"[indulás] {u}", file=sys.stderr, flush=True)

    def tmp_takaritas_hatter(self) -> None:
        """A-javító (2026-10-14, D8): a megmaradt saját ideiglenes fájlok takarítása a kézfogás után. A vault bejárása a
        kör-zár NÉLKÜL fut (a mentés pillanatképét nem tartja vissza), a törlés a zár alatt, és csak a core indulása előtt
        módosult fájlra (egy folyó mentés friss ideiglenes fájlja nem maradék). Foglalt zárnál a következő indulásra marad."""
        if not frame.vault_letezik(self.cfg):
            return
        jeloltek = frame.tmp_maradekok(self.cfg)
        if not jeloltek:
            return
        with frame.indulasi_zar(self.cfg) as van:
            uzenetek = frame.tmp_takaritas(self.cfg, elotte=self.indulas_ido, jeloltek=jeloltek) if van else []
        for u in uzenetek:
            print(f"[indulás] {u}", file=sys.stderr, flush=True)
        self._uzenetek_kezbesit(uzenetek)

    def _uzenetek_kezbesit(self, uzenetek: list[str]) -> None:
        """Az indulási üzenetek a felületnek: ha még nincs WS-kapcsolat, a következő `hello` viszi (`indulasi_uzenetek`),
        különben `indulasi_uzenet` esemény. A döntés a `_lock` alatt: a WS-kezelő a `bus`-ra az `add_ws` ELŐTT iratkozik
        fel, így az üzenet egyik úton sem veszhet el."""
        if not uzenetek:
            return
        with self._lock:
            van_ws = bool(self._ws)
            if not van_ws:
                self.indulasi_uzenetek += uzenetek      # nincs kinek: a következő `hello` viszi
        if van_ws:
            self.bus.publish({"tipus": "indulasi_uzenet", "uzenetek": uzenetek})     # a felület rögtön látja (C29.7b)

    def indulasi_hatter(self) -> threading.Thread:
        """A-javító (2026-10-14, D8): a kézfogás után, egy háttérszálon fut a saját ideiglenes fájlok takarítása (a vault
        bejárása) és a futó mag ujjlenyomata. A kézfogás-sor ezekre nem vár."""
        def fut() -> None:
            if not self.closing:
                _csendben(self.tmp_takaritas_hatter)
            _csendben(self.epites_szamol)
        self.indulas_szal = threading.Thread(target=fut, name="indulas-hatter", daemon=True)
        self.indulas_szal.start()
        return self.indulas_szal

    def epites_szamol(self) -> str:
        """CX-001: a futó mag ujjlenyomata, egyszer, a futás idejére (a forrásfájlokból, `core/epites.py`)."""
        self.epites_mag = epites.ujjlenyomat(self.cfg.root, 'mag')
        return self.epites_mag

    def _helyreallitas_zarban(self, tmp_takarit: bool = True) -> list[str]:
        """Az indulási helyreállítás teste (a kör-zár birtokában): elakadt `index.lock`, megszakadt átnevezés és gépi írás,
        megmaradt saját ideiglenes fájlok. → a felhasználónak szóló üzenetek."""
        uzenetek = frame.index_lock_takaritas(self.cfg)
        for repo in frame.live_repos(self.cfg).values():       # T099: a régi tárolók is megkapják a zárt git-környezetet
            try:
                repo.biztosit_kornyezet()
            except (OSError, snapshot.SnapshotError) as e:
                uzenetek.append(f"The Git environment of the {repo.name} snapshot store could not be secured "
                                f"({type(e).__name__}). See the Manifold log for details.")
                print(f"[recovery] {repo.name}: {e}", file=sys.stderr, flush=True)
        for repo in frame.live_repos(self.cfg).values():       # T020: egy megszakadt visszavonás/visszaállítás naplója
            try:
                uzenetek += repo.visszavonas_helyreallit()
            except (OSError, ValueError, KeyError, snapshot.SnapshotError) as e:
                uzenetek.append(f"Recovery of an interrupted undo in {repo.name} failed ({type(e).__name__}). "
                                f"Its journal is preserved at: {repo.naplo_dir}. See the Manifold log for details.")
                print(f"[recovery] undo {repo.name}: {e}", file=sys.stderr, flush=True)
        try:
            uzenetek += atnevezes.helyreallit(self.cfg)
        except (OSError, ValueError, KeyError) as e:      # a core ettől még induljon el
            uzenetek.append(f"Recovery of an interrupted rename failed ({type(e).__name__}). "
                            f"Its journal is preserved at: {self.cfg.path('run') / atnevezes.NAPLO}. See the Manifold log for details.")
            print(f"[recovery] rename: {e}", file=sys.stderr, flush=True)
        try:
            uzenetek += gepi_iras.helyreallit(self.cfg)
        except (OSError, ValueError, KeyError, snapshot.SnapshotError) as e:
            uzenetek.append(f"Recovery of an interrupted machine write failed ({type(e).__name__}). "
                            f"Its journal is preserved at: {self.cfg.path('run') / gepi_iras.NAPLO}. See the Manifold log for details.")
            print(f"[recovery] machine write: {e}", file=sys.stderr, flush=True)
        if tmp_takarit:     # a T093-as újrapróba a kézfogás után fut: csak a core indulása ELŐTT keletkezett maradék törlődik
            uzenetek += frame.tmp_takaritas(self.cfg, elotte=getattr(self, "indulas_ido", None))
        return uzenetek

    def _helyreallitas_ujra(self) -> None:
        """T093: háttérszál — a kör-zár felszabadulásáig (korlátosan) várva lefuttatja az elmaradt indulási helyreállítást;
        az üzenetek az `indulasi_uzenetek`-be kerülnek (az első/következő WS-kapcsolat `hello`-ja viszi)."""
        def fut() -> None:
            t0 = time.monotonic()
            while not self.closing and time.monotonic() - t0 < self.helyreallitas_ujra_max_mp:
                time.sleep(self.helyreallitas_ujra_mp)
                with frame.indulasi_zar(self.cfg) as van:
                    if not van:
                        continue
                    uzenetek = self._helyreallitas_zarban() if frame.vault_letezik(self.cfg) else []
                self._uzenetek_kezbesit(uzenetek)
                for u in uzenetek:
                    print(f"[indulás] {u}", file=sys.stderr, flush=True)
                return
        self.helyreallitas_szal = threading.Thread(target=fut, name="helyreallitas-ujra", daemon=True)
        self.helyreallitas_szal.start()

    def indulasi_uzenetek_atad(self) -> list[str]:
        with self._lock:
            out, self.indulasi_uzenetek = self.indulasi_uzenetek, []
        return out

    VEGALLAPOTOK = ("kesz", "hiba", "megallitva", "megszakadt")

    def _feladat_publish(self, e: dict, **k) -> None:
        """A feladatsor eseményei a WS-nek; egy vault-író feladat vége (gépi kör vége) a belső lemezes mentés jele is (34. döntés)."""
        self.bus.publish(e, **k)
        f = e.get("feladat") if e.get("tipus") == "feladat" else None
        if f and f.get("vault_ir") and f.get("allapot") in self.VEGALLAPOTOK:
            self.mentes_utemezo.kor_vege()
        if f and f.get("allapot") == "kesz":
            # C20b: a „Letöltés és bevitel” a sikeres letöltés után a SAJÁT letöltött mappáit sorba teszi (F4: hibánál nem)
            videolanc.letoltes_utan(self.queue, f)

    def _gepi_esemeny(self, e: dict) -> None:
        """C20b: a gépi tétel tracker-eseménye (`gepi_iras.ESEMENYEK`, a commit után, élesben): a videólánc záró eseménye a
        `Tracker.integralt_video` (a lépés a pos.sqlite-hoz nem fér hozzá)."""
        if e["tipus"] == "integralt_video":
            a = e["adat"]
            self.tracker.integralt_video(e["ut"], int(a.get("video_s") or 0), int(a.get("jegyzet_db") or 0),
                                         str(a.get("kotes") or "nincs"))

    def _vault_esemeny(self, e: dict, **k) -> None:
        """A `vaultio` eseménye a WS-nek; a saját írás az indexbe is azonnal bekerül (C06)."""
        self.bus.publish(e, **k)
        if e.get("tipus") == "vault_iras":
            self.index.sajat_iras(e["ut"], e["hash"])

    def add_ws(self, c: websocket.Connection) -> bool:
        with self._lock:
            if self.closing:
                return False
            self._ws.add(c)
            return True

    def drop_ws(self, c: websocket.Connection) -> None:
        with self._lock:
            self._ws.discard(c)
            utak = self._mentetlen.pop(c, None)
            if utak and not self.closing and self.mentetlen_turelem_mp > 0:
                self._turelem.append((self._ora() + self.mentetlen_turelem_mp, utak))

    def ws_uzenet(self, c: websocket.Connection, szoveg: str) -> None:
        """A felület üzenete a WS-en. `{tipus: "mentetlen", utak}`: a kapcsolat mentetlen dokumentumai (a teljes
        halmaz, minden változáskor); a kapcsolat zárásával törlődik. Más üzenet és a hibás alak némán kimarad."""
        try:
            e = json.loads(szoveg)
        except ValueError:
            return
        if isinstance(e, dict) and e.get("tipus") == "mentetlen" and isinstance(e.get("utak"), list):
            utak = {vaultio.nfc(u) for u in e["utak"][:2000] if isinstance(u, str)}
            with self._lock:
                if c in self._ws:
                    self._mentetlen[c] = utak
                    self._turelem.clear()           # a visszacsatlakozott felület teljes, hiteles halmazt küldött

    def mentetlen_utak(self) -> set[str]:
        with self._lock:
            most = self._ora()
            self._turelem = [(h, u) for h, u in self._turelem if h > most]
            return set().union(*self._mentetlen.values(), *(u for _, u in self._turelem))

    def titok_ok(self, kapott: str | None) -> bool:
        """Az API-titok egyezése (időállandó összevetés)."""
        return hmac.compare_digest((kapott or "").encode("utf-8"), self.api_titok.encode("utf-8"))

    def close_ws(self) -> None:
        """A leállás: a WS-kapcsolatok zárása és a folyó médiaküldések (videó-stream) megszakítása — egy lejátszás alatt álló
        videó kérése különben `KEREL_VARAKOZAS_MP`-ig tartaná a rendezett kilépést."""
        with self._lock:
            self.closing = True
            conns = list(self._ws)
            media_socketek = list(self._media)
        for c in conns:
            c.close(1001)
        for s in media_socketek:
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    @contextlib.contextmanager
    def media_kuldes(self, sock):
        """Egy folyó médiaküldés nyilvántartása (a `close_ws` megszakítja); leálláskor új küldés nem indul (503)."""
        with self._lock:
            if self.closing:
                raise HttpError(503, "a core leáll", kod="core.leall")
            self._media.add(sock)
        try:
            yield
        finally:
            with self._lock:
                self._media.discard(sock)

    # -------------------------------------------------------- modellréteg (C05)

    def feladat_env(self, t: tasks.TaskType) -> dict[str, str]:
        """A modelligényes és az automatikus feladat lépései a worker címét és a kérésmódot kapják."""
        # a gépi írás kliense ezen éri el a core-t (C16.5). A lépés a felületi API-titkot NEM kapja (35. döntés + T137, `core/lepes_kapu.py`):
        # a hitelesítője a `queue` által lépésenként sorsolt lépés-token (`MOS_LEPES_TOKEN`), amelyet a core az `X-Manifold` fejlécben
        # fogad, és amellyel csak a gépi írás és a tiszta számolók érhetők el
        env = {"MOS_CORE_URL": f"http://127.0.0.1:{self.port}"}
        if "modell" not in t.resources and not t.automatikus:
            return env
        u = self.worker.biztosit()
        self._figyelo_indit()
        # T182: a worker munkamenet-titka (a lépés kliense ezzel kéri a modellt; a pidfájl 0600, más folyamat nem olvassa)
        return {**env, "MOS_WORKER_URL": u, "MOS_WORKER_TITOK": kliens.titok(u),
                "MOS_MODELL_MOD": "auto" if t.automatikus else "interaktiv"}

    def _worker_automatikus(self, t: tasks.TaskType, fid: str) -> None:
        """M3 (C19): az automatikus feladat azonosítóját a worker is megkapja, és a kéréseit a lépés által küldött módtól
        függetlenül `auto` módban futtatja. Workert nem indít (a `feladat_env` már elindította, ha kell)."""
        if not t.automatikus:
            return
        u = self.worker.url or kliens.fut_url(self.cfg)
        if u:
            try:
                kliens.automatikus(u, fid)
            except kliens.KliensHiba:
                pass                                   # a lépés env-je (`MOS_MODELL_MOD=auto`) így is auto-t kér

    def _hasonlo_jegyzetek(self, ut: str, n: int) -> dict:
        """A C25c hasonló jegyzetei a vektortárból (modell nélkül) — az Asszisztens kártyájának tartalmi forrása (J3)."""
        from .automatika import kisero_elotag
        from .index.hibrid import hasonlo as H
        from .kereses_api import szolgalat
        return H.hasonlok(self.index.olvaso, szolgalat(self).tar(), ut, n, kisero_elotag(self.cfg))

    def _worker_megszakit(self, fid: str) -> None:
        """Egy leállított feladat folyó generálása szakadjon meg a workerben (C17). Workert nem indít: ha nem fut,
        nincs mit megszakítani."""
        u = self.worker.url or kliens.fut_url(self.cfg)
        if u:
            try:
                kliens.megszakit(u, fid)
            except kliens.KliensHiba:
                pass

    def _figyelo_indit(self) -> None:
        with self._lock:
            if self._figyelo is not None and self._figyelo.is_alive():
                return
            self._figyelo = threading.Thread(target=self._figyel, name="modell-figyelo", daemon=True)
            self._figyelo.start()

    def _figyel(self) -> None:
        """A worker állapota WS-eseményként (`modell`), változáskor; 5 s-onként, amíg a worker él."""
        elozo = None
        while not self.closing and self.worker.el():
            try:
                h = kliens.health(self.worker.url)
                most = {k: h.get(k) for k in ("modell", "keret_gb", "szunetek", "hutes_hatra_mp", "aktivitas", "fut")}
                most["aktivitas"] = (most["aktivitas"] or {}).get("allapot")
                self.tracker.szunet_minta("memoria", h.get("szunetek"), h.get("szunet_mp"))     # C27: a memóriaőr szünetei
                self.tracker.szunet_minta("hutes", h.get("hutesi_szunetek"), None)
            except kliens.KliensHiba:
                most = {"modell": None, "elerheto": False}
            if most != elozo:
                self.bus.publish({"tipus": "modell", **most})
                elozo = most
            for _ in range(10):
                if self.closing:
                    return
                time.sleep(0.5)

    def modell_allapot(self) -> dict:
        h = None
        if self.worker.url or kliens.fut_url(self.cfg):
            try:
                h = kliens.health(self.worker.url or kliens.fut_url(self.cfg))
            except kliens.KliensHiba:
                h = None
        t = kalibracio.megnyit(self.cfg)
        try:
            tabla = t.tabla()
        finally:
            t.close()
        return {"aktivitas": self.aktivitas.publikus(), "kapu": self.kapu.utolso_ok or None, "worker": h,
                "router": tabla}

    # -------------------------------------------------------- pillanatkép

    def repo(self, tar: str) -> snapshot.Repo:
        r = frame.live_repos(self.cfg).get(tar)
        if not r:
            raise HttpError(404, f"nincs ilyen élő pillanatkép-tároló: {tar}", kod="pillanatkep.nincs_tar", param={"tar": tar})
        return r

    def undo(self, tar: str, body: dict) -> dict:
        repo = self.repo(tar)
        sha, kor = body.get("sha"), body.get("kor")
        if bool(sha) == bool(kor):
            raise HttpError(400, "adj meg pontosan egyet: sha vagy kor", kod="pillanatkep.sha_vagy_kor")
        if kor and (not isinstance(kor, str) or not KOR_ID.fullmatch(kor) or "proba" in kor):
            raise HttpError(400, f"érvénytelen vagy próba-kör: {kor}", kod="pillanatkep.kor_ervenytelen", param={"kor": kor})
        if sha and (not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{7,40}", sha)):
            raise HttpError(400, f"érvénytelen commit: {sha}", kod="pillanatkep.commit_ervenytelen", param={"sha": sha})
        feladat = body.get("feladat")
        if feladat is not None and (not isinstance(feladat, str) or not re.fullmatch(r"F-[0-9]{8}-[0-9]{6}-[0-9]+", feladat)):
            raise HttpError(400, f"érvénytelen feladat-azonosító: {feladat!r}", kod="pillanatkep.feladat_azon", param={"feladat": repr(feladat)})
        kivetelek = snapshot.exclusions(self.cfg, tar)
        visszavont_forrasok: list = []
        media: dict = {}
        try:
            with frame.run_lock(self.cfg, wait=False, turelem_mp=frame.felhasznaloi_turelem(self.cfg)):
                # T174: a kör commitjai EGYSZER, `--fixed-strings --grep`-pel (nem a teljes napló kétszer Pythonban bontva);
                # a forrás-statisztika, a visszavonás és a füzetlánc ugyanazt a listát kapja
                kor_commitok = None
                if kor:
                    kor_commitok = [c for c in self._kor_commitok(repo, kor)
                                    if feladat is None or c.trailers.get(snapshot.TRAILER_TASK) == feladat]
                if tar == "vault":
                    visszavont_forrasok = self._visszavont_forrasok(repo, sha, kor_commitok)
                uj = repo.undo_commit(sha, kivetelek) if sha else repo.undo_run(kor, kivetelek, feladat, commitok=kor_commitok)
                if tar == "vault":          # a bináris média (L19, C20a): a kör-zár alatt, a szöveg visszavonása után
                    media = self._media_visszaallit(repo, sha, kor)
                    self._fuzet_visszavonas(repo, sha, kor, kor_commitok)
        except frame.Busy as exc:
            raise HttpError(409, str(exc), kod="pillanatkep.foglalt", foglalt=True) from exc
        except snapshot.NaploAll as exc:
            raise HttpError(409, str(exc), kod="pillanatkep.naplo_all", naplo=True) from exc
        except snapshot.UndoConflict as exc:
            raise HttpError(409, str(exc), kod="pillanatkep.visszavonas_utkozes", utkozes=True, fajlok=exc.files) from exc
        except snapshot.SnapshotError as exc:
            raise HttpError(400, str(exc), kod="pillanatkep.hibas") from exc
        if tar == "vault":                  # az index ne a figyelőre várjon (C16.5): az érintett utak azonnal
            self._index_jelez(repo.changed_files(uj))
        self.bus.publish({"tipus": "visszavonas", "tar": tar, "sha": uj, "visszavont": sha or kor})
        self.tracker.visszavonas(visszavont_forrasok)
        return {"ok": True, "sha": uj, **({"media": media} if media else {})}

    def _media_visszaallit(self, repo: snapshot.Repo, sha: str | None, kor: str | None) -> dict:
        """A visszavont tétel bináris fájljai a lánc munkamappájába (`binaris_naplo`, L19): nem törlünk, nem írunk felül. A szöveg
        visszavonását a média hibája nem hiúsítja meg (a hiba a válaszban és a naplóban). → üres, ha nem volt mit tenni."""
        def log(s: str) -> None:
            print(f"[visszavonás] {s}", file=sys.stderr, flush=True)
        try:
            r = binaris_naplo.visszavonas_utan(self.cfg, repo, sha, kor, log=log)
        except Exception as e:  # noqa: BLE001 — a média-visszaállítás hibája nem vihet el egy már megtörtént szöveg-visszavonást
            log(f"a bináris fájlok visszaállítása nem sikerült: {e}")
            return {"hiba": str(e)}
        if r["mozgatva"]:
            self._index_jelez([rel for rel, _ in r["mozgatva"]])
        ki = {"visszakoltoztetve": len(r["mozgatva"]), "marad": [{"ut": u, "ok": o} for u, o in r["marad"]]}
        return {k: v for k, v in ki.items() if v}

    @staticmethod
    def _kor_commitok(repo: snapshot.Repo, kor: str) -> list:
        try:
            return repo.kor_commitok(kor)
        except snapshot.SnapshotError:
            return []

    def _fuzet_visszavonas(self, repo: snapshot.Repo, sha: str | None, kor: str | None, kor_commitok: list | None = None) -> None:
        """L20 (C21): a visszavont füzet-tételek hatása a lánc állapotára (`core/fuzet.py`); a hiba a szöveg-visszavonást nem viszi el."""
        try:
            shak = [sha] if sha else [c.sha for c in (kor_commitok if kor_commitok is not None else repo.log(run=kor))]
            fuzet.visszavonas_utan(self.cfg, shak, kor)
        except Exception as e:  # noqa: BLE001
            print(f"[visszavonás] a füzetlánc állapota nem frissült: {e}", file=sys.stderr, flush=True)

    def _index_jelez(self, utak) -> None:
        """A core saját (visszavonás, visszaállítás) írásának változott útjai az indexnek, a figyelő megvárása nélkül."""
        self.index.jelez([self.index.lemez_ut(u) for u in utak])

    @staticmethod
    def _visszavont_forrasok(repo: snapshot.Repo, sha: str | None, kor_commitok: list | None) -> list[str | None]:
        """A visszavonandó commit(ok) `Mos-Forras` trailere (a tracker funkciónkénti mérése, C27); hiba esetén üres.
        `kor_commitok`: a kör (feladatra szűrt) commitjai, ha körre szól a visszavonás."""
        try:
            if kor_commitok is not None:
                return [c.trailers.get("Mos-Forras") for c in kor_commitok]
            ki = repo.git("log", "-1", "--format=%(trailers:only,unfold)", sha).stdout
            return [snapshot._parse_trailers(ki).get("Mos-Forras")]
        except snapshot.SnapshotError:
            return []


def regiszter_epit() -> utvonalak.Regiszter:
    """A core MINDEN végpontjának regisztere `App` és szerver nélkül (a kezelők nem futnak): az `App.__init__` ezt használja,
    és ebből olvas az útvonal-tábla teszt (`test_utvonalak`) és a dokumentáció-teszt (`test_dokumentacio`) is (T083).
    Új végpont-modul az `UTVONAL_MODULOK`-ba kerül; a vezérlő végpontjait a `tasks.utvonalak` regisztrálja."""
    r = utvonalak.Regiszter()
    _alap_utvonalak(r)
    for modul in UTVONAL_MODULOK:
        modul.utvonalak(r)
    return r


def _alap_utvonalak(r: utvonalak.Regiszter) -> None:
    """Ami az `App`-é és a szerver infrastruktúrájáé: életjel, állapot, pillanatkép-napló és -visszavonás, WebSocket."""
    r.get("/health", lambda k: {"ok": True})
    r.get("/api/allapot", lambda k: {
        "ok": True, "verzio": __version__, "pid": os.getpid(), "rss_mb": rss_mb(), "media_token": k.app.media_token,
        "feladatsor": {"aktiv": k.app.queue.active(), "lezarva": k.app.queue.closed},
        "tarolok": sorted(frame.live_repos(k.app.cfg))})

    def naplo(k):
        n = k.egesz("n", 20, 1, 500)
        repo = k.app.repo(k.m.group(1))
        return {"commitok": [{"sha": c.sha, "datum": c.date, "targy": c.subject, "trailerek": c.trailers}
                             for c in repo.log(n, run=k.q.get("kor") or None)]}
    r.get(re.compile(r"/api/pillanat/(\w+)/naplo"), naplo)
    r.post(re.compile(r"/api/pillanat/(\w+)/visszavonas"), lambda k: k.app.undo(k.m.group(1), k.torzs()))

    def ws(k):
        k.h._websocket()
        return utvonalak.KESZ
    r.get("/ws", ws)


def _handler(app: App):
    idokorlat = float(app.cfg.section("core").get("kezelo_idokorlat_mp", KEZELO_IDOKORLAT_MP))

    class Kezelo(BaseHTTPRequestHandler):
        server_version = "ManifoldCore"
        timeout = idokorlat     # T003: egy félbehagyott törzs vagy fejléc nem tarthatja korlát nélkül a kezelőszálat

        def log_message(self, *args):  # a stdout a kézfogásé
            pass

        # ---------------------------------------------------- segédek

        def _gazda_ok(self) -> bool:
            return self.headers.get("Host", "").rsplit(":", 1)[0] in HELYI_GAZDAK

        def _kuld(self, kod: int, torzs: bytes, tipus: str, fejlecek: dict | None = None) -> None:
            self.send_response(kod)
            self.send_header("Content-Type", tipus)
            self.send_header("Content-Length", str(len(torzs)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (fejlecek or {}).items():
                self.send_header(k, v)
            self.send_header("X-Content-Type-Options", "nosniff")
            utvonalak.biztonsagi_fejlecek(self)         # T103: keretezés ellen, minden válaszon
            self.send_header("Connection", "close")     # nincs keep-alive: a leállás nem vár tétlen kapcsolatra
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(torzs)

        def _json(self, kod: int, obj) -> None:
            self._kuld(kod, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def _torzs(self) -> dict:
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError as exc:
                raise HttpError(400, "hibás Content-Length", kod="http.content_length") from exc
            if n < 0:                   # L2: a negatív hossz a kapcsolat végéig olvasna
                raise HttpError(400, "hibás Content-Length", kod="http.content_length")
            if n > MAX_TORZS:
                raise HttpError(413, "túl nagy kérés", kod="http.tul_nagy")
            try:
                d = json.loads(self.rfile.read(n) or b"{}")
            except ValueError as exc:
                raise HttpError(400, "hibás JSON", kod="http.json_hibas") from exc
            if not isinstance(d, dict):
                raise HttpError(400, "JSON-objektum kell", kod="http.json_objektum")
            return d

        @staticmethod
        def _egesz(q: dict, kulcs: str, alap: int | None, also: int, felso: int) -> int | None:
            """Egy egész szám-paraméter a lekérdezésből (L2): hiányzik → `alap`; hibás vagy tartományon kívüli → 400."""
            v = q.get(kulcs)
            if v is None or v == "":
                return alap
            try:
                n = int(v)
            except ValueError:
                raise HttpError(400, f"hibás {kulcs}: egész szám kell", kod="http.egesz_szam", param={"kulcs": kulcs}) from None
            if not also <= n <= felso:
                raise HttpError(400, f"hibás {kulcs}: {also} és {felso} között kell lennie", kod="http.tartomany", param={"kulcs": kulcs, "also": also, "felso": felso})
            return n

        def _hitelesit(self, ut: str) -> None:
            """Az `X-Manifold` fejléc: a felületi API-titok (35. döntés: teljes jogú), vagy egy futó lépés tokenje (T137, 28(a)). A lépés-token
            az olvasókat és a `lepes_kapu.ENGEDELYEZETT` végpontokat éri el, minden mást (a szerkesztői írást is) nem; ismeretlen vagy lejárt
            érték 403."""
            kapott = self.headers.get("X-Manifold")
            if app.titok_ok(kapott):
                return
            if app.queue.lepes_feladat(kapott) is None:
                raise HttpError(403, "hiányzó vagy hibás X-Manifold fejléc", kod="http.x_manifold")
            if not lepes_kapu.engedelyezett(self.command, ut):
                raise HttpError(403, "lépés-folyamat ezt a végpontot nem hívhatja: a vaultba a gépi-írás szolgáltatáson át ír (28(a))", kod="http.lepes_tiltott")

        def _kezel(self, fn) -> None:
            if not self._gazda_ok():
                return self._kuld(403, b"This host is not allowed.", "text/plain; charset=utf-8")
            url = urllib.parse.urlsplit(self.path)
            ut = urllib.parse.unquote(url.path)
            q = {k: v[-1] for k, v in urllib.parse.parse_qs(url.query).items()}
            try:
                if ut.startswith("/api/") or ut == "/health":
                    self._hitelesit(ut)
                return fn(ut, q)
            except HttpError as e:
                if e.kod:
                    self._json(e.code, e.torzs())
                else:
                    alap = {404: "http.nem_talalhato", 409: "http.utkozes", 503: "http.nem_elerheto"}
                    self._json(e.code, hiba_torzs(e, alap_kod=alap.get(e.code, "http.keres_hibas"), **e.data))
            except atnevezes.Hiba as e:
                kod = next((f"atnevezes.{nev}" for mezo, nev in (
                    ("naplo", "naplo_all"), ("foglalt", "foglalt"), ("nyitott", "mentetlen"),
                    ("valtozott", "valtozott"), ("blokkolok", "blokkolt"), ("proba_hibak", "visszaallitva"))
                    if e.adat.get(mezo)), "atnevezes.sikertelen")
                self._json(e.kod, hiba_torzs(e, alap_kod=kod, **e.adat))
            except vaultio.NemElerheto as e:
                self._json(503, hiba_torzs(e, alap_kod=e.kod, lemez_hiba=True, vault_elerheto=False))
            except vaultio.NotFound as e:
                self._json(404, hiba_torzs(e, alap_kod="http.nem_talalhato"))
            except (vaultio.Invalid, tasks.Invalid, felulet.Hibas) as e:
                self._json(400, hiba_torzs(e, alap_kod="http.keres_hibas"))
            except vaultio.Conflict as e:
                self._json(409, hiba_torzs(e, alap_kod="http.utkozes", utkozes=True, **e.data))
            except (tasks.Closed, indexelo.NemKesz) as e:
                kod = "core.leall" if isinstance(e, tasks.Closed) else "index.nem_kesz"
                self._json(503, hiba_torzs(e, alap_kod=kod))
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                pass            # a kliens elment vagy elakadt (socket-időkorlát): nincs kinek választ küldeni
            except OSError as e:
                # T175: a lemezhiba (EACCES, ENOSPC, EFBIG, a kihúzott kötet…) magyarul, abszolút út nélkül, 507/503-mal
                kod, adat = vaultio.lemez_hiba(e, app.cfg.path("vault"))
                print(f"[core] lemezhiba: {self.command} {ut}: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
                self._json(kod, adat)
            except Exception as e:  # noqa: BLE001 — a szerver nem halhat meg egy kéréstől
                print(f"[core] {self.command} {ut}: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
                self._json(500, hiba_torzs(e, alap_kod="http.belso_hiba"))

        # ---------------------------------------------------- GET

        def do_GET(self):
            self._kezel(self._get)

        def do_HEAD(self):
            self._kezel(self._get)

        def _get(self, ut: str, q: dict):
            if self._utvonal("GET", ut, q):
                return
            if ut.startswith("/api/"):
                raise HttpError(404, "nincs ilyen végpont", kod="http.nincs_vegpont")
            return self._statikus(ut)

        def _utvonal(self, metodus: str, ut: str, q: dict, torzs: dict | None = None) -> bool:
            """A regiszterben talált kezelő futtatása (C11a); → igaz, ha volt ilyen végpont."""
            t = app.utvonalak.keres(metodus, ut)
            if t is None:
                return False
            kezelo, m = t
            modulkapu.ellenoriz(app.cfg, ut)
            eredmeny = kezelo(utvonalak.Kerees(app, self, ut, q, m, torzs))
            if eredmeny is utvonalak.KESZ:
                return True
            if isinstance(eredmeny, utvonalak.Etagos):
                if eredmeny.etag in (self.headers.get("If-None-Match") or ""):
                    self._kuld(304, b"", "application/json; charset=utf-8", {"ETag": eredmeny.etag})
                else:
                    self._kuld(200, eredmeny.torzs, "application/json; charset=utf-8", {"ETag": eredmeny.etag})
            elif isinstance(eredmeny, utvonalak.Valasz):
                self._json(eredmeny.kod, eredmeny.obj)
            else:
                self._json(200, eredmeny)
            return True

        def _statikus(self, ut: str):
            dist = app.cfg.path("app_dist")
            rel = ut.lstrip("/") or "index.html"
            if dist.is_dir():
                p = (dist / rel).resolve()
                if dist.resolve() in p.parents and p.is_file() and not any(s.startswith(".") for s in Path(rel).parts):
                    tipus = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
                    if tipus.startswith("text/") or tipus in ("application/javascript", "application/json"):
                        tipus += "; charset=utf-8"
                    return self._kuld(200, p.read_bytes(), tipus)
            if ut == "/":
                return self._kuld(200, URES_LAP, "text/html; charset=utf-8")
            raise HttpError(404, "nincs ilyen", kod="http.nincs_ilyen")

        # ---------------------------------------------------- POST / PUT

        def do_POST(self):
            self._kezel(self._post)

        def do_PUT(self):
            self._kezel(self._put)

        def _post(self, ut: str, q: dict):
            if not ut.startswith("/api/"):
                raise HttpError(404, "nincs ilyen végpont", kod="http.nincs_vegpont")
            body = self._torzs()        # a törzs a végpont keresése előtt olvasódik: a hibás törzs 400, nem 404
            if not self._utvonal("POST", ut, q, body):
                raise HttpError(404, "nincs ilyen végpont", kod="http.nincs_vegpont")

        def _put(self, ut: str, q: dict):
            if not self._utvonal("PUT", ut, q):
                raise HttpError(404, "nincs ilyen végpont", kod="http.nincs_vegpont")

        # ---------------------------------------------------- WebSocket

        def _websocket(self):
            self.protocol_version = "HTTP/1.1"          # a WS-kliens a hibaválaszt is HTTP/1.1-ként várja
            h = self.headers
            if "websocket" not in (h.get("Upgrade") or "").lower() or "upgrade" not in (h.get("Connection") or "").lower():
                raise HttpError(400, "WebSocket-kézfogás kell", kod="ws.kezfogas_kell")
            origin = h.get("Origin")
            sajat = {f"http://{g}:{app.port}" for g in HELYI_GAZDAK}
            if origin is not None and origin not in sajat:
                raise HttpError(403, "idegen origin", kod="ws.origin")
            key = h.get("Sec-WebSocket-Key")
            if not key or h.get("Sec-WebSocket-Version") != "13":
                raise HttpError(400, "hibás WebSocket-kézfogás", kod="ws.kezfogas_hibas")
            # a böngésző WS-e nem küldhet fejlécet: a titok az alprotokollban megy (`mos.<titok>`), a választottat vissza kell küldeni
            alprotokoll = next((p.strip() for p in (h.get("Sec-WebSocket-Protocol") or "").split(",")
                                if p.strip().startswith("mos.") and app.titok_ok(p.strip()[4:])), None)
            if alprotokoll is None:
                raise HttpError(403, "hiányzó vagy hibás WebSocket-titok", kod="ws.titok")
            conn = websocket.Connection(self.connection, self.rfile, self.wfile)
            sub = app.bus.subscribe()       # az `add_ws` ELŐTT: a közben küldött `indulasi_uzenet` sem vész el
            if not app.add_ws(conn):
                sub.close()
                raise HttpError(503, "a core leáll", kod="core.leall")
            self.connection.settimeout(None)     # a WS hosszan tétlen lehet; a lezárást a `Connection.close()` shutdown-ja végzi
            self.wfile.write(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                              f"Sec-WebSocket-Accept: {websocket.accept_key(key)}\r\n"
                              f"Sec-WebSocket-Protocol: {alprotokoll}\r\n\r\n").encode())
            self.close_connection = True

            def kuldo():
                try:
                    conn.send_json({"tipus": "hello", "verzio": __version__, "media_token": app.media_token,
                                    "figyelmeztetesek": app.indulasi_uzenetek_atad()})
                    while not conn.closed:
                        e = sub.get(timeout=0.5)
                        if e is not None:
                            conn.send_json(e)
                except (OSError, ConnectionError):
                    conn.closed = True

            t = threading.Thread(target=kuldo, name="ws-kuldo", daemon=True)
            t.start()
            try:
                conn.serve_incoming(lambda s: app.ws_uzenet(conn, s))
            finally:
                conn.closed = True
                sub.close()
                app.drop_ws(conn)
                t.join(timeout=2)

    return Kezelo


class Szerver(ThreadingHTTPServer):
    """A HTTP-szerver. `request_queue_size`: a stdlib alapértéke 5, de minden kérés új kapcsolat (nincs keep-alive), így
    roham (index-építés, sok egyidejű kérés) alatt a kernel RST-vel visszautasított (T021). A kezelőszálak `daemon`-ok
    és a szerver nem join-ol rájuk (`block_on_close = False`): a folyamatban lévő kéréseket saját számláló követi, és
    `varj_kerelsekre` KORLÁTOSAN várja meg (T003) — egy elakadt kapcsolat nem tarthatja vissza a leállást."""
    daemon_threads = True
    block_on_close = False
    request_queue_size = 128

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._folyamatban = 0
        self._fcond = threading.Condition()

    def process_request(self, request, client_address):
        with self._fcond:               # a kapcsolat az elfogadásakor számít, nem a szál indulásakor
            self._folyamatban += 1
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._kesz()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._kesz()

    def _kesz(self) -> None:
        with self._fcond:
            self._folyamatban -= 1
            self._fcond.notify_all()

    def folyamatban(self) -> int:
        with self._fcond:
            return self._folyamatban

    def varj_kerelsekre(self, timeout: float) -> bool:
        """Megvárja a folyamatban lévő kéréseket legfeljebb `timeout` másodpercig; igaz, ha mind véget ért."""
        with self._fcond:
            return self._fcond.wait_for(lambda: self._folyamatban == 0, timeout)


def vault_kanonikus(vault: Path) -> str | None:
    """A vault kanonikus útja (`fcntl F_GETPATH` a mappa leíróján: valódi kis-nagybetű, feloldott symlink és `..`); None, ha a
    mappa nem nyitható vagy a rendszer nem adja meg."""
    try:
        fd = os.open(vault, os.O_RDONLY)
    except OSError:
        return None
    try:
        nyers = fcntl.fcntl(fd, fcntl.F_GETPATH, bytes(1024)).split(b"\0", 1)[0]
        return os.fsdecode(nyers) or None
    except (OSError, AttributeError, ValueError):
        return None
    finally:
        os.close(fd)


def vault_kulcs(vault: Path) -> str:
    """A vault-őr kulcsa (F3-DESIGN §4): `sha256(F_GETPATH(vault))[:32]` — ugyanaz minden útírásra; tartalék a mappa
    `st_dev:st_ino`-ja, végül (nem létező mappa) a normalizált abszolút út."""
    kanonikus = vault_kanonikus(vault)
    if kanonikus:
        alap = kanonikus
    else:
        try:
            st = os.stat(vault)
            alap = f"{st.st_dev}:{st.st_ino}"
        except OSError:
            alap = os.path.normpath(os.path.abspath(vault))
    return hashlib.sha256(alap.encode("utf-8", "surrogateescape")).hexdigest()[:32]


def vault_or_ut(cfg: config.Config) -> Path:
    """A vault-őr zárfájlja: `{install_run}/vaults/<k>.lock` (gépenként, telepítésenként egy; a `visszaallitas` is vizsgálja)."""
    return cfg.path("install_run") / "vaults" / f"{vault_kulcs(cfg.path('vault'))}.lock"


def _zar_tartalom(cfg: config.Config) -> str:
    return f"pid {os.getpid()} · {cfg.workspace_id or '-'} · {cfg.path('vault')}"


def _zar_tulajdonos(tartalom: str) -> dict:
    """A zárfájl tartalmából a `foglalt` kézfogás: `pid <pid> · <id | -> · <vault>` (F3), vagy a v2-alak `pid <pid> · <vault>`."""
    pid_s, _, maradek = tartalom.strip().partition(" · ")
    kozep, _, vault = maradek.partition(" · ")
    if not (kozep == "-" or config.ID_MINTA.match(kozep)):
        vault = maradek                                   # a v2-alak: a vault-út maga is tartalmazhat ` · `-t
    try:
        pid = int(pid_s.removeprefix("pid ").strip())
    except ValueError:
        pid = None
    return {"foglalt": True, "pid": pid, "vault": vault or None}


def _zar_fog(ut: Path, tartalom: str):
    """Kizáró, nem váró `flock` egy zárfájlon. → (nyitott fájl, None), vagy (None, a zárat tartó core adatai)."""
    ut.parent.mkdir(parents=True, exist_ok=True)
    fh = open(ut, "a+")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        fh.seek(0)
        szoveg = fh.read()
        fh.close()
        return None, _zar_tulajdonos(szoveg)
    fh.seek(0)
    fh.truncate()
    fh.write(tartalom)
    fh.flush()
    return fh, None


def zar_foglalt(ut: Path) -> dict | None:
    """Egy zárfájl vizsgálata CSAK OLVASVA (`O_RDONLY`, `LOCK_SH|LOCK_NB`, azonnal elengedve): a tartó core adatai, ha foglalt;
    None, ha szabad vagy nem létezik. Idegen telepítés zárára (`idegen_zarak`) és a `visszaallitas`-ra: semmit nem hoz létre."""
    try:
        fd = os.open(ut, os.O_RDONLY)
    except OSError:
        return None
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            try:
                szoveg = os.read(fd, 8192).decode("utf-8", "replace")
            except OSError:
                szoveg = ""
            return _zar_tulajdonos(szoveg)
        except OSError:
            return None
        fcntl.flock(fd, fcntl.LOCK_UN)
        return None
    finally:
        os.close(fd)


def _core_zar(cfg: config.Config):
    """Az egypéldányos zár (T027): a `{run}/core.lock` a core teljes élettartamára. → (fájl, None) vagy (None, a zárat tartó
    core adatai). Termékben a `{run}` a vault `.manifold/var`-ja alatt van: egy nem csatolt kötet helyére (`/Volumes/X`) nem
    készül mappa (`vault_nem_elerheto`)."""
    vault = cfg.path("vault")
    if cfg.elrendezes == "termek" and not vault.is_dir():
        raise config.ConfigError(f"a munkatér mappája nem érhető el: {vault}", kod="vault_nem_elerheto",
                                 param={"vault": str(vault)})
    return _zar_fog(cfg.path("run") / "core.lock", _zar_tartalom(cfg))


def _vault_or(cfg: config.Config):
    """A vault-őr (F3-DESIGN §4): telepítésenként egy core egy vaulton, az állapot helyétől (`{run}`) függetlenül."""
    return _zar_fog(vault_or_ut(cfg), _zar_tartalom(cfg))


def _idegen_zarak(cfg: config.Config, sajat: list[Path]) -> dict | None:
    """A `[hordozhato] idegen_zarak` (más telepítések `core.lock`-jai) csak olvasva: az első foglalt tulajdonosa, vagy None.
    A saját zárfájl (ha a lista véletlenül megnevezi) kimarad."""
    for z in cfg.section("hordozhato").get("idegen_zarak") or []:
        ut = Path(os.path.expanduser(str(z)))
        if not ut.is_absolute():
            print(f"[core] idegen_zarak: nem abszolút út, kihagyva: {z}", file=sys.stderr, flush=True)
            continue
        if any(_azonos_fajl(ut, s) for s in sajat):
            continue
        foglalt = zar_foglalt(ut)
        if foglalt:
            return foglalt
    return None


def _azonos_fajl(a: Path, b: Path) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def _zarak(cfg: config.Config):
    """`core.lock` → vault-őr → idegen zárak (F3-DESIGN §4). → (a fogott zárfájlok, None), vagy ([], a tartó adatai): foglaltnál
    a már fogottak elengedve. Konfigurációs hibánál (`ConfigError`) is elenged, és továbbdobja."""
    fogott: list = []
    try:
        for fog in (_core_zar, _vault_or):
            fh, foglalt = fog(cfg)
            if fh is None:
                _elenged(fogott)
                return [], foglalt
            fogott.append(fh)
        foglalt = _idegen_zarak(cfg, [Path(fh.name) for fh in fogott])
        if foglalt:
            _elenged(fogott)
            return [], foglalt
    except BaseException:
        _elenged(fogott)
        raise
    return fogott, None


def _elenged(zarak: list) -> None:
    for fh in reversed(zarak):
        try:
            fh.close()                  # a `flock` a fájl lezárásával szabadul
        except OSError:
            pass
    zarak.clear()


def _munkater_nyit(cfg: config.Config) -> tuple[config.Config, list[str]]:
    """Termékben a `workspace.nyit` (formátum, áthelyezés, másolat; a zárak UTÁN és az `App()` helyreállítása ELŐTT, §3.4).
    Ha a munkatér új azonosítót kapott (másolat), a konfiguráció a `workspace.ujratolt`-tal újratöltődik, és a gyökerek az új
    feloldásra rögzülnek (a `python -m core start` rögzítése szerint). Hordozható elrendezésben nincs teendő."""
    if cfg.elrendezes != "termek":
        return cfg, []
    from . import gyokerek, workspace       # lusta: a munkatér-modul csak termékben kell
    uzenetek = [str(u) for u in (workspace.nyit(cfg) or [])]
    uj = workspace.ujratolt(cfg, os.environ)
    if uj is not None:
        gyokerek.rogzit(uj, os.environ)
        gyokerek.biztosit_mappak(uj)
        os.environ.update(gyokerek.folyamat_env(uj))
        cfg = uj
    return cfg, uzenetek


def _foglalt_kezfogas(out, foglalt: dict) -> int:
    """A `foglalt` kézfogás-sor (T027, változatlan alak) és a 75-ös kilépési kód."""
    out.write(json.dumps(foglalt) + "\n")
    out.flush()
    print(f"[core] másik core fut ugyanezen a vaulton (pid {foglalt['pid']}, {foglalt['vault']}): ez a példány kilép",
          file=sys.stderr, flush=True)
    return CORE_ZAR_KILEPES


def _hiba_kezfogas(out, e: Exception) -> int:
    """A konfigurációs hiba első stdout-sora (`{"hiba": kod, "param": …, "uzenet": …}`) és a 78-as kilépési kód."""
    kod = getattr(e, "kod", None) or "konfig_hiba"
    param = json_param(getattr(e, "param", None))
    uzenet = angol_uzenet(kod, param, "Manifold could not start. Check its configuration.")
    out.write(json.dumps({"hiba": kod, "param": param, "uzenet": uzenet}, ensure_ascii=False) + "\n")
    out.flush()
    print(f"[core] a core nem indul ({kod}): {e}", file=sys.stderr, flush=True)
    return KONFIG_HIBA_KILEPES


def _csendben(fn, *a, **k):
    """Egy karbantartó hívás, amelynek a hibája nem viheti el a core-t (csak a naplóba kerül)."""
    try:
        return fn(*a, **k)
    except Exception as e:  # noqa: BLE001
        print(f"[core] {getattr(fn, '__name__', fn)}: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        return None


def start(cfg: config.Config | None = None, stdin=None, out=None, start_delay: float | None = None,
          api_titok: str | None = None) -> int:
    """A core futása a stdin lezárulásáig. `stdin`/`out`: a tesztek csöve (alapból a folyamat saját). Egypéldányos
    (T027, F3-DESIGN §4): foglalt `core.lock`, vault-őr vagy idegen zár esetén az első stdout-sor a `foglalt` kézfogás, a
    kilépési kód 75; konfigurációs hibánál a `{"hiba": kod}` sor, 78. `api_titok`: a `python -m core start` a
    `MOS_API_TITOK`-ot kiveszi a környezetből (a gyermekfolyamatok ne örököljék), és így adja át."""
    out = out or sys.stdout
    zarak: list = []
    try:
        cfg = cfg or config.load()
        zarak, foglalt = _zarak(cfg)
        if foglalt:
            return _foglalt_kezfogas(out, foglalt)
        regi_run = cfg.path("run")
        cfg, uzenetek = _munkater_nyit(cfg)
        if cfg.path("run") != regi_run:      # az új azonosító más állapot-helyet adott (regiszter): ott is egy core
            fh, foglalt = _core_zar(cfg)
            if fh is None:
                _elenged(zarak)
                return _foglalt_kezfogas(out, foglalt)
            zarak.append(fh)
    except Exception as e:  # noqa: BLE001 — csak a `kod`-ot hordozó (konfigurációs, munkatér-) hiba sora; a többi traceback
        _elenged(zarak)
        if not isinstance(e, config.ConfigError) and not isinstance(getattr(e, "kod", None), str):
            raise
        return _hiba_kezfogas(out, e)
    try:
        corenaplo.indit(cfg)    # C29.7b (T031): forgatott core.log + faulthandler — csak a core.lock birtokosa, fő szálon
        return _fut(cfg, stdin or sys.stdin.buffer, out, start_delay, api_titok, uzenetek=uzenetek)
    finally:
        _elenged(zarak)


def _fut(cfg: config.Config, stdin, out, start_delay: float | None, api_titok: str | None = None,
         uzenetek: list[str] | None = None) -> int:
    app = App(cfg, start_delay=start_delay, api_titok=api_titok)
    app.indulasi_uzenetek += list(uzenetek or [])     # a `workspace.nyit` üzenetei (áthelyezés, másolat): az első `hello` viszi
    # a `MOS_CORE_PORT` felülírja a konfigot: a héj a core újraindításakor a régi porton indítja (a lap origin-je marad, C29.7b)
    httpd = Szerver(("127.0.0.1", int(os.environ.get("MOS_CORE_PORT") or cfg.section("core").get("port", 0))), _handler(app))
    app.port = httpd.server_address[1]
    # A-javító (2026-10-14, D8): a kézfogás előtt csak a gyors, naplóvezérelt helyreállítás (a felület első mentése előtt le
    # kell zárulnia) és az olcsó, időzítővel induló szolgálatok. A vault bejárása (ideiglenes fájlok), a futó mag
    # ujjlenyomata és az árva lépések leállítása a kézfogás UTÁN, háttérszálon (`App.indulasi_hatter`, `Queue._arva_szal`)
    app.indulas(tmp_takarit=False)  # elakadt index.lock, megszakadt átnevezés/gépi írás — az index előtt, a core.lock birtokában
    app.index.indit()           # a lexikai index a megnyitáskor indul, háttérszálon (C06-döntés)
    app.naptar.indit()          # C29: az első szinkron az indulási késleltetés (D8) után, háttérszálon
    app.asszisztens.indit()     # C30a: a higiénia-riport az indulási késleltetés (D8) után, tétlenségben
    app.fuzet_figyelo.indit()   # C21: a füzetmappa figyelése — 80(a): feltétel nélkül kikapcsolva (no-op; a füzetlánc csak kézzel indul)
    app.mentes_utemezo.indit()  # 34. döntés: időzített bundle tétlenségben, gépi kör végén
    app.teljes_mentes_figyelo.indit()  # CX-012: a mentési lemez felismerése (alapból ki; bekapcsolva is csak a D8-szünet után)
    app.kartya_szinkron.indit()  # C23b: a kártyamappa szinkronja (olvas; a tanulas.sqlite-ot írja)
    app.automatika.indit()      # C23b: a közös automatika-ütemező (az első ütem a D8-szünet után)
    # C29.8: a kapu jeleit (sysctl, ioreg) külön szál méri — az első mérést a kézfogás nem várja meg (addig a jel elavult: az
    # automatikus munka nem indul, és a kapu sem mér a sor zárja alatt)
    app.jelek.indit(elso_varakozas_mp=0)
    # C33 (T177): a kicsinyített képek gyorsítótárának takarítása a D8-szünet után, háttérszálon (csak a `{vault_kepek}` alatt)
    kepek_takaritas = threading.Timer(app.indulasi_szunet, lambda: _csendben(kepek.takarit, cfg))
    kepek_takaritas.daemon = True
    kepek_takaritas.start()

    leallas = {"indult": False, "kenyszer": False}
    leallas_zar = threading.Lock()
    fokozas_mp = float(cfg.section("core").get("leallas_fokozas_mp", LEALLAS_FOKOZAS_MP))
    mentes_zar = threading.Lock()
    mentes_allapot = {"indult": False}
    mentes_vege = threading.Event()

    def kilepesi_mentes(idokeret: float | None) -> None:
        """H2/K44: a belső lemezes mentés kilépéskor — egyszer: a fő szál vagy a kényszerág futtatja, amelyik előbb ér oda."""
        with mentes_zar:
            if mentes_allapot["indult"]:
                return
            mentes_allapot["indult"] = True
        try:
            _csendben(mentes.kilepeskor, cfg, idokeret=idokeret)
        finally:
            mentes_vege.set()

    def kenyszer_kilep() -> None:
        """A kényszerág vége (SIGTERM után `KENYSZER_MP`): a folyamat kilép — de előbb legfeljebb `KOR_ZAR_VARAKOZAS_MP`-ig
        várja a kör-zárat, hogy egy futó átnevezést vagy gépi írást (3–8 s) ne vágjon el a szándéknapló nélkül maradó
        részekre (a napló a következő indulásnál amúgy is visszaállít, H3); utána a K44 szerinti `KENYSZER_MENTES_MP`-es
        bundle-próba, ha a rendezett ág még nem jutott el hozzá (az `os._exit` előtt)."""
        t0 = time.monotonic()
        while time.monotonic() - t0 < KOR_ZAR_VARAKOZAS_MP:
            try:
                with frame.run_lock(cfg, wait=False):
                    break
            except frame.Busy:
                time.sleep(0.1)
        try:
            kilepesi_mentes(KENYSZER_MENTES_MP)
            mentes_vege.wait(KENYSZER_MENTES_MP + 0.5)     # ha a fő szál már menti: a saját 1 s-os keretét kivárjuk
        finally:
            os._exit(1)

    def leallit(kenyszer: bool) -> None:
        """A rendezett leállás: új feladat nincs, WS zár, a szerver a folyamatban lévő kérések (mentés, átnevezés)
        végén áll le. A stdin lezárásakor a futó feladat a tétel végén áll meg — de ha `leallas_fokozas_mp` (20 s) után
        is fut (pl. egy nem kulturáltan leállítható mentés, vagy egy elakadt lépés), azonnal leáll. SIGTERM-re (`kenyszer`,
        a második ⌘Q, H6) a lépések és a modell-worker azonnal, és `KENYSZER_MP` után a folyamat mindenképp kilép. A SIGTERM
        a már futó rendezett leállást is fokozza (T003): élesíti a végső időzítőt és azonnal leállítja a futó lépéseket.
        Minden komponens leállítása védett (`_csendben`): egy hibája nem akaszthatja el a `httpd.shutdown()`-t, és vele a
        kilépést és a kilépési mentést."""
        with leallas_zar:
            fokozas = leallas["indult"] and kenyszer and not leallas["kenyszer"]
            if leallas["indult"] and not fokozas:
                return
            leallas.update(indult=True, kenyszer=leallas["kenyszer"] or kenyszer)
        if kenyszer:
            vegso = threading.Timer(KENYSZER_MP, kenyszer_kilep)
            vegso.daemon = True
            vegso.start()
        if fokozas:                 # a rendezett leállás szála a lépések végét várja; ez a szál azonnal állítja le őket
            _csendben(app.queue.shutdown, timeout=8, azonnal=True)
            _csendben(app.worker.leallit, azonnal=True)
            return
        try:
            if kenyszer:
                _csendben(app.queue.shutdown, timeout=8, azonnal=True)
            elif _csendben(app.queue.shutdown, timeout=fokozas_mp) is not True:
                print(f"[core] leállás: a futó feladat {fokozas_mp:g} s alatt sem állt meg — azonnali leállítás",
                      file=sys.stderr, flush=True)
                _csendben(app.queue.shutdown, timeout=8, azonnal=True)
            _csendben(app.close_ws)
            if getattr(app, "kviz_api", None) is not None:
                # C22b: a késleltetett `## Kitöltések`-írás most (a kényszerágon elmarad)
                _csendben(app.kviz_api.leallit, irjon=not kenyszer)
            _csendben(app.cpp.leallit)      # C36a: a futó ellenőrzés megszakad, nem marad árva clang++ vagy teszt-folyamat
            _csendben(app.mentes_utemezo.leallit)
            _csendben(app.teljes_mentes_figyelo.leallit)
            _csendben(app.jelek.leallit)
            # a worker a folyó hívás végén kiürít és kilép; a kényszerágon azonnal (SIGTERM, 2 s után SIGKILL)
            _csendben(app.worker.leallit, azonnal=kenyszer)
            for komponens in (app.naptar, app.automatika, app.kartya_szinkron, app.asszisztens, app.fuzet_figyelo,
                              app.index):
                _csendben(komponens.leallit)
            kepek_takaritas.cancel()
            if not kenyszer:            # T177: a rendezett leálláskor is (időkerettel: a leállás nem várhat egy nagy gyorsítótárra)
                _csendben(kepek.takarit, cfg, hatarido_mp=1.0)
        finally:
            httpd.shutdown()

    def figyel():
        # nyers fd-olvasás: a pufferelt olvasó zárját a SIGTERM utáni leálláskor a démonszál fogná (Fatal error)
        fd = stdin.fileno()
        while True:
            try:
                if not os.read(fd, 4096):
                    break
            except OSError:
                break
        leallit(False)              # a stdin lezárult (a héj kilépett vagy leállít)

    def sigterm(signum, keret):
        signal.signal(signal.SIGTERM, signal.SIG_DFL)      # a második SIGTERM már azonnal öl
        threading.Thread(target=leallit, args=(True,), name="sigterm-leallas", daemon=True).start()

    if threading.current_thread() is threading.main_thread():  # a tesztek szálon indítják: ott nincs jelkezelő
        signal.signal(signal.SIGTERM, sigterm)      # a kézfogás ELŐTT: a héj a kézfogás után bármikor küldhet SIGTERM-et
    # F3-DESIGN §2.6: a kézfogás additív mezői — a héj a vault kötetének lecsatolását figyeli (nem a kódfáét)
    _csendben(munkater_futo.bejelent, cfg, app.port)
    out.write(json.dumps({"port": app.port, "pid": os.getpid(), "titok": app.api_titok,
                          "vault": vault_kanonikus(cfg.path("vault")) or str(cfg.path("vault")),
                          "munkater_id": cfg.workspace_id, "elrendezes": cfg.elrendezes}, ensure_ascii=False) + "\n")
    out.flush()
    app.indulasi_hatter()       # az ideiglenes fájlok takarítása; a futó mag ujjlenyomata (CX-001)
    threading.Thread(target=figyel, daemon=True).start()
    try:
        httpd.serve_forever()
    finally:
        _csendben(munkater_futo.elfelejt, cfg)
        _csendben(httpd.server_close)   # a figyelő port zárul; a folyamatban lévő kéréseket KORLÁTOSAN várjuk meg (T003)
        _csendben(httpd.varj_kerelsekre, 5 if leallas["kenyszer"] else KEREL_VARAKOZAS_MP)
        _csendben(app.queue.close, timeout=2)
        for komponens in (app.mentes_utemezo, app.teljes_mentes_figyelo, app.jelek, app.worker, app.naptar,
                          app.automatika, app.kartya_szinkron, app.asszisztens, app.fuzet_figyelo, app.index):
            _csendben(komponens.leallit)
        if app.indulas_szal is not None:    # a még futó indulási helyreállítás a kör-zárat foghatja: a mentés előtt kivárjuk
            app.indulas_szal.join(2 if leallas["kenyszer"] else INDULAS_VARAKOZAS_MP)
    if leallas["indult"]:
        # H2: a belső lemezre, ha a HEAD változott; a kényszerágon (K44) legfeljebb `KENYSZER_MENTES_MP` időkerettel
        kilepesi_mentes(KENYSZER_MENTES_MP if leallas["kenyszer"] else None)
    return 0
