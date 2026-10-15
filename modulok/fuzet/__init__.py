"""A füzetlánc (C21): kézzel írt füzetfotók bekötése a vault elméleti jegyzeteibe, zárt listás választással.

A legacy erős módszerének (`fuzet_eros.py`, 2026-09-26) portja két router-feladattal (CLAUDE.md 63(e)): `fuzet_fejezet` (képes
olvasás a fejezetek zárt listájából) → `fuzet_valaszto` (szöveges választás a fejezet elméleti jegyzetei közül). A modulok:

- `kep`: papírkivágás, oldalpárra bontás, forgatás-segéd, olvashatóság (modell nélkül; a legacy `fuzet.oldalak` portja);
- `modszer`: a promptok, a válaszok szétszedése, a jelöltlista és a választás — a lánc és az eval-feladatok egyetlen helye;
- `katalogus`: a vault elméleti jegyzetei és fejezetei (csak olvasva);
- `formatum`: a `## Füzet` szakasz tiszta függvényei (beágyazás + képlet-callout);
- `allapot`: a lánc állapota a vaulton kívül (`{state}/fuzet/`);
- `lanc`: a kör (olvasás → választás → átirat → gépi írás).
"""
