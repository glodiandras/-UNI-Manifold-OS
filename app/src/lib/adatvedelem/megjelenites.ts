// A Privacy Center állandó szövegei (a ratchet nem enged dinamikus kulcsot) és a méret-formázás.
import { tk } from '../i18n';

export const HELY_CIM: Record<string, string> = {
  workspace: tk('privacy.hely.workspace'),
  snapshots: tk('privacy.hely.snapshots'),
  index: tk('privacy.hely.index'),
  personal: tk('privacy.hely.personal'),
  models: tk('privacy.hely.models'),
  backup: tk('privacy.hely.backup'),
  caches: tk('privacy.hely.caches'),
  logs: tk('privacy.hely.logs'),
};
export const HELY_LEIRAS: Record<string, string> = {
  workspace: tk('privacy.hely.workspace_leiras'),
  snapshots: tk('privacy.hely.snapshots_leiras'),
  index: tk('privacy.hely.index_leiras'),
  personal: tk('privacy.hely.personal_leiras'),
  models: tk('privacy.hely.models_leiras'),
  backup: tk('privacy.hely.backup_leiras'),
  caches: tk('privacy.hely.caches_leiras'),
  logs: tk('privacy.hely.logs_leiras'),
};
export const ENGEDETT_CIM: Record<string, string> = {
  models: tk('privacy.halozat.engedett.models'),
  runtime_tools: tk('privacy.halozat.engedett.runtime_tools'),
  video_links: tk('privacy.halozat.engedett.video_links'),
};
export const TILTOTT_CIM: Record<string, string> = {
  telemetry: tk('privacy.halozat.tiltott.telemetry'),
  background_sync: tk('privacy.halozat.tiltott.background_sync'),
  cloud_ai: tk('privacy.halozat.tiltott.cloud_ai'),
  update_ping: tk('privacy.halozat.tiltott.update_ping'),
};
export const TRACKER_TAROL: Record<string, string> = {
  active_time: tk('privacy.tracker.active_time'),
  edit_counts: tk('privacy.tracker.edit_counts'),
  command_usage: tk('privacy.tracker.command_usage'),
  latency: tk('privacy.tracker.latency'),
  note_text: tk('privacy.tracker.note_text'),
};
export const FAJTA_CIM: Record<string, string> = {
  models: tk('privacy.letoltes.models'),
  video_links: tk('privacy.letoltes.video_links'),
};
export const ENGEDELY_SZO: Record<string, string> = {
  engedelyezve: tk('privacy.engedely.engedelyezve'),
  megtagadva: tk('privacy.engedely.megtagadva'),
  nincs_dontes: tk('privacy.engedely.nincs_dontes'),
  korlatozott: tk('privacy.engedely.korlatozott'),
  csak_iras: tk('privacy.engedely.csak_iras'),
  elutasitva: tk('privacy.engedely.megtagadva'),
  ismeretlen: tk('privacy.engedely.ismeretlen'),
};

/** Bájt → olvasható méret (tizedes: 1 jegy; 1000-es váltás, mint a Finder). */
export function meretSzoveg(bajt: number | null | undefined): string {
  if (bajt === null || bajt === undefined) return '–';
  const E = ['B', 'KB', 'MB', 'GB', 'TB'];
  let v = bajt;
  let i = 0;
  while (v >= 1000 && i < E.length - 1) { v /= 1000; i++; }
  return `${i === 0 ? Math.round(v) : v.toFixed(1)} ${E[i]}`;
}
