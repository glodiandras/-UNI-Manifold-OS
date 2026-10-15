<!--
  Az oszlopok kijelölése és sorrendje (C12b): a megjelenített oszlopok fent (↑↓ a sorrendhez), alattuk a vault többi
  tulajdonsága (file.*, a frontmatter kulcsai, a képletek). A kijelölés a nézet `order` listáját írja.
-->
<script lang="ts">
  import Ikon from '../lib/ikon/Ikon.svelte';
  import { ArrowDown, ArrowUp } from '../lib/ikon/ikonok';
  import type { BazisModell } from './modell.svelte';
  import { oszlopAzonok, oszlopKapcsol, oszlopMozgat, sorrendBeallit } from './muveletek';
  import type { Elerheto, Valasz } from './tipusok';

  let { modell, v }: { modell: BazisModell; v: Valasz } = $props();

  let kereso = $state('');
  const nezet = $derived(v.nezet?.index ?? 0);
  const lathato = $derived(oszlopAzonok(v));
  const elerheto = $derived.by((): Elerheto[] => {
    const ki = [...(v.fajl?.elerheto ?? [])];
    for (const o of v.oszlopok) if (!ki.some((e) => e.id === o.id)) ki.push({ id: o.id, nev: o.nev, ter: o.ter, tipus: o.tipus });
    return ki;
  });
  const szur = (e: { nev: string; id: string }) => {
    const k = kereso.trim().toLowerCase();
    return !k || e.nev.toLowerCase().includes(k) || e.id.toLowerCase().includes(k);
  };
  const megjelenitett = $derived(
    lathato
      .map((id) => ({ id, nev: v.oszlopok.find((o) => o.id === id)?.nev ?? id, tipus: v.oszlopok.find((o) => o.id === id)?.tipus ?? '' }))
      .filter(szur),
  );
  const tobbi = $derived(elerheto.filter((e) => !lathato.includes(e.id)).filter(szur));

  function kapcsol(id: string, be: boolean) {
    void modell.alkalmaz(sorrendBeallit(nezet, oszlopKapcsol(lathato, id, be)));
  }

  function mozgat(id: string, d: number) {
    const i = lathato.indexOf(id);
    void modell.alkalmaz(sorrendBeallit(nezet, oszlopMozgat(lathato, id, i + d)));
  }
</script>

<div class="oszlopok">
  <input class="kereso" type="search" placeholder="Tulajdonság keresése" aria-label="Tulajdonság keresése" bind:value={kereso} />
  <h4>Megjelenített</h4>
  <ul>
    {#each megjelenitett as o, i (o.id)}
      <li>
        <label>
          <input type="checkbox" checked onchange={() => kapcsol(o.id, false)} />
          <span class="nev">{o.nev}</span>
          <span class="tipus">{o.tipus}</span>
        </label>
        {#if !kereso}
          <button type="button" class="mozgat" aria-label="{o.nev} feljebb" disabled={i === 0} onclick={() => mozgat(o.id, -1)}>
            <Ikon ikon={ArrowUp} meret={14} />
          </button>
          <button type="button" class="mozgat" aria-label="{o.nev} lejjebb" disabled={i === lathato.length - 1} onclick={() => mozgat(o.id, 1)}>
            <Ikon ikon={ArrowDown} meret={14} />
          </button>
        {/if}
      </li>
    {:else}
      <li class="ures">Nincs megjelenített oszlop.</li>
    {/each}
  </ul>
  {#if tobbi.length}
    <h4>További tulajdonságok</h4>
    <ul>
      {#each tobbi as e (e.id)}
        <li>
          <label>
            <input type="checkbox" onchange={() => kapcsol(e.id, true)} />
            <span class="nev">{e.nev}</span>
            <span class="tipus">{e.tipus}</span>
          </label>
        </li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  .oszlopok {
    display: flex;
    flex-direction: column;
    gap: var(--t-1);
  }

  .kereso {
    box-sizing: border-box;
    width: 100%;
    height: 26px;
    padding: 0 var(--t-2);
    border: 1px solid var(--keret-mezo);
    border-radius: var(--kerekites-kicsi);
    background: var(--hatter);
    color: var(--szoveg);
    font: inherit;
  }

  h4 {
    margin: var(--t-2) 0 0;
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
    font-weight: var(--suly-kozepes);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  ul {
    margin: 0;
    padding: 0;
    list-style: none;
  }

  li {
    display: flex;
    align-items: center;
    min-height: 26px;
  }

  label {
    flex: 1;
    display: flex;
    align-items: center;
    gap: var(--t-2);
    min-width: 0;
    cursor: pointer;
  }

  .nev {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .tipus {
    margin-left: auto;
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
  }

  .mozgat {
    display: grid;
    place-items: center;
    width: var(--magassag-suru);
    height: var(--magassag-suru);
    border: 0;
    border-radius: var(--kerekites-kicsi);
    background: transparent;
    color: var(--szoveg-halvany);
    cursor: pointer;
  }

  .mozgat:hover:not(:disabled) {
    background: var(--hatter-hover);
    color: var(--szoveg);
  }

  .mozgat:disabled {
    opacity: var(--tiltott-atlatszosag);
    cursor: default;
  }

  .ures {
    color: var(--szoveg-halvany);
  }
</style>
