// A kód-munkafelület műveletei (C36a-UI, F10: minden nyelvre): az ellenőrzés (⌘R / ⇧⌘R) a mentés kivárásával, a formázás
// (⇧⌥F, clang-format: C++) egy szerkesztő-tranzakcióban, az új C++ feladat. A futtatás, a fordítás és az összevetés a core
// motorjáé (homokozóban, 53(b)); a felület forrást csak a felhasználó szerkesztésével ír (a meglévő egyetlen írási úton),
// gép nem (53(d)).

import { ApiHiba, kerdez } from '../lib/core/api';
import type { Felulet } from '../lib/elrendezes/felulet.svelte';
import { ertesitesek } from '../lib/ertesites/ertesites.svelte';
import { t } from '../lib/i18n';
import { csere } from '../szerkeszto/dokumentum/kulonbseg';
import { szerkesztok } from '../szerkeszto/szerkesztok.svelte';
import { kodFulok } from './aktiv.svelte';
import { kodFutasok, type FutasMod } from './futas.svelte';
import { BEAGYAZOTT_KOD, jegyzetNyelve, kodNyelvek, motorUt, nyelvUt, type KodNyelv, type Motor } from './nyelvek.svelte';

export interface KodCel {
  /** amit a core-nak küldünk (a forrás vagy a feladat-jegyzet) */
  ut: string;
  /** a jegyzetből indított futás jegyzete */
  jegyzet: string | null;
}

/** Az aktív Markdown-jegyzet szövege (a szerkesztő nézetéből, különben a nyitott dokumentumból). */
function jegyzetSzoveg(ut: string): string | undefined {
  const sz = szerkesztok.aktiv;
  const v = sz && sz.ut === ut ? sz.nezet() : null;
  return v ? v.state.doc.toString() : szerkesztok.dokumentumok.kap(ut)?.szoveg.toString();
}

/** A parancs célja: az aktív kód-fül, vagy az aktív, forrást (bármely ismert nyelvét) beágyazó Markdown-jegyzet; különben nincs. */
export function kodCel(): KodCel | null {
  const k = kodFulok.aktiv;
  if (k) return { ut: k.ut, jegyzet: null };
  const sz = szerkesztok.aktiv;
  if (sz && /\.md$/i.test(sz.ut)) {
    const szoveg = jegyzetSzoveg(sz.ut);
    if (szoveg && BEAGYAZOTT_KOD.test(szoveg)) return { ut: sz.ut, jegyzet: sz.ut };
  }
  return null;
}

/** A cél nyelve és motorja: a forrás kiterjesztéséből, jegyzetnél az első beágyazott forrásból (ahogy a core is választ). */
export function celNyelve(cel: KodCel | null): { nyelv: KodNyelv | null; motor: Motor } {
  if (!cel) return { nyelv: null, motor: 'cpp' };
  if (!/\.md$/i.test(cel.ut)) return { nyelv: nyelvUt(cel.ut), motor: motorUt(cel.ut) };
  const j = jegyzetNyelve(jegyzetSzoveg(cel.ut) ?? '');
  return j ? { nyelv: j.nyelv, motor: j.motor } : { nyelv: null, motor: 'cpp' };
}

/** A nyitott dokumentum mentésének kivárása (⌘R előtt): igaz, ha utána nincs mentetlen változás. */
export async function mentesKivar(ut: string): Promise<boolean> {
  const d = szerkesztok.dokumentumok.kap(ut);
  if (!d) return true;
  if (d.piszkos) await d.ment();
  else await d.kivar();
  return !d.mentetlen;
}

const varj = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** A forrás-fül előhozása: a már nyitott fül a paneljében előre kerül (a fókusz marad), különben osztásban nyílik. */
export function forrasMegmutat(felulet: Felulet, forras: string): void {
  const mt = felulet.munkaterulet;
  for (const p of mt.panelek()) {
    const f = p.fulek.find((x) => x.ut === forras);
    if (f) {
      p.aktiv = f.id;
      return;
    }
  }
  const eredeti = mt.aktivPanelId;
  mt.megnyit(forras, 'osztas');
  mt.aktival(eredeti);
}

/** Az ellenőrzés indítása. A jegyzetből indítva a forrás-fül előkerül (az eredmény ott látszik). */
export async function ellenoriz(felulet: Felulet, mod: FutasMod, cel: KodCel | null = kodCel(), jegyzet?: string): Promise<boolean> {
  if (!cel) return false;
  if (kodFutasok.fut) {
    ertesitesek.ertesit({ szint: 'info', cim: t('Már fut egy ellenőrzés'), szoveg: t('Várd meg a végét, vagy szakítsd meg (Esc).') });
    return false;
  }
  const valasztott = jegyzet ?? cel.jegyzet ?? kodFutasok.jegyzetValasztas.get(cel.ut) ?? null;
  // a mentés kivárása: a motor a lemezen álló fájlt fordítja (a jegyzetét és a .cpp-ét is)
  const utak = [cel.ut, valasztott].filter((u): u is string => !!u);
  for (const u of utak)
    if (!(await mentesKivar(u))) {
      ertesitesek.ertesit({
        szint: 'figyelmeztetes',
        cim: t('Az ellenőrzés nem indult'),
        szoveg: t('A fájl nincs mentve ({ut}); előbb az ütközést vagy a mentési hibát kell rendezni.', { ut: u }),
      });
      return false;
    }
  const { motor, nyelv } = celNyelve(cel);
  let r = await kodFutasok.indit(cel.ut, mod, valasztott, motor, nyelv?.azonosito);
  // a mentetlen-jelzés a WS-en megy: a mentés után egy rövid ideig a core még a régit láthatja
  for (let i = 0; !r.ok && r.kod === 'mentetlen' && i < 3; i++) {
    await varj(250 * (i + 1));
    r = await kodFutasok.indit(cel.ut, mod, valasztott, motor, nyelv?.azonosito);
  }
  if (r.ok) {
    kodFutasok.tobbertelmu = null;
    if (!kodFulok.aktiv || kodFulok.aktiv.ut !== r.cpp) forrasMegmutat(felulet, r.cpp);
    return true;
  }
  switch (r.kod) {
    case 'tobbertelmu':
      kodFutasok.tobbertelmu = { ut: cel.ut, mod, jegyzetek: r.jegyzetek ?? [] };
      break;
    case 'nincs_eszkoztar':
      ertesitesek.ertesit({ szint: 'hiba', cim: t('Nincs C++ eszköztár'), szoveg: r.uzenet, idotartam: 0 });
      break;
    case 'nincs_eszkozlanc': // az általános motor: a core üzenete megmondja, mi hiányzik és mi a teendő
      ertesitesek.ertesit({ szint: 'hiba', cim: t('Hiányzik az eszközlánc'), szoveg: r.uzenet, idotartam: 0 });
      void kodNyelvek.betolt(true);
      break;
    case 'foglalt':
      ertesitesek.ertesit({ szint: 'info', cim: t('Már fut egy ellenőrzés'), szoveg: r.uzenet });
      break;
    default:
      ertesitesek.ertesit({ szint: 'hiba', cim: t('Az ellenőrzés nem indult'), szoveg: r.uzenet });
  }
  return false;
}

/** Formázás clang-formattal (a core a homokozóban futtatja; C++): az eredmény egyetlen szerkesztő-tranzakció (⌘Z egy lépés). */
export async function formaz(): Promise<boolean> {
  const k = kodFulok.aktiv;
  const v = k?.nezet();
  if (!k || !v) return false;
  if (nyelvUt(k.ut)?.azonosito !== 'cpp') {
    ertesitesek.ertesit({ szint: 'info', cim: t('A formázás kimaradt'), szoveg: t('A formázás (clang-format) csak C++ forráson érhető el.') });
    return false;
  }
  if (!k.irhato()) {
    ertesitesek.ertesit({ szint: 'figyelmeztetes', cim: t('A fájl most nem írható'), szoveg: t('A formázás kimaradt.') });
    return false;
  }
  const elotte = v.state.doc.toString();
  let d: { szoveg: string; valtozott: boolean };
  try {
    d = await kerdez('/api/cpp/formaz', { metodus: 'POST', torzs: { szoveg: elotte }, idokorlat: 35000 });
  } catch (e) {
    ertesitesek.ertesit({ szint: 'hiba', cim: t('A formázás nem sikerült'), szoveg: e instanceof ApiHiba ? e.message : String(e) });
    return false;
  }
  if (!d.valtozott) return true;
  const most = k.nezet();
  if (!most || most.state.doc.toString() !== elotte) {
    ertesitesek.ertesit({ szint: 'info', cim: t('A formázás kimaradt'), szoveg: t('A szöveg közben változott; próbáld újra.') });
    return false;
  }
  const c = csere(most.state.doc, d.szoveg);
  if (c) most.dispatch({ changes: c, userEvent: 'input.format', scrollIntoView: false });
  return true;
}

/** Új feladat a kód-munkafelület bármely nyelvén (alap: C++): a forrás és a jegyzet a core-ban (két commit); utána a jegyzet nyílik, a forrás osztásban. */
export async function ujFeladat(felulet: Felulet, mappa: string, nev: string, nyelv = 'cpp'): Promise<{ ok: true } | { ok: false; hiba: string }> {
  let d: { jegyzet: string; cpp: string; forras?: string; nyelv?: string; figyelmeztetes?: string | null };
  try {
    d = await kerdez('/api/cpp/feladat', { metodus: 'POST', torzs: { mappa, nev, nyelv }, idokorlat: 15000 });
  } catch (e) {
    return { ok: false, hiba: e instanceof ApiHiba ? e.message : String(e) };
  }
  const mt = felulet.munkaterulet;
  mt.megnyit(d.jegyzet, mt.aktivFul?.ut ? 'ujful' : 'aktiv');
  forrasMegmutat(felulet, d.forras ?? d.cpp);
  if (d.figyelmeztetes) ertesitesek.ertesit({ szint: 'figyelmeztetes', cim: t('Az új feladat elkészült'), szoveg: d.figyelmeztetes });
  return { ok: true };
}
