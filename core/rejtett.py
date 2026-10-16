"""A vault-bejárások közös kihagyási szabálya (F3-DESIGN §3.6, I6): a `.manifold` (a munkatér beállításai és állapota,
benne a D9-próbaklónok teljes vault-másolataival) ugyanúgy láthatatlan, mint az `.obsidian`, a `.trash` és a `.git`.

Minden vault-bejáró innen veszi a listát (index, linkfeloldás, figyelő, bináris napló, kártya-szinkron, videó-egyezés …),
így egy új rejtett mappa egy helyen kerül be, és egyik bejáró sem marad le róla."""
from __future__ import annotations

KIHAGYOTT_MAPPAK = frozenset({".obsidian", ".trash", ".git", ".manifold", "node_modules"})

# A `node_modules`-t a v2 bináris-naplója és média-egyezése NEM hagyta ki (a vaultban írható mappa: `vaultio.norm_path` csak a pontos
# szakaszt tiltja, az Obsidian is látja): az I6 (a `.manifold` láthatatlansága) ezt nem szűkítheti — ezek a bejárók a listát a
# `node_modules` nélkül kapják (a leltár és a médiaindex egyezése a v2-vel).
MEDIA_KIHAGYOTT_MAPPAK = KIHAGYOTT_MAPPAK - {"node_modules"}

# A zárolandó útvonalak (`csatolmany.kuka`) a v2-ben minden fájlt felölelnek (`rglob`): csak a munkatér mappáját (állapot, próbaklónok,
# nem a felhasználó fájljai) hagyjuk ki.
MUNKATER_MAPPA = ".manifold"


def kihagyott(nev: str) -> bool:
    """A mappa (egy útszakasz neve) a vault-bejárásból kimarad-e."""
    return nev in KIHAGYOTT_MAPPAK


def metsz(almappak: list[str]) -> list[str]:
    """`os.walk` almappa-listájának helyben metszése (a kihagyott mappákba a bejárás nem lép be); ugyanazt a listát adja."""
    almappak[:] = [m for m in almappak if m not in KIHAGYOTT_MAPPAK]
    return almappak


def media_metsz(almappak: list[str]) -> list[str]:
    """Mint a `metsz`, de a `MEDIA_KIHAGYOTT_MAPPAK` listával (a `node_modules` bejárása marad): a bináris napló és a média-egyezés."""
    almappak[:] = [m for m in almappak if m not in MEDIA_KIHAGYOTT_MAPPAK]
    return almappak


def metsz_munkater(almappak: list[str]) -> list[str]:
    """Mint a `metsz`, de csak a munkatér mappáját (`.manifold`) hagyja ki: a zárolandó útvonalak bejárása (`csatolmany.kuka`)."""
    almappak[:] = [m for m in almappak if m != MUNKATER_MAPPA]
    return almappak
