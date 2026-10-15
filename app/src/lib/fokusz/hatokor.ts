// Billentyű-hatókörök: a nyitott modális átfedések verme. Ha nem üres, a globális gyorsbillentyűk közül
// csak az `atfedesben` jelölésűek élnek; minden mást a legfelső átfedés kezel (pl. ↑↓, Enter, Esc).

const verem: { nev: string }[] = [];

export function belep(nev: string): () => void {
  const jel = { nev };
  verem.push(jel);
  return () => {
    const i = verem.indexOf(jel);
    if (i >= 0) verem.splice(i, 1);
  };
}

export function legfelso(): string | null {
  return verem.length ? verem[verem.length - 1].nev : null;
}

export function modalisNyitva(): boolean {
  return verem.length > 0;
}
