// A Model Manager core-hívásai (core/modell/api.py). Letöltés és mérés csak felhasználói kattintásra indul (D3).
import { kerdez } from '../core/api';
import type { Feladat } from '../vezerlo/tipusok';
import type { Halmazok, Modell, ModellLista, SajatOsszegzes, SajatTetel, TesztRiport, TorlesEredmeny } from './tipusok';

const q = encodeURIComponent;
const IDO = 15000;

export const modellApi = {
  lista: () => kerdez<ModellLista>('/api/modellek', { idokorlat: IDO }),
  egy: (id: string) => kerdez<Modell>(`/api/modellek/${q(id)}`, { idokorlat: IDO }),
  letoltes: (id: string) => kerdez<{ feladat: Feladat }>(`/api/modellek/${q(id)}/letoltes`, { metodus: 'POST', torzs: {}, idokorlat: IDO }),
  megszakit: (id: string) => kerdez<{ feladat: Feladat }>(`/api/modellek/${q(id)}/letoltes/megszakitas`, { metodus: 'POST', torzs: {}, idokorlat: IDO }),
  torol: (id: string) => kerdez<TorlesEredmeny>(`/api/modellek/${q(id)}/torles`, { metodus: 'POST', torzs: { megerosit: true }, idokorlat: 60000 }),
  teszt: (id: string, feladat: string, halmaz: 'szallitott' | 'sajat') =>
    kerdez<{ feladat: Feladat; elofeltetel: unknown[] }>(`/api/modellek/${q(id)}/teszt`, { metodus: 'POST', torzs: { feladat, halmaz }, idokorlat: IDO }),
  riport: (id: string, feladat: string) => kerdez<TesztRiport>(`/api/modellek/${q(id)}/teszt/${q(feladat)}`, { idokorlat: IDO }),
  halmazok: () => kerdez<Halmazok>('/api/modellek/halmazok', { idokorlat: IDO }),
  halmazLetrehoz: (feladat: string, tetelek: SajatTetel[], nyelv: string) =>
    kerdez<SajatOsszegzes>(`/api/modellek/halmazok/${q(feladat)}`, { metodus: 'POST', torzs: { tetelek, nyelv }, idokorlat: 60000 }),
  halmazJovahagy: (feladat: string, tartott: string[]) =>
    kerdez<SajatOsszegzes>(`/api/modellek/halmazok/${q(feladat)}/jovahagyas`, { metodus: 'POST', torzs: { tartott }, idokorlat: IDO }),
  halmazValaszt: (feladat: string, halmaz: 'sajat' | 'szallitott') =>
    kerdez<SajatOsszegzes>(`/api/modellek/halmazok/${q(feladat)}/valasztas`, { metodus: 'POST', torzs: { halmaz }, idokorlat: IDO }),
  halmazTorol: (feladat: string) =>
    kerdez<{ feladat: string; torolve: boolean }>(`/api/modellek/halmazok/${q(feladat)}/torles`, { metodus: 'POST', torzs: {}, idokorlat: IDO }),
};
