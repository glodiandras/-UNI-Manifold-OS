// 80(a): a grafikon csak gombra készül — a ⌘P „Grafikonok beírása ebbe a jegyzetbe” parancs a `grafikon_beiras` (kézi) feladatot indítja.
import { describe, expect, it, vi } from 'vitest';
import { grafikonJegyzet, grafikonokBeirasa, grafikonParancsok } from '../src/szerkeszto/renderelok/plot/beiras';

describe('grafikonok beírása (80(a))', () => {
  it('a feladat a megnyitott jegyzet útjával indul, előtte ment', async () => {
    const sor: string[] = [];
    const keres = vi.fn(async (ut: string, o: { torzs?: unknown } = {}) => {
      sor.push(ut);
      expect(o.torzs).toEqual({ tipus: 'grafikon_beiras', parameterek: { utak: ['M10/a.md'] } });
      return { id: 'F-1' };
    });
    const mentes = vi.fn(async () => void sor.push('mentes'));
    expect(await grafikonokBeirasa('M10/a.md', mentes, keres as never)).toBe(true);
    expect(sor).toEqual(['mentes', '/api/feladatok']);
  });

  it('hibánál nem hamis siker', async () => {
    const keres = vi.fn(async () => {
      throw new Error('foglalt');
    });
    expect(await grafikonokBeirasa('M10/a.md', async () => {}, keres as never)).toBe(false);
  });

  it('a parancs csak tartalmi jegyzetnél érhető el', () => {
    expect(grafikonJegyzet('M10/a.md')).toBe(true);
    expect(grafikonJegyzet('ATTCHMNTS - cards/x.md')).toBe(false);
    expect(grafikonJegyzet('M10/.rejtett/x.md')).toBe(false);
    expect(grafikonJegyzet('M10/k.pdf')).toBe(false);
    let aktiv: { ut: string; mentes: () => Promise<void> } | null = null;
    const [p] = grafikonParancsok(() => aktiv);
    expect(p.id).toBe('grafikon.beiras');
    expect(p.elerheto?.()).toBe(false);
    aktiv = { ut: 'M10/a.md', mentes: async () => {} };
    expect(p.elerheto?.()).toBe(true);
  });
});
