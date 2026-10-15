// Hamis JSXGraph-könyvtár a ```plot tesztekhez: a hívásokat naplózza, a tábla ablakát tárolja. A valódi könyvtár
// viselkedését a Browser-pane-es próba és a K104 igazolja.
import { vi } from 'vitest';
import type { Konyvtar } from '../src/szerkeszto/renderelok/plot/rajzolo';

/* eslint-disable @typescript-eslint/no-explicit-any */
export interface Hivas {
  tipus: string;
  szulok: any[];
  attr: Record<string, any>;
  elem: any;
}

export function hamisKonyvtar() {
  const naplo = { init: [] as { doboz: HTMLElement; attr: any }[], hivasok: [] as Hivas[], bbox: [] as number[][], torolt: [] as any[], szabad: 0, esemenyek: {} as Record<string, () => void> };
  const tablak: any[] = [];
  const konyvtar: Konyvtar = {
    JSXGraph: {
      initBoard(doboz: HTMLElement, attr: any) {
        naplo.init.push({ doboz, attr });
        const bb = [...attr.boundingbox];
        const tabla = {
          canvasWidth: 400,
          canvasHeight: 300,
          unitX: 40,
          unitY: 30,
          origin: { scrCoords: [1, 200, 150] },
          getBoundingBox: () => [...bb],
          setBoundingBox: (n: number[]) => {
            bb.splice(0, 4, ...n);
            naplo.bbox.push([...n]);
          },
          create(tipus: string, szulok: any[], a: Record<string, any> = {}) {
            const elem: any = { tipus };
            naplo.hivasok.push({ tipus, szulok, attr: a, elem });
            return elem;
          },
          removeObject: (e: any) => naplo.torolt.push(e),
          update: vi.fn(),
          on: (nev: string, fn: () => void) => (naplo.esemenyek[nev] = fn),
          getUsrCoordsOfMouse: (e: any) => [e.__ux ?? 0, e.__uy ?? 0],
        };
        tablak.push(tabla);
        return tabla;
      },
      freeBoard: () => {
        naplo.szabad++;
      },
    },
  };
  return { konyvtar, naplo, tablak };
}

