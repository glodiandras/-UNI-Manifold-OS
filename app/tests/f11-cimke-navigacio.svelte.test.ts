import { ensureSyntaxTree } from '@codemirror/language';
import { EditorState } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { beallitasok } from '../src/lib/beallitasok/allapot.svelte';
import { alapBeallitasok } from '../src/lib/beallitasok/tipusok';
import { nyelv } from '../src/lib/i18n';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { vaultKereses } from '../src/lib/kereses/vaultKereses.svelte';
import { Regiszter } from '../src/lib/parancsok/regiszter';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';
import { bovitmenyek } from '../src/szerkeszto/beallitas';
import { szerkesztoTelepit } from '../src/szerkeszto';
import { cimkeAt } from '../src/szerkeszto/linkek/cimkek';
import { cimkeKeres, navigacioBeallit } from '../src/szerkeszto/linkek/navigacio';
import { obsidianElemzo } from '../src/szerkeszto/markdown/elemzo';
import { dokumentumRenderel } from '../src/szerkeszto/olvaso/html';
import { LustaRajzolo } from '../src/szerkeszto/olvaso/lusta';
import ListaMezo from '../src/szerkeszto/tulajdonsagok/ListaMezo.svelte';

const keresesek: string[] = [];
const nezetek: EditorView[] = [];
const takaritok: (() => void)[] = [];
function beallit(engedelyezett = true, kereses = true) {
  const ertek = alapBeallitasok(); ertek.modulok.cimkek = engedelyezett;
  ertek.modulok.kereses = kereses;
  beallitasok.fogad({ verzio: 1, rev: 'fixture', ertek, munkater: { id: 'fixture', nev: 'Fixture', vault: '/synthetic' }, setup_szukseges: false, ujrainditas: [] });
}
beforeEach(() => {
  keresesek.length = 0; nyelv.beallit('en'); beallit();
  navigacioBeallit({ megnyit() {}, keresCimke: c => keresesek.push(c) });
});
afterEach(() => {
  cleanup(); takaritok.splice(0).forEach(f => f()); nezetek.splice(0).forEach(v => v.destroy());
  navigacioBeallit(null); beallitasok.adat = null; nyelv.beallit('hu');
  document.body.textContent = ''; vi.restoreAllMocks();
});
function nezet(mod: 'elo' | 'forras', kurzor?: number) {
  const doc = 'Text #alpha/beta\n\nEnd';
  const v = new EditorView({ parent: document.body, state: EditorState.create({ doc, selection: { anchor: kurzor ?? doc.length }, extensions: bovitmenyek({ mod, csakOlvashato: false, ut: 'Host.md', cimke: 'Note' }) }) });
  ensureSyntaxTree(v.state, doc.length, 5000); nezetek.push(v);
  vi.spyOn(v, 'posAtCoords').mockReturnValue(9);
  return v;
}
function olvaso(doc: string) {
  const el = document.createElement('article'); document.body.append(el);
  const lusta = LustaRajzolo.azonnali(); takaritok.push(() => lusta.leall());
  el.append(dokumentumRenderel(obsidianElemzo.parse(doc), { ut: 'Host.md', olvas: (a, b) => doc.slice(a, b), lusta }));
  return el;
}

describe('törzs-címke megjelenítés és keresés', () => {
  it('LP/Source a közös Hashtag node-ot stílusozza és célozza', () => {
    for (const mod of ['elo', 'forras'] as const) {
      const v = nezet(mod);
      expect(v.dom.querySelector('.cm-cimke')?.textContent).toBe('#alpha/beta');
      expect(cimkeAt(v.state, 9)).toEqual({ cimke: 'alpha/beta', from: 5, to: 16 });
      const esem = new MouseEvent('mousedown', { bubbles: true, cancelable: true, button: 0, metaKey: mod === 'forras' });
      v.dom.querySelector('.cm-cimke')!.dispatchEvent(esem);
      expect(esem.defaultPrevented).toBe(true);
      expect(v.state.doc.toString()).toBe('Text #alpha/beta\n\nEnd');
    }
    expect(keresesek).toEqual(['alpha/beta', 'alpha/beta']);
  });

  it('Reader egérrel és Enterrel keres, forrást nem módosít; nested linkben nincs interaktív címke', async () => {
    const el = olvaso('Text #alpha/beta és [label #inside](Target.md).');
    const a = el.querySelector<HTMLElement>('a.cimke')!;
    expect(a.dataset.cimke).toBe('alpha/beta'); expect(a.getAttribute('href')).toBeNull();
    await fireEvent.click(a); await fireEvent.keyDown(a, { key: 'Enter' });
    expect(keresesek).toEqual(['alpha/beta', 'alpha/beta']);
    expect(el.querySelector('a.link a')).toBeNull();
    expect(el.querySelector('a.link .cimke')?.tagName).toBe('SPAN');
    expect(el.querySelector('a.link [data-cimke]')).toBeNull();
  });

  it('modul kikapcsolva nincs címke-navigáció, Readerben fókuszálható címke sem készül', () => {
    beallit(false);
    expect(cimkeKeres('alpha')).toBe(false);
    const el = olvaso('Text #alpha');
    expect(el.querySelector('a.cimke')).toBeNull(); expect(el.textContent).toBe('Text #alpha');
    expect(keresesek).toEqual([]);
  });

  it('kikapcsolt keresővel a címke és a tulajdonságchip is olvasható szöveg marad', () => {
    beallit(true, false);
    expect(cimkeKeres('alpha')).toBe(false);
    expect(olvaso('Text #alpha').querySelector('a.cimke')).toBeNull();
    render(ListaMezo, { props: { elemek: ['alpha'], cimke: 'Tags', irhato: false, cimkes: true, onvaltozas: vi.fn() } });
    expect(screen.queryByRole('button', { name: /Search for tag/ })).toBeNull();
    expect(keresesek).toEqual([]);
  });

  it('hibás örökölt címke nem alakítható más keresőoperátorrá', () => {
    for (const c of ['a OR b', 'a" file:secret', '#', '123', 'a\nb']) expect(cimkeKeres(c)).toBe(false);
    expect(keresesek).toEqual([]);
  });

  it('valódi regisztráció a közös keresőt nyitja a teljes nested tag operátorral', () => {
    const felulet = new Felulet();
    const le = szerkesztoTelepit(new Regiszter(), new CoreKapcsolat('ws://fixture'), felulet, new VaultFajlok()); takaritok.push(le);
    expect(cimkeKeres('alpha/beta')).toBe(true);
    expect(felulet.atfedes).toBe('kereso');
    expect(vaultKereses.q).toBe('tag:#alpha/beta');
  });
});

describe('tulajdonság-címke chip', () => {
  it('olvasási módban is kereshető, és az értéket/törlést nem módosítja', async () => {
    const valtozas = vi.fn();
    render(ListaMezo, { props: { elemek: ['alpha/beta'], cimke: 'Tags', irhato: false, cimkes: true, onvaltozas: valtozas } });
    await fireEvent.click(screen.getByRole('button', { name: 'Search for tag: #alpha/beta' }));
    expect(keresesek).toEqual(['alpha/beta']); expect(valtozas).not.toHaveBeenCalled();
    expect(screen.queryByRole('textbox')).toBeNull();
  });
  it('alias és általános listaelem nem válik címkévé', () => {
    render(ListaMezo, { props: { elemek: ['alpha/beta'], cimke: 'Aliases', irhato: false, onvaltozas: vi.fn() } });
    expect(screen.queryByRole('button', { name: /Search for tag/ })).toBeNull();
  });
});
