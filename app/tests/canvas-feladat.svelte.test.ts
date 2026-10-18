// 09-canvas-01: a szövegkártya feladat-jelölőnégyzete a kártya szövegét írja (bájthű foltozás, egy visszavonható lépés);
// csak olvasható, elavult és ütköző állapotban nem ír, és helyreállító szöveget ad.
import { describe, expect, it } from 'vitest';
import { beallit, fajl, fireEvent, hazi, iras, kartya, nyit, node, UT, utolso, vaszon, waitFor } from './canvas-seged.svelte';
import { szerkesztok } from '../src/szerkeszto/szerkesztok.svelte';
import { ertesitesek } from '../src/lib/ertesites/ertesites.svelte';

beallit();

const SZOVEG = 'Plan\\n- [ ] first\\n- [x] second\\n- [ ] third';
const EREDETI = fajl(
  [`{"id":"t1","type":"text","text":"${SZOVEG}","x":0,"y":0,"width":300,"height":200,"extra":{"keep":[1,2]}}`, node('t2', {}, 400, 0)],
  ['{"id":"e1","fromNode":"t1","toNode":"t2"}'],
);

const jelolok = (c: ReturnType<typeof nyit>) => [...kartya(c, 't1').querySelectorAll<HTMLInputElement>('input.feladat-jelolo')];

async function kesz(c: ReturnType<typeof nyit>): Promise<HTMLInputElement[]> {
  await vaszon(c);
  return await waitFor(() => {
    const j = jelolok(c);
    if (j.length !== 3) throw new Error('tasks not rendered');
    return j;
  });
}

describe('09-canvas-01: feladat-jelölőnégyzet a szövegkártyában', () => {
  it('a pipálás a kártya szövegét írja: csak a jelölő karaktere változik a fájlban, a többi bájt marad', async () => {
    const c = nyit(EREDETI);
    const [elso] = await kesz(c);
    expect(elso.checked).toBe(false);
    expect(elso.disabled).toBe(false);
    elso.click();
    await iras(1);
    expect(utolso()).toBe(EREDETI.replace('- [ ] first', '- [x] first'));
    expect(JSON.parse(utolso()).nodes[0].extra).toEqual({ keep: [1, 2] });
    expect(JSON.parse(utolso()).nodes[0].text).toBe('Plan\n- [x] first\n- [x] second\n- [ ] third');
  });

  it('a kipipált jelölő visszakapcsolása is ír', async () => {
    const c = nyit(EREDETI);
    const j = await kesz(c);
    expect(j[1].checked).toBe(true);
    j[1].click();
    await iras(1);
    expect(utolso()).toBe(EREDETI.replace('- [x] second', '- [ ] second'));
  });

  it('egy lépés: ⌘Z bájtra az eredetit adja, ⇧⌘Z újra beírja; a kártya újrarajzolva követi', async () => {
    const c = nyit(EREDETI);
    const v = await vaszon(c);
    const [elso] = await kesz(c);
    elso.click();
    await iras(1);
    await fireEvent.keyDown(v, { key: 'z', metaKey: true });
    await iras(2);
    expect(utolso()).toBe(EREDETI);
    await waitFor(() => expect(jelolok(c)[0].checked).toBe(false));
    await fireEvent.keyDown(v, { key: 'z', metaKey: true, shiftKey: true });
    await iras(3);
    expect(utolso()).toBe(EREDETI.replace('- [ ] first', '- [x] first'));
    await waitFor(() => expect(jelolok(c)[0].checked).toBe(true));
  });

  it('a pipálás a kártya állapotát nem a képernyőn hagyja: újrarajzolás után a megírt állapot áll', async () => {
    const c = nyit(EREDETI);
    const [elso] = await kesz(c);
    elso.click();
    await iras(1);
    await waitFor(() => expect(jelolok(c)[0].checked).toBe(true));
    expect(jelolok(c)[0].dataset.allapot ?? kartya(c, 't1').querySelector('li.feladat')?.getAttribute('data-allapot')).toBeTruthy();
  });

  it('csak olvasható canvasban (hibás bájtok) a jelölő le van tiltva, és a tooltip megmondja, mit kell tenni', async () => {
    // vegyes sorvégű fájl: a dokumentum csak olvasható; a nézet így is rajzol
    const vegyes = EREDETI.replace('\n\t"edges"', '\r\n\t"edges"');
    const c = nyit(vegyes);
    const j = await kesz(c);
    expect(j.every((x) => x.disabled)).toBe(true);
    expect(j[0].title).toMatch(/read-only/i);
    j[0].click();
    await new Promise((r) => setTimeout(r, 50));
    expect(hazi.putSzam).toBe(0);
  });

  it('elavult kártya: ha a jelölő már nem ott áll, nincs írás, a jelölő visszaáll, és a figyelmeztetés megmondja a teendőt', async () => {
    const c = nyit(EREDETI);
    const j = await kesz(c);
    // a szöveg a rajzolás óta módosult (más nézet / külső változás), de a DOM még a régi: a jelölő pozíciója elavult
    const forras = szerkesztok.dokumentumok.kap(UT)!;
    const mostani = forras.szoveg.toString();
    expect(mostani).toBe(EREDETI);
    j[0].dataset.jelolo = '3'; // olyan pozíció, ahol nincs jelölő
    j[0].click();
    await waitFor(() => expect(ertesitesek.lista.length).toBeGreaterThan(0));
    expect(hazi.putSzam).toBe(0);
    expect(j[0].checked).toBe(false);
    const e = ertesitesek.lista.at(-1)!;
    expect(e.szint).toBe('figyelmeztetes');
    expect(e.szoveg).toMatch(/tick the task again/i);
  });

  it('ütközés: a lemezen közben más változat lett → nincs felülírás, a jelölő visszaáll, a szöveg a feloldást kéri', async () => {
    const c = nyit(EREDETI);
    const j = await kesz(c);
    hazi.utkozes = true;
    j[2].click();
    await waitFor(() => expect(hazi.putSzam).toBeGreaterThan(0), { timeout: 4000 });
    await waitFor(() => expect(c.container.querySelector('.jel.hiba')?.textContent).toMatch(/Ütközés/), { timeout: 4000 });
    expect(hazi.lemez.get(UT)).toBe(EREDETI);
    expect(hazi.irasok).toEqual([]);
    // a következő pipálás az ütköző dokumentumra: elutasítva, helyreállító szöveggel
    const j2 = jelolok(c);
    j2[0].click();
    await waitFor(() => expect(ertesitesek.lista.some((e) => /conflict/i.test(e.szoveg))).toBe(true));
    expect(jelolok(c)[0].checked).toBe(false);
  });
});
