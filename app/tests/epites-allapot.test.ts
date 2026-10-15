// A build-állapot (javítókör D, 9., 10., 20. lelet): a friss válasz nem kérődik újra, a még számolt mag „számolás folyik”,
// a futó lapnál újabb dist (újrafordítás futó app mellett) újratöltést kínáló értesítést ad, a bukott lusta import nem
// gyorsítótárazódik.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { feluletUjabbAdiszken, futoEpitesLekerdezes, futoFelulet, type EpitesAllapotValasz } from '../src/lib/core/epites';
import { ertesitesek } from '../src/lib/ertesites/ertesites.svelte';
import { EPITES_FRISS_MS, EpitesAllapot } from '../src/lib/vezerlo/epites.svelte';

const valasz = (felulet: string, mag: string | null = 'abcdef123456'): EpitesAllapotValasz => ({
  ok: true,
  mag,
  reszek: [
    { resz: 'felulet', friss: true, azonosito: felulet },
    { resz: 'hej', friss: true, azonosito: 'hhhhhhhhhhhh' },
  ],
});

function metaBeallit(felulet: string | null) {
  document.querySelector('meta[name="manifold-epites"]')?.remove();
  if (felulet === null) return;
  const m = document.createElement('meta');
  m.name = 'manifold-epites';
  m.content = felulet;
  document.head.append(m);
}

beforeEach(() => {
  ertesitesek.lista = [];
});
afterEach(() => metaBeallit(null));

describe('a futó lap azonosítója', () => {
  it('a build meta-címkéjéből; nélküle üres (fejlesztői szerver, teszt)', () => {
    expect(futoFelulet()).toBe('');
    metaBeallit('0123456789abcdef0123');
    expect(futoFelulet()).toBe('0123456789abcdef0123');
    expect(new URLSearchParams(futoEpitesLekerdezes()).get('felulet')).toBe('0123456789abcdef0123');
  });

  it('a dist újabb a futó lapnál: csak ha mindkettő ismert és eltér', () => {
    expect(feluletUjabbAdiszken(valasz('0123456789ab'), '0123456789abcdef')).toBe(false);
    expect(feluletUjabbAdiszken(valasz('ffffffffffff'), '0123456789abcdef')).toBe(true);
    expect(feluletUjabbAdiszken(valasz('ffffffffffff'), '')).toBe(false);
    expect(feluletUjabbAdiszken(valasz(''), '0123456789abcdef')).toBe(false);
    expect(feluletUjabbAdiszken(null, '0123456789abcdef')).toBe(false);
  });
});

describe('a build-állapot tára', () => {
  it('a friss (60 s-on belüli) választ nem kéri újra; utána vagy kényszerrel igen', async () => {
    let most = 1000;
    const kero = vi.fn(async () => valasz(''));
    const a = new EpitesAllapot(kero, () => most);
    await a.frissit();
    await a.frissit();
    expect(kero).toHaveBeenCalledTimes(1);
    most += EPITES_FRISS_MS + 1;
    await a.frissit();
    expect(kero).toHaveBeenCalledTimes(2);
    await a.frissit(true);
    expect(kero).toHaveBeenCalledTimes(3);
  });

  it('a még számolt mag (null vagy hiányzó): „számol”, és nem számít frissnek', async () => {
    const kero = vi.fn(async () => valasz('', null));
    const a = new EpitesAllapot(kero, () => 0);
    await a.frissit();
    expect(a.szamol).toBe(true);
    await a.frissit();
    expect(kero).toHaveBeenCalledTimes(2);
    kero.mockImplementation(async () => {
      const v = valasz('');
      delete v.mag;
      return v;
    });
    await a.frissit();
    expect(a.szamol).toBe(true);
  });

  it('a párhuzamos kérések egy lekérésbe olvadnak; a hiba magyar szövegként', async () => {
    const kero = vi.fn(async () => {
      throw new TypeError('Load failed');
    });
    const a = new EpitesAllapot(kero, () => 0);
    await Promise.all([a.frissit(), a.frissit(true)]);
    expect(kero).toHaveBeenCalledTimes(1);
    expect(a.hiba).toBe('A core nem érhető el (megszakadt a kapcsolat).');
  });

  it('a futó lapnál újabb dist: tartós értesítés újratöltéssel, egy kulcson (nem ismétlődik)', async () => {
    metaBeallit('0123456789abcdef');
    const a = new EpitesAllapot(async () => valasz('ffffffffffff'), () => 0);
    await a.frissit(true);
    await a.frissit(true);
    const e = ertesitesek.lista.filter((x) => x.cim === 'A felület frissült');
    expect(e).toHaveLength(1);
    expect(e[0].idotartam).toBe(0);
    expect(e[0].muvelet?.nev).toBe('Újratöltés');
  });
});

describe('a bukott lusta import', () => {
  afterEach(() => {
    vi.doUnmock('mermaid');
    vi.resetModules();
  });

  it('a Mermaid bukott importja nem gyorsítótárazódik, és a build-állapotot ellenőrzi', async () => {
    vi.resetModules();
    let bukik = true;
    vi.doMock('mermaid', () => {
      if (bukik) throw new Error('Importing a module script failed.');
      return { default: { initialize: () => {}, render: async () => ({ svg: '<svg></svg>' }) } };
    });
    const epites = await import('../src/lib/vezerlo/epites.svelte');
    const frissit = vi.spyOn(epites.epitesAllapot, 'frissit').mockResolvedValue();
    const { mermaidRenderelo } = await import('../src/szerkeszto/renderelok/mermaid');
    const cel = document.createElement('div');
    const k = { jel: new AbortController().signal } as never;
    await expect(mermaidRenderelo.render('graph TD; A-->B', cel, k)).rejects.toThrow();
    expect(frissit).toHaveBeenCalledWith(true);
    bukik = false;
    vi.resetModules(); // a modul-gyorsítótár üríthető; a renderelő saját ígérete nem maradhat bukott
    await expect(mermaidRenderelo.render('graph TD; A-->B', cel, k)).resolves.not.toThrow();
  });
});
