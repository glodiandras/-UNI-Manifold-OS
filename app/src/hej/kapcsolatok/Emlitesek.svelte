<!--
  Linkeletlen említések (C10): a jegyzet neve vagy aliasa más jegyzetekben, link nélkül. Soronként egy kattintás
  a „Linkelés”: az említés `[[Név]]` (vagy `[[Név|szöveg]]`) lesz a másik jegyzetben.
-->
<script lang="ts">
  import { t } from '../../lib/i18n';
  import { fajlNev, mappa } from '../../lib/vault/fajlok.svelte';
  import { kornyezetReszek, type Emlites, type EmlitesForras } from '../../lib/vault/kapcsolatok.svelte';
  import { szuroEgyezik, szuroSzavak } from './szuro';

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

  // 02-links-11: szűrőmező — a jegyzet neve/útja vagy az említés sora
  let szuro = $state('');
  const szavak = $derived(szuroSzavak(szuro));
  const latszo = $derived.by(() => {
    if (!szavak.length) return forrasok;
    const ki: EmlitesForras[] = [];
    for (const f of forrasok) {
      if (szuroEgyezik(szavak, f.ut)) ki.push(f);
      else {
        const talalatok = f.talalatok.filter((ta) => szuroEgyezik(szavak, f.ut, ta.szoveg));
        if (talalatok.length) ki.push({ ...f, talalatok });
      }
    }
    return ki;
  });

  async function linkel(ut: string, em: Emlites) {
    const kulcs = `${ut}:${em.sor}:${em.oszlop}`;
    folyamatban = kulcs;
    try {
      await onlinkel(ut, em);
    } finally {
      folyamatban = null;
    }
  }
</script>

{#if !forrasok.length}
  <p class="ures">{t('Nincs linkeletlen említés.')}</p>
{:else}
  <input class="szuro" type="search" bind:value={szuro} placeholder={t('Szűrés…')} aria-label={t('Említések szűrése')} spellcheck="false" />
  {#if !latszo.length}<p class="ures" aria-live="polite">{t('Nincs találat.')}</p>{/if}
  <ul class="forrasok">
    {#each latszo as f (f.ut)}
      <li class="forras" data-elonezet-ut={f.ut}>
        <button type="button" class="fej" title={f.ut} onclick={(e) => onnyit(f.ut, f.talalatok[0]?.sor ?? null, e)} onauxclick={(e) => e.button === 1 && onnyit(f.ut, f.talalatok[0]?.sor ?? null, e)}>
          <span class="nev">{fajlNev(f.ut)}</span>
          {#if mappa(f.ut)}<span class="mappa">{mappa(f.ut)}</span>{/if}
        </button>
        <ul class="talalatok">
          {#each f.talalatok as ta (`${ta.sor}:${ta.oszlop}`)}
            {@const r = kornyezetReszek(ta.szoveg, ta.oszlop, ta.hossz)}
            <li class="talalat">
              <span class="szoveg">{r.elotte.trimStart().slice(-50)}<mark>{r.link}</mark>{r.utana.slice(0, 70)}</span>
              <button
                type="button"
                class="linkel"
                disabled={folyamatban !== null}
                aria-label={t('Linkelés: {link} a(z) {fajl} jegyzetben', { link: r.link, fajl: fajlNev(f.ut) })}
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
  .szuro {
    width: 100%;
    height: var(--magassag-gomb);
    margin-bottom: var(--t-2);
    padding: 0 var(--t-2);
    border: 1px solid var(--keret-mezo);
    border-radius: var(--kerekites);
    background: var(--hatter);
    color: var(--szoveg);
    font-size: var(--betu-ui);
  }

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
