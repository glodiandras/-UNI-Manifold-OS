// A canvas tiszta moduljai (C14): geometria, modell-műveletek, visszavonás-előzmény.

import { describe, expect, it } from 'vitest';
import { Elozmeny, MAX_LEPES } from '../src/canvas/elozmeny';
import {
  atmeretez,
  befoglalo,
  csoportTartalma,
  elGeometria,
  felenezoOldal,
  kepernyore,
  legkozelebbiOldal,
  mindentMutat,
  mozgatando,
  nagyit,
  racsra,
  vilagba,
  Z_MAX,
  Z_MIN,
} from '../src/canvas/geometria';
import { foltoz } from '../src/canvas/iro';
import { szinCss, ujId, type Csomopont, type Vaszon } from '../src/canvas/modell';
import {
  csoportKore,
  dobozBeallit,
  duplikal,
  elIranya,
  elIranyBeallit,
  hozzaad,
  modosit,
  mozgat,
  szinez,
  torol,
  ujCsomopont,
} from '../src/canvas/muveletek';

const n = (id: string, x: number, y: number, w = 100, h = 100, tobbi: Partial<Csomopont> = {}): Csomopont => ({
  id,
  type: 'text',
  text: id,
  x,
  y,
  width: w,
  height: h,
  ...tobbi,
});

const V: Vaszon = {
  nodes: [n('g', 0, 0, 500, 500, { type: 'group', label: 'G' }), n('a', 20, 20), n('b', 200, 200), n('c', 800, 0)],
  edges: [
    { id: 'e1', fromNode: 'a', toNode: 'b', fromSide: 'right', toSide: 'left' },
    { id: 'e2', fromNode: 'b', toNode: 'c' },
  ],
};

describe('geometria', () => {
  it('a nagyítás a kurzor alatti pontot helyben tartja, korlátok között', () => {
    const nz = { tx: 100, ty: 50, z: 1 };
    const p = { x: 300, y: 200 };
    const w = vilagba(nz, p);
    const u = nagyit(nz, p, 2);
    expect(kepernyore(u, w)).toEqual(p);
    expect(nagyit(nz, p, 100).z).toBe(Z_MAX);
    expect(nagyit(nz, p, 0).z).toBe(Z_MIN);
  });

  it('mindent mutat: a befoglaló doboz a képernyő közepén, legfeljebb 1-es nagyítással', () => {
    const d = befoglalo([n('a', 0, 0, 100, 100), n('b', 900, 400, 100, 100)])!;
    expect(d).toEqual({ x: 0, y: 0, width: 1000, height: 500 });
    const m = mindentMutat(d, { w: 1096, h: 800 });
    expect(m.z).toBeCloseTo(1);
    expect(kepernyore(m, { x: 500, y: 250 })).toEqual({ x: 548, y: 400 });
    expect(mindentMutat(n('x', 0, 0, 10, 10), { w: 800, h: 600 }).z).toBe(1);
    expect(mindentMutat(null, { w: 800, h: 600 })).toEqual({ tx: 400, ty: 300, z: 1 });
  });

  it('rács, átméretezés minimális mérettel', () => {
    expect(racsra(29)).toBe(20);
    expect(racsra(31)).toBe(40);
    expect(racsra(-31)).toBe(-40);
    const d = { x: 0, y: 0, width: 200, height: 100 };
    expect(atmeretez(d, 'se', 33, 17, 20)).toEqual({ x: 0, y: 0, width: 240, height: 120 });
    expect(atmeretez(d, 'nw', 500, 500, null)).toEqual({ x: 160, y: 60, width: 40, height: 40 });
    expect(atmeretez(d, 'w', -15, 0, null)).toEqual({ x: -15, y: 0, width: 215, height: 100 });
  });

  it('a csoport a benne teljesen álló node-okat viszi', () => {
    expect([...csoportTartalma(V, V.nodes![0])].sort()).toEqual(['a', 'b']);
    expect([...mozgatando(V, ['g'])].sort()).toEqual(['a', 'b', 'g']);
    expect([...mozgatando(V, ['c', 'nincs'])]).toEqual(['c']);
  });

  it('az él: megadott oldalak, hiányzónál a felé néző oldal; a nyíl befutó iránya', () => {
    const a = n('a', 0, 0);
    const b = n('b', 300, 0);
    const g = elGeometria(a, 'right', b, 'left');
    expect(g.kezd).toEqual({ x: 100, y: 50 });
    expect(g.veg).toEqual({ x: 300, y: 50 });
    expect(g.vegIrany).toEqual({ x: 1, y: -0 });
    expect(g.d.startsWith('M100,50 C')).toBe(true);
    expect(felenezoOldal(a, { x: 50, y: 500 })).toBe('bottom');
    expect(felenezoOldal(a, { x: -400, y: 60 })).toBe('left');
    expect(legkozelebbiOldal(b, { x: 305, y: 40 })).toBe('left');
  });
});

describe('műveletek: új objektum, a változatlan elem ugyanaz marad', () => {
  it('mozgatás egész lépéssel; a nem érintett node azonos objektum', () => {
    const u = mozgat(V, new Set(['a']), 10.4, -5.6);
    expect(u.nodes![1]).toMatchObject({ x: 30, y: 14 });
    expect(u.nodes![2]).toBe(V.nodes![2]);
    expect(mozgat(V, new Set(['a']), 0.2, 0.3)).toBe(V);
    expect(V.nodes![1].x).toBe(20); // a régi érintetlen
  });

  it('új node: a csoport a nem-csoportok elé, a többi a végére; Obsidian-kulcssorrend', () => {
    const t = ujCsomopont(V, 'text', { x: 1.6, y: 2 }, { text: 'x' });
    expect(Object.keys(t)).toEqual(['id', 'type', 'text', 'x', 'y', 'width', 'height']);
    expect(t.x).toBe(2);
    expect(t.id).toMatch(/^[0-9a-f]{16}$/);
    const f = ujCsomopont(V, 'file', { x: 0, y: 0 }, { file: 'a.md' });
    expect(Object.keys(f)).toEqual(['id', 'type', 'file', 'x', 'y', 'width', 'height']);
    const g = ujCsomopont(V, 'group', { x: 0, y: 0 }, { label: 'L' });
    expect(Object.keys(g)).toEqual(['id', 'type', 'x', 'y', 'width', 'height', 'label']);
    expect(hozzaad(V, t).nodes!.at(-1)).toBe(t);
    const v2 = hozzaad({ nodes: [n('g', 0, 0, 1, 1, { type: 'group' }), n('a', 0, 0)] }, g);
    expect(v2.nodes!.map((x) => x.id)).toEqual(['g', g.id, 'a']);
  });

  it('törlés: a node éleivel; él önmagában', () => {
    const u = torol(V, new Set(['b']));
    expect(u.nodes!.map((x) => x.id)).toEqual(['g', 'a', 'c']);
    expect(u.edges).toEqual([]);
    const e = torol(V, new Set(['e2']));
    expect(e.nodes).toBe(V.nodes);
    expect(e.edges!.map((x) => x.id)).toEqual(['e1']);
  });

  it('módosítás: undefined törli a kulcsot; változatlan értéknél ugyanaz a vászon', () => {
    const v = szinez(V, new Set(['a', 'e1']), '3');
    expect(v.nodes![1].color).toBe('3');
    expect(v.edges![0].color).toBe('3');
    const ki = szinez(v, new Set(['a']), null);
    expect('color' in ki.nodes![1]).toBe(false);
    expect(modosit(V, 'a', { text: 'a' })).toBe(V);
    expect(dobozBeallit(V, 'a', { x: 20, y: 20, width: 100, height: 100 })).toBe(V);
  });

  it('az él iránya: az alapértéket nem írja be, a meglévő kulcsot megtartja', () => {
    const e = V.edges![0];
    expect(elIranya(e)).toBe('elore');
    const vissza = elIranyBeallit(V, 'e1', 'vissza');
    expect(vissza.edges![0]).toMatchObject({ fromEnd: 'arrow', toEnd: 'none' });
    expect(elIranya(vissza.edges![0])).toBe('vissza');
    const elore = elIranyBeallit(vissza, 'e1', 'elore');
    expect(elore.edges![0]).toMatchObject({ fromEnd: 'none', toEnd: 'arrow' }); // a kulcsok maradtak
    expect(elIranyBeallit(V, 'e1', 'elore')).toBe(V);
    expect(elIranya(elIranyBeallit(V, 'e1', 'nincs').edges![0])).toBe('nincs');
    expect('fromEnd' in elIranyBeallit(V, 'e1', 'nincs').edges![0]).toBe(false);
  });

  it('duplikálás: új id-k, eltolás, a köztük futó él is', () => {
    const { vaszon, ujak } = duplikal(V, new Set(['a', 'b']));
    expect(ujak.size).toBe(2);
    expect(vaszon.nodes!.length).toBe(6);
    expect(vaszon.edges!.length).toBe(3);
    const ujEl = vaszon.edges!.at(-1)!;
    expect(ujak.has(ujEl.fromNode) && ujak.has(ujEl.toNode)).toBe(true);
    expect(vaszon.nodes!.find((x) => ujak.has(x.id) && x.text === 'a')).toMatchObject({ x: 60, y: 60 });
  });

  it('csoport a kijelölés köré, a rácsra igazítva', () => {
    const r = csoportKore(V, new Set(['a', 'b']))!;
    const g = r.vaszon.nodes!.find((x) => x.id === r.id)!;
    expect(g).toMatchObject({ type: 'group', x: -20, y: -20, width: 360, height: 360, label: 'Csoport' });
    expect(r.vaszon.nodes!.map((x) => x.type).indexOf('text')).toBeGreaterThan(r.vaszon.nodes!.indexOf(g));
    expect(csoportKore(V, new Set())).toBeNull();
  });

  it('a műveletek kimenete a foltozón át bájtra csak a változott részt írja', () => {
    const s = JSON.stringify(V, null, '\t');
    const ki = foltoz(s, mozgat(V, new Set(['c']), 20, 0));
    expect(ki).toBe(s.replace('"x": 800', '"x": 820'));
  });

  it('új id: nem ütközik', () => {
    const foglalt = new Set(['a']);
    for (let i = 0; i < 50; i++) foglalt.add(ujId(V, foglalt));
    expect(foglalt.size).toBe(51);
  });

  it('a szín CSS-értéke: preset tokenre, hex nyersen, a többi semmi', () => {
    expect(szinCss('1')).toBe('var(--canvas-szin-1)');
    expect(szinCss('#FF0000')).toBe('#FF0000');
    expect(szinCss('red; x')).toBeNull();
    expect(szinCss(undefined)).toBeNull();
  });
});

describe('előzmény', () => {
  it('visszavonás és újra; új lépés törli az újra-vermet; korlát', () => {
    const e = new Elozmeny();
    const a: Vaszon = { nodes: [] };
    const b: Vaszon = { nodes: [n('x', 0, 0)] };
    const c: Vaszon = { nodes: [n('x', 1, 0)] };
    e.rogzit(a);
    e.rogzit(b);
    expect(e.visszavon(c)).toBe(b);
    expect(e.visszavon(b)).toBe(a);
    expect(e.visszavon(a)).toBeNull();
    expect(e.ujra(a)).toBe(b);
    e.rogzit(b);
    expect(e.vanElore).toBe(false);
    for (let i = 0; i < MAX_LEPES + 10; i++) e.rogzit(a);
    let db = 0;
    while (e.visszavon(a)) db++;
    expect(db).toBe(MAX_LEPES);
  });
});
