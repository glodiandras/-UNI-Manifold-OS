// A vault összes képlete a szerkesztő elemzőjével és KaTeX-beállításával (C08 kész-feltétele).
// Futtatás: tests/kezi/kepletek.py (az a vault útját és a riport helyét a configból adja át).
//
// A vaultot csak olvassa. Minden `.md` a core `bejaras()`-a szerint (a `.obsidian`, `.trash`, `.git`,
// `node_modules` és a ponttal kezdődő fájlok nélkül), a core `szoveg()`-e szerint dekódolva
// (UTF-8 cserekarakterrel, `\r\n` és `\r` → `\n`). Kimenet: JSON-riport fájlonkénti darabszámmal,
// a hibákkal és a szigorúsági figyelmeztetésekkel kategóriánként.

import { readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join, relative } from 'node:path';
import { expect, it } from 'vitest';
import { obsidianElemzo } from '../../src/szerkeszto/markdown/elemzo';
import { kepletek } from '../../src/szerkeszto/markdown/fa';
import { katexEllenoriz } from '../../src/szerkeszto/renderelok/katex';

const VAULT = process.env.MOS_KEZI_VAULT;
const RIPORT = process.env.MOS_KEZI_RIPORT;
const KIHAGY = new Set(['.obsidian', '.trash', '.git', 'node_modules']);

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

function sorSzam(poz: number, sorKezdetek: number[]): number {
  let lo = 0;
  let hi = sorKezdetek.length - 1;
  while (lo < hi) {
    const m = (lo + hi + 1) >> 1;
    if (sorKezdetek[m] <= poz) lo = m;
    else hi = m - 1;
  }
  return lo + 1;
}

it.skipIf(!VAULT || !RIPORT)('a vault minden képlete hiba nélkül renderelődik', () => {
  const dekodolo = new TextDecoder('utf-8');
  const fajlok = bejar(VAULT!);
  const darab: Record<string, { sor: number; blokk: number; tex: string; display: boolean }[]> = {};
  const hibak: { ut: string; sor: number; display: boolean; tex: string; hiba: string }[] = [];
  const szigoru: Record<string, { db: number; peldak: { ut: string; sor: number; tex: string; uzenet: string }[] }> = {};
  const metrika: Record<string, { db: number; peldak: { ut: string; sor: number; tex: string }[] }> = {};
  let osszes = 0;
  let display = 0;
  const kezdes = performance.now();

  const eredetiWarn = console.warn;
  let aktualis = { ut: '', sor: 0, tex: '' };
  console.warn = (...a: unknown[]) => {
    const uzenet = a.map(String).join(' ');
    const kulcs = uzenet.replace(/'[^']*'/g, "'…'").slice(0, 120);
    const k = (metrika[kulcs] ??= { db: 0, peldak: [] });
    k.db++;
    if (k.peldak.length < 5) k.peldak.push({ ...aktualis });
  };
  try {
    for (const p of fajlok) {
      const ut = relative(VAULT!, p).normalize('NFC');
      const szoveg = dekodolo.decode(readFileSync(p)).replace(/\r\n?/g, '\n');
      const fa = obsidianElemzo.parse(szoveg);
      const sorKezdetek = [0];
      for (let i = szoveg.indexOf('\n'); i >= 0; i = szoveg.indexOf('\n', i + 1)) sorKezdetek.push(i + 1);
      const lista = kepletek(fa, (a, b) => szoveg.slice(a, b));
      if (!lista.length) continue;
      darab[ut] = [];
      for (const k of lista) {
        const sor = sorSzam(k.from, sorKezdetek);
        darab[ut].push({ sor, blokk: k.blokk ? 1 : 0, tex: k.tex.trim(), display: k.display });
        osszes++;
        if (k.display) display++;
        aktualis = { ut, sor, tex: k.tex };
        try {
          katexEllenoriz(k.tex, k.display, (kod: string, uzenet: string) => {
            const s = (szigoru[kod] ??= { db: 0, peldak: [] });
            s.db++;
            if (s.peldak.length < 5) s.peldak.push({ ut, sor, tex: k.tex.slice(0, 200), uzenet });
            return 'ignore';
          });
        } catch (e) {
          hibak.push({ ut, sor, display: k.display, tex: k.tex, hiba: e instanceof Error ? e.message : String(e) });
        }
      }
    }
  } finally {
    console.warn = eredetiWarn;
  }

  const riport = {
    ido_mp: Math.round(performance.now() - kezdes) / 1000,
    fajlok: fajlok.length,
    fajlok_keplettel: Object.keys(darab).length,
    kepletek: osszes,
    soron_beluli: osszes - display,
    megjelenitesi: display,
    hibak,
    szigorusag: szigoru,
    metrika,
    fajlonkent: darab,
  };
  writeFileSync(RIPORT!, JSON.stringify(riport, null, 1));
  expect(hibak, `${hibak.length} renderelési hiba (riport: ${RIPORT})`).toEqual([]);
});
