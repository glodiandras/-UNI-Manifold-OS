// A Health nézet szövegei: állandó kulcsok (a ratchet-teszt nem enged dinamikus kulcsot). A core üzenetei (`uzenet`) angol tartalékkal
// érkeznek a paraméterekkel kitöltve; itt a cím, a „mit jelent / mit tesz a javítás / tudj meg többet” szövegek vannak.
import { tk } from '../i18n';

export const CIM: Record<string, string> = {
  index: tk('egeszseg.cim.index'),
  pillanatkep: tk('egeszseg.cim.pillanatkep'),
  zarak: tk('egeszseg.cim.zarak'),
  lemezhely: tk('egeszseg.cim.lemezhely'),
  modellek: tk('egeszseg.cim.modellek'),
  munkater: tk('egeszseg.cim.munkater'),
  folyamatok: tk('egeszseg.cim.folyamatok'),
  telepites: tk('egeszseg.cim.telepites'),
};

/** „Learn more”: mit ellenőriz, miért számít, mit tehet a felhasználó. */
export const TUDJ_MEG: Record<string, string> = {
  index: tk('egeszseg.tudj.index'),
  pillanatkep: tk('egeszseg.tudj.pillanatkep'),
  zarak: tk('egeszseg.tudj.zarak'),
  lemezhely: tk('egeszseg.tudj.lemezhely'),
  modellek: tk('egeszseg.tudj.modellek'),
  munkater: tk('egeszseg.tudj.munkater'),
  folyamatok: tk('egeszseg.tudj.folyamatok'),
  telepites: tk('egeszseg.tudj.telepites'),
};

export const TUDJ_ALTALANOS = tk('egeszseg.tudj.altalanos');

/** Mit tesz pontosan a „Fix automatically” (és hogyan fordítható vissza). */
export const JAVITAS_LEIRAS: Record<string, string> = {
  zar_takarit: tk('egeszseg.javitas.zar_takarit'),
  git_zar_takarit: tk('egeszseg.javitas.git_zar_takarit'),
  regiszter_takarit: tk('egeszseg.javitas.regiszter_takarit'),
  index_ujraepit: tk('egeszseg.javitas.index_ujraepit'),
  gyorsitotar_torles: tk('egeszseg.javitas.gyorsitotar_torles'),
};

/** Mit tegyen a felhasználó, ha nincs gépi javítás. */
export const JAVITAS_KEZI: Record<string, string> = {
  index: tk('egeszseg.kezi.index'),
  pillanatkep: tk('egeszseg.kezi.pillanatkep'),
  zarak: tk('egeszseg.kezi.zarak'),
  lemezhely: tk('egeszseg.kezi.lemezhely'),
  modellek: tk('egeszseg.kezi.modellek'),
  munkater: tk('egeszseg.kezi.munkater'),
  folyamatok: tk('egeszseg.kezi.folyamatok'),
  telepites: tk('egeszseg.kezi.telepites'),
};

export const ALLAPOT_SZOVEG: Record<string, string> = {
  ok: tk('egeszseg.allapot.ok'),
  info: tk('egeszseg.allapot.info'),
  figyelem: tk('egeszseg.allapot.figyelem'),
  hiba: tk('egeszseg.allapot.hiba'),
};

/** A Diagnose részletek kulcsainak címkéi; az ismeretlen kulcs csak Developer módban látszik. */
export const RESZLET_CIM: Record<string, string> = {
  fajl: tk('egeszseg.reszlet.fajl'),
  sema: tk('egeszseg.reszlet.sema'),
  fajlok: tk('egeszseg.reszlet.fajlok'),
  quick_check: tk('egeszseg.reszlet.quick_check'),
  hiba: tk('egeszseg.reszlet.hiba'),
  felretett: tk('egeszseg.reszlet.felretett'),
  tarak: tk('egeszseg.reszlet.tarak'),
  zar: tk('egeszseg.reszlet.zar'),
  mentes_regi: tk('egeszseg.reszlet.mentes_regi'),
  workspace_szabad_gb: tk('egeszseg.reszlet.workspace_szabad_gb'),
  app_data_szabad_gb: tk('egeszseg.reszlet.app_data_szabad_gb'),
  kepek_gyorsitotara_mb: tk('egeszseg.reszlet.kepek_gyorsitotara_mb'),
  telepitve: tk('egeszseg.reszlet.telepitve'),
  hianyos: tk('egeszseg.reszlet.hianyos'),
  kod: tk('egeszseg.reszlet.kod'),
  kotet_lecsatolva: tk('egeszseg.reszlet.kotet_lecsatolva'),
  bejegyzes: tk('egeszseg.reszlet.bejegyzes'),
  core_port: tk('egeszseg.reszlet.core_port'),
  beallitott_port: tk('egeszseg.reszlet.beallitott_port'),
  worker: tk('egeszseg.reszlet.worker'),
  verzio: tk('egeszseg.reszlet.verzio'),
  commit: tk('egeszseg.reszlet.commit'),
  epitve: tk('egeszseg.reszlet.epitve'),
  modositott: tk('egeszseg.reszlet.modositott'),
  hianyzik: tk('egeszseg.reszlet.hianyzik'),
  tobblet: tk('egeszseg.reszlet.tobblet'),
};
