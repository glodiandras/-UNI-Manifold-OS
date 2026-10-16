// A videólinkek beolvasása a Bevitel szakasz mezőjéből (C20a). A core (`core/videolanc.py`) ugyanezeket az ellenőrzéseket végzi, és a
// helyi/privát címet is elutasítja; itt csak a gyors, kliensoldali visszajelzés: soronként egy http(s) link, ismétlés nélkül, legfeljebb VIDEO_MAX.

import { t } from '../i18n';
export const VIDEO_MAX = 20;

export interface LinkEredmeny {
  /** A beolvasott, érvényes linkek (sorrendtartó, ismétlés nélkül) */
  urlek: string[];
  /** A figyelmen kívül hagyott darabok és az okuk */
  hibak: string[];
}

export function linkekBeolvas(szoveg: string): LinkEredmeny {
  const urlek: string[] = [];
  const hibak: string[] = [];
  for (const darab of szoveg.split(/\s+/)) {
    const u = darab.trim();
    if (!u) continue;
    let ok = false;
    try {
      const p = new URL(u);
      ok = (p.protocol === 'http:' || p.protocol === 'https:') && !!p.hostname && !p.username && !p.password;
    } catch {
      ok = false;
    }
    if (!ok) hibak.push(t('Nem http(s) link: {url}', { url: u.length > 60 ? `${u.slice(0, 57)}…` : u }));
    else if (!urlek.includes(u)) urlek.push(u);
  }
  if (urlek.length > VIDEO_MAX) {
    hibak.push(t('Egy feladatban legfeljebb {max} link adható meg ({n} érkezett).', { max: VIDEO_MAX, n: urlek.length }));
  }
  return { urlek, hibak };
}
