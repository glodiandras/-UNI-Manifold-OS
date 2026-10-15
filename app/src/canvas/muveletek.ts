// A canvas modell-műveletei (C14, tiszta függvények): minden művelet új `Vaszon`-t ad, a régi érintetlen (a
// visszavonásé). A változatlan node/él ugyanaz az objektum marad, így az író csak a ténylegesen megváltozott
// mezőt írja át. A koordináta mindig egész (a spec szerint).

import { csomopontok, elek, ujId, type Csomopont, type El, type JsonObj, type Vaszon, type Veg } from './modell';
import { befoglalo, RACS, racsra, type Doboz } from './geometria';

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

/** Node-ok és élek törlése; a törölt node élei is mennek. */
export function torol(v: Vaszon, ids: Set<string>): Vaszon {
  const nodes = csomopontok(v).filter((c) => !ids.has(c.id));
  const maradt = new Set(nodes.map((c) => c.id));
  const edges = elek(v).filter((e) => !ids.has(e.id) && maradt.has(e.fromNode) && maradt.has(e.toNode));
  let ki: Vaszon = v;
  if (nodes.length !== csomopontok(v).length) ki = { ...ki, nodes };
  if (edges.length !== elek(v).length) ki = { ...ki, edges };
  return ki;
}

/** Egy node vagy él mezőinek módosítása (`undefined` = a kulcs törlése). */
export function modosit(v: Vaszon, id: string, mezok: JsonObj): Vaszon {
  const egyezik = (o: JsonObj) => Object.entries(mezok).every(([k, x]) => (x === undefined ? !(k in o) : o[k] === x));
  const ki = csere(v, (c) => (c.id === id && !egyezik(c) ? frissit(c, mezok as Partial<Csomopont>) : c));
  return ki !== v ? ki : elCsere(v, (e) => (e.id === id && !egyezik(e) ? frissit(e, mezok as Partial<El>) : e));
}

/** A szín beállítása (a `null` törli) node-okon és éleken. */
export function szinez(v: Vaszon, ids: Set<string>, szin: string | null): Vaszon {
  let ki = v;
  for (const id of ids) ki = modosit(ki, id, { color: szin ?? undefined });
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
  return modosit(v, id, mezok as JsonObj);
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
export function csoportKore(v: Vaszon, ids: Set<string>, cimke = 'Csoport'): { vaszon: Vaszon; id: string } | null {
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
