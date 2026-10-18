// A vászon geometriája (C14, tiszta függvények): nézet-transzformáció, nagyítás egy pont körül, rács,
// befoglaló doboz, „mindent mutat”, az él végpontjai és útja, a csoport tartalma. A koordináták a canvas
// világkoordinátái (px); a képernyőpont = világ × z + eltolás.

import { csomopontok, type Csomopont, type Oldal, type Vaszon } from './modell';

export interface Nezet {
  /** eltolás a képernyőn (px) */
  tx: number;
  ty: number;
  /** nagyítás */
  z: number;
}

export interface Pont {
  x: number;
  y: number;
}

export interface Doboz {
  x: number;
  y: number;
  width: number;
  height: number;
}

export const Z_MIN = 0.03;
export const Z_MAX = 3;
export const RACS = 20;
export const MIN_MERET = 40;

export const korlat = (z: number) => Math.min(Z_MAX, Math.max(Z_MIN, z));

export function vilagba(n: Nezet, p: Pont): Pont {
  return { x: (p.x - n.tx) / n.z, y: (p.y - n.ty) / n.z };
}

export function kepernyore(n: Nezet, p: Pont): Pont {
  return { x: p.x * n.z + n.tx, y: p.y * n.z + n.ty };
}

/** Nagyítás úgy, hogy a `p` képernyőpont alatti világpont a helyén maradjon. */
export function nagyit(n: Nezet, p: Pont, ujZ: number): Nezet {
  const z = korlat(ujZ);
  const w = vilagba(n, p);
  return { tx: p.x - w.x * z, ty: p.y - w.y * z, z };
}

export function racsra(v: number, racs = RACS): number {
  return Math.round(v / racs) * racs;
}

export function befoglalo(dobozok: Doboz[]): Doboz | null {
  if (!dobozok.length) return null;
  let x0 = Infinity;
  let y0 = Infinity;
  let x1 = -Infinity;
  let y1 = -Infinity;
  for (const d of dobozok) {
    x0 = Math.min(x0, d.x);
    y0 = Math.min(y0, d.y);
    x1 = Math.max(x1, d.x + d.width);
    y1 = Math.max(y1, d.y + d.height);
  }
  return { x: x0, y: y0, width: x1 - x0, height: y1 - y0 };
}

/** A nézet, amelyben a doboz kitölti a `meret` méretű képernyőt (margóval). A teljes vászon alapból legfeljebb 1×;
 *  a kijelölés külön nagyítási plafont kérhet (a közös nagyítási korlátokon belül). */
export function mindentMutat(d: Doboz | null, meret: { w: number; h: number }, margo = 48, maxNagyitas = 1): Nezet {
  if (!d || meret.w <= 0 || meret.h <= 0) return { tx: meret.w / 2, ty: meret.h / 2, z: 1 };
  const z = korlat(Math.min((meret.w - 2 * margo) / Math.max(d.width, 1), (meret.h - 2 * margo) / Math.max(d.height, 1), maxNagyitas));
  return { tx: meret.w / 2 - (d.x + d.width / 2) * z, ty: meret.h / 2 - (d.y + d.height / 2) * z, z };
}

export function metszi(a: Doboz, b: Doboz): boolean {
  return a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height;
}

export function tartalmazza(kulso: Doboz, belso: Doboz): boolean {
  return (
    belso.x >= kulso.x &&
    belso.y >= kulso.y &&
    belso.x + belso.width <= kulso.x + kulso.width &&
    belso.y + belso.height <= kulso.y + kulso.height
  );
}

/** Két képernyőpontból a (normalizált) téglalap. */
export function teglalap(a: Pont, b: Pont): Doboz {
  return { x: Math.min(a.x, b.x), y: Math.min(a.y, b.y), width: Math.abs(a.x - b.x), height: Math.abs(a.y - b.y) };
}

/** A csoport tartalma: a dobozában teljesen benne álló node-ok (a beágyazott csoportokkal és azok tartalmával). */
export function csoportTartalma(v: Vaszon, csoport: Csomopont): Set<string> {
  const ki = new Set<string>();
  for (const c of csomopontok(v)) if (c.id !== csoport.id && tartalmazza(csoport, c)) ki.add(c.id);
  return ki;
}

/** A mozgatandó node-ok: a kijelöltek és a kijelölt csoportok tartalma. */
export function mozgatando(v: Vaszon, kijelolt: Iterable<string>): Set<string> {
  const ki = new Set<string>();
  const szerint = new Map(csomopontok(v).map((c) => [c.id, c]));
  for (const id of kijelolt) {
    const c = szerint.get(id);
    if (!c) continue;
    ki.add(id);
    if (c.type === 'group') for (const t of csoportTartalma(v, c)) ki.add(t);
  }
  return ki;
}

export function oldalPont(d: Doboz, o: Oldal): Pont {
  switch (o) {
    case 'top':
      return { x: d.x + d.width / 2, y: d.y };
    case 'bottom':
      return { x: d.x + d.width / 2, y: d.y + d.height };
    case 'left':
      return { x: d.x, y: d.y + d.height / 2 };
    default:
      return { x: d.x + d.width, y: d.y + d.height / 2 };
  }
}

/** Az oldal, amely a célpont felé néz (a hiányzó `fromSide`/`toSide` helyett). */
export function felenezoOldal(d: Doboz, cel: Pont): Oldal {
  const dx = cel.x - (d.x + d.width / 2);
  const dy = cel.y - (d.y + d.height / 2);
  if (Math.abs(dx) * d.height >= Math.abs(dy) * d.width) return dx >= 0 ? 'right' : 'left';
  return dy >= 0 ? 'bottom' : 'top';
}

/** A dobozhoz legközelebbi oldal egy pontból (az él végének ejtésekor). */
export function legkozelebbiOldal(d: Doboz, p: Pont): Oldal {
  const tav: [Oldal, number][] = [
    ['top', Math.abs(p.y - d.y)],
    ['bottom', Math.abs(p.y - (d.y + d.height))],
    ['left', Math.abs(p.x - d.x)],
    ['right', Math.abs(p.x - (d.x + d.width))],
  ];
  return tav.sort((a, b) => a[1] - b[1])[0][0];
}

const IRANY: Record<Oldal, Pont> = { top: { x: 0, y: -1 }, bottom: { x: 0, y: 1 }, left: { x: -1, y: 0 }, right: { x: 1, y: 0 } };

export interface ElGeometria {
  /** SVG-út */
  d: string;
  /** a címke helye (az út közepe) */
  kozep: Pont;
  /** a két vég pontja és a befutó irány (egységvektor, a vég felé mutat) */
  kezd: Pont;
  kezdIrany: Pont;
  veg: Pont;
  vegIrany: Pont;
}

/** Az él útja: köbös Bézier az oldalak normálisa mentén (az Obsidian alakja). */
export function elGeometria(a: Doboz, aOldal: Oldal | undefined, b: Doboz, bOldal: Oldal | undefined): ElGeometria {
  const ak = { x: a.x + a.width / 2, y: a.y + a.height / 2 };
  const bk = { x: b.x + b.width / 2, y: b.y + b.height / 2 };
  const ao = aOldal ?? felenezoOldal(a, bk);
  const bo = bOldal ?? felenezoOldal(b, ak);
  const p0 = oldalPont(a, ao);
  const p3 = oldalPont(b, bo);
  const tav = Math.hypot(p3.x - p0.x, p3.y - p0.y);
  const k = Math.max(40, Math.min(tav / 2, 240));
  const p1 = { x: p0.x + IRANY[ao].x * k, y: p0.y + IRANY[ao].y * k };
  const p2 = { x: p3.x + IRANY[bo].x * k, y: p3.y + IRANY[bo].y * k };
  const kozep = {
    x: 0.125 * p0.x + 0.375 * p1.x + 0.375 * p2.x + 0.125 * p3.x,
    y: 0.125 * p0.y + 0.375 * p1.y + 0.375 * p2.y + 0.125 * p3.y,
  };
  return {
    d: `M${p0.x},${p0.y} C${p1.x},${p1.y} ${p2.x},${p2.y} ${p3.x},${p3.y}`,
    kozep,
    kezd: p0,
    kezdIrany: { x: -IRANY[ao].x, y: -IRANY[ao].y },
    veg: p3,
    vegIrany: { x: -IRANY[bo].x, y: -IRANY[bo].y },
  };
}

/** Nyílhegy (háromszög) a `hegy` pontban, a befutó `irany` szerint; `m` a hossza. */
export function nyilhegy(hegy: Pont, irany: Pont, m = 12): string {
  const h = Math.hypot(irany.x, irany.y) || 1;
  const ux = irany.x / h;
  const uy = irany.y / h;
  const bx = hegy.x - ux * m;
  const by = hegy.y - uy * m;
  const sz = m * 0.5;
  return `${hegy.x},${hegy.y} ${bx - uy * sz},${by + ux * sz} ${bx + uy * sz},${by - ux * sz}`;
}

/** Az átméretezés fogói és az új doboz egy fogó elmozdításából (világkoordinátában). */
export type Fogo = 'n' | 's' | 'e' | 'w' | 'ne' | 'nw' | 'se' | 'sw';
export const FOGOK: readonly Fogo[] = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'];

export function atmeretez(d: Doboz, f: Fogo, dx: number, dy: number, racs: number | null): Doboz {
  let x0 = d.x;
  let y0 = d.y;
  let x1 = d.x + d.width;
  let y1 = d.y + d.height;
  const r = (v: number) => (racs ? racsra(v, racs) : Math.round(v));
  if (f.includes('w')) x0 = Math.min(r(x0 + dx), x1 - MIN_MERET);
  if (f.includes('e')) x1 = Math.max(r(x1 + dx), x0 + MIN_MERET);
  if (f.includes('n')) y0 = Math.min(r(y0 + dy), y1 - MIN_MERET);
  if (f.includes('s')) y1 = Math.max(r(y1 + dy), y0 + MIN_MERET);
  return { x: x0, y: y0, width: x1 - x0, height: y1 - y0 };
}

// ---------------------------------------------------------------------------------------------------------------------
// Igazítás a többi kártyához (09-canvas-10, „snap to objects”): a mozgatott doboz bal/közép/jobb (és felső/közép/alsó)
// vonala a szomszédos dobozok vonalaihoz ugrik, ha a küszöbnél közelebb van; az igazítási vezetők a világ-rétegben rajzolódnak.

/** Egy vezetővonal: `x` tengelynél függőleges (`ertek` az x, `a`–`b` az y-tartomány), `y` tengelynél vízszintes. */
export interface Vezeto {
  tengely: 'x' | 'y';
  ertek: number;
  a: number;
  b: number;
}

export interface Igazitas {
  /** az eltolás, amellyel a doboz a vonalhoz kerül (0, ha nincs közel vonal) */
  dx: number;
  dy: number;
  vezetok: Vezeto[];
}

/** A doboz három vonala egy tengelyen: eleje, közepe, vége. */
const vonalak = (d: Doboz, t: 'x' | 'y'): number[] =>
  t === 'x' ? [d.x, d.x + d.width / 2, d.x + d.width] : [d.y, d.y + d.height / 2, d.y + d.height];

/** A legközelebbi vonalpár (a mozgatott doboz `sajat` vonalai és a többiek vonalai közt): a szükséges eltolás, vagy `null`. */
function legkozelebbiVonal(sajat: number[], masok: Doboz[], t: 'x' | 'y', kuszob: number): number | null {
  let legjobb: number | null = null;
  for (const m of masok)
    for (const o of vonalak(m, t))
      for (const s of sajat) {
        const el = o - s;
        if (Math.abs(el) <= kuszob && (legjobb === null || Math.abs(el) < Math.abs(legjobb))) legjobb = el;
      }
  return legjobb;
}

/** A vezetők a már igazított `d` dobozra: minden egyező vonalhoz egy szakasz, amely a doboz és az azzal egy vonalban álló dobozok
 *  teljes kiterjedését fogja át a másik tengelyen. */
function vezetok(d: Doboz, masok: Doboz[], t: 'x' | 'y', aktiv: number[]): Vezeto[] {
  const ki: Vezeto[] = [];
  const egyik = t === 'x' ? 'y' : 'x';
  const hossz = (b: Doboz) => (egyik === 'y' ? [b.y, b.y + b.height] : [b.x, b.x + b.width]);
  for (const ertek of aktiv) {
    let [a, b] = hossz(d);
    let van = false;
    for (const m of masok)
      if (vonalak(m, t).some((o) => Math.abs(o - ertek) < 0.5)) {
        const [ma, mb] = hossz(m);
        a = Math.min(a, ma);
        b = Math.max(b, mb);
        van = true;
      }
    if (van) ki.push({ tengely: t, ertek, a, b });
  }
  return ki;
}

/** Mozgatás: a doboz vonalai a többi doboz vonalaihoz ugranak (`kuszob` világ-egységben). */
export function igazitMozgatas(doboz: Doboz, masok: Doboz[], kuszob: number): Igazitas {
  const dx = legkozelebbiVonal(vonalak(doboz, 'x'), masok, 'x', kuszob) ?? 0;
  const dy = legkozelebbiVonal(vonalak(doboz, 'y'), masok, 'y', kuszob) ?? 0;
  const d: Doboz = { ...doboz, x: doboz.x + dx, y: doboz.y + dy };
  const aktivX = vonalak(d, 'x').filter((s) => masok.some((m) => vonalak(m, 'x').some((o) => Math.abs(o - s) < 0.5)));
  const aktivY = vonalak(d, 'y').filter((s) => masok.some((m) => vonalak(m, 'y').some((o) => Math.abs(o - s) < 0.5)));
  return { dx, dy, vezetok: [...vezetok(d, masok, 'x', aktivX), ...vezetok(d, masok, 'y', aktivY)] };
}

/** Átméretezés: csak a húzott oldalak igazodnak; a minimális méret megmarad. → az igazított doboz és a vezetők. */
export function igazitAtmeretezes(doboz: Doboz, fogo: Fogo, masok: Doboz[], kuszob: number): { doboz: Doboz; vezetok: Vezeto[] } {
  let x0 = doboz.x;
  let y0 = doboz.y;
  let x1 = doboz.x + doboz.width;
  let y1 = doboz.y + doboz.height;
  const kozel = (v: number, t: 'x' | 'y') => legkozelebbiVonal([v], masok, t, kuszob) ?? 0;
  if (fogo.includes('w')) x0 = Math.min(x0 + kozel(x0, 'x'), x1 - MIN_MERET);
  if (fogo.includes('e')) x1 = Math.max(x1 + kozel(x1, 'x'), x0 + MIN_MERET);
  if (fogo.includes('n')) y0 = Math.min(y0 + kozel(y0, 'y'), y1 - MIN_MERET);
  if (fogo.includes('s')) y1 = Math.max(y1 + kozel(y1, 'y'), y0 + MIN_MERET);
  const d: Doboz = { x: x0, y: y0, width: x1 - x0, height: y1 - y0 };
  const el = (v: number, t: 'x' | 'y') => masok.some((m) => vonalak(m, t).some((o) => Math.abs(o - v) < 0.5));
  const aktivX = [fogo.includes('w') ? x0 : null, fogo.includes('e') ? x1 : null].filter((v): v is number => v !== null && el(v, 'x'));
  const aktivY = [fogo.includes('n') ? y0 : null, fogo.includes('s') ? y1 : null].filter((v): v is number => v !== null && el(v, 'y'));
  return { doboz: d, vezetok: [...vezetok(d, masok, 'x', aktivX), ...vezetok(d, masok, 'y', aktivY)] };
}

/** A doboz látható-e a nézetben (a képernyő `w`×`h` méretével), `rahagyas` px ráhagyással: az élek és kártyák vágásához. */
export function nezetbenVan(d: Doboz, n: Nezet, w: number, h: number, rahagyas = 0): boolean {
  const a = vilagba(n, { x: -rahagyas, y: -rahagyas });
  const b = vilagba(n, { x: w + rahagyas, y: h + rahagyas });
  return metszi(teglalap(a, b), d);
}
