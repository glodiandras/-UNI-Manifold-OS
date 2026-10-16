import { EditorState } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import { cleanup, render } from '@testing-library/svelte';
import { afterEach, expect, it, vi } from 'vitest';
import { linkek } from '../src/lib/vault/linkek.svelte';
import Olvaso from '../src/szerkeszto/Olvaso.svelte';
import { Dokumentum } from '../src/szerkeszto/dokumentum/dokumentum.svelte';

const nezetek: EditorView[] = [];
afterEach(() => {
  cleanup();
  for (const v of nezetek.splice(0)) v.destroy();
  vi.restoreAllMocks(); vi.unstubAllGlobals();
});

function olvaso(szoveg: string) {
  const view = new EditorView({ state: EditorState.create({ doc: szoveg }) }); nezetek.push(view);
  const dok = new Dokumentum({ olvas: vi.fn(), ir: vi.fn() }, { ut: 'Host.md', tartalom: szoveg, hash: 'host', jel: '', mtime: 0 });
  const eredmeny = render(Olvaso, { props: { view, dok, ut: 'Host.md', valtozat: 0 } });
  return { ...eredmeny, view, dok };
}

it('a Reader egy külső célmentés után újraolvassa a beágyazást és megőrzi a görgetést', async () => {
  let szoveg = 'First version';
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ tipus: 'jegyzet', ut: 'Target.md', szoveg, kezd: 1 }), { headers: { 'Content-Type': 'application/json' } })));
  const { container, view } = olvaso('![[Target]]');
  await vi.waitFor(() => expect(container.querySelector('.beagyazas-torzs')?.textContent).toContain('First version'));
  const gorgeto = container.querySelector<HTMLElement>('.olvaso-gorgeto')!;
  gorgeto.scrollTop = 47;
  const fetchHivas = vi.mocked(fetch).mock.calls.length;
  szoveg = 'Unrelated'; linkek.tartalomValtozott(['Other.md']);   // 04-embeds-07: más cél mentése nem rajzol újra
  await new Promise((r) => setTimeout(r, 20));
  expect(vi.mocked(fetch).mock.calls.length).toBe(fetchHivas);
  expect(container.querySelector('.beagyazas-torzs')?.textContent).toContain('First version');
  szoveg = 'External update'; linkek.tartalomValtozott(['Target.md']);
  await vi.waitFor(() => expect(container.querySelector('.beagyazas-torzs')?.textContent).toContain('External update'));
  expect(gorgeto.scrollTop).toBe(47);
  expect(view.state.doc.toString()).toBe('![[Target]]');
});

it('a beágyazott vagy idegen útvonalú jelölő szövegeltolása soha nem írhatja a befogadó jegyzetet', () => {
  const { container, view, dok } = olvaso('- [ ] Host');
  const article = container.querySelector('article')!;
  for (const beagyazas of [false, true]) {
    const jel = document.createElement('input'); jel.type = 'checkbox'; jel.className = 'feladat-jelolo';
    jel.dataset.jelolo = '2'; jel.dataset.jeloloUt = 'Target.md';
    if (beagyazas) jel.dataset.beagyazas = 'true';
    article.appendChild(jel);
    jel.checked = true; jel.dispatchEvent(new Event('change', { bubbles: true }));
  }
  expect(view.state.doc.toString()).toBe('- [ ] Host');
  expect(dok.szoveg.toString()).toBe('- [ ] Host');
});
