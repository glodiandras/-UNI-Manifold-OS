# A legacy `modulok/ytdlp` portja (C20a, 2026-10-04)

A kód **másolat** a legacy `modulok/ytdlp`-ból (a `MOS_LEGACY` gyökér alatt, csak olvasva). A legacy `CLAUDE.md`-je erre a
projektre nem érvényes, ezért nem került át; a legacy `README.md` a `docs/LEGACY-README.md` (a 2.0 eltérései lent).

## Mi került át, és mi nem

| Átkerült (másolat) | Nem került át |
|---|---|
| `src/msp/**` (36 fájl, 7301 sor), `scripts/*`, `templates/`, `tests/` (373 pytest-teszt), `config/config.yaml`, `pyproject.toml`, `.gitignore`, `tortenelem-hatralevo.txt`; a `README.md` a `docs/LEGACY-README.md`-be költözött (a doctor a `docs` mappákat nem olvassa) | `CLAUDE.md` (a legacy munkaszerződése), `.venv.nosync` (1,4 GB; a 2.0 a `var/venv`-et használja), `.pytest_cache`, `logs/` |
| **a staging és az `archive/` nem a repóban él**: APFS-klón (`bin/mos video staging-klon`), a `.gitignore`-ok kizárják | |

Az `msp` azonosítói **változatlanok** (a port másolat; az angol maradékot a 12. döntés fedi, átnevezés nincs). A 2.0 ragasztó-kódja
(`modulok/ytdlp/*.py`: `__main__`, `utnorm`, `staging`, `elhelyezes`, `konvertalas`, …) magyar azonosítókkal készült.

## Eltérések a másolattól (az ÖSSZES)

1. `src/msp/downloader.py` — `resolve_ffmpeg`: **csak** a `ytdlp.ffmpeg_location` (a lánc a pinelt, sha256-ellenőrzött `[utak] ffmpeg`-et adja át,
   `modulok/ytdlp/lanc.py` + `eszkoz.py`; Javító 3, A3-17). **Nincs `MOS_FFMPEG`, nincs `<os>/runtime`-keresés, nincs PATH- és
   `imageio_ffmpeg`-tartalék**: az ellenőrzött és a futtatott bináris ugyanaz; a home-beli `~/.local/bin` (Save4K-symlink) tiltott.
   `_js_runtime_path`: csak a `ytdlp.node_location` (a `[utak] node`), nincs `MOS_NODE`, nincs PATH; a `deno` nincs pinelve; a yt-dlp
   `js_runtimes` csak a pinelt futtatót tartalmazza (az üres szótár a yt-dlp deno-alapértelmezését is kikapcsolja). `find_ytdlp_binary`: csak
   a kifejezett `ytdlp.binary` fájl, **nincs `shutil.which("yt-dlp")`** (A3-18: a PATH-os yt-dlp nem pinelt, önfrissítő).
2. `config/config.yaml` — `transcript.enabled: false` (az átirat a C20b: a worker hang-háttere; a port ASR-motorjai maguk töltenének
   modellt), `integration.enabled: false` + `command: []` (a legacy `bin/mos kor`-t hívta; a 2.0-ban nincs; a vaultba írás a C20b
   `mozgat` művelete), `ffmpeg_location: auto` = a runtime build. Kommentek frissítve.

3. `src/msp/config.py` — a `YtDlpConfig` új `node_location` mezője (`auto` = nincs), a `ffmpeg_location` jelentése (Javító 3).
4. `src/msp/transcription/base.py`, `src/msp/transcription/faster_whisper.py`, `mlx_whisper.py`, `whisper_cpp.py` — a modellt betöltő motorok `transcribe`-ja **kódból tiltott**
   (`base.modell_betoltes_tiltva`; §4: modellt kizárólag a modellgazda tölthet be; A3-22). A felirat-alapú motor modell nélkül működik.

5. `src/msp/crawl.py` (Bejárás, 2026-10-14; javasolt 84. döntés) — a bejárás kettévált: `walk()` az általános felfedezés (hatókör,
   robots.txt, késleltetés, korlátok, átirányítás, `should_stop` leállítás), a `Decision`/osztályozó dönti el az oldal sorsát; a `crawl()`
   ennek videóoldal-fogyasztója, új `on_video_page` és `should_stop` horoggal. Javítás: a relatív link az oldal írt címéhez (a záró `/`-rel)
   oldódik; a 404-es `HTTPError` lezárva. `src/msp/config.py` és `config/config.yaml` — `crawl.embed_patterns`: az iframe-be ágyazott
   `youtu.be` és a `video.cs50.io/<azonosító>`. A 2.0 ragasztója: `modulok/ytdlp/bejaras.py`, `bin/mos video letoltes --bejaras`.
6. `src/msp/pipeline.py`, `src/msp/downloader.py` (Közvetlen fájl, 2026-10-14; a javasolt 84. döntés kiegészítése) — az `ingest_url`
   új `page_url`, `page_title`, `user_agent` paramétere: egy weboldalon talált **közvetlen videófájl** az oldal forrásaként kerül a
   stagingbe (a source.md `url`-je, az archívum és a szolgáltató az oldalé, a cím az oldal címe, az azonosító a fájl-URL hash-e
   `u<hash>`, a `media_url` a fájl); a `DownloadRequest.user_agent` és a `probe(..., user_agent=)` a yt-dlp `http_headers`
   (`--user-agent`) értéke — a bejáró őszinte User-Agentje a böngészőt utánzó alapérték helyett. `config/config.yaml` — `provider_names`:
   `cs50.harvard.edu: "CS50"`. A 2.0 ragasztója: `modulok/ytdlp/kozvetlen.py`, `bejaras.py`, `lanc.py`.

Más fájl nem változott. (A `tests/` a változatlan legacy-készlet; a `test_crawl_all.py` bash-t igényel, a `crawl_all.sh --background` mód a
D4 miatt a 2.0-ban **nem támogatott**: háttérfolyamatot csak a futó app indíthat, a feladatsor az újrapróbálás és a leállítás forrása.)

## Futtatás

```bash
bin/mos video eszkoz-ellenorzes     # ffmpeg, yt-dlp, node a runtime alól
bin/mos video felmeres              # csak olvas: a staging videóinak kodekje, nem natív darabok
bin/mos video staging-klon --igen   # a legacy staging APFS-klónja (előtte méretlista)
bin/mos video test                  # a msp 373 pytest-tesztje + a portolt média-selftest
bin/mos video letoltes <url>        # a lánc egy lépése (hálózat: D3) — a vezérlő Bevitel szakasza ezt a feladatot indítja
bin/mos video letoltes --bejaras <oldal>          # egy oldal összes videója: csak a lista (letöltés nincs)
bin/mos video letoltes --bejaras <oldal> --igen   # … a lista még meg nem lévő videóinak letöltése (újraindítva folytatódik)
```

A tesztek hálózat nélkül futnak (hamis letöltő). A `tests/test_ytdlp_port.py` a `bin/mos test` részeként is lefuttatja őket.
