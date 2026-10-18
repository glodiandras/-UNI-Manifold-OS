// 13-palette-03: a gyorsváltó `Jegyzet#fejezet` / `Jegyzet^blokk` / `#fejezet` szintaxisa (kis/nagybetű- és ékezetfüggetlen, Tab-kiegészítés).
// Az Obsidian core váltójának heading/block keresése nem megerősített: a szintaxis kiegészítő, a sima fájlkeresés változatlan.
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({ kerdez: vi.fn() }));
vi.mock('../src/lib/core/api', async (importOriginal) => ({ ...(await importOriginal<typeof import('../src/lib/core/api')>()), kerdez: api.kerdez }));

import Valto from '../src/atfedes/Valto.svelte';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { nyelv } from '../src/lib/i18n';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';
import { linkek } from '../src/lib/vault/linkek.svelte';
import { blokkSzures, fejezetSzures, horgonyElemez, jegyzetKiegeszit, jegyzetKivalaszt } from '../src/lib/vault/valtoHorgony';
import { szerkesztok } from '../src/szerkeszto/szerkesztok.svelte';

const FAJLOK = [
  { ut: 'Projects/Árvíztűrő terv.md', tipus: 'md' as const, meret: 1, mtime: 3 },
  { ut: 'Plan.md', tipus: 'md' as const, meret: 1, mtime: 2 },
  { ut: 'Board.canvas', tipus: 'canvas' as const, meret: 1, mtime: 1 },
];
const JEGYZETEK: Record<string, unknown> = {
  'Plan.md': {
    fejezetek: [{ szint: 1, szoveg: 'Plan', sor: 1 }, { szint: 2, szoveg: 'Overview', sor: 3 }, { szint: 2, szoveg: 'Risks and costs', sor: 9 }],
    blokkok: [{ azon: 'goal-1', sor: 4, kezdo_sor: 4 }, { azon: 'budget', sor: 12, kezdo_sor: 11 }],
  },
  'Projects/Árvíztűrő terv.md': { fejezetek: [{ szint: 2, szoveg: 'Áttekintés', sor: 2 }], blokkok: [] },
};

function kornyezet() {
  const felulet = new Felulet({ csend: { be: false } });
  const fajlok = new VaultFajlok();
  fajlok.beallit(FAJLOK);
  return { felulet, fajlok, context: new Map([[KORNYEZET_KULCS, { felulet, fajlok, kapcsolat: new CoreKapcsolat('ws://x') }]]) };
}

beforeEach(() => {
  nyelv.beallit('hu');
  vi.spyOn(linkek, 'aliasokKap').mockResolvedValue({});
  api.kerdez.mockImplementation(async (ut: string) => {
    const m = /^\/api\/vault\/jegyzet\?ut=(.*)$/.exec(ut);
    if (m) return JEGYZETEK[decodeURIComponent(m[1])] ?? { fejezetek: [], blokkok: [] };
    if (ut.startsWith('/api/vault/fejezetek')) {
      return { fejezetek: [{ ut: 'Plan.md', szint: 2, szoveg: 'Overview', sor: 3 }, { ut: 'Projects/Árvíztűrő terv.md', szint: 2, szoveg: 'Áttekintés', sor: 2 }] };
    }
    throw new Error('váratlan hívás: ' + ut);
  });
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  api.kerdez.mockReset();
});

const opciok = () => screen.queryAllByRole('option').map((o) => o.textContent?.replace(/\s+/g, ' ').trim() ?? '');

describe('horgony-szintaxis (tiszta függvények)', () => {
  it('a lekérdezés elemzése: # fejezet, ^ blokk, #^ is blokk, vezető # vault-szintű', () => {
    expect(horgonyElemez('Plan#over')).toEqual({ jel: '#', jegyzet: 'Plan', szuro: 'over' });
    expect(horgonyElemez('Plan ^goal')).toEqual({ jel: '^', jegyzet: 'Plan', szuro: 'goal' });
    expect(horgonyElemez('Plan#^goal')).toEqual({ jel: '^', jegyzet: 'Plan', szuro: 'goal' });
    expect(horgonyElemez('#risk')).toEqual({ jel: '#', jegyzet: '', szuro: 'risk' });
    expect(horgonyElemez('Plan')).toBeNull();
    expect(horgonyElemez('')).toBeNull();
  });

  it('a jegyzetrész kis/nagybetűre és ékezetre érzéketlen; csak .md; pontos név előnyt élvez', () => {
    expect(jegyzetKivalaszt(FAJLOK, 'PLAN')?.ut).toBe('Plan.md');
    expect(jegyzetKivalaszt(FAJLOK, 'arvizturo')?.ut).toBe('Projects/Árvíztűrő terv.md');
    expect(jegyzetKivalaszt(FAJLOK, 'Board')).toBeNull();
    expect(jegyzetKivalaszt(FAJLOK, '')).toBeNull();
    expect(jegyzetKivalaszt([...FAJLOK, { ut: 'Plan B.md', tipus: 'md', meret: 1, mtime: 9 }], 'plan')?.ut).toBe('Plan.md');
  });

  it('fejezet- és blokkszűrés; a blokk a kezdősorra ugrik; Tab-kiegészítés a teljes névre', () => {
    const j = JEGYZETEK['Plan.md'] as { fejezetek: never[]; blokkok: never[] };
    expect(fejezetSzures('Plan.md', j.fejezetek, 'COSTS').map((t) => t.ertek.szoveg)).toEqual(['Risks and costs']);
    expect(fejezetSzures('Plan.md', j.fejezetek, '').length).toBe(3);
    expect(blokkSzures('Plan.md', j.blokkok, 'budg').map((t) => [t.ertek.szoveg, t.ertek.sor])).toEqual([['budget', 11]]);
    const l = horgonyElemez('pla#over')!;
    expect(jegyzetKiegeszit(l, FAJLOK[1])).toBe('Plan#over');
    expect(jegyzetKiegeszit(horgonyElemez('Plan#over')!, FAJLOK[1])).toBeNull();
  });
});

describe('gyorsváltó: Jegyzet#fejezet / Jegyzet^blokk', () => {
  it('Note#heading: a jegyzet fejezetei szűrve; kiválasztva megnyitja a jegyzetet és a fejezet sorára ugrik', async () => {
    const k = kornyezet();
    const ugras = vi.spyOn(szerkesztok, 'ugras').mockImplementation(() => {});
    render(Valto, { context: k.context });
    const input = screen.getByRole('combobox');
    await fireEvent.input(input, { target: { value: 'plan#COSTS' } });
    await vi.waitFor(() => expect(opciok()).toHaveLength(1));
    expect(opciok()[0]).toContain('Risks and costs');
    expect(opciok()[0]).toContain('Plan');
    await fireEvent.keyDown(input, { key: 'Enter' });
    expect(k.felulet.munkaterulet.aktivFul?.ut).toBe('Plan.md');
    expect(ugras).toHaveBeenCalledWith('Plan.md', 9);
    expect(k.felulet.atfedes).toBeNull();
  });

  it('Note^block: a blokkazonosítók; a kezdősorra ugrik; ékezetfüggetlen jegyzetnév', async () => {
    const k = kornyezet();
    const ugras = vi.spyOn(szerkesztok, 'ugras').mockImplementation(() => {});
    render(Valto, { context: k.context });
    const input = screen.getByRole('combobox');
    await fireEvent.input(input, { target: { value: 'PLAN^bud' } });
    await vi.waitFor(() => expect(opciok()).toHaveLength(1));
    expect(opciok()[0]).toContain('budget');
    await fireEvent.keyDown(input, { key: 'Enter' });
    expect(ugras).toHaveBeenCalledWith('Plan.md', 11);
    await fireEvent.input(input, { target: { value: 'arvizturo#attek' } });
    await vi.waitFor(() => expect(opciok().some((o) => o.includes('Áttekintés'))).toBe(true));
  });

  it('#szűrő: vault-szintű fejezetkeresés a core-ral; a találat jegyzet nevét mutatja', async () => {
    const k = kornyezet();
    vi.spyOn(szerkesztok, 'ugras').mockImplementation(() => {});
    render(Valto, { context: k.context });
    await fireEvent.input(screen.getByRole('combobox'), { target: { value: '#over' } });
    await vi.waitFor(() => expect(opciok()).toHaveLength(2));
    expect(api.kerdez.mock.calls.some(([u]) => String(u).startsWith('/api/vault/fejezetek?q=over'))).toBe(true);
    await fireEvent.keyDown(screen.getByRole('combobox'), { key: 'ArrowDown' });
    await fireEvent.keyDown(screen.getByRole('combobox'), { key: 'Enter', metaKey: true });
    expect(k.felulet.munkaterulet.aktivFul?.ut).toBe('Projects/Árvíztűrő terv.md');
  });

  it('Tab kiegészíti a jegyzetnevet, majd az aktív fejezet szövegét; a fókusz a mezőben marad', async () => {
    const k = kornyezet();
    render(Valto, { context: k.context });
    const input = screen.getByRole<HTMLInputElement>('combobox');
    await fireEvent.input(input, { target: { value: 'pla#over' } });
    await vi.waitFor(() => expect(opciok()).toHaveLength(1));
    await fireEvent.keyDown(input, { key: 'Tab' });
    expect(input.value).toBe('Plan#over');
    await fireEvent.keyDown(input, { key: 'Tab' });
    await vi.waitFor(() => expect(input.value).toBe('Plan#Overview'));
  });

  it('ismeretlen jegyzet vagy nincs találat: magyarázat, Enter nem hoz létre jegyzetet; a # nem lesz jegyzetnév', async () => {
    const k = kornyezet();
    render(Valto, { context: k.context });
    const input = screen.getByRole('combobox');
    await fireEvent.input(input, { target: { value: 'nincs-ilyen#x' } });
    expect(screen.getByRole('status').textContent).toContain('Nincs ilyen jegyzet');
    await fireEvent.keyDown(input, { key: 'Enter' });
    await fireEvent.keyDown(input, { key: 'Enter', shiftKey: true });
    expect(k.felulet.faUjNev).toBeNull();
    expect(k.felulet.faUjJegyzet).toBe(false);
    expect(screen.queryByRole('alert')).toBeNull();
    await fireEvent.input(input, { target: { value: 'Plan#zzzz' } });
    await vi.waitFor(() => expect(screen.getByRole('status').textContent).toContain('Nincs találat'));
  });

  it('a core hibája jelezve van (nem üres, hanem magyarázó állapot); a sima fájlkeresés változatlan', async () => {
    const k = kornyezet();
    api.kerdez.mockRejectedValue(new Error('offline'));
    render(Valto, { context: k.context });
    const input = screen.getByRole('combobox');
    await fireEvent.input(input, { target: { value: 'Plan#x' } });
    await vi.waitFor(() => expect(screen.getByRole('status').textContent).toContain('nem érhetők el'));
    await fireEvent.input(input, { target: { value: 'Plan' } });
    expect(opciok().some((o) => o.includes('Plan'))).toBe(true);
    expect(opciok().every((o) => !o.includes('#'))).toBe(true);
  });
});
