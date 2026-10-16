// Az AI-réteg több nyelvre (F10): a `kod_ai` események redukálója (D9: a `proba` = trial jelzés a modell/eredmény/kész eseményekből),
// az indítás a `.cpp`-nél a régi, minden másnál az általános motoron nyelv-paraméterrel, a rövid hibakódok, a tipp-lépcső
// tracker-jelzése csak a C36b szolgáltatásnál, a gombok és parancsok elérhetősége, és a „Próba” (Trial) jelölés a panelen.

import { cleanup, fireEvent, render } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, onTestFinished, vi } from 'vitest';
import { kodTelepit } from '../src/kod';
import { aiAlkalmaz, kodAI, KodAI, type AIFutas } from '../src/kod/ai.svelte';
import { kodFulok, type KodPeldany } from '../src/kod/aktiv.svelte';
import KodAIPanel from '../src/kod/KodAI.svelte';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { nyelv as nyelvAllapot } from '../src/lib/i18n';
import { Regiszter } from '../src/lib/parancsok/regiszter';

const valasz = (kod: number, adat: unknown) => new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });
const AI = 'kodai-0123456789ab';
const alap = { tipus: 'kod_ai', ai: AI, mod: 'hiba', nyelv: 'python', forras: 'Info/Fib.py', jegyzet: 'Info/Fib.md' };
const ev = (szakasz: string, adat: Record<string, unknown> = {}) => ({ ...alap, szakasz, ...adat });
let keresek: { ut: string; torzs: Record<string, unknown> | undefined }[];
let inditValasz: () => Response;
let aiValasz: () => Response;

beforeEach(() => {
  keresek = [];
  inditValasz = () => valasz(202, { ai: AI, mod: 'hiba', nyelv: 'python', forras: 'Info/Fib.py', jegyzet: 'Info/Fib.md' });
  aiValasz = () => valasz(404, { hiba: 'No such run', kod: 'kod.nincs_ilyen_futas' });
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    const u = new URL(url, 'http://127.0.0.1/');
    keresek.push({ ut: u.pathname, torzs: init?.body ? JSON.parse(String(init.body)) : undefined });
    if (u.pathname === '/api/kod/ai') return inditValasz();
    if (u.pathname === '/api/kod/ai/megszakit') return valasz(200, { megszakitva: true, allapot: 'fut' });
    if (u.pathname.startsWith('/api/kod/ai/')) return aiValasz();
    if (u.pathname === '/api/cpp/ai/allapot') return valasz(200, { kalibralt: false, modell: null, indok: 'nincs' });
    if (u.pathname === '/api/cpp/ai/tipp') return valasz(200, { uj: true });
    return valasz(404, { hiba: 'nincs' });
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  kodFulok.aktiv = null;
  kodAI.aktiv = null;
  kodAI.allapot = null;
});

describe('aiAlkalmaz: kod_ai', () => {
  it('az eseménysor: a forrás a `forras` mezőből, a nyelv, a motor kod; a trial (proba) a modell-eseménytől látszik', () => {
    let a: AIFutas | null = null;
    for (const e of [
      ev('indul'),
      ev('ellenorzes', { fordit_ok: true, atment_db: 1, ossz: 2, bizonyitek: { fajta: 'teszt' } }),
      ev('modell', { modell: 'qwen35_4b', proba: true, kalibracios_kulcs: 'kod_python', indok: 'no calibrated model for kod_python: the calibrated C++ model as a trial' }),
      ev('generalas', { tokenek: 30 }),
      ev('eredmeny', { proba: true, sor: 4, fajta: 'logika', magyarazat: 'Rossz feltétel', ellenorzott: false }),
      ev('kesz', { ok: true, mod: 'hiba', modell: 'qwen35_4b', proba: true, ms: 800 }),
    ])
      a = aiAlkalmaz(a, e);
    expect(a).toMatchObject({ ai: AI, cpp: 'Info/Fib.py', nyelv: 'python', motor: 'kod', allapot: 'kesz', tokenek: 30, modell: 'qwen35_4b', proba: true });
    expect(a!.indok).toContain('trial');
    expect(a!.eredmeny).toMatchObject({ sor: 4, proba: true });
    for (const kulcs of ['tipus', 'szakasz', 'forras', 'nyelv', 'ai', 'jegyzet']) expect(a!.eredmeny).not.toHaveProperty(kulcs);
  });

  it('kalibrált modell: nincs trial jelölés; a proba csak az eredmény/kész eseményből is bekapcsolja', () => {
    let a = aiAlkalmaz(null, ev('modell', { modell: 'm', proba: false, kalibracios_kulcs: 'kod_python', indok: 'calibrated' }));
    expect(a!.proba).toBe(false);
    a = aiAlkalmaz(a, ev('eredmeny', { proba: false, sor: 1 }));
    expect(a!.proba).toBe(false);
    // a modell-esemény elveszett (késői csatlakozás): az eredmény proba jelzése is elég
    const kesobbi = aiAlkalmaz(null, ev('eredmeny', { proba: true, sor: 1 }));
    expect(kesobbi!.proba).toBe(true);
  });

  it('a hiba kódja rövid alakban (kod.nincs_kalibralt → nincs_kalibralt), a szöveg a core angol mondata; a C36b esemény változatlanul él', () => {
    expect(aiAlkalmaz(null, ev('hiba', { kod: 'kod.nincs_kalibralt', param: { nyelv: 'Python', kulcs: 'kod_python' }, uzenet: 'There is no calibrated model for Python (kod_python) and no trial model.' }))).toMatchObject({
      allapot: 'hiba',
      hiba: { kod: 'nincs_kalibralt', uzenet: 'There is no calibrated model for Python (kod_python) and no trial model.' },
    });
    const regi = aiAlkalmaz(null, { tipus: 'cpp_ai', ai: 'ai-aaaaaaaaaaaa', mod: 'tipp', cpp: 'Info/Összeg.cpp', jegyzet: null, szakasz: 'indul' });
    expect(regi).toMatchObject({ cpp: 'Info/Összeg.cpp', nyelv: 'cpp', motor: 'cpp', proba: false });
    expect(aiAlkalmaz(regi, { tipus: 'kod_futas', szakasz: 'kesz' })).toBe(regi);
  });
});

describe('KodAI: az általános motor', () => {
  it('a .py indítása az /api/kod/ai-ra megy a nyelvvel és a megerősítéssel; a válasz forrása az útvonal', async () => {
    const k = new KodAI();
    expect(await k.indit('megoldas', 'Info/Fib.py', 'Info/Fib.md', true, undefined, 'python')).toEqual({ ok: true, ai: AI });
    expect(keresek[0]).toEqual({ ut: '/api/kod/ai', torzs: { mod: 'megoldas', ut: 'Info/Fib.py', jegyzet: 'Info/Fib.md', nyelv: 'python', megerosit: true } });
    expect(k.aktiv).toMatchObject({ ai: AI, cpp: 'Info/Fib.py', nyelv: 'python', motor: 'kod', allapot: 'fut', proba: false });
  });

  it('a .cpp a C36b szolgáltatáson marad (nyelv-mező nélkül); a hibakód rövid, a motor a hibában is megvan', async () => {
    const k = new KodAI();
    inditValasz = () => valasz(503, { hiba: 'nincs kalibrált modell', kod: 'nincs_kalibralt' });
    // a régi szolgáltatás útvonala: a teszt csak a kérés alakját nézi
    vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
      const u = new URL(url, 'http://127.0.0.1/');
      keresek.push({ ut: u.pathname, torzs: init?.body ? JSON.parse(String(init.body)) : undefined });
      return u.pathname === '/api/cpp/ai' ? inditValasz() : valasz(404, { hiba: 'nincs' });
    });
    expect(await k.indit('hiba', 'Info/Összeg.cpp', null)).toMatchObject({ ok: false, kod: 'nincs_kalibralt', motor: 'cpp' });
    expect(keresek.at(-1)).toEqual({ ut: '/api/cpp/ai', torzs: { mod: 'hiba', ut: 'Info/Összeg.cpp' } });
  });

  it('az általános motor hibakódjai rövid alakban jönnek: nincs kalibrált modell és nincs trial, hiányzó eszközlánc, foglalt', async () => {
    const k = new KodAI();
    for (const [kod, rovid] of [['kod.nincs_kalibralt', 'nincs_kalibralt'], ['kod.nincs_eszkozlanc', 'nincs_eszkozlanc'], ['kod.foglalt', 'foglalt'], ['kod.mentetlen', 'mentetlen']] as const) {
      inditValasz = () => valasz(409, { hiba: `msg ${kod}`, kod });
      expect(await k.indit('hiba', 'Info/Fib.py', null)).toMatchObject({ ok: false, kod: rovid, uzenet: `msg ${kod}`, motor: 'kod' });
    }
    expect(k.aktiv).toBeNull();
  });

  it('megszakítás az általános útvonalon; a késői csatlakozás összesítője (modell objektum, hiba objektum) beolvad', async () => {
    const k = new KodAI();
    await k.indit('hiba', 'Info/Fib.py', null);
    await k.megszakit();
    expect(keresek.some((x) => x.ut === '/api/kod/ai/megszakit' && x.torzs?.ai === AI)).toBe(true);
    aiValasz = () =>
      valasz(200, { ai: AI, nyelv: 'python', forras: 'Info/Fib.py', allapot: 'hiba', modell: { modell: 'qwen35_4b', proba: true, kalibracios_kulcs: 'kod_python', indok: 'trial' },
                    eredmeny: null, hiba: { kod: 'kod.csak_tavol', param: {}, uzenet: 'The calibrated code model only fits the away budget.' } });
    await k.frissit();
    expect(keresek.some((x) => x.ut === `/api/kod/ai/${AI}`)).toBe(true);
    expect(k.aktiv).toMatchObject({ allapot: 'hiba', modell: 'qwen35_4b', proba: true, indok: 'trial', hiba: { kod: 'csak_tavol', uzenet: 'The calibrated code model only fits the away budget.' } });
  });

  it('a tipp-lépcső tracker-jelzése csak a C36b szolgáltatásé: az általános motoron a szintek felfedése kérés nélkül megy', async () => {
    const k = new KodAI();
    k.aktiv = aiAlkalmaz(null, ev('eredmeny', { mod: 'tipp', szintek: [] }));
    await k.elsoSzint();
    await k.felfed();
    await k.felfed();
    expect(k.aktiv!.felfedve).toBe(3);
    expect(keresek.filter((x) => x.ut === '/api/cpp/ai/tipp')).toHaveLength(0);
  });

  it('indíthatóság: a .cpp kalibrált modell nélkül tiltva (D9), az általános motor nyelvei a router döntése szerint (trial jelölve)', () => {
    const k = new KodAI();
    expect(k.indithato('cpp')).toBe(false);
    expect(k.indithato('kod')).toBe(true);
    k.allapot = { kalibralt: true, modell: 'm', indok: '' };
    expect(k.indithato('cpp')).toBe(true);
    k.aktiv = aiAlkalmaz(null, ev('indul'));
    expect(k.indithato('kod')).toBe(false); // egyszerre egy kérés
    expect(k.indithato('cpp')).toBe(false);
  });
});

describe('a parancsok több nyelven', () => {
  function peldany(ut: string): KodPeldany {
    return { ut, nezet: () => null, mentes: async () => true, irhato: () => true, ugras: () => {} };
  }

  it('.py fülön az AI-parancsok kalibrált modell nélkül is elérhetők (trial), a .cpp fülön nem; a hibakereső mód és a formázás csak a megfelelő nyelven', () => {
    const reg = new Regiszter();
    const le = kodTelepit(reg, new Felulet({}), new CoreKapcsolat('ws://127.0.0.1:1/ws'));
    const ai = ['hiba', 'tipp', 'teszt', 'stressz'].map((m) => reg.kap(`kod.ai-${m}`)!);
    kodFulok.aktiv = peldany('Info/Fib.py');
    for (const p of ai) expect(reg.elerheto(p), p.id).toBe(true);
    expect(reg.elerheto(reg.kap('kod.ellenorzes')!)).toBe(true);
    expect(reg.elerheto(reg.kap('kod.ellenorzes-hibakereso')!)).toBe(false); // csak C és C++
    expect(reg.elerheto(reg.kap('kod.formaz')!)).toBe(false); // clang-format: C++
    expect(reg.elerheto(reg.kap('kod.eszkozlancok')!)).toBe(true);
    kodFulok.aktiv = peldany('Info/Összeg.cpp');
    for (const p of ai) expect(reg.elerheto(p), p.id).toBe(false); // kalibrált modell nélkül
    expect(reg.elerheto(reg.kap('kod.ellenorzes-hibakereso')!)).toBe(true);
    expect(reg.elerheto(reg.kap('kod.formaz')!)).toBe(true);
    kodFulok.aktiv = peldany('Info/prog.c');
    expect(reg.elerheto(reg.kap('kod.ellenorzes-hibakereso')!)).toBe(true); // C: sanitizer
    expect(reg.elerheto(reg.kap('kod.formaz')!)).toBe(false);
    le();
  });
});

describe('a Próba (Trial) jelölés az AI-panelen', () => {
  const rajzol = (ut = 'Info/Fib.py', nyelv: string | null = 'python') => render(KodAIPanel, { props: { ut, nyelv, onker: vi.fn(), onugras: vi.fn() } });

  it('minden proba:true eredményen látszik (ikon + szó + magyarázat), a futó kérésen is, a kalibrálton nem', () => {
    nyelvAllapot.beallit('en'); // a közös ProbaJel szava a szótárból jön
    onTestFinished(() => { nyelvAllapot.beallit('hu'); });
    kodAI.aktiv = aiAlkalmaz(null, ev('modell', { modell: 'qwen35_4b', proba: true, indok: 'trial: a kalibrált C++ modell' }));
    let c = rajzol();
    expect(c.container.querySelector('[data-jel="proba"]')!.textContent).toContain('Trial'); // a közös ProbaJel (F9)
    expect(c.container.querySelector('[data-jel="proba"] svg')).not.toBeNull(); // nem csak szín
    cleanup();

    kodAI.aktiv = [
      ev('modell', { modell: 'qwen35_4b', proba: true, indok: 'trial: a kalibrált C++ modell' }),
      ev('eredmeny', { proba: true, sor: 4, fajta: 'logika', fajta_szoveg: 'logic error', magyarazat: 'Rossz feltétel.', ellenorzott: true }),
      ev('kesz', { ok: true, proba: true }),
    ].reduce<AIFutas | null>((a, e) => aiAlkalmaz(a, e), null);
    c = rajzol();
    expect(c.container.querySelector('.eredmeny [data-jel="proba"]')!.textContent).toContain('Trial');
    expect(c.container.querySelector('.eredmeny [data-jel="proba"]')!.getAttribute('title')).toContain('trial: a kalibrált C++ modell');
    expect(c.container.textContent).toContain('Rossz feltétel.');
    expect(c.container.textContent).toContain('not calibrated');
    cleanup();

    kodAI.aktiv = [ev('modell', { modell: 'm', proba: false, indok: 'calibrated' }), ev('eredmeny', { proba: false, sor: 4, magyarazat: 'x', ellenorzott: true }), ev('kesz', { ok: true, proba: false })]
      .reduce<AIFutas | null>((a, e) => aiAlkalmaz(a, e), null);
    c = rajzol();
    expect(c.container.querySelector('[data-jel="proba"]')).toBeNull();
    expect(c.container.textContent).toContain('x');
  });

  it('.py fülön a gombok kalibrált modell nélkül is élnek és nincs „nincs kalibrált modell” felirat; a .cpp fülön tiltva', async () => {
    const onker = vi.fn();
    let c = render(KodAIPanel, { props: { ut: 'Info/Fib.py', nyelv: 'python', onker, onugras: vi.fn() } });
    const gomb = (szoveg: string) => [...c.container.querySelectorAll('button')].find((b) => b.textContent?.trim() === szoveg) as HTMLButtonElement;
    expect(gomb('Mi a hiba?').disabled).toBe(false);
    expect(c.container.textContent).not.toContain('nincs kalibrált modell');
    await fireEvent.click(gomb('Mi a hiba?'));
    expect(onker).toHaveBeenCalledWith('hiba');
    cleanup();
    kodAI.allapot = { kalibralt: false, modell: null, indok: 'nincs' };
    c = render(KodAIPanel, { props: { ut: 'Info/Összeg.cpp', nyelv: 'cpp', onker, onugras: vi.fn() } });
    expect(gomb('Mi a hiba?').disabled).toBe(true);
    expect(c.container.textContent).toContain('nincs kalibrált modell');
  });

  it('a hiányzó kalibrált és trial modell a core érthető mondatával jelenik meg a panelen (hibaállapot)', () => {
    kodAI.aktiv = aiAlkalmaz(null, ev('hiba', { kod: 'kod.nincs_kalibralt', param: {}, uzenet: 'There is no calibrated model for Python (kod_python) and no trial model. Settings › AI › Calibration.' }));
    const c = rajzol();
    expect(c.container.querySelector('[role="alert"]')!.textContent).toContain('no trial model');
    expect(c.container.querySelector('[data-jel="proba"]')).toBeNull(); // hiba: nincs eredmény, amit jelölni kellene
  });
});
