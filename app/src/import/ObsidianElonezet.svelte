<!--
  Az Obsidian-import előnézete (F8, csak olvas): mit másol a Manifold, mit hagy ki és miért, mi ütközik, hány link van, mely
  beállításokat veszi át, mely pluginok nem támogatottak. A fájlok változtatás nélkül másolódnak: erről is szól a képernyő.
-->
<script lang="ts">
  import { CircleAlert, CircleCheck, TriangleAlert } from '../lib/ikon/ikonok';
  import { t } from '../lib/i18n';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import { meretSzoveg } from '../lib/adatvedelem/megjelenites';
  import {
    AKADALY, AKADALY_TARTALEK, FAJL_FAJTA, FIGYELMEZTETES, FIGYELMEZTETES_TARTALEK, KIHAGYAS_OKA, KIHAGYAS_TARTALEK, MUVELET, NEM_ATVETT_OKA,
    NEM_ATVETT_TARTALEK, PLUGIN_ALLAPOT, UTKOZES_OKA, UTKOZES_TARTALEK, BEALLITAS_MOD, beallitasCim, ertekSzoveg, kodSzoveg, szam,
  } from '../lib/import/megjelenites';
  import type { ObsidianElonezet } from '../lib/import/tipusok';

  let { e }: { e: ObsidianElonezet } = $props();

  const o = $derived(e.osszesites);
  const atirasDb = $derived(e.atiras?.length ?? 0);
  const kihagyasCsoportok = $derived.by(() => {
    const m = new Map<string, number>();
    for (const k of e.kihagyott ?? []) m.set(k.ok, (m.get(k.ok) ?? 0) + 1);
    return [...m].sort((a, b) => b[1] - a[1]);
  });
  const kihagyottDb = $derived(o?.kihagyott_db ?? e.kihagyott?.length ?? 0);
  const fajlSorok = $derived(e.fajlok ?? []);
  const nemTamogatottPlugin = $derived([...(e.obsidian?.mag_pluginok ?? []).filter((p) => p.allapot === 'nem_tamogatott'), ...(e.obsidian?.kozossegi_pluginok ?? [])]);
  const mag = $derived(e.obsidian?.mag_pluginok ?? []);
  const kozossegi = $derived(e.obsidian?.kozossegi_pluginok ?? []);
</script>

<div class="elonezet" data-elonezet="obsidian" data-eredmeny={e.eredmeny}>
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

  {#if o}
    <section aria-labelledby="eo-osszes">
      <h4 id="eo-osszes">{t('import.osszesites.cim')}</h4>
      <dl>
        <dt>{t('import.osszesites.forras')}</dt><dd class="ut">{e.forras}</dd>
        <dt>{t('import.osszesites.cel')}</dt><dd class="ut">{e.cel}</dd>
        <dt>{t('import.osszesites.fajl')}</dt><dd data-mezo="fajl_db">{szam(o.fajl_db)}</dd>
        <dt>{t('import.osszesites.meret')}</dt><dd data-mezo="bajt">{meretSzoveg(o.bajt)}</dd>
        <dt>{t(FAJL_FAJTA.md)}</dt><dd>{szam(o.md_db)}</dd>
        <dt>{t(FAJL_FAJTA.canvas)}</dt><dd>{szam(o.canvas_db)}</dd>
        <dt>{t(FAJL_FAJTA.base)}</dt><dd>{szam(o.base_db)}</dd>
        <dt>{t(FAJL_FAJTA.csatolmany)}</dt><dd>{szam(o.csatolmany_db)}</dd>
        <dt>{t(FAJL_FAJTA.obsidian)}</dt><dd>{szam(o.obsidian_db)}</dd>
        <dt>{t(FAJL_FAJTA.egyeb)}</dt><dd>{szam(o.egyeb_db)}</dd>
        <dt>{t('import.osszesites.mappa')}</dt><dd>{szam(o.mappa_db)}</dd>
        <dt>{t('import.osszesites.masolando')}</dt><dd data-mezo="masolando_db">{szam(o.masolando_db)}</dd>
        {#if o.megvan_db > 0}<dt>{t('import.osszesites.megvan')}</dt><dd data-mezo="megvan_db">{szam(o.megvan_db)}</dd>{/if}
        {#if e.szabad_bajt != null}<dt>{t('import.osszesites.szabad')}</dt><dd>{meretSzoveg(e.szabad_bajt)}</dd>{/if}
      </dl>
      <p class="halvany">{atirasDb === 0 ? t('import.atiras.nincs') : t('import.atiras.van')}</p>
    </section>
  {/if}

  {#if kihagyottDb > 0}
    <section aria-labelledby="eo-kihagyott">
      <h4 id="eo-kihagyott">{t('import.kihagyott.cim')} <span class="szam">({szam(kihagyottDb)})</span></h4>
      <p class="halvany">{t('import.kihagyott.leiras')}</p>
      <ul data-lista="kihagyott-okok">
        {#each kihagyasCsoportok as [ok, db] (ok)}<li><span>{kodSzoveg(KIHAGYAS_OKA, ok, KIHAGYAS_TARTALEK)}</span> <span class="szam">{szam(db)}</span></li>{/each}
      </ul>
      <details>
        <summary>{t('import.kihagyott.reszletek')}</summary>
        <ul class="fajlok" aria-label={t('import.kihagyott.lista')}>
          {#each e.kihagyott as k, i (i)}<li><span class="ut">{k.ut}</span> <span class="halvany">{kodSzoveg(KIHAGYAS_OKA, k.ok, KIHAGYAS_TARTALEK)}</span></li>{/each}
        </ul>
        {#if e.kihagyott.length < kihagyottDb}<p class="halvany">{t('import.lista_csonkitva')}</p>{/if}
      </details>
    </section>
  {/if}

  {#if e.utkozesek?.length}
    <section aria-labelledby="eo-utkozes">
      <h4 id="eo-utkozes"><Ikon ikon={CircleAlert} /> {t('import.utkozes.cim')} <span class="szam">({szam(e.utkozesek.length)})</span></h4>
      <ul class="fajlok" data-lista="utkozesek">
        {#each e.utkozesek as u, i (i)}<li><span class="ut">{u.ut}</span>{#if u.masik} <span class="halvany">↔ <span class="ut">{u.masik}</span></span>{/if} <span class="halvany">{kodSzoveg(UTKOZES_OKA, u.ok, UTKOZES_TARTALEK)}</span></li>{/each}
      </ul>
    </section>
  {/if}

  {#if e.linkek}
    <section aria-labelledby="eo-linkek">
      <h4 id="eo-linkek">{t('import.linkek.cim')}</h4>
      <dl>
        <dt>{t('import.linkek.wikilink')}</dt><dd data-mezo="wikilink_db">{szam(e.linkek.wikilink_db)}</dd>
        <dt>{t('import.linkek.markdown')}</dt><dd data-mezo="markdown_link_db">{szam(e.linkek.markdown_link_db)}</dd>
        <dt>{t('import.linkek.beagyazas')}</dt><dd data-mezo="beagyazas_db">{szam(e.linkek.beagyazas_db)}</dd>
        <dt>{t('import.linkek.frontmatter')}</dt><dd data-mezo="frontmatter_db">{szam(e.linkek.frontmatter_db)}</dd>
        {#if e.linkek.beallitas?.link_formatum != null}<dt>{t('import.beallitas.link_formatum')}</dt><dd>{ertekSzoveg(e.linkek.beallitas.link_formatum)}</dd>{/if}
        {#if e.linkek.beallitas?.wikilinkek != null}<dt>{t('import.beallitas.wikilinkek')}</dt><dd>{ertekSzoveg(e.linkek.beallitas.wikilinkek)}</dd>{/if}
      </dl>
      <p class="halvany">{t('import.linkek.valtozatlan')}</p>
    </section>
  {/if}

  {#if e.obsidian}
    <section aria-labelledby="eo-beall">
      <h4 id="eo-beall">{t('import.beallitasok.cim')}</h4>
      {#if e.obsidian.beallitasok.length}
        <table aria-label={t('import.beallitasok.tabla')}>
          <thead><tr><th scope="col">{t('import.beallitasok.oszlop_nev')}</th><th scope="col">{t('import.beallitasok.oszlop_ertek')}</th><th scope="col">{t('import.beallitasok.oszlop_mod')}</th></tr></thead>
          <tbody>
            {#each e.obsidian.beallitasok as b, i (i)}
              <tr><th scope="row">{beallitasCim(b.kulcs)}</th><td class="ut">{ertekSzoveg(b.ertek)}</td><td class="halvany">{kodSzoveg(BEALLITAS_MOD, b.mod, 'import.beallitas.mod.ir')}</td></tr>
            {/each}
          </tbody>
        </table>
      {:else}
        <p class="halvany">{t('import.beallitasok.nincs')}</p>
      {/if}
      {#if e.obsidian.nem_atvett.length}
        <h5>{t('import.nematvett.cim')}</h5>
        <ul class="fajlok" data-lista="nem-atvett">
          {#each e.obsidian.nem_atvett as n, i (i)}<li><span class="ut">{n.forras ?? n.kulcs}</span> <span class="halvany">{kodSzoveg(NEM_ATVETT_OKA, n.ok, NEM_ATVETT_TARTALEK)}</span></li>{/each}
        </ul>
      {/if}
    </section>

    {#if mag.length || kozossegi.length}
      <section aria-labelledby="eo-plugin">
        <h4 id="eo-plugin">{t('import.plugin.cim')}</h4>
        {#if nemTamogatottPlugin.length}<p class="figyelem"><Ikon ikon={TriangleAlert} /> <span>{t('import.plugin.figyelmeztetes')}</span></p>{/if}
        {#if mag.length}
          <h5>{t('import.plugin.beepitett_cim')}</h5>
          <ul class="pluginok" data-lista="mag-pluginok">
            {#each mag as p (p.id)}
              <li data-plugin={p.id}><span class="ut">{p.id}</span> <span class="plugin-allapot" class:nem={p.allapot === 'nem_tamogatott'}>{#if p.allapot === 'nem_tamogatott'}<Ikon ikon={TriangleAlert} />{:else}<Ikon ikon={CircleCheck} />{/if}{kodSzoveg(PLUGIN_ALLAPOT, p.allapot, 'import.plugin.nem_tamogatott')}</span></li>
            {/each}
          </ul>
        {/if}
        {#if kozossegi.length}
          <h5>{t('import.plugin.kozossegi_cim')}</h5>
          <ul class="pluginok" data-lista="kozossegi-pluginok">
            {#each kozossegi as p (p.id)}
              <li data-plugin={p.id}><span class="ut">{p.id}</span> <span class="plugin-allapot nem"><Ikon ikon={TriangleAlert} />{t('import.plugin.nem_tamogatott')}</span></li>
            {/each}
          </ul>
          <p class="halvany">{t('import.plugin.kozossegi_leiras')}</p>
        {/if}
      </section>
    {/if}
  {/if}

  {#if fajlSorok.length}
    <details class="fajlreszlet">
      <summary>{t('import.fajlok.cim')}</summary>
      <ul class="fajlok" aria-label={t('import.fajlok.lista')}>
        {#each fajlSorok as f, i (i)}<li><span class="ut">{f.ut}</span> <span class="halvany">{meretSzoveg(f.meret)} · {kodSzoveg(MUVELET, f.muvelet, 'import.muvelet.masol')}</span></li>{/each}
      </ul>
      {#if e.fajlok_csonkitva}<p class="halvany">{t('import.lista_csonkitva')}</p>{/if}
    </details>
  {/if}
</div>

<style>
  .elonezet { display: flex; flex-direction: column; gap: var(--t-4); }
  section { display: flex; flex-direction: column; gap: var(--t-2); }
  h4, h5 { margin: 0; font-weight: var(--suly-kozepes); }
  h4 { display: flex; align-items: center; gap: var(--t-2); font-size: var(--betu-torzs); }
  h5 { font-size: var(--betu-ui); color: var(--szoveg-masodlagos); margin-top: var(--t-2); }
  p { margin: 0; }
  .eredmeny { display: flex; align-items: center; gap: var(--t-2); }
  .halvany { color: var(--szoveg-masodlagos); font-size: var(--betu-kicsi); }
  .szam { color: var(--szoveg-masodlagos); font-weight: var(--suly-normal); }
  dl { display: grid; grid-template-columns: max-content 1fr; gap: var(--t-1) var(--t-4); margin: 0; }
  dt { color: var(--szoveg-masodlagos); }
  dd { margin: 0; overflow-wrap: anywhere; user-select: text; }
  ul { margin: 0; padding-inline-start: var(--t-5); }
  ul li { margin-block: var(--t-1); }
  .akadalyok, .figyelmek, .pluginok { list-style: none; padding: 0; }
  .akadalyok li, .figyelmek li { display: flex; align-items: flex-start; gap: var(--t-2); padding: var(--t-2) var(--t-3); border-radius: var(--kerekites); }
  .akadalyok li { background: var(--hiba-hatter); color: var(--hiba); }
  .figyelmek li { background: var(--figyelmeztetes-hatter); color: var(--figyelmeztetes); }
  .figyelem { display: flex; align-items: flex-start; gap: var(--t-2); color: var(--figyelmeztetes); }
  .plugin-allapot { display: inline-flex; align-items: center; gap: var(--t-1); color: var(--szoveg-masodlagos); font-size: var(--betu-kicsi); }
  .plugin-allapot.nem { color: var(--figyelmeztetes); }
  .pluginok li { display: flex; align-items: center; gap: var(--t-3); justify-content: space-between; }
  .fajlok { max-height: calc(var(--t-8) * 4); overflow: auto; }
  .ut { overflow-wrap: anywhere; user-select: text; }
  table { border-collapse: collapse; width: 100%; }
  th, td { text-align: start; padding: var(--t-1) var(--t-2); border-bottom: var(--keret-vastag) solid var(--keret); vertical-align: top; }
  thead th { color: var(--szoveg-masodlagos); font-size: var(--betu-kicsi); font-weight: var(--suly-normal); }
  tbody th { font-weight: var(--suly-normal); }
  summary { cursor: default; }
</style>
