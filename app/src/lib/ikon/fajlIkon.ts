import { t } from '../i18n';
import type { IconNode } from 'lucide';
import type { FajlTipus } from '../vault/fajlok.svelte';
import { KOD_UT } from '../vault/kodFajl';
import { Code, File, FileImage, FileMusic, FilePlay, FileText, LayoutDashboard, Table2 } from './ikonok';

const IKONOK: Record<FajlTipus, IconNode> = {
  md: FileText,
  canvas: LayoutDashboard,
  base: Table2,
  pdf: File,
  kep: FileImage,
  video: FilePlay,
  hang: FileMusic,
  felirat: FileText,
  egyeb: File,
};

/** A típus szerinti ikon; az `egyeb` típusú forrásfájl (C36a-UI, F10: az index típusa nem változik) a kód-ikont kapja az út alapján. */
export function fajlIkon(tipus: FajlTipus | undefined, ut?: string | null): IconNode {
  if ((tipus ?? 'egyeb') === 'egyeb' && ut && KOD_UT.test(ut)) return Code;
  return IKONOK[tipus ?? 'egyeb'] ?? File;
}

export const TIPUS_NEV: Record<FajlTipus, string> = {
  get md() { return t('jegyzet'); },
  get canvas() { return t('canvas'); },
  get base() { return t('adatbázis-nézet'); },
  pdf: 'PDF',
  get kep() { return t('kép'); },
  get video() { return t('videó'); },
  get hang() { return t('hang'); },
  get felirat() { return t('felirat'); },
  get egyeb() { return t('fájl'); },
};
