<!--
  Kimenő linkeletlen említések (02-links-10): más jegyzetek neve vagy aliasa ebben a jegyzetben, link nélkül. Soronként egy
  „Linkelés” gomb: az említés a beállított alakú linkké (`[[Név]]` vagy `[szöveg](Név.md)`) alakul ebben a jegyzetben.
-->
<script lang="ts">
  import { t } from '../../lib/i18n';
  import { fajlNev, mappa } from '../../lib/vault/fajlok.svelte';
  import { kornyezetReszek, type KimenoEmlites, type KimenoEmlitesForras } from '../../lib/vault/kapcsolatok.svelte';

  let {
    forrasok,
    onlinkel,
  }: {
    forrasok: KimenoEmlitesForras[];
    /** a megemlített jegyzet útja és az említés */
    onlinkel: (celUt: string, em: KimenoEmlites) => void | Promise<void>;
  } = $props();

  let folyamatban = $state<string | null>(null);

  async function linkel(ut: string, em: KimenoEmlites) {
    folyamatban = `${ut}:${em.sor}:${em.oszlop}`;
    try {
      await onlinkel(ut, em);
    } finally {
      folyamatban = null;
    }
  }
</script>

{#if forrasok.length}
  <p class="cim">{t('Említett, még nem linkelt jegyzetek')}</p>
  <ul class="forrasok">
    {#each forrasok as f (f.ut)}
      <li class="forras" data-elonezet-ut={f.ut}>
        <span class="fej" title={f.ut}>
          <span class="nev">{fajlNev(f.ut)}</span>
          {#if mappa(f.ut)}<span class="mappa">{mappa(f.ut)}</span>{/if}
        </span>
        <ul class="talalatok">
          {#each f.talalatok as ta (`${ta.sor}:${ta.oszlop}`)}
            {@const r = kornyezetReszek(ta.szoveg, ta.oszlop, ta.hossz)}
            <li class="talalat">
              <span class="szoveg">{r.elotte.trimStart().slice(-50)}<mark>{r.link}</mark>{r.utana.slice(0, 70)}</span>
              <button
                type="button"
                class="linkel"
                disabled={folyamatban !== null}
                aria-label={t('Linkelés: {link} → {fajl}', { link: r.link, fajl: fajlNev(f.ut) })}
                onclick={() => linkel(f.ut, ta)}
              >
                {folyamatban === `${f.ut}:${ta.sor}:${ta.oszlop}` ? '…' : t('Linkelés')}
              </button>
            </li>
          {/each}
        </ul>
      </li>
    {/each}
  </ul>
{/if}

<style>
  .cim {
    margin: var(--t-2) 0 var(--t-1);
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
    padding: 2px var(--t-1);
    color: var(--szoveg-masodlagos);
    font-size: var(--betu-ui);
    font-weight: var(--suly-kozepes);
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
    border-left: 1px solid var(--keret);
    margin-left: var(--t-1);
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
