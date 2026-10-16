// A kísérőmappák felületi állandói (F3 WP6): a szállított alap a core `core/kiserok.py` + `config/os.toml` tükre, a munkatér mappáit
// a core adja (`GET /api/vault/sema` → `kisero`, `kisero_elotag`); a `beallitKiserok` átírja mindhármat és az előtagot.
import { readFileSync } from 'node:fs';
import { afterEach, describe, expect, it } from 'vitest';
import { kartyaUt, KARTYA_MAPPA } from '../src/kartya/allando';
import { kvizUt, KVIZ_MAPPA } from '../src/kviz/allando';
import { beallitKiserok, KISERO_ELOTAG, kiseroUt, OSSZEFOGLALO_MAPPA, osszefoglaloUt } from '../src/osszefoglalas/allando';

const ALAP = { elotag: KISERO_ELOTAG, kartya: KARTYA_MAPPA, kviz: KVIZ_MAPPA, osszefoglalas: OSSZEFOGLALO_MAPPA };
const toml = new TextDecoder().decode(readFileSync(decodeURIComponent(new URL('../../config/os.toml', import.meta.url).pathname).replace(/^\/@fs/, '')));

afterEach(() => beallitKiserok({ kartya: ALAP.kartya, kviz: ALAP.kviz, osszefoglalas: ALAP.osszefoglalas }, ALAP.elotag));

describe('a kísérőmappák alapja', () => {
  it('az os.toml semleges alapjának tükre (előtag + utótag)', () => {
    expect(toml).toContain(`kisero_elotag = "${KISERO_ELOTAG}"`);
    expect(KARTYA_MAPPA).toBe(`${KISERO_ELOTAG}Cards`);
    expect(KVIZ_MAPPA).toBe(`${KISERO_ELOTAG}Quizzes`);
    expect(OSSZEFOGLALO_MAPPA).toBe(`${KISERO_ELOTAG}Summaries`);
    for (const m of [KARTYA_MAPPA, KVIZ_MAPPA, OSSZEFOGLALO_MAPPA]) expect(toml).toContain(`mappa = "${m}"`);
  });

  it('nincs benne a fejlesztő v2-konvenciója', () => {
    for (const m of [KISERO_ELOTAG, KARTYA_MAPPA, KVIZ_MAPPA, OSSZEFOGLALO_MAPPA]) expect(m).not.toMatch(/ATTCHMNTS/);
  });
});

describe('beallitKiserok (a core /api/vault/sema válaszából)', () => {
  it('átírja a három mappát és az előtagot (NFC)', () => {
    beallitKiserok({ kartya: 'Zed - Kártyák', kviz: 'Zed - Kvízek', osszefoglalas: 'Zed - Összefoglalók' }, 'Zed - ');
    expect(kartyaUt('Zed - Kártyák/A — kártyák.md')).toBe(true);
    expect(kvizUt('Zed - Kvízek/K.md')).toBe(true);
    expect(osszefoglaloUt('Zed - Összefoglalók/O.md')).toBe(true);
    expect(kartyaUt(`${ALAP.kartya}/A — kártyák.md`)).toBe(false);
    expect(kiseroUt('T/Zed - Kártyák/x.md')).toBe(true);
    expect(kiseroUt(`${ALAP.elotag}Cards/x.md`)).toBe(false);
    expect(kiseroUt('M/Jegyzet.md')).toBe(false);
  });

  it('a hiányzó vagy üres érték az alapot hagyja', () => {
    beallitKiserok(null, undefined);
    beallitKiserok({ kartya: '', kviz: undefined }, '');
    expect([KISERO_ELOTAG, KARTYA_MAPPA, KVIZ_MAPPA, OSSZEFOGLALO_MAPPA]).toEqual([ALAP.elotag, ALAP.kartya, ALAP.kviz, ALAP.osszefoglalas]);
  });
});
