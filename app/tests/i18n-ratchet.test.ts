// Az i18n-ratchet (F4, PLAN P2): a felület szövegei a `t()` / `tp()` / `tk()` hívásokon át érkeznek a szótárba, nem nyers magyar
// literálként. A mai állomány (`i18n-ratchet.json`, fájlonként a nyers magyar szöveg-egységek száma) fedezett, de CSAK CSÖKKENHET:
// új ékezetes literál `t()` nélkül vagy egy fájl számának növekedése bukik. A számlálás szabályai: `i18n-keresok.ts` (fejléc).
//
//   - Új felületi szöveg: `t('Mentés')`, `t('{n} elem', { n })`, `tp('{n} jegyzet', n)`; táblázatban `tk('…')`.
//   - Valódi adat (vault-tulajdonságnév, mappanév), nem felületi szöveg: a sorra vagy az előző sorra `// i18n-ignore: <indok>`
//     (Svelte-sablonban `<!-- i18n-ignore: <indok> -->`); az indok kötelező.
//   - A számok csökkentése (egy fájl fordítása után): `MOS_I18N_FRISSIT=1 npx vitest run tests/i18n-ratchet.test.ts` újraírja a JSON-t
//     a mai számokkal; ha bármelyik fájl száma nőtt, a frissítés megtagadja. Alapállapot-felvétel: üres `fajlok`-nál.
import { readFileSync, writeFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { elemez, forrasFajlok, rovidUt, type Talalat } from './i18n-keresok';

const JSON_UT = `${(import.meta as unknown as { dirname: string }).dirname}/i18n-ratchet.json`; // a jsdom URL-je a `new URL(…, import.meta.url)`-t félreérti

interface RatchetJson {
  _leiras: string;
  /** Igaz: minden `t()` kulcsnak kell angol fordítás, és a szótár nem tartalmazhat elavult kulcsot (az integrátor kapcsolja be). */
  forditasKotelezo: boolean;
  fajlok: Record<string, number>;
}

const olvasJson = (): RatchetJson => JSON.parse(readFileSync(JSON_UT, 'utf8')) as RatchetJson;

const FORRASOK = Object.entries(forrasFajlok()).filter(([ut]) => !ut.endsWith('.d.ts'));
const ELEMZESEK = new Map(FORRASOK.map(([ut, szoveg]) => [rovidUt(ut), elemez(ut, szoveg)]));

const leiras = (t: Talalat) => `  sor ${t.sor}: ${t.szoveg}`;

describe('a nyers magyar felületi szöveg száma csak csökkenhet', () => {
  it('frissítés-mód: MOS_I18N_FRISSIT=1 újraírja a számokat (növekedést nem fogad el)', () => {
    if (process.env.MOS_I18N_FRISSIT !== '1') return;
    const regi = olvasJson();
    const uj: Record<string, number> = {};
    for (const [ut, e] of ELEMZESEK) if (e.magyar.length) uj[ut] = e.magyar.length;
    const alap = Object.keys(regi.fajlok).length === 0;
    const nott = Object.entries(uj).filter(([ut, n]) => n > (regi.fajlok[ut] ?? 0));
    if (!alap && nott.length) throw new Error(`a ratchet nem növelhető: ${nott.map(([ut, n]) => `${ut} (${regi.fajlok[ut] ?? 0} → ${n})`).join(', ')}`);
    const rendezett = Object.fromEntries(Object.entries(uj).sort(([a], [b]) => a.localeCompare(b)));
    writeFileSync(JSON_UT, `${JSON.stringify({ ...regi, fajlok: rendezett }, null, 2)}\n`);
  });

  it('egyetlen fájlban sem több nyers magyar szöveg, mint az engedélyezett (t()/tp()/tk() kell, vagy i18n-ignore indokkal)', () => {
    const engedett = olvasJson().fajlok;
    const sertesek: string[] = [];
    for (const [ut, e] of ELEMZESEK) {
      const n = e.magyar.length;
      const lehet = engedett[ut] ?? 0;
      if (n > lehet) sertesek.push(`${ut}: ${n} nyers magyar szöveg, engedélyezett ${lehet}\n${e.magyar.slice(0, 12).map(leiras).join('\n')}`);
    }
    expect(sertesek, 'új nyers magyar szöveg: használd a t()-t (lásd a tests/i18n-ratchet.test.ts fejlécét)').toEqual([]);
  });

  it('az engedélyezett számok csak létező fájlokra mutatnak (törölt fájl: frissítsd a JSON-t)', () => {
    const hianyzo = Object.keys(olvasJson().fajlok).filter((ut) => !ELEMZESEK.has(ut));
    expect(hianyzo).toEqual([]);
  });

  it('a csökkenthető számok jelzése (nem hiba): a javított fájlok engedélye lejjebb vihető', () => {
    const engedett = olvasJson().fajlok;
    const lejjebb = [...ELEMZESEK].filter(([ut, e]) => e.magyar.length < (engedett[ut] ?? 0)).map(([ut, e]) => `${ut}: ${engedett[ut]} → ${e.magyar.length}`);
    if (lejjebb.length) console.info(`i18n-ratchet: ${lejjebb.length} fájl engedélye csökkenthető (MOS_I18N_FRISSIT=1): ${lejjebb.slice(0, 10).join('; ')}`);
    expect(true).toBe(true);
  });
});

describe('a t() kulcsa állandó szöveg', () => {
  it('nincs dinamikus kulcs: t(`… ${x}`) helyett t(\'… {x}\', { x })', () => {
    const rossz = [...ELEMZESEK].flatMap(([ut, e]) => e.dinamikus.map((d) => `${ut}:${d.sor}`));
    expect(rossz).toEqual([]);
  });

  it('minden i18n-ignore megjegyzésnek van indoka', () => {
    const rossz: string[] = [];
    for (const [ut, szoveg] of FORRASOK)
      szoveg.split('\n').forEach((sor, i) => {
        if (/i18n-ignore(?!:\s*\S)/.test(sor) && !/`i18n-ignore/.test(sor)) rossz.push(`${rovidUt(ut)}:${i + 1}`);
      });
    expect(rossz).toEqual([]);
  });
});

describe('az elemző szabályai', () => {
  const IMPORT = `import { t } from '../lib/i18n';\n`;
  const magyar = (fajl: string, forras: string) => elemez(fajl, forras).magyar.map((m) => m.szoveg);
  const kulcsok = (fajl: string, forras: string) => elemez(fajl, forras).kulcsok.map((k) => `${k.fajta}:${k.kulcs}`);

  it('számol: szöveg-literál, sablon-literál (1 egység), throw, szövegcsomópont, statikus attribútum', () => {
    expect(magyar('a.ts', `const a = 'Mentés'; const b = \`Törölve: \${x}\`; throw new Error('Nincs találat');`)).toEqual(['Mentés', 'Törölve: {}', 'Nincs találat']);
    expect(magyar('A.svelte', `<p>Üzenet</p><img alt="Kép" /><Gomb cimke="Mégse" nev="x" /><span title="Súgó" class="fül">{'Kész'}</span>`)).toEqual(['Üzenet', 'Kép', 'Mégse', 'Súgó', 'Kész']);
  });

  it('nem számol: ékezet nélküli szöveg, megjegyzés, t()/tp()/tk() kulcsa, console, import, objektum-kulcs, összehasonlítás', () => {
    const forras = [
      `import x from './Állapot';`,
      `import { t, tp, tk } from '../lib/i18n';`,
      `// Mentés megjegyzés`,
      `const a = t('Mentés'); const b = tp('{n} jegyzet', n); const c = tk('Fájl'); const d = t('Szöveg: ' + 'hosszú');`,
      `console.error('Hiba történt');`,
      `const o = { 'Média': 1, nev: t('Név') }; const p = o['Média'];`,
      `if (x === 'Média' || 'Cím' !== y) {} switch (z) { case 'Fájl': break; }`,
      `type K = 'Média' | 'Cím'; const s = 'plain';`,
    ].join('\n');
    expect(magyar('a.ts', forras)).toEqual([]);
    expect(kulcsok('a.ts', forras)).toEqual(['t:Mentés', 'tp:{n} jegyzet', 'tk:Fájl', 't:Szöveg: hosszú', 't:Név']);
  });

  it('a t() paraméter-értéke és a dinamikus kulcs benne álló magyar szöveg számít; a dinamikus kulcs külön jelölt', () => {
    expect(magyar('a.ts', `${IMPORT}t('Fájl: {f}', { f: 'Napló' })`)).toEqual(['Napló']);
    const e = elemez('a.ts', `${IMPORT}const x = t(\`Kész: \${nev}\`);`);
    expect(e.dinamikus).toHaveLength(1);
    expect(e.magyar.map((m) => m.szoveg)).toEqual(['Kész: {}']);
  });

  it('az i18n-ignore indokkal a sorra vagy az előző sorra vonatkozik; indok nélkül nem', () => {
    expect(magyar('a.ts', `const a = 'Média'; // i18n-ignore: vault tulajdonságnév`)).toEqual([]);
    expect(magyar('a.ts', `const t = (x: string) => x; t('Fájl');`)).toEqual(['Fájl']); // helyi `t`: nem fordító hívás
    expect(magyar('a.ts', `// i18n-ignore: vault tulajdonságnév\nconst a = 'Média';`)).toEqual([]);
    expect(magyar('a.ts', `// i18n-ignore\nconst a = 'Média';`)).toEqual(['Média']);
    expect(magyar('A.svelte', `<!-- i18n-ignore: adat -->\n<p>Média</p>`)).toEqual([]);
  });

  it('a Svelte-sablonban a t() kifejezés nem számít; a TypeScript-típusok és a <style> kimaradnak', () => {
    const forras = `<script lang="ts">\n  import { t } from '../lib/i18n';\n  type T = 'Média';\n  const x = (y as 'Cím');\n</script>\n<p title={t('Súgó')}>{t('Szöveg')}</p>\n<style>.fül::after { content: 'é'; }</style>`;
    expect(magyar('A.svelte', forras)).toEqual([]);
    expect(kulcsok('A.svelte', forras)).toEqual(['t:Súgó', 't:Szöveg']);
  });

  it('a .ts fájl a <script> lezáró jelét tartalmazhatja, és a sorszámok megmaradnak', () => {
    const e = elemez('a.ts', `const a = 1;\nconst h = '</script>';\nconst b = 'Mentés';`);
    expect(e.magyar).toEqual([{ fajl: 'a.ts', sor: 3, szoveg: 'Mentés' }]);
    expect(elemez('a.ts', `import { t as fordit } from '../../lib/i18n';\nfordit('Mentés');`).kulcsok.map((k) => k.kulcs)).toEqual(['Mentés']);
  });
});
