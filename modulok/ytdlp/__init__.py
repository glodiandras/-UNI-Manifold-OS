"""A videólánc (C20a; docs/C20-TERV.md): a legacy `modulok/ytdlp` portja és a 2.0 ragasztó-kódja.

A másolt `msp` csomag a `src/` alatt él (angol azonosítókkal, `PORT.md`); az itteni modulok magyar azonosítókkal készültek:

- `utnorm`: a régi abszolút utak feloldása a `state.json`-okban (a jelenlegi gyökerekre),
- `staging`: a staging forrásmappa olvasása, leltára, azonosító szerinti keresése, a visszajelzés,
- `elhelyezes`: a vaultba kerülés **terve** (videómappa, melléklet-réteg, ütközés) — nem mozgat, nem ír,
- `konvertalas`: a nem natív videó (MKV, WebM, AV1/VP9) konvertálása beolvasáskor ffmpeg-gel,
- `lanc`: a `video_letoltes` feladat lépései (letöltés → konvertálás → staging → pillanatkép),
- `klon`: a staging APFS-klónja méretlistával,
- `__main__`: a `bin/mos video …` parancsok.

C20b (a bevitel a vaultba, a legacy `media_auto` 14 lépése a D1 szerint):

- `integralas`: a lánc (egy videó = egy gépi tétel a gépi-írás szolgáltatáson át: `mozgat` + `uj` + `csere`),
- `vaultoldal`: a vault-oldali mellékletek (a staging átirata → `.vtt`, `.info.json`, a forrásleíró jegyzet),
- `szovegreteg`, `egyezes`, `kotes`, `itelet`, `horgony`: a legacy `vaultlib`, `media_match`, `media_link`, `media_itelet` és
  `add_media_anchors` viselkedésre azonos portja (a verifikátor modellje: `kotes_modell.json`),
- `bevitel`: a behúzott helyi videó → staging-forrásmappa, `modell`: a worker hívásai (router, D9).

A C20a lánc (`lanc`) a vaultba nem ír; a vaultba csak az `integralas` ír, a core gépi-írás szolgáltatásán át.
"""
