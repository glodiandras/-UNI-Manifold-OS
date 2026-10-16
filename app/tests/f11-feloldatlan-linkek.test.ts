import { ensureSyntaxTree } from '@codemirror/language';
import { EditorState } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { linkek, LinkSzolgaltatas } from '../src/lib/vault/linkek.svelte';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { linkVerzioValt } from '../src/szerkeszto/beagyazas/widget';
import { bovitmenyek, markdownNyelv } from '../src/szerkeszto/beallitas';
import { jegyzetUtja } from '../src/szerkeszto/elo/jegyzet';
import { feloldatlanJelol, feloldatlanLinkek } from '../src/szerkeszto/linkek/feloldatlan';

interface Varakozo { forras: string; celok: string[]; jel: AbortSignal; valasz: (r: Response) => void }
const varakozok: Varakozo[] = [];
const nezetek: EditorView[] = [];
const vezerlok: AbortController[] = [];
const pihen = (ms = 20) => new Promise(r => setTimeout(r, ms));
const valasz = (celok: string[], hianyzo: string[] = []) => new Response(JSON.stringify({ eredmenyek: celok.map(cel => ({ cel, ut: hianyzo.includes(cel) ? null : cel + '.md', tobbertelmu: false })) }), { headers: { 'Content-Type': 'application/json' } });

beforeEach(() => {
  varakozok.length = 0;
  linkek.ervenytelenit();
  vi.stubGlobal('fetch', (_url: string, o: RequestInit) => new Promise<Response>(resolve => {
    const keres = JSON.parse(String(o.body));
    varakozok.push({ ...keres, jel: o.signal, valasz: resolve });
  }));
});
afterEach(() => {
  for (const ac of vezerlok.splice(0)) ac.abort();
  for (const v of nezetek.splice(0)) v.destroy();
  // A mesterséges fetch szándékosan nem engedelmeskedik az abortnak: a késői válaszok is biztonságosak.
  for (const p of varakozok.splice(0)) p.valasz(valasz(p.celok));
  vi.unstubAllGlobals(); vi.restoreAllMocks();
  document.body.replaceChildren();
});

function nezet(doc: string, elo = false) {
  const s = EditorState.create({ doc, selection: { anchor: doc.length }, extensions: elo ? bovitmenyek({ mod: 'elo', csakOlvashato: false, ut: 'Folder/Host.md', cimke: 'Host' }) : [markdownNyelv(), jegyzetUtja.of('Folder/Host.md'), feloldatlanLinkek()] });
  ensureSyntaxTree(s, s.doc.length, 5000);
  const hely = document.createElement('div'); document.body.appendChild(hely);
  const v = new EditorView({ state: s, parent: hely }); nezetek.push(v);
  return v;
}
function reader(linkek: Array<{ cel: string; forras?: string }>) {
  const gyoker = document.createElement('article'); document.body.appendChild(gyoker);
  for (const { cel, forras = 'Folder/Host.md' } of linkek) {
    const e = document.createElement('span'); e.className = 'wikilink'; e.dataset.cel = cel; e.dataset.forras = forras; e.textContent = cel;
    gyoker.appendChild(e);
  }
  const ac = new AbortController(); vezerlok.push(ac);
  const le = feloldatlanJelol(gyoker, ac.signal);
  return { gyoker, ac, le };
}

describe('F11: megerősített hiányzó link a szerkesztőben', () => {
  it('Live Preview-ban az alias szövegét is megjelöli, miközben a forrásjelölés rejtve marad', async () => {
    const v = nezet('[[Missing|Readable alias]]\n\nEnd', true);
    await vi.waitFor(() => expect(varakozok).toHaveLength(1));
    varakozok[0].valasz(valasz(['Missing'], ['Missing']));
    await vi.waitFor(() => expect(v.dom.querySelector('.cm-wikilink-feloldatlan')?.textContent).toContain('Readable alias'));
    expect(v.dom.querySelector('.cm-line')?.textContent).not.toContain('[[');
  });
  it('csak a core által hiányzónak jelölt wiki és helyi Markdown-link halványul', async () => {
    const v = nezet('[[Present]] [[Missing|alias]] [local](../Missing.md) [remote](https://example.com)');
    expect(v.dom.querySelector('.cm-wikilink-feloldatlan')).toBeNull();
    await vi.waitFor(() => expect(varakozok).toHaveLength(1));
    expect(varakozok[0].forras).toBe('Folder/Host.md');
    expect(varakozok[0].celok).toEqual(['Present', 'Missing', '../Missing.md']);
    varakozok[0].valasz(valasz(varakozok[0].celok, ['Missing', '../Missing.md']));
    await vi.waitFor(() => expect(v.dom.querySelectorAll('.cm-wikilink-feloldatlan')).toHaveLength(2));
    expect([...v.dom.querySelectorAll('.cm-wikilink-feloldatlan')].map(e => e.textContent)).toEqual(['[[Missing|alias]]', '[local](../Missing.md)']);
  });

  it('kód, képlet, komment, beágyazás és kép nem kerül feloldásra', async () => {
    const v = nezet('[[Real]]\n\n`[[Inline code]]` $[[Math]]$ %%[[Comment]]%%\n\n![[Embed]] ![Image](Image.png)\n\n```md\n[[Fenced]]\n```\n\n$$\n[[BlockMath]]\n$$');
    await vi.waitFor(() => expect(varakozok).toHaveLength(1));
    expect(varakozok[0].celok).toEqual(['Real']);
    varakozok[0].valasz(valasz(['Real']));
    await pihen(); expect(v.dom.querySelector('.cm-wikilink-feloldatlan')).toBeNull();
  });

  it('API-hiba vagy hiányos válasz nem válik hiányzó fájllá', async () => {
    const v = nezet('[[Unknown]]');
    await vi.waitFor(() => expect(varakozok).toHaveLength(1));
    varakozok[0].valasz(new Response(JSON.stringify({ hiba: 'Index unavailable' }), { status: 503 }));
    await pihen(); expect(v.dom.querySelector('.cm-wikilink-feloldatlan')).toBeNull();
    linkek.ervenytelenit(); v.dispatch({ effects: linkVerzioValt.of(linkek.verzio) });
    await vi.waitFor(() => expect(varakozok).toHaveLength(2));
    varakozok[1].valasz(new Response(JSON.stringify({ eredmenyek: [] })));
    await pihen(); expect(v.dom.querySelector('.cm-wikilink-feloldatlan')).toBeNull();
  });

  it('új cél létrehozása után a halvány jelzés eltűnik', async () => {
    const v = nezet('[[Created later]]');
    await vi.waitFor(() => expect(varakozok).toHaveLength(1));
    varakozok[0].valasz(valasz(varakozok[0].celok, ['Created later']));
    await vi.waitFor(() => expect(v.dom.querySelector('.cm-wikilink-feloldatlan')).not.toBeNull());
    linkek.ervenytelenit(); v.dispatch({ effects: linkVerzioValt.of(linkek.verzio) });
    expect(v.dom.querySelector('.cm-wikilink-feloldatlan')).toBeNull();
    await vi.waitFor(() => expect(varakozok).toHaveLength(2));
    varakozok[1].valasz(valasz(varakozok[1].celok));
    await pihen(); expect(v.dom.querySelector('.cm-wikilink-feloldatlan')).toBeNull();
  });

  it('szövegeltolás és új cél közben a késői eredmény nem díszíti az új szöveget', async () => {
    const v = nezet('[[Old]]');
    await vi.waitFor(() => expect(varakozok).toHaveLength(1));
    v.dispatch({ changes: { from: 0, to: v.state.doc.length, insert: 'Shifted [[New]]' } });
    await vi.waitFor(() => expect(varakozok).toHaveLength(2));
    expect(varakozok[0].jel.aborted).toBe(true);
    varakozok[0].valasz(valasz(['Old'], ['Old']));
    await pihen(); expect(v.dom.querySelector('.cm-wikilink-feloldatlan')).toBeNull();
    varakozok[1].valasz(valasz(['New'], ['New']));
    await vi.waitFor(() => expect(v.dom.querySelector('.cm-wikilink-feloldatlan')?.textContent).toBe('[[New]]'));
    expect(v.state.doc.toString()).toBe('Shifted [[New]]');
  });
});

describe('F11: Reader hiányzólink-jelölés', () => {
  it('a beágyazott jegyzet linkje a saját forrásával oldódik fel; külső séma kimarad', async () => {
    const { gyoker } = reader([{ cel: 'Missing' }, { cel: 'Present', forras: 'Other/Embed.md' }, { cel: 'https://example.com' }]);
    await vi.waitFor(() => expect(varakozok).toHaveLength(2));
    for (const p of varakozok) p.valasz(valasz(p.celok, ['Missing']));
    await vi.waitFor(() => expect(gyoker.querySelector('.wikilink-feloldatlan')?.textContent).toBe('Missing'));
    expect(varakozok.map(p => p.forras)).toEqual(['Folder/Host.md', 'Other/Embed.md']);
    expect(gyoker.querySelectorAll('.wikilink-feloldatlan')).toHaveLength(1);
  });

  it('abort után a késői válasz nem módosít DOM-ot és új beágyazást sem figyel', async () => {
    const { gyoker, ac } = reader([{ cel: 'Missing' }]);
    await vi.waitFor(() => expect(varakozok).toHaveLength(1));
    ac.abort(); varakozok[0].valasz(valasz(['Missing'], ['Missing']));
    const uj = document.createElement('span'); uj.className = 'wikilink'; uj.dataset.cel = 'Later'; uj.dataset.forras = 'Host.md'; gyoker.appendChild(uj);
    await pihen(60);
    expect(gyoker.querySelector('.wikilink-feloldatlan')).toBeNull();
    expect(varakozok).toHaveLength(1);
  });

  it('később betöltött beágyazás új linkjeit is jelöli', async () => {
    const { gyoker } = reader([]);
    const uj = document.createElement('span'); uj.className = 'wikilink'; uj.dataset.cel = 'Later'; uj.dataset.forras = 'Embed.md'; gyoker.appendChild(uj);
    await vi.waitFor(() => expect(varakozok).toHaveLength(1));
    varakozok[0].valasz(valasz(['Later'], ['Later']));
    await vi.waitFor(() => expect(uj.classList.contains('wikilink-feloldatlan')).toBe(true));
  });

  it('nagy dokumentumnál 200 cél/csomag és legfeljebb két párhuzamos kérés fut', async () => {
    reader(Array.from({ length: 501 }, (_, i) => ({ cel: `N${i}` })));
    await vi.waitFor(() => expect(varakozok).toHaveLength(2));
    expect(varakozok.map(p => p.celok.length)).toEqual([200, 200]);
    await pihen(); expect(varakozok).toHaveLength(2);
    varakozok[0].valasz(valasz(varakozok[0].celok));
    await vi.waitFor(() => expect(varakozok).toHaveLength(3));
    expect(varakozok[2].celok).toHaveLength(101);
    for (const p of varakozok.slice(1)) p.valasz(valasz(p.celok));
  });
});

describe('F11: feloldáscache pontossága', () => {
  it('ismert jegyzet aliasának változása is érvényteleníti a korábbi hiányzó eredményt', async () => {
    const szolg = new LinkSzolgaltatas(), kapcsolat = new CoreKapcsolat('ws://example.invalid');
    const le = szolg.figyel(kapcsolat, () => true);
    const regi = szolg.feloldas('Host.md', ['New alias']);
    varakozok[0].valasz(valasz(['New alias'], ['New alias'])); await regi;
    kapcsolat.szetoszt({ tipus: 'vault_valtozas', utak: ['Existing.md'] });
    expect(szolg.verzio).toBe(0);
    const uj = szolg.feloldas('Host.md', ['New alias']);
    expect(varakozok).toHaveLength(2);
    varakozok[1].valasz(valasz(['New alias'])); expect((await uj)[0].ut).toBe('New alias.md');
    le();
  });
  it('a vegyes cache/új kérés megtartja a már feloldott célt és a többértelműség jelzését', async () => {
    const szolg = new LinkSzolgaltatas();
    const elso = szolg.feloldas('Folder/Host.md', ['Existing']);
    varakozok[0].valasz(new Response(JSON.stringify({ eredmenyek: [{ cel: 'Existing', ut: 'Existing.md', tobbertelmu: true }] })));
    await elso;
    const masodik = szolg.feloldas('Folder/Host.md', ['Existing', 'Missing']);
    expect(varakozok[1].celok).toEqual(['Missing']);
    varakozok[1].valasz(valasz(['Missing'], ['Missing']));
    expect(await masodik).toEqual([{ cel: 'Existing', ut: 'Existing.md', tobbertelmu: true }, { cel: 'Missing', ut: null, tobbertelmu: false }]);
  });

  it('az elavult kérés nem törli az időközben érkezett új cache-bejegyzést', async () => {
    const szolg = new LinkSzolgaltatas();
    const regi = szolg.feloldas('Host.md', ['Target']);
    szolg.ervenytelenit();
    const uj = szolg.feloldas('Host.md', ['Target']);
    varakozok[1].valasz(valasz(['Target'])); await uj;
    varakozok[0].valasz(valasz(['Target'], ['Target'])); await regi;
    expect((await szolg.feloldas('Host.md', ['Target']))[0].ut).toBe('Target.md');
    expect(varakozok).toHaveLength(2);
  });

  it('hiányos sikeres válasz nem kerül hiányzóként cache-be', async () => {
    const szolg = new LinkSzolgaltatas();
    const keres = szolg.feloldas('Host.md', ['Unknown']);
    const hiba = expect(keres).rejects.toMatchObject({ statusz: 502 });
    varakozok[0].valasz(new Response(JSON.stringify({ eredmenyek: [] }))); await hiba;
    const uj = szolg.feloldas('Host.md', ['Unknown']);
    expect(varakozok).toHaveLength(2);
    varakozok[1].valasz(valasz(['Unknown'])); await uj;
  });
});
