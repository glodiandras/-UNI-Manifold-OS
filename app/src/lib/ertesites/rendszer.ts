// A rendszerértesítések (E10, CLAUDE.md 80(f)): a belső értesítésből (`ertesitesek`) azt, ami nem várhat, a macOS Értesítési
// központjába is elküldi — de csak akkor, ha az app nincs előtérben. Előtérben a belső buborék marad (egyik sem duplikálódik).
//
// Mi megy natívba (`nativbaMegy`):
//   - minden `hiba` szintű értesítés (köztük a mentési hiba, a vault eltűnése, a megszakadt core),
//   - minden, amit a hívó `rendszer: true`-val jelöl (pillanatkép nélküli mentés; a kézzel indított háttérfeladat vége).
// A natív híd a héj `{tipus: 'ertesites'}` üzenete; a kattintás a `window.manifold.ertesitesKattintas(azon)` hídon jön vissza.
// Böngészőben (héj nélkül) a küldés csendben elmarad.

import { hejbenFut, hejnek, type HejUzenet } from '../core/hej';
import type { Ertesites } from './ertesites.svelte';

/** A héj is korlátozza a szöveget; itt is vágjuk, hogy a hosszú hibaüzenet ne a héjon csonkuljon el hibásan. */
export const MAX_CIM = 120;
export const MAX_SZOVEG = 240;
/** Ennyi nyitott (kattintható) rendszerértesítést tartunk számon; a régebbi kattintása a belső előzményre esik vissza. */
const MAX_NYITOTT = 30;

export interface RendszerKornyezet {
  /** a felület a natív héjban fut (böngészőben nincs rendszerértesítés) */
  hejben: boolean;
  /** az ablak látszik és fókuszban van */
  elotter: boolean;
  /** a felhasználó beállítása (⌘P „Rendszerértesítések be/ki”) */
  bekapcsolva: boolean;
}

/** A küldés szabálya (tiszta függvény): natívba megy-e az értesítés. */
export function nativbaMegy(e: { szint: string; rendszer?: boolean }, k: RendszerKornyezet): boolean {
  if (!k.hejben || !k.bekapcsolva || k.elotter) return false;
  return e.szint === 'hiba' || e.rendszer === true;
}

export function elotterben(): boolean {
  return typeof document !== 'undefined' && document.visibilityState === 'visible' && document.hasFocus();
}

/** A híd üzenete: sortörés nélküli, levágott szöveg (a héj ezt jeleníti meg). */
export function ertesitesUzenet(e: { cim: string; szoveg: string; szint: string }, azon: string): Extract<HejUzenet, { tipus: 'ertesites' }> {
  const vag = (s: string, n: number) => {
    const t = s.replace(/\s+/g, ' ').trim();
    return t.length > n ? `${t.slice(0, n - 1)}…` : t;
  };
  return {
    tipus: 'ertesites',
    cim: vag(e.cim, MAX_CIM),
    szoveg: vag(e.szoveg, MAX_SZOVEG),
    azon,
    kategoria: e.szint === 'hiba' ? 'hiba' : e.szint === 'siker' ? 'kesz' : 'jelzes',
  };
}

/** A küldő és a kattintás-kezelő egy példánya. */
export class RendszerErtesites {
  bekapcsolva: () => boolean = () => true;
  /** ha az azonosítóhoz nincs művelet: az értesítés-előzmény megnyitása */
  alapMuvelet: () => void = () => {};
  /** a kattintásra futó művelet (a belső értesítés „Részletek” stb. gombja) azonosító szerint */
  private readonly nyitott = new Map<string, (() => void) | null>();

  private kornyezet(): RendszerKornyezet {
    return { hejben: hejbenFut(), elotter: elotterben(), bekapcsolva: this.bekapcsolva() };
  }

  kuld(e: Ertesites): boolean {
    if (!nativbaMegy(e, this.kornyezet())) return false;
    const azon = `e${e.id}`;
    this.nyitott.delete(azon); // frissített (kulcsos) értesítés: a sor végére kerül
    this.nyitott.set(azon, e.muvelet ? e.muvelet.futtat : null);
    while (this.nyitott.size > MAX_NYITOTT) this.nyitott.delete(this.nyitott.keys().next().value as string);
    hejnek(ertesitesUzenet(e, azon));
    return true;
  }

  /** A natív értesítésre kattintottak (az app már előre jött). */
  kattintas(azon: unknown): void {
    if (typeof azon !== 'string') return;
    const muvelet = this.nyitott.get(azon);
    this.nyitott.delete(azon);
    try {
      (muvelet ?? this.alapMuvelet)();
    } catch {
      // a kattintás hibája nem viheti el a hidat
    }
  }
}

export const rendszerErtesites = new RendszerErtesites();
