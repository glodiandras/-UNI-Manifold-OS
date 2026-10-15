// A vault összes linkje a szerkesztő Lezer-elemzőjével (C10.6: paritás a core link-halmazával, audit M6).
// Futtatás: tests/kezi/link_lezer_paritas.py (az a vault útját és a riport helyét a configból adja át).
//
// A vaultot csak olvassa. Bejárás és dekódolás, mint a `kepletek.kezi.ts`-ben (a core `bejaras()`-a és
// `szoveg()`-e szerint). Fájlonként: a `Wikilink`/`Embed` és a `Link`/`Image` → `URL` linkek (sor, oszlop,
// cél), és minden olyan `[[`, amelyből az elemző NEM csinált linket, a környező csomópont nevével — ebből
// látszik, miért nem link (kód, képlet, megjegyzés, táblázatcella, lezáratlan). A sor 1-től, az oszlop 0-tól
// számol, kódpontban (mint a core). Itt nincs összevetés és nincs feloldás: azt a Python-oldal végzi.

import { readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join, relative } from 'node:path';
import { expect, it } from 'vitest';
import { wikilinkAdat } from '../../src/szerkeszto/linkek/adat';
import { obsidianElemzo } from '../../src/szerkeszto/markdown/elemzo';

const VAULT = process.env.MOS_KEZI_VAULT;
const RIPORT = process.env.MOS_KEZI_RIPORT;
const KIHAGY = new Set(['.obsidian', '.trash', '.git', 'node_modules']);
// a „miért nem link” szempontjából érdekes csomópontok (belülről kifelé az első találat a kontextus)
const KONTEXTUS = new Set([
  'InlineCode', 'FencedCode', 'CodeBlock', 'InlineMath', 'DisplayMath', 'MathBlock', 'Comment', 'CommentBlock',
  'HTMLBlock', 'HTMLTag', 'Frontmatter', 'TableCell', 'TableHeader', 'TableRow', 'LinkReference', 'Link', 'Image',
]);

function bejar(gyoker: string): string[] {
  const ki: string[] = [];
  const mappa = (ut: string) => {
    for (const e of readdirSync(ut, { withFileTypes: true })) {
      const p = join(ut, e.name);
      if (e.isDirectory()) {
        if (!KIHAGY.has(e.name)) mappa(p);
      } else if (e.isFile() && !e.name.startsWith('.') && e.name.toLowerCase().endsWith('.md')) ki.push(p);
    }
  };
  mappa(gyoker);
  return ki.sort();
}

interface Link {
  sor: number;
  oszlop: number;
  fajta: 'wiki' | 'md';
  beagyazas: boolean;
  cel: string;
}

interface NemLink {
  sor: number;
  oszlop: number;
  kontextus: string;
}

it.skipIf(!VAULT || !RIPORT)('a vault linkjei a szerkesztő elemzőjével', () => {
  const dekodolo = new TextDecoder('utf-8');
  const fajlok = bejar(VAULT!);
  const fajlonkent: Record<string, { linkek: Link[]; nem_link: NemLink[]; frontmatter_veg: number }> = {};
  let osszes = 0;
  const kezdes = performance.now();

  for (const p of fajlok) {
    const ut = relative(VAULT!, p).normalize('NFC');
    const szoveg = dekodolo.decode(readFileSync(p)).replace(/\r\n?/g, '\n');
    if (!szoveg.includes('[[') && !szoveg.includes('](')) continue;
    const fa = obsidianElemzo.parse(szoveg);
    const sorKezdetek = [0];
    for (let i = szoveg.indexOf('\n'); i >= 0; i = szoveg.indexOf('\n', i + 1)) sorKezdetek.push(i + 1);
    const hely = (poz: number): [number, number] => {
      let lo = 0;
      let hi = sorKezdetek.length - 1;
      while (lo < hi) {
        const m = (lo + hi + 1) >> 1;
        if (sorKezdetek[m] <= poz) lo = m;
        else hi = m - 1;
      }
      return [lo + 1, [...szoveg.slice(sorKezdetek[lo], poz)].length];
    };
    const olvas = (a: number, b: number) => szoveg.slice(a, b);
    const linkek: Link[] = [];
    const wikiKezdet = new Set<number>();
    let frontmatterVeg = 0;
    fa.iterate({
      enter(n) {
        if (n.name === 'Frontmatter') frontmatterVeg = n.to;
        const w = wikilinkAdat(n.node, olvas);
        if (w) {
          wikiKezdet.add(w.beagyazas ? n.from + 1 : n.from);
          const [sor, oszlop] = hely(n.from);
          linkek.push({ sor, oszlop, fajta: 'wiki', beagyazas: w.beagyazas, cel: w.cel });
        } else if (n.name === 'Link' || n.name === 'Image') {
          const url = n.node.getChild('URL');
          if (!url) return;
          let cel = olvas(url.from, url.to);
          if (cel.startsWith('<') && cel.endsWith('>')) cel = cel.slice(1, -1);
          const [sor, oszlop] = hely(n.name === 'Image' ? n.from + 1 : n.from);
          linkek.push({ sor, oszlop, fajta: 'md', beagyazas: n.name === 'Image', cel });
        }
      },
    });
    const nemLink: NemLink[] = [];
    for (let i = szoveg.indexOf('[['); i >= 0; i = szoveg.indexOf('[[', i + 1)) {
      if (wikiKezdet.has(i)) continue;
      let kontextus = '';
      let belso = '';
      let linkben = false;
      for (let c: ReturnType<typeof fa.resolveInner> | null = fa.resolveInner(i, 1); c; c = c.parent) {
        if (!belso) belso = c.name;
        if (c.name === 'Wikilink' || c.name === 'Embed') linkben = true;
        if (!kontextus && KONTEXTUS.has(c.name)) kontextus = c.name;
      }
      if (linkben) continue; // a link belsejében álló `[[` a cél része
      const [sor, oszlop] = hely(i);
      nemLink.push({ sor, oszlop, kontextus: kontextus || `egyéb: ${belso}` });
    }
    if (!linkek.length && !nemLink.length) continue;
    osszes += linkek.length;
    fajlonkent[ut] = { linkek, nem_link: nemLink, frontmatter_veg: [...szoveg.slice(0, frontmatterVeg)].length };
  }

  const riport = {
    ido_mp: Math.round(performance.now() - kezdes) / 1000,
    fajlok: fajlok.length,
    linkek: osszes,
    fajlonkent,
  };
  writeFileSync(RIPORT!, JSON.stringify(riport));
  expect(fajlok.length).toBeGreaterThan(0);
});
