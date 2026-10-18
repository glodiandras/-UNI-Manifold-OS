<!--
  ⌘O gyorsváltó: a vault fájljai a core indexéből. Üres lekérdezésnél a legutóbbiak, utána a többi
  módosítás szerint; gépeléskor ékezetfüggetlen, elírástűrő keresés, a legutóbbiak előnyt kapnak.
-->
<script lang="ts">
  import { t } from '../lib/i18n';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import { fajlIkon } from '../lib/ikon/fajlIkon';
  import { kornyezet } from '../lib/kornyezet';
  import { FuzzyIndex, type Talalat } from '../lib/kereses/fuzzy';
  import Atfedes from '../lib/ui/Atfedes.svelte';
  import Billentyu from '../lib/ui/Billentyu.svelte';
  import Kiemelt from './Kiemelt.svelte';
  import ListaValaszto, { type Modositok } from '../lib/ui/ListaValaszto.svelte';
  import { kerdez } from '../lib/core/api';
  import { linkek, type VaultFejezet } from '../lib/vault/linkek.svelte';
  import { szerkesztok } from '../szerkeszto/szerkesztok.svelte';
  import {
    blokkSzures, fejezetSzures, horgonyElemez, jegyzetKiegeszit, jegyzetKivalaszt, type BlokkSor, type FejezetSor, type HorgonyElem,
  } from '../lib/vault/valtoHorgony';
  import { ujJegyzetCel } from '../lib/elrendezes/ujJegyzet';
  import { fajlNev, mappa, type FajlInfo } from '../lib/vault/fajlok.svelte';

  const LIMIT = 50;
  const { felulet, fajlok } = kornyezet();
  let lekerdezes = $state('');
  let aliasok = $state<Record<string, string[]>>({});
  let aliasHiba = $state(false);
  let nevHiba = $state(false);
  type ValtoElem = FajlInfo & { alias?: string; horgony?: HorgonyElem };
  const ujCel = $derived(ujJegyzetCel(lekerdezes));

  $effect(() => {
    void linkek.verzio;
    void linkek.tartalomVerzio;
    let ervenyes = true;
    void linkek.aliasokKap().then(a => { if (ervenyes) { aliasok = a; aliasHiba = false; } }, () => { if (ervenyes) aliasHiba = true; });
    return () => { ervenyes = false; };
  });
  $effect(() => { void lekerdezes; nevHiba = false; });
  // Excluded files (14-appearance-06): a kizárt fájl nem jelenik meg a gyorsváltóban (a link rá továbbra is feloldódik)
  const lista = $derived(fajlok.lista.filter(f => !f.kizart));
  const kereso = $derived.by(() => new FuzzyIndex<ValtoElem>(lista.flatMap(f => [
    { ertek: f, nev: fajlNev(f.ut), ut: mappa(f.ut) },
    ...[...new Set(aliasok[f.ut] ?? [])].filter(a => a.trim() && a !== fajlNev(f.ut)).map(alias => ({ ertek: { ...f, alias }, nev: alias, ut: f.ut })),
  ])));


  // `Jegyzet#fejezet` / `Jegyzet^blokk` / `#fejezet` (13-palette-03): a jegyzetrész a legjobb egyező .md; adatai a core indexéből
  const horgony = $derived(horgonyElemez(lekerdezes));
  const horgonyJegyzet = $derived.by(() => {
    if (!horgony) return null;
    if (horgony.jegyzet) return jegyzetKivalaszt(fajlok.lista, horgony.jegyzet, felulet.legutobbiFajlok);
    const aktivUt = felulet.munkaterulet.aktivFul?.ut;
    return horgony.jel === '^' && aktivUt ? (fajlok.info(aktivUt) ?? null) : null;
  });
  let jegyzetAdat = $state.raw<{ ut: string; fejezetek: FejezetSor[]; blokkok: BlokkSor[] } | null>(null);
  let vaultFejezetek = $state.raw<VaultFejezet[] | null>(null);
  let horgonyHiba = $state(false);
  const vaultSzintu = $derived(!!horgony && !horgony.jegyzet && horgony.jel === '#');

  $effect(() => {
    const ut = horgonyJegyzet?.ut ?? null;
    void linkek.tartalomVerzio;
    if (!ut) { jegyzetAdat = null; return; }
    let ervenyes = true;
    kerdez<{ fejezetek: FejezetSor[]; blokkok: BlokkSor[] }>(`/api/vault/jegyzet?ut=${encodeURIComponent(ut)}`, { idokorlat: 8000 }).then(
      (d) => { if (ervenyes) { jegyzetAdat = { ut, fejezetek: d.fejezetek ?? [], blokkok: d.blokkok ?? [] }; horgonyHiba = false; } },
      () => { if (ervenyes) { jegyzetAdat = null; horgonyHiba = true; } },
    );
    return () => { ervenyes = false; };
  });
  $effect(() => {
    if (!vaultSzintu) { vaultFejezetek = null; return; }
    const szuro = horgony!.szuro;
    const ac = new AbortController();
    const ido = setTimeout(() => {
      linkek.fejezetekMind(szuro, ac.signal).then(
        (d) => { if (!ac.signal.aborted) { vaultFejezetek = d.slice(0, LIMIT); horgonyHiba = false; } },
        () => { if (!ac.signal.aborted) horgonyHiba = true; },
      );
    }, 120);
    return () => { clearTimeout(ido); ac.abort(); };
  });
  const horgonyTalalatok = $derived.by((): Talalat<ValtoElem>[] => {
    if (!horgony) return [];
    if (vaultSzintu) {
      return (vaultFejezetek ?? []).flatMap((f) => {
        const info = fajlok.info(f.ut);
        return info ? [{ ertek: { ...info, horgony: { jel: '#' as const, ut: f.ut, sor: f.sor, szoveg: f.szoveg, szint: f.szint } }, pont: 0, kiemeles: [] as [number, number][] }] : [];
      });
    }
    const j = horgonyJegyzet;
    if (!j || jegyzetAdat?.ut !== j.ut) return [];
    const t = horgony.jel === '#' ? fejezetSzures(j.ut, jegyzetAdat.fejezetek, horgony.szuro) : blokkSzures(j.ut, jegyzetAdat.blokkok, horgony.szuro);
    return t.map((x) => ({ ...x, ertek: { ...j, horgony: x.ertek } }));
  });

  const talalatok = $derived.by((): Talalat<ValtoElem>[] => {
    if (horgony) return horgonyTalalatok;
    void fajlok.lista;
    const legutobbi = felulet.legutobbiFajlok;
    const q = lekerdezes.trim();
    if (!q) {
      const lat = new Set<string>();
      const ki: Talalat<ValtoElem>[] = [];
      for (const ut of legutobbi) {
        const f = fajlok.info(ut);
        if (f && !f.kizart && !lat.has(ut)) {
          lat.add(ut);
          ki.push({ ertek: f, pont: 0, kiemeles: [] });
        }
      }
      const tobbi = lista
        .filter((f) => !lat.has(f.ut))
        .sort((a, b) => (b.mtime ?? 0) - (a.mtime ?? 0))
        .slice(0, LIMIT - ki.length);
      return [...ki, ...tobbi.map((f) => ({ ertek: f, pont: 0, kiemeles: [] }))].slice(0, LIMIT);
    }
    const rang = new Map(legutobbi.map((u, i) => [u, i]));
    return kereso.keres(q, {
      limit: LIMIT,
      bonusz: (f) => {
        const i = rang.get(f.ut);
        return i === undefined ? 0 : Math.max(5, 30 - i);
      },
    });
  });

  const ures = $derived(
    fajlok.index && !fajlok.index.kesz
      ? t('Az index még épül…')
      : horgonyHiba
        ? t('A fejezetek és blokkok nem érhetők el.')
        : horgony && !vaultSzintu && !horgonyJegyzet
          ? t('Nincs ilyen jegyzet: „{kif}”', { kif: horgony.jegyzet || lekerdezes.trim() })
          : horgony
            ? t('Nincs találat erre: „{kif}”', { kif: horgony.szuro || lekerdezes.trim() })
            : lekerdezes.trim()
              ? t('Nincs találat erre: „{kif}”', { kif: lekerdezes.trim() })
              : t('A vault üres.'),
  );

  function letrehoz(m: Modositok = { uj: false, oszt: false }) {
    if (!ujCel) { nevHiba = true; return; }
    felulet.faUjNev = { ...ujCel, mod: m.oszt ? 'osztas' : m.uj ? 'ujful' : 'aktiv' };
    felulet.faUjJegyzet = true;
    felulet.oldalsav.nezet = 'fajlok';
    felulet.oldalsav.nyitva = true;
    bezar();
  }

  function bevitel(e: KeyboardEvent): boolean {
    if (horgony) return !talalatok.length;             // a `#`/`^` nem érvényes jegyzetnév: ott nincs létrehozás
    if (!e.shiftKey && talalatok.length) return false;
    if (lekerdezes.trim()) letrehoz({ uj: e.metaKey && !e.altKey, oszt: e.metaKey && e.altKey });
    return true;
  }

  function bezar() {
    felulet.atfedes = null;
  }

  function valaszt(t: Talalat<ValtoElem>, m: Modositok) {
    bezar();
    felulet.munkaterulet.megnyit(t.ertek.ut, m.oszt ? 'osztas' : m.uj ? 'ujful' : 'aktiv');
    if (t.ertek.horgony) szerkesztok.ugras(t.ertek.ut, t.ertek.horgony.sor);
  }

  /** Tab: a jegyzetrész a teljes névre (`Pla#` → `Plan#`); utána az aktív fejezet/blokk szövegére (`Plan#Áttekintés`). */
  function tab(elem: Talalat<ValtoElem> | undefined) {
    if (!horgony) return;
    const k = jegyzetKiegeszit(horgony, horgonyJegyzet);
    if (k !== null) lekerdezes = k;
    else if (elem?.ertek.horgony) lekerdezes = `${fajlNev(elem.ertek.ut)}${horgony.jel}${elem.ertek.horgony.szoveg}`;
  }
</script>

<Atfedes cimke={t('Gyorsváltó')} nev="valto" onbezar={bezar}>
  <ListaValaszto
    elemek={talalatok}
    kulcs={(t) => `${t.ertek.ut}\0${t.ertek.alias ?? ''}\0${t.ertek.horgony ? `${t.ertek.horgony.jel}${t.ertek.horgony.sor}` : ''}`}
    ontab={tab}
    onbevitel={bevitel}
    bind:lekerdezes
    helyorzo={t('Fájl keresése…')}
    cimke={t('Fájl keresése')}
    {ures}
    onvalaszt={valaszt}
    onbezar={bezar}
  >
    {#snippet sor(t: Talalat<ValtoElem>)}
      <span class="ikon"><Ikon ikon={fajlIkon(t.ertek.tipus)} /></span>
      {#if t.ertek.horgony}
        <span class="nev"><span class="jel" aria-hidden="true">{t.ertek.horgony.jel === '#' ? '#'.repeat(t.ertek.horgony.szint ?? 1) : '^'}</span>{#if t.kiemeles.length}<Kiemelt szoveg={t.ertek.horgony.szoveg} kiemeles={t.kiemeles} />{:else}{t.ertek.horgony.szoveg}{/if}</span>
        <span class="ut">{fajlNev(t.ertek.ut)}</span>
      {:else}
      <span class="nev">{#if t.kiemeles.length}<Kiemelt szoveg={t.ertek.alias ?? fajlNev(t.ertek.ut)} kiemeles={t.kiemeles} />{:else}{t.ertek.alias ?? fajlNev(t.ertek.ut)}{/if}</span>
      <span class="ut">{t.ertek.alias ? fajlNev(t.ertek.ut) : mappa(t.ertek.ut)}</span>
      {/if}
    {/snippet}
    {#snippet lablec()}
      {#if nevHiba}<span role="alert">{t('Adj meg érvényes jegyzetnevet vagy relatív mappát.')}</span>{/if}
      {#if aliasHiba}<span role="status">{t('Az aliasok nem érhetők el. Keress fájlnév alapján.')}</span>{/if}
      {#if lekerdezes.trim() && !horgony}
        <button type="button" class="letrehoz" disabled={!ujCel} onclick={() => letrehoz()}>{t('Új jegyzet: {nev}', { nev: lekerdezes.trim() })} <Billentyu akkord="Shift+Enter" /></button>
      {/if}
      {#if horgony}<span><kbd>⇥</kbd> {t('kiegészítés')}</span>{:else if !lekerdezes.trim()}<span>{t('Jegyzet#fejezet · Jegyzet^blokk')}</span>{/if}
      <span><kbd>↑↓</kbd> {t('választás')}</span>
      <span><kbd>↩</kbd> {t('megnyitás')}</span>
      <span><Billentyu akkord="Mod+Enter" /> {t('új fülben')}</span>
      <span><Billentyu akkord="Mod+Alt+Enter" /> {t('osztásban')}</span>
      <span><kbd>esc</kbd> {t('bezárás')}</span>
    {/snippet}
  </ListaValaszto>
</Atfedes>

<style>
  .ikon {
    color: var(--szoveg-halvany);
  }

  .nev {
    flex: 0 1 auto;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .jel {
    margin-right: var(--t-1);
    color: var(--szoveg-halvany);
  }

  .ut {
    flex: 1 1 0;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    text-align: right;
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
  }

  .letrehoz {
    display: inline-flex;
    align-items: center;
    gap: var(--t-2);
    padding: var(--t-1) var(--t-2);
    border-radius: var(--kerekites);
    color: var(--akcent-szoveg);
  }

  .letrehoz:hover { background: var(--hatter-hover); }
  .letrehoz:disabled { color: var(--szoveg-halvany); }

  kbd {
    color: var(--szoveg-masodlagos);
  }
</style>
