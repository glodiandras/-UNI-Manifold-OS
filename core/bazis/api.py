"""A Bases végpontjai (C12): `POST /api/vault/bazis/lekerdez` és `POST /api/vault/bazis/modosit`.

Mindkettő a `.base` **szövegét** kapja (a felület átlátszatlanul kezeli), és **nem ír**: a `lekerdez` a sorokat adja
az indexből, a `modosit` az új szöveget számolja (az élő ellenőrzés is ezt hívja). Az írás a felület dolga, az
egyetlen írási úton (fájlnál a `Dokumentum` → `PUT /api/vault/fajl`, blokknál a befoglaló jegyzet tranzakciója).
"""
from __future__ import annotations

import threading
import time

from ..vaultio import Invalid, norm_path
from .adat import Tar
from .ertekek import ErtekKeretHiba, IdokeretHiba
from .fuggvenyek import fuggveny_lista
from .lekerdezes import MAX_SOR, futtat
from .modell import betolt, hiba, modosit
from ..hibakod import kodol

_UTOLSO_MAX = 2000               # a megszakítás-nyilvántartás legfeljebb ennyi nézetet tart (a legrégebbi esik ki)


class Bazisok:
    def __init__(self, cfg, index):
        self.cfg = cfg
        self.index = index
        self.tar = Tar(index)
        # T040: a lekérdezés teljes időkerete (`[index] bazis_idokeret_mp`; 0 = nincs) és az elavult kérés megszakítása:
        # a kliens nézetenként (`azon`) sorszámozza a kéréseit (`kerdes`); az újabb a régebbit leállítja
        self.idokeret = float(cfg.section("index").get("bazis_idokeret_mp", 2))
        self._utolso: dict[str, int] = {}
        self._utolso_zar = threading.Lock()

    def _megszakitva(self, azon, kerdes):
        """A kérés jelzője: igaz, ha ugyanerre a nézetre újabb kérés érkezett. Nem azonosított kérésre `None`."""
        if not azon or kerdes is None:
            return None
        with self._utolso_zar:
            self._utolso[azon] = max(kerdes, self._utolso.pop(azon, -1))     # a kivétel + beszúrás a „legrégebbi” sorrendet frissíti
            while len(self._utolso) > _UTOLSO_MAX:
                self._utolso.pop(next(iter(self._utolso)))
        return lambda: self._utolso.get(azon, kerdes) > kerdes

    def _kesz_hiba(self, hely: str, kod: str, param: dict | None = None, megszakitva: bool = False) -> dict:
        """A lekérdezés leállt (időkeret, értékkeret, szélsőséges érték): a YAML-hiba szerződése szerint 200, `ok: false`."""
        return {"ok": False, "nezetek": [], "nezet": None, "oszlopok": [], "sorok": [], "csoportok": None,
                "osszesitok": {}, "osszes": 0, "levagva": False, "hibak": [hiba(hely, kod=kod, param=param)], "figyelmeztetesek": [],
                "ido_ms": 0, "generacio": self.index.generacio, "megszakitva": megszakitva}

    def lekerdez(self, t: dict) -> dict:
        """`{szoveg, ez?, nezet?, max_sor?}` (vagy `{segitseg: true}` → `{ok, fuggvenyek}`, lekérdezés nélkül) → a sorok, oszlopok, csoportok, összesítők (200 YAML-hibánál is:
        `ok: false` és a `hibak`). 400: hiányzó szöveg; 503: az index nincs kész."""
        if t.get("segitseg") is True:                       # 10-bases-10: a szerkesztő-segítség függvénylistája, lekérdezés nélkül
            return {"ok": True, "fuggvenyek": fuggveny_lista()}
        szoveg = t.get("szoveg")
        if not isinstance(szoveg, str):
            raise kodol(Invalid("hiányzik a `.base` szövege (szoveg)"), "bazis.api.hianyzik_base_szovege_szoveg")
        nezet = t.get("nezet")
        if nezet is not None and not isinstance(nezet, (str, int)) or isinstance(nezet, bool):
            raise kodol(Invalid("a nézet sorszám vagy név"), "bazis.api.nezet_sorszam_nev")
        ez = t.get("ez")
        ez = norm_path(ez) if ez else None
        max_sor = t.get("max_sor", MAX_SOR)
        if not isinstance(max_sor, int) or isinstance(max_sor, bool) or not 1 <= max_sor <= MAX_SOR:
            raise kodol(Invalid(f"a max_sor 1 és {MAX_SOR} közti egész"), "bazis.api.max_sor_1_max_sor", {"MAX_SOR": MAX_SOR})
        kerdes, azon = t.get("kerdes"), t.get("azon")
        if kerdes is not None and (not isinstance(kerdes, int) or isinstance(kerdes, bool)):
            raise kodol(Invalid("a kerdes sorszám (egész)"), "bazis.api.kerdes_sorszam_egesz")
        if azon is not None and (not isinstance(azon, str) or len(azon) > 200):
            raise kodol(Invalid("az azon legfeljebb 200 karakteres szöveg"), "bazis.api.azon_legfeljebb_200_karakteres_szoveg")
        self.index._kesz_vagy_hiba()
        bazis, hibak = betolt(szoveg)
        if bazis.vegzetes:
            return {"ok": False, "nezetek": [], "nezet": None, "oszlopok": [], "sorok": [], "csoportok": None,
                    "osszesitok": {}, "osszes": 0, "levagva": False, "hibak": hibak, "figyelmeztetesek": [],
                    "ido_ms": 0, "generacio": self.index.generacio}
        n = bazis.nezet_keres(nezet)
        figy = []
        if n is None:
            n = bazis.nezetek[0]
            figy.append(hiba("nezet", kod="bazis.api.nincs_nezet", param={"nezet": repr(nezet)}))
        megszakitva = self._megszakitva(azon, kerdes)
        # T179: a `Tabla` (hideg: írás után) építése külön mérve — az `ido_ms` csak a lekérdezésé
        t0 = time.perf_counter()
        tabla = self.tar.tabla()
        tabla_ms = round((time.perf_counter() - t0) * 1000, 1)
        try:
            v = futtat(bazis, tabla, n, ez, max_sor=max_sor,
                       hatarido_mp=self.idokeret if self.idokeret > 0 else None, megszakitva=megszakitva)
        except IdokeretHiba as e:
            return self._kesz_hiba("idokeret", e.kod, e.param, e.megszakitva)
        except ErtekKeretHiba as e:
            return self._kesz_hiba("ertekkeret", e.kod, e.param)
        except (OverflowError, ValueError, RecursionError) as e:       # szélsőséges érték (T041): hiba, nem 500
            return self._kesz_hiba("kifejezes", "bazis.futas.szelsoseges", {"tipus": type(e).__name__, "e": e})
        v["hibak"] = hibak + v["hibak"]
        v["figyelmeztetesek"] += figy
        return {"ok": True, **v, "tabla_ms": tabla_ms, "tabla_mod": self.tar.utolso_mod}

    def modosit(self, t: dict) -> dict:
        """`{szoveg, muvelet}` → `{ok, szoveg_uj, valtozas, hibak}`. Tiszta: nem ír. Hibánál (`ok: false`) a
        `szoveg_uj` a régi szöveg."""
        szoveg, muvelet = t.get("szoveg"), t.get("muvelet")
        if not isinstance(szoveg, str):
            raise kodol(Invalid("hiányzik a `.base` szövege (szoveg)"), "bazis.api.hianyzik_base_szovege_szoveg")
        if not isinstance(muvelet, dict):
            raise kodol(Invalid("hiányzik a művelet (muvelet)"), "bazis.api.hianyzik_muvelet_muvelet")
        uj, hibak, valtozas = modosit(szoveg, muvelet)
        return {"ok": not hibak, "szoveg_uj": uj, "valtozas": valtozas, "hibak": hibak}


def utvonalak(r) -> None:
    r.post("/api/vault/bazis/lekerdez", lambda k: k.app.bazisok.lekerdez(k.torzs()))
    r.post("/api/vault/bazis/modosit", lambda k: k.app.bazisok.modosit(k.torzs()))
