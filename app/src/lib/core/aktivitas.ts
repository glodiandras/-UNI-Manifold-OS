// Aktivitásjel a core-nak (C05: a memóriaőr aktív használatkor nem indít automatikus munkát):
// billentyű, kattintás, egér, görgetés → `POST /api/aktivitas`, legfeljebb másodpercenként egyszer.

import { kerdez } from './api';

export function aktivitasFigyelo(kuld: () => void = alapKuldo, koz = 1000): () => void {
  let utolso = 0;
  const jel = () => {
    const most = Date.now();
    if (most - utolso < koz) return;
    utolso = most;
    kuld();
  };
  const esemenyek = ['keydown', 'pointerdown', 'pointermove', 'wheel'] as const;
  for (const e of esemenyek) window.addEventListener(e, jel, { passive: true, capture: true });
  return () => {
    for (const e of esemenyek) window.removeEventListener(e, jel, { capture: true });
  };
}

function alapKuldo() {
  kerdez('/api/aktivitas', { metodus: 'POST', torzs: { forras: 'felulet' }, idokorlat: 2000 }).catch(() => {});
}
