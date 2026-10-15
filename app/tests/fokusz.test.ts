import { afterEach, describe, expect, it } from 'vitest';
import { csapda, fokuszVisszaallit, regioLep, utolsoFokuszKovet } from '../src/lib/fokusz/fokusz';

function tab(shift = false) {
  const e = new KeyboardEvent('keydown', { key: 'Tab', shiftKey: shift, bubbles: true, cancelable: true });
  document.activeElement?.dispatchEvent(e);
  return e;
}

afterEach(() => {
  document.body.innerHTML = '';
});

describe('fókuszcsapda', () => {
  it('a Tab körbejár a rétegben, és bezáráskor a fókusz a megnyitóra tér vissza', async () => {
    document.body.innerHTML = `<button id="nyito">nyit</button><div id="reteg"><input id="a"><button id="b">b</button></div>`;
    const nyito = document.getElementById('nyito')!;
    nyito.focus();
    const reteg = document.getElementById('reteg')!;
    const akcio = csapda(reteg, nyito);
    document.getElementById('b')!.focus();
    expect(tab().defaultPrevented).toBe(true);
    expect(document.activeElement?.id).toBe('a');
    expect(tab(true).defaultPrevented).toBe(true);
    expect(document.activeElement?.id).toBe('b');
    akcio.destroy();
    await Promise.resolve();
    expect(document.activeElement).toBe(nyito);
  });
});

describe('régióváltás (F6)', () => {
  it('körbe a régiók között, a jelölt fókuszcélra', () => {
    document.body.innerHTML = `
      <nav data-regio="oldalsav"><button id="o">o</button></nav>
      <main data-regio="munkaterulet"><button id="x">x</button><div id="nezet" tabindex="-1" data-regio-fokusz></div></main>
      <aside data-regio="jobb" inert><button id="j">j</button></aside>
      <footer data-regio="allapotsor"><button id="s">s</button></footer>`;
    regioLep(1);
    expect(document.activeElement?.id).toBe('o');
    regioLep(1);
    expect(document.activeElement?.id).toBe('nezet');
    regioLep(1);
    expect(document.activeElement?.id).toBe('s'); // a rejtett (inert) jobb panel kimarad
    regioLep(1);
    expect(document.activeElement?.id).toBe('o');
    regioLep(-1);
    expect(document.activeElement?.id).toBe('s');
  });
});

// A kézi kör F3-ja (C10.7): a „Manifold elrejtése” és a visszahozás után a héj a WKWebView-t teszi first
// responderré, és a lapon a `fokuszVisszaallit` adja vissza a fókuszt (a szerkesztőnek, a gyorskeresőnek).
describe('fókusz a visszahozás után', () => {
  it('elveszett fókusznál az utolsó fókuszált elem kapja vissza; ha van fókusz, nem nyúl hozzá', () => {
    document.body.innerHTML = `<main data-regio="munkaterulet"><button id="ful">fül</button><div id="szerk" contenteditable="true"></div></main><input id="mas">`;
    const le = utolsoFokuszKovet();
    const szerk = document.getElementById('szerk')!;
    szerk.focus();
    szerk.blur();
    expect(document.activeElement).toBe(document.body);
    expect(fokuszVisszaallit()).toBe(true);
    expect(document.activeElement).toBe(szerk);
    const mas = document.getElementById('mas')!;
    mas.focus();
    expect(fokuszVisszaallit()).toBe(false);
    expect(document.activeElement).toBe(mas);
    le();
  });

  it('ha az utolsó elem már nincs a lapon, a munkaterület kapja', () => {
    document.body.innerHTML = `<main data-regio="munkaterulet"><button id="ful">fül</button></main><input id="kereso">`;
    const le = utolsoFokuszKovet();
    const kereso = document.getElementById('kereso')!;
    kereso.focus();
    kereso.remove();
    expect(fokuszVisszaallit()).toBe(true);
    expect(document.activeElement?.id).toBe('ful');
    le();
  });
});
