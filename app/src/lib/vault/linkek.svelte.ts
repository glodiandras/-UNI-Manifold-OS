// A link-szolgáltatás (C10): a core link-API-ja a felületnek. A felület **nem old fel saját szabállyal** (L42):
// minden cél-feloldás, rövid cél-szöveg és horgony a core-tól jön; itt csak gyorsítótár és kényelmi hívás van.
//
// - `feloldas`: a (forrásmappa, cél) párokat gyorsítótárazza (a feloldás a forrás mappájától és a fájlhalmaztól
//   függ); a fájlszerkezet változására a gyorsítótár ürül és a `verzio` nő. Tartalmi mentéskor az aliasok
//   miatt a feloldási cache is ürül; a tartalomVerzio a beágyazások mellett a linkjelzéseket is frissíti.
// - `mediaUrl`: tokenes URL (`/media/<token>/<út>`): az <img>/<video>/<iframe> nem küldhet X-Manifold fejlécet.

import { ApiHiba, kerdez, statuszUzenet } from '../core/api';
import type { CoreKapcsolat } from '../core/ws.svelte';
import { mappa } from './fajlok.svelte';

export type BeagyazasTipus = 'jegyzet' | 'kep' | 'video' | 'hang' | 'pdf' | 'canvas' | 'base' | 'egyeb' | 'nincs';

export interface BeagyazasAdat {
  tipus: BeagyazasTipus;
  /** a feloldott fájl útja (nincs, ha `tipus === 'nincs'`) */
  ut?: string;
  /** a nyers cél (csak `nincs`-nél) */
  cel?: string;
  alcel?: string | null;
  tobbertelmu?: boolean;
  /** jegyzetnél: a szelet szövege (frontmatter nélkül), és első/utolsó sora (1-től) */
  szoveg?: string;
  kezd?: number | null;
  veg?: number | null;
  /** a fejezet/blokk nem található */
  alcel_hiba?: boolean;
}

export interface Feloldott {
  cel: string;
  ut: string | null;
  tobbertelmu: boolean;
}

const q = encodeURIComponent;

export class LinkSzolgaltatas {
  /** A média-URL-ek tokenje (a core indulásakor sorsolt; újraindulásnál új). */
  mediaToken = $state<string | null>(null);
  /** Nő, ha a fájlhalmaz szerkezete változott: a feloldások érvénytelenek. */
  verzio = $state(0);
  /** Nő minden tartalmi eseménynél is: a beágyazott szeletek újraolvasandók, a feloldási cache maradhat. */
  tartalomVerzio = $state(0);
  private readonly feloldasok = new Map<string, Feloldott>();
  private aliasok: Promise<Record<string, string[]>> | null = null;
  private tokenVaro: Promise<string | null> | null = null;

  /** A fájlszerkezet változott: a gyorsítótárak ürülnek. */
  ervenytelenit(): void {
    this.feloldasok.clear();
    this.aliasok = null;
    this.verzio++;
  }

  figyel(k: CoreKapcsolat, ismert: (ut: string) => boolean): () => void {
    const le1 = k.figyel('hello', (e) => {
      if (typeof e.media_token === 'string') this.mediaToken = e.media_token;
      this.ervenytelenit();
      this.tartalomVerzio++;
    });
    const le2 = k.figyel('vault_valtozas', (e) => {
      const utak = (e.utak as string[] | undefined) ?? [];
      const torolt = (e.torolt as string[] | undefined) ?? [];
      this.aliasok = null; // az `aliases` bármely mentéssel változhat
      this.feloldasok.clear(); // egy meglévő jegyzet új aliasa korábban hiányzó célt is feloldhat
      this.tartalomVerzio++;
      if (e.tomeges || torolt.length || utak.some((u) => !ismert(u))) this.ervenytelenit();
    });
    return () => {
      le1();
      le2();
    };
  }

  /** A média-token (ha még nincs, az `/api/allapot`-ból). */
  token(): Promise<string | null> {
    if (this.mediaToken) return Promise.resolve(this.mediaToken);
    this.tokenVaro ??= kerdez<{ media_token?: string }>('/api/allapot', { idokorlat: 5000 }).then(
      (d) => {
        this.mediaToken = d.media_token ?? null;
        this.tokenVaro = null;
        return this.mediaToken;
      },
      () => {
        this.tokenVaro = null;
        return null;
      },
    );
    return this.tokenVaro;
  }

  /** A fájl média-URL-je (a horgony — `#page=3`, `#t=12` — a hívóé). A `w` a kép kért szélessége (px): a core a
   *  kicsinyített változatot adja (C11a); nélküle az eredeti jön. */
  async mediaUrl(ut: string, w?: number): Promise<string> {
    const t = await this.token();
    return `/media/${t ?? ''}/${ut.split('/').map(q).join('/')}${w ? `?w=${w}` : ''}`;
  }

  /** A videó előnézeti képének URL-je (E14): a core a pinelt ffmpeg-gel készíti (`?poster=1`), a `t` az időpont másodpercben
   *  (nélküle ~1 mp). Hiba esetén a core 404-et ad: a `<video poster>` ilyenkor egyszerűen nem rajzol posztert. */
  async posterUrl(ut: string, t?: number): Promise<string> {
    const tok = await this.token();
    return `/media/${tok ?? ''}/${ut.split('/').map(q).join('/')}?poster=1${t ? `&t=${t}` : ''}`;
  }

  /** Link-célok feloldása a `forras` jegyzetből: a feloldott út (vagy `null`). */
  async feloldas(forras: string, celok: string[], jel?: AbortSignal): Promise<Feloldott[]> {
    jel?.throwIfAborted();
    const mp = mappa(forras);
    const kulcs = (c: string) => `${mp}\0${c}`;
    // Az aszinkron kérés alatt a közös cache változhat; az adott hívás a saját teljes válaszát őrzi.
    const eredmenyek = new Map(celok.flatMap(c => {
      const e = this.feloldasok.get(kulcs(c));
      return e ? [[c, e] as const] : [];
    }));
    const hianyzo = [...new Set(celok.filter((c) => !this.feloldasok.has(kulcs(c))))];
    if (hianyzo.length) {
      const verzio = this.verzio;
      const tartalomVerzio = this.tartalomVerzio;
      const d = await kerdez<{ eredmenyek: Feloldott[] }>('/api/vault/feloldas', {
        metodus: 'POST',
        torzs: { forras, celok: hianyzo },
        idokorlat: 10000,
        jel,
      });
      // A hiányos/hibás válasz ismeretlen állapot, nem megerősített hiányzó fájl.
      if (!Array.isArray(d.eredmenyek)) throw new ApiHiba(502, statuszUzenet(502));
      for (const c of hianyzo) {
        const talalatok = d.eredmenyek.filter(x => x?.cel === c);
        const e = talalatok[0];
        if (talalatok.length !== 1 || !(e.ut === null || (typeof e.ut === 'string' && e.ut.length > 0)))
          throw new ApiHiba(502, statuszUzenet(502));
        eredmenyek.set(c, { cel: c, ut: e.ut, tobbertelmu: !!e.tobbertelmu });
      }
      if (verzio === this.verzio && tartalomVerzio === this.tartalomVerzio && !jel?.aborted)
        for (const c of hianyzo) this.feloldasok.set(kulcs(c), eredmenyek.get(c)!);
    }
    jel?.throwIfAborted();
    return celok.map(c => ({ ...eredmenyek.get(c)!, cel: c }));
  }

  /** Egy cél feloldása (az út, vagy `null`). */
  async fajl(forras: string, cel: string): Promise<string | null> {
    return (await this.feloldas(forras, [cel]))[0].ut;
  }

  /** A fájl beírandó cél-szövege a `forras`-ból (a core legrövidebb egyértelmű alakja). */
  async linkCel(ut: string, forras: string): Promise<string> {
    const d = await kerdez<{ cel: string }>(`/api/vault/linkcel?ut=${q(ut)}&forras=${q(forras)}`, { idokorlat: 5000 });
    return d.cel;
  }

  /** Beágyazás/előnézet tartalma: típus, feloldott fájl, jegyzetnél a szelet. */
  beagyazas(forras: string, cel: string, alcel?: string | null): Promise<BeagyazasAdat> {
    const p = `/api/vault/beagyazas?forras=${q(forras)}&cel=${q(cel)}${alcel ? `&alcel=${q(alcel)}` : ''}`;
    return kerdez<BeagyazasAdat>(p, { idokorlat: 10000 });
  }

  /** Az aliasos fájlok aliasai (`{ut: [alias]}`); a fájlszerkezet változásáig gyorsítótárazva. */
  aliasokKap(): Promise<Record<string, string[]>> {
    this.aliasok ??= kerdez<{ aliasok: Record<string, string[]> }>('/api/vault/aliasok', { idokorlat: 10000 }).then(
      (d) => d.aliasok,
      (e) => {
        this.aliasok = null;
        if (e instanceof ApiHiba && e.statusz === 503) return {};
        throw e;
      },
    );
    return this.aliasok;
  }
}

export const linkek = new LinkSzolgaltatas();
