"""A modell-worker kliense (stdlib urllib) a core-nak, a CLI-nek és a láncoknak. Gépi tanulás nélkül.

A worker címe: `MOS_WORKER_URL` (a feladatsor adja a lépéseknek), különben a gépszintű `{install_run}/worker.pid` (F3-DESIGN
§4: egy telepítésen egy worker, a munkaterek core-jai közösen használják). Workert csak a core és a CLI indít (`Folyamat`), a
lánc nem: a worker a core gyermeke, és vele áll le (D4); a többi core a pidfájlon át veszi át.

Átvett worker eltűnése (F3, K11): ha egy másik core-tól átvett worker egy kérés közben megszűnik (kapcsolathiba, és a
pidfájl szerint már nem él), a kliens EGYSZER újraindítja (vagy átveszi az időközben indultat), és a kérést EGYSZER
megismétli. A worker halott, a kérése nem fut tovább: az ismétlés nem duplázódik. Közös bérlet (lease) az F5/F6-ban.
A lánc kéréseinek módja a `MOS_MODELL_MOD` (a feladatsor `auto`-t ad az automatikus feladatnak).

C33 (T182): a worker munkamenet-titkot kér (`X-Manifold: <titok>`). A titok forrása: a saját indítású workernél a
`Folyamat` sorsolja (`MOS_WORKER_TITOK` a gyermek env-jében), az átvett workernél a 0600-as pidfájl harmadik mezője, a
lépéseknél a feladatsor env-je (`MOS_WORKER_TITOK`). A titok nélküli (folyamaton belüli teszt-) worker a régi `1`-et fogadja.
"""
from __future__ import annotations

import json
import os
import secrets
import select
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from ..config import Config


class KliensHiba(RuntimeError):
    def __init__(self, kod: int, uzenet: str, adat: dict | None = None):
        super().__init__(uzenet)
        self.kod, self.adat = kod, adat or {}


def pidfajl(cfg: Config) -> Path:
    """A worker pidfájlja: `{install_run}/worker.pid` (hordozható elrendezésben a v2-beli `var/run/worker.pid`)."""
    return cfg.path("install_run") / "worker.pid"


_titkok: dict[str, str] = {}            # worker-cím → munkamenet-titok (a pidfájlból vagy a saját indításból)
_titkok_zar = threading.Lock()


def _titok_jegyez(u: str, titok: str | None) -> None:
    if titok:
        with _titkok_zar:
            _titkok[u.rstrip("/")] = titok


def _titok(u: str) -> str:
    """A cím titka: a jegyzett (pidfájl, saját indítás), különben a `MOS_WORKER_TITOK` env, különben a régi `1`."""
    with _titkok_zar:
        t = _titkok.get(u.rstrip("/"))
    return t or os.environ.get("MOS_WORKER_TITOK") or "1"


def fut_url(cfg: Config) -> str | None:
    """A futó worker címe a pidfájlból, ha a folyamat él (`"<pid> <port>[ <titok>]"`; a titok a kérésekhez jegyződik)."""
    try:
        mezok = pidfajl(cfg).read_text().split()
        pid, port = mezok[0], mezok[1]
        os.kill(int(pid), 0)
    except (OSError, ValueError, IndexError):
        return None
    u = f"http://127.0.0.1:{port}"
    _titok_jegyez(u, mezok[2] if len(mezok) > 2 else None)
    return u


def titok(u: str) -> str:
    """A worker címéhez tartozó titok (a core a lépések env-jébe adja: `MOS_WORKER_TITOK`)."""
    return _titok(u)


def url(cfg: Config | None = None) -> str:
    u = os.environ.get("MOS_WORKER_URL") or (fut_url(cfg) if cfg else None)
    if not u:
        raise KliensHiba(503, "nem fut modell-worker (a core indítja modelligényes feladatnál)")
    return u


# Az átvett worker eltűnésekor egyszer megismételhető kérések (a modellmunka; a `health`, `unload`, `megszakit` és
# `automatikus` nem: azok nem indíthatnak workert mellékhatásként)
UJRAPROBALHATO = frozenset({"/v1/chat/completions", "/v1/embeddings", "/v1/rerank", "/v1/audio/transcriptions",
                            "/router/valaszt"})
_atvevok: dict[str, "Folyamat"] = {}    # átvett (idegen) worker címe → az átvevő `Folyamat` (csak a saját folyamatban)


def _atvevo_jegyez(u: str | None, f: "Folyamat | None") -> None:
    if not u:
        return
    with _titkok_zar:
        if f is None:
            _atvevok.pop(u.rstrip("/"), None)
        else:
            _atvevok[u.rstrip("/")] = f


def _atvevo(u: str) -> "Folyamat | None":
    with _titkok_zar:
        return _atvevok.get(u.rstrip("/"))


def keres(u: str, ut: str, body: dict | None = None, timeout: float | None = None) -> dict:
    """Egy kérés a workernek. Ha a cím egy átvett workeré, és az a kérés közben eltűnt (kapcsolathiba, a pidfájl szerint
    nem él), a kérés átvevő `Folyamat`-a egyszer újraindítja, és a kérés egyszer megismétlődik (F3-DESIGN §4)."""
    try:
        return _keres(u, ut, body, timeout)
    except KliensHiba as e:
        f = _atvevo(u) if e.adat.get("kapcsolat") and ut in UJRAPROBALHATO else None
        u2 = f.atvett_eltunt(u) if f is not None else None
        if not u2:
            raise
        print(f"[modell-kliens] az átvett modell-worker eltűnt ({e}); újraindítva ({u2}), a kérést egyszer megismétlem",
              file=sys.stderr, flush=True)
        return _keres(u2, ut, body, timeout)


def _hallgat(u: str, timeout: float = 1.0) -> bool:
    """Fogad-e kapcsolatot a cím portja. A kilépett worker portja visszautasít — akkor is, ha a folyamata még be nem gyűjtött
    (zombi), és a pidfájl szerinti `kill(pid, 0)` még élőnek mutatja. Nem eldönthető esetben (időtúllépés): él."""
    try:
        port = int(u.rstrip("/").rsplit(":", 1)[1])
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except ConnectionRefusedError:
        return False
    except (OSError, ValueError, IndexError):
        return True


def _keres(u: str, ut: str, body: dict | None = None, timeout: float | None = None) -> dict:
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(u.rstrip("/") + ut, data=data, method="POST" if body is not None else "GET",
                                 headers={"X-Manifold": _titok(u), "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            adat = json.loads(e.read() or b"{}")
        except ValueError:
            adat = {}
        finally:
            e.close()
        raise KliensHiba(e.code, adat.get("hiba") or str(e), adat) from None
    except (urllib.error.URLError, OSError) as e:
        # `kapcsolat`: a kérés a hálózati rétegen akadt el (időtúllépés, bontott vagy visszautasított kapcsolat) — nem a worker
        # válaszolt hibával; a `chat_keres` ilyenkor egyszer újrapróbálhat
        raise KliensHiba(503, f"a modell-worker nem érhető el: {e}", {"kapcsolat": True}) from None


def _mod(mod: str | None) -> str:
    return mod or os.environ.get("MOS_MODELL_MOD") or "interaktiv"


def _feladat_id(body: dict) -> dict:
    """A kérő feladat azonosítója (a feladatsor `MOS_FELADAT`-ja), hogy a leállításkor a worker megszakíthassa."""
    fid = os.environ.get("MOS_FELADAT")
    if fid:
        body.setdefault("feladat_id", fid)
    return body


def megszakit(u: str, feladat_id: str, timeout: float = 3) -> dict:
    """A worker megszakítja a feladat folyó és várakozó kéréseit (C17)."""
    return keres(u, "/v1/megszakit", {"feladat_id": feladat_id}, timeout=timeout)


def automatikus(u: str, feladat_id: str, timeout: float = 3) -> dict:
    """A worker a feladat kéréseit `auto` módban futtatja (M3, C19; a core hívja az automatikus feladat indulásakor)."""
    return keres(u, "/v1/automatikus", {"feladat_id": feladat_id}, timeout=timeout)


# A chat-kérés válaszának felső korlátja (A-javító, 2026-10-14): egy lógó worker vagy egy elveszett válasz ne blokkolja örökre a
# lépést, a mérést és vele a leállást. `[modellgazda] chat_idokorlat_mp`: az interaktív kérés a betöltéssel és a generálással
# együtt (a gondolkodó modellek egy tétele ~600 s is lehet); `chat_idokorlat_auto_mp`: az `auto` kérés a worker sorában a
# tétlenségre is várhat (M3: aktív használat alatt nem indul), ezért annak a korlátja hosszabb, de véges.
CHAT_IDOKORLAT_MP = 900.0
CHAT_IDOKORLAT_AUTO_MP = 7200.0


def chat_idokorlat(mod: str | None, cfg: Config | None = None) -> float:
    """A chat-kérés időkorlátja a módhoz: a `[modellgazda]` kulcsaiból (ha a config betölthető), különben az alapértékek."""
    alap = {"chat_idokorlat_mp": CHAT_IDOKORLAT_MP, "chat_idokorlat_auto_mp": CHAT_IDOKORLAT_AUTO_MP}
    kulcs = "chat_idokorlat_auto_mp" if mod == "auto" else "chat_idokorlat_mp"
    try:
        if cfg is None:
            from .. import config as _config
            cfg = _config.load()
        ertek = float(cfg.section("modellgazda").get(kulcs, alap[kulcs]))
        return ertek if ertek > 0 else alap[kulcs]
    except Exception:  # noqa: BLE001 — config nélkül (teszt, idegen gyökér) az alapérték
        return alap[kulcs]


def _tetlen(u: str) -> bool:
    """A worker él és tétlen (nincs futó és várakozó kérés) — azaz a mi kérésünk nincs nála: elveszett."""
    try:
        h = health(u, timeout=5)
    except KliensHiba:
        return False
    return bool(h.get("ok")) and h.get("fut") is None and not h.get("fuggo")


def chat_keres(u: str, body: dict, timeout: float | None = None, ujraprobal: bool = True) -> dict:
    """A `/v1/chat/completions` időkorláttal (`chat_idokorlat`), és EGY óvatos újrapróbával: időtúllépés vagy kapcsolathiba után
    csak akkor, ha a worker él és tétlen (a kérés elveszett, nem fut tovább — így nem duplázódik). A mérés (`mos eval`) és a
    láncok `chat`-je is ezt hívja; a mérés ujjlenyomatos folytatása miatt egy tétel ismétlése veszteségmentes."""
    if timeout is None:
        timeout = chat_idokorlat(body.get("mod"))
    try:
        return keres(u, "/v1/chat/completions", body, timeout=timeout)
    except KliensHiba as e:
        if not (ujraprobal and e.adat.get("kapcsolat") and _tetlen(u)):
            raise
        print(f"[modell-kliens] a chat-kérés megszakadt ({e}); a worker tétlen: egyszer újrapróbálom", file=sys.stderr,
              flush=True)
        return keres(u, "/v1/chat/completions", body, timeout=timeout)


def chat(u: str, messages: list[dict], feladat: str | None = None, modell: str | None = None, mod: str | None = None,
         timeout: float | None = None, **kw) -> dict:
    """Egy chat-kérés a workernek. `timeout`: a válasz felső korlátja (alapból `chat_idokorlat` a módhoz); túllépésnél,
    ha a worker tétlen, egy újrapróba, különben `KliensHiba` (503)."""
    body = _feladat_id({"messages": messages, "mod": _mod(mod), **kw})
    if feladat:
        body["feladat"] = feladat
    if modell:
        body.update(model=modell, proba=True)
    return chat_keres(u, body, timeout=timeout)


def beagyaz(u: str, szovegek: list[str], feladat: str = "beagyazas", mod: str | None = None, **kw) -> list:
    r = keres(u, "/v1/embeddings", _feladat_id({"input": szovegek, "feladat": feladat, "mod": _mod(mod), **kw}))
    return [d["embedding"] for d in r["data"]]


def atir(u: str, hang: str, feladat: str = "atirat", modell: str | None = None, nyelv: str | None = "hu",
         mod: str | None = None, timeout: float | None = None) -> dict:
    """Hang → átirat (C20b): `{text, szegmensek, nyelv, hossz_mp, modell, proba, …}`. A `modell` csak próbában (D9)."""
    body = _feladat_id({"audio": hang, "feladat": feladat, "mod": _mod(mod)})
    if nyelv:
        body["nyelv"] = nyelv
    if modell:
        body.update(model=modell, proba=True)
    return keres(u, "/v1/audio/transcriptions", body, timeout=timeout)


def health(u: str, timeout: float = 5) -> dict:
    return keres(u, "/health", timeout=timeout)


def unload_ha_fut(cfg: Config) -> bool:
    u = fut_url(cfg)
    if not u:
        return False
    try:
        keres(u, "/unload", {}, timeout=600)
    except KliensHiba:
        return False
    return True


class Folyamat:
    """A worker gyermekfolyamatként (a core vagy a CLI gyermeke). Ha már fut egy (pidfájl), azt használja."""

    def __init__(self, cfg: Config, argv: list[str] | None = None, env: dict[str, str] | None = None,
                 sajat: bool = False):
        """`sajat`: csak saját workert indít (a futó idegen workert nem használja: az `env`-je, pl. a
        `MANIFOLD_MODELL_KERET_GB`-felülírás, csak így érvényes — M3, C19: az eval távol-keretes mérése)."""
        self.cfg = cfg
        self.argv = argv or [sys.executable, "-B", "-m", "core.modell.worker"]
        self.env_extra = dict(env or {})
        self.sajat = sajat
        self.proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self.url: str | None = None

    def el(self) -> bool:
        """Él-e a worker. C33 (T183): az átvett idegen workernél (`proc is None`) a pidfájl szerint — a halála után hamis."""
        if self.url is None:
            return False
        if self.proc is not None:
            return self.proc.poll() is None
        if fut_url(self.cfg) != self.url:
            _atvevo_jegyez(self.url, None)
            self.url = None
            return False
        return True

    def atvett_eltunt(self, u: str) -> str | None:
        """Egy kérés kapcsolathibát kapott az `u` címen. Ha ez a mi ÁTVETT workerünk volt, és a pidfájl szerint már nem él
        (nem csak lassú: egy élő worker időtúllépése nem ok az újraindításra), a worker egyszer újraindul (`biztosit`: egy
        időközben indult másikat átvesz, különben sajátot indít) → az új cím; egyébként None (a hívó a hibát továbbadja)."""
        with self._lock:
            if self.url and self.url.rstrip("/") != u.rstrip("/"):
                return self.url                       # egy másik szál már újraindította: az új címen ismétlünk
            if self.proc is not None or self.url is None:
                return None                           # saját worker (a core kezeli a halálát), vagy már leállítva
            if fut_url(self.cfg) == self.url and _hallgat(self.url):
                return None                           # él: nem tűnt el (pl. időtúllépés) — nincs újraindítás
            _atvevo_jegyez(self.url, None)
            self.url = None
        try:
            return self.biztosit()
        except KliensHiba as e:
            print(f"[modell-kliens] az átvett worker újraindítása nem sikerült: {e}", file=sys.stderr, flush=True)
            return None

    def _elso_sor(self, hatarido: float) -> bytes:
        """A worker kézfogás-sora határidővel (T183): `select` a csövön; lejáratkor b"" (a hívó leállítja a workert)."""
        fd = self.proc.stdout.fileno()
        buf = b""
        while b"\n" not in buf:
            marad = hatarido - time.monotonic()
            if marad <= 0:
                return b""
            r, _, _ = select.select([fd], [], [], marad)
            if not r:
                return b""
            darab = os.read(fd, 4096)
            if not darab:
                break
            buf += darab
        return buf.split(b"\n", 1)[0]

    def biztosit(self, timeout: float = 30) -> str:
        with self._lock:
            if self.proc is not None and self.proc.poll() is None and self.url:
                return self.url
            u = fut_url(self.cfg)
            if u and self.sajat:
                raise KliensHiba(503, "már fut egy modell-worker (a core-é vagy egy másik mérésé): a keretes mérés saját "
                                      "workert indít a keret-felülírással (M3) — zárd be az appot, vagy várd meg a másik mérést")
            if u:
                try:
                    health(u)
                    self.url = u
                    _atvevo_jegyez(u, self)             # átvett (idegen) worker: eltűnésekor egyszer újraindítunk
                    return u
                except KliensHiba:
                    pass
            env = {**os.environ, **self.env_extra}
            env["MOS_ROOT"] = str(self.cfg.root)
            sajat_titok = secrets.token_urlsafe(24)               # T182: a munkamenet titka (a pidfájlba 0600-zal kerül)
            env["MOS_WORKER_TITOK"] = sajat_titok
            kod = str(Path(__file__).resolve().parents[2])    # a futó core kódja (a config gyökere lehet más)
            env["PYTHONPATH"] = kod + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
            naplo = self.cfg.path("install_logs") / "worker.log"     # gépszintű (F3-DESIGN §4); hordozhatóban var/runs
            naplo.parent.mkdir(parents=True, exist_ok=True)
            with open(naplo, "a", encoding="utf-8") as err:
                self.proc = subprocess.Popen(self.argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err,
                                             env=env, cwd=str(self.cfg.root))
            # T183: a kézfogás határidővel (`select`): egy az első sora előtt elakadó worker nem tartja a zárat (és vele a core
            # stdin-ágú leállását) a végtelenségig
            sor = self._elso_sor(time.monotonic() + timeout)
            try:
                d = json.loads(sor)
                self.url = f"http://127.0.0.1:{d['port']}"
            except (ValueError, KeyError, TypeError):
                self.proc.kill()
                self.proc.wait()
                self.proc.stdin.close()
                self.proc.stdout.close()
                self.proc = None
                ok = "nem jelentkezett {:.0f} s alatt".format(timeout) if not sor else sor.decode(errors="replace").strip()
                raise KliensHiba(503, f"a modell-worker nem indult el: {ok} (napló: {naplo})") from None
            _titok_jegyez(self.url, sajat_titok)
            return self.url

    def leallit(self, timeout: float = 30, azonnal: bool = False) -> None:
        """A worker leállítása: a stdin zárásával a folyó hívás végén kiürít és kilép (`timeout` után SIGTERM, 10 s múlva
        SIGKILL). `azonnal` (a core kényszerága, második ⌘Q): rögtön SIGTERM, 2 s múlva SIGKILL — a `KENYSZER_MP`-es keretbe
        a kilépési bundle-próbának is bele kell férnie."""
        with self._lock:
            if self.proc is None:
                _atvevo_jegyez(self.url, None)
            p, self.proc, self.url = self.proc, None, None
        if p is None:
            return
        try:
            p.stdin.close()
        except OSError:
            pass
        if azonnal:
            p.terminate()
            try:
                p.wait(2)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
            p.stdout.close()
            return
        try:
            p.wait(timeout)
        except subprocess.TimeoutExpired:
            p.terminate()
            try:
                p.wait(10)
            except subprocess.TimeoutExpired:
                p.kill()
        p.stdout.close()
