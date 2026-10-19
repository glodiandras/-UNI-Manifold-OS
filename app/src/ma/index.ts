// A napi jegyzet, a sablonok és a „Ma” oldal telepítése (C15): a nézet-regisztráció és a parancsok. Az `App.svelte`
// hívja egyszer, a gráf és a Bases mellett.

import type { CoreKapcsolat } from '../lib/core/ws.svelte';
import type { Felulet } from '../lib/elrendezes/felulet.svelte';
import { nezetek } from '../lib/elrendezes/nezetek.svelte';
import { CalendarCheck, CalendarDays, FilePlus, FileText } from '../lib/ikon/ikonok';
import { tk } from '../lib/i18n';
import type { Regiszter } from '../lib/parancsok/regiszter';
import Ma from './Ma.svelte';
import { maAdat } from './modell.svelte';
import { perjelMuveletek } from '../szerkeszto/notion/perjel';
import { komponaloNyit, komponaloElerheto } from './komponaloAllapot.svelte';
import { napiJegyzetNyit, naploSzomszedNyit, datumIdoBeszur, sablonBeszurasElerheto, ujJegyzetSablonbol } from './naplo';

export function maTelepit(reg: Regiszter, felulet: Felulet, kapcsolat: CoreKapcsolat): () => void {
  const leNezet = nezetek.regisztral({
    id: 'ma.nezet',
    illeszkedik: (f) => f.ut === null && (f.nezet?.tipus === 'ma' || f.nezet?.tipus === 'manifold'),
    komponens: Ma,
    prioritas: -50, // az „Új fül” (−100) fölött, mint a gráf: az üres fül csak `ut === null` és nézet-állapot nélkül marad
  });
  const leParancsok = reg.regisztralMind([
    { id: 'jegyzet.kivon', nev: tk('s1.komponalo.kivon'), kategoria: tk('Szerkesztő'), ikon: FileText, elerheto: () => komponaloElerheto(true), futtat: () => komponaloNyit(felulet, 'kivon') },
    { id: 'jegyzet.osszefuz', nev: tk('s1.komponalo.osszefuz'), kategoria: tk('Szerkesztő'), ikon: FileText, elerheto: () => komponaloElerheto(false), futtat: () => komponaloNyit(felulet, 'osszefuz') },
    { id: 'sablon.datum-beszur', nev: tk('s1.napi.datum_beszur'), kategoria: tk('Szerkesztő'), ikon: CalendarDays, elerheto: sablonBeszurasElerheto, futtat: () => datumIdoBeszur('date') },
    { id: 'sablon.ido-beszur', nev: tk('s1.napi.ido_beszur'), kategoria: tk('Szerkesztő'), ikon: CalendarDays, elerheto: sablonBeszurasElerheto, futtat: () => datumIdoBeszur('time') },
    { id: 'naplo.elozo', nev: tk('s1.napi.elozo'), kategoria: tk('Napló'), ikon: CalendarDays, futtat: () => naploSzomszedNyit(felulet, 'elozo') },
    { id: 'naplo.kovetkezo', nev: tk('s1.napi.kovetkezo'), kategoria: tk('Napló'), ikon: CalendarDays, futtat: () => naploSzomszedNyit(felulet, 'kovetkezo') },
    {
      id: 'naplo.napi',
      nev: tk('Napi jegyzet megnyitása'),
      kategoria: tk('Napló'),
      billentyu: 'Mod+Shift+D',
      ikon: CalendarCheck,
      futtat: () => void napiJegyzetNyit(felulet),
    },
    {
      id: 'ma.megnyit',
      nev: tk('Manifold áttekintő'),
      kategoria: tk('Napló'),
      ikon: CalendarDays,
      futtat: () => {
        felulet.atfedes = null;
        felulet.munkaterulet.megnyitNezet('manifold');
      },
    },
    {
      id: 'sablon.beszur',
      nev: tk('Sablon beszúrása…'),
      kategoria: tk('Szerkesztő'),
      ikon: FileText,
      elerheto: sablonBeszurasElerheto,
      futtat: () => {
        felulet.sablonUj = null;
        felulet.atfedes = 'sablon';
      },
    },
    {
      id: 'sablon.uj-jegyzet',
      nev: tk('Új jegyzet sablonból…'),
      kategoria: tk('Fájl'),
      ikon: FilePlus,
      futtat: () => ujJegyzetSablonbol(felulet, null),
    },
  ]);
  perjelMuveletek.sablonValaszto = () => {
    felulet.sablonUj = null;
    felulet.atfedes = 'sablon';
  };
  const leFigyel = maAdat.figyel(kapcsolat);
  return () => {
    perjelMuveletek.sablonValaszto = null;
    leFigyel();
    leParancsok();
    leNezet();
  };
}
