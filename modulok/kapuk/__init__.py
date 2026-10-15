"""A közös forráshűség-kapu (C22a; `docs/C22-TERV.md` 1. fejezet).

**Egy kapu, négy fogyasztó**: a kvíz (C22b), a kártya (C23b), a vault-válasz (C25) és az összefoglaló (C26) ugyanazt a
vizsgálatot kéri — *állítás → forrásmondat → egyezés küszöbbel* — és nem készít sajátot.

- `forras`: a jegyzet előkészítése (frontmatter, megjegyzés, beágyazás, link-jelölés nélkül), a szakaszok, az idézet
  megkeresése a forrásban és a talált hely mondatra bővítése.
- `huseg`: `ellenoriz(forras, allitas, idezet, profil)` → `Verdikt` (hossz · kötött · támogatott · kényes tokenek ·
  tagadás-paritás); a küszöbök az `os.toml` `[kapuk]` szakaszából, a C18 `szoveg` halmazán mérve.
- `meres`: a mérés (pozitív és szintetikusan rontott negatív minták), `docs/C22-KAPU-MERES.md`.

A kapu **lexikai**, modellt nem hív és a vaultba nem ír. Amit nem lát (az átfogalmazott hamis állítás, a mondaton belüli
névcsere), azt a láncok modell-alapú „vak ellenőrzése” fedi.
"""
