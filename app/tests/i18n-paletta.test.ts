// A parancspaletta az aktív nyelven (F4): a parancsnév és a kategória a megjelenítéskor fordítódik (az id és a regisztráció
// kulcsa változatlan), a szűrés és a rendezés a megjelenített nyelven fut, a nyelvváltás frissíti a listát.
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { flushSync, tick } from 'svelte';
import { afterEach, describe, expect, it } from 'vitest';
import Paletta from '../src/atfedes/Paletta.svelte';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { nyelv, szotarKiegeszit } from '../src/lib/i18n';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { regiszter } from '../src/lib/parancsok/regiszter';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';

const kornyezet = () => {
  const felulet = new Felulet({});
  const context = new Map<unknown, unknown>([[KORNYEZET_KULCS, { felulet, fajlok: new VaultFajlok(), kapcsolat: new CoreKapcsolat('ws://x') }]]);
  return { felulet, context };
};
const opciok = () => screen.getAllByRole('option').map((o) => o.textContent?.replace(/\s+/g, ' ').trim());

const visszavon: (() => void)[] = [];
afterEach(() => {
  cleanup();
  while (visszavon.length) visszavon.pop()!();
  nyelv.beallit('hu');
});

function elokeszit() {
  visszavon.push(
    szotarKiegeszit('en', {
      Parancspaletta: 'Command palette',
      'Parancs keresése': 'Search commands',
      'Parancs keresése…': 'Search commands…',
      'Nincs ilyen parancs: „{lekerdezes}”': 'No command matches “{lekerdezes}”',
      választás: 'select',
      futtatás: 'run',
      bezárás: 'close',
      'Kártyák ebből': 'Cards from this',
      Tanulás: 'Study',
      'Oldalsáv elrejtése': 'Hide sidebar',
      Nézet: 'View',
    }),
  );
  const le = regiszter.regisztralMind([
    { id: 'i18nproba.kartya', nev: 'Kártyák ebből', kategoria: 'Tanulás', futtat: () => {} },
    { id: 'i18nproba.oldalsav', nev: 'Oldalsáv elrejtése', kategoria: 'Nézet', billentyu: 'Mod+Shift+7', futtat: () => {} },
  ]);
  visszavon.push(le);
}

describe('parancspaletta két nyelven', () => {
  it('magyarul a kulcsok jelennek meg (identitás); a feliratok magyarok', () => {
    elokeszit();
    const { context } = kornyezet();
    render(Paletta, { context });
    expect(screen.getByRole('combobox', { name: 'Parancs keresése' })).toBeTruthy();
    expect(screen.getByRole('dialog', { name: 'Parancspaletta' })).toBeTruthy();
    expect(opciok().some((o) => o?.includes('Tanulás') && o.includes('Kártyák ebből'))).toBe(true);
    expect(screen.getByText('választás', { exact: false })).toBeTruthy();
  });

  it('angolul a név, a kategória, a placeholder, a lábléc és az üres állapot fordított; a keresés a fordított néven fut', async () => {
    elokeszit();
    nyelv.beallit('en');
    const { context } = kornyezet();
    render(Paletta, { context });
    const mezo = screen.getByRole('combobox', { name: 'Search commands' });
    expect(screen.getByRole('dialog', { name: 'Command palette' })).toBeTruthy();
    expect(mezo.getAttribute('placeholder')).toBe('Search commands…');
    expect(opciok().some((o) => o?.includes('Study') && o.includes('Cards from this'))).toBe(true);
    expect(opciok().some((o) => o?.includes('Hide sidebar') && o.includes('⇧⌘7'))).toBe(true);
    expect(screen.getByText('select', { exact: false })).toBeTruthy();
    await fireEvent.input(mezo, { target: { value: 'cards' } });
    expect(opciok()[0]).toContain('Cards from this');
    await fireEvent.input(mezo, { target: { value: 'zzzzqq' } });
    expect(screen.getByText('No command matches “zzzzqq”')).toBeTruthy();
  });

  it('a nyelvváltás újrarajzolja a nyitott palettát; a regisztráció id-ja és kulcsa nem változik', async () => {
    elokeszit();
    const { context } = kornyezet();
    render(Paletta, { context });
    expect(opciok().some((o) => o?.includes('Kártyák ebből'))).toBe(true);
    nyelv.beallit('en');
    flushSync();
    await tick();
    expect(opciok().some((o) => o?.includes('Cards from this'))).toBe(true);
    expect(opciok().some((o) => o?.includes('Kártyák ebből'))).toBe(false);
    expect(regiszter.kap('i18nproba.kartya')?.nev).toBe('Kártyák ebből');
  });
});
