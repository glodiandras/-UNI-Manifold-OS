// A mappaválasztó, amelyet az import képernyők kapnak, ha a hívó nem ad sajátot: a héj natív ablaka (`window.manifold.mappaValasztas`).
// Böngészőben és régebbi héjjal `undefined`: a képernyő csak a beírható útvonalmezőt mutatja (nincs „Choose folder” gomb).
import { mappaValasztas, mappaValasztoVan } from '../core/mappavalasztas';

export type MappaValaszto = (cim: string) => Promise<string | null>;

export function alapValaszto(): MappaValaszto | undefined {
  if (!mappaValasztoVan()) return undefined;
  return (cim) => {
    const hid = (window as unknown as { manifold?: { mappaValasztas?: (cim?: string) => Promise<string | null> } }).manifold?.mappaValasztas;
    return typeof hid === 'function' ? hid(cim) : mappaValasztas(cim);
  };
}
