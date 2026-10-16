// A `[[` kiegészítés (C10): a `[[` (vagy `![[`) gépelésére menü nyílik a kurzor alatt; a C09 `/` menüjének mintájára
// (StateField + `showTooltip` + a közös `Menu`), a fókusz végig a szerkesztőben marad.
//
// A menü a gépelt szövegből dönt:
//   fájl-mód   `[[Jegy`            → fuzzy, ékezetfüggetlen találat a fájlnevekre ÉS az `aliases`-ekre (alias-találat:
//                                    `[[Jegyzet|Alias]]`); üresen a legutóbbiak;
//   fejezet    `[[Jegyzet#Fej`     → a cél fejezetei (az aktuális jegyzeté az élő szövegből: `[[#`);
//   blokk      `[[Jegyzet#^`       → a `^id`-s blokkok előnézettel; az aktuális jegyzet id nélküli blokkjához a beszúrás
//                                    az azonosítót is beírja (egy tranzakció);
//   alias      `[[Jegyzet|`        → a cél aliasai;
//   minden jegyzet fejezete  `[[##Fej`  → a vault összes fejezete (a core szűri), `[[Jegyzet#Fej]]` alakban;
//   nincs még  a fájl-módban a vaultban már használt, de még nem létező link-célok is megjelennek (`nincs még`).
// A beszúrt link alakját a beállítások adják (core `linkcel`): „New link format” és „Use [[Wikilinks]]”; kikapcsolt
// wikilinknél a `[[…]]` egésze markdown-linkre cserélődik. Egy már meglévő, nyitott `[[…` belsejében gépelve a menü újra előjön.
// A beírandó cél a core `linkcel`-éből jön (a legrövidebb egyértelmű alak, L42): nincs saját rövidítési szabály.
// A `[[` gépelésekor a záró `]]` is beíródik (a Backspace a párt együtt törli).

import { t } from '../../lib/i18n';
import { ensureSyntaxTree, syntaxTree } from '@codemirror/language';
import { type ChangeSpec, ChangeSet, EditorState, Facet, type Extension, Prec, StateEffect, StateField } from '@codemirror/state';
import { EditorView, keymap, showTooltip, ViewPlugin, type Tooltip, type TooltipView, type ViewUpdate } from '@codemirror/view';
import { commonmarkLanguage, markdown } from '@codemirror/lang-markdown';
import { ApiHiba, kerdez } from '../../lib/core/api';
import { fajlIkon } from '../../lib/ikon/fajlIkon';
import { FuzzyIndex } from '../../lib/kereses/fuzzy';
import { fajlNev, mappa, type FajlInfo } from '../../lib/vault/fajlok.svelte';
import { linkek, type LinkForma, type VaultFejezet } from '../../lib/vault/linkek.svelte';
import { jegyzetUtja } from '../elo/jegyzet';
import { OBSIDIAN_BOVITESEK } from '../markdown/elemzo';
import { Menu, type MenuElem } from '../notion/menu';
import { blokkok, fejezetSzoveg } from '../notion/blokkmodell';
import { fejezetLinkSzoveg, idBeir, ujBlokkId } from '../notion/muveletek';
import { ertesitesek } from '../../lib/ertesites/ertesites.svelte';
import { szerkesztok } from '../szerkesztok.svelte';
import { linkSzoveg } from './adat';

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
/** Az Esc: ezen a linken a menü nem nyílik újra, amíg a kurzor ki nem lép belőle (a hely az állapotban). */
const elvet = StateEffect.define<null>();

const TILTOTT = new Set(['FencedCode', 'CodeBlock', 'InlineCode', 'MathBlock', 'InlineMath', 'DisplayMath', 'HTMLBlock', 'HTMLTag', 'CommentBlock', 'Comment', 'ObsidianCommentBlock', 'ObsidianComment']);

/** Nyithat-e kiegészítés a `p` helyen (kódban, képletben, HTML-ben nem). */
export function linkNyithato(state: EditorState, p: number): boolean {
  if (state.readOnly) return false;
  const fa = ensureSyntaxTree(state, Math.min(state.doc.length, p + 1), 50) ?? syntaxTree(state);
  for (let n: ReturnType<typeof fa.resolveInner> | null = fa.resolveInner(p, -1); n; n = n.parent) if (TILTOTT.has(n.name)) return false;
  return true;
}

// ---------------------------------------------------------------------- a gépelt szöveg értelmezése

export type Mod = 'fajl' | 'fejezet' | 'blokk' | 'alias' | 'fejezetMind';

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
  // `[[##szűrő`: a vault összes fejezetében keres (üres cél, a `#` után még egy `#`)
  const osszes = cso < 0 && h >= 0 && cel === '' && alk.startsWith('#');
  const mod: Mod = cso >= 0 ? 'alias' : osszes ? 'fejezetMind' : h >= 0 ? (alk.startsWith('^') ? 'blokk' : 'fejezet') : 'fajl';
  return { mod, cel, alk: mod === 'blokk' || mod === 'fejezetMind' ? alk.slice(1) : alk, alias };
}

// ---------------------------------------------------------------------- jelöltek

/** A beírandó: a `[[` és `]]` közé kerülő szöveg, vagy — ha a „Use [[Wikilinks]]” ki van kapcsolva — a kész markdown-link,
 *  amelyre a `[[…]]` egésze cserélődik. */
export interface Beirando {
  szoveg: string;
  md?: string;
}

/** Egy menüelem és a beírása. `beir`: a lekérdezés helyére kerülő szöveg (aszinkron: a core cél-szövege kell); az `id` az
 *  id nélküli blokkhoz most generált azonosító. */
export interface Elem extends MenuElem {
  beir: (view: EditorView, q: Lekerdezes, id?: string) => Promise<Beirando | null>;
  /** az aktuális jegyzetben álló, azonosítót nem tartalmazó blokk: a beírás az id-t is beteszi */
  idKell?: number;
  /** másik jegyzetben álló, azonosítót nem tartalmazó blokk: a kiválasztás az id-t abba a jegyzetbe írja (hash-védett mentés) */
  masikIdKell?: { ut: string; szoveg: string; index: number };
  /** jegyzet-cél (md) útja: a beírása az Asszisztens tanuló magjának jelzés (J1) */
  tanulCel?: string;
}

const MAX_ELEM = 14;

/** A beszúrandó link a core alakjából (`linkcel`: formátum, alak, md-cél). A `cel` a gépelt cél, ha az a wikilinkben marad
 *  (fejezet-, blokk-, alias-mód); a core hibája esetén wikilink (a beszúrás sosem akad el a beállításon). */
async function linkBeirando(
  view: EditorView,
  ut: string,
  o: { cel?: string; alcel?: string | null; alias?: string | null; nev: string },
): Promise<Beirando> {
  const forras = view.state.facet(jegyzetUtja) ?? '';
  const beagyazas = view.state.field(kiegeszitesMezo, false)?.beagyazas ?? false;
  let forma: LinkForma = { cel: o.cel ?? '', alak: 'wiki', md: '' };
  try {
    forma = await linkek.linkForma(ut, forras, o.alcel);
  } catch (e) {
    if (o.cel === undefined) throw e; // a fájl-módban a core cél-szövege nélkül nincs link
  }
  const cel = o.cel ?? forma.cel;
  const wiki = `${cel}${o.alcel ? `#${o.alcel}` : ''}${o.alias ? `|${o.alias}` : ''}`;
  return forma.alak === 'md' && forma.md ? { szoveg: wiki, md: linkSzoveg(forma, { ...o, beagyazas }) } : { szoveg: wiki };
}

interface FajlErtek {
  ut: string;
  alias?: string;
  tipus: FajlInfo['tipus'];
  /** vaultban használt, de még nem létező link-cél (a szövege az `ut`-ban áll) */
  hianyzo?: boolean;
}

function fajlJeloltek(f: KiegeszitesForras, aliasok: Record<string, string[]>, hianyzok: string[]) {
  const j: { ertek: FajlErtek; nev: string; ut: string }[] = [];
  for (const x of f.fajlok()) {
    j.push({ ertek: { ut: x.ut, tipus: x.tipus }, nev: x.tipus === 'md' ? fajlNev(x.ut) : x.ut.slice(x.ut.lastIndexOf('/') + 1), ut: mappa(x.ut) });
    for (const a of aliasok[x.ut] ?? []) j.push({ ertek: { ut: x.ut, alias: a, tipus: x.tipus }, nev: a, ut: fajlNev(x.ut) });
  }
  for (const h of hianyzok) j.push({ ertek: { ut: h, tipus: 'md', hianyzo: true }, nev: h, ut: '' });
  return j;
}

type FajlIndex = FuzzyIndex<FajlErtek>;
const indexek = new WeakMap<object, { lista: FajlInfo[]; aliasok: Record<string, string[]>; hianyzok: string[]; index: FajlIndex }>();

function fajlIndex(f: KiegeszitesForras, aliasok: Record<string, string[]>, hianyzok: string[]): FajlIndex {
  const lista = f.fajlok();
  const mar = indexek.get(f);
  if (mar && mar.lista === lista && mar.aliasok === aliasok && mar.hianyzok === hianyzok) return mar.index;
  const index = new FuzzyIndex(fajlJeloltek(f, aliasok, hianyzok));
  indexek.set(f, { lista, aliasok, hianyzok, index });
  return index;
}

function fajlElemek(view: EditorView, f: KiegeszitesForras, q: Lekerdezes, aliasok: Record<string, string[]>, hianyzok: string[]): Elem[] {
  const forras = view.state.facet(jegyzetUtja) ?? '';
  const elem = (ut: string, tipus: FajlInfo['tipus'], alias: string | undefined, kiemeles?: [number, number][]): Elem => ({
    id: `f:${ut}:${alias ?? ''}`,
    tanulCel: tipus === 'md' ? ut : undefined,
    nev: alias ?? (tipus === 'md' ? fajlNev(ut) : ut.slice(ut.lastIndexOf('/') + 1)),
    ikon: fajlIkon(tipus),
    jelzo: alias ? `→ ${fajlNev(ut)}` : mappa(ut),
    kiemeles,
    beir: (v) => linkBeirando(v, ut, { alias, nev: tipus === 'md' ? fajlNev(ut) : ut.slice(ut.lastIndexOf('/') + 1) }),
  });
  const hianyzoElem = (cel: string, kiemeles?: [number, number][]): Elem => ({
    id: `u:${cel}`,
    nev: cel,
    ikon: fajlIkon('md'),
    jelzo: t('nincs még'),
    kiemeles,
    beir: async (v) => {
      let forma: LinkForma = { cel, alak: 'wiki', md: '' };
      try {
        forma = await linkek.linkFormaHianyzo(cel, forras);
      } catch (e) {
        if (!(e instanceof ApiHiba)) throw e;
      }
      const beagyazas = v.state.field(kiegeszitesMezo, false)?.beagyazas ?? false;
      return forma.alak === 'md' && forma.md ? { szoveg: cel, md: linkSzoveg(forma, { nev: cel, beagyazas }) } : { szoveg: cel };
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
  return fajlIndex(f, aliasok, hianyzok)
    .keres(query, {
      limit: MAX_ELEM,
      bonusz: (e) => {
        if (e.hianyzo) return -4; // a létező fájl a még nem létező cél előtt
        const i = rang.get(e.ut);
        return (e.tipus === 'md' ? 10 : 0) + (i === undefined ? 0 : Math.max(2, 12 - i)); // a jegyzetek a mellékletek előtt
      },
    })
    .map((t) => (t.ertek.hianyzo ? hianyzoElem(t.ertek.ut, t.kiemeles) : elem(t.ertek.ut, t.ertek.tipus, t.ertek.alias, t.kiemeles)));
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
    beir: (v) => linkBeirando(v, ut, { cel: q.cel, alcel: fejezetLinkSzoveg(h.szoveg), nev: fajlNev(ut) }),
  }));
  const szuro = q.alk.trim();
  if (!szuro) return elemek.slice(0, 30);
  const idx = new FuzzyIndex(elemek.map((e) => ({ ertek: e, nev: e.nev })));
  return idx.keres(szuro, { limit: MAX_ELEM }).map((t) => ({ ...t.ertek, kiemeles: t.kiemeles }));
}

/** `[[##szűrő`: a vault összes jegyzetének fejezete (a core szűri és rangsorolja, a felület elírástűrően újrarendezi). */
async function mindenFejezetElemek(q: Lekerdezes): Promise<Elem[]> {
  let lista: VaultFejezet[];
  try {
    lista = await linkek.fejezetekMind(q.alk.trim());
  } catch (e) {
    if (e instanceof ApiHiba) return [];
    throw e;
  }
  const elemek = lista.map((h, i): Elem => ({
    id: `H:${h.ut}:${h.sor}:${i}`,
    nev: h.szoveg,
    ikon: fajlIkon('md'),
    jelzo: `H${h.szint} · ${fajlNev(h.ut)}`,
    beir: (v) => linkBeirando(v, h.ut, { alcel: fejezetLinkSzoveg(h.szoveg), nev: fajlNev(h.ut) }),
  }));
  const szuro = q.alk.trim();
  if (!szuro) return elemek.slice(0, MAX_ELEM);
  const idx = new FuzzyIndex(lista.map((h, i) => ({ ertek: elemek[i], nev: h.szoveg, ut: h.ut })));
  return idx.keres(szuro, { limit: MAX_ELEM }).map((t) => ({ ...t.ertek, kiemeles: t.kiemeles }));
}

const ID_VEG = /[ \t]*\^[A-Za-z0-9-]+[ \t]*$/;

/** Egy másik jegyzet szövegének blokkmodellje (a szerkesztő elemzőjével, DOM nélkül). */
function masikAllapot(szoveg: string): EditorState {
  return EditorState.create({
    doc: szoveg,
    extensions: markdown({ base: commonmarkLanguage, extensions: OBSIDIAN_BOVITESEK, completeHTMLTags: false }),
  });
}

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
        nev: szoveg.slice(0, 90) || t('(üres)'),
        jelzo: b.id ? `^${b.id}` : t('új ^id'),
        idKell: b.id ? undefined : b.index,
        beir: (v, _q, id) => linkBeirando(v, ut, { cel: q.cel, alcel: `^${b.id ?? id ?? ''}`, nev: fajlNev(ut) }),
      });
    }
  } else {
    let tartalom: string;
    try {
      tartalom = (await kerdez<{ tartalom: string }>(`/api/vault/fajl?ut=${encodeURIComponent(ut)}`, { idokorlat: 5000 })).tartalom;
    } catch (e) {
      if (e instanceof ApiHiba) return [];
      throw e;
    }
    const allapot = masikAllapot(tartalom);
    const szoveg0 = allapot.doc.toString();
    for (const b of blokkok(allapot)) {
      if (b.idMod !== 'sorveg') continue;
      const szoveg = allapot.doc.line(b.elsoSor).text.replace(ID_VEG, '').replace(/^[ \t>]*(?:[-*+]|\d+[.)])?[ \t]*(?:\[.\][ \t]*)?/, '').trim();
      if (!szoveg && !b.id) continue;
      elemek.push({
        id: `b:${ut}:${b.elsoSor}`,
        nev: szoveg.slice(0, 90) || t('(üres)'),
        jelzo: b.id ? `^${b.id}` : t('új ^id'),
        masikIdKell: b.id ? undefined : { ut, szoveg: szoveg0, index: b.index },
        beir: (v, _q, id) => linkBeirando(v, ut, { cel: q.cel, alcel: `^${b.id ?? id ?? ''}`, nev: fajlNev(ut) }),
      });
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
  const elemek = lista.map((a): Elem => ({
    id: `a:${a}`,
    nev: a,
    beir: ut ? (v) => linkBeirando(v, ut, { cel: q.cel, alcel: q.alk || null, alias: a, nev: fajlNev(ut) }) : async () => ({ szoveg: `${q.cel}${q.alk ? `#${q.alk}` : ''}|${a}` }),
  }));
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
    case 'fajl': {
      let hianyzok: string[] = [];
      if (q.cel.trim()) {
        try {
          hianyzok = await linkek.feloldatlanSzovegek();
        } catch {
          hianyzok = [];
        }
      }
      return fajlElemek(view, f, q, aliasok, hianyzok);
    }
    case 'fejezet':
      return fejezetElemek(view, q);
    case 'fejezetMind':
      return mindenFejezetElemek(q);
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

/** Egy másik jegyzet id nélküli blokkjának azonosítót ír (a `Dokumentum` útján: hash-védett mentés, a nyitott szerkesztők
 *  élőben megkapják, ugyanaz a pillanatkép-szabály, mint a gépelésnél). → az új azonosító, vagy `null` (a hiba értesítésként
 *  megjelent, a link nem íródik be). Ha a jegyzet közben megváltozott, a blokkot a sorának szövege alapján keresi újra. */
export async function masikBlokkIdIr(m: { ut: string; szoveg: string; index: number }): Promise<string | null> {
  let dok;
  try {
    dok = await szerkesztok.dokumentumok.megnyit(m.ut);
  } catch (e) {
    ertesitesek.ertesit({ szint: 'hiba', cim: t('A jegyzet nem nyitható meg'), szoveg: e instanceof ApiHiba ? e.message : String(e) });
    return null;
  }
  const elavult = (): null => {
    ertesitesek.ertesit({ szint: 'figyelmeztetes', cim: t('A jegyzet közben megváltozott'), szoveg: t('A lista frissül, próbáld újra.'), idotartam: 4000 });
    return null;
  };
  try {
    if (dok.csakOlvashato || dok.allapot === 'utkozes' || dok.allapot === 'eltunt') {
      ertesitesek.ertesit({ szint: 'figyelmeztetes', cim: t('A jegyzet most nem írható'), szoveg: dok.csakOlvashato ?? m.ut });
      return null;
    }
    const kezdo = masikAllapot(m.szoveg);
    const eredeti = blokkok(kezdo)[m.index];
    if (!eredeti || eredeti.id || eredeti.idMod !== 'sorveg') return elavult();
    const sor = kezdo.doc.line(eredeti.elsoSor).text;
    const mai = dok.szoveg.toString();
    const allapot = mai === m.szoveg ? kezdo : masikAllapot(mai);
    let bl = mai === m.szoveg ? eredeti : undefined;
    if (!bl) {
      const egyezok = blokkok(allapot).filter((x) => !x.id && x.idMod === 'sorveg' && allapot.doc.line(x.elsoSor).text === sor);
      if (egyezok.length !== 1) return elavult();
      bl = egyezok[0];
    }
    const r = idBeir(allapot, bl, ujBlokkId(allapot));
    if (!r?.szerkesztes) return elavult();
    const cs = allapot.update({ changes: r.szerkesztes.changes }).changes;
    dok.valtozott(cs, cs.apply(dok.szoveg), null, true); // nyitott szerkesztőnél az előzménybe kerül: a ⌘Z visszahozza
    const eredmeny = await dok.ment();
    if (!eredmeny.ok) {
      ertesitesek.ertesit({ szint: 'hiba', cim: t('Az azonosító nem mentődött'), szoveg: dok.hiba ?? m.ut });
      return null;
    }
    return r.id;
  } catch (e) {
    ertesitesek.ertesit({ szint: 'hiba', cim: t('Az azonosító nem írható be'), szoveg: e instanceof Error ? e.message : String(e) });
    return null;
  } finally {
    await szerkesztok.dokumentumok.elenged(dok); // a nyitott szerkesztő-nézet tartja életben, különben lezár és kikerül
  }
}

/** A kiválasztott elem beírása a gépelt lekérdezés helyére; a meglévő záró `]]` után áll a kurzor. Az aktuális jegyzet id nélküli
 *  blokkjánál az azonosító beírása ugyanabban a tranzakcióban történik (egy ⌘Z visszavonja mindkettőt); másik jegyzetnél az
 *  azonosítót előbb abba a jegyzetbe menti. „Use [[Wikilinks]]” kikapcsolva a `[[…` egésze markdown-linkre cserélődik. */
async function alkalmaz(view: EditorView, e: Elem): Promise<void> {
  const a = view.state.field(kiegeszitesMezo, false);
  if (!a) return;
  const eredetiDoc = view.state.doc;
  const q = lekerdezesElemez(view.state.sliceDoc(a.from, view.state.selection.main.head));
  let idSzerk: { id: string; changes: ChangeSpec } | null = null;
  let id: string | undefined;
  if (e.idKell !== undefined) {
    const bl = blokkok(view.state)[e.idKell];
    const r = bl ? idBeir(view.state, bl, ujBlokkId(view.state)) : null;
    if (!r?.szerkesztes) return;
    idSzerk = { id: r.id, changes: r.szerkesztes.changes };
    id = r.id;
  } else if (e.masikIdKell) {
    const uj = await masikBlokkIdIr(e.masikIdKell);
    if (!uj || !menuk.has(view)) return;
    id = uj;
  }
  let eredmeny: Beirando | null;
  try {
    eredmeny = await e.beir(view, q, id);
  } catch {
    view.dispatch({ effects: zar.of(null) });
    return;
  }
  const b = view.state.field(kiegeszitesMezo, false);
  if (!eredmeny || !b || view.state.doc !== eredetiDoc) return; // közben gépelt: az új lekérdezésre vonatkozik
  const veg = view.state.selection.main.head;
  const zaroVan = view.state.sliceDoc(veg, veg + 2) === ']]';
  const valtozasok: ChangeSpec[] = [];
  if (idSzerk) valtozasok.push(idSzerk.changes);
  const link =
    eredmeny.md !== undefined
      ? { from: b.from - (b.beagyazas ? 3 : 2), to: zaroVan ? veg + 2 : veg, insert: eredmeny.md }
      : { from: b.from, to: zaroVan ? veg + 2 : veg, insert: `${eredmeny.szoveg}]]` };
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
    cimke: t('Link beszúrása'),
    ures: t('Nincs találat'),
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
        view.plugin(ujranyitas)?.elvet(a.from);
        view.dispatch({ effects: [zar.of(null), elvet.of(null)] });
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
  if (text !== '[' || view.state.readOnly) return false;
  if (from !== to) return kijelolesBurkol(view, from, to);
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

/** A `[` gépelése kijelöléssel (nem veszik el a kijelölt szöveg): először `[kijelölt]`, a második `[` `[[kijelölt]]`-re bővít, és a
 *  kijelölt szöveg lesz a menü lekérdezése. Többsoros kijelölésre és `[`/`]`-t tartalmazóra az alap viselkedés marad. */
function kijelolesBurkol(view: EditorView, from: number, to: number): boolean {
  const s = view.state;
  if (s.doc.lineAt(from).number !== s.doc.lineAt(to).number || /[[\]]/.test(s.sliceDoc(from, to)) || !linkNyithato(s, from)) return false;
  const elozo = s.sliceDoc(from - 1, from);
  if (elozo === '[' && s.sliceDoc(to, to + 1) === ']' && s.sliceDoc(from - 2, from - 1) !== '[') {
    const beagyazas = s.sliceDoc(from - 2, from - 1) === '!';
    view.dispatch({
      changes: [{ from, insert: '[' }, { from: to, insert: ']' }],
      selection: { anchor: to + 1 },
      effects: nyit.of({ from: from + 1, beagyazas }),
      userEvent: 'input.type',
    });
    return true;
  }
  view.dispatch({
    changes: [{ from, insert: '[' }, { from: to, insert: ']' }],
    selection: { anchor: from + 1, head: to + 1 },
    userEvent: 'input.type',
  });
  return true;
}

/** A `p` előtti, a sorban álló, még le nem zárt `[[` / `![[` helye (egy már meglévő link belseje), vagy `null`. */
export function nyitottLink(state: EditorState, p: number): Allapot | null {
  const sor = state.doc.lineAt(p);
  const elotte = state.sliceDoc(sor.from, p);
  const i = elotte.lastIndexOf('[[');
  if (i < 0 || elotte.slice(i + 2).includes(']')) return null;
  return { from: sor.from + i + 2, beagyazas: i > 0 && elotte[i - 1] === '!' };
}

function frontmatterben(state: EditorState, p: number): boolean {
  const fa = syntaxTree(state);
  for (let n: ReturnType<typeof fa.resolveInner> | null = fa.resolveInner(p, -1); n; n = n.parent) if (n.name === 'Frontmatter') return true;
  return false;
}

/** Egy meglévő `[[…` belsejében gépelve (vagy törölve) a menü újra előjön — a kiindulás a kurzor előtti szöveg, nem csak a
 *  `[` leütése. Az Esc az adott linken kikapcsolja, amíg a kurzor ki nem lép belőle; kódban, képletben és a frontmatterben nincs. */
const ujranyitas = ViewPlugin.fromClass(
  class {
    private mellozott: number | null = null;
    constructor(readonly view: EditorView) {}
    elvet(pos: number): void {
      this.mellozott = pos;
    }
    update(u: ViewUpdate): void {
      if (this.mellozott !== null) this.mellozott = u.changes.mapPos(this.mellozott, -1);
      if (!u.docChanged || u.state.field(kiegeszitesMezo, false)) return;
      if (!u.transactions.some((tr) => tr.isUserEvent('input.type') || tr.isUserEvent('delete'))) return;
      queueMicrotask(() => this.probal()); // az update közben nem küldhető tranzakció
    }
    private probal(): void {
      const v = this.view;
      if (!v.dom.isConnected || v.state.readOnly || v.state.field(kiegeszitesMezo, false)) return;
      const r = v.state.selection.main;
      if (!r.empty) return;
      const c = nyitottLink(v.state, r.head);
      if (!c) {
        this.mellozott = null;
        return;
      }
      if (this.mellozott === c.from || !linkNyithato(v.state, r.head) || frontmatterben(v.state, r.head)) return;
      v.dispatch({ effects: nyit.of(c) });
    }
  },
);

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
  return [kiegeszitesMezo, tooltip, billentyuk, gepeles, parTorles, ujranyitas];
}

/** A tesztekhez és a parancsokhoz: a menü megnyitása a kurzornál (beír egy `[[]]`-t). Kijelölt (egysoros) szövegnél a kijelölés
 *  nem vész el: `[[kijelölt]]` lesz, és a kijelölt szöveg a menü lekérdezése; egyéb kijelölésnél a link a kijelölés mögé kerül. */
export function linkBeszur(view: EditorView, beagyazas = false): boolean {
  const r = view.state.selection.main;
  if (view.state.readOnly || !linkNyithato(view.state, r.head)) return false;
  const elo = beagyazas ? '![[' : '[[';
  const kijelolt = r.empty ? '' : view.state.sliceDoc(r.from, r.to);
  if (kijelolt && !kijelolt.includes('\n') && !/[[\]]/.test(kijelolt)) {
    view.dispatch({
      changes: { from: r.from, to: r.to, insert: `${elo}${kijelolt}]]` },
      selection: { anchor: r.from + elo.length + kijelolt.length },
      effects: nyit.of({ from: r.from + elo.length, beagyazas }),
      userEvent: 'input.type',
    });
    return true;
  }
  const hely = r.empty ? r.head : r.to; // a kijelölt szöveg érintetlen marad
  view.dispatch({
    changes: { from: hely, insert: `${elo}]]` },
    selection: { anchor: hely + elo.length },
    effects: nyit.of({ from: hely + elo.length, beagyazas }),
    userEvent: 'input.type',
  });
  return true;
}

export const kiegeszitesFrissit = frissit;
