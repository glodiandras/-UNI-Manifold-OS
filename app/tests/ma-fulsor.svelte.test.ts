// A „Ma” nézet-fül a fülsorban (C15): a címe „Ma” (nem „Új fül”), a gráf mellett is a saját címét viseli.

import { cleanup, render, screen } from '@testing-library/svelte';
import { afterEach, describe, expect, it } from 'vitest';
import Fulsor from '../src/hej/Fulsor.svelte';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';

afterEach(() => {
  cleanup();
  document.body.textContent = '';
});

describe('fülsor', () => {
  it('a Ma-fül és a gráf-fül saját címet kap, az üres fül „Új fül”', () => {
    const felulet = new Felulet({});
    const m = felulet.munkaterulet;
    m.megnyitNezet('ma');
    m.megnyitNezet('graf', { mod: 'globalis' });
    m.ujFul();
    const context = new Map<unknown, unknown>([[KORNYEZET_KULCS, { felulet, fajlok: new VaultFajlok(), kapcsolat: new CoreKapcsolat('ws://x') }]]);
    render(Fulsor, { context, props: { panel: m.aktivPanel, aktivPanel: true, nezetId: 'nezet' } });
    expect(screen.getAllByRole('tab').map((t) => t.textContent?.trim())).toEqual(['Manifold', 'Gráf', 'Új fül']);
  });
});
