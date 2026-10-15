// A core eseménycsatornája (WS `/ws`): automatikus újracsatlakozással (0,5 s → 5 s). A felület ezekből
// frissít, nem pollingol (ARCHITECTURE 2.).

import { apiTitok } from './titok';

export type KapcsolatAllapot = 'kapcsolodik' | 'el' | 'megszakadt';

export interface CoreEsemeny {
  tipus: string;
  [kulcs: string]: unknown;
}

type Figyelo = (e: CoreEsemeny) => void;

export class CoreKapcsolat {
  allapot = $state<KapcsolatAllapot>('kapcsolodik');
  private ws: WebSocket | null = null;
  private readonly figyelok = new Map<string, Set<Figyelo>>();
  private varakozas = 500;
  private idozito: ReturnType<typeof setTimeout> | null = null;
  private leallitva = false;

  constructor(private readonly url = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`) {}

  indit(): void {
    this.leallitva = false;
    this.kapcsolodik();
  }

  leallit(): void {
    this.leallitva = true;
    if (this.idozito) clearTimeout(this.idozito);
    this.ws?.close();
  }

  /** Feliratkozás egy eseménytípusra (`*` = mind). */
  figyel(tipus: string, f: Figyelo): () => void {
    let s = this.figyelok.get(tipus);
    if (!s) this.figyelok.set(tipus, (s = new Set()));
    s.add(f);
    return () => s.delete(f);
  }

  /** Teszt és belső használat: egy esemény szétosztása. A core `kimaradt` jelzése (a lassú kliens sora túlcsordult, események
   *  vesztek el; T107) „bármi változhatott” eseménnyé is válik: a tömeges `vault_valtozas` fogyasztói (fájlfa, linkek, Bases,
   *  gráf, szerkesztő) maguktól újraolvasnak. */
  szetoszt(e: CoreEsemeny): void {
    for (const k of [e.tipus, '*']) {
      for (const f of this.figyelok.get(k) ?? []) {
        try {
          f(e);
        } catch (hiba) {
          console.error('WS-figyelő hiba', hiba);
        }
      }
    }
    if (e.tipus === 'kimaradt') this.szetoszt({ tipus: 'vault_valtozas', tomeges: true, utak: [], torolt: [], kulso: [] });
  }

  /** Üzenet a core-nak (C16.5: a mentetlen dokumentumok jelzése). → hamis, ha a kapcsolat épp nem él. */
  kuld(uzenet: CoreEsemeny): boolean {
    if (this.ws?.readyState !== WebSocket.OPEN) return false;
    this.ws.send(JSON.stringify(uzenet));
    return true;
  }

  private kapcsolodik() {
    let ws: WebSocket;
    try {
      // a böngésző WS-e nem küldhet fejlécet: a titok az alprotokollban megy (a core a választottat visszaküldi)
      ws = new WebSocket(this.url, [`mos.${apiTitok()}`]);
    } catch {
      return this.ujra();
    }
    this.ws = ws;
    ws.onopen = () => {
      this.allapot = 'el';
      this.varakozas = 500;
    };
    ws.onmessage = (m) => {
      try {
        const e = JSON.parse(String(m.data));
        if (e && typeof e.tipus === 'string') this.szetoszt(e);
      } catch {
        // hibás üzenet: kihagyjuk
      }
    };
    ws.onclose = () => {
      if (this.ws !== ws) return;
      this.ws = null;
      if (!this.leallitva) this.ujra();
    };
  }

  private ujra() {
    this.allapot = 'megszakadt';
    this.idozito = setTimeout(() => {
      this.allapot = 'kapcsolodik';
      this.kapcsolodik();
    }, this.varakozas);
    this.varakozas = Math.min(this.varakozas * 2, 5000);
  }
}
