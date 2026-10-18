<!--
  Excluded files (14-appearance-06): útvonal-előtagok vagy /regex/ minták listája. A lista csak LÁTHATÓSÁGOT szűr: a fájl nem törlődik,
  nem költözik, a link rá feloldódik; a fán halvány, a keresésből, a gráfból, a gyorsváltóból és a linkeletlen említésekből kimarad.
  A találatok számát és a minta érvényességét a core számolja (`POST /api/beallitasok/kizart-elonezet`), így nincs másik illesztő a felületen.
-->
<script lang="ts">
  import { onDestroy } from 'svelte';
  import { t, tk } from '../lib/i18n';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import { CircleAlert, Plus, X } from '../lib/ikon/ikonok';
  import { beallitasokApi, type KizartElonezet } from '../lib/beallitasok/api';

  let { lista = $bindable([]), tiltott = false, ervenytelen = $bindable(false) }: { lista?: string[]; tiltott?: boolean; ervenytelen?: boolean } = $props();

  const azonosito = $props.id();
  let uj = $state('');
  let elonezet = $state<KizartElonezet | null>(null);
  let nemElerheto = $state(false);
  let sorszam = 0;
  let kesleltetes: ReturnType<typeof setTimeout> | null = null;

  const HIBAK: Record<string, string> = {
    ures: tk('beallitasok.kizart_hiba_ures'), hossz: tk('beallitasok.kizart_hiba_hossz'), vezerlo_karakter: tk('beallitasok.kizart_hiba_vezerlo'),
    regex: tk('beallitasok.kizart_hiba_regex'), regex_veszelyes: tk('beallitasok.kizart_hiba_regex_veszelyes'), ut: tk('beallitasok.kizart_hiba_ut'),
  };
  const hibaSzoveg = (kod: string) => t(HIBAK[kod] ?? tk('beallitasok.kizart_hiba_tipus'));
  const sorEredmeny = (minta: string) => elonezet?.mintak.find((m) => m.minta === minta);
  $effect(() => { ervenytelen = !!elonezet?.mintak.some((m) => m.hiba); });

  $effect(() => {
    const mintak = [...lista];
    if (kesleltetes) clearTimeout(kesleltetes);
    const n = ++sorszam;
    kesleltetes = setTimeout(() => {
      beallitasokApi.kizartElonezet(mintak).then(
        (v) => { if (n === sorszam) { elonezet = v; nemElerheto = false; } },
        () => { if (n === sorszam) { elonezet = null; nemElerheto = true; } },
      );
    }, 200);
  });
  onDestroy(() => { sorszam++; if (kesleltetes) clearTimeout(kesleltetes); });

  function hozzaad() {
    const minta = uj.trim();
    if (!minta) return;
    if (!lista.includes(minta)) lista = [...lista, minta];
    uj = '';
  }
  function torol(minta: string) { lista = lista.filter((x) => x !== minta); }
</script>

<div class="kizart">
  <p id="{azonosito}-cim" class="cim">{t('beallitasok.kizart')}</p>
  <p class="leiras">{t('beallitasok.kizart_leiras')}</p>
  <div class="uj">
    <input type="text" bind:value={uj} spellcheck="false" autocomplete="off" disabled={tiltott} aria-label={t('beallitasok.kizart_uj')}
      placeholder={t('beallitasok.kizart_helyorzo')}
      onkeydown={(e) => { if (e.key === 'Enter') { e.preventDefault(); hozzaad(); } }} />
    <button type="button" class="m-gomb semleges" disabled={tiltott || !uj.trim()} onclick={hozzaad}><Ikon ikon={Plus} /> {t('beallitasok.kizart_hozzaad')}</button>
  </div>
  <ul aria-labelledby="{azonosito}-cim">
    {#each lista as minta (minta)}
      {@const e = sorEredmeny(minta)}
      <li>
        <code>{minta}</code>
        {#if e?.hiba}
          <span class="hiba" role="alert"><Ikon ikon={CircleAlert} /> {hibaSzoveg(e.hiba)}</span>
        {:else if e}
          <span class="db">{t('{n} találat', { n: e.db })}</span>
        {/if}
        <button type="button" class="m-gomb semleges suru" disabled={tiltott} aria-label={t('Eltávolítás: {minta}', { minta })} onclick={() => torol(minta)}><Ikon ikon={X} /></button>
      </li>
    {:else}
      <li class="ures">{t('beallitasok.kizart_ures')}</li>
    {/each}
  </ul>
  {#if elonezet}
    <p class="osszesites" role="status">{t('{n} / {m} fájl kizárva', { n: elonezet.kizart, m: elonezet.osszes })}</p>
  {:else if nemElerheto && lista.length}
    <p class="leiras" role="status">{t('beallitasok.kizart_nincs_index')}</p>
  {/if}
</div>

<style>
  .kizart { padding: var(--t-3) 0; }
  .cim { margin: 0 0 var(--t-1); font-weight: var(--suly-kozepes); }
  .leiras { margin: 0 0 var(--t-3); color: var(--szoveg-masodlagos); font-size: var(--betu-kicsi); }
  .uj { display: flex; align-items: center; gap: var(--t-3); }
  input { flex: 1; min-width: 0; padding: var(--t-2); color: var(--szoveg); background: var(--hatter); border: var(--keret-vastag) solid var(--keret-mezo); border-radius: var(--kerekites); font: inherit; }
  ul { list-style: none; margin: var(--t-3) 0 0; padding: 0; }
  li { display: flex; align-items: center; gap: var(--t-3); padding: var(--t-1) 0; }
  li code { flex: 1; min-width: 0; overflow-wrap: anywhere; font-family: var(--betu-mono); font-size: var(--betu-ui); }
  li.ures { color: var(--szoveg-masodlagos); font-size: var(--betu-kicsi); }
  .db { color: var(--szoveg-masodlagos); font-size: var(--betu-kicsi); }
  .hiba { display: inline-flex; align-items: center; gap: var(--t-1); color: var(--hiba); font-size: var(--betu-kicsi); }
  .osszesites { margin: var(--t-2) 0 0; font-size: var(--betu-kicsi); color: var(--szoveg-masodlagos); }
</style>
