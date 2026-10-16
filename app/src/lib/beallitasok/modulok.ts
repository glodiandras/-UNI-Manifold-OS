import { modulEngedelyezett } from './allapot.svelte';
import { MODULOK, type ModulId } from './tipusok';

const KULON: Record<string, ModulId> = {
  'hej.valto': 'gyorsvalto', 'kereses.kerdezz': 'kerdezz', 'naplo.napi': 'napi',
  'manifold.statisztika': 'tracker', 'manifold.hasznalat': 'tracker',
};
const ELONEVEK: Record<string, ModulId> = { sablon: 'sablonok', dolgozat: 'felkeszultseg', ma: 'napi', pdf: 'pdf',
  visszahivatkozasok: 'hivatkozasok', kimeno: 'hivatkozasok', emlites: 'hivatkozasok',
};
export function parancsModul(id: string): ModulId | undefined {
  if (KULON[id]) return KULON[id];
  if (/^manifold\.(asszisztens|tracker)-(be|ki)$/.test(id)) return id.includes('asszisztens') ? 'asszisztens' : 'tracker';
  const elso = id.split('.')[0];
  return ELONEVEK[elso] ?? (MODULOK.includes(elso as ModulId) ? elso as ModulId : undefined);
}
export function parancsEngedelyezett(id: string): boolean {
  const modul = parancsModul(id);
  return modul ? modulEngedelyezett(modul) : true;
}
export function nezetEngedelyezett(id: string): boolean {
  if (id === 'media.pdf') return modulEngedelyezett('pdf');
  if (id === 'media.lejatszo') return modulEngedelyezett('media');
  return parancsEngedelyezett(id);
}
