// Az eltűnt fájlok jelzése (javítókör D, 14. lelet): a gyanúsan zsugorodott fájllista (elérhetetlen vault, részleges index)
// nem üríti ki a nyitott füleket.

import { describe, expect, it, vi } from 'vitest';
import { VaultFajlok, type FajlInfo } from '../src/lib/vault/fajlok.svelte';

const fajl = (ut: string): FajlInfo => ({ ut, tipus: 'md', meret: 1, mtime: 1 });
const sok = (n: number) => Array.from({ length: n }, (_, i) => fajl(`M/${i}.md`));

describe('eltűnt fájlok', () => {
  it('a néhány eltűnt fájl jelződik (a fülei üresre válthatnak)', () => {
    const f = new VaultFajlok();
    const eltunt = vi.fn();
    f.eltuntek = eltunt;
    f.beallit(sok(100));
    f.beallit(sok(100).slice(2));
    expect(eltunt).toHaveBeenCalledExactlyOnceWith(new Set(['M/0.md', 'M/1.md']));
  });

  it('a nagy zsugorodás gyanús: nincs jelzés', () => {
    const f = new VaultFajlok();
    const eltunt = vi.fn();
    f.eltuntek = eltunt;
    f.beallit(sok(100));
    f.beallit(sok(100).slice(60)); // 60 eltűnt a 100-ból
    f.beallit([]); // üres lista
    expect(eltunt).not.toHaveBeenCalled();
  });

  it('elérhetetlen vault mellett nincs jelzés', () => {
    const f = new VaultFajlok();
    const eltunt = vi.fn();
    f.eltuntek = eltunt;
    f.beallit(sok(10));
    f.index = { kesz: true, elerheto: false };
    f.beallit(sok(10).slice(1));
    expect(eltunt).not.toHaveBeenCalled();
    f.index = { kesz: true, elerheto: true };
    f.beallit(sok(10).slice(2));
    expect(eltunt).toHaveBeenCalledExactlyOnceWith(new Set(['M/1.md']));
  });
});
