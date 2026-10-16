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

/** A `GET /api/vault/linkcel` válasza: a cél a beállított formátumban, az `alak` (wiki | md) és a kész md-cél (kódolva). */
export interface LinkCelAdat {
  ut: string;
  cel: string;
  alak?: 'wiki' | 'md';
  md?: string;
}

/** Tartalmi esemény: a megváltozott utak, vagy `null` (újrakapcsolódás, tömeges változás — minden érintett). */
export type TartalomFigyelo = (utak: ReadonlySet<string> | null) => void;

/** A core `linkcel` válasza: a beírandó cél a „New link format” szerint, az alak a „Use [[Wikilinks]]” szerint, és a kész
 *  markdown-link célja (kódolva, `.md`-vel, a horgonnyal). A felület csak ezekből épít linket (`linkSzoveg`). */
export interface LinkForma {
  cel: string;
  alak: 'wiki' | 'md';
  md: string;
}

export interface VaultFejezet {
  ut: string;
  szint: number;
  szoveg: string;
  sor: number;
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
  private feloldatlan: Promise<string[]> | null = null;
  private tokenVaro: Promise<string | null> | null = null;
  private readonly tartalomFigyelok = new Set<TartalomFigyelo>();

  /** Feliratkozás a célonkénti tartalmi eseményre (04-embeds-07): a beágyazás csak a saját céljának változásakor frissül. */
  tartalomFigyel(fn: TartalomFigyelo): () => void {
    this.tartalomFigyelok.add(fn);
    return () => { this.tartalomFigyelok.delete(fn); };
  }

  /** Tartalmi esemény: a `tartalomVerzio` nő, a feliratkozók megkapják az érintett utakat (`null`: mind). */
  tartalomValtozott(utak: Iterable<string> | null): void {
    this.tartalomVerzio++;
    const halmaz = utak === null ? null : new Set(utak);
    for (const fn of [...this.tartalomFigyelok]) {
      try { fn(halmaz); } catch (e) { console.error(e); }
    }
  }

  /** A fájlszerkezet változott: a gyorsítótárak ürülnek. */
  ervenytelenit(): void {
    this.feloldasok.clear();
    this.aliasok = null;
    this.feloldatlan = null;
    this.verzio++;
  }

  figyel(k: CoreKapcsolat, ismert: (ut: string) => boolean): () => void {
    const le1 = k.figyel('hello', (e) => {
      if (typeof e.media_token === 'string') this.mediaToken = e.media_token;
      this.ervenytelenit();
      this.tartalomValtozott(null);
    });
    const le2 = k.figyel('vault_valtozas', (e) => {
      const utak = (e.utak as string[] | undefined) ?? [];
      const torolt = (e.torolt as string[] | undefined) ?? [];
      this.aliasok = null; // az `aliases` bármely mentéssel változhat
      this.feloldatlan = null; // egy mentés új, még nem létező link-célt is behozhat
      this.feloldasok.clear(); // egy meglévő jegyzet új aliasa korábban hiányzó célt is feloldhat
      if (e.tomeges || torolt.length || utak.some((u) => !ismert(u))) this.ervenytelenit();
      this.tartalomValtozott(e.tomeges ? null : [...utak, ...torolt]);
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

  /** A fájl link-adatai a `forras`-ból: a cél a beállított link-formátumban, az alak (wiki/md) és az md-cél (04-embeds-09). */
  linkCelAdat(ut: string, forras: string): Promise<LinkCelAdat> {
    return kerdez<LinkCelAdat>(`/api/vault/linkcel?ut=${q(ut)}&forras=${q(forras)}`, { idokorlat: 5000 });
  }

  /** A beírandó link adatai a `forras`-ból (a core: formátum, alak, md-cél). A `alcel` az md-célba kerülő horgony. Régi vagy hiányos
   *  válasznál (`alak`/`md` nélkül) wikilink. */
  async linkForma(ut: string, forras: string, alcel?: string | null): Promise<LinkForma> {
    const d = await kerdez<{ cel: string; alak?: string; md?: string }>(
      `/api/vault/linkcel?ut=${q(ut)}&forras=${q(forras)}${alcel ? `&alcel=${q(alcel)}` : ''}`,
      { idokorlat: 5000 },
    );
    return { cel: d.cel, alak: d.alak === 'md' ? 'md' : 'wiki', md: d.md ?? '' };
  }

  /** Mint a `linkForma`, de még nem létező célra (`[[Új jegyzet]]`): a core csak a beállítást és a kódolást adja. */
  async linkFormaHianyzo(cel: string, forras: string): Promise<LinkForma> {
    const d = await kerdez<{ cel: string; alak?: string; md?: string }>(
      `/api/vault/linkcel?cel=${q(cel)}&forras=${q(forras)}`,
      { idokorlat: 5000 },
    );
    return { cel: d.cel, alak: d.alak === 'md' ? 'md' : 'wiki', md: d.md ?? '' };
  }

  /** A vaultban használt, de még nem létező link-célok szövegei (a `[[` javaslataihoz); a szerkezet/tartalom változásáig gyorsítótárazva. */
  feloldatlanSzovegek(): Promise<string[]> {
    this.feloldatlan ??= kerdez<{ szovegek: { cel: string }[] }>('/api/vault/feloldatlan?limit=300', { idokorlat: 8000 }).then(
      (d) => d.szovegek.map((x) => x.cel),
      (e) => {
        this.feloldatlan = null;
        if (e instanceof ApiHiba && (e.statusz === 503 || e.statusz === 404)) return [];
        throw e;
      },
    );
    return this.feloldatlan;
  }

  /** Az összes jegyzet fejezetei a szűrőre (a `[[##` kereséshez), a core szűrte és rangsorolta. */
  async fejezetekMind(szuro: string, jel?: AbortSignal): Promise<VaultFejezet[]> {
    const d = await kerdez<{ fejezetek: VaultFejezet[] }>(`/api/vault/fejezetek?q=${q(szuro)}&limit=300`, { idokorlat: 8000, jel });
    return Array.isArray(d.fejezetek) ? d.fejezetek : [];
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
