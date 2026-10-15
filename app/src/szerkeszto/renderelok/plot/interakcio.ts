// A grafikon interakciója (C35a), a rajzoló-könyvtártól függetlenül: az egér alatti érték a legközelebbi görbén, a
// nagyítás számítása (az eredmény a tábla új ablaka), a billentyűzet. Tiszta függvények. (A húzást a JSXGraph maga kezeli.)

import type { Rajzterv } from './terv';

export type Tartomany = [number, number];
export interface Nezet {
  x: Tartomany;
  y: Tartomany;
}
export interface Meret {
  szelesseg: number;
  magassag: number;
}
export interface Talalat {
  /** a görbe sorszáma a `terv.gorbek`-ben */
  gorbe: number;
  x: number;
  y: number;
}

/** A legkisebb és a legnagyobb ablak-szélesség (a lebegőpontos pontosság és a core 1e7-es plafonjának a fele alatt). */
export const MIN_SPAN = 1e-6;
export const MAX_SPAN = 1e6;
const KUSZOB_PX = 14;
const PARAM_MINTA = 600;

/** A kurzor (felhasználói koordináta) alatti vagy legközelebbi görbepont, ha a pixelben `KUSZOB_PX`-en belül van. */
export function legkozelebbi(terv: Rajzterv, nezet: Nezet, meret: Meret, x: number, y: number): Talalat | null {
  const pxY = meret.magassag / (nezet.y[1] - nezet.y[0]);
  const pxX = meret.szelesseg / (nezet.x[1] - nezet.x[0]);
  let legjobb: (Talalat & { tav: number }) | null = null;
  terv.gorbek.forEach((g, i) => {
    if (g.fajta === 'fuggveny') {
      const v = g.ertek(x);
      if (!Number.isFinite(v)) return;
      const tav = Math.abs(v - y) * pxY;
      if (tav <= KUSZOB_PX && (!legjobb || tav < legjobb.tav)) legjobb = { gorbe: i, x, y: v, tav };
    } else if (g.param) {
      const { x: fx, y: fy, lo, hi } = g.param;
      for (let k = 0; k < PARAM_MINTA; k++) {
        const t = lo + ((hi - lo) * k) / (PARAM_MINTA - 1);
        const px = fx(t);
        const py = fy(t);
        if (!Number.isFinite(px) || !Number.isFinite(py)) continue;
        const tav = Math.hypot((px - x) * pxX, (py - y) * pxY);
        if (tav <= KUSZOB_PX && (!legjobb || tav < legjobb.tav)) legjobb = { gorbe: i, x: px, y: py, tav };
      }
    }
  });
  if (!legjobb) return null;
  const { gorbe, x: tx, y: ty } = legjobb as Talalat & { tav: number };
  return { gorbe, x: tx, y: ty };
}

export function kozeppont(n: Nezet): [number, number] {
  return [(n.x[0] + n.x[1]) / 2, (n.y[0] + n.y[1]) / 2];
}

function szukit(lo: number, hi: number, kozep: number): Tartomany {
  const span = hi - lo;
  const uj = Math.min(MAX_SPAN, Math.max(MIN_SPAN, span));
  if (uj === span) return [lo, hi];
  const arany = (kozep - lo) / span;
  return [kozep - uj * arany, kozep + uj * (1 - arany)];
}

/** Nagyítás a (cx, cy) pont körül: `tenyezo` < 1 nagyít (az ablak kisebb), > 1 kicsinyít; a pont a helyén marad. */
export function nagyit(n: Nezet, cx: number, cy: number, tenyezo: number): Nezet {
  const ax: Tartomany = [cx + (n.x[0] - cx) * tenyezo, cx + (n.x[1] - cx) * tenyezo];
  const ay: Tartomany = [cy + (n.y[0] - cy) * tenyezo, cy + (n.y[1] - cy) * tenyezo];
  return { x: szukit(ax[0], ax[1], cx), y: szukit(ay[0], ay[1], cy) };
}

/** A fókuszban álló grafikon billentyűi: nyilak mozgatnak (az ablak tizede), `+`/`=` nagyít, `-` kicsinyít, `0` az
 *  alaphelyzet. `null`: nem a grafikon billentyűje (a böngésző kezeli). */
export function billentyu(n: Nezet, kulcs: string, alap: Nezet): Nezet | null {
  const sx = (n.x[1] - n.x[0]) / 10;
  const sy = (n.y[1] - n.y[0]) / 10;
  switch (kulcs) {
    case 'ArrowRight':
      return { x: [n.x[0] + sx, n.x[1] + sx], y: n.y };
    case 'ArrowLeft':
      return { x: [n.x[0] - sx, n.x[1] - sx], y: n.y };
    case 'ArrowUp':
      return { x: n.x, y: [n.y[0] + sy, n.y[1] + sy] };
    case 'ArrowDown':
      return { x: n.x, y: [n.y[0] - sy, n.y[1] - sy] };
    case '+':
    case '=': {
      const [cx, cy] = kozeppont(n);
      return nagyit(n, cx, cy, 0.8);
    }
    case '-': {
      const [cx, cy] = kozeppont(n);
      return nagyit(n, cx, cy, 1.25);
    }
    case '0':
      return { x: [...alap.x], y: [...alap.y] };
    default:
      return null;
  }
}
