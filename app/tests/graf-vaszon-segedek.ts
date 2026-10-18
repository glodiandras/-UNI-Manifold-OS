// A gráf-vászon tesztek közös segédje (F11): felvevő 2D-kontextus és hamis rAF. A kontextus a rajzoló hívásait a hívás
// pillanatában érvényes festési állapottal együtt rögzíti, így a színek, vastagságok, sugarak és a szaggatás vizsgálható.

export interface Hivas {
  fn: string;
  args: unknown[];
  fillStyle: unknown;
  strokeStyle: unknown;
  lineWidth: unknown;
  globalAlpha: unknown;
  dash: number[];
}

export interface FelvevoKontextus {
  ctx: CanvasRenderingContext2D;
  hivasok: Hivas[];
  torol(): void;
  nev(fn: string): Hivas[];
}

export function felvevoKontextus(): FelvevoKontextus {
  const hivasok: Hivas[] = [];
  const allapot: Record<string, unknown> = { fillStyle: '#000', strokeStyle: '#000', lineWidth: 1, globalAlpha: 1 };
  let dash: number[] = [];
  const cel: Record<string | symbol, unknown> = {};
  const ctx = new Proxy(cel, {
    get: (_t, k) => {
      if (typeof k !== 'string') return undefined;
      if (k in allapot) return allapot[k];
      if (k === 'measureText') return () => ({ width: 10 });
      if (k === 'canvas') return null;
      return (...args: unknown[]) => {
        if (k === 'setLineDash') dash = (args[0] as number[]).slice();
        hivasok.push({ fn: k, args, fillStyle: allapot.fillStyle, strokeStyle: allapot.strokeStyle, lineWidth: allapot.lineWidth, globalAlpha: allapot.globalAlpha, dash: dash.slice() });
      };
    },
    set: (_t, k, v) => {
      allapot[k as string] = v;
      return true;
    },
  }) as unknown as CanvasRenderingContext2D;
  return { ctx, hivasok, torol: () => (hivasok.length = 0), nev: (fn) => hivasok.filter((h) => h.fn === fn) };
}

export const SZINEK = {
  jegyzet: '#101010',
  canvas: '#102010',
  melleklet: '#103010',
  el: '#202020',
  elKiemelt: '#303030',
  kijelolt: '#404040',
  felulet: '#fafafa',
  szoveg: '#505050',
  halo: '#fafafa',
  talalat: '#606060',
  cimke: '#707070',
  feloldatlan: '#808080',
};
