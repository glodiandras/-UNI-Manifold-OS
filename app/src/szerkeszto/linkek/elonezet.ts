// Lebegő előnézet (C10): ⌘ (vagy ⌃) nyomva tartva a link fölött megjelenik a cél tartalma — jegyzet, fejezet,
// blokk, kép, PDF-oldal, videó —, ugyanazzal a renderelővel, mint a beágyazás (`beagyazas/rajzol.ts`). Egyetlen
// popover van; ~300 ms után jelenik meg, a popoverre lépve nyitva marad, Esc vagy az egér elhagyása zárja.
// Az Olvasó (`data-cel` elemek) és a szerkesztő (CodeMirror-pozíció → szintaxisfa) ugyanezt a modult használja;
// a billentyűzetes párja a „Link előnézete a kurzornál” parancs (`mutat`).

import { t } from '../../lib/i18n';
import { beagyazasElem } from '../beagyazas/rajzol';
import type { LinkAdat } from './adat';

export interface ElonezetCel {
  link: LinkAdat;
  /** a linket tartalmazó jegyzet útja (a feloldás alapja) */
  forras: string;
  /** a link helye a képernyőn (a popover ehhez igazodik) */
  rect: () => DOMRect;
}

export const ELONEZET_KESLELTETES = 300;
export const ELONEZET_ZARAS = 250;

const kulcs = (c: ElonezetCel) => `${c.forras}\0${c.link.cel}\0${c.link.alcel ?? ''}\0${c.link.from}`;

class LebegoElonezet {
  private pop: HTMLElement | null = null;
  private megjelent: string | null = null;
  private fuggo: ReturnType<typeof setTimeout> | null = null;
  private zaro: ReturnType<typeof setTimeout> | null = null;
  private vezerlo: AbortController | null = null;
  private egerBenn = false;

  get nyitva(): boolean {
    return !!this.pop;
  }

  /** A link fölé ért az egér (vagy elhagyta: `cel = null`). `meta`: a ⌘/⌃ nyomva van. */
  horgonyValt(cel: ElonezetCel | null, meta: boolean): void {
    this.torolFuggo();
    if (!cel) {
      this.zarUtemez();
      return;
    }
    this.torolZaro();
    if (this.megjelent === kulcs(cel)) return;
    if (meta) this.fuggo = setTimeout(() => this.mutat(cel), ELONEZET_KESLELTETES);
  }

  /** A ⌘ elengedése: a még meg nem jelent előnézet elmarad. */
  metaEngedve(): void {
    this.torolFuggo();
  }

  /** Az előnézet azonnal (a parancs és a tesztek). */
  mutat(cel: ElonezetCel): void {
    this.torolFuggo();
    this.torolZaro();
    this.zar();
    const pop = document.createElement('div');
    pop.className = 'link-elonezet';
    pop.setAttribute('role', 'region');
    pop.setAttribute('aria-label', t('Link előnézete'));
    pop.tabIndex = -1;
    this.vezerlo = new AbortController();
    const tartalom = document.createElement('div');
    tartalom.className = 'link-elonezet-tartalom md tipo';
    const elhelyez = () => this.elhelyez(pop, cel.rect());
    tartalom.appendChild(
      beagyazasElem(cel.link, {
        forras: cel.forras,
        kompakt: true,
        lanc: [{ ut: cel.forras, alcel: null }],
        jel: this.vezerlo.signal,
        kesz: elhelyez,
      }),
    );
    pop.appendChild(tartalom);
    pop.addEventListener('mouseenter', () => {
      this.egerBenn = true;
      this.torolZaro();
    });
    pop.addEventListener('mouseleave', () => {
      this.egerBenn = false;
      this.zarUtemez();
    });
    document.body.appendChild(pop);
    this.pop = pop;
    this.megjelent = kulcs(cel);
    elhelyez();
  }

  zar(): void {
    this.torolFuggo();
    this.torolZaro();
    this.vezerlo?.abort();
    this.vezerlo = null;
    this.pop?.remove();
    this.pop = null;
    this.megjelent = null;
    this.egerBenn = false;
  }

  private zarUtemez(): void {
    if (!this.pop || this.zaro) return;
    this.zaro = setTimeout(() => {
      this.zaro = null;
      if (!this.egerBenn) this.zar();
    }, ELONEZET_ZARAS);
  }

  private torolFuggo(): void {
    if (this.fuggo) clearTimeout(this.fuggo);
    this.fuggo = null;
  }

  private torolZaro(): void {
    if (this.zaro) clearTimeout(this.zaro);
    this.zaro = null;
  }

  private elhelyez(pop: HTMLElement, r: DOMRect): void {
    const szel = Math.min(440, window.innerWidth - 16);
    pop.style.width = `${szel}px`;
    const x = Math.max(8, Math.min(r.left, window.innerWidth - szel - 8));
    const mag = pop.offsetHeight || 200;
    const alatt = r.bottom + 6;
    const y = alatt + mag > window.innerHeight - 8 && r.top - mag - 6 > 8 ? r.top - mag - 6 : alatt;
    pop.style.left = `${x}px`;
    pop.style.top = `${Math.max(8, y)}px`;
  }
}

export const elonezet = new LebegoElonezet();

/** Az előnézet bekötése egy gyökérelemre: `azonosit` a céllal visszaad, ha az egér link fölött áll. */
export function elonezetKapcsol(
  gyoker: HTMLElement,
  azonosit: (cel: EventTarget | null, e: MouseEvent) => ElonezetCel | null,
): () => void {
  let akt: ElonezetCel | null = null;
  const mozgas = (e: MouseEvent) => {
    const c = azonosit(e.target, e);
    if ((c ? kulcs(c) : null) !== (akt ? kulcs(akt) : null)) {
      akt = c;
      elonezet.horgonyValt(c, e.metaKey || e.ctrlKey);
    } else if (c && (e.metaKey || e.ctrlKey) && !elonezet.nyitva) elonezet.horgonyValt(c, true);
  };
  const lent = () => {
    akt = null;
    elonezet.horgonyValt(null, false);
  };
  const le = (e: KeyboardEvent) => {
    if (e.key === 'Escape') elonezet.zar();
    else if ((e.key === 'Meta' || e.key === 'Control') && akt) elonezet.horgonyValt(akt, true);
  };
  const fel = (e: KeyboardEvent) => {
    if (e.key === 'Meta' || e.key === 'Control') elonezet.metaEngedve();
  };
  gyoker.addEventListener('mousemove', mozgas);
  gyoker.addEventListener('mouseleave', lent);
  window.addEventListener('keydown', le);
  window.addEventListener('keyup', fel);
  return () => {
    gyoker.removeEventListener('mousemove', mozgas);
    gyoker.removeEventListener('mouseleave', lent);
    window.removeEventListener('keydown', le);
    window.removeEventListener('keyup', fel);
    if (akt) elonezet.zar();
  };
}

/** A DOM-ban álló, `data-cel` attribútumos link (Olvasó, beágyazott tartalom) előnézeti célja. */
export function domCel(t: EventTarget | null): ElonezetCel | null {
  const e = (t as HTMLElement | null)?.closest<HTMLElement>('.wikilink[data-cel]');
  if (!e || e.dataset.forras === undefined) return null;
  return {
    link: { cel: e.dataset.cel ?? '', alcel: e.dataset.alcel ?? null, alias: null, beagyazas: false, from: 0, to: 0 },
    forras: e.dataset.forras,
    rect: () => e.getBoundingClientRect(),
  };
}
