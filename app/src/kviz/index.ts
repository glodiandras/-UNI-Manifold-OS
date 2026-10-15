// A kvíz telepítése (C22a, C22b): a kvízjegyzet beágyazásának saját megjelenítője és a „Kvíz ebből” (a C17 helyőrzője helyett,
// ugyanazon az azonosítón: ⌘P és a jegyzet helyi menüje). Az `App.svelte` hívja egyszer.

import type { Felulet } from '../lib/elrendezes/felulet.svelte';
import { ertesitesek } from '../lib/ertesites/ertesites.svelte';
import type { Regiszter } from '../lib/parancsok/regiszter';
import { jegyzetOsztalyRenderelok } from '../szerkeszto/beagyazas/regiszter';
import { szerkesztok } from '../szerkeszto/szerkesztok.svelte';
import { kvizUt } from './allando';
import { kvizGeneral } from './api';
import { kvizRenderelo } from './beagyazas';

const KISERO_ELOTAG = 'ATTCHMNTS - ';

function hibaSzoveg(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

/** „Kvíz ebből”: előbb ment (a gépi írás mentetlen dokumentumba nem ír, 28(c)), utána a `kviz_general` feladat indul; a vége a
 *  vezérlő szokásos értesítése (Visszavonással). A kvíz modellje lehet, hogy csak a távol-keretbe fér (63. döntés): akkor a
 *  feladat sorba áll, és tétlenségben készül el — ezt az értesítés kimondja. */
export async function kvizEbbol(indit: (ut: string) => Promise<unknown> = kvizGeneral): Promise<void> {
  const p = szerkesztok.aktiv;
  if (!p || !p.ut.toLowerCase().endsWith('.md')) {
    ertesitesek.ertesit({ szint: 'info', cim: 'Nyiss meg egy jegyzetet', szoveg: 'A kvíz a nyitott jegyzetből készül.' });
    return;
  }
  if (kvizUt(p.ut) || p.ut.normalize('NFC').split('/').some((r) => r.startsWith(KISERO_ELOTAG))) {
    ertesitesek.ertesit({ szint: 'info', cim: 'Ez egy kísérőjegyzet', szoveg: 'Kvíz a forrásjegyzetből készül, nem a kvízből vagy a kártyákból.' });
    return;
  }
  try {
    await p.mentes();
    await indit(p.ut);
  } catch (e) {
    ertesitesek.ertesit({ szint: 'hiba', cim: 'A kvíz készítése nem indult el', szoveg: hibaSzoveg(e) });
    return;
  }
  ertesitesek.ertesit({
    szint: 'info',
    cim: 'Kvíz készül',
    szoveg:
      'A modell kérdéseket javasol a jegyzetből; ami átmegy a kapukon, a kvízjegyzetbe kerül, a jegyzetbe egy beágyazó sor (visszavonható). ' +
      'Ha a kvíz modellje csak tétlenségben futhat, akkor készül el, amikor nem dolgozol.',
  });
}

export function kvizTelepit(reg?: Regiszter, felulet?: Felulet): () => void {
  const le = [jegyzetOsztalyRenderelok.regisztral(kvizRenderelo)];
  if (reg && felulet) {
    const jegyzetNyitva = () => !!felulet.munkaterulet.aktivFul?.ut?.toLowerCase().endsWith('.md');
    le.push(reg.regisztralMind([{ id: 'kviz.ebbol', nev: 'Kvíz ebből', kategoria: 'Jegyzet', elerheto: jegyzetNyitva, futtat: () => kvizEbbol() }]));
  }
  return () => le.forEach((f) => f());
}
