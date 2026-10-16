// A PDF kiemelései (C16): a core végpontjai (a kiemelés-fájl formátuma a core-é, `core/pdfkiemeles.py`) és a
// lapokra rajzolt réteg. A réteg a lap `div`-jébe kerül, százalékos téglalapokkal (a nagyítás nem rajzolja újra).

import { kerdez } from '../../lib/core/api';
import { t } from '../../lib/i18n';
import type { Teglalap } from './kijeloles';

export interface Kiemeles {
  id: string;
  oldal: number;
  szoveg: string;
  teglalapok: Teglalap[];
}

export interface KiemelesLista {
  pdf: string;
  fajl: string | null;
  hash: string | null;
  kiemelesek: Kiemeles[];
}

export interface UjKiemeles {
  ok: boolean;
  id: string;
  fajl: string;
  hash: string;
  cel: string;
  oldal: number;
  szoveg: string;
  teglalapok: Teglalap[];
  figyelmeztetes: string | null;
}

export const kiemelesApi = {
  lista: (ut: string) => kerdez<KiemelesLista>(`/api/pdf/kiemelesek?ut=${encodeURIComponent(ut)}`, { idokorlat: 8000 }),
  hozzaad: (ut: string, oldal: number, szoveg: string, teglalapok: Teglalap[]) =>
    kerdez<UjKiemeles>('/api/pdf/kiemeles', { metodus: 'POST', torzs: { ut, oldal, szoveg, teglalapok }, idokorlat: 15000 }),
  torol: (ut: string, id: string, alap: string | null) =>
    kerdez<{ ok: boolean; fajl: string; hash: string }>('/api/pdf/kiemeles/torol', {
      metodus: 'POST',
      torzs: { ut, id, alap },
      idokorlat: 15000,
    }),
};

const RETEG = 'mf-kiemeles-reteg';

/** A lap kiemelés-rétege (a meglévőt cseréli). A téglalap gomb: kattintásra a `valaszt` kapja. */
export function retegRajzol(lapDiv: HTMLElement, lista: Kiemeles[], valaszt: (k: Kiemeles, el: HTMLElement) => void): void {
  lapDiv.querySelector(`:scope > .${RETEG}`)?.remove();
  if (!lista.length) return;
  const r = document.createElement('div');
  r.className = RETEG;
  for (const k of lista)
    for (const [i, [x, y, w, h]] of k.teglalapok.entries()) {
      const d = document.createElement(i === 0 ? 'button' : 'span');
      d.className = 'mf-kiemeles';
      d.style.left = `${x * 100}%`;
      d.style.top = `${y * 100}%`;
      d.style.width = `${w * 100}%`;
      d.style.height = `${h * 100}%`;
      d.dataset.id = k.id;
      if (d instanceof HTMLButtonElement) {
        d.type = 'button';
        d.setAttribute('aria-label', t('Kiemelés: {szoveg}', { szoveg: k.szoveg.slice(0, 80) }));
      }
      d.addEventListener('click', (e) => {
        e.stopPropagation();
        valaszt(k, d);
      });
      r.appendChild(d);
    }
  lapDiv.appendChild(r);
}
