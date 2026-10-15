"""Kvíz egy jegyzetből (C22; `docs/C22-TERV.md`) — a modell nélküli mag (C22a).

A kvíz a vaultban él: kísérőjegyzet az `ATTCHMNTS - quizes/` mappában (a legacy formátuma, L47), a forrásjegyzetben egy
`![[…]]` beágyazó sor a `## Gyakorlás` alatt. A kitöltés eredménye a `{tanulas_db}`-ben (`core/tanulas_db.py`, 2-es migráció).

- `formatum`: a kvízjegyzet elemzője és írója, a fájlnév, a gép írta `## Kitöltések` szakasz — tiszta függvények.
- `mechanikus`: a jelölt kérdés mechanikus kapuja (szerkezet, jelölés, kiszivárgás).
- `generalas`: a lánc modell nélküli része (szakaszolás, jelöltek szétszedése, kapuk, kiválasztás); a modellhívás két
  hívható mögött áll, a C22b köti be.
- `ertekeles`: a kitöltés kiértékelése és az elemzés (tudod · tipp · tévképzet · hiány) — determinisztikus, modell nélkül.
- `tar`: a kitöltések és jelölések a `tanulas.sqlite`-ban.
- `esemeny`: a `kviz_eredmeny` tracker-esemény adata.

A C22a a vaultba nem ír és modellt nem hív; az éles kvíz-generálás, a gépi írás és a mérés a C22b.
"""
