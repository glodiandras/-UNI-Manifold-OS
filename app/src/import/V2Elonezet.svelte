<!--
  A v2-import előnézete (F8, csak Developer módban): mely munkatér-szintű beállítások és séma kerülnek át, mi ütközik (nem íródik
  felül), mi nem vihető át. A gépi állapot (indexek, modellek, kalibráció) nem része az importnak.
-->
<script lang="ts">
  import { CircleAlert, CircleCheck, TriangleAlert } from '../lib/ikon/ikonok';
  import { t, tk } from '../lib/i18n';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import {
    AKADALY, AKADALY_TARTALEK, FIGYELMEZTETES, FIGYELMEZTETES_TARTALEK, NEM_ATVETT_OKA, NEM_ATVETT_TARTALEK, UTKOZES_OKA, UTKOZES_TARTALEK, kodSzoveg, szam,
  } from '../lib/import/megjelenites';
  import type { V2Elonezet } from '../lib/import/tipusok';

  let { e }: { e: V2Elonezet } = $props();

  const ertek = (v: unknown) => (typeof v === 'string' ? v : v === undefined ? '–' : JSON.stringify(v));
  const SEMA: Record<string, string> = { ir: tk('import.v2.sema.ir'), azonos: tk('import.v2.sema.azonos'), utkozes: tk('import.v2.sema.utkozes') };
</script>

<div class="elonezet" data-elonezet="v2" data-eredmeny={e.eredmeny}>
  <p class="eredmeny" role="status">
    {#if e.eredmeny === 'tilos'}<Ikon ikon={CircleAlert} /> <strong>{t('import.eredmeny.tilos')}</strong>
    {:else if e.eredmeny === 'figyelmeztet'}<Ikon ikon={TriangleAlert} /> <strong>{t('import.eredmeny.figyelmeztet')}</strong>
    {:else}<Ikon ikon={CircleCheck} /> <strong>{t('import.eredmeny.mehet')}</strong>{/if}
  </p>
  {#if e.akadaly?.length}
    <ul class="akadalyok" aria-label={t('import.akadaly.lista')}>
      {#each e.akadaly as a (a)}<li data-akadaly={a}><Ikon ikon={CircleAlert} /><span>{kodSzoveg(AKADALY, a, AKADALY_TARTALEK)}</span></li>{/each}
    </ul>
  {/if}
  {#if e.figyelmeztetes?.length}
    <ul class="figyelmek" aria-label={t('import.figy.lista')}>
      {#each e.figyelmeztetes as f (f)}<li data-figyelmeztetes={f}><Ikon ikon={TriangleAlert} /><span>{kodSzoveg(FIGYELMEZTETES, f, FIGYELMEZTETES_TARTALEK)}</span></li>{/each}
    </ul>
  {/if}

  {#if e.eredmeny !== 'tilos'}
    <section aria-labelledby="v2-valtozas">
      <h4 id="v2-valtozas">{t('import.v2.valtozas_cim')} <span class="szam">({szam(e.kulcsok.length)})</span></h4>
      {#if e.kulcsok.length}
        <table aria-label={t('import.v2.valtozas_tabla')}>
          <thead><tr><th scope="col">{t('import.v2.oszlop_kulcs')}</th><th scope="col">{t('import.v2.oszlop_jelen')}</th><th scope="col">{t('import.v2.oszlop_uj')}</th></tr></thead>
          <tbody>{#each e.kulcsok as k (k.kulcs)}<tr><th scope="row">{k.kulcs}</th><td class="ut">{ertek(k.jelen)}</td><td class="ut">{ertek(k.uj)}</td></tr>{/each}</tbody>
        </table>
      {:else}
        <p class="halvany">{t('import.v2.nincs_valtozas')}</p>
      {/if}
      {#if e.sema}<p><strong>{t('import.v2.sema_cim')}</strong> <span data-sema={e.sema.muvelet}>{t(Object.hasOwn(SEMA, e.sema.muvelet) ? SEMA[e.sema.muvelet] : 'import.v2.sema.azonos')}</span></p>{/if}
      <dl>
        <dt>{t('import.v2.azonos')}</dt><dd>{szam(e.azonos_db)}</dd>
        <dt>{t('import.v2.gepi')}</dt><dd>{szam(e.nem_munkater_kulcs_db)}</dd>
      </dl>
    </section>

    {#if e.utkozesek.length}
      <section aria-labelledby="v2-utkozes">
        <h4 id="v2-utkozes"><Ikon ikon={TriangleAlert} /> {t('import.v2.utkozes_cim')} <span class="szam">({szam(e.utkozesek.length)})</span></h4>
        <p class="halvany">{t('import.v2.utkozes_leiras')}</p>
        <ul data-lista="utkozesek">
          {#each e.utkozesek as u, i (i)}<li><span class="ut">{u.kulcs}</span>{#if u.ok} <span class="halvany">{kodSzoveg(UTKOZES_OKA, u.ok, UTKOZES_TARTALEK)}</span>{:else} <span class="halvany">{ertek(u.jelen)} → {ertek(u.v2)}</span>{/if}</li>{/each}
        </ul>
      </section>
    {/if}
    {#if e.nem_atvett.length}
      <section aria-labelledby="v2-nem">
        <h4 id="v2-nem">{t('import.nematvett.cim')} <span class="szam">({szam(e.nem_atvett.length)})</span></h4>
        <ul data-lista="nem-atvett">
          {#each e.nem_atvett as n, i (i)}<li><span class="ut">{n.kulcs}</span> <span class="halvany">{kodSzoveg(NEM_ATVETT_OKA, n.ok, NEM_ATVETT_TARTALEK)}</span></li>{/each}
        </ul>
      </section>
    {/if}
    {#if e.ujrainditas}<p class="figyelem"><Ikon ikon={TriangleAlert} /> <span>{t('import.v2.ujrainditas_elore')}</span></p>{/if}
  {/if}
</div>

<style>
  .elonezet { display: flex; flex-direction: column; gap: var(--t-4); }
  section { display: flex; flex-direction: column; gap: var(--t-2); }
  h4 { display: flex; align-items: center; gap: var(--t-2); margin: 0; font-size: var(--betu-torzs); font-weight: var(--suly-kozepes); }
  p { margin: 0; }
  .eredmeny { display: flex; align-items: center; gap: var(--t-2); }
  .halvany { color: var(--szoveg-masodlagos); font-size: var(--betu-kicsi); }
  .szam { color: var(--szoveg-masodlagos); font-weight: var(--suly-normal); }
  dl { display: grid; grid-template-columns: max-content 1fr; gap: var(--t-1) var(--t-4); margin: 0; }
  dt { color: var(--szoveg-masodlagos); }
  dd { margin: 0; }
  ul { margin: 0; padding-inline-start: var(--t-5); }
  .akadalyok, .figyelmek { list-style: none; padding: 0; }
  .akadalyok li, .figyelmek li { display: flex; align-items: flex-start; gap: var(--t-2); padding: var(--t-2) var(--t-3); border-radius: var(--kerekites); }
  .akadalyok li { background: var(--hiba-hatter); color: var(--hiba); }
  .figyelmek li { background: var(--figyelmeztetes-hatter); color: var(--figyelmeztetes); }
  .figyelem { display: flex; align-items: flex-start; gap: var(--t-2); color: var(--figyelmeztetes); }
  table { border-collapse: collapse; width: 100%; }
  th, td { text-align: start; padding: var(--t-1) var(--t-2); border-bottom: var(--keret-vastag) solid var(--keret); vertical-align: top; }
  thead th { color: var(--szoveg-masodlagos); font-size: var(--betu-kicsi); font-weight: var(--suly-normal); }
  tbody th { font-weight: var(--suly-normal); }
  .ut { overflow-wrap: anywhere; user-select: text; }
</style>
