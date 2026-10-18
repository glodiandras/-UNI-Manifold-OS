// A nézetillesztés valódi canvas-kötései: ⇧1 az egész vásznat, ⇧2 a kijelölést mutatja. A kamera változása nem ír fájlt.
import { describe, expect, it } from 'vitest';
import type { Nezet } from '../src/canvas/geometria';
import { beallit, fajl, fireEvent, hazi, kartya, node, nyit, vaszon, waitFor } from './canvas-seged.svelte';

beallit();

const EREDETI = fajl(
  [node('a', {}, 0, 0), node('b', {}, 400, 0), node('c', {}, 6000, 3000)],
  ['{"id":"ab","fromNode":"a","toNode":"b"}'],
);

const transzformacio = (c: ReturnType<typeof nyit>) => c.container.querySelector<HTMLElement>('.vilag')!.style.transform;
const kamera = (c: ReturnType<typeof nyit>) => c.ful.nezet?.canvas as Nezet | undefined;

describe('09-canvas-11: nagyítás a kijelölésre', () => {
  it('a kis kártyát 2×-ig nagyítja, középre teszi és eltárolja a kamerát; az egész vászon margóval fér el', async () => {
    const c = nyit(EREDETI);
    const v = await vaszon(c);
    await fireEvent.focus(kartya(c, 'a'));
    await fireEvent.keyDown(v, { key: '2', code: 'Digit2', shiftKey: true });
    expect(transzformacio(c)).toBe('translate(340px, 340px) scale(2)');
    await waitFor(() => expect(kamera(c)).toEqual({ tx: 340, ty: 340, z: 2 }));
    await fireEvent.keyDown(v, { key: '1', shiftKey: true });
    await waitFor(() => expect(kamera(c)?.z).toBe(0.1764));
    // A teljes 6260×3060-as befoglaló szélessége 1104 pixelre illeszkedik a két 48 pixeles margó között.
    expect(kamera(c)?.tx).toBe(48);
    expect(hazi.putSzam).toBe(0);
    expect(hazi.lemez.get(c.ut)).toBe(EREDETI);
  });

  it('kijelölt élnél mindkét végpontot mutatja, a távoli harmadik kártyát kihagyja', async () => {
    const c = nyit(EREDETI);
    const v = await vaszon(c);
    const el = c.container.querySelector<SVGElement>('[data-el="ab"]')!;
    await fireEvent.pointerDown(el, { button: 0, clientX: 330, clientY: 30, pointerId: 1 });
    await fireEvent.keyDown(v, { key: '@', code: 'Digit2', shiftKey: true });
    const z = 1104 / 660;
    expect(transzformacio(c)).toBe(`translate(48px, ${400 - 30 * z}px) scale(${z})`);
    expect(hazi.putSzam).toBe(0);
  });

  it('kijelölés nélkül ⇧2 nem változtatja vagy menti a kamerát; ⇧1 kis vásznat legfeljebb 1×-ig nagyít', async () => {
    const c = nyit(fajl([node('a')]), { nezet: { tx: 20, ty: 30, z: 0.5 } });
    const v = await vaszon(c);
    const eredeti = transzformacio(c);
    await fireEvent.keyDown(v, { key: '2', code: 'Digit2', shiftKey: true });
    expect(transzformacio(c)).toBe(eredeti);
    expect(kamera(c)).toEqual({ tx: 20, ty: 30, z: 0.5 });
    await fireEvent.keyDown(v, { key: '1', shiftKey: true });
    expect(transzformacio(c)).toBe('translate(470px, 370px) scale(1)');
    expect(hazi.putSzam).toBe(0);
  });
});
