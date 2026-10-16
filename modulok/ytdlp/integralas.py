"""A videó bevitele a vaultba (C20b) — a bevitel 14 lépéses lánca.

    probe → duplikatum → letoltes → nyelv → szovegreteg → tema → elhelyezes → jegyzet → jeloltek → igazolas → beiras
          → verifikacio → naplo → visszajelzes

Minden lépés a staging egy forrásmappáján fut (a link a `video_letoltes` feladattal érkezik oda, a behúzott fájl a `bevitel.py`-val), és
**egy videó = egy gépi tétel** (`Mos-Forras: mos-video`, kör `VIDEOBE-…`): a videó APFS-klónja a videómappa alá (`mozgat`; `[video] vault_mappa`),
a felirat (`<törzs>.<nyelv>.vtt`), a proveniencia (`<törzs>.info.json`) és a forrásleíró jegyzet (`<törzs>.md`, a sentinel-lel) a
`<Téma>/Média/` rétegbe (`uj`), és a kötések `#t=` horgonya a tananyag-jegyzetek `Source:` listájába (`csere`). A tétel egy kattintással
visszavonható (a vezérlő „Mit változtatott” nézete); a videó-klón a visszavonáskor nem törlődik.

**Nincs „kérdezz rá”, minden tétel végállapotba kerül:**

| döntési pont                   | itt                                                                                              |
|--------------------------------|--------------------------------------------------------------------------------------------------|
| téma                           | `itelet.tema_vegso`: biztos / valószínű / bizonytalan téma, a bizonytalan is beíródik (visszavonható) |
| nagy modell                    | a router kalibrált `tema`/`kotes` modellje dönt, ha van; ha nincs, a lexikai út                      |
| erős kötési jelölt             | a verifikátor `auto` sávja beíródik; a `javaslat` a `kotes` modell olvasása után vagy `nem_kotve`   |
| séma- és tartalomkapuk         | a gépi írás kapui (séma, Status, alap-hash) + a horgony utóellenőrzése (`horgony.beir`)              |
| napló                          | nem íródik a vaultba: a futás riportja `{runs}/video/<kör>.json`, a commit, a vezérlő nézete         |

A tétel végállapotai: `integralva`, `mar_megvan`, `utkozes`, `nincs_tema`, `atirat_kalibralatlan`, `hiba` (a staging `integration.json`
ennek megfelelően `integrated` / `in_review`; a kalibrálatlan átirat és a hiba `pending` marad: a következő kör újrapróbálja).

Modell-kimenet (az átirat, a modell téma-ítélete, a modell kötés-olvasása) élesben csak kalibrált modellből íródik; a kifejezett modell
mindig próba (`proba: true`: a gépi írás a vault APFS-klónjára megy). A lexikai besorolás és a verifikátor determinisztikus: `modell: null`.

**Célmappa**: a `tema_mappa` (`--tema-mappa "<témamappa>"`, a Bevitel „Célmappa (téma)” mezője) a 6. lépést determinisztikussá teszi: a téma
a megadott mappa (`forras: "célmappa"`, `biztos`), a téma-modell és a lexikai besorolás nem fut, a staging tárgya nem számít; a kötés csak
a mappa saját jegyzeteihez (új mappánál nincs); a mellékletek a `<célmappa>/Média/` rétegbe, a hiányzó mappát a gépi írás első `uj`
művelete hozza létre ugyanabban a tételben. Az átirat szabálya változatlan: kész staging-átirat vagy kalibrált `atirat` nélkül a tétel
`pending` marad.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from core import gepi_kliens, videolanc

from . import egyezes as X
from . import elhelyezes, horgony, itelet, konvertalas, kotes as KT, staging, vaultoldal as VO
from .modell import Modellek, NincsModell
from .szovegreteg import K, cuek as vtt_cuek, longwords, nfc

FORRAS = "mos-video"
KOR_ELOTAG = "VIDEOBE"
LEPESEK = ("probe", "duplikatum", "letoltes", "nyelv", "szovegreteg", "tema", "elhelyezes", "jegyzet", "jeloltek", "igazolas",
           "beiras", "verifikacio", "naplo", "visszajelzes")
VEGALLAPOTOK = ("integralva", "mar_megvan", "utkozes", "nincs_tema", "atirat_kalibralatlan", "hiba", "kihagyva")
STAGING_ALLAPOT = {"integralva": "integrated", "mar_megvan": "integrated", "utkozes": "in_review", "nincs_tema": "in_review"}
# A staging forrás `targy` mezője (a letöltő tantárgy-nevei) → a tantárgy betűje. Az igazság a core `[pdf.tags]` táblázata (betű → címke):
# a `targy_terkep` annak a fordítottját veszi, és erre az alapra írja rá; ez az alap, ha a táblázat hiányzik vagy nem nevezi meg a tárgyat.
TARGY_TERKEP = {"Történelem": "T", "Irodalom": "I", "Magyar nyelv": "N", "Nyelvtan": "N", "Matematika": "M", "Fizika": "F",
                "Digitális kultúra": "D", "Angol": "E"}
MAX_KOTES_OLVASAS = 20          # videónként legfeljebb ennyi kötési javaslatot olvas el a modell
ASR_HANGFEDETTSEG_MIN = 0.75    # media.atirat.gepi.degeneralt_kuszob


def job_key(meta: dict) -> str:
    """`<extractor>-<videóazonosító>` (a munkamappa kulcsa: a link és a staging ugyanazt adja)."""
    ex = re.sub(r"[^a-z0-9]+", "", str(meta.get("extractor_key") or meta.get("extractor") or "media").lower())
    vid = re.sub(r"[^A-Za-z0-9_-]+", "_", str(meta.get("id") or ""))
    if not vid:
        raise staging.StagingHiba("a metaadatban nincs videóazonosító — a duplikátum-szűrés nem futtatható")
    return f"{ex or 'media'}-{vid}"


def targy_terkep(cimkek: dict | None = None) -> dict[str, str]:
    """`{tantárgy-név: betű}`: a `[pdf.tags]` (`{betű: címke}`) fordítottja az alap (`TARGY_TERKEP`) fölött; azonos címkénél az első betű."""
    ki = dict(TARGY_TERKEP)
    forditott: dict[str, str] = {}
    for betu, cimke in (cimkek or {}).items():
        if isinstance(cimke, str) and cimke.strip() and str(betu).strip():
            forditott.setdefault(nfc(cimke.strip()), str(betu).strip())
    ki.update(forditott)
    return ki


def targy_betu(src: dict, cimkek: dict | None = None) -> str | None:
    return targy_terkep(cimkek).get(nfc(src.get("targy") or ""))


def vault_videok(vault: Path, tema_minta=None, kizart_mappak=None) -> dict[str, str]:
    """`{videóazonosító: a melléklet vault-útja}` a témák `Média/` rétegének `.info.json`-jaiból."""
    ki: dict[str, str] = {}
    for t in X.temak(vault, tema_minta, kizart_mappak):
        d = vault / t / elhelyezes.ALAP_RETEG
        if not d.is_dir():
            continue
        for f in sorted(os.listdir(d)):
            if f.endswith(".info.json"):
                try:
                    vid = json.loads((d / f).read_text(encoding="utf-8")).get("id")
                except (OSError, ValueError):
                    continue
                if vid is not None:
                    ki.setdefault(str(vid), nfc(f"{t}/{elhelyezes.ALAP_RETEG}/{f}"))
    return ki


@dataclass
class Tetel:
    mappa: str
    allapot: str = "uj"
    uzenet: str | None = None
    kulcs: str | None = None
    cim: str | None = None
    lepesek: dict = field(default_factory=dict)
    tema: dict | None = None
    jeloltek: list = field(default_factory=list)
    utak: list = field(default_factory=list)
    commit: str | None = None
    jelek: dict = field(default_factory=dict)       # lépés → a modell-jel

    def jel(self, lepes: str, allapot: str = "kesz", **reszlet) -> None:
        self.lepesek[lepes] = {"allapot": allapot, **reszlet}


class Stop:
    def __init__(self, ut: str | None):
        self.ut = ut

    def __call__(self) -> bool:
        return bool(self.ut) and os.path.exists(self.ut)


class Integralas:
    """`proba`: a gépi írás a vault APFS-klónjára megy, a staging és a `var/` állapota nem változik. `kifejezett`: feladat → modell
    (csak próbában). `mappak`: a feldolgozandó staging-forrásmappák (alap: a staging összes `pending` forrása)."""

    def __init__(self, cfg, *, proba: bool = False, kifejezett: dict | None = None, stop=None, log=print,
                 modellek: Modellek | None = None, gepi=gepi_kliens, ffmpeg: str | None = None, max_db: int | None = None,
                 felmeres=None, temak: dict[str, str] | None = None, tema_mappa: str | None = None):
        self.cfg, self.proba, self.log = cfg, proba, log
        self.stop = stop or (lambda: False)
        self.M = modellek or Modellek(cfg, kifejezett)
        self.gepi = gepi
        self.vault = cfg.path("vault")
        v = cfg.section("video")
        self.video_mappa = str(v.get("vault_mappa") or elhelyezes.ALAP_VIDEO_MAPPA)
        self.bizonytalan_ir = str(v.get("bizonytalan_tema", "ir")) == "ir"
        self.max_db = max_db or int(v.get("integralas_max", 50))
        self.ffmpeg = ffmpeg or str(cfg.path("ffmpeg"))
        self.felmeres = felmeres or konvertalas.felmeres
        self.temak_felulir = dict(temak or {})     # kulcs → téma: a `--tema-felulir` (gazdai döntés) megfelelője, a próbakörnek
        self.cimkek = dict(cfg.section("pdf").get("tags") or {})
        self.index_kw = X.index_beallitas(cfg)      # `[video] tema_minta`, `kizart_mappak`, `[fuzet] elmelet_mappa`
        # 86. döntés (javasolt): a kényszerített célmappa — a téma determinisztikus (a téma-modell és a lexikai besorolás nem fut, a
        # staging tárgya nem számít), a kötés csak a mappa saját jegyzeteihez; az ellenőrzés egyetlen helye a `core/videolanc.py`
        self.tema_mappa = (videolanc.temamappa_ellenoriz(self.vault, tema_mappa, self.cimkek) if tema_mappa is not None else None)
        self.kor: str | None = None
        self._idx: X.NoteIndex | None = None
        self._korp: KT.Korpusz | None = None
        self._klon: Path | None = None
        app = cfg.path("video_jobs").parent
        self.elvet = KT.elvetettek(app / "kotes" / "elvetett.jsonl")

    # -------------------------------------------------- közös

    def idx(self) -> X.NoteIndex:
        if self._idx is None:
            t0 = time.time()
            self._idx = X.NoteIndex(self.vault, **self.index_kw)
            self._korp = KT.Korpusz(self._idx)
            self.log(f"[videó] jegyzetindex: {self._idx.nd} elméleti jegyzet, {len(self._idx.topics)} téma ({time.time() - t0:.1f} s)")
        return self._idx

    def korp(self) -> KT.Korpusz:
        self.idx()
        return self._korp

    def _allapot_mappa(self, kulcs: str) -> Path:
        if self.proba:
            return self.cfg.path("tmp") / "video-proba" / (self.kor or "kor") / kulcs
        return self.cfg.path("video_jobs") / kulcs

    def _allapot_ir(self, t: Tetel) -> None:
        if not t.kulcs:
            return
        d = self._allapot_mappa(t.kulcs)
        d.mkdir(parents=True, exist_ok=True)
        p = d / "integralas.json"
        tmp = d / f".integralas.json.{os.getpid()}.manifold-tmp"
        tmp.write_text(json.dumps({"kor": self.kor, "proba": self.proba, "ido": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                   **dataclasses.asdict(t)}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        os.replace(tmp, p)

    def _olvas(self, rp: str) -> dict:
        """A cél jegyzet szövege és hash-e: élesben a core-ból; próbában a kör klónjából, ha az már létezik."""
        if self.proba and self._klon is not None and (self._klon / rp).is_file():
            b = (self._klon / rp).read_bytes()
            return {"tartalom": b.decode("utf-8"), "hash": hashlib.sha1(b).hexdigest()}
        return self.gepi.olvas(rp)

    # -------------------------------------------------- a lánc

    def jeloltek(self, mappak: list[Path] | None = None) -> list[Path]:
        if mappak:
            ki = []
            for m in mappak:
                ki += [Path(x) for x in staging.forrasmappak(m)]
            return ki[: self.max_db]
        ki = []
        for d in staging.forrasmappak(self.cfg.path("staging")):
            try:
                st = json.loads(Path(d, "integration.json").read_text(encoding="utf-8")).get("integration_status")
            except (OSError, ValueError):
                continue
            if st == "pending":
                ki.append(Path(d))
            if len(ki) >= self.max_db:
                break
        return ki

    def futtat(self, mappak: list[Path] | None = None) -> dict:
        forrasok = self.jeloltek(mappak)
        self.kor = gepi_kliens.uj_kor(KOR_ELOTAG)
        self.log(f"[videó] {self.kor}: {len(forrasok)} forrás" + (" · PRÓBA (a vault APFS-klónján)" if self.proba else ""))
        tetelek: list[Tetel] = []
        vaultban = vault_videok(self.vault, self.index_kw["tema_minta"], self.index_kw["kizart_mappak"]) if forrasok else {}
        megallt = False
        for i, m in enumerate(forrasok):
            if self.stop():
                megallt = True
                self.log("[videó] megállítva a tétel végén")
                break
            self.log(f"[manifold-progress] {int(100 * i / max(len(forrasok), 1))}%")
            t = Tetel(str(m))
            tetelek.append(t)
            try:
                self.egy(t, vaultban)
            except NincsModell as e:
                t.allapot, t.uzenet = "atirat_kalibralatlan", str(e)
            except gepi_kliens.GepiHiba as e:
                t.allapot, t.uzenet = "hiba", f"gépi írás ({e.kod}): {e}"
            except Exception as e:  # noqa: BLE001 — a tétel végállapotot kap, a kör megy tovább (D1)
                t.allapot, t.uzenet = "hiba", f"{type(e).__name__}: {e}"
            self.log(f"[videó] {t.cim or Path(t.mappa).name}: {t.allapot}" + (f" — {t.uzenet}" if t.uzenet else ""))
            self._visszajelzes(t)
            self._allapot_ir(t)
        self.log("[manifold-progress] 100%")
        return self._riport(tetelek, megallt)

    def egy(self, t: Tetel, vaultban: dict[str, str]) -> None:
        # 1. probe — a staging forrásmappa beolvasva és ellenőrizve (msp séma 1)
        src = staging.olvas(t.mappa)
        mm = staging.meta_min(src)
        t.kulcs, t.cim = job_key(mm), src["cim"]
        t.jel("probe", cim=src["cim"], lap=src.get("lap"), targy=src.get("targy"))
        # 2. duplikatum — a videóazonosító a vault `Média/` rétegének info.json-jaiban
        if src["video_id"] in vaultban:
            t.jel("duplikatum", "mar_megvan", ut=vaultban[src["video_id"]])
            t.allapot, t.uzenet = "mar_megvan", f"már a vaultban: {vaultban[src['video_id']]}"
            return
        t.jel("duplikatum", talalat=0)
        # 3. letoltes — a staging videója (a vaultba a gépi írás klónozza; itt csak mérünk)
        torzs = elhelyezes.fajlnev_torzs(src["cim"])
        kit = os.path.splitext(src["media"])[1].lower() or ".mp4"
        video_nev = torzs + kit
        felm = self.felmeres(self.ffmpeg, src["media"])
        hossz = felm.hossz_s
        meret = os.path.getsize(src["media"])
        t.jel("letoltes", fajl=video_nev, meret=meret, hossz_s=round(hossz) if hossz else None, forras="staging (APFS-klón a vaultba)")
        # 4–5. nyelv és szövegréteg
        vtt, nyelv, atirat_info = self._szovegreteg(t, src, video_nev, hossz)
        vtt_nev = f"{torzs}.{nyelv}.vtt"
        f = X.Forras(video_nev, vtt_cuek(vtt), hossz or -1.0)
        # 6. tema
        targy = targy_betu(src, self.cimkek)
        if self.tema_mappa:
            targy = X.targy(self.tema_mappa)
            v = {"tema": self.tema_mappa, "forras": "célmappa", "biztossag": "biztos",
                 "jel": "a hívó megadta a célmappát (--tema-mappa): a téma-modell és a lexikai besorolás nem fut"}
            t.jel("tema", **v)
        elif t.kulcs in self.temak_felulir:
            v = {"tema": self.temak_felulir[t.kulcs], "forras": "megadott", "biztossag": "biztos", "jel": "a hívó adta meg (--tema-felulir)"}
            t.jel("tema", **v)
        else:
            v = self._tema(t, src, f, nyelv, targy)
        t.tema = {k: v[k] for k in ("tema", "forras", "biztossag", "jel")}
        if not v["tema"]:
            t.allapot, t.uzenet = "nincs_tema", v.get("jel") or "nincs jelölt téma"
            return
        if v["biztossag"] == "bizonytalan" and not self.bizonytalan_ir:
            t.allapot, t.uzenet = "nincs_tema", f"bizonytalan téma ({v['tema']}), a beállítás szerint nem íródik"
            return
        tema = v["tema"]
        # 7. elhelyezes — a terv (ütközésnél semmi: mindent vagy semmit, felülírás nincs)
        info_nev = f"{torzs}.info.json"
        terv = elhelyezes.terv(self._olvaso_vault(), tema, [video_nev, vtt_nev, info_nev], video_mappa=self.video_mappa,
                               torzs=torzs, sentinel=VO.SENTINEL)
        if terv["utkozesek"]:
            t.jel("elhelyezes", "utkozes", utkozesek=terv["utkozesek"])
            t.allapot, t.uzenet = "utkozes", "névütközés (felülírás nincs): " + ", ".join(terv["utkozesek"])
            return
        cel = terv["cel"]
        t.jel("elhelyezes", cel=cel, video_cel=terv["video_cel"], fajlok=sorted([video_nev, vtt_nev, info_nev]))
        # 8. jegyzet — a forrásleíró jegyzet (idempotens, a sentinel-lel)
        info_szoveg = VO.info_json_szoveg(src)
        info = json.loads(info_szoveg)
        jegyzet = VO.forrasjegyzet(video_nev, cimke=self.cimkek.get(X.targy(tema) or ""), info=info, hossz=hossz, meret=meret,
                                   feliratok=[VO.felirat_sor(vtt_nev, vtt)], info_nev=info_nev,
                                   egyezes=None, fedettseg_=VO.fedettseg(vtt, hossz))
        jegyzet_ut = f"{cel}/{torzs}.md"
        t.jel("jegyzet", jegyzet=jegyzet_ut)
        # 9. jeloltek + 10. igazolas (D1: nincs várakozás)
        elfogadott = self._kotes(t, f, nyelv, tema, targy, csak_tema=bool(self.tema_mappa))
        # 11. beiras — egy tétel: videó (klón) + mellékletek + jegyzet + a horgonyok
        muveletek = [{"tipus": "mozgat", "forras": str(Path(src["media"]).resolve()), "ut": f"{self.video_mappa}/{video_nev}",
                      "sha256": _sha256(src["media"])},
                     self.gepi.uj(f"{cel}/{vtt_nev}", vtt), self.gepi.uj(f"{cel}/{info_nev}", info_szoveg),
                     self.gepi.uj(jegyzet_ut, jegyzet, osztaly="normal")]
        horgonyzott: list[str] = []
        for rp in sorted({c["jegyzet"] for c in elfogadott}):
            cs = [c for c in elfogadott if c["jegyzet"] == rp]
            try:
                o = self._olvas(rp)
                uj, eredm = horgony.beir(o["tartalom"], [(video_nev, c["vegso_t"]) for c in cs])
            except (horgony.HorgonyHiba, gepi_kliens.GepiHiba) as e:
                for c in cs:
                    c["beiras_hiba"] = str(e)
                continue
            for c, (_, _, st) in zip(cs, eredm):
                c["beirva"] = st
            if uj != o["tartalom"]:
                muveletek.append(self.gepi.csere(rp, uj, o["hash"]))
                horgonyzott.append(rp)
        jelek = [j for j in t.jelek.values() if j]
        modell_jel = next((j for j in jelek if j.get("proba")), None) or (jelek[0] if jelek else None)
        biztos = "nincs" if not horgonyzott else ("biztos" if v["biztossag"] == "biztos" and
                                                  all(c.get("ki") == "gep" for c in elfogadott if c["jegyzet"] in horgonyzott)
                                                  else "valoszinu")
        r = self.gepi.ir(self.kor, f"video-{t.kulcs}", FORRAS, muveletek,
                         uzenet=f"videó: {torzs} → {tema}"[:200], proba=self.proba, modell=modell_jel,
                         dontes=f"téma: {tema} ({v['biztossag']}, {v['forras']}); horgony: {len(horgonyzott)} jegyzet"[:200],
                         esemeny={"tipus": "integralt_video", "ut": jegyzet_ut,     # 5. pont: Tracker.integralt_video (a core hívja)
                                  "adat": {"video_s": int(round(hossz or 0)), "jegyzet_db": len(horgonyzott), "kotes": biztos}})
        if r.get("proba_mappa"):
            self._klon = Path(r["proba_mappa"]) / self.vault.name
        t.commit, t.utak = r.get("sha"), list(r.get("utak") or []) + list(r.get("mozgatva") or [])
        t.jel("beiras", irva=len(horgonyzott), commit=r.get("sha"), proba=self.proba)
        # 12. verifikacio — a gépi írás kapui (séma, Status, alap-hash) + a horgony utóellenőrzése (horgony.beir) futott
        hiba = [c for c in elfogadott if c.get("beiras_hiba")]
        t.jel("verifikacio", g4="teljesul", visszautasitva=len(hiba))
        # 13. naplo — a riport a {runs} alatt (a vaultba nem íródik: a commit és a vezérlő „Mit változtatott” nézete viszi)
        t.jel("naplo", naplo="riport")
        t.allapot = "integralva"
        if atirat_info and atirat_info.get("hangfedettseg") is not None and atirat_info["hangfedettseg"] < ASR_HANGFEDETTSEG_MIN:
            t.uzenet = f"a gépi átirat hangfedettsége {atirat_info['hangfedettseg']} — a kimaradt szakaszra nem képezhető horgony"

    def _olvaso_vault(self) -> Path:
        return self._klon if (self.proba and self._klon is not None) else self.vault

    # -------------------------------------------------- 4–5. nyelv és szövegréteg

    def _szovegreteg(self, t: Tetel, src: dict, video_nev: str, hossz: float | None) -> tuple[str, str, dict | None]:
        a = src.get("atirat") or {}
        snyelv = itelet.norm_lang(a.get("language"))
        if src.get("atirat_kesz") and snyelv and src.get("felirat"):
            # a kiadói felirat (a bejárás közvetlen fájljáé, 84. d. javasolt kiegészítése): szó szerint, mért időbélyegekkel, „kiadói” (L44)
            vtt = Path(src["felirat"]).read_text(encoding="utf-8")
            t.jel("nyelv", nyelv=snyelv, kod="staging", forras="a kiadói felirat nyelve")
            t.jel("szovegreteg", osztaly="kiadói", fajl=f"{Path(video_nev).stem}.{snyelv}.vtt", cue=len(vtt_cuek(vtt)),
                  hangfedettseg=VO.fedettseg(vtt, hossz), forras=f"staging — {Path(src['felirat']).name}, a kiadó felirata")
            return vtt, snyelv, None
        if src.get("atirat_kesz") and snyelv:
            vtt = VO.vtt_stagingbol(src, snyelv, hossz)
            t.jel("nyelv", nyelv=snyelv, kod="staging", forras="a staging átiratának nyelve (config transcript.language)")
            t.jel("szovegreteg", osztaly="gépi", fajl=f"{Path(video_nev).stem}.{snyelv}.vtt", cue=len(vtt_cuek(vtt)),
                  hangfedettseg=VO.fedettseg(vtt, hossz), forras=f"staging — {a.get('transcript_engine')}, újra-ASR nélkül")
            return vtt, snyelv, None
        # a lánc maga ír át: a router kalibrált `atirat` modellje (élesben), vagy a kifejezett (próba); a nyelvet a hang dönti
        if not self.M.van("atirat"):
            raise NincsModell("nincs kész staging-átirat, és az `atirat` feladatra nincs kalibrált modell: a tétel a "
                              "kalibráció után a következő körben fut (élesben kalibrálatlan modellel nem írunk át)")
        r, jel = self.M.atir(src["media"], itelet.norm_lang(src["source"].get("language")))
        t.jelek["atirat"] = jel
        nyelv = itelet.norm_lang(r.get("nyelv")) or "hu"
        vtt = VO.vtt_atiratbol(r, nyelv, modell=str(r.get("model") or jel["modell"]),
                               nyelv_forras="hang (a felismerő)" if not src["source"].get("language") else "metaadat",
                               keszult=time.strftime("%Y-%m-%d"))
        cov, ism = VO.minoseg(r.get("szegmensek") or [], hossz)
        t.jel("nyelv", nyelv=nyelv, kod="hang", forras="a gépi átirat felismert nyelve")
        t.jel("szovegreteg", osztaly="gépi", fajl=f"{Path(video_nev).stem}.{nyelv}.vtt", cue=len(vtt_cuek(vtt)),
              hangfedettseg=cov, ismetles=ism, modell=jel["modell"], proba=jel["proba"])
        return vtt, nyelv, {"hangfedettseg": cov, "ismetles": ism}

    # -------------------------------------------------- 6. téma

    def _tema(self, t: Tetel, src: dict, f: X.Forras, nyelv: str, targy: str | None) -> dict:
        idx = self.idx()
        wins = X.windows(f, idx)
        cls = X.classify(f, idx, nyelv, wins, csak_targy=targy)
        d = None
        if not cls["auto"] and self.M.van("tema"):
            temak = itelet.temak_targyban(idx, targy)
            if not targy:
                temak = [x for x, _ in X.rank_topics(f, idx)[:12]]
            if temak:
                lista = itelet.temalista(temak, idx)
                pa, pb = itelet.tema_promptok(f.szoveg(), src["cim"], src.get("lap"), lista)
                va, ja = self.M.kerdez("tema", pa, itelet.TEMA_MAX_TOKEN) if pa else ("", None)
                vb, jb = self.M.kerdez("tema", pb, itelet.TEMA_MAX_TOKEN)
                ia, ib = itelet.sorszam(va, len(temak)), itelet.sorszam(vb, len(temak))
                it = {"tartalom": temak[ia - 1] if ia else None, "metaadat": temak[ib - 1] if ib else None,
                      "valasz": {"tartalom": va, "metaadat": vb}, "lista": itelet.lista_hash(temak), "modell": jb["modell"]}
                rang = [x for x in cls["rang"] if x[0] in set(temak)] if targy else \
                    [x for x in X.rank_topics(f, idx) if x[0] in set(temak)]
                d = itelet.tema_dontes(it, rang, cls.get("cim_tema"))
                d["itelet"] = it
                t.jelek["tema"] = next((j for j in (ja, jb) if j and j.get("proba")), jb)
        v = itelet.tema_vegso(cls, d, targy)
        if v["forras"] != "modell":
            t.jelek.pop("tema", None)        # a modell ítélete nem döntött: a tétel nem modell-kimenet a témában
        t.jel("tema", tema=v["tema"], forras=v["forras"], biztossag=v["biztossag"], jel=v["jel"],
              besorolas={k: cls.get(k) for k in ("auto", "auto_jel", "cim_tema", "margo", "top3", "okok", "targy_szukites")},
              modell=(d or {}).get("itelet"))
        return v

    # -------------------------------------------------- 9–10. kötés

    def _kotes(self, t: Tetel, f: X.Forras, nyelv: str, tema: str, targy_: str | None, csak_tema: bool = False) -> list[dict]:
        if nyelv != "hu":
            t.jel("jeloltek", db=0, nem_merheto=f"az átirat nyelve {nyelv}: a magyar jegyzetekkel lexikailag nem mérhető")
            t.jel("igazolas", elfogadva=0)
            return []
        if csak_tema and not (self._olvaso_vault() / tema).is_dir():
            t.jel("jeloltek", db=0, kihagyva="a célmappa új: nincs benne jegyzet, amelyhez kötni lehetne")
            t.jel("igazolas", elfogadva=0)
            return []
        korp = self.korp()
        res = KT.kotes(f, korp, tema, elvet=self.elvet)
        idx = korp.idx
        if csak_tema:           # 86. d.: a célmappás bevitel csak a mappa saját jegyzeteihez köt (a mappán kívüli jelölt el sem olvasódik)
            res = {k: [r for r in res.get(k) or [] if r["jegyzet"] in idx.notes and idx.notes[r["jegyzet"]]["tema"] == tema]
                   for k in ("auto", "javaslat")}
        out = []
        for gep, r in [(True, r) for r in res["auto"]] + [(False, r) for r in res["javaslat"]]:
            n = idx.notes[r["jegyzet"]]
            w_sw = {x[:K] for x in longwords(f.szoveg(r["t"]))}
            c = {"jegyzet": r["jegyzet"], "cim": n["cim"], "tema": n["tema"], "t": r["t"], "vegso_t": r["vegso_t"], "p": r["p"],
                 "sajat_tema": r["sajat_tema"], "bizonyitek": r["bizonyitek"], "sav": "gep" if gep else "javaslat",
                 "dontes": "elfogad" if gep else None, "ki": "gep" if gep else None, "indok": KT.indok(r) if gep else None}
            if not gep:
                c["ablak_szoveg"] = f.szoveg(r["t"])
                c["jegyzet_reszlet"] = X.best_passage(n["body"], w_sw, idx)
            out.append(c)
        varo = [c for c in out if not c.get("dontes")]
        olvasott = 0
        if varo and self.M.van("kotes"):
            for c in varo[:MAX_KOTES_OLVASAS]:
                if self.stop():
                    break
                v, jel = self.M.kerdez("kotes", itelet.kotes_prompt(c["ablak_szoveg"], c["cim"], c["jegyzet_reszlet"]),
                                       itelet.KOTES_MAX_TOKEN)
                olvasott += 1
                c["modell_itelet"], c["modell_valasz"] = itelet.igen_nem(v), v
                if itelet.kotes_dontes(c["p"], c["sajat_tema"], X.targy(tema), c["modell_itelet"]):
                    c.update(sav="modell", dontes="elfogad", ki="modell", indok=itelet.kotes_indok(c))
                    if not t.jelek.get("kotes") or jel.get("proba"):
                        t.jelek["kotes"] = jel
        for c in out:                         # a mért sáv alatti javaslat nem kötött, a gazda nem kap kérdést
            if not c.get("dontes"):
                c.update(dontes="nem_kotve", ki="szabaly", indok="a mért sáv alatt — nem kötve")
            c.pop("ablak_szoveg", None)
            c.pop("jegyzet_reszlet", None)
        t.jeloltek = out
        elf = [c for c in out if c["dontes"] == "elfogad"]
        t.jel("jeloltek", db=len(out), gep=sum(c["sav"] == "gep" for c in out), javaslat=len(res["javaslat"]),
              modell_olvasott=olvasott)
        t.jel("igazolas", elfogadva=len(elf), elvetve=sum(c["dontes"] == "elvet" for c in out),
              nem_kotve=sum(c["dontes"] == "nem_kotve" for c in out))
        return elf

    # -------------------------------------------------- 14. visszajelzés és riport

    def _visszajelzes(self, t: Tetel) -> None:
        """A staging `integration.json` `integration_status`-a (az egyetlen mező, amit a vault oldala visszaír; próbában nem)."""
        uj = STAGING_ALLAPOT.get(t.allapot)
        if self.proba or not uj:
            return
        try:
            r = staging.visszajelez(t.mappa, uj)
            t.jel("visszajelzes", staging=r, allapot=uj)
            self._ytdlp_commit(t)
        except (OSError, ValueError, RuntimeError) as e:
            t.jel("visszajelzes", "hiba", hiba=str(e))

    def _ytdlp_commit(self, t: Tetel) -> None:
        from . import lanc
        try:
            lanc.pillanat_utan(self.cfg, 0, self.log, celok=[Path(t.mappa)], uzenet=f"videólánc: a staging visszajelzése ({t.allapot})",
                               tetel=f"visszajelzes-{t.kulcs}")
        except Exception as e:  # noqa: BLE001 — a pillanatkép hiánya a vault-tételt nem viszi el (18. döntés mintája)
            self.log(f"[videó] FIGYELEM: az ytdlp pillanatkép nem készült: {e}")

    def _riport(self, tetelek: list[Tetel], megallt: bool) -> dict:
        r = {"kor": self.kor, "fajta": "video-integralas", "proba": self.proba, "megallitva": megallt, "eredmeny": {}, "tetelek": []}
        for t in tetelek:
            r["eredmeny"][t.allapot] = r["eredmeny"].get(t.allapot, 0) + 1
            r["tetelek"].append({"mappa": t.mappa, "kulcs": t.kulcs, "cim": t.cim, "allapot": t.allapot, "uzenet": t.uzenet,
                                 "tema": t.tema, "commit": t.commit, "utak": t.utak,
                                 "kotesek": [{k: c.get(k) for k in ("jegyzet", "vegso_t", "p", "sav", "dontes", "ki", "beirva")}
                                             for c in t.jeloltek if c.get("dontes") in ("elfogad", "elvet")],
                                 "modellek": {k: (v or {}).get("modell") for k, v in t.jelek.items()}})
        d = (self.cfg.path("tmp") / "video-proba") if self.proba else (self.cfg.path("runs") / "video")
        d.mkdir(parents=True, exist_ok=True)
        ut = d / f"{self.kor}.json"
        ut.write_text(json.dumps(r, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        self.log(f"[videó] vége: {r['eredmeny']}")
        self.log(f"Riport: {ut}")
        return r


def _sha256(p) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for darab in iter(lambda: f.read(1 << 20), b""):
            h.update(darab)
    return h.hexdigest()
