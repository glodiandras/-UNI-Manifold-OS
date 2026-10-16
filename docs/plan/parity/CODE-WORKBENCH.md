# F10 — Multi-language code workbench (backend + contract)

Not found in v2 (`grep -ril "workbench\|munkafelület" docs` gives only the C36a/C36b plans); designed from the C36a/C36b
code (`modulok/cpp`, `modulok/homokozo/program.py`, `core/cpp_utvonal.py`, `core/cpp_ai.py`). The backend is done; the UI
is the next wave.

## Layers

| Layer | File | Role |
|---|---|---|
| Profile schema | `core/kod_nyelvek.py` | the single place: id, extensions, sandbox source name, compile/run argv templates, toolchain discovery spec, diagnostics + runtime-report parser, calibration key, AI language name, fence tags |
| Discovery | `modulok/kod/felderites.py` | config override → embedded runtime → PATH; a tool counts only if its version probe passes **in the compile sandbox**; too-broad roots refused; xcrun shims resolved; no download (D3) |
| Sandbox | `modulok/kod/homokozo.py`, `kod_fordit.sb`, `kod_futtat.sb` | the C36a guards reused (time, memory fails closed, output, disk); native binaries run under the C36a `profil_futtat.sb` |
| Run | `modulok/kod/futtato.py`, `ellenorzes.py` | compile once, every `teszt` block in the sandbox; C/C++ delegate to the unchanged C36a engine |
| Diagnostics | `modulok/kod/diagnosztika.py` | `gcc`-style (clang, swiftc, rustc short, go, own Python/JS/TS checkers), `javac`; runtime: python, node, java, go, rust, swift — all bound to a source line |
| AI | `modulok/kod/ai.py`, `ai_futas.py` | five modes with a language parameter; C++ keeps the measured C36b prompt |
| Core | `core/kod_utvonal.py` (via `app.cpp.kod`) | endpoints, one check + one AI request at a time, WS events |

v1 languages: `cpp`, `c` (portable LLVM), `python`, `javascript`, `typescript` (embedded runtime; TS = Node's type
stripping, **no type checking**), `java`, `go`, `rust`, `swift` (system toolchain; `[kod.eszkozok]` paths). Only C/C++ have
the `hibakereso` (sanitizer) mode.

## D9 (AI)

Router task = `Profil.kalibracios_kulcs` (`kod` for C++, `kod_c`, `kod_python`, … — each language calibrated on its own gold
set, none exists yet). Calibrated → real (`proba: false`). Otherwise trial only (`proba: true`): `[kod] proba_modell`, else the
calibrated `kod` (C++) model. Neither → `kod.nincs_kalibralt`. A real request that the worker reports as a trial is refused.
The engine never writes; suggestions are accepted by the user in the editor.

## HTTP

All errors: `{hiba, kod, param}` (English catalog `core/hibauzenetek.py`, `kod.*`).

| Endpoint | Body / query | Answer |
|---|---|---|
| `GET /api/kod/nyelvek` | `?frissit=1` | `{nyelvek: [{azonosito, nev, kiterjesztesek, motor, nativ, eszkozlanc, kalibracios_kulcs, ai_modok, modok, telepites_tipp, elerheto, eszkozok: [{nev, ok, ut, valos, gyoker, forras, verzio, probak}], sdk, hiba: {kod, param, uzenet} \| null}]}` |
| `GET /api/kod/feladat` | `?ut=` (note `.md` or source) | `{nyelv, jegyzet, forras, jegyzetek, tesztek, hiba}` |
| `POST /api/kod/ellenoriz` | `{ut, jegyzet?, nyelv?, mod?: gyors\|hibakereso}` | 202 `{futas, nyelv, forras, jegyzet, mod, tesztek_db}` |
| `GET /api/kod/futas/{futas}` | | `{futas, nyelv, forras, jegyzet, mod, allapot: fut\|kesz\|hiba\|megszakitva, tesztek_db, fordit, tesztek, kesz, hiba}` |
| `POST /api/kod/megszakit` | `{futas}` | `{megszakitva, allapot}` |
| `POST /api/kod/ai` | `{mod: hiba\|tipp\|megoldas\|teszt\|stressz, ut, jegyzet?, nyelv?, megerosit?}` | 202 `{ai, mod, nyelv, forras, jegyzet}` |
| `GET /api/kod/ai/{ai}` | | `{ai, …, modell: {modell, proba, kalibracios_kulcs, indok}, eredmeny, kesz, hiba}` |
| `POST /api/kod/ai/megszakit` | `{ai}` | `{megszakitva, allapot}` |

Error codes: 400 `kod.hianyzik_ut`, `kod.ismeretlen_kiterjesztes`, `kod.ismeretlen_nyelv`, `kod.ismeretlen_mod`,
`kod.mod_nem_tamogatott`, `kod.ismeretlen_ai_mod`, `kod.megerosites_kell`, `kod.nincs_beagyazott_forras`,
`kod.hianyzik_azonosito`; 404 `kod.nincs_forras`, `kod.nincs_ilyen_futas`; 409 `kod.tobbertelmu` (+`jegyzetek`),
`kod.mentetlen` (+`utak`), `kod.foglalt`; 503 `kod.motor_nem_valaszol`, `kod.core_leall`.

## WS

Every event: `{tipus, szakasz, nyelv, forras, jegyzet, mod, futas | ai, …}`.

`kod_futas`: `indul {tesztek_db}` → `fordit_kesz {fordit: {ok, allapot, ms, csucs_mb, diagnosztika: [{szint, fajl, sor,
oszlop, uzenet, kapcsolo, sajat, vegzetes, kodreszlet}], hiba_db, figyelmeztetes_db, levagva, uzenet, kivonat, kod}}` →
`teszt {teszt: {sorszam, cim, allapot, ido_ms, cpu_ms, csucs_mb, idokorlat_s, memoria_mb, osszevetes, kilepes, jel, diff,
stdout_kivonat, stderr_kivonat, jelentes: {forras, fajta, leiras, fajl, sor, oszlop, fuggveny, keretek}, uzenet, hiba},
kesz_db, ossz}`… → `kesz {atment, tesztek_db, atment_db, fordit_ok, ms, hash, uzenet, kod}` | `hiba {kod, param, uzenet}` |
`megszakitva`. Test states: `atment`, `hibas_kimenet`, `futasi_hiba`, `szanitizer` (C/C++), `idotullepes`, `memoria`,
`kimenet_tullepes`, `iras_korlat`, `hibas_teszt`, `homokozo_hiba`. (C/C++ events come from the C36a engine: same shape,
Hungarian `uzenet` there.)

`kod_ai`: `indul` → `ellenorzes {fordit_ok, atment_db, ossz, bizonyitek}` → `modell {modell, proba, kalibracios_kulcs,
indok}` → `generalas {tokenek}`… → `eredmeny {mod, proba, …}` → `kesz {ok, mod, modell, proba, ms}` | `hiba {kod, param,
uzenet}` (`kod.nincs_kalibralt`, `kod.csak_tavol`, `kod.worker_hiba`, `kod.nincs_eszkozlanc`, …) | `megszakitva`.
The UI must show the trial label whenever `proba` is true.

## Open (next waves)

- `core/vaultio.py` reads/writes only `.cpp` among sources (C36a; `test_a_tobbi_forraskod_tovabbra_sem_olvashato_sem_irhato`):
  the editor of `.py/.js/.ts/.java/.go/.rs/.swift/.c` needs that allow-list widened (an integrator decision).
- Gold sets for `kod_<language>` (F6 measurement) — until then every non-C++ AI request is a trial.
- No tracker event for non-C++ runs yet (`cpp_proba` stays on `/api/cpp`).
