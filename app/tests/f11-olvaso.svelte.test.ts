import { EditorState } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import { cleanup, render } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, expect, it, vi } from 'vitest';
import { linkek } from '../src/lib/vault/linkek.svelte';
import Olvaso from '../src/szerkeszto/Olvaso.svelte';
import { Dokumentum } from '../src/szerkeszto/dokumentum/dokumentum.svelte';

const nezetek: EditorView[] = [];
afterEach(() => {
  cleanup();
  for (const v of nezetek.splice(0)) v.destroy();
  vi.useRealTimers();
  vi.restoreAllMocks(); vi.unstubAllGlobals();
});

function olvaso(szoveg: string) {
  const view = new EditorView({ state: EditorState.create({ doc: szoveg }) }); nezetek.push(view);
  const dok = new Dokumentum({ olvas: vi.fn(), ir: vi.fn() }, { ut: 'Host.md', tartalom: szoveg, hash: 'host', jel: '', mtime: 0 });
  const eredmeny = render(Olvaso, { props: { view, dok, ut: 'Host.md', valtozat: 0 } });
  return { ...eredmeny, view, dok };
}

it('a Reader egy külső célmentés után újraolvassa a beágyazást és megőrzi a görgetést', async () => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
  const tartalmak: Record<string, string> = { Target: 'First version', Untouched: 'Keep this embed' };
  const kertek: string[] = [];
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), 'http://localhost');
    expect(url.pathname).toBe('/api/vault/beagyazas');
    expect(url.searchParams.get('forras')).toBe('Host.md');
    const cel = url.searchParams.get('cel')!;
    expect(tartalmak).toHaveProperty(cel);
    kertek.push(cel);
    return new Response(JSON.stringify({ tipus: 'jegyzet', ut: `${cel}.md`, szoveg: tartalmak[cel], kezd: 1 }), { headers: { 'Content-Type': 'application/json' } });
  }));
  const forras = '![[Target]]\n\n![[Untouched]]';
  const { container, view } = olvaso(forras);
  const beagyazas = (cel: string) => container.querySelector<HTMLElement>(`.beagyazas[data-cel="${cel}"]`)!;
  const szoveg = (cel: string) => beagyazas(cel)?.querySelector('.beagyazas-torzs')?.textContent;
  await vi.waitFor(() => {
    expect(szoveg('Target')).toContain('First version');
    expect(szoveg('Untouched')).toContain('Keep this embed');
  });
  // Az onMount rajza után a kezdeti $effect is ütemez rajzot. Ez záruljon le az eseményenkénti mérés ELŐTT.
  await vi.runOnlyPendingTimersAsync();
  await vi.waitFor(() => {
    expect(szoveg('Target')).toContain('First version');
    expect(szoveg('Untouched')).toContain('Keep this embed');
  });
  const gorgeto = container.querySelector<HTMLElement>('.olvaso-gorgeto')!;
  gorgeto.scrollTop = 47;
  const kezdetiKeresek = [...kertek];
  const celDom = beagyazas('Target');
  const masikDom = beagyazas('Untouched');
  const masikTorzs = masikDom.querySelector('.beagyazas-torzs');
  linkek.tartalomValtozott(['Other.md']);   // 04-embeds-07: nem beágyazott cél mentése egyiket sem olvassa újra.
  await tick();
  await vi.runOnlyPendingTimersAsync();
  expect(kertek).toEqual(kezdetiKeresek);
  expect(beagyazas('Target')).toBe(celDom);
  expect(beagyazas('Untouched')).toBe(masikDom);
  expect(szoveg('Target')).toContain('First version');

  tartalmak.Target = 'External update';
  linkek.tartalomValtozott(['Target.md']);
  await vi.waitFor(() => expect(szoveg('Target')).toContain('External update'));
  await vi.runOnlyPendingTimersAsync();
  expect(kertek).toEqual([...kezdetiKeresek, 'Target']);
  expect(beagyazas('Untouched')).toBe(masikDom);
  expect(masikDom.querySelector('.beagyazas-torzs')).toBe(masikTorzs);
  expect(szoveg('Untouched')).toContain('Keep this embed');
  expect(gorgeto.scrollTop).toBe(47);
  expect(view.state.doc.toString()).toBe(forras);
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
