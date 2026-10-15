// A kártyák telepítése (C23b; docs/C23-TERV.md 5., 7.): a kísérőjegyzet beágyazásának interaktív paklija, a „Kártyák ebből”
// (a C17 helyőrzője helyett, ugyanazon az azonosítón: ⌘P és a jegyzet helyi menüje) és a „Mai ismétlés” (⌘P → a vezérlő
// Tanulás szakasza). Az `App.svelte` hívja egyszer.

import { tick } from 'svelte';
import type { Felulet } from '../lib/elrendezes/felulet.svelte';
import { ertesitesek } from '../lib/ertesites/ertesites.svelte';
import { GraduationCap } from '../lib/ikon/ikonok';
import type { Regiszter } from '../lib/parancsok/regiszter';
import { jegyzetOsztalyRenderelok } from '../szerkeszto/beagyazas/regiszter';
import { szerkesztok } from '../szerkeszto/szerkesztok.svelte';
import { kartyaUt } from './allando';
import { kartyaApi } from './api';
import { kartyaRenderelo } from './beagyazas';

const MAX_KIJELOLES = 20000;

function hibaSzoveg(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

/** „Kártyák ebből”: a kijelölésből, üres kijelölésnél az egész jegyzetből — előbb ment (a gépi írás mentetlen dokumentumba nem
 *  ír, 28(c)), utána a `kartya_general` feladat indul; a vége a vezérlő szokásos értesítése (Visszavonással). */
export async function kartyakEbbol(): Promise<void> {
  const p = szerkesztok.aktiv;
  const view = p?.nezet();
  if (!p || !view || !p.ut.toLowerCase().endsWith('.md')) {
    ertesitesek.ertesit({ szint: 'info', cim: 'Nyiss meg egy jegyzetet', szoveg: 'A kártyák a jegyzetből vagy a kijelölt részéből készülnek.' });
    return;
  }
  if (kartyaUt(p.ut)) {
    ertesitesek.ertesit({ szint: 'info', cim: 'Ez egy kártyapakli', szoveg: 'Kártya a forrásjegyzetből készül, nem a kísérőjegyzetből.' });
    return;
  }
  const s = view.state.selection.main;
  const kijeloles = s.empty ? undefined : view.state.sliceDoc(s.from, s.to).slice(0, MAX_KIJELOLES);
  try {
    await p.mentes();
    await kartyaApi.general(p.ut, kijeloles);
  } catch (e) {
    ertesitesek.ertesit({ szint: 'hiba', cim: 'A kártyák készítése nem indult el', szoveg: hibaSzoveg(e) });
    return;
  }
  ertesitesek.ertesit({
    szint: 'info',
    cim: 'Kártyák készülnek',
    szoveg: `A modell kártyákat javasol ${kijeloles ? 'a kijelölésből' : 'a jegyzetből'}; ami átmegy a kapukon, a kísérőjegyzetbe kerül (visszavonható).`,
  });
}

export function maiIsmetles(felulet: Felulet): void {
  felulet.atfedes = null;
  felulet.vezerlo.nyitott.tanulas = true;
  felulet.manifoldFeladat = null;
  felulet.manifoldMegnyit();
  void tick().then(() => document.querySelector<HTMLElement>('.vezerlo-tanulas .pakli')?.focus());
}

export function kartyaTelepit(reg: Regiszter, felulet: Felulet): () => void {
  const jegyzetNyitva = () => !!felulet.munkaterulet.aktivFul?.ut?.toLowerCase().endsWith('.md');
  const le = [
    jegyzetOsztalyRenderelok.regisztral(kartyaRenderelo),
    reg.regisztralMind([
      { id: 'kartya.ebbol', nev: 'Kártyák ebből', kategoria: 'Jegyzet', elerheto: jegyzetNyitva, futtat: () => kartyakEbbol() },
      { id: 'kartya.mai', nev: 'Mai ismétlés (kártyák)', kategoria: 'Manifold', ikon: GraduationCap, futtat: () => maiIsmetles(felulet) },
    ]),
  ];
  return () => le.forEach((f) => f());
}
