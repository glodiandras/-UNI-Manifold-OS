// A cella szerkesztőjének értékátalakításai (C12b): a nyers frontmatter-értékből a mező szövege és vissza.
// Tiszta függvények; az írást a `cellaIr` végzi, a séma-ellenőrzést a core.

import { datumBevitel, ertekSzoveg, LINK_KULCSOK, linkke, listaBevitel, listaElemek, szamBevitel } from '../szerkeszto/tulajdonsagok/ertek';
import type { TulajdonsagTipus } from '../szerkeszto/tulajdonsagok/tipusok';

export type Fajta = 'szoveg' | 'szam' | 'datum' | 'datumido' | 'lista' | 'jelolo' | 'valaszto';

/** Melyik szerkesztő jár az oszlop típusához. A `Status` mindig választó (zárt értékkészlet). */
export function fajta(oszlopTipus: string, kulcs: string, nyers?: unknown): Fajta {
  if (kulcs === 'Status') return 'valaszto';
  switch (oszlopTipus) {
    case 'checkbox':
      return 'jelolo';
    case 'number':
      return 'szam';
    case 'date':
      return 'datum';
    case 'datetime':
      return 'datumido';
    case 'tags':
    case 'multitext':
    case 'aliases':
      return 'lista';
    default:
      return Array.isArray(nyers) ? 'lista' : 'szoveg';
  }
}

/** A frontmatter-tulajdonság típusa íráshoz (a core `tipus` paramétere); ismeretlen: a core találja ki. */
export function iroTipus(oszlopTipus: string): TulajdonsagTipus | undefined {
  return ['text', 'multitext', 'number', 'checkbox', 'date', 'datetime', 'tags', 'aliases'].includes(oszlopTipus)
    ? (oszlopTipus as TulajdonsagTipus)
    : undefined;
}

/** A mező kezdőszövege a nyers értékből. */
export function kezdoSzoveg(f: Fajta, nyers: unknown): string {
  switch (f) {
    case 'lista':
      return listaElemek(nyers).join(', ');
    case 'datum':
      return datumBevitel('date', nyers);
    case 'datumido':
      return datumBevitel('datetime', nyers);
    case 'jelolo':
      return nyers === true || nyers === 'true' ? 'igen' : 'nem';
    default:
      return ertekSzoveg(nyers);
  }
}

export type Bevitel = { ertek: unknown } | { hiba: string };

/** A mező szövege a beírandó értékké. Üres szöveg: üres érték (a kulcs megmarad, `Kulcs:`). */
export function bevitelbol(f: Fajta, szoveg: string, kulcs: string): Bevitel {
  switch (f) {
    case 'szam': {
      const n = szamBevitel(szoveg);
      return n === undefined ? { hiba: 'Ez nem szám.' } : { ertek: n === null ? '' : n };
    }
    case 'lista': {
      const elemek = listaBevitel(szoveg);
      return { ertek: (LINK_KULCSOK as readonly string[]).includes(kulcs) ? elemek.map(linkke) : elemek };
    }
    case 'datum':
    case 'datumido':
      return { ertek: szoveg.trim() };
    case 'jelolo':
      return { ertek: szoveg === 'igen' };
    default: {
      const s = szoveg.trim();
      return { ertek: (LINK_KULCSOK as readonly string[]).includes(kulcs) && s ? linkke(s) : s };
    }
  }
}

/** A mező szövege és a kezdőszöveg azonos-e (változatlan szerkesztésnél nincs írás). */
export function valtozatlan(f: Fajta, kezdo: string, szoveg: string): boolean {
  return f === 'lista' ? JSON.stringify(listaBevitel(kezdo)) === JSON.stringify(listaBevitel(szoveg)) : kezdo.trim() === szoveg.trim();
}
