<!--
  Egy modell a Model Managerben: telepítettség (a lemezről: nincs / részleges / kész / eltérő revízió), letöltés folyamatjelzővel és
  megszakítással (csak kattintásra, D3), törlés megerősítéssel (a felszabaduló hely kiírva), a feladatonkénti jel (Calibrated /
  Trial) és a „Test this model” folyamat. A hiba ikonnal és szóval jelenik meg.
-->
<script lang="ts">
  import { tick } from 'svelte';
  import { Check, CircleAlert, CircleCheck, CircleDashed, Cog, Download, FlaskConical, Info, Square, Trash2, TriangleAlert } from 'lucide';
  import { meretSzoveg } from '../lib/adatvedelem/megjelenites';
  import { t, tk } from '../lib/i18n';
  import Ikon from '../lib/ikon/Ikon.svelte';
  import type { ModellTar } from '../lib/modellek/allapot.svelte';
  import { ALLAPOT_CIM, ALLAPOT_LEIRAS, SZEREP_CIM, feladatJelek, gbSzoveg, letoltheto, lemezen, merheto, nyelvNev, tobbnyelvu } from '../lib/modellek/megjelenites';
  import type { Modell, TelepitAllapot } from '../lib/modellek/tipusok';
  import ProbaJel from './ProbaJel.svelte';
  import TesztPanel from './TesztPanel.svelte';

  let { m, tar }: { m: Modell; tar: ModellTar } = $props();

  let torlesKerdes = $state(false);
  let tesztNyitva = $state(false);
  let megsemGomb: HTMLButtonElement | undefined = $state();

  const letolt = $derived(tar.aktiv(m, 'letoltes'));
  const teszt = $derived(tar.aktiv(m, 'teszt'));
  const foglalt = $derived(!!tar.foglalt[m.id]);
  const uzenet = $derived(tar.uzenetek[m.id]);
  const jelek = $derived(feladatJelek(m));
  const IKON: Record<TelepitAllapot, typeof Check> = { nincs: CircleDashed, reszleges: TriangleAlert, ellenorizetlen: Info, kesz: CircleCheck, elter_revizio: TriangleAlert, konvertalasra_var: Cog };
  const LETOLTES_CIMKE = { reszleges: tk('Letöltés folytatása ({meret})'), elter_revizio: tk('A támogatott verzió letöltése ({meret})'), alap: tk('Letöltés ({meret})') };
  const letoltesCimke = $derived(m.allapot === 'reszleges' ? LETOLTES_CIMKE.reszleges : m.allapot === 'elter_revizio' ? LETOLTES_CIMKE.elter_revizio : LETOLTES_CIMKE.alap);

  // a mérés végén a panel nyitva marad: az eredmény (jel, okok, riport) ott látszik
  $effect(() => { if (teszt) tesztNyitva = true; });

  async function torlesNyit() {
    torlesKerdes = true;
    await tick();
    megsemGomb?.focus();
  }
  async function torol() {
    const r = await tar.torol(m);
    if (r) torlesKerdes = false;
  }
</script>

<li class="modell" data-modell={m.id} data-allapot={m.allapot}>
  <div class="fej">
    <h3>{m.id}</h3>
    <span class="cimke">{SZEREP_CIM[m.szerep] ? t(SZEREP_CIM[m.szerep]) : m.szerep}</span>
    {#if m.ajanlott}<span class="cimke">{t('modellek.ajanlott')}</span>{/if}
    <span class="cimke">{tobbnyelvu(m) ? t('modellek.nyelv.mind') : m.nyelvek.map(nyelvNev).join(', ')}</span>
  </div>
  <p class="meta">
    <span>{t('Forrás: {repo}', { repo: m.repo })}</span>
    <span>{t('Letöltés mérete: {meret}', { meret: gbSzoveg(m.meret_gb) })}</span>
    <span>{t('Csúcs-memória: {meret}', { meret: gbSzoveg(m.csucs_gb) })}</span>
    {#if m.licenc}<span>{t('Licenc: {licenc}', { licenc: m.licenc })}</span>{/if}
  </p>

  <p class="allapot" role="status" data-allapot-sor><Ikon ikon={IKON[m.allapot]} /><strong>{t(ALLAPOT_CIM[m.allapot])}</strong>
    {#if lemezen(m)}<span class="halvany">{t('{meret} a lemezen', { meret: meretSzoveg(m.lemez_bajt) })}</span>{/if}</p>
  {#if m.allapot !== 'kesz' && m.allapot !== 'nincs'}<p class="halvany">{t(ALLAPOT_LEIRAS[m.allapot])}</p>{/if}

  {#if jelek.length}
    <div class="jelek" aria-label={t('modellek.jelek')}>
      {#each jelek as j (j.feladat)}<ProbaJel jel={j.jel} mero={j.sor?.mero} feladat={tar.feladatCim(j.feladat)} />{/each}
    </div>
  {/if}

  {#if letolt}
    <div class="haladas">
      <progress max="100" value={letolt.szazalek} aria-label={t('{modell} letöltésének haladása', { modell: m.id })}></progress>
      <span class="halvany" role="status">{letolt.allapot === 'sorban' ? t('modellek.letoltes.sorban') : t('Letöltés… {szazalek} %', { szazalek: Math.round(letolt.szazalek) })}</span>
    </div>
  {/if}

  <div class="gombok">
    {#if letolt}
      <button type="button" class="m-gomb semleges" disabled={foglalt} onclick={() => void tar.megszakit(m)}><Ikon ikon={Square} />{t('modellek.letoltes.megszakit')}</button>
    {:else if letoltheto(m)}
      <button type="button" class="m-gomb" disabled={foglalt} onclick={() => void tar.letoltes(m)}><Ikon ikon={Download} />{t(letoltesCimke, { meret: gbSzoveg(m.meret_gb) })}</button>
    {/if}
    {#if merheto(m)}
      <button type="button" class="m-gomb semleges" aria-expanded={tesztNyitva} onclick={() => (tesztNyitva = !tesztNyitva)}><Ikon ikon={FlaskConical} />{t('modellek.teszt.gomb')}</button>
    {/if}
    {#if lemezen(m) && !torlesKerdes}
      <button type="button" class="m-gomb semleges" disabled={foglalt || !!letolt || !!teszt} title={letolt || teszt ? t('modellek.torles.foglalt') : undefined} onclick={() => void torlesNyit()}><Ikon ikon={Trash2} />{t('modellek.torles.gomb')}</button>
    {/if}
  </div>

  {#if torlesKerdes}
    <div class="megerosites" role="group" aria-label={t('{modell} törlésének megerősítése', { modell: m.id })}>
      <p>{t('Törlöd a(z) {modell} modellt? Ez {meret} helyet szabadít fel.', { modell: m.id, meret: meretSzoveg(m.lemez_bajt) })}</p>
      <p class="halvany">{t('modellek.torles.kovetkezmeny')}</p>
      <div class="gombok">
        <button type="button" class="m-gomb semleges" bind:this={megsemGomb} onclick={() => (torlesKerdes = false)}>{t('modellek.torles.megsem')}</button>
        <button type="button" class="m-gomb" disabled={foglalt} onclick={() => void torol()}><Ikon ikon={Trash2} />{t('Törlés, {meret} felszabadítása', { meret: meretSzoveg(m.lemez_bajt) })}</button>
      </div>
    </div>
  {/if}

  {#if uzenet}
    {#if uzenet.fajta === 'hiba'}
      <div class="uzenet-hiba">
        <p class="hiba" role="alert">{uzenet.szoveg}</p>
        {#if uzenet.reszletek?.length}<ul>{#each uzenet.reszletek as r, i (i)}<li class="hiba-reszlet"><Ikon ikon={CircleAlert} />{r}</li>{/each}</ul>{/if}
      </div>
    {:else}
      <div class="uzenet-ok" role="status">
        <p><Ikon ikon={uzenet.fajta === 'siker' ? CircleCheck : Info} />{uzenet.szoveg}</p>
        {#if uzenet.reszletek?.length}<ul>{#each uzenet.reszletek as r, i (i)}<li>{r}</li>{/each}</ul>{/if}
      </div>
    {/if}
  {/if}

  {#if tesztNyitva || teszt}<TesztPanel {m} {tar} />{/if}
</li>

<style>
  .modell { display: flex; flex-direction: column; gap: var(--t-2); padding: var(--t-4); border: var(--keret-vastag) solid var(--keret); border-radius: var(--kerekites); list-style: none; }
  p { margin: 0; }
  .fej { display: flex; flex-wrap: wrap; align-items: center; gap: var(--t-2); }
  h3 { margin: 0; font-size: var(--betu-ui); font-weight: var(--suly-felkover); }
  .cimke { padding: 0 var(--t-2); border: var(--keret-vastag) solid var(--keret); border-radius: var(--kerekites-kicsi); color: var(--szoveg-masodlagos); font-size: var(--betu-kicsi); line-height: var(--sor-kicsi); }
  .meta { display: flex; flex-wrap: wrap; gap: var(--t-1) var(--t-4); color: var(--szoveg-masodlagos); font-size: var(--betu-kicsi); line-height: var(--sor-kicsi); }
  .allapot { display: flex; flex-wrap: wrap; align-items: center; gap: var(--t-2); }
  .halvany { color: var(--szoveg-masodlagos); font-size: var(--betu-kicsi); line-height: var(--sor-kicsi); }
  .jelek { display: flex; flex-wrap: wrap; gap: var(--t-2); }
  .haladas { display: flex; align-items: center; gap: var(--t-3); }
  progress { flex: 1; min-width: 0; accent-color: var(--akcent-kitoltes); }
  .gombok { display: flex; flex-wrap: wrap; gap: var(--t-2); }
  .megerosites { display: flex; flex-direction: column; gap: var(--t-2); padding: var(--t-3); background: var(--hatter-oldalsav); border-radius: var(--kerekites); }
  .uzenet-hiba, .uzenet-ok { padding: var(--t-3); border-radius: var(--kerekites); }
  .uzenet-hiba { background: var(--hiba-hatter); color: var(--hiba); }
  .uzenet-ok { background: var(--hatter-oldalsav); }
  .uzenet-ok p, .hiba-reszlet { display: flex; align-items: flex-start; gap: var(--t-2); }
  ul { margin: var(--t-1) 0 0; padding-inline-start: var(--t-5); }
  .hiba-reszlet { list-style: none; margin-inline-start: calc(-1 * var(--t-5)); }
</style>
