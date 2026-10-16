"""A videólánc (C20a; docs/C20-TERV.md): a letöltő csomag és a ragasztó-kód.

A letöltő (`msp`) a `src/` alatt él (angol azonosítókkal); az itteni modulok magyar azonosítókkal készültek:

- `staging`: a staging forrásmappa olvasása, leltára, azonosító szerinti keresése, a visszajelzés,
- `elhelyezes`: a vaultba kerülés **terve** (videómappa, melléklet-réteg, ütközés) — nem mozgat, nem ír,
- `konvertalas`: a nem natív videó (MKV, WebM, AV1/VP9) konvertálása beolvasáskor ffmpeg-gel,
- `lanc`: a `video_letoltes` feladat lépései (letöltés → konvertálás → staging → pillanatkép),
- `__main__`: a `bin/mos video …` parancsok.

C20b (a bevitel a vaultba, 14 lépés):

- `integralas`: a lánc (egy videó = egy gépi tétel a gépi-írás szolgáltatáson át: `mozgat` + `uj` + `csere`),
- `vaultoldal`: a vault-oldali mellékletek (a staging átirata → `.vtt`, `.info.json`, a forrásleíró jegyzet),
- `szovegreteg`, `egyezes`, `kotes`, `itelet`, `horgony`: a szövegréteg, a téma-besorolás, a videó–jegyzet kötés, a modell-ítéletek és a
  `#t=` horgony (a verifikátor modellje: `kotes_modell.json`),
- `bevitel`: a behúzott helyi videó → staging-forrásmappa, `modell`: a worker hívásai (router).

A C20a lánc (`lanc`) a vaultba nem ír; a vaultba csak az `integralas` ír, a core gépi-írás szolgáltatásán át.
"""
