// A tracker telepítése (C27): a gyűjtők (aktív idő, parancs-megfigyelő, kötegelt küldés), a két nézet-fül
// (Statisztika, Használat) és a parancsaik. Az `App.svelte` hívja egyszer. A karakter-, mentés- és gépelésmérés
// a szerkesztőben (`szerkeszto/`) kötődik a `trackerKliens`-hez; a kártya/kvíz/integrálás gyűjtői a C20–C23-ban.

import type { Felulet } from '../lib/elrendezes/felulet.svelte';
import { nezetek } from '../lib/elrendezes/nezetek.svelte';
import { ChartNoAxesColumn, Gauge } from '../lib/ikon/ikonok';
import { tk } from '../lib/i18n';
import type { Regiszter } from '../lib/parancsok/regiszter';
import { mediaNezetek } from '../media/aktiv.svelte';
import { aktivUtKulcs } from '../lib/tracker/aktivFul';
import { aktivIdoFigyelo } from '../lib/tracker/bevitel';
import { trackerKliens } from '../lib/tracker/kliens.svelte';
import { maiNap } from '../lib/tracker/megjelenites';
import HasznalatNezet from './HasznalatNezet.svelte';
import StatisztikaNezet from './StatisztikaNezet.svelte';

export function trackerTelepit(reg: Regiszter, felulet: Felulet): () => void {
  const m = felulet.munkaterulet;
  const nyit = (tipus: 'statisztika' | 'hasznalat') => () => {
    felulet.atfedes = null;
    m.megnyitNezet(tipus);
  };
  const leNezetek = [
    nezetek.regisztral({
      id: 'tracker.statisztika',
      illeszkedik: (f) => f.ut === null && f.nezet?.tipus === 'statisztika',
      komponens: StatisztikaNezet,
      prioritas: -50,
    }),
    nezetek.regisztral({
      id: 'tracker.hasznalat',
      illeszkedik: (f) => f.ut === null && f.nezet?.tipus === 'hasznalat',
      komponens: HasznalatNezet,
      prioritas: -50,
    }),
  ];
  const leParancsok = reg.regisztralMind([
    { id: 'manifold.statisztika', nev: tk('Statisztika megnyitása'), kategoria: tk('Manifold'), ikon: ChartNoAxesColumn, futtat: nyit('statisztika') },
    { id: 'manifold.hasznalat', nev: tk('Használat megnyitása'), kategoria: tk('Manifold'), ikon: Gauge, futtat: nyit('hasznalat') },
  ]);
  // parancsonkénti használat: egyetlen megfigyelő a regiszter végrehajtási pontján (azonosító + forrás)
  const leMegfigyelo = reg.megfigyel((id, forras) => trackerKliens.parancs(id, forras));
  // aktív idő (38. döntés): az ablak elöl van, 60 mp-en belül volt bevitel (a lejátszó játszása is az), és számító fül az aktív —
  // minden fájl-fül (jegyzet, PDF, videó, hang, canvas, base) és a gráf
  const leAktiv = aktivIdoFigyelo({
    most: () => performance.now(),
    aktivUt: () => aktivUtKulcs(m.aktivFul),
    lathato: () => document.visibilityState === 'visible',
    fokuszban: () => document.hasFocus(),
    jatszik: () => {
      const ut = aktivUtKulcs(m.aktivFul);
      return !!ut && mediaNezetek.jatszikUt(ut);
    },
    jelent: (ut, mp, nap) => trackerKliens.aktivMp(ut, mp, nap),
    nap: () => maiNap(),
  });
  const leKuldes = trackerKliens.indit();
  return () => {
    leKuldes();
    leAktiv();
    leMegfigyelo();
    leParancsok();
    leNezetek.forEach((f) => f());
  };
}
