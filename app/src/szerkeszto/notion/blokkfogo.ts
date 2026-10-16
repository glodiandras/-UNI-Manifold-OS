// A blokkfogó (⋮⋮) a bal margón (C09): az egér alatti blokk mellett jelenik meg. Húzásra a blokk a
// Markdown-szerkezet szerint mozog (a listaelem a gyerekeivel együtt), kattintásra menü nyílik: átalakítás,
// duplikálás, törlés, mozgatás fel/le, link másolása a blokkra (`^id` generálással). A húzás saját
// pointer-eseményekkel megy (a HTML5 húzás a WKWebView-ban megbízhatatlan); billentyűzetről Alt+↑/↓ és a
// parancsok érik el ugyanezt. A logika a `muveletek.ts`-ben él, itt csak a geometria és a DOM van.

import { t, tk } from '../../lib/i18n';
import { isolateHistory } from '@codemirror/commands';
import { type EditorState, type Extension, Facet, Prec } from '@codemirror/state';
import { EditorView, ViewPlugin, type ViewUpdate } from '@codemirror/view';
import { ikonElem } from '../../lib/ikon/ikonElem';
import {
  Code,
  ArrowDown,
  ArrowUp,
  Heading1,
  Heading2,
  Heading3,
  GripVertical,
  Link2,
  List,
  ListOrdered,
  ListTodo,
  Pilcrow,
  Quote,
  Trash2,
  CopyPlus,
  Replace,
} from '../../lib/ikon/ikonok';
import { ertesitesek } from '../../lib/ertesites/ertesites.svelte';
import { calloutTipusok } from '../renderelok/callout';
import { vagolapra } from '../vagolap';
import { type Blokk, blokkEleje, blokkSorban, blokkok, gyoker, leszarmazott, testverek } from './blokkmodell';
import { lebegoMenu, type MenuElem } from './menu';
import {
  atalakit,
  atalakithato,
  type AtalakitCel,
  blokkLink,
  type Cel,
  duplikal,
  idBeir,
  mozgat,
  torol,
  ujBlokkId,
} from './muveletek';

/** A jegyzet neve a blokklinkhez (`[[Név#^id]]`); a szerkesztő komponens adja: a core legrövidebb egyértelmű
 *  cél-szövege (C10, L42), nem saját szabály. */
export const linkNevForras = Facet.define<() => string | Promise<string>, () => string | Promise<string>>({
  combine: (v) => v[0] ?? (() => ''),
});

// ---------------------------------------------------------------------- csendes alkalmazás

function alkalmaz(view: EditorView, sz: { changes: unknown; selection: { anchor: number; head?: number } } | null, esemeny: string): boolean {
  if (!sz) return false;
  // a blokkművelet saját ⌘Z-lépés: a `delete.blokk` különben összeolvadna az előtte tett Backspace-szel (T170)
  view.dispatch({ changes: sz.changes as never, selection: sz.selection, userEvent: esemeny, scrollIntoView: true, annotations: isolateHistory.of('full') });
  return true;
}

interface BlokkAzon {
  elsoSor: number;
  tipus: Blokk['tipus'];
}

const azon = (b: Blokk): BlokkAzon => ({ elsoSor: b.elsoSor, tipus: b.tipus });

function keres(bl: readonly Blokk[], a: BlokkAzon): Blokk | null {
  return bl.find((b) => b.elsoSor === a.elsoSor && b.tipus === a.tipus) ?? null;
}

// ---------------------------------------------------------------------- mozgatás billentyűzetről

/** A kurzort tartalmazó (legbelső) blokk. */
export function kurzorBlokk(state: EditorState): Blokk | null {
  return blokkSorban(blokkok(state), state.doc.lineAt(state.selection.main.head).number);
}

/** A blokk szomszédja egy lépéssel fel/le: ugyanazon lista testvére, legfelső szinten az előző/következő
 *  egység (a lista egy egység). Üres, ha nincs hová. */
export function szomszedCel(bl: readonly Blokk[], b: Blokk, irany: -1 | 1): Cel | null {
  if (b.lista) {
    const tv = testverek(bl, b);
    const i = tv.findIndex((x) => x.index === b.index);
    const sz = tv[i + irany];
    if (sz) return { blokk: sz, hely: irany < 0 ? 'elott' : 'utan' };
    return null;
  }
  // legfelső szintű egységek: a nem listaelem blokkok és a listák (első elemmel képviselve)
  const egysegek = bl.filter((x) => x.szulo === null && (!x.lista || testverek(bl, x)[0].index === x.index));
  const i = egysegek.findIndex((x) => x.index === b.index);
  const sz = egysegek[i + irany];
  if (!sz) return null;
  if (sz.lista) {
    const tv = testverek(bl, sz);
    return irany < 0 ? { blokk: tv[0], hely: 'elott' } : { blokk: tv[tv.length - 1], hely: 'utan' };
  }
  return { blokk: sz, hely: irany < 0 ? 'elott' : 'utan' };
}

/** A kurzor blokkja egy lépést fel/le (Alt+↑/↓, parancs). */
export function blokkLep(view: EditorView, irany: -1 | 1): boolean {
  if (view.state.readOnly) return false;
  const bl = blokkok(view.state);
  const b = blokkSorban(bl, view.state.doc.lineAt(view.state.selection.main.head).number);
  if (!b) return false;
  const cel = szomszedCel(bl, b, irany);
  if (!cel) return true; // a határon: a billentyű el van fogyasztva, nincs sorcsere
  alkalmaz(view, mozgat(view.state, bl, b, cel), 'move.blokk');
  return true;
}

export function blokkDuplikal(view: EditorView): boolean {
  const bl = blokkok(view.state);
  const b = blokkSorban(bl, view.state.doc.lineAt(view.state.selection.main.head).number);
  return !!b && !view.state.readOnly && alkalmaz(view, duplikal(view.state, bl, b), 'input.blokk');
}

export function blokkTorol(view: EditorView): boolean {
  const bl = blokkok(view.state);
  const b = blokkSorban(bl, view.state.doc.lineAt(view.state.selection.main.head).number);
  return !!b && !view.state.readOnly && alkalmaz(view, torol(view.state, bl, b), 'delete.blokk');
}

/** A blokk linkjének másolása (`^id` beírásával, ha kell). Igaz, ha sikerült. */
export async function blokkLinkMasol(view: EditorView, a?: BlokkAzon): Promise<boolean> {
  const nev = await view.state.facet(linkNevForras)();   // a core kéri: a blokk helyét utána olvassuk
  if (!nev) return false;
  const bl = blokkok(view.state);
  const b = a ? keres(bl, a) : blokkSorban(bl, view.state.doc.lineAt(view.state.selection.main.head).number);
  if (!b) return false;
  const sorSzoveg = view.state.doc.line(b.elsoSor).text;
  let id = b.id;
  if (b.idMod !== 'nincs' && !id) {
    if (view.state.readOnly) {
      ertesitesek.ertesit({ szint: 'figyelmeztetes', cim: t('A jegyzet csak olvasható'), szoveg: t('A blokkazonosító nem írható be.') });
      return false;
    }
    const r = idBeir(view.state, b, ujBlokkId(view.state));
    if (r?.szerkesztes) alkalmaz(view, r.szerkesztes, 'input.blokkid');
    id = r?.id ?? null;
  }
  const link = blokkLink(nev, b, id, sorSzoveg);
  if (!link) return false;
  const ok = await vagolapra(link);
  ertesitesek.ertesit(
    ok
      ? { szint: 'siker', cim: t('Link másolva'), szoveg: link, idotartam: 3000 }
      : { szint: 'hiba', cim: t('A vágólapra másolás nem sikerült'), szoveg: link },
  );
  return ok;
}

// ---------------------------------------------------------------------- menü

const ATALAKITAS: { id: string; nev: string; ikon: MenuElem['ikon']; cel: AtalakitCel; jelzo?: string }[] = [
  { id: 'szoveg', nev: tk('Szöveg|beszuras'), ikon: Pilcrow, cel: { tipus: 'szoveg' } },
  { id: 'h1', nev: tk('Fejezet 1'), ikon: Heading1, cel: { tipus: 'fejezet', szint: 1 }, jelzo: '#' },
  { id: 'h2', nev: tk('Fejezet 2'), ikon: Heading2, cel: { tipus: 'fejezet', szint: 2 }, jelzo: '##' },
  { id: 'h3', nev: tk('Fejezet 3'), ikon: Heading3, cel: { tipus: 'fejezet', szint: 3 }, jelzo: '###' },
  { id: 'lista', nev: tk('Felsorolás|beszuras'), ikon: List, cel: { tipus: 'lista' }, jelzo: '-' },
  { id: 'szamozott', nev: tk('Számozott lista|beszuras'), ikon: ListOrdered, cel: { tipus: 'szamozott' }, jelzo: '1.' },
  { id: 'feladat', nev: tk('Feladat|beszuras'), ikon: ListTodo, cel: { tipus: 'feladat' }, jelzo: '[ ]' },
  { id: 'idezet', nev: tk('Idézet|beszuras'), ikon: Quote, cel: { tipus: 'idezet' }, jelzo: '>' },
  { id: 'kod', nev: tk('Kódblokk|beszuras'), ikon: Code, cel: { tipus: 'kod' }, jelzo: '```' },
];

function aktualis(b: Blokk, cel: AtalakitCel): boolean {
  switch (cel.tipus) {
    case 'szoveg':
      return b.tipus === 'bekezdes';
    case 'fejezet':
      return b.tipus === 'fejezet' && b.szint === cel.szint;
    case 'lista':
      return !!b.lista && !b.lista.rendezett && b.lista.feladat === null;
    case 'szamozott':
      return !!b.lista?.rendezett && b.lista.feladat === null;
    case 'feladat':
      return !!b.lista && b.lista.feladat !== null;
    case 'idezet':
      return b.tipus === 'idezet';
    case 'kod':
      return b.tipus === 'kod';
    default:
      return false;
  }
}

/** A blokk menüjének elemei; a műveletek az `akciok` térképbe kerülnek (azonosító szerint). */
export function blokkMenuElemek(view: EditorView, b: Blokk, akciok: Map<string, () => void>): MenuElem[] {
  const sorok = view.state.doc.toJSON();
  const iras = !view.state.readOnly;
  const bl = blokkok(view.state);
  const a = azon(b);
  const friss = () => keres(blokkok(view.state), a);
  const tevekenyseg = (id: string, f: (v: EditorView, x: Blokk) => void) =>
    akciok.set(id, () => {
      const x = friss();
      if (x) f(view, x);
    });

  const elemek: MenuElem[] = [];

  const atalakitasElemek = (): MenuElem[] => {
    const ki: MenuElem[] = ATALAKITAS.map((at) => {
      const id = `atal-${at.id}`;
      tevekenyseg(id, (v, x) => {
        alkalmaz(v, atalakit(v.state, x, at.cel), 'input.atalakit');
      });
      return {
        id,
        nev: t(at.nev),
        ikon: at.ikon,
        jelzo: at.jelzo,
        kijelolt: aktualis(b, at.cel),
        letiltva: !iras || (!atalakithato(sorok, b, at.cel) && !aktualis(b, at.cel)),
      };
    });
    ki.push({
      id: 'atal-callout',
      nev: t('Callout|beszuras'),
      ikon: Replace,
      kijelolt: b.tipus === 'callout',
      letiltva: !iras || !(atalakithato(sorok, b, { tipus: 'callout', callout: 'note' }) || b.tipus === 'callout'),
      almenu: () =>
        calloutTipusok.lista().map((tip) => {
          const nev = tip.nevek[0];
          const id = `callout-${nev}`;
          tevekenyseg(id, (v, x) => {
            alkalmaz(v, atalakit(v.state, x, { tipus: 'callout', callout: nev }), 'input.atalakit');
          });
          return {
            id,
            nev: tip.cimek[nev] ? t(tip.cimek[nev]) : nev,
            ikon: tip.ikon,
            jelzo: `[!${nev}]`,
            kijelolt: b.tipus === 'callout' && b.calloutTipus?.toLowerCase() === nev,
            letiltva: b.tipus === 'callout' ? false : !atalakithato(sorok, b, { tipus: 'callout', callout: nev }),
          };
        }),
    });
    return ki;
  };

  const atalakithatoBarmi = ATALAKITAS.some((t) => atalakithato(sorok, b, t.cel)) || atalakithato(sorok, b, { tipus: 'callout', callout: 'note' }) || b.tipus === 'callout';
  elemek.push({
    id: 'atalakitas',
    nev: t('Átalakítás'),
    ikon: Replace,
    almenu: atalakitasElemek,
    letiltva: !iras || !atalakithatoBarmi,
  });
  tevekenyseg('duplikal', (v, x) => alkalmaz(v, duplikal(v.state, blokkok(v.state), x), 'input.blokk'));
  elemek.push({ id: 'duplikal', nev: t('Duplikálás'), ikon: CopyPlus, letiltva: !iras });
  akciok.set('fel', () => {
    const x = friss();
    const c = x && szomszedCel(blokkok(view.state), x, -1);
    if (x && c) alkalmaz(view, mozgat(view.state, blokkok(view.state), x, c), 'move.blokk');
  });
  akciok.set('le', () => {
    const x = friss();
    const c = x && szomszedCel(blokkok(view.state), x, 1);
    if (x && c) alkalmaz(view, mozgat(view.state, blokkok(view.state), x, c), 'move.blokk');
  });
  elemek.push({ id: 'fel', nev: t('Mozgatás fel'), ikon: ArrowUp, jelzo: '⌥↑', letiltva: !iras || !b.mozgathato || !szomszedCel(bl, b, -1) });
  elemek.push({ id: 'le', nev: t('Mozgatás le'), ikon: ArrowDown, jelzo: '⌥↓', letiltva: !iras || !b.mozgathato || !szomszedCel(bl, b, 1) });
  akciok.set('link', () => void blokkLinkMasol(view, a));
  elemek.push({
    id: 'link',
    nev: t('Link másolása a blokkra'),
    ikon: Link2,
    leiras: b.tipus === 'fejezet' ? t('Fejezetlink: [[Név#Cím]]')
      : b.idMod === 'nincs' ? t('A listaelem saját sora nem szöveg (pl. kódkerítés): ide nem kerülhet blokkazonosító')
      : t('Blokkazonosító (^id) kerül a blokk végére, ha még nincs'),
    letiltva: (b.idMod === 'nincs' && b.tipus !== 'fejezet') || (b.idMod !== 'nincs' && !b.id && !iras),
  });
  tevekenyseg('torol', (v, x) => alkalmaz(v, torol(v.state, blokkok(v.state), x), 'delete.blokk'));
  elemek.push({ id: 'torol', nev: t('Törlés'), ikon: Trash2, veszely: true, letiltva: !iras });
  return elemek;
}

/** A blokk menüjének megnyitása a kurzornál (parancs). */
export function blokkMenuParancs(view: EditorView): boolean {
  const b = kurzorBlokk(view.state);
  if (!b) return false;
  const c = view.coordsAtPos(b.from) ?? view.contentDOM.getBoundingClientRect();
  const akciok = new Map<string, () => void>();
  lebegoMenu(view, c.left, c.bottom + 4, blokkMenuElemek(view, b, akciok), akciok, t('Blokk|menu'));
  return true;
}

// ---------------------------------------------------------------------- húzás: célpontok

interface Celpont {
  cel: Cel;
  /** a célvonal helye a dokumentumban (y) és a bal széle a képernyőn (x) */
  y: number;
  x: number;
}

const GYEREK_KUSZOB = 24;

function savAlja(view: EditorView, b: Blokk): number {
  const sor = b.lista ? b.szovegVegSor : b.utolsoSor;
  return view.lineBlockAt(view.state.doc.line(sor).to).bottom;
}

function savTeteje(view: EditorView, b: Blokk): number {
  // a PDF-kiemelésnél a jelölősortól: a blokk elé ejtett blokk oda kerül (muveletek.docCelPozicio)
  return view.lineBlockAt(view.state.doc.line(blokkEleje(b)).from).top;
}

function blokkBal(view: EditorView, b: Blokk, szint: number): number {
  const c = view.coordsAtPos(b.from + (b.lista ? b.lista.behuzas.length : 0), 1);
  const tartalom = view.contentDOM.getBoundingClientRect();
  const stilus = getComputedStyle(view.contentDOM);
  const alap = tartalom.left + (parseFloat(stilus.paddingLeft) || 0);
  return (c ? c.left : alap) + szint;
}

/** Érvényes-e a cél a forrásra (előzetesen, a szöveg olvasása nélkül). */
export function celErvenyes(bl: readonly Blokk[], src: Blokk, cel: Cel): boolean {
  if (cel.blokk.index === src.index || leszarmazott(bl, cel.blokk, src)) return false;
  if (!src.mozgathato || (!cel.blokk.mozgathato && cel.hely !== 'elott')) return false;     // T161 (C31)
  if (src.lista) return !!cel.blokk.lista;
  if (cel.hely === 'gyerek') return false;
  return !cel.blokk.lista || cel.blokk.szulo === null;
}

function celPont(view: EditorView, bl: readonly Blokk[], src: Blokk, clientX: number, clientY: number): Celpont | null {
  const doc = view.state.doc;
  const y = clientY - view.documentTop;
  const lb = view.lineBlockAtHeight(y);
  const sor = doc.lineAt(Math.min(lb.from, doc.length)).number;
  let b = blokkSorban(bl, sor);
  if (!b) {
    // üres sor két blokk között: a közelebbihez igazodik
    const kov = bl.find((x) => x.elsoSor > sor);
    let elozo: Blokk | null = null;
    for (const x of bl) if (x.utolsoSor < sor && (!elozo || x.utolsoSor >= elozo.utolsoSor)) elozo = x;
    const kozep = elozo ? savAlja(view, elozo) : -Infinity;
    const veg = kov ? savTeteje(view, kov) : Infinity;
    b = Math.abs(y - kozep) <= Math.abs(veg - y) ? elozo : kov ?? null;
    if (!b) return null;
  }
  // legfelső szintű forrásnál a lista egy egység: a pont a lista egészéhez igazodik
  if (!src.lista && b.lista) {
    const tv = testverek(bl, gyoker(bl, b));
    const teteje = savTeteje(view, tv[0]);
    const alja = view.lineBlockAt(view.state.doc.line(tv[tv.length - 1].utolsoSor).to).bottom;
    const felso = y < (teteje + alja) / 2;
    const cel: Cel = felso ? { blokk: tv[0], hely: 'elott' } : { blokk: tv[tv.length - 1], hely: 'utan' };
    if (!celErvenyes(bl, src, cel)) return null;
    const bal = blokkBal(view, tv[0], 0);
    return { cel, y: felso ? teteje : alja, x: bal };
  }
  const teteje = savTeteje(view, b);
  const alja = savAlja(view, b);
  const felso = y < (teteje + alja) / 2;
  let cel: Cel;
  let vonal: number;
  let szint = 0;
  if (felso) {
    cel = { blokk: b, hely: 'elott' };
    vonal = teteje;
  } else if (b.lista && b.gyerekek.length) {
    const elsoGyerek = bl[b.gyerekek[0]];
    cel = { blokk: elsoGyerek, hely: 'elott' };
    vonal = savTeteje(view, elsoGyerek);
    b = elsoGyerek;
  } else if (b.lista && src.lista && clientX > blokkBal(view, b, 0) + GYEREK_KUSZOB) {
    cel = { blokk: b, hely: 'gyerek' };
    vonal = alja;
    szint = GYEREK_KUSZOB;
  } else {
    cel = { blokk: b, hely: 'utan' };
    vonal = b.lista ? alja : view.lineBlockAt(doc.line(b.utolsoSor).to).bottom;
  }
  if (!celErvenyes(bl, src, cel)) return null;
  return { cel, y: vonal, x: blokkBal(view, b, szint) };
}

// ---------------------------------------------------------------------- a fogó (ViewPlugin)

const FOGO_MERET = 24;
const KUSZOB = 4;

class BlokkFogo {
  private readonly fogo = document.createElement('button');
  private readonly vonal = document.createElement('div');
  private readonly szellem = document.createElement('div');
  private aktiv: BlokkAzon | null = null;
  private cache: { doc: unknown; bl: Blokk[] } | null = null;
  private huzas: { src: Blokk; x0: number; y0: number; megkezdve: boolean; cel: Celpont | null; x: number; y: number } | null = null;
  private gorget = 0;
  private menuBezar: (() => void) | null = null;
  private readonly mozog = (e: MouseEvent) => this.egerMozog(e);
  private readonly elhagy = () => {
    if (!this.huzas && !this.menuBezar) this.rejt();
  };
  private readonly gomb = () => {
    if (!this.huzas) this.rejt();
  };

  constructor(private readonly view: EditorView) {
    const f = this.fogo;
    f.type = 'button';
    f.className = 'nt-fogo';
    f.tabIndex = -1;
    f.hidden = true;
    f.setAttribute('aria-label', t('Blokk: húzás vagy menü'));
    f.title = t('Húzás: áthelyezés · kattintás: menü');
    f.appendChild(ikonElem(GripVertical, 16));
    f.addEventListener('pointerdown', (e) => this.lenyom(e));
    f.addEventListener('pointermove', (e) => this.huz(e));
    f.addEventListener('pointerup', (e) => this.felenged(e));
    f.addEventListener('pointercancel', () => this.megszakit());
    f.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        this.menuMegnyit();
      }
    });
    this.vonal.className = 'nt-celvonal';
    this.vonal.hidden = true;
    this.szellem.className = 'nt-szellem';
    this.szellem.hidden = true;
    view.scrollDOM.append(f, this.vonal);
    document.body.appendChild(this.szellem);
    view.dom.addEventListener('mousemove', this.mozog);
    view.dom.addEventListener('mouseleave', this.elhagy);
    view.contentDOM.addEventListener('keydown', this.gomb);
    view.contentDOM.addEventListener('mousedown', this.gomb);
  }

  update(u: ViewUpdate): void {
    if (u.docChanged && !this.huzas) this.rejt();
    else if ((u.geometryChanged || u.heightChanged || u.selectionSet) && this.aktiv && !this.fogo.hidden && !this.huzas) {
      // a blokkok magassága változhat (aktív egység, widget kirajzolása): a fogó a blokkal marad
      queueMicrotask(() => {
        const b = this.aktiv && keres(this.blokkok(), this.aktiv);
        if (b && !this.fogo.hidden) this.pozicional(b);
      });
    }
  }

  destroy(): void {
    this.megszakit();
    this.menuBezar?.();
    this.view.dom.removeEventListener('mousemove', this.mozog);
    this.view.dom.removeEventListener('mouseleave', this.elhagy);
    this.view.contentDOM.removeEventListener('keydown', this.gomb);
    this.view.contentDOM.removeEventListener('mousedown', this.gomb);
    this.fogo.remove();
    this.vonal.remove();
    this.szellem.remove();
  }

  private blokkok(): Blokk[] {
    const doc = this.view.state.doc;
    if (!this.cache || this.cache.doc !== doc) this.cache = { doc, bl: blokkok(this.view.state) };
    return this.cache.bl;
  }

  private rejt(): void {
    this.fogo.hidden = true;
    this.aktiv = null;
  }

  private egerMozog(e: MouseEvent): void {
    if (this.huzas || this.menuBezar || this.view.state.readOnly) return;
    const c = this.view.contentDOM.getBoundingClientRect();
    const felso = this.view.scrollDOM.getBoundingClientRect();
    if (e.clientY < felso.top || e.clientY > felso.bottom) return;
    // a margón és a szövegen is a legközelebbi sor blokkja
    const x = Math.min(Math.max(e.clientX, c.left + 40), c.right - 8);
    const pos = this.view.posAtCoords({ x, y: e.clientY }, false);
    if (pos === null) return;
    const sor = this.view.state.doc.lineAt(pos).number;
    const b = blokkSorban(this.blokkok(), sor);
    if (!b) return;
    if (this.aktiv && this.aktiv.elsoSor === b.elsoSor && this.aktiv.tipus === b.tipus && !this.fogo.hidden) return;
    this.aktiv = azon(b);
    this.pozicional(b);
  }

  private pozicional(b: Blokk): void {
    const v = this.view;
    const scroller = v.scrollDOM.getBoundingClientRect();
    const tartalom = v.contentDOM.getBoundingClientRect();
    // a fogó az első sor szövegének közepéhez igazodik (a fejezet fölötti térköz nem számít)
    const c = v.coordsAtPos(b.from, 1);
    let kozep: number;
    if (c) kozep = c.top + Math.min(c.bottom - c.top, 26) / 2;
    else {
      const lb = v.lineBlockAt(b.from);
      kozep = v.documentTop + lb.top + Math.min(lb.height, 26) / 2;
    }
    const top = kozep - FOGO_MERET / 2 - scroller.top + v.scrollDOM.scrollTop;
    const left = tartalom.left - scroller.left + v.scrollDOM.scrollLeft + 4;
    this.fogo.style.top = `${top}px`;
    this.fogo.style.left = `${left}px`;
    this.fogo.hidden = false;
  }

  // ------------------------------------------------------------ húzás

  private lenyom(e: PointerEvent): void {
    if (e.button !== 0 || !this.aktiv) return;
    const b = keres(this.blokkok(), this.aktiv);
    if (!b) return;
    e.preventDefault();
    this.fogo.setPointerCapture?.(e.pointerId);
    this.huzas = { src: b, x0: e.clientX, y0: e.clientY, megkezdve: false, cel: null, x: e.clientX, y: e.clientY };
    document.addEventListener('keydown', this.esc, true);
  }

  private readonly esc = (e: KeyboardEvent) => {
    if (e.key === 'Escape' && this.huzas) {
      e.preventDefault();
      e.stopPropagation();
      this.megszakit();
    }
  };

  private huz(e: PointerEvent): void {
    const h = this.huzas;
    if (!h) return;
    h.x = e.clientX;
    h.y = e.clientY;
    if (!h.megkezdve) {
      if (Math.hypot(e.clientX - h.x0, e.clientY - h.y0) < KUSZOB) return;
      h.megkezdve = true;
      this.fogo.classList.add('huz');
      this.view.dom.classList.add('nt-huzas');
      this.szellem.textContent = this.view.state.doc.line(h.src.elsoSor).text.slice(0, 48) || '…';
      this.szellem.hidden = false;
      this.gorgetKor();
    }
    this.szellem.style.left = `${e.clientX + 14}px`;
    this.szellem.style.top = `${e.clientY + 10}px`;
    this.celFrissit();
  }

  private celFrissit(): void {
    const h = this.huzas;
    if (!h) return;
    h.cel = celPont(this.view, this.blokkok(), h.src, h.x, h.y);
    if (!h.cel) {
      this.vonal.hidden = true;
      return;
    }
    const scroller = this.view.scrollDOM.getBoundingClientRect();
    const tartalom = this.view.contentDOM.getBoundingClientRect();
    const jobb = tartalom.right - parseFloat(getComputedStyle(this.view.contentDOM).paddingRight || '0');
    this.vonal.style.top = `${this.view.documentTop + h.cel.y - scroller.top + this.view.scrollDOM.scrollTop - 1}px`;
    this.vonal.style.left = `${h.cel.x - scroller.left + this.view.scrollDOM.scrollLeft}px`;
    this.vonal.style.width = `${Math.max(40, jobb - h.cel.x)}px`;
    this.vonal.hidden = false;
  }

  /** Húzás közben a szélhez közeli egér görgeti a szerkesztőt. */
  private gorgetKor(): void {
    const lep = () => {
      const h = this.huzas;
      if (!h?.megkezdve) return;
      const r = this.view.scrollDOM.getBoundingClientRect();
      const sav = 48;
      let d = 0;
      if (h.y < r.top + sav) d = -Math.ceil((r.top + sav - h.y) / 4);
      else if (h.y > r.bottom - sav) d = Math.ceil((h.y - (r.bottom - sav)) / 4);
      if (d) {
        this.view.scrollDOM.scrollTop += d;
        this.celFrissit();
      }
      this.gorget = requestAnimationFrame(lep);
    };
    this.gorget = requestAnimationFrame(lep);
  }

  private veg(): void {
    cancelAnimationFrame(this.gorget);
    document.removeEventListener('keydown', this.esc, true);
    this.fogo.classList.remove('huz');
    this.view.dom.classList.remove('nt-huzas');
    this.vonal.hidden = true;
    this.szellem.hidden = true;
  }

  private megszakit(): void {
    if (!this.huzas) return;
    this.veg();
    this.huzas = null;
  }

  private felenged(e: PointerEvent): void {
    const h = this.huzas;
    if (!h) return;
    if (this.fogo.hasPointerCapture?.(e.pointerId)) this.fogo.releasePointerCapture(e.pointerId);
    this.veg();
    this.huzas = null;
    if (!h.megkezdve) {
      this.menuMegnyit();
      return;
    }
    if (!h.cel) return;
    const bl = blokkok(this.view.state);
    const src = keres(bl, azon(h.src));
    const cel = keres(bl, azon(h.cel.cel.blokk));
    if (src && cel) alkalmaz(this.view, mozgat(this.view.state, bl, src, { blokk: cel, hely: h.cel.cel.hely }), 'move.blokk');
    this.rejt();
  }

  // ------------------------------------------------------------ menü

  private menuMegnyit(): void {
    if (!this.aktiv) return;
    const b = keres(this.blokkok(), this.aktiv);
    if (!b) return;
    const r = this.fogo.getBoundingClientRect();
    const akciok = new Map<string, () => void>();
    this.menuBezar?.();
    const bezar = lebegoMenu(this.view, r.right + 4, r.top, blokkMenuElemek(this.view, b, akciok), akciok, t('Blokk|menu'));
    this.menuBezar = () => {
      bezar(false);
      this.menuBezar = null;
    };
    // a menü saját bezárása után a fogó újra követi az egeret
    const figyel = new MutationObserver(() => {
      if (!document.querySelector('.nt-lebego')) {
        this.menuBezar = null;
        figyel.disconnect();
      }
    });
    figyel.observe(document.body, { childList: true });
  }
}

const fogoPlugin = ViewPlugin.fromClass(BlokkFogo);

/** Alt+↑/↓: a blokk mozgatása (felülírja a CodeMirror sormozgatását, amely a szerkezetet törné). */
const blokkBillentyuk = Prec.high(
  EditorView.domEventHandlers({
    keydown(e, view) {
      if (!e.altKey || e.metaKey || e.ctrlKey || e.shiftKey || e.isComposing) return false;
      if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return false;
      e.preventDefault();
      return blokkLep(view, e.key === 'ArrowUp' ? -1 : 1);
    },
  }),
);

/** A blokkfogó, a blokkmenü és a blokk-billentyűk a Live Preview-ban. */
export function blokkfogoBovitmeny(): Extension {
  return [fogoPlugin, blokkBillentyuk];
}
