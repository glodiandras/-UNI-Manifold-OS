// A beágyazott pakli (C23b) jsdom-ban: kérdés → szóköz → a válasz és a négy gomb az intervallummal → „Jó” → a következő kártya;
// üres pakli: „Ma nincs esedékes kártya”.

import { cleanup, fireEvent, render } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Kartya, KartyaApi } from '../src/kartya/api';
import { IsmetlesMenet } from '../src/kartya/menet.svelte';
import Pakli from '../src/kartya/Pakli.svelte';

afterEach(() => cleanup());

const k = (azon: string): Kartya => ({
  azon, jegyzet: 'ATTCHMNTS - cards/A — kártyák.md', kerdes: `Mi a ${azon}?`, valasz: `Ez a ${azon}.`, forras: 'A#^m-1a2b',
  allapot: 0, uj: true, esedekes: null, sor: 1, esedekes_most: true, elorejelzes: { 1: 60, 2: 360, 3: 600, 4: 345600 },
});

function menet(kartyak: Kartya[]) {
  const valasz = vi.fn(async (azon: string, jegy: number) => ({ ok: true, allapot: {}, tracker: { ut: 'A.md', adat: { jegy, kartya_id: azon } } }));
  const api = {
    jegyzet: async (ut: string) => ({ ok: true, ut, kartyak, esedekes: 0, uj: kartyak.length, osszes: kartyak.length, hibak: [] }),
    valasz,
  } as unknown as KartyaApi;
  return { m: new IsmetlesMenet({ tipus: 'pakli', ut: 'ATTCHMNTS - cards/A — kártyák.md' }, { api }), valasz };
}

describe('Pakli', () => {
  it('kérdés, fordítás, értékelés gombbal', async () => {
    const { m, valasz } = menet([k('c-1'), k('c-2')]);
    await m.betolt();
    const { container } = render(Pakli, { props: { menet: m, cim: 'A — kártyák' } });
    expect(container.textContent).toContain('Mi a c-1?');
    expect(container.textContent).not.toContain('Ez a c-1.');
    await fireEvent.keyDown(container.querySelector('.pakli')!, { key: ' ' });
    expect(container.textContent).toContain('Ez a c-1.');
    const gombok = [...container.querySelectorAll('.pakli-gombok button')];
    expect(gombok.map((g) => g.textContent?.replace(/\s+/g, ' ').trim())).toEqual(['Újra 1 p 1', 'Nehéz 6 p 2', 'Jó 10 p 3', 'Könnyű 4 n 4']);
    await fireEvent.click(gombok[2]);
    await vi.waitFor(() => expect(container.textContent).toContain('Mi a c-2?'));
    expect(valasz).toHaveBeenCalledWith('c-1', 3, expect.any(Number));
  });

  it('üres pakli', async () => {
    const { m } = menet([]);
    await m.betolt();
    const { container } = render(Pakli, { props: { menet: m } });
    expect(container.textContent).toContain('Ma nincs esedékes kártya');
  });
});
