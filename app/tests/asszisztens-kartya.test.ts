// A javaslat-kártya (J3): az elfogadás csak a nyitott jegyzetbe ír, a szerkesztőn át, egy tranzakcióban (⌘Z egy lépés); a címke a
// tulajdonság-szerkesztő `modosit` útján (séma-sértés csendben nem íródik); a döntés a core hangolásába megy; az ütemező csak
// bekapcsolt Asszisztenssel, gépelési szünetben kérdez, és a core várakozását tartja. A kártya nem kér fókuszt.

import { afterEach, describe, expect, it, vi } from 'vitest';
import { EditorState } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import { history, undo } from '@codemirror/commands';
import { KartyaAllapot, kartyaAlkalmaz, type KartyaSegedek } from '../src/lib/asszisztens/kartya.svelte';
import type { KartyaJavaslat, KartyaValasz } from '../src/lib/asszisztens/tipusok';
import { kartyaUtemezo, kartyaUtemezoForras, type KartyaUtemezoBeallitas } from '../src/szerkeszto/asszisztens/kartyaUtemezo';
import { fmCimkek } from '../src/szerkeszto/tulajdonsagok/api';
import type { Elemzes, ModositEredmeny } from '../src/szerkeszto/tulajdonsagok/tipusok';

let v: EditorView | null = null;
afterEach(() => { v?.destroy(); v = null; document.getSelection()?.removeAllRanges(); document.body.textContent = ''; vi.useRealTimers(); });

function nezet(doc: string, tovabbi: unknown[] = []): EditorView {
  const parent = document.body.appendChild(document.createElement('div'));
  v = new EditorView({ parent, state: EditorState.create({ doc, extensions: [history(), ...(tovabbi as never[])] }) });
  return v;
}

const J = (muvelet: KartyaJavaslat['muvelet'], tipus: KartyaJavaslat['tipus'] = 'szerkezet'): KartyaJavaslat => ({
  azon: `${tipus}:0123456789ab`, tipus, helyzet: 'szunet_rovid', cim: 'Mit szólnál…?', indok: 'mert', allas: 'batrabb', muvelet,
});
const SEGED: KartyaSegedek = { ut: 'Mappa/Jegyzet.md', linkCel: async (c) => c.replace(/\.md$/, '').split('/').pop()! };

describe('az elfogadás a szerkesztőn át', () => {
  it('szakasz a jegyzet végére, üres sorral, egy ⌘Z-lépés', async () => {
    const w = nezet('# Cím\n\nSzöveg.');
    expect(await kartyaAlkalmaz(w, J({ fajta: 'szakasz', szoveg: '## Példák' }), SEGED)).toBe(true);
    expect(w.state.doc.toString()).toBe('# Cím\n\nSzöveg.\n\n## Példák\n');
    expect(undo(w)).toBe(true);
    expect(w.state.doc.toString()).toBe('# Cím\n\nSzöveg.');
  });

  it('link a core cél-szövegével (L42), a meglévő sorvég után', async () => {
    const w = nezet('Szöveg.\n');
    const linkCel = vi.fn(async () => 'Másik');
    expect(await kartyaAlkalmaz(w, J({ fajta: 'link', cel: 'B/Másik.md' }, 'tartalom'), { ...SEGED, linkCel })).toBe(true);
    expect(linkCel).toHaveBeenCalledWith('B/Másik.md');
    expect(w.state.doc.toString()).toBe('Szöveg.\n\nKapcsolódó: [[Másik]]\n');
  });

  it('címke a `modosit` útján: a frontmatter-blokk cseréje, egy ⌘Z-lépés', async () => {
    const fm = '---\nTags:\n  - Mathematics\nStatus:\n---\n';
    const w = nezet(fm + 'Törzs.');
    const elemez = vi.fn(async (): Promise<Elemzes> => ({ van: true, hiba: null, kulcsok: ['Tags', 'Status'], problemak: [], osztaly: 'jegyzet',
      tulajdonsagok: [{ kulcs: 'Tags', tipus: 'tags', ertek: ['Mathematics'], ervenyes: true }] }));
    const modosit = vi.fn(async (): Promise<ModositEredmeny> => ({ ok: true, fm_uj: '---\nTags:\n  - Mathematics\n  - Analízis\nStatus:\n---\n',
      megerositheto: false, valtozas: true, problemak: [] }));
    expect(await kartyaAlkalmaz(w, J({ fajta: 'cimke', ertek: 'Analízis' }, 'muvelet'), { ...SEGED, tulajdonsag: { elemez, modosit } })).toBe(true);
    expect(modosit).toHaveBeenCalledWith('Mappa/Jegyzet.md', fm, { muvelet: 'beallit', kulcs: 'Tags', ertek: ['Mathematics', 'Analízis'] }, false);
    expect(w.state.doc.toString()).toBe('---\nTags:\n  - Mathematics\n  - Analízis\nStatus:\n---\nTörzs.');
    expect(undo(w)).toBe(true);
    expect(w.state.doc.toString()).toBe(fm + 'Törzs.');
  });

  it('a séma-sértő címke nem íródik csendben (22(b)): üzenet, a jegyzet érintetlen', async () => {
    const fm = '---\nTags:\nStatus:\n---\n';
    const w = nezet(fm);
    const r = await kartyaAlkalmaz(w, J({ fajta: 'cimke', ertek: 'Ismeretlen' }, 'muvelet'), { ...SEGED, tulajdonsag: {
      elemez: async () => ({ van: true, hiba: null, kulcsok: [], problemak: [], osztaly: 'jegyzet', tulajdonsagok: [] }),
      modosit: async () => ({ ok: false, fm_uj: null, megerositheto: true, valtozas: false,
        problemak: [{ kod: 'ertekkeszlet', szint: 'sertes', kulcs: 'Tags', ertek: 'Ismeretlen', uzenet: 'A címke nincs az értékkészletben.' }] }),
    } });
    expect(r).toBe('A címke nincs az értékkészletben.');
    expect(w.state.doc.toString()).toBe(fm);
  });

  it('frontmatter nélkül a címke nem kerül be (a tulajdonság-panelre utal)', async () => {
    const w = nezet('Csak szöveg.');
    expect(await kartyaAlkalmaz(w, J({ fajta: 'cimke', ertek: 'X' }, 'muvelet'), SEGED)).toMatch(/tulajdonság/);
    expect(w.state.doc.toString()).toBe('Csak szöveg.');
  });

  it('sablon a meglévő „Sablon beszúrása” útján', async () => {
    const w = nezet('');
    const sablon = vi.fn(async () => undefined);
    expect(await kartyaAlkalmaz(w, J({ fajta: 'sablon', ut: '_Template/Óra.md' }, 'muvelet'), { ...SEGED, sablon })).toBe(true);
    expect(sablon).toHaveBeenCalledWith('_Template/Óra.md');
  });
});

describe('a kártya állapota és a döntés', () => {
  it('Igen: beír, „elfogad” megy a hangolásba, a kártya eltűnik; közben másik kártya nem jön', async () => {
    const dontes = vi.fn(async () => ({}));
    const k = new KartyaAllapot(dontes, 1000);
    const w = nezet('A');
    k.mutat(J({ fajta: 'szakasz', szoveg: '## B' }), w, SEGED);
    k.mutat(J({ fajta: 'szakasz', szoveg: '## C' }), w, SEGED);
    expect(k.aktiv?.javaslat.muvelet).toEqual({ fajta: 'szakasz', szoveg: '## B' });
    await k.igen();
    expect(w.state.doc.toString()).toBe('A\n\n## B\n');
    expect(dontes).toHaveBeenCalledWith(expect.objectContaining({ dontes: 'elfogad', tipus: 'szerkezet', helyzet: 'szunet_rovid' }));
    expect(k.aktiv).toBeNull();
  });

  it('Nem: „elutasit”, semmi nem íródik; lejárat: „figyelmen_kivul”', async () => {
    vi.useFakeTimers();
    const dontes = vi.fn(async () => ({}));
    const k = new KartyaAllapot(dontes, 1000);
    const w = nezet('A');
    k.mutat(J({ fajta: 'szakasz', szoveg: '## B' }), w, SEGED);
    k.nem();
    expect(dontes).toHaveBeenLastCalledWith(expect.objectContaining({ dontes: 'elutasit' }));
    expect(w.state.doc.toString()).toBe('A');
    k.mutat(J({ fajta: 'szakasz', szoveg: '## B' }), w, SEGED);
    await vi.advanceTimersByTimeAsync(1001);
    expect(k.aktiv).toBeNull();
    expect(dontes).toHaveBeenLastCalledWith(expect.objectContaining({ dontes: 'figyelmen_kivul' }));
  });

  it('a kártya nem veszi el a fókuszt a szerkesztőtől', async () => {
    const k = new KartyaAllapot(async () => ({}), 1000);
    const w = nezet('A');
    w.focus();
    k.mutat(J({ fajta: 'szakasz', szoveg: '## B' }), w, SEGED);
    expect(document.activeElement).toBe(w.contentDOM);
    k.elrejt(null);
  });
});

describe('az ütemező a szerkesztőben', () => {
  function utemezett(b: Partial<KartyaUtemezoBeallitas> = {}) {
    vi.useFakeTimers();
    const ker = vi.fn(async (): Promise<KartyaValasz> => ({ javaslat: J({ fajta: 'szakasz', szoveg: '## B' }), varakozas_mp: 90, kapcsolo: true }));
    const mutat = vi.fn();
    const allas = { be: true, latszik: false };
    const w = nezet('Szöveg', [kartyaUtemezo(), kartyaUtemezoForras.of({ ut: 'A.md', kapcsolo: () => allas.be, latszik: () => allas.latszik, ker, mutat,
      szunetMs: 100, megnyitasMs: 50, ...b })]);
    w.focus();
    return { w, ker, mutat, allas };
  }
  const gepel = (w: EditorView, s: string) => w.dispatch({ changes: { from: w.state.doc.length, insert: s }, userEvent: 'input.type' });

  it('megnyitáskor egyszer, gépelési szünetben újra — a core várakozását tartva', async () => {
    const { w, ker, mutat } = utemezett();
    await vi.advanceTimersByTimeAsync(60);
    expect(ker).toHaveBeenCalledWith('megnyitas', 'Szöveg', expect.anything());
    expect(mutat).toHaveBeenCalledTimes(1);
    gepel(w, ' x');
    await vi.advanceTimersByTimeAsync(150);
    expect(ker).toHaveBeenCalledTimes(1);                          // a 90 s-os várakozás még tart
    await vi.advanceTimersByTimeAsync(90_000);
    gepel(w, ' y');
    await vi.advanceTimersByTimeAsync(150);
    expect(ker).toHaveBeenLastCalledWith('szunet', 'Szöveg x y', expect.anything());
  });

  it('kikapcsolt Asszisztensnél és látható kártya mellett nem kérdez', async () => {
    const { w, ker, allas } = utemezett();
    allas.be = false;
    await vi.advanceTimersByTimeAsync(60);
    gepel(w, ' x');
    await vi.advanceTimersByTimeAsync(150);
    expect(ker).not.toHaveBeenCalled();
    allas.be = true;
    allas.latszik = true;
    gepel(w, ' y');
    await vi.advanceTimersByTimeAsync(150);
    expect(ker).not.toHaveBeenCalled();
  });

  it('a nézet lebontása a kártyát is elrejti', () => {
    const bezar = vi.fn();
    const { w } = utemezett({ bezar });
    w.destroy();
    v = null;
    expect(bezar).toHaveBeenCalledWith(w);
  });
});

describe('a címkék olvasása a tanuló jelzéséhez', () => {
  it('lista, soron belüli és üres alak', () => {
    expect(fmCimkek('---\nTags:\n  - Mathematics\n  - "#Analízis"\nStatus:\n---\n')).toEqual(['Mathematics', 'Analízis']);
    expect(fmCimkek('---\ntags: [a, "b"]\n---\n')).toEqual(['a', 'b']);
    expect(fmCimkek('---\nTags:\nStatus:\n---\n')).toEqual([]);
    expect(fmCimkek(null)).toEqual([]);
  });
});
