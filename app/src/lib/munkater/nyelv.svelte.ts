// A jegyzetek nyelve a workspace-beállításból jön. Független a felület angol nyelvétől;
// ismeretlen nyelvnél a macOS automatikus helyesírás-ellenőrzése dönt.
class TartalmiNyelv {
  kod = $state('');

  beallit(ertek: unknown): void {
    let kod = '';
    if (typeof ertek === 'string' && ertek.length <= 50 && ertek.trim()) {
      try {
        kod = Intl.getCanonicalLocales(ertek.trim())[0] ?? '';
      } catch {
        // Hibás vagy nem támogatott nyelvi címke nem állíthatja le a szerkesztőt.
      }
    }
    this.kod = kod;
  }
}

export const tartalmiNyelv = new TartalmiNyelv();
