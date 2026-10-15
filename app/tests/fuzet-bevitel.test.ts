// C21 (3. pont): a füzetfotók felületi bevitele — feltöltés egy csoportba, a lánc indítása (aktív jegyzet módban `cel`-lal), és a
// szerkesztő képejtése már nem indítja a láncot.
import { describe, expect, it, vi } from 'vitest';
import { EditorState } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import { fuzetFeltolt, fuzetKep, fuzetParancsok } from '../src/lib/fuzet/fuzet';
import beallitasForras from '../src/szerkeszto/beallitas.ts?raw';

const fajl = (nev: string) => new File([new Uint8Array([0xff, 0xd8, 1, 2, 3])], nev, { type: 'image/jpeg' });

describe('füzetfotók bevitele (C21)', () => {
  it('feltöltés egy csoportba, utána a lánc a cél jegyzettel', async () => {
    const hivasok: [string, unknown][] = [];
    const keres = vi.fn(async (ut: string, o: { torzs?: unknown } = {}) => {
      hivasok.push([ut, o.torzs]);
      return ut === '/api/fuzet/bejovo' ? { csoport: 'cs1' } : { id: 'F-1' };
    });
    const r = await fuzetFeltolt([fajl('IMG_1.JPG'), fajl('jegyzet.txt'), fajl('IMG_2.heic')], 'M10/a.md', keres as never);
    expect(r).toEqual({ id: 'F-1', feltoltve: 2 });
    expect(hivasok.map((h) => h[0])).toEqual(['/api/fuzet/bejovo', '/api/fuzet/bejovo', '/api/feladatok']);
    expect(hivasok[0][1]).toMatchObject({ nev: 'IMG_1.JPG', adat: btoa(String.fromCharCode(0xff, 0xd8, 1, 2, 3)) });
    expect(hivasok[0][1]).not.toHaveProperty('csoport');
    expect(hivasok[1][1]).toMatchObject({ nev: 'IMG_2.heic', csoport: 'cs1' });
    expect(hivasok[2][1]).toEqual({ tipus: 'fuzet_lanc', parameterek: { csoport: 'cs1', cel: 'M10/a.md' } });
    expect(await fuzetFeltolt([fajl('a.txt')], null, keres as never)).toBeNull();
  });

  it('a szerkesztő a behúzott képet nem küldi a füzetláncra (80(a): AI csak gombra)', () => {
    const feltolt = vi.fn(async () => null);
    const v = new EditorView({ state: EditorState.create({ doc: 'x' }) });
    const e = new Event('drop', { bubbles: true, cancelable: true }) as DragEvent;
    Object.defineProperty(e, 'dataTransfer', { value: { files: [fajl('IMG_1.jpg')] } });
    v.contentDOM.dispatchEvent(e);
    expect(feltolt).not.toHaveBeenCalled();
    expect(beallitasForras).not.toMatch(/fuzetBehuzas|fuzetFeltolt/);                 // a bekötés kikerült a szerkesztő beállításából
    v.destroy();
  });

  it('a parancsok', () => {
    const p = fuzetParancsok(() => null);
    expect(p.map((x) => x.id)).toEqual(['fuzet.feldolgoz', 'fuzet.hozzaad', 'fuzet.aktivba', 'fuzet.ellenoriz']);
    expect(p[2].elerheto?.()).toBe(false);
    expect(fuzetParancsok(() => 'a.md')[2].elerheto?.()).toBe(true);
    expect(fuzetKep({ name: 'X.HEIC' }) && !fuzetKep({ name: 'x.gif' })).toBe(true);
  });
});
