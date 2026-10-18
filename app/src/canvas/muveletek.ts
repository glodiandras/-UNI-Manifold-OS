// A canvas modell-műveletei (C14, tiszta függvények): minden művelet új `Vaszon`-t ad, a régi érintetlen (a
// visszavonásé). A változatlan node/él ugyanaz az objektum marad, így az író csak a ténylegesen megváltozott
// mezőt írja át. A koordináta mindig egész (a spec szerint).

import { csomopontok, elek, ujId, type Csomopont, type El, type JsonObj, type Oldal, type Vaszon, type Veg } from './modell';
import { befoglalo, mozgatando, RACS, racsra, type Doboz, type Pont } from './geometria';

/** Egy objektum új változata: az `undefined` értékű kulcs kikerül, a többi a helyén marad vagy a végére kerül. */
function frissit<T extends JsonObj>(o: T, mezok: Partial<T>): T {
  const ki = { ...o } as JsonObj;
  for (const [k, v] of Object.entries(mezok)) {
    if (v === undefined) delete ki[k];
    else ki[k] = v;
  }
  return ki as T;
}

function csere(v: Vaszon, f: (c: Csomopont) => Csomopont): Vaszon {
  let valtozott = false;
  const nodes = csomopontok(v).map((c) => {
    const u = f(c);
    if (u !== c) valtozott = true;
    return u;
  });
  return valtozott ? { ...v, nodes } : v;
}

function elCsere(v: Vaszon, f: (e: El) => El): Vaszon {
  let valtozott = false;
  const edges = elek(v).map((e) => {
    const u = f(e);
    if (u !== e) valtozott = true;
    return u;
  });
  return valtozott ? { ...v, edges } : v;
}

/** A node-ok eltolása (egész lépéssel); a nem érintett node ugyanaz az objektum marad. */
export function mozgat(v: Vaszon, ids: Set<string>, dx: number, dy: number): Vaszon {
  const rx = Math.round(dx);
  const ry = Math.round(dy);
  if (!rx && !ry) return v;
  return csere(v, (c) => (ids.has(c.id) ? frissit(c, { x: c.x + rx, y: c.y + ry }) : c));
}

/** A node-ok helye a rácsra igazítva (a húzás végén, ha a rács be van kapcsolva). */
export function racsraIgazit(v: Vaszon, ids: Set<string>, racs = RACS): Vaszon {
  return csere(v, (c) => {
    if (!ids.has(c.id)) return c;
    const x = racsra(c.x, racs);
    const y = racsra(c.y, racs);
    return x === c.x && y === c.y ? c : frissit(c, { x, y });
  });
}

export function dobozBeallit(v: Vaszon, id: string, d: Doboz): Vaszon {
  return csere(v, (c) => {
    if (c.id !== id) return c;
    const uj = { x: Math.round(d.x), y: Math.round(d.y), width: Math.round(d.width), height: Math.round(d.height) };
    return uj.x === c.x && uj.y === c.y && uj.width === c.width && uj.height === c.height ? c : frissit(c, uj);
  });
}

/** Új node: a csoport az első nem-csoport node elé kerül (alul marad), a többi a tömb végére (legfelül). */
export function hozzaad(v: Vaszon, c: Csomopont): Vaszon {
  const lista = [...csomopontok(v)];
  if (c.type === 'group') {
    const k = lista.findIndex((x) => x.type !== 'group');
    lista.splice(k < 0 ? lista.length : k, 0, c);
  } else lista.push(c);
  return { ...v, nodes: lista };
}

export function elHozzaad(v: Vaszon, e: El): Vaszon {
  return { ...v, edges: [...elek(v), e] };
}

/** Node-ok és élek törlése; a törölt node élei is mennek. Az `elIds` nélkül az `ids` node-ot és élt is jelent (régi hívók);
 *  vele a két gyűjtemény külön címzett (09-canvas-15: egy node és egy él osztozhat az id-n). */
export function torol(v: Vaszon, ids: Set<string>, elIds?: Set<string>): Vaszon {
  const nodes = csomopontok(v).filter((c) => !ids.has(c.id));
  const maradt = new Set(nodes.map((c) => c.id));
  const edges = elek(v).filter((e) => !(elIds ?? ids).has(e.id) && maradt.has(e.fromNode) && maradt.has(e.toNode));
  let ki: Vaszon = v;
  if (nodes.length !== csomopontok(v).length) ki = { ...ki, nodes };
  if (edges.length !== elek(v).length) ki = { ...ki, edges };
  return ki;
}

/** Egy node vagy él mezőinek módosítása (`undefined` = a kulcs törlése). A `fajta` nélkül a node az első, utána az él (régi
 *  hívók); megadva csak az adott gyűjteményben keres (09-canvas-15). */
export function modosit(v: Vaszon, id: string, mezok: JsonObj, fajta?: 'node' | 'el'): Vaszon {
  const egyezik = (o: JsonObj) => Object.entries(mezok).every(([k, x]) => (x === undefined ? !(k in o) : o[k] === x));
  if (fajta !== 'el') {
    const ki = csere(v, (c) => (c.id === id && !egyezik(c) ? frissit(c, mezok as Partial<Csomopont>) : c));
    if (ki !== v || fajta === 'node') return ki;
  }
  return elCsere(v, (e) => (e.id === id && !egyezik(e) ? frissit(e, mezok as Partial<El>) : e));
}

/** A szín beállítása (a `null` törli) node-okon és éleken. Az `elIds` nélkül az `ids` mindkét gyűjteményt jelenti. */
export function szinez(v: Vaszon, ids: Set<string>, szin: string | null, elIds?: Set<string>): Vaszon {
  let ki = v;
  if (elIds === undefined) {
    for (const id of ids) ki = modosit(ki, id, { color: szin ?? undefined });
    return ki;
  }
  for (const id of ids) ki = modosit(ki, id, { color: szin ?? undefined }, 'node');
  for (const id of elIds) ki = modosit(ki, id, { color: szin ?? undefined }, 'el');
  return ki;
}

export type ElIrany = 'elore' | 'vissza' | 'mindketto' | 'nincs';

export function elIranya(e: El): ElIrany {
  const k = e.fromEnd === 'arrow';
  const v = e.toEnd !== 'none';
  return k && v ? 'mindketto' : v ? 'elore' : k ? 'vissza' : 'nincs';
}

/** Az él iránya a végek beállításával. Ha a kulcs nincs a fájlban, és a kért érték az alapérték (kezdet: `none`,
 *  vég: `arrow`), nem íródik be; ha benne van, a kért értéket kapja (a kulcs marad). */
export function elIranyBeallit(v: Vaszon, id: string, irany: ElIrany): Vaszon {
  const e = elek(v).find((x) => x.id === id);
  if (!e) return v;
  const kezd: Veg = irany === 'vissza' || irany === 'mindketto' ? 'arrow' : 'none';
  const veg: Veg = irany === 'elore' || irany === 'mindketto' ? 'arrow' : 'none';
  const mezok: Partial<El> = {};
  if ('fromEnd' in e || kezd !== 'none') mezok.fromEnd = kezd;
  if ('toEnd' in e || veg !== 'arrow') mezok.toEnd = veg;
  return modosit(v, id, mezok as JsonObj, 'el');
}

/** A kijelölt node-ok másolata új azonosítókkal, `eltolas`-sal arrébb; a köztük futó élek is másolódnak. */
export function duplikal(v: Vaszon, ids: Set<string>, eltolas = RACS * 2): { vaszon: Vaszon; ujak: Set<string> } {
  const foglalt = new Set<string>();
  const lek = new Map<string, string>();
  let ki = v;
  for (const c of csomopontok(v)) {
    if (!ids.has(c.id)) continue;
    const id = ujId(v, foglalt);
    foglalt.add(id);
    lek.set(c.id, id);
    ki = hozzaad(ki, { ...c, id, x: c.x + eltolas, y: c.y + eltolas });
  }
  for (const e of elek(v)) {
    const a = lek.get(e.fromNode);
    const b = lek.get(e.toNode);
    if (!a || !b) continue;
    const id = ujId(v, foglalt);
    foglalt.add(id);
    ki = elHozzaad(ki, { ...e, id, fromNode: a, toNode: b });
  }
  return { vaszon: ki, ujak: new Set(lek.values()) };
}

/** Csoport a node-ok köré (margóval, a rácsra igazítva). */
export function csoportKore(v: Vaszon, ids: Set<string>, cimke = 'Group'): { vaszon: Vaszon; id: string } | null {
  const d = befoglalo(csomopontok(v).filter((c) => ids.has(c.id)));
  if (!d) return null;
  const m = RACS * 2;
  const id = ujId(v);
  const x = racsra(d.x - m);
  const y = racsra(d.y - m);
  const csoport: Csomopont = {
    id,
    type: 'group',
    x,
    y,
    width: racsra(d.x + d.width + m) - x,
    height: racsra(d.y + d.height + m) - y,
    label: cimke,
  };
  return { vaszon: hozzaad(v, csoport), id };
}

/** Az Obsidian alapméretei az új kártyáknak. */
export const UJ_MERET: Record<string, { width: number; height: number }> = {
  text: { width: 260, height: 60 },
  file: { width: 400, height: 400 },
  link: { width: 400, height: 120 },
  group: { width: 400, height: 400 },
};

/** Új node az Obsidian kulcssorrendjével: `id, type, text|file|url, x, y, width, height` (a csoport címkéje a végén). */
export function ujCsomopont(
  v: Vaszon,
  tipus: 'text' | 'file' | 'link' | 'group',
  hely: { x: number; y: number },
  tartalom: { text?: string; file?: string; subpath?: string; url?: string; label?: string } = {},
  meret = UJ_MERET[tipus],
): Csomopont {
  const c: JsonObj = { id: ujId(v), type: tipus };
  if (tipus === 'text') c.text = tartalom.text ?? '';
  if (tipus === 'file') {
    c.file = tartalom.file ?? '';
    if (tartalom.subpath) c.subpath = tartalom.subpath;
  }
  if (tipus === 'link') c.url = tartalom.url ?? '';
  Object.assign(c, { x: Math.round(hely.x), y: Math.round(hely.y), width: meret.width, height: meret.height });
  if (tipus === 'group' && tartalom.label) c.label = tartalom.label;
  return c as Csomopont;
}

// ---------------------------------------------------------------------------------------------------------------------
// Élek szerkesztése, másolás/beillesztés, átalakítás, elhelyezés (09-canvas-02/03/05/06). Mind tiszta függvény: új `Vaszon`-t
// adnak, a régi a visszavonásé; az író (`iro.foltoz`) csak a megváltozott literálokat írja át.

const SZEMBEN: Record<Oldal, Oldal> = { top: 'bottom', bottom: 'top', left: 'right', right: 'left' };

/** Az él egyik végének átcsatolása (09-canvas-06): másik kártyára vagy ugyanannak másik oldalára. A címke, a szín és a
 *  többi kulcs marad. `null`, ha az él nincs meg, a cél nincs meg, vagy az él hurok lenne (a másik vége ugyanaz a node). */
export function elUjracsatol(v: Vaszon, elId: string, veg: 'from' | 'to', nodeId: string, oldal: Oldal): Vaszon | null {
  const e = elek(v).find((x) => x.id === elId);
  if (!e || !csomopontok(v).some((c) => c.id === nodeId)) return null;
  if ((veg === 'from' ? e.toNode : e.fromNode) === nodeId) return null;
  return modosit(v, elId, veg === 'from' ? { fromNode: nodeId, fromSide: oldal } : { toNode: nodeId, toSide: oldal }, 'el');
}

export interface UjElKartyaval {
  vaszon: Vaszon;
  nodeId: string;
  elId: string;
}

/** Új él egy üres helyre engedve (09-canvas-06): új szövegkártya, amelynek a szembenéző oldala a `p` pont, és az él hozzá,
 *  egyetlen lépésben. A kártya a rácsra igazítható (`racs`). */
export function ujElUjKartyaval(v: Vaszon, from: string, oldal: Oldal, p: Pont, racs: boolean): UjElKartyaval | null {
  if (!csomopontok(v).some((c) => c.id === from)) return null;
  const toSide = SZEMBEN[oldal];
  const meret = UJ_MERET.text;
  // a kártya a `toSide` oldalának közepével ér a `p`-hez
  let x = toSide === 'left' ? p.x : toSide === 'right' ? p.x - meret.width : p.x - meret.width / 2;
  let y = toSide === 'top' ? p.y : toSide === 'bottom' ? p.y - meret.height : p.y - meret.height / 2;
  if (racs) {
    x = racsra(x);
    y = racsra(y);
  }
  const c = ujCsomopont(v, 'text', { x, y });
  const elId = ujId(v, new Set([c.id]));
  const el: El = { id: elId, fromNode: from, fromSide: oldal, toNode: c.id, toSide };
  return { vaszon: elHozzaad(hozzaad(v, c), el), nodeId: c.id, elId };
}

/** Szövegkártya → jegyzetkártya (09-canvas-05): a `type` `file` lesz, a `text` kulcs kikerül, a `file` bekerül; a hely, a
 *  méret, a szín és az ismeretlen kulcsok maradnak. A hívó csak a jegyzet SIKERES létrehozása után hívja. */
export function szovegbolFajl(v: Vaszon, id: string, ut: string): Vaszon {
  const c = csomopontok(v).find((x) => x.id === id);
  if (!c || c.type !== 'text') return v;
  return modosit(v, id, { type: 'file', file: ut, text: undefined }, 'node');
}

/** A vágólapra/beillesztéshez szánt részvászon: node-ok (a tömb sorrendjében, vagyis z-sorrendben) és élek. */
export interface Fragment {
  nodes: Csomopont[];
  edges: El[];
}

/** A kijelölés részvászna: a kijelölt node-ok (a kijelölt csoport a tartalmával, mint a mozgatásnál), és azok az élek, amelyek
 *  mindkét vége a másolt node-ok közt van, plusz a külön kijelölt élek. */
export function fragmentKijelolesbol(v: Vaszon, nodeIds: Set<string>, elIds: Set<string>): Fragment {
  const mind = mozgatando(v, nodeIds);
  const nodes = csomopontok(v).filter((c) => mind.has(c.id));
  const benne = new Set(nodes.map((c) => c.id));
  const edges = elek(v).filter((e) => elIds.has(e.id) || (benne.has(e.fromNode) && benne.has(e.toNode)));
  return { nodes, edges };
}

export interface Beillesztes {
  vaszon: Vaszon;
  nodeIds: Set<string>;
  elIds: Set<string>;
  /** a végei hiányzó, ezért kihagyott élek száma */
  kihagyott: number;
}

/** A részvászon beillesztése: új azonosítók (node-ok és élek közt is egyediek), a node-ok befoglaló dobozának bal felső
 *  sarka a `hova`-ba kerül (egész koordinátákkal). Az él, amelynek a vége se a részvásznon, se a vásznon nincs, kimarad. Az
 *  ismeretlen kulcsok és a node-ok sorrendje megmarad. */
export function beillesztFragment(v: Vaszon, f: Fragment, hova: Pont): Beillesztes {
  const bb = befoglalo(f.nodes);
  const dx = bb ? Math.round(hova.x - bb.x) : 0;
  const dy = bb ? Math.round(hova.y - bb.y) : 0;
  const foglalt = new Set<string>();
  const lek = new Map<string, string>();
  const meglevo = new Set(csomopontok(v).map((c) => c.id));
  let ki = v;
  for (const c of f.nodes) {
    const id = ujId(v, foglalt);
    foglalt.add(id);
    lek.set(c.id, id);
    ki = hozzaad(ki, { ...c, id, x: Math.round(c.x + dx), y: Math.round(c.y + dy) });
  }
  const elIds = new Set<string>();
  let kihagyott = 0;
  for (const e of f.edges) {
    const a = lek.get(e.fromNode) ?? (meglevo.has(e.fromNode) ? e.fromNode : null);
    const b = lek.get(e.toNode) ?? (meglevo.has(e.toNode) ? e.toNode : null);
    if (!a || !b) {
      kihagyott++;
      continue;
    }
    const id = ujId(v, foglalt);
    foglalt.add(id);
    elIds.add(id);
    ki = elHozzaad(ki, { ...e, id, fromNode: a, toNode: b });
  }
  return { vaszon: ki, nodeIds: new Set(lek.values()), elIds, kihagyott };
}

/** Több kártya rácsos elhelyezése (09-canvas-02): a blokk közepe a `kozep`; a visszaadott pontok a kártyák bal felső sarkai. */
export function racsElhelyez(meretek: { width: number; height: number }[], kozep: Pont, tav = RACS, maxOszlop = 4): Pont[] {
  const n = meretek.length;
  if (!n) return [];
  const oszlop = Math.min(n, n <= 3 ? n : Math.min(maxOszlop, Math.ceil(Math.sqrt(n))));
  const sor = Math.ceil(n / oszlop);
  const szel = Array.from({ length: oszlop }, () => 0);
  const mag = Array.from({ length: sor }, () => 0);
  meretek.forEach((m, k) => {
    szel[k % oszlop] = Math.max(szel[k % oszlop], m.width);
    mag[Math.floor(k / oszlop)] = Math.max(mag[Math.floor(k / oszlop)], m.height);
  });
  const ossz = (a: number[]) => a.reduce((s, x) => s + x, 0) + tav * (a.length - 1);
  const x0 = kozep.x - ossz(szel) / 2;
  const y0 = kozep.y - ossz(mag) / 2;
  return meretek.map((_, k) => {
    const o = k % oszlop;
    const r = Math.floor(k / oszlop);
    return {
      x: Math.round(x0 + szel.slice(0, o).reduce((s, x) => s + x + tav, 0)),
      y: Math.round(y0 + mag.slice(0, r).reduce((s, x) => s + x + tav, 0)),
    };
  });
}

/** Egy beillesztett vagy ejtett szöveg kártyamérete: a sorok számához igazodó magasság (legfeljebb 600). */
export function szovegMeret(szoveg: string): { width: number; height: number } {
  const sorok = szoveg.split('\n').reduce((n, s) => n + Math.max(1, Math.ceil(s.length / 30)), 0);
  return { width: UJ_MERET.text.width, height: Math.min(600, Math.max(UJ_MERET.text.height, racsra(sorok * 24 + 36))) };
}

/** A szövegkártya javasolt jegyzetneve (09-canvas-05): az első nem üres sor, a Markdown-jelölők és a fájlnévben tiltott
 *  karakterek nélkül, rövidítve; üres szövegnél `tartalek`. A core a végső szabályok őre (a név ütközhet, vagy elutasítható). */
export function javasoltJegyzetNev(szoveg: string, tartalek: string): string {
  const sor = szoveg.split('\n').map((s) => s.trim()).find((s) => s) ?? '';
  const tiszta = sor
    .replace(/^(?:[#>\-*+]+|\d+[.)]|- \[[ xX]\])\s+/u, '')
    .replace(/!?\[\[([^\]|#]*)(?:[#|][^\]]*)?\]\]/g, '$1')
    .replace(/[*_`~=]/g, '')
    .replace(/[\\/:*?"<>|#^[\]]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/^\.+/, '');
  const rovid = [...tiszta].slice(0, 60).join('').trim();
  return rovid || tartalek;
}
