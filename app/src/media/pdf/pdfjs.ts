// A pdf.js lusta betöltése (C16): a ~1 MB-os könyvtár és a nézője csak az első PDF megnyitásakor töltődik.
// Egy közös worker (module worker, `'self'`) szolgál ki minden dokumentumot. A futásidejű adatok (CMap, standard
// font, a JPX/JBIG2 JS-tartalék) a `dist/pdfjs/` alól jönnek (a `vite.config.ts` pluginje másolja); wasm nincs,
// eval nincs, script nincs → a CSP változatlan. Hálózat nincs: minden ugyanarról az originről.

import type * as PdfLib from 'pdfjs-dist';
import type * as PdfViewer from 'pdfjs-dist/web/pdf_viewer.mjs';
import { lustaImportHiba } from '../../lib/vezerlo/epites.svelte';

export type PdfjsLib = typeof PdfLib;
export type PdfjsViewer = typeof PdfViewer;

export interface Pdfjs {
  lib: PdfjsLib;
  viewer: PdfjsViewer;
}

export const ADAT_URL = '/pdfjs/';

/** A dokumentum betöltési beállításai: a nagy tankönyv (akár 325 MB) csak a kért lapok bájtjait kéri (Range). */
export const BETOLTES = {
  cMapUrl: `${ADAT_URL}cmaps/`,
  cMapPacked: true,
  standardFontDataUrl: `${ADAT_URL}standard_fonts/`,
  wasmUrl: `${ADAT_URL}wasm/`,
  useWasm: false,
  useWorkerFetch: true,
  enableXfa: false,
  disableAutoFetch: true,
  disableStream: true,
  rangeChunkSize: 262144,
  stopAtErrors: false,
} as const;

let betolto: Promise<Pdfjs> | null = null;

export function pdfjs(): Promise<Pdfjs> {
  betolto ??= (async () => {
    const lib = await import('pdfjs-dist');
    const { default: workerUrl } = await import('pdfjs-dist/build/pdf.worker.min.mjs?url');
    lib.GlobalWorkerOptions.workerSrc = workerUrl;
    // a néző a könyvtárat a `globalThis.pdfjsLib`-ből veszi
    (globalThis as unknown as { pdfjsLib: PdfjsLib }).pdfjsLib = lib;
    const viewer = await import('pdfjs-dist/web/pdf_viewer.mjs');
    await import('pdfjs-dist/web/pdf_viewer.css');
    return { lib, viewer };
  })();
  betolto.catch(() => {
    betolto = null;
    lustaImportHiba(); // ha a dist közben újrafordult, a chunk eltűnt: újratöltés kell
  });
  return betolto;
}
