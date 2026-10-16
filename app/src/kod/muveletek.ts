// A C++ munkafelület műveletei (C36a-UI): az ellenőrzés (⌘R / ⇧⌘R) a mentés kivárásával, a formázás (⇧⌥F) egy
// szerkesztő-tranzakcióban, az új feladat. A futtatás, a fordítás és az összevetés a core motorjáé (homokozóban, 53(b));
// a felület `.cpp`-t csak a felhasználó szerkesztésével ír (a meglévő egyetlen írási úton), gép nem (53(d)).

import { ApiHiba, kerdez } from '../lib/core/api';
import type { Felulet } from '../lib/elrendezes/felulet.svelte';
import { ertesitesek } from '../lib/ertesites/ertesites.svelte';
import { t } from '../lib/i18n';
import { csere } from '../szerkeszto/dokumentum/kulonbseg';
import { szerkesztok } from '../szerkeszto/szerkesztok.svelte';
import { kodFulok } from './aktiv.svelte';
import { kodFutasok, type FutasMod } from './futas.svelte';

/** A jegyzet beágyaz-e `.cpp`-t (csak felismerés, a feloldás a core-é, L42; a minta a `core/cpp_teszt.py`-é). */
export const BEAGYAZOTT_CPP = /!\[\[[^\]|#\n]+?\.cpp(?:#[^\]|\n]*)?(?:\|[^\]\n]*)?\]\]/i;

export interface KodCel {
  /** amit a core-nak küldünk (`.cpp` vagy a feladat-jegyzet) */
  ut: string;
  /** a jegyzetből indított futás jegyzete */
  jegyzet: string | null;
}

/** A parancs célja: az aktív `.cpp` fül, vagy az aktív, `.cpp`-t beágyazó Markdown-jegyzet; különben nincs. */
export function kodCel(): KodCel | null {
  const k = kodFulok.aktiv;
  if (k) return { ut: k.ut, jegyzet: null };
  const sz = szerkesztok.aktiv;
  if (sz && /\.md$/i.test(sz.ut)) {
    const v = sz.nezet();
    const szoveg = v ? v.state.doc.toString() : szerkesztok.dokumentumok.kap(sz.ut)?.szoveg.toString();
    if (szoveg && BEAGYAZOTT_CPP.test(szoveg)) return { ut: sz.ut, jegyzet: sz.ut };
  }
  return null;
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

/** A `.cpp` fül előhozása: a már nyitott fül a paneljében előre kerül (a fókusz marad), különben osztásban nyílik. */
export function cppMegmutat(felulet: Felulet, cpp: string): void {
  const mt = felulet.munkaterulet;
  for (const p of mt.panelek()) {
    const f = p.fulek.find((x) => x.ut === cpp);
    if (f) {
      p.aktiv = f.id;
      return;
    }
  }
  const eredeti = mt.aktivPanelId;
  mt.megnyit(cpp, 'osztas');
  mt.aktival(eredeti);
}

/** Az ellenőrzés indítása. A jegyzetből indítva a `.cpp` fül előkerül (az eredmény ott látszik). */
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
  let r = await kodFutasok.indit(cel.ut, mod, valasztott);
  // a mentetlen-jelzés a WS-en megy: a mentés után egy rövid ideig a core még a régit láthatja
  for (let i = 0; !r.ok && r.kod === 'mentetlen' && i < 3; i++) {
    await varj(250 * (i + 1));
    r = await kodFutasok.indit(cel.ut, mod, valasztott);
  }
  if (r.ok) {
    kodFutasok.tobbertelmu = null;
    if (!kodFulok.aktiv || kodFulok.aktiv.ut !== r.cpp) cppMegmutat(felulet, r.cpp);
    return true;
  }
  switch (r.kod) {
    case 'tobbertelmu':
      kodFutasok.tobbertelmu = { ut: cel.ut, mod, jegyzetek: r.jegyzetek ?? [] };
      break;
    case 'nincs_eszkoztar':
      ertesitesek.ertesit({ szint: 'hiba', cim: t('Nincs C++ eszköztár'), szoveg: r.uzenet, idotartam: 0 });
      break;
    case 'foglalt':
      ertesitesek.ertesit({ szint: 'info', cim: t('Már fut egy ellenőrzés'), szoveg: r.uzenet });
      break;
    default:
      ertesitesek.ertesit({ szint: 'hiba', cim: t('Az ellenőrzés nem indult'), szoveg: r.uzenet });
  }
  return false;
}

/** Formázás clang-formattal (a core a homokozóban futtatja): az eredmény egyetlen szerkesztő-tranzakció (⌘Z egy lépés). */
export async function formaz(): Promise<boolean> {
  const k = kodFulok.aktiv;
  const v = k?.nezet();
  if (!k || !v) return false;
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

/** Új C++ feladat: a `.cpp` és a sablonos jegyzet a core-ban (két commit); utána a jegyzet nyílik, a `.cpp` osztásban. */
export async function ujFeladat(felulet: Felulet, mappa: string, nev: string): Promise<{ ok: true } | { ok: false; hiba: string }> {
  let d: { jegyzet: string; cpp: string; figyelmeztetes?: string | null };
  try {
    d = await kerdez('/api/cpp/feladat', { metodus: 'POST', torzs: { mappa, nev }, idokorlat: 15000 });
  } catch (e) {
    return { ok: false, hiba: e instanceof ApiHiba ? e.message : String(e) };
  }
  const mt = felulet.munkaterulet;
  mt.megnyit(d.jegyzet, mt.aktivFul?.ut ? 'ujful' : 'aktiv');
  cppMegmutat(felulet, d.cpp);
  if (d.figyelmeztetes) ertesitesek.ertesit({ szint: 'figyelmeztetes', cim: t('Az új feladat elkészült'), szoveg: d.figyelmeztetes });
  return { ok: true };
}
