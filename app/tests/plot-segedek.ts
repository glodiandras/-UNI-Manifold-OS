// A ```plot tesztek közös segédei: a repó fájljai (a közös Python ↔ TypeScript vektorok, a dokumentáció, a forráskód-őrök)
// Vite `?raw` importtal — így nem kell Node-típus a `svelte-check`-hez, és a tesztek a munkamappától függetlenek.
import dokumentacioNyers from '../../docs/PLOT-FORMATUM.md?raw';
import forrasVektorNyers from '../../modulok/grafikon/vektorok/forras.json?raw';
import kifejezesVektorNyers from '../../modulok/grafikon/vektorok/kifejezes.json?raw';
import kifejezesForras from '../src/szerkeszto/renderelok/plot/kifejezes.ts?raw';
import plotCss from '../src/szerkeszto/renderelok/plot/plot.css?raw';
import rajzoloForras from '../src/szerkeszto/renderelok/plot/rajzolo.ts?raw';

export function vektor<T>(nev: 'kifejezes' | 'forras'): T {
  return JSON.parse(nev === 'kifejezes' ? kifejezesVektorNyers : forrasVektorNyers) as T;
}

export const dokumentacio: string = dokumentacioNyers;

/** A forráskód-őrök: a modul szövege (a megjegyzések nélkül lesz vizsgálva). */
export const forras = { kifejezes: kifejezesForras, rajzolo: rajzoloForras, css: plotCss };
