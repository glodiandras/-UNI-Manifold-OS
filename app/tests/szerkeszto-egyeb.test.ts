// A szerkesztő (C08) többi része: a vault KaTeX-esetei, a regiszterek, a parancsok billentyűi (nem ütköznek a
// héjéval), a fül nézet-állapota, és hogy a saját mentés nem tölti újra a teljes fájllistát.

import { afterEach, describe, expect, it, vi } from 'vitest';
import { alapParancsok } from '../src/alapParancsok';
import { CoreKapcsolat } from '../src/lib/core/ws.svelte';
import { Felulet } from '../src/lib/elrendezes/felulet.svelte';
import { MAX_NEZET_ALLAPOT, Munkaterulet } from '../src/lib/elrendezes/munkaterulet.svelte';
import { nezetek } from '../src/lib/elrendezes/nezetek.svelte';
import { normalizalLeiras } from '../src/lib/parancsok/billentyuk';
import { kezel } from '../src/lib/parancsok/kezelo';
import { Regiszter } from '../src/lib/parancsok/regiszter';
import { VaultFajlok } from '../src/lib/vault/fajlok.svelte';
import { szerkesztoTelepit } from '../src/szerkeszto';
import { eloszlas } from '../src/szerkeszto/meres';
import { CalloutTipusok } from '../src/szerkeszto/renderelok/callout';
import { katexEllenoriz, katexHtml, kepletElokeszit } from '../src/szerkeszto/renderelok/katex';
import { KodRendeloRegiszter } from '../src/szerkeszto/renderelok/regiszter';

afterEach(() => vi.restoreAllMocks());

describe('KaTeX: a vault esetei', () => {
  it.each([
    ['\\tg x + \\ctg y', false],
    ['3{,}14 \\cdot 10^{-3}', false],
    ['K_\\max = 840\\ \\mathrm{N}', false],
    ['F_\\min = \\mu_0 \\cdot mg', false],
    ['F_\\text{gáz \\to rakéta} = F_\\text{rakéta \\to gáz}', true],
    ['\\lim\\limits_{n \\to \\infty} a_n = A', false],
    ['2+c\\not\\equiv0\\pmod3 \\iff c\\notin\\{1,4,7\\}', true],
    ['\\begin{cases} x & x \\ge 0 \\\\ -x & x < 0 \\end{cases}', true],
    ['\\begin{aligned} a &= b \\\\ &= c \\end{aligned}', true],
    ['\\begin{pmatrix}x\\\\y\\end{pmatrix}', true],
    ['E_{hő} = \\frac{E_{el}}{0{,}3367}', false],
    ['90° \\text{és} W_{gáz}', false],
    ['I_1 + I_2 = I_3 \\tag{1}', true],
    ['\\overrightarrow{AB} \\perp \\vec{n}', false],
    ['\\boxed{x = \\dfrac{1}{2}}', true],
  ])('%s', (tex, display) => {
    expect(() => katexEllenoriz(tex, display)).not.toThrow();
  });

  it('a valódi szintaxishiba hiba marad (a vault 5 ilyen képletét a felhasználó javítja)', () => {
    expect(() => katexEllenoriz('n_{\\text{olaj}} = 1{,}46}', false)).toThrow();
    expect(() => katexEllenoriz('\\left{1,; 2\\right}', true)).toThrow();
    // a felületen nem dob: a forrás a hiba színével látszik
    expect(katexHtml('\\left{1\\right}', true)).toContain('katex-error');
  });

  it('a zárójel nélküli operátornév az indexben kapcsos zárójelet kap; más nem változik', () => {
    expect(kepletElokeszit('K_\\max + a^\\sin x')).toBe('K_{\\max} + a^{\\sin} x');
    expect(kepletElokeszit('K_{\\max} + \\maxima')).toBe('K_{\\max} + \\maxima');
    expect(kepletElokeszit('x_1 + \\max(a,b)')).toBe('x_1 + \\max(a,b)');
  });
});

describe('regiszterek', () => {
  it('kódblokk-renderelő: nyelvek, kisbetű, az info első szava; ütközés hiba', () => {
    const r = new KodRendeloRegiszter();
    const m = { nyelv: ['mermaid', 'Graph'], render: () => {} };
    const le = r.regisztral(m);
    expect(r.keres('mermaid')).toBe(m);
    expect(r.keres('  graph  extra info')).toBe(m);
    expect(r.keres('python')).toBeUndefined();
    expect(() => r.regisztral({ nyelv: 'graph', render: () => {} })).toThrow(/már regisztrált/);
    le();
    expect(r.keres('mermaid')).toBeUndefined();
  });

  it('callout-típusok: alias, magyar alapcím, ismeretlen típus a note stílusával; bővíthető', () => {
    const t = new CalloutTipusok();
    expect(t.megjelenes('TLDR')).toMatchObject({ tipus: 'tldr', cim: 'Röviden', szin: 'cian' });
    expect(t.megjelenes('danger')).toMatchObject({ cim: 'Veszély', szin: 'piros' });
    expect(t.megjelenes('sajat')).toMatchObject({ cim: 'Sajat', szin: 'kek' });
    const le = t.regisztral({ nevek: ['card'], cimek: { card: 'Kártya' }, ikon: [], szin: 'lila' });
    expect(t.megjelenes('card')).toMatchObject({ cim: 'Kártya', szin: 'lila' });
    expect(() => t.regisztral({ nevek: ['note'], cimek: {}, ikon: [], szin: 'kek' })).toThrow();
    le();
  });
});

describe('parancsok', () => {
  it('a szerkesztő billentyűi nem ütköznek a héjéval; a nézet és a parancsok leiratkoznak', () => {
    const reg = new Regiszter();
    const leHej = alapParancsok(reg, new Felulet({}));
    const le = szerkesztoTelepit(reg, new CoreKapcsolat('ws://127.0.0.1:1/ws'));
    for (const [akkord, id] of [
      ['Mod+E', 'szerkeszto.olvaso'],
      ['Mod+Shift+E', 'szerkeszto.forras'],
      ['Mod+S', 'szerkeszto.mentes'],
      ['Mod+B', 'szerkeszto.felkover'],
      ['Mod+I', 'szerkeszto.dolt'],
      ['Mod+Shift+H', 'szerkeszto.kiemeles'],
      ['Mod+F', 'szerkeszto.kereses'],
    ])
      expect(reg.akkordhoz(normalizalLeiras(akkord))?.id, akkord).toBe(id);
    // a ⌘H a macOS „Manifold elrejtése” (20. döntés): a felület nem nyelheti el
    expect(reg.akkordhoz(normalizalLeiras('Mod+H'))).toBeUndefined();
    const cmdH = new KeyboardEvent('keydown', { key: 'h', code: 'KeyH', metaKey: true, cancelable: true });
    expect(kezel(cmdH, reg)).toBe(false);
    expect(cmdH.defaultPrevented).toBe(false);
    // aktív szerkesztő nélkül egyik sem fut
    expect(reg.futtat('szerkeszto.olvaso')).toBe(false);
    expect(nezetek.valaszt({ id: 'f', ut: 'a.md' }, undefined)?.id).toBe('szerkeszto.md');
    expect(nezetek.valaszt({ id: 'f', ut: 'a.canvas' }, undefined)?.id).not.toBe('szerkeszto.md');
    le();
    leHej();
    expect(reg.kap('szerkeszto.olvaso')).toBeUndefined();
    expect(nezetek.valaszt({ id: 'f', ut: 'a.md' }, undefined)).toBeUndefined();
  });
});

describe('a fül nézet-állapota (C08)', () => {
  it('megmarad, a túl nagy elmarad; a másik fájl megnyitása és az eltűnés törli', () => {
    const m = new Munkaterulet();
    m.megnyit('a.md');
    m.aktivFul!.nezet = { mod: 'olvaso', sor: 12 };
    const ujra = new Munkaterulet(m.sorosit());
    expect(ujra.aktivFul!.nezet).toEqual({ mod: 'olvaso', sor: 12 });
    m.aktivFul!.nezet = { x: 'y'.repeat(MAX_NEZET_ALLAPOT) };
    expect(new Munkaterulet(m.sorosit()).aktivFul!.nezet).toBeUndefined();
    m.aktivFul!.nezet = { mod: 'forras' };
    m.megnyit('b.md');
    expect(m.aktivFul!.nezet).toBeUndefined();
    m.aktivFul!.nezet = { mod: 'forras' };
    m.eltuntek(new Set(['b.md']));
    expect(m.aktivFul!.nezet).toBeUndefined();
  });

  it('a szerkesztő módja a felület állapotában', () => {
    expect(new Felulet({}).szerkesztoMod).toBe('elo');
    const f = new Felulet({ szerkesztoMod: 'forras' });
    expect(f.szerkesztoMod).toBe('forras');
    expect(f.sorosit().szerkesztoMod).toBe('forras');
    expect(new Felulet({ szerkesztoMod: 'valami' }).szerkesztoMod).toBe('elo');
  });
});

describe('fájllista: a saját mentés nem tölt újra', () => {
  it('ismert út tartalmi változása nem, új vagy eltűnt fájl igen', () => {
    vi.useFakeTimers();
    try {
      const f = new VaultFajlok();
      f.beallit([{ ut: 'a.md', tipus: 'md', meret: 1, mtime: 1 }]);
      const frissit = vi.spyOn(f, 'frissit').mockResolvedValue();
      const k = new CoreKapcsolat('ws://127.0.0.1:1/ws');
      const le = f.figyel(k);
      k.szetoszt({ tipus: 'vault_valtozas', utak: ['a.md'], kulso: [], torolt: [] });
      vi.advanceTimersByTime(1000);
      expect(frissit).not.toHaveBeenCalled();
      k.szetoszt({ tipus: 'vault_valtozas', utak: ['uj.md'], kulso: ['uj.md'], torolt: [] });
      vi.advanceTimersByTime(1000);
      expect(frissit).toHaveBeenCalledTimes(1);
      k.szetoszt({ tipus: 'vault_valtozas', utak: [], kulso: [], torolt: ['a.md'] });
      vi.advanceTimersByTime(1000);
      expect(frissit).toHaveBeenCalledTimes(2);
      le();
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('a mérő eloszlása', () => {
  it('percentilisek', () => {
    const e = eloszlas(Array.from({ length: 100 }, (_, i) => i + 1));
    expect(e).toEqual({ p50: 50, p95: 95, p99: 99, max: 100, atlag: 50.5 });
  });
});
