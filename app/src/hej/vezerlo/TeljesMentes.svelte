<script lang="ts">
  import { t } from '../../lib/i18n';
  import { onMount } from 'svelte';
  import { hibaSzoveg, kerdez } from '../../lib/core/api';
  import { ertesitesek } from '../../lib/ertesites/ertesites.svelte';
  import { szerkesztok } from '../../szerkeszto/szerkesztok.svelte';
  import { idoRovid } from '../../lib/vezerlo/megjelenites';
  import { feladatsor } from '../../lib/vezerlo/feladatsor.svelte';
  let adat = $state<{
    ido: string | null; ellenorzott: boolean; kulso?: boolean; csatlakoztatva: boolean; cel?: string;
    linkelt?: number; masolt?: number; figyelo_be?: boolean; figyelo_cel?: string | null;
  } | null>(null);
  let cel = $state('');
  let fut = $state(false);
  let hiba = $state('');
  function frissit() { return kerdez<typeof adat>('/api/mentes/teljes').then(v => adat = v, e => hiba = hibaSzoveg(e)); }
  onMount(() => { void frissit(); });
  let legutobbi = '';
  $effect(() => {
    const kesz = feladatsor.lista.filter(f => f.tipus === 'teljes_mentes' && f.allapot === 'kesz').map(f => f.id).join(',');
    if (kesz !== legutobbi) { legutobbi = kesz; void frissit(); }
  });
  async function indit() {
    fut = true; hiba = '';
    try {
      await szerkesztok.dokumentumok.mindLezar();
      if (szerkesztok.dokumentumok.lista().some(d => !d.csakOlvashato && d.mentetlen)) {
        throw new Error(t('Van még mentetlen változás. A teljes mentés előtt rendezd a mentési hibát.'));
      }
      await kerdez('/api/feladatok', { metodus: 'POST', torzs: { tipus: 'teljes_mentes', parameterek: { cel } } });
      ertesitesek.ertesit({ szint: 'info', cim: t('A teljes mentés elindult'), szoveg: t('A haladás a Feladatok között látható. Az ellenőrzés végéig hagyd csatlakoztatva a lemezt.') });
    } catch (e) { hiba = hibaSzoveg(e); }
    finally { fut = false; }
  }
</script>

<section aria-label={t('Teljes külső mentés')}>
  <h3>{t('Teljes külső mentés')}</h3>
  {#if adat?.ellenorzott && adat.kulso && adat.ido}
    <p>{t('Utolsó ellenőrzött mentés:')} {idoRovid(adat.ido)}{adat.cel ? ` (${adat.cel})` : ''}.
      {adat.csatlakoztatva ? t('A mentési lemez csatlakoztatva.') : t('A mentési lemez most nem érhető el; az ellenőrzés a lemez nélkül nem ismételhető.')}</p>
  {:else}<p>{t('Még nincs ellenőrzött mentés külső lemezen. A belső szövegmentés nem tartalmazza a médiát.')}</p>{/if}
  <p>{t('Minden futás új, ellenőrzőösszeggel ellenőrzött változat; a változatlan fájlt az előzőből hard linkkel veszi át. A modellek és a futtatókörnyezet nincs benne: visszaállítás után újra le kell tölteni őket.')}</p>
  {#if adat?.figyelo_be && adat.figyelo_cel}
    <p>{t('Lemezfigyelés bekapcsolva: ha a(z) {cel} elérhető, és az utolsó mentés régi, a mentés magától sorba áll.', { cel: adat.figyelo_cel })}</p>
  {/if}
  <label>{t('Célmappa a külső lemezen')} <input bind:value={cel} placeholder={t('/Volumes/<külső lemez>/Manifold')} /></label>
  <button class="m-gomb semleges" disabled={fut || !cel.trim()} onclick={indit}>{t('Teljes mentés indítása')}</button>
  {#if hiba}<p role="alert">{hiba}</p>{/if}
</section>

<style>
  section { margin-top: var(--t-4); border-top: var(--keret-vastag) solid var(--keret); padding-top: var(--t-3); }
  h3, p, label { font-size: var(--betu-ui); line-height: var(--sor-ui); }
  label { display: grid; gap: var(--t-1); margin-bottom: var(--t-2); }
  input { min-width: 0; }
  p { color: var(--szoveg-halvany); }
  [role="alert"] { color: var(--hiba); }
</style>
