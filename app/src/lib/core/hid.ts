// A héj ↔ felület híd, a `window.manifold` (C07, C10.5, C29, C29.7b): a natív héj (Manifold.app) ezeket a függvényeket hívja.
// Külön modulban él (nem az `App.svelte`-ben), hogy a szerződése — a pontos felület, a `mentes()` jelentésének alakja és a
// lépések sorrendje — gépi teszt alatt álljon (T033): ha a híd nem regisztrálódik vagy a `mentes` hiányzik, a héj
// mentés nélkül állítaná le a core-t.
//
//   parancs(id)            a Nézet menü parancsa (a regiszterben; a gyorsbillentyűt a felület kezeli)
//   fokusz()               az ablak visszajöttekor az elveszett lapfókusz visszaállítása (C10.7)
//   naptarEngedely(v)      a rendszer engedélykérő ablaka utáni válasz (C29)
//   mentes()               kilépéskor: leáll állapot → felület-állapot és minden nyitott jegyzet lezárása → a tracker
//                          puffere (időkorláttal) → jelentés `{ok, mentetlen: [{ut, allapot, hiba}]}`
//   leallAllapot(szöveg|null)  a „leáll” réteg szövege; `null`: vissza a szerkesztéshez
//   hejUzenet({szint,cim,szoveg})  a héj értesítése a felületen (pl. a WebContent újratöltődött)
//   ertesitesKattintas(azon)  a rendszerértesítésre (macOS Értesítési központ) kattintottak: az app előre jött, a felület a hozzá
//                          tartozó műveletet futtatja (E10)
//   mentetlen()            a core halálakor: a mentetlen dokumentumok `[{ut, allapot, hiba, szoveg}]` — NEM ment, NEM zár, és nem
//                          kapcsolja be a „leáll” réteget (az újraindítás után a szerkesztés megy tovább; a héj ebből kérdez és másol)

import { t } from '../i18n';

import { ertesitesek, type Szint } from '../ertesites/ertesites.svelte';
import { rendszerErtesites } from '../ertesites/rendszer';
import { leall } from './leall.svelte';

/** A kilépés mentése a héjnak (a `szerkeszto/index.ts` `kilepesMentes`-e): `ok` csak ha minden jegyzet mentve van. */
export interface KilepesJelentes {
  ok: boolean;
  mentetlen: { ut: string; allapot: string; hiba: string | null }[];
}

export interface HidFuggosegek {
  parancsFuttat(id: string): void;
  fokuszVisszaallit(): void;
  naptarFogad(v: unknown): void;
  /** a felület tartós állapotának ütemezése (a `mentesKi` előtt) */
  mentesElokeszit(): void;
  /** a felület tartós állapotának azonnali mentése */
  mentesKi(): Promise<unknown>;
  kilepesMentes(): Promise<KilepesJelentes>;
  /** a tracker puffere (T114); a hívó időkorlátot tesz rá */
  trackerKi(): Promise<void>;
  /** a mentetlen dokumentumok szövegestül (a core halálakor a héj kérdéséhez és a vágólapos mentéshez) */
  mentetlenSzovegek(): MentetlenSzoveg[];
}

export interface MentetlenSzoveg {
  ut: string;
  allapot: string;
  hiba: string | null;
  szoveg: string;
}

/** A tracker-ürítés felső korlátja: a kilépést nem tarthatja fel egy nem válaszoló core. */
export const TRACKER_KI_MS = 2000;

const SZINTEK: Szint[] = ['info', 'siker', 'figyelmeztetes', 'hiba'];

function idokorlat(p: Promise<unknown>, ms: number): Promise<void> {
  return new Promise((kesz) => {
    const t = setTimeout(kesz, ms);
    p.then(
      () => (clearTimeout(t), kesz()),
      () => (clearTimeout(t), kesz()),
    );
  });
}

/** A híd telepítése. A visszaadott függvény leveszi. */
export function hidTelepit(f: HidFuggosegek, cel: Window = window): () => void {
  const hid = {
    parancs: (id: string) => f.parancsFuttat(id),
    fokusz: () => f.fokuszVisszaallit(),
    naptarEngedely: (v: unknown) => f.naptarFogad(v),
    mentes: async (): Promise<KilepesJelentes> => {
      // a „leáll” réteg előbb, mint bármi más: a mentés alatt begépelt szöveg a core leállásával elveszne (T121)
      leall.be(t('Mentés a kilépés előtt…'));
      f.mentesElokeszit();
      const [, jelentes] = await Promise.all([f.mentesKi(), f.kilepesMentes()]);
      // a tracker-puffer a dokumentumok mentése UTÁN (a mentés késleltetése és a karakterszám is bekerül); a hibája nem viszi el a jelentést
      await idokorlat(f.trackerKi(), TRACKER_KI_MS);
      return jelentes;
    },
    mentetlen: (): MentetlenSzoveg[] => {
      try {
        return f.mentetlenSzovegek();
      } catch {
        return []; // a héj kérdése nem akadhat el egy hibás dokumentumon
      }
    },
    leallAllapot: (szoveg: string | null) => {
      if (typeof szoveg === 'string') leall.be(szoveg);
      else leall.ki();
    },
    ertesitesKattintas: (azon: unknown) => rendszerErtesites.kattintas(azon),
    hejUzenet: (u: unknown) => {
      const e = (u ?? {}) as { szint?: unknown; cim?: unknown; szoveg?: unknown };
      if (typeof e.cim !== 'string') return;
      const szint = SZINTEK.find((s) => s === e.szint) ?? 'info';
      ertesitesek.ertesit({ szint, cim: e.cim, szoveg: typeof e.szoveg === 'string' ? e.szoveg : '', idotartam: 0, rendszer: szint !== 'info' && szint !== 'siker' });
    },
  };
  (cel as unknown as { manifold: unknown }).manifold = hid;
  return () => {
    delete (cel as unknown as { manifold?: unknown }).manifold;
  };
}
