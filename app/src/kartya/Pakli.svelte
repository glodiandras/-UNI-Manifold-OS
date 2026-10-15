<!--
  A kártyák ismétlése (C23b; docs/C23-TERV.md 7.): a beágyazott pakli a jegyzetben és a „Mai ismétlés” a vezérlőben.
  Kérdés → szóköz/Enter fordít → 1–4 értékel (a gombon a következő intervallum), ⌘Z az utolsó értékelést vonja vissza.
  A szöveg a vault aktuális fájljából, az állapot a core-ból; csak tokenekből rajzol (25. döntés).
-->
<script lang="ts">
  import { tick } from 'svelte';
  import { md } from '../kviz/megjelenites';
  import { linkMegnyit, nyitasMod } from '../szerkeszto/linkek/navigacio';
  import { GOMBOK, intervallum } from './allando';
  import type { IsmetlesMenet } from './menet.svelte';

  let { menet, forras = '', cim = '' }: { menet: IsmetlesMenet; forras?: string; cim?: string } = $props();

  let gyoker: HTMLDivElement | undefined = $state();
  const k = $derived(menet.aktualis);

  $effect(() => {
    void menet.fazis;
    void menet.i;
    if (menet.fazis !== 'kerdes' && menet.fazis !== 'valasz') return;
    void tick().then(() => (gyoker?.querySelector<HTMLElement>('[data-fokusz]') ?? gyoker)?.focus({ preventScroll: true }));
  });

  function billentyu(e: KeyboardEvent) {
    if (menet.billentyu(e)) {
      e.preventDefault();
      e.stopPropagation();
    }
  }

  function forrasNyit(e: MouseEvent, link: string) {
    e.preventDefault();
    const [cel, ...al] = link.split('#');
    void linkMegnyit({ forras: k?.jegyzet ?? forras, cel, alcel: al.length ? al.join('#') : null }, nyitasMod(e));
  }

  function forrasNev(link: string): string {
    const [cel, al] = link.split('#');
    const nev = cel.split('/').at(-1) ?? cel;
    return al && !al.startsWith('^') ? `${nev} › ${al}` : nev;
  }
</script>

<!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions (a blokk saját billentyűit kezeli: szóköz, Enter, 1–4, ⌘Z) -->
<div class="pakli" bind:this={gyoker} tabindex="-1" role="group" aria-label={cim ? `Kártyák: ${cim}` : 'Kártyák'} lang="hu" onkeydown={billentyu}>
  {#if menet.fazis === 'betolt'}
    <p class="pakli-al">Kártyák betöltése…</p>
  {:else if menet.fazis === 'hiba'}
    <p class="pakli-hiba">A kártyák nem tölthetők be: {menet.hiba}</p>
    <button class="m-gomb semleges suru" type="button" onclick={() => menet.betolt()}>Újra</button>
  {:else if menet.fazis === 'ures'}
    <p class="pakli-al">
      Ma nincs esedékes kártya{menet.osszes ? ` · ${menet.osszes} kártya összesen` : ''}.
    </p>
  {:else if menet.fazis === 'kesz'}
    <p class="pakli-al">Kész: {menet.kesz} kártya ismételve. <span class="halvany">⌘Z: az utolsó értékelés visszavonása</span></p>
  {:else if k}
    <div class="pakli-fej">
      {#if cim}<span class="pakli-cim">{cim}</span>{/if}
      <span class="halvany szam">{menet.hatra} hátra{k.uj ? ' · új' : ''}</span>
    </div>
    <div class="pakli-kerdes" use:md={{ szoveg: k.kerdes, ut: k.jegyzet }}></div>
    {#if menet.fazis === 'kerdes'}
      <button class="m-gomb semleges suru" type="button" data-fokusz onclick={() => menet.fordit()}>Válasz <kbd>szóköz</kbd></button>
    {:else}
      <div class="pakli-valasz" use:md={{ szoveg: k.valasz, ut: k.jegyzet }}></div>
      {#if k.forras}
        <a class="pakli-forras" href={`#${k.forras}`} onclick={(e) => forrasNyit(e, k.forras!)}>— {forrasNev(k.forras)}</a>
      {/if}
      <div class="pakli-gombok" role="group" aria-label="Értékelés">
        {#each GOMBOK as g (g.jegy)}
          <button class="m-gomb semleges suru" type="button" disabled={menet.kuld} data-fokusz={g.jegy === 3 ? '' : undefined}
                  onclick={() => menet.ertekel(g.jegy)}>
            <span>{g.nev}</span>
            <span class="halvany szam">{intervallum(k.elorejelzes?.[String(g.jegy)])}</span>
            <kbd>{g.jegy}</kbd>
          </button>
        {/each}
      </div>
    {/if}
    {#if menet.hiba}<p class="pakli-hiba">{menet.hiba}</p>{/if}
  {/if}
</div>

<style>
  .pakli {
    display: flex;
    flex-direction: column;
    gap: var(--t-2);
    padding: var(--t-3) var(--t-4);
    border: var(--keret-vastag) solid var(--keret);
    border-radius: var(--kerekites);
    background: var(--hatter-emelt);
    color: var(--szoveg);
    font-size: var(--betu-ui);
    line-height: var(--sor-ui);
  }

  .pakli:focus-visible {
    outline: var(--fokusz-vastag) solid var(--fokusz-gyuru);
    outline-offset: var(--fokusz-tav);
  }

  .pakli-fej {
    display: flex;
    justify-content: space-between;
    gap: var(--t-2);
  }

  .pakli-cim {
    font-weight: var(--suly-felkover);
  }

  .pakli-kerdes {
    font-size: var(--betu-torzs);
    line-height: var(--sor-torzs);
    font-weight: var(--suly-kozepes);
  }

  .pakli-valasz {
    padding-top: var(--t-2);
    border-top: var(--keret-vastag) solid var(--keret);
    font-size: var(--betu-torzs);
    line-height: var(--sor-torzs);
  }

  .pakli-kerdes :global(p),
  .pakli-valasz :global(p) {
    margin: 0;
  }

  .pakli-forras {
    color: var(--szoveg-masodlagos);
    font-size: var(--betu-kicsi);
    text-decoration: none;
  }

  .pakli-forras:hover {
    color: var(--akcent-szoveg);
  }

  .pakli-gombok {
    display: flex;
    flex-wrap: wrap;
    gap: var(--t-2);
  }

  .pakli-gombok .m-gomb {
    display: inline-flex;
    align-items: center;
    gap: var(--t-1);
  }

  .pakli-al {
    margin: 0;
    color: var(--szoveg-masodlagos);
  }

  .pakli-hiba {
    margin: 0;
    color: var(--hiba);
  }

  .halvany {
    color: var(--szoveg-halvany);
  }

  .szam {
    font-variant-numeric: tabular-nums;
  }

  kbd {
    padding: 0 var(--t-1);
    border: var(--keret-vastag) solid var(--keret-eros);
    border-radius: var(--kerekites-kicsi);
    font: inherit;
    font-size: var(--betu-kicsi);
  }
</style>
