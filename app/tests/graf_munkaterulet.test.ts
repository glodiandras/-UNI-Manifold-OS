import { describe, expect, it } from 'vitest';
import { Munkaterulet, nezetFul } from '../src/lib/elrendezes/munkaterulet.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';

describe('a gráf mint nézet-fül', () => {
  it('az üres „Új fül” átalakul gráffá, a nézet-fül nem az', () => {
    const m = new Munkaterulet();
    expect(nezetFul(m.aktivFul)).toBe(false);
    m.megnyitNezet('graf', { mod: 'globalis' });
    expect(m.aktivPanel.fulek).toHaveLength(1);
    expect(nezetFul(m.aktivFul)).toBe(true);
    expect(m.aktivFul?.ut).toBeNull();
    expect(m.aktivFul?.nezet).toEqual({ mod: 'globalis', tipus: 'graf' });
  });

  it('ugyanaz a nézet-fül nem duplázódik: aktiválódik, és az állapota frissül', () => {
    const m = new Munkaterulet();
    m.megnyit('a.md');
    m.megnyitNezet('graf', { mod: 'helyi', kozeppont: 'a.md', melyseg: 1 });
    expect(m.aktivPanel.fulek).toHaveLength(2);
    m.megnyit('b.md', 'ujful');
    m.megnyitNezet('graf', { mod: 'helyi', kozeppont: 'b.md', melyseg: 2 });
    expect(m.aktivPanel.fulek.filter((f) => nezetFul(f))).toHaveLength(1);
    expect(m.aktivFul?.nezet).toMatchObject({ mod: 'helyi', kozeppont: 'b.md', melyseg: 2 });
    m.megnyitNezet('graf', { mod: 'globalis' }); // a globális külön fül
    expect(m.aktivPanel.fulek.filter((f) => nezetFul(f))).toHaveLength(2);
  });

  it('a gráfról megnyitott jegyzet új fülbe kerül (a gráf nem íródik felül)', () => {
    const m = new Munkaterulet();
    m.megnyitNezet('graf', { mod: 'globalis' });
    const graf = m.aktivFul!.id;
    m.megnyit('x/jegyzet.md'); // alap mód: az aktív fülben — de az a gráf
    expect(m.aktivPanel.fulek).toHaveLength(2);
    expect(m.aktivPanel.fulek.find((f) => f.id === graf)?.nezet?.tipus).toBe('graf');
    expect(m.aktivFul?.ut).toBe('x/jegyzet.md');
  });

  it('a nézet-fül túléli a mentést és a betöltést, és az eltűnt fájl nem üríti ki', () => {
    const m = new Munkaterulet();
    m.megnyitNezet('graf', { mod: 'helyi', kozeppont: 'a.md', melyseg: 3 });
    const ujra = new Munkaterulet(JSON.parse(JSON.stringify(m.sorosit())));
    expect(nezetFul(ujra.aktivFul)).toBe(true);
    expect(ujra.aktivFul?.nezet).toMatchObject({ tipus: 'graf', kozeppont: 'a.md', melyseg: 3 });
    ujra.eltuntek(new Set(['a.md']));
    expect(nezetFul(ujra.aktivFul)).toBe(true);
  });

  it('a gráf felülírásai a felület mentésében: ép érték megmarad, hibás eldobódik', () => {
    const f = new Felulet({ graf: { lekerdezes: 'tag:#x', arvak: false, erok: { rugo: 9 }, ismeretlen: 1 } });
    expect(f.graf).toEqual({ lekerdezes: 'tag:#x', arvak: false, erok: { rugo: 3 } });
    expect(new Felulet(JSON.parse(JSON.stringify(f.sorosit()))).graf).toEqual(f.graf);
    expect(new Felulet({}).graf).toEqual({});
  });
});
