import { afterEach, describe, expect, it, vi } from 'vitest';
import { OlvasoKereses } from '../src/szerkeszto/olvaso/kereses';

const keresok: OlvasoKereses[] = [];
afterEach(() => { keresok.splice(0).forEach(k => k.leallit()); document.body.replaceChildren(); vi.restoreAllMocks(); });
function keres(html: string) {
  const gyoker = document.createElement('article'); gyoker.innerHTML = html; document.body.appendChild(gyoker);
  const valtozott = vi.fn();
  const k = new OlvasoKereses(gyoker, valtozott); keresok.push(k);
  return { gyoker, k, valtozott };
}

describe('F11 Reading find', () => {
  it('a formázáson átnyúló szöveg egy találat, a DOM és a teljes szöveg bezáráskor megmarad', () => {
    const { gyoker, k, valtozott } = keres('<p>A red <strong>fox</strong> runs.</p><p>RED FOX</p>');
    const eredeti = gyoker.innerHTML;
    k.keres('red fox');
    expect(valtozott).toHaveBeenLastCalledWith({ osszes: 2, aktualis: 1 });
    expect([...gyoker.querySelectorAll('.olvaso-talalat-aktiv')].map(e => e.textContent).join('')).toBe('red fox');
    k.lep(1); expect(valtozott).toHaveBeenLastCalledWith({ osszes: 2, aktualis: 2 });
    k.lep(1); expect(valtozott).toHaveBeenLastCalledWith({ osszes: 2, aktualis: 1 });
    k.lep(-1); expect(valtozott).toHaveBeenLastCalledWith({ osszes: 2, aktualis: 2 });
    k.keres(''); expect(gyoker.innerHTML).toBe(eredeti);
  });

  it('a kis/nagybetű opció, Unicode és regexnek látszó egyszerű szöveg pontos', () => {
    const { k, valtozott } = keres('<p>Árvíz árvíz a.b axb [.*] 👩‍💻</p>');
    k.keres('Árvíz'); expect(valtozott).toHaveBeenLastCalledWith({ osszes: 2, aktualis: 1 });
    k.keres('Árvíz', true); expect(valtozott).toHaveBeenLastCalledWith({ osszes: 1, aktualis: 1 });
    k.keres('a.b'); expect(valtozott).toHaveBeenLastCalledWith({ osszes: 1, aktualis: 1 });
    k.keres('[.*]'); expect(valtozott).toHaveBeenLastCalledWith({ osszes: 1, aktualis: 1 });
    k.keres('👩‍💻'); expect(valtozott).toHaveBeenLastCalledWith({ osszes: 1, aktualis: 1 });
  });

  it('a bekezdések és <br> között nem keletkezik hamis összeillesztett találat; a vezérlők saját DOM-ja érintetlen', () => {
    const { gyoker, k, valtozott } = keres('<p>one<br>two</p><p>three</p><button>one</button><input value="one"><div class="beagyazas-kviz"><p>one</p></div><div class="beagyazas-osszefoglalo"><p>one</p></div>');
    k.keres('onetwo'); expect(valtozott).toHaveBeenLastCalledWith({ osszes: 0, aktualis: 0 });
    k.keres('one'); expect(valtozott).toHaveBeenLastCalledWith({ osszes: 1, aktualis: 1 });
    expect(gyoker.querySelector('button mark')).toBeNull();
    expect(gyoker.querySelector('.beagyazas-kviz mark')).toBeNull();
    expect(gyoker.querySelector('.beagyazas-osszefoglalo mark')).toBeNull();
  });

  it('minden találat navigálható nagy jegyzetben is, a DOM-jelölés korlátos marad', () => {
    const { gyoker, k, valtozott } = keres(Array.from({ length: 501 }, (_, i) => `<p>match ${i}</p>`).join(''));
    k.keres('match'); expect(valtozott).toHaveBeenLastCalledWith({ osszes: 501, aktualis: 1 });
    expect(gyoker.querySelectorAll('mark').length).toBeLessThanOrEqual(120);
    k.lep(-1); expect(valtozott).toHaveBeenLastCalledWith({ osszes: 501, aktualis: 501 });
    expect(gyoker.lastElementChild!.querySelector('.olvaso-talalat-aktiv')).not.toBeNull();
    expect(gyoker.querySelectorAll('mark').length).toBeLessThanOrEqual(120);
  });

  it('később érkező tartalomra frissül; a saját jelölései nem indítanak visszacsatolt keresést', async () => {
    const { gyoker, k, valtozott } = keres('<p>find</p>');
    k.keres('find');
    const hivott = valtozott.mock.calls.length;
    await new Promise(r => setTimeout(r, 90)); expect(valtozott).toHaveBeenCalledTimes(hivott);
    const p = document.createElement('p'); p.textContent = 'find'; gyoker.appendChild(p);
    await vi.waitFor(() => expect(valtozott).toHaveBeenLastCalledWith({ osszes: 2, aktualis: 1 }));
    k.leallit(); expect(gyoker.querySelector('mark')).toBeNull();
    const darab = valtozott.mock.calls.length;
    p.textContent = 'find again'; await new Promise(r => setTimeout(r, 80));
    expect(valtozott).toHaveBeenCalledTimes(darab);
  });

  it('a zárt callout tartalma megnyílik a találathoz ugráskor', () => {
    const { gyoker, k } = keres('<details><summary>Callout</summary><p>Hidden result</p></details>');
    k.keres('result'); expect(gyoker.querySelector('details')!.open).toBe(true);
  });
});
