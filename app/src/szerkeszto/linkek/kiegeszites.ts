// A `[[` kiegészítés (C10): a `[[` (vagy `![[`) gépelésére menü nyílik a kurzor alatt; a C09 `/` menüjének mintájára
// (StateField + `showTooltip` + a közös `Menu`), a fókusz végig a szerkesztőben marad.
//
// A menü a gépelt szövegből dönt:
//   fájl-mód   `[[Jegy`            → fuzzy, ékezetfüggetlen találat a fájlnevekre ÉS az `aliases`-ekre (alias-találat:
//                                    `[[Jegyzet|Alias]]`); üresen a legutóbbiak;
//   fejezet    `[[Jegyzet#Fej`     → a cél fejezetei (az aktuális jegyzeté az élő szövegből: `[[#`);
//   blokk      `[[Jegyzet#^`       → a `^id`-s blokkok előnézettel; az aktuális jegyzet id nélküli blokkjához a beszúrás
//                                    az azonosítót is beírja (egy tranzakció);
//   alias      `[[Jegyzet|`        → a cél aliasai.
// A beírandó cél a core `linkcel`-éből jön (a legrövidebb egyértelmű alak, L42): nincs saját rövidítési szabály.
// A `[[` gépelésekor a záró `]]` is beíródik (a Backspace a párt együtt törli).

import { ensureSyntaxTree, syntaxTree } from '@codemirror/language';
import { type ChangeSpec, ChangeSet, type EditorState, Facet, type Extension, Prec, StateEffect, StateField } from '@codemirror/state';
import { EditorView, keymap, showTooltip, type Tooltip, type TooltipView, type ViewUpdate } from '@codemirror/view';
import { ApiHiba, kerdez } from '../../lib/core/api';
import { fajlIkon } from '../../lib/ikon/fajlIkon';
import { FuzzyIndex } from '../../lib/kereses/fuzzy';
import { fajlNev, mappa, type FajlInfo } from '../../lib/vault/fajlok.svelte';
import { linkek } from '../../lib/vault/linkek.svelte';
import { jegyzetUtja } from '../elo/jegyzet';
import { Menu, type MenuElem } from '../notion/menu';
import { blokkok, fejezetSzoveg } from '../notion/blokkmodell';
import { fejezetLinkSzoveg, idBeir, ujBlokkId } from '../notion/muveletek';

/** A kiegészítés adatforrásai (a szerkesztő komponens adja): a vault fájljai és a legutóbbiak. */
export interface KiegeszitesForras {
  fajlok(): FajlInfo[];
  legutobbi(): string[];
  /** J1: a beírt jegyzet-link célja (az Asszisztens ismétlődő-művelet mintájához; a core a kapcsolót nézi) */
  tanul?(cel: string): void;
}

export const kiegeszitesForras = Facet.define<KiegeszitesForras, KiegeszitesForras | null>({
  combine: (v) => v[0] ?? null,
});

interface Allapot {
  /** a `[[` utáni első karakter helye */
  from: number;
  beagyazas: boolean;
}

const nyit = StateEffect.define<Allapot>();
const zar = StateEffect.define<null>();
const frissit = StateEffect.define<null>();

const TILTOTT = new Set(['FencedCode', 'CodeBlock', 'InlineCode', 'MathBlock', 'InlineMath', 'DisplayMath', 'HTMLBlock', 'HTMLTag', 'CommentBlock', 'Comment']);

/** Nyithat-e kiegészítés a `p` helyen (kódban, képletben, HTML-ben nem). */
export function linkNyithato(state: EditorState, p: number): boolean {
  if (state.readOnly) return false;
  const fa = ensureSyntaxTree(state, Math.min(state.doc.length, p + 1), 50) ?? syntaxTree(state);
  for (let n: ReturnType<typeof fa.resolveInner> | null = fa.resolveInner(p, -1); n; n = n.parent) if (TILTOTT.has(n.name)) return false;
  return true;
}

// ---------------------------------------------------------------------- a gépelt szöveg értelmezése

export type Mod = 'fajl' | 'fejezet' | 'blokk' | 'alias';

export interface Lekerdezes {
  mod: Mod;
  /** a gépelt cél (a `#`/`|` előtt) */
  cel: string;
  /** a `#` utáni szűrő (blokknál a `^` után) */
  alk: string;
  alias: string;
}

export function lekerdezesElemez(q: string): Lekerdezes {
  const cso = q.indexOf('|');
  const resz = cso >= 0 ? q.slice(0, cso) : q;
  const alias = cso >= 0 ? q.slice(cso + 1) : '';
  const h = resz.indexOf('#');
  const cel = h >= 0 ? resz.slice(0, h) : resz;
  const alk = h >= 0 ? resz.slice(h + 1) : '';
  const mod: Mod = cso >= 0 ? 'alias' : h >= 0 ? (alk.startsWith('^') ? 'blokk' : 'fejezet') : 'fajl';
  return { mod, cel, alk: mod === 'blokk' ? alk.slice(1) : alk, alias };
}

// ---------------------------------------------------------------------- jelöltek

/** Egy menüelem és a beírása. `beir`: a lekérdezés helyére kerülő szöveg (aszinkron: a core cél-szövege kell). */
export interface Elem extends MenuElem {
  beir: (view: EditorView, q: Lekerdezes) => Promise<{ szoveg: string; extra?: unknown } | null>;
  /** az aktuális jegyzetben álló, azonosítót nem tartalmazó blokk: a beírás az id-t is beteszi */
  idKell?: number;
  /** jegyzet-cél (md) útja: a beírása az Asszisztens tanuló magjának jelzés (J1) */
  tanulCel?: string;
}

const MAX_ELEM = 14;

function fajlJeloltek(f: KiegeszitesForras, aliasok: Record<string, string[]>) {
  const j: { ertek: { ut: string; alias?: string; tipus: FajlInfo['tipus'] }; nev: string; ut: string }[] = [];
  for (const x of f.fajlok()) {
    j.push({ ertek: { ut: x.ut, tipus: x.tipus }, nev: x.tipus === 'md' ? fajlNev(x.ut) : x.ut.slice(x.ut.lastIndexOf('/') + 1), ut: mappa(x.ut) });
    for (const a of aliasok[x.ut] ?? []) j.push({ ertek: { ut: x.ut, alias: a, tipus: x.tipus }, nev: a, ut: fajlNev(x.ut) });
  }
  return j;
}

type FajlIndex = FuzzyIndex<{ ut: string; alias?: string; tipus: FajlInfo['tipus'] }>;
const indexek = new WeakMap<object, { lista: FajlInfo[]; aliasok: Record<string, string[]>; index: FajlIndex }>();

function fajlIndex(f: KiegeszitesForras, aliasok: Record<string, string[]>): FajlIndex {
  const lista = f.fajlok();
  const mar = indexek.get(f);
  if (mar && mar.lista === lista && mar.aliasok === aliasok) return mar.index;
  const index = new FuzzyIndex(fajlJeloltek(f, aliasok));
  indexek.set(f, { lista, aliasok, index });
  return index;
}

function fajlElemek(view: EditorView, f: KiegeszitesForras, q: Lekerdezes, aliasok: Record<string, string[]>): Elem[] {
  const forras = view.state.facet(jegyzetUtja) ?? '';
  const elem = (ut: string, tipus: FajlInfo['tipus'], alias: string | undefined, kiemeles?: [number, number][]): Elem => ({
    id: `f:${ut}:${alias ?? ''}`,
    tanulCel: tipus === 'md' ? ut : undefined,
    nev: alias ?? (tipus === 'md' ? fajlNev(ut) : ut.slice(ut.lastIndexOf('/') + 1)),
    ikon: fajlIkon(tipus),
    jelzo: alias ? `→ ${fajlNev(ut)}` : mappa(ut),
    kiemeles,
    beir: async () => {
      const cel = await linkek.linkCel(ut, forras);
      return { szoveg: alias ? `${cel}|${alias}` : cel };
    },
  });
  const query = q.cel.trim();
  if (!query) {
    const lat = new Set<string>();
    const ki: Elem[] = [];
    const info = new Map(f.fajlok().map((x) => [x.ut, x]));
    for (const ut of f.legutobbi()) {
      const x = info.get(ut);
      if (x && ut !== forras && !lat.has(ut)) {
        lat.add(ut);
        ki.push(elem(ut, x.tipus, undefined));
      }
    }
    for (const x of [...f.fajlok()].sort((a, b) => (b.mtime ?? 0) - (a.mtime ?? 0))) {
      if (ki.length >= MAX_ELEM) break;
      if (!lat.has(x.ut) && x.ut !== forras) ki.push(elem(x.ut, x.tipus, undefined));
    }
    return ki.slice(0, MAX_ELEM);
  }
  const rang = new Map(f.legutobbi().map((u, i) => [u, i]));
  return fajlIndex(f, aliasok)
    .keres(query, {
      limit: MAX_ELEM,
      bonusz: (e) => {
        const i = rang.get(e.ut);
        return (e.tipus === 'md' ? 10 : 0) + (i === undefined ? 0 : Math.max(2, 12 - i)); // a jegyzetek a mellékletek előtt
      },
    })
    .map((t) => elem(t.ertek.ut, t.ertek.tipus, t.ertek.alias, t.kiemeles));
}

/** A cél jegyzet: az aktuális (üres cél), vagy a core által feloldott fájl útja (nem md: `null`). */
async function celJegyzet(view: EditorView, cel: string): Promise<string | null> {
  const forras = view.state.facet(jegyzetUtja);
  if (!forras) return null;
  if (!cel.trim()) return forras;
  const ut = await linkek.fajl(forras, cel.trim());
  return ut && ut.toLowerCase().endsWith('.md') ? ut : null;
}

/** A jegyzet fejezetei az élő szerkesztőből. */
export function eloFejezetek(state: EditorState): { szint: number; szoveg: string; sor: number }[] {
  const ki: { szint: number; szoveg: string; sor: number }[] = [];
  const fa = ensureSyntaxTree(state, state.doc.length, 200) ?? syntaxTree(state);
  fa.iterate({
    enter(n) {
      const m = /^(?:ATX|Setext)Heading(\d)$/.exec(n.name);
      if (!m) return;
      const sor = state.doc.lineAt(n.from);
      const szoveg = fejezetSzoveg(sor.text);
      if (szoveg) ki.push({ szint: Number(m[1]), szoveg, sor: sor.number });
      return false;
    },
  });
  return ki;
}

async function fejezetElemek(view: EditorView, q: Lekerdezes): Promise<Elem[]> {
  const ut = await celJegyzet(view, q.cel);
  if (!ut) return [];
  let lista: { szint: number; szoveg: string; sor: number }[];
  if (ut === view.state.facet(jegyzetUtja)) lista = eloFejezetek(view.state);
  else {
    try {
      lista = (await kerdez<{ fejezetek: typeof lista }>(`/api/vault/jegyzet?ut=${encodeURIComponent(ut)}`, { idokorlat: 5000 })).fejezetek;
    } catch (e) {
      if (e instanceof ApiHiba) return [];
      throw e;
    }
  }
  const elemek = lista.map((h): Elem => ({
    id: `h:${h.sor}`,
    nev: h.szoveg,
    jelzo: `H${h.szint}`,
    beir: async () => ({ szoveg: `${q.cel}#${fejezetLinkSzoveg(h.szoveg)}` }),
  }));
  const szuro = q.alk.trim();
  if (!szuro) return elemek.slice(0, 30);
  const idx = new FuzzyIndex(elemek.map((e) => ({ ertek: e, nev: e.nev })));
  return idx.keres(szuro, { limit: MAX_ELEM }).map((t) => ({ ...t.ertek, kiemeles: t.kiemeles }));
}

const ID_VEG = /[ \t]*\^[A-Za-z0-9-]+[ \t]*$/;

async function blokkElemek(view: EditorView, q: Lekerdezes): Promise<Elem[]> {
  const ut = await celJegyzet(view, q.cel);
  if (!ut) return [];
  const elemek: Elem[] = [];
  if (ut === view.state.facet(jegyzetUtja)) {
    const sorKurzor = view.state.doc.lineAt(view.state.selection.main.head).number;
    for (const b of blokkok(view.state)) {
      if (b.idMod !== 'sorveg') continue;
      const szoveg = view.state.doc.line(b.elsoSor).text.replace(ID_VEG, '').replace(/^[ \t>]*(?:[-*+]|\d+[.)])?[ \t]*(?:\[.\][ \t]*)?/, '').trim();
      if (!szoveg && !b.id) continue;
      if (!b.id && b.elsoSor <= sorKurzor && sorKurzor <= b.utolsoSor) continue; // a saját sorára nem hivatkozunk
      elemek.push({
        id: `b:${b.elsoSor}`,
        nev: szoveg.slice(0, 90) || '(üres)',
        jelzo: b.id ? `^${b.id}` : 'új ^id',
        idKell: b.id ? undefined : b.index,
        beir: async () => ({ szoveg: `${q.cel}#^${b.id ?? ''}` }),
      });
    }
  } else {
    let szovegek: string[] = [];
    let blokkLista: { azon: string; sor: number; kezdo_sor: number }[] = [];
    try {
      const [j, f] = await Promise.all([
        kerdez<{ blokkok: typeof blokkLista }>(`/api/vault/jegyzet?ut=${encodeURIComponent(ut)}`, { idokorlat: 5000 }),
        kerdez<{ tartalom: string }>(`/api/vault/fajl?ut=${encodeURIComponent(ut)}`, { idokorlat: 5000 }),
      ]);
      blokkLista = j.blokkok;
      szovegek = f.tartalom.split(/\r\n?|\n/);
    } catch (e) {
      if (e instanceof ApiHiba) return [];
      throw e;
    }
    for (const b of blokkLista) {
      const sor = (szovegek[b.kezdo_sor - 1] ?? '').replace(ID_VEG, '').replace(/^[ \t>]*(?:[-*+]|\d+[.)])?[ \t]*/, '').trim();
      elemek.push({ id: `b:${b.azon}`, nev: sor.slice(0, 90) || `(${b.azon})`, jelzo: `^${b.azon}`, beir: async () => ({ szoveg: `${q.cel}#^${b.azon}` }) });
    }
  }
  const szuro = q.alk.trim();
  if (!szuro) return elemek.slice(0, 30);
  const idx = new FuzzyIndex(elemek.map((e) => ({ ertek: e, nev: e.nev })));
  return idx.keres(szuro, { limit: MAX_ELEM }).map((t) => ({ ...t.ertek, kiemeles: t.kiemeles }));
}

async function aliasElemek(view: EditorView, q: Lekerdezes, aliasok: Record<string, string[]>): Promise<Elem[]> {
  const ut = await celJegyzet(view, q.cel);
  const lista = (ut && aliasok[ut]) || [];
  const szuro = q.alias.trim();
  const elemek = lista.map((a): Elem => ({ id: `a:${a}`, nev: a, beir: async () => ({ szoveg: `${q.cel}${q.alk ? `#${q.alk}` : ''}|${a}` }) }));
  if (!szuro) return elemek;
  const idx = new FuzzyIndex(elemek.map((e) => ({ ertek: e, nev: e.nev })));
  return idx.keres(szuro, { limit: MAX_ELEM }).map((t) => ({ ...t.ertek, kiemeles: t.kiemeles }));
}

/** A menü elemei a lekérdezéshez. */
export async function elemek(view: EditorView, f: KiegeszitesForras, q: Lekerdezes): Promise<Elem[]> {
  let aliasok: Record<string, string[]> = {};
  if (q.mod === 'fajl' || q.mod === 'alias') {
    try {
      aliasok = await linkek.aliasokKap();
    } catch {
      aliasok = {};
    }
  }
  switch (q.mod) {
    case 'fajl':
      return fajlElemek(view, f, q, aliasok);
    case 'fejezet':
      return fejezetElemek(view, q);
    case 'blokk':
      return blokkElemek(view, q);
    case 'alias':
      return aliasElemek(view, q, aliasok);
  }
}

// ---------------------------------------------------------------------- állapot

function ervenyes(state: EditorState, a: Allapot): boolean {
  const r = state.selection.main;
  if (!r.empty || r.head < a.from) return false;
  if (state.doc.lineAt(a.from).number !== state.doc.lineAt(r.head).number) return false;
  return !state.sliceDoc(a.from, r.head).includes(']');
}

const kiegeszitesMezo = StateField.define<Allapot | null>({
  create: () => null,
  update(ertek, tr) {
    for (const e of tr.effects) {
      if (e.is(zar)) return null;
      if (e.is(nyit)) return e.value;
    }
    if (!ertek) return null;
    if (!tr.docChanged && !tr.selection) return ertek;
    const uj = { ...ertek, from: tr.changes.mapPos(ertek.from, -1) };
    return ervenyes(tr.state, uj) ? uj : null;
  },
});

export function lekerdezes(state: EditorState): string | null {
  const a = state.field(kiegeszitesMezo, false);
  return a ? state.sliceDoc(a.from, state.selection.main.head) : null;
}

export function kiegeszitesNyitva(state: EditorState): boolean {
  return !!state.field(kiegeszitesMezo, false);
}

// ---------------------------------------------------------------------- beírás

/** A kiválasztott elem beírása a gépelt lekérdezés helyére; a meglévő záró `]]` után áll a kurzor. Az id nélküli
 *  blokknál az azonosító beírása ugyanabban a tranzakcióban történik (egy ⌘Z visszavonja mindkettőt). */
async function alkalmaz(view: EditorView, e: Elem): Promise<void> {
  const a = view.state.field(kiegeszitesMezo, false);
  if (!a) return;
  const eredetiDoc = view.state.doc;
  const q = lekerdezesElemez(view.state.sliceDoc(a.from, view.state.selection.main.head));
  let eredmeny: { szoveg: string } | null;
  try {
    eredmeny = await e.beir(view, q);
  } catch {
    view.dispatch({ effects: zar.of(null) });
    return;
  }
  const b = view.state.field(kiegeszitesMezo, false);
  if (!eredmeny || !b || view.state.doc !== eredetiDoc) return; // közben gépelt: az új lekérdezésre vonatkozik
  const veg = view.state.selection.main.head;
  const zaroVan = view.state.sliceDoc(veg, veg + 2) === ']]';
  let szoveg = eredmeny.szoveg;
  const valtozasok: ChangeSpec[] = [];
  if (e.idKell !== undefined) {
    const bl = blokkok(view.state)[e.idKell];
    const r = bl ? idBeir(view.state, bl, ujBlokkId(view.state)) : null;
    if (!r?.szerkesztes) return;
    valtozasok.push(r.szerkesztes.changes);
    szoveg = szoveg.replace(/#\^$/, `#^${r.id}`);
  }
  const link = { from: b.from, to: zaroVan ? veg + 2 : veg, insert: `${szoveg}]]` };
  valtozasok.push(link);
  const cs = ChangeSet.of(valtozasok, eredetiDoc.length);
  view.dispatch({
    changes: cs,
    selection: { anchor: cs.mapPos(link.to, 1) },
    effects: zar.of(null),
    userEvent: 'input.link',
    scrollIntoView: true,
  });
  view.focus();
  if (e.tanulCel) view.state.facet(kiegeszitesForras)?.tanul?.(e.tanulCel);
}

// ---------------------------------------------------------------------- DOM: tooltip és billentyűk

const menuk = new WeakMap<EditorView, Menu>();

function jelez(view: EditorView, id: string | null): void {
  if (id) view.contentDOM.setAttribute('aria-activedescendant', id);
  else view.contentDOM.removeAttribute('aria-activedescendant');
}

function letrehoz(view: EditorView): TooltipView {
  const lista = new Map<string, Elem>();
  const menu = new Menu({
    cimke: 'Link beszúrása',
    ures: 'Nincs találat',
    onValaszt: (e) => {
      const el = lista.get(e.id);
      if (el) void alkalmaz(view, el);
    },
    onAktiv: (id) => jelez(view, id),
  });
  menuk.set(view, menu);
  menu.elem.classList.add('nt-linkmenu');
  let utolso: string | null = null;
  let sorszam = 0;
  const frissitMenu = (state: EditorState, kenyszer = false) => {
    const q = lekerdezes(state);
    const f = state.facet(kiegeszitesForras);
    if (q === null || !f) return;
    if (q === utolso && !kenyszer) return;
    utolso = q;
    const en = ++sorszam;
    void elemek(view, f, lekerdezesElemez(q)).then(
      (es) => {
        if (en !== sorszam || !menuk.has(view)) return; // újabb lekérdezés vagy bezárt menü
        lista.clear();
        for (const x of es) lista.set(x.id, x);
        menu.beallit(es);
        jelez(view, menu.aktivId);
      },
      () => {
        if (en === sorszam && menuk.has(view)) menu.beallit([]);
      },
    );
  };
  frissitMenu(view.state, true);
  const c = view.contentDOM;
  c.setAttribute('aria-haspopup', 'listbox');
  c.setAttribute('aria-expanded', 'true');
  c.setAttribute('aria-controls', `${menu.id}-lista`);
  // az aliasok vagy a fájlszerkezet változása újra szűr
  const leKapcsol = linkekFigyel(() => frissitMenu(view.state, true));
  return {
    dom: menu.elem,
    update: (u: ViewUpdate) => {
      if (u.transactions.some((t) => t.effects.some((e) => e.is(frissit)))) frissitMenu(u.state, true);
      else frissitMenu(u.state);
    },
    destroy() {
      leKapcsol();
      menuk.delete(view);
      c.removeAttribute('aria-activedescendant');
      c.removeAttribute('aria-haspopup');
      c.removeAttribute('aria-expanded');
      c.removeAttribute('aria-controls');
    },
  };
}

/** A `linkek.verzio` változására (új fájl) a menü újra szűr. */
function linkekFigyel(f: () => void): () => void {
  let utolso = linkek.verzio;
  const t = setInterval(() => {
    if (linkek.verzio !== utolso) {
      utolso = linkek.verzio;
      f();
    }
  }, 500);
  return () => clearInterval(t);
}

const tooltip = showTooltip.compute([kiegeszitesMezo], (state): Tooltip | null => {
  const a = state.field(kiegeszitesMezo);
  return a ? { pos: a.from, above: false, strictSide: false, arrow: false, create: letrehoz } : null;
});

const billentyuk = Prec.highest(
  EditorView.domEventHandlers({
    keydown(e, view) {
      const a = view.state.field(kiegeszitesMezo, false);
      if (!a || e.isComposing) return false;
      if (e.key === 'Escape') {
        view.dispatch({ effects: zar.of(null) });
        e.preventDefault();
        return true;
      }
      const m = menuk.get(view);
      if (!m) return false;
      if ((e.key === 'Enter' || e.key === 'Tab') && m.meret === 0) {
        // találat nélkül a gépelt szöveg a link (az Obsidian módjára): a kurzor a `]]` után áll
        const veg = view.state.selection.main.head;
        view.dispatch({
          effects: zar.of(null),
          selection: { anchor: view.state.sliceDoc(veg, veg + 2) === ']]' ? veg + 2 : veg },
        });
        e.preventDefault();
        return true;
      }
      if (m.billentyu(e)) {
        e.preventDefault();
        return true;
      }
      return false;
    },
    blur(_e, view) {
      if (view.state.field(kiegeszitesMezo, false)) view.dispatch({ effects: zar.of(null) });
      return false;
    },
  }),
);

/** A `[[` gépelése: beírja a záró `]]`-t és megnyitja a menüt. */
const gepeles = EditorView.inputHandler.of((view, from, to, text) => {
  if (text !== '[' || from !== to || view.state.readOnly) return false;
  const s = view.state;
  if (s.sliceDoc(from - 1, from) !== '[' || s.sliceDoc(from - 2, from - 1) === '[') return false;
  if (!linkNyithato(s, from)) return false;
  const beagyazas = s.sliceDoc(from - 2, from - 1) === '!';
  const zaroVan = s.sliceDoc(from, from + 2) === ']]';
  view.dispatch({
    changes: { from, to, insert: zaroVan ? '[' : '[]]' },
    selection: { anchor: from + 1 },
    effects: nyit.of({ from: from + 1, beagyazas }),
    userEvent: 'input.type',
  });
  return true;
});

/** Backspace a `[[|]]` közepén: a pár együtt törlődik. */
const parTorles = Prec.high(
  keymap.of([
    {
      key: 'Backspace',
      run(view) {
        const r = view.state.selection.main;
        if (!r.empty || view.state.readOnly) return false;
        if (view.state.sliceDoc(r.head - 2, r.head + 2) !== '[[]]') return false;
        view.dispatch({ changes: { from: r.head - 2, to: r.head + 2 }, selection: { anchor: r.head - 2 }, effects: zar.of(null), userEvent: 'delete.backward' });
        return true;
      },
    },
  ]),
);

/** A `[[` kiegészítés a szerkesztőben (Live Preview és Forrás is). */
export function kiegeszitesBovitmeny(): Extension {
  return [kiegeszitesMezo, tooltip, billentyuk, gepeles, parTorles];
}

/** A tesztekhez és a parancsokhoz: a menü megnyitása a kurzornál (beír egy `[[]]`-t). */
export function linkBeszur(view: EditorView, beagyazas = false): boolean {
  const r = view.state.selection.main;
  if (view.state.readOnly || !linkNyithato(view.state, r.head)) return false;
  const elo = beagyazas ? '![[' : '[[';
  view.dispatch({
    changes: { from: r.from, to: r.to, insert: `${elo}]]` },
    selection: { anchor: r.from + elo.length },
    effects: nyit.of({ from: r.from + elo.length, beagyazas }),
    userEvent: 'input.type',
  });
  return true;
}

export const kiegeszitesFrissit = frissit;
