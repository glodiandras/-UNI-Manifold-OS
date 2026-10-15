"""A keresés-aranyhalmaz közös része: az 50 kérdés–jegyzet pár (`parok.json`) és a mérőkorpusz a vaultból.

A korpusz futásidőben, csak olvasva épül: az 50 céljegyzet + tárgymappánként a cél szomszédos elméleti
jegyzetei (nehéz negatívok: azonos fejezet, rokon téma), címsor szerinti darabokban. A párokat a C25 a teljes
vaulton futó hibrid keresés mérésére is használja (ott a `cel` út a találat `ut` mezőjével vethető össze).

**Rögzített korpusz (C19)**: a `parok.json` `korpusz_commit` kulcsa a vault pillanatkép-tárolójának (`{vault_git}`)
egy commitja; a mérés korpusza ennek a fájából épül (`GitFa`: csak olvas, `GIT_OPTIONAL_LOCKS=0`), nem az élő
vaultból. Így a vault későbbi változása nem avítja el a generált sorokat (a sor kulcsa a kérés ujjlenyomata, amely a
darabok szövegét hordozza): a mérés reprodukálható. A kulcs nélkül (álvault a tesztekben) az élő mappa a forrás.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

ITT = Path(__file__).resolve().parent
sys.path.insert(0, str(ITT.parent))
from kozos import arany as A  # noqa: E402
from kozos import bm25, tavolsag  # noqa: E402

SZOMSZED = 5            # célonként ennyi szomszédos jegyzet a mappából
DARAB_MAX = 1200        # egy darab legfeljebb ennyi karakter
_NEV = re.compile(r"^(\d+) - (.+)\.md$")


def parok() -> dict:
    return A.betolt(ITT, "parok.json")


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


class MappaFa:
    """Az élő vault (vagy az álvault) mappája mint korpusz-forrás; a lemezen álló név NFD is lehet."""

    def __init__(self, vault: Path):
        self.vault = Path(vault)

    def _ut(self, rel: str, mappa: bool = False) -> Path | None:
        for r in (rel, unicodedata.normalize("NFD", rel)):
            p = self.vault / r
            if p.is_dir() if mappa else p.is_file():
                return p
        return None

    def van(self, rel: str) -> bool:
        return self._ut(rel) is not None

    def olvas(self, rel: str) -> str:
        return self._ut(rel).read_text(encoding="utf-8")

    def nevek(self, mappa_rel: str) -> list[str]:
        """A mappa közvetlen fájljainak neve (NFC)."""
        mappa = self._ut(mappa_rel, mappa=True)
        return [nfc(f.name) for f in mappa.iterdir() if f.is_file()] if mappa else []


def _git_env() -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_ATTR_NOSYSTEM": "1",
                "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0", "LC_ALL": "C"})
    return env


class GitFa:
    """A vault pillanatkép-tárolójának egy commitja mint korpusz-forrás: csak olvas (`ls-tree`, `cat-file`)."""

    def __init__(self, git_dir: Path, commit: str):
        self.git_dir, self.commit = Path(git_dir), commit
        lista = self._git("ls-tree", "-r", "-z", "--name-only", commit).decode("utf-8")
        self._utak = {nfc(u): u for u in lista.split("\0") if u}

    def _git(self, *args: str) -> bytes:
        try:
            r = subprocess.run(["git", "--git-dir", str(self.git_dir), *args], capture_output=True, env=_git_env(),
                               check=True)
        except (OSError, subprocess.CalledProcessError) as e:
            hiba = (getattr(e, "stderr", b"") or b"").decode(errors="replace").strip()
            raise FileNotFoundError(f"a rögzített korpusz commitja ({self.commit}) nem olvasható a(z) {self.git_dir} "
                                    f"tárolóból: {hiba or e}") from None
        return r.stdout

    def van(self, rel: str) -> bool:
        return nfc(rel) in self._utak

    def olvas(self, rel: str) -> str:
        return self._git("cat-file", "blob", f"{self.commit}:{self._utak[nfc(rel)]}").decode("utf-8")

    def nevek(self, mappa_rel: str) -> list[str]:
        elo = nfc(mappa_rel).rstrip("/") + "/"
        return [u[len(elo):] for u in self._utak if u.startswith(elo) and "/" not in u[len(elo):]]


def forras(cfg, parok_: dict) -> MappaFa | GitFa:
    """A mérés korpusz-forrása: a `korpusz_commit` fája a `{vault_git}`-ben (rögzített), különben az élő vault."""
    commit = parok_.get("korpusz_commit")
    return GitFa(cfg.path("vault_git"), commit) if commit else MappaFa(cfg.path("vault"))


def torzs(szoveg: str) -> str:
    if szoveg.startswith("---"):
        vege = szoveg.find("\n---", 3)
        szoveg = szoveg[vege + 4:] if vege > 0 else szoveg
    szoveg = re.split(r"\n## Füzet\s*\n", szoveg)[0]
    szoveg = re.sub(r"!\[\[[^\]]*\]\]", " ", szoveg)
    return re.sub(r"\[\[([^\]|#]*)(?:#[^\]|]*)?(?:\|([^\]]*))?\]\]", lambda m: m.group(2) or m.group(1), szoveg).strip()


def darabok(cim: str, szoveg: str) -> list[str]:
    """A jegyzet címsor szerinti darabjai (hosszú szakasz bekezdésenként tovább vágva), a címmel az elején."""
    ki, akt = [], ""
    for bek in re.split(r"\n\s*\n", torzs(szoveg)):
        bek = bek.strip()
        if not bek:
            continue
        uj_szakasz = bek.startswith("#")
        if akt and ((uj_szakasz and len(akt) > DARAB_MAX // 2) or len(akt) + len(bek) > DARAB_MAX):
            ki.append(akt)
            akt = ""
        akt = f"{akt}\n\n{bek}" if akt else bek
        while len(akt) > DARAB_MAX * 1.5:
            ki.append(akt[:DARAB_MAX])
            akt = akt[DARAB_MAX:]
    if akt:
        ki.append(akt)
    return [f"{cim}\n\n{d}" for d in ki]


def _szomszedok(fa: MappaFa | GitFa, rel: str) -> list[str]:
    """A cél mappájának számozott elméleti jegyzetei közül a sorszámban legközelebbiek."""
    mappa = rel.rsplit("/", 1)[0]
    sajat = int(_NEV.match(rel.rsplit("/", 1)[1]).group(1))
    jeloltek = []
    for nev in fa.nevek(mappa):
        m = _NEV.match(nev)
        r = f"{mappa}/{nev}"
        if m and r != rel:
            jeloltek.append((abs(int(m.group(1)) - sajat), int(m.group(1)), r))
    return [r for _, _, r in sorted(jeloltek)[:SZOMSZED]]


def korpusz(vault: Path | MappaFa | GitFa, parlista: list[dict]) -> dict[str, list[str]]:
    """`{vault-relatív út: [darab…]}`: a célok és a szomszédaik. A forrás egy mappa (`Path`: élő vault, álvault) vagy egy
    fa (`forras()`: a rögzített commit). Hiányzó cél → `FileNotFoundError`."""
    fa = vault if isinstance(vault, (MappaFa, GitFa)) else MappaFa(vault)
    hianyzik = [p["cel"] for p in parlista if not fa.van(p["cel"])]
    if hianyzik:
        raise FileNotFoundError(f"hiányzó céljegyzet a vaultban ({len(hianyzik)}): {hianyzik[:3]}")
    utak: list[str] = []
    for p in parlista:
        for r in [p["cel"]] + _szomszedok(fa, p["cel"]):
            if r not in utak:
                utak.append(r)
    ki = {}
    for r in sorted(utak):
        cim = _NEV.match(r.rsplit("/", 1)[1]).group(2)
        ki[r] = darabok(cim, fa.olvas(r))
    return ki


def tokenek(szoveg: str) -> list[str]:
    return [w[:6] for w in (tavolsag.hajt(x) for x in tavolsag.szavak(szoveg)) if len(w) >= 3]


def lexikai(korp: dict[str, list[str]]) -> bm25.Bm25:
    """BM25 a korpusz darabjain (azonosító: `út#sorszám`): a rerank jelöltjeihez és a lexikai alapszinthez."""
    b = bm25.Bm25()
    for ut, dk in korp.items():
        for i, d in enumerate(dk):
            b.hozzaad(f"{ut}#{i}", tokenek(d))
    return b


def jegyzet_rangsor(b: bm25.Bm25, kerdes: str) -> list[tuple[str, str]]:
    """Jegyzetek a legjobb darabjuk pontja szerint: [(út, a legjobb darab azonosítója)…]."""
    ki, latott = [], set()
    for azon, _ in b.rangsor(tokenek(kerdes)):
        ut = azon.rsplit("#", 1)[0]
        if ut not in latott:
            latott.add(ut)
            ki.append((ut, azon))
    return ki


def rangmutatok(helyek: list[int | None], k_ertekek=(1, 5, 10)) -> dict:
    """A cél helyezései (1-től; `None`: nincs a listán) → recall@k és MRR."""
    n = len(helyek)
    ki = {f"recall{k}": round(sum(1 for h in helyek if h and h <= k) / n, 4) if n else 0.0 for k in k_ertekek}
    ki["mrr"] = round(sum(1 / h for h in helyek if h) / n, 4) if n else 0.0
    return ki
