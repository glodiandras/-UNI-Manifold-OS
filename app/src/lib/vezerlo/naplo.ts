// A feladat naplójának követése a részlet-nézetben (C17): a 2 s-os lekérdezés, az állapot-effekt és a mount ugyanazt a
// frissítést kéri — egyszerre egy kérés megy, a közben jött kérés egy ismétlésbe olvad; az elavult `tol`-ra jött válasz
// eldobódik (különben a sorok duplázódnának), és a megtartott sorok száma plafonos.

/** Ennyi naplósor marad a nézetben; a régebbiek levágódnak (a teljes napló a core-ban marad). */
export const MAX_NAPLO_SOR = 5000;

export interface NaploAllapot {
  sorok: string[];
  /** A következő lekérés kezdősora (a core `osszes_sor`-a). */
  tol: number;
  /** Ennyi korábbi sor nem látszik a plafon miatt. */
  levagva: number;
}

/**
 * Az új sorok hozzáfűzése. → `null`, ha a válasz elavult (nem a mostani `tol`-ra kérték), vagy nincs új sor.
 */
export function naploHozzafuz(
  a: NaploAllapot,
  kertTol: number,
  valasz: { sorok: string[]; osszes_sor: number },
  max = MAX_NAPLO_SOR,
): NaploAllapot | null {
  if (kertTol !== a.tol || !valasz.sorok.length) return null;
  const osszes = [...a.sorok, ...valasz.sorok];
  const le = Math.max(0, osszes.length - max);
  return { sorok: le ? osszes.slice(le) : osszes, tol: valasz.osszes_sor, levagva: a.levagva + le };
}

/** Egyszerre egy futás: a futás közbeni hívás nem indít párhuzamos kérést, hanem a futás után egyszer megismétli. */
export function egyszerre(f: () => Promise<void>): () => Promise<void> {
  let folyik: Promise<void> | null = null;
  let ujra = false;
  const indit = (): Promise<void> => {
    if (folyik) {
      ujra = true;
      return folyik;
    }
    folyik = (async () => {
      try {
        do {
          ujra = false;
          await f();
        } while (ujra);
      } finally {
        folyik = null;
      }
    })();
    return folyik;
  };
  return indit;
}
