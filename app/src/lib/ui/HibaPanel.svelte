<!--
  Közös hiba-minta (F7): „What happened / Fix / [Fix automatically] [Open diagnostics]”. A hiba mindig ikonnal és szóval jön
  (a `role="alert"` + `.hiba` sor az alap.css szabálya szerint ikont kap); a burgundi nem jelez állapotot. A „Fix automatically”
  csak akkor látszik, ha a hívó biztonságos, visszafordítható javítást ad; a futása közben tiltott, a hibáját a panel mutatja.
-->
<script lang="ts">
  import { hibaUzenet } from '../core/api';
  import { t } from '../i18n';

  let { mi, javitas = '', automatikus, diagnosztika, ujra, ujraCimke }: {
    mi: string;
    javitas?: string;
    automatikus?: () => Promise<string | void> | string | void;
    diagnosztika?: () => void;
    ujra?: () => void;
    ujraCimke?: string;
  } = $props();

  let fut = $state(false);
  let eredmeny = $state('');
  let hiba = $state('');

  async function futtat() {
    if (fut || !automatikus) return;
    fut = true;
    hiba = '';
    eredmeny = '';
    try {
      eredmeny = (await automatikus()) || '';
    } catch (e) {
      hiba = hibaUzenet(e);
    } finally {
      fut = false;
    }
  }
</script>

<section class="hiba-panel" aria-label={t('hibapanel.cim')} data-hiba-panel>
  <h3>{t('hibapanel.mi')}</h3>
  <p class="hiba" role="alert">{mi}</p>
  {#if javitas}
    <h3>{t('hibapanel.javitas')}</h3>
    <p class="javitas">{javitas}</p>
  {/if}
  {#if automatikus || diagnosztika || ujra}
    <div class="gombok">
      {#if automatikus}<button type="button" class="m-gomb" disabled={fut} onclick={futtat}>{t('hibapanel.automatikus')}</button>{/if}
      {#if ujra}<button type="button" class="m-gomb semleges" onclick={ujra}>{ujraCimke ?? t('hibapanel.ujra')}</button>{/if}
      {#if diagnosztika}<button type="button" class="m-gomb semleges" onclick={diagnosztika}>{t('hibapanel.diagnosztika')}</button>{/if}
    </div>
  {/if}
  {#if fut}<p role="status" class="allapot">{t('hibapanel.fut')}</p>{/if}
  {#if eredmeny}<p role="status" class="allapot">{eredmeny}</p>{/if}
  {#if hiba}<p class="hiba" role="alert">{hiba}</p>{/if}
</section>

<style>
  .hiba-panel { display: flex; flex-direction: column; gap: var(--t-2); padding: var(--t-4); background: var(--hiba-hatter); border: var(--keret-vastag) solid var(--keret); border-radius: var(--kerekites); }
  h3 { margin: 0; font-size: var(--betu-kicsi); font-weight: var(--suly-kozepes); color: var(--szoveg-masodlagos); }
  p { margin: 0; }
  .hiba { display: flex; align-items: flex-start; color: var(--hiba); }
  .javitas { color: var(--szoveg); }
  .gombok { display: flex; flex-wrap: wrap; gap: var(--t-2); margin-top: var(--t-1); }
  .allapot { color: var(--szoveg-masodlagos); font-size: var(--betu-kicsi); }
</style>
