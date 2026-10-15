<!--
  Linkeletlen említések (C10): a jegyzet neve vagy aliasa más jegyzetekben, link nélkül. Soronként egy kattintás
  a „Linkelés”: az említés `[[Név]]` (vagy `[[Név|szöveg]]`) lesz a másik jegyzetben.
-->
<script lang="ts">
  import { fajlNev, mappa } from '../../lib/vault/fajlok.svelte';
  import { kornyezetReszek, type Emlites, type EmlitesForras } from '../../lib/vault/kapcsolatok.svelte';

  let {
    forrasok,
    onlinkel,
    onnyit,
  }: {
    forrasok: EmlitesForras[];
    onlinkel: (forras: string, t: Emlites) => void | Promise<void>;
    onnyit: (ut: string, sor: number | null, e: MouseEvent) => void;
  } = $props();

  let folyamatban = $state<string | null>(null);

  async function linkel(ut: string, t: Emlites) {
    const kulcs = `${ut}:${t.sor}:${t.oszlop}`;
    folyamatban = kulcs;
    try {
      await onlinkel(ut, t);
    } finally {
      folyamatban = null;
    }
  }
</script>

{#if !forrasok.length}
  <p class="ures">Nincs linkeletlen említés.</p>
{:else}
  <ul class="forrasok">
    {#each forrasok as f (f.ut)}
      <li class="forras">
        <button type="button" class="fej" title={f.ut} onclick={(e) => onnyit(f.ut, f.talalatok[0]?.sor ?? null, e)}>
          <span class="nev">{fajlNev(f.ut)}</span>
          {#if mappa(f.ut)}<span class="mappa">{mappa(f.ut)}</span>{/if}
        </button>
        <ul class="talalatok">
          {#each f.talalatok as t (`${t.sor}:${t.oszlop}`)}
            {@const r = kornyezetReszek(t.szoveg, t.oszlop, t.hossz)}
            <li class="talalat">
              <span class="szoveg">{r.elotte.trimStart().slice(-50)}<mark>{r.link}</mark>{r.utana.slice(0, 70)}</span>
              <button
                type="button"
                class="linkel"
                disabled={folyamatban !== null}
                aria-label={`Linkelés: ${r.link} a(z) ${fajlNev(f.ut)} jegyzetben`}
                onclick={() => linkel(f.ut, t)}
              >
                {folyamatban === `${f.ut}:${t.sor}:${t.oszlop}` ? '…' : 'Linkelés'}
              </button>
            </li>
          {/each}
        </ul>
      </li>
    {/each}
  </ul>
{/if}

<style>
  .ures {
    margin: 0;
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
  }

  ul {
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .forras + .forras {
    margin-top: var(--t-2);
  }

  .fej {
    display: flex;
    align-items: baseline;
    gap: var(--t-2);
    width: 100%;
    padding: 2px var(--t-1);
    border-radius: var(--kerekites-kicsi);
    text-align: left;
    font-size: var(--betu-ui);
    color: var(--szoveg-masodlagos);
    font-weight: var(--suly-kozepes);
  }

  .fej:hover {
    background: var(--hatter-hover);
  }

  .nev {
    flex: none;
    max-width: 70%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .mappa {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--szoveg-halvany);
    font-weight: normal;
    font-size: var(--betu-kicsi);
  }

  .talalatok {
    padding-left: var(--t-3);
    margin-left: var(--t-1);
    border-left: 1px solid var(--keret);
  }

  .talalat {
    display: flex;
    align-items: flex-start;
    gap: var(--t-2);
    padding: 2px var(--t-1);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
    color: var(--szoveg-halvany);
  }

  .szoveg {
    flex: 1;
    min-width: 0;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    overflow-wrap: anywhere;
  }

  mark {
    padding: 0 1px;
    border-radius: var(--kerekites-jel);
    background: var(--jeloles-hatter);
    color: var(--szoveg);
  }

  .linkel {
    flex: none;
    padding: 0 var(--t-2);
    border-radius: var(--kerekites-kicsi);
    background: var(--hatter-hover);
    color: var(--akcent-szoveg);
    font-size: var(--betu-kicsi);
  }

  .linkel:hover:not(:disabled) {
    background: var(--hatter-aktiv);
  }

  .linkel:disabled {
    opacity: var(--tiltott-atlatszosag);
  }
</style>
