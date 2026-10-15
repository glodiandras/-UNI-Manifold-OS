"""A modellréteg beállításai a `config/os.toml`-ból: `[modellgazda]`, `[keret]`, `[aktivitas]`, `[ho]`,
`[router]`, `[meres]` és a regiszter (`[modellek.*]`, L30). A beépített alapértékek a legacy
`calibration.json → helyi_modell` értékei (L31). Felülírás: `MANIFOLD_MODELL_KERET_GB` (a keret,
L24), `MANIFOLD_MODELL_ZAR` (a zár útja, L23).

A mérés kérés-beállításai (C18.1) a modell szakaszában (`gondolkodas`, `gondolkodas_token`, …) és a
`[modellek.<m>.meres.<feladat>]` alszakaszban élnek; a feloldás a `core/modell/eval.py` dolga."""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from pathlib import Path

from ..config import Config

ALAP_GAZDA = {"port": 0, "cache_gb": 0.25, "prefill_lepes": 256, "min_szabad_szazalek": 20,
              "tartalek_szazalek": 5, "helyreallas_mp": 30, "zar": "{state}/modell.lock", "probalkozas": 3,
              "tetlen_urites_perc": 10}
ALAP_KERET = {"munka": 5.0, "tavol": 9.0}
ALAP_AKTIVITAS = {"aktiv_mp": 120, "tavol_perc": 15, "rendszer_tetlenseg": True}
ALAP_HO = {"bekapcsolva": True, "min_token": 32, "alap_minta": 5, "ablak": 5, "kuszob": 0.7, "hutes_mp": 120}
# a lockban lévő futtatók (config/requirements.lock); a többihez a betöltő érthető hibát ad
FUTTATOK = ("mlx-vlm", "mlx-lm", "sentence-transformers", "mlx-whisper", "mlx-audio", "transformers")
# a mérés kérés-beállításának kulcsai (C18.1): a modell szakaszában és a `meres.<feladat>` alszakaszban
MERES_KULCSOK = ("gondolkodas", "gondolkodas_token", "max_tokens_szorzo", "repetition_penalty",
                 "repetition_context_size", "temperature")
ALAP_MERES = {"ervenyes_kuszob": 0.10}


class RegiszterHiba(KeyError):
    """Ismeretlen modell (nincs a `[modellek]` alatt)."""

    def __str__(self) -> str:
        return str(self.args[0]) if self.args else "ismeretlen modell"


@dataclass(frozen=True)
class Modell:
    nev: str
    repo: str
    futtato: str
    csucs_gb: float | None
    kepessegek: tuple = ()
    feladat: tuple = ()
    minta: tuple = ()
    csucs_mert: bool = False
    konvertalas: bool = False
    gondolkodo: bool = False               # a válasz előtt gondolkodik (`<think>`), külön token-keret kell (C18.1)
    meres: tuple = ()                      # ((feladat | "*", ((kulcs, érték), …)), …): a mérés kérés-beállításai
    meres_kihagy: str = ""                 # nem üres: a mérési parancslista kihagyja, az indoklással (K32, előpróba)
    meres_kihagy_feladat: tuple = ()       # ((feladat, indok), …): csak ezek a feladatok maradnak ki a mérésből
    revizio: str = ""                      # a HF-repó rögzített commitja (C19, T141): ezt a pillanatképet tölti a betöltő
    csalad: str = ""                       # a modellcsalád a modellkártyáról (C24b): a második vélemény ebből zár ki

    def meres_beallitas(self, feladat: str) -> dict:
        """A modell mérés-beállítása egy feladatra: a modell szintje, rajta a feladat alszakasza."""
        d = dict(self.meres)
        return {**dict(d.get("*", ())), **dict(d.get(feladat, ()))}


@dataclass
class Beallitas:
    gazda: dict
    keretek: dict
    aktivitas: dict
    ho: dict
    router: dict
    modellek: dict[str, Modell]
    zar: Path
    run: Path
    models: Path
    router_db: Path
    keret_felulirva: float | None = None
    extra: dict = field(default_factory=dict)
    meres: dict = field(default_factory=lambda: dict(ALAP_MERES))

    def keret_gb(self, nev: str | float | None) -> float:
        """A keret GB-ban: név (`munka`/`tavol`), szám, vagy None → munka. A környezeti felülírás
        (`MANIFOLD_MODELL_KERET_GB`) mindennél erősebb (L24)."""
        if self.keret_felulirva is not None:
            return self.keret_felulirva
        return ervenyes_keret(self.keretek, nev)

    def modell(self, nev_vagy_repo: str) -> Modell:
        if nev_vagy_repo in self.modellek:
            return self.modellek[nev_vagy_repo]
        for m in self.modellek.values():
            if m.repo == nev_vagy_repo:
                return m
        raise RegiszterHiba(f"ismeretlen modell: {nev_vagy_repo} (config/os.toml [modellek])")

    def feladat_szabaly(self, feladat: str) -> dict:
        return dict((self.router.get("feladat") or {}).get(feladat) or {})


def _kihagy(ertek) -> dict:
    """A `meres_kihagy` kulcs: szöveg = az egész modell kimarad, tábla = csak a megnevezett feladatok (K32)."""
    if isinstance(ertek, dict):
        return {"meres_kihagy_feladat": tuple(sorted((str(f), str(i).strip()) for f, i in ertek.items()))}
    return {"meres_kihagy": str(ertek or "").strip()}


def _meres(nev: str, m: dict) -> tuple:
    """A modell mérés-kulcsai fagyasztva; ismeretlen kulcs a `meres.<feladat>` alatt: hiba."""
    def fagy(d: dict, hol: str) -> tuple:
        rossz = sorted(set(d) - set(MERES_KULCSOK))
        if rossz:
            raise ValueError(f"[modellek.{nev}{hol}]: ismeretlen mérés-kulcs: {', '.join(rossz)}")
        return tuple(sorted(d.items()))
    ki = [("*", fagy({k: v for k, v in m.items() if k in MERES_KULCSOK}, ""))]
    for f, d in (m.get("meres") or {}).items():
        ki.append((f, fagy(dict(d), f".meres.{f}")))
    return tuple(ki)


def ervenyes_keret(keretek: dict, nev) -> float:
    """A keret GB-ban (`munka` | `tavol` | véges, pozitív szám; None → munka). A NaN, a végtelen, a ≤ 0, a logikai érték és
    az ismeretlen név `ValueError` (M3, C19: a worker 400-zal utasítja el)."""
    if nev is None:
        return float(keretek["munka"])
    if isinstance(nev, bool):
        raise ValueError(f"érvénytelen keret: {nev!r} (munka | tavol | pozitív szám)")
    if isinstance(nev, str) and nev in keretek:
        return float(keretek[nev])
    try:
        gb = float(nev)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"ismeretlen keret: {nev} (munka | tavol | szám)") from exc
    if not math.isfinite(gb) or gb <= 0:
        raise ValueError(f"érvénytelen keret: {nev!r} (véges, pozitív GB kell)")
    return gb


def betolt(cfg: Config, environ: dict | None = None) -> Beallitas:
    env = os.environ if environ is None else environ
    gazda = {**ALAP_GAZDA, **cfg.section("modellgazda")}
    modellek = {}
    for nev, m in cfg.section("modellek").items():
        cs = m.get("csucs_gb", m.get("becsult_gb"))
        modellek[nev] = Modell(nev=nev, repo=m["repo"], futtato=m.get("futtato", "mlx-vlm"),
                               csucs_gb=float(cs) if cs is not None else None,
                               kepessegek=tuple(m.get("kepessegek", ())), feladat=tuple(m.get("feladat", ())),
                               minta=tuple(m.get("minta", ())), csucs_mert=bool(m.get("csucs_mert")),
                               konvertalas=bool(m.get("konvertalas")), gondolkodo=bool(m.get("gondolkodo")),
                               meres=_meres(nev, m), revizio=str(m.get("revizio") or ""),
                               csalad=str(m.get("csalad") or "").strip(),
                               **_kihagy(m.get("meres_kihagy")))
    zar = env.get("MANIFOLD_MODELL_ZAR") or cfg.expand(str(gazda["zar"]))
    keret_env = env.get("MANIFOLD_MODELL_KERET_GB")
    return Beallitas(gazda=gazda, keretek={**ALAP_KERET, **cfg.section("keret")},
                     aktivitas={**ALAP_AKTIVITAS, **cfg.section("aktivitas")}, ho={**ALAP_HO, **cfg.section("ho")},
                     router=dict(cfg.section("router")), modellek=modellek, zar=Path(zar), run=cfg.path("run"),
                     models=cfg.path("models"), router_db=cfg.path("router_db"),
                     keret_felulirva=ervenyes_keret({}, keret_env) if keret_env else None,
                     meres={**ALAP_MERES, **cfg.section("meres")})
