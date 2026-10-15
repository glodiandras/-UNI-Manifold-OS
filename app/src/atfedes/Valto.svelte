<!--
  ⌘O gyorsváltó: a vault fájljai a core indexéből. Üres lekérdezésnél a legutóbbiak, utána a többi
  módosítás szerint; gépeléskor ékezetfüggetlen, elírástűrő keresés, a legutóbbiak előnyt kapnak.
-->
<script lang="ts">
  import Ikon from '../lib/ikon/Ikon.svelte';
  import { fajlIkon } from '../lib/ikon/fajlIkon';
  import { kornyezet } from '../lib/kornyezet';
  import type { Talalat } from '../lib/kereses/fuzzy';
  import Atfedes from '../lib/ui/Atfedes.svelte';
  import Billentyu from '../lib/ui/Billentyu.svelte';
  import Kiemelt from './Kiemelt.svelte';
  import ListaValaszto, { type Modositok } from '../lib/ui/ListaValaszto.svelte';
  import { fajlNev, mappa, type FajlInfo } from '../lib/vault/fajlok.svelte';

  const LIMIT = 50;
  const { felulet, fajlok } = kornyezet();
  let lekerdezes = $state('');

  const talalatok = $derived.by((): Talalat<FajlInfo>[] => {
    void fajlok.lista;
    const legutobbi = felulet.legutobbiFajlok;
    const q = lekerdezes.trim();
    if (!q) {
      const lat = new Set<string>();
      const ki: Talalat<FajlInfo>[] = [];
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
    return fajlok.kereso().keres(q, {
      limit: LIMIT,
      bonusz: (f) => {
        const i = rang.get(f.ut);
        return i === undefined ? 0 : Math.max(5, 30 - i);
      },
    });
  });

  const ures = $derived(
    fajlok.index && !fajlok.index.kesz
      ? 'Az index még épül…'
      : lekerdezes.trim()
        ? `Nincs találat erre: „${lekerdezes.trim()}”`
        : 'A vault üres.',
  );

  function bezar() {
    felulet.atfedes = null;
  }

  function valaszt(t: Talalat<FajlInfo>, m: Modositok) {
    bezar();
    felulet.munkaterulet.megnyit(t.ertek.ut, m.oszt ? 'osztas' : m.uj ? 'ujful' : 'aktiv');
  }
</script>

<Atfedes cimke="Gyorsváltó" nev="valto" onbezar={bezar}>
  <ListaValaszto
    elemek={talalatok}
    kulcs={(t) => t.ertek.ut}
    bind:lekerdezes
    helyorzo="Fájl keresése…"
    cimke="Fájl keresése"
    {ures}
    onvalaszt={valaszt}
    onbezar={bezar}
  >
    {#snippet sor(t: Talalat<FajlInfo>)}
      <span class="ikon"><Ikon ikon={fajlIkon(t.ertek.tipus)} /></span>
      <span class="nev">{#if t.kiemeles.length}<Kiemelt szoveg={fajlNev(t.ertek.ut)} kiemeles={t.kiemeles} />{:else}{fajlNev(t.ertek.ut)}{/if}</span>
      <span class="ut">{mappa(t.ertek.ut)}</span>
    {/snippet}
    {#snippet lablec()}
      <span><kbd>↑↓</kbd> választás</span>
      <span><kbd>↩</kbd> megnyitás</span>
      <span><Billentyu akkord="Mod+Enter" /> új fülben</span>
      <span><Billentyu akkord="Mod+Alt+Enter" /> osztásban</span>
      <span><kbd>esc</kbd> bezárás</span>
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
