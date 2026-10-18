// WCAG AA a tokenekből, mindkét témára: szöveg ≥ 4,5; nagy szöveg, UI-elem és fókuszgyűrű ≥ 3.
import { describe, expect, it } from 'vitest';
import { kontraszt, tokenSzinek } from '../src/lib/design/kontraszt';
import css from '../src/styles/tokens.css?raw';

const szinek = tokenSzinek(css);

const HATTEREK = ['hatter', 'hatter-oldalsav', 'hatter-emelt', 'hatter-hover', 'hatter-aktiv'];
// A burgundi akcentus (C37): a kitöltött gomb és a márkafelület, a hiba–akcent megkülönböztetés.
const FELULETEK_AKCENT = [...HATTEREK, 'hatter-kijelolt'];

/** [előtér, háttér, minimum] */
const PAROK: [string, string, number][] = [
  ...HATTEREK.flatMap((h): [string, string, number][] => [
    ['szoveg', h, 4.5],
    ['szoveg-masodlagos', h, 4.5],
    ['szoveg-halvany', h, 4.5],
    ['akcent-szoveg', h, 4.5],
    ['fokusz-gyuru', h, 3],
    ['keret-mezo', h, 3],
  ]),
  ['szoveg', 'hatter-kijelolt', 4.5],
  ['szoveg-masodlagos', 'hatter-kijelolt', 4.5],
  ['kiemeles', 'hatter-kijelolt', 4.5],
  ['kiemeles', 'hatter-emelt', 4.5],
  ['akcent-eloter', 'akcent-kitoltes', 4.5],
  ['akcent-eloter', 'akcent-hover', 4.5],
  // az akcentus mint vonal és jel (célvonala, elválasztó, a futó feladat pontja, kurzor, töltősáv): UI-elem, minden síkon
  ...FELULETEK_AKCENT.map((h): [string, string, number] => ['akcent', h, 3]),
  ...['hatter-kod', 'hatter-kijelolt'].map((h): [string, string, number] => ['akcent-szoveg', h, 4.5]),
  ['fokusz-gyuru', 'hatter-kijelolt', 3],
  ['fokusz-gyuru', 'hatter-kod', 3],
  // a kitöltött gomb határa (C38, K226): a mély kitöltés sötétben a felülettől csak 1,2–1,3:1-re válik el, ezért 1 px-es
  // belső vonalat kap; a vonal minden síkon, ahol kitöltött gomb állhat (a hover is), UI-elem (≥ 3, WCAG 1.4.11)
  ...['hatter', 'hatter-oldalsav', 'hatter-emelt', 'hatter-hover'].map((h): [string, string, number] => ['akcent-kitoltes-keret', h, 3]),
  // a márka (az app-ikon színei): a krém a burgundin szöveg
  ['krem', 'burgundi', 4.5],
  ['akcent-eloter', 'burgundi', 4.5],
  // a hiba és az akcent szomszédos színcsalád: a hibát a hatter-hiba doboz és az ikon is jelzi; mindkettő olvasható
  ['hiba', 'hatter-kijelolt', 4.5],
  ['akcent-szoveg', 'hiba-hatter', 4.5],
  ['siker', 'siker-hatter', 4.5],
  ['figyelmeztetes', 'figyelmeztetes-hatter', 4.5],
  ['hiba', 'hiba-hatter', 4.5],
  ['siker', 'hatter-emelt', 4.5],
  ['figyelmeztetes', 'hatter-emelt', 4.5],
  ['hiba', 'hatter-emelt', 4.5],
  ['akcent', 'hatter-oldalsav', 3],
  // a tulajdonság-panel, a címkefa és az előzmények (C11b)
  ['szoveg-masodlagos', 'figyelmeztetes-hatter', 4.5],
  ['hiba', 'hatter', 4.5],
  ['figyelmeztetes', 'hatter', 4.5],
  ['akcent-szoveg', 'hatter-kijelolt', 4.5],
  ['szoveg-halvany', 'hatter-kijelolt', 4.5],
  // a Manifold-vezérlő (C17): halvány szöveg a lapon és a sor hoverén, a napló szövege a kódháttéren, a haladássáv
  // töltése (UI-elem, ≥ 3) a sáv hátterén
  ['szoveg-halvany', 'hatter-emelt', 4.5],
  ['szoveg-halvany', 'hatter-hover', 4.5],
  ['szoveg-masodlagos', 'hatter-kod', 4.5],
  ['akcent', 'hatter-aktiv', 3],
  // a gráfnézet (C13): a csúcsszínek UI-elemek (≥ 3) a vászon hátterén
  ...['jegyzet', 'canvas', 'melleklet', 'cimke', 'feloldatlan'].map((n): [string, string, number] => [`graf-${n}`, 'hatter', 3]),
  // a canvas (C14): a preset szín a kártya fejlécének szövege a halvány kitöltésen (≥ 4,5), és keretként, élként
  // a vászon hátterén (UI-elem, ≥ 3); a kártya szövege a kitöltésen
  ...['1', '2', '3', '4', '5', '6'].flatMap((n): [string, string, number][] => [
    [`canvas-szin-${n}`, `canvas-szin-${n}-hatter`, 4.5],
    [`canvas-szin-${n}`, 'hatter', 3],
    ['szoveg', `canvas-szin-${n}-hatter`, 4.5],
    ['szoveg-halvany', `canvas-szin-${n}-hatter`, 4.5],
  ]),
  // a szerkesztő (C08): kódblokk, kiemelés, callout
  ['szoveg', 'hatter-kod', 4.5],
  ['szoveg-halvany', 'hatter-kod', 4.5],
  ...['kulcsszo', 'szoveg', 'szam', 'megjegyzes', 'fuggveny', 'tipus', 'meta'].map(
    (n): [string, string, number] => [`kod-${n}`, 'hatter-kod', 4.5],
  ),
  ['szoveg', 'jeloles-hatter', 4.5],
  ['lejatszo-felirat', 'lejatszo-hatter', 4.5],
  ...['kek', 'cian', 'zold', 'narancs', 'piros', 'lila', 'szurke'].flatMap((n): [string, string, number][] => [
    [`callout-${n}`, `callout-${n}-hatter`, 4.5],
    ['szoveg', `callout-${n}-hatter`, 4.5],
    ['szoveg-halvany', `callout-${n}-hatter`, 4.5],
  ]),
];

describe('kontraszt (WCAG AA)', () => {
  it('a tokenek mindkét témában beolvashatók', () => {
    for (const nev of ['hatter', 'szoveg', 'akcent', 'fokusz-gyuru']) {
      expect(szinek[nev], nev).toBeDefined();
    }
  });

  for (const [tema, i] of [['világos', 0], ['sötét', 1]] as const) {
    it.each(PAROK)(`${tema}: %s a(z) %s háttéren ≥ %s`, (elo, hat, min) => {
      const arany = kontraszt(szinek[elo][i], szinek[hat][i]);
      expect(arany, `${elo} / ${hat}: ${arany.toFixed(2)}`).toBeGreaterThanOrEqual(min);
    });
  }

  it('az app-ikon: a bordó lap a mélybordó alapon grafika-kontraszt (≥ 3, az ikon témától független)', () => {
    expect(kontraszt('#c23a52', '#3d1119')).toBeGreaterThanOrEqual(3);
    expect(kontraszt('#f3ece3', '#3d1119')).toBeGreaterThanOrEqual(4.5);
  });

  it('a canvas preset színei a callout-tokenekre képeződnek (T163), a sárga saját', () => {
    for (const [n, c] of [['1', 'piros'], ['2', 'narancs'], ['4', 'zold'], ['5', 'cian'], ['6', 'lila']]) {
      expect(szinek[`canvas-szin-${n}`], n).toEqual(szinek[`callout-${c}`]);
      expect(szinek[`canvas-szin-${n}-hatter`], n).toEqual(szinek[`callout-${c}-hatter`]);
    }
    expect(css).not.toMatch(/canvas-sarga/);
  });

  it('a kontraszt képlete a WCAG ismert értékeit adja', () => {
    expect(kontraszt('#000000', '#ffffff')).toBeCloseTo(21, 5);
    expect(kontraszt('#777777', '#ffffff')).toBeCloseTo(4.48, 2);
  });
});
