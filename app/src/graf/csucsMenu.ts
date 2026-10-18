// A gráf csúcsának menüje (11-graph-05): jobb gomb vagy Shift+F10 / ContextMenu a kijelölt csúcson, illetve a címke- és
// a feloldatlan csúcs kattintása. A menü a közös lebegő menü (`notion/menu`): billentyűzettel járható, Esc zár és visszaadja a
// fókuszt a vászonnak. A létrehozás a meglévő, core-hatáskörű új-jegyzet útvonalon megy (`jegyzetLetrehoz`, L42): a gráf
// sem fájlt nem ír, sem célt nem talál ki.

import { t } from '../lib/i18n';
import type { Felulet } from '../lib/elrendezes/felulet.svelte';
import { ertesitesek } from '../lib/ertesites/ertesites.svelte';
import { keresoMegnyit } from '../lib/kereses/kereso';
import { CIMKE_ELOTAG, FELOLDATLAN_ELOTAG, type GrafAdat } from '../lib/graf/modell';
import { cimkeKeresheto, jegyzetLetrehoz, type NyitasMod } from '../szerkeszto/linkek/navigacio';
import { lebegoMenu, type MenuElem } from '../szerkeszto/notion/menu';

export interface CsucsMenuKontextus {
  felulet: Felulet;
  /** Fájl megnyitása a gráf nézetéhez illő panelben (a jegyzet melletti helyi gráfnál a jegyzet csoportjában). */
  fajlMegnyit(ut: string, mod: NyitasMod): void;
  /** A csúcs helyi gráfja ugyanebben a nézetben. */
  helyiGraf(ut: string): void;
  /** A fókusz visszaadása a vászonnak. */
  fokusz(): void;
}

/** A vágólapra másolás; a hibát látható értesítés mondja (ikonnal és szóval), nem csendes. */
async function masol(szoveg: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(szoveg);
  } catch {
    ertesitesek.ertesit({ szint: 'hiba', cim: t('A vágólapra másolás nem sikerült'), szoveg });
  }
}

/** A menü elemei (tiszta függvény: a teszt a lebegő menü nélkül is vizsgálja). Az elemek `fn` mezeje a művelet. */
export function csucsMenuElemek(
  g: GrafAdat,
  i: number,
  k: CsucsMenuKontextus,
): { elemek: MenuElem[]; akciok: Map<string, () => void> } {
  const elemek: MenuElem[] = [];
  const akciok = new Map<string, () => void>();
  const hozzaad = (id: string, nev: string, fn: () => void, letiltva = false) => {
    elemek.push({ id, nev, ...(letiltva ? { letiltva } : {}) });
    akciok.set(id, fn);
  };
  const tipus = g.tipus[i];
  if (tipus === 'cimke') {
    const cimke = g.ut[i].slice(CIMKE_ELOTAG.length);
    const nev = g.nev[i].replace(/^#/, '');
    hozzaad('kereses', t('Keresés erre a címkére'), () => keresoMegnyit(k.felulet, `tag:#${nev}`), !cimkeKeresheto());
    hozzaad('masol', t('Címke másolása'), () => void masol(`#${nev || cimke}`));
  } else if (tipus === 'feloldatlan') {
    const cel = g.ut[i].slice(FELOLDATLAN_ELOTAG.length);
    // forrás = az első jegyzet, amely erre hivatkozik (a core a forrás mappájából dönti el a helyet)
    const jegyzet = [...g.szomszedok(i)].find((j) => !g.virtualis(j));
    const forras = jegyzet === undefined ? null : g.ut[jegyzet];
    hozzaad(
      'letrehoz',
      t('Jegyzet létrehozása'),
      () => {
        if (!forras) return;
        void jegyzetLetrehoz(forras, cel).then((ut) => {
          if (!ut) return;
          ertesitesek.ertesit({ szint: 'siker', cim: t('Új jegyzet'), szoveg: ut, idotartam: 3000 });
          k.fajlMegnyit(ut, 'ujful');
        });
      },
      forras === null,
    );
    hozzaad('masol', t('Név másolása'), () => void masol(cel));
  } else {
    const ut = g.ut[i];
    hozzaad('megnyit', t('Megnyitás'), () => k.fajlMegnyit(ut, 'aktiv'));
    hozzaad('ujful', t('Megnyitás új fülben'), () => k.fajlMegnyit(ut, 'ujful'));
    hozzaad('osztas', t('Megnyitás jobbra'), () => k.fajlMegnyit(ut, 'osztas'));
    hozzaad('fa', t('Megmutatás a fájlfában'), () => k.felulet.megmutatFaban(ut));
    hozzaad('helyi', t('Helyi gráf innen'), () => k.helyiGraf(ut));
    hozzaad('masol', t('Útvonal másolása'), () => void masol(ut));
  }
  return { elemek, akciok };
}

/**
 * Megnyitja a csúcs menüjét a `clientX`, `clientY` pontnál; a visszaadott függvény bezárja. A kattintott címke egyetlen
 * lépésben keres (ha a Címkék és a Keresés modul él), a többi esetben a menü ajánlja fel a műveletet.
 */
export function csucsMenu(g: GrafAdat, i: number, clientX: number, clientY: number, k: CsucsMenuKontextus, kozvetlenCimke = false): (fokusz?: boolean) => void {
  if (kozvetlenCimke && g.tipus[i] === 'cimke' && cimkeKeresheto()) {
    keresoMegnyit(k.felulet, `tag:#${g.nev[i].replace(/^#/, '')}`);
    return () => undefined;
  }
  const { elemek, akciok } = csucsMenuElemek(g, i, k);
  return lebegoMenu({ focus: () => k.fokusz() }, clientX, clientY, elemek, akciok, t('Gráfcsúcs menü'));
}
