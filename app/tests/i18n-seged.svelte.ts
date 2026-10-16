// A reaktivitás-tesztek segédje (runes csak `.svelte.ts` modulban fordul): a kifejezés minden újraszámolásának értékei.
import { flushSync } from 'svelte';

export function figyel(kifejezes: () => string): { ertekek: string[]; le: () => void; frissit: () => void } {
  const ertekek: string[] = [];
  const le = $effect.root(() => {
    $effect(() => {
      ertekek.push(kifejezes());
    });
  });
  flushSync();
  return { ertekek, le, frissit: () => flushSync() };
}
