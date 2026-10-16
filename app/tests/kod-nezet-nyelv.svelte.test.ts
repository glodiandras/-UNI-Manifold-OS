// A kód-fül más nyelveken (F10), jsdom-ban, ál-core-ral: a nyelv a kiterjesztésből, az eszközlánc-állapot (kész / hiányzik + a core
// teendője), a ⌘R az általános motoron (a mentés kivárásával), a sorhoz kötött hiba az editorban (szintaxis-hiba, futási hiba), az
// „elemzés” felirat az értelmezett nyelveknél, a megszakítás, az AI-panel; és a jegyzetből indított futás nyelv szerinti motorja.

import { forEachDiagnostic } from '@codemirror/lint';
import { EditorView } from '@codemirror/view';
import { cleanup, fireEvent, render, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { kodAI } from '../src/kod/ai.svelte';
import { kodFulok } from '../src/kod/aktiv.svelte';
import { kodFutasok } from '../src/kod/futas.svelte';
import KodFul from '../src/kod/KodFul.svelte';
import { celNyelve, ellenoriz, kodCel } from '../src/kod/muveletek';
import { kodNyelvek } from '../src/kod/nyelvek.svelte';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import type { Ful } from '../src/lib/elrendezes/munkaterulet.svelte';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';
import { sorVege } from '../src/szerkeszto/dokumentum/mentesSor';
import { szerkesztok, type SzerkesztoPeldany } from '../src/szerkeszto/szerkesztok.svelte';
import { EditorState } from '@codemirror/state';

const UT = 'Info/Fib.py';
const JEGYZET = 'Info/Fib.md';
const FORRAS = 'def fib(n):\n    return n if n < 2 else fib(n - 1) + fib(n - 2)\n\nprint(fib(int(input())))\nprint(1 / 0)\n';
const FUTAS = 'kod-0123456789ab';

let lemez: Map<string, string>;
let keresek: { modszer: string; ut: string; torzs: Record<string, unknown> | undefined }[];
let ellenorizValasz: () => Response;
let nyelvekValasz: () => Response;

const hash = (s: string) => `h${s.length}:${[...s].reduce((h, c) => (h * 31 + c.charCodeAt(0)) | 0, 7)}`;
const valasz = (kod: number, adat: unknown) => new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });
const profil = (azonosito: string, nev: string, elerheto: boolean, hiba: unknown = null, extra: Record<string, unknown> = {}) => ({
  azonosito, nev, kiterjesztesek: [], motor: azonosito === 'cpp' ? 'cpp' : 'nyelv', nativ: false, eszkozlanc: 'rendszer', kalibracios_kulcs: `kod_${azonosito}`, ai_modok: [],
  modok: ['gyors'], telepites_tipp: `Install ${nev}.`, elerheto, eszkozok: [{ nev: azonosito, ok: elerheto }], hiba, ...extra,
});

beforeEach(() => {
  lemez = new Map([[UT, FORRAS]]);
  keresek = [];
  kodFutasok.aktiv = null;
  kodFutasok.tobbertelmu = null;
  kodFutasok.jegyzetValasztas.clear();
  kodNyelvek.visszaallit();
  kodAI.aktiv = null;
  kodAI.allapot = null;
  ellenorizValasz = () => valasz(202, { futas: FUTAS, nyelv: 'python', forras: UT, jegyzet: JEGYZET, mod: 'gyors', tesztek_db: 1 });
  nyelvekValasz = () => valasz(200, { nyelvek: [profil('python', 'Python', true, null, { eszkozlanc: 'beagyazott' }), profil('java', 'Java', false, { kod: 'kod.nincs_eszkozlanc', param: {}, uzenet: 'No Java toolchain (missing: javac). Install a JDK (17 or newer).' })] });
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    const u = new URL(url, 'http://127.0.0.1/');
    const torzs = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : undefined;
    keresek.push({ modszer: init?.method ?? 'GET', ut: u.pathname, torzs });
    if (u.pathname === '/api/vault/fajl' && (!init?.method || init.method === 'GET')) {
      const ut = u.searchParams.get('ut')!;
      const t = lemez.get(ut);
      if (t === undefined) return valasz(404, { hiba: 'nincs ilyen fájl' });
      return valasz(200, { ut, tartalom: t, hash: hash(t), jel: '', mtime: 0, kodolas_hiba: false });
    }
    if (u.pathname === '/api/vault/fajl' && init?.method === 'PUT') {
      const k = torzs as { ut: string; tartalom: string; alap: string };
      const regi = lemez.get(k.ut)!;
      if (k.alap !== hash(regi)) return valasz(409, { hiba: 'ütközés', utkozes: true, hash: hash(regi) });
      lemez.set(k.ut, k.tartalom);
      return valasz(200, { ok: true, ut: k.ut, hash: hash(k.tartalom), jel: '', uzenet: 'mentve', pillanat: null, elotte: null, git: true });
    }
    if (u.pathname === '/api/kod/nyelvek') return nyelvekValasz();
    if (u.pathname === '/api/kod/ellenoriz') return ellenorizValasz();
    if (u.pathname === '/api/kod/feladat')
      return valasz(200, { nyelv: 'python', jegyzet: JEGYZET, forras: UT, jegyzetek: [JEGYZET], hiba: null, tesztek: [{ sorszam: 1, sor: 8, cim: 'Példa', bemenet: '5\n', kimenet: '5\n', idokorlat_s: null, hiba: null }] });
    if (u.pathname === '/api/kod/megszakit') return valasz(200, { megszakitva: true, allapot: 'fut' });
    return valasz(404, { hiba: `nincs: ${u.pathname}` });
  });
});

afterEach(async () => {
  cleanup();
  await sorVege();
  vi.unstubAllGlobals();
  for (const d of szerkesztok.dokumentumok.lista()) szerkesztok.dokumentumok.eldob(d.ut);
  szerkesztok.aktiv = null;
});

function nyit(ut = UT) {
  const ful = $state<Ful>({ id: 'f1', ut });
  const felulet = new Felulet({});
  const kornyezet = { felulet, fajlok: new VaultFajlok(), kapcsolat: new CoreKapcsolat('ws://127.0.0.1:1/ws') };
  const c = render(KodFul, { props: { ful, info: undefined, aktiv: true }, context: new Map([[KORNYEZET_KULCS, kornyezet]]) });
  return { c, felulet };
}

async function nezet(c: { container: HTMLElement }): Promise<EditorView> {
  return await waitFor(() => {
    const el = c.container.querySelector<HTMLElement>('.cm-editor');
    expect(el).not.toBeNull();
    return EditorView.findFromDOM(el!)!;
  });
}

const ev = (szakasz: string, adat: Record<string, unknown> = {}) => ({ tipus: 'kod_futas', futas: FUTAS, nyelv: 'python', forras: UT, jegyzet: JEGYZET, mod: 'gyors', szakasz, ...adat });
const fordit = (ok: boolean, diagnosztika: unknown[] = []) => ({ ok, allapot: ok ? 'ok' : 'hiba', ms: 30, hiba_db: ok ? 0 : 1, figyelmeztetes_db: 0, diagnosztika });

describe('a .py fül', () => {
  it('betöltés: a forrás a szerkesztőben, a fül az aktív kód-fül, a nyelv jelvénye; a hibakereső gomb nincs (csak C/C++)', async () => {
    const { c } = nyit();
    const v = await nezet(c);
    expect(v.state.doc.toString()).toBe(FORRAS);
    expect(kodFulok.aktiv?.ut).toBe(UT);
    expect(c.container.querySelector('.cm-kodszerkeszto')).not.toBeNull();
    expect(c.container.querySelector('.jelveny .nev')!.textContent).toBe('Python');
    expect(c.container.querySelector('[aria-label="Ellenőrzés hibakereső móddal"]')).toBeNull();
    expect(c.container.querySelector('[aria-label="Ellenőrzés"]')).not.toBeNull();
    expect(v.contentDOM.getAttribute('aria-label')).toBe('Forráskód (Python): Fib.py');
    // a színezés lustán érkezik: a Python-nyelv a betöltés után kapcsolódik
    await waitFor(() => expect(v.dom.querySelector('.tok-keyword, .tok-def, .tok-variableName')).not.toBeNull());
  });

  it('az eszközlánc kész: jelvény ikonnal és szóval, nincs figyelmeztető sáv', async () => {
    const { c } = nyit();
    await waitFor(() => expect(c.container.querySelector('.jelveny.jo')).not.toBeNull());
    expect(c.container.querySelector('.jelveny')!.textContent).toContain('Eszközlánc kész');
    expect(c.container.querySelector('.jelveny svg')).not.toBeNull();
    expect(c.container.querySelector('.figy')).toBeNull();
  });

  it('az eszközlánc hiányzik: a jelvény és a sáv megnevezi a hiányt és a teendőt (a core mondata), az újraellenőrzés frissít', async () => {
    nyelvekValasz = () => valasz(200, { nyelvek: [profil('python', 'Python', false, { kod: 'kod.nincs_eszkozlanc', param: {}, uzenet: 'No Python toolchain (missing: python3). Install Python.' })] });
    const { c } = nyit();
    const figy = await waitFor(() => {
      const f = c.container.querySelector<HTMLElement>('.figy');
      expect(f).not.toBeNull();
      return f!;
    });
    expect(c.container.querySelector('.jelveny.rossz')!.textContent).toContain('Eszközlánc hiányzik');
    expect(figy.textContent).toContain('Python: az eszközlánc hiányzik');
    expect(figy.textContent).toContain('Hiányzik: python');
    expect(figy.textContent).toContain('No Python toolchain (missing: python3). Install Python.');
    // újraellenőrzés: a core gyorsítótárát megkerüli
    nyelvekValasz = () => valasz(200, { nyelvek: [profil('python', 'Python', true)] });
    await fireEvent.click(figy.querySelector('button')!);
    await waitFor(() => expect(c.container.querySelector('.figy')).toBeNull());
    expect(keresek.some((k) => k.ut === '/api/kod/nyelvek')).toBe(true);
    expect(c.container.querySelector('.jelveny.jo')).not.toBeNull();
  });

  it('a jelvényre kattintva az összes nyelv eszközlánca látszik, a hiányzóké teendővel', async () => {
    const { c } = nyit();
    await waitFor(() => expect(c.container.querySelector('.jelveny.jo')).not.toBeNull());
    await fireEvent.click(c.container.querySelector('.jelveny')!);
    const lista = await waitFor(() => {
      const l = c.container.querySelector<HTMLElement>('.lista');
      expect(l).not.toBeNull();
      return l!;
    });
    expect(lista.textContent).toContain('Python');
    expect(lista.textContent).toContain('Java');
    expect(lista.textContent).toContain('No Java toolchain (missing: javac). Install a JDK (17 or newer).');
    expect(lista.querySelectorAll('.allapot svg')).toHaveLength(2); // ikon + szó, nem csak szín
    expect(lista.querySelector('.aktualis .nev')!.textContent).toBe('Python');
  });

  it('a core nem válaszol az eszközláncokra: a jelvény megmondja, a lista ismételhető állapotot mutat', async () => {
    nyelvekValasz = () => valasz(503, { hiba: 'The code engine does not answer: boom', kod: 'kod.motor_nem_valaszol' });
    const { c } = nyit();
    await waitFor(() => expect(c.container.querySelector('.jelveny')!.textContent).toContain('Az eszközlánc állapota nem ismert'));
    await fireEvent.click(c.container.querySelector('.jelveny')!);
    await waitFor(() => expect(c.container.querySelector('[data-ures]')).not.toBeNull());
    expect(c.container.querySelector('[data-ures]')!.textContent).toContain('does not answer');
  });

  it('gépelés → mentés az egyetlen írási úton; a ⌘R előbb kivárja a mentést, majd az /api/kod/ellenoriz-t hívja a nyelvvel', async () => {
    const { c, felulet } = nyit();
    const v = await nezet(c);
    v.dispatch({ changes: { from: 0, insert: '# megoldás\n' } });
    expect(await ellenoriz(felulet, 'gyors')).toBe(true);
    const put = keresek.findIndex((k) => k.modszer === 'PUT' && k.ut === '/api/vault/fajl');
    const post = keresek.findIndex((k) => k.ut === '/api/kod/ellenoriz');
    expect(put).toBeGreaterThanOrEqual(0);
    expect(post).toBeGreaterThan(put);
    expect(lemez.get(UT)!.startsWith('# megoldás\n')).toBe(true);
    expect(keresek[post].torzs).toEqual({ ut: UT, mod: 'gyors', nyelv: 'python' });
    expect(keresek.some((k) => k.ut === '/api/cpp/ellenoriz')).toBe(false);
    expect(kodFutasok.aktiv).toMatchObject({ motor: 'kod', nyelv: 'python', ut: UT });
  });

  it('szintaxis-hiba: „Szintaxis-hiba” felirat (nem „Fordítás”), a hozzá kötött sor aláhúzva, kattintásra ugrás a sorra', async () => {
    const { c, felulet } = nyit();
    const v = await nezet(c);
    await ellenoriz(felulet, 'gyors');
    kodFutasok.esemeny(ev('indul', { tesztek_db: 1 }));
    kodFutasok.esemeny(ev('fordit_kesz', { fordit: fordit(false, [{ szint: 'error', fajl: 'megoldas.py', sor: 2, oszlop: 12, uzenet: "invalid syntax", sajat: true, kodreszlet: [] }]) }));
    kodFutasok.esemeny(ev('kesz', { atment: false, tesztek_db: 1, atment_db: 0, fordit_ok: false, ms: 40 }));
    const gomb = await waitFor(() => {
      const g = [...c.container.querySelectorAll<HTMLButtonElement>('.diag-gomb')].find((b) => b.textContent!.includes('invalid syntax'));
      expect(g).toBeTruthy();
      return g!;
    });
    expect(c.container.textContent).toContain('Szintaxis-hiba');
    expect(c.container.textContent).not.toContain('Fordítás sikertelen');
    const lista: { from: number; message: string; source?: string; severity: string }[] = [];
    forEachDiagnostic(v.state, (d, from) => lista.push({ from, message: d.message, source: d.source, severity: d.severity }));
    expect(lista).toHaveLength(1);
    expect(lista[0]).toMatchObject({ message: 'invalid syntax', source: 'Python', severity: 'error' });
    expect(v.state.doc.lineAt(lista[0].from).number).toBe(2);
    await fireEvent.click(gomb);
    expect(v.state.doc.lineAt(v.state.selection.main.head).number).toBe(2);
  });

  it('futási hiba: a teszt jelentése a saját sorra kötve aláhúzva az editorban, a nem saját keret nem; a panel mutatja a sort', async () => {
    const { c, felulet } = nyit();
    const v = await nezet(c);
    await ellenoriz(felulet, 'gyors');
    kodFutasok.esemeny(ev('fordit_kesz', { fordit: fordit(true) }));
    kodFutasok.esemeny(
      ev('teszt', {
        teszt: {
          sorszam: 1, cim: 'Példa', allapot: 'futasi_hiba', ido_ms: 9, csucs_mb: 8, diff: null, kilepes: 1, jel: null, uzenet: 'the program exited with an error',
          stdout_kivonat: '', stderr_kivonat: 'Traceback…',
          jelentes: { forras: 'python', fajta: 'ZeroDivisionError', leiras: 'ZeroDivisionError: division by zero', fajl: 'megoldas.py', sor: 5, oszlop: null, fuggveny: null, sajat: true, keretek: [] },
        },
        ossz: 1,
      }),
    );
    kodFutasok.esemeny(ev('teszt', { teszt: { sorszam: 2, cim: null, allapot: 'futasi_hiba', ido_ms: 9, csucs_mb: 8, diff: null, jelentes: { forras: 'python', fajta: 'E', leiras: 'idegen modul', fajl: 'lib.py', sor: 3, oszlop: null, fuggveny: null, sajat: false, keretek: [] } }, ossz: 2 }));
    kodFutasok.esemeny(ev('kesz', { atment: false, tesztek_db: 2, atment_db: 0, fordit_ok: true, ms: 50 }));
    const lista: { from: number; message: string }[] = [];
    await waitFor(() => {
      lista.length = 0;
      forEachDiagnostic(v.state, (d, from) => lista.push({ from, message: d.message }));
      expect(lista).toHaveLength(1);
    });
    expect(lista[0].message).toBe('ZeroDivisionError: division by zero');
    expect(v.state.doc.lineAt(lista[0].from).number).toBe(5);
    expect(c.container.textContent).toContain('Szintaxis rendben');
    expect(c.container.textContent).toContain('0/2 teszt átment');
    const ugro = [...c.container.querySelectorAll<HTMLButtonElement>('.link-gomb')].find((b) => b.textContent!.includes('5'));
    expect(ugro).toBeTruthy();
  });

  it('Esc futás közben az általános motor megszakítójára megy', async () => {
    const { c, felulet } = nyit();
    await nezet(c);
    await ellenoriz(felulet, 'gyors');
    kodFutasok.esemeny(ev('indul', { tesztek_db: 1 }));
    await fireEvent.keyDown(c.container.querySelector('.kod-ful')!, { key: 'Escape' });
    await waitFor(() => expect(keresek.some((k) => k.ut === '/api/kod/megszakit')).toBe(true));
    expect(keresek.some((k) => k.ut === '/api/cpp/megszakit')).toBe(false);
    expect(c.container.textContent).toContain('Megszakítás…');
  });

  it('hiányzó eszközlánc az indításkor: tartós hibaértesítés a core mondatával, és az eszközlánc-lista frissül', async () => {
    const { ertesitesek } = await import('../src/lib/ertesites/ertesites.svelte');
    const { c, felulet } = nyit();
    await nezet(c);
    ellenorizValasz = () => valasz(503, { hiba: 'No Python toolchain (missing: python3). Install Python.', kod: 'kod.nincs_eszkozlanc', param: { nyelv: 'Python' } });
    expect(await ellenoriz(felulet, 'gyors')).toBe(false);
    const e = ertesitesek.lista.find((x) => x.cim === 'Hiányzik az eszközlánc');
    expect(e?.szoveg).toContain('Install Python.');
    expect(e?.szint).toBe('hiba');
    expect(e?.idotartam).toBe(0);
    for (const x of [...ertesitesek.lista]) ertesitesek.elvet(x.id);
    expect(keresek.filter((k) => k.ut === '/api/kod/nyelvek').length).toBeGreaterThanOrEqual(2);
  });

  it('az AI-panel a fülön: a gombok kalibrált modell nélkül is élnek (trial), a próba-eredmény jelölt', async () => {
    const { c } = nyit();
    await nezet(c);
    const gomb = [...c.container.querySelectorAll('button')].find((b) => b.textContent?.trim() === 'Mi a hiba?') as HTMLButtonElement;
    expect(gomb.disabled).toBe(false);
    kodAI.esemeny({ tipus: 'kod_ai', ai: 'kodai-0123456789ab', mod: 'hiba', nyelv: 'python', forras: UT, jegyzet: JEGYZET, szakasz: 'modell', modell: 'qwen35_4b', proba: true, indok: 'trial' });
    kodAI.esemeny({ tipus: 'kod_ai', ai: 'kodai-0123456789ab', mod: 'hiba', nyelv: 'python', forras: UT, jegyzet: JEGYZET, szakasz: 'eredmeny', proba: true, sor: 5, fajta: 'logika', magyarazat: 'Nullával osztasz.', ellenorzott: true });
    await waitFor(() => expect(c.container.querySelector('.eredmeny [data-jel="proba"]')).not.toBeNull());   // a közös ProbaJel (szava: tests/kod-ai-nyelv.test.ts)
    expect(c.container.querySelector('.eredmeny [data-jel="proba"] svg')).not.toBeNull();
  });
});

describe('a jegyzetből indított futás nyelve', () => {
  function mdPeldany(ut: string, szoveg: string): SzerkesztoPeldany {
    const v = new EditorView({ state: EditorState.create({ doc: szoveg }) });
    return { ut, nezet: () => v, mod: () => 'elo', olvasoValt: () => {}, forrasValt: () => {}, mentes: async () => {}, pillanatkep: async () => {}, fokuszban: () => true, ugras: () => {}, vazlat: () => [], valtozat: () => 0 };
  }

  it('a .py-t beágyazó jegyzet cél és az általános motoron fut; a .cpp-t beágyazó a régin; az ismeretlen kiterjesztés nem cél', async () => {
    szerkesztok.aktiv = mdPeldany(JEGYZET, '# Fib\n\n![[Fib.py]]\n');
    expect(kodCel()).toEqual({ ut: JEGYZET, jegyzet: JEGYZET });
    expect(celNyelve(kodCel())).toMatchObject({ motor: 'kod', nyelv: { azonosito: 'python' } });
    const felulet = new Felulet({});
    expect(await ellenoriz(felulet, 'gyors')).toBe(true);
    expect(keresek.find((k) => k.ut === '/api/kod/ellenoriz')!.torzs).toEqual({ ut: JEGYZET, mod: 'gyors', jegyzet: JEGYZET, nyelv: 'python' });
    kodFutasok.aktiv = null;

    szerkesztok.aktiv = mdPeldany('Info/Régi.md', '![[Régi.cpp]]');
    expect(celNyelve(kodCel())).toMatchObject({ motor: 'cpp', nyelv: { azonosito: 'cpp' } });

    szerkesztok.aktiv = mdPeldany('Info/Más.md', '![[Más.rb]]\n[[Fib.py]] csak link');
    expect(kodCel()).toBeNull();
    expect(celNyelve(null)).toEqual({ nyelv: null, motor: 'cpp' });
  });

  it('több beágyazott forrás: az első dönt (ahogy a core is választ)', () => {
    szerkesztok.aktiv = mdPeldany(JEGYZET, '![[Fib.go]]\n![[Fib.cpp]]');
    expect(celNyelve(kodCel())).toMatchObject({ motor: 'kod', nyelv: { azonosito: 'go' } });
  });
});
