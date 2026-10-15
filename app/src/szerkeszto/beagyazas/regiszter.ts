// A beágyazás-renderelők bővítési pontja (C10). A jegyzet, kép, videó, hang és PDF a `rajzol.ts`-ben él; a
// többi típus (canvas: C14, base: C12, a PDF-nézet horgonya: C16) ide regisztrál, addig helyőrző-chip jelenik meg.
//
//   beagyazasRenderelok.regisztral({ tipus: 'canvas', render: (adat, kont, o) => { … } });

import type { BeagyazasAdat, BeagyazasTipus } from '../../lib/vault/linkek.svelte';
import type { LinkAdat } from '../linkek/adat';

/** A beágyazás-lánc egy eleme (a körkörös beágyazás védelméhez). */
export interface LancElem {
  ut: string;
  alcel: string | null;
}

export interface BeagyazasOpciok {
  /** a beágyazást tartalmazó jegyzet útja (a feloldás alapja) */
  forras: string;
  lanc?: LancElem[];
  melyseg?: number;
  /** lebegő előnézet: korlátozott méret, fejléc nélkül */
  kompakt?: boolean;
  /** sor közepén álló beágyazás: a jegyzet helyett csak link-chip (a kép és a videó marad) */
  sorban?: boolean;
  jel?: AbortSignal;
  /** a tartalom megérkezett (a méret változhatott: a CodeMirror új mérést kér) */
  kesz?: () => void;
  /** korlátos kérés-sor a tartalom lekérésére (C33, T184: a canvas jegyzetkártyái legfeljebb 6 egyidejű kéréssel) */
  sor?: { futtat<T>(f: () => Promise<T>, jel?: AbortSignal): Promise<T> };
}

export interface BeagyazasRenderelo {
  tipus: BeagyazasTipus;
  /** A `kont` elembe rajzol; a hibát a hívó mutatja. */
  render(adat: BeagyazasAdat, link: LinkAdat, kont: HTMLElement, o: BeagyazasOpciok): void | Promise<void>;
}

/** Egy jegyzet-osztály beágyazásának saját megjelenítője (C22a): a kísérőjegyzet (kvíz, később a kártyapakli) a jegyzet szövege
 *  helyett interaktív blokk. Csak az egész jegyzet beágyazására (nincs `#fejezet`/`#^blokk`) és nem lebegő előnézetben hat. */
export interface JegyzetOsztalyRenderelo {
  /** az azonosítója (a kettős regisztráció ellen) */
  id: string;
  /** igaz, ha a beágyazott jegyzetet ez a renderelő rajzolja */
  illeszkedik(adat: BeagyazasAdat, link: LinkAdat): boolean;
  render(adat: BeagyazasAdat, link: LinkAdat, kont: HTMLElement, o: BeagyazasOpciok): void | Promise<void>;
}

class JegyzetOsztalyRegiszter {
  private readonly lista: JegyzetOsztalyRenderelo[] = [];

  regisztral(r: JegyzetOsztalyRenderelo): () => void {
    if (this.lista.some((x) => x.id === r.id)) throw new Error(`már regisztrált jegyzet-osztály renderelő: ${r.id}`);
    this.lista.push(r);
    return () => {
      const i = this.lista.indexOf(r);
      if (i >= 0) this.lista.splice(i, 1);
    };
  }

  keres(adat: BeagyazasAdat, link: LinkAdat): JegyzetOsztalyRenderelo | undefined {
    return this.lista.find((r) => r.illeszkedik(adat, link));
  }
}

export const jegyzetOsztalyRenderelok = new JegyzetOsztalyRegiszter();

class Regiszter {
  private readonly lista = new Map<BeagyazasTipus, BeagyazasRenderelo>();

  regisztral(r: BeagyazasRenderelo): () => void {
    if (this.lista.has(r.tipus)) throw new Error(`már regisztrált beágyazás-renderelő: ${r.tipus}`);
    this.lista.set(r.tipus, r);
    return () => {
      if (this.lista.get(r.tipus) === r) this.lista.delete(r.tipus);
    };
  }

  keres(tipus: BeagyazasTipus): BeagyazasRenderelo | undefined {
    return this.lista.get(tipus);
  }
}

export const beagyazasRenderelok = new Regiszter();
