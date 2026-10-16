// A felület-forráskód i18n-vizsgálója (F4): a ratchet-teszt (`i18n-ratchet.test.ts`) és a szótár-lefedettségi teszt (`i18n.test.ts`)
// közös elemzője. A Svelte saját elemzőjével olvassa a `.svelte` és a `.ts` fájlokat (a `.ts`-t `<script lang="ts">` közé csomagolva,
// így a sorszámok megmaradnak), és két dolgot gyűjt:
//   - `magyar`: ékezetes magyar betűt tartalmazó szöveg-literálok, amelyek NINCSENEK `t()`/`tp()`/`tk()` hívásban (a ratchet ezeket számolja);
//   - `kulcsok`: a `t('…')` / `tp('…')` / `tk('…')` hívások szöveg-kulcsai (a lefedettség-teszt ezeket veti a szótárhoz). Fordító hívásnak
//     csak a `…/i18n` modulból importált `t` / `tp` / `tk` számít (egy helyi `t` változó hívása nem).
//
// Magyar szöveg-egység: egy szöveg-literál, egy sablon-literál (a `${…}`-kel együtt 1), egy Svelte-sablon szövegcsomópont, egy
// statikus attribútum-szöveg. NEM számít: megjegyzés, `t()`/`tp()`/`tk()` első argumentuma (állandó szöveg), `console.*` híváshoz adott
// szöveg, import/export útvonal, objektum-kulcs és `obj['kulcs']` elérés, összehasonlítás (`=== 'Média'`) és `case` címke
// (a vault tulajdonságnevei és adatok), TypeScript-típusok, `<style>`, és az olyan sor, amelyen vagy előtte a sorban
// `i18n-ignore: <indok>` megjegyzés áll (a valódi adat — nem felületi szöveg — kivétele, indoklással).

import { parse } from 'svelte/compiler';

export interface Talalat {
  fajl: string;
  sor: number;
  szoveg: string;
}

export interface Kulcs {
  fajl: string;
  sor: number;
  kulcs: string;
  fajta: 't' | 'tp' | 'tk';
}

export interface Elemzes {
  magyar: Talalat[];
  kulcsok: Kulcs[];
  /** `t(\`…${x}…\`)`: a kulcs nem állandó szöveg (nem fordítható): a hívó a `t('… {x}', { x })` alakot használja. */
  dinamikus: Talalat[];
}

const EKEZETES = /[áéíóöőúüűÁÉÍÓÖŐÚÜŰ]/;
const KIVETEL_JEL = /i18n-ignore:\s*\S/;
const FORDITO_NEV = new Set(['t', 'tp', 'tk']);
/** A szótár-modul importjának útvonala: `…/i18n` (vagy `…/i18n/index`): csak az innen importált `t`/`tp`/`tk` fordító hívás. */
const I18N_MODUL = /(^|\/)i18n(\/index(\.ts)?)?$/;
/** Az elem (nem komponens) statikus attribútumai közül a felhasználónak mutatott szöveget hordozók. */
const SZOVEG_ATTR = new Set(['aria-label', 'aria-description', 'aria-roledescription', 'aria-placeholder', 'aria-valuetext', 'title', 'placeholder', 'alt', 'label']);
/** A TypeScript-csomópontok közül azok, amelyek értéket csomagolnak (az `expression` bejárandó); a többi (típus) kimarad. */
const TS_ERTEK = new Set(['TSAsExpression', 'TSSatisfiesExpression', 'TSNonNullExpression', 'TSTypeAssertion', 'TSInstantiationExpression']);
const OSSZEHASONLITO = new Set(['===', '!==', '==', '!=', 'in']);
const KIHAGYOTT_KULCS = new Set(['loc', 'start', 'end', 'type', 'leadingComments', 'trailingComments', 'metadata', 'css']);

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Csp = any;

function sorSzam(sorokKezdete: number[], pozicio: number): number {
  let lo = 0;
  let hi = sorokKezdete.length - 1;
  while (lo < hi) {
    const kozep = (lo + hi + 1) >> 1;
    if (sorokKezdete[kozep] <= pozicio) lo = kozep;
    else hi = kozep - 1;
  }
  return lo + 1;
}

/** Az állandó szöveg-kulcs egy `t()` első argumentumából: szöveg-literál, kifejezés nélküli sablon, vagy ezek `+` láncolata. */
function allandoSzoveg(n: Csp): string | null {
  if (!n) return null;
  if (n.type === 'Literal' && typeof n.value === 'string') return n.value;
  if (n.type === 'TemplateLiteral' && n.expressions.length === 0) return n.quasis[0].value.cooked ?? '';
  if (n.type === 'BinaryExpression' && n.operator === '+') {
    const a = allandoSzoveg(n.left);
    const b = allandoSzoveg(n.right);
    return a !== null && b !== null ? a + b : null;
  }
  return null;
}

export function elemez(fajl: string, forras: string): Elemzes {
  const svelte = fajl.endsWith('.svelte');
  const kod = svelte ? forras : `<script lang="ts">${forras.replaceAll('</script', '<\\/script')}</script>`;
  const gyoker = parse(kod, { modern: true }) as Csp;
  const sorok = kod.split('\n');
  const kezdetek: number[] = [0];
  for (let i = 0, p = 0; i < sorok.length - 1; i++) kezdetek.push((p += sorok[i].length + 1));

  const magyar: Talalat[] = [];
  const kulcsok: Kulcs[] = [];
  const dinamikus: Talalat[] = [];

  // a fájlban a szótár-modulból importált `t` / `tp` / `tk` helyi nevei (egy helyi `t` változó hívása nem fordítás)
  const fordito_nevek = new Map<string, Kulcs['fajta']>();
  for (const szkript of [gyoker.module, gyoker.instance])
    for (const d of (szkript?.content?.body ?? []) as Csp[]) {
      if (d.type !== 'ImportDeclaration' || !I18N_MODUL.test(String(d.source?.value ?? ''))) continue;
      for (const sp of d.specifiers as Csp[]) {
        const eredeti = sp.imported?.name ?? sp.imported?.value;
        if (sp.type === 'ImportSpecifier' && FORDITO_NEV.has(eredeti)) fordito_nevek.set(sp.local.name, eredeti);
      }
    }

  const kivetel = (sor: number) => KIVETEL_JEL.test(sorok[sor - 1] ?? '') || KIVETEL_JEL.test(sorok[sor - 2] ?? '');
  const jelol = (poz: number, szoveg: string, tomb: Talalat[] = magyar) => {
    const sor = sorSzam(kezdetek, poz);
    if (!kivetel(sor)) tomb.push({ fajl, sor, szoveg: szoveg.replace(/\s+/g, ' ').trim().slice(0, 90) });
  };
  /** A szöveg első nem-szóköz karakterének helye (a sor- és kivétel-meghatározáshoz). */
  const elsoKarakter = (n: Csp, szoveg: string) => n.start + (szoveg.length - szoveg.trimStart().length);

  function fordito(n: Csp): boolean {
    if (n.type !== 'CallExpression' || n.callee?.type !== 'Identifier' || !fordito_nevek.has(n.callee.name)) return false;
    const fajta = fordito_nevek.get(n.callee.name)!;
    const [elso, ...tobbi] = n.arguments as Csp[];
    const szoveg = allandoSzoveg(elso);
    if (szoveg !== null) kulcsok.push({ fajl, sor: sorSzam(kezdetek, n.start), kulcs: szoveg, fajta });
    else if (elso?.type === 'TemplateLiteral') jelol(elso.start, `${fajta}(\`…\`)`, dinamikus);
    if (szoveg === null && elso) bejar(elso, n, 'arguments'); // dinamikus kulcs: a benne álló szöveg magyar szövegnek számít
    for (const a of tobbi) bejar(a, n, 'arguments');
    return true;
  }

  function bejar(n: Csp, szulo: Csp, kulcs: string): void {
    if (!n || typeof n !== 'object') return;
    if (Array.isArray(n)) {
      for (const x of n) bejar(x, szulo, kulcs);
      return;
    }
    if (typeof n.type !== 'string') return;
    const tipus: string = n.type;

    if (tipus.startsWith('TS')) {
      if (TS_ERTEK.has(tipus)) bejar(n.expression, n, 'expression');
      return;
    }
    if (tipus === 'CallExpression') {
      if (fordito(n)) return;
      const c = n.callee;
      if (c?.type === 'MemberExpression' && c.object?.type === 'Identifier' && c.object.name === 'console') return; // fejlesztői napló
    }
    if (tipus === 'Literal' && typeof n.value === 'string') {
      if (EKEZETES.test(n.value) && !adatSzovegKornyezet(szulo, kulcs, n)) jelol(n.start, n.value);
      return;
    }
    if (tipus === 'TemplateLiteral') {
      const szoveg = (n.quasis as Csp[]).map((q) => q.value.cooked ?? '').join('{}');
      if (EKEZETES.test(szoveg) && !adatSzovegKornyezet(szulo, kulcs, n)) jelol(n.start, szoveg);
      for (const e of n.expressions as Csp[]) bejar(e, n, 'expressions');
      return;
    }
    if (tipus === 'TaggedTemplateExpression') {
      bejar(n.tag, n, 'tag');
      for (const e of n.quasi.expressions as Csp[]) bejar(e, n, 'expressions');
      return;
    }
    if (tipus === 'Text') {
      const szoveg: string = n.data ?? '';
      if (EKEZETES.test(szoveg) && szoveg.trim()) jelol(elsoKarakter(n, szoveg), szoveg);
      return;
    }
    if (tipus === 'Attribute') {
      attributum(n, szulo);
      return;
    }

    for (const k of Object.keys(n)) {
      if (KIHAGYOTT_KULCS.has(k)) continue;
      if (adatKulcs(tipus, k, n)) continue;
      bejar(n[k], n, k);
    }
  }

  /** Az a csomópont-mező, amelyben álló szöveg adat (kulcs, útvonal), nem felületi szöveg. */
  function adatKulcs(tipus: string, k: string, n: Csp): boolean {
    if (k === 'source' && /^(Import|Export)/.test(tipus)) return true;
    if (k === 'key' && !n.computed && (tipus === 'Property' || tipus === 'PropertyDefinition' || tipus === 'MethodDefinition')) return true;
    if (k === 'property' && tipus === 'MemberExpression' && n.computed && n.property?.type === 'Literal') return true;
    return false;
  }

  /** Összehasonlítás (`x === 'Média'`) és `case` címke: adat, nem megjelenített szöveg. */
  function adatSzovegKornyezet(szulo: Csp, kulcs: string, n: Csp): boolean {
    if (!szulo) return false;
    if (szulo.type === 'BinaryExpression' && OSSZEHASONLITO.has(szulo.operator) && (kulcs === 'left' || kulcs === 'right')) return n === szulo.left || n === szulo.right;
    if (szulo.type === 'SwitchCase' && kulcs === 'test') return true;
    return false;
  }

  function attributum(n: Csp, elem: Csp): void {
    const ertek = n.value;
    if (ertek === true || ertek == null) return;
    const komponens = elem?.type === 'Component' || elem?.type === 'SvelteComponent' || elem?.type === 'SvelteSelf';
    const reszek: Csp[] = Array.isArray(ertek) ? ertek : [ertek];
    for (const r of reszek) {
      if (r.type === 'Text') {
        if ((komponens || SZOVEG_ATTR.has(n.name)) && EKEZETES.test(r.data ?? '') && (r.data ?? '').trim()) jelol(elsoKarakter(r, r.data), r.data);
      } else bejar(r, n, 'value');
    }
  }

  if (gyoker.module) bejar(gyoker.module.content, gyoker, 'module');
  if (gyoker.instance) bejar(gyoker.instance.content, gyoker, 'instance');
  if (gyoker.fragment) bejar(gyoker.fragment, gyoker, 'fragment');
  return { magyar, kulcsok, dinamikus };
}

/** Az `app/src` minden `.ts` és `.svelte` fájlja (nyers szöveg), a `tests/`-hez viszonyított útvonallal (`../src/…`). */
export function forrasFajlok(): Record<string, string> {
  return import.meta.glob(['../src/**/*.ts', '../src/**/*.svelte'], { query: '?raw', import: 'default', eager: true }) as Record<string, string>;
}

/** `../src/lib/x.ts` → `src/lib/x.ts` (a ratchet-JSON kulcsa). */
export function rovidUt(ut: string): string {
  return ut.replace(/^\.\.\//, '');
}
