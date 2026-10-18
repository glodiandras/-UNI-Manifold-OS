// A canvas fül nézete (C14) jsdom-ban, ál-core-ral: betöltés, húzás → a mentett szövegben csak az x/y literál
// változik, visszavonás → bájtra az eredeti, törlés az éllel, csak-olvasható hibás JSON, ütközés. A WebKit-
// megjelenést a képernyőképes kör és a kézi lista méri; ez a komponens kötéseit védi.

import { EditorView } from '@codemirror/view';
import { cleanup, fireEvent, render, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { canvasok } from '../src/canvas/aktiv.svelte';
import CanvasFul from '../src/canvas/CanvasFul.svelte';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import type { Ful } from '../src/lib/elrendezes/munkaterulet.svelte';
import { KORNYEZET_KULCS } from '../src/lib/kornyezet';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';
import { kilepesMentes, szerkesztesLezar } from '../src/szerkeszto';
import { sorVege } from '../src/szerkeszto/dokumentum/mentesSor';
import { gepiIrasFigyel } from '../src/szerkeszto/gepiIras';
import { szerkesztok } from '../src/szerkeszto/szerkesztok.svelte';

const UT = 'Térképek/Próba.canvas';
const EREDETI =
  '{\n\t"nodes":[\n' +
  '\t\t{"id":"aaaaaaaaaaaaaaaa","type":"text","text":"Első **kártya**","x":0,"y":0,"width":260,"height":60},\n' +
  '\t\t{"id":"bbbbbbbbbbbbbbbb","type":"text","text":"Második","x":400,"y":0,"width":260,"height":60,"color":"4"}\n' +
  '\t],\n\t"edges":[\n' +
  '\t\t{"id":"eeeeeeeeeeeeeeee","fromNode":"aaaaaaaaaaaaaaaa","fromSide":"right","toNode":"bbbbbbbbbbbbbbbb","toSide":"left","label":"tovább"}\n' +
  '\t]\n}';

interface Iras {
  ut: string;
  tartalom: string;
  alap: string;
  elso: boolean;
  pillanat: boolean;
}

let lemez: Map<string, string>;
let irasok: Iras[];
let utkozes = false;
/** a PUT 400-at ad (a core elutasítja a canvast) */
let elutasit = false;
let putSzam = 0;

const hash = (s: string) => `h${s.length}:${[...s].reduce((h, c) => (h * 31 + c.charCodeAt(0)) | 0, 7)}`;
const valasz = (kod: number, adat: unknown) =>
  new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });

beforeEach(() => {
  lemez = new Map([[UT, EREDETI]]);
  irasok = [];
  utkozes = false;
  elutasit = false;
  putSzam = 0;
  // a `bind:clientWidth` ResizeObservert kér (a jsdom-ban nincs; a méret itt úgyis 0)
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    const u = new URL(url, 'http://127.0.0.1/');
    if (u.pathname === '/api/vault/fajl' && (!init?.method || init.method === 'GET')) {
      const ut = u.searchParams.get('ut')!;
      const t = lemez.get(ut);
      if (t === undefined) return valasz(404, { hiba: 'nincs ilyen fájl' });
      return valasz(200, { ut, tartalom: t, hash: hash(t), jel: '', mtime: 0, kodolas_hiba: false });
    }
    if (u.pathname === '/api/vault/fajl' && init?.method === 'PUT') {
      const k = JSON.parse(String(init.body)) as Iras;
      const regi = lemez.get(k.ut)!;
      putSzam++;
      if (elutasit) return valasz(400, { hiba: 'a canvas nem érvényes JSON Canvas, nem mentődött' });
      if (utkozes || k.alap !== hash(regi)) return valasz(409, { hiba: 'ütközés', utkozes: true, hash: hash(regi) });
      irasok.push(k);
      lemez.set(k.ut, k.tartalom);
      return valasz(200, { ok: true, ut: k.ut, hash: hash(k.tartalom), jel: '', uzenet: 'mentve', pillanat: null, elotte: null, git: true });
    }
    return valasz(404, { hiba: `nincs: ${u.pathname}` });
  });
});

afterEach(async () => {
  cleanup();
  await sorVege(); // a bezáráskori lezárás (pillanatkép) még a tesztnek szóló `fetch`-csonkkal fusson le, ne szivárogjon tovább
  vi.unstubAllGlobals();
  for (const d of szerkesztok.dokumentumok.lista()) szerkesztok.dokumentumok.eldob(d.ut);
});

function nyit(szoveg = EREDETI) {
  lemez.set(UT, szoveg);
  const ful = $state<Ful>({ id: 'f1', ut: UT, nezet: { canvas: { tx: 0, ty: 0, z: 1 } } });
  const kornyezet = { felulet: new Felulet({}), fajlok: new VaultFajlok(), kapcsolat: new CoreKapcsolat('ws://127.0.0.1:1/ws') };
  return render(CanvasFul, {
    props: { ful, info: undefined, aktiv: true },
    context: new Map([[KORNYEZET_KULCS, kornyezet]]),
  });
}

async function vaszon(c: ReturnType<typeof nyit>): Promise<HTMLElement> {
  return await waitFor(() => {
    const v = c.container.querySelector<HTMLElement>('.vaszon');
    expect(v).not.toBeNull();
    return v!;
  });
}

const kartya = (c: ReturnType<typeof nyit>, id: string) =>
  c.container.querySelector<HTMLElement>(`.kartya[data-id="${id.repeat(16).slice(0, 16)}"]`)!;

describe('canvas-nézet', () => {
  it('betöltés: a kártyák a helyükön, az él címkével, a színes kártya jelölve', async () => {
    const c = nyit();
    await vaszon(c);
    const a = kartya(c, 'a');
    const b = kartya(c, 'b');
    expect(a.style.left).toBe('0px');
    expect(b.style.left).toBe('400px');
    expect(b.classList.contains('szines')).toBe(true);
    expect(c.container.querySelector('.el-cimke')?.textContent?.trim()).toBe('tovább');
    expect(c.container.querySelectorAll('path.el-vonal').length).toBe(1);
    expect(canvasok.aktiv?.ut).toBe(UT);
    expect(irasok).toEqual([]);
  });

  it('inaktív panelben a canvas nem marad a ⌘P canvas-parancsainak és a ⌘S-nek a célja (T166)', async () => {
    const c = nyit();
    await vaszon(c);
    expect(canvasok.aktiv?.ut).toBe(UT);
    expect(szerkesztok.masNezet).not.toBeNull();
    await c.rerender({ aktiv: false });
    expect(canvasok.aktiv).toBeNull();
    expect(szerkesztok.masNezet).toBeNull();
    await c.rerender({ aktiv: true });
    expect(canvasok.aktiv?.ut).toBe(UT);
  });

  it('húzás: a mentett szövegben csak az x/y literál változik; ⌘Z után bájtra az eredeti', async () => {
    const c = nyit();
    const v = await vaszon(c);
    const a = kartya(c, 'a');
    await fireEvent.pointerDown(a, { button: 0, clientX: 10, clientY: 10, pointerId: 1 });
    await fireEvent.pointerMove(v, { clientX: 40, clientY: 25, pointerId: 1 });
    await fireEvent.pointerMove(v, { clientX: 52, clientY: 33, pointerId: 1 });
    await fireEvent.pointerUp(v, { clientX: 52, clientY: 33, pointerId: 1 });
    await waitFor(() => expect(irasok.length).toBe(1), { timeout: 3000 });
    // rácsra igazítva (20): +42 → 40, +23 → 20
    expect(irasok[0].tartalom).toBe(EREDETI.replace('"x":0,"y":0,"width":260', '"x":40,"y":20,"width":260'));
    expect(irasok[0].elso).toBe(true);
    await fireEvent.keyDown(v, { key: 'z', metaKey: true });
    await waitFor(() => expect(irasok.length).toBe(2), { timeout: 3000 });
    expect(irasok[1].tartalom).toBe(EREDETI);
  });

  it('kijelölés és törlés: a node az élével megy, a többi bájt marad', async () => {
    const c = nyit();
    const v = await vaszon(c);
    const b = kartya(c, 'b');
    await fireEvent.pointerDown(b, { button: 0, clientX: 450, clientY: 10, pointerId: 1 });
    await fireEvent.pointerUp(v, { clientX: 450, clientY: 10, pointerId: 1 });
    expect(b.classList.contains('kijelolt')).toBe(true);
    await fireEvent.keyDown(v, { key: 'Delete' });
    await waitFor(() => expect(irasok.length).toBe(1), { timeout: 3000 });
    expect(irasok[0].tartalom).toBe(
      '{\n\t"nodes":[\n\t\t{"id":"aaaaaaaaaaaaaaaa","type":"text","text":"Első **kártya**","x":0,"y":0,"width":260,"height":60}\n\t],\n\t"edges":[]\n}',
    );
  });

  it('nyilakkal mozgatás a rács lépésével, Esc törli a kijelölést', async () => {
    const c = nyit();
    const v = await vaszon(c);
    const a = kartya(c, 'a');
    await fireEvent.focus(a);
    expect(a.classList.contains('kijelolt')).toBe(true);
    await fireEvent.keyDown(v, { key: 'ArrowRight', shiftKey: true });
    await waitFor(() => expect(irasok.length).toBe(1), { timeout: 3000 });
    expect(irasok[0].tartalom).toContain('"x":100,"y":0,"width":260');
    await fireEvent.keyDown(v, { key: 'Escape' });
    expect(a.classList.contains('kijelolt')).toBe(false);
  });

  it('hibás JSON: csak olvasható, a hiba helye látszik, írás nincs', async () => {
    const c = nyit('{\n\t"nodes":[\n\t\t{"id":"a",}\n\t]\n}');
    await waitFor(() => expect(c.container.querySelector('.olvasasi-hiba')).not.toBeNull());
    expect(c.container.querySelector('.olvasasi-hiba')!.textContent).toMatch(/nem érvényes JSON.*line 3, column/);
    expect(c.container.querySelector('.jel.figyelmeztetes')?.textContent).toBe('Csak olvasható');
    expect(c.container.querySelector('.vaszon')).toBeNull();
    expect(irasok).toEqual([]);
  });

  it('ütközés: a mentés 409-et kap → a fejléc jelzi, és a fájl nem íródik felül', async () => {
    const c = nyit();
    const v = await vaszon(c);
    utkozes = true;
    await fireEvent.focus(kartya(c, 'a'));
    await fireEvent.keyDown(v, { key: 'ArrowDown' });
    await waitFor(() => expect(c.container.querySelector('.jel.hiba')?.textContent).toMatch(/Ütközés/), { timeout: 3000 });
    expect(lemez.get(UT)).toBe(EREDETI);
  });
});

// ---------------------------------------------------------------------- C29.7a: adatvesztési leletek

/** Szövegkártya szerkesztése: kijelölés + ↩, utána gépelés a kártya CodeMirror-szerkesztőjébe (mentetlen szöveg). */
async function kartyaSzerkesztes(c: ReturnType<typeof nyit>, id = 'a'): Promise<EditorView> {
  const v = await vaszon(c);
  const k = kartya(c, id);
  await fireEvent.focus(k);
  await fireEvent.keyDown(v, { key: 'Enter' });
  const e = await waitFor(() => {
    const x = k.querySelector<HTMLElement>('.cm-editor');
    expect(x).not.toBeNull();
    return x!;
  });
  const ev = EditorView.findFromDOM(e)!;
  ev.dispatch({ changes: { from: ev.state.doc.length, insert: ' + új' } });
  return ev;
}

const UJ_SZOVEG = '"text":"Első **kártya** + új"';

describe('a nyitott szövegkártya-szerkesztő szövege nem vész el (T004)', () => {
  it('kilépéskor (⌘Q): a héj mentés-jelentése előtt a szöveg a lemezre kerül, a jelentés rendben', async () => {
    const c = nyit();
    await kartyaSzerkesztes(c);
    expect(lemez.get(UT)).toBe(EREDETI); // a szerkesztés alatt még nincs a dokumentumban
    const j = await kilepesMentes();
    expect(j).toEqual({ ok: true, mentetlen: [] });
    expect(lemez.get(UT)).toContain(UJ_SZOVEG);
  });

  it('az ablak elrejtésekor a szöveg a lemezre kerül', async () => {
    const c = nyit();
    await kartyaSzerkesztes(c);
    await szerkesztesLezar();
    expect(lemez.get(UT)).toContain(UJ_SZOVEG);
  });

  it('⌘S: ment, és a kártya-szerkesztő nyitva marad (a szöveg tovább szerkeszthető)', async () => {
    const c = nyit();
    const ev = await kartyaSzerkesztes(c);
    await szerkesztok.masNezet!.mentes();
    expect(lemez.get(UT)).toContain(UJ_SZOVEG);
    expect(kartya(c, 'a').querySelector('.cm-editor')).not.toBeNull();
    expect(EditorView.findFromDOM(kartya(c, 'a').querySelector<HTMLElement>('.cm-editor')!)).toBe(ev); // ugyanaz a szerkesztő
    ev.dispatch({ changes: { from: ev.state.doc.length, insert: '!' } });
    await szerkesztesLezar();
    expect(lemez.get(UT)).toContain('"text":"Első **kártya** + új!"');
  });

  it('a fül bezárásakor a szöveg mentődik', async () => {
    const c = nyit();
    await kartyaSzerkesztes(c);
    c.unmount();
    await waitFor(() => expect(lemez.get(UT)).toContain(UJ_SZOVEG), { timeout: 3000 });
  });
});

describe('a nyitott szövegkártya a core felé „mentetlen” (28(c), C29.7b)', () => {
  it('kártya-szerkesztés alatt a dokumentum mentetlen (a gép nem ír bele, WS-jelentés is), zárása után nem', async () => {
    const kapcsolat = new CoreKapcsolat('ws://127.0.0.1:1/ws');
    const kuldve: { tipus: string; utak: string[] }[] = [];
    vi.spyOn(kapcsolat, 'kuld').mockImplementation((u) => (kuldve.push(u as never), true));
    const le = gepiIrasFigyel(kapcsolat, szerkesztok.dokumentumok);
    try {
      const c = nyit();
      expect(szerkesztok.dokumentumok.mentetlenUtak()).toEqual([]);
      const ev = await kartyaSzerkesztes(c);
      expect(lemez.get(UT)).toBe(EREDETI); // a szöveg még nincs a dokumentumban — mégis mentetlen
      expect(szerkesztok.dokumentumok.mentetlenUtak()).toEqual([UT]);
      await waitFor(() => expect(kuldve.at(-1)).toEqual({ tipus: 'mentetlen', utak: [UT] }));
      await fireEvent.keyDown(ev.contentDOM, { key: 'Escape' }); // a kártya lezárása: a szöveg a dokumentumba kerül
      await waitFor(() => expect(kartya(c, 'a').querySelector('.cm-editor')).toBeNull());
      await waitFor(() => expect(kuldve.at(-1)?.utak).not.toContain(UT), { timeout: 3000 }); // a mentés lezajlása után tiszta
      expect(lemez.get(UT)).toContain(UJ_SZOVEG);
    } finally {
      le();
    }
  });

  it('a kártya zárása után (mentés előtt is) a jelzés megszűnik, ha a dokumentum tiszta', async () => {
    const c = nyit();
    await vaszon(c);
    const k = kartya(c, 'a');
    await fireEvent.focus(k);
    await fireEvent.keyDown(c.container.querySelector<HTMLElement>('.vaszon')!, { key: 'Enter' });
    await waitFor(() => expect(szerkesztok.dokumentumok.mentetlenUtak()).toEqual([UT]));
    await fireEvent.keyDown(k.querySelector<HTMLElement>('.cm-content')!, { key: 'Escape' }); // változtatás nélkül zárul
    await waitFor(() => expect(szerkesztok.dokumentumok.mentetlenUtak()).toEqual([]));
  });
});

describe('a canvas mentési hibái (T030)', () => {
  it('a 400 tartós hiba: nincs újrapróba, és az „A lemezen lévő betöltése” kiút visszaadja a lemez állapotát', async () => {
    const c = nyit();
    const v = await vaszon(c);
    elutasit = true;
    await fireEvent.focus(kartya(c, 'a'));
    await fireEvent.keyDown(v, { key: 'ArrowDown' });
    const gomb = await waitFor(
      () => {
        const g = [...c.container.querySelectorAll('button')].find((b) => b.textContent?.includes('A lemezen lévő betöltése'));
        expect(g).toBeTruthy();
        return g!;
      },
      { timeout: 4000 },
    );
    const eddig = putSzam;
    await new Promise((r) => setTimeout(r, 2600)); // az első újrapróba ideje (2 s) elmúlt
    expect(putSzam).toBe(eddig);
    elutasit = false;
    await fireEvent.click(gomb);
    await waitFor(() => expect(c.container.querySelector('.jel.hiba')).toBeNull(), { timeout: 3000 });
    expect(kartya(c, 'a').style.top).toBe('0px'); // a lemezen lévő változat áll
    expect(lemez.get(UT)).toBe(EREDETI);
  });

  it('az „Összevetés” canvasnál ellenőrzi a JSON-t: érvénytelen szöveg nem menthető', async () => {
    const c = nyit();
    const v = await vaszon(c);
    utkozes = true;
    await fireEvent.focus(kartya(c, 'a'));
    await fireEvent.keyDown(v, { key: 'ArrowDown' });
    const osszevetes = (await c.findByRole('button', { name: /Összevetés/ })) as HTMLButtonElement;
    await waitFor(() => expect(osszevetes.disabled).toBe(false), { timeout: 3000 });
    await fireEvent.click(osszevetes);
    const b = await waitFor(
      () => {
        const e = document.querySelectorAll<HTMLElement>('.merge .cm-editor');
        expect(e.length).toBe(2);
        return EditorView.findFromDOM(e[1])!;
      },
      { timeout: 3000 },
    );
    const ment = (await c.findByRole('button', { name: /összefésült szöveg mentése/ })) as HTMLButtonElement;
    expect(ment.disabled).toBe(false); // az induló szöveg érvényes
    b.dispatch({ changes: { from: 0, to: b.state.doc.length, insert: '{ "nodes": [ }' } });
    await waitFor(() => expect(ment.disabled).toBe(true));
    expect(document.body.textContent).toMatch(/nem érvényes JSON/);
  });
});

describe('húzás közben külső változás (T113)', () => {
  it('a húzás megszakad: a külső módosítás nem íródik felül a régi modellel', async () => {
    const c = nyit();
    const v = await vaszon(c);
    const a = kartya(c, 'a');
    await fireEvent.pointerDown(a, { button: 0, clientX: 10, clientY: 10, pointerId: 1 });
    await fireEvent.pointerMove(v, { clientX: 40, clientY: 25, pointerId: 1 });
    lemez.set(UT, EREDETI.replace('Második', 'Kívülről'));
    const dok = szerkesztok.dokumentumok.kap(UT)!;
    await dok.kulsoValtozas(); // tiszta dokumentum: csendes újratöltés
    await fireEvent.pointerMove(v, { clientX: 52, clientY: 33, pointerId: 1 });
    await fireEvent.pointerUp(v, { clientX: 52, clientY: 33, pointerId: 1 });
    await dok.ment({ kenyszer: true });
    expect(lemez.get(UT)).toContain('Kívülről');
    expect(irasok.every((i) => i.tartalom.includes('Kívülről'))).toBe(true);
    expect(a.style.left).toBe('0px'); // a húzás nem érvényesült
  });
});
