// A jegyzetek oldalikonja és borítóképe (C11b): az `icon` és a `cover` frontmatter-kulcs a core indexéből
// (`/api/vault/ikonok`). A felület csak megjelenít; a képfájl feloldása a core-é (L42). A tárolt érték lehet emoji
// vagy szöveg (az `ut` ilyenkor `null`), wikilink vagy fájlnév (az `ut` a feloldott vault-fájl); a külső URL a CSP miatt
// nem tölthető be (az `ut` `null`, a megjelenítés nem próbálja).

import { ApiHiba, kerdez } from '../core/api';
import type { CoreKapcsolat } from '../core/ws.svelte';

export interface IkonAdat {
  ertek: string;
  ut: string | null;
}

export interface JegyzetIkonok {
  icon?: IkonAdat;
  cover?: IkonAdat;
}

const KEP = /\.(png|jpe?g|gif|webp|avif|svg|bmp|tiff?|heic)$/i;

/** Egy ikon-érték megjelenítési módja. */
export function ikonFajta(a: IkonAdat | undefined): { fajta: 'emoji' | 'kep' | 'nincs'; szoveg: string } {
  if (!a) return { fajta: 'nincs', szoveg: '' };
  if (a.ut && KEP.test(a.ut)) return { fajta: 'kep', szoveg: a.ut };
  const sz = a.ertek.trim();
  if (a.ut || /^[a-z][a-z0-9+.-]*:\/\//i.test(sz) || sz.startsWith('[[') || KEP.test(sz)) return { fajta: 'nincs', szoveg: sz };
  // emoji vagy rövid szöveg (legfeljebb néhány karakter): a címke előtt jelenik meg
  return [...sz].length <= 4 ? { fajta: 'emoji', szoveg: sz } : { fajta: 'nincs', szoveg: sz };
}

export class VaultIkonok {
  terkep = $state.raw<Record<string, JegyzetIkonok>>({});
  private idozito: ReturnType<typeof setTimeout> | null = null;
  private sorszam = 0;

  kap(ut: string | null | undefined): JegyzetIkonok | undefined {
    return ut ? this.terkep[ut] : undefined;
  }

  async frissit(): Promise<void> {
    const en = ++this.sorszam;
    try {
      const d = await kerdez<{ ikonok: Record<string, JegyzetIkonok> }>('/api/vault/ikonok', { idokorlat: 8000 });
      if (en === this.sorszam) this.terkep = d.ikonok ?? {};
    } catch (e) {
      if (!(e instanceof ApiHiba && e.statusz === 503)) console.warn('ikonok:', e);
    }
  }

  private utemez(ms = 1200) {
    if (this.idozito) clearTimeout(this.idozito);
    this.idozito = setTimeout(() => void this.frissit(), ms);
  }

  /** WS-figyelés: egy jegyzet mentése megváltoztathatja a frontmatterét, ezért a vault változására (lassítva) újratölt. */
  figyel(k: CoreKapcsolat): () => void {
    const le1 = k.figyel('vault_valtozas', () => this.utemez());
    const le2 = k.figyel('index', () => this.utemez(0));
    const le3 = k.figyel('hello', () => this.utemez(0));
    return () => {
      le1();
      le2();
      le3();
      if (this.idozito) clearTimeout(this.idozito);
    };
  }
}

export const ikonok = new VaultIkonok();
