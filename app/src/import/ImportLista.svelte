<!--
  Az importok listája (F8): az ehhez a telepítéshez tartozó Obsidian-importok és ennek a munkatérnek a v2-importjai, legújabb elöl,
  állapottal (ikon + szó), időpontokkal, eredménnyel / hibával, a napló helyével. Innen folytatható a megszakadt import és
  visszavonható a kész. A lista a core `import` eseményére frissül.
-->
<script lang="ts">
  import { getContext, onMount, untrack } from 'svelte';
  import { CircleAlert, CircleCheck, Folder, Info, RotateCcw, TriangleAlert } from '../lib/ikon/ikonok';
  import { t, tp } from '../lib/i18n';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import HibaPanel from '../lib/ui/HibaPanel.svelte';
  import UresAllapot from '../lib/ui/UresAllapot.svelte';
  import { meretSzoveg } from '../lib/adatvedelem/megjelenites';
  import type { CoreKapcsolat } from '../lib/core/ws.svelte';
  import { importApi } from '../lib/import/api';
  import { ALLAPOT_CIM, FAJTA_CIM, allapotKulcs, hibaKodbol, idoSzoveg, importHiba, szam, type ImportHiba } from '../lib/import/megjelenites';
  import type { ImportAllapot, ImportFajta } from '../lib/import/tipusok';
  import { KORNYEZET_KULCS, type Kornyezet } from '../lib/kornyezet';
  import Visszaford from './Visszaford.svelte';

  let { fajta = 'obsidian', kapcsolat: kapcsolatKivulrol, onfolytat }: {
    /** Melyik fajta látszik (a v2-importok csak a Developer-szakaszban kérdezhetők). */
    fajta?: ImportFajta;
    kapcsolat?: CoreKapcsolat | null;
    onfolytat?: (a: ImportAllapot) => void;
  } = $props();

  const kontextus = getContext<Kornyezet | undefined>(KORNYEZET_KULCS);
  const kapcsolat = untrack(() => (kapcsolatKivulrol === undefined ? (kontextus?.kapcsolat ?? null) : kapcsolatKivulrol));

  let elemek = $state<ImportAllapot[] | null>(null);
  let betoltes = $state(false);
  let hiba = $state<ImportHiba | null>(null);
  let reszlet = $state<string | null>(null);
  let visszaId = $state<string | null>(null);
  let sorszam = 0;

  const lista = $derived((elemek ?? []).filter((a) => a.fajta === fajta));

  async function betolt() {
    const sz = ++sorszam;
    betoltes = true;
    try {
      const r = await importApi.lista();
      if (sz !== sorszam) return;
      elemek = r.importok;
      hiba = null;
    } catch (e) {
      if (sz !== sorszam) return;
      hiba = importHiba(e);
    } finally {
      if (sz === sorszam) betoltes = false;
    }
  }

  onMount(() => {
    void betolt();
    if (!kapcsolat) return;
    const le = [
      kapcsolat.figyel('import', (e) => { if (e.allapot !== undefined) void betolt(); }),
      kapcsolat.figyel('hello', () => void betolt()),
      kapcsolat.figyel('kimaradt', () => void betolt()),
    ];
    return () => le.forEach((f) => f());
  });

  const IKON = { fut: Info, megszakadt: TriangleAlert, megszakitva: TriangleAlert, hiba: CircleAlert, kesz: CircleCheck, visszaforditva: RotateCcw, reszben_visszaforditva: TriangleAlert } as const;
  const folytathato = (a: ImportAllapot) => a.fajta === 'obsidian' && (a.allapot === 'hiba' || a.allapot === 'megszakitva' || allapotKulcs(a) === 'megszakadt');
  const visszafordithato = (a: ImportAllapot) => a.allapot === 'kesz' || a.allapot === 'hiba' || a.allapot === 'megszakitva' || allapotKulcs(a) === 'megszakadt';
</script>

<section class="lista" aria-label={t('import.lista.cim')} data-import-lista={fajta} aria-busy={betoltes}>
  <div class="fej">
    <h4>{t('import.lista.cim')}</h4>
    <button type="button" class="m-gomb semleges" disabled={betoltes} onclick={() => void betolt()}>{t('import.lista.frissit')}</button>
  </div>
  {#if hiba}
    <HibaPanel mi={hiba.mi} javitas={hiba.javitas} ujra={() => void betolt()} ujraCimke={t('import.ujra')} />
  {:else if elemek === null}
    <p role="status" class="halvany">{t('import.lista.betoltes')}</p>
  {:else if lista.length === 0}
    <UresAllapot ikon={Folder} cim={t('import.lista.ures_cim')} leiras={fajta === 'v2' ? t('import.lista.ures_v2') : t('import.lista.ures_leiras')} kicsi />
  {:else}
    <ul>
      {#each lista as a (a.id)}
        {@const kulcs = allapotKulcs(a)}
        {@const h = a.hiba ? hibaKodbol(a.hiba.kod, a.hiba.uzenet, a.hiba.param) : null}
        <li data-import={a.id} data-allapot={kulcs}>
          <div class="sorfej">
            <strong>{t(FAJTA_CIM[a.fajta])}</strong>
            <span class="allapot" class:rossz={kulcs === 'hiba'} class:figy={kulcs === 'megszakadt' || kulcs === 'megszakitva' || kulcs === 'reszben_visszaforditva'}><Ikon ikon={IKON[kulcs]} />{t(ALLAPOT_CIM[kulcs])}</span>
          </div>
          <dl>
            <dt>{t('import.osszesites.forras')}</dt><dd class="ut">{a.forras ?? '–'}</dd>
            {#if a.fajta === 'obsidian'}<dt>{t('import.osszesites.cel')}</dt><dd class="ut">{a.cel ?? '–'}</dd>{/if}
            <dt>{t('import.lista.kezdve')}</dt><dd>{idoSzoveg(a.kezdve)}</dd>
            <dt>{t('import.lista.frissitve')}</dt><dd>{idoSzoveg(a.frissitve)}</dd>
          </dl>
          {#if a.allapot === 'kesz' && a.eredmeny}
            <p class="halvany">
              {#if a.fajta === 'obsidian'}{t('{db} fájl másolva · {meret}', { db: szam(a.eredmeny.masolt_db), meret: meretSzoveg(a.eredmeny.bajt) })}{:else}{tp('{n} beállítás módosult', a.eredmeny.valtozas ?? 0)}{/if}
            </p>
          {/if}
          {#if h && a.allapot === 'hiba'}
            <p class="hiba" role="alert">{h.mi}</p>
            <p class="halvany">{h.javitas}</p>
          {/if}
          {#if visszaId === a.id}
            <Visszaford id={a.id} fajta={a.fajta} onkesz={() => void betolt()} onmegse={() => (visszaId = null)} />
          {:else}
            <div class="gombok">
              {#if folytathato(a) && onfolytat}<button type="button" class="m-gomb semleges" onclick={() => onfolytat?.(a)}>{t('import.attekint_folytat')}</button>{/if}
              {#if visszafordithato(a) && kulcs !== 'fut'}<button type="button" class="m-gomb semleges" onclick={() => (visszaId = a.id)}>{t('import.visszaford.gomb')}</button>{/if}
              <button type="button" class="m-gomb link" aria-expanded={reszlet === a.id} onclick={() => (reszlet = reszlet === a.id ? null : a.id)}>{reszlet === a.id ? t('import.lista.reszlet_be') : t('import.lista.reszlet')}</button>
            </div>
          {/if}
          {#if reszlet === a.id}
            <dl class="naplo" data-naplo>
              {#if a.eredmeny?.naplo}<dt>{t('import.lista.naplo')}</dt><dd class="ut">{a.eredmeny.naplo}</dd>{/if}
              {#if a.opciok && a.fajta === 'obsidian'}
                <dt>{t('import.opcio.obsidian')}</dt><dd>{a.opciok.obsidian_mappa === false ? t('import.ertek.ki') : t('import.ertek.be')}</dd>
                <dt>{t('import.opcio.kuka')}</dt><dd>{a.opciok.kuka_mappa ? t('import.ertek.be') : t('import.ertek.ki')}</dd>
              {/if}
              {#if a.eredmeny?.beallitasok_irva?.length}<dt>{t('import.kesz.beallitasok')}</dt><dd>{a.eredmeny.beallitasok_irva.length}</dd>{/if}
              {#if a.eredmeny?.irt?.length}<dt>{t('import.v2.kesz_irt')}</dt><dd class="ut">{a.eredmeny.irt.join(', ')}</dd>{/if}
              {#if a.visszaforditas}
                <dt>{t('import.lista.visszaforditas')}</dt>
                <dd>{a.fajta === 'v2' ? tp('{n} beállításfájl visszaállítva', a.visszaforditas.visszaallitva?.length ?? 0) : tp('{n} elem a Kukába került', a.visszaforditas.kukaba?.length ?? 0)}{#if a.visszaforditas.megtartva?.length} · {tp('{n} fájl maradt', a.visszaforditas.megtartva.length)}{/if}</dd>
              {/if}
              <dt>{t('import.lista.azonosito')}</dt><dd class="ut">{a.id}</dd>
            </dl>
          {/if}
        </li>
      {/each}
    </ul>
  {/if}
</section>

<style>
  .lista { display: flex; flex-direction: column; gap: var(--t-3); min-width: 0; }
  .fej { display: flex; align-items: center; justify-content: space-between; gap: var(--t-3); }
  h4 { margin: 0; font-size: var(--betu-torzs); font-weight: var(--suly-kozepes); }
  p { margin: 0; }
  ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--t-3); }
  li { display: flex; flex-direction: column; gap: var(--t-2); padding: var(--t-3); border: var(--keret-vastag) solid var(--keret); border-radius: var(--kerekites); }
  .sorfej { display: flex; align-items: center; justify-content: space-between; gap: var(--t-3); }
  .allapot { display: inline-flex; align-items: center; gap: var(--t-1); color: var(--szoveg-masodlagos); }
  .allapot.rossz { color: var(--hiba); }
  .allapot.figy { color: var(--figyelmeztetes); }
  .halvany { color: var(--szoveg-masodlagos); font-size: var(--betu-kicsi); }
  .hiba { display: flex; align-items: flex-start; color: var(--hiba); }
  dl { display: grid; grid-template-columns: max-content 1fr; gap: var(--t-1) var(--t-4); margin: 0; }
  dt { color: var(--szoveg-masodlagos); }
  dd { margin: 0; overflow-wrap: anywhere; user-select: text; }
  .gombok { display: flex; flex-wrap: wrap; gap: var(--t-2); }
  .ut { overflow-wrap: anywhere; }
</style>
