<!--
  „Mit tanult az asszisztens” (J1; ESZREVETELEK-TERV 2. fejezet 6. pont): minden, amit az asszisztens helyben tanult —
  az elfogadott szövegminták, az ismétlődő műveletek (címke, sablon, link mappánként), a javaslatok gyakoriságának hangolása
  és az elutasított javaslatok. Minden a `{state}/asszisztens.json`-ban él, a vaultba nem kerül; egyenként és egyben is törölhető.
-->
<script lang="ts">
  import { t } from '../../lib/i18n';
  import { onMount } from 'svelte';
  import { asszisztensApi } from '../../lib/asszisztens/api';
  import { hangolasSzoveg, helyzetSzoveg } from '../../lib/asszisztens/megjelenites';
  import type { TanultFajta, TanultLista } from '../../lib/asszisztens/tipusok';

  let adat = $state.raw<TanultLista | null>(null);
  let hiba = $state('');
  let foglalt = $state(false);
  let megerosit = $state(false);
  let elotte = $state('');
  let szoveg = $state('');

  const uzenet = (e: unknown) => (e instanceof Error ? e.message : String(e));

  async function betolt() {
    try {
      adat = await asszisztensApi.tanult();
      hiba = '';
    } catch (e) {
      hiba = uzenet(e);
    }
  }

  onMount(() => void betolt());

  async function torol(fajta: TanultFajta, kulcs?: string) {
    foglalt = true;
    try {
      adat = await asszisztensApi.tanultTorol(fajta, kulcs);
      hiba = '';
      megerosit = false;
    } catch (e) {
      hiba = uzenet(e);
    } finally {
      foglalt = false;
    }
  }

  async function tanit() {
    foglalt = true;
    hiba = '';
    try {
      await asszisztensApi.mintaTanit(elotte, szoveg);
      elotte = '';
      szoveg = '';
      await betolt();
    } catch (e) {
      hiba = uzenet(e);
    } finally {
      foglalt = false;
    }
  }

  const ures = $derived(!!adat && !adat.mintak.length && !adat.muveletek.length && !adat.hangolas.length && !adat.elutasitott.length);
</script>

<section class="tanult" aria-labelledby="tanult-cim">
  <h3 id="tanult-cim">{t('Mit tanult az asszisztens')}</h3>
  <p class="halvany">{t('Helyben, ezen a gépen tárolja; a vaultba nem ír. Bármelyik tételt törölheted, akkor elfelejti.')}</p>
  {#if adat && !adat.kapcsolo}<p class="halvany" role="status">{t('Az asszisztens ki van kapcsolva: most nem tanul és nem javasol.')}</p>{/if}

  {#if ures}
    <p class="halvany">{t('Még nem tanult semmit.')}</p>
  {:else if adat}
    {#if adat.mintak.length}
      <h4>{t('Elfogadott szövegfolytatások')}</h4>
      <ul>
        {#each adat.mintak as m (m.elotte)}
          <li>
            <span class="minta">…{m.elotte}<b>{m.szoveg}</b></span>
            <button type="button" class="m-gomb semleges suru" disabled={foglalt} aria-label={t('A szövegminta törlése: {minta}', { minta: m.elotte })}
              onclick={() => void torol('minta', m.elotte)}>{t('Törlés')}</button>
          </li>
        {/each}
      </ul>
    {/if}
    {#if adat.muveletek.length}
      <h4>{t('Ismétlődő műveletek')}</h4>
      <ul>
        {#each adat.muveletek as m (m.kulcs)}
          <li>
            <span>{m.muvelet_nev} „{m.ertek}” · {m.mappa || t('a vault gyökere')} · {m.db}× {#if !m.tanult}<span class="halvany">{t('(megfigyelés)')}</span>{/if}</span>
            <button type="button" class="m-gomb semleges suru" disabled={foglalt} aria-label={t('A művelet-minta törlése: {minta}', { minta: m.ertek })}
              onclick={() => void torol('muvelet', m.kulcs)}>{t('Törlés')}</button>
          </li>
        {/each}
      </ul>
    {/if}
    {#if adat.hangolas.length}
      <h4>{t('Mikor javasol (a döntéseidből)')}</h4>
      <ul>
        {#each adat.hangolas as h (h.kulcs)}
          <li>
            <span>{h.tipus_nev}, {helyzetSzoveg(h.helyzet)}: {t('{igen} igen / {nem} nem', { igen: h.elfogad, nem: h.elutasit })} · {hangolasSzoveg(h.szint)}</span>
            <button type="button" class="m-gomb semleges suru" disabled={foglalt} aria-label={t('A hangolás törlése: {tipus}, {helyzet}', { tipus: h.tipus_nev, helyzet: helyzetSzoveg(h.helyzet) })}
              onclick={() => void torol('hangolas', h.kulcs)}>{t('Törlés')}</button>
          </li>
        {/each}
      </ul>
    {/if}
    {#if adat.elutasitott.length}
      <h4>{t('Elutasított javaslatok (egy ideig nem térnek vissza)')}</h4>
      <ul>
        {#each adat.elutasitott as e (e.kulcs)}
          <li>
            <span>{e.cim || e.kulcs}</span>
            <button type="button" class="m-gomb semleges suru" disabled={foglalt} aria-label={t('Az elutasítás törlése: {cim}', { cim: e.cim || e.kulcs })}
              onclick={() => void torol('elutasitott', e.kulcs)}>{t('Törlés')}</button>
          </li>
        {/each}
      </ul>
    {/if}
  {/if}

  <details>
    <summary>{t('Új szövegfolytatás tanítása')}</summary>
    <p class="halvany">{t('A folytatás csak akkor jelenik meg, ha a kurzor előtti szöveg pontosan erre az előzményre végződik. Tab elfogadja, Esc elveti.')}</p>
    <label>{t('Előzmény (8–100 karakter)')}<textarea bind:value={elotte} maxlength="100" rows="2"></textarea></label>
    <label>{t('Elfogadott folytatás')}<textarea bind:value={szoveg} maxlength="800" rows="3"></textarea></label>
    <button type="button" class="m-gomb semleges" disabled={foglalt || elotte.trim().length < 8 || !szoveg.trim()} onclick={() => void tanit()}>{t('Minta elfogadása')}</button>
  </details>

  {#if megerosit}
    <p class="kerdes" role="alert">{t('Mindent elfelejt, amit eddig tanult? Ez nem vonható vissza.')}</p>
    <div class="sor">
      <button type="button" class="m-gomb semleges" disabled={foglalt} onclick={() => void torol('mind')}>{t('Igen, mindent törlök')}</button>
      <button type="button" class="m-gomb semleges" disabled={foglalt} onclick={() => (megerosit = false)}>{t('Mégse')}</button>
    </div>
  {:else}
    <div class="sor">
      <button type="button" class="m-gomb semleges" disabled={foglalt || ures || !adat} onclick={() => (megerosit = true)}>{t('Mind törlése…')}</button>
    </div>
  {/if}
  {#if hiba}<p class="hiba" role="alert">{hiba}</p>{/if}
</section>

<style>
  .tanult {
    margin-top: var(--t-4);
    font-size: var(--betu-kicsi);
  }

  h3 {
    margin: var(--t-3) 0 var(--t-1);
  }

  h4 {
    margin: var(--t-3) 0 var(--t-1);
    color: var(--szoveg-masodlagos);
  }

  ul {
    display: grid;
    gap: var(--t-1);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  li {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--t-2);
  }

  li > span {
    min-width: 0;
    overflow-wrap: anywhere;
  }

  .minta {
    white-space: pre-wrap;
  }

  b {
    color: var(--szoveg);
  }

  .halvany {
    color: var(--szoveg-halvany);
  }

  label {
    display: grid;
    gap: var(--t-1);
    margin: var(--t-2) 0;
  }

  textarea {
    width: 100%;
    box-sizing: border-box;
    resize: vertical;
  }

  .sor {
    display: flex;
    gap: var(--t-2);
    margin-top: var(--t-2);
  }

  details {
    margin-top: var(--t-3);
  }

  .hiba {
    color: var(--hiba);
  }
</style>
