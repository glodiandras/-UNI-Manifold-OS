# 07 – F9 biztonsági audit (PLAN §10 F9, „a 32. pont auditjai”)

Dátum: 2026-10-16. Hatókör: a termék-repó (`/Volumes/Work/[UNI] Manifold-OS`) kódja; szintetikus vaultok és ál-HOME-ok ideiglenes
mappában, a valódi vault és a v2 érintetlen, hálózati kérés nincs (a feloldó cserélve, a `socket` védőhálóval). Minden lelethez
regressziós teszt tartozik; a teljes szint: `bin/mos test --szint biztonsag`.

| § | Terület | Teszt | Eredmény |
|---|---|---|---|
| 1 | Homokozó-kitörés (F10 kódfuttatás, valódi `sandbox-exec`) | `tests/biztonsag/test_homokozo_kitores.py` | nincs lelet |
| 2 | Útvonal-bejárás, symlink-szökés a vault-API-kon | `tests/biztonsag/test_utvonal_bejaras.py` | nincs kihasználható lelet; 2 megjegyzés |
| 3 | SSRF a külső kép-letöltőn (és a videólánc címszűrőjén) | `tests/biztonsag/test_ssrf.py` | **1 lelet, javítva** |
| 4 | A gépi-írás kapu megkerülése (lépés-token) | `tests/biztonsag/test_gepi_kapu.py` | nincs lelet |
| 5 | Beégetett titok, fejlesztői út/név | `tests/biztonsag/test_titok_es_ut.py` | 1 javítva, 1 átadva (Swift) |
| 6 | Függőségek (offline) | `tests/biztonsag/test_titok_es_ut.py::FuggosegTest` | nincs lelet (korlátos módszer) |
| 7 | Mellékleletek (robosztusság) | `tests/mentes_visszaallitas/test_serult_index.py` | **2 lelet, javítva** |

## §1 Homokozó (`modulok/kod/kod_futtat.sb`, `kod_fordit.sb`, `modulok/homokozo/*`)

A profil `deny default`; olvasható csak a rendszerkönyvtárak, az értelmező futtatókörnyezete (`OLVAS_1..4`) és a saját `MUNKA`
mappa; írható csak a `MUNKA`; exec csak az értelmező; hálózat, fork, más folyamat jelzése tiltott. A forrás a `MUNKA`-ba másolódik
(`modulok/kod/futtato.py:194-209`), a vault mappája nem olvasási gyökér.

Új próbák Pythonban és JavaScriptben (a beágyazott futtatókörnyezetekkel): vault-jegyzet olvasása és listázása, `~/.ssh` olvasása,
írás a vaultba, az `{install}`-ba, a HOME-ba, a `/private/tmp`-be és a kódfába; symlink és hard link a munkamappában egy vault-fájlra;
TCP a helyi portra (IPv4/IPv6), DNS, UDP, `exec`, `fork`/`spawn`. Mind elutasítva, a célfájlok nem jönnek létre, a helyi port nem kap
kapcsolatot. Pozitív kontroll: a `MUNKA`-ba írás működik, a `/etc/hosts` olvasása tiltott (a profil valóban él). A korábbi lefedés
marad: `test_homokozo_program` (F1–F13, C/C++), `test_homokozo` (CAS), `test_homokozo_elszigeteles`, `test_kod_ellenorzes`.

Elfogadott: a `file-read-metadata` globális (egy fájl LÉTEZÉSE megtudható, tartalma és mappalistája nem) — a profil kommentje rögzíti.

## §2 Útvonal-bejárás és symlink-szökés

Valódi HTTP-n, minden utat fogadó végponton ugyanaz a rosszindulatú útkészlet: `..` (perjellel, visszaperjellel, érvényes előtag
után), abszolút út, NUL és újsor, rejtett szakasz (`.obsidian`), U+2025, a vaulton KÍVÜLRE mutató symlink-jegyzet és symlink-mappa.
Végpontok: `GET/PUT /api/vault/fajl`, `POST /api/vault/uj` (mappa és név), `POST /api/vault/atnevezes(/terv)` (ki és BE: a
kinti fájl bemásolása is), `GET /media/<token>/…`, `POST /api/vault/import` (feltöltés), `GET /api/vault/elozmeny(/valtozat)`,
`POST /api/vault/elozmeny/visszaallit` (a `sha` helyén opció is), `GET /api/vault/tulajdonsagok/kulcsok`; a hitelesítés útírás-
változatai (`//api`, `/API`, `/%61pi`, `/./api`, `/app/../api`). Elvárás és eredmény: 4xx, a kinti titok egyetlen válaszban sincs, a
vaulton kívül semmi nem jön létre és nem változik, és a kinti tartalom a vaultba sem kerül be. Az őrök: `vaultio.norm_path`
(rejtett és `..` szakasz, vezérlőkarakter), `Vault._abs` → `utkapu.alatta` (realpath), `kanonikus`, a médiánál engedélylista.

Megjegyzések (nem kihasználható, nem javítva):
- **M2.1** `POST /api/vault/uj` abszolút `mappa`-val: a `norm_path` a kezdő `/`-t levágja, így a jegyzet a vaulton BELÜL, egy
  `private/var/…` almappában jön létre. Szökés nincs, de meglepő. Javaslat: a `norm_path` utasítsa el az abszolút utat (közös API;
  a felület esetleges `/`-os útjai miatt külön kör).
- **M2.2** Egy commitolt symlink-jegyzet előzmény-változata a link CÉLJÁNAK szövegét adja (a git a linket tárolja, nem a fájlt) —
  csak metaadat, tartalom nem szivárog.

## §3 SSRF — **lelet, javítva**

`core/kulso_kep.py` (és a videólánc `_helyi_cim`-je) közös szűrője, `core/videolanc._nem_nyilvanos`, az `ipaddress.is_global`-ra
támaszkodott. Ez a **NAT64 jól ismert előtagot** (`64:ff9b::/96`, RFC 6052) és az **IPv4-kompatibilis** `::a.b.c.d` alakot
globálisnak mondja: `https://[64:ff9b::7f00:1]/` (DNS64/NAT64 hálózaton az átjáró 127.0.0.1-e) és egy `64:ff9b::a00:5` DNS-válasz (az
átjáró mögötti 10/8) átment. Javítás (`core/videolanc.py`): a `::/96` mindig nem-nyilvános, a `64:ff9b::/96`-nál a beágyazott IPv4 dönt
(a nyilvános NAT64-cím továbbra is engedett). Regresszió: `test_ssrf.py` (beágyazott alakok, DNS-válaszok, szám- és névalakok, URL-szint;
a kapcsolat továbbra is az ellenőrzött IP-re megy, az átirányítás ugyanígy szűrt — `test_kulso_kep.py`).

## §4 Gépi-írás kapu

A lépés-token (`MOS_LEPES_TOKEN`) minden `GET`-et és az `ENGEDELYEZETT` számolókat hívhatja. Ellenőrizve valódi HTTP-n: (a) mind a
81 regisztrált fix `GET` útvonal (paraméterrel és nélküle) lépés-tokennel — utána a vault bájtjai, a pillanatkép-HEAD és a kinti
mappa változatlan: **egyetlen olvasó sem ír**; (b) az engedett számolók író-jellegű argumentumokkal sem írnak (új számoló esetén a
teszt szól); (c) minden író végpont 403/404/405 a lépés-tokennel minden útírás-változatban (záró `/`, `//`, százalékkódolás, query) és
`X-HTTP-Method-Override`-dal; `GET`/`HEAD` író útra sem fut le. Lelet nincs.

## §5 Titkok és fejlesztői utak

- Titok-alakú karakterlánc (HF, `sk-`, GitHub, AWS, Slack, Google, privát kulcs) a repó egyetlen fájljában sincs (`git ls-files -co`).
- A szállított fákban (`core`, `modulok`, `app/src`, `shell`, `bin`, `config`, `packaging`, `docs/user`, README) fejlesztői név vagy út:
  **javítva** `core/vaultkivul.py:3` docstringje (`/Volumes/work/manifold/…` → semleges példa). **Átadva** (a packaging-agens fájlja,
  nem szerkesztettem): `shell/Sources/RootLocator.swift:51` önteszt-táblája `"/Volumes/Work/Manifold-OS"` és `"/Volumes/Work/Manifold.app"`
  — semleges lemeznévre (`/Volumes/Disk/…`) cserélendő; a teszt ismert kivételként listázza, és szól, ha eltűnik.
- Nem szállított, de `git archive`-ba kerülő: `docs/dev/ARCHITECTURE.md`, `docs/dev/LEGACY-SZERZODESEK.md`, `docs/PLAN.md`, `CLAUDE.md`
  tartalmaz `/Volumes/Work/…` utat; a `.gitattributes` csak a `docs/plan/**`-t és a `DECISIONS-v2.md`-t zárja ki. Javaslat: az RC
  előtti ellenőrzőlistán export-ignore vagy semlegesítés (R9).

## §6 Függőségek (offline)

Offline nincs sebezhetőségi adatbázis; a módszer: a `config/requirements.lock` és az `app/package-lock.json` pinjei egy padló-táblával
(az audit idején ismert javított verziók: pl. jinja2 ≥ 3.1.6, h11 ≥ 0.16, requests ≥ 2.32.4, urllib3 ≥ 2.5, setuptools ≥ 78.1.1,
torch ≥ 2.6, pdfjs-dist ≥ 4.2.67, dompurify ≥ 3.2.4, katex ≥ 0.16.21, nanoid ≥ 3.3.8 …) összevetve: minden pin a padló felett. A
lockok épek: az npm minden csomagja a registryből, integritás-hash-sel; a pip-lock hash-elt, közvetlen URL / editable nincs. **A
felhasználóra vár:** az RC előtt egy online `pip-audit -r config/requirements.lock` és `npm audit --omit=dev` (a pinek újabbak, mint
amit offline meg lehet ítélni).

## §7 Mellékleletek (a próbák közben, javítva)

- **L7.1** Index-verseny: az író a `vault.sqlite`-t az első migráció commitja ELŐTT hozza létre; az ebben az ablakban nyitó olvasó üres
  sémán futott (`no such table: fts` → **500**). Javítás: `core/index/olvaso.py` — `user_version < VERZIO` mellett `NemKesz` (503).
  Teszt: `test_serult_index.SemaNelkuliOlvasoTest`.
- **L7.2** A fájl KÖZEPÉN sérült index: az olcsó nyitáskori próba nem látja, az író csak akkor, ha oda ír — az olvasók (keresés)
  **tartósan 500**-at adtak („malformed”). Javítás: az olvasó a sérülést jelzi (`_olvaso_serult`), az író pool-generációnként egyszer
  félreteszi és újraépíti (`core/index/indexelo.py`), a kérés 503. Teszt: `test_serult_index.KozepeSerultTest` (lásd 08 §4).

## Nyitott kockázatok

- A „gépszintű” modellzár (`{install_state}/modell.lock`) felhasználónként él: két bejelentkezett felhasználó egyszerre tölthet modellt
  (RAM). v1-ben elfogadható; ha nem, közös (`/Users/Shared`) zár kell.
- Közös (két felhasználó által nyitott) munkatér saját `core.log`-ja a másik felhasználó HOME-útját is rögzíti (alacsony).
- `atnevezes.visszaallitva` (az önellenőrzés visszagörget) HTTP 500-zal jön — adatbiztonságilag rendben, UX-ben 409 lenne helyes (08 §2).
