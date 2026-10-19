import { kerdez } from '../lib/core/api';

export interface MostSzoveg { szoveg: string; formatum: string; ismeretlen: string[] }

/** A dátumformátum egyetlen forrása a core; a felület nem tart második Moment-formázót. */
export function mostSzoveg(fajta: 'date' | 'time', formatum?: string): Promise<MostSzoveg> {
  return kerdez('/api/sablon/most', { metodus: 'POST', torzs: { fajta, ...(formatum === undefined ? {} : { formatum }) }, idokorlat: 10000 });
}
