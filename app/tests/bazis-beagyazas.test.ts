// A Bases a jegyzetben (C12 7. lépés): az interaktív kódblokk-renderelő három visszafelé kompatibilis bővítése
// (regiszter, `RendereloWidget`, atomi tartomány), a ```` ```base ```` blokk, a `![[x.base#Nézet]]` beágyazás és az
// Olvasó. A Mermaid-féle (nem interaktív) viselkedés változatlan marad.

import { ensureSyntaxTree } from '@codemirror/language';
import { EditorState, type Transaction } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { bazisBeagyazasRenderelo, bazisKodRenderelo } from '../src/bazis/beagyazas';
import { blokkForras, fajlForras } from '../src/bazis/forras';
import { bazisTelepit } from '../src/bazis/index';
import type { Valasz } from '../src/bazis/tipusok';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import type { Kornyezet } from '../src/lib/kornyezet';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';
import { bovitmenyek } from '../src/szerkeszto/beallitas';
import { blokkMezo } from '../src/szerkeszto/elo/blokkok';
import { obsidianElemzo } from '../src/szerkeszto/markdown/elemzo';
import { dokumentumRenderel } from '../src/szerkeszto/olvaso/html';
import { LustaRajzolo } from '../src/szerkeszto/olvaso/lusta';
import { type KodRenderelo, type RenderKornyezet, kodRenderelok } from '../src/szerkeszto/renderelok/regiszter';
import { szerkesztok } from '../src/szerkeszto/szerkesztok.svelte';

const valaszok = (kod: number, adat: unknown) =>
  new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });

function kornyezet(): Kornyezet {
  return { felulet: new Felulet({}), fajlok: new VaultFajlok(), kapcsolat: new CoreKapcsolat('ws://127.0.0.1:1/ws') };
}

const BLOKK_JEGYZET = '# Cím\n\n```base\nviews:\n  - type: table\n```\n\nVége.';
const BLOKK_KOD = 'views:\n  - type: table';

function bazisValasz(db = 2, kieg: Partial<Valasz> = {}): Valasz {
  return {
    ok: true,
    nezetek: [{ nev: 'Táblázat', tipus: 'table', ismert: true }],
    nezet: { index: 0, nev: 'Táblázat', tipus: 'table', eredeti_tipus: 'table', beallitas: {} },
    oszlopok: [{ id: 'file.name', nev: 'Fájlnév', ter: 'file', tipus: 'text', szerkesztheto: false, szelesseg: null }],
    sorok: Array.from({ length: db }, (_, i) => ({
      ut: `K/Jegyzet ${i}.md`,
      nev: `Jegyzet ${i}`,
      md: true,
      cellak: [{ t: 'link' as const, cel: `K/Jegyzet ${i}.md`, ut: `K/Jegyzet ${i}.md`, nev: `Jegyzet ${i}` }],
    })),
    csoportok: null,
    osszesitok: {},
    osszes: db,
    levagva: false,
    hibak: [],
    figyelmeztetesek: [],
    ido_ms: 1,
    generacio: 1,
    ...kieg,
  };
}

let nezetek: EditorView[];
let tranzakciok: Transaction[];

function szerkeszto(doc: string, o: { csakOlvashato?: boolean; kurzor?: number; ut?: string } = {}): EditorView {
  const state = EditorState.create({
    doc,
    selection: { anchor: o.kurzor ?? doc.length },
    extensions: bovitmenyek({ mod: 'elo', csakOlvashato: !!o.csakOlvashato, ut: o.ut ?? 'Jegyzet.md', cimke: 'próba' }),
  });
  ensureSyntaxTree(state, state.doc.length, 5000);
  const v = new EditorView({
    state,
    parent: document.body,
    dispatchTransactions(trs, view) {
      tranzakciok.push(...trs);
      view.update(trs);
    },
  });
  nezetek.push(v);
  return v;
}

beforeEach(() => {
  nezetek = [];
  tranzakciok = [];
});

afterEach(() => {
  nezetek.forEach((v) => v.destroy());
  document.body.textContent = '';
  vi.unstubAllGlobals();
});

// ---------------------------------------------------------------------- az interaktív renderelő szerződése

describe('interaktív kódblokk-renderelő (a Live Preview widgetje)', () => {
  let kapott: RenderKornyezet[];
  let frissitesek: string[];
  let takaritva: number;
  let frissitVisszater: boolean;
  const le: Array<() => void> = [];

  function interaktiv(): KodRenderelo {
    return {
      nyelv: 'probabazis',
      interaktiv: true,
      render(forras, cel, k) {
        kapott.push(k);
        cel.textContent = `RAJZ:${forras}`;
        return () => {
          takaritva++;
        };
      },
      frissit(cel, forras) {
        frissitesek.push(forras);
        cel.textContent = `FRISS:${forras}`;
        return frissitVisszater;
      },
    };
  }

  beforeEach(() => {
    kapott = [];
    frissitesek = [];
    takaritva = 0;
    frissitVisszater = true;
  });

  afterEach(() => le.splice(0).forEach((f) => f()));

  const DOC = '# Cím\n\n```probabazis\nelső\nmásodik\n```\n\nVége.';

  it('a blokk kirajzolódik, a környezet `blokk` mezőt kap; a nem interaktív renderelő nem', async () => {
    le.push(kodRenderelok.regisztral(interaktiv()));
    le.push(kodRenderelok.regisztral({ nyelv: 'probasima', render: (f, cel, k) => { kapott.push(k); cel.textContent = f; } }));
    szerkeszto(DOC);
    await vi.waitFor(() => expect(document.querySelector('.cm-renderelt-blokk')?.textContent).toBe('RAJZ:első\nmásodik'));
    expect(kapott[0].blokk).toBeDefined();
    expect(kapott[0].blokk!.csakOlvashato).toBe(false);
    szerkeszto('x\n\n```probasima\nA\n```\n\ny');
    await vi.waitFor(() => expect(kapott).toHaveLength(2));
    expect(kapott[1].blokk).toBeUndefined();
  });

  it('a `csere` egyetlen tranzakció (input.bazis); a widget helyben frissül (ugyanaz a DOM-elem)', async () => {
    le.push(kodRenderelok.regisztral(interaktiv()));
    const v = szerkeszto(DOC);
    await vi.waitFor(() => expect(kapott).toHaveLength(1));
    const elem = document.querySelector('.cm-renderelt-blokk')!;
    tranzakciok.length = 0;
    expect(kapott[0].blokk!.csere('új\nkód')).toBe(true);
    expect(tranzakciok).toHaveLength(1);
    expect(tranzakciok[0].isUserEvent('input.bazis')).toBe(true);
    expect(v.state.doc.toString()).toBe('# Cím\n\n```probabazis\núj\nkód\n```\n\nVége.');
    await vi.waitFor(() => expect(frissitesek).toEqual(['új\nkód']));
    expect(document.querySelector('.cm-renderelt-blokk')).toBe(elem); // a DOM megmaradt
    expect(elem.textContent).toBe('FRISS:új\nkód');
    expect(kapott).toHaveLength(1); // nem rajzolódott újra
    expect(takaritva).toBe(0);
    // a frissítés után a következő csere az új szöveghez képest ellenőriz
    expect(kapott[0].blokk!.csere('harmadik')).toBe(true);
    expect(v.state.doc.toString()).toContain('```probabazis\nharmadik\n```');
  });

  it('azonos szövegre a csere nem ír; üres blokk kódja is cserélhető', async () => {
    le.push(kodRenderelok.regisztral(interaktiv()));
    const v = szerkeszto(DOC);
    await vi.waitFor(() => expect(kapott).toHaveLength(1));
    tranzakciok.length = 0;
    expect(kapott[0].blokk!.csere('első\nmásodik')).toBe(true);
    expect(tranzakciok).toHaveLength(0);
    expect(v.state.doc.toString()).toBe(DOC);
    const u = szerkeszto('a\n\n```probabazis\n```\n\nb');
    await vi.waitFor(() => expect(kapott).toHaveLength(2));
    expect(kapott[1].blokk!.csere('x: 1')).toBe(true);
    expect(u.state.doc.toString()).toBe('a\n\n```probabazis\nx: 1\n```\n\nb');
  });

  it('a csak olvasható jegyzet blokkja nem ír', async () => {
    le.push(kodRenderelok.regisztral(interaktiv()));
    const v = szerkeszto(DOC, { csakOlvashato: true });
    await vi.waitFor(() => expect(kapott).toHaveLength(1));
    expect(kapott[0].blokk!.csakOlvashato).toBe(true);
    expect(kapott[0].blokk!.csere('x')).toBe(false);
    expect(v.state.doc.toString()).toBe(DOC);
  });

  it('ha a `frissit` hamisat ad, a widget újrarajzolódik (új környezet, a régi takarít)', async () => {
    le.push(kodRenderelok.regisztral(interaktiv()));
    frissitVisszater = false;
    szerkeszto(DOC);
    await vi.waitFor(() => expect(kapott).toHaveLength(1));
    const regi = kapott[0].blokk!;
    expect(regi.csere('új')).toBe(true);
    await vi.waitFor(() => expect(kapott).toHaveLength(2));
    await vi.waitFor(() => expect(takaritva).toBe(1));
    expect(kapott[0].jel.aborted).toBe(true);
    expect(regi.csere('még')).toBe(false); // a régi widget már nem ír
    expect(kapott[1].blokk!.csere('még')).toBe(true);
  });

  it('a kattintás nem visz a forrásba (interaktív), a nem interaktívnál igen', async () => {
    le.push(kodRenderelok.regisztral(interaktiv()));
    le.push(kodRenderelok.regisztral({ nyelv: 'probasima', render: (f, cel) => void (cel.textContent = f) }));
    const v = szerkeszto(DOC);
    await vi.waitFor(() => expect(document.querySelector('.cm-renderelt-blokk')).not.toBeNull());
    const vege = v.state.selection.main.head;
    document.querySelector('.cm-renderelt-blokk')!.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, button: 0 }));
    expect(v.state.selection.main.head).toBe(vege);
    const w = szerkeszto('x\n\n```probasima\nA\n```\n\ny');
    await vi.waitFor(() => expect(w.dom.querySelector('.cm-renderelt-blokk')).not.toBeNull());
    w.dom.querySelector('.cm-renderelt-blokk')!.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, button: 0 }));
    expect(w.state.selection.main.head).toBe(w.state.doc.line(3).from);
  });

  it('a `forrasba()` a blokk elejére teszi a kurzort: a blokk aktív lesz, a widget lebomlik', async () => {
    le.push(kodRenderelok.regisztral(interaktiv()));
    const v = szerkeszto(DOC);
    await vi.waitFor(() => expect(kapott).toHaveLength(1));
    kapott[0].blokk!.forrasba();
    expect(v.state.selection.main.head).toBe(v.state.doc.line(3).from);
    await vi.waitFor(() => expect(document.querySelector('.cm-renderelt-blokk')).toBeNull());
    expect(takaritva).toBe(1);
    expect(kapott[0].jel.aborted).toBe(true);
  });

  it('az interaktív blokk a kurzornak atomi (a nem interaktív nem)', async () => {
    le.push(kodRenderelok.regisztral(interaktiv()));
    le.push(kodRenderelok.regisztral({ nyelv: 'probasima', render: (f, cel) => void (cel.textContent = f) }));
    const atomi = (v: EditorView) => {
      const ki: Array<[number, number]> = [];
      for (const f of v.state.facet(EditorView.atomicRanges)) f(v).between(0, v.state.doc.length, (a, b) => void ki.push([a, b]));
      return ki;
    };
    const v = szerkeszto(DOC);
    await vi.waitFor(() => expect(document.querySelector('.cm-renderelt-blokk')).not.toBeNull());
    expect(atomi(v)).toContainEqual([v.state.doc.line(3).from, v.state.doc.line(6).to]);
    const w = szerkeszto('x\n\n```probasima\nA\n```\n\ny');
    await vi.waitFor(() => expect(w.dom.querySelector('.cm-renderelt-blokk')).not.toBeNull());
    expect(atomi(w)).toEqual([]);
    void blokkMezo;
  });

  it('a nem interaktív renderelő viselkedése változatlan: nincs `blokk`, nincs `updateDOM`-frissítés, a szöveg-csere újrarajzol', async () => {
    const hivasok: string[] = [];
    le.push(kodRenderelok.regisztral({ nyelv: 'probasima', render: (f, cel) => void (hivasok.push(f), (cel.textContent = f)) }));
    const v = szerkeszto('x\n\n```probasima\nA\n```\n\ny');
    await vi.waitFor(() => expect(hivasok).toEqual(['A']));
    v.dispatch({ changes: { from: v.state.doc.line(4).from, to: v.state.doc.line(4).to, insert: 'B' } });
    await vi.waitFor(() => expect(hivasok).toEqual(['A', 'B']));
  });
});

// ---------------------------------------------------------------------- a blokk forrása

describe('blokkForras', () => {
  it('az írás a `csere`-n át megy; a záró soremelés lekerül; a változás jelez', async () => {
    const csere = vi.fn(() => true);
    const f = blokkForras('N.md', BLOKK_KOD, { csakOlvashato: false, csere });
    const jelek: number[] = [];
    f.figyel(() => jelek.push(1));
    expect(f.szoveg()).toBe(BLOKK_KOD);
    expect(f.ez).toBe('N.md');
    expect(await f.ir('views:\n  - type: cards\n')).toBe(true);
    expect(csere).toHaveBeenCalledWith('views:\n  - type: cards');
    expect(f.szoveg()).toBe('views:\n  - type: cards');
    expect(jelek).toHaveLength(1);
    expect(await f.ir('views:\n  - type: cards\n')).toBe(true); // nincs változás: nincs írás
    expect(csere).toHaveBeenCalledTimes(1);
  });

  it('a sikertelen csere nem módosítja a forrást', async () => {
    const f = blokkForras('N.md', 'a', { csakOlvashato: false, csere: () => false });
    expect(await f.ir('b')).toBe(false);
    expect(f.szoveg()).toBe('a');
  });

  it('csak olvasható jegyzetnél jelzi az okát; Olvasóban (blokk nélkül) csak memóriában ír', async () => {
    expect(blokkForras('N.md', 'a', { csakOlvashato: true, csere: () => false }).csakOlvashato()).toContain('csak olvasható');
    const o = blokkForras('N.md', 'a');
    expect(o.csakOlvashato()).toBeNull();
    expect(await o.ir('b\n')).toBe(true);
    expect(o.szoveg()).toBe('b');
  });

  it('a `beallit` a widget frissítése: jelez, ha tényleg más a szöveg', () => {
    const f = blokkForras('N.md', 'a');
    const jelek: number[] = [];
    f.figyel(() => jelek.push(1));
    f.beallit('a');
    expect(jelek).toHaveLength(0);
    f.beallit('b');
    expect(jelek).toHaveLength(1);
    expect(f.szoveg()).toBe('b');
  });
});

// ---------------------------------------------------------------------- a Bases blokkja és beágyazása, valódi nézettel

describe('```base blokk és ![[x.base]] beágyazás', () => {
  let lekerdezesek: Array<{ szoveg: string; ez: string; nezet: unknown }>;
  let lemez: Map<string, string>;
  let le: () => void;

  beforeEach(() => {
    lekerdezesek = [];
    lemez = new Map([['K/Könyvek.base', 'views:\n  - type: table\n    name: Egy\n  - type: table\n    name: Kettő\n']]);
    vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
      const u = new URL(url, 'http://127.0.0.1/');
      if (u.pathname === '/api/vault/bazis/lekerdez') {
        const k = JSON.parse(String(init!.body));
        lekerdezesek.push(k);
        return valaszok(200, bazisValasz(2));
      }
      if (u.pathname === '/api/vault/beagyazas')
        return valaszok(200, { tipus: 'base', ut: 'K/Könyvek.base', alcel: u.searchParams.get('alcel') });
      if (u.pathname === '/api/vault/fajl') {
        const t = lemez.get(u.searchParams.get('ut')!);
        return t === undefined ? valaszok(404, { hiba: 'nincs' }) : valaszok(200, { ut: u.searchParams.get('ut'), tartalom: t, hash: 'h', jel: '', mtime: 0 });
      }
      return valaszok(404, { hiba: 'nincs' });
    });
    le = bazisTelepit(kornyezet());
  });

  afterEach(() => le());

  it('a ```base blokk a Live Preview-ban kirajzolódik: a blokk szövege a lekérdezés, a `this` a jegyzet', async () => {
    szerkeszto(BLOKK_JEGYZET, { ut: 'Jegyzetek/Fő.md' });
    await vi.waitFor(() => expect(document.querySelectorAll('.cm-renderelt-blokk .sor')).toHaveLength(2));
    expect(lekerdezesek[0]).toMatchObject({ szoveg: BLOKK_KOD, ez: 'Jegyzetek/Fő.md' });
    expect(document.querySelector('.cm-renderelt-blokk .talalat')!.textContent).toContain('2 találat');
    expect(document.querySelector('.cm-renderelt-blokk .forras-gomb')).not.toBeNull();
  });

  it('a „Forrás” gomb megnyitja a blokk forrását', async () => {
    const v = szerkeszto(BLOKK_JEGYZET);
    await vi.waitFor(() => expect(document.querySelector('.forras-gomb')).not.toBeNull());
    (document.querySelector('.forras-gomb') as HTMLButtonElement).click();
    expect(v.state.selection.main.head).toBe(v.state.doc.line(3).from);
    await vi.waitFor(() => expect(document.querySelector('.cm-renderelt-blokk')).toBeNull());
    expect(v.dom.textContent).toContain('views:');
  });

  it('a blokkban a kattintás a saját vezérlőkre megy, nem a forrásba', async () => {
    const v = szerkeszto(BLOKK_JEGYZET);
    await vi.waitFor(() => expect(document.querySelector('.cm-renderelt-blokk .sor')).not.toBeNull());
    const vege = v.state.selection.main.head;
    document.querySelector('.cm-renderelt-blokk .sor')!.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, button: 0 }));
    expect(v.state.selection.main.head).toBe(vege);
  });

  it('az Olvasóban rögzített forrással rajzol (nincs Forrás gomb)', async () => {
    const forras = '```base\n' + BLOKK_KOD + '\n```';
    const kont = document.createElement('article');
    document.body.appendChild(kont);
    kont.appendChild(
      dokumentumRenderel(obsidianElemzo.parse(forras), { olvas: (a, b) => forras.slice(a, b), ut: 'Olv.md', lusta: LustaRajzolo.azonnali(), elotag: 'o' }),
    );
    await vi.waitFor(() => expect(kont.querySelectorAll('.sor')).toHaveLength(2));
    expect(lekerdezesek[0]).toMatchObject({ szoveg: BLOKK_KOD, ez: 'Olv.md' });
    expect(kont.querySelector('.forras-gomb')).toBeNull();
  });

  it('`![[x.base#Nézet]]`: a fájl a Dokumentumán át, a megnevezett nézettel, a `this` a befoglaló jegyzet', async () => {
    szerkeszto('Elő\n\n![[Könyvek.base#Kettő]]\n\nUtó', { ut: 'Jegyzetek/Fő.md', kurzor: 0 });
    await vi.waitFor(() => expect(document.querySelectorAll('.beagyazas-base .sor')).toHaveLength(2));
    expect(lekerdezesek[0]).toMatchObject({ szoveg: lemez.get('K/Könyvek.base'), ez: 'Jegyzetek/Fő.md', nezet: 'Kettő' });
    expect(szerkesztok.dokumentumok.kap('K/Könyvek.base')!.nezetSzam).toBe(1);
  });

  it('a beágyazás lebontása elengedi a dokumentumot', async () => {
    const v = szerkeszto('Elő\n\n![[Könyvek.base]]\n\nUtó', { ut: 'Jegyzetek/Fő.md', kurzor: 0 });
    await vi.waitFor(() => expect(document.querySelector('.beagyazas-base .sor')).not.toBeNull());
    const d = szerkesztok.dokumentumok.kap('K/Könyvek.base')!;
    expect(d.nezetSzam).toBe(1);
    v.dispatch({ selection: { anchor: v.state.doc.line(3).from + 2 } });
    // F11: az aktív önálló embed forrása alatt is megmarad a preview és a dokumentumkapcsolat.
    expect(document.querySelector('.beagyazas-base')).not.toBeNull();
    expect(d.nezetSzam).toBe(1);
    // Valódi widget-megszűnés: a forrásjelölés kikerül a dokumentumból. A cél nem maradhat csatolva vagy cache-ben.
    const sor = v.state.doc.line(3);
    v.dispatch({ changes: { from: sor.from, to: sor.to, insert: '' } });
    await vi.waitFor(() => expect(document.querySelector('.beagyazas-base')).toBeNull());
    await vi.waitFor(() => expect(d.nezetSzam).toBe(0));
    await vi.waitFor(() => expect(szerkesztok.dokumentumok.kap('K/Könyvek.base')).toBeUndefined());
  });

  it('sor közepén álló beágyazás csak link-chip', async () => {
    szerkeszto('Elő\n\nSor ![[Könyvek.base]] utó', { ut: 'Jegyzetek/Fő.md', kurzor: 0 });
    await vi.waitFor(() => expect(document.querySelector('.beagyazas-chip')).not.toBeNull());
    expect(document.querySelector('.beagyazas-base')).toBeNull();
    expect(lekerdezesek).toHaveLength(0);
  });

  it('a hiányzó `.base` fájl hibaüzenet, nem dob', async () => {
    lemez.clear();
    szerkeszto('Elő\n\n![[Könyvek.base]]\n\nUtó', { ut: 'Jegyzetek/Fő.md', kurzor: 0 });
    await vi.waitFor(() => expect(document.querySelector('.beagyazas-hiba')?.textContent).toContain('nem rajzolható'));
  });

  it('a telepítés nem regisztrál kétszer, és a leállítás eltávolít mindent', () => {
    const k = kornyezet();
    const masodik = () => bazisTelepit(k);
    expect(masodik).toThrow(/már regisztrált/);
    le();
    const ujra = bazisTelepit(k); // a leállítás után újra telepíthető
    ujra();
    le = () => {};
  });

  it('a renderelők közvetlenül is létrehozhatók (a regiszterbe kötés nélkül)', () => {
    const k = kornyezet();
    expect(bazisKodRenderelo(k)).toMatchObject({ nyelv: 'base', interaktiv: true });
    expect(bazisBeagyazasRenderelo(k).tipus).toBe('base');
    void fajlForras;
  });
});
