// A canvas modellje (C14): a JSON Canvas 1.0 (jsoncanvas.org/spec/1.0) adatai, ahogy a fájlban állnak. A modell
// maga a JSON-érték (közönséges objektumok), így az ismeretlen kulcs, az ismeretlen node-típus és a
// `styleAttributes`-szerű bővítés változatlanul megmarad; a nézet és a műveletek csak a spec mezőit olvassák.
// A műveletek a modellt nem módosítják helyben: új objektumot adnak (a régi a visszavonásé).

import { elemez, ertekbol, JsonHiba } from './json';
import { tk, t } from '../lib/i18n';

export type JsonObj = Record<string, unknown>;

export type CsomopontTipus = 'text' | 'file' | 'link' | 'group';
export type Oldal = 'top' | 'right' | 'bottom' | 'left';
export type Veg = 'none' | 'arrow';

export interface Csomopont extends JsonObj {
  id: string;
  type: string;
  x: number;
  y: number;
  width: number;
  height: number;
  color?: string;
  text?: string;
  file?: string;
  subpath?: string;
  url?: string;
  label?: string;
  background?: string;
  backgroundStyle?: string;
}

export interface El extends JsonObj {
  id: string;
  fromNode: string;
  toNode: string;
  fromSide?: Oldal;
  toSide?: Oldal;
  fromEnd?: Veg;
  toEnd?: Veg;
  color?: string;
  label?: string;
}

/** A fájl gyökere: a `nodes` és az `edges` opcionális (a spec szerint); a többi kulcs érintetlenül megmarad. */
export interface Vaszon extends JsonObj {
  nodes?: Csomopont[];
  edges?: El[];
}

export const OLDALAK: readonly Oldal[] = ['top', 'right', 'bottom', 'left'];
export const ISMERT_TIPUSOK: readonly string[] = ['text', 'file', 'link', 'group'];

export const csomopontok = (v: Vaszon): Csomopont[] => v.nodes ?? [];
export const elek = (v: Vaszon): El[] => v.edges ?? [];

/** Az él kezdő és záró vége a spec alapértékeivel: a kezdet `none`, a vég `arrow`. */
export const kezdoVeg = (e: El): Veg => (e.fromEnd === 'arrow' ? 'arrow' : 'none');
export const zaroVeg = (e: El): Veg => (e.toEnd === 'none' ? 'none' : 'arrow');

export interface Beolvasas {
  /** a modell, ha a fájl JSON Canvas-ként olvasható (különben `null`, és a `hiba` mondja, miért) */
  vaszon: Vaszon | null;
  /** végzetes hiba: a nézet csak olvasásra nyit, és nem ír */
  hiba: string | null;
  /** a JSON-hiba helye (1-től számolt sor és oszlop) */
  hely: { sor: number; oszlop: number } | null;
  /** nem végzetes eltérések a spectől (a nézet így is rajzol és ír) */
  figyelmeztetesek: string[];
}

const objektum = (x: unknown): x is JsonObj => typeof x === 'object' && x !== null && !Array.isArray(x);
const szam = (x: unknown): x is number => typeof x === 'number' && Number.isFinite(x);

/** A fájl szövegének beolvasása és ellenőrzése. Az üres szöveg üres canvas (az Obsidian is így nyitja). */
export function beolvas(szoveg: string): Beolvasas {
  const figyelmeztetesek: string[] = [];
  const rossz = (hiba: string, hely: Beolvasas['hely'] = null): Beolvasas => ({ vaszon: null, hiba, hely, figyelmeztetesek });
  if (!szoveg.trim()) return { vaszon: {}, hiba: null, hely: null, figyelmeztetesek };
  let v: unknown;
  try {
    v = ertekbol(elemez(szoveg));
  } catch (e) {
    if (e instanceof JsonHiba) return rossz(t('A canvas nem érvényes JSON: {hiba}', { hiba: e.message }), { sor: e.sor, oszlop: e.oszlop });
    throw e;
  }
  if (!objektum(v)) return rossz(t('A canvas gyökere nem objektum.'));
  for (const k of ['nodes', 'edges'] as const)
    if (k in v && !Array.isArray(v[k])) return rossz(t('A „{kulcs}” nem tömb.', { kulcs: k }));
  // 09-canvas-15: a spec az azonosító egyediségét gyűjteményenként kéri — egy node és egy él osztozhat az id-n (a nézet a
  // kijelölést és a törlést ezért gyűjtemény szerint minősíti, `kijeloles.ts`); gyűjteményen belüli ismétlődés végzetes
  const ids = new Set<string>();
  for (const [n, c] of ((v.nodes ?? []) as unknown[]).entries()) {
    if (!objektum(c)) return rossz(t('A {n}. node nem objektum.', { n: n + 1 }));
    if (typeof c.id !== 'string' || !c.id) return rossz(t('A {n}. node-nak nincs azonosítója (id).', { n: n + 1 }));
    if (ids.has(c.id)) return rossz(t('Két elemnek azonos az azonosítója: {id}.', { id: c.id }));
    ids.add(c.id);
    if (typeof c.type !== 'string') return rossz(t('A(z) {id} node-nak nincs típusa (type).', { id: c.id }));
    for (const m of ['x', 'y', 'width', 'height'])
      if (!szam(c[m])) return rossz(t('A(z) {id} node „{mezo}” mezője nem szám.', { id: c.id, mezo: m }));
    if (!ISMERT_TIPUSOK.includes(c.type)) figyelmeztetesek.push(t('Ismeretlen node-típus: {tipus} ({id}).', { tipus: c.type, id: c.id }));
    for (const m of ['x', 'y', 'width', 'height'])
      if (!Number.isInteger(c[m])) figyelmeztetesek.push(t('A(z) {id} node „{mezo}” mezője nem egész szám.', { id: c.id, mezo: m }));
  }
  const csomopontIds = new Set(ids);
  const elIds = new Set<string>();
  for (const [n, e] of ((v.edges ?? []) as unknown[]).entries()) {
    if (!objektum(e)) return rossz(t('A {n}. él nem objektum.', { n: n + 1 }));
    if (typeof e.id !== 'string' || !e.id) return rossz(t('A {n}. élnek nincs azonosítója (id).', { n: n + 1 }));
    if (elIds.has(e.id)) return rossz(t('Két elemnek azonos az azonosítója: {id}.', { id: e.id }));
    elIds.add(e.id);
    if (typeof e.fromNode !== 'string' || typeof e.toNode !== 'string')
      return rossz(t('A(z) {id} élnek nincs kezdő vagy záró node-ja.', { id: e.id }));
    if (!csomopontIds.has(e.fromNode) || !csomopontIds.has(e.toNode))
      figyelmeztetesek.push(t('A(z) {id} él nem létező node-ra mutat; nem rajzolódik.', { id: e.id }));
  }
  return { vaszon: v as Vaszon, hiba: null, hely: null, figyelmeztetesek };
}

/** Egy új, 16 hexa jegyű azonosító (az Obsidian alakja), amely a canvasban még nem foglalt (node-ok és élek között sem). */
export function ujId(v: Vaszon, foglalt: Set<string> = new Set()): string {
  const van = new Set([...csomopontok(v).map((c) => c.id), ...elek(v).map((e) => e.id), ...foglalt]);
  for (;;) {
    const b = new Uint8Array(8);
    crypto.getRandomValues(b);
    const id = Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('');
    if (!van.has(id)) return id;
  }
}

/** A preset színek neve (a spec: 1 piros … 6 lila); a hex szín a felhasználó adata, nyersen. */
export const SZIN_NEV: Record<string, string> = {
  '1': tk('piros'),
  '2': tk('narancs'),
  '3': tk('sárga'),
  '4': tk('zöld'),
  '5': tk('cián'),
  '6': tk('lila'),
};

/** A hex szín: `#rgb`, `#rrggbb`, vagy átlátszósággal `#rgba`, `#rrggbbaa` (09-canvas-12: az importált szín nem tűnik el). */
export const HEX_SZIN = /^#(?:[0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})$/i;

/** A szín CSS-értéke: a preset a tokenre képeződik, a hex szín nyersen, a többi (ismeretlen) nincs. */
export function szinCss(szin: unknown): string | null {
  if (typeof szin !== 'string' || !szin) return null;
  if (SZIN_NEV[szin]) return `var(--canvas-szin-${szin})`;
  return HEX_SZIN.test(szin) ? szin : null;
}
