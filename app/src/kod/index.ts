// A C++ munkafelület telepítése (C36a-UI; `docs/C36A-UI-TERV.md`): a `.cpp` fül nézete, a ⌘P parancsai (⌘R, ⇧⌘R,
// ⇧⌥F, megszakítás, új feladat), a `![[x.cpp]]` beágyazás és a `cpp_futas` WS-esemény feliratkozása. Az `App.svelte`
// hívja egyszer, a többi nézet telepítése mellett.

import './kod.css';
import type { CoreKapcsolat } from '../lib/core/ws.svelte';
import type { Felulet } from '../lib/elrendezes/felulet.svelte';
import { nezetek } from '../lib/elrendezes/nezetek.svelte';
import { t, tk } from '../lib/i18n';
import { Bug, Play, Square } from '../lib/ikon/ikonok';
import type { Regiszter } from '../lib/parancsok/regiszter';
import { beagyazasRenderelok } from '../szerkeszto/beagyazas/regiszter';
import { AI_MOD_NEV, kodAI } from './ai.svelte';
import { aiKer } from './aiElfogad';
import { kodFulok } from './aktiv.svelte';
import { CPP, kodBeagyazasRenderelo } from './beagyazas';
import { kodFutasok } from './futas.svelte';
import KodFul from './KodFul.svelte';
import { ellenoriz, formaz, kodCel } from './muveletek';

export function kodTelepit(reg: Regiszter, felulet: Felulet, kapcsolat: CoreKapcsolat): () => void {
  const le = [
    nezetek.regisztral({
      id: 'kod.cpp',
      illeszkedik: (f, info) => !!f.ut && CPP.test(f.ut) && (!info || info.tipus === 'egyeb'),
      komponens: KodFul,
      prioritas: 10,
    }),
    beagyazasRenderelok.regisztral(kodBeagyazasRenderelo),
    kodFutasok.telepit(kapcsolat),
    kodAI.telepit(kapcsolat),
    reg.regisztralMind([
      {
        id: 'kod.ellenorzes',
        nev: tk('C++: ellenőrzés (fordítás és tesztek)'),
        kategoria: 'C++',
        billentyu: 'Mod+R',
        ikon: Play,
        elerheto: () => kodCel() !== null,
        futtat: () => void ellenoriz(felulet, 'gyors'),
      },
      {
        id: 'kod.ellenorzes-hibakereso',
        nev: tk('C++: ellenőrzés hibakereső móddal (ASan, UBSan)'),
        kategoria: 'C++',
        billentyu: 'Mod+Shift+R',
        ikon: Bug,
        elerheto: () => kodCel() !== null,
        futtat: () => void ellenoriz(felulet, 'hibakereso'),
      },
      {
        id: 'kod.formaz',
        nev: tk('C++: formázás (clang-format)'),
        kategoria: 'C++',
        billentyu: 'Alt+Shift+F',
        elerheto: () => !!kodFulok.aktiv?.irhato(),
        futtat: () => void formaz(),
      },
      {
        id: 'kod.megszakit',
        nev: tk('C++: a futó ellenőrzés megszakítása'),
        kategoria: 'C++',
        ikon: Square,
        elerheto: () => kodFutasok.fut,
        futtat: () => void kodFutasok.megszakit(),
      },
      // C36b: az AI-segítség, csak kattintásra (kalibrált `kod` modell nélkül nem elérhető, D9)
      ...(['hiba', 'tipp', 'teszt', 'stressz'] as const).map((mod) => ({
        id: `kod.ai-${mod}`,
        get nev() {
          return t('C++ AI: {mod}', { mod: t(AI_MOD_NEV[mod]) });
        },
        kategoria: 'C++',
        elerheto: () => kodCel() !== null && kodAI.kalibralt && !kodAI.fut,
        futtat: () => void aiKer(felulet, mod),
      })),
      {
        id: 'kod.ai-megszakit',
        nev: tk('C++ AI: a futó kérés megszakítása'),
        kategoria: 'C++',
        ikon: Square,
        elerheto: () => kodAI.fut,
        futtat: () => void kodAI.megszakit(),
      },
      {
        id: 'kod.uj-feladat',
        nev: tk('Új C++ feladat…'),
        kategoria: 'C++',
        futtat: () => {
          felulet.atfedes = 'cpp-feladat';
        },
      },
    ]),
  ];
  return () => le.forEach((f) => f());
}
