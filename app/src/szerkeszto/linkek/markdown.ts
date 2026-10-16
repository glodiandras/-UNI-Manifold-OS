// A Markdown-cél szöveges felbontása. A fájlt továbbra is a core oldja fel; itt nincs útkeresés.

function kulsoSema(cel: string): boolean {
  return /^[a-z][a-z\d+.-]*:/i.test(cel) || cel.startsWith('//');
}

/** A teljes komponens-dekódolás (a `%3A` → `:` is): csak a séma/hálózati-hivatkozás elutasításához; hibánál a változatlan szöveg. */
function mereven(cel: string): string {
  try {
    return decodeURIComponent(cel);
  } catch {
    return cel;
  }
}

/** Helyi Markdown-cél: egyszer dekódolt út és horgony. Külső/tiltott séma nem kerülhet a vault API-ba. */
export function markdownCel(nyers: string): { cel: string; alcel: string | null } | null {
  let cim = nyers.trim();
  if (cim.startsWith('<') && cim.endsWith('>')) cim = cim.slice(1, -1);
  // A Markdown escape nem URL-escape: a kettőt külön, egyszer alkalmazzuk.
  cim = cim.replace(/\\([!"#$%&'()*+,\-./:;<=>?@[\]\\^_`{|}~])/g, '$1');
  if (!cim || /^[a-z][a-z\d+.-]*:/i.test(cim) || cim.startsWith('//')) return null;
  // A core `feloldas.md_reszek`-ével azonos sorrend és szabály (a gráf és az átnevezés ezt használja): az EGÉSZ cél egyszer
  // `decodeURI`-vel dekódolódik — a fenntartott jelek (`; / ? : @ & = + $ , #`) `%XX` alakban maradnak —, az NBSP szóköz,
  // és csak ezután válik el a horgony az első `#`-nél. A közös vektorok: `tests/fixtures/md-cel-vektorok.json`.
  try {
    const teljes = decodeURI(cim).replace(/\u00a0/g, ' ');
    const hash = teljes.indexOf('#');
    const cel = hash < 0 ? teljes : teljes.slice(0, hash);
    const alcel = hash < 0 ? null : teljes.slice(hash + 1).trim() || null;
    if (/[\u0000-\u001f\u007f]/.test(cel + (alcel ?? '')) || kulsoSema(cel) || kulsoSema(mereven(cel))) return null;
    return { cel, alcel };
  } catch {
    return null; // Hibás százalék-kódolás: ne találjon el egy másik fájlt.
  }
}
