// A beágyazás renderelése (C10), ál-core-ral: jegyzet (egész, fejezet), kép (méret, alt), videó (`#t=`), hang,
// PDF (`#page=N`), hiányzó cél, canvas-helyőrző és a regiszter; a KÖRKÖRÖS beágyazás és a mélységkorlát védelme.
// A feloldást, a szeletet és a típust a core adja (`/api/vault/beagyazas`); ezt a teszt táblázatból szimulálja.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { linkek } from '../src/lib/vault/linkek.svelte';
import { kepetNagyit, kepVodor } from '../src/szerkeszto/beagyazas/nagyito';
import { MAX_MELYSEG, korkoros } from '../src/szerkeszto/beagyazas/rajzol';
import { beagyazasRenderelok } from '../src/szerkeszto/beagyazas/regiszter';
import { obsidianElemzo } from '../src/szerkeszto/markdown/elemzo';
import { dokumentumRenderel } from '../src/szerkeszto/olvaso/html';
import { LustaRajzolo } from '../src/szerkeszto/olvaso/lusta';

type Valasz = Record<string, unknown>;
let tabla: Record<string, Valasz>; // "forras|cel|alcel" → válasz
let kerelmek: string[];

function valasz(adat: unknown, kod = 200) {
  return new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });
}

beforeEach(() => {
  kerelmek = [];
  tabla = {};
  linkek.mediaToken = 'tok';
  vi.stubGlobal('fetch', async (url: string) => {
    const u = new URL(url, 'http://127.0.0.1/');
    kerelmek.push(u.pathname + u.search);
    if (u.pathname === '/api/vault/beagyazas') {
      const k = `${u.searchParams.get('forras')}|${u.searchParams.get('cel')}|${u.searchParams.get('alcel') ?? ''}`;
      return valasz(tabla[k] ?? { tipus: 'nincs', cel: u.searchParams.get('cel') });
    }
    return valasz({ hiba: 'nincs' }, 404);
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.body.textContent = '';
});

function rajzol(szoveg: string, ut = 'Fő.md'): HTMLElement {
  const kont = document.createElement('div');
  document.body.appendChild(kont);
  kont.appendChild(dokumentumRenderel(obsidianElemzo.parse(szoveg), { olvas: (a, b) => szoveg.slice(a, b), ut, lusta: LustaRajzolo.azonnali() }));
  return kont;
}

describe('jegyzet-beágyazás', () => {
  it('az egész jegyzet: fejléc a névvel, a törzs az Olvasó renderelésével', async () => {
    tabla['Fő.md|Cél|'] = { tipus: 'jegyzet', ut: 'M/Cél.md', szoveg: '# Cél\n\nA **szöveg** és $x^2$.\n' };
    const k = rajzol('Előtte\n\n![[Cél]]\n');
    await vi.waitFor(() => expect(k.querySelector('.beagyazas-jegyzet .beagyazas-torzs h1')?.textContent).toBe('Cél'));
    expect(k.querySelector('.beagyazas-cim')!.textContent).toBe('Cél');
    expect(k.querySelector('.beagyazas-torzs strong')!.textContent).toBe('szöveg');
    expect(k.querySelector('.beagyazas-torzs .katex')).not.toBeNull();
  });

  it('fejezet és blokk: az alcél a core-nak megy, a fejléc mutatja', async () => {
    tabla['Fő.md|Cél|Első rész'] = { tipus: 'jegyzet', ut: 'Cél.md', alcel: 'Első rész', szoveg: '## Első rész\nszöveg' };
    tabla['Fő.md|Cél|^b1'] = { tipus: 'jegyzet', ut: 'Cél.md', alcel: '^b1', szoveg: 'egy blokk ^b1' };
    const k = rajzol('![[Cél#Első rész]]\n\n![[Cél#^b1]]\n');
    await vi.waitFor(() => expect(k.querySelectorAll('.beagyazas-jegyzet')).toHaveLength(2));
    const fejek = [...k.querySelectorAll('.beagyazas-cim')].map((e) => e.textContent);
    expect(fejek).toEqual(['Cél › Első rész', 'Cél › ^b1']);
    expect(k.textContent).toContain('egy blokk');
    expect(k.textContent).not.toContain('^b1 ^b1'); // a blokkazonosítót az Olvasó elrejti
    expect(kerelmek.some((u) => u.includes('alcel=%5Eb1'))).toBe(true);
  });

  it('hibás fejezet: jelzés, tartalom nélkül', async () => {
    tabla['Fő.md|Cél|Nincs'] = { tipus: 'jegyzet', ut: 'Cél.md', alcel_hiba: true, szoveg: '' };
    const k = rajzol('![[Cél#Nincs]]');
    await vi.waitFor(() => expect(k.querySelector('.beagyazas-hianyzo')?.textContent).toContain('Cél#Nincs'));
  });

  it('a beágyazott jegyzet linkje a saját jegyzetéből old fel (data-forras)', async () => {
    tabla['Fő.md|Cél|'] = { tipus: 'jegyzet', ut: 'M/Cél.md', szoveg: 'lásd [[Másik|innen]]' };
    const k = rajzol('![[Cél]]');
    await vi.waitFor(() => expect(k.querySelector('.beagyazas-torzs .wikilink')).not.toBeNull());
    const wl = k.querySelector<HTMLElement>('.beagyazas-torzs .wikilink')!;
    expect(wl.textContent).toBe('innen');
    expect(wl.dataset).toMatchObject({ cel: 'Másik', forras: 'M/Cél.md' });
  });
});

describe('körkörös beágyazás és mélység', () => {
  it('a közvetlen önbeágyazás', async () => {
    tabla['A.md|A|'] = { tipus: 'jegyzet', ut: 'A.md', szoveg: 'önmaga ![[A]]' };
    const k = rajzol('![[A]]', 'A.md');
    await vi.waitFor(() => expect(k.querySelector('.beagyazas-hiba')?.textContent).toContain('Körkörös beágyazás'));
    expect(kerelmek).toHaveLength(1); // a feloldás után nem renderel tovább
  });

  it('A → B → A: a második szinten megáll, az útvonalat jelzi', async () => {
    tabla['A.md|B|'] = { tipus: 'jegyzet', ut: 'B.md', szoveg: 'B tartalma\n\n![[A]]' };
    tabla['B.md|A|'] = { tipus: 'jegyzet', ut: 'A.md', szoveg: 'A tartalma\n\n![[B]]' };
    const k = rajzol('![[B]]', 'A.md');
    await vi.waitFor(() => expect(k.querySelector('.beagyazas-hiba')?.textContent).toContain('Körkörös beágyazás'));
    expect(k.querySelector('.beagyazas-hiba')!.textContent).toBe('Körkörös beágyazás: A → B → A');
    expect(k.textContent).toContain('B tartalma');
  });

  it('a jegyzet saját fejezetének beágyazása nem körkörös, amíg nem ismétlődik pontosan', () => {
    expect(korkoros([{ ut: 'A.md', alcel: null }], 'A.md', 'Fej')).toBe(false);
    expect(korkoros([{ ut: 'A.md', alcel: null }], 'A.md', null)).toBe(true);
    expect(korkoros([{ ut: 'A.md', alcel: 'Fej' }], 'A.md', 'Fej')).toBe(true);
    expect(korkoros([{ ut: 'A.md', alcel: 'Fej' }], 'A.md', 'Más')).toBe(false);
    expect(korkoros([{ ut: 'A.md', alcel: 'Fej' }], 'A.md', null)).toBe(true);
  });

  it('a mélységkorlát', async () => {
    for (let i = 0; i < 10; i++) tabla[`N${i}.md|N${i + 1}|`] = { tipus: 'jegyzet', ut: `N${i + 1}.md`, szoveg: `szint ${i + 1}\n\n![[N${i + 2}]]` };
    tabla['Fő.md|N1|'] = { tipus: 'jegyzet', ut: 'N0.md', szoveg: 'szint 0\n\n![[N1]]' };
    tabla['N0.md|N1|'] = { tipus: 'jegyzet', ut: 'N1.md', szoveg: 'szint 1\n\n![[N2]]' };
    const k = rajzol('![[N1]]');
    await vi.waitFor(() => expect(k.querySelector('.beagyazas-hiba')?.textContent).toBe('Túl mély beágyazás'));
    expect(k.querySelectorAll('.beagyazas-jegyzet').length).toBe(MAX_MELYSEG);
  });
});

describe('média', () => {
  it('kép: méret és alt-szöveg, tokenes URL', async () => {
    tabla['Fő.md|kep.png|'] = { tipus: 'kep', ut: 'Képek/kép 1.png' };
    const k = rajzol('![[kep.png|300x200]] és ![[kep.png|szép felirat]]');
    await vi.waitFor(() => expect(k.querySelectorAll('img.beagyazas-kep')).toHaveLength(2));
    const [a, b] = k.querySelectorAll<HTMLImageElement>('img.beagyazas-kep');
    expect(a.getAttribute('width')).toBe('300');
    expect(a.getAttribute('height')).toBe('200');
    expect(a.alt).toBe('kép 1.png');
    expect(a.getAttribute('src')).toBe('/media/tok/K%C3%A9pek/k%C3%A9p%201.png?w=400'); // |300 → 300 px × dpr 1 → 400-as vödör
    expect(b.alt).toBe('szép felirat');
    expect(b.getAttribute('width')).toBeNull();
  });

  it('kép (C11a, M9): kicsinyített változat a megjelenített szélességnek megfelelő vödörrel, async dekódolás, lusta betöltés', async () => {
    tabla['Fő.md|kep.png|'] = { tipus: 'kep', ut: 'a.jpg' };
    const k = rajzol('![[kep.png]] ![[kep.png|300]] ![[kep.png|1000]]');
    await vi.waitFor(() => expect(k.querySelectorAll('img.beagyazas-kep')).toHaveLength(3));
    const [alap, kicsi, nagy] = [...k.querySelectorAll<HTMLImageElement>('img.beagyazas-kep')];
    expect(alap.getAttribute('src')).toBe('/media/tok/a.jpg?w=800'); // jsdom: a sáv szélessége ismeretlen → 800
    expect(kicsi.getAttribute('src')).toBe('/media/tok/a.jpg?w=400');
    expect(nagy.getAttribute('src')).toBe('/media/tok/a.jpg?w=1600');
    for (const i of [alap, kicsi, nagy]) {
      expect(i.decoding).toBe('async');
      expect(i.loading).toBe('lazy');
    }
  });

  it('a képpontsűrűség a vödröt növeli (retina: 300 px → 600 px → 800-as vödör)', async () => {
    vi.stubGlobal('devicePixelRatio', 2);
    tabla['Fő.md|kep.png|'] = { tipus: 'kep', ut: 'a.jpg' };
    const k = rajzol('![[kep.png|300]]');
    await vi.waitFor(() => expect(k.querySelector('img.beagyazas-kep')).not.toBeNull());
    expect(k.querySelector('img.beagyazas-kep')!.getAttribute('src')).toBe('/media/tok/a.jpg?w=800');
    vi.unstubAllGlobals();
  });

  it('kattintásra az eredeti nyílik a nagyítóban (`w` nélkül); Esc zár, a fókusz visszatér', async () => {
    tabla['Fő.md|kep.png|'] = { tipus: 'kep', ut: 'Képek/a b.jpg' };
    const k = rajzol('![[kep.png]]');
    await vi.waitFor(() => expect(k.querySelector('img.beagyazas-kep')).not.toBeNull());
    const kep = k.querySelector<HTMLImageElement>('img.beagyazas-kep')!;
    expect(kep.getAttribute('role')).toBe('button');
    kep.focus();
    kep.click();
    await vi.waitFor(() => expect(document.querySelector('.nagyito')).not.toBeNull());
    const nagy = document.querySelector<HTMLImageElement>('.nagyito-kep')!;
    expect(nagy.getAttribute('src')).toBe('/media/tok/K%C3%A9pek/a%20b.jpg');
    expect(document.querySelector('.nagyito')!.getAttribute('aria-modal')).toBe('true');
    expect(document.activeElement).toBe(document.querySelector('.nagyito-bezar'));
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    expect(document.querySelector('.nagyito')).toBeNull();
    expect(document.activeElement).toBe(kep);
  });

  it('a nagyító a háttérre és a gombra kattintva zár, a képre kattintva nem; egyszerre egy van', async () => {
    const zar = kepetNagyit('/media/tok/a.jpg', 'a.jpg');
    kepetNagyit('/media/tok/b.jpg', 'b.jpg');
    expect(document.querySelectorAll('.nagyito')).toHaveLength(1);
    document.querySelector<HTMLElement>('.nagyito-kep')!.click();
    expect(document.querySelector('.nagyito')).not.toBeNull();
    document.querySelector<HTMLElement>('.nagyito')!.click();
    expect(document.querySelector('.nagyito')).toBeNull();
    zar(); // a már bezárt nézegető bezárása nem hiba
  });

  it('kepVodor: a legkisebb vödör, ami elég; a legnagyobbnál nagyobb kérés a legnagyobbat kapja', () => {
    expect([100, 400, 401, 800, 801, 1600, 5000].map((px) => kepVodor(px))).toEqual([400, 400, 800, 800, 1600, 1600, 1600]);
    expect(kepVodor(300, 2)).toBe(800);
    expect(kepVodor(704, 2)).toBe(1600);
  });

  it('videó: a `#t=` másodpercben a forrásban és a lejátszás kezdetén', async () => {
    tabla['Fő.md|v.mp4|t=12:40'] = { tipus: 'video', ut: 'v.mp4', alcel: 't=12:40' };
    const k = rajzol('![[v.mp4#t=12:40]]');
    await vi.waitFor(() => expect(k.querySelector('video.beagyazas-video')).not.toBeNull());
    const v = k.querySelector<HTMLVideoElement>('video')!;
    expect(v.getAttribute('src')).toBe('/media/tok/v.mp4#t=760');
    expect(v.getAttribute('poster')).toBe('/media/tok/v.mp4?poster=1&t=760');
    expect(v.controls).toBe(true);
    expect(v.preload).toBe('metadata');
  });

  it('videó időkód nélkül: az első képkocka (`#t=0.001`) és a core-poszter lejátszás előtt', async () => {
    tabla['Fő.md|v 1.mp4|'] = { tipus: 'video', ut: 'ó/v 1.mp4' };
    const k = rajzol('![[v 1.mp4]]');
    await vi.waitFor(() => expect(k.querySelector('video.beagyazas-video')).not.toBeNull());
    const v = k.querySelector<HTMLVideoElement>('video')!;
    expect(v.getAttribute('src')).toBe('/media/tok/%C3%B3/v%201.mp4#t=0.001');
    expect(v.getAttribute('poster')).toBe('/media/tok/%C3%B3/v%201.mp4?poster=1');
  });

  it('PDF: az oldal a fragmentumban; hang', async () => {
    tabla['Fő.md|d.pdf|page=3'] = { tipus: 'pdf', ut: 'Könyvek/d.pdf', alcel: 'page=3' };
    tabla['Fő.md|h.m4a|'] = { tipus: 'hang', ut: 'h.m4a' };
    const k = rajzol('![[d.pdf#page=3]]\n\n![[h.m4a]]');
    await vi.waitFor(() => expect(k.querySelector('iframe.beagyazas-pdf')).not.toBeNull());
    expect(k.querySelector('iframe')!.getAttribute('src')).toBe('/media/tok/K%C3%B6nyvek/d.pdf#page=3');
    expect(k.querySelector('iframe')!.title).toContain('3. oldal');
    await vi.waitFor(() => expect(k.querySelector('audio.beagyazas-hang')).not.toBeNull());
  });
});

describe('hiányzó cél és helyőrzők', () => {
  it('hiányzó jegyzet: jelzés és létrehozás gomb; a média nem kap gombot', async () => {
    const k = rajzol('![[Nincs ilyen]] és ![[nincs.png]]');
    await vi.waitFor(() => expect(k.querySelectorAll('.beagyazas-hianyzo')).toHaveLength(2));
    const gombok = k.querySelectorAll('.beagyazas-letrehoz');
    expect(gombok).toHaveLength(1);
    expect(k.textContent).toContain('Nem található: Nincs ilyen');
  });

  it('canvas: link-chip, a regiszterből felülírható', async () => {
    tabla['Fő.md|Vászon.canvas|'] = { tipus: 'canvas', ut: 'Vászon.canvas' };
    let k = rajzol('![[Vászon.canvas]]');
    await vi.waitFor(() => expect(k.querySelector('.beagyazas-chip .beagyazas-cim')?.textContent).toBe('Vászon.canvas'));
    const le = beagyazasRenderelok.regisztral({
      tipus: 'canvas',
      render: (a, _l, kont) => {
        kont.className = 'beagyazas canvas-rajz';
        kont.textContent = `rajz: ${a.ut}`;
      },
    });
    k = rajzol('![[Vászon.canvas]]');
    await vi.waitFor(() => expect(k.querySelector('.canvas-rajz')?.textContent).toBe('rajz: Vászon.canvas'));
    le();
    expect(() => beagyazasRenderelok.regisztral({ tipus: 'canvas', render: () => {} })()).not.toThrow();
  });

  it('a core hibája (503) nem dob, jelzést ad', async () => {
    vi.stubGlobal('fetch', async () => valasz({ hiba: 'az index épül' }, 503));
    const k = rajzol('![[X]]');
    await vi.waitFor(() => expect(k.querySelector('.beagyazas-hiba')?.textContent).toContain('az index épül'));
  });

  it('beágyazás ismeretlen forrás nélkül (ut: null) nyers szöveg marad', () => {
    const sz = '![[X]]';
    const kont = document.createElement('div');
    kont.appendChild(dokumentumRenderel(obsidianElemzo.parse(sz), { olvas: (a, b) => sz.slice(a, b), ut: null, lusta: LustaRajzolo.azonnali() }));
    expect(kont.querySelector('.beagyazas-nyers')!.textContent).toBe('![[X]]');
  });
});
