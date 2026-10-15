"""A modellréteg core-oldali végpontjai az útvonal-regiszterben (C11a): ML nélkül, csak az `App` állapotát adják."""
from __future__ import annotations


def utvonalak(r) -> None:
    r.get("/api/modell", lambda k: k.app.modell_allapot())

    def modellek(k):
        from .attekintes import attekintes
        return attekintes(k.app.cfg)
    r.get("/api/vezerlo/modellek", modellek)          # C19: a vezérlő Modellek szakasza (csak olvas)

    def aktivitas(k):
        k.app.aktivitas.jel()
        return {"ok": True}
    r.post("/api/aktivitas", aktivitas)
