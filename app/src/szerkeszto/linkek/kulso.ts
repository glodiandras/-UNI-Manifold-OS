// Külső link (C11a, audit M8): a Markdown-link és a csupasz URL megnyitása. A WebView nem navigálhat (a héj
// minden idegen címet elvet), ezért a megnyitás a héjon át megy: `{tipus: "megnyit", url}` → `NSWorkspace.open`.
// Csak `http`, `https` és `mailto` séma mehet; a héj ugyanezt újra ellenőrzi (a felület nem megbízható oldal).

import { t } from '../../lib/i18n';
import { hejbenFut, hejnek } from '../../lib/core/hej';
import { ertesitesek } from '../../lib/ertesites/ertesites.svelte';

const SEMAK = new Set(['http:', 'https:', 'mailto:']);

/** A megnyitható cím (normalizálva), vagy `null`: relatív, ismeretlen vagy tiltott séma (`javascript:`, `file:`…). */
export function kulsoCim(url: string): string | null {
  const nyers = url.trim().replace(/^<|>$/g, '');
  if (!nyers) return null;
  const teljes = /^www\./i.test(nyers) ? `https://${nyers}` : nyers;
  try {
    const u = new URL(teljes);
    if (!SEMAK.has(u.protocol)) return null;
    if (u.protocol !== 'mailto:' && !u.hostname) return null;
    return u.href;
  } catch {
    return null;
  }
}

/** A külső link megnyitása; → igaz, ha a cím megnyitható volt (és a kérés elment). */
export function kulsoLink(url: string): boolean {
  const cim = kulsoCim(url);
  if (!cim) return false;
  if (hejbenFut()) hejnek({ tipus: 'megnyit', url: cim });
  else if (typeof window !== 'undefined') window.open(cim, '_blank', 'noopener,noreferrer'); // fejlesztői böngésző
  else ertesitesek.ertesit({ szint: 'figyelmeztetes', cim: t('A link nem nyitható meg'), szoveg: cim });
  return true;
}
