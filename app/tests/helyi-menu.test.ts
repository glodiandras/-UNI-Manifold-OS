// A jegyzet helyi menüje (C17): csak Markdown-jegyzetben nyílik; Kivágás/Másolás/Beillesztés + a Manifold-parancsok a
// regiszterből (a helyőrzők és a valódi parancsok ugyanazon az azonosítón); a kijelölés nélküli vágás/másolás tiltott.

import { EditorState } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { hejKepesseg } from '../src/lib/core/hej';
import { regiszter } from '../src/lib/parancsok/regiszter';
import { jegyzetUtja } from '../src/szerkeszto/elo/jegyzet';
import { helyiMenuBovitmeny, menuElemek, menuNyithato, nativMenuElemek } from '../src/szerkeszto/helyiMenu';
import { JEGYZET_MENU_PARANCSOK } from '../src/vezerlo/helyorzok';

const nezetek: EditorView[] = [];
function szerkeszto(ut: string | null, doc = 'Hello világ', sel?: [number, number]) {
  const v = new EditorView({
    state: EditorState.create({
      doc,
      selection: sel ? { anchor: sel[0], head: sel[1] } : undefined,
      extensions: [jegyzetUtja.of(ut), helyiMenuBovitmeny()],
    }),
    parent: document.body,
  });
  nezetek.push(v);
  return v;
}

const leiratkozok: (() => void)[] = [];
afterEach(() => {
  nezetek.splice(0).forEach((v) => v.destroy());
  leiratkozok.splice(0).forEach((f) => f());
  document.body.textContent = '';
  vi.restoreAllMocks();
});

describe('a helyi menü', () => {
  it('csak Markdown-jegyzetben nyitható', () => {
    expect(menuNyithato(szerkeszto('A/Jegyzet.md'))).toBe(true);
    expect(menuNyithato(szerkeszto('A/JEGYZET.MD'))).toBe(true);
    expect(menuNyithato(szerkeszto('A/Vaszon.canvas'))).toBe(false);
    expect(menuNyithato(szerkeszto(null))).toBe(false);
    expect(menuNyithato(szerkeszto(''))).toBe(false);
  });

  it('kijelölés nélkül a Kivágás és a Másolás tiltott, a Beillesztés nem', () => {
    const { elemek } = menuElemek(szerkeszto('a.md'));
    const letiltva = Object.fromEntries(elemek.map((e) => [e.id, !!e.letiltva]));
    expect(letiltva).toMatchObject({ kivag: true, masol: true, beillesztes: false });
  });

  it('kijelöléssel a Kivágás kiveszi a szöveget és a vágólapra teszi; a Másolás nem módosít', async () => {
    const irt: string[] = [];
    vi.stubGlobal('navigator', { clipboard: { writeText: async (t: string) => void irt.push(t) } });
    const v = szerkeszto('a.md', 'Hello világ', [0, 5]);
    const { elemek, akciok } = menuElemek(v);
    expect(elemek.find((e) => e.id === 'kivag')!.letiltva).toBe(false);
    akciok.get('masol')!();
    expect(v.state.doc.toString()).toBe('Hello világ');
    akciok.get('kivag')!();
    expect(v.state.doc.toString()).toBe(' világ');
    await vi.waitFor(() => expect(irt).toEqual(['Hello', 'Hello']));
    vi.unstubAllGlobals();
  });

  it('a Beillesztés a vágólap szövegét a kijelölés helyére írja; ha nem olvasható, értesít', async () => {
    vi.stubGlobal('navigator', { clipboard: { readText: async () => 'ÚJ' } });
    const v = szerkeszto('a.md', 'Hello világ', [6, 11]);
    menuElemek(v).akciok.get('beillesztes')!();
    await vi.waitFor(() => expect(v.state.doc.toString()).toBe('Hello ÚJ'));
    vi.stubGlobal('navigator', { clipboard: { readText: async () => Promise.reject(new Error('tiltott')) } });
    menuElemek(v).akciok.get('beillesztes')!();
    vi.unstubAllGlobals();
  });

  it('a Manifold-parancsok a regiszterből jönnek: ami nincs regisztrálva, kimarad; az elérhetetlen tiltott; a futtatás a regiszteren át megy', () => {
    const futott = vi.fn();
    leiratkozok.push(
      regiszter.regisztral({ id: 'kartya.ebbol', nev: 'Kártyák ebből', futtat: futott }),
      regiszter.regisztral({ id: 'kviz.ebbol', nev: 'Kvíz ebből', elerheto: () => false, futtat: () => {} }),
    );
    const { elemek, akciok } = menuElemek(szerkeszto('a.md'));
    const manifold = elemek.filter((e) => e.csoport === 'Manifold');
    expect(manifold.map((e) => e.nev)).toEqual(['Kártyák ebből', 'Kvíz ebből']);
    expect(manifold.map((e) => !!e.letiltva)).toEqual([false, true]);
    akciok.get('parancs:kartya.ebbol')!();
    expect(futott).toHaveBeenCalledTimes(1);
    expect(JEGYZET_MENU_PARANCSOK).toEqual(['kartya.ebbol', 'kviz.ebbol', 'matek.megoldas', 'matek.levezetes', 'osszefoglalas.keszit']);   // az utolsó C26b óta valódi parancs
  });

  it('jobb klikk megnyitja a menüt (a natív helyett), canvas-kártyában nem; Esc zárja', () => {
    const v = szerkeszto('a.md');
    const e = new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: 10, clientY: 10 });
    v.contentDOM.dispatchEvent(e);
    expect(e.defaultPrevented).toBe(true);
    const menu = document.querySelector('.nt-lebego')!;
    expect(menu).not.toBeNull();
    expect(menu.textContent).toContain('Beillesztés');
    menu.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    expect(document.querySelector('.nt-lebego')).toBeNull();
    const masik = szerkeszto('vaszon.canvas');
    const e2 = new MouseEvent('contextmenu', { bubbles: true, cancelable: true });
    masik.contentDOM.dispatchEvent(e2);
    expect(e2.defaultPrevented).toBe(false);
    expect(document.querySelector('.nt-lebego')).toBeNull();
  });

  describe('natív menü a héjban (C32b)', () => {
    const uzenetek: unknown[] = [];
    function hejjel(kepesseg: boolean) {
      const w = window as unknown as Record<string, unknown>;
      uzenetek.length = 0;
      w.webkit = { messageHandlers: { manifold: { postMessage: (u: unknown) => void uzenetek.push(u) } } };
      if (kepesseg) w.__MOS_HEJ__ = { helyiMenu: true };
    }
    afterEach(() => {
      const w = window as unknown as Record<string, unknown>;
      delete w.webkit;
      delete w.__MOS_HEJ__;
    });

    it('a képességet a héj hirdeti; hirdetés nélkül (régi héj, böngésző) nincs natív menü', () => {
      expect(hejKepesseg('helyiMenu')).toBe(false);
      hejjel(false);
      expect(hejKepesseg('helyiMenu')).toBe(false);
      hejjel(true);
      expect(hejKepesseg('helyiMenu')).toBe(true);
    });

    it('képességgel a jobb klikk nem tiltja le a natív menüt, és a Manifold-parancsok listáját elküldi a héjnak', () => {
      leiratkozok.push(
        regiszter.regisztral({ id: 'kartya.ebbol', nev: 'Kártyák ebből', futtat: () => {} }),
        regiszter.regisztral({ id: 'kviz.ebbol', nev: 'Kvíz ebből', elerheto: () => false, futtat: () => {} }),
      );
      hejjel(true);
      const v = szerkeszto('a.md');
      const e = new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: 10, clientY: 10 });
      v.contentDOM.dispatchEvent(e);
      expect(e.defaultPrevented).toBe(false);
      expect(document.querySelector('.nt-lebego')).toBeNull();
      expect(uzenetek).toEqual([
        { tipus: 'helyi-menu', elemek: [{ id: 'kartya.ebbol', nev: 'Kártyák ebből', letiltva: false }, { id: 'kviz.ebbol', nev: 'Kvíz ebből', letiltva: true }] },
      ]);
      // egy forrás: a saját menü Manifold-csoportjával azonos lista
      expect(nativMenuElemek(v).map((x) => x.nev)).toEqual(menuElemek(v).elemek.filter((x) => x.csoport === 'Manifold').map((x) => x.nev));
    });

    it('canvas-kártyában képességgel sem küld semmit', () => {
      hejjel(true);
      szerkeszto('vaszon.canvas').contentDOM.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, cancelable: true }));
      expect(uzenetek).toEqual([]);
    });
  });
});
