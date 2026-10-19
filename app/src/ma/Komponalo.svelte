<script lang="ts">
  import { onDestroy, onMount, untrack } from 'svelte';
  import { hibaUzenet } from '../lib/core/api';
  import { beallitasok } from '../lib/beallitasok/allapot.svelte';
  import { ertesitesek } from '../lib/ertesites/ertesites.svelte';
  import { t, tk } from '../lib/i18n';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import { TriangleAlert } from '../lib/ikon/ikonok';
  import { kornyezet } from '../lib/kornyezet';
  import Atfedes from '../lib/ui/Atfedes.svelte';
  import { alapMappa } from '../bazis/ujJegyzet';
  import { komponaloAblak, kivonasVegez, osszefuzesTerv, osszefuzesVegez, osszefuzesVisszavon, type OsszefuzesTerv } from './komponaloAllapot.svelte';

  const { felulet, fajlok } = kornyezet();
  const keres = untrack(() => komponaloAblak.keres!);
  let el = true;
  onDestroy(() => { el = false; sorszam++; });
  const aktiv = () => el && komponaloAblak.keres === keres;
  let sorszam = 0;
  let mod = $state<'uj'|'meglevo'>(keres.mod === 'kivon' ? 'uj' : 'meglevo');
  let nev = $state('');
  let mappa = $state(alapMappa(untrack(() => beallitasok.ertek.fajlok.uj_mappa), keres.forras));
  let cel = $state('');
  let hely = $state<'veg'|'eleje'>('veg');
  let utana = $state(untrack(() => beallitasok.ertek.fajlok.kivonas_utana ?? 'link'));
  let terv = $state<OsszefuzesTerv | null>(null);
  let folyamat = $state<''|'terv'|'iras'>('');
  let hiba = $state('');
  let mezo: HTMLInputElement | undefined = $state();
  const cim = $derived(keres.mod === 'kivon' ? t('s1.komponalo.kivon') : t('s1.komponalo.osszefuz'));
  const celok = $derived(fajlok.lista.filter(f => f.tipus === 'md' && f.ut !== keres.forras && !f.kizart));
  const ervenyes = $derived(mod === 'uj' ? !!nev.trim() : !!cel.trim() && cel.trim() !== keres.forras);
  onMount(() => mezo?.focus());
  $effect(() => { void cel; void hely; terv = null; sorszam++; untrack(() => { if (folyamat === 'terv') folyamat = ''; }); });

  function bezar() { if (folyamat !== 'iras' && aktiv()) komponaloAblak.keres = null; }
  async function tervez() {
    const n = ++sorszam;
    folyamat = 'terv'; hiba = ''; terv = null;
    try {
      const r = await osszefuzesTerv(keres, cel.trim(), hely, aktiv);
      if (aktiv() && n === sorszam) terv = r;
    } catch (e) { if (aktiv() && n === sorszam) hiba = hibaUzenet(e); }
    finally { if (aktiv() && n === sorszam) folyamat = ''; }
  }
  async function vegrehajt() {
    if (folyamat || !ervenyes) return;
    if (keres.mod === 'osszefuz' && !terv) { await tervez(); return; }
    folyamat = 'iras'; hiba = '';
    try {
      if (keres.mod === 'kivon') {
        const r = await kivonasVegez(keres, mod === 'uj' ? { mod, nev: nev.trim(), mappa } : { mod, ut: cel.trim(), hely }, aktiv, utana);
        const ut = r.eredmeny.ut;
        ertesitesek.ertesit({ szint: r.cserelve ? 'siker' : 'figyelmeztetes', cim: t(r.cserelve ? tk('s1.komponalo.kivonva') : tk('s1.komponalo.forras_megmaradt')), szoveg: ut, idotartam: r.cserelve ? 6000 : 0, muvelet: { nev: t('Megnyitás'), futtat: () => felulet.munkaterulet.megnyit(ut) } });
        if (r.eredmeny.figyelmeztetes) ertesitesek.ertesit({ szint: 'figyelmeztetes', cim: t('Pillanatkép nélkül mentve'), szoveg: r.eredmeny.figyelmeztetes });
        if (aktiv()) { komponaloAblak.keres = null; if (r.cserelve) keres.nezet.focus(); }
      } else if (terv) {
        const r = await osszefuzesVegez(keres, terv, aktiv);
        ertesitesek.ertesit({ szint: r.forras_kukaban ? 'siker' : 'figyelmeztetes', cim: t(r.forras_kukaban ? tk('s1.komponalo.osszefuzve') : tk('s1.komponalo.kuka_hiba')), szoveg: r.forras_hiba || r.cel, idotartam: 0, muvelet: r.visszavonhato ? { nev: t('Visszavonás'), futtat: () => void osszefuzesVisszavon(r, felulet) } : undefined });
        if (!r.visszavonhato) ertesitesek.ertesit({ szint: 'figyelmeztetes', cim: t('s1.komponalo.undo_nincs'), szoveg: r.cel, idotartam: 0 });
        if (aktiv()) { komponaloAblak.keres = null; felulet.munkaterulet.megnyit(r.cel); }
      }
    } catch (e) {
      const uzenet = hibaUzenet(e);
      if (aktiv()) { hiba = uzenet; terv = null; }
      else ertesitesek.ertesit({ szint: 'hiba', cim: t('s1.komponalo.hiba'), szoveg: uzenet, idotartam: 0 });
    } finally { if (aktiv()) folyamat = ''; }
  }
</script>

<Atfedes cimke={cim} nev="komponalo" onbezar={bezar} szeles>
  <form onsubmit={(e) => { e.preventDefault(); void vegrehajt(); }}>
    <h1>{cim}</h1>
    <p class="forras">{keres.forras}</p>
    <fieldset disabled={!!folyamat}>
      {#if keres.mod === 'kivon'}
        <label>{t('s1.komponalo.cel_tipus')}<select bind:value={mod}><option value="uj">{t('s1.komponalo.uj')}</option><option value="meglevo">{t('s1.komponalo.meglevo')}</option></select></label>
      {/if}
      {#if mod === 'uj'}
        <label>{t('s1.komponalo.nev')}<input type="text" bind:this={mezo} bind:value={nev} autocomplete="off" /></label>
        <label>{t('Mappa')}<input type="text" bind:value={mappa} autocomplete="off" spellcheck="false" /></label>
      {:else}
        <label>{t('s1.komponalo.cel_ut')}<input type="text" bind:this={mezo} bind:value={cel} list="komponalo-jegyzetek" autocomplete="off" spellcheck="false" /></label>
        <datalist id="komponalo-jegyzetek">{#each celok as f (f.ut)}<option value={f.ut}></option>{/each}</datalist>
        <label>{t('s1.komponalo.hely')}<select bind:value={hely}><option value="veg">{t('s1.komponalo.veg')}</option><option value="eleje">{t('s1.komponalo.eleje')}</option></select></label>
      {/if}
      {#if keres.mod === 'kivon'}
        <label>{t('s1.napi.kivonas_utana')}<select bind:value={utana}><option value="link">{t('s1.napi.link')}</option><option value="beagyazas">{t('s1.napi.beagyazas')}</option><option value="semmi">{t('s1.napi.semmi')}</option></select></label>
        <p class="segito">{t('s1.komponalo.kivonas_leiras')}</p>
      {/if}
    </fieldset>
    {#if terv}
      <section class="terv" aria-label={t('s1.komponalo.terv')}>
        <p>{t('A(z) {forras} a Kukába kerül; a tartalma a(z) {cel} jegyzethez kerül.', { forras: terv.forras, cel: terv.cel })}</p>
        <p>{t('Átírandó linkek: {db}', { db: terv.modositott_linkek })}</p>
        <p>{t('A cél sorainak száma: {elotte} → {utana}', terv.cel_sorok)}</p>
        {#each terv.blokkolok as b}<p class="hiba" role="alert"><Ikon ikon={TriangleAlert} meret={14} />{b}</p>{/each}
        {#each terv.figyelmeztetesek as figy}
          <p class="figyelmeztetes"><Ikon ikon={TriangleAlert} meret={14} />
            {#if figy.kod === 'fuggo_tulajdonsag'}{t('Sémaütközés miatt kimaradó tulajdonságok: {kulcsok}', { kulcsok: (figy.kulcsok ?? []).join(', ') })}
            {:else if figy.kod === 'megmaradt_ertek'}{t('A cél meglévő értékei maradnak: {kulcsok}', { kulcsok: (figy.kulcsok ?? []).join(', ') })}
            {:else if figy.kod === 'beagyazas'}{t('Ellenőrizendő beágyazások: {db}', { db: figy.db ?? 0 })}
            {:else}{t('s1.komponalo.tulajdonsag_figyelmeztetes')}{/if}
          </p>
        {/each}
        {#each terv.fajlok as f (f.ut)}
          <details><summary>{f.ut}</summary>{#each f.linkek as l}<pre>{l.regi}{'\n→ '}{l.uj}</pre>{/each}</details>
        {/each}
      </section>
    {/if}
    {#if hiba}<p class="hiba" role="alert"><Ikon ikon={TriangleAlert} meret={14} />{hiba}</p>{/if}
    {#if keres.mod === 'kivon' && hiba}<p class="segito">{t('s1.komponalo.bizonytalan')}</p>{/if}
    <footer>
      <button type="button" class="m-gomb semleges" disabled={folyamat === 'iras'} onclick={bezar}>{t('Mégse')}</button>
      <button type="submit" class="m-gomb" disabled={!!folyamat || !ervenyes || !!terv && (!terv.ok || !!terv.blokkolok.length)}>{folyamat ? t('Folyamatban…') : keres.mod === 'kivon' ? t('s1.komponalo.kivon') : terv ? t('s1.komponalo.megerosit') : t('s1.komponalo.terv')}</button>
    </footer>
  </form>
</Atfedes>

<style>
  form { padding: var(--t-4); display: flex; flex-direction: column; gap: var(--t-3); }
  h1, p { margin: 0; }
  h1 { font-size: var(--betu-torzs); }
  .forras, .segito { color: var(--szoveg-halvany); overflow-wrap: anywhere; }
  fieldset { border: 0; padding: 0; margin: 0; display: flex; flex-direction: column; gap: var(--t-3); min-width: 0; }
  label { display: flex; flex-direction: column; gap: var(--t-1); }
  input, select { padding: var(--t-2); border: var(--keret-vastag) solid var(--keret-mezo); border-radius: var(--kerekites-kicsi); color: var(--szoveg); background: var(--hatter); font: inherit; min-width: 0; }
  input:focus-visible, select:focus-visible { outline: var(--fokusz-vastag) solid var(--fokusz-gyuru); outline-offset: var(--fokusz-tav); }
  .terv { display: flex; flex-direction: column; gap: var(--t-2); overflow-wrap: anywhere; }
  pre { white-space: pre-wrap; overflow-wrap: anywhere; font-family: var(--betu-mono); }
  .hiba, .figyelmeztetes { display: flex; align-items: center; gap: var(--t-1); }
  .hiba { color: var(--hiba); }
  .figyelmeztetes { color: var(--figyelmeztetes); }
  footer { display: flex; justify-content: flex-end; gap: var(--t-2); }
</style>
