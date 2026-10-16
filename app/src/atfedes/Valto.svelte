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
  import { linkek } from '../lib/vault/linkek.svelte';
  import { ujJegyzetCel } from '../lib/elrendezes/ujJegyzet';
  import { fajlNev, mappa, type FajlInfo } from '../lib/vault/fajlok.svelte';

  const LIMIT = 50;
  const { felulet, fajlok } = kornyezet();
  let lekerdezes = $state('');
  let aliasok = $state<Record<string, string[]>>({});
  let aliasHiba = $state(false);
  let nevHiba = $state(false);
  type ValtoElem = FajlInfo & { alias?: string };
  const ujCel = $derived(ujJegyzetCel(lekerdezes));

  $effect(() => {
    void linkek.verzio;
    void linkek.tartalomVerzio;
    let ervenyes = true;
    void linkek.aliasokKap().then(a => { if (ervenyes) { aliasok = a; aliasHiba = false; } }, () => { if (ervenyes) aliasHiba = true; });
    return () => { ervenyes = false; };
  });
  $effect(() => { void lekerdezes; nevHiba = false; });
  const kereso = $derived.by(() => new FuzzyIndex<ValtoElem>(fajlok.lista.flatMap(f => [
    { ertek: f, nev: fajlNev(f.ut), ut: mappa(f.ut) },
    ...[...new Set(aliasok[f.ut] ?? [])].filter(a => a.trim() && a !== fajlNev(f.ut)).map(alias => ({ ertek: { ...f, alias }, nev: alias, ut: f.ut })),
  ])));


  const talalatok = $derived.by((): Talalat<ValtoElem>[] => {
    void fajlok.lista;
    const legutobbi = felulet.legutobbiFajlok;
    const q = lekerdezes.trim();
    if (!q) {
      const lat = new Set<string>();
      const ki: Talalat<ValtoElem>[] = [];
      for (const ut of legutobbi) {
        const f = fajlok.info(ut);
        if (f && !lat.has(ut)) {
          lat.add(ut);
          ki.push({ ertek: f, pont: 0, kiemeles: [] });
        }
      }
      const tobbi = fajlok.lista
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
  }
</script>

<Atfedes cimke={t('Gyorsváltó')} nev="valto" onbezar={bezar}>
  <ListaValaszto
    elemek={talalatok}
    kulcs={(t) => `${t.ertek.ut}\0${t.ertek.alias ?? ''}`}
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
      <span class="nev">{#if t.kiemeles.length}<Kiemelt szoveg={t.ertek.alias ?? fajlNev(t.ertek.ut)} kiemeles={t.kiemeles} />{:else}{t.ertek.alias ?? fajlNev(t.ertek.ut)}{/if}</span>
      <span class="ut">{t.ertek.alias ? fajlNev(t.ertek.ut) : mappa(t.ertek.ut)}</span>
    {/snippet}
    {#snippet lablec()}
      {#if nevHiba}<span role="alert">{t('Adj meg érvényes jegyzetnevet vagy relatív mappát.')}</span>{/if}
      {#if aliasHiba}<span role="status">{t('Az aliasok nem érhetők el. Keress fájlnév alapján.')}</span>{/if}
      {#if lekerdezes.trim()}
        <button type="button" class="letrehoz" disabled={!ujCel} onclick={() => letrehoz()}>{t('Új jegyzet: {nev}', { nev: lekerdezes.trim() })} <Billentyu akkord="Shift+Enter" /></button>
      {/if}
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
