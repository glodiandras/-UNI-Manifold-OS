// Az AI-réteg műveletei a felületen (C36b, F10: minden nyelvre): az indítás (a mentés kivárásával, mint a ⌘R) és a javaslat
// ELFOGADÁSA. Gép semmit nem ír magától (53(d)): a teszt-blokk a feladat-jegyzetbe, a javított program a forrásba csak a felhasználó
// gombnyomására kerül, egyetlen szerkesztő-tranzakcióban a nyitott dokumentumon (`Dokumentum.valtozott`, a nyitott nézet
// előzményébe: a ⌘Z egy lépés), és a szokásos mentési úton íródik (pillanatképpel, ha a fájl máshol nincs nyitva).

import { ChangeSet } from '@codemirror/state';
import type { Felulet } from '../lib/elrendezes/felulet.svelte';
import { ertesitesek } from '../lib/ertesites/ertesites.svelte';
import { t, tk } from '../lib/i18n';
import type { Dokumentum } from '../szerkeszto/dokumentum/dokumentum.svelte';
import { csere } from '../szerkeszto/dokumentum/kulonbseg';
import { szerkesztok } from '../szerkeszto/szerkesztok.svelte';
import { kodAI, type AIMod } from './ai.svelte';
import { kodFulok } from './aktiv.svelte';
import { kodFutasok } from './futas.svelte';
import { BEAGYAZOTT_KOD } from './nyelvek.svelte';
import { celNyelve, forrasMegmutat, kodCel, mentesKivar, type KodCel } from './muveletek';

const UZENET: Record<string, string> = {
  nincs_kalibralt: tk('A C++ AI-hoz még nincs kalibrált modell (a `kod` mérése után kapcsol be).'),
  nincs_eszkoztar: tk('Nincs C++ eszköztár: bin/mos cpp telepit --igen'),
  foglalt: tk('Már fut egy AI-kérés: várd meg a végét, vagy szakítsd meg.'),
  megerosites_kell: tk('A teljes megoldás csak megerősítéssel kérhető.'),
};

/** Egy AI-kérés indítása az aktív kód-fülről vagy feladat-jegyzetből. */
export async function aiKer(felulet: Felulet, mod: AIMod, megerosit = false, cel: KodCel | null = kodCel()): Promise<boolean> {
  if (!cel) return false;
  const jegyzet = cel.jegyzet ?? kodFutasok.jegyzetValasztas.get(cel.ut) ?? null;
  for (const u of [cel.ut, jegyzet].filter((x): x is string => !!x))
    if (!(await mentesKivar(u))) {
      ertesitesek.ertesit({ szint: 'figyelmeztetes', cim: t('Az AI-kérés nem indult'), szoveg: t('A fájl nincs mentve ({ut}).', { ut: u }) });
      return false;
    }
  const { motor, nyelv } = celNyelve(cel);
  let r = await kodAI.indit(mod, cel.ut, jegyzet, megerosit, motor, nyelv?.azonosito);
  for (let i = 0; !r.ok && r.kod === 'mentetlen' && i < 3; i++) {
    await new Promise((v) => setTimeout(v, 250 * (i + 1)));
    r = await kodAI.indit(mod, cel.ut, jegyzet, megerosit, motor, nyelv?.azonosito);
  }
  if (r.ok) {
    const cpp = kodAI.aktiv?.cpp;
    if (cpp && (!kodFulok.aktiv || kodFulok.aktiv.ut !== cpp)) forrasMegmutat(felulet, cpp);
    return true;
  }
  if (r.kod === 'tobbertelmu') {
    ertesitesek.ertesit({ szint: 'info', cim: t('Melyik feladat?'), szoveg: t('Több jegyzet ágyazza be ezt a fájlt: előbb futtasd a ⌘R-t, és válassz.') });
    return false;
  }
  // a C36b szolgáltatás kódjaihoz saját (C++) szöveg tartozik; az általános motor mondata (nyelv, hiányzó eszköz, trial-szabály) a core-é
  const szoveg = r.motor === 'cpp' && UZENET[r.kod] ? t(UZENET[r.kod]) : r.uzenet;
  ertesitesek.ertesit({ szint: r.kod === 'foglalt' ? 'info' : 'hiba', cim: t('Az AI-kérés nem indult'), szoveg, idotartam: r.kod === 'nincs_eszkozlanc' ? 0 : undefined });
  return false;
}

type Eredmeny = { ok: true } | { ok: false; uzenet: string };

async function dokumentumon(ut: string, valtoztat: (d: Dokumentum) => ChangeSet | null): Promise<Eredmeny> {
  const dk = szerkesztok.dokumentumok;
  let d: Dokumentum;
  try {
    d = await dk.megnyit(ut);
  } catch (e) {
    return { ok: false, uzenet: e instanceof Error ? e.message : String(e) };
  }
  try {
    if (d.csakOlvashato) return { ok: false, uzenet: d.csakOlvashato };
    if (d.allapot === 'utkozes' || d.allapot === 'eltunt') return { ok: false, uzenet: t('A fájl közben megváltozott vagy eltűnt; előbb azt kell rendezni.') };
    const cs = valtoztat(d);
    if (cs) d.valtozott(cs, cs.apply(d.szoveg), null, true);
    const m = await d.ment(d.nezetSzam === 0 ? { pillanat: true } : {});
    return m.ok ? { ok: true } : { ok: false, uzenet: d.hiba ?? t('A mentés nem sikerült.') };
  } finally {
    await dk.elenged(d);
  }
}

/** A beszúrás helye: az utolsó `teszt` blokk után, különben a beágyazott forrás elé, különben a végére. */
export function tesztHely(szoveg: string): number {
  const sorok = szoveg.split('\n');
  let poz = 0;
  let utolsoTesztVeg = -1;
  let beagyazas = -1;
  let nyito: string | null = null;
  for (const s of sorok) {
    const veg = poz + s.length;
    if (nyito) {
      if (s.trim().startsWith(nyito) && s.trim().replace(/`/g, '') === '') {
        utolsoTesztVeg = Math.min(veg + 1, szoveg.length);
        nyito = null;
      }
    } else {
      const m = /^(`{3,})teszt\b/.exec(s.trim());
      if (m) nyito = m[1];
      else if (beagyazas < 0 && BEAGYAZOTT_KOD.test(s)) beagyazas = poz;
    }
    poz = veg + 1;
  }
  if (utolsoTesztVeg >= 0) return utolsoTesztVeg;
  if (beagyazas >= 0) return beagyazas;
  return szoveg.length;
}

/** A beszúrt szöveg: a blokk előtt és után egy-egy üres sor (a meglévő sortörésekkel együtt). */
export function beszurando(szoveg: string, hely: number, blokk: string): string {
  const elotte = szoveg.slice(0, hely);
  const kezd = hely === 0 || elotte.endsWith('\n\n') ? '' : elotte.endsWith('\n') ? '\n' : '\n\n';
  const b = blokk.endsWith('\n') ? blokk : blokk + '\n';
  const utana = hely < szoveg.length && !szoveg.startsWith('\n', hely) ? '\n' : '';
  return kezd + b + utana;
}

/** Egy ellenőrzött teszt-blokk beszúrása a feladat-jegyzetbe (egy tranzakció). */
export function tesztBeszur(jegyzet: string, blokk: string): Promise<Eredmeny> {
  return dokumentumon(jegyzet, (d) => {
    const szoveg = d.szoveg.toString();
    const hely = tesztHely(szoveg);
    return ChangeSet.of([{ from: hely, insert: beszurando(szoveg, hely, blokk) }], szoveg.length);
  });
}

/** A javított program beillesztése a forrásba (a teljes szöveg cseréje egy tranzakcióban; ⌘Z visszahozza a régit). */
export function megoldasBeilleszt(cpp: string, kod: string): Promise<Eredmeny> {
  return dokumentumon(cpp, (d) => {
    const c = csere(d.szoveg, kod.endsWith('\n') ? kod : kod + '\n');
    return c ? ChangeSet.of([c], d.szoveg.length) : null;
  });
}
