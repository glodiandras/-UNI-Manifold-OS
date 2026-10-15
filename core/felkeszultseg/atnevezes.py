"""A tracker útvonalainak átnevezés-követése (C28a, T063) — **olvasáskor**, a `tr_*` táblák módosítása nélkül.

A tracker (`tr_aktiv`, `tr_karakter`, `tr_esemeny`) a **kiíráskori** útvonalat tárolja; a jegyzet átnevezése vagy
áthelyezése után a régi sorok a régi úton maradnak, így a témánkénti tanult idő szétesne. A követés a vault
pillanatkép-tárolójának átnevezés-commitjaiból épül (`git log -M --diff-filter=R --name-status`, a tracker legkorábbi
napja óta): a 2.0 saját átnevezése, annak **visszavonása** (revert-commit, amely visszanevezi a fájlt) és a külső
szerkesztés is így látszik. A lánc A→B→C és az A→B→A is helyes: egy jegyzet minden korábbi és mostani útvonala egy
halmaz. Ismert korlát: a 100%-nál (a git `-M` küszöbénél) kisebb hasonlóságú átnevezés+szerkesztés kimaradhat.

A térkép a tároló HEAD-jére és a kezdő napra gyorsítótárazva; nincs tároló → üres térkép és figyelmeztetés.
"""
from __future__ import annotations

import unicodedata
from datetime import date, timedelta

from .. import frame

_GYORSITOTAR: dict[str, tuple[tuple[str, str], "Terkep"]] = {}     # a tároló git-könyvtára → ((HEAD, kezdő nap), térkép)
_REK = "\x1e"


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


class Terkep:
    def __init__(self, atnevezesek=(), figyelmeztetes: str | None = None):
        self.figyelmeztetes = figyelmeztetes
        self._aliasok: dict[str, set[str]] = {}
        for regi, uj in atnevezesek:                       # időrendben: a régi név halmaza átmegy az újra
            halmaz = self._aliasok.pop(regi, set()) | {regi}
            self._aliasok.setdefault(uj, set()).update(halmaz)

    def korabbi(self, ut: str) -> list[str]:
        """Az `ut` jegyzet korábbi útvonalai (az `ut` nélkül), rendezve."""
        return sorted(self._aliasok.get(ut, set()) - {ut})

    def aliasok(self, ut: str) -> set[str]:
        """Az `ut` és minden korábbi útvonala: a tracker sorait ezekre kell összeadni."""
        return {ut} | self._aliasok.get(ut, set())

    def jelenlegi(self, ut: str) -> str:
        """Egy (akár korábbi) útvonal mostani neve (C33, T180: a tracker jegyzet-listája a mostani úton csoportosít)."""
        if not hasattr(self, "_jelen"):
            self._jelen = {regi: most for most, regiek in self._aliasok.items() for regi in regiek}
            for most in self._aliasok:
                self._jelen[most] = most
        return self._jelen.get(ut, ut)


def _atnevezesek(kimenet: str) -> list[tuple[str, str]]:
    ki = []
    for rec in kimenet.split(_REK):
        if not rec.strip("\n\0"):
            continue
        _, _, farok = rec.partition("\0")
        mezok = farok.lstrip("\n").split("\0")
        i = 0
        while i < len(mezok):
            statusz = mezok[i]
            if statusz[:1] in ("R", "C") and i + 2 < len(mezok):
                if statusz[:1] == "R":
                    ki.append((_nfc(mezok[i + 1]), _nfc(mezok[i + 2])))
                i += 3
            else:
                i += 2 if statusz else 1
    return ki


def terkep(cfg, kezdet_nap: str | None) -> Terkep:
    """A `kezdet_nap` (ÉÉÉÉ-HH-NN, a tracker legkorábbi napja) óta történt átnevezések térképe. `None` → üres térkép."""
    if not kezdet_nap:
        return Terkep()
    repo = frame.live_repos(cfg).get("vault")
    if repo is None:
        return Terkep(figyelmeztetes="a vault pillanatkép-tárolója nem érhető el: az átnevezés előtti útvonalak nem követhetők")
    try:
        head = repo.git("rev-parse", "--verify", "-q", "HEAD", check=False)
        if head.returncode != 0:
            return Terkep()
        kulcs = (head.stdout.strip(), kezdet_nap)
        tarolt = _GYORSITOTAR.get(str(repo.git_dir))
        if tarolt and tarolt[0] == kulcs:
            return tarolt[1]
        tol = (date.fromisoformat(kezdet_nap) - timedelta(days=1)).isoformat()
        p = repo.git("log", f"--since={tol} 00:00:00", "--reverse", "-M", "--diff-filter=R", "--name-status", "-z",
                     f"--format={_REK}%H")
        t = Terkep(_atnevezesek(p.stdout))
    except Exception as e:                        # noqa: BLE001 — a követés hibája nem akaszthatja a becslést
        return Terkep(figyelmeztetes=f"az átnevezés-követés nem érhető el: {e}")
    _GYORSITOTAR[str(repo.git_dir)] = (kulcs, t)
    return t
