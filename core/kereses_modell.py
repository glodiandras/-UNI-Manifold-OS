"""A hibrid keresés és a „Kérdezz a vaulttól” modell-kötése a workeren át (C25b modellfele; 58. döntés).

A core modellt nem tölt be (§4): a három hívható a worker végpontjait hívja, a modellt a router választja (D9: élesben a
feladatra kalibrált modell), a betöltő tölti be.

- `WorkerBeagyazo` — `(szövegek, fajta) → vektorok` a `/v1/embeddings`-en (`feladat = "beagyazas"`). A neve a router
  döntése (`/router/valaszt`), és **minden válasznál ellenőrzött**: ha a worker más modellel válaszolt (a router közben
  átállt), a hívás hibát dob, így egy vektortárba két modell vektorai nem keveredhetnek (a tár modell-kulcsa, C25b-mag).
  Előtag: a C19 a `beagyazas` kalibrációját előtag nélkül mérte, ezért itt sincs (`ELOTAG_VERZIO`; más szabály = más
  modell-kulcs = a vektortár újraépül, 2. audit T154).
- `WorkerReranker` — `(kérdés, dokumentumok) → pontok` a `/v1/rerank`-en (`feladat = "rerank"`).
- `WorkerModell` — a vault-válasz nyelvi modellje (`feladat = "szoveg"`): tokenfolyam a `/v1/chat/stream`-en; a
  fogyasztó bezárásakor a kapcsolat bomlik, és a worker a következő tokennél megáll. A válasz `proba` jele a worker
  döntése: élesben csak kalibrált modell fut, a `kalibralt` mező a router-tábla szerint (D9).

A mód (`mod`): a felhasználó kérdése és keresése `interaktiv`, a vektorindex építése `auto` (aktív használatkor szünetel, M3).
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Callable, Iterator

from .modell import kliens

ELOTAG_VERZIO = "nincs-v1"           # a beágyazott szöveg előtag nélkül (a C19 kalibrációjával azonosan)
KOTEG = 16


class ModellValtozott(RuntimeError):
    """A worker más beágyazóval válaszolt, mint amelyre a kötés szól (a router közben átállt)."""


def router_modell(u: str, feladat: str, keret: str = "munka") -> str | None:
    """A router döntése (száraz futás, betöltés nélkül): a feladat modelljének neve, vagy `None`."""
    try:
        r = kliens.keres(u, "/router/valaszt", {"feladat": feladat, "keret": keret}, timeout=10)
    except kliens.KliensHiba:
        return None
    return r.get("modell") if not r.get("var_tavolra") else None


class WorkerBeagyazo:
    def __init__(self, url: Callable[[], str], nev: str, dim: int = 0, mod: str = "interaktiv",
                 feladat_id: str | None = None, koteg: int = KOTEG, keret: str | None = None):
        self.url, self.nev, self._dim, self.mod, self.feladat_id, self.koteg = url, nev, int(dim), mod, feladat_id, koteg
        self.keret = keret                        # a kérés keretje (csak szűkíthet, M3)
        self.elotag = ELOTAG_VERZIO
        self.utolso_memoria: dict | None = None

    @property
    def dim(self) -> int:
        """A vektorok hossza; ismeretlenül egy próba-beágyazás adja (a vektortár modell-kulcsa már az első írás előtt
        a valódi dimenziót kapja — a 0 utólag „másik modellnek” látszana, és a tár újraépülne)."""
        if not self._dim:
            self(["dimenzió"], "dokumentum")
        return self._dim

    def mas_moddal(self, mod: str, feladat_id: str | None = None) -> "WorkerBeagyazo":
        return WorkerBeagyazo(self.url, self.nev, self._dim, mod, feladat_id, self.koteg, self.keret)

    def __call__(self, szovegek: list[str], fajta: str) -> list[list[float]]:
        if fajta not in ("kerdes", "dokumentum"):
            raise ValueError(f"ismeretlen fajta: {fajta}")
        ki: list[list[float]] = []
        for i in range(0, len(szovegek), self.koteg):
            body = {"input": list(szovegek[i:i + self.koteg]), "feladat": "beagyazas", "mod": self.mod}
            if self.feladat_id:
                body["feladat_id"] = self.feladat_id
            if self.keret is not None:
                body["keret"] = self.keret
            r = kliens.keres(self.url(), "/v1/embeddings", body)
            if r.get("modell") != self.nev:
                raise ModellValtozott(f"a worker {r.get('modell')} beágyazóval válaszolt, a kötés {self.nev}")
            self.utolso_memoria = r.get("memoria")
            ki.extend(d["embedding"] for d in r["data"])
        if ki and not self._dim:
            self._dim = len(ki[0])
        if any(len(v) != self._dim for v in ki):
            raise ValueError("a beágyazó vektorainak hossza eltér")
        return ki


class WorkerReranker:
    def __init__(self, url: Callable[[], str], mod: str = "interaktiv"):
        self.url, self.mod = url, mod
        self.nev: str | None = None

    def __call__(self, kerdes: str, dokumentumok: list[str]) -> list[float]:
        r = kliens.keres(self.url(), "/v1/rerank", {"query": kerdes, "documents": list(dokumentumok),
                                                   "feladat": "rerank", "mod": self.mod})
        self.nev = r.get("modell")
        return [float(x["relevance_score"]) for x in sorted(r["results"], key=lambda x: x["index"])]


class WorkerModell:
    """A vault-válasz modellje: `(prompt, max_tokens) → tokenek` (folyam). A `nev` és a `proba` a folyam végén
    ismert (a worker `vege` eseménye)."""

    def __init__(self, url: Callable[[], str], feladat: str = "szoveg", mod: str = "interaktiv",
                 timeout: float = 600, keret: str | None = None, proba_modell: str | None = None):
        """`keret`: a kérés keretje (csak szűkíthet, M3); `proba_modell`: kifejezett modell, csak próbaként (D9) — a mérés
        használja, élesben a router választ."""
        self.url, self.feladat, self.mod, self.timeout = url, feladat, mod, timeout
        self.keret, self.proba_modell = keret, proba_modell
        self.nev: str | None = None
        self.proba: bool | None = None
        self.utolso: dict = {}

    def __call__(self, prompt: str, max_tokens: int) -> Iterator[str]:
        # a gondolkodás ki: a `szoveg` kalibrációja gondolkodás nélkül mért (31(b)), és a JSON-soros válasz első szava így jön
        # leghamarabb (a nem gondolkodó modell sablonja a jelet figyelmen kívül hagyja)
        body = {"messages": [{"role": "user", "content": prompt}], "feladat": self.feladat, "mod": self.mod,
                "max_tokens": int(max_tokens), "temperature": 0.0, "gondolkodas": False}
        if self.keret is not None:
            body["keret"] = self.keret
        if self.proba_modell:
            body.update(model=self.proba_modell, proba=True)
        return self._folyam(body)

    def _folyam(self, body: dict) -> Iterator[str]:
        for e in chat_folyam(self.url(), body, self.timeout):
            if e.get("tipus") == "token":
                yield e.get("szoveg", "")
            elif e.get("tipus") == "vege":
                self.nev, self.proba, self.utolso = e.get("modell"), bool(e.get("proba")), e
            elif e.get("tipus") == "hiba":
                raise kliens.KliensHiba(int(e.get("kod") or 500), str(e.get("hiba") or "a generálás hibával állt meg"))


def chat_folyam(u: str, body: dict, timeout: float = 600) -> Iterator[dict]:
    """A worker `/v1/chat/stream` NDJSON-eseményei. A generátor bezárása a kapcsolatot bontja: a worker a következő
    tokennél észleli (az írás hibája), és a generálás megáll."""
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(u.rstrip("/") + "/v1/chat/stream", data=data, method="POST",
                                 headers={"X-Manifold": kliens.titok(u), "Content-Type": "application/json"})
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        try:
            adat = json.loads(e.read() or b"{}")
        except ValueError:
            adat = {}
        finally:
            e.close()
        raise kliens.KliensHiba(e.code, adat.get("hiba") or str(e), adat) from None
    except (urllib.error.URLError, OSError) as e:
        raise kliens.KliensHiba(503, f"a modell-worker nem érhető el: {e}") from None
    try:
        for sor in r:
            sor = sor.strip()
            if sor:
                yield json.loads(sor)
    finally:
        r.close()
