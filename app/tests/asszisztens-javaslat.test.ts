// A linkjavaslat a szerkesztőben (C30b-mag; T064): az aláhúzás a core válaszából, a Tab csak látható és aktív javaslatnál
// fogad el (egy ⌘Z lépés), az Esc elvet, a tiltott helyeken (kód, frontmatter, link, plot/teszt blokk, képlet) nincs javaslat,
// a kapcsoló és a küszöb némít, az elavult válasz eldobódik, a döntés útvonal és szöveg nélkül megy a statisztikába.

import { undo } from '@codemirror/commands';
import { EditorState } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { alapKliens, aktivJavaslatAllapot, javaslatUrit, type JavaslatKliens, lathatoJavaslatok } from '../src/szerkeszto/asszisztens/javaslat';
import {
  aktivJavaslat,
  AKTIV_TAVOLSAG,
  bekezdesHatar,
  hasonlosagSzuro,
  kuszobSzabaly,
  MAX_ALAP,
  utf16Konvertalo,
  VART_ALAP_MS,
} from '../src/szerkeszto/asszisztens/javaslatSegedek';
import { bovitmenyek } from '../src/szerkeszto/beallitas';
import { emlitesLink } from '../src/szerkeszto/linkek/emlites';
import type { EmlitesTalalat, EmlitesValasz, HasonlosagValasz, JavaslatKuszob } from '../src/lib/asszisztens/tipusok';
import { billentyu, gepel, tisztit } from './notion-segedek';
import { ensureSyntaxTree } from '@codemirror/language';

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  tisztit();
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

/** Az álmag: a szövegben megkeresi a neveket (kis-nagybetűtől függetlenül, a nyers szövegben — a core maszkolását NEM
 *  utánozza, hogy a felület saját védelme is látszódjon), és kódpont-pozíciót ad, mint a valódi API. */
function alMag(nevek: Record<string, string>, tobbertelmu: string[] = []) {
  return (szoveg: string): EmlitesValasz => {
    const ki: EmlitesTalalat[] = [];
    for (const [nev, cel] of Object.entries(nevek)) {
      const re = new RegExp(nev.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'giu');
      for (const m of szoveg.matchAll(re)) {
        const kezd = Array.from(szoveg.slice(0, m.index)).length;
        const sorok = szoveg.slice(0, m.index).split('\n');
        const tobb = tobbertelmu.includes(nev);
        ki.push({
          kezd, veg: kezd + Array.from(m[0]).length, sor: sorok.length, oszlop: Array.from(sorok[sorok.length - 1]).length,
          szoveg: m[0], cel: tobb ? null : cel, tobbertelmu: tobb, jeloltek: [], forras: 'nev',
        });
      }
    }
    return { ut: 'Jegyzet.md', emlitesek: ki.sort((a, b) => a.kezd - b.kezd), kapcsolo: true };
  };
}

interface Opciok {
  kuszob?: JavaslatKuszob | null;
  /** a C25c hasonlóság álkliense (a jegyzet–cél pontok); hiányzik: a kliensnek nincs `hasonlosag` képessége */
  hasonlosag?: (celok: string[]) => Promise<HasonlosagValasz>;
  kapcsolo?: boolean;
  csakOlvashato?: boolean;
  nevek?: Record<string, string>;
  tobbertelmu?: string[];
  kesleltetes?: () => Promise<void>;
}

function felallit(doc: string, kurzor = doc.length, o: Opciok = {}) {
  const allapot = { be: o.kapcsolo ?? true };
  const mag = alMag(o.nevek ?? { Newton: 'Fizika/Newton.md' }, o.tobbertelmu);
  const kliens: JavaslatKliens & {
    emlitesek: ReturnType<typeof vi.fn>;
    dontes: ReturnType<typeof vi.fn>;
    hasonlosag: ReturnType<typeof vi.fn>;
  } = {
    emlitesek: vi.fn(async (_ut: string, szoveg: string) => {
      await o.kesleltetes?.();
      return mag(szoveg);
    }),
    dontes: vi.fn(async () => ({ fogadva: true })),
    kuszob: vi.fn(async (): Promise<JavaslatKuszob | null> => o.kuszob ?? { szint: 'alap', szorzo: 1 }),
    hasonlosag: vi.fn(async (_ut: string, celok: string[]) => {
      if (!o.hasonlosag) throw new Error('nincs hasonlóság-álkliens');
      return o.hasonlosag(celok);
    }),
  };
  if (!o.hasonlosag) delete (kliens as { hasonlosag?: unknown }).hasonlosag; // a képesség hiánya: a lexikai javaslat változatlan
  const hely = document.createElement('div');
  document.body.appendChild(hely);
  const nezet = new EditorView({
    state: EditorState.create({
      doc,
      selection: { anchor: kurzor },
      extensions: bovitmenyek({
        mod: 'elo',
        csakOlvashato: o.csakOlvashato ?? false,
        ut: 'Jegyzet.md',
        cimke: 'próba',
        linkNev: () => 'Jegyzet',
        javaslat: {
          ut: 'Jegyzet.md',
          kapcsolo: () => allapot.be,
          linkCel: async (celUt) => celUt.replace(/^.*\//, '').replace(/\.md$/, ''),
          kliens,
        },
      }),
    }),
    parent: hely,
  });
  ensureSyntaxTree(nezet.state, nezet.state.doc.length, 5000);
  return { nezet, kliens, allapot };
}

/** Pont-álkliens: a megadott célok pontjai, a többi `null`. */
function pontok(t: Record<string, number | null>, allapot: HasonlosagValasz['allapot'] = 'ok') {
  return async (celok: string[]): Promise<HasonlosagValasz> => ({
    ut: 'Jegyzet.md',
    allapot,
    elavult: false,
    pontok: Object.fromEntries(celok.map((c) => [c, t[c] ?? null])),
  });
}

/** Beírja a szöveget a végére (karakterenként), majd lejár a csend: megjön a javaslat. */
async function gepelEsVar(nezet: EditorView, szoveg: string, ms = VART_ALAP_MS + 100) {
  gepel(nezet, szoveg);
  await vi.advanceTimersByTimeAsync(ms);
}

const tab = (v: EditorView) => billentyu(v, 'Tab');
const esc = (v: EditorView) => billentyu(v, 'Escape');

describe('segédek', () => {
  it('a kódpontból UTF-16 lesz (emoji, ékezet), akár visszafelé is', () => {
    const f = utf16Konvertalo('a😀é𝔸b');
    expect([0, 1, 2, 3, 4, 5].map(f)).toEqual([0, 1, 3, 4, 6, 7]);
    expect(f(2)).toBe(3); // visszalépés: újraszámol
  });

  it('a küszöb-szabály: nema tilt, szigorú egy javaslatot enged és lassít, alap/hiányzó az alap', () => {
    expect(kuszobSzabaly({ szint: 'nema', szorzo: null }).tilt).toBe(true);
    expect(kuszobSzabaly({ szint: 'szigoru', szorzo: 1.5 })).toEqual({ tilt: false, vartMs: 1800, max: 1 });
    expect(kuszobSzabaly({ szint: 'alap', szorzo: 1 })).toEqual({ tilt: false, vartMs: VART_ALAP_MS, max: MAX_ALAP });
    expect(kuszobSzabaly(null)).toEqual({ tilt: false, vartMs: VART_ALAP_MS, max: MAX_ALAP });
  });

  it('az aktív javaslat: amelyiken a kurzor áll, vagy a vége előtti legfeljebb AKTIV_TAVOLSAG kódegység, ugyanabban a sorban', () => {
    const { nezet } = felallit('Newton' + ' '.repeat(AKTIV_TAVOLSAG + 2) + '\nmásik sor', 0);
    const doc = nezet.state.doc;
    const j = { id: 1, from: 0, to: 6, szoveg: 'Newton', celUt: 'N.md', kulcs: 'k' };
    expect(aktivJavaslat([j], doc, 3)).toBe(j);
    expect(aktivJavaslat([j], doc, 6)).toBe(j);
    expect(aktivJavaslat([j], doc, 6 + AKTIV_TAVOLSAG + 1)).toBe(null);
    expect(aktivJavaslat([j], doc, doc.length - 2)).toBe(null); // másik sorban
  });

  it('a bekezdés-határ az üres soroknál ér véget', () => {
    const { nezet } = felallit('a\nb\n\nc\nd\n\ne');
    const d = nezet.state.doc;
    expect(bekezdesHatar(d, 3)).toEqual([0, 3]);
    expect(bekezdesHatar(d, 6)).toEqual([5, 8]);
  });

  it('a link szövege megegyezik a jobb panel „linkeletlen említés” szabályával', () => {
    expect(emlitesLink('Newton', 'Newton', 'Newton')).toBe('[[Newton]]');
    expect(emlitesLink('Newton', 'Newton', 'newton')).toBe('[[Newton|newton]]');
  });
});

describe('aláhúzás', () => {
  it('gépelés és csend után megjelenik, a kódpont-pozíció UTF-16-ra váltva (emoji előtte)', async () => {
    const { nezet, kliens } = felallit('😀 szöveg ');
    await gepelEsVar(nezet, 'Newton törvénye');
    expect(kliens.emlitesek).toHaveBeenCalledTimes(1);
    const [j] = lathatoJavaslatok(nezet.state);
    expect(nezet.state.sliceDoc(j.from, j.to)).toBe('Newton');
    expect(nezet.dom.querySelectorAll('.cm-javaslat').length).toBe(1);
  });

  it('nyitáskor és szerkesztés nélkül nem kérdez; a gépelés közbeni csendig sem', async () => {
    const { nezet, kliens } = felallit('Newton');
    await vi.advanceTimersByTimeAsync(5000);
    expect(kliens.emlitesek).not.toHaveBeenCalled();
    gepel(nezet, ' ');
    await vi.advanceTimersByTimeAsync(VART_ALAP_MS - 200);
    gepel(nezet, 'x'); // újra gépel: az időzítő újraindul
    await vi.advanceTimersByTimeAsync(VART_ALAP_MS - 200);
    expect(kliens.emlitesek).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(400);
    expect(kliens.emlitesek).toHaveBeenCalledTimes(1);
  });

  it('a többértelmű említésre nem javasol (rossz linket nem ajánlunk)', async () => {
    const { nezet } = felallit('', 0, { tobbertelmu: ['Newton'] });
    await gepelEsVar(nezet, 'Newton törvénye');
    expect(lathatoJavaslatok(nezet.state)).toEqual([]);
  });

  it('az aláhúzás a gépelésre vele mozog; a szó belsejébe írás eltünteti, a szóköz nem', async () => {
    const { nezet } = felallit('');
    await gepelEsVar(nezet, 'Newton');
    expect(lathatoJavaslatok(nezet.state).length).toBe(1);
    nezet.dispatch({ changes: { from: 0, insert: 'Az ' }, userEvent: 'input.type' });
    const [j] = lathatoJavaslatok(nezet.state);
    expect(nezet.state.sliceDoc(j.from, j.to)).toBe('Newton');
    gepel(nezet, ' ');
    expect(lathatoJavaslatok(nezet.state).length).toBe(1);
    nezet.dispatch({ changes: { from: j.from + 3, insert: 'x' }, userEvent: 'input.type' });
    expect(lathatoJavaslatok(nezet.state).length).toBe(0);
  });

  it('a szó végére írt betű (Newtons) eltünteti: nem önálló szó', async () => {
    const { nezet } = felallit('');
    await gepelEsVar(nezet, 'Newton');
    gepel(nezet, 's');
    expect(lathatoJavaslatok(nezet.state)).toEqual([]);
  });

  it('csak a kurzor bekezdésének javaslatai látszanak, a kurzorhoz legközelebbiek, a küszöb szerinti számban', async () => {
    const { nezet } = felallit('Newton elöl\n\nNewton hátul és Newton megint ');
    gepel(nezet, '.');
    await vi.advanceTimersByTimeAsync(VART_ALAP_MS + 100);
    expect(nezet.dom.querySelectorAll('.cm-javaslat').length).toBe(2); // az utolsó bekezdés két említése
    expect(lathatoJavaslatok(nezet.state).length).toBe(3); // az elöl álló is megvan, csak nem látszik
  });

  it('kapcsoló ki: nincs kérés, nincs aláhúzás, és a Tab a behúzásé', async () => {
    const { nezet, kliens } = felallit('', 0, { kapcsolo: false });
    await gepelEsVar(nezet, 'Newton');
    expect(kliens.emlitesek).not.toHaveBeenCalled();
    expect(nezet.dom.querySelector('.cm-javaslat')).toBeNull();
    tab(nezet);
    expect(nezet.state.doc.toString()).not.toContain('[[');
    expect(nezet.state.doc.toString()).toContain('\t'); // a behúzás kezelte
  });

  it('a kapcsoló kikapcsolása (javaslatUrit) eltünteti a meglévő aláhúzást, és a Tab nem hat', async () => {
    const { nezet, allapot, kliens } = felallit('');
    await gepelEsVar(nezet, 'Newton');
    expect(nezet.dom.querySelector('.cm-javaslat')).not.toBeNull();
    allapot.be = false;
    nezet.dispatch({ effects: javaslatUrit.of(null) });
    expect(nezet.dom.querySelector('.cm-javaslat')).toBeNull();
    tab(nezet);
    expect(nezet.state.doc.toString()).not.toContain('[[');
    expect(kliens.dontes).not.toHaveBeenCalled();
  });

  it('a némított fajta (küszöb: nema) nem kérdez és nem húz alá', async () => {
    const { nezet, kliens } = felallit('', 0, { kuszob: { szint: 'nema', szorzo: null } });
    await gepelEsVar(nezet, 'Newton');
    expect(kliens.emlitesek).not.toHaveBeenCalled();
    expect(nezet.dom.querySelector('.cm-javaslat')).toBeNull();
  });

  it('szigorú küszöb: lassabban kérdez (a szorzó), és egyszerre csak egy javaslat látszik', async () => {
    const { nezet, kliens } = felallit('', 0, { kuszob: { szint: 'szigoru', szorzo: 1.5 } });
    gepel(nezet, 'Newton és Newton ');
    // az első kérés az alap várakozás után indul (a küszöböt még nem ismerte); a második szerkesztésnél már a szorzott
    await vi.advanceTimersByTimeAsync(VART_ALAP_MS + 100);
    expect(kliens.emlitesek).toHaveBeenCalledTimes(1);
    expect(nezet.dom.querySelectorAll('.cm-javaslat').length).toBe(1);
    gepel(nezet, 'x');
    await vi.advanceTimersByTimeAsync(VART_ALAP_MS + 100);
    expect(kliens.emlitesek).toHaveBeenCalledTimes(1); // a szigorú várakozás (1800 ms) még nem telt le
    await vi.advanceTimersByTimeAsync(800);
    expect(kliens.emlitesek).toHaveBeenCalledTimes(2);
  });

  it('csak olvasható szerkesztőben nincs kérés és nincs javaslat', async () => {
    const { nezet, kliens } = felallit('Newton ', 7, { csakOlvashato: true });
    nezet.dispatch({ changes: { from: 0, insert: 'x' }, annotations: [] });
    await vi.advanceTimersByTimeAsync(VART_ALAP_MS + 100);
    expect(kliens.emlitesek).not.toHaveBeenCalled();
  });

  it('az elavult válasz eldobódik (közben gépelt)', async () => {
    let kioldo: () => void = () => undefined;
    const { nezet, kliens } = felallit('', 0, { kesleltetes: () => new Promise<void>((ok) => (kioldo = ok)) });
    await gepelEsVar(nezet, 'Newton');
    expect(kliens.emlitesek).toHaveBeenCalledTimes(1);
    gepel(nezet, ' ma'); // a válasz előtt változik a dokumentum
    kioldo();
    await vi.advanceTimersByTimeAsync(10);
    expect(lathatoJavaslatok(nezet.state)).toEqual([]);
  });

  it('hibás válasz (a core nem elérhető) nem dob és nem húz alá', async () => {
    const { nezet, kliens } = felallit('');
    kliens.emlitesek.mockRejectedValue(new Error('nincs'));
    await gepelEsVar(nezet, 'Newton');
    expect(lathatoJavaslatok(nezet.state)).toEqual([]);
  });
});

describe('tiltott helyek: a felület a core maszkolásán túl is kihagyja', () => {
  // az álmag a nyers szövegben talál, ezért ami itt kimarad, a felület saját szűrője
  const ESETEK: [string, string][] = [
    ['kódblokk', 'Elöl\n\n```\nNewton törvénye\n```\n'],
    ['plot blokk', 'Elöl\n\n```plot\nf(x)=Newton\n```\n'],
    ['teszt blokk', 'Elöl\n\n```teszt\nNewton 5\n```\n'],
    ['kódblokk nyelvvel', 'Elöl\n\n```cpp\n// Newton\nint x;\n```\n'],
    ['frontmatter', '---\nTags: Newton\nSource: Newton\n---\nszöveg\n'],
    ['soron belüli kód', 'Ez `Newton` kód.'],
    ['wikilink', 'Lásd [[Newton]] és [[Valami|Newton]].'],
    ['md-link', 'Lásd [Newton](https://pelda.hu) itt.'],
    ['md-link címe', 'Lásd [szöveg](Newton.md) itt.'],
    ['URL', 'Itt: https://pelda.hu/Newton oldal.'],
    ['beágyazás', 'Kép: ![[Newton.png]]'],
    ['soron belüli képlet', 'Ahol $F = Newton$ áll.'],
    ['képletblokk', 'Elöl\n\n$$\nNewton = 1\n$$\n'],
    ['HTML-megjegyzés', 'Elöl <!-- Newton --> hátul'],
  ];

  it.each(ESETEK)('%s', async (_nev, doc) => {
    const { nezet, kliens } = felallit(doc, 0);
    nezet.dispatch({ changes: { from: nezet.state.doc.length, insert: ' ' }, userEvent: 'input.type' });
    await vi.advanceTimersByTimeAsync(VART_ALAP_MS + 100);
    expect(kliens.emlitesek).toHaveBeenCalledTimes(1);
    expect(lathatoJavaslatok(nezet.state)).toEqual([]);
    expect(nezet.dom.querySelector('.cm-javaslat')).toBeNull();
  });

  it('a próba-érzékeny kontroll: ugyanaz a szó sima szövegben javaslat', async () => {
    const { nezet } = felallit('Lásd ```nem kód``` — ', 0);
    nezet.dispatch({ changes: { from: nezet.state.doc.length, insert: 'Newton ' }, userEvent: 'input.type' });
    await vi.advanceTimersByTimeAsync(VART_ALAP_MS + 100);
    expect(lathatoJavaslatok(nezet.state).length).toBe(1);
  });
});

describe('Tab: csak látható, aktív javaslatnál (T064)', () => {
  it('a javaslaton álló kurzornál beszúrja a linket, egy tranzakcióban (egy ⌘Z), és a döntés megy', async () => {
    const { nezet, kliens } = felallit('');
    await gepelEsVar(nezet, 'Az Newton törvénye');
    nezet.dispatch({ selection: { anchor: 3 + 3 } }); // a javaslat belsejébe
    expect(aktivJavaslatAllapot(nezet.state)).not.toBeNull();
    expect(nezet.dom.querySelector('.cm-javaslat-aktiv')).not.toBeNull();
    const e = tab(nezet);
    expect(e.defaultPrevented).toBe(true);
    await vi.advanceTimersByTimeAsync(10);
    expect(nezet.state.doc.toString()).toBe('Az [[Newton]] törvénye');
    expect(nezet.state.selection.main.head).toBe('Az [[Newton]]'.length);
    expect(kliens.dontes).toHaveBeenCalledExactlyOnceWith('elfogad');
    expect(undo(nezet)).toBe(true);
    expect(nezet.state.doc.toString()).toBe('Az Newton törvénye');
  });

  it('kisbetűs említésnél az írásmódot alias őrzi', async () => {
    const { nezet } = felallit('');
    await gepelEsVar(nezet, 'a newton');
    tab(nezet);
    await vi.advanceTimersByTimeAsync(10);
    expect(nezet.state.doc.toString()).toBe('a [[Newton|newton]]');
  });

  it('a javaslat után rövid szöveggel még aktív (a szóköz után is), messzebb már nem', async () => {
    const { nezet } = felallit('');
    await gepelEsVar(nezet, 'Newton');
    gepel(nezet, ' és ');
    expect(aktivJavaslatAllapot(nezet.state)).not.toBeNull();
    gepel(nezet, 'x'.repeat(AKTIV_TAVOLSAG));
    expect(aktivJavaslatAllapot(nezet.state)).toBeNull();
  });

  it('nincs javaslat: a Tab a megszokott behúzás, semmi nem mentődik a statisztikába', async () => {
    const { nezet, kliens } = felallit('szöveg');
    const e = tab(nezet);
    await vi.advanceTimersByTimeAsync(10);
    expect(nezet.state.doc.toString()).toContain('\t');
    expect(nezet.state.doc.toString()).not.toContain('[[');
    expect(kliens.dontes).not.toHaveBeenCalled();
    expect(e.defaultPrevented).toBe(true); // az indentWithTab kezelte, nem a javaslat
  });

  it('a javaslat látszik, de a kurzor máshol áll: a Tab a behúzásé, a javaslat marad', async () => {
    const { nezet, kliens } = felallit('');
    await gepelEsVar(nezet, 'Newton');
    gepel(nezet, ' ' + 'y'.repeat(AKTIV_TAVOLSAG + 5));
    expect(lathatoJavaslatok(nezet.state).length).toBe(1);
    tab(nezet);
    await vi.advanceTimersByTimeAsync(10);
    expect(nezet.state.doc.toString()).not.toContain('[[');
    expect(nezet.state.doc.toString()).toContain('\t');
    expect(kliens.dontes).not.toHaveBeenCalled();
  });

  it('módosítóval (⇧⇥, ⌥⇥) nem hat', async () => {
    const { nezet } = felallit('');
    await gepelEsVar(nezet, 'Newton');
    billentyu(nezet, 'Tab', { shiftKey: true });
    billentyu(nezet, 'Tab', { altKey: true });
    await vi.advanceTimersByTimeAsync(10);
    expect(nezet.state.doc.toString()).not.toContain('[[');
  });

  it('kijelölésnél és több kurzornál nem hat', async () => {
    const { nezet } = felallit('');
    await gepelEsVar(nezet, 'Newton');
    nezet.dispatch({ selection: { anchor: 0, head: 3 } });
    tab(nezet);
    await vi.advanceTimersByTimeAsync(10);
    expect(nezet.state.doc.toString()).not.toContain('[[');
  });

  it('nyitott / menü esetén a menüé a Tab (a javaslat nem lép be)', async () => {
    const { nezet, kliens } = felallit('');
    gepel(nezet, '/');
    gepel(nezet, 'kod');
    // az álmag a "kod"-ot nem ismeri; felvesszük külön magba
    kliens.emlitesek.mockImplementation(async (_u: string, sz: string) => alMag({ kod: 'Kod.md' })(sz));
    await vi.advanceTimersByTimeAsync(VART_ALAP_MS + 100);
    expect(aktivJavaslatAllapot(nezet.state)).not.toBeNull();
    tab(nezet);
    await vi.advanceTimersByTimeAsync(10);
    expect(nezet.state.doc.toString()).not.toContain('[[kod');
    expect(kliens.dontes).not.toHaveBeenCalled();
  });

  it('csak olvasható állapotban a Tab nem hat', async () => {
    const { nezet } = felallit('Newton', 6, { csakOlvashato: true });
    expect(aktivJavaslatAllapot(nezet.state)).toBeNull();
    tab(nezet);
    await vi.advanceTimersByTimeAsync(10);
    expect(nezet.state.doc.toString()).toBe('Newton');
  });

  it('közben gépelt (a feloldás alatt érvénytelenné váló) javaslatra a Tab nem ír', async () => {
    const { nezet } = felallit('');
    await gepelEsVar(nezet, 'Newton');
    // a kurzor a javaslaton, majd a feloldás alatt a szó belsejébe írnak
    nezet.dispatch({ selection: { anchor: 3 } });
    tab(nezet);
    nezet.dispatch({ changes: { from: 2, insert: 'x' } });
    await vi.advanceTimersByTimeAsync(10);
    expect(nezet.state.doc.toString()).toBe('Nexwton');
  });
});

describe('Esc: elvet', () => {
  it('az aktív javaslatot elveti, a döntés megy, és ugyanaz nem tér vissza az újabb válaszban sem', async () => {
    const { nezet, kliens } = felallit('');
    await gepelEsVar(nezet, 'Newton');
    const e = esc(nezet);
    expect(e.defaultPrevented).toBe(true);
    expect(nezet.dom.querySelector('.cm-javaslat')).toBeNull();
    expect(kliens.dontes).toHaveBeenCalledExactlyOnceWith('elutasit');
    gepel(nezet, ' és újra Newton');
    await vi.advanceTimersByTimeAsync(VART_ALAP_MS + 100);
    expect(lathatoJavaslatok(nezet.state)).toEqual([]);
  });

  it('javaslat nélkül az Esc nem foglalt (a többi kezelőé)', async () => {
    const { nezet, kliens } = felallit('szöveg');
    const e = esc(nezet);
    expect(e.defaultPrevented).toBe(false);
    expect(kliens.dontes).not.toHaveBeenCalled();
  });

  it('kikapcsolt Asszisztensnél az Esc nem hat', async () => {
    const { nezet, allapot, kliens } = felallit('');
    await gepelEsVar(nezet, 'Newton');
    allapot.be = false;
    const e = esc(nezet);
    expect(e.defaultPrevented).toBe(false);
    expect(kliens.dontes).not.toHaveBeenCalled();
  });
});

describe('a statisztikába csak a fajta és a döntés megy (51(d))', () => {
  it('a kliens POST-ja pontosan {fajta, dontes}: útvonal és szöveg nélkül', async () => {
    vi.useRealTimers();
    const kerelmek: { url: string; body: unknown }[] = [];
    vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
      kerelmek.push({ url, body: init?.body ? JSON.parse(String(init.body)) : undefined });
      return new Response(JSON.stringify({ fogadva: true }), { status: 200 });
    });
    await alapKliens.dontes('elfogad');
    await alapKliens.dontes('elutasit');
    expect(kerelmek.map((k) => k.url)).toEqual(['/api/asszisztens/dontes', '/api/asszisztens/dontes']);
    expect(kerelmek.map((k) => k.body)).toEqual([
      { fajta: 'emlites', dontes: 'elfogad' },
      { fajta: 'emlites', dontes: 'elutasit' },
    ]);
  });

  it('a küszöb a statisztika emlites-sorából jön; az említés-kérés az útvonalat és a szöveget küldi (core API, nem statisztika)', async () => {
    vi.useRealTimers();
    const hivasok: string[] = [];
    vi.stubGlobal('fetch', async (url: string) => {
      hivasok.push(url);
      return new Response(
        JSON.stringify({ fajtak: { emlites: { kuszob: { szint: 'szigoru', szorzo: 1.5 } } } }),
        { status: 200 },
      );
    });
    expect(await alapKliens.kuszob()).toEqual({ szint: 'szigoru', szorzo: 1.5 });
    expect(hivasok).toEqual(['/api/asszisztens/statisztika']);
  });
});

describe('hasonlósági szűrő (C30b, K205 (b))', () => {
  const NEVEK = { Newton: 'Fizika/Newton.md', Kepler: 'Fizika/Kepler.md', Egyiptom: 'Tortenelem/Egyiptom.md' };
  const MAG = 0.55;
  const kuszobMagas: JavaslatKuszob = { szint: 'alap', szorzo: 1, hasonlosag: MAG };

  it('a küszöb alatti cél nem javaslat, a küszöbön és fölötte az; az ismeretlen pontú (null) marad', async () => {
    const { nezet, kliens } = felallit('', 0, {
      nevek: NEVEK,
      kuszob: kuszobMagas,
      hasonlosag: pontok({ 'Fizika/Newton.md': 0.8, 'Fizika/Kepler.md': MAG, 'Tortenelem/Egyiptom.md': 0.3 }),
    });
    await gepelEsVar(nezet, 'Newton Kepler Egyiptom');
    expect(kliens.hasonlosag).toHaveBeenCalledTimes(1);
    expect(lathatoJavaslatok(nezet.state).map((j) => j.szoveg)).toEqual(['Newton', 'Kepler']);
    // a nulla pont (a cél nincs az indexben / nincs vektora) nem ítélet: a lexikai javaslat marad
    const m = felallit('', 0, { nevek: NEVEK, kuszob: kuszobMagas, hasonlosag: pontok({}) });
    await gepelEsVar(m.nezet, 'Newton Kepler');
    expect(lathatoJavaslatok(m.nezet.state).length).toBe(2);
  });

  it('a kérés pontosan {ut, célok}: egyedi célok, a szöveg nem megy', async () => {
    const { nezet, kliens } = felallit('', 0, { nevek: NEVEK, kuszob: kuszobMagas, hasonlosag: pontok({}) });
    await gepelEsVar(nezet, 'Newton Newton Kepler');
    const [ut, celok] = kliens.hasonlosag.mock.calls[0];
    expect(ut).toBe('Jegyzet.md');
    expect(celok).toEqual(['Fizika/Newton.md', 'Fizika/Kepler.md']);
    expect(kliens.hasonlosag.mock.calls[0].length).toBe(3); // ut, célok, megszakító jel — szöveg nincs
  });

  it('a többértelmű célra nem kérdez (nincs rá javaslat)', async () => {
    const { nezet, kliens } = felallit('', 0, { nevek: NEVEK, tobbertelmu: ['Newton'], kuszob: kuszobMagas, hasonlosag: pontok({}) });
    await gepelEsVar(nezet, 'Newton Kepler');
    expect(kliens.hasonlosag.mock.calls[0][1]).toEqual(['Fizika/Kepler.md']);
  });

  it('a szigorúbb küszöb (a core a szorzóval emeli) a közepes hasonlóságot is kiszűri', async () => {
    const { nezet } = felallit('', 0, {
      nevek: NEVEK,
      kuszob: { szint: 'szigoru', szorzo: 1.5, hasonlosag: 0.825 },
      hasonlosag: pontok({ 'Fizika/Newton.md': 0.7, 'Fizika/Kepler.md': 0.9 }),
    });
    gepel(nezet, 'Newton és Kepler ');
    await vi.advanceTimersByTimeAsync(VART_ALAP_MS + 100);
    await vi.advanceTimersByTimeAsync(10);
    // szigorúnál egyszerre egy javaslat látszik (a kurzorhoz legközelebbi a szűrés UTÁN): csak a Kepler marad egyáltalán
    expect(lathatoJavaslatok(nezet.state).map((j) => j.szoveg)).toEqual(['Kepler']);
  });

  it('küszöb nélkül (a core nem adott hasonlósági küszöböt) nincs kérés és nincs szűrés', async () => {
    const { nezet, kliens } = felallit('', 0, { nevek: NEVEK, hasonlosag: pontok({ 'Fizika/Newton.md': 0.01 }) });
    await gepelEsVar(nezet, 'Newton');
    expect(kliens.hasonlosag).not.toHaveBeenCalled();
    expect(lathatoJavaslatok(nezet.state).length).toBe(1);
  });

  it('a kliensnek nincs hasonlóság-képessége: a lexikai javaslat változatlan', async () => {
    const { nezet } = felallit('', 0, { nevek: NEVEK, kuszob: kuszobMagas });
    await gepelEsVar(nezet, 'Newton Kepler');
    expect(lathatoJavaslatok(nezet.state).length).toBe(2);
  });

  it('nincs vektor: a lexikai javaslat marad, és a core-t egy percig nem kérdezi újra', async () => {
    const { nezet, kliens } = felallit('', 0, { nevek: NEVEK, kuszob: kuszobMagas, hasonlosag: pontok({}, 'nincs_vektor') });
    await gepelEsVar(nezet, 'Newton');
    expect(lathatoJavaslatok(nezet.state).length).toBe(1);
    expect(kliens.hasonlosag).toHaveBeenCalledTimes(1);
    gepel(nezet, ' Kepler');
    await vi.advanceTimersByTimeAsync(VART_ALAP_MS + 100);
    expect(kliens.hasonlosag).toHaveBeenCalledTimes(1); // a „nincs vektor” válasz után szünet
    expect(lathatoJavaslatok(nezet.state).length).toBe(2);
    await vi.advanceTimersByTimeAsync(61_000);
    gepel(nezet, ' ');
    await vi.advanceTimersByTimeAsync(VART_ALAP_MS + 100);
    expect(kliens.hasonlosag).toHaveBeenCalledTimes(2);
  });

  it('a hasonlóság hibája (a core nem elérhető) nem dob, és a lexikai javaslat marad', async () => {
    const { nezet, kliens } = felallit('', 0, { nevek: NEVEK, kuszob: kuszobMagas, hasonlosag: pontok({}) });
    kliens.hasonlosag.mockRejectedValue(new Error('404'));
    await gepelEsVar(nezet, 'Newton');
    expect(lathatoJavaslatok(nezet.state).length).toBe(1);
  });

  it('a pontok egy percig gyorsítótárban vannak: csak a hiányzó cél kérdeződik', async () => {
    const { nezet, kliens } = felallit('', 0, {
      nevek: NEVEK,
      kuszob: kuszobMagas,
      hasonlosag: pontok({ 'Fizika/Newton.md': 0.9, 'Fizika/Kepler.md': 0.2 }),
    });
    await gepelEsVar(nezet, 'Newton ');
    gepel(nezet, 'és Kepler ');
    await vi.advanceTimersByTimeAsync(VART_ALAP_MS + 100);
    expect(kliens.hasonlosag).toHaveBeenCalledTimes(2);
    expect(kliens.hasonlosag.mock.calls[1][1]).toEqual(['Fizika/Kepler.md']);
    gepel(nezet, 'és Kepler ');
    await vi.advanceTimersByTimeAsync(VART_ALAP_MS + 100);
    expect(kliens.hasonlosag).toHaveBeenCalledTimes(2); // a Kepler pontja már megvan: nincs új kérés
    expect(lathatoJavaslatok(nezet.state).map((j) => j.szoveg)).toEqual(['Newton']);
  });

  it('az elavult válasz a hasonlóság kérése alatt is eldobódik (közben gépelt)', async () => {
    let kioldo: () => void = () => undefined;
    const { nezet, kliens } = felallit('', 0, { nevek: NEVEK, kuszob: kuszobMagas, hasonlosag: pontok({}) });
    kliens.hasonlosag.mockImplementation(
      () => new Promise((ok) => (kioldo = () => ok({ ut: 'Jegyzet.md', allapot: 'ok', elavult: false, pontok: {} }))),
    );
    await gepelEsVar(nezet, 'Newton');
    gepel(nezet, ' ma'); // a pontok megérkezése előtt változik a dokumentum
    kioldo();
    await vi.advanceTimersByTimeAsync(10);
    expect(lathatoJavaslatok(nezet.state)).toEqual([]);
  });

  it('a szűrt (nem látható) javaslatnál a Tab a megszokott behúzás, nem fogad el (T064)', async () => {
    const { nezet, kliens } = felallit('', 0, {
      nevek: NEVEK,
      kuszob: kuszobMagas,
      hasonlosag: pontok({ 'Tortenelem/Egyiptom.md': 0.2 }),
    });
    await gepelEsVar(nezet, 'Egyiptom');
    expect(nezet.dom.querySelector('.cm-javaslat')).toBeNull();
    expect(aktivJavaslatAllapot(nezet.state)).toBeNull();
    tab(nezet);
    await vi.advanceTimersByTimeAsync(10);
    expect(nezet.state.doc.toString()).not.toContain('[[');
    expect(nezet.state.doc.toString()).toContain('\t');
    expect(kliens.dontes).not.toHaveBeenCalled();
  });

  it('a szabály és a szűrő tiszta függvényei', () => {
    expect(kuszobSzabaly({ szint: 'alap', szorzo: 1, hasonlosag: 0.55 }).hasonlosag).toBe(0.55);
    expect(kuszobSzabaly({ szint: 'alap', szorzo: 1, hasonlosag: null }).hasonlosag).toBeUndefined();
    expect(kuszobSzabaly({ szint: 'alap', szorzo: 1 })).not.toHaveProperty('hasonlosag');
    const szuro = hasonlosagSzuro(
      new Map([
        ['a', 0.7],
        ['b', 0.4],
        ['c', null],
      ]),
      0.55,
    );
    expect([szuro?.('a'), szuro?.('b'), szuro?.('c'), szuro?.('d')]).toEqual([true, false, true, true]);
    expect(hasonlosagSzuro(null, 0.55)).toBeUndefined();
    expect(hasonlosagSzuro(new Map(), undefined)).toBeUndefined();
  });

  it('az alapkliens a statisztika emlites-sorának hasonlosag_kuszob-ját adja a küszöbbel, és a /api/kereses/hasonlosag-ot hívja', async () => {
    vi.useRealTimers();
    const kerelmek: { url: string; body: unknown }[] = [];
    vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
      kerelmek.push({ url, body: init?.body ? JSON.parse(String(init.body)) : undefined });
      return new Response(
        JSON.stringify(
          url.includes('statisztika')
            ? { fajtak: { emlites: { kuszob: { szint: 'szigoru', szorzo: 1.5 }, hasonlosag_kuszob: 0.825 } } }
            : { ut: 'J.md', allapot: 'ok', elavult: false, pontok: { 'A.md': 0.7 } },
        ),
        { status: 200 },
      );
    });
    expect(await alapKliens.kuszob()).toEqual({ szint: 'szigoru', szorzo: 1.5, hasonlosag: 0.825 });
    const v = await alapKliens.hasonlosag?.('J.md', ['A.md'], new AbortController().signal);
    expect(v?.pontok).toEqual({ 'A.md': 0.7 });
    expect(kerelmek[1]).toEqual({ url: '/api/kereses/hasonlosag', body: { ut: 'J.md', celok: ['A.md'] } });
  });
});
