/** A gyorsváltóban beírt név előkészítése. A végleges út- és ütközésellenőrzés a core kizáró írásáé. */
export function ujJegyzetCel(lekerdezes: string): { nev: string; mappa?: string } | null {
  const szoveg = lekerdezes.normalize('NFC').trim();
  if (!szoveg || szoveg.startsWith('/') || /[\\:*?"<>|#^\[\]\u0000-\u001f\u007f]/u.test(szoveg)) return null;
  const reszek = szoveg.split('/');
  if (reszek.some(r => !r || r.startsWith('.') || r !== r.trim())) return null;
  const nev = reszek.pop()!.replace(/\.md$/i, '').trim();
  if (!nev || nev.startsWith('.')) return null;
  return { nev, ...(reszek.length ? { mappa: reszek.join('/') } : {}) };
}
