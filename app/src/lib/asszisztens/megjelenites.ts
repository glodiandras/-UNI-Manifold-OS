// Az Asszisztens megjelenítési segédei (C30a): magyar feliratok, arány és küszöb szövege, idő.

import { t, tk, locale } from '../i18n';

import type { HigieniaFajta, Kuszob, StatisztikaFajta } from './tipusok';

export const FAJTA_CIM: Record<HigieniaFajta, string> = {
  get torott_link() { return t('Törött link'); },
  get tobbertelmu_link() { return t('Többértelmű link'); },
  get arva_jegyzet() { return t('Árva jegyzet'); },
  get hibas_keplet() { return t('Hibás képlet'); },
  get hibas_frontmatter() { return t('Hibás tulajdonság'); },
  get sema_sertes() { return t('Séma-sértés'); },
  get hianyzo_forrashorgony() { return t('Hiányzó forráshorgony'); },
  get hianyzo_media() { return t('Hiányzó média'); },
};

export const STATISZTIKA_CIM: Record<StatisztikaFajta, string> = {
  get emlites() { return t('Linkjavaslat'); },
  get szokas() { return t('Szokás-javaslat'); },
  get higienia() { return t('Higiénia'); },
};

export function fajtaCim(fajta: string): string {
  return (FAJTA_CIM as Record<string, string>)[fajta] ?? fajta;
}

export function aranySzoveg(arany: number | null): string {
  return arany === null ? '—' : `${Math.round(arany * 100)}%`;
}

export function kuszobSzoveg(k: Kuszob): string {
  if (k.szint === 'nema') return t('néma (nem javasol)');
  if (k.szint === 'szigoru') return t('szigorúbb (×{szorzo})', { szorzo: String(k.szorzo ?? 1).replace('.', locale() === 'hu-HU' ? ',' : '.') });
  return t('alap');
}

/** A riport elkészültének ideje magyarul, rövid alakban; érvénytelen vagy hiányzó érték: üres szöveg. */
export function szamolvaSzoveg(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return new Intl.DateTimeFormat(locale(), { dateStyle: 'medium', timeStyle: 'short' }).format(d);
}

// ---------------------------------------------------------------- J1: a „Mit tanult az asszisztens” lista

const HELYZET_RESZ: Record<string, string> = {
  folytat: tk('folytatás'), kifejt: tk('kifejtés'), osszefoglal: tk('összefoglalás'), szoveg: tk('szövegben'),
  szunet: tk('gépelési szünetben'), megnyitas: tk('megnyitáskor'), rovid: tk('rövid jegyzet'), kozepes: tk('közepes jegyzet'), hosszu: tk('hosszú jegyzet'),
};

/** A hangolás helyzet-kódja magyarul (`szunet_rovid` → „gépelési szünetben, rövid jegyzet”). */
export function helyzetSzoveg(h: string): string {
  return h.split('_').map((r) => (HELYZET_RESZ[r] ? t(HELYZET_RESZ[r]) : r)).join(', ');
}

const HANGOLAS: Record<string, string> = { batrabb: tk('gyakrabban javasol'), alap: tk('alap gyakoriság'), ritkabb: tk('ritkábban javasol'), nema: tk('néma (nem javasol)') };

export function hangolasSzoveg(szint: string): string {
  return HANGOLAS[szint] ? t(HANGOLAS[szint]) : szint;
}
