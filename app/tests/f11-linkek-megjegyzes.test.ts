import { ensureSyntaxTree } from '@codemirror/language';
import { EditorState } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { LinkSzolgaltatas } from '../src/lib/vault/linkek.svelte';
import { bovitmenyek } from '../src/szerkeszto/beallitas';
import { markdownCel } from '../src/szerkeszto/linkek/markdown';
import { linkAt } from '../src/szerkeszto/linkek/szerkeszto';
import { obsidianElemzo } from '../src/szerkeszto/markdown/elemzo';
import { dokumentumRenderel } from '../src/szerkeszto/olvaso/html';
import { LustaRajzolo } from '../src/szerkeszto/olvaso/lusta';

const nezetek: EditorView[] = [];
afterEach(() => { for (const v of nezetek.splice(0)) v.destroy(); document.body.textContent = ''; vi.unstubAllGlobals(); });
function nezet(doc: string, kurzor = doc.length, mod: 'elo' | 'forras' = 'elo'): EditorView {
  const parent = document.createElement('div'); document.body.append(parent);
  const view = new EditorView({ parent, state: EditorState.create({ doc, selection: { anchor: kurzor }, extensions: bovitmenyek({ mod, ut: 'Folder/Host.md', cimke: 'Note', csakOlvashato: false }) }) });
  ensureSyntaxTree(view.state, doc.length, 5000); nezetek.push(view); return view;
}

describe('helyi Markdown-célok', () => {
  it.each([
    ['../Notes/A%20B.md#Els%C5%91%20r%C3%A9sz', { cel: '../Notes/A B.md', alcel: 'Első rész' }],
    ['<A%23B%3FC.md#^block>', { cel: 'A#B?C.md', alcel: '^block' }],
    ['#Heading', { cel: '', alcel: 'Heading' }],
    ['A%2520B.md', { cel: 'A%20B.md', alcel: null }],
    ['A\\(B\\).md', { cel: 'A(B).md', alcel: null }],
  ])('egyszer bont és dekódol: %s', (url, cel) => expect(markdownCel(url)).toEqual(cel));
  it.each(['https://example.com/a', 'mailto:a@example.com', 'javascript:alert(1)', 'file:///a.md', '//example.com/a', 'javascript%3Aalert(1)', '%2F%2Fexample.com/a', 'A%00.md', 'bad%zz.md', ''])('külső vagy hibás cél nem jut a vault API-ba: %s', url => expect(markdownCel(url)).toBeNull());
  it('Link node belső, külső és kép célját megkülönbözteti mindkét szerkesztőmódban', () => {
    const doc = '[Felirat](../Target%20Note.md#Section) [web](https://example.com) ![alt](pic.png)';
    for (const mod of ['elo', 'forras'] as const) {
      const v = nezet(doc, 3, mod);
      expect(linkAt(v.state, 3)).toMatchObject({ cel: '../Target Note.md', alcel: 'Section', alias: 'Felirat', beagyazas: false });
      expect(linkAt(v.state, doc.indexOf('web') + 1)).toBeNull();
      expect(linkAt(v.state, doc.indexOf('alt') + 1)).toBeNull();
    }
  });
  it('Live Preview csak a feliratot mutatja, az aktív sor visszaadja a teljes forrást', () => {
    const doc = '[**Felirat**](<Target%20Note.md#Section> "title")\n\nEnd';
    const v = nezet(doc);
    const sor = () => v.dom.querySelector('.cm-line')!.textContent;
    expect(sor()).toBe('Felirat');
    expect(v.dom.querySelector('.cm-felkover')?.textContent).toBe('Felirat');
    v.dispatch({ selection: { anchor: 4 } });
    expect(sor()).toBe(doc.split('\n')[0]);
  });
  it('Reader azonos core-feloldásra alkalmas DOM-adatokat ad', () => {
    const doc = '[Felirat](Target%20Note.md#Heading)';
    const elem = dokumentumRenderel(obsidianElemzo.parse(doc), { ut: 'Folder/Host.md', olvas: (a, b) => doc.slice(a, b), lusta: LustaRajzolo.azonnali() });
    const a = elem.querySelector<HTMLElement>('.wikilink')!;
    expect(a.textContent).toBe('Felirat');
    expect(a.dataset).toMatchObject({ cel: 'Target Note.md', alcel: 'Heading', forras: 'Folder/Host.md' });
  });
});

describe('Obsidian %% megjegyzések', () => {
  it('az opaque soron belüli és üres sorokon átívelő blokk nem értelmezi a belső linket/képletet', () => {
    const doc = 'Visible %%secret [[Hidden]] $x$%% text\n\n%%\n# Hidden\n\n![[Hidden]]\n%%\n\nEnd';
    const fa = obsidianElemzo.parse(doc);
    const nevek: string[] = []; fa.iterate({ enter(n) { nevek.push(n.name); } });
    expect(nevek).toContain('ObsidianComment'); expect(nevek).toContain('ObsidianCommentBlock');
    expect(nevek).not.toContain('Wikilink'); expect(nevek).not.toContain('InlineMath'); expect(nevek).not.toContain('Embed');
    const elem = dokumentumRenderel(fa, { ut: 'Host.md', olvas: (a, b) => doc.slice(a, b), lusta: LustaRajzolo.azonnali() });
    expect(elem.textContent).toContain('Visible  text'); expect(elem.textContent).not.toContain('secret'); expect(elem.textContent).not.toContain('Hidden'); expect(elem.textContent).toContain('End');
  });
  it('kód, frontmatter, escape és lezáratlan jelölő szöveg marad', () => {
    for (const doc of ['---\nvalue: %%yaml%%\n---', '`%%code%%`', '```md\n%%fence%%\n```', '\\%%escaped%%', '%%open']) {
      const nevek: string[] = []; obsidianElemzo.parse(doc).iterate({ enter(n) { nevek.push(n.name); } });
      expect(nevek.filter(n => n.startsWith('ObsidianComment'))).toEqual([]);
    }
  });
  it('LP halvány forrásként tartja meg, Source megőrzi a megjegyzést', () => {
    const doc = 'Visible %%secret%% text\n\nEnd';
    const v = nezet(doc);
    expect(v.dom.querySelector('.cm-line')?.textContent).toBe('Visible %%secret%% text');
    expect(v.dom.querySelector('.cm-jelolo')?.textContent).toBe('%%secret%%');
    v.dispatch({ selection: { anchor: 12 } });
    expect(v.dom.querySelector('.cm-line')?.textContent).toContain('%%secret%%');
    expect(nezet(doc, doc.length, 'forras').dom.textContent).toContain('%%secret%%');
  });
});

it('ismert fájl mentése a beágyazásokat frissíti, de a feloldási cache-t megőrzi', () => {
  const szolg = new LinkSzolgaltatas();
  const figyelok = new Map<string, (e: Record<string, unknown>) => void>();
  const le = vi.fn();
  const k = { figyel: (tipus: string, fn: (e: Record<string, unknown>) => void) => { figyelok.set(tipus, fn); return le; } } as unknown as CoreKapcsolat;
  const leallit = szolg.figyel(k, ut => ut === 'Known.md');
  figyelok.get('vault_valtozas')!({ utak: ['Known.md'] });
  expect(szolg.tartalomVerzio).toBe(1); expect(szolg.verzio).toBe(0);
  figyelok.get('vault_valtozas')!({ utak: ['New.md'] });
  expect(szolg.tartalomVerzio).toBe(2); expect(szolg.verzio).toBe(1);
  figyelok.get('hello')!({ media_token: 'new' });
  expect(szolg.tartalomVerzio).toBe(3); expect(szolg.mediaToken).toBe('new');
  leallit(); expect(le).toHaveBeenCalledTimes(2);
});
