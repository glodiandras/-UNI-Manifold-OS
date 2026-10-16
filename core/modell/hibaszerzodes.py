"""Az AI-funkciók közös hibaszerződése (F6; az 5. audit §5 vége).

Minden AI-funkció hibatörzse a meglévő (funkció-specifikus) `kod`/`param` mellé egy `ai` mezőt kap:

    "ai": {"kod": "nincs_kalibralt" | "nincs_telepitve" | "csak_tavol" | "nincs_ai_runtime" | "worker_hiba",
           "feladat": "<router-feladat>", "funkcio": "<a manifeszt [funkcio.*] kulcsa vagy null>", "param": {...}}

A felület ebből és a manifeszt `funkcio → feladatok` táblájából generálja a szöveget és a gombokat („Install a model”, „Test a
model”): a funkció saját `kod`-ja visszafelé kompatibilis marad, a közös jelentést az `ai.kod` hordozza.
"""
from __future__ import annotations

KODOK = ("nincs_kalibralt", "nincs_telepitve", "csak_tavol", "nincs_ai_runtime", "worker_hiba")
_TAVOL = ("csak tartós tétlenségben", "távol-keret", "tavolra_var")


def osztalyoz(e: BaseException | None) -> str:
    """Egy worker-/routerhiba (`kliens.KliensHiba`, `RoutingHiba`, …) közös kódja."""
    if e is None:
        return "nincs_kalibralt"
    adat = getattr(e, "adat", None) or {}
    kod = getattr(e, "kod", None)
    szoveg = str(e)
    if isinstance(kod, str) and kod in KODOK:
        return kod
    if adat.get("nincs_kalibralt") or type(e).__name__ in ("RoutingHiba", "NincsMasikCsalad", "NincsModell"):
        return "csak_tavol" if any(x in szoveg for x in _TAVOL) else "nincs_kalibralt"
    if kod == 503 and (adat.get("kapcsolat") or "nem indult" in szoveg or "nem fut modell-worker" in szoveg):
        return "nincs_ai_runtime"
    return "worker_hiba"


def ai_mezo(feladat: str, e: BaseException | None = None, funkcio: str | None = None, kod: str | None = None,
            **param) -> dict:
    """A hibatörzs `ai` mezője (a `HttpError(..., ai=ai_mezo(...))` hívásnak)."""
    return {"kod": kod if kod in KODOK else osztalyoz(e), "feladat": feladat, "funkcio": funkcio,
            "param": {k: v for k, v in param.items() if v is None or isinstance(v, (str, int, float, bool))}}
