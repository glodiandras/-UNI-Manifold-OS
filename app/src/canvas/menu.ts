// A canvas helyi menüi (09-canvas-04): üres vászon, kártya és él. Mindhárom ugyanazokat a műveleteket hívja, mint az eszköztár és
// a gyorsbillentyűk (a menü csak elérés; semmi nem csak itt él), és billentyűzetről is nyitható (⇧F10 vagy a menü-billentyű).
// A felépítés tiszta függvény: a menüelemek és az `id → művelet` térkép; a megjelenítés a közös lebegő menüé.

import { t } from '../lib/i18n';
import {
  ClipboardPaste,
  Copy,
  CopyPlus,
  ExternalLink,
  FileOutput,
  FilePlus,
  Focus,
  Grid3x3,
  Hash,
  Link,
  Magnet,
  Maximize,
  Palette,
  Pencil,
  Scissors,
  SquareDashed,
  Trash2,
  Type,
} from '../lib/ikon/ikonok';
import type { MenuElem } from '../szerkeszto/notion/menu';
import { SZIN_NEV, type Oldal } from './modell';
import type { ElIrany } from './muveletek';

export interface MenuAkciok {
  ujSzoveg(): void;
  ujFajl(): void;
  ujLink(): void;
  ujCsoport(): void;
  beilleszt(): void;
  mindKijelol(): void;
  mindentMutat(): void;
  racsKapcsol(): void;
  objektumKapcsol(): void;
  szerkeszt(): void;
  megnyit(ujFulben: boolean): void;
  jegyzette(): void;
  alcel(): void;
  szin(kod: string | null): void;
  masol(): void;
  kivag(): void;
  duplikal(): void;
  csoportKore(): void;
  kijelolesMutat(): void;
  torol(): void;
  cimke(): void;
  irany(i: ElIrany): void;
  oldal(veg: 'from' | 'to', o: Oldal): void;
  ujracsatol(veg: 'from' | 'to'): void;
}

export interface MenuAllapot {
  irhato: boolean;
  racs: boolean;
  objektum: boolean;
  /** kártya-menü: a kártya típusa és mit lehet vele */
  kartya?: { tipus: string; fajlTipus: string | null; nyithato: boolean; szerkesztheto: boolean; db: number };
}

const ELEM = (id: string, nev: string, o: Partial<MenuElem> = {}): MenuElem => ({ id, nev, ...o });

class Epito {
  readonly elemek: MenuElem[] = [];
  readonly akciok = new Map<string, () => void>();

  add(id: string, nev: string, f: () => void, o: Partial<MenuElem> = {}): this {
    this.elemek.push(ELEM(id, nev, o));
    this.akciok.set(id, f);
    return this;
  }

  /** Almenü: az elemei ugyanebbe az akció-térképbe kerülnek. */
  alm(id: string, nev: string, gyerekek: { id: string; nev: string; f: () => void; kijelolt?: boolean }[], o: Partial<MenuElem> = {}): this {
    for (const g of gyerekek) this.akciok.set(g.id, g.f);
    this.elemek.push(ELEM(id, nev, { ...o, almenu: () => gyerekek.map((g) => ELEM(g.id, g.nev, { kijelolt: g.kijelolt })) }));
    return this;
  }
}

const SZINEK = (a: MenuAkciok, utpotag: string) => [
  { id: `${utpotag}-nincs`, nev: t('No colour'), f: () => a.szin(null) },
  ...Object.entries(SZIN_NEV).map(([kod, nev]) => ({ id: `${utpotag}-${kod}`, nev: t(nev), f: () => a.szin(kod) })),
];

const OLDALAK: { o: Oldal; nev: string }[] = [
  { o: 'top', nev: t('Top') },
  { o: 'right', nev: t('Right') },
  { o: 'bottom', nev: t('Bottom') },
  { o: 'left', nev: t('Left') },
];

export function vaszonMenu(a: MenuAkciok, s: MenuAllapot): { elemek: MenuElem[]; akciok: Map<string, () => void> } {
  const e = new Epito();
  const i = s.irhato;
  e.add('uj-szoveg', t('New text card here'), a.ujSzoveg, { ikon: Type, letiltva: !i });
  e.add('uj-fajl', t('Add note or file here…'), a.ujFajl, { ikon: FilePlus, letiltva: !i });
  e.add('uj-link', t('New web link card here'), a.ujLink, { ikon: Link, letiltva: !i });
  e.add('uj-csoport', t('New group'), a.ujCsoport, { ikon: SquareDashed, letiltva: !i });
  e.add('beilleszt', t('Paste'), a.beilleszt, { ikon: ClipboardPaste, letiltva: !i, jelzo: '⌘V' });
  e.add('mind', t('Select all'), a.mindKijelol, { jelzo: '⌘A' });
  e.add('mutat', t('Zoom to fit'), a.mindentMutat, { ikon: Maximize, jelzo: '⇧1' });
  e.add('racs', t('Snap to grid'), a.racsKapcsol, { ikon: Grid3x3, kijelolt: s.racs });
  e.add('objektum', t('Snap to other cards'), a.objektumKapcsol, { ikon: Magnet, kijelolt: s.objektum });
  return e;
}

export function kartyaMenu(a: MenuAkciok, s: MenuAllapot): { elemek: MenuElem[]; akciok: Map<string, () => void> } {
  const e = new Epito();
  const i = s.irhato;
  const k = s.kartya!;
  if (k.szerkesztheto) e.add('szerkeszt', k.tipus === 'file' ? t('Edit note in the card') : t('Edit'), a.szerkeszt, { ikon: Pencil, letiltva: !i, jelzo: '↩' });
  if (k.nyithato) {
    e.add('megnyit', t('Open'), () => a.megnyit(false), { ikon: ExternalLink });
    if (k.tipus === 'file') e.add('megnyit-uj', t('Open in new tab'), () => a.megnyit(true), { ikon: ExternalLink, jelzo: '⌘↩' });
  }
  if (k.db === 1 && k.tipus === 'text') e.add('jegyzette', t('Convert to note…'), a.jegyzette, { ikon: FileOutput, letiltva: !i });
  if (k.db === 1 && k.tipus === 'file' && (k.fajlTipus === 'md' || k.fajlTipus === 'pdf' || k.fajlTipus === 'base'))
    e.add(
      'alcel',
      k.fajlTipus === 'md' ? t('Choose heading or block…') : k.fajlTipus === 'pdf' ? t('Choose page…') : t('Choose view…'),
      a.alcel,
      { ikon: Hash, letiltva: !i },
    );
  e.alm('szin', t('Colour'), SZINEK(a, 'kszin'), { ikon: Palette, letiltva: !i });
  e.add('masol', t('Copy'), a.masol, { ikon: Copy, jelzo: '⌘C' });
  e.add('kivag', t('Cut'), a.kivag, { ikon: Scissors, letiltva: !i, jelzo: '⌘X' });
  e.add('duplikal', t('Duplicate'), a.duplikal, { ikon: CopyPlus, letiltva: !i, jelzo: '⌘D' });
  e.add('csoport', t('Group around selection'), a.csoportKore, { ikon: SquareDashed, letiltva: !i });
  e.add('mutat', t('Zoom to selection'), a.kijelolesMutat, { ikon: Focus, jelzo: '⇧2' });
  e.add('torol', t('Delete'), a.torol, { ikon: Trash2, veszely: true, letiltva: !i, jelzo: '⌫' });
  return e;
}

export function elMenu(a: MenuAkciok, s: MenuAllapot): { elemek: MenuElem[]; akciok: Map<string, () => void> } {
  const e = new Epito();
  const i = s.irhato;
  e.add('cimke', t('Edit label'), a.cimke, { ikon: Pencil, letiltva: !i, jelzo: '↩' });
  e.alm(
    'irany',
    t('Direction'),
    [
      { id: 'irany-elore', nev: t('One way (→)'), f: () => a.irany('elore') },
      { id: 'irany-vissza', nev: t('One way, reversed (←)'), f: () => a.irany('vissza') },
      { id: 'irany-mindketto', nev: t('Both ways (↔)'), f: () => a.irany('mindketto') },
      { id: 'irany-nincs', nev: t('No arrow (—)'), f: () => a.irany('nincs') },
    ],
    { letiltva: !i },
  );
  e.alm('szin', t('Colour'), SZINEK(a, 'eszin'), { ikon: Palette, letiltva: !i });
  e.alm('kezd-oldal', t('Start side'), OLDALAK.map((o) => ({ id: `kezd-${o.o}`, nev: o.nev, f: () => a.oldal('from', o.o) })), { letiltva: !i });
  e.alm('veg-oldal', t('End side'), OLDALAK.map((o) => ({ id: `veg-${o.o}`, nev: o.nev, f: () => a.oldal('to', o.o) })), { letiltva: !i });
  e.add('ujracsatol-kezd', t('Reconnect start to another card…'), () => a.ujracsatol('from'), { letiltva: !i });
  e.add('ujracsatol-veg', t('Reconnect end to another card…'), () => a.ujracsatol('to'), { letiltva: !i });
  e.add('masol', t('Copy'), a.masol, { ikon: Copy, jelzo: '⌘C' });
  e.add('kivag', t('Cut'), a.kivag, { ikon: Scissors, letiltva: !i, jelzo: '⌘X' });
  e.add('mutat', t('Zoom to selection'), a.kijelolesMutat, { ikon: Focus, jelzo: '⇧2' });
  e.add('torol', t('Delete'), a.torol, { ikon: Trash2, veszely: true, letiltva: !i, jelzo: '⌫' });
  return e;
}
