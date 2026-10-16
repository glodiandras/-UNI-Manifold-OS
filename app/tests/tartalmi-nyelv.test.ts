import { afterEach, describe, expect, it } from 'vitest';
import { nyelv } from '../src/lib/i18n';
import { tartalmiNyelv } from '../src/lib/munkater/nyelv.svelte';
import { kiserokBetolt } from '../src/szerkeszto/tulajdonsagok/api';
import type { kerdez } from '../src/lib/core/api';

afterEach(() => {
  tartalmiNyelv.beallit('');
  nyelv.beallit('hu');
});

describe('a workspace tartalmi nyelve független a felülettől', () => {
  it('a core munkatérnyelve tölti, miközben a felület angol marad', async () => {
    nyelv.beallit('en');
    const keres = (async () => ({ nyelv: 'hu' })) as typeof kerdez;
    await kiserokBetolt(keres);
    expect(tartalmiNyelv.kod).toBe('hu');
    expect(nyelv.kod).toBe('en');
  });

  it('a címke kanonikus; hibás vagy hiányzó érték nem örökli az angol UI-nyelvet', () => {
    tartalmiNyelv.beallit('EN-gb');
    expect(tartalmiNyelv.kod).toBe('en-GB');
    for (const rossz of ['../hu', 'hu_HU', 42, null, undefined, 'x'.repeat(100)]) {
      tartalmiNyelv.beallit(rossz);
      expect(tartalmiNyelv.kod).toBe('');
    }
  });
});
