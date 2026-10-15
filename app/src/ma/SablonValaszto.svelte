<!--
  „Sablon beszúrása…” (C15): a sablonmappa jegyzeteinek listája (a core adja, `GET /api/sablon/lista`); a választás a
  nyitott jegyzet kurzorához fűzi a kiértékelt sablont. Az átfedés a gyorsváltó mintája: combobox + listbox.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { ApiHiba, kerdez } from '../lib/core/api';
  import { csend } from '../lib/elrendezes/csend.svelte';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import { FileText } from '../lib/ikon/ikonok';
  import { normalizal } from '../lib/kereses/fuzzy';
  import { kornyezet } from '../lib/kornyezet';
  import Atfedes from '../lib/ui/Atfedes.svelte';
  import ListaValaszto from '../lib/ui/ListaValaszto.svelte';
  import { sablonBeszurasAktiv } from './naplo';
  import type { SablonInfo, SablonLista } from './tipusok';

  const { felulet } = kornyezet();
  let lekerdezes = $state('');
  let lista = $state<SablonLista | null>(null);
  let hiba = $state<string | null>(null);

  onMount(() => {
    kerdez<SablonLista>('/api/sablon/lista', { idokorlat: 5000 })
      .then((l) => (lista = l))
      .catch((e) => (hiba = e instanceof ApiHiba ? e.message : String(e)));
  });

  const talalatok = $derived.by((): SablonInfo[] => {
    const q = normalizal(lekerdezes.trim());
    const mind = lista?.sablonok ?? [];
    return q ? mind.filter((s) => normalizal(s.nev).includes(q)) : mind;
  });

  const ures = $derived(
    hiba ?? (lista === null ? 'Betöltés…' : lista.sablonok.length ? `Nincs találat erre: „${lekerdezes.trim()}”` : `A sablonmappa (${lista.mappa}) még üres.`),
  );

  const ujMod = felulet.sablonUj !== null;

  function bezar() {
    felulet.atfedes = null;
    felulet.sablonUj = null;
  }

  function valaszt(s: SablonInfo) {
    const uj = felulet.sablonUj;
    bezar();
    if (uj) {
      // a fa kéri be a nevet, és a core hozza létre (C32b); a fa csendben átfedésként nyílik, mint az „Új jegyzet a fájlfában”
      felulet.oldalsav.nezet = 'fajlok';
      if (!felulet.oldalsav.nyitva) csend.oldalsavAtfedes = true;
      felulet.faUjSablon = { mappa: uj.mappa, sablon: s.ut };
    }
    else void sablonBeszurasAktiv(s.ut);
  }
</script>

<Atfedes cimke={ujMod ? "Új jegyzet sablonból" : "Sablon beszúrása"} nev="sablon" onbezar={bezar}>
  <ListaValaszto
    elemek={talalatok}
    kulcs={(s) => s.ut}
    bind:lekerdezes
    helyorzo="Sablon keresése…"
    cimke="Sablon keresése"
    {ures}
    onvalaszt={valaszt}
    onbezar={bezar}
  >
    {#snippet sor(s: SablonInfo)}
      <span class="ikon"><Ikon ikon={FileText} /></span>
      <span class="nev">{s.nev}</span>
    {/snippet}
    {#snippet lablec()}
      <span><kbd>↑↓</kbd> választás</span>
      <span><kbd>↩</kbd> {ujMod ? 'új jegyzet ebből' : 'beszúrás a kurzornál'}</span>
      <span><kbd>esc</kbd> bezárás</span>
    {/snippet}
  </ListaValaszto>
</Atfedes>

<style>
  .ikon {
    color: var(--szoveg-halvany);
  }

  .nev {
    flex: 1 1 auto;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  kbd {
    color: var(--szoveg-masodlagos);
  }
</style>
