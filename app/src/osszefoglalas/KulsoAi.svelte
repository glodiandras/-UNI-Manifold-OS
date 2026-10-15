<!--
  „Külső AI válasza…” (C26b, 49. döntés): a visszamásolt válasz a közös forráshűség-kapun át dolgozódik fel (a core csak olvas),
  az átment állítások `## Állítások` blokkját a FELHASZNÁLÓ illeszti a szerkesztő kurzorához (a külső AI kalibrálatlan: gép
  nem ír belőle a vaultba; a beillesztés a szokásos írási úton megy, a ⌘Z egy lépés). Csak tokenekből rajzol (25. döntés).
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { ApiHiba } from '../lib/core/api';
  import { ertesitesek } from '../lib/ertesites/ertesites.svelte';
  import { kornyezet } from '../lib/kornyezet';
  import Atfedes from '../lib/ui/Atfedes.svelte';
  import { vagolapra } from '../szerkeszto/vagolap';
  import { osszefoglalasApi, type KulsoValasz } from './api';
  import { kulsoAi } from './kulsoAllapot.svelte';
  import { jegyzetNev, torzsBeszur } from './parancsok';

  const { felulet } = kornyezet();
  const PELDA = '[{"allitas": "…", "forras": "J1", "idezet": "…"}]';
  const OK_NEV: Record<string, string> = {
    forras_nelkul: 'forrás (idézet) nélkül',
    ismeretlen_forras: 'ismeretlen jegyzet-azonosító',
    kotott: 'az idézet nincs a jegyzetben',
    hossz: 'az idézet hossza nem megfelelő',
    tamogatas: 'az idézet nem támasztja alá',
    kenyes: 'szám vagy név nem szerepel az idézetben',
    tagadas: 'tagadás eltér',
    duplikatum: 'ismétlés',
    ugyanaz_a_hely: 'ugyanarra a helyre épül',
    allitas_hossz: 'túl rövid vagy hosszú állítás',
    tiltott_jeloles: 'tiltott jelölés',
  };

  let valasz = $state('');
  let folyik = $state(false);
  let hiba = $state<string | null>(null);
  let eredmeny = $state<KulsoValasz | null>(null);
  let bevitel: HTMLTextAreaElement | undefined = $state();

  onMount(() => bevitel?.focus());

  function bezar() {
    felulet.atfedes = null;
  }

  async function feldolgoz() {
    if (!valasz.trim() || folyik) return;
    folyik = true;
    hiba = null;
    eredmeny = null;
    try {
      eredmeny = await osszefoglalasApi.valasz(kulsoAi.utak, valasz);
    } catch (e) {
      hiba = e instanceof ApiHiba ? e.message : String(e);
    } finally {
      folyik = false;
    }
  }

  function beszur() {
    if (!eredmeny?.torzs) return;
    const r = torzsBeszur(eredmeny.torzs);
    if (!r.ok) {
      hiba = r.hiba ?? 'A beillesztés nem sikerült.';
      return;
    }
    ertesitesek.ertesit({ szint: 'siker', cim: 'Az állítások bekerültek', szoveg: `${eredmeny.allitasok} állítás a kurzornál (⌘Z visszavonja); a mentés a szokásos úton megy.` });
    bezar();
  }

  async function masol() {
    if (eredmeny?.torzs && (await vagolapra(eredmeny.torzs))) ertesitesek.ertesit({ szint: 'siker', cim: 'Az állítások a vágólapon vannak' });
  }

  function billentyu(e: KeyboardEvent) {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && !e.isComposing) {
      e.preventDefault();
      void feldolgoz();
    }
  }
</script>

<Atfedes cimke="Külső AI válasza" nev="kulso-ai" onbezar={bezar} szeles>
  <div class="doboz">
    <h2 class="cim">Külső AI válasza</h2>
    <p class="seg">
      Jegyzetek: {kulsoAi.utak.map(jegyzetNev).join(', ')}.
      {#if !kulsoAi.csomagKesz}A kontextus-csomagot előbb a „Kontextus-csomag a vágólapra” paranccsal tudod a külső AI elé vinni.{/if}
      Illeszd ide a válaszát (JSON); a forráshűség-kapu csak azt engedi át, ami a jegyzet szó szerinti mondatával alátámasztott.
    </p>
    <textarea
      bind:this={bevitel}
      bind:value={valasz}
      onkeydown={billentyu}
      class="mezo"
      rows="8"
      spellcheck="false"
      placeholder={PELDA}
      aria-label="A külső AI válasza"
    ></textarea>
    {#if hiba}<p class="hiba" role="alert">{hiba}</p>{/if}
    {#if eredmeny}
      <div class="eredmeny" role="status" aria-live="polite">
        <b>{eredmeny.allitasok} állítás ment át a kapun</b>{eredmeny.elvetett.length ? `, ${eredmeny.elvetett.length} kiesett` : ''}.
        {#if eredmeny.statisztika.nem_ertelmezheto}A válasz nem értelmezhető JSON-listaként.{/if}
        {#if eredmeny.elvetett.length}
          <ul class="elvetett">
            {#each eredmeny.elvetett.slice(0, 8) as x, i (i)}
              <li><span>{x.allitas.slice(0, 90)}</span> <small>— {OK_NEV[x.ok] ?? x.ok}</small></li>
            {/each}
          </ul>
        {/if}
        {#if eredmeny.torzs}<pre class="elonezet">{eredmeny.torzs}</pre>{/if}
      </div>
    {/if}
    <div class="gombok">
      <button type="button" class="m-gomb semleges masodlagos" onclick={bezar}>Bezár</button>
      {#if eredmeny?.torzs}
        <button type="button" class="m-gomb semleges masodlagos" onclick={() => void masol()}>Másolás</button>
        <button type="button" class="m-gomb elso" onclick={beszur}>Beillesztés a kurzornál</button>
      {:else}
        <button type="button" class="m-gomb elso" disabled={!valasz.trim() || folyik} onclick={() => void feldolgoz()}>
          {folyik ? 'Ellenőrzés…' : 'Ellenőrzés a kapun'} <kbd>⌘↵</kbd>
        </button>
      {/if}
    </div>
  </div>
</Atfedes>

<style>
  .doboz {
    display: flex;
    flex-direction: column;
    gap: var(--t-3);
    padding: var(--t-4) var(--t-5);
  }

  .cim {
    margin: 0;
    font-size: var(--betu-h4);
  }

  .seg {
    margin: 0;
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
  }

  .mezo {
    padding: var(--t-2) var(--t-3);
    border: var(--keret-vastag) solid var(--keret-mezo);
    border-radius: var(--kerekites);
    background: var(--hatter);
    color: var(--szoveg);
    font: inherit;
    resize: vertical;
  }

  .mezo:focus-visible {
    outline: var(--fokusz-vastag) solid var(--fokusz-gyuru);
    outline-offset: var(--fokusz-tav);
  }

  .hiba {
    margin: 0;
    color: var(--hiba);
    font-size: var(--betu-ui);
  }

  .eredmeny {
    font-size: var(--betu-ui);
    color: var(--szoveg-masodlagos);
  }

  .elvetett {
    margin: var(--t-1) 0 0;
    padding-left: var(--t-5);
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
  }

  .elonezet {
    max-height: 14em;
    margin: var(--t-2) 0 0;
    padding: var(--t-2) var(--t-3);
    overflow: auto;
    border-radius: var(--kerekites);
    background: var(--hatter-emelt);
    color: var(--szoveg);
    font: inherit;
    font-size: var(--betu-kicsi);
    white-space: pre-wrap;
  }

  .gombok {
    display: flex;
    justify-content: flex-end;
    gap: var(--t-2);
  }

  kbd {
    color: inherit;
  }
</style>
