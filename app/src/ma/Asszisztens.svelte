<!--
  Az Asszisztens a „Ma” oldalon (C30a): csendes szakasz, csak ha van mit mutatni — a jegyzethigiénia új tételeinek száma
  (a legutóbb „látva” jelölt riport óta) és a heti szokásminta-javaslat. Üres állapotban a szakasz el sem jelenik. A
  számítás a core háttérszálában fut (aktív használat alatt szünetel); az oldal csak a gyorsítótárat olvassa. A „Láttam”
  nullázza az újat, a javaslat „Megnyitás” / „Nem kell” gombja döntés (a statisztikába kerül).
-->
<script lang="ts">
  import { untrack } from 'svelte';
  import { t, tp } from '../lib/i18n';
  import { asszisztensMa as m } from '../lib/asszisztens/adat.svelte';
  import { fajtaCim } from '../lib/asszisztens/megjelenites';
  import type { HigieniaTetel } from '../lib/asszisztens/tipusok';
  import { kornyezet } from '../lib/kornyezet';
  import { fajlNev } from '../lib/vault/fajlok.svelte';
  import { nyitasMod } from '../szerkeszto/linkek/navigacio';
  import { szerkesztok } from '../szerkeszto/szerkesztok.svelte';
  import type { Hiba, MaAsszisztens } from './tipusok';
  import { hibas } from './tipusok';

  let { szakasz, datum }: { szakasz: MaAsszisztens | Hiba | undefined; datum: string | undefined } = $props();
  const { felulet } = kornyezet();

  const be = $derived(!!szakasz && !hibas(szakasz) && szakasz.kapcsolo);
  const higienia = $derived(be && szakasz && !hibas(szakasz) && szakasz.higienia && szakasz.higienia.uj > 0 ? szakasz.higienia : null);
  const javaslat = $derived(be ? m.szokas : null);
  let reszletek = $state(false);

  // a javaslat a napra és a kapcsolóra tölt (a core a hét első alkalmas napján ki is adja); az új tételek listája kérésre
  $effect(() => {
    void datum;
    if (be) untrack(() => void m.betoltSzokas());
  });
  $effect(() => {
    if (reszletek && higienia) untrack(() => void m.betoltOsszegzes());
  });

  const tetelek = $derived(m.osszegzes?.uj_tetelek ?? []);

  function tetelNyit(tetel: HigieniaTetel, e: MouseEvent) {
    felulet.munkaterulet.megnyit(tetel.ut, nyitasMod(e));
    if (tetel.sor) szerkesztok.ugras(tetel.ut, tetel.sor);
  }

  async function javaslatNyit(e: MouseEvent) {
    const ut = javaslat?.legutobbi_ut;
    if (ut) felulet.munkaterulet.megnyit(ut, nyitasMod(e));
    await m.szokasDontes('elfogad');
  }
</script>

{#if higienia || javaslat}
  <section aria-labelledby="ma-asszisztens">
    <h2 id="ma-asszisztens">{t('Asszisztens')}</h2>
    {#if javaslat}
      <div class="doboz" role="group" aria-label={t('Heti szokás-javaslat')}>
        <p>{javaslat.szoveg}</p>
        <div class="gombok">
          {#if javaslat.legutobbi_ut}
            <button type="button" class="m-gomb semleges gomb" disabled={m.foglalt} onclick={(e) => void javaslatNyit(e)} title={javaslat.legutobbi_ut}>
              {t('Megnyitás:')} {fajlNev(javaslat.legutobbi_ut)}
            </button>
          {/if}
          <button type="button" class="m-gomb semleges gomb" disabled={m.foglalt} onclick={() => void m.szokasDontes('elutasit')}>{t('Nem kell')}</button>
        </div>
      </div>
    {/if}
    {#if higienia}
      <div class="doboz" role="group" aria-label={t('Jegyzethigiénia')}>
        <p>
          {t('Jegyzethigiénia:')} <strong>{tp('{n} új észrevétel', higienia.uj)}</strong> <span class="halvany">({t('összesen {n}', { n: higienia.ossz })})</span>
        </p>
        <div class="gombok">
          <button type="button" class="m-gomb semleges gomb" aria-expanded={reszletek} onclick={() => (reszletek = !reszletek)}>
            {reszletek ? t('Elrejtés') : t('Áttekintés')}
          </button>
          <button type="button" class="m-gomb semleges gomb" disabled={m.foglalt} onclick={() => void m.latva()}>{t('Láttam')}</button>
        </div>
        {#if reszletek}
          <ul class="lista" role="list">
            {#each tetelek as tetel (tetel.azonosito)}
              <li>
                <button type="button" class="sor-gomb" onclick={(e) => tetelNyit(tetel, e)} title={tetel.ut}>
                  <span class="cimke">{fajtaCim(tetel.fajta)}</span>
                  <span class="szoveg">{tetel.uzenet}</span>
                  <span class="halvany">{fajlNev(tetel.ut)}</span>
                </button>
              </li>
            {/each}
          </ul>
        {/if}
      </div>
    {/if}
    {#if m.hiba}<p class="hiba" role="alert">{m.hiba}</p>{/if}
  </section>
{/if}

<style>
  section {
    margin-top: var(--t-6);
  }

  h2 {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    margin: 0 0 var(--t-2);
    padding-bottom: var(--t-1);
    border-bottom: var(--keret-vastag) solid var(--keret);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
    font-weight: var(--suly-felkover);
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--szoveg-halvany);
  }

  .doboz {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--t-2);
    margin-top: var(--t-2);
    padding: var(--t-2) var(--t-3);
    border: var(--keret-vastag) solid var(--keret);
    border-radius: var(--kerekites);
  }

  p {
    margin: 0;
  }

  .halvany {
    color: var(--szoveg-halvany);
  }

  .hiba {
    margin-top: var(--t-2);
    color: var(--hiba);
  }

  .gombok {
    display: flex;
    flex-wrap: wrap;
    gap: var(--t-2);
  }

  .lista {
    align-self: stretch;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .sor-gomb {
    display: flex;
    align-items: baseline;
    gap: var(--t-3);
    width: 100%;
    padding: var(--t-1) 0;
    text-align: left;
    color: inherit;
  }

  .sor-gomb:hover {
    background: var(--hatter-hover);
  }

  .cimke {
    flex: none;
    color: var(--szoveg-masodlagos);
  }

  .szoveg {
    flex: 1;
    min-width: 0;
    overflow-wrap: anywhere;
  }
</style>
