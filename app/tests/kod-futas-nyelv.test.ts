// A ⌘R futás-állapota több nyelvre (F10): a `kod_futas` WS-események ugyanazt a redukálót használják, mint a C36a `cpp_futas`;
// a `.cpp` a régi `/api/cpp/*`-on marad (a tracker-jelzés miatt), minden más nyelv az `/api/kod/*`-on fut; az indítás hibaágai
// (`kod.nincs_eszkozlanc`, `kod.tobbertelmu`, `kod.mentetlen`), a megszakítás és a késői csatlakozás motoronként.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { alkalmaz, KodFutasok, osszesit, type Futas } from '../src/kod/futas.svelte';

const FUTAS = 'kod-0123456789ab';
const alap = { tipus: 'kod_futas', futas: FUTAS, nyelv: 'python', forras: 'Info/Fib.py', jegyzet: 'Info/Fib.md', mod: 'gyors' };
const ev = (szakasz: string, adat: Record<string, unknown> = {}) => ({ ...alap, szakasz, ...adat });
const fordit = (ok: boolean, diagnosztika: unknown[] = []) => ({ ok, allapot: ok ? 'ok' : 'hiba', ms: 40, diagnosztika, hiba_db: ok ? 0 : 1, figyelmeztetes_db: 0 });
const teszt = (sorszam: number, allapot = 'atment', extra: Record<string, unknown> = {}) => ({ sorszam, cim: null, allapot, ido_ms: 8, csucs_mb: 9, diff: null, ...extra });
const valasz = (kod: number, adat: unknown) => new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });

describe('alkalmaz: kod_futas', () => {
  it('a teljes eseménysor; a forrás a `forras` mezőből, a nyelv az eseményből, a motor kod', () => {
    let a: Futas | null = null;
    for (const e of [
      ev('indul', { tesztek_db: 2 }),
      ev('fordit_kesz', { fordit: fordit(true) }),
      ev('teszt', { teszt: teszt(1), kesz_db: 1, ossz: 2 }),
      ev('teszt', { teszt: teszt(2, 'futasi_hiba', { jelentes: { forras: 'python', fajta: 'ZeroDivisionError', leiras: 'division by zero', fajl: 'megoldas.py', sor: 4, oszlop: null, fuggveny: 'fib', sajat: true, keretek: [] } }), kesz_db: 2, ossz: 2 }),
      ev('kesz', { atment: false, tesztek_db: 2, atment_db: 1, fordit_ok: true, ms: 120, hash: 'x', uzenet: '', kod: null }),
    ])
      a = alkalmaz(a, e);
    expect(a).toMatchObject({ futas: FUTAS, ut: 'Info/Fib.py', nyelv: 'python', motor: 'kod', jegyzet: 'Info/Fib.md', allapot: 'kesz' });
    expect(a!.tesztek.map((t) => t.allapot)).toEqual(['atment', 'futasi_hiba']);
    expect(a!.tesztek[1].jelentes).toMatchObject({ sor: 4, sajat: true });
    // a `kesz` összesítőbe nem kerül át az útvonal-metaadat (forras, nyelv, jegyzet, tipus)
    for (const kulcs of ['tipus', 'forras', 'nyelv', 'jegyzet', 'futas', 'szakasz']) expect(a!.kesz).not.toHaveProperty(kulcs);
    expect(osszesit(a!)).toEqual({ fordit_ok: true, atment_db: 1, tesztek_db: 2, allapot: 'kesz' });
  });

  it('a C36a esemény (cpp_futas, ut) változatlanul értelmezett: motor cpp, nyelv a kiterjesztésből', () => {
    const a = alkalmaz(null, { tipus: 'cpp_futas', futas: 'futas-aaaaaaaaaaaa', ut: 'Info/Összeg.cpp', jegyzet: null, mod: 'gyors', szakasz: 'indul', tesztek_db: 1 });
    expect(a).toMatchObject({ ut: 'Info/Összeg.cpp', nyelv: 'cpp', motor: 'cpp' });
  });

  it('a hiba kódja rövid alakban, a szöveg a core angol mondata; a megszakítás lezár', () => {
    expect(alkalmaz(null, ev('hiba', { kod: 'kod.nincs_eszkozlanc', param: {}, uzenet: 'No Python toolchain (missing: python3). Install Python.' }))).toMatchObject({
      allapot: 'hiba',
      hiba: { kod: 'nincs_eszkozlanc', uzenet: 'No Python toolchain (missing: python3). Install Python.' },
    });
    expect(alkalmaz(alkalmaz(null, ev('indul')), ev('megszakitva'))!.allapot).toBe('megszakitva');
  });

  it('az esemény nyelv nélkül is kap nyelvet a kiterjesztésből (késői csatlakozás)', () => {
    const a = alkalmaz(null, { tipus: 'kod_futas', futas: FUTAS, forras: 'x/Main.java', szakasz: 'teszt', teszt: teszt(1), ossz: 3 });
    expect(a).toMatchObject({ nyelv: 'java', motor: 'kod', tesztek_db: 3 });
  });
});

describe('KodFutasok: az általános motor', () => {
  let keresek: { modszer: string; url: string; torzs: unknown }[];
  let ellenorizValasz: () => Response;
  let futasValasz: () => Response;

  beforeEach(() => {
    keresek = [];
    ellenorizValasz = () => valasz(202, { futas: FUTAS, nyelv: 'python', forras: 'Info/Fib.py', jegyzet: 'Info/Fib.md', mod: 'gyors', tesztek_db: 2 });
    futasValasz = () => valasz(404, { hiba: 'No such run', kod: 'kod.nincs_ilyen_futas' });
    vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
      const u = new URL(url, 'http://127.0.0.1/');
      keresek.push({ modszer: init?.method ?? 'GET', url: u.pathname + u.search, torzs: init?.body ? JSON.parse(String(init.body)) : undefined });
      if (u.pathname === '/api/kod/ellenoriz') return ellenorizValasz();
      if (u.pathname === '/api/kod/feladat')
        return valasz(200, { nyelv: 'python', jegyzet: 'Info/Fib.md', forras: 'Info/Fib.py', jegyzetek: ['Info/Fib.md'], hiba: null, tesztek: [{ sorszam: 1, sor: 3, cim: 'Példa', bemenet: '5\n', kimenet: '5\n', idokorlat_s: null, hiba: null }] });
      if (u.pathname === '/api/kod/megszakit') return valasz(200, { megszakitva: true, allapot: 'fut' });
      if (u.pathname.startsWith('/api/kod/futas/')) return futasValasz();
      return valasz(404, { hiba: 'nincs' });
    });
  });
  afterEach(() => vi.unstubAllGlobals());

  it('a .py indítása az /api/kod/ellenoriz-re megy, a nyelvvel; a válasz forrása az útvonal; a leírás a /api/kod/feladat-ból', async () => {
    const k = new KodFutasok();
    const kapcs = new CoreKapcsolat('ws://127.0.0.1:1/ws');
    const le = k.telepit(kapcs);
    const jelzesek: string[] = [];
    k.figyel((u) => jelzesek.push(u));
    const r = await k.indit('Info/Fib.py', 'gyors', null, undefined, 'python');
    expect(r).toEqual({ ok: true, futas: FUTAS, cpp: 'Info/Fib.py', jegyzet: 'Info/Fib.md' });
    expect(keresek[0]).toEqual({ modszer: 'POST', url: '/api/kod/ellenoriz', torzs: { ut: 'Info/Fib.py', mod: 'gyors', nyelv: 'python' } });
    expect(k.aktiv).toMatchObject({ futas: FUTAS, ut: 'Info/Fib.py', nyelv: 'python', motor: 'kod', allapot: 'fut', tesztek_db: 2 });
    await vi.waitFor(() => expect(k.leirasok[FUTAS]?.[0].bemenet).toBe('5\n'));
    expect(keresek.some((x) => x.url.startsWith('/api/kod/feladat?ut=Info%2FFib.md'))).toBe(true);
    // a WS-en a kod_futas események érkeznek
    kapcs.szetoszt(ev('fordit_kesz', { fordit: fordit(true) }));
    kapcs.szetoszt(ev('kesz', { atment: true, tesztek_db: 2, atment_db: 2, fordit_ok: true, ms: 12 }));
    expect(k.fut).toBe(false);
    expect(k.utolso['Info/Fib.py']).toEqual({ fordit_ok: true, atment_db: 2, tesztek_db: 2, allapot: 'kesz' });
    expect(jelzesek).toEqual(['Info/Fib.py']);
    le();
  });

  it('a motor az útból következik: .cc és .c az általános, .cpp a régi; a jegyzetből indítottnál a hívó adja', async () => {
    const k = new KodFutasok();
    await k.indit('a/x.cc', 'gyors');
    expect(keresek[0].url).toBe('/api/kod/ellenoriz');
    k.aktiv = null;
    ellenorizValasz = () => valasz(202, { futas: 'futas-bbbbbbbbbbbb', cpp: 'a/x.cpp', jegyzet: null, mod: 'gyors', tesztek_db: 0 });
    await k.indit('a/x.cpp', 'gyors');
    expect(keresek.find((x) => x.url === '/api/cpp/ellenoriz')).toEqual({ modszer: 'POST', url: '/api/cpp/ellenoriz', torzs: { ut: 'a/x.cpp', mod: 'gyors' } }); // nyelv-mező a régi motornak nem megy
    k.aktiv = null;
    ellenorizValasz = () => valasz(202, { futas: FUTAS, nyelv: 'python', forras: 'Info/Fib.py', jegyzet: 'Info/Fib.md', mod: 'gyors', tesztek_db: 1 });
    await k.indit('Info/Fib.md', 'gyors', 'Info/Fib.md', 'kod');
    expect(keresek.filter((x) => x.url === '/api/kod/ellenoriz').at(-1)!.torzs).toEqual({ ut: 'Info/Fib.md', mod: 'gyors', jegyzet: 'Info/Fib.md' });
  });

  it('a hibaágak rövid kóddal jönnek vissza: hiányzó eszközlánc, többértelmű jegyzet, mentetlen fájl, nem támogatott mód', async () => {
    const k = new KodFutasok();
    ellenorizValasz = () => valasz(503, { hiba: 'No Java toolchain (missing: javac). Install a JDK.', kod: 'kod.nincs_eszkozlanc', param: { nyelv: 'Java' } });
    expect(await k.indit('x/Main.java', 'gyors')).toMatchObject({ ok: false, kod: 'nincs_eszkozlanc', uzenet: 'No Java toolchain (missing: javac). Install a JDK.' });
    ellenorizValasz = () => valasz(409, { hiba: 'More than one task note embeds this source: choose one.', kod: 'kod.tobbertelmu', jegyzetek: ['A.md', 'B.md'] });
    expect(await k.indit('x/Main.java', 'gyors')).toMatchObject({ ok: false, kod: 'tobbertelmu', jegyzetek: ['A.md', 'B.md'] });
    ellenorizValasz = () => valasz(409, { hiba: 'unsaved', kod: 'kod.mentetlen', utak: ['x/Main.java'] });
    expect(await k.indit('x/Main.java', 'gyors')).toMatchObject({ ok: false, kod: 'mentetlen', utak: ['x/Main.java'] });
    ellenorizValasz = () => valasz(400, { hiba: 'The hibakereso mode is only available for C and C++.', kod: 'kod.mod_nem_tamogatott', param: { mod: 'hibakereso', nyelv: 'Java' } });
    expect(await k.indit('x/Main.java', 'hibakereso')).toMatchObject({ ok: false, kod: 'mod_nem_tamogatott' });
    expect(k.aktiv).toBeNull();
  });

  it('megszakítás: az általános motor útvonalán; a core újraindulása után az elveszett futás hibával zárul', async () => {
    const k = new KodFutasok();
    await k.indit('Info/Fib.py', 'gyors');
    await k.megszakit();
    expect(k.aktiv!.megszakitasKerve).toBe(true);
    expect(keresek.some((x) => x.url === '/api/kod/megszakit' && (x.torzs as { futas: string }).futas === FUTAS)).toBe(true);
    expect(keresek.some((x) => x.url === '/api/cpp/megszakit')).toBe(false);
    await k.frissit();
    expect(keresek.at(-1)!.url).toBe(`/api/kod/futas/${FUTAS}`);
    expect(k.aktiv).toMatchObject({ allapot: 'hiba', hiba: { kod: 'elveszett' } });
  });

  it('késői csatlakozás: a GET /api/kod/futas/{id} összesítője (forras, nyelv, hiba objektum) a futás állapota lesz', async () => {
    const k = new KodFutasok();
    await k.indit('Info/Fib.py', 'gyors');
    futasValasz = () =>
      valasz(200, {
        id: FUTAS, futas: FUTAS, nyelv: 'python', forras: 'Info/Fib.py', jegyzet: 'Info/Fib.md', mod: 'gyors', allapot: 'hiba', tesztek_db: 2,
        fordit: fordit(true), tesztek: [teszt(1)], kesz: null,
        hiba: { kod: 'kod.motor_hiba', param: {}, uzenet: 'The code engine stopped unexpectedly' },
      });
    await k.frissit();
    expect(k.aktiv).toMatchObject({ futas: FUTAS, ut: 'Info/Fib.py', nyelv: 'python', motor: 'kod', allapot: 'hiba', hiba: { kod: 'motor_hiba', uzenet: 'The code engine stopped unexpectedly' } });
    expect(k.aktiv!.tesztek).toHaveLength(1);
  });

  it('mindkét eseménytípusra feliratkozik (cpp_futas és kod_futas), és a leiratkozás mindkettőt leveszi', () => {
    const k = new KodFutasok();
    const kapcs = new CoreKapcsolat('ws://127.0.0.1:1/ws');
    const le = k.telepit(kapcs);
    kapcs.szetoszt({ tipus: 'cpp_futas', futas: 'futas-cccccccccccc', ut: 'a.cpp', jegyzet: null, mod: 'gyors', szakasz: 'indul', tesztek_db: 1 });
    expect(k.aktiv).toMatchObject({ motor: 'cpp', nyelv: 'cpp' });
    kapcs.szetoszt(ev('indul', { tesztek_db: 1 }));
    expect(k.aktiv).toMatchObject({ futas: FUTAS, motor: 'kod', nyelv: 'python' });
    le();
    kapcs.szetoszt({ ...ev('indul'), futas: 'kod-ffffffffffff' });
    expect(k.aktiv!.futas).toBe(FUTAS);
  });
});
