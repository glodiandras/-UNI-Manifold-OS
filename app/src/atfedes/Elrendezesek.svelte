<!--
  Névvel mentett elrendezések (06-workspace-26): a jelenlegi munkaterület mentése névvel, betöltés és törlés egy átfedésben.
  Az elrendezés a fülek szerkezetét és az oldalsáv/jobb panel nyitottságát tartalmazza; a betöltés nem ír a vaultba.
-->
<script lang="ts">
  import { t, tp } from '../lib/i18n';
  import { onMount } from 'svelte';
  import { MAX_ELRENDEZES } from '../lib/elrendezes/felulet.svelte';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import { CircleAlert } from '../lib/ikon/ikonok';
  import { kornyezet } from '../lib/kornyezet';
  import Atfedes from '../lib/ui/Atfedes.svelte';

  const { felulet } = kornyezet();
  let nev = $state('');
  let hiba = $state<string | null>(null);
  let bevitel: HTMLInputElement | undefined = $state();

  onMount(() => bevitel?.focus());

  function bezar() {
    felulet.atfedes = null;
  }

  function ment() {
    const e = felulet.elrendezesMent(nev);
    if (e === 'ok') { nev = ''; hiba = null; return; }
    hiba = e === 'ures' ? t('Adj nevet az elrendezésnek.')
      : e === 'tul-sok' ? t('Legfeljebb {n} elrendezés menthető. Törölj egyet.', { n: MAX_ELRENDEZES })
      : t('Ez az elrendezés túl nagy a mentéshez. Zárj be néhány fület.');
  }

  function betolt(n: string) {
    if (felulet.elrendezesBetolt(n)) bezar();
  }

  function bevitelBillentyu(e: KeyboardEvent) {
    if (e.key === 'Enter' && !e.isComposing) {
      e.preventDefault();
      ment();
    }
  }
</script>

<Atfedes cimke={t('Munkaterület-elrendezések')} nev="elrendezesek" onbezar={bezar}>
  <div class="doboz">
    <h2 class="cim">{t('Munkaterület-elrendezések')}</h2>
    <label class="mezo">
      <span>{t('A jelenlegi elrendezés mentése névvel')}</span>
      <span class="sor">
        <input bind:this={bevitel} bind:value={nev} onkeydown={bevitelBillentyu} maxlength="60" spellcheck="false" autocomplete="off" placeholder={t('Az elrendezés neve')} />
        <button type="button" class="m-gomb elso" disabled={!nev.trim()} onclick={ment}>{t('Mentés')}</button>
      </span>
    </label>
    {#if hiba}<p class="hiba" role="alert"><Ikon ikon={CircleAlert} meret={14} /> {hiba}</p>{/if}
    <ul class="lista" aria-label={t('Mentett elrendezések')}>
      {#each felulet.elrendezesek as e (e.nev)}
        <li>
          <span class="nev" title={e.nev}>{e.nev}</span>
          <button type="button" class="m-gomb semleges masodlagos" onclick={() => betolt(e.nev)} aria-label={t('{nev} betöltése', { nev: e.nev })}>{t('Betöltés')}</button>
          <button type="button" class="m-gomb semleges masodlagos" onclick={() => felulet.elrendezesTorol(e.nev)} aria-label={t('{nev} törlése', { nev: e.nev })}>{t('Törlés')}</button>
        </li>
      {:else}
        <li class="ures">{t('Még nincs mentett elrendezés.')}</li>
      {/each}
    </ul>
    <p class="seg">{tp('{n} elrendezés', felulet.elrendezesek.length)} · {t('legfeljebb {n}', { n: MAX_ELRENDEZES })}</p>
  </div>
</Atfedes>

<style>
  .doboz {
    display: flex;
    flex-direction: column;
    gap: var(--t-3);
    padding: var(--t-4) var(--t-5);
    max-height: min(80vh, 40rem);
    overflow: hidden;
  }

  .cim {
    margin: 0;
    font-size: var(--betu-h4);
  }

  .mezo {
    display: flex;
    flex-direction: column;
    gap: var(--t-1);
    font-size: var(--betu-ui);
    color: var(--szoveg-masodlagos);
  }

  .sor {
    display: flex;
    gap: var(--t-2);
  }

  .sor input {
    flex: 1;
    min-width: 0;
    padding: var(--t-2) var(--t-3);
    border: 1px solid var(--keret-mezo);
    border-radius: var(--kerekites);
    background: var(--hatter);
    color: var(--szoveg);
    font: inherit;
  }

  .lista {
    margin: 0;
    padding: 0;
    list-style: none;
    overflow-y: auto;
    border: 1px solid var(--keret);
    border-radius: var(--kerekites);
  }

  .lista li {
    display: flex;
    align-items: center;
    gap: var(--t-2);
    padding: var(--t-1) var(--t-3);
    font-size: var(--betu-ui);
  }

  .nev {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .ures {
    color: var(--szoveg-halvany);
  }

  .seg {
    margin: 0;
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
  }

  .hiba {
    margin: 0;
    color: var(--hiba);
    font-size: var(--betu-ui);
  }
</style>
