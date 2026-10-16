// 04-embeds-02: a Privacy › Network szakasz kimondja, hogy külső kép csak kattintásra töltődik le (D3).
import { cleanup, render, screen } from '@testing-library/svelte';
import { afterEach, beforeEach, expect, it } from 'vitest';
import BeallitasokAblak from '../src/beallitasok/Beallitasok.svelte';
import { beallitasAblak } from '../src/beallitasok/allapot.svelte';
import { BeallitasokTar, beallitasok } from '../src/lib/beallitasok/allapot.svelte';
import { alapBeallitasok } from '../src/lib/beallitasok/tipusok';
import { nyelv } from '../src/lib/i18n';

beforeEach(() => { nyelv.beallit('en'); });
afterEach(() => { cleanup(); beallitasok.adat = null; nyelv.beallit('hu'); beallitasAblak.szakasz = 'altalanos'; });

it('a Network adatvédelmi szakasz jelzi: külső kép csak kattintásra, https-en, a csatolmány-mappába', () => {
  const tar = new BeallitasokTar();
  tar.fogad({ verzio: 1, rev: 'r1', ertek: alapBeallitasok(), munkater: { id: 'synthetic', nev: 'Synthetic', vault: '/synthetic/vault' }, setup_szukseges: false, ujrainditas: [] });
  beallitasAblak.szakasz = 'halozat';
  render(BeallitasokAblak, { props: { tar, onbezar: () => {}, onsetup: () => {}, onrendszer: () => {} } });
  expect(screen.getByText(/External images in notes are never loaded automatically/)).toBeTruthy();
});
