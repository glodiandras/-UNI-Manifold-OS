// A javaslat-kártya állapota és elfogadása (J3; ESZREVETELEK-TERV 2. fejezet 3. pont). A kártya középen jelenik meg
// („Mit szólnál…?” Igen/Nem), **nem modális és nem kér fókuszt** (CX tartós döntése): a gépelés megy tovább, a kártya
// magától eltűnik, ha nem döntesz. Az elfogadás **csak a nyitott jegyzetbe ír, a szerkesztőn át**: egyetlen tranzakció
// (⌘Z egy lépés); a címke a tulajdonság-szerkesztő `modosit` útján (a séma-sértő érték nem íródik csendben, 22(b));
// a sablon a „Sablon beszúrása” meglévő útján. A döntés a core hangolásába megy (fajta × helyzet).

import { isolateHistory } from '@codemirror/commands';
import type { EditorView } from '@codemirror/view';
import { ertesitesek } from '../ertesites/ertesites.svelte';
import type { Parancs } from '../parancsok/regiszter';
import { blokkCsere, fmBlokk } from '../../szerkeszto/tulajdonsagok/fm';
import { tulajdonsagApi } from '../../szerkeszto/tulajdonsagok/api';
import type { TulajdonsagApi } from '../../szerkeszto/tulajdonsagok/tipusok';
import { asszisztensApi } from './api';
import type { KartyaJavaslat, KartyaDontes } from './tipusok';

export const KARTYA_LATHATO_MS = 30_000;

export interface KartyaSegedek {
  ut: string;
  /** a link célja a core legrövidebb egyértelmű alakjában (L42) */
  linkCel(cel: string): Promise<string>;
  tulajdonsag?: Pick<TulajdonsagApi, 'elemez' | 'modosit'>;
  sablon?(ut: string): Promise<void>;
}

/** A dokumentum végére egy új bekezdés (üres sorral elválasztva). */
function vegere(view: EditorView, szoveg: string): void {
  const doc = view.state.doc;
  const vege = doc.sliceString(Math.max(0, doc.length - 2));
  const elo = doc.length === 0 ? '' : vege.endsWith('\n\n') ? '' : vege.endsWith('\n') ? '\n' : '\n\n';
  view.dispatch({ changes: { from: doc.length, insert: `${elo}${szoveg}\n` }, annotations: isolateHistory.of('full'), userEvent: 'input.complete' });
}

/** Az elfogadás végrehajtása. `true`: bekerült; szöveg: miért nem (értesítésnek). */
export async function kartyaAlkalmaz(view: EditorView, j: KartyaJavaslat, s: KartyaSegedek): Promise<true | string> {
  if (view.state.readOnly) return 'A jegyzet csak olvasható.';
  const m = j.muvelet;
  if (m.fajta === 'szakasz') {
    vegere(view, m.szoveg);
    return true;
  }
  if (m.fajta === 'link') {
    const doc = view.state.doc;
    const cel = await s.linkCel(m.cel);
    if (view.state.doc !== doc) return 'Közben változott a jegyzet; a javaslat elmaradt.';
    vegere(view, `Kapcsolódó: [[${cel}]]`);
    return true;
  }
  if (m.fajta === 'sablon') {
    if (!s.sablon) return 'A sablon most nem szúrható be.';
    await s.sablon(m.ut);
    return true;
  }
  // címke: a tulajdonság-szerkesztő egyetlen írási útja (a nyitott dokumentum frontmatter-blokkjának cseréje)
  const api = s.tulajdonsag ?? tulajdonsagApi();
  const fm = fmBlokk(view.state.doc);
  if (!fm) return 'A jegyzetnek nincs tulajdonság-blokkja; a címkét a tulajdonság-panelen adhatod hozzá.';
  const e = await api.elemez(s.ut, fm.szoveg);
  const t = e.tulajdonsagok.find((x) => x.tipus === 'tags' || x.kulcs.toLowerCase() === 'tags');
  const kulcs = t?.kulcs ?? 'Tags';
  const regi = Array.isArray(t?.ertek) ? (t!.ertek as unknown[]).map(String) : typeof t?.ertek === 'string' && t.ertek ? [t.ertek] : [];
  if (regi.some((c) => c.replace(/^#/, '').toLowerCase() === m.ertek.toLowerCase())) return true;
  const r = await api.modosit(s.ut, fm.szoveg, { muvelet: 'beallit', kulcs, ertek: [...regi, m.ertek] }, false);
  if (!r.ok || r.fm_uj === null) return r.problemak[0]?.uzenet ?? 'A címke a séma szerint nem írható be csendben; a tulajdonság-panelen megerősítheted.';
  const most = fmBlokk(view.state.doc);
  if (most?.szoveg !== fm.szoveg) return 'Közben változott a jegyzet tulajdonsága; a javaslat elmaradt.';
  const c = blokkCsere(most, r.fm_uj);
  if (c) view.dispatch({ changes: c, annotations: isolateHistory.of('full'), userEvent: 'input.complete' });
  return true;
}

interface Aktiv {
  javaslat: KartyaJavaslat;
  view: EditorView;
  segedek: KartyaSegedek;
}

export class KartyaAllapot {
  aktiv = $state.raw<Aktiv | null>(null);
  foglalt = $state(false);
  private ido: ReturnType<typeof setTimeout> | null = null;
  constructor(private readonly dontesKuld: (d: KartyaDontes) => Promise<unknown> = (d) => asszisztensApi.kartyaDontes(d),
    private readonly lathatoMs = KARTYA_LATHATO_MS) {}

  mutat(javaslat: KartyaJavaslat, view: EditorView, segedek: KartyaSegedek): void {
    if (this.aktiv) return;
    this.aktiv = { javaslat, view, segedek };
    this.idozit();
  }

  private idozit(): void {
    if (this.ido) clearTimeout(this.ido);
    this.ido = setTimeout(() => this.elrejt('figyelmen_kivul'), this.lathatoMs);
  }

  /** Az egér a kártyán: amíg olvasod, nem tűnik el. */
  tart(): void {
    if (this.aktiv) this.idozit();
  }

  private kuld(a: Aktiv, dontes: KartyaDontes['dontes']): void {
    const j = a.javaslat;
    void this.dontesKuld({ azon: j.azon, tipus: j.tipus, helyzet: j.helyzet, dontes, cim: j.cim }).catch(() => undefined);
  }

  /** Eltűnés döntés nélkül (lejárt, a jegyzet bezárult): kis súlyú „figyelmen kívül” jel. */
  elrejt(dontes: 'figyelmen_kivul' | null = null, view?: EditorView): void {
    const a = this.aktiv;
    if (!a || (view && a.view !== view)) return;
    if (this.ido) clearTimeout(this.ido);
    this.ido = null;
    this.aktiv = null;
    if (dontes) this.kuld(a, dontes);
  }

  async igen(): Promise<void> {
    const a = this.aktiv;
    if (!a || this.foglalt) return;
    this.foglalt = true;
    try {
      const r = a.view.dom.isConnected ? await kartyaAlkalmaz(a.view, a.javaslat, a.segedek) : 'A jegyzet közben bezárult.';
      if (r === true) this.kuld(a, 'elfogad');
      else ertesitesek.ertesit({ szint: 'figyelmeztetes', cim: 'A javaslat nem került be', szoveg: r });
    } catch (e) {
      ertesitesek.ertesit({ szint: 'hiba', cim: 'A javaslat nem került be', szoveg: e instanceof Error ? e.message : String(e) });
    } finally {
      this.foglalt = false;
      if (this.aktiv === a) this.elrejt(null);
    }
  }

  nem(): void {
    const a = this.aktiv;
    if (!a) return;
    this.elrejt(null);
    this.kuld(a, 'elutasit');
  }
}

export const kartyaAllapot = new KartyaAllapot();

/** A kártya parancsai a ⌘P-ben (a kártya nem kér fókuszt, így billentyűről is elérhető). */
export function kartyaParancsok(): Parancs[] {
  const van = () => !!kartyaAllapot.aktiv;
  return [
    { id: 'asszisztens.kartya-igen', nev: 'Asszisztens: a javaslat elfogadása', kategoria: 'Asszisztens', elerheto: van, futtat: () => kartyaAllapot.igen() },
    { id: 'asszisztens.kartya-nem', nev: 'Asszisztens: a javaslat elutasítása', kategoria: 'Asszisztens', elerheto: van, futtat: () => kartyaAllapot.nem() },
  ];
}
