// Az összefoglaló telepítése (C26b; docs/C26-TERV.md 7.): a kísérőjegyzet beágyazásának megjelenítője, az „Összefoglalás” (a C17
// helyőrzője helyett, ugyanazon az azonosítón: ⌘P és a jegyzet helyi menüje), az „Összefoglalás a mappából”, a „Kontextus-csomag a
// vágólapra” és a „Külső AI válasza…”. Az `App.svelte` hívja egyszer.

import { tk } from '../lib/i18n';
import type { Felulet } from '../lib/elrendezes/felulet.svelte';
import type { Regiszter } from '../lib/parancsok/regiszter';
import { jegyzetOsztalyRenderelok } from '../szerkeszto/beagyazas/regiszter';
import { osszefoglaloRenderelo } from './beagyazas';
import { kontextusCsomag, kulsoAiMegnyit, osszefoglalas, osszefoglalasAktivMappabol } from './parancsok';

export function osszefoglalasTelepit(reg: Regiszter, felulet: Felulet): () => void {
  const jegyzetNyitva = () => !!felulet.munkaterulet.aktivFul?.ut?.toLowerCase().endsWith('.md');
  const mappabanNyitva = () => !!felulet.munkaterulet.aktivFul?.ut?.includes('/');
  const le = [
    jegyzetOsztalyRenderelok.regisztral(osszefoglaloRenderelo),
    reg.regisztralMind([
      { id: 'osszefoglalas.keszit', nev: tk('Összefoglalás'), kategoria: tk('Jegyzet'), elerheto: () => !!felulet.munkaterulet.aktivFul?.ut, futtat: () => osszefoglalas(felulet) },
      { id: 'osszefoglalas.mappa', nev: tk('Összefoglalás a mappából'), kategoria: tk('Jegyzet'), elerheto: mappabanNyitva, futtat: () => osszefoglalasAktivMappabol(felulet) },
      { id: 'osszefoglalas.kontextus', nev: tk('Kontextus-csomag a vágólapra'), kategoria: tk('Jegyzet'), elerheto: jegyzetNyitva, futtat: () => kontextusCsomag(felulet) },
      { id: 'osszefoglalas.kulso-ai', nev: tk('Külső AI válasza…'), kategoria: tk('Jegyzet'), elerheto: jegyzetNyitva, futtat: () => kulsoAiMegnyit(felulet) },
    ]),
  ];
  return () => le.forEach((f) => f());
}
