"""Álmodell a modellréteg tesztjeihez: a betöltő szabályai valódiak, csak a háttér (MLX) ál."""
import threading
import time

from core.modell import beallitas as B
from core.modell.betolto import Betolto
from core.modell.hatter import Hatter, Megszakitva


class AlHatter(Hatter):
    """Naplózza a hívásokat; `hibak`: ennyi hívás dob GPU-memóriahibát; `tps`: a generálási sebesség."""
    naplo: list = []
    beallitasok: list = []                     # a general-hívások kérés-beállításai (C18.1)
    csucs_ertek: float | None = 3.5            # az ál MLX-csúcsmemória GB-ban (C29.8, T045); None: nem mérhető háttér
    nullazasok: int = 0                        # a csúcs-számláló nullázásainak száma

    def __init__(self, hibak=None, tps=50.0, tokenek=64, kesleltetes=None, folyamatos=None):
        self.hibak = hibak if hibak is not None else [0]       # közös számláló: az újratöltés után is fogy
        self.tps, self.tokenek, self.kesleltetes = tps, tokenek, kesleltetes
        self.folyamatos = folyamatos           # Event: a „generálás” addig tart, amíg meg nem szakítják (token-ciklus)
        self.modell = None

    def betolt(self, modell, ut, cache_gb):
        self.modell = modell
        AlHatter.naplo.append(("betolt", modell.nev, cache_gb))

    def csucs_nullaz(self):
        AlHatter.nullazasok += 1               # nem a `naplo`-ba: a hívássorrend-tesztek nem látják

    def csucs_gb(self):
        return AlHatter.csucs_ertek

    def urit(self):
        AlHatter.naplo.append(("urit", self.modell.nev if self.modell else None))
        self.modell = None

    def general(self, messages, kepek, max_tokens, temperature, gondolkodas, prefill_lepes, repetition_penalty,
                megszakit=None, repetition_context_size=None, tokenre=None):
        if self.kesleltetes:
            self.kesleltetes.wait(10)
        if self.folyamatos is not None:
            self.folyamatos.set()
            t0 = time.monotonic()
            while time.monotonic() - t0 < 10:
                if megszakit is not None and megszakit():
                    AlHatter.naplo.append(("megszakitva", self.modell.nev))
                    raise Megszakitva("a generálás megszakadt")
                time.sleep(0.01)
            raise RuntimeError("a generálást senki nem szakította meg")
        if megszakit is not None and megszakit():
            raise Megszakitva("a generálás megszakadt")
        if self.hibak[0]:
            self.hibak[0] -= 1
            raise RuntimeError("[METAL] Command buffer execution failed: Insufficient Memory")
        AlHatter.naplo.append(("general", self.modell.nev, messages[-1]["content"] if messages else ""))
        AlHatter.beallitasok.append({"max_tokens": max_tokens, "temperature": temperature, "gondolkodas": gondolkodas,
                                     "repetition_penalty": repetition_penalty,
                                     "repetition_context_size": repetition_context_size})
        tps = self.tps() if callable(self.tps) else self.tps
        if tokenre is not None:                # a folyam (C25b): a válasz két darabban
            tokenre(f"{self.modell.nev}:")
            tokenre(" válasz")
        return {"text": f"{self.modell.nev}: válasz", "prompt_tokens": 10, "generation_tokens": self.tokenek,
                "generation_tps": tps, "prompt_tps": 100.0, "prefill": prefill_lepes, "temp": temperature}

    def beagyaz(self, szovegek):
        AlHatter.naplo.append(("beagyaz", self.modell.nev, len(szovegek)))
        return [[1.0, 0.0] for _ in szovegek]

    def rerank(self, kerdes, dokumentumok):
        return [float(len(d)) for d in dokumentumok]

    def atir(self, hang, nyelv, megszakit=None):
        """Ál-átirat (C20b): a hangfájl nevéből két szegmens."""
        if megszakit is not None and megszakit():
            raise Megszakitva("az átirat megszakadt")
        AlHatter.naplo.append(("atir", self.modell.nev, hang, nyelv))
        return {"text": "Első mondat. Második mondat.", "nyelv": nyelv, "hossz_mp": 7.5,
                "szegmensek": [{"start": 0.0, "end": 3.0, "text": "Első mondat."},
                               {"start": 3.0, "end": 7.5, "text": "Második mondat."}]}


def al_betolto(b: B.Beallitas, mem=lambda: 60, hibak=0, **hatter_kw):
    AlHatter.naplo = []
    AlHatter.beallitasok = []
    hatter_kw["hibak"] = [hibak]
    return Betolto(b, hatter_gyar=lambda m: AlHatter(**hatter_kw), helyi_ut=lambda m, hub: f"/al/{m.repo}",
                   mem=mem, osszes_gb=lambda: 16.0, naplo=lambda s: None)


class AlAktivitas:
    """Kézzel állítható aktivitásjel."""

    def __init__(self, allapot="tetlen"):
        self._a = allapot
        self.lock = threading.Lock()
        self.hivasok = 0                  # az ütemező minden döntési körben lekérdezi: a tesztek köröket számolnak vele (T085)

    def allapot(self):
        self.hivasok += 1
        return self._a

    def allit(self, a):
        self._a = a

    def publikus(self):
        return {"allapot": self._a, "tetlen_mp": 0}


def beallitas(cfg, **gazda):
    b = B.betolt(cfg, {})
    b.gazda.update(gazda)
    return b
