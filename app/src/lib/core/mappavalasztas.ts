// A natív mappaválasztó (F8, import): a héj (`shell/Sources/MappaValaszto.swift`) `NSOpenPanel`-t mutat, és EGYETLEN abszolút
// útvonalat ad vissza. Böngészőben és régebbi héjjal nincs ilyen csatorna: ott az import képernyők beírható útvonalmezője marad.
//
// Biztonsági szerződés (a híd nem általános fájlolvasó):
//  - csak útvonal-szöveg jön vissza, tartalom soha; a héj semmit nem olvas a mappából;
//  - a panel csak felhasználói kattintásból nyílik: ha a böngészőmotor jelzi, hogy nincs friss felhasználói aktiváció
//    (`navigator.userActivation.isActive === false`), a kérés el sem megy, az eredmény `null`;
//  - egyszerre egy kérés élhet (a héj a másodikat is elutasítja);
//  - a visszaadott útvonalat a felület kizárólag az import-előnézethez adja a core-nak (az előnézet nem ír).

interface MappaHid {
  postMessage(adat: { tipus: 'mappa-valaszto'; cim?: string }): Promise<unknown>;
}

/** A héjnak adott panel-üzenet legnagyobb hossza (a héj ugyanennyire vág). */
export const MAPPA_CIM_MAX = 200;

function csatorna(): MappaHid | undefined {
  return (window as unknown as { webkit?: { messageHandlers?: { mappaValaszto?: MappaHid } } }).webkit?.messageHandlers?.mappaValaszto;
}

/** Van-e natív mappaválasztó (a Manifold.app új héja); böngészőben és régi héjjal nincs. */
export function mappaValasztoVan(): boolean {
  return typeof csatorna()?.postMessage === 'function';
}

let folyamatban = false;

/** A natív mappaválasztó megnyitása. → a választott abszolút útvonal, vagy `null` (megszakítás, nincs híd, nincs aktiváció, hiba). */
export async function mappaValasztas(cim?: string): Promise<string | null> {
  const ch = csatorna();
  if (!ch || typeof ch.postMessage !== 'function' || folyamatban) return null;
  if ((navigator as unknown as { userActivation?: { isActive?: boolean } }).userActivation?.isActive === false) return null;
  folyamatban = true;
  try {
    const kerelem: { tipus: 'mappa-valaszto'; cim?: string } = { tipus: 'mappa-valaszto' };
    if (typeof cim === 'string' && cim.trim()) kerelem.cim = cim.slice(0, MAPPA_CIM_MAX);
    const v = await ch.postMessage(kerelem);
    // csak nem üres, abszolút útvonal-szöveg fogadható el (a `~` a core-nál is csak a felhasználó saját kezű beírása)
    return typeof v === 'string' && v.startsWith('/') && !v.includes('\0') && v.length <= 4096 ? v : null;
  } catch {
    return null;
  } finally {
    folyamatban = false;
  }
}
