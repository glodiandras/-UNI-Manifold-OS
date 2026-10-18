"""Jegyzetenkénti előzmények (C11b): a jegyzet pillanatképei (melyik kör, milyen forrás), egy változat szövege a
diffhez, és a visszaállítás egy verzióra **revert-commitként** (nem reset, nem checkout: CLAUDE.md 4.).

A napló a `snapshot.Repo.fajl_naplo` (`git log --follow`): az átnevezés előtti változatok is látszanak. Az azonos úton
álló változat visszaállítása a patch-alapú revert-commit (`Repo.visszaallit_fajl`); a **régi néven álló** változaté
(39. döntés, C29.6) a régi úton álló tartalom a JELENLEGI útra íródik új tartalom-írásként (`Mos-Visszaallit`
trailerrel), a régi fájl nem támad fel. Mindkettő a kör-zár alatt fut, mint a visszavonás, maga is visszavonható; a
nyitott szerkesztők a lemezen megjelenő változást külső változásként kapják (a tiszta dokumentum csendben újratölt,
a mentetlen ütközést jelez), és az index a változott utakat azonnal megkapja (`jelez`, T102).

Lapozás (13-palette-05): a napló `elotte=<sha>` kurzorral lapoz (`tovabb`, `kovetkezo` a válaszban); a lapméret és a mélység-plafon
a `[elozmeny]` konfigurációból jön (`lap`, `lap_max`, `max_melyseg`), nem kódba égetett 200. A `valtozat`/`visszaallit` bármely, a
fájl történetében elérhető commitot megtalál (a keresés a plafonig nő), nem csak a legutóbbi 200-at.

Törölt jegyzetek (13-palette-04): a `torolt` felsorolja a HEAD-ben már nem álló (írható típusú) fájlokat a törlő commit szerint, a
`torolt_valtozat` megadja a törlés előtti szöveget, a `visszahoz` pedig új fájlként írja vissza — az eredeti helyre (ütközésnél
409, semmi nem íródik) vagy ütközésmentes új néven; a visszaállítás maga is egy pillanatkép-commit (`Mos-Visszaallit`), visszavonható.
`.canvas` és `.base` ugyanúgy előzményes, mint a `.md` (a napló és a revert útvonal-független).
"""
from __future__ import annotations

import contextlib
import os
import re
import unicodedata
from pathlib import PurePosixPath

from . import frame, snapshot, tartos, vaultio
from .utvonalak import HttpError

FORRAS = "pult-elozmeny"               # a visszaállítás commitjának Mos-Forras trailere (L09: új érték csak hozzáadással)
KOR_ELOTAG = "VISSZA"                  # Mos-Kor előtag (a KOR_ID-ban is)
MAX_BEJEGYZES = 200                    # a `[elozmeny] lap_max` alapértéke
ALAP_LAP = 50                          # a `[elozmeny] lap` alapértéke
KEZDO_ABLAK = 256                      # a sha-keresés első naplóablaka; ha nem elég, négyszeresére nő a mélység-plafonig
ALAP_MELYSEG = 20000                   # a `[elozmeny] max_melyseg` alapértéke: ennél régebbi bejegyzést a keresés nem néz

_KOR_CIMKE = (("SZERK", "Szerkesztés a Manifoldban"), ("ATNEV", "Átnevezés"), ("VISSZA", "Visszaállítás egy verzióra"),
              ("LEPES", "Gépi lépés"), ("FUZET", "Füzet-lánc"), ("KVIZ", "Kvíz-lánc"), ("KOR", "Gépi kör"))


def _hajtogat(s: str) -> str:
    """Ékezet- és kisbetű-független összehasonlító alak."""
    return "".join(c for c in unicodedata.normalize("NFD", s.casefold()) if not unicodedata.combining(c))


def cimke(tr: dict[str, str], targy: str) -> tuple[str, str]:
    """(típus, magyar felirat) a commit trailereiből: melyik kör, milyen forrás."""
    if "Mos-Visszavon" in tr or "Mos-Visszavon-Kor" in tr:
        return "visszavonas", "Visszavonás"
    if "Mos-Visszaallit" in tr:
        return "visszaallitas", "Visszaállítás egy verzióra"
    kor = tr.get("Mos-Kor", "")
    for elotag, felirat in _KOR_CIMKE:
        if kor.startswith(elotag + "-"):
            return elotag.lower(), felirat
    if tr.get("Mos-Forras") == "kezi" or targy.startswith("kézi változások"):
        return "kezi", "Kézi változás (Obsidian, Finder, …)"
    if frame.KOR_MINTA.fullmatch(kor):      # a C16.5 óta új lánc új előtagot hozhat (L12)
        return "gepi", "Gépi írás"
    return "egyeb", "Pillanatkép"


class Elozmeny:
    def __init__(self, cfg, busy=lambda: False, jelez=lambda utak: None):
        self.cfg = cfg
        self.busy = busy
        self.jelez = jelez              # a visszaállítás után a változott (NFC) utak az indexnek, mint a visszavonásnál
        self._v = vaultio.Vault(cfg)

    def _ut(self, ut) -> str:
        """A kérés útja kanonikus alakban (T018): a git a lemezen álló, NFC nevet ismeri, kis-nagybetűre érzékenyen."""
        return self._v.kanonikus(vaultio.norm_path(ut))

    def _repo(self) -> snapshot.Repo:
        r = frame.live_repos(self.cfg).get("vault")
        if not r:
            raise HttpError(404, "a vault pillanatkép-tárolója nem érhető el, az előzmények nem állnak rendelkezésre", kod="elozmeny.nincs_pillanatkep_tarolo")
        return r

    def _el(self, repo: snapshot.Repo, ut: str) -> None:
        """T104: az út él-e a HEAD-ben vagy a lemezen — különben 404 (a jegyzetet közben átnevezték vagy törölték). Így a
        régi út nem kap előzményt és nem támad fel az új név mellett."""
        van_lemezen = os.path.lexists(repo.work_tree / ut)
        van_headben = repo.has_head() and repo.git("cat-file", "-e", f"HEAD:{ut}", check=False).returncode == 0
        if not (van_lemezen or van_headben):
            raise HttpError(404, f"a jegyzetet közben átnevezték vagy törölték: {ut} — nyisd meg az új nevén", kod="elozmeny.jegyzet_athelyezve", param={"ut": ut})

    def _beallitas(self) -> tuple[int, int, int]:
        """(alap lapméret, lap-plafon, mélység-plafon) a `[elozmeny]` konfigurációból; érvénytelen érték az alapra esik."""
        sz = self.cfg.section("elozmeny")

        def egesz(kulcs: str, alap: int) -> int:
            v = sz.get(kulcs, alap)
            return v if type(v) is int and v >= 1 else alap
        lap_max = egesz("lap_max", MAX_BEJEGYZES)
        return min(egesz("lap", ALAP_LAP), lap_max), lap_max, egesz("max_melyseg", ALAP_MELYSEG)

    def _lap(self, n) -> int:
        alap, plafon, _ = self._beallitas()
        return alap if n is None else max(1, min(int(n), plafon))

    def _keres(self, repo: snapshot.Repo, ut: str, sha: str | None, extra: int = 1) -> tuple[list[dict], int | None]:
        """A fájl naplója (legújabb elöl) addig, amíg a `sha` (előtag) megvan és még `extra` további elem áll utána — a plafonig
        (`max_melyseg`) bővülő ablakkal, így a 200. után is elérhető minden változat. → (napló, a `sha` indexe vagy None)."""
        _, _, plafon = self._beallitas()
        hossz = KEZDO_ABLAK
        while True:
            hossz = min(hossz, plafon)
            sorok = repo.fajl_naplo(ut, hossz)
            i = next((j for j, c in enumerate(sorok) if sha and c["sha"].startswith(sha)), None)
            if len(sorok) < hossz or hossz >= plafon or (i is not None and i + extra < len(sorok)):
                return sorok, i
            hossz *= 4

    def naplo(self, ut, n=None, elotte: str | None = None) -> dict:
        """Egy lap a jegyzet napjából. `n`: a lapméret (alap: `[elozmeny] lap`, plafon: `lap_max`); `elotte`: a már látott legrégebbi
        bejegyzés sha-ja — a lap az annál RÉGEBBIEKkel kezdődik. A válasz `tovabb` jelzi, hogy van régebbi, `kovetkezo` a következő
        lap kurzora."""
        ut = self._ut(ut)
        repo = self._repo()
        self._el(repo, ut)
        meret = self._lap(n)
        if elotte:
            if not re.fullmatch(r"[0-9a-fA-F]{7,64}", str(elotte)):
                raise HttpError(400, "érvénytelen kurzor (elotte)", kod="elozmeny.kurzor_hibas")
            sorok, i = self._keres(repo, ut, str(elotte), meret + 1)
            if i is None:
                raise HttpError(404, f"a kurzor nem tartozik ehhez a jegyzethez: {elotte}", kod="elozmeny.commit_nem_erinti", param={"sha": str(elotte)})
            ablak = sorok[i + 1:i + 1 + meret + 1]
            elso_lap = False
        else:
            ablak = repo.fajl_naplo(ut, meret + 1)
            elso_lap = True
        lap = ablak[:meret]
        tovabb = len(ablak) > meret
        ki = []
        for i, c in enumerate(lap):
            tipus, felirat = cimke(c["trailerek"], c["targy"])
            kovetkezo = ablak[i + 1] if i + 1 < len(ablak) else None
            ki.append({
                "sha": c["sha"], "datum": c["datum"], "targy": c["targy"], "tipus": tipus, "cimke": felirat,
                "kor": c["trailerek"].get("Mos-Kor"), "forras": c["trailerek"].get("Mos-Forras"),
                "statusz": c["statusz"], "ut_akkor": c["ut_akkor"], "regi_ut": c["regi_ut"],
                # a következő (régebbi) elem: a változat „előtte” állapota
                "elozo": ({"sha": kovetkezo["sha"], "ut": kovetkezo["ut_akkor"]} if kovetkezo else None),
                # 39. döntés: a régi néven álló változat is visszaállítható (a jelenlegi útra íródik)
                "visszaallithato": c["statusz"] != "D" and (i > 0 or not elso_lap),
            })
        return {"ut": ut, "bejegyzesek": ki, "lap": meret, "tovabb": tovabb, "kovetkezo": lap[-1]["sha"] if lap and tovabb else None}

    def valtozat(self, ut, sha: str) -> dict:
        """A `sha` commit utáni és az azt megelőző szöveg: a felület ebből rajzolja a diffet."""
        ut = self._ut(ut)
        repo = self._repo()
        self._el(repo, ut)
        naplo, i = self._keres(repo, ut, str(sha), 1)
        if i is None:
            raise HttpError(404, f"a commit nem érinti ezt a jegyzetet: {sha}", kod="elozmeny.commit_nem_erinti", param={"sha": sha})
        c = naplo[i]
        szoveg, ok = (None, "nincs") if c["statusz"] == "D" else repo.fajl_valtozat(c["sha"], c["ut_akkor"])
        elozo, elozo_ok = (None, "nincs")
        if i + 1 < len(naplo):
            e = naplo[i + 1]
            elozo, elozo_ok = (None, "nincs") if e["statusz"] == "D" else repo.fajl_valtozat(e["sha"], e["ut_akkor"])
        return {"sha": c["sha"], "ut_akkor": c["ut_akkor"], "szoveg": szoveg, "szoveg_ok": ok,
                "elozo": elozo, "elozo_ok": elozo_ok}

    def visszaallit(self, ut, sha: str) -> dict:
        ut = self._ut(ut)
        repo = self._repo()
        self._el(repo, ut)
        naplo, i = self._keres(repo, ut, str(sha), 0) if len(str(sha)) >= 7 else ([], None)
        c = naplo[i] if i is not None else None
        if c is None:
            raise HttpError(404, f"a commit nem érinti ezt a jegyzetet: {sha}", kod="elozmeny.commit_nem_erinti", param={"sha": sha})
        if c["statusz"] == "D":
            raise HttpError(400, "ebben a commitban a jegyzet törölve lett, nincs mire visszaállítani", kod="elozmeny.jegyzet_torolve_a_commitban")
        if self.busy():
            raise HttpError(409, "egy vault-író feladat fut — a visszaállítás a vége után indítható", kod="elozmeny.iro_feladat_fut", foglalt=True)
        kor = frame.new_id(KOR_ELOTAG)
        trailerek = {snapshot.TRAILER_RUN: kor, snapshot.TRAILER_ITEM: ut, "Mos-Forras": FORRAS}
        try:
            with frame.run_lock(self.cfg, wait=False, turelem_mp=frame.felhasznaloi_turelem(self.cfg)):
                if c["ut_akkor"] != ut:             # a régi néven álló változat → a jelenlegi útra (39. döntés)
                    uj = self._visszaallit_regi_utrol(repo, ut, c, trailerek)
                else:
                    uj = repo.visszaallit_fajl(ut, c["sha"], trailerek)
        except frame.Busy as exc:
            raise HttpError(409, str(exc), kod="pillanatkep.foglalt", foglalt=True) from exc
        except snapshot.NaploAll as exc:
            raise HttpError(409, str(exc), kod="pillanatkep.naplo_all", naplo=True) from exc
        except snapshot.UndoConflict as exc:
            raise HttpError(409, str(exc), kod="pillanatkep.visszavonas_utkozes", utkozes=True, fajlok=exc.files) from exc
        except snapshot.SnapshotError as exc:
            raise HttpError(400, str(exc), kod="pillanatkep.hibas") from exc
        self.jelez(repo.changed_files(uj))          # T102: az index ne a figyelőre várjon (a visszavonáshoz hasonlóan)
        return {"ok": True, "ut": ut, "sha": uj, "visszaallitott": c["sha"]}

    # ------------------------------------------------------------ törölt jegyzetek (13-palette-04)

    def torolt(self, q: str = "", n=None) -> dict:
        """A törölt (a HEAD-ben már nem álló) írható fájlok a törlés ideje szerint, a legújabb elöl; `q`: ékezet- és
        kisbetű-független részszöveg az útban. Az `ut_van` jelzi, hogy az eredeti helyen jelenleg áll-e (idegen) fájl."""
        repo = self._repo()
        _, plafon_lap, melyseg = self._beallitas()
        meret = self._lap(n)
        kulcs = _hajtogat(str(q or "").strip())
        ki = []
        for t in repo.torolt_fajlok(melyseg):
            if not t["ut"].lower().endswith(vaultio.IRHATO):
                continue
            if kulcs and not all(sz in _hajtogat(t["ut"]) for sz in kulcs.split()):
                continue
            tipus, felirat = cimke(t["trailerek"], t["targy"])
            ki.append({"ut": t["ut"], "sha": t["sha"], "datum": t["datum"], "targy": t["targy"], "tipus": tipus,
                       "cimke": felirat, "ut_van": self._foglalt(t["ut"])})
            if len(ki) >= meret:
                break
        return {"torolt": ki, "lap": meret, "lap_max": plafon_lap}

    def _foglalt(self, ut: str) -> bool:
        """Áll-e a lemezen ezen az úton (vagy kis-nagybetűtől / normalizálástól eltérő alakban) bármi."""
        p = self._v.lemezen(ut)
        if os.path.lexists(p):
            return True
        try:
            nev = unicodedata.normalize("NFC", p.name).casefold()
            return any(unicodedata.normalize("NFC", n).casefold() == nev for n in os.listdir(p.parent))
        except OSError:
            return False

    def _torolt_commit(self, repo: snapshot.Repo, ut: str, sha: str) -> dict:
        """A `sha` törlő commit sora az `ut` útra (különben 404/400), a törlés előtti változat commitjával."""
        ut = vaultio.norm_path(ut)
        if not ut.lower().endswith(vaultio.IRHATO):
            raise HttpError(400, "csak jegyzet, adatbázis-nézet vagy canvas állítható vissza", kod="elozmeny.torolt_tipus")
        if not re.fullmatch(r"[0-9a-fA-F]{7,64}", str(sha or "")):
            raise HttpError(400, "hiányzó vagy érvénytelen sha", kod="elozmeny.hianyzo_sha")
        _, _, melyseg = self._beallitas()
        c = next((t for t in repo.torolt_fajlok(melyseg) if t["ut"] == ut and t["sha"].startswith(str(sha))), None)
        if c is None:
            raise HttpError(404, f"nincs ilyen törölt jegyzet: {ut}", kod="elozmeny.nincs_torolt", param={"ut": ut})
        return c

    def torolt_valtozat(self, ut, sha: str) -> dict:
        """A törölt jegyzet utolsó (törlés előtti) szövege a diffhez / előnézethez: ugyanaz az alak, mint a `valtozat`."""
        repo = self._repo()
        c = self._torolt_commit(repo, ut, sha)
        szoveg, ok = repo.fajl_valtozat(f"{c['sha']}^", c["ut"])
        return {"sha": c["sha"], "ut_akkor": c["ut"], "szoveg": szoveg, "szoveg_ok": ok, "elozo": None, "elozo_ok": "nincs"}

    def visszahoz(self, ut, sha: str, mod: str = "eredeti", nev=None) -> dict:
        """A törölt jegyzet visszahozása ÚJ FÁJLKÉNT, a törlés előtti változat bájtra pontos másával (a CRLF is).
        `mod`: `eredeti` — az eredeti úton; ha ott már áll valami (kis-nagybetűtől / normalizálástól függetlenül), 409
        `elozmeny.visszahoz_utkozes` és SEMMI nem íródik; `uj` — ugyanabban a mappában a `nev` (alap: `<név> (visszaállítva)`),
        ütközésnél sorszámmal. A fájl nem íródik felül (RENAME_EXCL); a mappa hiányzó része létrejön. Egy `Mos-Visszaallit`
        pillanatkép-commit rögzíti, maga is visszavonható."""
        if mod not in ("eredeti", "uj"):
            raise HttpError(400, "a mod `eredeti` vagy `uj`", kod="elozmeny.mod_hibas")
        repo = self._repo()
        c = self._torolt_commit(repo, ut, sha)
        eredeti = c["ut"]
        if self.busy():
            raise HttpError(409, "egy vault-író feladat fut — a visszaállítás a vége után indítható", kod="elozmeny.iro_feladat_fut", foglalt=True)
        tartalom = repo.git_bytes("show", f"{c['sha']}^:{eredeti}", check=False)
        if tartalom.returncode != 0:
            raise HttpError(400, f"a változat tartalma nem olvasható: {c['sha'][:7]}:{eredeti}", kod="elozmeny.valtozat_nem_olvashato", param={"sha": c["sha"][:7], "ut": eredeti})
        b = tartalom.stdout
        if len(b) > vaultio.MAX_SZOVEG:
            raise HttpError(400, "túl nagy változat, nem állítható vissza", kod="elozmeny.valtozat_tul_nagy")
        mappa, fajl = (str(PurePosixPath(eredeti).parent), PurePosixPath(eredeti).name)
        mappa = "" if mappa == "." else mappa
        if mappa:
            mappa = self._v.kanonikus(mappa)               # a lemezen álló mappanév (APFS: kis-nagybetű / NFD), mint a mentésnél
        if mod == "eredeti":
            cel = f"{mappa}/{fajl}" if mappa else fajl
            if self._foglalt(cel):
                raise HttpError(409, f"az eredeti helyen már áll egy fájl: {cel} — állítsd vissza új néven", kod="elozmeny.visszahoz_utkozes", param={"ut": cel})
        else:
            cel = self._uj_nev(mappa, fajl, nev)
        vissza_mappa = self._v._abs(mappa) if mappa else self._v.root
        kor = frame.new_id(KOR_ELOTAG)
        trailerek = {snapshot.TRAILER_RUN: kor, snapshot.TRAILER_ITEM: cel, "Mos-Forras": FORRAS, "Mos-Visszaallit": c["sha"]}
        try:
            with frame.run_lock(self.cfg, wait=False, turelem_mp=frame.felhasznaloi_turelem(self.cfg)):
                with vaultio._ut_zar(cel):
                    if mod == "eredeti" and self._foglalt(cel):        # a zár alatt újra: közben létrejöhetett
                        raise HttpError(409, f"az eredeti helyen már áll egy fájl: {cel} — állítsd vissza új néven", kod="elozmeny.visszahoz_utkozes", param={"ut": cel})
                    repo.visszavonas_helyreallit_vagy_hiba()           # a kézi commit ELŐTT (lásd `_visszaallit_regi_utrol`)
                    if not vissza_mappa.is_dir():
                        os.makedirs(vissza_mappa, exist_ok=True)
                        tartos.fsync_mappa(vissza_mappa.parent)
                    p = self._v._abs(cel)
                    try:
                        tartos.kizaro_ir(p, b)                         # tmp + fsync + RENAME_EXCL: meglévő fájlt nem ír felül
                    except FileExistsError:
                        raise HttpError(409, f"az eredeti helyen már áll egy fájl: {cel} — állítsd vissza új néven", kod="elozmeny.visszahoz_utkozes", param={"ut": cel}) from None
                    try:
                        uj = repo.commit_machine(f"visszaállítás törlés után: {cel} ← {c['sha'][:7]}^", trailerek, [cel])
                    except BaseException:
                        with contextlib.suppress(OSError):             # a félkész állapot nem marad: a most írt fájl el
                            p.unlink()
                        raise
        except frame.Busy as exc:
            raise HttpError(409, str(exc), kod="pillanatkep.foglalt", foglalt=True) from exc
        except snapshot.NaploAll as exc:
            raise HttpError(409, str(exc), kod="pillanatkep.naplo_all", naplo=True) from exc
        except snapshot.SnapshotError as exc:
            raise HttpError(400, str(exc), kod="pillanatkep.hibas") from exc
        self.jelez(repo.changed_files(uj) if uj else [cel])
        return {"ok": True, "ut": cel, "eredeti_ut": eredeti, "sha": uj, "visszaallitott": c["sha"], "uj_nev": cel != eredeti}

    def _uj_nev(self, mappa: str, fajl: str, nev) -> str:
        """Ütközésmentes új út a mappában: a megadott `nev` (kiterjesztés nélkül is), különben `<név> (visszaállítva)`."""
        tores = PurePosixPath(fajl)
        kit = tores.suffix
        if nev is not None:
            if not isinstance(nev, str):
                raise HttpError(400, "érvénytelen név", kod="elozmeny.nev_hibas")
            alap = unicodedata.normalize("NFC", nev).strip()
            if alap.lower().endswith(kit.lower()):
                alap = alap[:-len(kit)].rstrip()
            if not alap or alap.startswith(".") or re.search(r'[\\/:*?"<>|#^\[\]\x00-\x1f\x7f]', alap) or len(alap.encode("utf-8")) > 200:
                raise HttpError(400, 'érvénytelen név — tilos benne: \\ / : * ? " < > | # ^ [ ]', kod="elozmeny.nev_hibas")
        else:
            alap = f"{tores.stem} (visszaállítva)"
        for i in range(1, 1000):
            jel = alap if i == 1 else f"{alap} {i}"
            ut = f"{mappa}/{jel}{kit}" if mappa else f"{jel}{kit}"
            if not self._foglalt(ut):
                return ut
        raise HttpError(409, "nem található szabad név", kod="elozmeny.visszahoz_utkozes", param={"ut": fajl})

    def _visszaallit_regi_utrol(self, repo: snapshot.Repo, ut: str, c: dict, trailerek: dict) -> str:
        """A `c` commit utáni, a jegyzet RÉGI nevén álló tartalom a jelenlegi `ut`-ra (39. döntés, T075): bájtra pontos
        tartalom-írás az útvonal-zár és az atomi csere alatt, egy gépi commit (`Mos-Visszaallit`), amely maga is
        visszavonható. A régi fájl nem támad fel. Commit-hibánál a jelenlegi tartalom visszaáll."""
        p = vaultio.Vault(self.cfg).lemezen(ut)
        ujtartalom = repo.git_bytes("show", f"{c['sha']}:{c['ut_akkor']}", check=False)
        if ujtartalom.returncode != 0:
            raise HttpError(400, f"a változat tartalma nem olvasható: {c['sha'][:7]}:{c['ut_akkor']}", kod="elozmeny.valtozat_nem_olvashato", param={"sha": c["sha"][:7], "ut": c["ut_akkor"]})
        b = ujtartalom.stdout
        if len(b) > vaultio.MAX_SZOVEG:
            raise HttpError(400, "túl nagy változat, nem állítható vissza", kod="elozmeny.valtozat_tul_nagy")
        with vaultio._ut_zar(ut):
            try:
                regi = p.read_bytes()
            except FileNotFoundError:
                raise HttpError(404, f"a jegyzetet közben átnevezték vagy törölték: {ut}", kod="elozmeny.jegyzet_athelyezve_rovid", param={"ut": ut}) from None
            if regi == b:
                raise HttpError(400, f"ez már a jelenlegi változat: {ut}", kod="elozmeny.mar_jelenlegi", param={"ut": ut})
            repo.visszavonas_helyreallit_vagy_hiba()            # a kézi commit ELŐTT: félkész visszavonás maradványa ne kerüljön bele
            tartos.atomi_ir(p, b)
            try:
                return repo.commit_machine(f"visszaállítás: {ut} → {c['sha'][:7]} (átnevezés előtti változat)",
                                           {**trailerek, "Mos-Visszaallit": c["sha"]}, [ut])
            except BaseException:
                tartos.atomi_ir(p, regi)
                raise


def utvonalak(r) -> None:
    def naplo(k):
        return k.app.elozmeny.naplo(k.q.get("ut"), k.egesz("n", None, 1, 10_000), k.q.get("elotte") or None)

    def torolt(k):
        return k.app.elozmeny.torolt(k.q.get("q") or "", k.egesz("n", None, 1, 10_000))

    def torolt_valtozat(k):
        return k.app.elozmeny.torolt_valtozat(k.q.get("ut"), k.q.get("sha"))

    def visszahoz(k):
        t = k.torzs()
        return k.app.elozmeny.visszahoz(t.get("ut"), t.get("sha"), t.get("mod") or "eredeti", t.get("nev"))

    def valtozat(k):
        sha = k.q.get("sha")
        if not sha:
            raise HttpError(400, "hiányzó sha", kod="elozmeny.hianyzo_sha")
        return k.app.elozmeny.valtozat(k.q.get("ut"), sha)

    def visszaallit(k):
        t = k.torzs()
        return k.app.elozmeny.visszaallit(t.get("ut"), t.get("sha"))

    r.get("/api/vault/elozmeny", naplo)
    r.get("/api/vault/elozmeny/valtozat", valtozat)
    r.post("/api/vault/elozmeny/visszaallit", visszaallit)
    r.get("/api/vault/elozmeny/torolt", torolt)
    r.get("/api/vault/elozmeny/torolt/valtozat", torolt_valtozat)
    r.post("/api/vault/elozmeny/visszahoz", visszahoz)
