// Determinisztikus kezdőállás (a legacy `kezdoAllas` portja): minden felső mappa egy körcikk, azon belül
// napraforgó-spirál (aranyszög) fokszám szerint rendezve. Ugyanarra a gráfra mindig ugyanazt adja, és a mappák
// már a fizika előtt is együtt vannak. Frissítéskor a régi pozíciók megmaradnak, az új csúcsok a szomszédaik
// átlagába kerülnek (`pozicioFrissites`).

import { locale } from '../i18n';
export interface KezdoBemenet {
  n: number;
  felsoMappa: readonly string[];
  fok: ArrayLike<number>;
}

const ARANYSZOG = Math.PI * (3 - Math.sqrt(5));

export function kezdoAllas(g: KezdoBemenet): Float32Array {
  const { n } = g;
  const poz = new Float32Array(2 * n);
  const csoport = new Map<string, number[]>();
  for (let i = 0; i < n; i++) {
    const k = g.felsoMappa[i] || '~';
    let l = csoport.get(k);
    if (!l) csoport.set(k, (l = []));
    l.push(i);
  }
  const kulcsok = [...csoport.keys()].sort((a, b) => a.localeCompare(b, locale()));
  const R = 9 * Math.sqrt(n);
  let sz = 0;
  for (const k of kulcsok) {
    const tagok = csoport.get(k)!.sort((a, b) => g.fok[b] - g.fok[a] || a - b);
    const resz = tagok.length / n;
    const szog = 2 * Math.PI * (sz + resz / 2);
    sz += resz;
    const cx = Math.cos(szog) * R * 0.55;
    const cy = Math.sin(szog) * R * 0.55;
    tagok.forEach((i, j) => {
      const r = 8 * Math.sqrt(j + 0.5);
      poz[2 * i] = cx + r * Math.cos(j * ARANYSZOG);
      poz[2 * i + 1] = cy + r * Math.sin(j * ARANYSZOG);
    });
  }
  return poz;
}

/**
 * Új szerkezet pozíciói: a régi út helyzete megmarad, az új csúcs a már elhelyezett szomszédai átlagába kerül
 * (kis eltolással), ha nincs ilyen, a kezdőállásba. `regi`: út → [x, y].
 */
export function pozicioFrissites(
  g: KezdoBemenet & { ut: readonly string[]; kezd: Int32Array; lista: Int32Array },
  regi: ReadonlyMap<string, readonly [number, number]>,
): { poz: Float32Array; uj: number } {
  const kezdo = kezdoAllas(g);
  const poz = new Float32Array(2 * g.n);
  const van = new Uint8Array(g.n);
  let uj = 0;
  for (let i = 0; i < g.n; i++) {
    const r = regi.get(g.ut[i]);
    if (r) {
      poz[2 * i] = r[0];
      poz[2 * i + 1] = r[1];
      van[i] = 1;
    } else uj++;
  }
  for (let i = 0; i < g.n; i++) {
    if (van[i]) continue;
    let sx = 0;
    let sy = 0;
    let db = 0;
    for (let e = g.kezd[i]; e < g.kezd[i + 1]; e++) {
      const s = g.lista[e];
      if (!van[s]) continue;
      sx += poz[2 * s];
      sy += poz[2 * s + 1];
      db++;
    }
    if (db) {
      poz[2 * i] = sx / db + ((i % 7) - 3) * 2;
      poz[2 * i + 1] = sy / db + ((i % 5) - 2) * 2;
    } else {
      poz[2 * i] = kezdo[2 * i];
      poz[2 * i + 1] = kezdo[2 * i + 1];
    }
  }
  return { poz, uj };
}
