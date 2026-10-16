// A kód-munkafelület telepítése (C36a-UI, F10: több nyelv; `docs/C36A-UI-TERV.md`, `docs/plan/parity/CODE-WORKBENCH.md`): a
// forrásfájlok (`.cpp`, `.py`, `.js`, … a core nyelvprofiljai) fül-nézete, a ⌘P parancsai (⌘R, ⇧⌘R, ⇧⌥F, megszakítás, AI,
// eszközláncok, új C++ feladat), a `![[x.ext]]` beágyazás és a `cpp_futas` / `kod_futas` / `cpp_ai` / `kod_ai` WS-események
// feliratkozása. Az `App.svelte` hívja egyszer, a többi nézet telepítése mellett.

import './kod.css';
import type { CoreKapcsolat } from '../lib/core/ws.svelte';
import type { Felulet } from '../lib/elrendezes/felulet.svelte';
import { nezetek } from '../lib/elrendezes/nezetek.svelte';
import { t, tk } from '../lib/i18n';
import { Bug, Code, Play, Square } from '../lib/ikon/ikonok';
import type { Regiszter } from '../lib/parancsok/regiszter';
import { beagyazasRenderelok } from '../szerkeszto/beagyazas/regiszter';
import { AI_MOD_NEV, kodAI } from './ai.svelte';
import { aiKer } from './aiElfogad';
import { kodFulok } from './aktiv.svelte';
import { kodBeagyazasRenderelo } from './beagyazas';
import { kodFutasok } from './futas.svelte';
import KodFul from './KodFul.svelte';
import { celNyelve, ellenoriz, formaz, kodCel } from './muveletek';
import { KOD_UT, kodNyelvek, nyelvUt } from './nyelvek.svelte';

/** A cél nyelvének hibakereső (sanitizer) módja: C és C++ (a core a többit `kod.mod_nem_tamogatott`-tal utasítja el). */
const hibakeresoVan = () => celNyelve(kodCel()).nyelv?.hibakereso === true;

export function kodTelepit(reg: Regiszter, felulet: Felulet, kapcsolat: CoreKapcsolat): () => void {
  const le = [
    nezetek.regisztral({
      id: 'kod.cpp', // a C36a-UI azonosítója (az elrendezés-állapot hivatkozhat rá); most minden nyelv forrásfáját kezeli
      illeszkedik: (f, info) => !!f.ut && KOD_UT.test(f.ut) && (!info || info.tipus === 'egyeb'),
      komponens: KodFul,
      prioritas: 10,
    }),
    beagyazasRenderelok.regisztral(kodBeagyazasRenderelo),
    kodFutasok.telepit(kapcsolat),
    kodAI.telepit(kapcsolat),
    reg.regisztralMind([
      {
        id: 'kod.ellenorzes',
        nev: tk('Kód: ellenőrzés (fordítás és tesztek)'),
        kategoria: tk('Kód'),
        billentyu: 'Mod+R',
        ikon: Play,
        elerheto: () => kodCel() !== null,
        futtat: () => void ellenoriz(felulet, 'gyors'),
      },
      {
        id: 'kod.ellenorzes-hibakereso',
        nev: tk('Kód: ellenőrzés hibakereső móddal (ASan, UBSan; C és C++)'),
        kategoria: tk('Kód'),
        billentyu: 'Mod+Shift+R',
        ikon: Bug,
        elerheto: () => kodCel() !== null && hibakeresoVan(),
        futtat: () => void ellenoriz(felulet, 'hibakereso'),
      },
      {
        id: 'kod.formaz',
        nev: tk('Kód: formázás (clang-format, C++)'),
        kategoria: tk('Kód'),
        billentyu: 'Alt+Shift+F',
        elerheto: () => !!kodFulok.aktiv?.irhato() && nyelvUt(kodFulok.aktiv.ut)?.azonosito === 'cpp',
        futtat: () => void formaz(),
      },
      {
        id: 'kod.megszakit',
        nev: tk('Kód: a futó ellenőrzés megszakítása'),
        kategoria: tk('Kód'),
        ikon: Square,
        elerheto: () => kodFutasok.fut,
        futtat: () => void kodFutasok.megszakit(),
      },
      {
        id: 'kod.eszkozlancok',
        nev: tk('Kód: nyelvek és eszközláncok'),
        kategoria: tk('Kód'),
        ikon: Code,
        elerheto: () => !!kodFulok.aktiv,
        futtat: () => {
          kodNyelvek.panelNyitva = !kodNyelvek.panelNyitva;
          void kodNyelvek.betolt(true);
        },
      },
      // C36b, F10: az AI-segítség, csak kattintásra. A `.cpp` kalibrált modell nélkül nem elérhető (D9); a többi nyelven a
      // kalibrálatlan modell csak jelölt próbaként (trial) fut — a gombok engednek, a felület minden próbát jelöl.
      ...(['hiba', 'tipp', 'teszt', 'stressz'] as const).map((mod) => ({
        id: `kod.ai-${mod}`,
        get nev() {
          return t('Kód AI: {mod}', { mod: t(AI_MOD_NEV[mod]) });
        },
        kategoria: tk('Kód'),
        elerheto: () => kodCel() !== null && kodAI.indithato(celNyelve(kodCel()).motor),
        futtat: () => void aiKer(felulet, mod),
      })),
      {
        id: 'kod.ai-megszakit',
        nev: tk('Kód AI: a futó kérés megszakítása'),
        kategoria: tk('Kód'),
        ikon: Square,
        elerheto: () => kodAI.fut,
        futtat: () => void kodAI.megszakit(),
      },
      {
        id: 'kod.uj-feladat',
        nev: tk('kod.uj_feladat.parancs'),
        kategoria: tk('Kód'),
        futtat: () => {
          felulet.atfedes = 'cpp-feladat';
        },
      },
    ]),
  ];
  return () => le.forEach((f) => f());
}
