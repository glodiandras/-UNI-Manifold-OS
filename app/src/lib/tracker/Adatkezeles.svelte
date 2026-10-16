<!--
  A tracker adatainak kezelése (C27): a használati mérés JSON-exportja és az adatok törlése. A törlés kétlépcsős
  (megerősítés), és csak a tracker saját adatát érinti — a vaultot és a naptár-importot nem; előtte a kliens a törlés
  hatókörébe eső puffert eldobja és megvárja a már úton lévő köteget (T110). Az export a core `{szemelyes}/export/`
  mappájába is leírja a fájlt, és a vágólapra másolja a JSON-t. Alapból csak a használati adatot exportálja (jegyzetútvonal
  nélkül); a tevékenységnapló (jegyzetútvonalakkal) külön, megnevezett választás (T111).
-->
<script lang="ts">
  import { t, tk, tp } from '../i18n';
  import { ApiHiba } from '../core/api';
  import { ertesitesek } from '../ertesites/ertesites.svelte';
  import { trackerApi } from './api';
  import { trackerKliens } from './kliens.svelte';
  import { hasznalatVezerlo, statisztikaVezerlo } from './adat.svelte';
  import { maiNap, napEltol } from './megjelenites';
  import type { TorlesMit } from './tipusok';

  let { onvaltozas = () => {} }: { onvaltozas?: () => void } = $props();

  type Mit = TorlesMit;
  const CIMKE: Record<Mit, string> = { tevekenyseg: tk('a tevékenységnaplót'), hasznalat: tk('a használati mérést'), minden: tk('a tracker minden adatát') };

  let megerosit = $state<Mit | null>(null);
  let valaszt = $state(false); // a törlés választéka csak a „Törlés…” gomb után látszik (kevés látszó funkció)
  let fut = $state(false);

  async function exportal(tevekenyseg: boolean) {
    fut = true;
    try {
      const ig = maiNap();
      const r = await trackerApi.exportal(napEltol(ig, -89), ig, tevekenyseg);
      let masolva = false;
      try {
        await navigator.clipboard.writeText(JSON.stringify(r.tartalom, null, 1));
        masolva = true;
      } catch {
        /* a vágólap nem érhető el: a fájl így is megvan */
      }
      const tartalom = tevekenyseg ? t('a használati adat és a tevékenységnapló (jegyzetútvonalakkal)') : t('a használati adat (jegyzetútvonal nélkül)');
      ertesitesek.ertesit({
        szint: 'siker',
        cim: tevekenyseg ? t('A használati adat és a tevékenységnapló exportálva') : t('A használati adat exportálva'),
        szoveg: masolva ? t('{ut} — a vágólapra is került: {tartalom}', { ut: r.ut, tartalom }) : t('{ut} — {tartalom}', { ut: r.ut, tartalom }),
        idotartam: 10000,
      });
    } catch (e) {
      ertesitesek.ertesit({ szint: 'hiba', cim: t('Az export nem sikerült'), szoveg: e instanceof ApiHiba ? e.message : String(e) });
    } finally {
      fut = false;
    }
  }

  async function torol(mit: Mit) {
    fut = true;
    await trackerKliens.torlesElott(mit);
    try {
      const r = await trackerApi.torol(mit);
      ertesitesek.ertesit({ szint: 'info', cim: t('Törölve: {mit}', { mit: t(CIMKE[mit]) }), szoveg: tp('{n} sor', r.torolt) });
      megerosit = null;
      valaszt = false;
      void statisztikaVezerlo.frissit();
      void hasznalatVezerlo.frissit();
      onvaltozas();
    } catch (e) {
      ertesitesek.ertesit({ szint: 'hiba', cim: t('A törlés nem sikerült'), szoveg: e instanceof ApiHiba ? e.message : String(e) });
    } finally {
      trackerKliens.torlesUtan();
      fut = false;
    }
  }
</script>

<div class="adatok">
  {#if megerosit}
    <p class="kerdes" role="alert">{t('Biztosan törlöd {mit}? Ez nem vonható vissza.', { mit: t(CIMKE[megerosit]) })}</p>
    <div class="sor">
      <button type="button" class="m-gomb semleges gomb veszely" disabled={fut} onclick={() => void torol(megerosit!)}>{t('Igen, törlés')}</button>
      <button type="button" class="m-gomb semleges gomb" disabled={fut} onclick={() => ((megerosit = null), (valaszt = false))}>{t('Mégse')}</button>
    </div>
  {:else if valaszt}
    <div class="sor">
      <button type="button" class="m-gomb semleges gomb" disabled={fut} onclick={() => (megerosit = 'tevekenyseg')}>{t('Tevékenységnapló')}</button>
      <button type="button" class="m-gomb semleges gomb" disabled={fut} onclick={() => (megerosit = 'hasznalat')}>{t('Használati mérés')}</button>
      <button type="button" class="m-gomb semleges gomb" disabled={fut} onclick={() => (megerosit = 'minden')}>{t('Minden|torles')}</button>
      <button type="button" class="m-gomb semleges gomb" disabled={fut} onclick={() => (valaszt = false)}>{t('Mégse')}</button>
    </div>
  {:else}
    <div class="sor">
      <button type="button" class="m-gomb semleges gomb" disabled={fut} onclick={() => void exportal(false)}>{t('Export (használat)')}</button>
      <button type="button" class="m-gomb semleges gomb" disabled={fut} title={t('A jegyzetek útvonalait is tartalmazza')} onclick={() => void exportal(true)}>{t('Export (használat + tevékenységnapló)')}</button>
      <button type="button" class="m-gomb semleges gomb" disabled={fut} onclick={() => (valaszt = true)}>{t('Törlés…')}</button>
    </div>
  {/if}
</div>

<style>
  .adatok {
    margin-top: var(--t-3);
  }

  .sor {
    display: flex;
    flex-wrap: wrap;
    gap: var(--t-2);
  }

  .kerdes {
    margin: 0 0 var(--t-2);
    color: var(--szoveg);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
  }

  .veszely {
    border-color: var(--hiba);
    color: var(--hiba);
  }
</style>
