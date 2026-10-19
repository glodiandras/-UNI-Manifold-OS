// CX-005: a fájlcím szerkesztése (átnevezés, a H1 független), a fülön belüli előzmény (⌥⌘←/→), a bezárt fül
// újranyitása (⇧⌘T) és az „Osztás jobbra” új akkordja (⇧⌘2) a billentyűkezelőn át. Az akkordok ütközés-próbája:
// `billentyu-utkozes.test.ts`.

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const atnev = vi.hoisted(() => ({
  terv: vi.fn(),
  vegrehajt: vi.fn(),
  ertesites: vi.fn(),
}));
vi.mock('../src/szerkeszto/linkek/atnevezes', () => ({
  atnevezesTerv: atnev.terv,
  atnevezesVegrehajt: atnev.vegrehajt,
  atnevezesErtesites: atnev.ertesites,
}));

import { alapParancsok } from '../src/alapParancsok';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { kezel } from '../src/lib/parancsok/kezelo';
import { Regiszter } from '../src/lib/parancsok/regiszter';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';
import FajlCim from '../src/szerkeszto/FajlCim.svelte';
import { szerkesztok } from '../src/szerkeszto/szerkesztok.svelte';

afterEach(() => cleanup());

describe('FajlCim (CX-005)', () => {
  let felulet: Felulet;
  beforeEach(() => {
    atnev.terv.mockReset().mockResolvedValue({ ok: true, blokkolok: [], terv_hash: 'h1' });
    atnev.vegrehajt.mockReset().mockResolvedValue({ ok: true });
    atnev.ertesites.mockReset();
    vi.spyOn(szerkesztok.dokumentumok, 'mindLezar').mockResolvedValue(undefined);
    felulet = new Felulet({});
  });

  function megjelenit(ut = 'Mappa/Régi név.md', irhato = true) {
    const context = new Map<unknown, unknown>([
      [KORNYEZET_KULCS, { felulet, fajlok: new VaultFajlok(), kapcsolat: new CoreKapcsolat('ws://127.0.0.1:1/ws') }],
    ]);
    render(FajlCim, { props: { ut, irhato }, context });
    return screen.getByLabelText('Jegyzet fájlneve') as HTMLInputElement;
  }

  it('a mező a fájlnevet mutatja kiterjesztés nélkül; az Enter átnevezi a fájlt a mappáján belül', async () => {
    const mezo = megjelenit();
    expect(mezo.value).toBe('Régi név');
    await fireEvent.input(mezo, { target: { value: '  Új név  ' } });
    await fireEvent.keyDown(mezo, { key: 'Enter' });
    await fireEvent.blur(mezo);
    await waitFor(() => expect(atnev.vegrehajt).toHaveBeenCalledWith('Mappa/Régi név.md', 'Mappa/Új név.md', 'h1', expect.any(Function)));
    expect(atnev.terv).toHaveBeenCalledWith('Mappa/Régi név.md', 'Mappa/Új név.md');
    expect(szerkesztok.dokumentumok.mindLezar).toHaveBeenCalled(); // előbb minden mentetlen szerkesztés lezárul
    expect(atnev.ertesites).toHaveBeenCalledOnce();
  });

  it('a gyökérben álló fájl; a beírt .md nem duplázódik', async () => {
    const mezo = megjelenit('Jegyzet.md');
    await fireEvent.input(mezo, { target: { value: 'Másik.md' } });
    await fireEvent.blur(mezo);
    await waitFor(() => expect(atnev.terv).toHaveBeenCalledWith('Jegyzet.md', 'Másik.md'));
  });

  it('változatlan vagy üres név, és az Esc: nincs átnevezés, a mező visszaáll', async () => {
    const mezo = megjelenit();
    await fireEvent.blur(mezo);
    await fireEvent.input(mezo, { target: { value: '   ' } });
    await fireEvent.blur(mezo);
    expect(mezo.value).toBe('Régi név');
    await fireEvent.input(mezo, { target: { value: 'Elvetett' } });
    await fireEvent.keyDown(mezo, { key: 'Escape' });
    await fireEvent.blur(mezo);
    expect(mezo.value).toBe('Régi név');
    expect(atnev.terv).not.toHaveBeenCalled();
  });

  it('a blokkolt terv ikonos hibát mutat, a javítható név megmarad', async () => {
    atnev.terv.mockResolvedValue({ ok: false, blokkolok: ['A cél foglalt.'], terv_hash: '' });
    const mezo = megjelenit();
    await fireEvent.input(mezo, { target: { value: 'Foglalt' } });
    await fireEvent.blur(mezo);
    const hiba = await screen.findByRole('alert');
    expect(hiba.textContent).toContain('A cél foglalt.');
    expect(hiba.classList.contains('hiba')).toBe(true);
    expect(mezo.value).toBe('Foglalt');
    expect(atnev.vegrehajt).not.toHaveBeenCalled();
  });

  it('a nem írható dokumentumnál a mező tiltott', () => {
    expect(megjelenit('a.md', false).disabled).toBe(true);
  });
});

describe('navigáció és fülek a billentyűzetről (CX-005)', () => {
  function billentyu(key: string, code: string, mod: { meta?: boolean; alt?: boolean; shift?: boolean } = {}) {
    const e = new KeyboardEvent('keydown', { key, code, metaKey: !!mod.meta, altKey: !!mod.alt, shiftKey: !!mod.shift, bubbles: true, cancelable: true });
    document.body.dispatchEvent(e);
    return e;
  }

  function telep() {
    const reg = new Regiszter();
    const felulet = new Felulet({});
    const le = alapParancsok(reg, felulet);
    return { reg, felulet, m: felulet.munkaterulet, le };
  }

  it('⌥⌘← vissza, ⌥⌘→ előre a fül saját előzményében', () => {
    const { reg, m, le } = telep();
    m.megnyit('a.md');
    m.megnyit('b.md');
    expect(kezel(billentyu('ArrowLeft', 'ArrowLeft', { meta: true, alt: true }), reg)).toBe(true);
    expect(m.aktivFul?.ut).toBe('a.md');
    expect(kezel(billentyu('ArrowRight', 'ArrowRight', { meta: true, alt: true }), reg)).toBe(true);
    expect(m.aktivFul?.ut).toBe('b.md');
    // az előzmény a végén: a parancs nem csinál semmit (nem dob)
    kezel(billentyu('ArrowRight', 'ArrowRight', { meta: true, alt: true }), reg);
    expect(m.aktivFul?.ut).toBe('b.md');
    expect(m.aktivPanel.fulek).toHaveLength(1);
    le();
  });

  it('⇧⌘T a legutóbb bezárt fület a helyére nyitja; az üres fül nem kerül a listába', () => {
    const { reg, m, le } = telep();
    m.megnyit('a.md');
    m.megnyit('b.md', 'ujful');
    m.megnyit('c.md', 'ujful');
    m.aktival(m.aktivPanelId, m.aktivPanel.fulek[1].id);
    m.bezar();
    expect(m.aktivPanel.fulek.map((f) => f.ut)).toEqual(['a.md', 'c.md']);
    expect(kezel(billentyu('t', 'KeyT', { meta: true, shift: true }), reg)).toBe(true);
    expect(m.aktivPanel.fulek.map((f) => f.ut)).toEqual(['a.md', 'b.md', 'c.md']);
    expect(m.aktivFul?.ut).toBe('b.md');
    m.ujFul();
    m.bezar(); // üres fül
    kezel(billentyu('t', 'KeyT', { meta: true, shift: true }), reg);
    expect(m.aktivPanel.fulek.map((f) => f.ut)).toEqual(['a.md', 'b.md', 'c.md']); // nem jött vissza üres fül
    le();
  });

  it('a teljes alapparancs-készlet ütközés nélkül regisztrál', () => {
    const reg = new Regiszter();
    expect(() => alapParancsok(reg, new Felulet({}))()).not.toThrow();
  });

  it('⇧⌘2 jobbra oszt (a magyar kiosztáson a ⇧2 jele „"”: a számjegyet az event.code adja)', () => {
    const { reg, m, le } = telep();
    m.megnyit('a.md');
    expect(kezel(billentyu('"', 'Digit2', { meta: true, shift: true }), reg)).toBe(true);
    expect(m.panelek()).toHaveLength(2);
    // a régi akkord (⌥⌘→) már nem oszt, hanem előre navigál
    expect(reg.akkordhoz('Mod+Alt+ArrowRight')?.id).toBe('navigacio.elore');
    le();
  });
});
