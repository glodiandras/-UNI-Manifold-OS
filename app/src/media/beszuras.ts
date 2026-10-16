// Beszúrás a jegyzetbe a PDF-ből és a lejátszóból (C16): az idézet `Source`-horgonnyal, és az időkód-link.
//
// A cél az aktív szerkesztő, különben az utoljára aktív, még nyitott (a PDF vagy a lejátszó mellett osztásban álló)
// jegyzet. Egy CodeMirror-tranzakció: a ⌘Z egy lépésben visszavon. A frontmatter a tulajdonság-szerkesztő útján
// változik (a core számolja az új blokkot, soronkénti cserével, C11b), a link szövege a core legrövidebb
// egyértelmű cél-alakja (L42). Ha nincs hová, a szöveg a vágólapra kerül.

import { ApiHiba } from '../lib/core/api';
import { ertesitesek } from '../lib/ertesites/ertesites.svelte';
import { t } from '../lib/i18n';
import { linkek } from '../lib/vault/linkek.svelte';
import { fajlNev } from '../lib/vault/fajlok.svelte';
import { irhato } from '../szerkeszto/beallitas';
import { szerkesztok, type SzerkesztoPeldany } from '../szerkeszto/szerkesztok.svelte';
import { tulajdonsagApi } from '../szerkeszto/tulajdonsagok/api';
import { blokkCsere, fmBlokk } from '../szerkeszto/tulajdonsagok/fm';

/** A beszúrás célja: írható (nem Olvasó módú, nem csak olvasható) szerkesztő, vagy `null` (T117). */
export function celSzerkeszto(): SzerkesztoPeldany | null {
  for (const p of [szerkesztok.aktiv, szerkesztok.utolso]) {
    const v = p?.nezet();
    if (p && v && p.mod() !== 'olvaso' && irhato(v)) return p;
  }
  return null;
}

/** Egy idézet-sor szövege: ne nyisson Markdown-blokkot, linket, megjegyzést vagy blokkazonosítót (a core `_escape`
 *  párja; a közös vektorok: `tests/adat/idezet_escape.json`, T168). */
export function idezetSor(s: string): string {
  let t = s.replaceAll('%%', '%​%').replaceAll('[[', '[​[').replaceAll(']]', ']​]');
  t = t.replace(/\s\^(?=[A-Za-z0-9-]+\n?$)/, ' \\^'); // a sorvégi ` ^azonosító` ne legyen blokkazonosító
  if (/^(#{1,6}\s|>|[-+*]\s|\d+[.)]\s|=+\s*$|-{3,}\s*$|```|~~~|\||<)/.test(t)) t = '\\' + t;
  return t;
}

/** A PDF-idézet blokkja: `> szöveg` és alatta `> — [[cél#page=N]]`. */
export function idezetBlokk(szoveg: string, cel: string, oldal: number): string {
  return `> ${idezetSor(szoveg)}\n> — [[${cel}#page=${oldal}]]`;
}

/** Az idő `m:ss` vagy `h:mm:ss` alakban (egész másodpercre lefelé). */
export function idoSzoveg(mp: number): string {
  const s = Math.max(0, Math.floor(Number.isFinite(mp) ? mp : 0));
  const h = Math.floor(s / 3600);
  const p = Math.floor((s % 3600) / 60);
  const m = String(s % 60).padStart(2, '0');
  return h ? `${h}:${String(p).padStart(2, '0')}:${m}` : `${p}:${m}`;
}

/** Az időkód-link: a horgony másodpercben, az alias olvasható időként. */
export function idokodLink(cel: string, mp: number): string {
  const s = Math.max(0, Math.floor(mp));
  return `[[${cel}#t=${s}|${idoSzoveg(s)}]]`;
}

/** A blokk beszúrási terve: a kurzor sora után új bekezdésként, üres sorban a sor helyén; a frontmatterben álló
 *  kurzornál a frontmatter után. Előtte és utána üres sor választja el (különben a következő sor az idézet
 *  folytatása lenne). */
export function blokkHely(doc: string, kurzor: number, blokk: string, fmVege: number): { from: number; to: number; insert: string } {
  const poz = Math.max(kurzor, fmVege);
  const sorEleje = doc.lastIndexOf('\n', poz - 1) + 1;
  const i = doc.indexOf('\n', poz);
  const sorVege = i < 0 ? doc.length : i;
  const kovetkezoNemUres = sorVege < doc.length && doc[sorVege + 1] !== undefined && doc[sorVege + 1] !== '\n';
  if (!doc.slice(sorEleje, sorVege).trim()) {
    const elotteUres = sorEleje === 0 || sorEleje <= fmVege || doc.slice(0, sorEleje).endsWith('\n\n');
    return { from: sorEleje, to: sorVege, insert: `${elotteUres ? '' : '\n'}${blokk}${kovetkezoNemUres ? '\n' : ''}` };
  }
  return { from: sorVege, to: sorVege, insert: `\n\n${blokk}${kovetkezoNemUres ? '\n' : ''}${sorVege === doc.length ? '\n' : ''}` };
}

function hibaSzoveg(e: unknown): string {
  return e instanceof ApiHiba || e instanceof Error ? e.message : String(e);
}

async function vagolapra(szoveg: string, cim: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(szoveg);
    ertesitesek.ertesit({ szint: 'figyelmeztetes', cim, szoveg: t('Nincs nyitott jegyzet: a szöveg a vágólapra került.') });
  } catch {
    ertesitesek.ertesit({ szint: 'figyelmeztetes', cim, szoveg: t('Nyiss meg egy jegyzetet (például osztásban), és próbáld újra.') });
  }
}

/** A `Source` frissítésének eredménye: az új frontmatter-blokk (`fm`; `null`, ha a horgony már benne van, vagy nem írható), és
 *  `kihagyva`: a Source-írás elmaradásának oka (magyar szöveg), ha a célra a `Source` séma-sértést okozna. */
interface SourceEredmeny {
  fm: string | null;
  kihagyva: string | null;
}

/** A `Source` lista új frontmatter-blokkja a horgonnyal. A séma-kapu nem kerülhető meg (CLAUDE.md 37. döntés, T073): a
 *  `megerosit` nem beégetett igaz — ha a cél osztályában nincs `Source`, vagy nincs frontmatter, vagy a blokk formailag hibás,
 *  a mező nem íródik (`kihagyva`), az idézet pedig a hivatkozás nélkül is bekerül (az értesítés szól). */
async function sourceFm(p: SzerkesztoPeldany, fm: string | null, horgony: string): Promise<SourceEredmeny> {
  const api = tulajdonsagApi();
  const el = await api.elemez(p.ut, fm);
  const forras = el.tulajdonsagok.find((x) => x.kulcs === 'Source');
  const regi = Array.isArray(forras?.ertek) ? (forras.ertek as unknown[]).filter((x): x is string => typeof x === 'string') : typeof forras?.ertek === 'string' && forras.ertek ? [forras.ertek] : [];
  const kis = horgony.toLowerCase();
  if (regi.some((x) => x.trim().toLowerCase() === kis)) return { fm: null, kihagyva: null };
  const e = await api.modosit(p.ut, fm, { muvelet: 'beallit', kulcs: 'Source', ertek: [...regi, horgony], tipus: 'multitext' }, false);
  if (!e.ok || e.fm_uj === null) {
    return { fm: null, kihagyva: e.problemak.map((x) => x.uzenet).join(' ') || t('a Source mező nem írható') };
  }
  return { fm: e.fm_uj, kihagyva: null };
}

export interface BeszurasEredmeny {
  ut: string;
  source: boolean;
}

/** PDF-idézet a célzott jegyzetbe (a `Source` listába is, ha még nincs benne). */
export async function idezetBeszur(pdf: string, oldal: number, szoveg: string): Promise<BeszurasEredmeny | null> {
  const p = celSzerkeszto();
  if (!p) {
    let cel = fajlNev(pdf) + '.pdf';
    try {
      cel = await linkek.linkCel(pdf, pdf);
    } catch {
      /* a fájlnév marad */
    }
    await vagolapra(idezetBlokk(szoveg, cel, oldal), t('Az idézet nem került jegyzetbe'));
    return null;
  }
  try {
    const cel = await linkek.linkCel(pdf, p.ut);
    const v0 = p.nezet()!;
    const fm0 = fmBlokk(v0.state.doc);
    const { fm: ujFm, kihagyva } = await sourceFm(p, fm0?.szoveg ?? null, `[[${cel}#page=${oldal}]]`);
    const v = p.nezet();
    const fm = v ? fmBlokk(v.state.doc) : null;
    if (!v || (fm?.szoveg ?? null) !== (fm0?.szoveg ?? null)) throw new Error(t('a jegyzet közben megváltozott; próbáld újra'));
    const doc = v.state.doc.toString();
    const fmCsere = ujFm !== null ? blokkCsere(fm, ujFm) : null;
    const blokk = blokkHely(doc, v.state.selection.main.head, idezetBlokk(szoveg, cel, oldal), fm?.ig ?? 0);
    const valtozasok = [fmCsere, blokk].filter((x): x is NonNullable<typeof x> => !!x).sort((a, b) => a.from - b.from);
    const cs = v.state.changes(valtozasok);
    const vege = cs.mapPos(blokk.to, 1) - (blokk.insert.endsWith('\n') ? 1 : 0);
    v.dispatch({ changes: cs, selection: { anchor: vege }, userEvent: 'input.paste', scrollIntoView: true });
    if (kihagyva) {
      ertesitesek.ertesit({
        szint: 'figyelmeztetes',
        cim: t('Az idézet Source nélkül került be'),
        szoveg: t('A jegyzet sémája nem engedi a forrás-hivatkozás beírását ({ok}) — az idézet a Source mező nélkül került a jegyzetbe.', { ok: kihagyva }),
      });
    }
    return { ut: p.ut, source: fmCsere !== null };
  } catch (e) {
    ertesitesek.ertesit({ szint: 'hiba', cim: t('Az idézet nem került be'), szoveg: hibaSzoveg(e) });
    return null;
  }
}

/** Időkód-link a célzott jegyzet kurzorához (a kijelölés helyére). */
export async function idokodBeszur(media: string, mp: number): Promise<BeszurasEredmeny | null> {
  const p = celSzerkeszto();
  let cel = fajlNev(media);
  try {
    cel = await linkek.linkCel(media, p?.ut ?? media);
  } catch {
    /* a fájlnév marad (az index még épül) */
  }
  const link = idokodLink(cel, mp);
  if (!p) {
    await vagolapra(link, t('Az időkód nem került jegyzetbe'));
    return null;
  }
  const v = p.nezet();
  if (!v) return null;
  const { from, to } = v.state.selection.main;
  const fm = fmBlokk(v.state.doc);
  if (fm && from < fm.ig) {
    // a frontmatterben álló kurzor: a link a frontmatter utáni első sorba, saját bekezdésként (a YAML ép marad)
    const b = blokkHely(v.state.doc.toString(), fm.ig, link, fm.ig);
    const vege = b.from + b.insert.length - (b.insert.endsWith('\n') ? 1 : 0);
    v.dispatch({ changes: b, selection: { anchor: vege }, userEvent: 'input.paste', scrollIntoView: true });
    return { ut: p.ut, source: false };
  }
  const elotte = from > 0 ? v.state.sliceDoc(from - 1, from) : '';
  const szoveg = (elotte && !/\s|\(|\[/.test(elotte) ? ' ' : '') + link;
  v.dispatch({ changes: { from, to, insert: szoveg }, selection: { anchor: from + szoveg.length }, userEvent: 'input.paste', scrollIntoView: true });
  return { ut: p.ut, source: false };
}
