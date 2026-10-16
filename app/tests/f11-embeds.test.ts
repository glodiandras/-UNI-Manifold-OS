import { ensureSyntaxTree } from '@codemirror/language';
import { EditorState, Text } from '@codemirror/state';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { linkek } from '../src/lib/vault/linkek.svelte';
import { ApiHiba } from '../src/lib/core/api';
import { bovitmenyek } from '../src/szerkeszto/beallitas';
import { beagyazottFeladatValt } from '../src/szerkeszto/beagyazas/feladat';
import type { EditorView } from '@codemirror/view';
import { BeagyazasWidget, tartalomVerzioValt } from '../src/szerkeszto/beagyazas/widget';
import { Dokumentum } from '../src/szerkeszto/dokumentum/dokumentum.svelte';
import type { FajlIrasKeres } from '../src/szerkeszto/dokumentum/api';
import { blokkMezo } from '../src/szerkeszto/elo/blokkok';
import { mediaHorgony } from '../src/szerkeszto/linkek/adat';
import { obsidianElemzo } from '../src/szerkeszto/markdown/elemzo';
import { dokumentumRenderel } from '../src/szerkeszto/olvaso/html';
import { LustaRajzolo } from '../src/szerkeszto/olvaso/lusta';
import { szerkesztok } from '../src/szerkeszto/szerkesztok.svelte';

const kerelmek: URL[] = [];
let tartalom = '';
let kezd = 1;
function render(szoveg: string, csakOlvashato = false) {
  const kont = document.createElement('article');
  document.body.appendChild(kont);
  kont.appendChild(dokumentumRenderel(obsidianElemzo.parse(szoveg), {
    olvas: (a, b) => szoveg.slice(a, b), ut: 'Folder/Host.md', lusta: LustaRajzolo.azonnali(), csakOlvashato,
  }));
  return kont;
}

beforeEach(() => {
  kerelmek.length = 0;
  tartalom = '';
  kezd = 1;
  linkek.mediaToken = 'tok';
  vi.stubGlobal('fetch', async (url: string) => {
    const u = new URL(url, 'http://127.0.0.1/');
    kerelmek.push(u);
    const cel = u.searchParams.get('cel')!;
    return new Response(JSON.stringify(cel.endsWith('.png')
      ? { tipus: 'kep', ut: cel.replace(/^\.\.\//, '') }
      : { tipus: 'jegyzet', ut: 'Target.md', szoveg: tartalom, kezd }), { headers: { 'Content-Type': 'application/json' } });
  });
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  document.body.replaceChildren();
});

describe('F11: helyi Markdown-kép és média méretek', () => {
  it('Reader: a helyi Markdown-hivatkozás ugyanazt az út/horgony navigációt kapja, a formázása megmarad', () => {
    const k = render('[A **section**](<../Other%20note.md#A%20heading>) és [same](#Here)');
    const [masik, ugyanaz] = k.querySelectorAll<HTMLElement>('.wikilink');
    expect(masik.dataset).toMatchObject({ cel: '../Other note.md', alcel: 'A heading', forras: 'Folder/Host.md' });
    expect(masik.querySelector('strong')!.textContent).toBe('section');
    expect(masik.getAttribute('href')).toBeNull();
    expect(ugyanaz.dataset).toMatchObject({ cel: '', alcel: 'Here' });
  });
  it('Reader: a dekódolt út a közös core-feloldáshoz megy, a méret és alt külön marad', async () => {
    const k = render('![A diagram|300x200](<../Assets/a%20b%23c.png>)');
    await vi.waitFor(() => expect(k.querySelector('img')).not.toBeNull());
    expect(kerelmek[0].searchParams.get('forras')).toBe('Folder/Host.md');
    expect(kerelmek[0].searchParams.get('cel')).toBe('../Assets/a b#c.png');
    const kep = k.querySelector('img')!;
    expect(kep.alt).toBe('A diagram');
    expect(kep.width).toBe(300);
    expect(kep.height).toBe(200);
    expect(kep.getAttribute('src')).toBe('/media/tok/Assets/a%20b%23c.png?w=400');
  });

  it('külső és tiltott séma: sem core-lekérés, sem img hálózati kérés nem indul', () => {
    const k = render('![remote](https://example.com/a.png)\n\n![bad](javascript:alert)');
    expect(k.querySelectorAll('img')).toHaveLength(0);
    expect(k.querySelectorAll('.beagyazas-kulso')).toHaveLength(2);
    expect(kerelmek).toHaveLength(0);
  });

  it.each([
    ['page=3&height=400', { page: 3, height: 400 }],
    ['height=280&page=2', { height: 280, page: 2 }],
    ['height=0&page=-2', {}],
    ['height=320junk&page=2x', {}],
    ['t=1:02:03&height=300', { t: 3723, height: 300 }],
    ['t=12:40,20', { t: 760 }],
  ])('média-horgony %s', (nyers, vart) => expect(mediaHorgony(nyers)).toEqual(vart));
});

describe('F11: stabil Live Preview beágyazás', () => {
  function allapot(szoveg: string, pos: number) {
    const s = EditorState.create({ doc: szoveg, selection: { anchor: pos }, extensions: bovitmenyek({ mod: 'elo', csakOlvashato: false, ut: 'Host.md', cimke: 'Host' }) });
    ensureSyntaxTree(s, s.doc.length, 5000);
    return s.update({ selection: { anchor: pos } }).state;
  }
  it.each(['![[Picture.png]]', '![alt](Picture.png)'])('az aktív önálló %s forrása alatt megmarad a preview', (szoveg) => {
    const s = allapot(szoveg + '\n\nEnd', 3);
    const d: Array<{ from: number; to: number; blokk: boolean }> = [];
    s.field(blokkMezo).between(0, s.doc.length, (from, to, v) => {
      if (v.spec.widget instanceof BeagyazasWidget) d.push({ from, to, blokk: !!v.spec.block });
    });
    expect(d).toEqual([{ from: szoveg.length, to: szoveg.length, blokk: true }]);
    expect(s.doc.toString()).toBe(szoveg + '\n\nEnd');
  });

  it('külső tartalomváltozáskor a widget azonossága változik, a dokumentum és kurzor megmarad', () => {
    const s = allapot('![[Target]]\n\nEnd', 15);
    let regi: BeagyazasWidget | null = null;
    s.field(blokkMezo).between(0, s.doc.length, (_f, _t, v) => { if (v.spec.widget instanceof BeagyazasWidget) regi = v.spec.widget; });
    linkek.tartalomVerzio++;
    const uj = s.update({ effects: tartalomVerzioValt.of(linkek.tartalomVerzio) }).state;
    let most: BeagyazasWidget | null = null;
    uj.field(blokkMezo).between(0, uj.doc.length, (_f, _t, v) => { if (v.spec.widget instanceof BeagyazasWidget) most = v.spec.widget; });
    expect(regi).not.toBeNull();
    expect(most).not.toBeNull();
    expect((regi! as BeagyazasWidget).eq(most!)).toBe(false);
    expect(uj.doc.eq(s.doc)).toBe(true);
    expect(uj.selection.eq(s.selection)).toBe(true);
  });

  it.each([
    '%%\nHidden comment\n%%\n\nVisible',
    'Before %%hidden\ncomment%% after\n\nVisible',
  ])('a többsoros komment LP-ban forrás marad, csak az Olvasó rejti el: %s', (szoveg) => {
    const s = allapot(szoveg, szoveg.length);
    let rejtett = 0;
    s.field(blokkMezo).between(0, s.doc.length, (from, to) => { if (to > from) rejtett++; });
    expect(rejtett).toBe(0);
    const aktiv = s.update({ selection: { anchor: szoveg.indexOf('%%') + 2 } }).state;
    let aktivRejtett = 0;
    aktiv.field(blokkMezo).between(0, aktiv.doc.length, (from, to) => { if (to > from) aktivRejtett++; });
    expect(aktivRejtett).toBe(0);
    const olvaso = render(szoveg);
    expect(olvaso.textContent).not.toContain('comment');
    expect(olvaso.textContent).toContain('Visible');
  });
});

describe('F11: beágyazott feladat célbiztonsága', () => {
  const teljes = '---\ntitle: Tasks\n---\n\n## Tasks\n- [ ] Target\n';
  function dokumentum(szoveg = teljes, ut = 'Target.md') {
    const api = { olvas: vi.fn(), ir: vi.fn(async (k: FajlIrasKeres) => ({ ok: true, ut: k.ut, hash: 'saved', git: true, pillanat: 'snapshot', jel: '', uzenet: '', elotte: null })) };
    const d = new Dokumentum(api, { ut, tartalom: szoveg, hash: 'base', jel: '', mtime: 0 });
    vi.spyOn(d, 'kulsoValtozas').mockResolvedValue();
    return { d, api };
  }

  it('fejezet szeletből kizárólag a cél változik, másik panel szinkronizál és a rendes CAS mentés fut', async () => {
    tartalom = '## Tasks\n- [ ] Target\n'; kezd = 5;
    const { d, api } = dokumentum();
    const alkalmaz = vi.fn();
    const le = d.csatol({ alkalmaz });
    vi.spyOn(szerkesztok.dokumentumok, 'megnyit').mockResolvedValue(d);
    const k = render('- [ ] Host\n\n![[Target#Tasks]]');
    await vi.waitFor(() => expect(k.querySelector('.beagyazas-torzs input')).not.toBeNull());
    const jel = k.querySelector<HTMLInputElement>('.beagyazas-torzs input')!;
    const buborek = vi.fn(); k.addEventListener('change', buborek);
    jel.checked = true; jel.dispatchEvent(new Event('change', { bubbles: true }));
    await vi.waitFor(() => expect(api.ir).toHaveBeenCalledTimes(1));
    expect(api.ir.mock.calls[0][0]).toMatchObject({ ut: 'Target.md', alap: 'base', tartalom: teljes.replace('[ ]', '[x]') });
    expect(alkalmaz).toHaveBeenCalledTimes(1);
    expect(alkalmaz.mock.calls[0][1]).toBe(true);
    expect(k.querySelector<HTMLInputElement>('input')!.checked).toBe(false);
    expect(buborek).not.toHaveBeenCalled();
    le(); await d.lezar();
  });

  it('azonos [ ] egy másik helyen sem elég: elavult szeletnél nincs írás', async () => {
    tartalom = '## Tasks\n- [ ] Target\n'; kezd = 5;
    const { d, api } = dokumentum('Shifted\n' + teljes);
    vi.spyOn(szerkesztok.dokumentumok, 'megnyit').mockResolvedValue(d);
    const k = render('![[Target#Tasks]]');
    await vi.waitFor(() => expect(k.querySelector('input')).not.toBeNull());
    const jel = k.querySelector<HTMLInputElement>('input')!;
    jel.checked = true; jel.dispatchEvent(new Event('change', { bubbles: true }));
    await vi.waitFor(() => expect(k.querySelector('.beagyazas-feladat-hiba')).not.toBeNull());
    expect(api.ir).not.toHaveBeenCalled();
    expect(jel.checked).toBe(false);
    expect(d.szoveg.toString()).toBe('Shifted\n' + teljes);
  });

  it('read-only fogadó nézetben a beágyazott feladat sem írható', async () => {
    tartalom = '- [ ] Task';
    const k = render('![[Target]]', true);
    await vi.waitFor(() => expect(k.querySelector('input')).not.toBeNull());
    expect(k.querySelector<HTMLInputElement>('input')!.disabled).toBe(true);
  });

  it('mentési ütközésnél a cél változása megmarad, hiba látszik, a befogadó változatlan', async () => {
    tartalom = '- [ ] Target'; kezd = 1;
    const { d, api } = dokumentum(tartalom);
    api.ir.mockRejectedValue(new ApiHiba(409, 'Conflict', { utkozes: true, hash: 'new' }));
    vi.spyOn(szerkesztok.dokumentumok, 'megnyit').mockResolvedValue(d);
    const k = render('- [ ] Host\n\n![[Target]]');
    await vi.waitFor(() => expect(k.querySelector('.beagyazas-torzs input')).not.toBeNull());
    const jel = k.querySelector<HTMLInputElement>('.beagyazas-torzs input')!;
    jel.checked = true; jel.dispatchEvent(new Event('change', { bubbles: true }));
    await vi.waitFor(() => expect(k.querySelector('.beagyazas-feladat-hiba')).not.toBeNull());
    expect(d.allapot).toBe('utkozes');
    expect(d.szoveg.toString()).toBe('- [x] Target');
    expect(jel.checked).toBe(true);
    expect(k.querySelector<HTMLInputElement>('input')!.checked).toBe(false);
  });


  it('a külső widget megszűnése a belső beágyazás függő feladatnyitását is megszakítja', async () => {
    vi.stubGlobal('fetch', async (url: string) => {
      const cel = new URL(url, 'http://127.0.0.1/').searchParams.get('cel');
      const adat = cel === 'Outer'
        ? { tipus: 'jegyzet', ut: 'Outer.md', szoveg: '![[Inner]]', kezd: 1 }
        : { tipus: 'jegyzet', ut: 'Inner.md', szoveg: '- [ ] Inner', kezd: 1 };
      return new Response(JSON.stringify(adat), { headers: { 'Content-Type': 'application/json' } });
    });
    const { d, api } = dokumentum('- [ ] Inner', 'Inner.md');
    let nyitva!: (d: Dokumentum) => void;
    const megnyit = vi.spyOn(szerkesztok.dokumentumok, 'megnyit').mockReturnValue(new Promise(r => { nyitva = r; }));
    const widget = new BeagyazasWidget({ cel: 'Outer', alcel: null, alias: null, beagyazas: true, from: 0, to: 10 }, 'Host.md', linkek.verzio, true);
    const kont = widget.toDOM({ state: { readOnly: false }, requestMeasure: vi.fn() } as unknown as EditorView);
    document.body.appendChild(kont);
    await vi.waitFor(() => expect(kont.querySelector('input')).not.toBeNull());
    const jel = kont.querySelector<HTMLInputElement>('input')!;
    expect(jel.dataset.jeloloUt).toBe('Inner.md');
    jel.checked = true; jel.dispatchEvent(new Event('change', { bubbles: true }));
    await vi.waitFor(() => expect(megnyit).toHaveBeenCalledWith('Inner.md'));
    widget.destroy(kont); kont.remove();
    nyitva(d);
    await new Promise(r => setTimeout(r, 0));
    await d.kivar();
    expect(d.szoveg.toString()).toBe('- [ ] Inner');
    expect(api.ir).not.toHaveBeenCalled();
  });

  it('hibás kezdő sor/pozíció és ütköző cél nem írható', async () => {
    const { d } = dokumentum('- [ ] Task');
    expect(beagyazottFeladatValt(d, 0, '- [ ] Task', 2)).toBeNull();
    expect(beagyazottFeladatValt(d, 1, '- [ ] Task', -1)).toBeNull();
    d.allapot = 'utkozes';
    expect(beagyazottFeladatValt(d, 1, '- [ ] Task', 2)).toBeNull();
    expect(d.szoveg.eq(Text.of(['- [ ] Task']))).toBe(true);
  });
});
