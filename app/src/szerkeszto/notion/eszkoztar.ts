// Lebegő formázó eszköztár (C09): nem üres kijelölés fölött, Live Preview-ban. Félkövér, dőlt, kód, kiemelés,
// link; mind a meglévő váltó körbefogást (`formazas.ts`) használja, a kijelölés megmarad, a gomb „nyomva”
// állapota a körbefogásból jön. Az egérrel húzott kijelölés közben nem jelenik meg, csak az egér elengedése
// után, így nem zavarja a kijelölést. A billentyűs formázás (⌘B, ⌘I, ⌘⇧H, ⌘K) eszköztár nélkül is megy.
//
// A link a Markdown-link `[szöveg](url)`; a wikilink a `[[` kiegészítésé (C10). Az URL-ben a szóköz és a
// zárójelek százalékkal kódolódnak (minden Markdown-megjelenítőben érvényes). A kijelölt link URL-je
// szerkeszthető, a link eltávolítható (a szöveg marad).

import { t, tk } from '../../lib/i18n';
import { ensureSyntaxTree, syntaxTree } from '@codemirror/language';
import { type EditorState, type Extension, StateEffect, StateField } from '@codemirror/state';
import { EditorView, showTooltip, type Tooltip, type TooltipView, ViewPlugin, type ViewUpdate } from '@codemirror/view';
import type { SyntaxNode } from '@lezer/common';
import type { IconNode } from 'lucide';
import { ikonElem } from '../../lib/ikon/ikonElem';
import { Bold, Check, Code, Highlighter, Italic, Link, Unlink, X } from '../../lib/ikon/ikonok';
import { levelBlokk } from '../elo/aktivBlokk';
import { korbefog, korbefogva } from '../formazas';

const KIZART = new Set([
  'FencedCode',
  'CodeBlock',
  'MathBlock',
  'InlineMath',
  'DisplayMath',
  'Frontmatter',
  'Table',
  'HTMLBlock',
  'CommentBlock',
  'Comment',
  'LinkReference',
  'InlineCode',
]);

/** Megjelenhet-e az eszköztár a főkijelölésre: egy blokkon belül áll, és nem kódban, képletben, táblázatban. */
export function eszkoztarEngedett(state: EditorState): boolean {
  const r = state.selection.main;
  if (r.empty || state.readOnly || r.to - r.from > 5000) return false;
  const fa = ensureSyntaxTree(state, r.to, 50) ?? syntaxTree(state);
  const a = levelBlokk(fa.resolveInner(r.from, 1)) ?? levelBlokk(fa.resolveInner(r.from, -1));
  const b = levelBlokk(fa.resolveInner(r.to, -1)) ?? levelBlokk(fa.resolveInner(r.to, 1));
  if (!a || !b || a.from !== b.from) return false;
  for (const pos of [r.from, r.to]) {
    for (let n: SyntaxNode | null = fa.resolveInner(pos, pos === r.from ? 1 : -1); n; n = n.parent) if (KIZART.has(n.name)) return false;
  }
  return true;
}

export interface LinkAdat {
  /** a teljes link `[szöveg](url)` */
  from: number;
  to: number;
  szoveg: string;
  url: string;
  urlFrom: number;
  urlTo: number;
}

/** A főkijelölést tartalmazó Markdown-link (`[szöveg](url)`), ha van. */
export function linkAdat(state: EditorState): LinkAdat | null {
  const r = state.selection.main;
  const fa = ensureSyntaxTree(state, r.to, 50) ?? syntaxTree(state);
  for (let n: SyntaxNode | null = fa.resolveInner(r.from, 1); n; n = n.parent) {
    if (n.name !== 'Link' || n.from > r.from || n.to < r.to) continue;
    const jelek: SyntaxNode[] = [];
    let url: SyntaxNode | null = null;
    for (let c = n.firstChild; c; c = c.nextSibling) {
      if (c.name === 'LinkMark') jelek.push(c);
      else if (c.name === 'URL') url = c;
    }
    if (!url || jelek.length < 2) return null;
    return {
      from: n.from,
      to: n.to,
      szoveg: state.sliceDoc(jelek[0].to, jelek[1].from),
      url: state.sliceDoc(url.from, url.to).replace(/^<|>$/g, ''),
      urlFrom: url.from,
      urlTo: url.to,
    };
  }
  return null;
}

/** Az URL védése: a szóköz és a zárójelek, a `<` `>` kódolva (a Markdown-link célja így érvényes marad). */
export function urlKodol(url: string): string {
  return url.trim().replace(/[ ()<>]/g, (c) => `%${c.charCodeAt(0).toString(16).toUpperCase().padStart(2, '0')}`);
}

function szovegKodol(szoveg: string): string {
  return szoveg.replace(/([[\]])/g, '\\$1');
}

// ---------------------------------------------------------------------- állapot

const eszkoztarMutat = StateEffect.define<boolean>();

const lathato = StateField.define<boolean>({
  create: () => false,
  update(v, tr) {
    for (const e of tr.effects) if (e.is(eszkoztarMutat)) return e.value;
    if (tr.state.selection.main.empty) return false;
    if (tr.isUserEvent('select.pointer')) return false;
    if (tr.selection) return true;
    return v;
  },
});

const peldanyok = new WeakMap<EditorView, Eszkoztar>();

interface GombLeiras {
  jel: string;
  ikon: IconNode;
  cimke: string;
  billentyu?: string;
}

const GOMBOK: GombLeiras[] = [
  { jel: '**', ikon: Bold, cimke: tk('Félkövér'), billentyu: '⌘B' },
  { jel: '*', ikon: Italic, cimke: tk('Dőlt'), billentyu: '⌘I' },
  { jel: '`', ikon: Code, cimke: tk('Kód') },
  { jel: '==', ikon: Highlighter, cimke: tk('Kiemelés'), billentyu: '⌘⇧H' },
];

class Eszkoztar {
  readonly dom = document.createElement('div');
  private readonly gombok: { jel: string; gomb: HTMLButtonElement }[] = [];
  private readonly linkGomb: HTMLButtonElement;
  private readonly sor = document.createElement('div');
  private readonly urlSor = document.createElement('div');
  private readonly urlMezo = document.createElement('input');
  private readonly eltavolit: HTMLButtonElement;

  constructor(private readonly view: EditorView) {
    const d = this.dom;
    d.className = 'nt-eszkoztar';
    d.setAttribute('role', 'toolbar');
    d.setAttribute('aria-label', t('Formázás'));
    d.addEventListener('mousedown', (e) => {
      if ((e.target as HTMLElement).closest('input') === null) e.preventDefault(); // a kijelölés maradjon
    });
    this.sor.className = 'nt-eszk-sor';
    for (const g of GOMBOK) {
      const b = this.gomb(g.ikon, g.billentyu ? `${t(g.cimke)} (${g.billentyu})` : t(g.cimke), t(g.cimke));
      b.addEventListener('click', () => {
        korbefog(this.view, g.jel);
        this.frissit(this.view.state);
      });
      this.gombok.push({ jel: g.jel, gomb: b });
      this.sor.appendChild(b);
    }
    const elv = document.createElement('span');
    elv.className = 'nt-eszk-elvalaszto';
    elv.setAttribute('role', 'separator');
    this.sor.appendChild(elv);
    this.linkGomb = this.gomb(Link, t('Link (⌘K)'), t('Link'));
    this.linkGomb.addEventListener('click', () => this.linkNyit());
    this.sor.appendChild(this.linkGomb);

    this.urlSor.className = 'nt-eszk-sor nt-eszk-url';
    this.urlSor.hidden = true;
    this.urlMezo.type = 'text';
    this.urlMezo.className = 'nt-eszk-mezo';
    this.urlMezo.placeholder = 'https://…';
    this.urlMezo.setAttribute('aria-label', t('A link címe'));
    this.urlMezo.spellcheck = false;
    this.urlMezo.addEventListener('keydown', (e) => {
      if (e.isComposing) return;
      if (e.key === 'Enter') {
        e.preventDefault();
        this.linkAlkalmaz();
      } else if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        this.linkZar();
      }
    });
    const ok = this.gomb(Check, t('Link beállítása'), t('Link beállítása'));
    ok.addEventListener('click', () => this.linkAlkalmaz());
    this.eltavolit = this.gomb(Unlink, t('Link eltávolítása'), t('Link eltávolítása'));
    this.eltavolit.addEventListener('click', () => this.linkEltavolit());
    const meg = this.gomb(X, t('Mégse (esc)'), t('Mégse'));
    meg.addEventListener('click', () => this.linkZar());
    this.urlSor.append(this.urlMezo, ok, this.eltavolit, meg);
    d.append(this.sor, this.urlSor);
  }

  private gomb(ikon: IconNode, cimke: string, aria: string): HTMLButtonElement {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'nt-eszk-gomb';
    b.title = cimke;
    b.setAttribute('aria-label', aria);
    b.appendChild(ikonElem(ikon, 16));
    return b;
  }

  frissit(state: EditorState): void {
    for (const { jel, gomb } of this.gombok) gomb.setAttribute('aria-pressed', String(korbefogva(state, jel)));
    this.linkGomb.setAttribute('aria-pressed', String(!!linkAdat(state)));
  }

  get urlNyitva(): boolean {
    return !this.urlSor.hidden;
  }

  linkNyit(): void {
    const l = linkAdat(this.view.state);
    this.urlMezo.value = l?.url ?? '';
    this.eltavolit.hidden = !l;
    this.sor.hidden = true;
    this.urlSor.hidden = false;
    this.urlMezo.focus();
    this.urlMezo.select();
  }

  private linkZar(): void {
    this.urlSor.hidden = true;
    this.sor.hidden = false;
    this.view.focus();
  }

  private linkAlkalmaz(): void {
    const url = urlKodol(this.urlMezo.value);
    if (!url) {
      this.linkZar();
      return;
    }
    const s = this.view.state;
    const r = s.selection.main;
    const l = linkAdat(s);
    if (l) {
      this.view.dispatch({ changes: { from: l.urlFrom, to: l.urlTo, insert: url }, userEvent: 'input.link' });
    } else {
      const szoveg = szovegKodol(s.sliceDoc(r.from, r.to));
      this.view.dispatch({
        changes: { from: r.from, to: r.to, insert: `[${szoveg}](${url})` },
        selection: { anchor: r.from + 1, head: r.from + 1 + szoveg.length },
        userEvent: 'input.link',
      });
    }
    this.linkZar();
  }

  private linkEltavolit(): void {
    const l = linkAdat(this.view.state);
    if (l) {
      this.view.dispatch({
        changes: { from: l.from, to: l.to, insert: l.szoveg },
        selection: { anchor: l.from, head: l.from + l.szoveg.length },
        userEvent: 'input.link',
      });
    }
    this.linkZar();
  }
}

function letrehoz(view: EditorView): TooltipView {
  const e = new Eszkoztar(view);
  peldanyok.set(view, e);
  e.frissit(view.state);
  return {
    dom: e.dom,
    update: (u: ViewUpdate) => e.frissit(u.state),
    destroy: () => peldanyok.delete(view),
  };
}

const tooltip = showTooltip.compute([lathato, 'selection'], (state): Tooltip | null => {
  if (!state.field(lathato) || !eszkoztarEngedett(state)) return null;
  const r = state.selection.main;
  return { pos: r.from, end: r.to, above: true, strictSide: true, arrow: false, create: letrehoz };
});

/** Az egérgomb elengedése után megjelenik az eszköztár (a húzás közben nem). */
class EgerFigyelo {
  lent = false;
  private readonly fel = () => {
    if (!this.lent) return;
    this.lent = false;
    if (!this.view.state.selection.main.empty) this.view.dispatch({ effects: eszkoztarMutat.of(true) });
  };

  constructor(private readonly view: EditorView) {
    document.addEventListener('mouseup', this.fel, true);
  }

  destroy(): void {
    document.removeEventListener('mouseup', this.fel, true);
  }
}

const egerFigyelo = ViewPlugin.fromClass(EgerFigyelo, {
  eventHandlers: {
    mousedown(this: EgerFigyelo) {
      this.lent = true;
    },
  },
});

/** A link beállítása parancsból (⌘K): kijelöléssel megnyitja az URL-mezőt, kijelölés nélkül `[]()`-t ír. */
export function linkParancs(view: EditorView): boolean {
  if (view.state.readOnly) return false;
  const r = view.state.selection.main;
  if (r.empty) {
    view.dispatch({
      changes: { from: r.head, insert: '[]()' },
      selection: { anchor: r.head + 1 },
      userEvent: 'input.link',
      scrollIntoView: true,
    });
    return true;
  }
  if (!eszkoztarEngedett(view.state)) return false;
  const kesz = () => {
    const e = peldanyok.get(view);
    if (e) e.linkNyit();
    return !!e;
  };
  if (!kesz()) {
    view.dispatch({ effects: eszkoztarMutat.of(true) });
    requestAnimationFrame(kesz);
  }
  return true;
}

/** A lebegő eszköztár a Live Preview-ban. */
export function eszkoztarBovitmeny(): Extension {
  return [lathato, tooltip, egerFigyelo];
}
