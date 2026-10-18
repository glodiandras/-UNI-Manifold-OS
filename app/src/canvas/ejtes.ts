// Ejtés a vászonra (09-canvas-02): a fájlfából húzott jegyzetek és fájlok, a Finderből húzott fájlok és a böngészőből húzott
// URL kártyává válnak. Itt csak a besorolás él (tiszta függvény); a kártyák létrehozása és az importálás a nézeté. Az ejtett
// tartalom nem megbízható adat: a vault-útból csak az kerül kártyára, ami a fájllistában van, az URL-ből csak a
// `kulsoCim` által elfogadott `http`/`https` cím (D3: hálózati kérés nincs, a link-kártya csak címet mutat).

import { VAULT_HUZAS } from '../szerkeszto/csatolmany';
import { kulsoCim } from '../szerkeszto/linkek/kulso';

export interface EjtesTartalom {
  /** vault-útak (a fájlfából): már a vaultban lévő fájlok */
  utak: string[];
  /** külső fájlok (Finder): importálás után lesznek kártyák */
  fajlok: File[];
  /** a böngészőből húzott URL */
  url: string | null;
}

export type EjtesAdat = Pick<DataTransfer, 'getData' | 'files' | 'types'>;

/** Van-e az ejtésben olyan, amit a vászon kezel (a `dragover` ebből dönt, hogy az ejtés megengedett-e). */
export function ejtesKezelheto(dt: Pick<DataTransfer, 'types'> | null): boolean {
  const t = Array.from(dt?.types ?? []);
  return t.includes('Files') || t.includes(VAULT_HUZAS) || t.includes('text/uri-list') || t.includes('text/plain');
}

const URL_SOR = /^(?:https?:\/\/|www\.)\S+$/i;

/** Az ejtés tartalma: fájlok → fájlfa-húzás → szövegben álló vault-utak → URL. Ismeretlen útból nem lesz kártya. */
export function ejtesOsztalyoz(dt: EjtesAdat, letezik: (ut: string, fajlfabol: boolean) => boolean): EjtesTartalom {
  const fajlok = Array.from(dt.files ?? []);
  if (fajlok.length) return { utak: [], fajlok, url: null };
  const belso = dt.getData(VAULT_HUZAS);
  if (belso && letezik(belso, true)) return { utak: [belso], fajlok: [], url: null };
  const sima = dt.getData('text/plain') ?? '';
  const sorok = sima.split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
  // a fájlfa több elem húzásakor a `text/plain` az utakat sorolja (a mappák nem fájlok: kimaradnak)
  if (sorok.length && sorok.every((u) => letezik(u, false))) return { utak: [...new Set(sorok)], fajlok: [], url: null };
  const lista = (dt.getData('text/uri-list') ?? '').split(/\r?\n/).map((s) => s.trim()).find((s) => s && !s.startsWith('#'));
  const jelolt = lista ?? (sorok.length === 1 && URL_SOR.test(sorok[0]) ? sorok[0] : null);
  const cim = jelolt ? kulsoCim(jelolt) : null;
  return { utak: [], fajlok: [], url: cim && /^https?:/i.test(cim) ? cim : null };
}

export const ures = (e: EjtesTartalom): boolean => !e.utak.length && !e.fajlok.length && !e.url;
