// A `vite.config.ts` build-pluginjének (a pdf.js adatfájljai, C16) két Node-hívása; a projektben nincs @types/node.
declare module 'node:fs' {
  export function readdirSync(ut: string): string[];
  export function readFileSync(ut: string): Uint8Array;
}
declare module 'node:child_process' {
  export function execFileSync(ut: string, args: string[], opciok: { encoding: 'utf8' }): string;
}
