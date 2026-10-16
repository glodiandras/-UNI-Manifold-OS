// A Markdown-cél szöveges felbontása. A fájlt továbbra is a core oldja fel; itt nincs útkeresés.

/** Helyi Markdown-cél: egyszer dekódolt út és horgony. Külső/tiltott séma nem kerülhet a vault API-ba. */
export function markdownCel(nyers: string): { cel: string; alcel: string | null } | null {
  let cim = nyers.trim();
  if (cim.startsWith('<') && cim.endsWith('>')) cim = cim.slice(1, -1);
  // A Markdown escape nem URL-escape: a kettőt külön, egyszer alkalmazzuk.
  cim = cim.replace(/\\([!"#$%&'()*+,\-./:;<=>?@[\]\\^_`{|}~])/g, '$1');
  if (!cim || /^[a-z][a-z\d+.-]*:/i.test(cim) || cim.startsWith('//')) return null;
  const hash = cim.indexOf('#');
  try {
    const cel = decodeURIComponent(hash < 0 ? cim : cim.slice(0, hash));
    const alcel = hash < 0 ? null : decodeURIComponent(cim.slice(hash + 1)).trim() || null;
    if (/[\u0000-\u001f\u007f]/.test(cel + (alcel ?? '')) || /^[a-z][a-z\d+.-]*:/i.test(cel) || cel.startsWith('//')) return null;
    return { cel, alcel };
  } catch {
    return null; // Hibás százalék-kódolás: ne találjon el egy másik fájlt.
  }
}
