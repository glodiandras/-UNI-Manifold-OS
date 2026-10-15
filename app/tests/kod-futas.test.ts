// A ⌘R futás-állapota (C36a-UI): a `cpp_futas` WS-események tiszta redukálója, a késői csatlakozás és az indítás
// hibaágai ál-core-ral. A motor eseménysorát a `modulok/cpp/ellenorzes.py` adja (indul → fordit_kesz → teszt… → kesz).

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { alkalmaz, KodFutasok, osszesit, type Futas } from '../src/kod/futas.svelte';

const alap = { tipus: 'cpp_futas', futas: 'futas-aaaaaaaaaaaa', ut: 'Info/Összeg.cpp', jegyzet: 'Info/Összeg.md', mod: 'gyors' };
const ev = (szakasz: string, adat: Record<string, unknown> = {}) => ({ ...alap, szakasz, ...adat });
const fordit = (ok: boolean) => ({ ok, allapot: ok ? 'ok' : 'hiba', ms: 412, diagnosztika: [], hiba_db: ok ? 0 : 1, figyelmeztetes_db: 0 });
const teszt = (sorszam: number, allapot = 'atment') => ({ sorszam, cim: null, allapot, ido_ms: 3, csucs_mb: 1.2, diff: null });

describe('alkalmaz (redukáló)', () => {
  it('a teljes eseménysor: indul → fordit_kesz → teszt ×2 → kesz', () => {
    let a: Futas | null = null;
    for (const e of [
      ev('indul', { tesztek_db: 2 }),
      ev('fordit_kesz', { fordit: fordit(true) }),
      ev('teszt', { teszt: teszt(1), kesz_db: 1, ossz: 2 }),
      ev('teszt', { teszt: teszt(2, 'hibas_kimenet'), kesz_db: 2, ossz: 2 }),
      ev('kesz', { atment: false, tesztek_db: 2, atment_db: 1, fordit_ok: true, ms: 900, hash: 'x', uzenet: '' }),
    ])
      a = alkalmaz(a, e);
    expect(a!.allapot).toBe('kesz');
    expect(a!.fordit!.ok).toBe(true);
    expect(a!.tesztek.map((t) => t.allapot)).toEqual(['atment', 'hibas_kimenet']);
    expect(a!.kesz).toMatchObject({ atment_db: 1, tesztek_db: 2, ms: 900 });
    expect(a!.kesz).not.toHaveProperty('tipus');
    expect(osszesit(a!)).toEqual({ fordit_ok: true, atment_db: 1, tesztek_db: 2, allapot: 'kesz' });
  });

  it('késői csatlakozás: az első látott esemény (nem `indul`) is új futást kezd', () => {
    const a = alkalmaz(null, ev('teszt', { teszt: teszt(3), ossz: 4 }));
    expect(a).toMatchObject({ futas: alap.futas, ut: alap.ut, allapot: 'fut', tesztek_db: 4 });
    expect(a!.tesztek).toHaveLength(1);
  });

  it('a hiba és a megszakítás lezár', () => {
    expect(alkalmaz(null, ev('hiba', { kod: 'nincs_eszkoztar', uzenet: 'nincs C++ eszköztár' }))).toMatchObject({
      allapot: 'hiba',
      hiba: { kod: 'nincs_eszkoztar', uzenet: 'nincs C++ eszköztár' },
    });
    expect(alkalmaz(alkalmaz(null, ev('indul')), ev('megszakitva'))!.allapot).toBe('megszakitva');
  });

  it('ugyanaz a teszt kétszer: csere, sorszám szerint rendezve', () => {
    let a = alkalmaz(null, ev('teszt', { teszt: teszt(2) }));
    a = alkalmaz(a, ev('teszt', { teszt: teszt(1) }));
    a = alkalmaz(a, ev('teszt', { teszt: teszt(2, 'idotullepes') }));
    expect(a!.tesztek.map((t) => [t.sorszam, t.allapot])).toEqual([
      [1, 'atment'],
      [2, 'idotullepes'],
    ]);
  });

  it('a lezárt, régebbi futás késve érkező eseménye nem írja felül az újat; a hiányos esemény nem hat', () => {
    const uj = alkalmaz(null, { ...ev('indul'), futas: 'futas-bbbbbbbbbbbb' });
    expect(alkalmaz(uj, ev('kesz', { atment: true }), new Set([alap.futas]))).toBe(uj);
    expect(alkalmaz(uj, { tipus: 'cpp_futas', szakasz: 'indul' })).toBe(uj);
    expect(alkalmaz(uj, { ...ev('ismeretlen'), futas: 'futas-cccccccccccc' })).toBe(uj);
  });
});

const valasz = (kod: number, adat: unknown) => new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });

describe('KodFutasok', () => {
  let keresek: { url: string; torzs: unknown }[];
  let ellenorizValasz: () => Response;

  beforeEach(() => {
    keresek = [];
    ellenorizValasz = () => valasz(202, { futas: alap.futas, cpp: alap.ut, jegyzet: alap.jegyzet, mod: 'gyors', tesztek_db: 2 });
    vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
      const u = new URL(url, 'http://127.0.0.1/');
      keresek.push({ url: u.pathname + u.search, torzs: init?.body ? JSON.parse(String(init.body)) : undefined });
      if (u.pathname === '/api/cpp/ellenoriz') return ellenorizValasz();
      if (u.pathname === '/api/cpp/feladat')
        return valasz(200, { tesztek: [{ sorszam: 1, sor: 3, cim: 'Példa', bemenet: '3 4\n', kimenet: '7\n', idokorlat_s: null, hiba: null }] });
      if (u.pathname === '/api/cpp/megszakit') return valasz(200, { megszakitva: true, allapot: 'fut' });
      if (u.pathname.startsWith('/api/cpp/futas/')) return valasz(404, { hiba: 'nincs ilyen futás' });
      return valasz(404, { hiba: 'nincs' });
    });
  });

  afterEach(() => vi.unstubAllGlobals());

  it('indítás: 202 → futó állapot, a leírás betöltődik; a WS-események frissítik; a kész futás összesítője megmarad', async () => {
    const k = new KodFutasok();
    const kapcs = new CoreKapcsolat('ws://127.0.0.1:1/ws');
    const le = k.telepit(kapcs);
    const jelzesek: string[] = [];
    k.figyel((u) => jelzesek.push(u));
    const r = await k.indit(alap.ut, 'gyors');
    expect(r).toEqual({ ok: true, futas: alap.futas, cpp: alap.ut, jegyzet: alap.jegyzet });
    expect(keresek[0]).toEqual({ url: '/api/cpp/ellenoriz', torzs: { ut: alap.ut, mod: 'gyors' } });
    expect(k.fut).toBe(true);
    await vi.waitFor(() => expect(k.leirasok[alap.futas]?.[0].bemenet).toBe('3 4\n'));
    kapcs.szetoszt(ev('fordit_kesz', { fordit: fordit(true) }));
    kapcs.szetoszt(ev('kesz', { atment: true, tesztek_db: 2, atment_db: 2, fordit_ok: true, ms: 10 }));
    expect(k.fut).toBe(false);
    expect(k.utolso[alap.ut]).toEqual({ fordit_ok: true, atment_db: 2, tesztek_db: 2, allapot: 'kesz' });
    expect(jelzesek).toEqual([alap.ut]);
    le();
  });

  it('a hibaágak a kóddal és a többértelmű jegyzetek listájával jönnek vissza', async () => {
    const k = new KodFutasok();
    ellenorizValasz = () => valasz(409, { hiba: 'több feladat-jegyzet', kod: 'tobbertelmu', jegyzetek: ['A.md', 'B.md'] });
    expect(await k.indit('x.cpp', 'gyors')).toMatchObject({ ok: false, kod: 'tobbertelmu', jegyzetek: ['A.md', 'B.md'] });
    ellenorizValasz = () => valasz(503, { hiba: 'nincs C++ eszköztár (hiányzik: clang++)', kod: 'nincs_eszkoztar' });
    expect(await k.indit('x.cpp', 'hibakereso', 'A.md')).toMatchObject({ ok: false, kod: 'nincs_eszkoztar' });
    expect(keresek.at(-1)!.torzs).toEqual({ ut: 'x.cpp', mod: 'hibakereso', jegyzet: 'A.md' });
    expect(k.aktiv).toBeNull();
  });

  it('megszakítás: azonnali jelzés és POST; a core újraindulása után elveszett futás hibával zárul', async () => {
    const k = new KodFutasok();
    await k.indit(alap.ut, 'gyors');
    await k.megszakit();
    expect(k.aktiv!.megszakitasKerve).toBe(true);
    expect(keresek.some((x) => x.url === '/api/cpp/megszakit' && (x.torzs as { futas: string }).futas === alap.futas)).toBe(true);
    await k.frissit();
    expect(k.aktiv).toMatchObject({ allapot: 'hiba', hiba: { kod: 'elveszett' } });
  });
});
