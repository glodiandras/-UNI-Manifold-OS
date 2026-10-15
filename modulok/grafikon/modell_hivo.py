"""A ```plot modell-ágának worker-kötése (C35b; CLAUDE.md 28(g), 56(b), 59(d) és 72. javasolt döntés, D9).

    Hivo(cfg, modell=None) — a `modell_ag.ModellHivas` (`(prompt, max_tokens) → szöveg`) a modell-workeren át

**Lusta**: a worker-kapcsolat és a router-döntés az első híváskor jön létre — a képlet nélküli vagy csak `biztos` képletű jegyzet
a workerhez nem nyúl. **D9**: alapból a `grafikon` router-feladat kalibrált modellje (`POST /router/valaszt`; a keretet a worker
az aktivitásból dönti: munka-keret → a legjobb oda férő kalibrált sor, `qwen35_4b`; távol-keret → a legjobb). Ha nincs ilyen, vagy a
jobb modell a távol-keretre vár, a hívás `ModellNemElerheto` (a jegyzet később újra sorra kerül). A **kifejezett** modell (`modell=`)
próba: a worker `proba: true`-t ad vissza, a gépi írás jele ezt hordozza (D9).

A kérés-beállítás (gondolkodás, token-keret) a regiszterből jön, a mérés szabályával (`core.modell.eval.keres_beallitas`, a `grafikon`
feladat): a mért és az éles kérés beállítása ugyanaz. A hívó attribútumai (`kalibralt`, `jel`) az utolsó hívás után érvényesek;
a `jel` a gépi-írás `modell` mezője (`core/gepi_kliens.modell_jel`).
"""
from __future__ import annotations

from .modell_ag import ModellNemElerheto

FELADAT = "grafikon"


class Hivo:
    def __init__(self, cfg, modell: str | None = None, mod: str | None = None, kliens=None, gepi=None):
        self.cfg, self.modell, self.mod = cfg, modell, mod
        self.kalibralt = False
        self.jel: dict | None = None
        self.hivas = 0
        self._kliens, self._gepi = kliens, gepi
        self._b = None
        self._u: str | None = None
        self._nev: str | None = None

    # -- lusta kapcsolat
    def _elokeszit(self) -> None:
        if self._u is not None:
            return
        from core.modell import beallitas as B
        from core.modell import kliens
        kl = self._kliens or kliens
        try:
            u = kl.url(self.cfg)
        except kl.KliensHiba as e:
            raise ModellNemElerheto(f"nem fut modell-worker: {e}") from None
        b = B.betolt(self.cfg)
        if self.modell is not None:
            try:
                b.modell(self.modell)
            except B.RegiszterHiba as e:
                raise ModellNemElerheto(str(e)) from None
            self._nev, self.kalibralt = self.modell, False
        else:
            try:
                dont = kl.keres(u, "/router/valaszt", {"feladat": FELADAT})
            except kl.KliensHiba as e:
                if e.kod == 409:
                    raise ModellNemElerheto(f"a `{FELADAT}` feladatra nincs kalibrált modell (D9): {e}") from None
                raise ModellNemElerheto(f"a router nem válaszolt: {e}") from None
            if not dont.get("modell"):
                raise ModellNemElerheto(f"a `{FELADAT}` modellje most nem futhat: {dont.get('indok') or 'a távol-keretre vár'}")
            self._nev, self.kalibralt = dont["modell"], True
        self._b, self._u = b, u

    def __call__(self, prompt: str, max_tokens: int) -> str:
        self._elokeszit()
        from core import gepi_kliens
        from core.modell import eval as E
        from core.modell import kliens
        kl = self._kliens or kliens
        k = E.keres_beallitas(self._b, self._b.modell(self._nev), FELADAT,
                              {"tipus": "chat", "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens})
        uzenetek = k.pop("messages")
        k.pop("tipus", None)
        try:
            r = kl.chat(self._u, uzenetek, feladat=FELADAT, modell=self._nev if self.modell else None, mod=self.mod, **k)
        except kl.KliensHiba as e:
            if e.kod in (409, 503):                     # nincs kalibrált modell / most nem fér a keretbe / a worker nem elérhető
                raise ModellNemElerheto(f"a modell-worker most nem tud válaszolni: {e}") from None
            raise
        self.hivas += 1
        self.jel = (self._gepi or gepi_kliens).modell_jel(r)
        if self.modell:
            self.jel["proba"] = True
        return r["choices"][0]["message"]["content"]
