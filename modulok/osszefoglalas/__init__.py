"""Összefoglalás egy jegyzetből, mappából vagy videóból, és a kontextus-csomag (C26; `docs/C26-TERV.md`) — a modell
nélküli mag (C26a).

Az összefoglaló a vaultban él: kísérőjegyzet az `ATTCHMNTS - summaries/` mappában (45. döntés, T058), a forrásjegyzetben
egy `![[…]]` beágyazó sor a `## Gyakorlás` alatt (`core/gyakorlas.py`). **Minden állítása mellett a forrás linkje és a
jegyzet szó szerinti mondata áll; a forrás nélküli mondat kiesik** (TERV 5.7).

- `formatum`: az összefoglaló-jegyzet elemzője és írója, a fájlnév, a horgony-linkek — tiszta függvények.
- `szakaszolas`: a jegyzet fejezetei és blokkjai (az index táblái, tiszta bemenet) → darabok és horgonyok.
- `video`: az átirat időablakai → darabok, időkód-horgonyokkal.
- `lanc`: a lánc modell nélküli része (darabok, kapuk, kiválasztás, mappa-szint); a modell egy hívható mögött áll, a C26b
  köti be. A forráshűség a **közös** `modulok/kapuk` kapuja; új kapu nincs.
- `automatika`: az automatikus mód döntései (10 perc csend, új vagy erősen módosult, tiltva) — tiszta függvények, ütemező és
  háttérszál nélkül; a memóriaőr a meglévő `Kapu.admit`.
- `kontextus`: a kontextus-csomag a külső AI-nak, és a visszamásolt válasz feldolgozása a kapun át.
- `promptok`: a C18 `szoveg` halmazának összefoglaló-promptja (`PROMPT_VERZIO`).

A C26a a vaultba nem ír és modellt nem hív; az éles generálás, a gépi írás és a mérés a C26b.
"""
