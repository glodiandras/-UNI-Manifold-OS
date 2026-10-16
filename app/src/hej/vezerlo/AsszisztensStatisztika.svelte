<!--
  Az Asszisztens statisztikája a vezérlőben (C30a): a javaslatok elfogadási aránya fajtánként és a belőle számolt küszöb,
  a jegyzethigiénia állása, és az egy gombos törlés (kétlépcsős). A statisztika helyben, a `pos.sqlite`-ban él, csak
  darabszámot tárol (útvonal és szöveg nélkül), a Tracker- és az Asszisztens-kapcsoló alatt; törölve a küszöb az alapra áll.
-->
<script lang="ts">
  import { t, tp } from '../../lib/i18n';
  import { onMount } from 'svelte';
  import { asszisztensMa, asszisztensStatisztika as stat } from '../../lib/asszisztens/adat.svelte';
  import { aranySzoveg, kuszobSzoveg, STATISZTIKA_CIM, szamolvaSzoveg } from '../../lib/asszisztens/megjelenites';
  import type { StatisztikaFajta } from '../../lib/asszisztens/tipusok';
  import { ertesitesek } from '../../lib/ertesites/ertesites.svelte';
  import { kornyezet } from '../../lib/kornyezet';

  const { kapcsolat } = kornyezet();
  const FAJTAK: StatisztikaFajta[] = ['emlites', 'szokas', 'higienia'];

  let megerosit = $state(false);

  onMount(() => {
    void stat.betolt();
    void asszisztensMa.betoltOsszegzes();
    return kapcsolat.figyel('asszisztens_valtozas', () => {
      void stat.betolt();
      void asszisztensMa.betoltOsszegzes();
    });
  });

  const a = $derived(stat.adat);
  const h = $derived(asszisztensMa.osszegzes);

  async function torol() {
    if (await stat.torol()) {
      megerosit = false;
      ertesitesek.ertesit({ szint: 'info', cim: t('Az Asszisztens statisztikája törölve'), idotartam: 4000 });
    }
  }
</script>

{#if stat.hiba && !a}
  <p class="hiba" role="alert">{t('A statisztika nem érhető el: {hiba}', { hiba: stat.hiba })}</p>
{:else if a}
  <h3>{t('Javaslatok statisztikája')} <span class="halvany">{t('(utolsó {n} nap)', { n: a.ablak_nap })}</span></h3>
  {#if !a.kapcsolo.tracker}
    <p class="halvany" role="status">{t('A Tracker ki van kapcsolva: új statisztika nem gyűlik, a küszöb alap.')}</p>
  {/if}
  <table>
    <thead>
      <tr><th scope="col">{t('Fajta')}</th><th scope="col">{t('Elfogadva')}</th><th scope="col">{t('Elutasítva')}</th><th scope="col">{t('Arány')}</th><th scope="col">{t('Küszöb')}</th></tr>
    </thead>
    <tbody>
      {#each FAJTAK as f (f)}
        {@const s = a.fajtak[f]}
        <tr>
          <th scope="row">{STATISZTIKA_CIM[f]}</th>
          <td>{s.elfogad}</td>
          <td>{s.elutasit}</td>
          <td>{aranySzoveg(s.arany)}</td>
          <td>{kuszobSzoveg(s.kuszob)}</td>
        </tr>
      {/each}
    </tbody>
  </table>
  <p class="halvany">{t('Csak darabszám, helyben; útvonalat és szöveget nem tárol.')}</p>
  {#if megerosit}
    <p class="kerdes" role="alert">{t('Biztosan törlöd az Asszisztens statisztikáját? A küszöb az alapra áll. Ez nem vonható vissza.')}</p>
    <div class="sor">
      <button type="button" class="m-gomb semleges gomb veszely" disabled={stat.foglalt} onclick={() => void torol()}>{t('Igen, törlés')}</button>
      <button type="button" class="m-gomb semleges gomb" disabled={stat.foglalt} onclick={() => (megerosit = false)}>{t('Mégse')}</button>
    </div>
  {:else}
    <div class="sor">
      <button type="button" class="m-gomb semleges gomb" disabled={stat.foglalt} onclick={() => (megerosit = true)}>{t('Statisztika törlése…')}</button>
    </div>
  {/if}
  {#if stat.hiba}<p class="hiba" role="alert">{stat.hiba}</p>{/if}
{/if}

{#if h?.kesz}
  <h3>{t('Jegyzethigiénia')}</h3>
  <p>
    {tp('{n} észrevétel', h.ossz)}{h.uj ? `, ${t('ebből {n} új', { n: h.uj })}` : ''}{h.szamolva ? ` · ${t('számolva: {mikor}', { mikor: szamolvaSzoveg(h.szamolva) })}` : ''}.
  </p>
  {#if h.szunetel}<p class="halvany" role="status">{t('A számítás vár: aktív használat alatt nem fut.')}</p>{/if}
{:else if h && !h.kapcsolo}
  <p class="halvany">{t('A higiénia-riport az Asszisztens kikapcsolva nem számolódik.')}</p>
{:else if h}
  <p class="halvany" role="status">{t('A higiénia-riport az app indulása után, tétlenségben készül el.')}</p>
{/if}


<style>
  h3 {
    margin: var(--t-3) 0 var(--t-1);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
    font-weight: var(--suly-felkover);
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--szoveg-halvany);
  }

  p {
    margin: var(--t-1) 0 0;
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
    color: var(--szoveg-masodlagos);
  }

  .halvany {
    color: var(--szoveg-halvany);
    text-transform: none;
    letter-spacing: 0;
    font-weight: inherit;
  }

  .hiba {
    color: var(--hiba);
  }

  .kerdes {
    color: var(--szoveg);
  }

  table {
    width: 100%;
    border-collapse: collapse;
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
    font-variant-numeric: tabular-nums;
  }

  th,
  td {
    padding: 1px var(--t-1);
    text-align: right;
    color: var(--szoveg-masodlagos);
    font-weight: inherit;
  }

  th[scope='row'],
  thead th:first-child,
  td:last-child,
  thead th:last-child {
    text-align: left;
  }

  thead th {
    color: var(--szoveg-halvany);
  }

  .sor {
    display: flex;
    flex-wrap: wrap;
    gap: var(--t-2);
    margin-top: var(--t-2);
  }

  .veszely {
    border-color: var(--hiba);
    color: var(--hiba);
  }
</style>
