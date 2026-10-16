// A `![[x.ext]]` beágyazás más nyelveken (F10): színezett, csak olvasható kód a nyelv nevével és az utolsó futás jelvényével
// (`kod_futas` esemény); az ismeretlen kiterjesztés link-chip marad; és az `.mts` (a pillanatkép bináris-ként zárja ki) nem kód.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { kodBeagyazasRenderelo } from '../src/kod/beagyazas';
import { kodFutasok } from '../src/kod/futas.svelte';

const valasz = (kod: number, adat: unknown) => new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });
const PY = 'def fib(n):\n    return n  # vége\n';
const link = (cel: string) => ({ cel, alcel: null, alias: null, beagyazas: true, from: 0, to: 0 });
let keresek: string[];

beforeEach(() => {
  keresek = [];
  kodFutasok.utolso = {};
  vi.stubGlobal('fetch', async (url: string) => {
    const u = new URL(url, 'http://127.0.0.1/');
    keresek.push(u.pathname);
    if (u.pathname === '/api/vault/fajl') return valasz(200, { ut: u.searchParams.get('ut'), tartalom: PY, hash: 'h', jel: '', mtime: 0 });
    return valasz(404, { hiba: 'nincs' });
  });
});
afterEach(() => vi.unstubAllGlobals());

describe('a kód-beágyazás más nyelveken', () => {
  it('.py: színezett kód, a nyelv neve, a Megnyitás gomb; a jelvény a kod_futas eseményből élőben frissül', async () => {
    const ut = 'Info/Fib.py';
    const kont = document.createElement('span');
    const jel = new AbortController();
    await kodBeagyazasRenderelo.render({ tipus: 'egyeb', ut, alcel: null } as never, link('Fib.py'), kont, { forras: 'Info/Fib.md', jel: jel.signal });
    expect(kont.className).toBe('beagyazas kod-beagyazas');
    expect(kont.querySelector('.beagyazas-cim')!.textContent).toBe('Fib.py');
    expect(kont.querySelector('.kod-nyelv-jel')!.textContent).toBe('Python');
    expect(kont.querySelector('.kod-beagyazas-nyit')!.textContent).toBe('Megnyitás');
    const kod = kont.querySelector('pre.kod-beagyazas-kod code')!;
    expect(kod.textContent).toBe(PY.replace(/\n$/, ''));
    await vi.waitFor(() => expect(kod.querySelector('.tok-keyword, .tok-definitionKeyword')).not.toBeNull());
    expect(kod.querySelector('.tok-comment')?.textContent).toBe('# vége');
    const jelv = kont.querySelector<HTMLElement>('.kod-jelveny')!;
    expect(jelv.hidden).toBe(true);
    const alap = { tipus: 'kod_futas', futas: 'kod-111111111111', nyelv: 'python', forras: ut, jegyzet: null, mod: 'gyors' };
    kodFutasok.esemeny({ ...alap, szakasz: 'indul', tesztek_db: 3 });
    kodFutasok.esemeny({ ...alap, szakasz: 'fordit_kesz', fordit: { ok: true, diagnosztika: [] } });
    kodFutasok.esemeny({ ...alap, szakasz: 'kesz', atment: true, tesztek_db: 3, atment_db: 3, fordit_ok: true, ms: 9 });
    expect(jelv.hidden).toBe(false);
    expect(jelv.textContent).toBe('3/3 átment');
    expect(jelv.classList.contains('jo')).toBe(true);
    jel.abort();
  });

  it('minden profil minden kiterjesztése kód-beágyazás a nyelve nevével; az ismeretlen és az .mts link-chip', async () => {
    for (const [ut, nev] of [['a/x.cc', 'C++'], ['a/x.c', 'C'], ['a/x.mjs', 'JavaScript'], ['a/x.ts', 'TypeScript'], ['a/Main.java', 'Java'], ['a/x.go', 'Go'], ['a/x.rs', 'Rust'], ['a/x.swift', 'Swift']]) {
      const kont = document.createElement('span');
      await kodBeagyazasRenderelo.render({ tipus: 'egyeb', ut, alcel: null } as never, link(ut.split('/')[1]), kont, { forras: 'J.md' });
      expect(kont.className, ut).toBe('beagyazas kod-beagyazas');
      expect(kont.querySelector('.kod-nyelv-jel')!.textContent, ut).toBe(nev);
    }
    for (const ut of ['a/x.rb', 'a/x.mts', 'a/x.h']) {
      const kont = document.createElement('span');
      const elozo = keresek.length;
      await kodBeagyazasRenderelo.render({ tipus: 'egyeb', ut, alcel: null } as never, link(ut.split('/')[1]), kont, { forras: 'J.md' });
      expect(kont.className, ut).toBe('beagyazas beagyazas-chip');
      expect(keresek.length, ut).toBe(elozo); // nem olvassa be a fájlt
    }
  });
});
