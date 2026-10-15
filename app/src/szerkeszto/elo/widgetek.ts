// A Live Preview widgetjei. Mindegyiknek van `eq`-ja (a forrásszöveg szerint), így a CodeMirror a DOM-ot
// újrahasznosítja; a blokkszintűeknek `estimatedHeight`-je (a görgetősáv nem ugrik a renderelés előtt).
// A kattintás a forrásba visz (a blokk aktív lesz, a jelölés látszik), kivéve a saját vezérlőket
// (jelölőnégyzet, másolás, callout-összecsukó).

import { syntaxTree } from '@codemirror/language';
import { type EditorView, WidgetType } from '@codemirror/view';
import type { SyntaxNode } from '@lezer/common';
import { ikonElem } from '../../lib/ikon/ikonElem';
import { ChevronRight } from '../../lib/ikon/ikonok';
import { calloutTipusok } from '../renderelok/callout';
import { katexHtml } from '../renderelok/katex';
import { type BlokkKapcsolat, type KodRenderelo, renderel } from '../renderelok/regiszter';
import { sotetTema } from '../renderelok/tema';
import { masolasGomb, tablaRenderel } from '../olvaso/html';
import { LustaRajzolo } from '../olvaso/lusta';
import { calloutHajtasValt } from './hajtas';

const SOR = 26; // a törzs egy sorának magassága px-ben (16 px × 1,6)

/** A widget helyére kattintás: a kurzor a forrásbeli `eltolas`-ra kerül (a widget eleje + eltolás). */
function forrasba(view: EditorView, dom: HTMLElement, eltolas = 0) {
  const kezd = view.posAtDOM(dom);
  view.dispatch({ selection: { anchor: Math.min(kezd + eltolas, view.state.doc.length) }, scrollIntoView: false });
  view.focus();
}

// ---------------------------------------------------------------------- képlet

export class KepletWidget extends WidgetType {
  constructor(
    readonly tex: string,
    readonly display: boolean,
    readonly blokk = false,
  ) {
    super();
  }

  eq(m: KepletWidget) {
    return m.tex === this.tex && m.display === this.display && m.blokk === this.blokk;
  }

  toDOM(view: EditorView) {
    const e: HTMLElement = document.createElement(this.blokk ? 'div' : 'span');
    e.className = this.blokk ? 'cm-keplet-blokk' : this.display ? 'cm-keplet cm-keplet-display' : 'cm-keplet';
    e.innerHTML = katexHtml(this.tex, this.display);
    e.addEventListener('mousedown', (ev) => {
      if (ev.button !== 0) return;
      ev.preventDefault();
      forrasba(view, e);
    });
    return e;
  }

  get estimatedHeight() {
    return this.blokk ? Math.max(48, 30 * this.tex.split('\n').length) : -1;
  }

  ignoreEvent(e: Event) {
    return e.type === 'mousedown';
  }
}

/** A szerkesztett képletblokk alatti élő előnézet. */
export class KepletElonezetWidget extends KepletWidget {
  constructor(tex: string) {
    super(tex, true, true);
  }

  toDOM(view: EditorView) {
    const e = super.toDOM(view);
    e.classList.add('cm-keplet-elonezet');
    e.setAttribute('aria-hidden', 'true');
    return e;
  }

  eq(m: KepletWidget) {
    return m instanceof KepletElonezetWidget && m.tex === this.tex;
  }
}

// ---------------------------------------------------------------------- táblázat

export class TablaWidget extends WidgetType {
  constructor(
    readonly forras: string,
    readonly node: SyntaxNode,
    readonly from: number,
    readonly behuzas: number,
  ) {
    super();
  }

  eq(m: TablaWidget) {
    return m.forras === this.forras && m.behuzas === this.behuzas;
  }

  toDOM(view: EditorView) {
    const kont = document.createElement('div');
    kont.className = 'cm-tablazat';
    if (this.behuzas) kont.style.paddingLeft = `${this.behuzas}ch`;
    const olvas = (a: number, b: number) => this.forras.slice(a - this.from, b - this.from);
    const t = tablaRenderel(this.node, { olvas, ut: null, lusta: LustaRajzolo.azonnali() });
    kont.appendChild(t);
    kont.addEventListener('mousedown', (ev) => {
      if (ev.button !== 0) return;
      ev.preventDefault();
      const cella = (ev.target as HTMLElement).closest<HTMLElement>('[data-from]');
      const eltolas = cella ? Number(cella.dataset.from) - this.from : 0;
      forrasba(view, kont, Math.max(0, eltolas));
    });
    return kont;
  }

  get estimatedHeight() {
    return 34 * (this.forras.split('\n').length - 1) + 16;
  }

  ignoreEvent(e: Event) {
    return e.type === 'mousedown';
  }
}

// ---------------------------------------------------------------------- elválasztó, renderelt kódblokk

export class ElvalasztoWidget extends WidgetType {
  eq() {
    return true;
  }

  toDOM(view: EditorView) {
    const e = document.createElement('div');
    e.className = 'cm-elvalaszto-widget';
    e.appendChild(document.createElement('hr'));
    e.addEventListener('mousedown', (ev) => {
      if (ev.button !== 0) return;
      ev.preventDefault();
      forrasba(view, e);
    });
    return e;
  }

  get estimatedHeight() {
    return SOR;
  }

  ignoreEvent(e: Event) {
    return e.type === 'mousedown';
  }
}

/** Egy kirajzolt renderelt blokk életciklus-állapota. A DOM-hoz kötött (nem a widget-példányhoz): a CodeMirror
 *  `updateDOM`-mal új widget-példányhoz rendelhet egy meglévő DOM-ot, az állapotnak ezt át kell vészelnie. */
interface BlokkAllapot {
  r: KodRenderelo;
  /** a renderelőnek utoljára átadott forrás: a `csere` ennek egyezését ellenőrzi a dokumentumban */
  forras: string;
  megszakito: AbortController;
  takarito: (() => void) | null;
  cel: HTMLElement;
}

const BLOKK_ALLAPOT = new WeakMap<HTMLElement, BlokkAllapot>();

/** A widget helyén álló kódblokk kódjának tartománya: (a CodeText eleje, vége), vagy az üres blokk beszúrási
 *  pontja a nyitó sor után (`ures`: oda a kódot soremeléssel kell beszúrni, hogy a záró kerítés külön sorban maradjon). */
function kodTartomany(view: EditorView, dom: HTMLElement): { from: number; to: number; ures?: true } | null {
  let n: SyntaxNode | null = syntaxTree(view.state).resolveInner(view.posAtDOM(dom), 1);
  while (n && n.name !== 'FencedCode') n = n.parent;
  if (!n) return null;
  let from = -1;
  let to = -1;
  for (let c = n.firstChild; c; c = c.nextSibling)
    if (c.name === 'CodeText') {
      if (from < 0) from = c.from;
      to = c.to;
    }
  if (from >= 0) return { from, to };
  const nyito = view.state.doc.lineAt(n.from);
  return nyito.to + 1 <= view.state.doc.length && n.to > nyito.to ? { from: nyito.to + 1, to: nyito.to + 1, ures: true } : null;
}

export class RendereloWidget extends WidgetType {
  constructor(
    readonly r: KodRenderelo,
    readonly forras: string,
    readonly ut: string | null,
  ) {
    super();
  }

  eq(m: RendereloWidget) {
    return m.r === this.r && m.forras === this.forras;
  }

  toDOM(view: EditorView) {
    const e = document.createElement('div');
    e.className = 'cm-renderelt-blokk';
    const cel = document.createElement('div');
    cel.style.minHeight = `${this.r.becsultMagassag?.(this.forras) ?? 120}px`;
    e.appendChild(cel);
    const allapot: BlokkAllapot = { r: this.r, forras: this.forras, megszakito: new AbortController(), takarito: null, cel };
    BLOKK_ALLAPOT.set(e, allapot);
    const blokk: BlokkKapcsolat | undefined = this.r.interaktiv
      ? {
          get csakOlvashato() {
            return view.state.readOnly;
          },
          csere: (uj) => {
            if (view.state.readOnly || allapot.megszakito.signal.aborted) return false;
            let t: { from: number; to: number; ures?: true } | null;
            try {
              t = kodTartomany(view, e);
            } catch {
              return false; // a widget közben lekerült a dokumentumról
            }
            if (!t || view.state.sliceDoc(t.from, t.to) !== allapot.forras) return false; // a blokk közben megváltozott
            if (uj === allapot.forras) return true;
            view.dispatch({ changes: { from: t.from, to: t.to, insert: t.ures && uj ? `${uj}\n` : uj }, userEvent: 'input.bazis' });
            return true;
          },
          forrasba: () => forrasba(view, e),
        }
      : undefined;
    void renderel(this.r, this.forras, cel, {
      ut: this.ut,
      sotet: sotetTema(),
      jel: allapot.megszakito.signal,
      ...(blokk ? { blokk } : {}),
    }).then((t) => {
      if (allapot.megszakito.signal.aborted) return t(); // a widget a renderelés vége előtt lebomlott: a takarítás most jön
      cel.style.minHeight = '';
      allapot.takarito = t;
      view.requestMeasure();
    });
    if (!this.r.interaktiv)
      e.addEventListener('mousedown', (ev) => {
        if (ev.button !== 0) return;
        ev.preventDefault();
        forrasba(view, e);
      });
    return e;
  }

  /** Interaktív blokknál az új forrás helyben érvényesül (a görgetés, a fókusz és a nézet-állapot megmarad). */
  updateDOM(dom: HTMLElement, view: EditorView) {
    const a = BLOKK_ALLAPOT.get(dom);
    if (!a || a.r !== this.r || !this.r.interaktiv || !this.r.frissit) return false;
    if (!this.r.frissit(a.cel, this.forras)) return false;
    a.forras = this.forras;
    view.requestMeasure();
    return true;
  }

  destroy(dom: HTMLElement) {
    const a = BLOKK_ALLAPOT.get(dom);
    if (!a) return;
    a.megszakito.abort();
    a.takarito?.();
    BLOKK_ALLAPOT.delete(dom);
  }

  get estimatedHeight() {
    return this.r.becsultMagassag?.(this.forras) ?? 120;
  }

  ignoreEvent(e: Event) {
    return this.r.interaktiv ? true : e.type === 'mousedown';
  }
}

// ---------------------------------------------------------------------- sorszintű widgetek

export class JeloloWidget extends WidgetType {
  constructor(
    readonly kesz: boolean,
    readonly jeloloFrom: number,
  ) {
    super();
  }

  eq(m: JeloloWidget) {
    return m.kesz === this.kesz;
  }

  toDOM(view: EditorView) {
    const e = document.createElement('input');
    e.type = 'checkbox';
    e.className = 'cm-feladat-jelolo';
    e.checked = this.kesz;
    e.setAttribute('aria-label', this.kesz ? 'Feladat: nincs kész' : 'Feladat: kész');
    e.addEventListener('mousedown', (ev) => ev.preventDefault());
    e.addEventListener('click', (ev) => {
      ev.preventDefault();
      if (view.state.readOnly) return;
      const pos = view.posAtDOM(e);
      const allapot = view.state.sliceDoc(pos + 1, pos + 2);
      view.dispatch({ changes: { from: pos + 1, to: pos + 2, insert: allapot === ' ' ? 'x' : ' ' }, userEvent: 'input.feladat' });
    });
    return e;
  }

  ignoreEvent() {
    return true;
  }
}

/** A soron belüli `<br>` a Live Preview-ban (C32): valódi sortörés, mint az Olvasóban. */
export class SorToresWidget extends WidgetType {
  eq() {
    return true;
  }

  toDOM() {
    return document.createElement('br');
  }

  ignoreEvent() {
    return false;
  }
}

export class PontWidget extends WidgetType {
  eq() {
    return true;
  }

  toDOM() {
    const e = document.createElement('span');
    e.className = 'cm-lista-pont';
    e.setAttribute('aria-hidden', 'true');
    e.textContent = '•';
    return e;
  }

  ignoreEvent() {
    return false;
  }
}

export class LabjegyzetWidget extends WidgetType {
  constructor(readonly cimke: string) {
    super();
  }

  eq(m: LabjegyzetWidget) {
    return m.cimke === this.cimke;
  }

  toDOM() {
    const e = document.createElement('sup');
    e.className = 'cm-labjegyzet-widget';
    e.textContent = this.cimke;
    return e;
  }

  ignoreEvent() {
    return false;
  }
}

/** A kirajzolt wikilink `#horgony` jele helyett álló elválasztó (` › `). */
export class LinkSzovegWidget extends WidgetType {
  constructor(readonly szoveg: string) {
    super();
  }

  eq(m: LinkSzovegWidget) {
    return m.szoveg === this.szoveg;
  }

  toDOM() {
    const e = document.createElement('span');
    e.className = 'cm-link-elvalaszto';
    e.textContent = this.szoveg;
    return e;
  }

  ignoreEvent() {
    return false;
  }
}

/** A kódblokk nyitó sora helyett: nyelvcímke és másolás gomb. A kódot kattintáskor olvassa ki a jelenlegi
 *  állapotból (a widget helyén álló kódblokkból), így a közben átírt kód is helyesen másolódik. */
export class KodFejWidget extends WidgetType {
  constructor(readonly nyelv: string) {
    super();
  }

  eq(m: KodFejWidget) {
    return m.nyelv === this.nyelv;
  }

  toDOM(view: EditorView) {
    const e = document.createElement('span');
    e.className = 'cm-kodblokk-fej';
    const n = document.createElement('span');
    n.className = 'cm-kodblokk-nyelv';
    n.textContent = this.nyelv;
    e.append(n, masolasGomb(() => kodAHelyen(view, view.posAtDOM(e))));
    return e;
  }

  ignoreEvent(e: Event) {
    return (e.target as HTMLElement).closest('.kod-masol') !== null;
  }
}

function kodAHelyen(view: EditorView, pos: number): string {
  let n: SyntaxNode | null = syntaxTree(view.state).resolveInner(pos, 1);
  while (n && n.name !== 'FencedCode') n = n.parent;
  if (!n) return '';
  let kod = '';
  for (let c = n.firstChild; c; c = c.nextSibling) if (c.name === 'CodeText') kod += view.state.sliceDoc(c.from, c.to);
  return kod;
}

/** A callout összecsukója: a csukott/nyitott állapotot nézet-állapotként váltja (a fájl nem változik). */
function hajtoGomb(view: EditorView, hely: HTMLElement, csukva: boolean): HTMLButtonElement {
  const b = document.createElement('button');
  b.type = 'button';
  b.className = 'callout-hajto' + (csukva ? '' : ' nyitva');
  b.setAttribute('aria-expanded', String(!csukva));
  b.setAttribute('aria-label', csukva ? 'Callout kibontása' : 'Callout összecsukása');
  b.appendChild(ikonElem(ChevronRight, 16));
  b.addEventListener('mousedown', (ev) => ev.preventDefault());
  b.addEventListener('click', (ev) => {
    ev.preventDefault();
    const sor = view.state.doc.lineAt(view.posAtDOM(hely));
    view.dispatch({ effects: calloutHajtasValt.of({ pos: sor.from, csukva: !csukva }) });
  });
  return b;
}

/** A callout fejlécének jele (`[!típus]±`) helyett: ikon és — ha a forrásban nincs cím — az alapcím az
 *  összecsukóval. Ha van cím, az összecsukó a cím után áll (`CalloutHajtoWidget`). */
export class CalloutFejWidget extends WidgetType {
  constructor(
    readonly tipus: string,
    readonly vanCim: boolean,
    readonly hajthato: boolean,
    readonly csukva: boolean,
  ) {
    super();
  }

  eq(m: CalloutFejWidget) {
    return m.tipus === this.tipus && m.vanCim === this.vanCim && m.hajthato === this.hajthato && m.csukva === this.csukva;
  }

  toDOM(view: EditorView) {
    const m = calloutTipusok.megjelenes(this.tipus);
    const e = document.createElement('span');
    e.className = 'cm-callout-jel';
    const ikon = document.createElement('span');
    ikon.className = 'callout-ikon';
    ikon.appendChild(ikonElem(m.ikon, 16));
    e.appendChild(ikon);
    if (!this.vanCim) {
      const c = document.createElement('span');
      c.className = 'callout-cim-szoveg';
      c.textContent = m.cim;
      e.appendChild(c);
      if (this.hajthato) e.appendChild(hajtoGomb(view, e, this.csukva));
    }
    return e;
  }

  ignoreEvent(e: Event) {
    return (e.target as HTMLElement).closest('.callout-hajto') !== null;
  }
}

export class CalloutHajtoWidget extends WidgetType {
  constructor(readonly csukva: boolean) {
    super();
  }

  eq(m: CalloutHajtoWidget) {
    return m.csukva === this.csukva;
  }

  toDOM(view: EditorView) {
    const e = document.createElement('span');
    e.className = 'cm-callout-jel cm-callout-hajto-hely';
    e.appendChild(hajtoGomb(view, e, this.csukva));
    return e;
  }

  ignoreEvent(e: Event) {
    return (e.target as HTMLElement).closest('.callout-hajto') !== null;
  }
}
