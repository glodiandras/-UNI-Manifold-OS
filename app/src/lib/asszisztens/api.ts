// Az Asszisztens (C30a) core-hívásai. A teljes riport a háttérben számolódik: ezek a hívások sosem számolnak soron belül.

import { kerdez } from '../core/api';
import type { DontesFajta, EmlitesValasz, HasonlosagValasz, HigieniaOsszegzes, JegyzetHigienia, KartyaDontes, KartyaValasz, Statisztika, SzokasJavaslat, TanultFajta, TanultLista, TanultMuvelet } from './tipusok';

const q = encodeURIComponent;

export const asszisztensApi = {
  /** Egy jegyzet tételei (a jobb panelhez). */
  jegyzetHigienia: (ut: string) => kerdez<JegyzetHigienia>(`/api/higienia?ut=${q(ut)}`, { idokorlat: 10000 }),
  osszegzes: () => kerdez<HigieniaOsszegzes>('/api/asszisztens/higienia', { idokorlat: 10000 }),
  latva: () => kerdez<HigieniaOsszegzes>('/api/asszisztens/higienia/latva', { metodus: 'POST', torzs: {}, idokorlat: 10000 }),
  szokas: () => kerdez<{ javaslat: SzokasJavaslat | null }>('/api/asszisztens/szokas', { idokorlat: 10000 }),
  szokasDontes: (azon: string, dontes: 'elfogad' | 'elutasit') =>
    kerdez<{ ok: boolean }>('/api/asszisztens/szokas/dontes', { metodus: 'POST', torzs: { azon, dontes }, idokorlat: 10000 }),
  /** A nyitott (akár mentetlen) szöveg linkeletlen említései (C30a core API; a szerkesztő linkjavaslata). */
  emlitesek: (ut: string, szoveg: string, jel?: AbortSignal) =>
    kerdez<EmlitesValasz>('/api/asszisztens/emlitesek', { metodus: 'POST', torzs: { ut, szoveg }, idokorlat: 8000, jel }),
  /** A jegyzet és a javasolt célok hasonlósága (C25c; C30b linkjavaslat-szűrő): modell nélkül, a vektortárból; `allapot != ok`: nincs szűrés. */
  hasonlosag: (ut: string, celok: string[], jel?: AbortSignal) =>
    kerdez<HasonlosagValasz>('/api/kereses/hasonlosag', { metodus: 'POST', torzs: { ut, celok }, idokorlat: 8000, jel }),
  /** Egy javaslat sorsa: csak a fajta és a döntés megy (útvonal és szöveg nélkül, 51(d)); a core a két kapcsoló alatt számolja. */
  dontes: (fajta: DontesFajta, dontes: 'elfogad' | 'elutasit') =>
    kerdez<{ fogadva: boolean; ok?: string }>('/api/asszisztens/dontes', { metodus: 'POST', torzs: { fajta, dontes }, idokorlat: 10000 }),
  /** J1: egy felhasználói művelet (címke, sablon, link) jelzése a tanuló magnak; a core a kapcsolót nézi, a vaultba nem ír. */
  tanul: (muvelet: TanultMuvelet, ut: string, ertek: string) =>
    kerdez<{ fogadva: boolean; tanult?: boolean }>('/api/asszisztens/tanul', { metodus: 'POST', torzs: { muvelet, ut, ertek }, idokorlat: 5000 }),
  /** CX-011: egy szövegminta kézi tanítása (előzmény → folytatás). */
  mintaTanit: (elotte: string, szoveg: string) =>
    kerdez<{ mintak: { elotte: string; szoveg: string }[] }>('/api/asszisztens/mintak/tanit', { metodus: 'POST', torzs: { elotte, szoveg }, idokorlat: 10000 }),
  /** J3: a nyitott (akár mentetlen) jegyzet kártya-jelöltje; modellt nem hív. */
  kartya: (ut: string, szoveg: string, alkalom: 'megnyitas' | 'szunet', jel?: AbortSignal) =>
    kerdez<KartyaValasz>('/api/asszisztens/kartya', { metodus: 'POST', torzs: { ut, szoveg, alkalom }, idokorlat: 8000, jel }),
  kartyaDontes: (d: KartyaDontes) => kerdez<{ fogadva: boolean }>('/api/asszisztens/kartya/dontes', { metodus: 'POST', torzs: d, idokorlat: 5000 }),
  /** J1: a „Mit tanult az asszisztens” lista és a soronkénti törlés. */
  tanult: () => kerdez<TanultLista>('/api/asszisztens/tanult', { idokorlat: 10000 }),
  tanultTorol: (fajta: TanultFajta, kulcs?: string) =>
    kerdez<TanultLista & { ok: boolean }>('/api/asszisztens/tanult/torles', { metodus: 'POST', torzs: { fajta, kulcs }, idokorlat: 10000 }),
  statisztika: () => kerdez<Statisztika>('/api/asszisztens/statisztika', { idokorlat: 10000 }),
  statisztikaTorol: () =>
    kerdez<{ torolt: number; tisztitva: boolean }>('/api/asszisztens/statisztika/torles', { metodus: 'POST', torzs: {}, idokorlat: 60000 }),
};
