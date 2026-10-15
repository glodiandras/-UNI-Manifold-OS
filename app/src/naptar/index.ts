// A naptár és az emlékeztetők telepítése (C29): a vezérlő-szakasz adatának WS-figyelése, az értesítések, a
// natív engedély-híd válaszának feldolgozása és a parancsok. Az `App.svelte` hívja egyszer. A naptárba írni
// itt sem lehet: az egyetlen író út a Ma oldal „Beírom a naptárba” gombja (D12).

import type { Felulet } from '../lib/elrendezes/felulet.svelte';
import { ertesitesek } from '../lib/ertesites/ertesites.svelte';
import type { CoreKapcsolat } from '../lib/core/ws.svelte';
import { CalendarCheck, CalendarDays } from '../lib/ikon/ikonok';
import { naptarVezerlo } from '../lib/naptar/allapot.svelte';
import { naptarHid } from '../lib/naptar/hid.svelte';
import { engedelySzoveg, szinkronEredmeny } from '../lib/naptar/megjelenites';
import type { EngedelyAllapot, NaptarEngedelyValasz } from '../lib/naptar/tipusok';
import type { Regiszter } from '../lib/parancsok/regiszter';
import { maAdat } from '../ma/modell.svelte';
import { naptarErtesitesek } from './ertesites';

/** A „Naptár szinkronizálása” parancs: egy kör, majd egy rövid értesítés az eredményről. */
export async function naptarSzinkronParancs(): Promise<void> {
  await naptarVezerlo.szinkron();
  maAdat.utemez(100);
  const a = naptarVezerlo.adat;
  if (naptarVezerlo.muveletHiba) {
    ertesitesek.ertesit({ szint: 'hiba', cim: 'A naptár szinkronja nem sikerült', szoveg: naptarVezerlo.muveletHiba });
  } else if (a?.hiba) {
    ertesitesek.ertesit({ szint: 'figyelmeztetes', cim: 'A naptár szinkronja hibát jelzett', szoveg: a.hiba });
  } else if (a) {
    ertesitesek.ertesit({ szint: 'siker', cim: 'A naptár szinkronizálva', szoveg: szinkronEredmeny(a) });
  }
}

/**
 * A héj válasza az engedély-kérésre (és a kérés nélküli állapot-lekérdezésre): a core engedély-állapotát frissíti,
 * a most megkapott olvasási engedélynél egy kört is indít (hogy az adat azonnal megjelenjen), és a Ma oldalt újratölti.
 * Kérésre érkezett válasznál egy rövid értesítés mondja ki az eredményt.
 */
export async function engedelyValasz(v: NaptarEngedelyValasz, kerdesre: boolean): Promise<void> {
  if (kerdesre) {
    const e = v.esemeny as EngedelyAllapot | null | undefined;
    if (v.hiba) ertesitesek.ertesit({ szint: 'hiba', cim: 'A naptár-engedély kérése nem sikerült', szoveg: v.hiba });
    else if (e === 'engedelyezve') ertesitesek.ertesit({ szint: 'siker', cim: 'A naptár-hozzáférés engedélyezve' });
    else ertesitesek.ertesit({ szint: 'figyelmeztetes', cim: 'A naptár-hozzáférés nincs engedélyezve', szoveg: `Állapot: ${engedelySzoveg(e)}.` });
  }
  await naptarVezerlo.betolt(true);
  if (v.esemeny === 'engedelyezve' && naptarVezerlo.adat?.naptar?.allapot !== 'engedelyezve') await naptarVezerlo.szinkron();
  maAdat.utemez(150);
}

export function naptarTelepit(reg: Regiszter, felulet: Felulet, kapcsolat: CoreKapcsolat): () => void {
  const le = [
    naptarVezerlo.figyel(kapcsolat),
    naptarErtesitesek(kapcsolat, {
      jegyzetNyit: (ut) => felulet.munkaterulet.megnyit(ut, 'ujful'),
      maNyit: () => void reg.futtat('ma.megnyit', 'gomb'),
      vezerloNyit: () => {
        felulet.atfedes = null;
        felulet.vezerlo.nyitott.naptar = true;
        felulet.manifoldFeladat = null;
        felulet.manifoldMegnyit();
      },
    }),
    naptarHid.figyel((v, kerdesre) => void engedelyValasz(v, kerdesre)),
    reg.regisztralMind([
      { id: 'naptar.szinkron', nev: 'Naptár szinkronizálása', kategoria: 'Napló', ikon: CalendarDays, futtat: () => naptarSzinkronParancs() },
      {
        id: 'naptar.engedely',
        nev: 'Naptár-engedély kérése…',
        kategoria: 'Napló',
        ikon: CalendarCheck,
        elerheto: () => naptarHid.elerheto,
        futtat: () => void naptarHid.kerd(),
      },
    ]),
  ];
  return () => le.forEach((f) => f());
}
