#!/usr/bin/env python3
"""Developer tool: generate SYNTHETIC, neutral training / evaluation data for the repository with your own Anthropic key.

NOT part of the product: it lives in `tools/` (not packaged, see `packaging/csomag_kozos.KOD_RESZEK`), it is never imported by
the core, and nothing it writes is read by the product until you adopt it explicitly.

What it makes (`tools/gen_sablonok/*.toml`, the only prompts it ever sends; English, neutral, no real people/companies/notes):
  kod, kiegeszites, matek   gold-set CANDIDATES in the shipped set format (new English candidate set `arany_en.json`)
  demo                      extra demo-workspace note candidates (English, in the style of `core/demo_tartalom.py`)
  doku                      optional review remarks for the `docs/user/*.md` pages (a suggestions report; modifies nothing)

Usage (run with the project interpreter, e.g. `bin/mos exec python3 tools/gen_szintetikus.py ...`; stdlib only):
  1. Put the key into the macOS Keychain (it is prompted for, so it never appears in argv or shell history):
         security add-generic-password -s manifold-anthropic -a "$USER" -w
     (`--kulcs-env` reads `ANTHROPIC_API_KEY` instead; that is the only alternative source.)
  2. Dry run (no network, no key read; prints the number of calls and the worst-case cost):
         python3 tools/gen_szintetikus.py --szaraz
  3. Real run (default budget: `--max-usd 5.00`, `--max-hivas 60`, lifetime `--osszes-max-usd 20.00`):
         python3 tools/gen_szintetikus.py [--sablon kiegeszites --sablon matek ...] [--max-usd 2]
     Output: `var/staging/szintetikus/<run-id>/` (gitignored): `tetelek.jsonl`, `elutasitott.jsonl`, `jovahagyas.toml`,
     `manifest.json`, `koltseg.json` (running cost, written after every call).
  4. Review `tetelek.jsonl`; set `jovahagyva = true` in `jovahagyas.toml` for what you accept.
  5. Adopt (no network): `python3 tools/gen_szintetikus.py --atvesz <run-id> --cel kiegeszites [--szaraz] [--mind-jovahagy]`.

Safety rules (enforced in code, covered by `tests/test_gen_szintetikus.py`):
  - the key comes only from the Keychain (`security find-generic-password -s manifold-anthropic -w`) or, with `--kulcs-env`,
    from `ANTHROPIC_API_KEY`; it is never printed, logged, written, put in argv, an exception or a traceback;
  - one fixed endpoint (`https://api.anthropic.com/v1/messages`), standard library only, no redirects, timeout, at most 3 retries
    (429 / 5xx / connection errors, exponential back-off), bounded response size; only `claude-*` model ids with a known price;
  - cost guard: before every call the worst case (estimated input + `max_tokens` x output price) must fit the remaining run
    budget and the lifetime budget; the real cost comes from the response `usage`; state is saved after every call;
  - no vault, workspace or user data is read or sent (the optional `doku` template sends the repository's own `docs/user` pages);
  - every item is schema-checked, de-duplicated, scanned for secrets / personal data / paths / URLs, size- and language-checked;
    rejected items go to `elutasitott.jsonl` with the reason;
  - `--atvesz` copies only approved items, only into a clean target, never changes an approval state (`allapot` stays `vazlat`).
"""
from __future__ import annotations

import argparse
import ast
import contextlib
import datetime as _dt
import fcntl
import hashlib
import json
import math
import os
import re
import secrets
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parent                                   # tools/ sits directly under the repository root

# ---------------------------------------------------------------------------------------------------- constants

API_URL = "https://api.anthropic.com/v1/messages"
API_HOST = "api.anthropic.com"
API_VERSION = "2023-06-01"
KEYCHAIN_SZOLGALTATAS = "manifold-anthropic"
IDOKORLAT_S = 120.0
MAX_UJRA = 3                                          # retries after the first attempt
MAX_VALASZ_BAJT = 4 * 1024 * 1024
MAX_KERES_BAJT = 256 * 1024
MAX_HIBA_BAJT = 8192
ALAP_OLCSO = "claude-haiku-5-5"
ALAP_MINOSEG = "claude-sonnet-5-5"
MODELL_RE = re.compile(r"^claude-[a-z0-9][a-z0-9.\-]{0,62}\Z")
KULCS_RE = re.compile(r"^[A-Za-z0-9_\-]{20,400}\Z")
AZON_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]{0,63}\Z")
ALAP_MAX_USD = 5.00
ALAP_MAX_HIVAS = 60
ALAP_OSSZES_MAX_USD = 20.00
CELOK = ("kod", "kiegeszites", "matek", "demo", "doku")
ATVEHETO_CELOK = ("kod", "kiegeszites", "matek", "demo")
KIMENET_GYOKER_REL = Path("var") / "staging" / "szintetikus"
SABLON_MAPPA = TOOLS / "gen_sablonok"
ARAK_UT = TOOLS / "gen_arak.toml"

# exit codes
KILEPES_OK, KILEPES_HIBA, KILEPES_HASZNALAT, KILEPES_KOLTSEG, KILEPES_HALOZAT = 0, 1, 2, 3, 4


class GenHiba(Exception):
    """A user-facing error; the message never contains the key."""

    def __init__(self, uzenet: str, kod: int = KILEPES_HIBA):
        super().__init__(uzenet)
        self.kod = kod


class KoltsegHiba(GenHiba):
    def __init__(self, uzenet: str):
        super().__init__(uzenet, KILEPES_KOLTSEG)


class SzallitoHiba(GenHiba):
    def __init__(self, uzenet: str, vegzetes: bool = False):
        super().__init__(uzenet, KILEPES_HALOZAT)
        self.vegzetes = vegzetes


# ---------------------------------------------------------------------------------------------------- secret / PII filters
# Mirror of `tests/biztonsag/test_titok_es_ut.py` (a parity test keeps them in step).

TITOK_MINTAK = {
    "huggingface": r"\bhf_[A-Za-z0-9]{30,}\b",
    "sk_kulcs": r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{24,}\b",
    "github": r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b",
    "aws": r"\bAKIA[0-9A-Z]{16}\b",
    "slack": r"\bxox[abprs]-[0-9A-Za-z-]{10,}\b",
    "google": r"\bAIza[0-9A-Za-z_-]{35}\b",
    "privat_kulcs": r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----",
}
SZEMELYES_MINTAK = {
    "email": r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}",
    "url": r"(?i)\b(?:https?|ftp|file)://\S+|\bwww\.[a-z0-9\-]+\.[a-z]{2,}",
    "ut": r"(?:/Users/|/home/|/Volumes/|/private/|/var/folders/|[A-Za-z]:\\Users\\|~/)\S*",
    "telefon": r"(?<![\d.])\+\d{1,3}[\s.\-]?\(?\d{1,4}\)?[\s.\-]?\d{3,4}[\s.\-]?\d{3,4}(?!\d)",
    "ip": r"\b(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}\b",
}
_TITOK_RE = {k: re.compile(v) for k, v in TITOK_MINTAK.items()}
_SZEMELYES_RE = {k: re.compile(v) for k, v in SZEMELYES_MINTAK.items()}


def titkot_kiszed(szoveg, kulcs: str | None = None) -> str:
    """The text with the key (if known) and anything secret-shaped masked; used on every text that may leave the process."""
    s = str(szoveg)
    if kulcs:
        s = s.replace(kulcs, "[key]")
    for r in _TITOK_RE.values():
        s = r.sub("[secret]", s)
    return s


def tilos_talalat(szoveg: str) -> str | None:
    """`secret:<kind>` / `personal:<kind>` for the first forbidden shape in the text, else None."""
    for k, r in _TITOK_RE.items():
        if r.search(szoveg):
            return f"secret:{k}"
    for k, r in _SZEMELYES_RE.items():
        if r.search(szoveg):
            return f"personal:{k}"
    return None


# ---------------------------------------------------------------------------------------------------- language check

_ANGOL_SZAVAK = frozenset("the a an of to in is are and or for with that this it as be by on at from each every if then when where "
                          "which what how can will must you your not no all any one two".split())
_MAGYAR_SZAVAK = frozenset("hogy egy nem vagy kell oldd feladat szamitsd eredmeny jegyzet azt ezt meg van minden mert csak "
                           "utan elott kozott szerint".split())
_NEM_ANGOL_BETU = re.compile("[À-ÖØ-öø-ɏ]")       # Latin-1 / Latin Extended letters (not x or /)
_KOD_BLOKK = re.compile(r"```.*?```|`[^`\n]*`|\$\$.*?\$\$|\$[^$\n]*\$|\[\[[^\]]*\]\]", re.S)


def nem_angol_ok(szoveg: str) -> str | None:
    """None when the text looks English, else the reason. Letters outside ASCII + Greek, or Hungarian marker words, fail."""
    if _NEM_ANGOL_BETU.search(szoveg):
        return "non-English letters"
    return None


def angol_e(szoveg: str) -> str | None:
    """Reason when a human-language text does not look English (code, maths and links are ignored); None when fine."""
    ok = nem_angol_ok(szoveg)
    if ok:
        return ok
    szavak = re.findall(r"[A-Za-z]+", _KOD_BLOKK.sub(" ", szoveg).lower())
    if len(szavak) >= 3 and sum(1 for w in szavak if w in _MAGYAR_SZAVAK) >= 2:
        return "Hungarian marker words"
    if len(szavak) >= 10 and sum(1 for w in szavak if w in _ANGOL_SZAVAK) * 12 < len(szavak):
        return "too few English function words"
    return None


# ---------------------------------------------------------------------------------------------------- small helpers

def _most() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _ma() -> str:
    return _dt.date.today().isoformat()


def atomi_ir(ut: Path, tartalom: str) -> None:
    ut.parent.mkdir(parents=True, exist_ok=True)
    tmp = ut.with_name(f".{ut.name}.tmp-{os.getpid()}")
    try:
        tmp.write_text(tartalom, encoding="utf-8")
        os.replace(tmp, ut)
    finally:
        with contextlib.suppress(OSError):
            tmp.unlink()


def json_ir(ut: Path, adat) -> None:
    atomi_ir(ut, json.dumps(adat, ensure_ascii=False, indent=1) + "\n")


def normalizalt_hash(szoveg: str) -> str:
    """Hash of the lower-cased alphanumerics only: layout and punctuation differences do not make a new item."""
    lap = re.sub(r"[^0-9a-z]+", "", szoveg.lower())
    return hashlib.sha256(lap.encode("utf-8")).hexdigest()[:16]


def fajl_sha256(ut: Path) -> str:
    return hashlib.sha256(Path(ut).read_bytes()).hexdigest()


def toml_szoveg(s: str) -> str:
    """A TOML basic string (printable ASCII only: the summary lines are for a human review file)."""
    s = re.sub(r"\s+", " ", str(s)).strip().encode("ascii", "replace").decode("ascii")
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def futas_azon_ellenoriz(azon: str) -> str:
    if not isinstance(azon, str) or not AZON_RE.match(azon) or azon in (".", "..") or ".." in azon:
        raise GenHiba("invalid run id (letters, digits, '-' and '_' only, at most 64 characters)", KILEPES_HASZNALAT)
    return azon


def futas_mappa(gyoker: Path, azon: str, *, letezik: bool | None = None) -> Path:
    """`<root>/var/staging/szintetikus/<run-id>`; the id is validated and the resolved path must stay below the staging root."""
    futas_azon_ellenoriz(azon)
    alap = (Path(gyoker) / KIMENET_GYOKER_REL)
    ut = alap / azon
    try:
        ut.resolve().relative_to(alap.resolve())
    except ValueError:
        raise GenHiba("the run folder would leave the staging area", KILEPES_HASZNALAT) from None
    if ut.is_symlink():
        raise GenHiba("the run folder is a symbolic link", KILEPES_HASZNALAT)
    if letezik is True and not ut.is_dir():
        raise GenHiba(f"no such run: {azon}", KILEPES_HASZNALAT)
    if letezik is False and ut.exists():
        raise GenHiba(f"the run folder already exists: {azon}", KILEPES_HASZNALAT)
    return ut


# ---------------------------------------------------------------------------------------------------- key

def kulcs_olvas(env_kapcsolo: bool = False, *, futtat=subprocess.run, kornyezet=None) -> str:
    """The API key: Keychain by default, `ANTHROPIC_API_KEY` only with the explicit switch. Errors never contain the key."""
    if env_kapcsolo:
        nyers = (os.environ if kornyezet is None else kornyezet).get("ANTHROPIC_API_KEY", "")
        forras = "ANTHROPIC_API_KEY"
    else:
        try:
            p = futtat(["security", "find-generic-password", "-s", KEYCHAIN_SZOLGALTATAS, "-w"], capture_output=True, text=True,
                       timeout=20, check=False)
        except (OSError, subprocess.SubprocessError):
            raise GenHiba("cannot run the macOS `security` tool (use --kulcs-env on other systems)", KILEPES_HASZNALAT) from None
        if p.returncode != 0:
            raise GenHiba(f"no key in the Keychain (service '{KEYCHAIN_SZOLGALTATAS}'); add it with: "
                          f"security add-generic-password -s {KEYCHAIN_SZOLGALTATAS} -a \"$USER\" -w", KILEPES_HASZNALAT)
        nyers = p.stdout or ""
        forras = "Keychain"
    kulcs = nyers.strip()
    if not KULCS_RE.match(kulcs):
        raise GenHiba(f"the key from {forras} is missing or does not look like an API key", KILEPES_HASZNALAT)
    return kulcs


# ---------------------------------------------------------------------------------------------------- prices and cost guard

@dataclass(frozen=True)
class Ar:
    bemenet: float          # USD per million input tokens
    kimenet: float          # USD per million output tokens


def arak_betolt(ut: Path = ARAK_UT) -> dict[str, Ar]:
    try:
        with open(ut, "rb") as f:
            adat = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise GenHiba(f"cannot read the price file {ut.name}: {type(e).__name__}", KILEPES_HASZNALAT) from None
    ki = {}
    for modell, v in (adat.get("modell") or {}).items():
        try:
            b, k = float(v["bemenet_usd_mtok"]), float(v["kimenet_usd_mtok"])
        except (KeyError, TypeError, ValueError):
            raise GenHiba(f"price file: bad entry for {modell}", KILEPES_HASZNALAT) from None
        if not MODELL_RE.match(modell) or not (math.isfinite(b) and math.isfinite(k)) or not (0 < b <= 1000 and 0 < k <= 1000):
            raise GenHiba(f"price file: bad model id or price for {modell}", KILEPES_HASZNALAT)
        ki[modell] = Ar(b, k)
    if not ki:
        raise GenHiba("the price file has no models", KILEPES_HASZNALAT)
    return ki


def modell_ellenoriz(modell: str, arak: dict[str, Ar]) -> str:
    if not isinstance(modell, str) or not MODELL_RE.match(modell):
        raise GenHiba("only 'claude-' model ids are accepted", KILEPES_HASZNALAT)
    if modell not in arak:
        raise GenHiba(f"model {modell} has no price in {ARAK_UT.name}: add a conservative price first", KILEPES_HASZNALAT)
    return modell


def bemenet_becsles(rendszer: str, felhasznalo: str) -> int:
    """Upper estimate of the input tokens: 2 bytes per token plus a fixed overhead."""
    return math.ceil(len((rendszer + felhasznalo).encode("utf-8")) / 2) + 64


def legrosszabb_usd(ar: Ar, bemenet_tok: int, max_tokens: int) -> float:
    return bemenet_tok * ar.bemenet / 1e6 + max_tokens * ar.kimenet / 1e6


def tenyleges_usd(ar: Ar, usage: dict) -> float:
    """Cost from the response usage. Cache tokens are charged as plain input (an upper bound)."""
    bem = sum(int(usage.get(k) or 0) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    return legrosszabb_usd(ar, bem, int(usage.get("output_tokens") or 0))


def _json_olvas(ut: Path, alap: dict) -> dict:
    """A missing file is the empty state; an unreadable one is an error (never silently reset a budget)."""
    if not ut.exists():
        return json.loads(json.dumps(alap))
    try:
        d = json.loads(ut.read_text(encoding="utf-8"))
        if not isinstance(d, dict):
            raise ValueError
        return d
    except (OSError, ValueError):
        raise KoltsegHiba(f"cost file unreadable: {ut.name} (fix or remove it by hand; the tool will not reset a budget)") from None


class Koltsegor:
    """Per-run and lifetime budget. `foglal` reserves the worst case BEFORE a call, `rogzit` replaces it with the real cost,
    `felold` releases it when the call failed. Both files are rewritten after every step, so a crash leaves the reservation of
    the interrupted call counted (conservative)."""

    def __init__(self, futas_mappa_: Path, osszes_ut: Path, arak: dict[str, Ar], max_usd: float, max_hivas: int,
                 osszes_max_usd: float):
        self.mappa, self.osszes_ut, self.arak = Path(futas_mappa_), Path(osszes_ut), arak
        self.max_usd, self.max_hivas, self.osszes_max = float(max_usd), int(max_hivas), float(osszes_max_usd)
        self.allapot = {"max_usd": self.max_usd, "max_hivas": self.max_hivas, "osszes_max_usd": self.osszes_max,
                        "osszeg_usd": 0.0, "fuggo_usd": 0.0, "hivasok": 0, "http_probak": 0, "bemenet_tok": 0, "kimenet_tok": 0,
                        "modellek": {}, "frissitve": None}
        self._ment()

    def _ment(self) -> None:
        self.allapot["frissitve"] = _most()
        self.allapot["osszeg_usd"] = round(self.allapot["osszeg_usd"], 6)
        self.allapot["fuggo_usd"] = round(max(self.allapot["fuggo_usd"], 0.0), 6)
        json_ir(self.mappa / "koltseg.json", self.allapot)

    @contextlib.contextmanager
    def _osszes(self):
        """Lifetime file under an exclusive lock (parallel runs cannot both spend the same remainder)."""
        self.osszes_ut.parent.mkdir(parents=True, exist_ok=True)
        with open(self.osszes_ut.with_name(self.osszes_ut.name + ".lock"), "a+") as zar:
            fcntl.flock(zar, fcntl.LOCK_EX)
            try:
                d = _json_olvas(self.osszes_ut, {"osszeg_usd": 0.0, "fuggo_usd": 0.0, "napok": {}, "hivasok": 0})
                yield d
                d["osszeg_usd"] = round(float(d.get("osszeg_usd") or 0.0), 6)
                d["fuggo_usd"] = round(max(float(d.get("fuggo_usd") or 0.0), 0.0), 6)
                d["frissitve"] = _most()
                json_ir(self.osszes_ut, d)
            finally:
                fcntl.flock(zar, fcntl.LOCK_UN)

    def osszes_allapot(self) -> dict:
        with self._osszes() as d:
            return dict(d)

    def maradek_usd(self) -> float:
        a = self.allapot
        return self.max_usd - a["osszeg_usd"] - a["fuggo_usd"]

    def foglal(self, modell: str, bemenet_tok: int, max_tokens: int) -> float:
        """Reserve the worst case of one call; raises `KoltsegHiba` when it does not fit the run or the lifetime budget."""
        worst = legrosszabb_usd(self.arak[modell], bemenet_tok, max_tokens)
        a = self.allapot
        if a["hivasok"] >= self.max_hivas:
            raise KoltsegHiba(f"call limit reached ({self.max_hivas})")
        if a["osszeg_usd"] + a["fuggo_usd"] + worst > self.max_usd + 1e-12:
            raise KoltsegHiba(f"the next call (worst case ${worst:.4f}) does not fit the run budget "
                              f"(spent ${a['osszeg_usd']:.4f} of ${self.max_usd:.2f})")
        with self._osszes() as d:
            hasznalt = float(d.get("osszeg_usd") or 0.0) + float(d.get("fuggo_usd") or 0.0)
            if hasznalt + worst > self.osszes_max + 1e-12:
                raise KoltsegHiba(f"the next call (worst case ${worst:.4f}) does not fit the lifetime budget "
                                  f"(${hasznalt:.4f} of ${self.osszes_max:.2f} used; --osszes-max-usd)")
            d["fuggo_usd"] = float(d.get("fuggo_usd") or 0.0) + worst
        a["fuggo_usd"] += worst
        a["hivasok"] += 1
        self._ment()
        return worst

    def rogzit(self, worst: float, modell: str, usage: dict | None, probak: int = 1) -> float:
        """Replace the reservation with the real cost (no usage in the answer: the worst case is charged)."""
        ar = self.arak[modell]
        if usage:
            valos = tenyleges_usd(ar, usage)
            bem = sum(int(usage.get(k) or 0) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
            kim = int(usage.get("output_tokens") or 0)
        else:
            valos, bem, kim = worst, 0, 0
        a = self.allapot
        a["fuggo_usd"] -= worst
        a["osszeg_usd"] += valos
        a["http_probak"] += max(int(probak), 1)
        a["bemenet_tok"] += bem
        a["kimenet_tok"] += kim
        m = a["modellek"].setdefault(modell, {"hivasok": 0, "bemenet_tok": 0, "kimenet_tok": 0, "usd": 0.0})
        m["hivasok"] += 1
        m["bemenet_tok"] += bem
        m["kimenet_tok"] += kim
        m["usd"] = round(m["usd"] + valos, 6)
        self._ment()
        with self._osszes() as d:
            d["fuggo_usd"] = float(d.get("fuggo_usd") or 0.0) - worst
            d["osszeg_usd"] = float(d.get("osszeg_usd") or 0.0) + valos
            d["hivasok"] = int(d.get("hivasok") or 0) + 1
            napok = d.setdefault("napok", {})
            napok[_ma()] = round(float(napok.get(_ma()) or 0.0) + valos, 6)
        return valos

    def felold(self, worst: float, probak: int = 1) -> None:
        """A failed call (no answer, nothing billed): release the reservation."""
        a = self.allapot
        a["fuggo_usd"] -= worst
        a["http_probak"] += max(int(probak), 1)
        self._ment()
        with self._osszes() as d:
            d["fuggo_usd"] = float(d.get("fuggo_usd") or 0.0) - worst


# ---------------------------------------------------------------------------------------------------- transport

@dataclass
class Valasz:
    szoveg: str
    usage: dict | None
    leallas: str | None = None
    probak: int = 1


class _NincsAtiranyitas(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):               # a redirect could carry the key to another host
        return None


def _alap_nyito():
    return urllib.request.build_opener(_NincsAtiranyitas()).open


def url_ellenoriz(url: str) -> None:
    from urllib.parse import urlsplit
    r = urlsplit(url)
    if url != API_URL or r.scheme != "https" or r.hostname != API_HOST or r.port not in (None, 443):
        raise SzallitoHiba("refusing to send to a host other than " + API_HOST, True)


class HttpSzallito:
    """The only network code: POST to the fixed endpoint with the standard library. `nyito` and `alvas` are injectable
    for tests; the key lives only in this object and in the request header."""

    def __init__(self, kulcs: str, *, nyito=None, alvas=time.sleep, idokorlat: float = IDOKORLAT_S):
        self._kulcs = kulcs
        self._nyito = nyito or _alap_nyito()
        self._alvas = alvas
        self._idokorlat = idokorlat

    def __repr__(self) -> str:
        return "HttpSzallito(<key hidden>)"

    def _hiba(self, szoveg, vegzetes=False) -> SzallitoHiba:
        return SzallitoHiba(titkot_kiszed(szoveg, self._kulcs), vegzetes)

    def kuld(self, modell: str, rendszer: str, felhasznalo: str, max_tokens: int) -> Valasz:
        torzs = json.dumps({"model": modell, "max_tokens": int(max_tokens), "system": rendszer,
                            "messages": [{"role": "user", "content": felhasznalo}]}, ensure_ascii=False).encode("utf-8")
        if len(torzs) > MAX_KERES_BAJT:
            raise self._hiba("request too large", True)
        url_ellenoriz(API_URL)
        probak = 0
        utolso = "unknown error"
        while probak <= MAX_UJRA:
            probak += 1
            kerelem = urllib.request.Request(API_URL, data=torzs, method="POST", headers={
                "content-type": "application/json", "anthropic-version": API_VERSION, "x-api-key": self._kulcs,
                "accept": "application/json", "user-agent": "manifold-gen-szintetikus/1"})
            varakozas = None
            try:
                with self._nyito(kerelem, timeout=self._idokorlat) as v:
                    nyers = v.read(MAX_VALASZ_BAJT + 1)
                if len(nyers) > MAX_VALASZ_BAJT:
                    raise self._hiba("response too large", True)
                return self._ertelmez(nyers, probak)
            except SzallitoHiba:
                raise
            except urllib.error.HTTPError as e:
                kod = int(getattr(e, "code", 0) or 0)
                try:
                    leiras = self._hibatest(e.read(MAX_HIBA_BAJT))
                except Exception:               # noqa: BLE001 — the body is only a hint
                    leiras = ""
                with contextlib.suppress(Exception):
                    e.close()
                utolso = f"HTTP {kod}" + (f" ({leiras})" if leiras else "")
                if kod == 429 or 500 <= kod <= 599:
                    with contextlib.suppress(Exception):
                        varakozas = min(float(e.headers.get("retry-after")), 30.0)
                else:
                    msg = f"the API refused the request: {utolso}"
                    if kod in (401, 403):
                        msg += " (check the key and its permissions)"
                    raise self._hiba(msg, True) from None
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
                utolso = f"connection problem ({type(e).__name__})"
            except Exception as e:              # noqa: BLE001 — unexpected: report the type only, never the content
                raise self._hiba(f"unexpected transport error ({type(e).__name__})", True) from None
            if probak > MAX_UJRA:
                break
            self._alvas(varakozas if varakozas is not None else float(2 ** (probak - 1)))
        raise self._hiba(f"giving up after {probak} attempts: {utolso}")

    @staticmethod
    def _hibatest(nyers: bytes) -> str:
        try:
            e = json.loads(nyers.decode("utf-8", "replace")).get("error") or {}
            return f"{str(e.get('type') or '')[:40]}: {str(e.get('message') or '')[:160]}".strip(": ")
        except (ValueError, AttributeError):
            return ""

    def _ertelmez(self, nyers: bytes, probak: int) -> Valasz:
        try:
            d = json.loads(nyers.decode("utf-8"))
            tartalom = d["content"]
            szoveg = "".join(b.get("text", "") for b in tartalom if isinstance(b, dict) and b.get("type") == "text")
            usage = d.get("usage") if isinstance(d.get("usage"), dict) else None
            return Valasz(szoveg, usage, d.get("stop_reason"), probak)
        except (ValueError, KeyError, TypeError, AttributeError):
            raise self._hiba("the API answer could not be understood", True) from None


# ---------------------------------------------------------------------------------------------------- templates

SABLON_KULCSOK = {"nev", "cel", "modell_osztaly", "hivasok", "tetel_hivasonkent", "max_tokens", "alapertelmezett", "rendszer",
                  "felhasznalo", "valtozatossag", "tiltasok", "forras", "max_oldal"}
KOZOS_TILTASOK = (
    "Everything must be invented, neutral and generic: no real person, no real company or product tied to a person, no private "
    "note, no handwriting, no developer, file system or home-folder path, no URL, e-mail address, phone number, key or secret.",
    "Write in English only. Do not mention these rules or yourself. Answer with the requested JSON and nothing else.",
)
ISMERT_JELOLOK = ("<<tetel_db>>", "<<valtozat>>", "<<sorszam>>", "<<oldal_nev>>", "<<oldal_szoveg>>", "<<tiltott_cimek>>")


@dataclass
class Sablon:
    nev: str
    cel: str
    osztaly: str
    hivasok: int
    tetel_hivasonkent: int
    max_tokens: int
    alapertelmezett: bool
    rendszer: str
    felhasznalo: str
    valtozatossag: list
    tiltasok: list
    forras: str | None
    max_oldal: int
    hash: str
    ut: Path


def sablon_betolt(ut: Path) -> Sablon:
    try:
        nyers = Path(ut).read_bytes()
        s = tomllib.loads(nyers.decode("utf-8")).get("sablon") or {}
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        raise GenHiba(f"cannot read the template {Path(ut).name}", KILEPES_HASZNALAT) from None
    hibas = lambda m: GenHiba(f"template {Path(ut).name}: {m}", KILEPES_HASZNALAT)      # noqa: E731
    ismeretlen = set(s) - SABLON_KULCSOK
    if ismeretlen:
        raise hibas("unknown keys " + ", ".join(sorted(ismeretlen)))
    nev, cel = s.get("nev"), s.get("cel")
    if not isinstance(nev, str) or not AZON_RE.match(nev) or nev != Path(ut).stem:
        raise hibas("`nev` must equal the file name")
    if cel not in CELOK:
        raise hibas("`cel` must be one of " + ", ".join(CELOK))
    if s.get("modell_osztaly") not in ("olcso", "minoseg"):
        raise hibas("`modell_osztaly` is 'olcso' or 'minoseg'")
    forras = s.get("forras")
    if forras not in (None, "docs/user"):
        raise hibas("`forras` can only be 'docs/user'")
    if (cel == "doku") != (forras == "docs/user"):
        raise hibas("`forras = \"docs/user\"` belongs to (and only to) the doku template")
    ints = {}
    for k, lo, hi in (("hivasok", 1, 200), ("tetel_hivasonkent", 1, 50), ("max_tokens", 256, 16000)):
        v = s.get(k, 1 if k in ("tetel_hivasonkent",) else None)
        if not isinstance(v, int) or isinstance(v, bool) or not lo <= v <= hi:
            raise hibas(f"`{k}` must be an integer in {lo}..{hi}")
        ints[k] = v
    max_oldal = s.get("max_oldal", 0)
    if not isinstance(max_oldal, int) or isinstance(max_oldal, bool) or not 0 <= max_oldal <= 100:
        raise hibas("`max_oldal` must be 0..100")
    for k in ("rendszer", "felhasznalo"):
        if not isinstance(s.get(k), str) or not s[k].strip():
            raise hibas(f"`{k}` is required")
    for k in ("valtozatossag", "tiltasok"):
        v = s.get(k, [])
        if not isinstance(v, list) or not all(isinstance(x, str) and x.strip() for x in v):
            raise hibas(f"`{k}` must be a list of strings")
    if not s.get("valtozatossag"):
        raise hibas("`valtozatossag` needs at least one entry")
    if len(s["rendszer"]) + len(s["felhasznalo"]) > 20000:
        raise hibas("prompt too long")
    for t in re.findall(r"<<[a-z_]+>>", s["rendszer"] + s["felhasznalo"]):
        if t not in ISMERT_JELOLOK:
            raise hibas(f"unknown placeholder {t}")
    if tilos_talalat(s["rendszer"] + s["felhasznalo"]):
        raise hibas("the prompt contains a secret- or personal-data-shaped string")
    return Sablon(nev=nev, cel=cel, osztaly=s["modell_osztaly"], hivasok=ints["hivasok"], tetel_hivasonkent=ints["tetel_hivasonkent"],
                  max_tokens=ints["max_tokens"], alapertelmezett=bool(s.get("alapertelmezett", False)), rendszer=s["rendszer"],
                  felhasznalo=s["felhasznalo"], valtozatossag=list(s["valtozatossag"]), tiltasok=list(s.get("tiltasok", [])),
                  forras=forras, max_oldal=max_oldal, hash=hashlib.sha256(nyers).hexdigest(), ut=Path(ut))


def sablonok_betolt(mappa: Path = SABLON_MAPPA) -> dict[str, Sablon]:
    ki = {}
    for ut in sorted(Path(mappa).glob("*.toml")):
        s = sablon_betolt(ut)
        ki[s.nev] = s
    if not ki:
        raise GenHiba("no templates found", KILEPES_HASZNALAT)
    return ki


@dataclass
class Hivas:
    sablon: Sablon
    sorszam: int
    rendszer: str
    felhasznalo: str
    oldal: str | None = None


def _rendszer_szoveg(s: Sablon) -> str:
    szabalyok = list(KOZOS_TILTASOK) + s.tiltasok
    return s.rendszer.strip() + "\n\nHard rules:\n" + "\n".join(f"- {x}" for x in szabalyok)


def doku_oldalak(gyoker: Path, max_oldal: int) -> list[tuple[str, str]]:
    """The repository's own user-guide pages `(file name, text)`; pages with secret/personal-shaped content are skipped."""
    ki = []
    mappa = Path(gyoker) / "docs" / "user"
    if not mappa.is_dir():
        return ki
    for p in sorted(mappa.glob("*.md")):
        if not re.match(r"^[A-Z0-9\-]+\.md\Z", p.name) or p.is_symlink() or not p.is_file() or p.stat().st_size > 60_000:
            continue
        szoveg = p.read_text(encoding="utf-8", errors="replace")
        if tilos_talalat(szoveg):
            continue
        ki.append((p.name, szoveg))
        if max_oldal and len(ki) >= max_oldal:
            break
    return ki


def hivasok_terve(s: Sablon, gyoker: Path = REPO) -> list[Hivas]:
    rendszer = _rendszer_szoveg(s)
    ki = []
    if s.cel == "doku":
        for i, (nev, szoveg) in enumerate(doku_oldalak(gyoker, s.max_oldal or s.hivasok), 1):
            f = s.felhasznalo.replace("<<oldal_nev>>", nev).replace("<<oldal_szoveg>>", szoveg).replace("<<sorszam>>", str(i))
            ki.append(Hivas(s, i, rendszer, f, nev))
        return ki
    for i in range(1, s.hivasok + 1):
        f = (s.felhasznalo.replace("<<tetel_db>>", str(s.tetel_hivasonkent)).replace("<<sorszam>>", str(i))
             .replace("<<valtozat>>", s.valtozatossag[(i - 1) % len(s.valtozatossag)]))
        ki.append(Hivas(s, i, rendszer, f))
    return ki


# ---------------------------------------------------------------------------------------------------- validation of items

class Elutasit(Exception):
    """An item is rejected; the message is the stable reason."""


@dataclass
class Kontextus:
    gyoker: Path = REPO
    demo_utak: frozenset = frozenset()
    demo_cimek: frozenset = frozenset()
    matek: object = None                       # `kozos.matek` when importable (sympy present), else None

    @classmethod
    def epit(cls, gyoker: Path = REPO) -> "Kontextus":
        k = cls(gyoker=Path(gyoker))
        sys_path = list(sys.path)
        try:
            for p in (str(Path(gyoker)), str(Path(gyoker) / "modulok" / "eval")):
                if p not in sys.path:
                    sys.path.insert(0, p)
            try:
                from core import demo_tartalom
                utak = frozenset(demo_tartalom.jegyzetek(0))
                k.demo_utak = utak
                k.demo_cimek = frozenset(Path(u).stem.lower() for u in utak)
            except Exception:                  # noqa: BLE001 — the demo module is optional context
                pass
            try:
                from kozos import matek
                k.matek = matek
            except Exception:                  # noqa: BLE001 — sympy may be missing
                pass
        finally:
            sys.path[:] = sys_path
        return k


def _szoveg(d: dict, kulcs: str, lo: int, hi: int, *, egysoros: bool = True) -> str:
    v = d.get(kulcs)
    if not isinstance(v, str):
        raise Elutasit(f"schema: `{kulcs}` is not a string")
    if "\x00" in v or (egysoros and ("\n" in v or "\r" in v)):
        raise Elutasit(f"schema: `{kulcs}` has forbidden characters")
    if not lo <= len(v) <= hi:
        raise Elutasit(f"size: `{kulcs}` length {len(v)} not in {lo}..{hi}")
    return v


def _csak_kulcsok(d, engedett: set, kotelezo: set) -> None:
    if not isinstance(d, dict):
        raise Elutasit("schema: the item is not an object")
    extra, hiany = set(d) - engedett, kotelezo - set(d)
    if extra:
        raise Elutasit("schema: unexpected keys " + ",".join(sorted(str(x) for x in extra)[:5]))
    if hiany:
        raise Elutasit("schema: missing keys " + ",".join(sorted(hiany)))


def _lista(d: dict, kulcs: str, db_lo: int, db_hi: int, hossz_hi: int) -> list:
    v = d.get(kulcs)
    if not isinstance(v, list) or not db_lo <= len(v) <= db_hi:
        raise Elutasit(f"schema: `{kulcs}` must be a list of {db_lo}..{db_hi} strings")
    ki = []
    for x in v:
        if not isinstance(x, str) or not 1 <= len(x) <= hossz_hi or "\n" in x or "\x00" in x:
            raise Elutasit(f"schema: bad element in `{kulcs}`")
        if x in ki:
            raise Elutasit(f"schema: duplicate element in `{kulcs}`")
        ki.append(x)
    return ki


@dataclass
class Tiszta:
    """A validated item: the target-format payload, its dedup text, the human-language text (language check) and all strings."""
    tetel: dict
    kulcs: str
    emberi: str
    figyelmeztetes: list = field(default_factory=list)


def norm_kieg(n, ctx: Kontextus) -> Tiszta:
    _csak_kulcsok(n, {"elotte", "utana", "elfogadhato"}, {"elotte", "utana", "elfogadhato"})
    elotte, utana = _szoveg(n, "elotte", 8, 220), _szoveg(n, "utana", 0, 120)
    elf = _lista(n, "elfogadhato", 1, 6, 60)
    if "```" in elotte + utana or any(e in elotte for e in elf if len(e) > 2):
        raise Elutasit("schema: the answer already appears in the context")
    return Tiszta({"elotte": elotte, "utana": utana, "elfogadhato": elf}, elotte + "|" + utana, elotte + " " + utana)


MATEK_TEMAK = ("algebra", "fuggveny", "trigonometria", "exp_log", "sorozat", "koordinatageometria", "analizis",
               "valoszinuseg_kombinatorika")
_MATEK_ERTEK = re.compile(r"^[0-9a-zA-Z+\-*/^().,! ]{1,60}\Z")
_MATEK_INTERVALLUM = re.compile(r"^[\[(][0-9a-zA-Z+\-*/^().!\s]{1,24},[0-9a-zA-Z+\-*/^().!\s]{1,24}[\])]"
                                r"(?:\s*U\s*[\[(][0-9a-zA-Z+\-*/^().!\s]{1,24},[0-9a-zA-Z+\-*/^().!\s]{1,24}[\])])*\Z")
_MATEK_VALTOZO = re.compile(r"^[a-z]\Z")


def _matek_vart(v) -> dict:
    if not isinstance(v, dict):
        raise Elutasit("schema: `vart` is not an object")
    t = v.get("tipus")
    if t in ("szam", "kifejezes", "intervallum"):
        _csak_kulcsok(v, {"tipus", "ertek", "egysegek"}, {"tipus", "ertek"})
        e = _szoveg(v, "ertek", 1, 60)
        rx = _MATEK_INTERVALLUM if t == "intervallum" else _MATEK_ERTEK
        if not rx.match(e):
            raise Elutasit(f"schema: `ertek` is not in the machine syntax for '{t}'")
        ki = {"tipus": t, "ertek": e}
    elif t == "halmaz":
        _csak_kulcsok(v, {"tipus", "ertekek", "egysegek"}, {"tipus", "ertekek"})
        es = _lista(v, "ertekek", 1, 8, 60)
        if not all(_MATEK_ERTEK.match(e) for e in es):
            raise Elutasit("schema: `ertekek` is not in the machine syntax")
        ki = {"tipus": t, "ertekek": es}
    elif t == "par":
        _csak_kulcsok(v, {"tipus", "ertekek", "egysegek"}, {"tipus", "ertekek"})
        e = v.get("ertekek")
        if not isinstance(e, dict) or not 2 <= len(e) <= 4 or not all(
                isinstance(a, str) and _MATEK_VALTOZO.match(a) and isinstance(b, str) and _MATEK_ERTEK.match(b) for a, b in e.items()):
            raise Elutasit("schema: `ertekek` must map 2..4 variables to values")
        ki = {"tipus": t, "ertekek": dict(e)}
    else:
        raise Elutasit("schema: unknown answer type")
    if "egysegek" in v:
        ki["egysegek"] = _lista(v, "egysegek", 1, 3, 12)
    return ki


def _matek_onellenorzes(vart: dict, matek) -> str:
    """Whether the expected answer parses and matches itself (sympy via the shipped `kozos.matek`); text for the manifest."""
    t = vart["tipus"]
    if t == "halmaz":
        sor = "; ".join(f"x = {e}" for e in vart["ertekek"])
    elif t == "par":
        sor = "; ".join(f"{a} = {b}" for a, b in vart["ertekek"].items())
    else:
        sor = vart["ertek"]
    try:
        ok, indok = matek.ekvivalens(vart, sor)
    except Exception as e:                 # noqa: BLE001 — a parser failure is a rejection, not a crash
        raise Elutasit(f"schema: the expected answer does not parse ({type(e).__name__})") from None
    if not ok:
        raise Elutasit(f"schema: the expected answer does not match itself ({indok})")
    return "parsed"


def norm_matek(n, ctx: Kontextus) -> Tiszta:
    _csak_kulcsok(n, {"tema", "szoveg", "vart"}, {"tema", "szoveg", "vart"})
    if n.get("tema") not in MATEK_TEMAK:
        raise Elutasit("schema: unknown topic")
    szoveg = _szoveg(n, "szoveg", 20, 700)
    if szoveg.count("$") < 2 or szoveg.count("$") % 2:
        raise Elutasit("schema: the statement needs balanced $...$ maths")
    vart = _matek_vart(n.get("vart"))
    figy = []
    if ctx.matek is not None:
        figy.append("answer self-check: " + _matek_onellenorzes(vart, ctx.matek))
    else:
        figy.append("answer self-check skipped (no sympy): syntax only")
    figy.append("expected answer NOT independently verified: recompute before approving")
    return Tiszta({"tema": n["tema"], "szoveg": szoveg, "vart": vart}, szoveg, szoveg, figy)


KOD_TEMAK = ("ciklus_tomb", "rendezes_kereses", "dp", "graf", "szam_sztring")
KOD_FAJTAK = ("index", "tulcsordulas", "inicializalas", "alapeset", "ido", "feltetel", "sorrend", "egyeb")
_CPP_TILTOTT = re.compile(r"\b(?:system|popen|fork|vfork|exec[lv]?[pe]?|fopen|freopen|ifstream|ofstream|fstream|socket|connect|"
                          r"getenv|setenv|dlopen|asm|__asm__|signal|kill|ptrace|syscall|remove|rename|chdir|mmap)\s*[(<]|"
                          r"#\s*include\s*(?:<(?:fstream|filesystem|unistd\.h|sys/[^>]*|netinet/[^>]*|thread|future)>|\")|\bstd::filesystem\b|"
                          r"\b__builtin_trap\b|#\s*pragma\b")
_PY_IMPORT_OK = {"random", "math", "string", "itertools"}
_PY_TILTOTT_NEVEK = {"open", "exec", "eval", "compile", "__import__", "getattr", "setattr", "delattr", "globals", "locals", "vars",
                     "input", "breakpoint", "exit", "quit", "help"}


def _py_ellenoriz(forras: str) -> None:
    try:
        fa = ast.parse(forras)
    except SyntaxError:
        raise Elutasit("schema: `bemenet_py` is not valid Python") from None
    fuggvenyek = {}
    for csucs in ast.walk(fa):
        if isinstance(csucs, ast.Import):
            if any(a.name.split(".")[0] not in _PY_IMPORT_OK for a in csucs.names):
                raise Elutasit("safety: `bemenet_py` imports a module outside random/math/string/itertools")
        elif isinstance(csucs, ast.ImportFrom):
            if (csucs.module or "").split(".")[0] not in _PY_IMPORT_OK or csucs.level:
                raise Elutasit("safety: `bemenet_py` imports a module outside random/math/string/itertools")
        elif isinstance(csucs, ast.Name) and (csucs.id in _PY_TILTOTT_NEVEK or (csucs.id.startswith("__") and csucs.id.endswith("__"))):
            raise Elutasit(f"safety: `bemenet_py` uses `{csucs.id}`")
        elif isinstance(csucs, ast.Attribute) and csucs.attr.startswith("__"):
            raise Elutasit("safety: `bemenet_py` uses a dunder attribute")
    for csucs in fa.body:
        if isinstance(csucs, ast.FunctionDef):
            fuggvenyek[csucs.name] = len(csucs.args.args)
    if fuggvenyek.get("general") != 2 or fuggvenyek.get("ervenyes") != 1:
        raise Elutasit("schema: `bemenet_py` needs `general(rng, meret)` and `ervenyes(s)`")


def norm_kod(n, ctx: Kontextus) -> Tiszta:
    kulcsok = {"cim", "tema", "nehezseg", "idokorlat_s", "leiras_md", "ref_cpp", "lassu_cpp", "bemenet_py", "hibak"}
    _csak_kulcsok(n, kulcsok, kulcsok)
    cim = _szoveg(n, "cim", 4, 80)
    if n.get("tema") not in KOD_TEMAK:
        raise Elutasit("schema: unknown topic")
    if n.get("nehezseg") not in (1, 2, 3) or isinstance(n.get("nehezseg"), bool):
        raise Elutasit("schema: `nehezseg` is 1..3")
    ik = n.get("idokorlat_s")
    if not isinstance(ik, (int, float)) or isinstance(ik, bool) or not 0.5 <= ik <= 5:
        raise Elutasit("schema: `idokorlat_s` is 0.5..5")
    leiras = _szoveg(n, "leiras_md", 200, 6000, egysoros=False)
    if len(re.findall(r"^```teszt\b", leiras, re.M)) < 2 or "--- bemenet" not in leiras or "--- kimenet" not in leiras:
        raise Elutasit("schema: `leiras_md` needs at least two ```teszt blocks with '--- bemenet' / '--- kimenet'")
    for kulcs in ("ref_cpp", "lassu_cpp"):
        forras = _szoveg(n, kulcs, 80, 8000, egysoros=False)
        if "\r" in forras or "\t" in forras:
            raise Elutasit(f"schema: `{kulcs}` must use LF and spaces")
        if not re.search(r"\bint\s+main\s*\(", forras):
            raise Elutasit(f"schema: `{kulcs}` has no main()")
        if _CPP_TILTOTT.search(forras):
            raise Elutasit(f"safety: `{kulcs}` uses a forbidden construct")
    _py_ellenoriz(_szoveg(n, "bemenet_py", 40, 4000, egysoros=False))
    sorok = n["ref_cpp"].split("\n")
    hibak = n.get("hibak")
    if not isinstance(hibak, list) or len(hibak) != 3:
        raise Elutasit("schema: exactly three planted bugs are required")
    ki = []
    for i, h in enumerate(hibak, 1):
        _csak_kulcsok(h, {"id", "fajta", "sor", "eredeti", "csere", "magyarazat"}, {"id", "fajta", "sor", "eredeti", "csere", "magyarazat"})
        if h["id"] != f"h{i}" or h["fajta"] not in KOD_FAJTAK:
            raise Elutasit("schema: bug ids are h1..h3 and `fajta` is a known kind")
        s = h["sor"]
        if not isinstance(s, int) or isinstance(s, bool) or not 1 <= s <= len(sorok):
            raise Elutasit("schema: bug `sor` is outside the reference solution")
        eredeti, csere = _szoveg(h, "eredeti", 1, 200), _szoveg(h, "csere", 1, 200)
        if sorok[s - 1] != eredeti:
            raise Elutasit(f"schema: bug {h['id']}: line {s} of ref_cpp is not `eredeti`")
        if csere == eredeti or _CPP_TILTOTT.search(csere):
            raise Elutasit(f"schema: bug {h['id']}: bad replacement")
        ki.append({"id": h["id"], "fajta": h["fajta"], "sor": s, "eredeti": eredeti, "csere": csere,
                   "magyarazat": _szoveg(h, "magyarazat", 12, 300)})
    if len({h["sor"] for h in ki}) != 3:
        raise Elutasit("schema: the three bugs must be on three different lines")
    tiszta = {"cim": cim, "tema": n["tema"], "nehezseg": n["nehezseg"], "idokorlat_s": float(ik), "leiras_md": leiras,
              "ref_cpp": n["ref_cpp"], "lassu_cpp": n["lassu_cpp"], "bemenet_py": n["bemenet_py"], "hibak": ki}
    return Tiszta(tiszta, cim + "|" + n["ref_cpp"], cim + "\n" + leiras + "\n" + " ".join(h["magyarazat"] for h in ki),
                  ["static checks only: compile, run and freeze the evidence with modulok/eval/kod/keszit.py in the sandbox"])


_DEMO_UT = re.compile(r"^(?P<mappa>[A-Z][A-Za-z ]{2,24})/(?P<fajl>[A-Z0-9][A-Za-z0-9 ,'()&\-]{1,70})\.md\Z")
_WIKILINK = re.compile(r"(?<!!)\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")


def norm_demo(n, ctx: Kontextus) -> Tiszta:
    _csak_kulcsok(n, {"ut", "szoveg"}, {"ut", "szoveg"})
    ut = _szoveg(n, "ut", 8, 100)
    m = _DEMO_UT.match(ut)
    if not m:
        raise Elutasit("schema: `ut` must look like 'Folder/Note title.md'")
    if ctx.demo_utak and ut in ctx.demo_utak:
        raise Elutasit("duplicate: the note already exists in the demo workspace")
    if ctx.demo_cimek and m["fajl"].lower() in ctx.demo_cimek:
        raise Elutasit("duplicate: a demo note with this title exists")
    szoveg = _szoveg(n, "szoveg", 300, 6000, egysoros=False)
    if "\r" in szoveg or "![[" in szoveg or not re.search(r"^# \S", szoveg, re.M):
        raise Elutasit("schema: the note needs a '# Title' heading, LF line ends and no embeds")
    if szoveg.startswith("---\n") and "\n---\n" not in szoveg[4:]:
        raise Elutasit("schema: unterminated front matter")
    figy = []
    cimek = ctx.demo_cimek
    nem_oldott = sorted({t.strip() for t in _WIKILINK.findall(szoveg) if cimek and t.strip().lower() not in cimek})
    if nem_oldott:
        figy.append("links to notes outside the demo workspace: " + ", ".join(nem_oldott[:6]))
    return Tiszta({"ut": ut, "szoveg": szoveg}, ut, szoveg, figy)


DOKU_TIPUSOK = ("accuracy", "clarity", "missing", "consistency", "typo", "structure")


def norm_doku(n, ctx: Kontextus) -> Tiszta:
    _csak_kulcsok(n, {"oldal", "tipus", "hely", "javaslat"}, {"oldal", "tipus", "hely", "javaslat"})
    oldal = _szoveg(n, "oldal", 4, 60)
    if not re.match(r"^[A-Z0-9\-]+\.md\Z", oldal):
        raise Elutasit("schema: `oldal` is a docs/user page name")
    if n.get("tipus") not in DOKU_TIPUSOK:
        raise Elutasit("schema: unknown remark type")
    hely, javaslat = _szoveg(n, "hely", 2, 160), _szoveg(n, "javaslat", 12, 500)
    return Tiszta({"oldal": oldal, "tipus": n["tipus"], "hely": hely, "javaslat": javaslat}, oldal + "|" + hely + "|" + javaslat,
                  javaslat)


NORMALIZALOK = {"kiegeszites": norm_kieg, "matek": norm_matek, "kod": norm_kod, "demo": norm_demo, "doku": norm_doku}
MERET_HATAR = {"kiegeszites": 2_000, "matek": 4_000, "kod": 40_000, "demo": 16_000, "doku": 2_000}


def tetel_ellenoriz(cel: str, nyers, ctx: Kontextus) -> Tiszta:
    """Schema, size, secret / personal-data / path / URL and language checks for one item. Raises `Elutasit`."""
    t = NORMALIZALOK[cel](nyers, ctx)
    teljes = json.dumps(t.tetel, ensure_ascii=False)
    if len(teljes.encode("utf-8")) > MERET_HATAR[cel]:
        raise Elutasit("size: the item is too large")
    mind = _osszes_szoveg(t.tetel)
    if (talalat := tilos_talalat(mind)):
        raise Elutasit(talalat)
    if (ok := nem_angol_ok(mind)):
        raise Elutasit("language: " + ok)
    if (ok := angol_e(t.emberi)):
        raise Elutasit("language: " + ok)
    return t


def _osszes_szoveg(x) -> str:
    if isinstance(x, str):
        return x
    if isinstance(x, dict):
        return "\n".join(_osszes_szoveg(v) for v in x.values())
    if isinstance(x, (list, tuple)):
        return "\n".join(_osszes_szoveg(v) for v in x)
    return ""


def tetel_azon(cel: str, t: Tiszta) -> str:
    return f"{cel}-{normalizalt_hash(t.kulcs)[:10]}"


def tetel_hash(cel: str, tetel: dict) -> str:
    """Dedup hash of an already validated payload (the same text the generation step used)."""
    kulcs = {"kiegeszites": lambda d: d["elotte"] + "|" + d["utana"], "matek": lambda d: d["szoveg"],
             "kod": lambda d: d["cim"] + "|" + d["ref_cpp"], "demo": lambda d: d["ut"],
             "doku": lambda d: d["oldal"] + "|" + d["hely"] + "|" + d["javaslat"]}[cel](tetel)
    return normalizalt_hash(kulcs)


def osszegzes(cel: str, d: dict) -> str:
    return {"kiegeszites": lambda: f"...{d['elotte'][-40:]} [{d['elfogadhato'][0]}] {d['utana'][:20]}",
            "matek": lambda: d["szoveg"][:90], "kod": lambda: f"{d['cim']} ({d['tema']})", "demo": lambda: d["ut"],
            "doku": lambda: f"{d['oldal']}: {d['tipus']}: {d['hely'][:50]}"}[cel]()


def json_tombbol(szoveg: str) -> list:
    """The JSON objects of an answer: a whole array, or (truncated answer) every complete object after the first `[`."""
    s = szoveg.strip()
    m = re.match(r"^```(?:json)?\s*\n(.*?)(?:\n```\s*)?$", s, re.S)
    if m:
        s = m.group(1).strip()
    with contextlib.suppress(ValueError):
        d = json.loads(s)
        if isinstance(d, dict):
            vals = [v for v in d.values() if isinstance(v, list)]
            d = vals[0] if len(vals) == 1 else [d]
        return d if isinstance(d, list) else []
    i = s.find("[")
    if i < 0:
        return []
    dek, ki = json.JSONDecoder(), []
    i += 1
    while i < len(s):
        while i < len(s) and s[i] in " \t\r\n,":
            i += 1
        if i >= len(s) or s[i] != "{":
            break
        try:
            obj, i = dek.raw_decode(s, i)
        except ValueError:
            break
        ki.append(obj)
    return ki


# ---------------------------------------------------------------------------------------------------- generation run

@dataclass
class Opciok:
    sablonok: list = field(default_factory=list)
    szaraz: bool = False
    max_usd: float = ALAP_MAX_USD
    max_hivas: int = ALAP_MAX_HIVAS
    osszes_max_usd: float = ALAP_OSSZES_MAX_USD
    kulcs_env: bool = False
    modell_olcso: str = ALAP_OLCSO
    modell_minoseg: str = ALAP_MINOSEG
    futas_id: str | None = None
    gyoker: Path = REPO
    sablon_mappa: Path = SABLON_MAPPA
    arak_ut: Path = ARAK_UT


def terv(opc: Opciok, sablonok: dict[str, Sablon], arak: dict[str, Ar]) -> dict:
    """Selected templates, number of calls and worst-case cost (no network, no key)."""
    valasztott = [sablonok[n] for n in opc.sablonok] if opc.sablonok else [s for s in sablonok.values() if s.alapertelmezett]
    modellek = {"olcso": modell_ellenoriz(opc.modell_olcso, arak), "minoseg": modell_ellenoriz(opc.modell_minoseg, arak)}
    sorok, ossz_hivas, ossz_usd = [], 0, 0.0
    for s in valasztott:
        hivasok = hivasok_terve(s, opc.gyoker)
        modell = modellek[s.osztaly]
        usd = sum(legrosszabb_usd(arak[modell], bemenet_becsles(h.rendszer, h.felhasznalo), s.max_tokens) for h in hivasok)
        sorok.append({"sablon": s.nev, "cel": s.cel, "modell": modell, "hivasok": len(hivasok), "legrosszabb_usd": round(usd, 4)})
        ossz_hivas += len(hivasok)
        ossz_usd += usd
    return {"sablonok": sorok, "hivasok": ossz_hivas, "legrosszabb_usd": round(ossz_usd, 4), "modellek": modellek,
            "belefer": ossz_usd <= opc.max_usd + 1e-12 and ossz_hivas <= opc.max_hivas,
            "valasztott": valasztott}


def uj_futas_id() -> str:
    return _dt.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)


def jovahagyas_ir(mappa: Path, futas: str, elfogadott: list[dict]) -> None:
    sorok = [f"# Review file for run {futas}.",
             "# Set `jovahagyva = true` for every item you accept (items are in tetelek.jsonl), then run:",
             f"#   python3 tools/gen_szintetikus.py --atvesz {futas} --cel <target>", ""]
    for t in elfogadott:
        sorok += ["[[tetel]]", f"id = {toml_szoveg(t['azonosito'])}", f"cel = {toml_szoveg(t['cel'])}", "jovahagyva = false",
                  f"osszegzes = {toml_szoveg(osszegzes(t['cel'], t['tetel']))}", ""]
    atomi_ir(mappa / "jovahagyas.toml", "\n".join(sorok))


def _jsonl_hozzaad(ut: Path, sorok: list[dict]) -> None:
    if not sorok:
        return
    ut.parent.mkdir(parents=True, exist_ok=True)
    with open(ut, "a", encoding="utf-8") as f:
        for s in sorok:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")


def futtat(opc: Opciok, *, szallito=None, kimenet=print) -> int:
    """One generation run. `szallito` is injectable (tests); without it the key is read and the HTTPS transport is built."""
    arak = arak_betolt(opc.arak_ut)
    sablonok = sablonok_betolt(opc.sablon_mappa)
    for n in opc.sablonok:
        if n not in sablonok:
            raise GenHiba(f"unknown template: {n} (available: {', '.join(sablonok)})", KILEPES_HASZNALAT)
    t = terv(opc, sablonok, arak)
    if not t["valasztott"]:
        raise GenHiba("no template selected", KILEPES_HASZNALAT)
    kimenet(f"plan: {t['hivasok']} call(s), worst-case cost ${t['legrosszabb_usd']:.4f} "
            f"(run limit ${opc.max_usd:.2f} / {opc.max_hivas} calls; lifetime limit ${opc.osszes_max_usd:.2f})")
    for s in t["sablonok"]:
        kimenet(f"  {s['sablon']:<16} -> {s['cel']:<12} {s['modell']:<22} {s['hivasok']:>3} call(s)  worst ${s['legrosszabb_usd']:.4f}")
    if opc.szaraz:
        kimenet("dry run: no network was used, no key was read." + ("" if t["belefer"] else "  WARNING: this plan does NOT fit the limits."))
        return KILEPES_OK if t["belefer"] else KILEPES_KOLTSEG
    if not t["belefer"]:
        kimenet("the plan exceeds the limits; select fewer templates or raise --max-usd / --max-hivas (the run stops at the limit).")
    futas = futas_azon_ellenoriz(opc.futas_id) if opc.futas_id is not None else uj_futas_id()
    mappa = futas_mappa(opc.gyoker, futas, letezik=False)
    kulcs = None
    if szallito is None:
        kulcs = kulcs_olvas(opc.kulcs_env)
        szallito = HttpSzallito(kulcs)
    mappa.mkdir(parents=True)
    (mappa / "tetelek.jsonl").touch()
    ior = Koltsegor(mappa, Path(opc.gyoker) / KIMENET_GYOKER_REL / "osszes_koltseg.json", arak, opc.max_usd, opc.max_hivas,
                    opc.osszes_max_usd)
    ctx = Kontextus.epit(opc.gyoker)
    manifest = {"futas_id": futas, "keszult": _most(), "allapot": "running", "modellek": t["modellek"],
                "sablonok": {}, "tetelek": [], "elutasitott_db": 0, "megjegyzesek": []}
    elfogadott: list[dict] = []
    lathato: dict[str, set] = {}
    allapot_kod, ok_szoveg = KILEPES_OK, "complete"

    def ment_manifest(allapot: str) -> None:
        manifest["allapot"] = allapot
        manifest["koltseg"] = {k: ior.allapot[k] for k in ("osszeg_usd", "hivasok", "http_probak", "bemenet_tok", "kimenet_tok", "modellek")}
        manifest["tetelek"] = [x["azonosito"] for x in elfogadott]
        manifest["frissitve"] = _most()
        json_ir(mappa / "manifest.json", manifest)

    ment_manifest("running")
    try:
        for s in t["valasztott"]:
            modell = t["modellek"][s.osztaly]
            sm = manifest["sablonok"][s.nev] = {"sha256": s.hash, "cel": s.cel, "modell": modell, "hivasok_terv": 0,
                                                "hivasok": 0, "elfogadott": 0, "elutasitott": 0, "hibas_valasz": 0}
            hivasok = hivasok_terve(s, opc.gyoker)
            sm["hivasok_terv"] = len(hivasok)
            lathato.setdefault(s.cel, set())
            for h in hivasok:
                try:
                    worst = ior.foglal(modell, bemenet_becsles(h.rendszer, h.felhasznalo), s.max_tokens)
                except KoltsegHiba as e:
                    allapot_kod, ok_szoveg = e.kod, "stopped by the cost guard: " + str(e)
                    break
                try:
                    v = szallito.kuld(modell, h.rendszer, h.felhasznalo, s.max_tokens)
                except GenHiba as e:
                    ior.felold(worst)
                    allapot_kod, ok_szoveg = e.kod, "transport failure: " + titkot_kiszed(e, kulcs)
                    break
                ior.rogzit(worst, modell, v.usage, v.probak)
                sm["hivasok"] += 1
                nyers = json_tombbol(v.szoveg)
                if not nyers:
                    sm["hibas_valasz"] += 1
                uj, elutasitva = [], []
                for i, elem in enumerate(nyers):
                    try:
                        if s.cel == "doku" and isinstance(elem, dict):
                            elem = {**elem, "oldal": h.oldal}            # the page is known from the request, not from the answer
                        tiszta = tetel_ellenoriz(s.cel, elem, ctx)
                        hash_ = normalizalt_hash(tiszta.kulcs)
                        if hash_ in lathato[s.cel]:
                            raise Elutasit("duplicate")
                        lathato[s.cel].add(hash_)
                        uj.append({"azonosito": tetel_azon(s.cel, tiszta), "cel": s.cel, "sablon": s.nev, "modell": modell,
                                   "hivas": h.sorszam, "tetel": tiszta.tetel, "megjegyzesek": tiszta.figyelmeztetes})
                    except Elutasit as e:
                        elutasitva.append({"sablon": s.nev, "hivas": h.sorszam, "sorszam": i, "ok": str(e)[:200],
                                           "reszlet": titkot_kiszed(json.dumps(elem, ensure_ascii=False)[:300], kulcs)})
                _jsonl_hozzaad(mappa / "tetelek.jsonl", uj)
                _jsonl_hozzaad(mappa / "elutasitott.jsonl", elutasitva)
                elfogadott += uj
                sm["elfogadott"] += len(uj)
                sm["elutasitott"] += len(elutasitva)
                manifest["elutasitott_db"] += len(elutasitva)
                jovahagyas_ir(mappa, futas, elfogadott)
                ment_manifest("running")
            if allapot_kod != KILEPES_OK:
                break
    except KeyboardInterrupt:
        allapot_kod, ok_szoveg = KILEPES_HIBA, "interrupted"
    finally:
        if elfogadott or not (mappa / "jovahagyas.toml").exists():
            jovahagyas_ir(mappa, futas, elfogadott)
        if any(x["cel"] == "doku" for x in elfogadott):
            doku_jelentes_ir(mappa, elfogadott)
        ment_manifest(ok_szoveg)
    a = ior.allapot
    kimenet(f"run {futas}: {ok_szoveg}; {a['hivasok']} call(s), cost ${a['osszeg_usd']:.4f}; "
            f"{len(elfogadott)} item(s) kept, {manifest['elutasitott_db']} rejected")
    kimenet(f"output: {KIMENET_GYOKER_REL / futas}")
    return allapot_kod


def doku_jelentes_ir(mappa: Path, elfogadott: list[dict]) -> None:
    """A human-readable suggestions report; the pages themselves are never modified."""
    oldalak: dict[str, list] = {}
    for t in elfogadott:
        if t["cel"] == "doku":
            oldalak.setdefault(t["tetel"]["oldal"], []).append(t["tetel"])
    sorok = ["# Documentation review suggestions", "", "Generated remarks; nothing in docs/user was changed. Verify each before acting.", ""]
    for oldal, lista in sorted(oldalak.items()):
        sorok += [f"## {oldal}", ""]
        sorok += [f"- **{x['tipus']}** ({x['hely']}): {x['javaslat']}" for x in lista]
        sorok.append("")
    atomi_ir(mappa / "doku_jelentes.md", "\n".join(sorok))


# ---------------------------------------------------------------------------------------------------- adoption

# target → (file relative to the repository, list key in the file, how a stored item looks)
CELHELYEK = {
    "kiegeszites": (Path("modulok/eval/kiegeszites/arany_en.json"), "tetel"),
    "matek": (Path("modulok/eval/matek/arany_en.json"), "feladatok"),
    "kod": (Path("modulok/eval/kod/arany_en.json"), "feladatok"),
    "demo": (Path("core/demo_kiegeszito.json"), "jegyzetek"),
}


def tarolt_tetel(cel: str, azon: str, tetel: dict) -> dict:
    sy = azon.split("-", 1)[1]
    if cel == "kiegeszites":
        return {"id": "sy-" + sy, **tetel}
    if cel == "matek":
        return {"id": "sy-" + sy, "tema": tetel["tema"], "forras": "synthetic (model-generated, not independently verified)",
                "szoveg": tetel["szoveg"], "vart": tetel["vart"]}
    if cel == "kod":
        return {"id": "sy-" + sy, "forras": "synthetic (model-generated, static checks only)", **tetel}
    return {"id": "sy-" + sy, **tetel}


def git_tiszta(gyoker: Path, rel: Path) -> bool:
    """True when git sees no change (and no untracked file) at the target path; any git problem counts as not clean."""
    try:
        p = subprocess.run(["git", "-C", str(gyoker), "status", "--porcelain", "--", str(rel)], capture_output=True, text=True,
                           timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False
    return p.returncode == 0 and not p.stdout.strip()


def jovahagyott_azonok(futas_ut: Path, mind: bool, cel: str, tetelek: dict[str, dict]) -> list[str]:
    if mind:
        return [a for a, t in tetelek.items() if t["cel"] == cel]
    try:
        d = tomllib.loads((futas_ut / "jovahagyas.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        raise GenHiba("jovahagyas.toml is missing or invalid", KILEPES_HASZNALAT) from None
    ki = []
    for x in d.get("tetel") or []:
        if not isinstance(x, dict) or not isinstance(x.get("id"), str) or x.get("jovahagyva") not in (True, False):
            raise GenHiba("jovahagyas.toml: every [[tetel]] needs `id` and a boolean `jovahagyva`", KILEPES_HASZNALAT)
        if x["id"] not in tetelek:
            raise GenHiba(f"jovahagyas.toml names an unknown item: {x['id']}", KILEPES_HASZNALAT)
        if x["jovahagyva"] is True and tetelek[x["id"]]["cel"] == cel:
            ki.append(x["id"])
    return ki


def atvesz(futas: str, cel: str, *, mind: bool = False, szaraz: bool = False, gyoker: Path = REPO, kimenet=print,
           tiszta_e=git_tiszta) -> int:
    """Copy the APPROVED items of a run into the repository (no network). Writes nothing when the target is not clean or
    anything fails validation; never changes an approval state."""
    if cel not in ATVEHETO_CELOK:
        raise GenHiba("--cel must be one of " + ", ".join(ATVEHETO_CELOK), KILEPES_HASZNALAT)
    gyoker = Path(gyoker)
    ut = futas_mappa(gyoker, futas, letezik=True)
    tetelek: dict[str, dict] = {}
    try:
        for sor in (ut / "tetelek.jsonl").read_text(encoding="utf-8").splitlines():
            if sor.strip():
                x = json.loads(sor)
                tetelek[x["azonosito"]] = x
    except (OSError, ValueError, KeyError, TypeError):
        raise GenHiba("tetelek.jsonl is missing or invalid", KILEPES_HASZNALAT) from None
    azonok = jovahagyott_azonok(ut, mind, cel, tetelek)
    if not azonok:
        kimenet("nothing approved for this target: nothing to do.")
        return KILEPES_OK
    ctx = Kontextus.epit(gyoker)
    rel, kulcs = CELHELYEK[cel]
    cel_ut = gyoker / rel
    uj_tetelek, hashek = [], set()
    for a in azonok:
        x = tetelek[a]
        try:
            tiszta = tetel_ellenoriz(cel, x["tetel"], ctx)         # re-validate: the staging file may have been edited by hand
        except Elutasit as e:
            raise GenHiba(f"validation failed for {a}: {e}; nothing was written", KILEPES_HIBA) from None
        if tetel_azon(cel, tiszta) != a:
            raise GenHiba(f"{a}: the item no longer matches its identifier; nothing was written", KILEPES_HIBA)
        h = tetel_hash(cel, tiszta.tetel)
        if h in hashek:
            continue
        hashek.add(h)
        uj_tetelek.append((a, h, tarolt_tetel(cel, a, tiszta.tetel)))
    letezo, letezo_hashek = None, set()
    if cel_ut.exists():
        try:
            letezo = json.loads(cel_ut.read_text(encoding="utf-8"))
            if not isinstance(letezo, dict) or not isinstance(letezo.get(kulcs), list):
                raise ValueError
        except (OSError, ValueError):
            raise GenHiba(f"{rel} exists but is not a valid candidate set; nothing was written", KILEPES_HIBA) from None
        if letezo.get("allapot") != "vazlat":
            raise GenHiba(f"{rel} is not a draft (allapot={letezo.get('allapot')!r}); refusing to change an approved set", KILEPES_HIBA)
        for k in letezo[kulcs]:
            with contextlib.suppress(Exception):
                letezo_hashek.add(tetel_hash(cel, {kk: vv for kk, vv in k.items() if kk not in ("id", "forras")}))
    ujak = [(a, tt) for a, h, tt in uj_tetelek if h not in letezo_hashek]
    atugrott = len(uj_tetelek) - len(ujak)
    if letezo is None:
        verzio, kimeneti = "gen-1", {"verzio": "gen-1", "allapot": "vazlat", "nyelv": "en", "forras": "synthetic",
                                     "jovahagyva": None, "keszult": _most(), "jelolt_futasok": [futas], kulcs: [tt for _, tt in ujak]}
    else:
        m = re.match(r"^gen-(\d+)\Z", str(letezo.get("verzio")))
        verzio = f"gen-{int(m.group(1)) + 1}" if m else "gen-1"
        kimeneti = dict(letezo)                                        # approval fields stay exactly as they were
        kimeneti.update(verzio=verzio, frissitve=_most(), jelolt_futasok=list(letezo.get("jelolt_futasok") or []) + [futas])
        kimeneti[kulcs] = list(letezo[kulcs]) + [tt for _, tt in ujak]
    kimenet(f"adopt run {futas} -> {rel}")
    kimenet(f"  approved: {len(azonok)}; new: {len(ujak)}; already present / duplicate: {atugrott}; version {verzio}; "
            f"state stays '{kimeneti['allapot']}'")
    for a, tt in ujak[:20]:
        kimenet("  + " + a + ": " + osszegzes(cel, {k: v for k, v in tt.items() if k not in ("id", "forras")}))
    if not ujak:
        kimenet("nothing new to write.")
        return KILEPES_OK
    if szaraz:
        kimenet("dry run: nothing was written.")
        return KILEPES_OK
    if not cel_ut.parent.is_dir():
        raise GenHiba(f"target folder {rel.parent} does not exist", KILEPES_HIBA)
    if not tiszta_e(gyoker, rel):
        raise GenHiba(f"the target {rel} is not clean in git (uncommitted changes, or git is unavailable); nothing was written",
                      KILEPES_HIBA)
    json_ir(cel_ut, kimeneti)
    json_ir(ut / "atvett.json", {"cel": cel, "fajl": str(rel), "verzio": verzio, "azonositok": [a for a, _ in ujak], "ido": _most()})
    kimenet(f"written: {rel}")
    return KILEPES_OK


# ---------------------------------------------------------------------------------------------------- command line

def _pozitiv_float(s: str) -> float:
    try:
        v = float(s)
    except ValueError:
        raise argparse.ArgumentTypeError("a number is required") from None
    if not math.isfinite(v) or v <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return v


def _pozitiv_int(s: str) -> int:
    try:
        v = int(s)
    except ValueError:
        raise argparse.ArgumentTypeError("an integer is required") from None
    if v <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return v


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="gen_szintetikus.py", description=__doc__.split("\n\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sablon", action="append", default=[], metavar="NAME", help="template to run (repeatable; default: all default ones)")
    p.add_argument("--szaraz", action="store_true", help="dry run: no network, no key; print the plan and the worst-case cost")
    p.add_argument("--max-usd", type=_pozitiv_float, default=ALAP_MAX_USD, help=f"budget of this run (default {ALAP_MAX_USD:.2f})")
    p.add_argument("--max-hivas", type=_pozitiv_int, default=ALAP_MAX_HIVAS, help=f"call limit of this run (default {ALAP_MAX_HIVAS})")
    p.add_argument("--osszes-max-usd", type=_pozitiv_float, default=ALAP_OSSZES_MAX_USD,
                   help=f"lifetime budget over all runs (default {ALAP_OSSZES_MAX_USD:.2f})")
    p.add_argument("--kulcs-env", action="store_true", help="read the key from ANTHROPIC_API_KEY instead of the Keychain")
    p.add_argument("--modell-olcso", default=ALAP_OLCSO, help=f"model for cheap tasks (default {ALAP_OLCSO})")
    p.add_argument("--modell-minoseg", default=ALAP_MINOSEG, help=f"model for quality-critical tasks (default {ALAP_MINOSEG})")
    p.add_argument("--futas-id", default=None, help="run folder name (default: timestamp + random)")
    p.add_argument("--atvesz", metavar="RUN_ID", help="adopt the approved items of a run into the repository (no network)")
    p.add_argument("--cel", choices=ATVEHETO_CELOK, help="target set for --atvesz")
    p.add_argument("--mind-jovahagy", action="store_true", help="with --atvesz: approve every kept item of the target")
    return p


def main(argv=None) -> int:
    a = parser().parse_args(argv)
    try:
        if a.atvesz:
            if not a.cel:
                raise GenHiba("--atvesz needs --cel", KILEPES_HASZNALAT)
            return atvesz(a.atvesz, a.cel, mind=a.mind_jovahagy, szaraz=a.szaraz)
        if a.cel or a.mind_jovahagy:
            raise GenHiba("--cel / --mind-jovahagy belong to --atvesz", KILEPES_HASZNALAT)
        return futtat(Opciok(sablonok=a.sablon, szaraz=a.szaraz, max_usd=a.max_usd, max_hivas=a.max_hivas,
                             osszes_max_usd=a.osszes_max_usd, kulcs_env=a.kulcs_env, modell_olcso=a.modell_olcso,
                             modell_minoseg=a.modell_minoseg, futas_id=a.futas_id))
    except GenHiba as e:
        print("error: " + titkot_kiszed(e), file=sys.stderr)
        return e.kod
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return KILEPES_HIBA
    except Exception as e:              # noqa: BLE001 — no traceback: it could carry request data; the type is enough
        print(f"error: unexpected {type(e).__name__}", file=sys.stderr)
        return KILEPES_HIBA


if __name__ == "__main__":
    sys.exit(main())
