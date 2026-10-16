// F11: az aktív jegyzet és a kijelölés számai. A szerkesztő publikál, az állapotsor nem olvas DOM-szöveget.
import { SvelteMap } from 'svelte/reactivity';

export interface KijelolesTartomany { from: number; to: number }
export interface SzovegSzamok {
  ut: string;
  szavak: number;
  karakterek: number;
  osszesSzavak: number;
  osszesKarakterek: number;
  kijelolt: boolean;
}

const szoBonto = typeof Intl.Segmenter === 'function' ? new Intl.Segmenter(undefined, { granularity: 'word' }) : null;
const karakterBonto = typeof Intl.Segmenter === 'function' ? new Intl.Segmenter(undefined, { granularity: 'grapheme' }) : null;
export function szovegetSzamol(szoveg: string): { szavak: number; karakterek: number } {
  let szavak = 0, karakterek = 0;
  if (szoBonto) { for (const s of szoBonto.segment(szoveg)) if (s.isWordLike) szavak++; }
  else szavak = (szoveg.match(/[\p{L}\p{N}]+(?:['’][\p{L}\p{N}]+)*/gu) ?? []).length;
  if (karakterBonto) { for (const _ of karakterBonto.segment(szoveg)) karakterek++; }
  else karakterek = Array.from(szoveg).length;
  return { szavak, karakterek };
}

export class SzovegStatisztika {
  private adatok = new SvelteMap<string, SzovegSzamok>();
  private szovegek = new Map<string, string>();

  frissit(fulId: string, ut: string, szoveg: string, tartomanyok: readonly KijelolesTartomany[] = []): void {
    const regi = this.adatok.get(fulId);
    const osszes = regi?.ut === ut && this.szovegek.get(fulId) === szoveg
      ? { szavak: regi.osszesSzavak, karakterek: regi.osszesKarakterek } : szovegetSzamol(szoveg);
    const reszek: KijelolesTartomany[] = [];
    const ervenyes = tartomanyok.filter(r => Number.isFinite(r.from) && Number.isFinite(r.to)).map(r => ({ from: Math.max(0, Math.min(szoveg.length, Math.floor(Math.min(r.from, r.to)))), to: Math.max(0, Math.min(szoveg.length, Math.floor(Math.max(r.from, r.to)))) })).filter(r => r.to > r.from).sort((a, b) => a.from - b.from);
    for (const r of ervenyes) {
      const utolso = reszek[reszek.length - 1];
      if (utolso && r.from <= utolso.to) utolso.to = Math.max(utolso.to, r.to);
      else reszek.push({ ...r });
    }
    const kijelolt = reszek.length > 0;
    const szamok = kijelolt ? reszek.reduce((s, r) => {
      const resz = szovegetSzamol(szoveg.slice(r.from, r.to));
      return { szavak: s.szavak + resz.szavak, karakterek: s.karakterek + resz.karakterek };
    }, { szavak: 0, karakterek: 0 }) : osszes;
    this.szovegek.set(fulId, szoveg);
    this.adatok.set(fulId, { ut, ...szamok, osszesSzavak: osszes.szavak, osszesKarakterek: osszes.karakterek, kijelolt });
  }

  olvas(fulId: string | undefined, ut: string | null | undefined): SzovegSzamok | undefined {
    const adat = fulId ? this.adatok.get(fulId) : undefined;
    return adat?.ut === ut ? adat : undefined;
  }

  torol(fulId: string): void { this.adatok.delete(fulId); this.szovegek.delete(fulId); }
}

export const statisztika = new SzovegStatisztika();
