// A ```plot blokk renderelője (C35a): a kódblokk-regiszterbe köti a rajzolót. A JSXGraph külön chunkban, csak az első
// grafikonnál töltődik be (a Mermaid mintája); a rajzolat csak design-tokenből színez (25. döntés). Az interaktív
// renderelő: a húzás és a nagyítás a táblát éri, a forrás a „</>” gombbal (`blokk.forrasba`) nyílik.
// Formátum: docs/PLOT-FORMATUM.md; terv: docs/C35-TERV.md.

import './plot.css';
import { lustaImportHiba } from '../../../lib/vezerlo/epites.svelte';
import { kodRenderelok, type KodRenderelo } from '../regiszter';
import { MAGASSAG_PX, biztonsagosit, rajzol, type Konyvtar } from './rajzolo';

let betoltes: Promise<Konyvtar> | null = null;

function jsxgraph(): Promise<Konyvtar> {
  return (betoltes ??= import('jsxgraph').then(
    (m) => {
      const k = m.default as unknown as Konyvtar;
      biztonsagosit(k); // a lusta import után, a táblák létrehozása előtt: a feliratok szövegek, nem HTML (A3-14)
      return k;
    },
    (e) => {
      betoltes = null; // a bukott import nem gyorsítótárazódik; ha a dist közben újrafordult, újratöltés kell
      lustaImportHiba();
      throw e;
    },
  ));
}

export const plotRenderelo: KodRenderelo = {
  nyelv: 'plot',
  interaktiv: true,
  becsultMagassag: () => MAGASSAG_PX,
  async render(forras, cel, k) {
    return rajzol(forras, cel, k, await jsxgraph());
  },
};

/** A renderelő regisztrálása a kódblokk-regiszterben; leiratkozót ad. */
export function plotTelepit(): () => void {
  return kodRenderelok.regisztral(plotRenderelo);
}
