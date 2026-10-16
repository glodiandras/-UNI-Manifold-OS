<!--
  A beágyazott összefoglaló a jegyzetben (C26b): csendes fejléc → a számozott állítások, mindegyik mellett a forrás-link, és
  kattintásra a jegyzet szó szerinti mondata. A core elemzése adja a sodródást: ha a forrás azóta megváltozott (az idézet már
  nem áll szó szerint), az állítás „elavult lehet” jelölést kap, és fent egy sor ajánlja az újragenerálást. Csak olvas; az
  újragenerálás a `osszefoglalas` feladat (gépi írás, visszavonható). Csak tokenekből rajzol (25. döntés).
-->
<script lang="ts">
  import { tartalmiNyelv } from '../lib/munkater/nyelv.svelte';
  import { ApiHiba } from '../lib/core/api';
  import { nyelv, t, tp } from '../lib/i18n';
  import { ertesitesek } from '../lib/ertesites/ertesites.svelte';
  import { szerkesztok } from '../szerkeszto/szerkesztok.svelte';
  import { linkMegnyit, nyitasMod } from '../szerkeszto/linkek/navigacio';
  import { SZINT_NEV } from './allando';
  import { osszefoglalasApi, type OsszAllitas, type OsszJegyzet } from './api';

  let { ut, forras, cim }: { ut: string; forras: string; cim: string } = $props();

  let adat = $state<OsszJegyzet | null>(null);
  let hiba = $state<string | null>(null);
  let kuld = $state(false);
  let nyitott = $state<Set<string>>(new Set());

  const uzenet = (e: unknown) => (e instanceof ApiHiba ? e.message : e instanceof Error ? e.message : String(e));

  export async function betolt(): Promise<void> {
    hiba = null;
    try {
      adat = await osszefoglalasApi.jegyzet(ut);
    } catch (e) {
      adat = null;
      hiba = uzenet(e);
    }
  }

  $effect(() => {
    void ut;
    void betolt();
  });

  const elavult = $derived(adat ? adat.allitasok.filter((a) => a.sodrodott || a.horgony_hianyzik || a.forras_hianyzik).length : 0);
  const forrasHianyzik = $derived(!!adat && adat.forras_hianyzik.length > 0);

  function nyit(e: MouseEvent, a: OsszAllitas) {
    e.preventDefault();
    void linkMegnyit({ forras, cel: a.cel, alcel: a.alcel }, nyitasMod(e));
  }

  function idezetValt(id: string) {
    const uj = new Set(nyitott);
    if (uj.has(id)) uj.delete(id);
    else uj.add(id);
    nyitott = uj;
  }

  function jelzes(a: OsszAllitas): string {
    if (a.forras_hianyzik) return t('a forrás már nincs meg');
    if (a.sodrodott) return t('elavult lehet: a forrás azóta megváltozott');
    if (a.horgony_hianyzik) return t('a hivatkozott hely már nincs a forrásban');
    return '';
  }

  async function ujra() {
    if (!adat?.szint || !adat.forras_ut || adat.szint !== 'jegyzet' || kuld) return;
    kuld = true;
    try {
      const p = szerkesztok.aktiv;
      if (p && p.ut === adat.forras_ut) await p.mentes();       // a gépi írás mentetlen dokumentumba nem ír (28(c))
      await osszefoglalasApi.keszit({ szint: 'jegyzet', ut: adat.forras_ut });
      ertesitesek.ertesit({ szint: 'info', cim: t('Az összefoglaló újra készül'), szoveg: t('Ami átmegy a kapukon, felváltja a mostanit (visszavonható).') });
    } catch (e) {
      ertesitesek.ertesit({ szint: 'hiba', cim: t('Az újragenerálás nem indult el'), szoveg: uzenet(e) });
    } finally {
      kuld = false;
    }
  }
</script>

<div class="ossz" role="group" aria-label={t('Összefoglaló: {cim}', { cim })} lang={nyelv.kod}>
  {#if hiba}
    <p class="ossz-hiba" role="alert">{t('Az összefoglaló nem tölthető be: {hiba}', { hiba })}</p>
    <div class="ossz-sor"><button type="button" class="m-gomb semleges ossz-gomb" onclick={() => void betolt()}>{t('Újra')}</button></div>
  {:else if !adat}
    <p class="ossz-al">{t('Összefoglaló betöltése…')}</p>
  {:else}
    <div class="ossz-fej">
      <div>
        <div class="ossz-cim">{t('Összefoglaló · {cim}', { cim: adat.cim ?? cim })}</div>
        <div class="ossz-al">
          {tp('{n} állítás', adat.allitasok.length)} · {t(SZINT_NEV[adat.szint ?? 'jegyzet'] ?? adat.szint)}{adat.modell ? ` · ${adat.modell}` : ''}{adat.keszult ? ` · ${adat.keszult}` : ''}
        </div>
      </div>
      {#if adat.szint === 'jegyzet' && adat.forras_ut && !forrasHianyzik}
        <button type="button" class="m-gomb semleges ossz-gomb" disabled={kuld} onclick={() => void ujra()}>{t('Újragenerálás')}</button>
      {/if}
    </div>
    {#if elavult}
      <p class="ossz-megj" role="status">
        {tp('{n} állítás elavult lehet: a forrás azóta megváltozott', elavult)}{adat.szint === 'jegyzet' && !forrasHianyzik ? ' — ' + t('az újragenerálás frissíti') : ''}.
      </p>
    {/if}
    {#if adat.hibak.length && !adat.allitasok.length}
      <p class="ossz-hiba" role="alert">{t('Az összefoglaló jegyzetben nincs érvényes állítás ({lista}).', { lista: adat.hibak.map((h) => h.fajta.replaceAll('_', ' ')).join(', ') })}</p>
    {/if}
    <ol class="ossz-lista">
      {#each adat.allitasok as a (a.id)}
        {@const j = jelzes(a)}
        <li class:elavult={!!j}>
          <span class="ossz-szoveg" lang={tartalmiNyelv.kod}>{a.szoveg}</span>
          <a class="ossz-link" lang={tartalmiNyelv.kod} href={`#${a.id}`} title={a.alcel ? `${a.cel} › ${a.alcel}` : a.cel} onclick={(e) => nyit(e, a)}>{a.felirat}</a>
          <button
            type="button"
            class="ossz-idezet-gomb"
            aria-expanded={nyitott.has(a.id)}
            aria-label={t('A jegyzet mondata')}
            title={t('A jegyzet szó szerinti mondata')}
            onclick={() => idezetValt(a.id)}
          >„”</button>
          {#if j}<span class="ossz-jel">{j}</span>{/if}
          {#if nyitott.has(a.id)}
            <blockquote class="ossz-idezet" lang={tartalmiNyelv.kod}>{a.idezet}</blockquote>
          {/if}
        </li>
      {/each}
    </ol>
  {/if}
</div>

<style>
  .ossz {
    display: block;
    margin-block: var(--t-2);
    padding: var(--t-4);
    border: var(--keret-vastag) solid var(--keret);
    border-radius: var(--kerekites-nagy);
    background: var(--hatter-emelt);
    color: var(--szoveg);
    font-family: var(--betu-rendszer);
    font-size: var(--betu-ui);
    line-height: var(--sor-ui);
    white-space: normal;          /* a szerkesztő sora `pre-wrap`: a sablon térközei ne látsszanak */
  }

  .ossz-fej {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--t-2) var(--t-4);
  }

  .ossz-cim {
    font-weight: var(--suly-felkover);
  }

  .ossz-al {
    color: var(--szoveg-halvany);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
  }

  .ossz-sor {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--t-2);
    margin-top: var(--t-3);
  }

  .ossz-megj {
    margin: var(--t-3) 0 0;
    padding: var(--t-2) var(--t-3);
    border-radius: var(--kerekites);
    background: var(--figyelmeztetes-hatter);
    color: var(--figyelmeztetes);
  }

  .ossz-hiba {
    margin: var(--t-3) 0 0;
    color: var(--hiba);
  }

  .ossz-lista {
    margin: var(--t-3) 0 0;
    padding-left: var(--t-5);
  }

  .ossz-lista li {
    margin-block: var(--t-2);
  }

  .ossz-lista li.elavult .ossz-szoveg {
    color: var(--szoveg-masodlagos);
  }

  .ossz-link {
    margin-left: var(--t-2);
    color: var(--akcent-szoveg);
    font-size: var(--betu-kicsi);
  }

  .ossz-idezet-gomb {
    margin-left: var(--t-1);
    padding: 0 var(--t-1);
    border: 0;
    border-radius: var(--kerekites-jel);
    background: transparent;
    color: var(--szoveg-halvany);
    font: inherit;
    font-size: var(--betu-kicsi);
    cursor: pointer;
  }

  .ossz-idezet-gomb:hover,
  .ossz-idezet-gomb[aria-expanded='true'] {
    color: var(--szoveg);
  }

  .ossz-jel {
    display: block;
    color: var(--figyelmeztetes);
    font-size: var(--betu-kicsi);
    line-height: var(--sor-kicsi);
  }

  .ossz-idezet {
    margin: var(--t-1) 0 0;
    padding: var(--t-1) var(--t-3);
    border-left: 2px solid var(--keret-eros);
    color: var(--szoveg-masodlagos);
    font-size: var(--betu-kicsi);
  }

  .ossz-gomb:focus-visible,
  .ossz-idezet-gomb:focus-visible,
  .ossz-link:focus-visible {
    outline: var(--fokusz-vastag) solid var(--fokusz-gyuru);
    outline-offset: var(--fokusz-tav);
  }
</style>
