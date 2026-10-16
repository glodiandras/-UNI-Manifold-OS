// A tulajdonság-szerkesztő core-hívásai. Tiszta számoló végpontok: a core nem ír fájlt, az írás a nyitott
// dokumentumon át megy (egy írási út: automatikus mentés, ütközés, ⌘Z).

import { kerdez } from '../../lib/core/api';
import { tartalmiNyelv } from '../../lib/munkater/nyelv.svelte';
import { asszisztensApi } from '../../lib/asszisztens/api';
import { vezerloKapcsolok } from '../../lib/vezerlo/kapcsolok.svelte';
import { beallitKiserok } from '../../osszefoglalas/allando';
import type { Elemzes, ErtekJavaslatok, KulcsJavaslat, ModositEredmeny, Muvelet, OsszefesulesEredmeny, Sema, TulajdonsagApi } from './tipusok';

/** A sablon frontmatterének összefésülése a jegyzetével (C32b): tiszta számoló, nem ír fájlt. */
export function osszefesul(ut: string, fm: string | null, sablonFm: string): Promise<OsszefesulesEredmeny> {
  return kerdez<OsszefesulesEredmeny>('/api/vault/tulajdonsagok/osszefesul', {
    metodus: 'POST',
    torzs: { ut, fm, sablon_fm: sablonFm },
    idokorlat: 8000,
  });
}

/** A munkatér kísérőmappái a core-ból (`GET /api/vault/sema`): a kártya-, kvíz- és összefoglaló-állandók igazodnak hozzájuk. Hiba esetén a
 *  szállított alap marad (a felület nem akad el rajta). */
export async function kiserokBetolt(keres: typeof kerdez = kerdez): Promise<void> {
  try {
    const s = await keres<Sema>('/api/vault/sema', { idokorlat: 5000 });
    beallitKiserok(s.kisero, s.kisero_elotag);
    tartalmiNyelv.beallit(s.nyelv);
  } catch {
    /* az alap marad */
  }
}

export function tulajdonsagApi(): TulajdonsagApi {
  return {
    elemez: (ut, fm) =>
      kerdez<Elemzes>('/api/vault/tulajdonsagok/elemez', { metodus: 'POST', torzs: { ut, fm }, idokorlat: 8000 }),
    modosit: async (ut, fm, m: Muvelet, megerosit) => {
      const r = await kerdez<ModositEredmeny>('/api/vault/tulajdonsagok/modosit', {
        metodus: 'POST',
        torzs: { ut, fm, megerosit, forras: 'felhasznalo', ...m },
        idokorlat: 8000,
      });
      if (r.ok && r.valtozas) cimkeTanul(ut, fm, m);
      return r;
    },
    sema: async (ut) => {
      const s = await kerdez<Sema>(`/api/vault/sema?ut=${encodeURIComponent(ut)}`, { idokorlat: 5000 });
      beallitKiserok(s.kisero, s.kisero_elotag);
      tartalmiNyelv.beallit(s.nyelv);
      return s;
    },
    kulcsok: (ut) =>
      kerdez<{ kulcsok: KulcsJavaslat[]; index_kesz: boolean }>(`/api/vault/tulajdonsagok/kulcsok?ut=${encodeURIComponent(ut)}`, { idokorlat: 5000 }),
    ertekek: (ut, kulcs) =>
      kerdez<ErtekJavaslatok>(`/api/vault/tulajdonsagok/ertekek?ut=${encodeURIComponent(ut)}&kulcs=${encodeURIComponent(kulcs)}`, { idokorlat: 5000 }),
  };
}

/** A frontmatter `Tags` értékei (könnyű olvasás a tanuló jelzéséhez; a pontos elemzés a core-é). */
export function fmCimkek(fm: string | null): string[] {
  if (!fm) return [];
  const sorok = fm.split(/\r?\n/);
  const i = sorok.findIndex((s) => /^tags\s*:/i.test(s));
  if (i < 0) return [];
  const tisztit = (x: string) => x.trim().replace(/^["']|["']$/g, '').replace(/^#/, '');
  const sajat = sorok[i].replace(/^tags\s*:/i, '').trim();
  if (sajat) return sajat.replace(/^\[|\]$/g, '').split(',').map(tisztit).filter(Boolean);
  const ki: string[] = [];
  for (const s of sorok.slice(i + 1)) {
    const m = /^\s+-\s*(.*)$/.exec(s);
    if (!m) break;
    const c = tisztit(m[1]);
    if (c) ki.push(c);
  }
  return ki;
}

/** J1: a felhasználó által hozzáadott címkék jelzése az Asszisztens tanuló magjának (ismétlődő művelet). */
function cimkeTanul(ut: string, fm: string | null, m: Muvelet): void {
  if (m.muvelet !== 'beallit' || m.kulcs.toLowerCase() !== 'tags' || !vezerloKapcsolok.ertek.asszisztens || !ut.toLowerCase().endsWith('.md')) return;
  const uj = Array.isArray(m.ertek) ? m.ertek.map(String) : typeof m.ertek === 'string' ? [m.ertek] : [];
  const regi = new Set(fmCimkek(fm).map((c) => c.toLowerCase()));
  for (const c of uj.map((x) => x.replace(/^#/, '').trim()).filter((x) => x && !regi.has(x.toLowerCase())))
    void asszisztensApi.tanul('cimke', ut, c).catch(() => undefined);
}
