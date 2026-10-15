// Csak olvasható jegyzet és a programos beszúrások (C29.7a, T117): az `EditorState.readOnly` a `view.dispatch`-et nem
// tiltja, ezért a sablon-beszúrás, a PDF-idézet, az időkód és a helyi menü csendben módosította a csak olvasható
// dokumentumot (a változás nem mentődött, a dokumentum örökre „piszkos” maradt). Itt: közös `irhato` őr + a
// `changeFilter` háló; és az Olvasó feladat-jelölője elavult pozíción (T120).

import { history } from '@codemirror/commands';
import { EditorState } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import { fireEvent, render } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ertesitesek } from '../src/lib/ertesites/ertesites.svelte';
import { sablonBeszurasAktiv, sablonBeszurasElerheto } from '../src/ma/naplo';
import { celSzerkeszto, idezetBeszur, idokodBeszur } from '../src/media/beszuras';
import { bovitmenyek, irhato, szinkronJel } from '../src/szerkeszto/beallitas';
import { jegyzetUtja } from '../src/szerkeszto/elo/jegyzet';
import { menuElemek } from '../src/szerkeszto/helyiMenu';
import Olvaso from '../src/szerkeszto/Olvaso.svelte';
import { szerkesztok, type Mod, type SzerkesztoPeldany } from '../src/szerkeszto/szerkesztok.svelte';

let kerelmek: string[];
const json = (adat: unknown, kod = 200) => new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });
const nezetek: EditorView[] = [];

beforeEach(() => {
  kerelmek = [];
  vi.stubGlobal('fetch', async (url: string) => {
    kerelmek.push(url);
    return url.startsWith('/api/vault/linkcel') ? json({ cel: 'v.mp4' }) : json({});
  });
  ertesitesek.lista.length = 0;
});

afterEach(() => {
  if (szerkesztok.aktiv) szerkesztok.megszunt(szerkesztok.aktiv);
  if (szerkesztok.utolso) szerkesztok.megszunt(szerkesztok.utolso);
  nezetek.splice(0).forEach((v) => v.destroy());
  document.body.textContent = '';
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function nezet(doc: string, csakOlvashato: boolean, kurzor = doc.length): EditorView {
  const hely = document.createElement('div');
  document.body.append(hely);
  const v = new EditorView({
    state: EditorState.create({
      doc,
      selection: { anchor: kurzor },
      extensions: [history(), EditorState.readOnly.of(csakOlvashato), jegyzetUtja.of('M01/Jegyzet.md')],
    }),
    parent: hely,
  });
  nezetek.push(v);
  return v;
}

function peldany(v: EditorView, mod: Mod = 'elo'): SzerkesztoPeldany {
  const p = { ut: 'M01/Jegyzet.md', nezet: () => v, mod: () => mod } as unknown as SzerkesztoPeldany;
  szerkesztok.beallit(p);
  return p;
}

describe('a `changeFilter` háló', () => {
  const ext = (ro: boolean) => bovitmenyek({ mod: 'forras', csakOlvashato: ro, ut: 'a.md', cimke: 'a' });

  it('csak olvasható állapotban a programos változás nem módosítja a dokumentumot', () => {
    const s = EditorState.create({ doc: 'abc', extensions: ext(true) });
    expect(s.update({ changes: { from: 0, insert: 'x' } }).state.doc.toString()).toBe('abc');
    const v = new EditorView({ state: s, parent: document.body });
    nezetek.push(v);
    v.dispatch({ changes: { from: 3, insert: 'y' } });
    expect(v.state.doc.toString()).toBe('abc');
  });

  it('a dokumentum felőli szinkron (`szinkronJel`) csak olvasható állapotban is átmegy', () => {
    const s = EditorState.create({ doc: 'abc', extensions: ext(true) });
    expect(s.update({ changes: { from: 0, insert: 'x' }, annotations: szinkronJel.of(true) }).state.doc.toString()).toBe('xabc');
  });

  it('írható állapotban a változás átmegy; a kijelölés csak olvasható állapotban is mozoghat', () => {
    const iro = EditorState.create({ doc: 'abc', extensions: ext(false) });
    expect(iro.update({ changes: { from: 0, insert: 'x' } }).state.doc.toString()).toBe('xabc');
    const ro = EditorState.create({ doc: 'abc', extensions: ext(true) });
    expect(ro.update({ selection: { anchor: 2 } }).state.selection.main.head).toBe(2);
  });

  it('`irhato`: a nézet állapotából', () => {
    expect(irhato(nezet('a', true))).toBe(false);
    expect(irhato(nezet('a', false))).toBe(true);
  });
});

describe('PDF-idézet és időkód csak olvasható jegyzetbe', () => {
  it('nincs cél: az idézet és az időkód a vágólapra kerül, a jegyzet nem változik', async () => {
    const v = nezet('# Cím\n', true);
    peldany(v);
    expect(celSzerkeszto()).toBeNull();
    const iras = vi.fn(async () => {});
    vi.stubGlobal('navigator', { clipboard: { writeText: iras } });
    expect(await idezetBeszur('Mx/10 - Matematika.pdf', 3, 'Szöveg')).toBeNull();
    expect(await idokodBeszur('v.mp4', 3)).toBeNull();
    expect(v.state.doc.toString()).toBe('# Cím\n');
    expect(iras).toHaveBeenCalledTimes(2);
  });

  it('írható jegyzetbe továbbra is beszúr', async () => {
    const v = nezet('Lásd', false);
    peldany(v);
    await idokodBeszur('v.mp4', 45);
    expect(v.state.doc.toString()).toBe('Lásd [[v.mp4#t=45|0:45]]');
  });
});

describe('sablon beszúrása csak olvasható jegyzetbe', () => {
  it('nem elérhető, és közvetlen hívásra sem ír (nincs core-kérés)', async () => {
    const v = nezet('# Cím\n', true);
    peldany(v);
    expect(sablonBeszurasElerheto()).toBe(false);
    await sablonBeszurasAktiv('Sablonok/Napi jegyzet.md');
    expect(v.state.doc.toString()).toBe('# Cím\n');
    expect(kerelmek).toEqual([]);
    expect(ertesitesek.lista.at(-1)?.szoveg).toMatch(/csak olvasható/);
  });
});

describe('a helyi menü csak olvasható jegyzetben', () => {
  it('a Kivágás és a Beillesztés tiltott, és az akciójuk nem módosít', () => {
    const v = nezet('Hello világ', true, 0);
    v.dispatch({ selection: { anchor: 0, head: 5 } });
    const { elemek, akciok } = menuElemek(v);
    const letiltva = Object.fromEntries(elemek.map((e) => [e.id, !!e.letiltva]));
    expect(letiltva.kivag).toBe(true);
    expect(letiltva.beillesztes).toBe(true);
    expect(letiltva.masol).toBe(false); // a másolás olvasás
    vi.stubGlobal('navigator', { clipboard: { writeText: async () => {}, readText: async () => 'X' } });
    akciok.get('kivag')!();
    expect(v.state.doc.toString()).toBe('Hello világ');
  });
});

describe('az Olvasó feladat-jelölője (T120)', () => {
  function olvasoNezet(doc: string): EditorView {
    const v = new EditorView({
      state: EditorState.create({ doc, extensions: bovitmenyek({ mod: 'forras', csakOlvashato: false, ut: 'proba.md', cimke: 'p' }) }),
      parent: document.body,
    });
    nezetek.push(v);
    return v;
  }

  it('ha a jelölő pozíciója közben elavult (külső változás a 120 ms-os újrarajzolás előtt), nem ír', async () => {
    const v = olvasoNezet('- [ ] a\n- b\n');
    const r = render(Olvaso, { props: { view: v, dok: { csakOlvashato: false } as never, ut: 'proba.md', valtozat: 0 } });
    const doboz = r.container.querySelector<HTMLInputElement>('input.feladat-jelolo')!;
    expect(doboz).not.toBeNull();
    v.dispatch({ changes: { from: 0, insert: 'xx\n' } }); // külső változás: a `[` pozíciója elcsúszott
    doboz.checked = true;
    await fireEvent.change(doboz);
    expect(v.state.doc.toString()).toBe('xx\n- [ ] a\n- b\n'); // a régi pozíción (a `-`) semmi nem íródott át
  });

  it('friss pozíción a jelölő kapcsol', async () => {
    const v = olvasoNezet('- [ ] a\n- b\n');
    const r = render(Olvaso, { props: { view: v, dok: { csakOlvashato: false } as never, ut: 'proba.md', valtozat: 0 } });
    const doboz = r.container.querySelector<HTMLInputElement>('input.feladat-jelolo')!;
    doboz.checked = true;
    await fireEvent.change(doboz);
    expect(v.state.doc.toString()).toBe('- [x] a\n- b\n');
  });
});
