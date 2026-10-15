// Az AI-panel (C36b) jsdom-ban: kalibrált modell nélkül a gombok tiltva és a sáv megmondja, miért (D9); a tipp-lépcső
// szintenként fed fel; a teljes megoldás csak a második (megerősítő) kattintásra kérhető; az „ellenőrizve” / „nem
// ellenőrzött” jel a motor eredményéből; a javaslat gombja csak az ellenőrzött teszt-blokknál jelenik meg.

import { cleanup, fireEvent, render } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { aiAlkalmaz, kodAI } from '../src/kod/ai.svelte';
import KodAI from '../src/kod/KodAI.svelte';

const UT = 'Info/Összeg.cpp';
const alap = { tipus: 'cpp_ai', ai: 'ai-aaaaaaaaaaaa', cpp: UT, jegyzet: 'Info/Összeg.md' };
const valasz = (kod: number, adat: unknown) => new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });

beforeEach(() => {
  vi.stubGlobal('fetch', async () => valasz(200, { uj: true }));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  kodAI.aktiv = null;
  kodAI.allapot = null;
});

function rajzol(onker = vi.fn()) {
  return { c: render(KodAI, { props: { ut: UT, onker, onugras: vi.fn() } }), onker };
}

const gomb = (c: { container: HTMLElement }, szoveg: string) =>
  [...c.container.querySelectorAll('button')].find((b) => b.textContent?.trim() === szoveg) as HTMLButtonElement | undefined;

describe('KodAI', () => {
  it('kalibrált modell nélkül tiltva, megnevezett okkal', () => {
    kodAI.allapot = { kalibralt: false, modell: null, indok: 'A C++ AI-hoz még nincs kalibrált modell.' };
    const { c } = rajzol();
    expect(gomb(c, 'Mi a hiba?')!.disabled).toBe(true);
    expect(c.container.textContent).toContain('nincs kalibrált modell');
  });

  it('a tipp-lépcső és a teljes megoldás megerősítése', async () => {
    kodAI.allapot = { kalibralt: true, modell: 'qwen35_4b', indok: '' };
    kodAI.aktiv = aiAlkalmaz(null, { ...alap, mod: 'tipp', szakasz: 'eredmeny', hely_sor: 7, ellenorzott: true,
      szintek: [1, 2, 3].map((s) => ({ szint: s, cim: ['Irány', 'Algoritmus', 'Hely'][s - 1], szoveg: `szint-${s}`, kiszurve: false, hianyzik: false })) });
    const { c, onker } = rajzol();
    expect(c.container.textContent).toContain('szint-1');
    expect(c.container.textContent).not.toContain('szint-2');
    await fireEvent.click(gomb(c, 'Következő tipp')!);
    await fireEvent.click(gomb(c, 'Következő tipp')!);
    expect(c.container.textContent).toContain('szint-3');
    expect(c.container.textContent).toContain('ellenőrizve');
    await fireEvent.click(gomb(c, 'Teljes megoldás…')!);
    expect(onker).not.toHaveBeenCalled();
    await fireEvent.click(gomb(c, 'Igen, mutasd')!);
    expect(onker).toHaveBeenCalledWith('megoldas', true);
  });

  it('a szélső teszt: csak az ellenőrzött esetnek van „Hozzáadás” gombja', () => {
    kodAI.allapot = { kalibralt: true, modell: 'qwen35_4b', indok: '' };
    kodAI.aktiv = aiAlkalmaz(null, { ...alap, mod: 'teszt', szakasz: 'eredmeny', ellenorzott: true,
      referencia: { ellenorzott: true, ossz: 2, atment_db: 2 },
      esetek: [
        { bemenet: '1\n5\n', vart: '5\n', kapott: '0\n', allapot: 'elteres', blokk: '```teszt X\n--- bemenet\n1\n5\n--- kimenet\n5\n```\n' },
        { bemenet: '0\n', vart: null, kapott: '0\n', allapot: 'nem_ellenorzott', blokk: null },
      ] });
    const { c } = rajzol();
    expect(c.container.textContent).toContain('a megoldásod eltér');
    expect(c.container.querySelectorAll('button')).toBeTruthy();
    expect([...c.container.querySelectorAll('button')].filter((b) => b.textContent?.includes('Hozzáadás')).length).toBe(1);
  });
});
