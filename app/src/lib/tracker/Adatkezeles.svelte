<!--
  A tracker adatainak kezelése (C27): a használati mérés JSON-exportja és az adatok törlése. A törlés kétlépcsős
  (megerősítés), és csak a tracker saját adatát érinti — a vaultot és a naptár-importot nem; előtte a kliens a törlés
  hatókörébe eső puffert eldobja és megvárja a már úton lévő köteget (T110). Az export a core `{szemelyes}/export/`
  mappájába is leírja a fájlt, és a vágólapra másolja a JSON-t. Alapból csak a használati adatot exportálja (jegyzetútvonal
  nélkül); a tevékenységnapló (jegyzetútvonalakkal) külön, megnevezett választás (T111).
-->
<script lang="ts">
  import { ApiHiba } from '../core/api';
  import { ertesitesek } from '../ertesites/ertesites.svelte';
  import { trackerApi } from './api';
  import { trackerKliens } from './kliens.svelte';
  import { hasznalatVezerlo, statisztikaVezerlo } from './adat.svelte';
  import { maiNap, napEltol } from './megjelenites';
  import type { TorlesMit } from './tipusok';

  let { onvaltozas = () => {} }: { onvaltozas?: () => void } = $props();

  type Mit = TorlesMit;
  const CIMKE: Record<Mit, string> = { tevekenyseg: 'a tevékenységnaplót', hasznalat: 'a használati mérést', minden: 'a tracker minden adatát' };

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
      const tartalom = tevekenyseg ? 'a használati adat és a tevékenységnapló (jegyzetútvonalakkal)' : 'a használati adat (jegyzetútvonal nélkül)';
      ertesitesek.ertesit({
        szint: 'siker',
        cim: tevekenyseg ? 'A használati adat és a tevékenységnapló exportálva' : 'A használati adat exportálva',
        szoveg: `${r.ut} — ${masolva ? 'a vágólapra is került: ' : ''}${tartalom}`,
        idotartam: 10000,
      });
    } catch (e) {
      ertesitesek.ertesit({ szint: 'hiba', cim: 'Az export nem sikerült', szoveg: e instanceof ApiHiba ? e.message : String(e) });
    } finally {
      fut = false;
    }
  }

  async function torol(mit: Mit) {
    fut = true;
    await trackerKliens.torlesElott(mit);
    try {
      const r = await trackerApi.torol(mit);
      ertesitesek.ertesit({ szint: 'info', cim: `Törölve: ${CIMKE[mit]}`, szoveg: `${r.torolt} sor` });
      megerosit = null;
      valaszt = false;
      void statisztikaVezerlo.frissit();
      void hasznalatVezerlo.frissit();
      onvaltozas();
    } catch (e) {
      ertesitesek.ertesit({ szint: 'hiba', cim: 'A törlés nem sikerült', szoveg: e instanceof ApiHiba ? e.message : String(e) });
    } finally {
      trackerKliens.torlesUtan();
      fut = false;
    }
  }
</script>

<div class="adatok">
  {#if megerosit}
    <p class="kerdes" role="alert">Biztosan törlöd {CIMKE[megerosit]}? Ez nem vonható vissza.</p>
    <div class="sor">
      <button type="button" class="m-gomb semleges gomb veszely" disabled={fut} onclick={() => void torol(megerosit!)}>Igen, törlés</button>
      <button type="button" class="m-gomb semleges gomb" disabled={fut} onclick={() => ((megerosit = null), (valaszt = false))}>Mégse</button>
    </div>
  {:else if valaszt}
    <div class="sor">
      <button type="button" class="m-gomb semleges gomb" disabled={fut} onclick={() => (megerosit = 'tevekenyseg')}>Tevékenységnapló</button>
      <button type="button" class="m-gomb semleges gomb" disabled={fut} onclick={() => (megerosit = 'hasznalat')}>Használati mérés</button>
      <button type="button" class="m-gomb semleges gomb" disabled={fut} onclick={() => (megerosit = 'minden')}>Minden</button>
      <button type="button" class="m-gomb semleges gomb" disabled={fut} onclick={() => (valaszt = false)}>Mégse</button>
    </div>
  {:else}
    <div class="sor">
      <button type="button" class="m-gomb semleges gomb" disabled={fut} onclick={() => void exportal(false)}>Export (használat)</button>
      <button type="button" class="m-gomb semleges gomb" disabled={fut} title="A jegyzetek útvonalait is tartalmazza" onclick={() => void exportal(true)}>Export (használat + tevékenységnapló)</button>
      <button type="button" class="m-gomb semleges gomb" disabled={fut} onclick={() => (valaszt = true)}>Törlés…</button>
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
