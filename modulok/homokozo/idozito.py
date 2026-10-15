"""Puha időkorlát a homokozó gyermekében: `setitimer` + SIGALRM, egymásba ágyazható.

A feladat egészére a gyermek tesz korlátot, egy lépésre (pl. egy sor megoldáshalmaza) a hívó szűkebbet; a belső
korlát lejárta után a külső hátralévő ideje visszaáll. A kivétel `BaseException`, hogy a nem megbízható kód
`except Exception`-je ne nyelje el; a szülő kemény korlátja (SIGKILL) ettől függetlenül él.
Csak a fő szálban működik (a jelkezelő ott fut).
"""
from __future__ import annotations

import signal
import time
from contextlib import contextmanager


class Idotullepes(BaseException):
    pass


def _kezelo(_jel, _keret):
    raise Idotullepes()


@contextmanager
def korlatozva(mp: float):
    """A blokk legfeljebb `mp` másodpercig fut, különben `Idotullepes`. A külső korlát nem hosszabbodik meg."""
    elozo_kezelo = signal.signal(signal.SIGALRM, _kezelo)
    kulso, _ = signal.getitimer(signal.ITIMER_REAL)
    indul = time.monotonic()
    sajat = mp if not kulso else min(mp, kulso)
    signal.setitimer(signal.ITIMER_REAL, max(sajat, 0.001))
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, elozo_kezelo)
        if kulso:
            maradek = kulso - (time.monotonic() - indul)
            signal.setitimer(signal.ITIMER_REAL, max(maradek, 0.001))      # a külső lejárt: azonnal szól
