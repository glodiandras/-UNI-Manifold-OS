// A C++ AI-réteg a felületen (C36b): a `cpp_ai` események redukálója, az indítás és a hibaágai ál-core-ral, a tipp-lépcső
// felfedése (a tracker-jelzés a core-é), a parancsok elérhetősége (kalibrált modell nélkül tiltva, D9), és a javaslat
// beszúrásának helye a feladat-jegyzetben (a beszúrás maga a felhasználó szerkesztő-tranzakciója).

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { kodTelepit } from '../src/kod';
import { aiAlkalmaz, kodAI, KodAI, type AIFutas } from '../src/kod/ai.svelte';
import { beszurando, tesztHely } from '../src/kod/aiElfogad';
import { kodFulok, type KodPeldany } from '../src/kod/aktiv.svelte';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { Regiszter } from '../src/lib/parancsok/regiszter';

const valasz = (kod: number, adat: unknown) => new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });
const alap = { tipus: 'cpp_ai', ai: 'ai-aaaaaaaaaaaa', mod: 'tipp', cpp: 'Info/Összeg.cpp', jegyzet: 'Info/Összeg.md' };
const ev = (szakasz: string, adat: Record<string, unknown> = {}) => ({ ...alap, szakasz, ...adat });
let keresek: { ut: string; torzs: Record<string, unknown> | undefined }[];
let inditValasz: () => Response;

beforeEach(() => {
  keresek = [];
  inditValasz = () => valasz(202, { ai: 'ai-bbbbbbbbbbbb', mod: 'hiba', cpp: 'Info/Összeg.cpp', jegyzet: 'Info/Összeg.md' });
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    const u = new URL(url, 'http://127.0.0.1/');
    keresek.push({ ut: u.pathname, torzs: init?.body ? JSON.parse(String(init.body)) : undefined });
    if (u.pathname === '/api/cpp/ai') return inditValasz();
    if (u.pathname === '/api/cpp/ai/tipp') return valasz(200, { uj: true });
    if (u.pathname === '/api/cpp/ai/allapot') return valasz(200, { kalibralt: true, modell: 'qwen35_4b', indok: '' });
    return valasz(404, { hiba: 'nincs' });
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  kodFulok.aktiv = null;
  kodAI.aktiv = null;
  kodAI.allapot = null;
});

describe('aiAlkalmaz (redukáló)', () => {
  it('a teljes eseménysor és a tipp első szintje', () => {
    let a: AIFutas | null = null;
    for (const e of [
      ev('indul'),
      ev('ellenorzes', { fordit_ok: true, atment_db: 1, ossz: 2, bizonyitek: { fajta: 'teszt' } }),
      ev('generalas', { tokenek: 40 }),
      ev('modell', { modell: 'qwen35_4b' }),
      ev('eredmeny', { szintek: [{ szint: 1, cim: 'Irány', szoveg: 'x' }], hely_sor: 5, ellenorzott: false }),
      ev('kesz', { ok: true }),
    ])
      a = aiAlkalmaz(a, e);
    expect(a).toMatchObject({ allapot: 'kesz', tokenek: 40, modell: 'qwen35_4b', felfedve: 1 });
    expect(a!.ellenorzes).toMatchObject({ atment_db: 1, ossz: 2 });
    expect(a!.eredmeny).toMatchObject({ hely_sor: 5 });
    expect(a!.eredmeny).not.toHaveProperty('tipus');
  });

  it('a hiba és a megszakítás lezár; más esemény nem módosít', () => {
    expect(aiAlkalmaz(null, ev('hiba', { kod: 'nincs_kalibralt', uzenet: 'nincs' }))).toMatchObject({
      allapot: 'hiba',
      hiba: { kod: 'nincs_kalibralt' },
    });
    const a = aiAlkalmaz(null, ev('indul'));
    expect(aiAlkalmaz(a, ev('megszakitva'))!.allapot).toBe('megszakitva');
    expect(aiAlkalmaz(a, { tipus: 'cpp_futas', szakasz: 'kesz' })).toBe(a);
  });
});

describe('KodAI', () => {
  it('az indítás a kért móddal és a megerősítéssel; a hibakód a válaszból', async () => {
    const k = new KodAI();
    expect(await k.indit('megoldas', 'Info/Összeg.cpp', null, true)).toEqual({ ok: true, ai: 'ai-bbbbbbbbbbbb' });
    expect(keresek[0].torzs).toEqual({ mod: 'megoldas', ut: 'Info/Összeg.cpp', megerosit: true });
    expect(k.fut).toBe(true);
    inditValasz = () => valasz(503, { hiba: 'nincs kalibrált modell', kod: 'nincs_kalibralt' });
    expect(await k.indit('hiba', 'Info/Összeg.cpp', null)).toMatchObject({ ok: false, kod: 'nincs_kalibralt' });
  });

  it('a tipp-lépcső szintenként fed fel, legfeljebb a harmadikig', async () => {
    const k = new KodAI();
    k.aktiv = aiAlkalmaz(null, ev('eredmeny', { szintek: [] }));
    await k.felfed();
    await k.felfed();
    await k.felfed();
    expect(k.aktiv!.felfedve).toBe(3);
    expect(keresek.map((x) => x.torzs?.szint)).toEqual([2, 3]);
  });

  it('a kalibráltság a core-ból', async () => {
    const k = new KodAI();
    await k.frissit();
    expect(k.kalibralt).toBe(true);
  });
});

describe('a parancsok', () => {
  it('kalibrált modell nélkül nem érhetők el; kalibrálttal az aktív .cpp fülön igen', () => {
    const reg = new Regiszter();
    const le = kodTelepit(reg, new Felulet({}), new CoreKapcsolat('ws://127.0.0.1:1/ws'));
    const p: KodPeldany = { ut: 'Info/Összeg.cpp', nezet: () => null, mentes: async () => true, irhato: () => true, ugras: () => {} };
    kodFulok.aktiv = p;
    for (const m of ['hiba', 'tipp', 'teszt', 'stressz']) expect(reg.elerheto(reg.kap(`kod.ai-${m}`)!)).toBe(false);
    kodAI.allapot = { kalibralt: true, modell: 'qwen35_4b', indok: '' };
    for (const m of ['hiba', 'tipp', 'teszt', 'stressz']) expect(reg.elerheto(reg.kap(`kod.ai-${m}`)!)).toBe(true);
    expect(reg.kap('kod.ai-megoldas')).toBeFalsy(); // a teljes megoldás csak a tipp-lépcsőből, megerősítéssel
    expect(reg.elerheto(reg.kap('kod.ai-megszakit')!)).toBe(false);
    le();
  });
});

describe('a teszt-blokk beszúrásának helye', () => {
  const jegyzet = '# Ö\n\n```teszt A\n--- bemenet\n1\n--- kimenet\n1\n```\n\nszöveg\n\n![[Ö.cpp]]\n';
  it('az utolsó teszt-blokk után, különben a beágyazás elé, különben a végére', () => {
    expect(jegyzet.slice(0, tesztHely(jegyzet)).endsWith('```\n')).toBe(true);
    const nincsTeszt = '# Ö\n\nszöveg\n\n![[Ö.cpp]]\n';
    expect(nincsTeszt.slice(tesztHely(nincsTeszt))).toBe('![[Ö.cpp]]\n');
    expect(tesztHely('# Ö')).toBe(3);
  });
  it('üres sor a blokk előtt és után', () => {
    const blokk = '```teszt X\n--- bemenet\n2\n--- kimenet\n2\n```\n';
    const h = tesztHely(jegyzet);
    const uj = jegyzet.slice(0, h) + beszurando(jegyzet, h, blokk) + jegyzet.slice(h);
    expect(uj).toContain('```\n\n```teszt X\n');
    expect(uj).toContain('```\n\nszöveg');
    expect(beszurando('a', 1, blokk).startsWith('\n\n```teszt')).toBe(true);
  });
});
