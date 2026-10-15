<!--
  ⌘P parancspaletta: a regiszter elérhető parancsai. Üres lekérdezésnél a legutóbbiak elöl, utána
  kategória és név szerint; gépeléskor ugyanaz az ékezetfüggetlen, elírástűrő keresés, mint a váltóban.
-->
<script lang="ts">
  import { onDestroy } from 'svelte';
  import { fokuszban } from '../lib/fokusz/fokusz';
  import { kornyezet } from '../lib/kornyezet';
  import { FuzzyIndex, type Talalat } from '../lib/kereses/fuzzy';
  import { regiszter, type Parancs } from '../lib/parancsok/regiszter';
  import Atfedes from '../lib/ui/Atfedes.svelte';
  import Billentyu from '../lib/ui/Billentyu.svelte';
  import ListaValaszto from '../lib/ui/ListaValaszto.svelte';
  import Kiemelt from './Kiemelt.svelte';

  const { felulet } = kornyezet();
  let lekerdezes = $state('');
  let valtozat = $state(0);
  onDestroy(regiszter.feliratkoz(() => valtozat++));

  const rendezo = new Intl.Collator('hu', { sensitivity: 'base' });
  const parancsok = $derived.by(() => {
    void valtozat;
    return regiszter.lista();
  });
  const kereso = $derived(
    new FuzzyIndex(parancsok.map((p) => ({ ertek: p, nev: p.nev, ut: p.kategoria ?? '' }))),
  );

  const talalatok = $derived.by((): Talalat<Parancs>[] => {
    const legutobbi = felulet.legutobbiParancsok;
    const q = lekerdezes.trim();
    if (!q) {
      const rang = new Map(legutobbi.map((id, i) => [id, i]));
      return [...parancsok]
        .sort(
          (a, b) =>
            (rang.get(a.id) ?? 1e6) - (rang.get(b.id) ?? 1e6) ||
            rendezo.compare(a.kategoria ?? '', b.kategoria ?? '') ||
            rendezo.compare(a.nev, b.nev),
        )
        .map((p) => ({ ertek: p, pont: 0, kiemeles: [] }));
    }
    const rang = new Map(legutobbi.map((id, i) => [id, i]));
    return kereso.keres(q, {
      limit: 100,
      bonusz: (p) => {
        const i = rang.get(p.id);
        return i === undefined ? 0 : Math.max(5, 20 - i);
      },
    });
  });

  function bezar() {
    felulet.atfedes = null;
  }

  // A megnyitó (pl. a szerkesztő) — init közben, a mező autofókusza előtt. A fókusz a záró animáció végén térne vissza
  // rá (`csapda`), a szerkesztő-fókuszt kívánó parancsok (Félkövér, ⌘K, Wikilink…) addig csendben nem futnának.
  const megnyito = fokuszban();

  function valaszt(t: Talalat<Parancs>) {
    bezar();
    // a paletta bezárása után fusson (a parancs nyithat másik réteget), a fókusz már a megnyitón
    setTimeout(() => {
      if (megnyito?.isConnected && document.activeElement !== megnyito) megnyito.focus({ preventScroll: true });
      regiszter.futtat(t.ertek.id, 'paletta');
    }, 0);
  }
</script>

<Atfedes cimke="Parancspaletta" nev="paletta" onbezar={bezar}>
  <ListaValaszto
    elemek={talalatok}
    kulcs={(t) => t.ertek.id}
    bind:lekerdezes
    helyorzo="Parancs keresése…"
    cimke="Parancs keresése"
    ures={`Nincs ilyen parancs: „${lekerdezes.trim()}”`}
    onvalaszt={valaszt}
    onbezar={bezar}
  >
    {#snippet sor(t: Talalat<Parancs>)}
      {#if t.ertek.kategoria}<span class="kategoria">{t.ertek.kategoria}</span>{/if}
      <span class="nev"><Kiemelt szoveg={t.ertek.nev} kiemeles={t.kiemeles} /></span>
      {#if t.ertek.billentyu}<span class="billentyu"><Billentyu akkord={t.ertek.billentyu} /></span>{/if}
    {/snippet}
    {#snippet lablec()}
      <span><kbd>↑↓</kbd> választás</span>
      <span><kbd>↩</kbd> futtatás</span>
      <span><kbd>esc</kbd> bezárás</span>
    {/snippet}
  </ListaValaszto>
</Atfedes>

<style>
  .kategoria {
    flex: none;
    color: var(--szoveg-halvany);
  }

  .kategoria::after {
    content: ':';
  }

  .nev {
    flex: 1 1 0;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .billentyu {
    flex: none;
    display: flex;
  }

  kbd {
    color: var(--szoveg-masodlagos);
  }
</style>
