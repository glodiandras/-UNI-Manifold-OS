// Az ikonsáv (06-workspace-12) beállítása: melyik parancs-ikon látszik és milyen sorrendben. A parancs a regiszteré
// (`regiszter.kap(id)`): a tooltip és a gyorsbillentyű így együtt marad a billentyű-testreszabással; itt csak az azonosító,
// az ikon és az elrendezés tartozik. Tiszta függvények, a felület állapotát az `Ikonsav.svelte` és a `Felulet` kezeli.

import type { IconNode } from 'lucide';
import { ArrowLeftRight, CalendarCheck, Command, FilePlus, FileText, FolderOpen, LayoutDashboard, Network, PanelLeft, Search, Settings } from '../ikon/ikonok';

export interface IkonsavBeallitas {
  /** Hamis: az egész ikonsáv rejtett (a rács oszlopa 0 széles); a „Show ribbon” kapcsoló. */
  lathato: boolean;
  /** A rejtett ikonok parancs-azonosítói. */
  rejtett: string[];
  /** A teljes sorrend (felső és alsó csoport együtt); ami hiányzik, az alap helyén követi. */
  sorrend: string[];
}

export interface IkonsavDef {
  id: string;
  ikon: IconNode;
  csoport: 'felso' | 'also';
}

export const IKONSAV_ALAP: readonly IkonsavDef[] = [
  { id: 'hej.oldalsav', ikon: PanelLeft, csoport: 'felso' },
  { id: 'kereses.panel', ikon: Search, csoport: 'felso' },
  { id: 'hej.valto', ikon: ArrowLeftRight, csoport: 'felso' },
  { id: 'fa.uj-jegyzet', ikon: FilePlus, csoport: 'felso' },
  { id: 'sablon.uj-jegyzet', ikon: FileText, csoport: 'felso' },
  { id: 'graf.megnyit', ikon: Network, csoport: 'felso' },
  { id: 'naplo.napi', ikon: CalendarCheck, csoport: 'felso' },
  { id: 'hej.paletta', ikon: Command, csoport: 'felso' },
  { id: 'munkater.valto', ikon: FolderOpen, csoport: 'also' },
  { id: 'manifold.vezerlo', ikon: LayoutDashboard, csoport: 'also' },
  { id: 'beallitasok.megnyit', ikon: Settings, csoport: 'also' },
];

export const IKONSAV_ALAPERTEK: IkonsavBeallitas = { lathato: true, rejtett: [], sorrend: [] };

const ISMERT = new Set(IKONSAV_ALAP.map((d) => d.id));

/** A mentett érték ellenőrzése: csak ismert azonosító, ismétlés nélkül; hibás alakra az alapérték. */
export function ikonsavErvenyes(x: unknown): IkonsavBeallitas {
  if (!x || typeof x !== 'object') return { ...IKONSAV_ALAPERTEK, rejtett: [], sorrend: [] };
  const o = x as Record<string, unknown>;
  const lista = (v: unknown): string[] => (Array.isArray(v) ? [...new Set(v.filter((s): s is string => typeof s === 'string' && ISMERT.has(s)))] : []);
  return { lathato: typeof o.lathato === 'boolean' ? o.lathato : true, rejtett: lista(o.rejtett), sorrend: lista(o.sorrend) };
}

/** Az ikonok csoportonként, a mentett sorrendben (a hiányzók az alap sorrendjében a végén); a rejtettek nélkül. */
export function ikonsavElemek(b: IkonsavBeallitas, rejtettekIs = false): { felso: IkonsavDef[]; also: IkonsavDef[] } {
  const hely = new Map(b.sorrend.map((id, i) => [id, i]));
  const rendezett = (csoport: 'felso' | 'also') =>
    IKONSAV_ALAP.map((d, alapHely) => ({ d, alapHely }))
      .filter(({ d }) => d.csoport === csoport && (rejtettekIs || !b.rejtett.includes(d.id)))
      .sort((a, c) => (hely.get(a.d.id) ?? 1000 + a.alapHely) - (hely.get(c.d.id) ?? 1000 + c.alapHely))
      .map(({ d }) => d);
  return { felso: rendezett('felso'), also: rendezett('also') };
}

/** A teljes sorrend (rejtettekkel együtt) a mentéshez: a mai látható sorrend, benne az `id` a `delta` hellyel odébb a csoportján belül. */
export function ikonMozgat(b: IkonsavBeallitas, id: string, delta: -1 | 1): IkonsavBeallitas {
  const csoportok = ikonsavElemek(b, true);
  const def = IKONSAV_ALAP.find((d) => d.id === id);
  if (!def) return b;
  const lista = (def.csoport === 'felso' ? csoportok.felso : csoportok.also).map((d) => d.id);
  const i = lista.indexOf(id), j = i + delta;
  if (i < 0 || j < 0 || j >= lista.length) return b;
  [lista[i], lista[j]] = [lista[j], lista[i]];
  const masik = (def.csoport === 'felso' ? csoportok.also : csoportok.felso).map((d) => d.id);
  return { ...b, sorrend: def.csoport === 'felso' ? [...lista, ...masik] : [...masik, ...lista] };
}

/** Az `id` ikon a `cel` ikon helyére (húzással), azonos csoporton belül: lefelé húzva a cél után, felfelé előtte áll meg. */
export function ikonAthelyez(b: IkonsavBeallitas, id: string, cel: string): IkonsavBeallitas {
  const a = IKONSAV_ALAP.find((d) => d.id === id), c = IKONSAV_ALAP.find((d) => d.id === cel);
  if (!a || !c || a.csoport !== c.csoport || id === cel) return b;
  const csoportok = ikonsavElemek(b, true);
  const eredeti = (a.csoport === 'felso' ? csoportok.felso : csoportok.also).map((d) => d.id);
  const lefele = eredeti.indexOf(id) < eredeti.indexOf(cel);
  const lista = eredeti.filter((x) => x !== id);
  lista.splice(lista.indexOf(cel) + (lefele ? 1 : 0), 0, id);
  const masik = (a.csoport === 'felso' ? csoportok.also : csoportok.felso).map((d) => d.id);
  return { ...b, sorrend: a.csoport === 'felso' ? [...lista, ...masik] : [...masik, ...lista] };
}
