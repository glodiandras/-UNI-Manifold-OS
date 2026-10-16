// A vizuális táblázatszerkesztő (C09): Live Preview-ban a Markdown-táblázat helyén álló widget. A cella
// kattintásra szerkeszthető (a nyers Markdown-forrással, `<input>`-ban), a Tab/Enter/nyilak lépnek; sor- és
// oszlopfogók a húzáshoz és a menühöz (beszúrás, duplikálás, törlés, áthelyezés, igazítás); „+” a jobb és az
// alsó szélen. Minden szerkesztés egyetlen tranzakció, amely a táblázatot újraigazítva írja vissza (a
// modell: `modell.ts`), így a ⌘Z egy lépést von vissza, és a fájl végig érvényes Markdown.
//
// A widget a táblázat teljes soraiból (az idézet-előtaggal együtt) áll, a modellt a saját szövegéből
// olvassa be; a dokumentum helyét a `posAtDOM` adja, és az írás előtt ellenőrzi, hogy a szöveg még
// ugyanaz-e (egyébként nem ír).

import { t as tx, tk } from '../../../lib/i18n';
import { syntaxTree } from '@codemirror/language';
import { EditorState, type Extension, Prec, Transaction } from '@codemirror/state';
import { EditorView, WidgetType } from '@codemirror/view';
import type { SyntaxNode } from '@lezer/common';
import { ikonElem } from '../../../lib/ikon/ikonElem';
import {
  AlignCenter,
  AlignLeft,
  AlignRight,
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  CopyPlus,
  GripVertical,
  Plus,
  Trash2,
} from '../../../lib/ikon/ikonok';
import { tablaRenderel } from '../../olvaso/html';
import { LustaRajzolo } from '../../olvaso/lusta';
import { fokuszBevalt, fokuszKer } from '../fokusz';
import { lebegoMenu, type MenuElem } from '../menu';
import {
  type Igazitas,
  oszlopBeszur,
  oszlopDuplikal,
  oszlopIgazit,
  oszlopMozgat,
  oszlopSzam,
  oszlopTorol,
  sorBeszur,
  sorDuplikal,
  sorMozgat,
  sorTorol,
  cellaIr,
  szerializal,
  type Tabla,
  tablaForrasbol,
} from './modell';

type Elemzes = NonNullable<ReturnType<typeof tablaForrasbol>>;

const elemzesek = new Map<string, Elemzes | null>();

/** A táblázat sorainak elemzése (a widget és a döntés is használja; egy kis gyorsítótárral). */
function elemez(forras: string): Elemzes | null {
  if (elemzesek.has(forras)) return elemzesek.get(forras)!;
  const e = tablaForrasbol(forras);
  if (elemzesek.size > 1000) elemzesek.delete(elemzesek.keys().next().value as string);
  elemzesek.set(forras, e);
  return e;
}

const nezetek = new WeakMap<HTMLElement, TablaNezet>();
const KUSZOB = 4;

const LEIRAS: Record<string, string> = { '': tk('Nincs|igazitas'), bal: tk('Balra|igazitas'), kozep: tk('Középre|igazitas'), jobb: tk('Jobbra|igazitas') };

class TablaNezet {
  readonly dom = document.createElement('div');
  private readonly wrap = document.createElement('div');
  private readonly vonal = document.createElement('div');
  private readonly tabla: Tabla;
  private szerk: { sor: number; oszlop: number; input: HTMLInputElement; regi: Node[]; cella: HTMLElement } | null = null;
  private huzas: { fajta: 'sor' | 'oszlop'; index: number; x0: number; y0: number; megkezdve: boolean; cel: number } | null = null;

  constructor(
    private readonly view: EditorView,
    private readonly forras: string,
    private readonly csakOlvashato: boolean,
    e: Elemzes,
  ) {
    this.tabla = e.tabla;
    const d = this.dom;
    d.className = 'cm-tablazat nt-tabla';
    d.classList.toggle('csak-olvashato', csakOlvashato);
    nezetek.set(d, this);
    this.wrap.className = 'nt-tabla-wrap';
    this.vonal.className = 'nt-tabla-vonal';
    this.vonal.hidden = true;
    d.appendChild(this.wrap);
    const t = tablaRenderel(e.node, { olvas: e.olvas, ut: null, lusta: LustaRajzolo.azonnali() });
    this.wrap.appendChild(t);
    this.cellak(t);
    if (!csakOlvashato) this.vezerlok();
    this.wrap.appendChild(this.vonal);
    requestAnimationFrame(() => {
      try {
        const f = fokuszBevalt(view, view.posAtDOM(d));
        if (f) this.szerkeszt(f.sor, f.oszlop, 'mind');
      } catch {
        /* a widget közben megszűnt */
      }
    });
  }

  private cella(sor: number, oszlop: number): HTMLElement | null {
    return this.dom.querySelector<HTMLElement>(`[data-sor="${sor}"][data-oszlop="${oszlop}"]`);
  }

  private cellak(t: HTMLTableElement): void {
    [...t.rows].forEach((tr, s) => {
      [...tr.cells].forEach((td, o) => {
        td.dataset.sor = String(s);
        td.dataset.oszlop = String(o);
        if (this.csakOlvashato) return;
        td.tabIndex = 0;
        td.addEventListener('mousedown', (ev) => {
          // szerkesztett cellából másik cellára (F2, C10.7): a fókusz ne menjen el — a WebKit a szerkesztő
          // gyökerének adná, a blur lezárna, a widget újraépülne, és a kattintás célja megszűnne
          if (ev.button !== 0 || !this.szerk || this.szerk.cella === td || (ev.target as HTMLElement).closest('.nt-fogo-sav')) return;
          ev.preventDefault();
          this.szerkeszt(s, o);
        });
        td.addEventListener('click', (ev) => {
          if (!this.dom.isConnected || (ev.target as HTMLElement).closest('.nt-fogo-sav')) return;
          this.szerkeszt(s, o);
        });
        td.addEventListener('keydown', (ev) => this.cellaBillentyu(ev, s, o));
      });
    });
  }

  // ------------------------------------------------------------ vezérlők: fogók és „+”

  private vezerlok(): void {
    const t = this.tabla;
    const oszlopok = oszlopSzam(t);
    for (let o = 0; o < oszlopok; o++) {
      const td = this.cella(0, o);
      if (!td) continue;
      td.appendChild(this.fogo('oszlop', o, tx('{n}. oszlop: húzás vagy menü', { n: o + 1 })));
    }
    for (let s = 1; s < t.sorok.length; s++) {
      const td = this.cella(s, 0);
      if (td) td.appendChild(this.fogo('sor', s, tx('{n}. sor: húzás vagy menü', { n: s })));
    }
    const plusO = this.plusz(tx('Oszlop hozzáadása'), 'nt-plusz-oszlop', () => this.alkalmaz(oszlopBeszur(t, oszlopok), { sor: 0, oszlop: oszlopok }));
    const plusS = this.plusz(tx('Sor hozzáadása'), 'nt-plusz-sor', () => this.alkalmaz(sorBeszur(t, t.sorok.length), { sor: t.sorok.length, oszlop: 0 }));
    this.wrap.append(plusO, plusS);
  }

  private plusz(cimke: string, osztaly: string, fut: () => void): HTMLButtonElement {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = `nt-plusz ${osztaly}`;
    b.title = cimke;
    b.setAttribute('aria-label', cimke);
    b.appendChild(ikonElem(Plus, 14));
    b.addEventListener('mousedown', (e) => e.preventDefault());
    b.addEventListener('click', fut);
    return b;
  }

  private fogo(fajta: 'sor' | 'oszlop', index: number, cimke: string): HTMLElement {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = `nt-fogo-sav nt-${fajta}-fogo`;
    b.title = tx('Húzás: áthelyezés · kattintás: menü');
    b.setAttribute('aria-label', cimke);
    b.tabIndex = -1;
    b.appendChild(ikonElem(GripVertical, 14));
    b.addEventListener('pointerdown', (e) => {
      if (e.button !== 0) return;
      e.preventDefault();
      e.stopPropagation();
      b.setPointerCapture?.(e.pointerId);
      this.huzas = { fajta, index, x0: e.clientX, y0: e.clientY, megkezdve: false, cel: -1 };
    });
    b.addEventListener('pointermove', (e) => this.huz(e));
    b.addEventListener('pointerup', (e) => {
      if (b.hasPointerCapture?.(e.pointerId)) b.releasePointerCapture(e.pointerId);
      this.felenged(b);
    });
    b.addEventListener('pointercancel', () => this.huzasVege());
    b.addEventListener('click', (e) => e.stopPropagation());
    b.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        this.menu(fajta, index, b);
      } else if (e.key === 'Escape') this.view.focus();
    });
    return b;
  }

  // ------------------------------------------------------------ húzás

  /** A rendezhető sorok/oszlopok határai (képernyő-koordináta): az i. elem előtti és az utolsó utáni. */
  private hatarok(fajta: 'sor' | 'oszlop'): { poz: number[]; kezd: number } {
    if (fajta === 'sor') {
      const sorok = [...this.dom.querySelectorAll<HTMLElement>('tr')];
      const poz: number[] = [];
      for (let i = 1; i < sorok.length; i++) poz.push(sorok[i].getBoundingClientRect().top);
      poz.push(sorok[sorok.length - 1].getBoundingClientRect().bottom);
      return { poz, kezd: 1 };
    }
    const fej = [...this.dom.querySelectorAll<HTMLElement>('tr:first-child > *')];
    const poz = fej.map((c) => c.getBoundingClientRect().left);
    poz.push(fej[fej.length - 1].getBoundingClientRect().right);
    return { poz, kezd: 0 };
  }

  private huz(e: PointerEvent): void {
    const h = this.huzas;
    if (!h) return;
    if (!h.megkezdve) {
      if (Math.hypot(e.clientX - h.x0, e.clientY - h.y0) < KUSZOB) return;
      h.megkezdve = true;
      this.dom.classList.add('huz');
    }
    const { poz, kezd } = this.hatarok(h.fajta);
    const x = h.fajta === 'sor' ? e.clientY : e.clientX;
    let legjobb = 0;
    poz.forEach((p, i) => {
      if (Math.abs(p - x) < Math.abs(poz[legjobb] - x)) legjobb = i;
    });
    h.cel = kezd + legjobb;
    const wrap = this.wrap.getBoundingClientRect();
    this.vonal.hidden = false;
    this.vonal.dataset.fajta = h.fajta;
    if (h.fajta === 'sor') {
      this.vonal.style.top = `${poz[legjobb] - wrap.top - 1}px`;
      this.vonal.style.left = '0';
      this.vonal.style.width = `${this.dom.querySelector('table')!.getBoundingClientRect().width}px`;
      this.vonal.style.height = '';
      this.vonal.style.left = '0';
    } else {
      this.vonal.style.left = `${poz[legjobb] - wrap.left - 1}px`;
      this.vonal.style.top = '0';
      this.vonal.style.height = `${this.dom.querySelector('table')!.getBoundingClientRect().height}px`;
      this.vonal.style.width = '';
    }
  }

  private huzasVege(): void {
    this.huzas = null;
    this.vonal.hidden = true;
    this.dom.classList.remove('huz');
  }

  private felenged(gomb: HTMLElement): void {
    const h = this.huzas;
    this.huzasVege();
    if (!h) return;
    if (!h.megkezdve) {
      this.menu(h.fajta, h.index, gomb);
      return;
    }
    const t = this.tabla;
    const uj = h.fajta === 'sor' ? sorMozgat(t, h.index, h.cel) : oszlopMozgat(t, h.index, h.cel);
    if (uj !== t) this.alkalmaz(uj);
  }

  // ------------------------------------------------------------ menük

  private menu(fajta: 'sor' | 'oszlop', index: number, gomb: HTMLElement): void {
    const t = this.tabla;
    const akciok = new Map<string, () => void>();
    const el = (id: string, nev: string, ikon: MenuElem['ikon'], fut: () => void, tobb: Partial<MenuElem> = {}): MenuElem => {
      akciok.set(id, fut);
      return { id, nev, ikon, ...tobb };
    };
    const elemek: MenuElem[] = [];
    if (fajta === 'sor') {
      elemek.push(
        el('fole', tx('Beszúrás fölé'), ArrowUp, () => this.alkalmaz(sorBeszur(t, index), { sor: index, oszlop: 0 })),
        el('alae', tx('Beszúrás alá'), ArrowDown, () => this.alkalmaz(sorBeszur(t, index + 1), { sor: index + 1, oszlop: 0 })),
        el('dup', tx('Duplikálás'), CopyPlus, () => this.alkalmaz(sorDuplikal(t, index))),
        el('fel', tx('Mozgatás fel'), ArrowUp, () => this.alkalmaz(sorMozgat(t, index, index - 1)), { letiltva: index <= 1 }),
        el('le', tx('Mozgatás le'), ArrowDown, () => this.alkalmaz(sorMozgat(t, index, index + 2)), { letiltva: index >= t.sorok.length - 1 }),
        el('torol', tx('Sor törlése'), Trash2, () => this.alkalmaz(sorTorol(t, index)), { veszely: true }),
      );
    } else {
      const igazitas = ([ ['', tx('Nincs|igazitas'), AlignLeft], ['bal', tx('Balra|igazitas'), AlignLeft], ['kozep', tx('Középre|igazitas'), AlignCenter], ['jobb', tx('Jobbra|igazitas'), AlignRight] ] as const).map(
        ([ig, nev, ikon]) =>
          el(`ig-${ig || 'nincs'}`, nev, ikon, () => this.alkalmaz(oszlopIgazit(t, index, ig as Igazitas)), { kijelolt: t.igazitas[index] === ig }),
      );
      elemek.push(
        el('balra', tx('Beszúrás balra'), ArrowLeft, () => this.alkalmaz(oszlopBeszur(t, index), { sor: 0, oszlop: index })),
        el('jobbra', tx('Beszúrás jobbra'), ArrowRight, () => this.alkalmaz(oszlopBeszur(t, index + 1), { sor: 0, oszlop: index + 1 })),
        { id: 'igazitas', nev: tx('Igazítás'), ikon: AlignLeft, jelzo: tx(LEIRAS[t.igazitas[index]]), almenu: () => igazitas },
        el('dup', tx('Duplikálás'), CopyPlus, () => this.alkalmaz(oszlopDuplikal(t, index))),
        el('bal', tx('Mozgatás balra'), ArrowLeft, () => this.alkalmaz(oszlopMozgat(t, index, index - 1)), { letiltva: index <= 0 }),
        el('jobb', tx('Mozgatás jobbra'), ArrowRight, () => this.alkalmaz(oszlopMozgat(t, index, index + 2)), { letiltva: index >= oszlopSzam(t) - 1 }),
        el('torol', tx('Oszlop törlése'), Trash2, () => this.alkalmaz(oszlopTorol(t, index)), { veszely: true, letiltva: oszlopSzam(t) <= 1 }),
      );
    }
    const r = gomb.getBoundingClientRect();
    lebegoMenu(
      { focus: () => this.fokuszCellara(fajta === 'sor' ? index : 0, fajta === 'sor' ? 0 : index) },
      r.left,
      r.bottom + 4,
      elemek,
      akciok,
      fajta === 'sor' ? tx('Sor|menu') : tx('Oszlop|menu'),
    );
  }

  private fokuszCellara(sor: number, oszlop: number): void {
    this.cella(sor, oszlop)?.focus();
  }

  // ------------------------------------------------------------ szerkesztés

  private cellaBillentyu(e: KeyboardEvent, s: number, o: number): void {
    if (e.target !== e.currentTarget || e.isComposing) return;
    const t = this.tabla;
    if (e.key === 'Enter' || e.key === 'F2') {
      e.preventDefault();
      this.szerkeszt(s, o, 'vege');
    } else if (e.key === 'Escape') {
      e.preventDefault();
      this.kilep(1);
    } else if (e.key.startsWith('Arrow')) {
      e.preventDefault();
      const ds = e.key === 'ArrowDown' ? 1 : e.key === 'ArrowUp' ? -1 : 0;
      const dO = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
      const ns = s + ds;
      const no = o + dO;
      if (ns < 0) this.kilep(-1);
      else if (ns >= t.sorok.length) this.kilep(1);
      else if (no >= 0 && no < oszlopSzam(t)) this.fokuszCellara(ns, no);
    } else if (e.key.length === 1 && !e.metaKey && !e.ctrlKey && !e.altKey) {
      // a begépelt karakter a cella tartalmát váltja
      e.preventDefault();
      this.szerkeszt(s, o, 'mind');
      if (this.szerk) this.szerk.input.value = e.key;
    }
  }

  /** Kilépés a táblázatból a szerkesztőbe: a kurzor a táblázat elé (-1) vagy mögé (1) kerül. */
  private kilep(irany: -1 | 1): void {
    let from: number;
    try {
      from = this.view.posAtDOM(this.dom);
    } catch {
      return;
    }
    const to = from + this.forras.length;
    const doc = this.view.state.doc;
    const poz = irany < 0 ? Math.max(0, from - 1) : Math.min(doc.length, to + 1);
    this.view.dispatch({ selection: { anchor: poz }, scrollIntoView: true });
    this.view.focus();
  }

  szerkeszt(sor: number, oszlop: number, kijeloles: 'vege' | 'mind' = 'vege'): void {
    if (this.csakOlvashato) return;
    if (this.szerk && this.szerk.sor === sor && this.szerk.oszlop === oszlop) return;
    // ha a lezárás írt, a widget újraépül: a célcellát az új widget nyitja (`fokuszKer`)
    if (this.lezar(true, { sor, oszlop })) return;
    const td = this.cella(sor, oszlop);
    if (!td) return;
    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'nt-cella-mezo';
    input.value = this.tabla.sorok[sor][oszlop] ?? '';
    input.spellcheck = true;
    input.setAttribute('lang', this.view.contentDOM.lang);
    input.setAttribute('aria-label', sor === 0 ? tx('Fejléc, {o}. oszlop', { o: oszlop + 1 }) : tx('{s}. sor, {o}. oszlop', { s: sor, o: oszlop + 1 }));
    const fogok = [...td.querySelectorAll(':scope > .nt-fogo-sav')];
    const regi = [...td.childNodes].filter((n) => !fogok.includes(n as Element));
    for (const n of regi) td.removeChild(n);
    td.insertBefore(input, td.firstChild);
    td.classList.add('szerkesztes');
    this.szerk = { sor, oszlop, input, regi, cella: td };
    input.addEventListener('keydown', (e) => this.mezoBillentyu(e));
    input.addEventListener('blur', () => {
      // a következő cellára lépés maga kezeli; itt csak a kilépés a táblázatból zár
      if (this.szerk?.input === input) setTimeout(() => this.szerk?.input === input && !this.dom.contains(document.activeElement) && this.lezar(true));
    });
    input.focus();
    if (kijeloles === 'mind') input.select();
    else input.setSelectionRange(input.value.length, input.value.length);
  }

  /** A szerkesztett cella lezárása: ha változott, a tranzakció írja; különben a régi tartalom visszakerül. */
  private lezar(ment: boolean, mozgas?: { sor: number; oszlop: number }): boolean {
    const sz = this.szerk;
    if (!sz) return false;
    this.szerk = null;
    const uj = sz.input.value.trim();
    const regi = this.tabla.sorok[sz.sor][sz.oszlop] ?? '';
    const ujTabla = cellaIr(this.tabla, sz.sor, sz.oszlop, uj);
    // a védett alak dönt (a `a|b` és a `a\|b` ugyanaz a cella): változatlan cellánál nincs írás
    if (ment && ujTabla.sorok[sz.sor][sz.oszlop] !== regi && this.alkalmaz(ujTabla, mozgas)) return true;
    sz.input.remove();
    sz.cella.classList.remove('szerkesztes');
    for (const n of [...sz.regi].reverse()) sz.cella.insertBefore(n, sz.cella.firstChild);
    return false;
  }

  private mezoBillentyu(e: KeyboardEvent): void {
    const sz = this.szerk;
    if (!sz || e.isComposing) return;
    const t = this.tabla;
    const { sor, oszlop, input } = sz;
    const oszlopok = oszlopSzam(t);
    const mozog = (s: number, o: number): void => {
      e.preventDefault();
      if (s < 0) {
        this.lezar(true);
        this.kilep(-1);
        return;
      }
      if (s >= t.sorok.length) {
        // az utolsó sor alatt új sor jön, ha volt mit lezárni vagy Enter/Tab kérte
        const uj = sorBeszur(cellaIrHaKell(t, sor, oszlop, input.value), t.sorok.length);
        this.szerk = null;
        this.alkalmaz(uj, { sor: s, oszlop: o });
        return;
      }
      if (!this.lezar(true, { sor: s, oszlop: o })) this.szerkeszt(s, o, 'mind');
    };
    switch (e.key) {
      case 'Enter':
        mozog(sor + 1, oszlop);
        break;
      case 'Tab': {
        let s = sor;
        let o = oszlop + (e.shiftKey ? -1 : 1);
        if (o >= oszlopok) {
          o = 0;
          s++;
        } else if (o < 0) {
          o = oszlopok - 1;
          s--;
        }
        if (s < 0) {
          e.preventDefault();
          this.lezar(true);
          this.kilep(-1);
        } else mozog(s, o);
        break;
      }
      case 'Escape':
        e.preventDefault();
        e.stopPropagation();
        this.lezar(false);
        this.cella(sor, oszlop)?.focus();
        break;
      case 'ArrowUp':
        mozog(sor - 1, oszlop);
        break;
      case 'ArrowDown':
        if (sor + 1 >= t.sorok.length) {
          e.preventDefault();
          this.lezar(true);
          this.kilep(1);
        } else mozog(sor + 1, oszlop);
        break;
      case 'ArrowLeft':
        if (input.selectionStart === 0 && input.selectionEnd === 0 && !e.shiftKey && (oszlop > 0 || sor > 0))
          mozog(oszlop > 0 ? sor : sor - 1, oszlop > 0 ? oszlop - 1 : oszlopok - 1);
        break;
      case 'ArrowRight':
        if (input.selectionStart === input.value.length && input.selectionEnd === input.value.length && !e.shiftKey && (oszlop < oszlopok - 1 || sor < t.sorok.length - 1))
          mozog(oszlop < oszlopok - 1 ? sor : sor + 1, oszlop < oszlopok - 1 ? oszlop + 1 : 0);
        break;
    }
  }

  // ------------------------------------------------------------ írás

  /** A modell új változatának visszaírása a dokumentumba (egy tranzakció). A `fokusz` az új táblázat
   *  cellája, amelyre a szerkesztés után állni kell. Hamis, ha nem írt (a widget közben megszűnt, vagy a
   *  szöveg megváltozott). */
  private alkalmaz(uj: Tabla, fokusz?: { sor: number; oszlop: number }): boolean {
    const view = this.view;
    let from: number;
    try {
      from = view.posAtDOM(this.dom);
    } catch {
      return false;
    }
    const to = from + this.forras.length;
    if (view.state.sliceDoc(from, to) !== this.forras) return false; // közben megváltozott
    const insert = szerializal(uj).join(view.state.lineBreak);
    if (insert === this.forras) {
      if (fokusz) this.szerkeszt(fokusz.sor, fokusz.oszlop, 'mind');
      return true;
    }
    if (fokusz) fokuszKer(view, from, fokusz.sor, fokusz.oszlop);
    view.dispatch({ changes: { from, to, insert }, userEvent: 'input.tablazat' });
    return true;
  }

  destroy(): void {
    nezetek.delete(this.dom);
    this.szerk = null;
  }
}

function cellaIrHaKell(t: Tabla, sor: number, oszlop: number, ertek: string): Tabla {
  const uj = ertek.trim();
  return uj === (t.sorok[sor][oszlop] ?? '') ? t : cellaIr(t, sor, oszlop, uj);
}

// ---------------------------------------------------------------------- a widget

export class TablaSzerkesztoWidget extends WidgetType {
  private constructor(
    readonly forras: string,
    readonly csakOlvashato: boolean,
    private readonly elemzes: Elemzes,
  ) {
    super();
  }

  /** A widget a táblázat soraihoz; null, ha a sorok önállóan nem elemezhetők táblázatként (pl. listaelembe
   *  ágyazott táblázat) — olyankor az olvasható widget marad. */
  static keszit(forras: string, csakOlvashato: boolean): TablaSzerkesztoWidget | null {
    const e = elemez(forras);
    return e ? new TablaSzerkesztoWidget(forras, csakOlvashato, e) : null;
  }

  eq(m: TablaSzerkesztoWidget): boolean {
    return m.forras === this.forras && m.csakOlvashato === this.csakOlvashato;
  }

  toDOM(view: EditorView): HTMLElement {
    return new TablaNezet(view, this.forras, this.csakOlvashato, this.elemzes).dom;
  }

  destroy(dom: HTMLElement): void {
    nezetek.get(dom)?.destroy();
  }

  get estimatedHeight(): number {
    return 34 * (this.forras.split('\n').length - 1) + 16;
  }

  ignoreEvent(): boolean {
    return true;
  }
}

// ---------------------------------------------------------------------- a szerkesztőből a táblázatba

/** A `sor` (1-alapú) sorát tartalmazó táblázat sorainak tartománya, ha táblázat. */
export function tablaSorban(state: EditorState, sor: number): { from: number; to: number } | null {
  const l = state.doc.line(sor);
  const fa = syntaxTree(state);
  for (let n: SyntaxNode | null = fa.resolveInner(l.to, -1); n; n = n.parent) {
    if (n.name === 'Table') return { from: state.doc.lineAt(n.from).from, to: state.doc.lineAt(n.to).to };
  }
  return null;
}

/** A táblázat egy cellájára állítja a fókuszt (a már felépített widgeten). */
export function tablaFokusz(view: EditorView, from: number, sor: number, oszlop: number, szerkeszt = false): boolean {
  for (const el of view.contentDOM.querySelectorAll<HTMLElement>('.nt-tabla')) {
    let p: number;
    try {
      p = view.posAtDOM(el);
    } catch {
      continue;
    }
    if (p !== from) continue;
    const n = nezetek.get(el);
    if (!n) return false;
    if (szerkeszt) n.szerkeszt(sor, oszlop, 'mind');
    else el.querySelector<HTMLElement>(`[data-sor="${sor}"][data-oszlop="${oszlop}"]`)?.focus();
    return true;
  }
  return false;
}

/** Nyilak és Backspace/Delete a táblázat szélén: a kurzor a táblázat első/utolsó cellájára lép (a táblázat
 *  a szerkesztőben egyetlen egység, a kurzor nem megy át rajta), és a szomszéd sor szövege nem folyik bele a
 *  táblázat sorába. */
export const tablaBillentyuk: Extension = Prec.high(
  EditorView.domEventHandlers({
    keydown(e, view) {
      if (e.isComposing || e.altKey || e.metaKey || e.ctrlKey || e.shiftKey) return false;
      const r = view.state.selection.main;
      if (!r.empty) return false;
      const doc = view.state.doc;
      const sor = doc.lineAt(r.head);
      const utolsoSor = (t: { from: number; to: number }) => Math.max(0, doc.lineAt(t.to).number - doc.lineAt(t.from).number - 1);
      const kovetkezo = () => {
        if (r.head !== sor.to || sor.number >= doc.lines) return null;
        const t = tablaSorban(view.state, sor.number + 1);
        return t && t.from === doc.line(sor.number + 1).from ? t : null;
      };
      const elozo = () => {
        if (r.head !== sor.from || sor.number <= 1) return null;
        const t = tablaSorban(view.state, sor.number - 1);
        return t && doc.lineAt(t.to).number === sor.number - 1 ? t : null;
      };
      if (e.key === 'ArrowDown' || e.key === 'ArrowRight') {
        const t = kovetkezo();
        if (t && tablaFokusz(view, t.from, 0, 0)) {
          e.preventDefault();
          return true;
        }
      } else if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') {
        const t = elozo();
        if (t && tablaFokusz(view, t.from, utolsoSor(t), 0)) {
          e.preventDefault();
          return true;
        }
      } else if (e.key === 'Backspace' && sor.text !== '') {
        const t = elozo();
        if (t) {
          e.preventDefault();
          tablaFokusz(view, t.from, utolsoSor(t), 0);
          return true;
        }
      } else if (e.key === 'Delete' && sor.text !== '') {
        const t = kovetkezo();
        if (t) {
          e.preventDefault();
          tablaFokusz(view, t.from, 0, 0);
          return true;
        }
      }
      return false;
    },
  }),
);

/** A táblázat sorai, ha a táblázat sor elején áll (nem idézetben, nem behúzva): a védelem csak ezekre. */
function sajatTabla(state: EditorState, sor: number): { from: number; to: number } | null {
  const t = tablaSorban(state, sor);
  return t && !/^[\s>]/.test(state.doc.lineAt(t.from).text) ? t : null;
}

/** Gépelés a táblázat mellett (F2, C10.7): ha a kurzor a táblázat szélén (az első sor elején, az utolsó sor
 *  végén) vagy a közvetlenül alatta álló üres sorban marad, a Markdown a begépelt szöveget a táblázatba
 *  olvasná (a fejléc elé fűzve vagy pipe nélküli sorként), és az elválasztó üres sor elveszne. A szöveg
 *  ilyenkor új bekezdésbe kerül, üres sorral a táblázat és a szomszéd blokk felé is; a táblázat bájtra
 *  változatlan, egy tranzakció, egy ⌘Z. Az összetett bevitel (holt billentyű) kimarad: a kompozíció közbeni
 *  átírás széttörné. */
export const tablaVedo: Extension = EditorState.transactionFilter.of((tr) => {
  if (!tr.docChanged || !(tr.isUserEvent('input.type') || tr.isUserEvent('input.paste')) || tr.isUserEvent('input.type.compose'))
    return tr;
  let db = 0;
  let poz = 0;
  let ures = true;
  let szoveg = '';
  tr.changes.iterChanges((a, b, _c, _d, ins) => {
    db++;
    poz = a;
    ures = a === b;
    szoveg = ins.toString();
  });
  if (db !== 1 || !ures || !szoveg || /^[\r\n]/.test(szoveg)) return tr;
  const s = tr.startState;
  const doc = s.doc;
  const nl = s.lineBreak;
  const sor = doc.lineAt(poz);
  const nemUres = (n: number) => n >= 1 && n <= doc.lines && doc.line(n).text.trim() !== '';
  let hova: number;
  let elotte: string;
  let utana: string;
  const itt = sajatTabla(s, sor.number);
  const fent = sor.number > 1 && sor.text.trim() === '' ? sajatTabla(s, sor.number - 1) : null;
  if (itt && poz === itt.to) {
    // az utolsó sor végén: ha alatta üres sor áll, oda; különben két sortöréssel a táblázat mögé
    const kov = sor.number + 1;
    if (kov <= doc.lines && !nemUres(kov)) {
      hova = doc.line(kov).from;
      elotte = nl;
      utana = nemUres(kov + 1) ? nl : '';
    } else {
      hova = poz;
      elotte = nl + nl;
      utana = kov <= doc.lines ? nl : '';
    }
  } else if (fent && doc.lineAt(fent.to).number === sor.number - 1) {
    hova = sor.from;
    elotte = nl;
    utana = nemUres(sor.number + 1) ? nl : '';
  } else if (itt && poz === itt.from) {
    hova = poz;
    elotte = nemUres(sor.number - 1) ? nl : '';
    utana = nl + nl;
  } else return tr;
  return {
    changes: { from: hova, insert: elotte + szoveg + utana },
    selection: { anchor: hova + elotte.length + szoveg.length },
    userEvent: tr.annotation(Transaction.userEvent),
    scrollIntoView: true,
  };
});
