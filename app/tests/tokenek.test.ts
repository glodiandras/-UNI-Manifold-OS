// A token-őr (C39, DESIGN.md 24.): a felület stílusai csak tokenből rajzolnak.
// Minden `var(--x)` létező tokenre mutat; szín-literál csak a tokens.css-ben áll; a puszta színtoken nem lehet egy
// árnyék, körvonal vagy keret egyetlen értéke (a C37 lelete: `box-shadow: var(--fokusz-gyuru)` érvénytelen CSS, így
// nem volt fókuszgyűrű); a betűméret, a sortáv, a súly, a lekerekítés, az átmenet ideje, az árnyék, az átlátszóság,
// a fókusz-vonal, a vezérlő-magasság és a globális réteg csak tokenből jön; a kitöltött gomb egy helyen él.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

// A `.css` `?raw` importja a vitest CSS-kezelése miatt üres szöveget adhat (a modulgráfban már betöltött stíluslap),
// ezért a stíluslapok a lemezről jönnek; a listát a glob adja, így új stíluslap magától a vizsgálatba kerül.
const CSS_FAJLOK = Object.keys(import.meta.glob('../src/**/*.css'));
const olvas = (ut: string) => new TextDecoder().decode(readFileSync(decodeURIComponent(new URL(ut, import.meta.url).pathname)));
const CSS: Record<string, string> = Object.fromEntries(CSS_FAJLOK.map((ut) => [ut, olvas(ut)]));
const tokensCss = CSS['../src/styles/tokens.css'];

const FORRASOK: Record<string, string> = {
  ...(import.meta.glob(['../src/**/*.svelte', '../src/**/*.ts'], { query: '?raw', import: 'default', eager: true }) as Record<string, string>),
  ...CSS,
};

/** A szabályok alól kivett fájlok, indokkal (explicit lista: új kivétel csak ide, indokkal). A vendorált könyvtárak
 *  (pdf.js, JSXGraph, KaTeX, CodeMirror) stíluslapjai nem az `app/src` alatt állnak, ezért nem kerülnek a vizsgálatba. */
const KIVETELEK: Record<string, string> = {
  '../src/styles/tokens.css': 'a tokenek forrása: itt állnak a nyers értékek',
  '../src/lib/design/kontraszt.ts': 'a tokens.css elemzője: a reguláris kifejezése `var(--` szöveget tartalmaz',
};

/** Egyes deklarációk kivétele (`<fájl> <tulajdonság>: <érték>` → indok); a lista minden eleme létező deklarációra
 *  mutat (teszt őrzi), így az elavult kivétel nem marad itt. */
const ERTEK_KIVETELEK: Record<string, string> = {
  'canvas/canvas.css font-size: 28px':
    'a beágyazott canvas kicsinyített SVG-képének felirata vászon-egységben (a kép a beágyazás méretére skálázódik), nem képernyő-pixel',
};
const HASZNALT_KIVETEL = new Set<string>();

/** A kitöltött gomb egyetlen helye (a design system `m-gomb`-ja). */
const KITOLTOTT_GOMB_HELYE = '../src/styles/minta.css';

const rov = (ut: string) => ut.replace('../src/', '');

/** A fájl stílus-szövege: a `.css` egésze, a `.svelte` `<style>` blokkjai; a megjegyzések nélkül. */
function stilus(ut: string, s: string): string {
  let css = '';
  if (ut.endsWith('.css')) css = s;
  else if (ut.endsWith('.svelte')) css = [...s.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/g)].map((m) => m[1]).join('\n');
  // a megjegyzés helyén a sortörések maradnak, hogy a sorszám pontos legyen
  return css.replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, ' '));
}

/** Deklarációk: [sorszám, tulajdonság, érték]. */
function deklaraciok(css: string): [number, string, string][] {
  const ki: [number, string, string][] = [];
  const re = /(^|[{;\s])([a-z-]+)\s*:\s*([^;{}]+);/g;
  for (const m of css.matchAll(re)) {
    const sor = css.slice(0, m.index! + m[1].length).split('\n').length;
    ki.push([sor, m[2], m[3].trim()]);
  }
  return ki;
}

/** A tokens.css tokenjei: név → érték. */
const TOKENEK = new Map<string, string>([...tokensCss.matchAll(/--([a-z0-9-]+)\s*:\s*([^;]+);/g)].map((m) => [m[1], m[2].trim()]));

const SZIN_TOKENEK = new Set<string>();
for (const [nev, ertek] of TOKENEK) if (/^(light-dark|rgba?)\(/.test(ertek) && !/\dpx/.test(ertek)) SZIN_TOKENEK.add(nev);
for (let i = 0; i < 3; i++)
  for (const [nev, ertek] of TOKENEK) {
    const a = /^var\(--([a-z0-9-]+)\)$/.exec(ertek);
    if (a && SZIN_TOKENEK.has(a[1])) SZIN_TOKENEK.add(nev);
  }

/** Minden helyi egyedi tulajdonság (`--x:`, `style:--x`, `setProperty('--x'`) a forrásokban. */
const HELYI = new Set<string>();
for (const s of Object.values(FORRASOK)) {
  for (const m of s.matchAll(/(?:^|[\s{;"'`(])--([a-z0-9-]+)\s*:/g)) HELYI.add(m[1]);
  for (const m of s.matchAll(/style:--([a-z0-9-]+)/g)) HELYI.add(m[1]);
  for (const m of s.matchAll(/(?:setProperty|\.set)\(\s*['"`]--([a-z0-9-]+)/g)) HELYI.add(m[1]);
}

function sertesek(vizsgal: (ut: string, sor: number, tul: string, ertek: string) => string | null): string[] {
  const ki: string[] = [];
  for (const [ut, s] of Object.entries(FORRASOK)) {
    if (ut in KIVETELEK || ut.endsWith('.ts')) continue;
    for (const [sor, tul, ertek] of deklaraciok(stilus(ut, s))) {
      const kulcs = `${rov(ut)} ${tul}: ${ertek.replace(/\s+/g, ' ')}`;
      if (kulcs in ERTEK_KIVETELEK) {
        HASZNALT_KIVETEL.add(kulcs);
        continue;
      }
      const h = vizsgal(ut, sor, tul, ertek);
      if (h) ki.push(`${rov(ut)}:${sor} ${tul}: ${ertek} — ${h}`);
    }
  }
  return ki;
}

/** Az érték a `var(…)` hivatkozások nélkül (a tartalmuk token, nem nyers érték). */
const varNelkul = (e: string) => e.replace(/var\(--[a-z0-9-]+(?:\s*,[^()]*(?:\([^()]*\))?[^()]*)?\)/g, 'TOKEN');

/** A sértések teljes listája a hibaüzenetben (a vitest diffje hosszú tömböt csonkol). */
function ures(ki: string[]): void {
  if (ki.length) throw new Error(`${ki.length} sértés:\n` + ki.join('\n'));
}

const PX = /(?<![\w.-])(?:\d*\.)?\d+px\b/;
const NEM_NULLA_PX = /(?<![\w.-])(?:0*[1-9]\d*(?:\.\d+)?|0?\.\d*[1-9]\d*)px\b/;

describe('token-őr (C39)', () => {
  it('minden stíluslap vizsgálva van, és a kivételek létező fájlokra mutatnak', () => {
    expect(CSS_FAJLOK.length).toBeGreaterThan(5);
    for (const s of Object.values(CSS)) expect(s.length).toBeGreaterThan(0);
    for (const ut of Object.keys(KIVETELEK)) expect(FORRASOK[ut], ut).toBeDefined();
  });

  it('minden var(--x) létező tokenre vagy helyi egyedi tulajdonságra mutat', () => {
    const ki: string[] = [];
    for (const [ut, s] of Object.entries(FORRASOK)) {
      if (ut in KIVETELEK) continue;
      // a `--nev-` végű hivatkozás futásidőben összerakott név (pl. `var(--callout-${szin})`): a teljes nevet a
      // kontraszt-teszt és a modul saját tesztje őrzi
      for (const m of s.matchAll(/var\(--([a-z0-9-]*[a-z0-9])(?![a-z0-9-]|\$)/g)) {
        if (!TOKENEK.has(m[1]) && !HELYI.has(m[1])) ki.push(`${rov(ut)}: --${m[1]}`);
      }
    }
    ures([...new Set(ki)]);
  });

  it('szín-literál csak a tokens.css-ben áll', () => {
    const ki = sertesek((_u, _s, tul, ertek) => {
      if (tul.startsWith('--')) return null;
      if (/#[0-9a-fA-F]{3,8}\b/.test(ertek) || /\b(rgba?|hsla?|oklch|oklab|lab|lch)\(/.test(ertek)) return 'nyers szín';
      if (/(^|\s)(white|black|red|blue|green|gray|grey|yellow|orange|purple|pink)(\s|$)/.test(ertek)) return 'nevesített szín';
      return null;
    });
    ures(ki);
  });

  it('a puszta színtoken nem lehet árnyék, körvonal vagy keret egyetlen értéke', () => {
    const ki = sertesek((_u, _s, tul, ertek) => {
      if (!/^(box-shadow|text-shadow|outline|border|border-(top|right|bottom|left)|border-block|border-inline)$/.test(tul)) return null;
      const m = /^var\(--([a-z0-9-]+)\)$/.exec(ertek);
      return m && SZIN_TOKENEK.has(m[1]) ? 'érvénytelen: a szín egymagában nem árnyék/vonal' : null;
    });
    ures(ki);
  });

  it('a betűméret, a sortáv, a súly és a lekerekítés tokenből jön', () => {
    const ki = sertesek((_u, _s, tul, ertek) => {
      const e = varNelkul(ertek);
      if ((tul === 'font-size' || tul === 'line-height') && PX.test(e)) return 'nyers px';
      if (tul === 'font-weight' && /\d/.test(e)) return 'nyers súly';
      if (/^border(-[a-z]+)*-radius$/.test(tul) && /\d+(px|%|em|rem)/.test(e)) return 'nyers lekerekítés';
      return null;
    });
    ures(ki);
  });

  it('az átmenet ideje, az árnyék, az átlátszóság és a fókusz-vonal tokenből jön', () => {
    const ki = sertesek((_u, _s, tul, ertek) => {
      const e = varNelkul(ertek);
      if (/^(transition|transition-duration|transition-delay|animation|animation-duration)$/.test(tul) && /(?<![\w.-])(?:0*[1-9]\d*(?:\.\d+)?|0?\.\d*[1-9]\d*)m?s\b/.test(e))
        return 'nyers idő'; // a 0 s (azonnali `visibility`-váltás) nem érték, hanem a mozgás hiánya
      if (tul === 'box-shadow' && NEM_NULLA_PX.test(e)) return 'nyers árnyék';
      if (tul === 'opacity' && !/^(0|1|TOKEN)$/.test(e.trim())) return 'nyers átlátszóság';
      if ((tul === 'outline' || tul === 'outline-offset' || tul === 'outline-width') && NEM_NULLA_PX.test(e)) return 'nyers fókusz-vonal';
      return null;
    });
    ures(ki);
  });

  it('a vezérlő-magasság tokenből jön (a 22 px a 4-es rácson kívül esik)', () => {
    const ki = sertesek((_u, _s, tul, ertek) => {
      if (!/^(min-|max-)?(height|width|block-size|inline-size)$/.test(tul)) return null;
      return /^(20|22|24|28|32|36|44)px$/.test(ertek.trim()) ? 'nyers vezérlő-méret' : null;
    });
    ures(ki);
  });

  it('a 10-es vagy nagyobb z-index csak rétegtokenből jön (a komponensen belüli 1–9 helyi halmozás)', () => {
    const ki = sertesek((_u, _s, tul, ertek) => (tul === 'z-index' && /^\d+$/.test(ertek) && Number(ertek) >= 10 ? 'nyers réteg' : null));
    ures(ki);
  });

  it('a kitöltött gomb egy helyen él (minta.css, a design system m-gomb-ja)', () => {
    const ki = sertesek((ut, _s, tul, ertek) =>
      ut !== KITOLTOTT_GOMB_HELYE && /^background(-color)?$/.test(tul) && /var\(--akcent-(kitoltes|hover)\)/.test(ertek) ? 'saját kitöltött gomb' : null,
    );
    ures(ki);
  });

  it('minden érték-kivétel létező deklarációra mutat (az előző tesztek után)', () => {
    expect(Object.keys(ERTEK_KIVETELEK).filter((k) => !HASZNALT_KIVETEL.has(k))).toEqual([]);
  });

  it('az őr a régi hibát megtalálja (önpróba)', () => {
    const css = '.a:focus-visible { box-shadow: var(--fokusz-gyuru); font-size: 11px; border-radius: 3px; height: 22px; }';
    const d = deklaraciok(css);
    expect(d.map((x) => x[1])).toEqual(['box-shadow', 'font-size', 'border-radius', 'height']);
    expect(SZIN_TOKENEK.has('fokusz-gyuru')).toBe(true);
    expect(SZIN_TOKENEK.has('graf-jegyzet')).toBe(true);
  });
});
