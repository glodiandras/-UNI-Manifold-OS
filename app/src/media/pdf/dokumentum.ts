// A megnyitott PDF-ek közös gyorsítótára (C16): egy fájl egyszer töltődik, akárhány fül és beágyazás mutatja.
// Hivatkozásszámlálás: az utolsó elengedés után 30 s-ig még él (fülváltás, újrarajzolt beágyazás), utána a
// dokumentum és a lapjainak gyorsítótára felszabadul. A fájl változásakor (`vault_valtozas`) a régi bejegyzés
// érvénytelen: a következő kérés újratölt.

import type { PDFDocumentLoadingTask, PDFDocumentProxy } from 'pdfjs-dist';
import { linkek } from '../../lib/vault/linkek.svelte';
import { BETOLTES, pdfjs } from './pdfjs';

const ELENGEDES_MS = 30_000;

interface Bejegyzes {
  igeret: Promise<PDFDocumentProxy>;
  feladat: Promise<PDFDocumentLoadingTask>;
  hivatkozas: number;
  idozito: ReturnType<typeof setTimeout> | null;
  ervenytelen: boolean;
}

export interface PdfHivatkozas {
  dok: PDFDocumentProxy;
  elenged(): void;
}

const tar = new Map<string, Bejegyzes>();

async function feladat(ut: string): Promise<PDFDocumentLoadingTask> {
  const { lib } = await pdfjs();
  const url = await linkek.mediaUrl(ut);
  return lib.getDocument({ url, ...BETOLTES });
}

function felszabadit(ut: string, b: Bejegyzes): void {
  if (tar.get(ut) === b) tar.delete(ut);
  void b.feladat.then((f) => f.destroy()).catch(() => {});
}

/** A dokumentum (és az elengedő függvény); a hívó minden sikeres `nyit` után pontosan egyszer enged el. */
export async function nyit(ut: string): Promise<PdfHivatkozas> {
  let b = tar.get(ut);
  if (!b || b.ervenytelen) {
    const f = feladat(ut);
    b = { igeret: f.then((x) => x.promise), feladat: f, hivatkozas: 0, idozito: null, ervenytelen: false };
    const sajat = b;
    tar.set(ut, b);
    b.igeret.catch(() => {
      if (tar.get(ut) === sajat) tar.delete(ut);
    });
  }
  const bej = b;
  bej.hivatkozas++;
  if (bej.idozito) {
    clearTimeout(bej.idozito);
    bej.idozito = null;
  }
  let dok: PDFDocumentProxy;
  try {
    dok = await bej.igeret;
  } catch (e) {
    bej.hivatkozas--;
    throw e;
  }
  let elengedve = false;
  return {
    dok,
    elenged() {
      if (elengedve) return;
      elengedve = true;
      if (--bej.hivatkozas > 0) return;
      if (bej.ervenytelen) return felszabadit(ut, bej);
      bej.idozito = setTimeout(() => {
        if (bej.hivatkozas === 0) felszabadit(ut, bej);
      }, ELENGEDES_MS);
    },
  };
}

/** A fájl megváltozott vagy eltűnt: a következő `nyit` újratölt; a most nyitott nézetek a régit mutatják tovább. */
export function ervenytelenit(ut: string): void {
  const b = tar.get(ut);
  if (!b) return;
  b.ervenytelen = true;
  tar.delete(ut);
  if (b.hivatkozas === 0) felszabadit(ut, b);
}

/** Tesztekhez és a leállításhoz. */
export function mindetElenged(): void {
  for (const [ut, b] of [...tar]) {
    if (b.idozito) clearTimeout(b.idozito);
    felszabadit(ut, b);
  }
}
