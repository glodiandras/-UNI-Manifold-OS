import { afterEach, describe, expect, it, vi } from 'vitest';
import { belep } from '../src/lib/fokusz/hatokor';
import { ariaAlak, elemez, esemenybol, megjelenit, normalizalLeiras } from '../src/lib/parancsok/billentyuk';
import { kezel } from '../src/lib/parancsok/kezelo';
import { Regiszter } from '../src/lib/parancsok/regiszter';
import { ApiHiba } from '../src/lib/core/api';
import { ertesitesek } from '../src/lib/ertesites/ertesites.svelte';

function billentyu(init: KeyboardEventInit & { key: string; code?: string }, cel: EventTarget = document.body) {
  const e = new KeyboardEvent('keydown', { bubbles: true, cancelable: true, ...init });
  Object.defineProperty(e, 'target', { value: cel });
  return e;
}

describe('billentyűakkordok', () => {
  it('elemzés és egységes alak', () => {
    expect(elemez('Mod+Shift+M')).toEqual({ mod: true, ctrl: false, alt: false, shift: true, kulcs: 'm' });
    expect(normalizalLeiras('shift+mod+m')).toBe('Mod+Shift+m');
    expect(normalizalLeiras('Ctrl+Shift+Tab')).toBe('Ctrl+Shift+Tab');
    expect(() => elemez('Hyper+X')).toThrow();
  });

  it('megjelenítés macOS-jelekkel, ⌃⌥⇧⌘ sorrendben', () => {
    expect(megjelenit('Mod+Shift+M')).toBe('⇧⌘M');
    expect(megjelenit('Mod+Alt+ArrowRight')).toBe('⌥⌘→');
    expect(megjelenit('Ctrl+Tab')).toBe('⌃⇥');
    expect(ariaAlak('Mod+Shift+M')).toBe('Shift+Meta+M');
  });

  it('eseményből: betű a felirat szerint, szám a kód szerint, Option-betű a kódból', () => {
    expect(esemenybol(billentyu({ key: 'p', code: 'KeyP', metaKey: true }))?.kulcs).toBe('p');
    // magyar QWERTZ: a Z helyén az Y — a felirat számít
    expect(esemenybol(billentyu({ key: 'y', code: 'KeyZ', metaKey: true }))?.kulcs).toBe('y');
    expect(esemenybol(billentyu({ key: '"', code: 'Digit2', metaKey: true, shiftKey: true }))?.kulcs).toBe('2');
    expect(esemenybol(billentyu({ key: 'π', code: 'KeyP', altKey: true }))?.kulcs).toBe('p');
    expect(esemenybol(billentyu({ key: 'Meta', code: 'MetaLeft', metaKey: true }))).toBeNull();
  });
});

describe('regiszter', () => {
  it('regisztrál, listáz, futtat, leiratkozik', () => {
    const r = new Regiszter();
    const f = vi.fn();
    const le = r.regisztral({ id: 'proba.egy', nev: 'Egy', futtat: f });
    expect(r.lista().map((p) => p.id)).toEqual(['proba.egy']);
    expect(r.futtat('proba.egy')).toBe(true);
    expect(f).toHaveBeenCalledOnce();
    le();
    expect(r.lista()).toEqual([]);
    expect(r.futtat('proba.egy')).toBe(false);
  });

  it('ütköző azonosító és billentyű hiba; a hibás azonosító is', () => {
    const r = new Regiszter();
    r.regisztral({ id: 'a.b', nev: 'A', billentyu: 'Mod+K', futtat: () => {} });
    expect(() => r.regisztral({ id: 'a.b', nev: 'A2', futtat: () => {} })).toThrow(/már regisztrált/);
    expect(() => r.regisztral({ id: 'a.c', nev: 'C', billentyu: 'mod+k', futtat: () => {} })).toThrow(/foglalt/);
    expect(() => r.regisztral({ id: 'Rossz Id', nev: 'X', futtat: () => {} })).toThrow(/hibás/);
  });

  it('az elérhetetlen és a palettán kívüli parancs nem látszik', () => {
    const r = new Regiszter();
    r.regisztral({ id: 'a.rejtett', nev: 'R', palettaban: false, futtat: () => {} });
    r.regisztral({ id: 'a.tiltott', nev: 'T', elerheto: () => false, futtat: () => {} });
    r.regisztral({ id: 'a.hibas', nev: 'H', elerheto: () => { throw new Error('x'); }, futtat: () => {} });
    expect(r.lista()).toEqual([]);
    expect(r.futtat('a.tiltott')).toBe(false);
    expect(r.futtat('a.rejtett')).toBe(true);
  });

  it('futás után jelez (legutóbbiak), változáskor értesít', () => {
    const r = new Regiszter();
    const futott: string[] = [];
    r.futasUtan = (id) => futott.push(id);
    const valtozas = vi.fn();
    r.feliratkoz(valtozas);
    r.regisztral({ id: 'a.b', nev: 'A', futtat: () => {} });
    r.futtat('a.b');
    expect(futott).toEqual(['a.b']);
    expect(valtozas).toHaveBeenCalledOnce();
  });
});

describe('a parancs hibája', () => {
  it('az aszinkron és a szinkron hiba magyar hibaértesítést ad (nem csak konzolt)', async () => {
    const konzol = vi.spyOn(console, 'error').mockImplementation(() => {});
    try {
      ertesitesek.lista = [];
      const r = new Regiszter();
      r.regisztral({ id: 'a.async', nev: 'Aszinkron próba', futtat: async () => { throw new ApiHiba(500, 'a core belső hibája'); } });
      r.regisztral({ id: 'a.sync', nev: 'Szinkron próba', futtat: () => { throw new TypeError('Load failed'); } });
      expect(r.futtat('a.async')).toBe(true);
      await new Promise((k) => setTimeout(k, 0));
      expect(r.futtat('a.sync')).toBe(true);
      const hibak = ertesitesek.lista.filter((e) => e.szint === 'hiba').map((e) => [e.cim, e.szoveg]);
      expect(hibak).toEqual([
        ['A parancs nem sikerült: Aszinkron próba', 'a core belső hibája'],
        ['A parancs nem sikerült: Szinkron próba', 'A core nem érhető el (megszakadt a kapcsolat).'],
      ]);
    } finally {
      konzol.mockRestore();
      ertesitesek.lista = [];
    }
  });
});

describe('billentyűkezelő', () => {
  let ki: (() => void) | null = null;
  afterEach(() => {
    ki?.();
    ki = null;
  });

  it('a gyorsbillentyű futtatja a parancsot és elnyeli az eseményt', () => {
    const r = new Regiszter();
    const f = vi.fn();
    r.regisztral({ id: 'a.paletta', nev: 'P', billentyu: 'Mod+P', futtat: f });
    const e = billentyu({ key: 'p', code: 'KeyP', metaKey: true });
    expect(kezel(e, r)).toBe(true);
    expect(f).toHaveBeenCalledOnce();
    expect(e.defaultPrevented).toBe(true);
    expect(kezel(billentyu({ key: 'p', code: 'KeyP' }), r)).toBe(false);
  });

  it('szerkeszthető mezőben a módosító nélküli billentyű a gépelésé, a ⌘ nem', () => {
    const r = new Regiszter();
    const f = vi.fn();
    r.regisztral({ id: 'a.esc', nev: 'E', billentyu: 'Escape', futtat: f });
    r.regisztral({ id: 'a.p', nev: 'P', billentyu: 'Mod+P', futtat: f });
    const mezo = document.createElement('input');
    expect(kezel(billentyu({ key: 'Escape', code: 'Escape' }, mezo), r)).toBe(false);
    expect(kezel(billentyu({ key: 'p', code: 'KeyP', metaKey: true }, mezo), r)).toBe(true);
  });

  it('a `szerkesztoNyer` parancs billentyűje a szerkesztőben a CodeMirroré (⌥⌘↓), kívül és a palettából fut', () => {
    const r = new Regiszter();
    const oszt = vi.fn();
    r.regisztral({ id: 'panel.oszt-le', nev: 'Osztás lefelé', billentyu: 'Mod+Alt+ArrowDown', szerkesztoNyer: true, futtat: oszt });
    const cm = document.createElement('div');
    cm.className = 'cm-editor';
    const tartalom = document.createElement('div');
    tartalom.className = 'cm-content';
    tartalom.contentEditable = 'true';
    cm.append(tartalom);
    const e = billentyu({ key: 'ArrowDown', code: 'ArrowDown', metaKey: true, altKey: true }, tartalom);
    expect(kezel(e, r)).toBe(false);
    expect(e.defaultPrevented).toBe(false); // a CM megkapja
    expect(oszt).not.toHaveBeenCalled();
    expect(kezel(billentyu({ key: 'ArrowDown', code: 'ArrowDown', metaKey: true, altKey: true }), r)).toBe(true);
    expect(r.futtat('panel.oszt-le', 'paletta')).toBe(true);
    expect(oszt).toHaveBeenCalledTimes(2);
  });

  it('nyitott átfedés alatt csak az `atfedesben` parancs fut', () => {
    const r = new Regiszter();
    const sima = vi.fn();
    const atfedes = vi.fn();
    r.regisztral({ id: 'a.sima', nev: 'S', billentyu: 'Mod+W', futtat: sima });
    r.regisztral({ id: 'a.valto', nev: 'V', billentyu: 'Mod+O', atfedesben: true, futtat: atfedes });
    ki = belep('paletta');
    expect(kezel(billentyu({ key: 'w', code: 'KeyW', metaKey: true }), r)).toBe(false);
    expect(kezel(billentyu({ key: 'o', code: 'KeyO', metaKey: true }), r)).toBe(true);
    expect(sima).not.toHaveBeenCalled();
    expect(atfedes).toHaveBeenCalledOnce();
  });
});
