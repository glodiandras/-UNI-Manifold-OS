// A kód-munkafelület nyelvtáblája és eszközlánc-állapota (F10): minden profil-kiterjesztés kód-fájl (fa, ikon, nézet, beágyazás),
// a nyelv a kiterjesztésből és a jegyzet kódblokk-jelölőjéből jön, a motor-választás (a `.cpp` a C36a-n marad), és a
// `GET /api/kod/nyelvek` eszközlánc-állapota (elérhető / hiányzik + érthető teendő a `kod.*` hibakódból).

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  BEAGYAZOTT_KOD,
  jegyzetNyelve,
  KOD_NYELVEK,
  KOD_UT,
  KodNyelvek,
  motorForras,
  motorUt,
  nyelvAzonosito,
  nyelvKeritesbol,
  nyelvUt,
  rovidKod,
} from '../src/kod/nyelvek.svelte';
import { Code, File } from '../src/lib/ikon/ikonok';
import { fajlIkon } from '../src/lib/ikon/fajlIkon';
import { KOD_KITERJESZTESEK, elsoBeagyazottKod } from '../src/lib/vault/kodFajl';
import { nemTamogatott } from '../src/lib/vault/fa';

const valasz = (kod: number, adat: unknown) => new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });

describe('a nyelvtábla', () => {
  it('minden profil minden szerkeszthető kiterjesztése kód-fájl, kis- és nagybetűvel; az azonosító a kiterjesztésből jön', () => {
    expect(KOD_NYELVEK.map((n) => n.azonosito)).toEqual(['cpp', 'c', 'python', 'javascript', 'typescript', 'java', 'go', 'rust', 'swift']);
    for (const n of KOD_NYELVEK)
      for (const k of n.kiterjesztesek) {
        expect(KOD_UT.test(`Mappa/Fájl${k}`), k).toBe(true);
        expect(KOD_UT.test(`Mappa/FÁJL${k.toUpperCase()}`), k).toBe(true);
        expect(nyelvUt(`Mappa/x${k}`)?.azonosito, k).toBe(n.azonosito);
      }
  });

  it('nem kód: jegyzet, fejlécfájl, szkript, a pillanatképből kizárt .mts, kiterjesztés nélküli név, mappanévben álló pont', () => {
    for (const ut of ['J.md', 'x.h', 'x.hpp', 'x.sh', 'x.rb', 'x.mts', 'x.cpp.bak', 'Makefile', 'mappa.py/readme', 'x.jsx', 'x.txt'])
      expect(KOD_UT.test(ut), ut).toBe(false);
    expect(nyelvUt('x.mts')).toBeNull();
    expect(nyelvUt('mappa.py/readme')).toBeNull();
    expect(nyelvUt(null)).toBeNull();
    expect(KOD_KITERJESZTESEK).not.toContain('.mts');
  });

  it('a fájlfa és az ikon: minden kód-fájl látszik és kód-ikont kap, az egyéb ismeretlen nem', () => {
    for (const k of KOD_KITERJESZTESEK) {
      expect(nemTamogatott({ ut: `a/b${k}`, tipus: 'egyeb' }), k).toBe(false);
      expect(fajlIkon('egyeb', `a/b${k}`), k).toBe(Code);
    }
    expect(nemTamogatott({ ut: 'a/b.zip', tipus: 'egyeb' })).toBe(true);
    expect(fajlIkon('egyeb', 'a/b.zip')).toBe(File);
    expect(fajlIkon('md', 'a/b.py')).not.toBe(Code); // az index típusa dönt: a jegyzet marad jegyzet
  });

  it('a jegyzet kódblokkjának nyelvjelölőjéből (fence) a nyelv; ismeretlen jelölő nincs', () => {
    expect(nyelvKeritesbol('py')?.azonosito).toBe('python');
    expect(nyelvKeritesbol('Python')?.azonosito).toBe('python');
    expect(nyelvKeritesbol('c++ {.numberLines}')?.azonosito).toBe('cpp');
    expect(nyelvKeritesbol('js')?.azonosito).toBe('javascript');
    expect(nyelvKeritesbol('ts')?.azonosito).toBe('typescript');
    expect(nyelvKeritesbol('golang')?.azonosito).toBe('go');
    expect(nyelvKeritesbol('rs')?.azonosito).toBe('rust');
    for (const n of KOD_NYELVEK) for (const j of n.kerites) expect(nyelvKeritesbol(j)?.azonosito, j).toBe(n.azonosito);
    expect(nyelvKeritesbol('mermaid')).toBeNull();
    expect(nyelvKeritesbol('')).toBeNull();
    expect(nyelvAzonosito('swift')?.nev).toBe('Swift');
  });

  it('a beágyazott forrás a jegyzetben: bármely nyelv, #alcímmel és |mérettel is; sima link és ismeretlen kiterjesztés nem', () => {
    expect(BEAGYAZOTT_KOD.test('![[Fib.py]]')).toBe(true);
    expect(BEAGYAZOTT_KOD.test('szöveg ![[mappa/Fib.PY#sor|300]] szöveg')).toBe(true);
    expect(BEAGYAZOTT_KOD.test('![[Összeg.cpp]]')).toBe(true);
    expect(BEAGYAZOTT_KOD.test('[[Fib.py]] csak link')).toBe(false);
    expect(BEAGYAZOTT_KOD.test('![[Fib.rb]]')).toBe(false);
    expect(BEAGYAZOTT_KOD.test('![[kep.png]]')).toBe(false);
    expect(elsoBeagyazottKod('# F\n\n![[mappa/Fib.py#x|3]]\n![[B.cpp]]')).toBe('mappa/Fib.py');
    expect(elsoBeagyazottKod('semmi')).toBeNull();
  });
});

describe('a motor-választás', () => {
  it('a .cpp és a .cpp-t beágyazó jegyzet a C36a motoron marad; minden más forrás az általánoson', () => {
    expect(motorForras('a/b.cpp')).toBe('cpp');
    expect(motorForras('a/b.CPP')).toBe('cpp');
    expect(motorForras('a/b.cc')).toBe('kod');
    expect(motorForras('a/b.c')).toBe('kod');
    expect(motorForras('a/b.py')).toBe('kod');
    expect(motorForras(null)).toBe('cpp'); // ismeretlen: a régi viselkedés
    expect(motorUt('Info/Feladat.md')).toBe('cpp');
    expect(motorUt('x.go')).toBe('kod');
  });

  it('a jegyzet nyelve az első beágyazott forrás szerint (ahogy a core is választ)', () => {
    expect(jegyzetNyelve('![[A.py]]\n![[B.cpp]]')).toMatchObject({ forras: 'A.py', motor: 'kod', nyelv: { azonosito: 'python' } });
    expect(jegyzetNyelve('![[B.cpp]]')).toMatchObject({ motor: 'cpp', nyelv: { azonosito: 'cpp' } });
    expect(jegyzetNyelve('nincs beágyazás')).toBeNull();
  });

  it('a core kod.-előtagos hibakódja rövid alakra, a régi kód változatlan', () => {
    expect(rovidKod('kod.nincs_eszkozlanc')).toBe('nincs_eszkozlanc');
    expect(rovidKod('tobbertelmu')).toBe('tobbertelmu');
    expect(rovidKod(undefined)).toBeNull();
    expect(rovidKod('')).toBeNull();
  });
});

describe('az eszközlánc-állapot', () => {
  let keresek: string[];
  const NYELVEK = [
    { azonosito: 'cpp', nev: 'C++', kiterjesztesek: ['.cpp'], motor: 'cpp', nativ: true, eszkozlanc: 'beagyazott', kalibracios_kulcs: 'kod', ai_modok: [], modok: ['gyors', 'hibakereso'],
      telepites_tipp: 'Install the portable LLVM: bin/mos cpp telepit --igen', elerheto: true, eszkozok: [{ nev: 'clang++', ok: true }], hiba: null },
    { azonosito: 'java', nev: 'Java', kiterjesztesek: ['.java'], motor: 'nyelv', nativ: false, eszkozlanc: 'rendszer', kalibracios_kulcs: 'kod_java', ai_modok: [], modok: ['gyors'],
      telepites_tipp: 'Install a JDK (17 or newer) and set its path in Settings, or put javac/java on PATH.', elerheto: false,
      eszkozok: [{ nev: 'javac', ok: false }, { nev: 'java', ok: false }],
      hiba: { kod: 'kod.nincs_eszkozlanc', param: { nyelv: 'Java', hianyzo: 'javac, java', tipp: 'Install a JDK.' }, uzenet: 'No Java toolchain (missing: javac, java). Install a JDK.' } },
    { azonosito: 'go', nev: 'Go', kiterjesztesek: ['.go'], motor: 'nyelv', nativ: true, eszkozlanc: 'rendszer', kalibracios_kulcs: 'kod_go', ai_modok: [], modok: ['gyors'],
      telepites_tipp: 'Install Go and set its path in Settings, or put go on PATH.', elerheto: false, eszkozok: [{ nev: 'go', ok: false }], hiba: null },
  ];

  beforeEach(() => {
    keresek = [];
    vi.stubGlobal('fetch', async (url: string) => {
      keresek.push(url);
      if (url.startsWith('/api/kod/nyelvek')) return valasz(200, { nyelvek: NYELVEK });
      return valasz(404, { hiba: 'nincs' });
    });
  });
  afterEach(() => vi.unstubAllGlobals());

  it('betöltés után nyelvenként elérhető / hiányzik, a hiányzó eszközökkel', async () => {
    const k = new KodNyelvek();
    expect(k.elerheto('java')).toBeNull(); // még nem ismert
    await k.betolt();
    expect(keresek).toEqual(['/api/kod/nyelvek']);
    expect(k.elerheto('cpp')).toBe(true);
    expect(k.elerheto('java')).toBe(false);
    expect(k.elerheto('nincs')).toBeNull();
    expect(k.hianyzo('java')).toEqual(['javac', 'java']);
    expect(k.teendo('cpp')).toBeNull();
  });

  it('a teendő a core kod.* hibakódjának mondata; hibakód nélkül a telepítési tipp', async () => {
    const k = new KodNyelvek();
    await k.betolt();
    expect(k.teendo('java')).toBe('No Java toolchain (missing: javac, java). Install a JDK.');
    expect(k.teendo('go')).toBe('Install Go and set its path in Settings, or put go on PATH.');
  });

  it('az újraellenőrzés a core gyorsítótárát megkerüli (?frissit=1); egyszerre egy kérés fut', async () => {
    const k = new KodNyelvek();
    const a = k.betolt(true);
    const b = k.betolt(true);
    await Promise.all([a, b]);
    expect(keresek).toEqual(['/api/kod/nyelvek?frissit=1']);
    expect(k.folyamatban).toBe(false);
    k.kellLista(); // van lista: nem kér újra
    expect(keresek).toHaveLength(1);
  });

  it('ha a core nem válaszol: hiba az állapotban, lista nélkül; a következő betöltés javít', async () => {
    let jo = false;
    let hivas = 0;
    vi.stubGlobal('fetch', async () => (hivas++, jo ? valasz(200, { nyelvek: NYELVEK }) : valasz(503, { hiba: 'The code engine does not answer: x', kod: 'kod.motor_nem_valaszol' })));
    const k = new KodNyelvek();
    k.kellLista();
    await vi.waitFor(() => expect(k.folyamatban).toBe(false));
    expect(k.lista).toBeNull();
    expect(k.hiba).toContain('does not answer');
    expect(k.elerheto('cpp')).toBeNull();
    k.kellLista(); // a hibás válasz után a kód-fül nem kérdez újra magától (nincs kérés-hurok)
    k.kellLista();
    await Promise.resolve();
    expect(hivas).toBe(1);
    jo = true;
    await k.betolt(true);
    expect(k.hiba).toBeNull();
    expect(k.elerheto('cpp')).toBe(true);
  });
});
