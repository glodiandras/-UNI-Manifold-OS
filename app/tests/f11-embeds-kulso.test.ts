// 04-embeds-02 / 01-rendering-04 (külső kép explicit letöltése), 04-embeds-07 (célonkénti frissítés, canvas-kártya),
// 04-embeds-08 (beillesztett kép neve), 04-embeds-09 (link-formátum beszúráskor). A hálózat mockolt: valódi kérés nincs,
// és a webview sosem kér külső képet.
import { readFileSync } from 'node:fs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { linkek } from '../src/lib/vault/linkek.svelte';
import type { FajlIrasKeres } from '../src/szerkeszto/dokumentum/api';
import { Dokumentum } from '../src/szerkeszto/dokumentum/dokumentum.svelte';
import { obsidianElemzo } from '../src/szerkeszto/markdown/elemzo';
import { dokumentumRenderel } from '../src/szerkeszto/olvaso/html';
import { LustaRajzolo } from '../src/szerkeszto/olvaso/lusta';
import { szerkesztok } from '../src/szerkeszto/szerkesztok.svelte';
import { beagyazasElem, beagyazasokFrissit } from '../src/szerkeszto/beagyazas/rajzol';
import { kepLinkAtir, kepLinkValtozasok, letoltottUrit } from '../src/szerkeszto/beagyazas/kulsoKep';
import { jegyzetRajzol, szovegRajzol } from '../src/canvas/tartalom';
import { BEAGYAZHATO, beillesztettNev, beszurtLink, urlLinkCel } from '../src/szerkeszto/csatolmany';

const URL_ = 'https://img.example/a/diagram.png';
interface Kerelem { url: URL; metodus: string; torzs: Record<string, unknown> | null }
const kerelmek: Kerelem[] = [];
let importValasz: () => Response;
let jegyzetek: Record<string, string> = {};

function json(adat: unknown, statusz = 200): Response {
  return new Response(JSON.stringify(adat), { status: statusz, headers: { 'Content-Type': 'application/json' } });
}

function render(szoveg: string, ut = 'Folder/Host.md', csakOlvashato = false): HTMLElement {
  const kont = document.createElement('article');
  document.body.appendChild(kont);
  kont.appendChild(dokumentumRenderel(obsidianElemzo.parse(szoveg), {
    olvas: (a, b) => szoveg.slice(a, b), ut, lusta: LustaRajzolo.azonnali(), csakOlvashato,
  }));
  return kont;
}

beforeEach(() => {
  kerelmek.length = 0;
  jegyzetek = { 'Target.md': 'First', 'Other.md': 'Other' };
  letoltottUrit();
  linkek.mediaToken = 'tok';
  importValasz = () => json({ ok: true, kesz: true, ut: 'Folder/Attachments/diagram.png', meglevo: false, figyelmeztetes: null });
  vi.stubGlobal('fetch', vi.fn(async (cim: string, init?: RequestInit) => {
    const url = new URL(cim, 'http://127.0.0.1/');
    if (url.origin !== 'http://127.0.0.1') throw new Error(`külső kérés: ${cim}`);
    kerelmek.push({ url, metodus: init?.method ?? 'GET', torzs: init?.body ? JSON.parse(String(init.body)) : null });
    if (url.pathname === '/api/vault/import') return importValasz();
    if (url.pathname === '/api/vault/linkcel') return json({ ut: url.searchParams.get('ut'), cel: 'Attachments/diagram.png', alak: 'wiki', md: 'Attachments/diagram.png' });
    if (url.pathname === '/api/vault/beagyazas') {
      const cel = url.searchParams.get('cel')!;
      if (cel.endsWith('.png')) return json({ tipus: 'kep', ut: cel });
      const ut = `${cel.replace(/\.md$/, '')}.md`;
      if (!(ut in jegyzetek)) return json({ tipus: 'nincs', cel });
      return json({ tipus: 'jegyzet', ut, szoveg: jegyzetek[ut], kezd: 1 });
    }
    return json({ eredmenyek: [] });
  }));
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  document.body.replaceChildren();
});

const beagyazasKeresek = () => kerelmek.filter((k) => k.url.pathname === '/api/vault/beagyazas');

describe('04-embeds-02 / 01-rendering-04: külső kép csak kattintásra', () => {
  it('a CSP nem lazul: az img-src nem enged külső forrást', () => {
    const index = readFileSync(`${(import.meta as unknown as { dirname: string }).dirname}/../index.html`, 'utf8');
    const imgSrc = /img-src([^;]*);/.exec(index)![1];
    expect(imgSrc.trim()).toBe("'self' data: blob:");
    expect(index).not.toMatch(/connect-src[^;]*https:/);
  });

  it('helyőrző: nincs <img>, nincs kérés; a gomb és az ikon látszik', () => {
    const k = render(`![Diagram](${URL_})`);
    expect(k.querySelectorAll('img')).toHaveLength(0);
    expect(kerelmek).toHaveLength(0);
    const kont = k.querySelector<HTMLElement>('.beagyazas-kulso')!;
    expect(kont.textContent).toContain('Diagram');
    expect(kont.querySelector('svg.ikon')).not.toBeNull();
    expect(kont.querySelector('button.beagyazas-kulso-letolt')).not.toBeNull();
  });

  it('nem https séma, lebegő előnézet és csak olvasható nézet: letöltés gomb nélkül', () => {
    expect(render('![x](http://img.example/a.png)').querySelector('button')).toBeNull();
    expect(render(`![x](${URL_})`, 'Folder/Host.md', true).querySelector('button')).toBeNull();
    const kompakt = beagyazasElem({ cel: URL_, alcel: null, alias: null, beagyazas: true, from: 0, to: 0, kulso: true },
      { forras: 'Folder/Host.md', kompakt: true });
    expect(kompakt.querySelector('button')).toBeNull();
    expect(kerelmek).toHaveLength(0);
  });

  it('kattintásra a core tölt le (url + forrás), utána a helyi fájl rajzolódik; a munkamenetben újra nem kér', async () => {
    const k = render(`![Diagram|300](${URL_})`);
    k.querySelector<HTMLButtonElement>('.beagyazas-kulso-letolt')!.click();
    await vi.waitFor(() => expect(k.querySelector('img')).not.toBeNull());
    const imp = kerelmek.filter((x) => x.url.pathname === '/api/vault/import');
    expect(imp).toHaveLength(1);
    expect(imp[0]).toMatchObject({ metodus: 'POST', torzs: { url: URL_, forras: 'Folder/Host.md' } });
    const img = k.querySelector('img')!;
    expect(img.getAttribute('src')).toMatch(/^\/media\/tok\/Folder\/Attachments\/diagram\.png\?w=/);
    expect(img.alt).toBe('Diagram');
    expect(img.width).toBe(300);
    expect(k.querySelector('.beagyazas-kulso-atir')).not.toBeNull();
    const masik = render(`![Diagram](${URL_})`);
    await vi.waitFor(() => expect(masik.querySelector('img')).not.toBeNull());
    expect(kerelmek.filter((x) => x.url.pathname === '/api/vault/import')).toHaveLength(1);
  });

  it('hiba: ikon és szöveg (role=alert), a gomb újrapróbálható, kép nem jelenik meg', async () => {
    importValasz = () => json({ hiba: 'Images are not downloaded from local or private addresses.', kod: 'kulso_kep.helyi_cim', param: {} }, 403);
    const k = render(`![x](${URL_})`);
    const b = k.querySelector<HTMLButtonElement>('.beagyazas-kulso-letolt')!;
    b.click();
    await vi.waitFor(() => expect(k.querySelector('[role="alert"]')).not.toBeNull());
    const hiba = k.querySelector<HTMLElement>('[role="alert"]')!;
    expect(hiba.querySelector('svg.ikon')).not.toBeNull();
    expect(hiba.textContent!.length).toBeGreaterThan(10);
    expect(b.disabled).toBe(false);
    expect(k.querySelector('img')).toBeNull();
    importValasz = () => json({ ok: true, kesz: true, ut: 'Folder/Attachments/diagram.png' });
    b.click();
    await vi.waitFor(() => expect(k.querySelector('img')).not.toBeNull());
    expect(k.querySelector('[role="alert"]')).toBeNull();
  });
});

describe('04-embeds-02: a jegyzet linkje csak kifejezett választásra íródik át (CAS)', () => {
  it('csak a pontos külső kép URL-része cserélődik: alt, méret, kód, más link marad', () => {
    const szoveg = [`![Alt|200](${URL_})`, `[link](${URL_})`, '```', `![c](${URL_})`, '```', `![b](<${URL_}>)`, '![o](https://other.example/x.png)'].join('\n');
    const v = kepLinkValtozasok(szoveg, URL_, 'Attachments/diagram.png');
    expect(v).toHaveLength(2);
    let uj = szoveg;
    for (const c of [...v].reverse()) uj = uj.slice(0, c.from) + c.insert + uj.slice(c.to);
    expect(uj.split('\n')).toEqual(['![Alt|200](Attachments/diagram.png)', `[link](${URL_})`, '```', `![c](${URL_})`, '```',
      '![b](Attachments/diagram.png)', '![o](https://other.example/x.png)']);
  });

  function dokumentum(szoveg: string) {
    const api = { olvas: vi.fn(), ir: vi.fn(async (k: FajlIrasKeres) => ({ ok: true, ut: k.ut, hash: 'saved', git: true, pillanat: 'p', jel: '', uzenet: '', elotte: null })) };
    const d = new Dokumentum(api, { ut: 'Folder/Host.md', tartalom: szoveg, hash: 'base', jel: '', mtime: 0 });
    vi.spyOn(d, 'kulsoValtozas').mockResolvedValue();
    vi.spyOn(szerkesztok.dokumentumok, 'megnyit').mockResolvedValue(d);
    vi.spyOn(szerkesztok.dokumentumok, 'elenged').mockResolvedValue();
    return { d, api };
  }

  it('a gomb a közös Dokumentumon ír, a mentés az alap hash-sel (CAS) megy', async () => {
    const { api } = dokumentum(`Intro\n![Diagram](${URL_})\n`);
    const k = render(`![Diagram](${URL_})`);
    k.querySelector<HTMLButtonElement>('.beagyazas-kulso-letolt')!.click();
    await vi.waitFor(() => expect(k.querySelector('.beagyazas-kulso-atir')).not.toBeNull());
    expect(api.ir).not.toHaveBeenCalled();                     // a letöltés magában nem írja a jegyzetet
    k.querySelector<HTMLButtonElement>('.beagyazas-kulso-atir')!.click();
    await vi.waitFor(() => expect(api.ir).toHaveBeenCalledTimes(1));
    expect(api.ir.mock.calls[0][0]).toMatchObject({ ut: 'Folder/Host.md', alap: 'base', tartalom: 'Intro\n![Diagram](Attachments/diagram.png)\n' });
    await vi.waitFor(() => expect(k.querySelector('[role="status"]')).not.toBeNull());
  });

  it('ha a link közben eltűnt vagy ütközés van, nincs írás, a hiba látszik', async () => {
    const { d, api } = dokumentum('Nothing here\n');
    await expect(kepLinkAtir('Folder/Host.md', URL_, 'Folder/Attachments/diagram.png')).rejects.toThrow();
    expect(api.ir).not.toHaveBeenCalled();
    vi.spyOn(d, 'allapot', 'get').mockReturnValue('utkozes');
    await expect(kepLinkAtir('Folder/Host.md', URL_, 'Folder/Attachments/diagram.png')).rejects.toThrow();
    expect(api.ir).not.toHaveBeenCalled();
    expect(d.szoveg.toString()).toBe('Nothing here\n');
  });
});

describe('04-embeds-07: célonkénti érvénytelenítés (Olvasó, canvas-kártya)', () => {
  it('csak az érintett cél rajzol újra; a hiányzó cél bármely tartalmi eseményre újrafeloldódik', async () => {
    const k = render('![[Target]]\n\n![[Other]]\n\n![[Missing]]');
    await vi.waitFor(() => expect(k.querySelectorAll('.beagyazas-torzs')).toHaveLength(2));
    const masik = k.querySelectorAll<HTMLElement>('.beagyazas-torzs')[1];
    expect(k.querySelector('.beagyazas-hianyzo')).not.toBeNull();
    const elotte = beagyazasKeresek().length;
    jegyzetek['Target.md'] = 'Second';
    jegyzetek['Missing.md'] = 'Now here';
    expect(beagyazasokFrissit(k, new Set(['Target.md']))).toBe(2);   // a cél + a feloldatlan
    await vi.waitFor(() => expect(k.textContent).toContain('Second'));
    await vi.waitFor(() => expect(k.textContent).toContain('Now here'));
    expect(beagyazasKeresek().slice(elotte).map((x) => x.url.searchParams.get('cel')).sort()).toEqual(['Missing', 'Target']);
    expect(k.querySelectorAll<HTMLElement>('.beagyazas-torzs')[1]).toBe(masik);   // a nem érintett DOM ugyanaz
  });

  it('beágyazott beágyazás: a belső cél változása a legkülső érintett elemet rajzolja újra, egyszer', async () => {
    jegyzetek['Target.md'] = 'Outer ![[Other]]';
    const k = render('![[Target]]');
    await vi.waitFor(() => expect(k.textContent).toContain('Other'));
    const elotte = beagyazasKeresek().length;
    jegyzetek['Other.md'] = 'Changed';
    expect(beagyazasokFrissit(k, new Set(['Other.md']))).toBe(1);
    await vi.waitFor(() => expect(k.textContent).toContain('Changed'));
    expect(beagyazasKeresek().slice(elotte).map((x) => x.url.searchParams.get('cel'))).toEqual(['Other']);
  });

  it('canvas jegyzetkártya és szövegkártya a célja mentésekor frissül, lebontás után nem', async () => {
    const kartya = document.body.appendChild(document.createElement('div'));
    const le = jegyzetRajzol(kartya, 'Target.md', undefined, 'Board.canvas');
    const szoveg = document.body.appendChild(document.createElement('div'));
    const le2 = szovegRajzol(szoveg, 'See ![[Other]]', 'Board.canvas');
    await vi.waitFor(() => expect(kartya.textContent).toContain('First'));
    await vi.waitFor(() => expect(szoveg.textContent).toContain('Other'));
    jegyzetek['Target.md'] = 'Card update';
    linkek.tartalomValtozott(['Target.md']);
    await vi.waitFor(() => expect(kartya.textContent).toContain('Card update'));
    jegyzetek['Other.md'] = 'Text card update';
    linkek.tartalomValtozott(['Other.md']);
    await vi.waitFor(() => expect(szoveg.textContent).toContain('Text card update'));
    le(); le2();
    const elotte = beagyazasKeresek().length;
    linkek.tartalomValtozott(null);
    await new Promise((r) => setTimeout(r, 20));
    expect(beagyazasKeresek().length).toBe(elotte);
  });
});

describe('04-embeds-08 / -09: beillesztett kép neve és link-formátum', () => {
  const most = new Date(2026, 9, 16, 9, 5, 7);
  it.each([
    ['image.png', 'image/png', 'Pasted image 20261016090507.png'],
    ['', 'image/jpeg', 'Pasted image 20261016090507.jpg'],
    ['blob', 'image/webp', 'Pasted image 20261016090507.webp'],
    ['Screenshot.PNG', 'image/png', 'Pasted image 20261016090507.png'],
    ['Holiday photo.jpg', 'image/jpeg', 'Holiday photo.jpg'],
    ['image.png', 'application/pdf', 'image.png'],
  ])('%s (%s) → %s', (nev, tipus, vart) => {
    expect(beillesztettNev(new File([new Uint8Array([1])], nev, { type: tipus }), most).name).toBe(vart);
  });

  it('a beszúrt link a core formátumát követi (wiki/md, kódolt md-cél, média !)', () => {
    expect(beszurtLink({ ut: 'A/Pasted image 1.png', cel: 'Pasted image 1.png', alak: 'wiki', md: 'Pasted%20image%201.png' }, 'A/Pasted image 1.png'))
      .toBe('![[Pasted image 1.png]]');
    expect(beszurtLink({ ut: 'A/Pasted image 1.png', cel: '../A/Pasted image 1.png', alak: 'md', md: '../A/Pasted%20image%201.png' }, 'A/Pasted image 1.png'))
      .toBe('![Pasted image 1.png](../A/Pasted%20image%201.png)');
    expect(beszurtLink({ ut: 'Docs/Note.md', cel: 'Docs/Note', alak: 'md', md: 'Docs/Note.md' }, 'Docs/Note.md')).toBe('[Note](Docs/Note.md)');
    expect(beszurtLink({ ut: 'x.txt', cel: 'x.txt' }, 'x.txt')).toBe('[[x.txt]]');
    expect(BEAGYAZHATO.test('clip.webm') && BEAGYAZHATO.test('a.avif') && !BEAGYAZHATO.test('a.txt')).toBe(true);
  });

  it('kijelölésre beillesztett URL: <…> csak szükség esetén', () => {
    expect(urlLinkCel('https://example.com/a')).toBe('https://example.com/a');
    expect(urlLinkCel('https://example.com/a_(b)')).toBe('<https://example.com/a_(b)>');
  });
});
