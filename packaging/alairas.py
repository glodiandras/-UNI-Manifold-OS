"""Aláírás és notarizáció (F9; P8, PLAN §7 „Aláírás”) — OPCIÓ, a kiadást végző ember indítja.

Módok:
  nincs      nem nyúl az aláíráshoz (fejlesztői/teszt-build; a héj eredeti aláírásának erőforrás-pecsétje ekkor érvénytelen,
             helyben, karantén nélkül az app így is indul);
  adhoc      `codesign --sign -` (P8 első kör): minden Mach-O belülről kifelé, végül az app; Gatekeeper alatt a felhasználó a
             Rendszerbeállítások › Adatvédelem és biztonság › „Megnyitás mégis” úton engedélyezi;
  identitas  Developer ID: a tanúsítvány NEVE a `MANIFOLD_SIGN_IDENTITY` (vagy a régi `MOS_ALAIRAS_IDENTITAS`) környezeti
             változóból, a kulcs a felhasználó kulcskarikájában marad. `--options runtime --timestamp` + `entitlements.plist`.
Notarizáció (csak `identitas` mellett): `xcrun notarytool submit <dmg> --keychain-profile $MANIFOLD_NOTARY_PROFILE --wait`, majd
`xcrun stapler staple <dmg>`. A profilt a felhasználó egyszer hozza létre (`xcrun notarytool store-credentials`); hitelesítő
adat a repóban nincs, a szkript nem kér és nem ír ki jelszót.

A terv (`terv`) tiszta függvény: a tesztek a parancsokat ellenőrzik, valódi aláírás nélkül.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from csomag_kozos import CSOMAG_MAPPA, CsomagHiba, Futtato, futtat, macho

MODOK = ("nincs", "adhoc", "identitas")
ENTITLEMENTS = CSOMAG_MAPPA / "entitlements.plist"
IDENTITAS_VALTOZOK = ("MANIFOLD_SIGN_IDENTITY", "MOS_ALAIRAS_IDENTITAS")
NOTARY_PROFIL_VALTOZO = "MANIFOLD_NOTARY_PROFILE"
KOTEG = 200                         # ennyi fájl egy `codesign` hívásban


@dataclass
class AlairasTerv:
    mod: str
    identitas: str
    parancsok: list[list[str]] = field(default_factory=list)
    machok: int = 0


def identitas_kornyezetbol(env: dict | None = None) -> str:
    env = os.environ if env is None else env
    for k in IDENTITAS_VALTOZOK:
        if env.get(k):
            return env[k]
    return ""


def machok(app: Path) -> list[Path]:
    """Az app összes Mach-O-ja a fő futtatható NÉLKÜL, mélység szerint csökkenő sorrendben (belülről kifelé)."""
    fo = app / "Contents" / "MacOS"
    ki = [p for p in app.rglob("*") if macho(p) and p.parent != fo]
    return sorted(ki, key=lambda p: (-len(p.relative_to(app).parts), str(p)))


def terv(app: Path, mod: str, *, identitas: str = "", entitlements: Path = ENTITLEMENTS) -> AlairasTerv:
    if mod not in MODOK:
        raise CsomagHiba("alairas_mod", f"ismeretlen aláírási mód: {mod} ({' | '.join(MODOK)})")
    t = AlairasTerv(mod, identitas)
    if mod == "nincs":
        return t
    if mod == "identitas" and not identitas:
        raise CsomagHiba("alairas_identitas", "identitas módhoz a MANIFOLD_SIGN_IDENTITY környezeti változó kell "
                                              "(a kulcskarikában lévő Developer ID tanúsítvány neve)")
    azon = "-" if mod == "adhoc" else identitas
    kapcsolok = ["--force", "--sign", azon]
    if mod == "identitas":
        kapcsolok += ["--options", "runtime", "--timestamp", "--entitlements", str(entitlements)]
    belso = machok(app)
    t.machok = len(belso)
    for i in range(0, len(belso), KOTEG):
        t.parancsok.append(["codesign", *kapcsolok, *[str(p) for p in belso[i:i + KOTEG]]])
    t.parancsok.append(["codesign", *kapcsolok, str(app)])
    t.parancsok.append(["codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app)])
    return t


def identitas_ellenoriz(identitas: str, futtato: Futtato = futtat) -> None:
    ki = futtato(["security", "find-identity", "-p", "codesigning", "-v"], check=False).stdout
    if f'"{identitas}"' not in ki:
        raise CsomagHiba("alairas_identitas", f"nincs \"{identitas}\" nevű érvényes kódaláíró tanúsítvány a kulcskarikában "
                                              "(security find-identity -p codesigning -v)")


def alair(app: Path, mod: str, *, env: dict | None = None, futtato: Futtato = futtat, naplo=print) -> AlairasTerv:
    identitas = identitas_kornyezetbol(env) if mod == "identitas" else ""
    t = terv(app, mod, identitas=identitas)
    if mod == "identitas":
        identitas_ellenoriz(identitas, futtato)
    for cmd in t.parancsok:
        naplo("$ " + " ".join(cmd[:6]) + (f" … (+{len(cmd) - 6})" if len(cmd) > 6 else ""))
        futtato(cmd, timeout=3600)
    if mod != "nincs":
        naplo(f"aláírva ({mod}): {t.machok} belső Mach-O + az app")
    return t


def notarizal_terv(dmg: Path, profil: str) -> list[list[str]]:
    if not profil:
        raise CsomagHiba("notarizacio_profil", f"a notarizációhoz a {NOTARY_PROFIL_VALTOZO} környezeti változó kell (a "
                                               "`xcrun notarytool store-credentials` által létrehozott kulcskarika-profil neve)")
    return [["xcrun", "notarytool", "submit", str(dmg), "--keychain-profile", profil, "--wait"],
            ["xcrun", "stapler", "staple", str(dmg)],
            ["xcrun", "stapler", "validate", str(dmg)]]


def notarizal(dmg: Path, *, env: dict | None = None, futtato: Futtato = futtat, naplo=print) -> None:
    env = os.environ if env is None else env
    for cmd in notarizal_terv(dmg, env.get(NOTARY_PROFIL_VALTOZO, "")):
        naplo("$ " + " ".join(cmd))
        futtato(cmd, timeout=7200)
