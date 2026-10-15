// A Bases kártyanézete (C12b 10. lépés): rács a cardSize szerint, borítókép (kicsinyített, lusta), a nem üres
// tulajdonságok felirattal, csoportfejlécek, 100-as adagok.

import { cleanup, fireEvent, render, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Kartyak from '../src/bazis/Kartyak.svelte';
import type { Oszlop, Sor, Valasz } from '../src/bazis/tipusok';

const OSZLOPOK: Oszlop[] = [
  { id: 'file.name', nev: 'Fájlnév', ter: 'file', tipus: 'text', szerkesztheto: false, szelesseg: null },
  { id: 'Author', nev: 'Szerző', ter: 'note', tipus: 'text', szerkesztheto: true, szelesseg: null },
  { id: 'Tags', nev: 'Címkék', ter: 'note', tipus: 'tags', szerkesztheto: true, szelesseg: null },
];

function sor(i: number, kieg: Partial<Sor> = {}): Sor {
  const ut = `X03 - Books/Könyv ${i}.md`;
  return {
    ut,
    nev: `Könyv ${i}`,
    md: true,
    cellak: [{ t: 'link', cel: ut, ut, nev: `Könyv ${i}` }, i % 2 ? `Szerző ${i}` : null, { t: 'lista', e: i % 3 ? ['a'] : [] }],
    ...kieg,
  };
}

function valasz(db: number, beallitas: Record<string, unknown> = {}, kieg: Partial<Valasz> = {}): Valasz {
  return {
    ok: true,
    nezetek: [{ nev: 'Kártyák', tipus: 'cards', ismert: true }],
    nezet: { index: 0, nev: 'Kártyák', tipus: 'cards', eredeti_tipus: 'cards', beallitas },
    oszlopok: OSZLOPOK,
    sorok: Array.from({ length: db }, (_, i) => sor(i + 1)),
    csoportok: null,
    osszesitok: {},
    osszes: db,
    levagva: false,
    hibak: [],
    figyelmeztetesek: [],
    ido_ms: 1,
    generacio: 1,
    ...kieg,
  };
}

beforeEach(() => {
  vi.stubGlobal('fetch', async () => new Response(JSON.stringify({ media_token: 'tok' }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('Kartyak', () => {
  it('minden sor egy kártya: a cím a fájl linkje, csak a nem üres tulajdonságok látszanak felirattal', () => {
    const { container } = render(Kartyak, { props: { valasz: valasz(3) } });
    const k = container.querySelectorAll('.kartya');
    expect(k).toHaveLength(3);
    expect(k[0].querySelector('.cim')?.textContent?.trim()).toBe('Könyv 1');
    const tul = (e: Element) => [...e.querySelectorAll('.tul .felirat')].map((x) => x.textContent);
    expect(tul(k[0])).toEqual(['Szerző', 'Címkék']); // Könyv 1: szerző van, lista egyelemű
    expect(tul(k[1])).toEqual(['Címkék']); // Könyv 2: nincs szerző
    expect(tul(k[2])).toEqual(['Szerző']); // Könyv 3: üres lista
    expect(k[2].querySelector('.tul .ertek')?.textContent?.trim()).toBe('Szerző 3');
  });

  it('az üres lista nem ad sort', () => {
    const v = valasz(3);
    v.sorok[2].cellak[2] = { t: 'lista', e: [] };
    const { container } = render(Kartyak, { props: { valasz: v } });
    expect([...container.querySelectorAll('.kartya')[2].querySelectorAll('.tul .felirat')].map((e) => e.textContent)).toEqual(['Szerző']);
  });

  it('a kártyaméret a cardSize (120 és 800 px közé szorítva), alapból 200', () => {
    const racs = (b: Record<string, unknown>) => render(Kartyak, { props: { valasz: valasz(1, b) } }).container.querySelector<HTMLElement>('.racs')!.style.getPropertyValue('--kartya-meret');
    expect(racs({})).toBe('200px');
    cleanup();
    expect(racs({ cardSize: 420 })).toBe('420px');
    cleanup();
    expect(racs({ cardSize: 20 })).toBe('120px');
    cleanup();
    expect(racs({ cardSize: 9000 })).toBe('800px');
  });

  it('borítókép: a vault-képből kicsinyített URL, imageFit és imageAspectRatio; szín és külső URL', async () => {
    const v = valasz(3, { image: 'Cover', imageFit: 'contain', imageAspectRatio: 0.7 });
    v.sorok[0].kep = { t: 'ut', ut: 'Media/Képek/a b.png' };
    v.sorok[1].kep = { t: 'szin', v: '#336699' };
    v.sorok[2].kep = { t: 'kulso', url: 'https://x.test/k.png' };
    const { container } = render(Kartyak, { props: { valasz: v } });
    const kep = await waitFor(() => {
      const i = container.querySelector<HTMLImageElement>('.kartya img');
      expect(i).not.toBeNull();
      return i!;
    });
    expect(kep.getAttribute('src')).toBe('/media/tok/Media/K%C3%A9pek/a%20b.png?w=400');
    expect(kep.style.objectFit).toBe('contain');
    const dobozok = container.querySelectorAll<HTMLElement>('.kep');
    expect(dobozok[0].style.aspectRatio).toMatch(/^0\.7/);
    expect(dobozok[1].style.background).toContain('rgb(51, 102, 153)');
    expect(dobozok[2].textContent).toContain('külső kép');
    expect(dobozok[2].querySelector('img')).toBeNull(); // a CSP miatt nem tölthető
  });

  it('kép nélküli kártyán nincs képterület', () => {
    const { container } = render(Kartyak, { props: { valasz: valasz(2) } });
    expect(container.querySelector('.kep')).toBeNull();
  });

  it('a csoportosított nézet csoportfejlécekkel', () => {
    const v = valasz(4, { groupBy: { property: 'Author' } }, {
      csoportok: [
        { kulcs: null, cimke: '', tol: 0, db: 1, osszesitok: {}, huzhato: true },
        { kulcs: 'Szerző', cimke: 'Szerző', tol: 1, db: 3, osszesitok: {}, huzhato: true },
      ],
    });
    const { container } = render(Kartyak, { props: { valasz: v } });
    const fejek = [...container.querySelectorAll('.csoport')].map((e) => e.textContent?.replace(/\s+/g, ' ').trim());
    expect(fejek).toEqual(['Nincs érték 1', 'Szerző 3']);
    expect(container.querySelectorAll('.kartya')).toHaveLength(4);
  });

  it('250 sor 100-as adagokban rajzolódik, a „További” gomb hozza a következőt', async () => {
    const { container } = render(Kartyak, { props: { valasz: valasz(250) } });
    expect(container.querySelectorAll('.kartya')).toHaveLength(100);
    const gomb = container.querySelector<HTMLButtonElement>('.tovabb')!;
    expect(gomb.textContent).toContain('További 100 a(z) 150 közül');
    await fireEvent.click(gomb);
    expect(container.querySelectorAll('.kartya')).toHaveLength(200);
    await fireEvent.click(container.querySelector('.tovabb')!);
    expect(container.querySelectorAll('.kartya')).toHaveLength(250);
    expect(container.querySelector('.tovabb')).toBeNull();
  });

  it('üres találat: jelzés', () => {
    const { container } = render(Kartyak, { props: { valasz: valasz(0) } });
    expect(container.querySelector('.ures')?.textContent).toContain('Nincs a feltételeknek megfelelő fájl');
  });
});
