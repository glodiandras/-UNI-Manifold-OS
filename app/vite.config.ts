import { readdirSync, readFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import type { Plugin } from 'vite';
import { defineConfig } from 'vitest/config';

declare const process: { env: Record<string, string | undefined> };

const PERF = process.env.MOS_TELJESITMENY === '1';

// A build azonosítója egy forrásból, buildenként (a `--watch` minden újrafordításánál is) újraszámolva: a `dist/epites.json`
// (a core ehhez méri a dist frissességét) és a lap `<meta name="manifold-epites">` címkéje (a futó lap ebből tudja, melyik
// buildből való; `lib/core/epites.ts`) ugyanazt az értéket kapja. (Korábban a `define` a konfig betöltésekor számolódott, az
// `epites.json` minden bundle-nél: watch módban az első újrafordítástól a futó lap „elavult” volt.)
function epitesAzonosito(): Plugin {
  let epites = '{}';
  return {
    name: 'manifold-epites',
    apply: 'build',
    buildStart() {
      epites = execFileSync('../bin/mos', ['epites'], { encoding: 'utf8' });
    },
    transformIndexHtml() {
      const felulet = String((JSON.parse(epites) as { felulet?: string }).felulet ?? '');
      return [{ tag: 'meta', attrs: { name: 'manifold-epites', content: felulet }, injectTo: 'head' }];
    },
    generateBundle() {
      this.emitFile({ type: 'asset', fileName: 'epites.json', source: epites });
    },
  };
}

// A pdf.js futásidejű adatai (C16) fix úton a `dist/pdfjs/` alá: a worker a CMap-et, a standard fontot és a
// JPX/JBIG2 dekódoló JS-tartalékát (`*_nowasm_fallback.js`, dinamikus import) név szerint kéri, hashelt név nem jó.
// A wasm nem kerül be (`useWasm: false`, a CSP-ben nincs `wasm-unsafe-eval`).
function pdfjsAdatok(): Plugin {
  const forras = 'node_modules/pdfjs-dist';
  const mappak: [string, (n: string) => boolean][] = [
    ['cmaps', (n) => n.endsWith('.bcmap') || n === 'LICENSE'],
    ['standard_fonts', () => true],
    ['wasm', (n) => n.endsWith('_nowasm_fallback.js') || n.startsWith('LICENSE')],
  ];
  return {
    name: 'manifold-pdfjs-adatok',
    apply: 'build',
    generateBundle() {
      for (const [mappa, kell] of mappak)
        for (const nev of readdirSync(`${forras}/${mappa}`).filter(kell))
          this.emitFile({ type: 'asset', fileName: `pdfjs/${mappa}/${nev}`, source: readFileSync(`${forras}/${mappa}/${nev}`) });
    },
  };
}

// A build egy statikus csomag (app/dist), a core szolgálja ki ugyanazon az originen. Külső URL nincs benne (D3).
export default defineConfig({
  plugins: [svelte(), pdfjsAdatok(), epitesAzonosito()],
  base: '/',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    assetsInlineLimit: 0,
    sourcemap: false,
    reportCompressedSize: false,
  },
  resolve: process.env.VITEST ? { conditions: ['browser'] } : undefined,
  // a tesztek a repó más mappáiból (docs/, modulok/: a közös Python ↔ TypeScript vektorok) is olvasnak `?raw`-val
  server: process.env.VITEST ? { fs: { allow: ['..'] } } : undefined,
  // `MOS_TELJESITMENY=1` (a `bin/mos perf`): a falióra-alapú perf-készlet (tests/perf/*.perf.ts, T008) fut, egymás után, Node-ban;
  // különben az alap készlet (tests/**/*.test.ts), amelyben abszolút ms-kapu nincs (csak arány)
  test: PERF
    ? { environment: 'node', include: ['tests/perf/**/*.perf.ts'], fileParallelism: false }
    : {
        environment: 'jsdom',
        include: ['tests/**/*.test.ts'],
        setupFiles: ['tests/beallitas.ts'],
        restoreMocks: true,
        css: { include: [/tokens\.css/] },
      },
});
