# 08 – F9 mentés / visszaállítás audit (PLAN §10 F9, „a 32. pont auditjai”)

Dátum: 2026-10-16. Kérdés: minden írási út pillanatkép-e, amelyet a visszavonás (`POST /api/pillanat/vault/visszavonas` → `Repo.undo_commit`
/ `undo_run`: **új, fordított commit**, a `git revert` szemantikája) bájtra visszavesz; ütközésnél (CAS) semmi nem íródik; a kódban
nincs munkafát eldobó git-művelet; és a sérült index helyreáll. Szintetikus vaultok; a szint: `bin/mos test --szint mentes`.

## §1 Körutak (snapshot → módosítás → visszavonás → a visszavonás visszavonása)

`tests/mentes_visszaallitas/test_korut.py`, valódi HTTP-n (élő `vault.git`). Minden úton: a visszavonás után a vault (a `types.json`-nal)
bájtra az előző; a visszavonás visszavonása után bájtra a módosított; a korábbi commitok a HEAD ősei maradnak (a történet nem íródik át);
a vaulton kívül semmi nem változik.

| Írási út | Végpont / függvény | Eredmény |
|---|---|---|
| jegyzet mentése | `PUT /api/vault/fajl` (`elso`, `pillanat`) | rendben; CRLF-es jegyzet CRLF marad, bájtra visszaáll |
| új jegyzet | `POST /api/vault/uj` | rendben (a visszavonás a fájlt eltávolítja; a tartalma a történetben, a visszavonás visszavonása visszahozza) |
| átnevezés linkátírással | `POST /api/vault/atnevezes` | rendben (a hivatkozó jegyzet linkje is visszaáll) |
| áthelyezés másik mappába | ugyanaz | rendben |
| tulajdonság-típus regiszter | `POST /api/vault/tulajdonsagok/tipus` (`.obsidian/types.json`) | rendben; két egymás utáni változásból a második külön visszavonható |
| előzmény-visszaállítás | `POST /api/vault/elozmeny/visszaallit` | rendben |
| Obsidian-import visszafordítása | `importalas.obsidian_importal` → szerkesztés pillanatképpel → `undo_commit` → `visszafordit` | rendben: a forrás bájtra és metaadatra azonos, a visszafordítás mindent visz (a Kukába, nem töröl) |
| demo alaphelyzet | `demo.alaphelyzet` → `undo_commit(utana)` | rendben: a felhasználó szerkesztése egy visszavonással visszajön, a hozzáadott jegyzet félretéve, nem törölve |

Meglévő lefedés (változatlan, a szint része): `test_snapshot` (a visszavonási mag: NFD, CRLF, ütközés, napló, helyreállítás),
`test_mentes` (bundle kilépéskor, rotáció), `test_visszaallitas` (bundle → üres hely), `test_teljes_mentes(_termek)`,
`fresh_install/test_alap` (telepítés → mentés → a tároló elvesztése → visszaállítás bundle-ből → újraindítás), `test_elozmeny`,
`test_tulajdonsag_tipusok`, `test_tartos`.

## §2 Konfliktuskezelés (CAS)

`test_korut.py::test_cas_utkozesek_nem_irnak`, `test_visszavonasi_utkozes_nem_ir`, `test_atnevezes_a_terv_utani_…`:
- elavult `alap` hash → 409 `vault.jegyzet_valtozott`; `alap` nélkül → 400 (vak felülírás nincs);
- elavult `rev` a típusregiszterre → 409; elavult `terv_hash` (az index már látta a változást) → 409;
- a visszavonandó sort azóta más is módosította → 409 `pillanatkep.visszavonas_utkozes`, semmi nem változik, nincs commit;
  hibás `sha`/`kor` (`HEAD`, `--all`, próba-kör) → 4xx;
- **megfigyelés**: ha a terv után, de az index frissülése ELŐTT jelenik meg egy új, a forrásra hivatkozó jegyzet, az átnevezés lefut, az
  önellenőrzése bukik, és **visszagörget** (`atnevezes.visszaallitva`): a vault bájtra az eredeti, félkész állapot nincs. A válasz HTTP
  **500** — adatbiztonságilag rendben, a felületnek 409 lenne a helyes jel (javaslat, nem javítottam: közös hibatérkép).

## §3 Statikus őr: „soha `reset --hard` / `clean` / `checkout -- .`”

`tests/mentes_visszaallitas/test_git_or.py`: a Python-kódban (`core`, `modulok`, `bin`, `packaging`) minden hívás literál-argumentumait
(beágyazott listákkal együtt), a shell- és Swift-forrásokban a sorokat vizsgálja: `reset --hard/--merge/--keep`, `clean`, a munkafa
`checkout`-ja/`restore`-ja, `stash`, `switch --discard-changes`, `read-tree -u`, `push --force`, `branch -D`. Az őr ültetett mintákon
önellenőrzött. Lelet nincs; a `snapshot.py` egyetlen `reset`-je (`reset -q -- <utak>`) csak a stage-ből vesz ki.

## §4 Helyreállítás sérült indexből — **1 lelet, javítva**

`tests/mentes_visszaallitas/test_serult_index.py`, a teljes core-on: (1) nem SQLite fájl → félretéve (`serult-<idő>.sqlite`, nem
törölve), újraépül, a keresés működik, a vault és a HEAD változatlan; (2) **a fájl közepén sérült valódi index**: az olcsó nyitáskori
próba (`tar._probaolvas`) nem látja, az író csak akkor, ha oda ír — a keresés **tartósan 500**-at adott. Javítás: az olvasó a
`SQLITE_CORRUPT/NOTADB` hibánál jelez (`IndexOlvaso._olvaso_serult`), az író pool-generációnként egyszer félreteszi és újraépíti
(`Index._koteg` `serult` üzenet → `_serult_ujraepit`), a kérés addig 503; utána `PRAGMA quick_check = ok`; (3) hiányzó index → újraépül.
Mellékes javítás: a séma nélküli (épp létrejött) fájl olvasása 500 helyett 503 (07 §7 L7.1).

## Nyitott kockázatok / a felhasználóra vár

- A bináris média nincs a git-bundle-ben (14. döntés): a média helyreállítása a teljes (külső lemezes) mentésből megy — a kiadás előtti
  kézi kör: teljes mentés → üres gépre visszaállítás, a média megléte.
- A visszavonás-ütközés felületi szövege és a 500-as `atnevezes.visszaallitva` UX-e (§2).
