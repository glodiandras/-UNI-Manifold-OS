"""Note composer (12-templates-10 / 12-templates-11): jegyzetrész kivonása új vagy meglévő jegyzetbe, és két jegyzet összefűzése.

**Kivonás** (`POST /api/komponalo/kivon`). A felület a kijelölt szöveget és a forrás útját küldi; a core **előbb a célt** írja
(új jegyzet: `Vault.create`, meglévő: hash-védett `Vault.write` a végére vagy az elejére, mindkettő pillanatképpel), és csak ezután
adja vissza az eredményt — a szerkesztő a forrásban a kijelölést (link / beágyazás / semmi) a saját tranzakciójában cseréli
(⌘Z), és csak akkor, ha a kijelölés közben nem változott. Hiba a két írás között: a cél megvan, a forrás érintetlen (nincs
adatvesztés; a duplikátum látható). A kivonás-sablon (`beallitasok.fajlok.kivonas_sablon`, vault-relatív út) változói:
`{{content}}`, `{{fromTitle}}`, `{{newTitle}}`, `{{date:…}}`, `{{time:…}}` — egy menetben, a kijelölés szövege nem értékelődik újra.

**Összefűzés** (`POST /api/komponalo/osszefuz/terv` és `/api/komponalo/osszefuz`). Terv / végrehajtás pár, mint az átnevezés. A terv
csak olvas: a forrás törzse a cél végére (`veg`) vagy elejére (`eleje`) kerül, a frontmatter a Tulajdonságok szabályai szerint
egyesül (új kulcs hozzáadódik, a lista egyesül, a meglévő érték marad, a séma-sértő kulcs nem íródik: `fuggo`), a forrásra mutató
összes link (jegyzet, canvas, Bases) az **átnevezés** link-átíróján át a célra mutat (`Atnevezes._terv_kozos` a `{forrás → cél}`
leképezéssel; a `#fejezet` és `#^blokk` horgony marad, mert a törzs változatlanul átkerül). A végrehajtás (kör-zár + útvonal-zárak alatt):
kézi pillanatkép → hash-ellenőrzés → a cél, majd a linkelő fájlok atomi, CAS-védett írása (bukáskor a memóriában tartott eredeti
bájtokból visszaállítás) → egy gépi commit (`Mos-Kor: KOMP-…`) → a forrás a **Kukába** (soha nem végleges törlés) → a törlés
commitja ugyanabban a körben. A visszavonás: `POST /api/pillanat/vault/visszavonas {kor}` (git revert minden lépésre; a Kuka
példánya megmarad). Nincs szándéknapló: a sorrend (cél → linkelők → forrás) miatt bármely megszakadás legfeljebb duplikátumot hagy,
adatot soha. A forrás Kukába helyezésének hibája nem vonja vissza az összefűzést: a válasz `forras_kukaban: false`.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime

from . import csatolmany, frame, sablon, snapshot, vaultio
from .atnevezes import _Terv
from .index import feloldas
from .index.maszk import FM_RE
from .utvonalak import HttpError
from .vaultio import Invalid, NotFound, norm_path

KOR_ELOTAG = "KOMP"                        # új kör-előtag (L12); a `gepi_iras` gazdai előtagjai között is szerepel
MAX_SZOVEG = 2_000_000                     # a kivonható / összefűzött szöveg felső korlátja (karakter)
HELYEK = ("veg", "eleje")


def _hiba(statusz: int, uzenet: str, kod: str, **param) -> HttpError:
    return HttpError(statusz, uzenet, kod=kod, param=param or None)


def _jegyzet_ut(vault, ut, szerep: str) -> str:
    """Egy meglévő `.md` jegyzet kanonikus útja; Invalid / NotFound másképp."""
    rp = vault.kanonikus(norm_path(ut))
    if not rp.lower().endswith(".md"):
        raise _hiba(400, f"csak jegyzet (.md) komponálható: {rp}", "komponalo.nem_jegyzet", ut=rp)
    if not vault._abs(rp).is_file():
        raise _hiba(404, f"nincs ilyen jegyzet: {rp}", "komponalo.nincs_jegyzet", ut=rp)
    return rp


def _mentetlen(app, *utak: str) -> list[str]:
    nyitott = {vaultio.nfc(u).casefold() for u in app.atnevezes.mentetlen()}
    return [u for u in utak if vaultio.nfc(u).casefold() in nyitott]


def _nev(rp: str) -> str:
    return vaultio.nfc(rp.rpartition("/")[2][:-3])


def _fm_torzs(szoveg: str) -> tuple[str, str]:
    """(frontmatter-blokk | "", törzs)."""
    m = FM_RE.match(szoveg)
    return (szoveg[:m.end()], szoveg[m.end():]) if m else ("", szoveg)


def _eol(szoveg: str) -> str:
    return "\r\n" if "\r\n" in szoveg else "\n"


def beillesztes(regi: str, beszurando: str, hely: str) -> str:
    """A `beszurando` blokk a jegyzet végére (`veg`) vagy a frontmatter utáni elejére (`eleje`), egy üres sorral elválasztva. A
    jegyzet meglévő bájtjai érintetlenek; csak a beszúrt rész veszi fel a jegyzet sorvégét (CRLF-es jegyzet CRLF marad)."""
    eol = _eol(regi)
    blokk = beszurando.replace("\r\n", "\n").strip("\n").replace("\n", eol) + eol
    if hely == "eleje":
        fm, torzs = _fm_torzs(regi)
        if not torzs.strip():
            return fm + blokk
        return fm + blokk + eol + torzs.lstrip("\r\n")
    if not regi.strip():
        return blokk
    return regi.rstrip("\r\n") + eol + eol + blokk


def _kivonas_sablon(app, szoveg: str, forras_cim: str, uj_cim: str) -> str:
    """A beállított kivonás-sablon kiértékelése (nincs beállítva: a szöveg szó szerint). Hiányzó sablon: 404."""
    ut = str(app.cfg.section("beallitasok").get("fajlok", {}).get("kivonas_sablon", "") or "").strip()
    if not ut:
        return szoveg
    sb = sablon.beallitasok(app.cfg)
    try:
        rp = norm_path(ut if ut.lower().endswith(".md") else ut + ".md")
        alap = app.vault.read(rp)["tartalom"]
    except (Invalid, NotFound):
        raise _hiba(404, f"nincs ilyen kivonás-sablon: {ut}", "komponalo.sablon_nincs", ut=ut) from None
    most = datetime.now().astimezone()
    return sablon.kiertekel(alap, uj_cim, most, nyelv=sb["nyelv"], datum=sb["datum"], ido=sb["ido"],
                            extra={"content": szoveg, "fromtitle": forras_cim, "newtitle": uj_cim}).szoveg


# ====================================================================== kivonás


def kivon(app, d) -> dict:
    """A `POST /api/komponalo/kivon` törzse. `d`: `{forras, szoveg, cel}` — a `cel` vagy `{mod: "uj", nev, mappa?}` (a `mappa` híján az új
    jegyzetek beállított helye), vagy `{mod: "meglevo", ut, hely: "veg"|"eleje"}`. → `{ok, ut, nev, letrejott, pillanat, figyelmeztetes}`;
    a forrás szövegét a szerkesztő cseréli (a core nem nyúl a forráshoz)."""
    if not isinstance(d, dict):
        raise _hiba(400, "a kérés törzse objektum", "komponalo.torzs")
    vault = app.vault
    szoveg, cel = d.get("szoveg"), d.get("cel")
    if not isinstance(szoveg, str) or not szoveg.strip():
        raise _hiba(400, "nincs mit kivonni (üres a szöveg)", "komponalo.szoveg_kell")
    if len(szoveg) > MAX_SZOVEG:
        raise _hiba(400, "túl nagy a kivonandó szöveg", "komponalo.tul_nagy")
    forras = _jegyzet_ut(vault, d.get("forras"), "forras")
    if not isinstance(cel, dict) or cel.get("mod") not in ("uj", "meglevo"):
        raise _hiba(400, "a cél új vagy meglévő jegyzet lehet", "komponalo.cel_mod")
    forras_cim = _nev(forras)
    if cel["mod"] == "uj":
        nev = cel.get("nev")
        if not isinstance(nev, str) or not nev.strip():
            raise _hiba(400, "hiányzik az új jegyzet neve", "komponalo.nev_kell")
        mappa = cel.get("mappa")
        if mappa is None:
            kerelem = vault.link_jegyzet_helye(nev, forras)
        elif isinstance(mappa, str):
            kerelem = {"mappa": mappa, "nev": nev}
        else:
            raise _hiba(400, "a `mappa` szöveg lehet", "komponalo.mappa_alak")
        uj_cim = vaultio.nfc(kerelem["nev"]).strip()
        tartalom = _kivonas_sablon(app, szoveg, forras_cim, uj_cim)
        if not tartalom.endswith("\n"):
            tartalom += "\n"
        r = vault.create({**kerelem, "tartalom": tartalom})        # névütközés / hibás név: Invalid, semmi sem íródik
        return {"ok": True, "ut": r["ut"], "nev": _nev(r["ut"]), "letrejott": True, "pillanat": r.get("pillanat"),
                "figyelmeztetes": r.get("figyelmeztetes")}
    hely = cel.get("hely", "veg")
    if hely not in HELYEK:
        raise _hiba(400, "a hely a jegyzet vége vagy eleje lehet", "komponalo.hely")
    ut = _jegyzet_ut(vault, cel.get("ut"), "cel")
    if ut.casefold() == forras.casefold():
        raise _hiba(400, "a forrás és a cél ugyanaz a jegyzet", "komponalo.azonos")
    if _mentetlen(app, ut):
        raise _hiba(409, f"{ut} nyitva van mentetlen változással", "komponalo.mentetlen", ut=ut)
    olvasott = vault.read(ut)
    if olvasott["kodolas_hiba"]:
        raise _hiba(409, f"{ut} nem érvényes UTF-8: nem írható át", "komponalo.kodolas", ut=ut)
    beszurando = _kivonas_sablon(app, szoveg, forras_cim, _nev(ut))
    uj = beillesztes(olvasott["tartalom"], beszurando, hely)
    r = vault.write({"ut": ut, "alap": olvasott["hash"], "tartalom": uj, "elso": True, "pillanat": True})
    return {"ok": True, "ut": ut, "nev": _nev(ut), "letrejott": False, "pillanat": r.get("pillanat"),
            "figyelmeztetes": r.get("figyelmeztetes")}


# ====================================================================== összefűzés


@dataclass
class _Osszefuzes:
    forras: str
    cel: str
    hely: str
    blokkolok: list[str] = field(default_factory=list)
    figyelmeztetesek: list[dict] = field(default_factory=list)
    forras_bajt: bytes = b""
    cel_bajt: bytes = b""
    cel_uj: bytes = b""
    terv: _Terv | None = None
    irasok: dict[str, tuple[bytes, bytes]] = field(default_factory=dict)       # út → (régi, új) bájtok; a cél az első
    tulajdonsagok: dict = field(default_factory=dict)
    hash: str = ""


def _sha1(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()


def _dekodol(b: bytes) -> str | None:
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _alap(app, forras, cel, hely) -> _Osszefuzes:
    """Az összefűzés terve (csak olvas). Az alaki hibák kivételek, a vault állapotából jövő akadályok a `blokkolok`-ban."""
    vault = app.vault
    if hely not in HELYEK:
        raise _hiba(400, "a hely a jegyzet vége vagy eleje lehet", "komponalo.hely")
    f, c = _jegyzet_ut(vault, forras, "forras"), _jegyzet_ut(vault, cel, "cel")
    if f.casefold() == c.casefold():
        raise _hiba(400, "a forrás és a cél ugyanaz a jegyzet", "komponalo.azonos")
    m = _Osszefuzes(f, c, hely)
    nyitott = _mentetlen(app, f, c)
    if nyitott:
        m.blokkolok.append(f"Unsaved changes: {', '.join(nyitott)}. Save or close them first.")
    m.forras_bajt, m.cel_bajt = vault.lemezen(f).read_bytes(), vault.lemezen(c).read_bytes()
    f_szoveg, c_szoveg = _dekodol(m.forras_bajt), _dekodol(m.cel_bajt)
    if f_szoveg is None or c_szoveg is None:
        m.blokkolok.append("A note is not valid UTF-8 and cannot be merged safely.")
    fajlok = [rp for rp, _ in feloldas.bejaras(vault.root)]
    if f not in fajlok or c not in fajlok:
        m.blokkolok.append("A note is not in the index yet. Try again in a moment.")
    if m.blokkolok:
        m.hash = _sha1(json.dumps([f, c, hely, m.blokkolok], sort_keys=True).encode("utf-8"))
        return m
    # a forrásra mutató linkek átírása: az átnevezés tervezője a {forrás → cél} leképezéssel
    terv = _Terv(f, c, [], {}, lek={f: c})
    app.atnevezes._terv_kozos(terv, fajlok)
    m.terv = terv
    m.blokkolok += terv.blokkolok
    if m.blokkolok:
        m.hash = _sha1(json.dumps([f, c, hely, m.blokkolok], sort_keys=True).encode("utf-8"))
        return m
    forras_uj = terv.fajlok[f].uj.decode("utf-8", "replace") if f in terv.fajlok else f_szoveg
    cel_alap = terv.fajlok[c].uj.decode("utf-8", "replace") if c in terv.fajlok else c_szoveg
    fm_f, torzs_f = _fm_torzs(forras_uj)
    fm_c, torzs_c = _fm_torzs(cel_alap)
    fm_uj = fm_c
    if fm_f:
        # a frontmatter nélküli cél üres blokkot kap alapnak: az egyesítés ugyanazokkal a szabályokkal fut
        ered = app.tulajdonsagok.osszefesul(c, fm_c or "---\n---\n", fm_f)
        m.tulajdonsagok = {k: ered[k] for k in ("hozzaadva", "egyesitve", "kitoltve", "megmaradt", "kihagyva", "fuggo")}
        if any(x.get("kulcs") is None for x in ered["kihagyva"]):
            m.blokkolok.append("A note has invalid frontmatter: " + "; ".join(x["uzenet"] for x in ered["kihagyva"] if x.get("kulcs") is None))
        elif fm_c or ered["valtozas"]:
            fm_uj = ered["fm_uj"] or ""
    if not m.blokkolok:
        eol = _eol(cel_alap)
        forras_blokk = torzs_f.replace("\r\n", "\n").strip("\n").replace("\n", eol)
        if not forras_blokk:                                    # üres forrástörzs: a cél törzse változatlan
            uj_torzs = torzs_c
        elif hely == "eleje":
            uj_torzs = (forras_blokk + eol + eol + torzs_c.lstrip("\r\n")) if torzs_c.strip() else forras_blokk + eol
        else:
            uj_torzs = (torzs_c.rstrip("\r\n") + eol + eol + forras_blokk + eol) if torzs_c.strip() else forras_blokk + eol
        if fm_uj and uj_torzs and not fm_uj.endswith("\n"):
            fm_uj += eol
        uj_szoveg = fm_uj + uj_torzs
        if len(uj_szoveg) > MAX_SZOVEG:
            m.blokkolok.append("The merged note would be too large.")
        m.cel_uj = uj_szoveg.encode("utf-8")
        m.irasok[c] = (m.cel_bajt, m.cel_uj)
        for rp, fj in sorted(terv.fajlok.items()):
            if rp not in (f, c):
                m.irasok[rp] = (fj.regi, fj.uj)
        beagyazas = sum(1 for fj in terv.fajlok.values() for sor in fj.szerk if "![" in sor["regi"])
        if beagyazas:
            m.figyelmeztetesek.append({"kod": "beagyazas", "db": beagyazas})
        if m.tulajdonsagok.get("fuggo"):
            m.figyelmeztetesek.append({"kod": "fuggo_tulajdonsag", "kulcsok": [x["kulcs"] for x in m.tulajdonsagok["fuggo"]]})
        if m.tulajdonsagok.get("megmaradt"):
            m.figyelmeztetesek.append({"kod": "megmaradt_ertek", "kulcsok": list(m.tulajdonsagok["megmaradt"])})
    m.hash = _sha1(json.dumps(
        [f, c, hely, _sha1(m.forras_bajt), _sha1(m.cel_bajt), _sha1(m.cel_uj), m.blokkolok,
         [[rp, _sha1(a), _sha1(b)] for rp, (a, b) in sorted(m.irasok.items())]], sort_keys=True).encode("utf-8"))
    return m


def osszefuz_terv(app, forras, cel, hely="veg") -> dict:
    """A `POST /api/komponalo/osszefuz/terv` törzse: a felhasználó által jóváhagyandó terv (a terv a megerősítés). Csak olvas."""
    m = _alap(app, forras, cel, hely)
    fajlok = []
    if m.terv is not None:
        for rp, fj in sorted(m.terv.fajlok.items()):
            if rp != m.forras:
                fajlok.append({"ut": rp, "darab": fj.darab, "linkek": fj.szerk})
    elotte = _dekodol(m.cel_bajt) or ""
    utana = _dekodol(m.cel_uj) or ""
    return {"ok": not m.blokkolok, "forras": m.forras, "cel": m.cel, "hely": m.hely, "blokkolok": m.blokkolok,
            "figyelmeztetesek": m.figyelmeztetesek, "tulajdonsagok": m.tulajdonsagok,
            "cel_sorok": {"elotte": elotte.count("\n"), "utana": utana.count("\n")},
            "fajlok": fajlok, "modositott_linkek": sum(f["darab"] for f in fajlok), "kukaba": m.forras, "terv_hash": m.hash}


def _kuka(app, ut) -> None:
    csatolmany.kuka(app, {"ut": ut, "megerosit": True})


def osszefuz_vegrehajt(app, forras, cel, hely, terv_hash, kukaba=None) -> dict:
    """A `POST /api/komponalo/osszefuz` törzse. `kukaba(app, ut)`: a forrás Kukába helyezése (a tesztek cserélik)."""
    vault, at = app.vault, app.atnevezes
    m = _alap(app, forras, cel, hely)                           # az alaki hibák (400) előbb, mint az állapot-akadályok (409)
    repo = vault.repo()
    if repo is None:
        raise _hiba(409, "nincs élő pillanatkép-tároló: pillanatkép nélkül nem fűzök össze", "komponalo.nincs_pillanatkep")
    if at.busy():
        raise _hiba(409, "egy vault-író feladat fut", "komponalo.foglalt")
    if m.blokkolok:
        raise _hiba(409, "az összefűzés nem hajtható végre: " + " ".join(m.blokkolok), "komponalo.blokkolt", ok=" ".join(m.blokkolok))
    if not isinstance(terv_hash, str) or terv_hash != m.hash:
        raise _hiba(409, "a vault közben megváltozott — nézd át újra a tervet", "komponalo.terv_valtozott")
    kor = frame.new_id(KOR_ELOTAG)
    try:
        with frame.run_lock(app.cfg, wait=False, turelem_mp=frame.felhasznaloi_turelem(app.cfg)):
            with at._utak_zarolva(m.terv):
                pillanat = _iras_es_commit(app, repo, m, kor)
    except frame.Busy:
        raise _hiba(409, "egy másik vault-művelet fut", "komponalo.foglalt") from None
    modositott = sorted(m.irasok)
    try:                                                         # az index az írások után azonnal (a Kuka-lépés külön frissít)
        app.index.frissit([app.index.lemez_ut(rp) for rp in modositott])
    except Exception:                                            # noqa: BLE001 — az index figyelője úgyis utoléri
        pass
    kukaban, kuka_hiba, torles_pillanat = True, None, None
    try:
        (kukaba or _kuka)(app, m.forras)
    except HttpError as e:
        kukaban, kuka_hiba = False, str(e)
    except OSError as e:
        kukaban, kuka_hiba = False, e.strerror or str(e)
    if kukaban:
        try:
            with frame.run_lock(app.cfg, wait=False, turelem_mp=frame.felhasznaloi_turelem(app.cfg)):
                utak = csatolmany.kovetett(repo, [m.forras])
                if utak:
                    torles_pillanat = repo.commit_machine(
                        f"jegyzet összefűzve és a Kukában: {m.forras} → {m.cel}",
                        {snapshot.TRAILER_RUN: kor, snapshot.TRAILER_ITEM: m.cel, "Mos-Forras": vaultio.FORRAS}, utak)
        except (frame.Busy, snapshot.SnapshotError):
            torles_pillanat = None                               # a törlés a következő kézi commitba kerül; a kör visszavonható marad
    return {"ok": True, "forras": m.forras, "cel": m.cel, "hely": m.hely, "modositott": modositott, "kor": kor,
            "pillanat": pillanat, "torles_pillanat": torles_pillanat, "forras_kukaban": kukaban, "forras_hiba": kuka_hiba,
            "visszavonhato": pillanat is not None}


def _iras_es_commit(app, repo, m: _Osszefuzes, kor: str) -> str | None:
    """A kör-zár és az útvonal-zárak alatt: kézi pillanatkép → hash-ellenőrzés → írások (cél elöl) → egy gépi commit. Bukáskor
    a már megírt fájlok a memóriában tartott eredeti bájtokból visszaállnak."""
    vault, at = app.vault, app.atnevezes
    repo.commit("kézi változások az összefűzés előtt", {"Mos-Forras": "kezi"})
    for rp in (m.forras, m.cel, *m.irasok):
        try:
            b = vault.lemezen(rp).read_bytes()
        except FileNotFoundError:
            raise _hiba(409, f"{rp} közben eltűnt — nézd át újra a tervet", "komponalo.terv_valtozott") from None
        elvart = m.forras_bajt if rp == m.forras else (m.irasok[rp][0] if rp in m.irasok else m.cel_bajt)
        if b != elvart:
            raise _hiba(409, f"{rp} közben megváltozott — nézd át újra a tervet", "komponalo.terv_valtozott")
    lepesek: list[tuple] = []
    try:
        for rp, (regi, uj) in m.irasok.items():
            p = vault.lemezen(rp)
            at._ir(p, uj, regi=regi)
            lepesek.append(("irva", p, regi, uj))
        utak = csatolmany.kovetett(repo, sorted(m.irasok))
        return repo.commit_machine(
            f"jegyzet összefűzve: {m.forras} → {m.cel}",
            {snapshot.TRAILER_RUN: kor, snapshot.TRAILER_ITEM: m.cel, "Mos-Forras": vaultio.FORRAS}, utak) if utak else None
    except BaseException:
        at._visszaallit(lepesek)
        raise


def utvonalak(r) -> None:
    r.post("/api/komponalo/kivon", lambda k: kivon(k.app, k.torzs()))
    r.post("/api/komponalo/osszefuz/terv",
           lambda k: osszefuz_terv(k.app, k.torzs().get("forras"), k.torzs().get("cel"), k.torzs().get("hely") or "veg"))
    r.post("/api/komponalo/osszefuz",
           lambda k: osszefuz_vegrehajt(k.app, k.torzs().get("forras"), k.torzs().get("cel"), k.torzs().get("hely") or "veg",
                                        k.torzs().get("terv_hash")))
