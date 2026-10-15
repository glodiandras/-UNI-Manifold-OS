import { svelte } from '@sveltejs/vite-plugin-svelte';
import { defineConfig } from 'vitest/config';

// A kézi próbák (tests/kezi/*.kezi.ts) a valódi vaulton vagy annak klónján futnak, Node-környezetben; a
// rendes tesztkör nem futtatja őket. Indításuk a tests/kezi/*.py szkriptekből (azok adják át az utakat, és a
// feladat méretéhez igazított időkorlátot: `_kornyezet.vitest_futtat` → MOS_KEZI_IDOKORLAT_MS).
// A Svelte-bővítmény a `.svelte.ts` modulok runes-ai miatt kell (pl. a Dokumentum állapota); a `browser` feltétel és a
// `tests/beallitas.ts` ugyanaz, mint a fő konfigban (T084), különben a runes-os modulok a szerver-oldali svelte-et kapják.
const idokorlat = Number(process.env.MOS_KEZI_IDOKORLAT_MS) || 120_000;

export default defineConfig({
  plugins: [svelte()],
  resolve: { conditions: ['browser'] },
  test: {
    environment: 'node',
    include: ['tests/kezi/**/*.kezi.ts'],
    setupFiles: ['tests/beallitas.ts'],
    testTimeout: idokorlat,
    hookTimeout: idokorlat,
  },
});
