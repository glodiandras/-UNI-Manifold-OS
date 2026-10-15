// A vezérlő „Modellek” szakasza (C19): feladatonként a router-tábla, a kalibrált jel és a router döntése a két keretre.

import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Modellek from '../src/hej/vezerlo/Modellek.svelte';
import type { ModellAttekintes } from '../src/lib/vezerlo/tipusok';

const json = (a: unknown, kod = 200) => new Response(JSON.stringify(a), { status: kod, headers: { 'Content-Type': 'application/json' } });

function adat(): ModellAttekintes {
  const sor = (modell: string, pontszam: number, keret: 'munka' | 'tavol', kalibralt: boolean, aktualis = true) => ({
    modell, pontszam, keret, kalibralt, aktualis, datum: '2026-10-07T20:00:00', aranyhalmaz_verzio: 'szoveg-v2', ervenyes: true,
    csucs_gb: keret === 'munka' ? 4.1 : 8.5, snapshot: 'abc', megjegyzes: 'mos eval, n=40',
  });
  return {
    keretek: { munka: 5, tavol: 9 },
    feladatok: [
      {
        feladat: 'szoveg', aktualis_verzio: 'szoveg-v2', router_feladat: true,
        sorok: [sor('gemma4_12b', 0.595, 'tavol', true), sor('qwen35_4b', 0.433, 'munka', true), sor('gemma4_e2b', 0.392, 'munka', false, false)],
        dontes: {
          munka: { modell: 'qwen35_4b', var_tavolra: false, indok: 'a jobb nem fér' },
          tavol: { modell: 'gemma4_12b', var_tavolra: false, indok: 'a legjobb kalibrált' },
        },
      },
      {
        feladat: 'osztalyozas', aktualis_verzio: null, router_feladat: true, sorok: [],
        dontes: {
          munka: { modell: null, var_tavolra: false, indok: 'nincs' },
          tavol: { modell: null, var_tavolra: false, indok: 'nincs' },
        },
      },
    ],
  };
}

let hivasok: string[];

beforeEach(() => {
  hivasok = [];
  vi.stubGlobal('fetch', async (url: string) => {
    const u = new URL(url, 'http://127.0.0.1/');
    hivasok.push(u.pathname);
    return u.pathname === '/api/vezerlo/modellek' ? json(adat()) : json({ hiba: 'nincs' }, 404);
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('Modellek szakasz', () => {
  it('feladatonként a döntés és a sorok, a kalibrált jellel és az elavult sor jelölésével', async () => {
    render(Modellek);
    expect(await screen.findByText('Szöveg: összefoglaló, kártya')).toBeTruthy();
    const dontes = document.querySelector('.dontes')!.textContent!.replace(/\s+/g, ' ');
    expect(dontes).toContain('munka: qwen35_4b');
    expect(dontes).toContain('távol: gemma4_12b');
    const sorok = [...document.querySelectorAll('tbody tr')].map((tr) => [...tr.querySelectorAll('td')].map((td) => td.textContent!.trim()).join(' ').trim());
    expect(sorok[0]).toMatch(/^✓ ?gemma4_12b 0\.595 távol · 8\.5 GB v2$/);
    expect(sorok[2]).toContain('(elavult)');
    expect(document.querySelectorAll('tr.regi').length).toBe(1);
    expect(screen.getByText('Nincs mért sor (nincs aranyhalmaza).')).toBeTruthy();
  });

  it('egyszer tölt, a Frissítés újrakérdez; modell-workert nem érint', async () => {
    render(Modellek);
    await screen.findByText('Frissítés');
    expect(hivasok).toEqual(['/api/vezerlo/modellek']);
    await fireEvent.click(screen.getByText('Frissítés'));
    await vi.waitFor(() => expect(hivasok.length).toBe(2));
  });
});
