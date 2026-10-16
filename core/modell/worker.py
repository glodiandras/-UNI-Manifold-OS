"""A modell-worker: külön folyamat, egyszerre EGY modellel (ARCHITECTURE 1.–2.; a legacy `gazda` utódja).

Életciklus (a héj↔core mintája): a core indítja stdin-csővel; az első stdout-sor `{"port", "pid"}`; a
stdin lezárulásakor a folyó hívás végén kiürít és kilép. Egy telepítésen egy worker fut (`{install_run}/worker.lock`; F3-DESIGN
§4), a címe a `{install_run}/worker.pid`-ben (`"<pid> <port> <titok>"`, L29; 0600): a többi core (más munkatér) ezen át veszi
át (D4: a worker az indító core gyermeke). A worker csak a telepítés szakaszait olvassa (`config.load(munkater=False)`), a
vaultba nem ír és nem olvas belőle. Hordozható elrendezésben az `{install_run}` a v2-beli `var/run`.

Biztonság (L29): csak `127.0.0.1`; a `Host` csak helyi cím; minden kérésben `X-Manifold: <titok>`. C33 (T182): a titok
munkamenetenként sorsolt (a core a `MOS_WORKER_TITOK` env-ben adja, különben a worker sorsol), a pidfájl 0600, így egy
idegen helyi folyamat nem tölthet modellt és nem „mérgezhet” előre egy feladat-azonosítót (`/v1/megszakit`). A titok
nélkül összerakott gazda (`Gazda(titok=None)`, a folyamaton belüli tesztek) a régi `X-Manifold: 1`-et fogadja.

Végpontok (OpenAI-szerű részhalmaz, JSON):
    GET  /health                 állapot: betöltött modell, keret, aktivitás, szabad memória, szünetek, hűtés
    POST /v1/chat/completions    {feladat | modell+proba, messages, images, max_tokens, temperature, gondolkodas,
                                  repetition_penalty, repetition_context_size, mod, keret, kizart_csalad}
    POST /v1/chat/stream         ugyanaz NDJSON-folyamként: {tipus: token | vege | hiba} soronként (C25b)
    POST /v1/embeddings          {input, feladat="beagyazas" | modell+proba}
    POST /v1/rerank              {query, documents, feladat="rerank" | modell+proba}
    POST /v1/audio/transcriptions {audio: abszolút út, nyelv, feladat="atirat" | modell+proba} → {text, szegmensek, …} (C20b;
                                  a worker a megnevezett hangfájlt csak olvassa, a pinelt ffmpeg-gel dekódolja)
    POST /v1/megszakit           {feladat_id} → a leállított feladat folyó generálása megszakad (C17)
    POST /v1/automatikus         {feladat_id} → a feladat kérései `auto` módban futnak (M3, C19; a core jelzi)
    POST /unload
    GET  /router                 a kalibrációs tábla
    POST /router/valaszt         {feladat, keret, kizart_csalad} → a router döntése (száraz futás)
Élesben csak kalibrált modell fut (D9): kifejezett `modell` csak `proba: true`-val, és a válasz ezt hordozza.
"""
from __future__ import annotations

import collections
import fcntl
import hmac
import json
import os
import queue
import re
import secrets
import signal
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .. import config
from . import beallitas as B
from . import halmaz
from .aktivitas import Aktivitas
from .betolto import Betolto, KeretHiba, Leallas
from .hatter import BetoltesHiba, Megszakitva
from .ho import Ho
from . import kalibracio
from .kalibracio import Tabla
from .router import NincsMasikCsalad, Router, RoutingHiba
from .utemezo import AUTO, INTERAKTIV, Keres, Utemezo

HELYI = {"127.0.0.1", "localhost", "[::1]"}
MAX_TORZS = 64 * 1024 * 1024


class KeresHiba(ValueError):
    pass


def _kizart_csalad(body: dict) -> str | None:
    """A kérés `kizart_csalad` mezője (C24b, második vélemény): nem üres szöveg vagy semmi."""
    v = body.get("kizart_csalad")
    if v is None or v == "":
        return None
    if not isinstance(v, str) or len(v) > 40:
        raise KeresHiba("a kizart_csalad egy modellcsalád neve legyen (szöveg)")
    return v


FELADAT_ID = re.compile(r"F-[0-9A-Za-z-]{1,40}")


class Gazda:
    """A worker állapota; a tesztek álháttérrel és álaktivitással rakják össze."""

    def __init__(self, b: B.Beallitas, betolto: Betolto, aktivitas: Aktivitas, tabla: Tabla, verziok=None,
                 titok: str | None = None, **utemezo_kw):
        self.b = b
        self.titok = titok              # T182: a munkamenet titka (None: a folyamaton belüli tesztek régi `1`-e)
        self.betolto = betolto
        self.aktivitas = aktivitas
        self.tabla = tabla
        self.router = Router(b, tabla, verziok=verziok)
        self._auto_lock = threading.Lock()
        self._automatikus: collections.OrderedDict[str, None] = collections.OrderedDict()
        self.ho = Ho(b.ho, tabla)
        self.utemezo = Utemezo(b, betolto, aktivitas, self.router, self.ho, **utemezo_kw)

    def automatikus(self, body: dict) -> dict:
        """A core jelzi, hogy egy feladat automatikus (`TaskType.automatikus`): a kérései a megadott módtól függetlenül
        `auto` módban futnak (M3, C19) — aktív használatkor szünetelnek, és nem kapnak távol-keretet."""
        fid = body.get("feladat_id")
        if not isinstance(fid, str) or not fid:
            raise KeresHiba("a feladat_id kötelező")
        with self._auto_lock:
            self._automatikus[fid] = None
            self._automatikus.move_to_end(fid)
            while len(self._automatikus) > 256:
                self._automatikus.popitem(last=False)
        return {"ok": True}

    def _keres(self, tipus: str, body: dict, alap_feladat: str | None) -> Keres:
        mod = body.get("mod")
        if mod is None:
            raise KeresHiba("a mod kötelező (auto | interaktiv; M3)")
        if mod not in (AUTO, INTERAKTIV):
            raise KeresHiba(f"ismeretlen mód: {mod} (auto | interaktiv)")
        fid = str(body["feladat_id"]) if body.get("feladat_id") else None
        with self._auto_lock:
            if fid in self._automatikus:
                mod = AUTO                                     # az automatikus feladat kérése mindig auto (M3)
        modell = None
        if body.get("model"):
            if not body.get("proba"):
                raise KeresHiba("élesben csak kalibrált modell fut: adj meg feladatot, vagy próbához proba=true-t")
            modell = self.b.modell(str(body["model"]))
        feladat = body.get("feladat") or alap_feladat
        if modell is None and not feladat:
            raise KeresHiba("a kérésben nincs feladat")
        keret = body.get("keret")
        if keret is not None:
            try:
                B.ervenyes_keret(self.b.keretek, keret)  # érvényes-e (NaN/inf/≤ 0 → 400); az ütemező csak szűkíteni engedi
            except ValueError as exc:
                raise KeresHiba(str(exc)) from None
        return Keres(tipus, body, mod=mod, feladat=feladat, modell=modell, keret=keret, feladat_id=fid,
                     kizart_csalad=_kizart_csalad(body))

    def chat(self, body: dict) -> dict:
        if not isinstance(body.get("messages"), list):
            raise KeresHiba("a messages lista kötelező")
        k = self._keres("chat", body, None)
        o = self.utemezo.bekuld(k)
        r = o["r"]
        return {"object": "chat.completion", "model": o["modell"].repo, "modell": o["modell"].nev,
                "feladat": k.feladat, "proba": k.modell is not None, "keret_gb": o["keret_gb"], "mp": o["mp"],
                "memoria": o["memoria"],
                "choices": [{"index": 0, "message": {"role": "assistant", "content": r["text"].strip()},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": r.get("prompt_tokens", 0), "completion_tokens": r.get("generation_tokens", 0),
                          "generation_tps": round(float(r.get("generation_tps") or 0), 2)}}

    def chat_folyam(self, body: dict) -> tuple[Keres, "queue.Queue[dict]"]:
        """A `/v1/chat/stream` (C25b): a kérés ugyanúgy az ütemezőn megy, a szövegdarabok egy sorba kerülnek, ahogy
        készülnek (`token`), a végén `vege` (modell, próba, mérés) vagy `hiba`. A kérő bontása: `Utemezo.elvet`."""
        if not isinstance(body.get("messages"), list):
            raise KeresHiba("a messages lista kötelező")
        k = self._keres("chat", body, None)
        sor: queue.Queue[dict] = queue.Queue()
        k.tokenre = lambda t: sor.put({"tipus": "token", "szoveg": t})

        def fut():
            try:
                o = self.utemezo.bekuld(k)
                r = o["r"]
                sor.put({"tipus": "vege", "modell": o["modell"].nev, "feladat": k.feladat, "proba": k.modell is not None,
                         "keret_gb": o["keret_gb"], "mp": o["mp"], "memoria": o["memoria"],
                         "usage": {"prompt_tokens": r.get("prompt_tokens", 0),
                                   "completion_tokens": r.get("generation_tokens", 0),
                                   "generation_tps": round(float(r.get("generation_tps") or 0), 2)}})
            except Megszakitva as exc:
                sor.put({"tipus": "hiba", "kod": 409, "hiba": str(exc), "megszakitva": True})
            except RoutingHiba as exc:
                sor.put({"tipus": "hiba", "kod": 409, "hiba": str(exc), "nincs_kalibralt": True})
            except (KeretHiba, Leallas, TimeoutError) as exc:
                sor.put({"tipus": "hiba", "kod": 503, "hiba": str(exc)})
            except (KeresHiba, B.RegiszterHiba, BetoltesHiba, ValueError) as exc:
                sor.put({"tipus": "hiba", "kod": 400, "hiba": str(exc)})
            except Exception as exc:  # noqa: BLE001 — a kérő mindig kap végeseményt
                sor.put({"tipus": "hiba", "kod": 500, "hiba": f"{type(exc).__name__}: {exc}"})

        threading.Thread(target=fut, name="chat-folyam", daemon=True).start()
        return k, sor

    def embed(self, body: dict) -> dict:
        szov = body.get("input", [])
        body = {**body, "input": [szov] if isinstance(szov, str) else list(szov)}
        k = self._keres("embed", body, "beagyazas")
        o = self.utemezo.bekuld(k)
        return {"object": "list", "model": o["modell"].repo, "modell": o["modell"].nev, "proba": k.modell is not None,
                "memoria": o["memoria"], "data": [{"object": "embedding", "index": i, "embedding": v} for i, v in enumerate(o["r"]["vektorok"])]}

    def rerank(self, body: dict) -> dict:
        k = self._keres("rerank", body, "rerank")
        o = self.utemezo.bekuld(k)
        return {"model": o["modell"].repo, "modell": o["modell"].nev, "proba": k.modell is not None,
                "memoria": o["memoria"], "results": [{"index": i, "relevance_score": p} for i, p in enumerate(o["r"]["pontok"])]}

    def atir(self, body: dict) -> dict:
        """Hang → átirat (C20b): a kérés az ütemezőn megy, mint a többi; a válasz a szöveg és az időkódos szegmensek."""
        hang = body.get("audio")
        if not isinstance(hang, str) or not os.path.isabs(hang) or "\x00" in hang or len(hang) > 4096:
            raise KeresHiba("az audio egy hangfájl abszolút útja legyen")
        nyelv = body.get("nyelv")
        if nyelv is not None and (not isinstance(nyelv, str) or not nyelv.isalpha() or len(nyelv) > 8):
            raise KeresHiba("a nyelv egy nyelvkód legyen (pl. hu)")
        k = self._keres("atirat", body, "atirat")
        o = self.utemezo.bekuld(k)
        r = o["r"]
        return {"object": "transcription", "model": o["modell"].repo, "modell": o["modell"].nev, "feladat": k.feladat,
                "proba": k.modell is not None, "keret_gb": o["keret_gb"], "mp": o["mp"], "memoria": o["memoria"],
                "text": r["text"], "szegmensek": r["szegmensek"], "nyelv": r.get("nyelv"), "hossz_mp": r.get("hossz_mp")}

    def megszakit(self, body: dict) -> dict:
        """Egy leállított feladat kéréseinek megszakítása (C17): a folyó generálás a következő tokennél megáll. C33 (T182):
        csak feladatsor-alakú azonosító (`F-…`) fogadható; a hívó a titkot ismerő core (a lépései)."""
        fid = body.get("feladat_id")
        if not isinstance(fid, str) or not fid:
            raise KeresHiba("a feladat_id kötelező")
        if not FELADAT_ID.fullmatch(fid):
            raise KeresHiba(f"érvénytelen feladat-azonosító: {fid!r}")
        return {"ok": True, "megszakitott": self.utemezo.megszakit(fid)}

    def valaszt(self, body: dict) -> dict:
        keret = self.b.keret_gb(body.get("keret") or ("tavol" if self.aktivitas.allapot() == "tavol" else "munka"))
        return {"keret_gb": keret, **self.router.valaszt(str(body.get("feladat") or ""), keret,
                                                        kizart_csalad=_kizart_csalad(body)).publikus()}

    def health(self) -> dict:
        return {"ok": True, "pid": os.getpid(), **self.betolto.allapot(), "aktivitas": self.aktivitas.publikus(),
                "keretek": self.b.keretek, "keret_felulirva": self.b.keret_felulirva, **self.utemezo.allapot()}


def _handler(g: Gazda):
    class Kezelo(BaseHTTPRequestHandler):
        server_version = "ManifoldWorker"

        def log_message(self, *a):
            pass

        def _kuld(self, kod: int, obj) -> None:
            data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(kod)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(data)

        def _enged(self) -> bool:
            vart = g.titok if g.titok is not None else "1"
            kapott = self.headers.get("X-Manifold") or ""
            if (self.headers.get("Host") or "").rsplit(":", 1)[0] not in HELYI or \
                    not hmac.compare_digest(kapott.encode("utf-8"), vart.encode("utf-8")):
                self._kuld(403, {"hiba": "csak helyi kérés, a munkamenet X-Manifold titkával"})
                return False
            return True

        def _vegez(self, fn) -> None:
            try:
                return self._kuld(200, fn())
            except (KeresHiba, B.RegiszterHiba, BetoltesHiba, ValueError) as exc:
                return self._kuld(400, {"hiba": str(exc)})
            except Megszakitva as exc:
                return self._kuld(409, {"hiba": str(exc), "megszakitva": True})
            except RoutingHiba as exc:
                return self._kuld(409, {"hiba": str(exc), "nincs_kalibralt": True,
                                        **({"nincs_masik_csalad": True} if isinstance(exc, NincsMasikCsalad) else {})})
            except (KeretHiba, Leallas, TimeoutError) as exc:
                return self._kuld(503, {"hiba": str(exc)})
            except (BrokenPipeError, ConnectionResetError):
                return None
            except Exception as exc:  # noqa: BLE001 — a kapcsolat ne szakadjon meg szó nélkül
                return self._kuld(500, {"hiba": f"{type(exc).__name__}: {exc}"})

        def _folyam(self, body: dict) -> None:
            """NDJSON-folyam: soronként egy esemény. A kérő bontását az írás hibája jelzi (a következő tokennél, vagy a
            várakozás alatti 1 s-os életjelnél): ekkor a kérés kikerül a sorból, illetve a generálás megáll."""
            try:
                k, sor = g.chat_folyam(body)
            except (KeresHiba, B.RegiszterHiba, ValueError) as exc:
                return self._kuld(400, {"hiba": str(exc)})
            try:
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Connection", "close")
                self.end_headers()
                while True:
                    try:
                        e = sor.get(timeout=1.0)
                    except queue.Empty:
                        self.wfile.write(b"\n")               # életjel: a bontott kapcsolat így is kiderül
                        self.wfile.flush()
                        continue
                    self.wfile.write(json.dumps(e, ensure_ascii=False).encode("utf-8") + b"\n")
                    self.wfile.flush()
                    if e["tipus"] in ("vege", "hiba"):
                        return None
            except (BrokenPipeError, ConnectionResetError, OSError):
                g.utemezo.elvet(k)
                return None

        def do_GET(self):
            if not self._enged():
                return
            if self.path == "/health":
                return self._vegez(g.health)
            if self.path == "/router":
                return self._vegez(lambda: {"tabla": g.tabla.tabla()})
            self._kuld(404, {"hiba": "nincs ilyen végpont"})

        def do_POST(self):
            if not self._enged():
                return
            try:
                n = int(self.headers.get("Content-Length") or 0)
                if n > MAX_TORZS:
                    return self._kuld(413, {"hiba": "túl nagy kérés"})
                body = json.loads(self.rfile.read(n) or b"{}")
                if not isinstance(body, dict):
                    raise ValueError
            except ValueError:
                return self._kuld(400, {"hiba": "érvénytelen JSON"})
            if self.path == "/v1/chat/stream":
                return self._folyam(body)
            utak = {"/v1/chat/completions": lambda: g.chat(body), "/v1/embeddings": lambda: g.embed(body),
                    "/v1/rerank": lambda: g.rerank(body), "/router/valaszt": lambda: g.valaszt(body),
                    "/v1/audio/transcriptions": lambda: g.atir(body),
                    "/v1/megszakit": lambda: g.megszakit(body), "/v1/automatikus": lambda: g.automatikus(body),
                    "/unload": lambda: (g.utemezo.urit(), {"ok": True})[1]}
            if self.path in utak:
                return self._vegez(utak[self.path])
            self._kuld(404, {"hiba": "nincs ilyen végpont"})

    return Kezelo


class Szerver(ThreadingHTTPServer):
    daemon_threads = True


def gazda_osszerak(cfg: config.Config, titok: str | None = None) -> Gazda:
    b = B.betolt(cfg)
    return Gazda(b, Betolto(b), Aktivitas.beallitasbol(b), kalibracio.megnyit(cfg),
                 verziok=halmaz.Verziok(cfg.path("modulok")), titok=titok)


def pidfajl_ir(ut: Path, pid: int, port: int, titok: str) -> None:
    """A `{install_run}/worker.pid` (`"<pid> <port> <titok>"`) 0600-as joggal, atomi cserével (T182): a titkot más fiók nem olvassa."""
    tmp = ut.with_name(f".{ut.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, f"{pid} {port} {titok}\n".encode("ascii"))
    finally:
        os.close(fd)
    os.replace(tmp, ut)


def main(stdin=None, out=None) -> int:
    # L28: futásidőben offline; a modellek a {models} alatt
    # F3: a worker gépszintű — csak a telepítés szakaszai kellenek, munkatér nélkül is betölt (a `{var}` családja halasztott)
    cfg = config.load(munkater=False)
    os.environ.update({"HF_HOME": str(cfg.path("models")), "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"})
    run = cfg.path("install_run")
    run.mkdir(parents=True, exist_ok=True)
    lock_fd = os.open(run / "worker.lock", os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print(json.dumps({"hiba": f"már fut egy modell-worker ({run / 'worker.pid'})"}, ensure_ascii=False), flush=True)
        return 3
    titok = os.environ.get("MOS_WORKER_TITOK") or secrets.token_urlsafe(24)
    g = gazda_osszerak(cfg, titok=titok)
    b = g.b
    httpd = Szerver(("127.0.0.1", int(b.gazda.get("port") or 0)), _handler(g))
    port = httpd.server_address[1]
    pidfajl = run / "worker.pid"
    pidfajl_ir(pidfajl, os.getpid(), port, titok)
    out = out or sys.stdout
    out.write(json.dumps({"port": port, "pid": os.getpid()}) + "\n")
    out.flush()
    stdin = stdin or sys.stdin.buffer
    leall = threading.Event()

    def vege(*_):
        if leall.is_set():
            return
        leall.set()
        threading.Thread(target=lambda: (g.utemezo.leall(), httpd.shutdown()), daemon=True).start()

    def figyel():
        try:
            while stdin.read(4096):
                pass
        except (OSError, ValueError):
            pass
        vege()

    threading.Thread(target=figyel, daemon=True).start()
    signal.signal(signal.SIGTERM, vege)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
        g.betolto.urit()
        try:
            if pidfajl.read_text().split()[0] == str(os.getpid()):
                pidfajl.unlink()
        except (OSError, IndexError):
            pass
        os.close(lock_fd)
    return 0


if __name__ == "__main__":
    sys.exit(main())
