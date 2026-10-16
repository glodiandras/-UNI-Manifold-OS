// A törzs címke-javaslatai a frontmatterrel közös CM-kiegészítőben. Csak valódi #token után kér
// adatot; a közös címketár összefogja az egyidejű igényeket és a WS-frissítést.

import type { CompletionContext, CompletionResult, CompletionSource } from '@codemirror/autocomplete';
import { ensureSyntaxTree } from '@codemirror/language';
import type { SyntaxNode } from '@lezer/common';
import { modulEngedelyezett } from '../../lib/beallitasok/allapot.svelte';
import { locale, tp } from '../../lib/i18n';
import { FuzzyIndex } from '../../lib/kereses/fuzzy';
import { cimkek, type CimkeCsucs } from '../../lib/vault/cimkek.svelte';
import { kiegeszitesNyitva } from '../linkek/kiegeszites';
import { CIMKE_KARAKTER, CIMKE_PREFIX, cimkeErtek } from '../markdown/cimke';

const VEDETT = new Set(['Frontmatter', 'FrontmatterContent', 'FencedCode', 'CodeBlock', 'InlineCode', 'MathBlock', 'InlineMath', 'DisplayMath', 'HTMLBlock', 'HTMLTag', 'Comment', 'CommentBlock', 'ObsidianComment', 'ObsidianCommentBlock', 'Link', 'Autolink', 'URL', 'LinkReference', 'Wikilink', 'Embed']);

export interface CimkeKiegeszitesOpciok {
  tar?: { readonly lista: CimkeCsucs[]; kerjen(): Promise<void> };
  engedelyezett?: () => boolean;
}

interface CimkeIndex { lista: CimkeCsucs[]; index: FuzzyIndex<CimkeCsucs> }
const indexek = new WeakMap<CimkeCsucs[], CimkeIndex>();
function cimkeIndex(lista: CimkeCsucs[]): CimkeIndex {
  let tar = indexek.get(lista);
  if (tar) return tar;
  const egyedi = new Map<string, CimkeCsucs>();
  for (const c of lista) {
    const ertek = cimkeErtek(c.cimke);
    if (!ertek) continue;
    const kis = ertek.toLowerCase();
    const elozo = egyedi.get(kis);
    if (!elozo || c.db > elozo.db || c.db === elozo.db && c.ossz > elozo.ossz) egyedi.set(kis, { ...c, cimke: ertek, kis });
  }
  const ervenyes = [...egyedi.values()];
  tar = { lista: ervenyes, index: new FuzzyIndex(ervenyes.map((c) => ({ ertek: c, nev: c.cimke }))) };
  indexek.set(lista, tar);
  return tar;
}

/** A # utáni tartomány: a kurzor utáni címke-folytatás is cserélődik, a # és az írásjelek maradnak. */
export function cimkeHely(cx: CompletionContext): { from: number; to: number; q: string } | null {
  const s = cx.state;
  if (s.readOnly || kiegeszitesNyitva(s)) return null;
  const sor = s.doc.lineAt(cx.pos);
  const m = CIMKE_PREFIX.exec(s.sliceDoc(sor.from, cx.pos));
  if (!m) return null;
  const from = cx.pos - m[1].length;
  const fa = ensureSyntaxTree(s, Math.min(s.doc.length, cx.pos + 1), 100);
  if (!fa) return null;
  // Balra is nézünk: lezárt kód/link végén közvetlenül a zárójel elé szúrt # még védett.
  for (const bias of [-1, 1] as const) for (let n: SyntaxNode | null = fa.resolveInner(cx.pos, bias); n; n = n.parent) if (VEDETT.has(n.name)) return null;
  let to = cx.pos;
  for (const c of s.sliceDoc(cx.pos, sor.to)) {
    if (!CIMKE_KARAKTER.test(c)) break;
    to += c.length;
  }
  return { from, to, q: m[1] };
}

export function cimkeForras(o: CimkeKiegeszitesOpciok = {}): CompletionSource {
  const tar = o.tar ?? cimkek;
  const engedelyezett = o.engedelyezett ?? (() => modulEngedelyezett('cimkek'));
  return async (cx): Promise<CompletionResult | null> => {
    if (!engedelyezett()) return null;
    const h = cimkeHely(cx);
    if (!h) return null;
    await tar.kerjen();
    if (cx.aborted || !engedelyezett()) return null;
    const { lista, index } = cimkeIndex(tar.lista);
    const talalatok = h.q ? index.keres(h.q, { limit: 60, bonusz: (c) => Math.min(20, Math.log2(Math.max(0, c.ossz) + 1) * 3) }) :
      [...lista].sort((a, b) => b.ossz - a.ossz || a.cimke.localeCompare(b.cimke, locale(), { numeric: true })).slice(0, 60).map((c) => ({ ertek: c, kiemeles: [] as [number, number][] }));
    if (!talalatok.length) return null;
    const kiemeles = new Map(talalatok.map((t) => [t.ertek.cimke, t.kiemeles.flat()]));
    return {
      from: h.from, to: h.to, filter: false,
      options: talalatok.map(({ ertek: c }, i) => ({ label: c.cimke, apply: c.cimke, type: 'keyword', detail: tp('{n} jegyzetben', c.ossz), boost: 99 - i })),
      getMatch: (c) => kiemeles.get(c.label) ?? [],
    };
  };
}
