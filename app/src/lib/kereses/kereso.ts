// A nagy keresőablak (E3, ⇧⌘F) segédei: a megnyitás (a kijelölés a kezdő szöveg, mint az Obsidianben) és a kiemelendő
// szavak a keresőnyelvű lekérdezésből (a fájlnév és a mappa-út kiemeléséhez; a tartalom kiemelését a core adja).

import { modalisNyitva } from '../fokusz/hatokor';
import { tick } from 'svelte';
import { modulEngedelyezett } from '../beallitasok/allapot.svelte';
import type { Felulet } from '../elrendezes/felulet.svelte';
import { szerkesztok } from '../../szerkeszto/szerkesztok.svelte';
import { vaultKereses } from './vaultKereses.svelte';

/** Az aktív szerkesztő egysoros kijelölése (ez lesz a kezdő keresőszöveg), különben üres. */
export function kijeloltSzoveg(): string {
  const v = szerkesztok.aktiv?.nezet();
  const r = v?.state.selection.main;
  if (!v || !r || r.empty) return '';
  const sz = v.state.sliceDoc(r.from, r.to).trim();
  return sz && !sz.includes('\n') && sz.length <= 200 ? sz : '';
}

/** A keresőablak megnyitása. `szoveg`: kezdő lekérdezés (pl. „Keresés ebben a mappában”); nélküle az aktív kijelölés,
 *  és ha nincs, az előző lekérdezés marad (a mező megnyitáskor kijelöli). */
export function keresoMegnyit(felulet: Felulet, szoveg?: string): void {
  if (!modulEngedelyezett('kereses')) return;
  const kezdo = szoveg ?? (kijeloltSzoveg() || undefined);
  if (kezdo !== undefined) vaultKereses.beallit(kezdo, true);
  felulet.atfedes = 'kereso';
}

const dokkolasok = new WeakMap<Felulet, number>();
/** A tartós találati panel: a lekérdezés marad, az átfedés fókuszvisszaadását kivárva kap fókuszt. */
export function keresoOldalsav(felulet: Felulet): void {
  if (!modulEngedelyezett('kereses')) return;
  const n = (dokkolasok.get(felulet) ?? 0) + 1;
  dokkolasok.set(felulet, n);
  felulet.atfedes = null;
  felulet.oldalsav.nezet = 'kereses';
  felulet.oldalsav.nyitva = true;
  void (async () => {
    await tick();
    for (let i = 0; i < 36 && document.querySelector('.fatyol'); i++) await new Promise(r => setTimeout(r, 20));
    if (dokkolasok.get(felulet) === n && felulet.oldalsav.nezet === 'kereses' && felulet.atfedes === null && !modalisNyitva() && modulEngedelyezett('kereses')) vaultKereses.fokuszal();
  })();
}

const MUVELET = /^(?:OR|AND)$/;

/** A lekérdezés szó szerint keresett szavai (a kiemeléshez): az idézőjelek, a zárójelek, az operátorok, a
 *  `-tagadás`, a `tag:`, a `line:` és a `/regex/` kimarad; a `path:` és a `file:` értéke marad (a név és az út kiemelése). */
export function keresoSzavak(q: string): string[] {
  const ki: string[] = [];
  for (const m of q.matchAll(/"([^"]*)"|(\S+)/g)) {
    let s = m[1] ?? m[2];
    if (m[2] !== undefined) {
      s = s.replace(/^[()]+|[()]+$/g, '');
      if (s.startsWith('-') || MUVELET.test(s) || /^(?:tag|line):/i.test(s)) continue;
      s = s.replace(/^(?:path|file):/i, '').replace(/^"|"$/g, '');
      if (s.length > 1 && s.startsWith('/') && s.endsWith('/')) continue;
    }
    s = s.trim();
    if (s) ki.push(s);
  }
  return [...new Set(ki)];
}

/** Ékezet- és kis-nagybetű-független alak, UTF-16 egységenként (a hossz megmarad, így az indexek az eredeti szövegére érvényesek). */
function gyuru(s: string): string {
  return s
    .split('')
    .map((c) => c.normalize('NFD')[0].toLowerCase()[0] ?? c)
    .join('');
}

/** A szöveg kiemelésre szabdalt darabjai a szavak ékezet- és kis-nagybetű-független előfordulásai szerint. */
export function szoKiemeles(szoveg: string, szavak: string[]): { t: string; jelolt: boolean }[] {
  if (!szavak.length) return [{ t: szoveg, jelolt: false }];
  const g = gyuru(szoveg);
  const tartomanyok: [number, number][] = [];
  for (const sz of szavak) {
    const k = gyuru(sz);
    if (!k) continue;
    for (let i = g.indexOf(k); i >= 0; i = g.indexOf(k, i + k.length)) tartomanyok.push([i, i + k.length]);
  }
  tartomanyok.sort((a, b) => a[0] - b[0] || b[1] - a[1]);
  const ki: { t: string; jelolt: boolean }[] = [];
  let p = 0;
  for (const [a, b] of tartomanyok) {
    if (b <= p) continue;
    const kezd = Math.max(a, p);
    if (kezd > p) ki.push({ t: szoveg.slice(p, kezd), jelolt: false });
    ki.push({ t: szoveg.slice(kezd, b), jelolt: true });
    p = b;
  }
  if (p < szoveg.length) ki.push({ t: szoveg.slice(p), jelolt: false });
  return ki;
}
