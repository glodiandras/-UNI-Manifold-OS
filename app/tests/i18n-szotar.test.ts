// A szótárak épsége és lefedettsége (F4): `src/lib/i18n/en/*.json`. KEMÉNY: a fájlok alakja, az azonos kulcs azonos értéke, a
// `{param}`-egyezés a magyar kulcs és az angol érték közt, a többes számú párok. FIGYELMEZTETÉS (az integrátor kapcsolja kötelezővé a
// `i18n-ratchet.json` `forditasKotelezo: true` értékével, ha a lefedettség 100 %): minden `t()`/`tp()`/`tk()` kulcsnak van angol
// fordítása, és a szótárban nincs a forrásban nem használt (elavult) kulcs.
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { alapSzoveg, szotarFajlok } from '../src/lib/i18n';
import { elemez, forrasFajlok, rovidUt } from './i18n-keresok';

const KATEGORIA = /\|(zero|one|two|few|many|other)$/;
const PARAM = /\{([A-Za-z_][A-Za-z0-9_]*)\}/g;
/** Core-hibakód kulcsa (`hiba.vault.nem_elerheto`): nincs magyar kulcsa, a forrás dinamikusan (`hiba.${kod}`) hivatkozik rá. */
const HIBAKOD = /^hiba\.[a-z0-9_.]+$/;

const KOTELEZO = (JSON.parse(readFileSync(`${(import.meta as unknown as { dirname: string }).dirname}/i18n-ratchet.json`, 'utf8')) as { forditasKotelezo: boolean }).forditasKotelezo;

const FAJLOK = Object.entries(szotarFajlok()).filter(([ut]) => ut.startsWith('./en/'));
const EN = new Map<string, string>(FAJLOK.flatMap(([, sz]) => Object.entries(sz)));
// A core a feladatneveket, lépésleírásokat és figyelmeztetéseket is küldi. Ezek dinamikusan jelennek meg a UI-ban, ezért a
// szövegkulcsainál a Python-forrás is használatnak számít. Csak tényleges előfordulást fogadunk el; a szomszédos
// Python-literálokat ("hosszú " "mondat") összefűzzük, hogy egy hosszú, több sorba tördelt üzenet se látszódjon elavultnak.
const PYTHON_FORRAS = Object.values(import.meta.glob(['../../core/**/*.py', '../../modulok/**/*.py'], { query: '?raw', import: 'default', eager: true }) as Record<string, string>)
  .map((sz) => sz.replace(/["']\s*["']/g, ''));

const parameterek = (s: string) => new Set([...s.matchAll(PARAM)].map((m) => m[1]));

describe('a szótárfájlok alakja', () => {
  it('a fájlok a várt partíciók, lapos szöveg→szöveg objektumok, üres érték nélkül, azonos kezdő/záró szóközzel', () => {
    // egy partíció több fájlt is használhat (párhuzamos munkához): `<partíció>.json` vagy `<partíció>-<utótag>.json` (pl. `core-b.json`)
    const nevek = FAJLOK.map(([ut]) => ut.replace('./en/', '').replace('.json', '')).sort();
    const PARTICIOK = ['beallitasok', 'core', 'hej', 'lib', 'modulok', 'nezetek', 'oldalak', 'parancsok', 'pdfjs', 'setup', 'szerkeszto'];
    expect(nevek.filter((n) => !new RegExp(`^(${PARTICIOK.join('|')})(-[a-z0-9]+)?$`).test(n))).toEqual([]);
    expect([...new Set(nevek.map((n) => n.split('-')[0]))].sort()).toEqual(PARTICIOK);
    const rossz: string[] = [];
    for (const [ut, sz] of FAJLOK) {
      if (!sz || typeof sz !== 'object' || Array.isArray(sz)) rossz.push(`${ut}: nem objektum`);
      for (const [k, v] of Object.entries(sz ?? {})) {
        if (typeof v !== 'string' || v.trim() === '') rossz.push(`${ut}: "${k}" értéke nem nemüres szöveg`);
        if (k.trim() === '') rossz.push(`${ut}: üres kulcs`);
        // a szövegrészletek (`'{i}/{n}. lépés · '`) szóközzel kezdődhetnek/végződhetnek, de az érték szóköze ugyanaz kell legyen (összefűzésnél számít)
        else if (typeof v === 'string' && (k.length - k.trimStart().length !== v.length - v.trimStart().length || k.length - k.trimEnd().length !== v.length - v.trimEnd().length))
          rossz.push(`${ut}: "${k}" → "${v}": a kezdő/záró szóköz eltér a kulcs és az érték közt`);
      }
    }
    expect(rossz).toEqual([]);
  });

  it('azonos kulcs több fájlban csak azonos értékkel állhat', () => {
    const latott = new Map<string, { ut: string; ertek: string }>();
    const utkozes: string[] = [];
    for (const [ut, sz] of FAJLOK)
      for (const [k, v] of Object.entries(sz)) {
        const elozo = latott.get(k);
        if (elozo && elozo.ertek !== v) utkozes.push(`"${k}": ${elozo.ut} = "${elozo.ertek}", ${ut} = "${v}"`);
        latott.set(k, { ut, ertek: v });
      }
    expect(utkozes, 'azonos magyar kulcs két fordítással: igazítsd az értékeket, vagy különítsd el környezettel (`Kulcs|ctx`)').toEqual([]);
  });

  it('a {param}-ok egyeznek a magyar kulcs és az angol érték közt (a core-hibakódoknál és a `|zero` alaknál az érték részhalmaz is lehet)', () => {
    const rossz: string[] = [];
    for (const [k, v] of EN) {
      const kerete = parameterek(v);
      if (HIBAKOD.test(k)) continue;
      const alap = parameterek(alapSzoveg(k.replace(KATEGORIA, '')));
      if (k.endsWith('|zero')) {
        if (![...kerete].every((p) => alap.has(p))) rossz.push(`"${k}": az értékben ismeretlen paraméter`);
      } else if (alap.size !== kerete.size || ![...alap].every((p) => kerete.has(p))) rossz.push(`"${k}" → "${v}": a {param}-ok eltérnek (${[...alap]} / ${[...kerete]})`);
    }
    expect(rossz).toEqual([]);
  });

  it('a többes számú bejegyzések párban állnak: `|one` mellett `|other` is van', () => {
    const rossz: string[] = [];
    for (const k of EN.keys()) {
      const m = k.match(KATEGORIA);
      if (!m) continue;
      const alap = k.replace(KATEGORIA, '');
      if (m[1] === 'one' && !EN.has(`${alap}|other`)) rossz.push(`"${alap}": van |one, de nincs |other`);
      if (m[1] === 'other' && !EN.has(`${alap}|one`)) rossz.push(`"${alap}": van |other, de nincs |one`);
    }
    expect(rossz).toEqual([]);
  });
});

describe('a forrás t()/tp()/tk() kulcsai és a szótár', () => {
  const FORRAS = Object.entries(forrasFajlok()).filter(([ut]) => !ut.endsWith('.d.ts') && !ut.includes('/lib/i18n/'));
  const kulcsok = FORRAS.flatMap(([ut, szoveg]) => elemez(ut, szoveg).kulcsok.map((k) => ({ ...k, fajl: rovidUt(ut) })));
  const egyedi = [...new Map(kulcsok.map((k) => [`${k.fajta === 'tp' ? 'tp' : 't'}:${k.kulcs}`, k])).values()];

  const lefedett = (k: { fajta: string; kulcs: string }) =>
    k.fajta === 'tp' ? EN.has(k.kulcs) || (EN.has(`${k.kulcs}|one`) && EN.has(`${k.kulcs}|other`)) : EN.has(k.kulcs);

  it('lefedettség: minden kulcsnak van angol fordítása (figyelmeztetés, amíg a forditasKotelezo hamis)', () => {
    const hianyzo = egyedi.filter((k) => !lefedett(k));
    const szazalek = egyedi.length ? (100 * (egyedi.length - hianyzo.length)) / egyedi.length : 100;
    const jelentes = `i18n lefedettség: ${egyedi.length - hianyzo.length}/${egyedi.length} kulcs fordítva (${szazalek.toFixed(1)} %)`;
    if (hianyzo.length) console.warn(`${jelentes}; hiányzik pl.: ${hianyzo.slice(0, 8).map((k) => `${k.fajl}:${k.sor} "${k.kulcs}"`).join('; ')}`);
    else console.info(jelentes);
    if (KOTELEZO) expect(hianyzo.map((k) => `${k.fajl}:${k.sor} "${k.kulcs}"`)).toEqual([]);
    else expect(egyedi.length).toBeGreaterThanOrEqual(0);
  });

  it('elavult kulcs: a szótár minden kulcsát használja a forrás (figyelmeztetés, amíg a forditasKotelezo hamis)', () => {
    const hasznalt = new Set(kulcsok.filter((k) => k.fajta !== 'tp').map((k) => k.kulcs));
    const tpKulcsok = new Set(kulcsok.filter((k) => k.fajta === 'tp').map((k) => k.kulcs));
    const elavult = [...EN.keys()].filter((k) => {
      if (HIBAKOD.test(k)) return false;
      if (PYTHON_FORRAS.some((sz) => sz.includes(k))) return false;
      const m = k.match(KATEGORIA);
      return m ? !tpKulcsok.has(k.replace(KATEGORIA, '')) && !hasznalt.has(k) : !hasznalt.has(k) && !tpKulcsok.has(k);
    });
    if (elavult.length) console.warn(`i18n szótár: ${elavult.length} nem használt kulcs, pl.: ${elavult.slice(0, 8).map((k) => `"${k}"`).join('; ')}`);
    if (KOTELEZO) expect(elavult).toEqual([]);
    else expect(elavult.length).toBeGreaterThanOrEqual(0);
  });
});
