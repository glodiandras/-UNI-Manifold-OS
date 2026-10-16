// Címsor- és listaelem-összecsukás (01-rendering-05/06, 05-editing-03) a Live Preview-ban és a Forrás módban; az Olvasó
// ugyanezt az állapotot mutatja (`olvaso/hajtas.ts`). Az összecsukás nézet-állapot: a jegyzet szövegébe soha nem íródik,
// a fül tartós nézet-állapotába (`ful.nezet.hajtott`, a hajtás kezdősorainak száma) kerül, ahogy az Obsidian is a
// munkaterületben tartja.
//
//   címsor (csak a dokumentum felső szintjén) → a sor végétől a következő azonos vagy magasabb szintű címsorig;
//   listaelem, amelynek a további sorokon gyermeke van (beágyazott lista, újabb bekezdés) → az első sor végétől az elem végéig.
// A záró üres sorok nem hajtódnak be (a következő szakasz előtti térköz megmarad). A CodeMirror saját, minden blokkra
// kiterjedő `foldNodeProp`-ját nem használjuk: hajtható csak az, amit ez a modul ad.

import { codeFolding, ensureSyntaxTree, foldEffect, foldedRanges, foldState, syntaxTree, unfoldEffect } from '@codemirror/language';
import type { EditorState, Extension, Range, StateEffect } from '@codemirror/state';
import { Decoration, type DecorationSet, type EditorView, ViewPlugin, type ViewUpdate, WidgetType } from '@codemirror/view';
import type { SyntaxNode, Tree } from '@lezer/common';
import { t } from '../lib/i18n';
import { ikonElem } from '../lib/ikon/ikonElem';
import { ChevronRight } from '../lib/ikon/ikonok';
import './megjelenites.css';

export interface Tartomany {
  from: number;
  to: number;
}

/** A tartós nézet-állapotban legfeljebb ennyi hajtás marad meg (a fül nézet-állapota 2 KB-ba fér, `MAX_NEZET_ALLAPOT`). */
export const MAX_HAJTOTT = 120;

const CIMSOR = /^(?:ATX|Setext)Heading(\d)$/;

const teljesFak = new WeakMap<EditorState, Tree>();

/** A szintaxisfa. Felhasználói műveletnél (`kenyszerit`) állapotonként egyszer, korlátos időben a teljes dokumentumra
 *  kiterjesztjük; a sor eleji jelek kirajzolása soha nem vár az elemzőre (a nagy jegyzet gépelését nem lassítja). */
function fa(state: EditorState, kenyszerit: boolean): Tree {
  const t = syntaxTree(state);
  if (!kenyszerit || t.length >= state.doc.length) return t;
  let k = teljesFak.get(state);
  if (!k) teljesFak.set(state, (k = ensureSyntaxTree(state, state.doc.length, 200) ?? t));
  return k;
}

function cimsorSzint(n: SyntaxNode | null): number | null {
  const m = n ? CIMSOR.exec(n.name) : null;
  return m ? Number(m[1]) : null;
}

/** A tartomány vége a záró üres sorok nélkül; `null`, ha a kezdősor után nem marad tartalom. */
function veg(state: EditorState, sorSzam: number, vegPoz: number): Tartomany | null {
  const doc = state.doc;
  let s = doc.lineAt(Math.max(0, Math.min(vegPoz, doc.length)));
  while (s.number > sorSzam && !s.text.trim()) s = doc.line(s.number - 1);
  if (s.number <= sorSzam) return null;
  return { from: doc.line(sorSzam).to, to: s.to };
}

/** A sorhoz tartozó hajtható tartomány (a sor végétől), vagy `null`. */
export function hajthatoTartomany(state: EditorState, sorKezdet: number, kenyszerit = true): Tartomany | null {
  const doc = state.doc;
  if (sorKezdet < 0 || sorKezdet > doc.length) return null;
  const sor = doc.lineAt(sorKezdet);
  const behuzas = /^[ \t]*/.exec(sor.text)![0].length;
  if (behuzas === sor.length) return null;
  const f = fa(state, kenyszerit);

  // felső szintű címsor
  const felso = f.topNode.childAfter(sor.from);
  const szint = felso && felso.from <= sor.to ? cimsorSzint(felso) : null;
  if (felso && szint !== null && doc.lineAt(felso.from).number === sor.number) {
    let kov = felso.nextSibling;
    while (kov) {
      const k = cimsorSzint(kov);
      if (k !== null && k <= szint) break;
      kov = kov.nextSibling;
    }
    return veg(state, sor.number, kov ? kov.from - 1 : doc.length);
  }

  // listaelem, amelynek a további sorokon gyermeke van (a legkülső, ezen a soron kezdődő elem)
  let elem: SyntaxNode | null = null;
  const elotag = /^(?:[ \t]*>)*[ \t]*/.exec(sor.text)![0].length; // idézetben álló lista
  for (let n: SyntaxNode | null = f.resolveInner(sor.from + elotag, 1); n; n = n.parent)
    if (n.name === 'ListItem' && doc.lineAt(n.from).number === sor.number) elem = n;
  if (!elem) return null;
  let gyermek = false;
  for (let c = elem.firstChild; c && !gyermek; c = c.nextSibling)
    if (c.name !== 'ListMark' && doc.lineAt(c.from).number > sor.number) gyermek = true;
  return gyermek ? veg(state, sor.number, elem.to) : null;
}

/** Az éppen összecsukott tartomány, amely ennek a sornak a végén kezdődik. */
export function hajtottAzonSoron(state: EditorState, sorKezdet: number): Tartomany | null {
  const sor = state.doc.lineAt(sorKezdet);
  let ki: Tartomany | null = null;
  foldedRanges(state).between(sor.to, sor.to, (from, to) => {
    if (from === sor.to) {
      ki = { from, to };
      return false;
    }
  });
  return ki;
}

/** Az összes hajtható tartomány a dokumentum sorrendjében (a beágyazottak is). */
export function osszesHajthato(state: EditorState): Tartomany[] {
  const ki: Tartomany[] = [];
  const doc = state.doc;
  for (let i = 1; i <= doc.lines; i++) {
    const r = hajthatoTartomany(state, doc.line(i).from);
    if (r) ki.push(r);
  }
  return ki;
}

function hajtott(state: EditorState): Tartomany[] {
  const ki: Tartomany[] = [];
  foldedRanges(state).between(0, state.doc.length, (from, to) => {
    ki.push({ from, to });
  });
  return ki.sort((a, b) => a.from - b.from || b.to - a.to);
}

const tartalmaz = (kulso: Tartomany, belso: Tartomany) =>
  kulso.from <= belso.from && belso.to <= kulso.to && (kulso.from !== belso.from || kulso.to !== belso.to);

/** Egy sor összecsukása vagy kibontása (a gomb és a parancs közös útja). */
export function sorHajtasValt(view: EditorView, sorKezdet: number): boolean {
  const mar = hajtottAzonSoron(view.state, sorKezdet);
  if (mar) {
    view.dispatch({ effects: unfoldEffect.of(mar) });
    return true;
  }
  const r = hajthatoTartomany(view.state, sorKezdet);
  if (!r) return false;
  view.dispatch({ effects: foldEffect.of(r) });
  return true;
}

/** „Összecsukás váltása”: a kurzor során, vagy ha az nem hajtható, a kurzort tartalmazó legközelebbi szakaszon / elemen. */
export function hajtasValt(view: EditorView): boolean {
  const state = view.state;
  const doc = state.doc;
  const fej = state.selection.main.head;
  const sor = doc.lineAt(fej);
  if (hajtottAzonSoron(state, sor.from) || hajthatoTartomany(state, sor.from)) return sorHajtasValt(view, sor.from);
  for (let n = sor.number - 1, lepes = 0; n >= 1 && lepes < 5000; n--, lepes++) {
    const r = hajthatoTartomany(state, doc.line(n).from);
    if (r && r.from < fej && fej <= r.to) {
      view.dispatch({ effects: foldEffect.of(r), selection: { anchor: doc.line(n).from + /^[ \t]*/.exec(doc.line(n).text)![0].length } });
      return true;
    }
  }
  return false;
}

/** „Mindet összecsukja”: minden címsor és gyermekes listaelem (a beágyazottak is, így a kibontás után is csukva maradnak). */
export function mindetHajt(view: EditorView): boolean {
  const mar = hajtott(view.state);
  const uj = osszesHajthato(view.state).filter((r) => !mar.some((m) => m.from === r.from && m.to === r.to));
  if (!uj.length) return false;
  const effects: StateEffect<unknown>[] = uj.map((r) => foldEffect.of(r));
  // a kurzor nem maradhat egy összecsukott tartomány belsejében (a CodeMirror akkor azonnal kibontaná)
  const fej = view.state.selection.main.head;
  const kulso = uj.find((r) => r.from < fej && fej < r.to && !uj.some((m) => tartalmaz(m, r)));
  view.dispatch(kulso ? { effects, selection: { anchor: view.state.doc.lineAt(kulso.from).from } } : { effects });
  return true;
}

/** „Mindet kibontja”. */
export function mindetKibont(view: EditorView): boolean {
  const mar = hajtott(view.state);
  if (!mar.length) return false;
  view.dispatch({ effects: mar.map((r) => unfoldEffect.of(r)) });
  return true;
}

/** „Több összecsukása”: a látható (nem csukott tartományban álló), még nyitott hajthatók közül a legbelsőket csukja. */
export function hajtasTobb(view: EditorView): boolean {
  const mar = hajtott(view.state);
  const lathato = osszesHajthato(view.state).filter(
    (r) => !mar.some((m) => (m.from === r.from && m.to === r.to) || (m.from <= r.from && r.to <= m.to)),
  );
  const legbelso = lathato.filter((r) => !lathato.some((m) => tartalmaz(r, m)));
  if (!legbelso.length) return false;
  view.dispatch({ effects: legbelso.map((r) => foldEffect.of(r)) });
  return true;
}

/** „Kevesebb összecsukása”: a csukott tartományok közül a legkülsőket bontja ki. */
export function hajtasKevesebb(view: EditorView): boolean {
  const mar = hajtott(view.state);
  const kulso = mar.filter((r) => !mar.some((m) => tartalmaz(m, r)));
  if (!kulso.length) return false;
  view.dispatch({ effects: kulso.map((r) => unfoldEffect.of(r)) });
  return true;
}

// ---------------------------------------------------------------------- tartós nézet-állapot

/** A csukott tartományok kezdősorainak száma (1-től), legfeljebb `MAX_HAJTOTT`. */
export function hajtottSorok(state: EditorState): number[] {
  const ki: number[] = [];
  for (const r of hajtott(state)) {
    if (ki.length >= MAX_HAJTOTT) break;
    const n = state.doc.lineAt(r.from).number;
    if (ki[ki.length - 1] !== n) ki.push(n);
  }
  return ki;
}

/** A mentett sorszámok visszaállítása: csak a ma is hajtható sorok csukódnak (az elavult vagy hibás érték elmarad). */
export function hajtasVisszaallit(view: EditorView, mentett: unknown): void {
  if (!Array.isArray(mentett) || !mentett.length) return;
  const doc = view.state.doc;
  const tartomanyok: Tartomany[] = [];
  const latott = new Set<number>();
  for (const x of mentett.slice(0, MAX_HAJTOTT)) {
    if (typeof x !== 'number' || !Number.isInteger(x) || x < 1 || x > doc.lines || latott.has(x)) continue;
    latott.add(x);
    const r = hajthatoTartomany(view.state, doc.line(x).from);
    if (r) tartomanyok.push(r);
  }
  if (!tartomanyok.length) return;
  tartomanyok.sort((a, b) => a.from - b.from);
  const effects = tartomanyok.map((r) => foldEffect.of(r));
  const fej = view.state.selection.main.head;
  const fedo = tartomanyok.find((r) => r.from < fej && fej < r.to);
  // a visszaállított kurzor egy csukott tartományban: a hajtás marad, a kurzor a tartomány elé kerül
  view.dispatch(fedo ? { effects, selection: { anchor: fedo.from } } : { effects });
}

/** Változott-e a tranzakcióban a hajtás-állapot (a nézet-állapot mentéséhez). */
export function hajtasValtozott(elotte: EditorState, utana: EditorState): boolean {
  return elotte.field(foldState, false) !== utana.field(foldState, false);
}

// ---------------------------------------------------------------------- a sor eleji összecsukó

class HajtoWidget extends WidgetType {
  constructor(readonly csukva: boolean) {
    super();
  }

  eq(m: HajtoWidget) {
    return m.csukva === this.csukva;
  }

  toDOM(view: EditorView) {
    const hely = document.createElement('span');
    hely.className = 'cm-hajto-hely';
    const b = document.createElement('button');
    b.type = 'button';
    b.tabIndex = -1; // billentyűzetről a parancsok érik el (a szerkesztő fókusza nem ugrik a gombra)
    b.className = 'cm-hajto' + (this.csukva ? ' csukva' : '');
    b.setAttribute('aria-expanded', String(!this.csukva));
    b.setAttribute('aria-label', this.csukva ? t('Kibontás') : t('Összecsukás'));
    b.title = b.getAttribute('aria-label')!;
    b.appendChild(ikonElem(ChevronRight, 14));
    b.addEventListener('mousedown', (e) => e.preventDefault());
    b.addEventListener('click', (e) => {
      e.preventDefault();
      sorHajtasValt(view, view.state.doc.lineAt(view.posAtDOM(hely)).from);
    });
    hely.appendChild(b);
    return hely;
  }

  ignoreEvent() {
    return true;
  }
}

const NYITOTT = Decoration.widget({ widget: new HajtoWidget(false), side: -1 });
const CSUKOTT = Decoration.widget({ widget: new HajtoWidget(true), side: -1 });

function jelek(view: EditorView): DecorationSet {
  const state = view.state;
  const ki: Range<Decoration>[] = [];
  for (const { from, to } of view.visibleRanges) {
    for (let p = from; p <= to; ) {
      const sor = state.doc.lineAt(p);
      const r = hajthatoTartomany(state, sor.from, false);
      if (r) {
        const hely = sor.from + /^[ \t]*/.exec(sor.text)![0].length;
        ki.push((hajtottAzonSoron(state, sor.from) ? CSUKOTT : NYITOTT).range(hely));
      }
      p = sor.to + 1;
    }
  }
  return Decoration.set(ki, true);
}

const hajtoJelek = ViewPlugin.fromClass(
  class {
    decorations: DecorationSet;
    constructor(view: EditorView) {
      this.decorations = jelek(view);
    }
    update(u: ViewUpdate) {
      if (u.docChanged || u.viewportChanged || syntaxTree(u.startState) !== syntaxTree(u.state) || hajtasValtozott(u.startState, u.state))
        this.decorations = jelek(u.view);
    }
  },
  { decorations: (p) => p.decorations },
);

/** A szerkesztő összecsukás-bővítménye (mindkét szerkesztő módban). */
export function hajtasBovitmeny(): Extension {
  return [codeFolding({ placeholderText: '…' }), hajtoJelek];
}
