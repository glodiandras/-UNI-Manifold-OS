// A canvas vágólapja (09-canvas-03). Másoláskor a kijelölés JSON Canvas részvászna kerül a vágólapra egy Manifold MIME-típuson
// (`application/x-manifold-canvas`), mellette szöveges tartalék (a szövegkártyák szövege, a jegyzetkártyák `[[…]]` linkje, a
// link-kártyák URL-je), így más alkalmazásba is beilleszthető. Beillesztéskor ugyanezt a részvásznat olvassuk vissza; ha a
// MIME-típus nem maradt meg (a WebKit nem minden esetben adja át), a saját utolsó másolat szövege egyezéssel azonosít.
// Az Obsidian saját vágólap-formátuma nem ismert (09 audit, 7. kérdés): a szöveges tartalékban álló, érvényes JSON Canvas
// részvászon (nodes/edges) is beilleszthető. A beolvasás mindig a canvas saját ellenőrzőjén (`beolvas`) megy át.

import { kulsoCim } from '../szerkeszto/linkek/kulso';
import { beolvas, csomopontok, elek, type Csomopont, type El } from './modell';
import type { Fragment } from './muveletek';

export const CANVAS_MIME = 'application/x-manifold-canvas';
/** A beillesztett részvászon felső korlátja (a vágólap tartalma nem megbízható adat). */
export const MAX_FRAGMENT_BAJT = 4 * 1024 * 1024;
export const MAX_FRAGMENT_NODE = 5000;

/** A részvászon JSON-ja a vágólapra; a `manifold` kulcs csak jelölő (a beolvasás a spec mezőit nézi). */
export function fragmentJson(f: Fragment): string {
  return JSON.stringify({ manifold: 'canvas-fragment', version: 1, nodes: f.nodes, edges: f.edges });
}

/** A szöveges tartalék: szövegkártya → szövege, jegyzet/fájl → `[[út#alcím]]`, link → URL, csoport → címke. */
export function fragmentSzoveg(f: Fragment): string {
  const reszek: string[] = [];
  for (const c of f.nodes) {
    if (c.type === 'text' && typeof c.text === 'string') reszek.push(c.text);
    else if (c.type === 'file' && typeof c.file === 'string')
      reszek.push(`[[${c.file.replace(/\.md$/i, '')}${typeof c.subpath === 'string' ? c.subpath : ''}]]`);
    else if (c.type === 'link' && typeof c.url === 'string') reszek.push(c.url);
    else if (c.type === 'group' && typeof c.label === 'string' && c.label) reszek.push(c.label);
  }
  return reszek.join('\n\n');
}

/** A legutóbbi saját másolat (a WebKit esetleges MIME-vesztésére és a menüből indított beillesztésre). */
let sajat: { szoveg: string; json: string } | null = null;

export function sajatMasolat(): { szoveg: string; json: string } | null {
  return sajat;
}

export function sajatTorol(): void {
  sajat = null;
}

/** A másolat rögzítése a saját pufferben, és a vágólapra szánt tartalma; `null`, ha nincs mit másolni. */
export function masolatKeszit(f: Fragment): { szoveg: string; json: string } | null {
  if (!f.nodes.length && !f.edges.length) return null;
  sajat = { szoveg: fragmentSzoveg(f), json: fragmentJson(f) };
  return sajat;
}

/** A másolat a vágólap-eseményre (`copy`/`cut`); → igaz, ha volt mit másolni. */
export function vagolapraIr(dt: Pick<DataTransfer, 'setData'>, f: Fragment): boolean {
  const m = masolatKeszit(f);
  if (!m) return false;
  dt.setData(CANVAS_MIME, m.json);
  dt.setData('text/plain', m.szoveg);
  return true;
}

/** Egy szöveg részvászonként: érvényes JSON Canvas legalább egy node-dal vagy éllel; különben `null`. A javasolt méret-,
 *  darabszám- és szerkezeti korlátokon túl semmit nem fogad el. */
export function fragmentBeolvas(szoveg: string): Fragment | null {
  if (szoveg.length > MAX_FRAGMENT_BAJT || !/^\s*\{/.test(szoveg)) return null;
  const b = beolvas(szoveg);
  if (!b.vaszon || b.hiba) return null;
  const nodes: Csomopont[] = csomopontok(b.vaszon);
  const edges: El[] = elek(b.vaszon);
  if (!nodes.length && !edges.length) return null;
  if (nodes.length > MAX_FRAGMENT_NODE || edges.length > MAX_FRAGMENT_NODE * 4) return null;
  return { nodes, edges };
}

export type Beillesztendo =
  | { fajta: 'fragment'; fragment: Fragment }
  | { fajta: 'link'; url: string }
  | { fajta: 'szoveg'; szoveg: string }
  | { fajta: 'fajlok'; fajlok: File[] }
  | { fajta: 'ures' };

/** Mi áll a vágólapon: fájlok (kép) → a részvászon → egyetlen URL → szöveg. */
export function beillesztOsztalyoz(dt: Pick<DataTransfer, 'getData' | 'files'> | null): Beillesztendo {
  if (!dt) return { fajta: 'ures' };
  const fajlok = Array.from(dt.files ?? []);
  if (fajlok.length) return { fajta: 'fajlok', fajlok };
  const sima = dt.getData('text/plain') ?? '';
  const nyers = dt.getData(CANVAS_MIME) || (sajat && sajat.szoveg === sima && sima ? sajat.json : '') || '';
  if (nyers) {
    const f = fragmentBeolvas(nyers);
    if (f) return { fajta: 'fragment', fragment: f };
  }
  const f = fragmentBeolvas(sima);
  if (f) return { fajta: 'fragment', fragment: f };
  const egy = sima.trim();
  if (egy && !/\s/.test(egy) && kulsoCim(egy) && /^(?:https?:\/\/|www\.)/i.test(egy)) return { fajta: 'link', url: kulsoCim(egy)! };
  if (sima.trim()) return { fajta: 'szoveg', szoveg: sima };
  return { fajta: 'ures' };
}
