// A vezérlő (C17) core-hívásai. A visszavonás a meglévő pillanatkép-végpont (kör szerint); a „Mentés most” a
// feladatsor `mentes` típusa.

import { kerdez } from '../core/api';
import type { Feladat, FeladatReszlet, Kapcsolok, ModellAttekintes, Rendszer, Valtozasok } from './tipusok';
import type { BejarasEredmeny } from './videoBejaras';

const q = encodeURIComponent;

/** A `GET /api/video/allapot` válasza. A `fuggo` és a `temamappak` a célmappás bevitelé (86. döntés, javasolt). */
export interface VideoAllapot {
  staging: Record<string, number>;
  varakozik: number;
  /** a várakozó staging-forrásmappák (staging-relatív út, a mappa neve mint cím) */
  fuggo?: { mappa: string; cim: string }[];
  /** a vault gyökerének téma-mappái (a „Célmappa (téma)” javaslatai) */
  temamappak?: string[];
}

export const vezerloApi = {
  feladatok: () => kerdez<{ feladatok: Feladat[] }>('/api/feladatok', { idokorlat: 10000 }),
  reszlet: (id: string, tol = 0) => kerdez<FeladatReszlet>(`/api/feladatok/${q(id)}?tol=${tol}`, { idokorlat: 10000 }),
  leallit: (id: string, azonnal: boolean) =>
    kerdez<{ allapot: string }>(`/api/feladatok/${q(id)}/leallitas`, { metodus: 'POST', torzs: { azonnal }, idokorlat: 15000 }),
  valtozasok: (id: string) => kerdez<Valtozasok>(`/api/feladatok/${q(id)}/valtozasok`, { idokorlat: 20000 }),
  visszavon: (kor: string) =>
    kerdez<{ ok: boolean; sha: string }>('/api/pillanat/vault/visszavonas', { metodus: 'POST', torzs: { kor }, idokorlat: 60000 }),
  rendszer: () => kerdez<Rendszer>('/api/vezerlo/rendszer', { idokorlat: 10000 }),
  /** A router-tábla feladatonként (C19): csak olvas, modellt nem tölt. */
  modellek: () => kerdez<ModellAttekintes>('/api/vezerlo/modellek', { idokorlat: 10000 }),
  kapcsolok: () => kerdez<{ kapcsolok: Kapcsolok }>('/api/vezerlo/kapcsolok', { idokorlat: 5000 }),
  kapcsolokIr: (r: Partial<Kapcsolok>) =>
    kerdez<{ ok: boolean; kapcsolok: Kapcsolok }>('/api/vezerlo/kapcsolok', { metodus: 'PUT', torzs: r, idokorlat: 5000 }),
  mentesInditas: () => kerdez<Feladat>('/api/feladatok', { metodus: 'POST', torzs: { tipus: 'mentes' }, idokorlat: 10000 }),
  /** Videók letöltése a stagingbe (C20a; yt-dlp: az egyetlen hálózati lépés). A core a linkeket ellenőrzi (400 magyar üzenettel). */
  videoLetoltes: (urlek: string[], bevitel = true, bejaras?: { megerosit: boolean }) =>
    kerdez<Feladat>('/api/feladatok', {
      metodus: 'POST',
      torzs: {
        tipus: 'video_letoltes',
        parameterek: {
          urlek,
          ...(bevitel ? { bevitel: true } : {}),
          ...(bejaras ? { bejaras: true, ...(bejaras.megerosit ? { megerosit: true } : {}) } : {}),
        },
      },
      idokorlat: 10000,
    }),
  /** 84. döntés (javasolt): egy oldal videóinak felderítése (`video_bejaras`; hálózat, de letöltés nincs). */
  videoBejaras: (url: string) =>
    kerdez<Feladat>('/api/feladatok', { metodus: 'POST', torzs: { tipus: 'video_bejaras', parameterek: { url } }, idokorlat: 10000 }),
  /** A bejárás eredménye (csak olvas; még nincs: `{kesz: false}`). */
  videoBejarasEredmeny: (url: string) =>
    kerdez<BejarasEredmeny>(`/api/video/bejaras?url=${q(url)}`, { idokorlat: 10000 }),
  /** C20b: a staging várakozó videóinak bevitele a vaultba (gépi írás, videónként visszavonható; `proba`: a vault klónjára). */
  videoBevitel: (proba = false, celmappa?: { temaMappa: string; mappak: string[] }) =>
    kerdez<Feladat>('/api/feladatok', {
      metodus: 'POST',
      torzs: {
        tipus: 'video_integralas',
        parameterek: {
          ...(celmappa ? { mappak: celmappa.mappak, tema_mappa: celmappa.temaMappa } : {}),
          ...(proba ? { proba: true } : {}),
        },
      },
      idokorlat: 10000,
    }),
  /** C20b: a staging forrásai `integration_status` szerint (csak olvas); 86. d.: a várakozó forrásmappák és a vault téma-mappái. */
  videoAllapot: () => kerdez<VideoAllapot>('/api/video/allapot', { idokorlat: 10000 }),
};
