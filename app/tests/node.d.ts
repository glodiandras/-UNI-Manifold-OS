// A kézi (`tests/kezi/*.kezi.ts`) próbák Node-API-jai, a @types/node helyett (a csomag nincs a
// lockfájlban, D3): csak amit a próbák használnak.

declare module 'node:fs' {
  interface Dirent {
    name: string;
    isDirectory(): boolean;
    isFile(): boolean;
  }
  export function readdirSync(ut: string, o: { withFileTypes: true }): Dirent[];
  export function readFileSync(ut: string): Uint8Array;
  export function readFileSync(ut: string, kodolas: 'utf8'): string;
  export function writeFileSync(ut: string, adat: string | Uint8Array): void;
  export function existsSync(ut: string): boolean;
  export function mkdirSync(ut: string, o?: { recursive?: boolean }): void;
}

declare module 'node:path' {
  export function join(...reszek: string[]): string;
  export function relative(tol: string, ig: string): string;
}

declare const process: { env: Record<string, string | undefined> };
