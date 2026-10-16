// A kódblokk-renderelők regisztere: a ```` ```nyelv ```` blokkot a Live Preview és az Olvasó ezzel rajzolja
// ki, ha a nyelvhez renderelő tartozik. A C08 a Mermaidot köti be; a későbbi modulok ugyanígy:
//
//   kodRenderelok.regisztral({ nyelv: 'plot', render: (forras, cel, k) => { … }, becsultMagassag: () => 320 });
//
// (C35: plot, C22: quiz, C23: card, C12: base.) A renderelő a `cel` elembe rajzol, és visszaadhat takarító
// függvényt; a hibát a regiszter a blokkban jeleníti meg (nem tűnik el csendben, és nem értesítés).
//
// Interaktív renderelő (C12, Bases): a blokk saját vezérlőket tartalmaz, ezért a kattintás nem visz a forrásba (a
// forrás a renderelő „Forrás” gombjával nyílik: `RenderKornyezet.blokk.forrasba`), a blokk a kurzornak atomi, és a
// forrás változásakor a DOM helyben frissül (`frissit`), így a görgetés és a fókusz megmarad. A blokk forrását a
// renderelő a befoglaló jegyzet **egyetlen tranzakciójával** írja át (`blokk.csere`).

import { t } from '../../lib/i18n';
import { modulEngedelyezett } from '../../lib/beallitasok/allapot.svelte';
export interface RenderKornyezet {
  /** a jegyzet vault-relatív útja (ha van) */
  ut: string | null;
  /** a dokumentum a sötét témában áll-e (a rajzolat színei) */
  sotet: boolean;
  /** a widget megszűnésekor megszakad (a lassú renderelés ne írjon eltűnt elembe) */
  jel: AbortSignal;
  /** Csak a Live Preview adja, interaktív renderelőnek: a blokk forrásának írása és megnyitása. Az Olvasóban
   *  nincs (a renderelő ott a rögzített forrással dolgozik, a beállítás csak memóriában változik). */
  blokk?: BlokkKapcsolat;
}

export interface BlokkKapcsolat {
  /** a befoglaló jegyzet csak olvasható */
  csakOlvashato: boolean;
  /** A blokk kódjának (a kerítés nélküli szövegnek) cseréje egyetlen tranzakcióban. Hamis, ha a blokk közben
   *  megváltozott (a szövege már nem a renderelő utoljára kapott szövege), vagy a jegyzet csak olvasható. */
  csere(ujForras: string): boolean;
  /** A blokk forrásának megnyitása: a kurzor a blokk elejére kerül, a blokk aktív lesz. */
  forrasba(): void;
}

export type Takarito = () => void;

export interface KodRenderelo {
  /** a kódblokk nyelve(i), kisbetűvel */
  nyelv: string | readonly string[];
  render(forras: string, cel: HTMLElement, k: RenderKornyezet): void | Takarito | Promise<void | Takarito>;
  /** becsült magasság px-ben (a Live Preview helyfoglalása a renderelés előtt) */
  becsultMagassag?: (forras: string) => number;
  /** Saját vezérlők vannak a blokkban (lásd fent): a kattintás nem visz a forrásba, a blokk atomi. */
  interaktiv?: boolean;
  /** Az interaktív blokk helyben frissítése új forrással (a widget `updateDOM`-ja hívja). Igaz, ha a `cel` DOM-ja
   *  a helyén maradhat; hamis esetén a widget újrarajzolódik. */
  frissit?(cel: HTMLElement, forras: string): boolean;
}

export class KodRendeloRegiszter {
  private readonly nyelvek = new Map<string, KodRenderelo>();

  regisztral(r: KodRenderelo): () => void {
    const nevek = (typeof r.nyelv === 'string' ? [r.nyelv] : [...r.nyelv]).map((n) => n.toLowerCase());
    for (const n of nevek) if (this.nyelvek.has(n)) throw new Error(`már regisztrált kódblokk-renderelő: ${n}`); // i18n-ignore: programozói hiba
    for (const n of nevek) this.nyelvek.set(n, r);
    return () => {
      for (const n of nevek) if (this.nyelvek.get(n) === r) this.nyelvek.delete(n);
    };
  }

  /** A kódblokk info-sorához tartozó renderelő (az első szó, kisbetűvel). */
  keres(info: string): KodRenderelo | undefined {
    const nyelv = /^\S*/.exec(info.trim())?.[0].toLowerCase() ?? '';
    if (nyelv === 'base' && !modulEngedelyezett('bazis')) return undefined;
    if (nyelv === 'query' && !modulEngedelyezett('kereses')) return undefined; // 08-search-13: a Keresés modul nélkül sima kódblokk
    return nyelv ? this.nyelvek.get(nyelv) : undefined;
  }
}

export const kodRenderelok = new KodRendeloRegiszter();

/** Renderelés hibakezeléssel: a hiba a blokkban, a téma hiba-színével jelenik meg. */
export async function renderel(r: KodRenderelo, forras: string, cel: HTMLElement, k: RenderKornyezet): Promise<Takarito> {
  try {
    const t = await r.render(forras, cel, k);
    return typeof t === 'function' ? t : () => {};
  } catch (e) {
    if (k.jel.aborted) return () => {};
    cel.replaceChildren();
    const h = document.createElement('div');
    h.className = 'renderelo-hiba';
    h.setAttribute('role', 'note');
    h.textContent = t('A blokk nem rajzolható ki: {hiba}', { hiba: e instanceof Error ? e.message : String(e) });
    cel.appendChild(h);
    return () => {};
  }
}
