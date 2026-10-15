// A téma: rendszer (prefers-color-scheme) | világos | sötét. A <html data-tema> és a héj címsora követi.

import { hejnek } from '../core/hej';

export type Tema = 'rendszer' | 'vilagos' | 'sotet';

export const TEMAK: Tema[] = ['rendszer', 'vilagos', 'sotet'];

export function alkalmaz(tema: Tema): void {
  const html = document.documentElement;
  if (tema === 'rendszer') delete html.dataset.tema;
  else html.dataset.tema = tema;
  hejnek({ tipus: 'tema', ertek: tema });
}
