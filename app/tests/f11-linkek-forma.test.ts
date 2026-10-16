// F11 / 02-links: a beírt link alakja a beállításokból („New link format”, „Use [[Wikilinks]]”), a Markdown-cél értelmezésének
// közös vektorai a core-ral, a középső gombos megnyitás módja, a panel-szűrő és a kimenő említések tárolója.

import { readFileSync } from 'node:fs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { szuroEgyezik, szuroSzavak } from '../src/hej/kapcsolatok/szuro';
import { alapBeallitasok } from '../src/lib/beallitasok/tipusok';
import { Kapcsolatok } from '../src/lib/vault/kapcsolatok.svelte';
import { LinkSzolgaltatas } from '../src/lib/vault/linkek.svelte';
import { linkSzoveg } from '../src/szerkeszto/linkek/adat';
import { markdownCel } from '../src/szerkeszto/linkek/markdown';
import { nyitasMod } from '../src/szerkeszto/linkek/navigacio';

const valasz = (adat: unknown, kod = 200) => new Response(JSON.stringify(adat), { status: kod, headers: { 'Content-Type': 'application/json' } });
afterEach(() => vi.unstubAllGlobals());

describe('linkSzoveg: wikilink vagy markdown-link a beállítás szerint', () => {
  const wiki = { cel: 'Mappa/Jegyzet', alak: 'wiki' as const, md: 'Mappa/Jegyzet.md' };
  const md = { cel: 'Mappa/Jegyzet', alak: 'md' as const, md: 'Mappa/Jegyzet.md' };

  it('wiki: [[cél]], horgonnyal és aliasszal, beágyazásként', () => {
    expect(linkSzoveg(wiki, { nev: 'Jegyzet' })).toBe('[[Mappa/Jegyzet]]');
    expect(linkSzoveg(wiki, { nev: 'Jegyzet', alcel: 'Fej', alias: 'másik' })).toBe('[[Mappa/Jegyzet#Fej|másik]]');
    expect(linkSzoveg(wiki, { nev: 'Jegyzet', beagyazas: true, alcel: '^abc123' })).toBe('![[Mappa/Jegyzet#^abc123]]');
  });

  it('md: [felirat](kódolt-cél.md), a felirat a név (horgonnyal), vagy az alias; a [ ] a feliratból kikerül', () => {
    expect(linkSzoveg(md, { nev: 'Jegyzet' })).toBe('[Jegyzet](Mappa/Jegyzet.md)');
    expect(linkSzoveg({ ...md, md: 'Mappa/Jegyzet.md#Els%C5%91' }, { nev: 'Jegyzet', alcel: 'Első' })).toBe('[Jegyzet#Első](Mappa/Jegyzet.md#Els%C5%91)');
    expect(linkSzoveg(md, { nev: 'Jegyzet', alias: 'a [b] szöveg' })).toBe('[a b szöveg](Mappa/Jegyzet.md)');
    expect(linkSzoveg({ cel: 'kep.png', alak: 'md', md: 'kep.png' }, { nev: 'kep.png', beagyazas: true })).toBe('![kep.png](kep.png)');
  });

  it('md alak kész md-cél nélkül (régi válasz) wikilinkre esik vissza: a beszúrás sosem ír üres célt', () => {
    expect(linkSzoveg({ cel: 'X', alak: 'md', md: '' }, { nev: 'X' })).toBe('[[X]]');
  });
});

describe('a link-szolgáltatás a core linkcel-válaszából', () => {
  it('az alak és az md-cél átjön; hiányos (régi) válasznál wikilink; a horgony a kérésben utazik', async () => {
    const hivasok: string[] = [];
    vi.stubGlobal('fetch', async (url: string) => {
      hivasok.push(url);
      return url.includes('ut=Uj.md') ? valasz({ ut: 'Uj.md', cel: 'Uj', alak: 'md', md: 'Uj.md#H' }) : valasz({ ut: 'Regi.md', cel: 'Regi' });
    });
    const sz = new LinkSzolgaltatas();
    expect(await sz.linkForma('Uj.md', 'A.md', 'H')).toEqual({ cel: 'Uj', alak: 'md', md: 'Uj.md#H' });
    expect(hivasok[0]).toContain('alcel=H');
    expect(await sz.linkForma('Regi.md', 'A.md')).toEqual({ cel: 'Regi', alak: 'wiki', md: '' });
    expect(hivasok[1]).not.toContain('alcel');
  });

  it('a még nem létező cél a `cel` paraméterrel kérdez', async () => {
    let url = '';
    vi.stubGlobal('fetch', async (u: string) => { url = u; return valasz({ ut: null, cel: 'Új cél', alak: 'md', md: '%C3%9Aj%20c%C3%A9l.md' }); });
    const f = await new LinkSzolgaltatas().linkFormaHianyzo('Új cél', 'A.md');
    expect(url).toContain('cel=%C3%9Aj%20c%C3%A9l');
    expect(f.alak).toBe('md');
  });

  it('a feloldatlan szövegek gyorsítótárazottak, a fájlszerkezet változása ürít, a 404/503 üres lista', async () => {
    let db = 0;
    let kod = 200;
    vi.stubGlobal('fetch', async () => { db++; return kod === 200 ? valasz({ szovegek: [{ cel: 'Még nincs', db: 3 }] }) : valasz({ hiba: 'x' }, kod); });
    const sz = new LinkSzolgaltatas();
    expect(await sz.feloldatlanSzovegek()).toEqual(['Még nincs']);
    await sz.feloldatlanSzovegek();
    expect(db).toBe(1);
    sz.ervenytelenit();
    await sz.feloldatlanSzovegek();
    expect(db).toBe(2);
    sz.ervenytelenit();
    kod = 503;
    expect(await sz.feloldatlanSzovegek()).toEqual([]);
  });
});

describe('Markdown-cél: a core md_reszek és a felület markdownCel közös vektorai', () => {
  const v = JSON.parse(readFileSync(`${(import.meta as unknown as { dirname: string }).dirname}/fixtures/md-cel-vektorok.json`, 'utf8')) as { vektorok: [string, string | null, string | null][] };
  it.each(v.vektorok)('%s', (nyers, cel, alcel) => {
    expect(markdownCel(nyers)).toEqual(cel === null ? null : { cel, alcel });
  });

  it('szándékos eltérések: a felület biztonsági okból több célt elutasít, mint a gráf', () => {
    expect(markdownCel('javascript:alert(1)')).toBeNull();
    expect(markdownCel('%2F%2Fexample.com/x')).toBeNull();
    expect(markdownCel('#Fejezet')).toEqual({ cel: '', alcel: 'Fejezet' }); // a gráf az üres célú md-linket nem veszi fel
  });
});

describe('a középső gomb új fület nyit', () => {
  it('nyitasMod: button 1 → ujful, ⌥-szal osztás; a bal gomb a módosítók szerint', () => {
    const e = { metaKey: false, ctrlKey: false, altKey: false };
    expect(nyitasMod({ ...e, button: 1 })).toBe('ujful');
    expect(nyitasMod({ ...e, altKey: true, button: 1 })).toBe('osztas');
    expect(nyitasMod({ ...e, button: 0 })).toBe('aktiv');
    expect(nyitasMod({ ...e, metaKey: true })).toBe('ujful');
    expect(nyitasMod({ ...e, ctrlKey: true, altKey: true })).toBe('osztas');
  });
});

describe('panel-szűrő: ékezet- és kisbetű-független, minden szó', () => {
  it('szavak és egyezés', () => {
    expect(szuroSzavak('  Árvíz  Tűrő ')).toEqual(['arviz', 'turo']);
    expect(szuroEgyezik([], 'bármi')).toBe(true);
    expect(szuroEgyezik(szuroSzavak('arviz'), 'Matek/Árvíztűrő.md')).toBe(true);
    expect(szuroEgyezik(szuroSzavak('matek tűrő'), 'Matek/Árvíztűrő.md')).toBe(true);
    expect(szuroEgyezik(szuroSzavak('matek fizika'), 'Matek/Árvíztűrő.md')).toBe(false);
    expect(szuroEgyezik(szuroSzavak('x'), null, undefined)).toBe(false);
  });
});

describe('a Kapcsolatok tároló kimenő említései', () => {
  beforeEach(() => undefined);

  it('md jegyzetnél betölti, hibája nem üríti a többi listát; nem md-nél nincs kérés', async () => {
    let hiba = false;
    const kerelmek: string[] = [];
    vi.stubGlobal('fetch', async (url: string) => {
      const u = new URL(url, 'http://127.0.0.1/');
      kerelmek.push(u.pathname);
      if (u.pathname === '/api/vault/kimeno-emlitesek') return hiba ? valasz({ hiba: 'x' }, 500) : valasz({ forrasok: [{ ut: 'B.md', talalatok: [{ sor: 1, oszlop: 3, hossz: 1, szoveg: 'a B c', emlitett: 'B' }] }] });
      if (u.pathname === '/api/vault/visszahivatkozasok') return valasz({ forrasok: [{ ut: 'C.md', linkek: [] }] });
      return valasz({ forrasok: [], linkek: [] });
    });
    const k = new Kapcsolatok();
    await k.frissit('A.md');
    expect(k.kimenoEmlitesek).toHaveLength(1);
    expect(k.kimenoEmlitesek[0].talalatok[0].emlitett).toBe('B');
    hiba = true;
    await k.frissit('A.md');
    expect(k.kimenoEmlitesek).toHaveLength(0);
    expect(k.visszahivatkozasok).toHaveLength(1);
    expect(k.hiba).toBeNull();
    kerelmek.length = 0;
    await k.frissit('kep.png');
    expect(kerelmek).not.toContain('/api/vault/kimeno-emlitesek');
    await k.frissit(null);
    expect(k.kimenoEmlitesek).toHaveLength(0);
  });
});

describe('beállítások: az új alapértékek', () => {
  it('a wikilink alapból be van kapcsolva, a link-formátum rövid', () => {
    expect(alapBeallitasok().fajlok.wikilinkek).toBe(true);
    expect(alapBeallitasok().fajlok.link_formatum).toBe('rovid');
  });
});
