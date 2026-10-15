"""Jegyzetenkénti előzmények (C11b): a jegyzet pillanatképei (melyik kör, milyen forrás), egy változat szövege a
diffhez, és a visszaállítás egy verzióra **revert-commitként** (nem reset, nem checkout: CLAUDE.md 4.).

A napló a `snapshot.Repo.fajl_naplo` (`git log --follow`): az átnevezés előtti változatok is látszanak. Az azonos úton
álló változat visszaállítása a patch-alapú revert-commit (`Repo.visszaallit_fajl`); a **régi néven álló** változaté
(39. döntés, C29.6) a régi úton álló tartalom a JELENLEGI útra íródik új tartalom-írásként (`Mos-Visszaallit`
trailerrel), a régi fájl nem támad fel. Mindkettő a kör-zár alatt fut, mint a visszavonás, maga is visszavonható; a
nyitott szerkesztők a lemezen megjelenő változást külső változásként kapják (a tiszta dokumentum csendben újratölt,
a mentetlen ütközést jelez), és az index a változott utakat azonnal megkapja (`jelez`, T102).
"""
from __future__ import annotations

import os

from . import frame, snapshot, tartos, vaultio
from .utvonalak import HttpError

FORRAS = "pult-elozmeny"               # a visszaállítás commitjának Mos-Forras trailere (L09: új érték csak hozzáadással)
KOR_ELOTAG = "VISSZA"                  # Mos-Kor előtag (a KOR_ID-ban is)
MAX_BEJEGYZES = 200

_KOR_CIMKE = (("SZERK", "Szerkesztés a Manifoldban"), ("ATNEV", "Átnevezés"), ("VISSZA", "Visszaállítás egy verzióra"),
              ("LEPES", "Gépi lépés"), ("FUZET", "Füzet-lánc"), ("KVIZ", "Kvíz-lánc"), ("KOR", "Gépi kör"))


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
            raise HttpError(404, "a vault pillanatkép-tárolója nem érhető el, az előzmények nem állnak rendelkezésre")
        return r

    def _el(self, repo: snapshot.Repo, ut: str) -> None:
        """T104: az út él-e a HEAD-ben vagy a lemezen — különben 404 (a jegyzetet közben átnevezték vagy törölték). Így a
        régi út nem kap előzményt és nem támad fel az új név mellett."""
        van_lemezen = os.path.lexists(repo.work_tree / ut)
        van_headben = repo.has_head() and repo.git("cat-file", "-e", f"HEAD:{ut}", check=False).returncode == 0
        if not (van_lemezen or van_headben):
            raise HttpError(404, f"a jegyzetet közben átnevezték vagy törölték: {ut} — nyisd meg az új nevén")

    def naplo(self, ut, n: int = 50) -> dict:
        ut = self._ut(ut)
        self._el(self._repo(), ut)
        sorok = self._repo().fajl_naplo(ut, max(1, min(int(n), MAX_BEJEGYZES)))
        ki = []
        for i, c in enumerate(sorok):
            tipus, felirat = cimke(c["trailerek"], c["targy"])
            ki.append({
                "sha": c["sha"], "datum": c["datum"], "targy": c["targy"], "tipus": tipus, "cimke": felirat,
                "kor": c["trailerek"].get("Mos-Kor"), "forras": c["trailerek"].get("Mos-Forras"),
                "statusz": c["statusz"], "ut_akkor": c["ut_akkor"], "regi_ut": c["regi_ut"],
                # a következő (régebbi) elem: a változat „előtte” állapota
                "elozo": ({"sha": sorok[i + 1]["sha"], "ut": sorok[i + 1]["ut_akkor"]} if i + 1 < len(sorok) else None),
                # 39. döntés: a régi néven álló változat is visszaállítható (a jelenlegi útra íródik)
                "visszaallithato": c["statusz"] != "D" and i > 0,
            })
        return {"ut": ut, "bejegyzesek": ki}

    def valtozat(self, ut, sha: str) -> dict:
        """A `sha` commit utáni és az azt megelőző szöveg: a felület ebből rajzolja a diffet."""
        ut = self._ut(ut)
        repo = self._repo()
        self._el(repo, ut)
        naplo = repo.fajl_naplo(ut, MAX_BEJEGYZES)
        i = next((j for j, c in enumerate(naplo) if c["sha"].startswith(sha)), None)
        if i is None:
            raise HttpError(404, f"a commit nem érinti ezt a jegyzetet: {sha}")
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
        naplo = repo.fajl_naplo(ut, MAX_BEJEGYZES)
        c = next((c for c in naplo if c["sha"].startswith(str(sha)) and len(str(sha)) >= 7), None)
        if c is None:
            raise HttpError(404, f"a commit nem érinti ezt a jegyzetet: {sha}")
        if c["statusz"] == "D":
            raise HttpError(400, "ebben a commitban a jegyzet törölve lett, nincs mire visszaállítani")
        if self.busy():
            raise HttpError(409, "egy vault-író feladat fut — a visszaállítás a vége után indítható", foglalt=True)
        kor = frame.new_id(KOR_ELOTAG)
        trailerek = {snapshot.TRAILER_RUN: kor, snapshot.TRAILER_ITEM: ut, "Mos-Forras": FORRAS}
        try:
            with frame.run_lock(self.cfg, wait=False, turelem_mp=frame.felhasznaloi_turelem(self.cfg)):
                if c["ut_akkor"] != ut:             # a régi néven álló változat → a jelenlegi útra (39. döntés)
                    uj = self._visszaallit_regi_utrol(repo, ut, c, trailerek)
                else:
                    uj = repo.visszaallit_fajl(ut, c["sha"], trailerek)
        except frame.Busy as exc:
            raise HttpError(409, str(exc), foglalt=True) from exc
        except snapshot.NaploAll as exc:
            raise HttpError(409, str(exc), naplo=True) from exc
        except snapshot.UndoConflict as exc:
            raise HttpError(409, str(exc), utkozes=True, fajlok=exc.files) from exc
        except snapshot.SnapshotError as exc:
            raise HttpError(400, str(exc)) from exc
        self.jelez(repo.changed_files(uj))          # T102: az index ne a figyelőre várjon (a visszavonáshoz hasonlóan)
        return {"ok": True, "ut": ut, "sha": uj, "visszaallitott": c["sha"]}

    def _visszaallit_regi_utrol(self, repo: snapshot.Repo, ut: str, c: dict, trailerek: dict) -> str:
        """A `c` commit utáni, a jegyzet RÉGI nevén álló tartalom a jelenlegi `ut`-ra (39. döntés, T075): bájtra pontos
        tartalom-írás az útvonal-zár és az atomi csere alatt, egy gépi commit (`Mos-Visszaallit`), amely maga is
        visszavonható. A régi fájl nem támad fel. Commit-hibánál a jelenlegi tartalom visszaáll."""
        p = vaultio.Vault(self.cfg).lemezen(ut)
        ujtartalom = repo.git_bytes("show", f"{c['sha']}:{c['ut_akkor']}", check=False)
        if ujtartalom.returncode != 0:
            raise HttpError(400, f"a változat tartalma nem olvasható: {c['sha'][:7]}:{c['ut_akkor']}")
        b = ujtartalom.stdout
        if len(b) > vaultio.MAX_SZOVEG:
            raise HttpError(400, "túl nagy változat, nem állítható vissza")
        with vaultio._ut_zar(ut):
            try:
                regi = p.read_bytes()
            except FileNotFoundError:
                raise HttpError(404, f"a jegyzetet közben átnevezték vagy törölték: {ut}") from None
            if regi == b:
                raise HttpError(400, f"ez már a jelenlegi változat: {ut}")
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
        return k.app.elozmeny.naplo(k.q.get("ut"), k.egesz("n", 50, 1, MAX_BEJEGYZES))

    def valtozat(k):
        sha = k.q.get("sha")
        if not sha:
            raise HttpError(400, "hiányzó sha")
        return k.app.elozmeny.valtozat(k.q.get("ut"), sha)

    def visszaallit(k):
        t = k.torzs()
        return k.app.elozmeny.visszaallit(t.get("ut"), t.get("sha"))

    r.get("/api/vault/elozmeny", naplo)
    r.get("/api/vault/elozmeny/valtozat", valtozat)
    r.post("/api/vault/elozmeny/visszaallit", visszaallit)
