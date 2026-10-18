// A canvas telepítése (C14): a `.canvas` fül nézete, a ⌘P parancsai és a `![[x.canvas]]` beágyazás. Az
// `App.svelte` hívja egyszer, a többi nézet telepítése mellett.

import './canvas.css';
import { ApiHiba, kerdez } from '../lib/core/api';
import type { Felulet } from '../lib/elrendezes/felulet.svelte';
import { nezetek } from '../lib/elrendezes/nezetek.svelte';
import { ertesitesek } from '../lib/ertesites/ertesites.svelte';
import { mappa, type VaultFajlok } from '../lib/vault/fajlok.svelte';
import type { Regiszter } from '../lib/parancsok/regiszter';
import { beagyazasRenderelok } from '../szerkeszto/beagyazas/regiszter';
import { canvasok, type CanvasParancs } from './aktiv.svelte';
import { canvasBeagyazasRenderelo } from './beagyazas';
import CanvasFul from './CanvasFul.svelte';
import { t, tk } from '../lib/i18n';

const PARANCSOK: [CanvasParancs, string, boolean][] = [
  ['uj-szoveg', tk('Canvas: új szövegkártya'), true],
  ['uj-fajl', tk('Canvas: jegyzet vagy fájl hozzáadása'), true],
  ['uj-link', tk('Canvas: új link-kártya'), true],
  ['uj-csoport', tk('Canvas: új csoport (a kijelölés köré)'), true],
  ['duplikal', tk('Canvas: a kijelölés duplikálása'), true],
  ['torol', tk('Canvas: a kijelölés törlése'), true],
  ['mind', tk('Canvas: mindent kijelöl'), false],
  ['mindent-mutat', tk('Canvas: mindent mutat'), false],
  ['nagyitas-100', tk('Canvas: nagyítás 100%'), false],
  ['nagyit', tk('Canvas: nagyítás'), false],
  ['kicsinyit', tk('Canvas: kicsinyítés'), false],
  ['racs', tk('Canvas: rácsra igazítás be/ki'), true],
  ['visszavon', tk('Canvas: visszavonás'), true],
  ['ujra', tk('Canvas: újra'), true],
  ['masol', tk('Canvas: copy the selection'), false],
  ['kivag', tk('Canvas: cut the selection'), true],
  ['beillesztes', tk('Canvas: paste'), true],
  ['kijeloles-mutat', tk('Canvas: zoom to selection'), false],
  ['objektum-igazitas', tk('Canvas: snap to other cards on/off'), false],
  ['jegyzette', tk('Canvas: convert the text card to a note'), true],
  ['alcel', tk('Canvas: choose heading, block, page or view of the card'), true],
  ['helyi-menu', tk('Canvas: open the context menu'), false],
];

// i18n-ignore: a vaultba írt fájlnév (azonosító), nem felületi szöveg; semleges angol alapérték (09-canvas-14)
export const UJ_NEV = 'Untitled';

/** Új, üres canvas (`{}`, az Obsidian alakja) az aktív fájl mappájában (különben a gyökérben), a következő szabad
 *  „Untitled N” néven; utána megnyílik. Meglévőt nem ír felül (a core `POST /api/vault/uj` szabálya). */
export async function ujCanvas(felulet: Felulet, fajlok: VaultFajlok): Promise<string | null> {
  const akt = felulet.munkaterulet.aktivFul?.ut ?? null;
  const hely = akt ? mappa(akt) : '';
  const foglalt = (nev: string) => !!fajlok.info(hely ? `${hely}/${nev}.canvas` : `${nev}.canvas`);
  for (let n = 0; n < 100; n++) {
    const nev = n ? `${UJ_NEV} ${n}` : UJ_NEV;
    if (foglalt(nev)) continue;
    try {
      const d = await kerdez<{ ut: string }>('/api/vault/uj', { metodus: 'POST', torzs: { mappa: hely, nev, tipus: 'canvas' }, idokorlat: 10000 });
      felulet.munkaterulet.megnyit(d.ut, akt ? 'ujful' : 'aktiv');
      return d.ut;
    } catch (e) {
      if (e instanceof ApiHiba && e.statusz === 400 && (e.kod === 'vault.van_ilyen_fajl' || /már van/.test(e.message))) continue;
      ertesitesek.ertesit({ szint: 'hiba', cim: t('Az új canvas nem jött létre'), szoveg: e instanceof Error ? e.message : String(e) });
      return null;
    }
  }
  return null;
}

export function canvasTelepit(reg: Regiszter, felulet: Felulet, fajlok: VaultFajlok): () => void {
  const le = [
    nezetek.regisztral({
      id: 'canvas',
      illeszkedik: (f, info) => !!f.ut && (info ? info.tipus === 'canvas' : f.ut.toLowerCase().endsWith('.canvas')),
      komponens: CanvasFul,
      prioritas: 10,
    }),
    beagyazasRenderelok.regisztral(canvasBeagyazasRenderelo),
    reg.regisztral({ id: 'canvas.uj', nev: tk('Új canvas'), kategoria: 'Canvas', futtat: () => void ujCanvas(felulet, fajlok) }),
    reg.regisztralMind(
      PARANCSOK.map(([p, nev, ir]) => ({
        id: `canvas.${p}`,
        nev,
        kategoria: 'Canvas',
        elerheto: () => !!canvasok.aktiv && (!ir || canvasok.aktiv.irhato()),
        futtat: () => canvasok.aktiv?.parancs(p),
      })),
    ),
  ];
  return () => le.forEach((f) => f());
}
