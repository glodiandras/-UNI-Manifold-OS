<!--
  Kimenő linkek (C10): a jegyzet linkjei; a feloldottak megnyithatók, a feloldatlanok külön, kattintásra
  létrejön az új jegyzet. Ugyanaz a cél egyszer szerepel (a beágyazás jelölve).
-->
<script lang="ts">
  import { t } from '../../lib/i18n';
  import Ikon from '../../lib/ikon/Ikon.svelte';
  import { fajlIkon } from '../../lib/ikon/fajlIkon';
  import { Plus } from '../../lib/ikon/ikonok';
  import { fajlNev, type FajlInfo } from '../../lib/vault/fajlok.svelte';
  import type { KimenoLink } from '../../lib/vault/kapcsolatok.svelte';

  let {
    linkek,
    info,
    onnyit,
    onletrehoz,
  }: {
    linkek: KimenoLink[];
    info: (ut: string) => FajlInfo | undefined;
    onnyit: (l: KimenoLink, e: MouseEvent) => void;
    onletrehoz: (l: KimenoLink) => void;
  } = $props();

  const egyedi = $derived.by(() => {
    const lat = new Set<string>();
    const ki: KimenoLink[] = [];
    for (const l of linkek) {
      const k = `${l.cel ?? `?${l.cel_nyers}`}#${l.alcel ?? ''}:${l.beagyazas}`;
      if (lat.has(k)) continue;
      lat.add(k);
      ki.push(l);
    }
    return ki;
  });
  const feloldott = $derived(egyedi.filter((l) => l.cel));
  const feloldatlan = $derived(egyedi.filter((l) => !l.cel && l.cel_nyers.trim()));
</script>

{#if !feloldott.length && !feloldatlan.length}
  <p class="ures">{t('A jegyzetből nem mutat link.')}</p>
{/if}
{#if feloldott.length}
  <ul>
    {#each feloldott as l, i (i)}
      <li>
        <button type="button" class="sor" title={l.cel ?? ''} onclick={(e) => onnyit(l, e)}>
          <Ikon ikon={fajlIkon(info(l.cel!)?.tipus)} meret={14} />
          <span class="nev">{fajlNev(l.cel!)}{l.alcel ? ` › ${l.alcel}` : ''}</span>
          {#if l.beagyazas}<span class="jel">{t('beágyazás')}</span>{/if}
          {#if l.tulajdonsag}<span class="jel">{l.tulajdonsag}</span>{/if}
        </button>
      </li>
    {/each}
  </ul>
{/if}
{#if feloldatlan.length}
  <p class="cim">{t('Feloldatlan')}</p>
  <ul>
    {#each feloldatlan as l, i (i)}
      <li>
        <button type="button" class="sor hianyzo" title={t('Új jegyzet létrehozása')} onclick={() => onletrehoz(l)}>
          <Ikon ikon={Plus} meret={14} />
          <span class="nev">{l.cel_nyers.trim()}</span>
        </button>
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

  .cim {
    margin: var(--t-2) 0 var(--t-1);
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
    text-transform: none;
  }

  ul {
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .sor {
    display: flex;
    align-items: center;
    gap: var(--t-2);
    width: 100%;
    padding: 2px var(--t-1);
    border-radius: var(--kerekites-kicsi);
    text-align: left;
    font-size: var(--betu-ui);
    color: var(--szoveg-masodlagos);
  }

  .sor:hover {
    background: var(--hatter-hover);
    color: var(--szoveg);
  }

  .hianyzo {
    color: var(--szoveg-halvany);
  }

  .nev {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .jel {
    flex: none;
    padding: 0 var(--t-1);
    border-radius: var(--kerekites-kicsi);
    background: var(--hatter-aktiv);
    color: var(--szoveg-masodlagos);
    font-size: var(--betu-kicsi);
  }
</style>
