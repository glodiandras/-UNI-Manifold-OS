// A Bevitel szakasz behúzott/kiválasztott videója (C20b, 7. pont): a fájl darabonként a core beérkező mappájába kerül
// (`POST /api/video/bejovo`, sorrendhelyes `offset`-tel, a JSON-törzs korlátja alatt), utána a `video_integralas` feladat
// (`POST /api/feladatok {csoport}`) staging-forrást készít belőle, és a vaultba viszi (gépi írás, tételenként visszavonható).
// A vaultba a felület nem ír.

import { kerdez } from '../core/api';
import type { Feladat } from './tipusok';

/** Egy feltöltött darab (dekódolva); a base64-es törzs így ~8 MiB, a core 16 MiB-os JSON-korlátja alatt. */
export const DARAB = 6 * 1024 * 1024;
const VIDEO = /\.(mp4|m4v|mov|mkv|webm|avi)$/i;

export function videoFajl(f: { name: string }): boolean {
  return VIDEO.test(f.name);
}

async function base64(f: Blob): Promise<string> {
  const b = new Uint8Array(await f.arrayBuffer());
  let s = '';
  for (let i = 0; i < b.length; i += 0x8000) s += String.fromCharCode(...b.subarray(i, i + 0x8000));
  return btoa(s);
}

export interface Haladas {
  fajl: string;
  i: number;
  n: number;
  szazalek: number;
}

/** A videók feltöltése egy csoportba, majd a bevitel indítása. → az új feladat (vagy hiba: kivétel). */
export async function videoFeltolt(
  fajlok: File[],
  opciok: { proba?: boolean; haladas?: (h: Haladas) => void } = {},
  keres = kerdez,
): Promise<Feladat> {
  const videok = fajlok.filter(videoFajl);
  if (!videok.length) throw new Error('Nincs videófájl (mp4, m4v, mov, mkv, webm, avi).');
  let csoport: string | undefined;
  for (const [i, f] of videok.entries()) {
    let offset = 0;
    do {
      const darab = f.slice(offset, offset + DARAB);
      const vege = offset + darab.size >= f.size;
      const r = await keres<{ csoport: string; offset?: number }>('/api/video/bejovo', {
        metodus: 'POST',
        torzs: { nev: f.name, offset, adat: await base64(darab), vege, ...(csoport ? { csoport } : {}) },
        idokorlat: 120_000,
      });
      csoport = r.csoport;
      offset += darab.size;
      opciok.haladas?.({ fajl: f.name, i, n: videok.length, szazalek: f.size ? Math.round((100 * offset) / f.size) : 100 });
    } while (offset < f.size);
  }
  return keres<Feladat>('/api/feladatok', {
    metodus: 'POST',
    torzs: { tipus: 'video_integralas', parameterek: { csoport, ...(opciok.proba ? { proba: true } : {}) } },
    idokorlat: 10_000,
  });
}

/** Rejtett fájlválasztó: a kiválasztott videók. */
export function videoValaszt(): Promise<File[]> {
  return new Promise((kesz) => {
    const be = document.createElement('input');
    be.type = 'file';
    be.multiple = true;
    be.accept = 'video/*,.mkv,.webm';
    be.addEventListener('change', () => kesz(Array.from(be.files ?? [])), { once: true });
    be.click();
  });
}
