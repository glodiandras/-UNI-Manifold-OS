import type { IconNode } from 'lucide';
import type { FajlTipus } from '../vault/fajlok.svelte';
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

/** A típus szerinti ikon; az `egyeb` típusú `.cpp` (C36a-UI: az index típusa nem változik) a kód-ikont kapja az út alapján. */
export function fajlIkon(tipus: FajlTipus | undefined, ut?: string | null): IconNode {
  if ((tipus ?? 'egyeb') === 'egyeb' && ut && /\.cpp$/i.test(ut)) return Code;
  return IKONOK[tipus ?? 'egyeb'] ?? File;
}

export const TIPUS_NEV: Record<FajlTipus, string> = {
  md: 'jegyzet',
  canvas: 'canvas',
  base: 'adatbázis-nézet',
  pdf: 'PDF',
  kep: 'kép',
  video: 'videó',
  hang: 'hang',
  felirat: 'felirat',
  egyeb: 'fájl',
};
