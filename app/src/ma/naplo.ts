// A napi jegyzet és a sablon-beszúrás műveletei (C15). A logika a core-é (útvonal, váz, kiértékelés); itt csak a
// megnyitás, a kurzor és a hibák felülete van.

import { ApiHiba, kerdez } from '../lib/core/api';
import { t } from '../lib/i18n';
import type { Felulet } from '../lib/elrendezes/felulet.svelte';
import { ertesitesek } from '../lib/ertesites/ertesites.svelte';
import { asszisztensApi } from '../lib/asszisztens/api';
import { vezerloKapcsolok } from '../lib/vezerlo/kapcsolok.svelte';
import { fajlNev } from '../lib/vault/fajlok.svelte';
import { irhato } from '../szerkeszto/beallitas';
import { szerkesztok, type SzerkesztoPeldany } from '../szerkeszto/szerkesztok.svelte';
import { osszefesul, tulajdonsagApi } from '../szerkeszto/tulajdonsagok/api';
import { blokkCsere, fmBlokk } from '../szerkeszto/tulajdonsagok/fm';
import type { OsszefesulesEredmeny } from '../szerkeszto/tulajdonsagok/tipusok';
import { beszurasTerv } from './sablon';
import type { NaploValasz, SablonKimenet } from './tipusok';

const uzenet = (e: unknown) => (e instanceof ApiHiba ? e.message : e instanceof Error ? e.message : String(e));

/**
 * ⌘⇧D: a mai napi jegyzet megnyitása; ha még nincs, a core létrehozza a vault konvenciója szerint (a váz a
 * sablonmappa „Napi jegyzet” jegyzete, ha van), és a kurzor a `{{cursor}}` helyére áll. Kétszeri hívás ugyanazt a
 * jegyzetet nyitja (a core nem ír felül). A Ma-nézet fülét nem írja át: a jegyzet új fülben nyílik mellette.
 */
export async function napiJegyzetNyit(felulet: Felulet): Promise<void> {
  let d: NaploValasz;
  try {
    d = await kerdez<NaploValasz>('/api/naplo/ma', { metodus: 'POST', torzs: {}, idokorlat: 15000 });
  } catch (e) {
    ertesitesek.ertesit({ szint: 'hiba', cim: t('A napi jegyzet nem nyitható meg'), szoveg: uzenet(e) });
    return;
  }
  felulet.atfedes = null;
  const m = felulet.munkaterulet;
  m.megnyit(d.ut, 'aktiv');
  const ful = m.aktivFul;
  if (d.letrejott && d.kurzor !== null && ful && ful.ut === d.ut && !ful.nezet) ful.nezet = { kurzor: d.kurzor };
  felulet.megmutatFaban(d.ut);
  if (d.letrejott) ertesitesek.ertesit({ szint: 'siker', cim: t('Napi jegyzet létrehozva'), szoveg: fajlNev(d.ut) });
  if (d.figyelmeztetes) ertesitesek.ertesit({ szint: 'figyelmeztetes', cim: t('Pillanatkép nélkül mentve'), szoveg: d.figyelmeztetes });
}

/** „Új jegyzet sablonból” (C32b): a sablon-választó megnyitása új-jegyzet módban; a választás után a fájlfa kéri be a nevet
 *  (`mappa`: a cél mappa, `null`: a fa fókuszált mappája), a core a `POST /api/sablon/uj` úton hozza létre. A parancs a fát is
 *  megnyitja, hogy a névmező látszódjon (csendben az oldalsáv átfedésként). */
export function ujJegyzetSablonbol(felulet: Felulet, mappa: string | null): void {
  felulet.sablonUj = { mappa };
  felulet.atfedes = 'sablon';
}

/** Elérhető-e a sablon beszúrása: van nyitott, nem Olvasó módú szerkesztő. */
export function sablonBeszurasElerheto(): boolean {
  const p = szerkesztok.aktiv;
  const v = p?.nezet();
  return !!p && p.mod() !== 'olvaso' && !!v && irhato(v);
}

/** A sablon kiértékelése a core-ban és beszúrása az aktív szerkesztő kurzorához (egy tranzakció: a ⌘Z egy lépés). */
export async function sablonBeszurasAktiv(sablonUt: string): Promise<void> {
  const p = szerkesztok.aktiv;
  const cel = p?.nezet();
  if (!p || p.mod() === 'olvaso' || (cel && !irhato(cel))) {
    ertesitesek.ertesit({
      szint: 'figyelmeztetes',
      cim: t('Nincs hová beszúrni'),
      szoveg: cel && !irhato(cel) ? t('A jegyzet csak olvasható.') : t('Nyiss meg egy jegyzetet szerkesztésre.'),
    });
    return;
  }
  let k: SablonKimenet;
  try {
    k = await kerdez<SablonKimenet>('/api/sablon/kiertekel', { metodus: 'POST', torzs: { ut: sablonUt, cim: fajlNev(p.ut) }, idokorlat: 10000 });
  } catch (e) {
    ertesitesek.ertesit({ szint: 'hiba', cim: t('A sablon nem értékelhető ki'), szoveg: uzenet(e) });
    return;
  }
  const aktivE = () => {
    const v = szerkesztok.aktiv?.nezet();
    return v && szerkesztok.aktiv === p && irhato(v) ? v : null;
  };
  let v = aktivE();
  if (!v) {                                                // közben másik jegyzetre váltott (vagy csak olvasható lett)
    ertesitesek.ertesit({ szint: 'figyelmeztetes', cim: t('A sablon nem került be'), szoveg: t('Közben másik jegyzet lett az aktív.') });
    return;
  }
  // C32b: mindkettőnek van frontmatterje → a core összefésüli (a számolás nem ír; az írás a dokumentumon át megy)
  const sablonFm = k.frontmatter ? fmBlokk(k.szoveg) : null;
  const jegyzetFm = sablonFm ? (fmBlokk(v.state.doc.toString())?.szoveg ?? null) : null;
  let of: OsszefesulesEredmeny | null = null;
  if (sablonFm && jegyzetFm !== null) {
    try {
      of = await osszefesul(p.ut, jegyzetFm, sablonFm.szoveg);
    } catch {
      of = null;                                           // régi core vagy hiba: a sablon tulajdonságai kimaradnak (értesítéssel)
    }
    v = aktivE();
    if (!v || (fmBlokk(v.state.doc.toString())?.szoveg ?? null) !== jegyzetFm) {
      ertesitesek.ertesit({ szint: 'figyelmeztetes', cim: t('A sablon nem került be'), szoveg: t('Közben megváltozott a jegyzet tulajdonsága; próbáld újra.') });
      return;
    }
  }
  const s = v.state.selection.main;
  const terv = beszurasTerv(v.state.doc.toString(), s.from, s.to, k, of);
  v.dispatch({ changes: terv.changes, selection: { anchor: terv.anchor }, scrollIntoView: true, userEvent: 'input.paste' });
  v.focus();
  // J1: a sablon beszúrása a tanuló magnak (ismétlődő művelet: ebben a mappában ezt a sablont használod)
  if (vezerloKapcsolok.ertek.asszisztens && p.ut.toLowerCase().endsWith('.md')) void asszisztensApi.tanul('sablon', p.ut, sablonUt).catch(() => undefined);
  if (terv.frontmatterKihagyva)
    ertesitesek.ertesit({ szint: 'info', cim: t('A sablon tulajdonságai kimaradtak'), szoveg: t('A jegyzetnek már van frontmatterje; a törzs bekerült.') });
  if (of) osszefesulesJelzes(p, of);
}

const KULCSOK = (l: string[]) => l.join(', ');

/** Az összefésülés csendes visszajelzése: csak akkor szól, ha valami nem úgy ment, ahogy a sablon kérte (meglévő érték
 *  megmaradt, nem írható kulcs kimaradt), és a séma-sértő kulcsok megerősítése (az írás a `modosit` útján). */
function osszefesulesJelzes(p: SzerkesztoPeldany, of: OsszefesulesEredmeny): void {
  const kihagyva = of.kihagyva.filter((x) => x.kulcs !== null).map((x) => x.kulcs as string);
  if (of.megmaradt.length || kihagyva.length)
    ertesitesek.ertesit({
      szint: 'info',
      cim: t('A sablon tulajdonságai összefésülve'),
      szoveg: [of.megmaradt.length ? t('A jegyzet értéke megmaradt: {kulcsok}.', { kulcsok: KULCSOK(of.megmaradt) }) : '', kihagyva.length ? t('Nem írható: {kulcsok}.', { kulcsok: KULCSOK(kihagyva) }) : '']
        .filter(Boolean)
        .join(' '),
    });
  if (!of.fuggo.length) return;
  ertesitesek.ertesit({
    szint: 'figyelmeztetes',
    cim: t('A sablon séma-sértő tulajdonságot kér'),
    szoveg: of.fuggo.map((f) => `${f.kulcs}: ${f.problemak[0]?.uzenet ?? t('a séma szerint nem szokásos')}`).join(' · '),
    idotartam: 0,
    kulcs: 'sablon-fuggo',
    muvelet: { nev: t('Mégis beírom'), futtat: () => void fuggoBeir(p, of.fuggo) },
  });
}

/** A megerősített, séma-sértő kulcsok beírása: kulcsonként a `modosit` `megerosit: true` hívása (ugyanaz az út, mint a
 *  tulajdonság-panel „Mégis beírom” gombjáé), a csere a nyitott dokumentumba megy (⌘Z). */
async function fuggoBeir(p: SzerkesztoPeldany, fuggo: OsszefesulesEredmeny['fuggo']): Promise<void> {
  const api = tulajdonsagApi();
  for (const f of fuggo) {
    const v = szerkesztok.aktiv === p ? p.nezet() : null;
    if (!v || !irhato(v)) {
      ertesitesek.ertesit({ szint: 'figyelmeztetes', cim: t('A tulajdonság nem került be'), szoveg: t('Közben másik jegyzet lett az aktív.') });
      return;
    }
    const blokk = fmBlokk(v.state.doc.toString());
    try {
      const r = await api.modosit(p.ut, blokk?.szoveg ?? null, { muvelet: 'beallit', kulcs: f.kulcs, ertek: f.ertek, tipus: f.tipus }, true);
      const most = p.nezet();
      if (!most || (fmBlokk(most.state.doc.toString())?.szoveg ?? null) !== (blokk?.szoveg ?? null)) throw new Error(t('Közben megváltozott a frontmatter.'));
      if (!r.ok || r.fm_uj === null) throw new Error(r.problemak[0]?.uzenet ?? t('A módosítás nem írható.'));
      const c = blokkCsere(blokk, r.fm_uj);
      if (c) most.dispatch({ changes: c, userEvent: 'input.tulajdonsag' });
    } catch (e) {
      ertesitesek.ertesit({ szint: 'hiba', cim: t('A(z) „{kulcs}” nem írható', { kulcs: f.kulcs }), szoveg: uzenet(e) });
    }
  }
}
