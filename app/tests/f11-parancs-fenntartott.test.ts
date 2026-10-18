// 13-palette-02: a fenntartott (natív menü) akkordok egy forrásból — a shell menüjéből — származnak, a validátor mindet tiltja, és a
// türelmes betöltés egy rossz kötés miatt nem dobja el az egész kiosztást (13-palette-01 importja is ezt használja).
import { describe, expect, it } from 'vitest';
import { RESERVED_CHORDS, fenntartott, normalizalLeiras } from '../src/lib/parancsok/billentyuk';
import { Regiszter } from '../src/lib/parancsok/regiszter';
import tabla from '../../config/billentyuk.json';

const SWIFT = import.meta.glob('../../shell/Sources/AppController.swift', { query: '?raw', import: 'default', eager: true }) as Record<string, string>;

/** A Swift menü `keyEquivalent`-jei és módosítói: önálló (a Python-generátortól független) kinyerő. */
function swiftAkkordok(forras: string): string[] {
  const sorok = forras.split('\n');
  const ki: string[] = [];
  sorok.forEach((sor, i) => {
    if (sor.trim().startsWith('//')) return;
    const m = /keyEquivalent:\s*"([^"\\]+)"/.exec(sor);
    if (!m) return;
    const nev = /^\s*(?:let|var)\s+(\w+)\s*=/.exec(sor)?.[1];
    let modok = ['Mod'];
    if (nev) {
      for (const k of sorok.slice(i + 1, i + 8)) {
        const mk = new RegExp(`${nev}\\.keyEquivalentModifierMask\\s*=\\s*\\[([^\\]]*)\\]`).exec(k);
        if (mk) {
          const m2: Record<string, string> = { command: 'Mod', option: 'Alt', shift: 'Shift', control: 'Ctrl' };
          modok = mk[1].split(',').map((x) => m2[x.trim().replace(/^\./, '')]).filter(Boolean);
        }
      }
    }
    ki.push(normalizalLeiras([...modok, m[1]].join('+')));
  });
  return ki;
}

const regiszter = () => {
  const r = new Regiszter();
  r.regisztral({ id: 'proba.egy', nev: 'Egy', billentyu: 'Mod+Alt+9', futtat: () => {} });
  r.regisztral({ id: 'proba.ketto', nev: 'Kettő', futtat: () => {} });
  r.regisztral({ id: 'beallitasok.megnyit', nev: 'Settings', billentyu: 'Mod+,', futtat: () => {} });
  return r;
};

describe('fenntartott akkordok: egy forrás', () => {
  it('a RESERVED_CHORDS pontosan a shell menüjének akkordjai (a menü új akkordja a listában is megjelenik)', () => {
    const forras = Object.values(SWIFT)[0];
    expect(forras, 'AppController.swift nem olvasható').toBeTruthy();
    const menu = swiftAkkordok(forras);
    expect(menu.length).toBeGreaterThanOrEqual(12);
    expect([...new Set(menu)].sort()).toEqual(Object.keys(RESERVED_CHORDS).sort());
  });

  it('tartalmazza a szabványos szerkesztő- és ablak-akkordokat, a tulajdonos pedig csak a beállítások parancs', () => {
    for (const a of ['Mod+c', 'Mod+v', 'Mod+x', 'Mod+z', 'Mod+Shift+z', 'Mod+a', 'Mod+h', 'Mod+Alt+h', 'Mod+m', 'Mod+q', 'Mod+Ctrl+f', 'Mod+Shift+o', 'Mod+,']) {
      expect(RESERVED_CHORDS[a], a).toBeTruthy();
      expect(RESERVED_CHORDS[a].ok).toBeTruthy();
    }
    expect(RESERVED_CHORDS['Mod+,'].tulajdonos).toBe('beallitasok.megnyit');
    expect(fenntartott('Mod+,', 'beallitasok.megnyit')).toBe(false);
    expect(fenntartott('Mod+,', 'x.y')).toBe(true);
    expect(fenntartott('Mod+c')).toBe(true);
    expect(fenntartott('Mod+Alt+9')).toBe(false);
  });

  it('a regiszter alapértelmezései (config/billentyuk.json "alap") nem natív akkordok és nem ütköznek', () => {
    const alap = tabla.alap as Record<string, string>;
    for (const [id, akkord] of Object.entries(alap)) expect(fenntartott(akkord, id), `${id}: ${akkord}`).toBe(false);
    expect(new Set(Object.values(alap)).size).toBe(Object.keys(alap).length);
  });
});

describe('a validátor a teljes natív listát tiltja', () => {
  it.each(Object.keys(RESERVED_CHORDS).filter((a) => a !== 'Mod+,'))('%s nem rendelhető parancshoz', (akkord) => {
    expect(() => regiszter().billentyuketEllenoriz({ 'proba.ketto': akkord })).toThrow(/reserved|foglalt/i);
    expect(() => regiszter().billentyuketAlkalmaz({ 'proba.ketto': akkord })).toThrow();
  });

  it('a Mod+, csak a beállítások parancsé; más alakú írás ugyanazt az akkordot jelenti', () => {
    const r = regiszter();
    expect(() => r.billentyuketEllenoriz({ 'proba.ketto': 'cmd+,' })).toThrow();
    expect(() => r.billentyuketEllenoriz({ 'proba.ketto': 'Meta+Shift+Z' })).toThrow();
    expect(() => r.billentyuketEllenoriz({ 'beallitasok.megnyit': 'Mod+,' })).not.toThrow();
    expect(() => r.billentyuketEllenoriz({ 'beallitasok.megnyit': 'Mod+Alt+9' })).toThrow();
    expect(() => r.billentyuketEllenoriz({ 'proba.ketto': 'Mod+Alt+8' })).not.toThrow();
  });
});

describe('türelmes betöltés (tárolt vagy importált kiosztás)', () => {
  it('az érvénytelen, fenntartott és ütköző kötést kihagyja és jelenti, a többit alkalmazza', () => {
    const r = new Regiszter();
    r.regisztral({ id: 'proba.a', nev: 'A', billentyu: 'Mod+Alt+1', futtat: () => {} });
    r.regisztral({ id: 'proba.b', nev: 'B', billentyu: 'Mod+Alt+2', futtat: () => {} });
    r.regisztral({ id: 'proba.c', nev: 'C', futtat: () => {} });
    r.regisztral({ id: 'proba.d', nev: 'D', futtat: () => {} });
    const elutasitott = r.billentyuketAlkalmazTurelmesen({
      'proba.c': 'Mod+c', // natív
      'proba.d': 'Mod+Alt+7', // jó
      'proba.a': 'Mod+Alt+2', // a B alapértelmezésével ütközik
      'proba.x': 'garbage', // érvénytelen
    });
    expect(elutasitott.map((e) => e.id).sort()).toEqual(['proba.a', 'proba.c', 'proba.x']);
    expect(elutasitott.every((e) => !!e.ok)).toBe(true);
    expect(r.akkordhoz('Mod+Alt+7')?.id).toBe('proba.d');
    expect(r.akkordhoz('Mod+Alt+1')?.id).toBe('proba.a'); // a rossz kötés helyett az alapértelmezés marad
    expect(r.akkordhoz('Mod+Alt+2')?.id).toBe('proba.b');
    expect(r.akkordhoz('Mod+c')).toBeUndefined();
  });

  it('két parancs akkordcseréje elfogadott (sorrendfüggetlenül)', () => {
    const r = new Regiszter();
    r.regisztral({ id: 'proba.a', nev: 'A', billentyu: 'Mod+Alt+1', futtat: () => {} });
    r.regisztral({ id: 'proba.b', nev: 'B', billentyu: 'Mod+Alt+2', futtat: () => {} });
    expect(r.billentyuketAlkalmazTurelmesen({ 'proba.a': 'Mod+Alt+2', 'proba.b': 'Mod+Alt+1' })).toEqual([]);
    expect(r.akkordhoz('Mod+Alt+1')?.id).toBe('proba.b');
    expect(r.akkordhoz('Mod+Alt+2')?.id).toBe('proba.a');
  });
});
