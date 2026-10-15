// A `![[x.cpp]]` beágyazás és a kódrészletek (C36a-UI): színezett, csak olvasható kód a jelvénnyel; a nem `.cpp` `egyeb`
// cél link-chip marad; a hiányzó `![[x.cpp]]` „Létrehozás”-a `.cpp`-t kér (nem `x.cpp.md`-t); a kódrészletek a
// kiegészítő listában.

import { CompletionContext, type Completion } from '@codemirror/autocomplete';
import { EditorState } from '@codemirror/state';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { jelveny, kodBeagyazasRenderelo } from '../src/kod/beagyazas';
import { kodFutasok } from '../src/kod/futas.svelte';
import { RESZLETEK, reszletForras } from '../src/kod/reszletek';
import { fajlNev } from '../src/lib/vault/fajlok.svelte';
import { jegyzetLetrehoz } from '../src/szerkeszto/linkek/navigacio';

const CPP = '#include <bits/stdc++.h>\nusing namespace std;\n\nint main() {\n    return 0; // vége\n}\n';
const valasz = (kod: number, adat: unknown) => new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });
let keresek: { ut: string; torzs: unknown }[];

beforeEach(() => {
  keresek = [];
  kodFutasok.utolso = {};
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    const u = new URL(url, 'http://127.0.0.1/');
    keresek.push({ ut: u.pathname, torzs: init?.body ? JSON.parse(String(init.body)) : undefined });
    if (u.pathname === '/api/vault/fajl') return valasz(200, { ut: u.searchParams.get('ut'), tartalom: CPP, hash: 'h', jel: '', mtime: 0 });
    if (u.pathname === '/api/vault/uj') return valasz(201, { ut: 'Info/Új.cpp' });
    return valasz(404, { hiba: 'nincs' });
  });
});

afterEach(() => vi.unstubAllGlobals());

const link = (cel: string) => ({ cel, alcel: null, alias: null, beagyazas: true, from: 0, to: 0 });

describe('a .cpp beágyazás', () => {
  it('színezett kód, fejléc a fájlnévvel és a Megnyitás gombbal; a jelvény az utolsó futásból, élőben frissül', async () => {
    const ut = 'Info/Összeg.cpp';
    const kont = document.createElement('span');
    const jel = new AbortController();
    await kodBeagyazasRenderelo.render({ tipus: 'egyeb', ut, alcel: null } as never, link('Összeg.cpp'), kont, { forras: 'Info/Összeg.md', jel: jel.signal });
    expect(kont.className).toBe('beagyazas kod-beagyazas');
    expect(kont.querySelector('.beagyazas-cim')!.textContent).toBe('Összeg.cpp');
    expect(kont.querySelector('.kod-beagyazas-nyit')!.textContent).toBe('Megnyitás');
    const kod = kont.querySelector('pre.kod-beagyazas-kod code')!;
    expect(kod.textContent).toBe(CPP.replace(/\n$/, ''));
    await vi.waitFor(() => expect(kod.querySelector('.tok-keyword')).not.toBeNull());
    expect(kod.querySelector('.tok-comment')?.textContent).toBe('// vége');
    const jelv = kont.querySelector<HTMLElement>('.kod-jelveny')!;
    expect(jelv.hidden).toBe(true);
    kodFutasok.esemeny({ tipus: 'cpp_futas', futas: 'futas-111111111111', ut, jegyzet: null, mod: 'gyors', szakasz: 'indul', tesztek_db: 5 });
    kodFutasok.esemeny({ tipus: 'cpp_futas', futas: 'futas-111111111111', ut, jegyzet: null, mod: 'gyors', szakasz: 'fordit_kesz', fordit: { ok: true, diagnosztika: [] } });
    kodFutasok.esemeny({ tipus: 'cpp_futas', futas: 'futas-111111111111', ut, jegyzet: null, mod: 'gyors', szakasz: 'kesz', atment: false, tesztek_db: 5, atment_db: 4, fordit_ok: true, ms: 9 });
    expect(jelv.hidden).toBe(false);
    expect(jelv.textContent).toBe('4/5 átment');
    expect(jelv.classList.contains('rossz')).toBe(true);
    jel.abort(); // a beágyazás eltűnt: a figyelő leiratkozik
  });

  it('a nem .cpp egyéb cél link-chip marad', async () => {
    const kont = document.createElement('span');
    await kodBeagyazasRenderelo.render({ tipus: 'egyeb', ut: 'Adat/minta.txt', alcel: null } as never, link('minta.txt'), kont, { forras: 'J.md' });
    expect(kont.className).toBe('beagyazas beagyazas-chip');
    expect(keresek).toHaveLength(0);
  });

  it('jelvény: fordítási hiba, csak fordítás, minden átment, megszakítva', () => {
    expect(jelveny(undefined)).toBeNull();
    expect(jelveny({ fordit_ok: false, atment_db: 0, tesztek_db: 3, allapot: 'kesz' })).toEqual({ szoveg: 'fordítási hiba', fajta: 'rossz' });
    expect(jelveny({ fordit_ok: true, atment_db: 0, tesztek_db: 0, allapot: 'kesz' })!.szoveg).toBe('lefordul');
    expect(jelveny({ fordit_ok: true, atment_db: 3, tesztek_db: 3, allapot: 'kesz' })).toEqual({ szoveg: '3/3 átment', fajta: 'jo' });
    expect(jelveny({ fordit_ok: true, atment_db: 1, tesztek_db: 3, allapot: 'megszakitva' })!.fajta).toBe('semleges');
  });

  it('a hiányzó ![[x.cpp]] létrehozása C++ forrást kér (tipus: cpp), nem x.cpp.md-t; a .md változatlan', async () => {
    expect(await jegyzetLetrehoz('Info/Összeg.md', 'Új.cpp')).toBe('Info/Új.cpp');
    // C31 (T158): a helyet a core dönti a nyers link-célból (`link`), a típus a `.cpp` célból
    expect(keresek.at(-1)).toEqual({ ut: '/api/vault/uj', torzs: { link: { cel: 'Új.cpp', forras: 'Info/Összeg.md' }, tipus: 'cpp' } });
    await jegyzetLetrehoz('Info/Összeg.md', 'Másik');
    expect(keresek.at(-1)!.torzs).toEqual({ link: { cel: 'Másik', forras: 'Info/Összeg.md' } });
    expect(fajlNev('Info/Új.cpp')).toBe('Új.cpp');
  });
});

describe('kódrészletek', () => {
  function lista(szoveg: string, explicit = false): Completion[] | null {
    const st = EditorState.create({ doc: szoveg });
    const r = reszletForras(new CompletionContext(st, szoveg.length, explicit));
    return r ? (r.options as Completion[]) : null;
  }

  it('szó elején ajánl, megjegyzésben és sztringben nem; ⌃Space üres helyen is', () => {
    expect(lista('fo')!.map((o) => o.label)).toContain('for');
    expect(lista('int x; // fo')).toBeNull();
    expect(lista('cout << "fo')).toBeNull();
    expect(lista('')).toBeNull();
    expect(lista('', true)!.length).toBe(RESZLETEK.length);
  });

  it('minden részlet magyar leírással; a címkék egyediek; a main váz a core cpp_vaz-ával egyező szerkezetű', () => {
    expect(new Set(RESZLETEK.map((r) => r.cimke)).size).toBe(RESZLETEK.length);
    for (const r of RESZLETEK) expect(r.leiras.length).toBeGreaterThan(3);
    const main = RESZLETEK.find((r) => r.cimke === 'main')!.sablon;
    expect(main).toContain('#include <bits/stdc++.h>');
    expect(main).toContain('cin.tie(nullptr);');
    // a mezők nem tartalmaznak csupasz számot (a CodeMirror a `${0}`-t mezőindexnek venné, üres szöveggel)
    for (const r of RESZLETEK) expect(r.sablon).not.toMatch(/\$\{\d+\}/);
  });
});
