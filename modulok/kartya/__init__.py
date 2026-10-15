"""Kártyák és FSRS (C23; `docs/C23-TERV.md`).

A kártya a vaultban él: kísérőjegyzet (`ATTCHMNTS - cards/<jegyzet> — kártyák.md`), kártyánként egy `> [!card]`
callout `^c-…` azonosítóval. Az ütemezés állapota a `{tanulas_db}`-ben él, az azonosítóhoz kötve
(`core/tanulas_db.py`).

- `formatum`: a kísérőjegyzet elemzője és írója, a kísérőjegyzet neve — tiszta függvények.
- `szinkron`: a kártyamappa olvasása → a `tanulas.sqlite` (a vaultba nem ír).
- `utemezo`: FSRS (py-fsrs): válasz, visszavonás, esedékesek, előrejelzés.
- `apkg`, `html`: Anki-csomag export és import; Markdown ↔ Anki-HTML.

- `generalas`, `horgony`, `lanc` (C23b): AI-generálás a kapukkal, a forrás horgonyai és `## Gyakorlás` sora, a lépés I/O-ja (a
  vaultba csak a gépi-írás szolgáltatáson át ír); `meres`, `kuszob_meres`: a kártya-arany mérése és az „erősen módosult” küszöb.

A végpontok a `core/kartya_api.py`-ban, a feladattípusok a `core/kartya_feladat.py`-ban, az ütemező a `core/automatika.py`-ban.
"""
