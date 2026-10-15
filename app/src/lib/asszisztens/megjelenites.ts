// Az Asszisztens megjelenítési segédei (C30a): magyar feliratok, arány és küszöb szövege, idő.

import type { HigieniaFajta, Kuszob, StatisztikaFajta } from './tipusok';

export const FAJTA_CIM: Record<HigieniaFajta, string> = {
  torott_link: 'Törött link',
  tobbertelmu_link: 'Többértelmű link',
  arva_jegyzet: 'Árva jegyzet',
  hibas_keplet: 'Hibás képlet',
  hibas_frontmatter: 'Hibás tulajdonság',
  sema_sertes: 'Séma-sértés',
  hianyzo_forrashorgony: 'Hiányzó forráshorgony',
  hianyzo_media: 'Hiányzó média',
};

export const STATISZTIKA_CIM: Record<StatisztikaFajta, string> = {
  emlites: 'Linkjavaslat',
  szokas: 'Szokás-javaslat',
  higienia: 'Higiénia',
};

export function fajtaCim(fajta: string): string {
  return (FAJTA_CIM as Record<string, string>)[fajta] ?? fajta;
}

export function aranySzoveg(arany: number | null): string {
  return arany === null ? '—' : `${Math.round(arany * 100)}%`;
}

export function kuszobSzoveg(k: Kuszob): string {
  if (k.szint === 'nema') return 'néma (nem javasol)';
  if (k.szint === 'szigoru') return `szigorúbb (×${String(k.szorzo ?? 1).replace('.', ',')})`;
  return 'alap';
}

/** A riport elkészültének ideje magyarul, rövid alakban; érvénytelen vagy hiányzó érték: üres szöveg. */
export function szamolvaSzoveg(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return new Intl.DateTimeFormat('hu', { dateStyle: 'medium', timeStyle: 'short' }).format(d);
}

// ---------------------------------------------------------------- J1: a „Mit tanult az asszisztens” lista

const HELYZET_RESZ: Record<string, string> = {
  folytat: 'folytatás', kifejt: 'kifejtés', osszefoglal: 'összefoglalás', szoveg: 'szövegben',
  szunet: 'gépelési szünetben', megnyitas: 'megnyitáskor', rovid: 'rövid jegyzet', kozepes: 'közepes jegyzet', hosszu: 'hosszú jegyzet',
};

/** A hangolás helyzet-kódja magyarul (`szunet_rovid` → „gépelési szünetben, rövid jegyzet”). */
export function helyzetSzoveg(h: string): string {
  return h.split('_').map((r) => HELYZET_RESZ[r] ?? r).join(', ');
}

const HANGOLAS: Record<string, string> = { batrabb: 'gyakrabban javasol', alap: 'alap gyakoriság', ritkabb: 'ritkábban javasol', nema: 'néma (nem javasol)' };

export function hangolasSzoveg(szint: string): string {
  return HANGOLAS[szint] ?? szint;
}
