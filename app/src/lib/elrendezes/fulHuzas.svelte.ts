// Fül húzása panel-szélre (06-workspace-02): a húzás állapota és a zóna számítása. A húzás közben a `dataTransfer` tartalma
// nem olvasható, ezért a fül azonosítója itt él; a tiszta `huzasZona` a pointer helyéből dönti el, merre osszon a drop.

export const HUZAS_TIPUS = 'application/x-manifold-ful';

export type HuzasZona = 'bal' | 'jobb' | 'fel' | 'le' | 'kozep';

/** A fülhúzás közös állapota: a panelek ebből tudják, hogy mutassák-e a szélzónákat. */
export const fulHuzas = $state<{ fulId: string | null }>({ fulId: null });

/** A zóna a panel téglalapján belüli helyből: a szélső 25 % (legfeljebb 96 px) a négy irány, a közép a „fülcsoportba” ejtés.
 *  A sarokban az számít, amelyik szélhez a pont (aránylag) közelebb van. */
export function huzasZona(x: number, y: number, szelesseg: number, magassag: number): HuzasZona {
  if (szelesseg <= 0 || magassag <= 0) return 'kozep';
  const sav = (meret: number) => Math.min(meret * 0.25, 96);
  const bal = x / sav(szelesseg), jobb = (szelesseg - x) / sav(szelesseg);
  const fel = y / sav(magassag), le = (magassag - y) / sav(magassag);
  const legkisebb = Math.min(bal, jobb, fel, le);
  if (legkisebb >= 1) return 'kozep';
  return legkisebb === bal ? 'bal' : legkisebb === jobb ? 'jobb' : legkisebb === fel ? 'fel' : 'le';
}

/** A kapcsolt panelek görgetés-szinkronjának közös, nem reaktív visszhang-gátja (ms időbélyeg). */
export const szinkronAllapot = { ido: 0 };
