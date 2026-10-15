"""Felkészültség-becslés és dolgozat-oldal (C28a; `docs/C28-TERV.md`, TERV 5.8).

A naptár dolgozata + a felkészülési jegyzet `Source`/`NN` témái → témánként a kártyák FSRS-felidézése, a kvíz, az
utolsó tanulás és a tanult idő → átlátható képletű felkészültségi szám → napi terv a dolgozatig. **A számokat kód
számolja**; a szöveges értékelés a helyi modellel (`ertekeles`, C28b) csak szavakba önti őket.

Minden itt **csak olvas**: a vaultba, a naptárba és a DB-kbe nem ír (a tanulási blokkot csak a jóváhagyott javaslat írja
a naptárba, D12), új tábla és migráció nincs.

- `keplet`: a képlet (tiszta függvények);  `terv`: a napi terv (tiszta);  `kotes`: dolgozat ↔ felkészülési jegyzet (L59);
- `temak`: a jegyzet `Source`/`NN` témái;  `forrasok`: a kvíz-adatforrás illesztője (C22);
- `atnevezes`: a tracker útvonalainak átnevezés-követése (olvasáskor, git-ből);
- `adat`: a bemenetek betöltése;  `osszesit`: a végpontok válasza;  `forras`: javaslat-forrás a C29 horgán;  `api`: végpontok.

C28b (`docs/C28-TERV.md` 10.):
- `eredmeny`: a dolgozat eredménye a „Dolgozat kiértékelő” jegyzetek szabad szövegéből (a legacy `eredmeny()` portja, három hiba javítva);
- `rekonstrukcio` + `Adatok(rekonstrukcio=True)`: a becslés egy múltbeli időpontra, külön becslés-napló nélkül (kártya: `valasz.utana`/
  `visszavonva`; tracker: a nap végéig; kvíz: időbélyegek), a kvíz-forrás a C22 tárolójára kötve (`forrasok.kviz_tar_forras`);
- `kalibracio`: önkalibráció (ridge, leave-one-out, `n < kalibracio_min` → a súlyok nem változnak); az `os.toml`-t csak a CLI írja;
- `ertekeles`: szöveges értékelés a helyi modellel a szám-kapun át (D9: kalibrált modell vagy próba); nem ír a vaultba;
- `__main__`: `bin/mos felkeszultseg eredmeny | kalibral [--rogzit]`.
"""
