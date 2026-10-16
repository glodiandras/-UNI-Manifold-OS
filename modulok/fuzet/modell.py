"""A füzetlánc modellhívásai a workeren át (a modellt csak a modellgazda tölti).

Élesben a router dönt (`feladat`: `fuzet_fejezet`, `fuzet_valaszto`, `ocr_kezi`): csak kalibrált modell fut. Kifejezett modell
(`--olvaso`, `--valaszto`, `--atirat`) csak próbában: a worker `proba: true`-val válaszol, és a gépi írás ezt csak a klónra engedi.
A kérés a mérés beállítását kapja (`core.modell.eval.keres_beallitas`: ismétlés-büntetés, gondolkodás, token-szorzó), hogy a
kalibrált beállítás és az éles kérés ne térjen el. A válaszok fotónként gyorsítótárban élnek (`{fuzet}/valaszok/`): egy megállított
kör onnan folytatódik, és az ellenőrző kör sem kérdez újra (a kulcs a fotó, a fajta, a modell és a prompt ujjlenyomata).
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from core.modell import beallitas as B
from core.modell import kliens
from core.modell.eval import keres_beallitas


class NincsModell(RuntimeError):
    """A feladatra nincs kalibrált modell, és kifejezett (próba) modell sincs megadva."""


def _nincs_modell(feladat: str, indok: str) -> NincsModell:
    """Az egyetlen szöveg, amellyel a lánc megáll, ha a feladatnak nincs kalibrált modellje (akár a router előzetes döntése, akár a
    worker 409-es válasza mondja)."""
    ok = f" ({indok})" if indok and "kalibrált modell" not in indok else ""
    return NincsModell(f"a(z) „{feladat}” feladatra nincs kalibrált modell{ok}: élesben nem fut; próbához adj meg egy "
                       "modellnevet (a Beállítások › AI listájából) és --proba-t")


def _nincs_kalibralt(e: Exception) -> bool:
    """A worker 409-es `nincs_kalibralt` válasza (a megszakítás szintén 409, de nem ez)."""
    return getattr(e, "kod", None) == 409 and bool((getattr(e, "adat", None) or {}).get("nincs_kalibralt"))


class Modellek:
    def __init__(self, cfg, kifejezett: dict[str, str] | None = None, u: str | None = None):
        self.cfg = cfg
        self.kifejezett = {k: v for k, v in (kifejezett or {}).items() if v}
        self._u = u
        self._b = None
        self._dontes: dict[str, str] = {}

    def url(self) -> str:
        if self._u is None:
            self._u = kliens.url(self.cfg)
        return self._u

    def beallitas(self):
        if self._b is None:
            self._b = B.betolt(self.cfg)
        return self._b

    def modell_nev(self, feladat: str) -> str:
        """A feladat modellje: a kifejezett (próba), különben a router döntése (száraz futás a workeren)."""
        if feladat in self.kifejezett:
            return self.kifejezett[feladat]
        if feladat not in self._dontes:
            try:
                d = kliens.keres(self.url(), "/router/valaszt", {"feladat": feladat})
            except kliens.KliensHiba as e:
                if _nincs_kalibralt(e):
                    raise _nincs_modell(feladat, str(e)) from None
                raise
            if not d.get("modell"):
                raise _nincs_modell(feladat, d.get("indok") or "a router nem választott")
            self._dontes[feladat] = d["modell"]
        return self._dontes[feladat]

    def kerdez(self, feladat: str, prompt: str, kepek: list[str] | None = None, max_tokens: int = 256,
               beallitas_feladat: str | None = None) -> tuple[str, dict]:
        """→ (a válasz szövege, a gépi írás modell-jele). `beallitas_feladat`: a mérés-beállítás kulcsa, ha más, mint a feladat
        (a forgatás-próba a `fuzet_fejezet` modelljén fut, a `fuzet_forgatas` mérés beállításával)."""
        nev = self.modell_nev(feladat)
        m = self.beallitas().modell(nev)
        keres = {"messages": [{"role": "user", "content": prompt}], "max_tokens": int(max_tokens)}
        if kepek:
            keres["images"] = [str(k) for k in kepek]
        k = keres_beallitas(self.beallitas(), m, beallitas_feladat or feladat, keres)
        extra = {x: k[x] for x in ("images", "max_tokens", "temperature", "gondolkodas", "repetition_penalty",
                                   "repetition_context_size") if x in k}
        try:
            r = kliens.chat(self.url(), k["messages"], feladat=feladat, modell=self.kifejezett.get(feladat), **extra)
        except kliens.KliensHiba as e:
            # a router döntése és a chat közben a kalibráció elveszhet: a worker 409-e is „nincs modell” — a lánc egyszer áll meg, nem fotónként hibázik
            if _nincs_kalibralt(e):
                raise _nincs_modell(feladat, str(e)) from None
            raise
        szoveg = r["choices"][0]["message"]["content"]
        return szoveg, {"feladat": r.get("feladat") or feladat, "modell": r.get("modell") or nev, "proba": bool(r.get("proba"))}


class Gyorsitotar:
    """A modell válaszai fotónként: `{fuzet}/valaszok/<fajta>/<sha256>.json` (tiszta függvény-eredmény, nem döntési állapot)."""

    def __init__(self, cfg):
        self.d = cfg.path("fuzet") / "valaszok"

    @staticmethod
    def lenyomat(*reszek) -> str:
        return hashlib.sha1(json.dumps(reszek, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]

    def olvas(self, fajta: str, sha: str, lenyomat: str) -> dict | None:
        p = self.d / fajta / f"{sha}.json"
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return r if r.get("lenyomat") == lenyomat else None

    def ir(self, fajta: str, sha: str, lenyomat: str, adat: dict) -> dict:
        p = self.d / fajta / f"{sha}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        r = {**adat, "lenyomat": lenyomat}
        tmp = p.with_name(f".{p.name}.{os.getpid()}.manifold-tmp")
        tmp.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, p)
        return r
