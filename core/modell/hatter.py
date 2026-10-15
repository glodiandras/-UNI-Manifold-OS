"""A betöltő hátterei: egy-egy futtató (`futtato` a regiszterben) betöltése és hívása.

A hátteret KIZÁRÓLAG a betöltő (`betolto.Betolto`) példányosítja és hívja, a zár, a keret és az őr
alatt (L22). Az ML-könyvtárak lustán, a háttérben töltődnek: a core és a worker indulása gyors marad.

Kész: `mlx-vlm` (szöveg + kép), `mlx-lm` (szöveg), `sentence-transformers` (beágyazás, CrossEncoder-rerank),
`mlx-whisper` (hang → átirat, C20b). A `mlx-audio` (parakeet) háttere csak mért igény mellett készül (C20b, K29).
"""
from __future__ import annotations

import gc
import importlib
import os
import subprocess

from .beallitas import Modell


class BetoltesHiba(RuntimeError):
    """A modell nem tölthető be (nincs letöltve, konvertálás kell, nincs hozzá háttér)."""


class Megszakitva(Exception):
    """A kérést megszakították (a feladatot leállították, C17): a részleges eredmény eldobódik."""


# ------------------------------------------------------------------ MLX-memória (bench, állapot)

def mlx_csucs_nullaz() -> None:
    import mlx.core as mx
    mx.reset_peak_memory()


def mlx_csucs_gb() -> float:
    import mlx.core as mx
    return mx.get_peak_memory() / 1e9


def mlx_aktiv_gb() -> float:
    import mlx.core as mx
    return mx.get_active_memory() / 1e9


def _mlx_urit() -> None:
    gc.collect()
    try:
        import mlx.core as mx
        mx.clear_cache()
    except ImportError:
        pass


def _prompt(messages: list[dict]) -> str:
    """A legacy gazda alakja: a szöveges üzenetek egymás után, üres sorral (L27: a kimenet azonos)."""
    return "\n\n".join(m["content"] for m in messages if isinstance(m.get("content"), str))


class Hatter:
    """Az interfész. A `general` eredménye: `{text, prompt_tokens, generation_tokens, generation_tps}`."""

    def csucs_nullaz(self) -> None:
        """A csúcsmemória-számláló nullázása (C29.8, T045: a betöltés ELŐTT hívja a betöltő, így a csúcs a betöltést is tartalmazza).
        Alapból nincs mérés."""

    def csucs_gb(self) -> float | None:
        """A nullázás óta mért csúcsmemória GB-ban; `None`, ha a háttér nem mér (nem MLX)."""
        return None

    def betolt(self, modell: Modell, ut: str, cache_gb: float) -> None:
        raise NotImplementedError

    def urit(self) -> None:
        raise NotImplementedError

    def general(self, messages: list[dict], kepek: list[str], max_tokens: int, temperature: float,
                gondolkodas: bool | None, prefill_lepes: int | None, repetition_penalty: float | None,
                megszakit=None, repetition_context_size: int | None = None, tokenre=None) -> dict:
        """`megszakit`: hívható, amely igaz, ha a generálást le kell állítani (tokenenként kérdezi; `Megszakitva`).
        `repetition_context_size`: az ismétlés-büntetés ablaka tokenben (C18.1; `None`: a könyvtár alapja, 20).
        `tokenre`: hívható, amely minden elkészült szövegdarabot megkap (a folyam, C25b)."""
        raise BetoltesHiba("ez a modell nem generál szöveget")

    def beagyaz(self, szovegek: list[str]) -> list[list[float]]:
        raise BetoltesHiba("ez a modell nem beágyazó")

    def rerank(self, kerdes: str, dokumentumok: list[str]) -> list[float]:
        raise BetoltesHiba("ez a modell nem reranker")

    def atir(self, hang: str, nyelv: str | None, megszakit=None) -> dict:
        """Hang → átirat (C20b): `{text, szegmensek: [{start, end, text}], nyelv, hossz_mp}`."""
        raise BetoltesHiba("ez a modell nem ír át hangot")


class MlxVlm(Hatter):
    def csucs_nullaz(self):
        mlx_csucs_nullaz()

    def csucs_gb(self):
        return round(mlx_csucs_gb(), 3)

    def betolt(self, modell, ut, cache_gb):
        import mlx.core as mx
        from mlx_vlm import load
        mx.set_cache_limit(int(cache_gb * 1e9))
        self.modell, self.proc = load(ut)

    def urit(self):
        self.modell = self.proc = None
        _mlx_urit()

    def general(self, messages, kepek, max_tokens, temperature, gondolkodas, prefill_lepes, repetition_penalty,
                megszakit=None, repetition_context_size=None, tokenre=None):
        from mlx_vlm import generate, stream_generate
        from mlx_vlm.prompt_utils import apply_chat_template
        tkw = {} if gondolkodas is None else {"enable_thinking": bool(gondolkodas)}
        p = apply_chat_template(self.proc, self.modell.config, _prompt(messages), num_images=len(kepek), **tkw)
        kw = {"max_tokens": max_tokens, "temperature": temperature, "verbose": False}
        if prefill_lepes:
            kw["prefill_step_size"] = prefill_lepes
        if repetition_penalty is not None:
            kw["repetition_penalty"] = repetition_penalty
            if repetition_context_size is not None:
                kw["repetition_context_size"] = int(repetition_context_size)
        if megszakit is None and tokenre is None:
            r = generate(self.modell, self.proc, p, kepek or None, **kw)
            return {"text": r.text, "prompt_tokens": r.prompt_tokens, "generation_tokens": r.generation_tokens,
                    "generation_tps": r.generation_tps, "prompt_tps": r.prompt_tps}
        kw.pop("verbose", None)
        szoveg, utolso = [], None
        for r in stream_generate(self.modell, self.proc, p, kepek or None, **kw):
            if megszakit is not None and megszakit():
                raise Megszakitva("a generálás megszakadt")
            szoveg.append(r.text)
            if tokenre is not None and r.text:
                tokenre(r.text)
            utolso = r
        if megszakit is not None and megszakit():
            raise Megszakitva("a generálás megszakadt")
        return {"text": "".join(szoveg), "prompt_tokens": getattr(utolso, "prompt_tokens", 0),
                "generation_tokens": getattr(utolso, "generation_tokens", 0),
                "generation_tps": getattr(utolso, "generation_tps", 0.0),
                "prompt_tps": getattr(utolso, "prompt_tps", 0.0)}


class MlxLm(Hatter):
    def csucs_nullaz(self):
        mlx_csucs_nullaz()

    def csucs_gb(self):
        return round(mlx_csucs_gb(), 3)

    def betolt(self, modell, ut, cache_gb):
        import mlx.core as mx
        from mlx_lm import load
        mx.set_cache_limit(int(cache_gb * 1e9))
        self.modell, self.tok = load(ut)

    def urit(self):
        self.modell = self.tok = None
        _mlx_urit()

    def general(self, messages, kepek, max_tokens, temperature, gondolkodas, prefill_lepes, repetition_penalty,
                megszakit=None, repetition_context_size=None, tokenre=None):
        if kepek:
            raise BetoltesHiba("ez a modell csak szöveget olvas (mlx-lm)")
        from mlx_lm import stream_generate
        from mlx_lm.sample_utils import make_logits_processors, make_sampler
        tkw = {} if gondolkodas is None else {"enable_thinking": bool(gondolkodas)}
        uzenetek = [{"role": m.get("role", "user"), "content": m["content"]} for m in messages
                    if isinstance(m.get("content"), str)]
        if getattr(self.tok, "chat_template", None):
            p = self.tok.apply_chat_template(uzenetek, add_generation_prompt=True, tokenize=False, **tkw)
        else:
            p = _prompt(messages)
        kw = {"max_tokens": max_tokens, "sampler": make_sampler(temp=temperature)}
        if prefill_lepes:
            kw["prefill_step_size"] = prefill_lepes
        if repetition_penalty is not None:
            ablak = {} if repetition_context_size is None else {"repetition_context_size": int(repetition_context_size)}
            kw["logits_processors"] = make_logits_processors(repetition_penalty=repetition_penalty, **ablak)
        szoveg, utolso = [], None
        for r in stream_generate(self.modell, self.tok, p, **kw):
            if megszakit is not None and megszakit():
                raise Megszakitva("a generálás megszakadt")
            szoveg.append(r.text)
            if tokenre is not None and r.text:
                tokenre(r.text)
            utolso = r
        if megszakit is not None and megszakit():
            raise Megszakitva("a generálás megszakadt")
        return {"text": "".join(szoveg), "prompt_tokens": getattr(utolso, "prompt_tokens", 0),
                "generation_tokens": getattr(utolso, "generation_tokens", 0),
                "generation_tps": getattr(utolso, "generation_tps", 0.0),
                "prompt_tps": getattr(utolso, "prompt_tps", 0.0)}


class SentenceTransformers(Hatter):
    """Beágyazás (fp16, MPS) vagy CrossEncoder-rerank a képesség szerint. Ugyanazt a zárat tartja; a beágyazó
    a nyelvi modell mellett csak akkor marad bent, ha együtt beleférnek a keretbe (`Betolto.egyutt_maradhat`, C25b)."""

    def betolt(self, modell, ut, cache_gb):
        if "rerank" in modell.kepessegek:
            from sentence_transformers import CrossEncoder
            self.m, self.rerank_mod = CrossEncoder(ut, device="mps"), True
        else:
            from sentence_transformers import SentenceTransformer
            self.m, self.rerank_mod = SentenceTransformer(ut, device="mps").half(), False

    def urit(self):
        self.m = None
        gc.collect()
        try:
            import torch
            torch.mps.empty_cache()
        except Exception:  # noqa: BLE001 — MPS nélkül nincs mit üríteni
            pass

    def beagyaz(self, szovegek):
        if self.rerank_mod:
            raise BetoltesHiba("ez a modell reranker, nem beágyazó")
        v = self.m.encode(szovegek, normalize_embeddings=True, batch_size=16, convert_to_numpy=True)
        return v.astype("float32").tolist()

    def rerank(self, kerdes, dokumentumok):
        if not self.rerank_mod:
            raise BetoltesHiba("ez a modell beágyazó, nem reranker")
        return [float(x) for x in self.m.predict([(kerdes, d) for d in dokumentumok])]


HANG_MINTAVETEL = 16000          # a Whisper bemenete: 16 kHz, mono, float32 [-1, 1]
HANG_MAX_MP = 4 * 3600           # ennél hosszabb hangot nem írunk át egy kérésben (memória: ~0,9 GB float32)


def ffmpeg_ut() -> str:
    """A pinelt ffmpeg (`[utak] ffmpeg`, 47(a)): a PATH-os és a home-beli tiltott, ezért az mlx_whisper saját betöltője
    (`ffmpeg` a PATH-ról) nem futhat — a hangot ez a modul dekódolja, és tömbként adja a modellnek."""
    from .. import config
    ff = config.load().path("ffmpeg")
    if not ff.is_file() or not os.access(ff, os.X_OK):
        raise BetoltesHiba(f"nincs meg a pinelt ffmpeg ({ff}); telepítés: bin/mos runtime fetch ffmpeg")
    return str(ff)


def hang_tomb(hang: str, ffmpeg: str | None = None, max_mp: float = HANG_MAX_MP):
    """A hangfájl (vagy a videó hangsávja) 16 kHz-es mono float32 tömbként, a pinelt ffmpeg-gel (csak olvas)."""
    import numpy as np
    if not isinstance(hang, str) or not os.path.isabs(hang) or "\x00" in hang:
        raise BetoltesHiba("a hang útja abszolút út legyen")
    if not os.path.isfile(hang):
        raise BetoltesHiba(f"nincs ilyen hangfájl: {hang}")
    cmd = [ffmpeg or ffmpeg_ut(), "-nostdin", "-v", "error", "-t", str(int(max_mp)), "-i", hang, "-vn", "-f", "s16le",
           "-ac", "1", "-acodec", "pcm_s16le", "-ar", str(HANG_MINTAVETEL), "-"]
    try:
        r = subprocess.run(cmd, capture_output=True, check=True, timeout=max(60.0, max_mp / 5))
    except subprocess.CalledProcessError as exc:
        raise BetoltesHiba(f"a hang nem olvasható: {exc.stderr.decode('utf-8', 'replace').strip()[:300]}") from None
    except subprocess.TimeoutExpired:
        raise BetoltesHiba("a hang dekódolása túllépte az időkorlátot") from None
    if not r.stdout:
        raise BetoltesHiba("a fájlban nincs hangsáv")
    return np.frombuffer(r.stdout, np.int16).flatten().astype(np.float32) / 32768.0


class MlxWhisper(Hatter):
    """mlx-whisper (C20b). A modell a betöltő zárja alatt töltődik (`ModelHolder`: a könyvtár osztályszintű tárolója, az
    `urit` üríti); a hívás determinisztikus (`temperature=0`, L27: a hőmérséklet-visszaesés ki), a nyelv kötött. Az előző
    szegmens szövege nem kondicionál (`condition_on_previous_text=False`): visszaesés nélkül ez óv a hosszú előadások
    ismétlő hurkától; a K29 mérése dönt, ha mégis rontana."""

    def csucs_nullaz(self):
        mlx_csucs_nullaz()

    def csucs_gb(self):
        return round(mlx_csucs_gb(), 3)

    def betolt(self, modell, ut, cache_gb):
        import mlx.core as mx
        from mlx_whisper.transcribe import ModelHolder
        mx.set_cache_limit(int(cache_gb * 1e9))
        ModelHolder.get_model(ut, mx.float16)
        self.ut = ut

    def urit(self):
        try:
            from mlx_whisper.transcribe import ModelHolder
            ModelHolder.model = ModelHolder.model_path = None
        except ImportError:
            pass
        self.ut = None
        _mlx_urit()

    def atir(self, hang, nyelv, megszakit=None):
        from mlx_whisper import transcribe
        if megszakit is not None and megszakit():
            raise Megszakitva("az átirat megszakadt")
        tomb = hang_tomb(hang)
        r = transcribe(tomb, path_or_hf_repo=self.ut, language=nyelv or None, temperature=0.0, verbose=None,
                       condition_on_previous_text=False, fp16=True)
        if megszakit is not None and megszakit():
            raise Megszakitva("az átirat megszakadt")
        szegmensek = [{"start": round(float(s["start"]), 2), "end": round(float(s["end"]), 2), "text": s["text"].strip()}
                      for s in r.get("segments") or [] if str(s.get("text") or "").strip()]
        return {"text": (r.get("text") or "").strip(), "szegmensek": szegmensek, "nyelv": r.get("language") or nyelv,
                "hossz_mp": round(len(tomb) / HANG_MINTAVETEL, 2)}


HATTEREK: dict[str, type[Hatter]] = {"mlx-vlm": MlxVlm, "mlx-lm": MlxLm, "sentence-transformers": SentenceTransformers,
                                     "mlx-whisper": MlxWhisper}
KESOBB = {"mlx-audio": "C20b2 (átirat, csak mért igény mellett)", "transformers": "C25 (keresés)"}


def gyar(modell: Modell) -> Hatter:
    if modell.konvertalas:
        raise BetoltesHiba(f"{modell.nev}: nem MLX-formátum, előbb konvertálni kell (a konvertálás a betöltő "
                           "alatt fut, egyszeri helyi lépés)")
    if modell.futtato in HATTEREK:
        return HATTEREK[modell.futtato]()
    if modell.futtato in KESOBB:
        raise BetoltesHiba(f"{modell.nev}: a(z) {modell.futtato} hátterét a {KESOBB[modell.futtato]} adja hozzá")
    raise BetoltesHiba(f"{modell.nev}: a(z) {modell.futtato} futtató nincs a config/requirements.lock-ban")


def helyi_ut(modell: Modell, hub: str) -> str:
    """A modell helyi pillanatképe hálózat NÉLKÜL (`local_files_only`, L28); a rögzített revízióé (C19, T141), ha van."""
    try:
        hf = importlib.import_module("huggingface_hub")
        return hf.snapshot_download(modell.repo, local_files_only=True, cache_dir=hub, revision=modell.revizio or None,
                                    allow_patterns=list(modell.minta) or None)
    except Exception as exc:  # noqa: BLE001 — a huggingface_hub több hibafajtát dob
        raise BetoltesHiba(f"{modell.nev}: nincs a helyi gyorsítótárban ({modell.repo}); letöltés: "
                           f"mos models pull {modell.nev}") from exc
