<!--
  Fájlválasztó a canvas új jegyzet- vagy fájlkártyájához (C14): a ⌘O gyorsváltó keresője (ékezetfüggetlen, elírástűrő,
  a legutóbbiak előnyt kapnak), a választás nem nyit meg, hanem visszaadja az utat.
-->
<script lang="ts">
  import { t } from '../lib/i18n';
  import Kiemelt from '../atfedes/Kiemelt.svelte';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import { fajlIkon } from '../lib/ikon/fajlIkon';
  import { kornyezet } from '../lib/kornyezet';
  import type { Talalat } from '../lib/kereses/fuzzy';
  import Atfedes from '../lib/ui/Atfedes.svelte';
  import ListaValaszto from '../lib/ui/ListaValaszto.svelte';
  import { fajlNev, mappa, type FajlInfo } from '../lib/vault/fajlok.svelte';

  let { onvalaszt, onbezar }: { onvalaszt: (ut: string) => void; onbezar: () => void } = $props();

  const LIMIT = 50;
  const { felulet, fajlok } = kornyezet();
  let lekerdezes = $state('');

  const talalatok = $derived.by((): Talalat<FajlInfo>[] => {
    void fajlok.lista;
    const q = lekerdezes.trim();
    const rang = new Map(felulet.legutobbiFajlok.map((u, i) => [u, i]));
    if (!q) {
      const legutobbi = felulet.legutobbiFajlok.map((u) => fajlok.info(u)).filter((f): f is FajlInfo => !!f);
      const lat = new Set(legutobbi.map((f) => f.ut));
      const tobbi = fajlok.lista.filter((f) => !lat.has(f.ut)).sort((a, b) => (b.mtime ?? 0) - (a.mtime ?? 0));
      return [...legutobbi, ...tobbi].slice(0, LIMIT).map((f) => ({ ertek: f, pont: 0, kiemeles: [] }));
    }
    return fajlok.kereso().keres(q, {
      limit: LIMIT,
      bonusz: (f) => {
        const i = rang.get(f.ut);
        return i === undefined ? 0 : Math.max(5, 30 - i);
      },
    });
  });

  const ures = $derived(lekerdezes.trim() ? t('Nincs találat erre: „{kif}”', { kif: lekerdezes.trim() }) : t('A vault üres.'));
</script>

<Atfedes cimke={t('Jegyzet vagy fájl a canvasra')} nev="canvas-fajl" {onbezar}>
  <ListaValaszto
    elemek={talalatok}
    kulcs={(t) => t.ertek.ut}
    bind:lekerdezes
    helyorzo={t('Jegyzet vagy fájl keresése…')}
    cimke={t('Jegyzet vagy fájl keresése')}
    {ures}
    onvalaszt={(t) => onvalaszt(t.ertek.ut)}
    {onbezar}
  >
    {#snippet sor(t: Talalat<FajlInfo>)}
      <span class="ikon"><Ikon ikon={fajlIkon(t.ertek.tipus)} /></span>
      <span class="nev">{#if t.kiemeles.length}<Kiemelt szoveg={fajlNev(t.ertek.ut)} kiemeles={t.kiemeles} />{:else}{fajlNev(t.ertek.ut)}{/if}</span>
      <span class="ut">{mappa(t.ertek.ut)}</span>
    {/snippet}
    {#snippet lablec()}
      <span><kbd>↑↓</kbd> {t('választás')}</span>
      <span><kbd>↩</kbd> {t('a canvasra')}</span>
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

  kbd {
    color: var(--szoveg-masodlagos);
  }
</style>
