import { describe, expect, it } from 'vitest';
import { Munkaterulet, type OsztasCs } from '../src/lib/elrendezes/munkaterulet.svelte';

const utak = (m: Munkaterulet) => m.aktivPanel.fulek.map((f) => f.ut);

describe('munkaterület', () => {
  it('egy üres füllel indul', () => {
    const m = new Munkaterulet();
    expect(m.panelek()).toHaveLength(1);
    expect(utak(m)).toEqual([null]);
  });

  it('megnyitás: az aktív fülben, új fülben, a már nyitottra vált', () => {
    const m = new Munkaterulet();
    const nyitott: string[] = [];
    m.megnyitasUtan = (u) => nyitott.push(u);
    m.megnyit('a.md');
    expect(utak(m)).toEqual(['a.md']);
    m.megnyit('b.md', 'ujful');
    expect(utak(m)).toEqual(['a.md', 'b.md']);
    m.megnyit('a.md');
    expect(m.aktivFul?.ut).toBe('a.md');
    expect(utak(m)).toEqual(['a.md', 'b.md']);
    m.megnyit('c.md');
    expect(utak(m)).toEqual(['c.md', 'b.md']); // az aktív fül tartalma cserélődik
    expect(nyitott).toEqual(['a.md', 'b.md', 'a.md', 'c.md']);
  });

  it('bezárás: a szomszéd lesz aktív; az utolsó fül helyett üres fül', () => {
    const m = new Munkaterulet();
    m.megnyit('a.md');
    m.megnyit('b.md', 'ujful');
    m.megnyit('c.md', 'ujful');
    m.aktival(m.aktivPanelId, m.aktivPanel.fulek[1].id);
    m.bezar();
    expect(m.aktivFul?.ut).toBe('c.md');
    m.bezar();
    m.bezar();
    expect(utak(m)).toEqual([null]);
  });

  it('léptetés körbe és ⌘1–9', () => {
    const m = new Munkaterulet();
    m.megnyit('a.md');
    m.megnyit('b.md', 'ujful');
    m.megnyit('c.md', 'ujful');
    m.lep(1);
    expect(m.aktivFul?.ut).toBe('a.md');
    m.lep(-1);
    expect(m.aktivFul?.ut).toBe('c.md');
    m.nedik(2);
    expect(m.aktivFul?.ut).toBe('b.md');
    m.nedik(9);
    expect(m.aktivFul?.ut).toBe('c.md');
  });

  it('osztás: új panel a fül másolatával, az utolsó fül bezárása összevonja', () => {
    const m = new Munkaterulet();
    m.megnyit('a.md');
    const elso = m.aktivPanelId;
    m.oszt('sor');
    expect(m.panelek()).toHaveLength(2);
    expect(m.gyoker.tipus).toBe('osztas');
    expect((m.gyoker as OsztasCs).irany).toBe('sor');
    expect(m.aktivFul?.ut).toBe('a.md');
    expect(m.aktivPanelId).not.toBe(elso);
    m.oszt('oszlop');
    expect(m.panelek()).toHaveLength(3);
    m.bezar();
    expect(m.panelek()).toHaveLength(2);
    m.bezar();
    expect(m.panelek()).toHaveLength(1);
    expect(m.gyoker.tipus).toBe('panel');
    expect(m.aktivPanelId).toBe(elso);
  });

  it('megnyitás osztásban és panelek közti fókusz', () => {
    const m = new Munkaterulet();
    m.megnyit('a.md');
    m.megnyit('b.md', 'osztas');
    const [p1, p2] = m.panelek();
    expect(p1.fulek.map((f) => f.ut)).toEqual(['a.md']);
    expect(p2.fulek.map((f) => f.ut)).toEqual(['b.md']);
    expect(m.aktivPanelId).toBe(p2.id);
    m.panelLep(1);
    expect(m.aktivPanelId).toBe(p1.id);
  });

  it('fül áthelyezése panelek között; az üres forráspanel eltűnik', () => {
    const m = new Munkaterulet();
    m.megnyit('a.md');
    m.megnyit('b.md', 'osztas');
    const [p1, p2] = m.panelek();
    m.athelyez(p2.fulek[0].id, p1.id, 1);
    expect(m.panelek()).toHaveLength(1);
    expect(m.aktivPanel.fulek.map((f) => f.ut)).toEqual(['a.md', 'b.md']);
    expect(m.aktivFul?.ut).toBe('b.md');
    m.athelyez(m.aktivPanel.fulek[1].id, m.aktivPanelId, 0);
    expect(utak(m)).toEqual(['b.md', 'a.md']);
  });

  it('arány korlátozva; eltűnt fájl fülei üresre váltanak', () => {
    const m = new Munkaterulet();
    m.megnyit('a.md');
    m.oszt('sor');
    m.aranyBeallit(m.gyoker.id, 0.99);
    expect((m.gyoker as OsztasCs).arany).toBe(0.85);
    m.eltuntek(new Set(['a.md']));
    expect(m.panelek().map((p) => p.fulek[0].ut)).toEqual([null, null]);
  });

  it('sorosítás és visszatöltés; hibás mentésre alapelrendezés', () => {
    const m = new Munkaterulet();
    m.megnyit('a.md');
    m.megnyit('b.md', 'osztas');
    const s = JSON.parse(JSON.stringify(m.sorosit()));
    const m2 = new Munkaterulet(s);
    expect(m2.panelek().map((p) => p.fulek.map((f) => f.ut))).toEqual([['a.md'], ['b.md']]);
    expect(m2.aktivPanelId).toBe(m.aktivPanelId);
    expect(new Munkaterulet({ gyoker: { tipus: 'osztas', id: 'x' } }).panelek()).toHaveLength(1);
    expect(new Munkaterulet('szemét').panelek()).toHaveLength(1);
  });
});

describe('fájllista reaktivitása', () => {
  it('a fájl adata a lista megérkezése után a származtatott értékben is megjelenik', async () => {
    const { VaultFajlok } = await import('../src/lib/vault/fajlok.svelte');
    const f = new VaultFajlok();
    let info: unknown = 'kezdet';
    const le = $effect.root(() => {
      $effect(() => {
        info = f.info('a.md');
      });
    });
    const { flushSync } = await import('svelte');
    flushSync();
    expect(info).toBeUndefined();
    expect(f.betoltve).toBe(false);
    f.beallit([{ ut: 'a.md', tipus: 'md', meret: 1, mtime: 1 }]);
    flushSync();
    expect(info).toMatchObject({ ut: 'a.md' });
    le();
  });
});

it('CX-005: előzmény, elágazás, átnevezés, bezárt fül helyreállítása', () => {
  const m = new Munkaterulet();
  m.megnyit('A/a.md');
  m.aktivFul!.nezet = { kurzor: 42, sor: 9, mod: 'forras' };
  m.megnyit('b.md');
  m.navigal(-1);
  expect(m.aktivFul?.ut).toBe('A/a.md');
  expect(m.aktivFul?.nezet?.kurzor).toBe(42);
  m.navigal(1);
  expect(m.aktivFul?.ut).toBe('b.md');
  m.utatNevez('A', 'C');
  m.navigal(-1);
  expect(m.aktivFul?.ut).toBe('C/a.md');
  m.megnyit('d.md');
  m.navigal(1);
  expect(m.aktivFul?.ut).toBe('d.md');
  const id = m.aktivFul!.id;
  m.bezar();
  m.ujranyit();
  expect(m.aktivFul?.id).toBe(id);
  expect(m.aktivFul?.ut).toBe('d.md');
  m.navigal(-1);
  expect(m.aktivFul?.ut).toBe('C/a.md');
});
