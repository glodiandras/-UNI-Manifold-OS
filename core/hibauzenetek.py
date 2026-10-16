"""English fallbacks for the core error contract (F4).

These messages are shipped with the core so API clients do not depend on the UI
bundle. Identifiers and parameter names remain stable across translations.
"""

ANGOL = {'asszisztens.api.limit_tartomany': 'The limit must be a whole number from 1 to 500.',
 'asszisztens.api.objektum_kell': 'A JSON object is required.',
 'asszisztens.api.szoveg_kotelezo': 'The text is required.',
 'asszisztens.emlites.szoveg_kotelezo': 'The text is required.',
 'asszisztens.hangolo.dontes_ertek': 'The decision must be elfogad, elutasit or figyelmen_kivul.',
 'asszisztens.hangolo.helyzet_azonosito': 'The situation must be a short lowercase ID (a–z, 0–9, _).',
 'asszisztens.hangolo.ismeretlen_fajta': 'Unknown suggestion type: {tipus}',
 'asszisztens.homlokzat.fajta_ertek': 'The type must be minta, muvelet, elutasitott, hangolas or mind.',
 'asszisztens.homlokzat.kulcs_kell': 'The `kulcs` field is the ID of the item to delete.',
 'asszisztens.homlokzat.nincs_tetel': 'There is no such learned item.',
 'asszisztens.kiegeszites.azonosito': 'Invalid suggestion ID.',
 'asszisztens.kiegeszites.elotte_kell': 'The `elotte` field is the preceding text of the pattern to delete.',
 'asszisztens.kiegeszites.elozmeny_hossz': 'Enter a preceding text of 8 to 100 characters and a continuation of at '
                                           'most 800 characters.',
 'asszisztens.kiegeszites.kijeloles_hossz': 'The selection can have at most 4000 characters, and `kezi` must be true '
                                            'or false.',
 'asszisztens.kiegeszites.mod_ertek': 'The mode must be folytat, kifejt or osszefoglal.',
 'asszisztens.kiegeszites.szovegkornyezet': 'The context of the suggestion is too long or missing.',
 'asszisztens.mintatar.alkalom_ertek': 'The `alkalom` field must be megnyitas or szunet.',
 'asszisztens.mintatar.ertek_hossz': 'The `ertek` field must be a single line of at most 300 characters.',
 'asszisztens.mintatar.javaslat_azonosito': 'Invalid suggestion ID.',
 'asszisztens.mintatar.muvelet_ertek': 'The action must be cimke, sablon or link.',
 'asszisztens.mintatar.szoveg_kell': 'The `szoveg` field is required (at most 200,000 characters).',
 'asszisztens.mintatar.ut_kell': 'The `ut` field is the workspace-relative path of a note.',
 'asszisztens.statisztika.adatbazis_nem_irhato': 'The statistics database cannot be written.',
 'asszisztens.statisztika.fajta_dontes': 'The type must be emlites, szokas or higienia, and the decision elfogad or '
                                         'elutasit.',
 'asszisztens.szokas.dontes_ertek': 'The decision must be elfogad or elutasit.',
 'asszisztens.szokas.mar_dontottek': 'This suggestion has already been decided.',
 'asszisztens.szokas.nincs_ilyen_javaslat': 'There is no such suggestion.',
 'asszisztens.szolgalat.kikapcsolva': 'The assistant is turned off.',
 'asszisztens.szolgalat.nincs_riport': 'There is no report yet.',
 'asszisztens.szolgalat.riport_nincs_kesz': 'The health report is not ready yet.',
 'atirat.hianyzik_ut': 'The `ut` parameter is missing.',
 'atirat.nincs_ilyen_fajl_rel': 'No such file: {rel}',
 'atirat.video_hangfajl_rel': 'Not a video or audio file: {rel}',
 'atnevezes.blokkolt': 'The rename cannot proceed. Resolve the issues shown in the preview.',
 'atnevezes.foglalt': 'Another write is in progress. Wait for it to finish and try renaming again.',
 'atnevezes.mentetlen': 'Save or close the unsaved documents before renaming.',
 'atnevezes.naplo_all': 'An interrupted rename needs recovery before another rename can start.',
 'atnevezes.nincs_ilyen_fajl_indexben_regi': 'No such file in the index: {regi}',
 'atnevezes.nincs_pillanatkep': 'Renaming requires an available snapshot store.',
 'atnevezes.sikertelen': 'The rename could not be completed.',
 'atnevezes.valtozott': 'The vault changed after the rename preview. Review the plan and try again.',
 'atnevezes.visszaallitva': 'The rename did not pass its checks and was rolled back. Review the plan and try again.',
 'bazis.api.azon_legfeljebb_200_karakteres_szoveg': 'The `azon` field must be text of at most 200 characters.',
 'bazis.api.hianyzik_base_szovege_szoveg': 'The text of the `.base` file (`szoveg`) is missing.',
 'bazis.api.hianyzik_muvelet_muvelet': 'The action (`muvelet`) is missing.',
 'bazis.api.kerdes_sorszam_egesz': 'The `kerdes` field must be a whole number.',
 'bazis.api.max_sor_1_max_sor': 'The `max_sor` field must be a whole number from 1 to {MAX_SOR}.',
 'bazis.api.nezet_sorszam_nev': 'The view must be given by number or name.',
 'bazis.modell.base_gyoker': 'The root of the `.base` file must be key–value pairs.',
 'bazis.modell.hianyzik_szoveg': 'The text is missing.',
 'bazis.modell.ismeretlen_nezettipus': 'Unknown view type: {eredeti}. It is shown as a table.',
 'bazis.modell.kiirt_elter': 'The written text differs when read back.',
 'bazis.modell.kiirt_nem_olvashato': 'The written text cannot be read back: {e}',
 'bazis.modell.kulcs_ertek_parok': '`{kulcs}` must be key–value pairs.',
 'bazis.modell.kulcs_erteke_lista': 'The value of `{kulcs}` must be a list.',
 'bazis.modell.muvelet_objektum': 'The action must be an object.',
 'bazis.modell.nezet_ertek_parok': 'A view must be key–value pairs.',
 'bazis.modell.osszesito_szoveg': 'A summary must be expression text.',
 'bazis.modell.szuro_objektum_kulcs': 'A filter object must contain exactly one `and`, `or` or `not` key.',
 'bazis.modell.szuro_szerkezet': 'A filter must be text or an and/or/not structure.',
 'bazis.modell.views_lista': '`views` must be a list.',
 'config_hianyzik': 'The configuration was not found: {ut}',
 'config_toml_hibas': 'Invalid TOML file {ut}: {hiba}',
 'core.leall': 'Manifold is shutting down.',
 'cpp_ai.core_leall': 'Manifold is shutting down.',
 'cpp_ai.ez_tipp_keres': 'This is not a hint request.',
 'cpp_ai.hianyzik_ai': 'The `ai` parameter is missing.',
 'cpp_ai.jegyzet_md_fajl_legyen': 'The `jegyzet` field must be a .md file.',
 'cpp_ai.mod_ezek_egyike_join': 'The `mod` field must be one of: {join}',
 'cpp_ai.nincs_ilyen_ai_keres_aid': 'No such AI request: {aid}',
 'cpp_ai.szint_1_2_3': 'The `szint` field must be 1, 2 or 3.',
 'cpp_utvonal.core_leall': 'Manifold is shutting down.',
 'cpp_utvonal.ervenytelen_nev_tilos_benne_kezdodhet': 'Invalid name. It cannot contain \\ / : * ? " < > | # ^ [ ] and '
                                                      'cannot start with a dot.',
 'cpp_utvonal.fajl_join_kiterjesztesu_legyen_rp': 'The file must have a {join} extension: {rp}',
 'cpp_utvonal.formazas_sikertelen': 'Formatting failed: {exc}',
 'cpp_utvonal.hianyzik_futas': 'The `futas` parameter is missing.',
 'cpp_utvonal.hianyzik_szoveg': 'The `szoveg` field is missing.',
 'cpp_utvonal.hianyzik_ut_ut': 'The path (`ut`) is missing.',
 'cpp_utvonal.mod_gyors_hibakereso_lehet': 'The `mod` field must be gyors or hibakereso.',
 'cpp_utvonal.motor_nem_indul': 'The C++ engine could not start: {exc}',
 'cpp_utvonal.motor_nem_valaszol': 'The C++ engine is not responding: {exc}',
 'cpp_utvonal.nincs_clang_format': 'clang-format is not installed (run bin/mos cpp telepit --igen).',
 'cpp_utvonal.nincs_ilyen_futas_fid': 'No such run: {fid}',
 'cpp_utvonal.nincs_ilyen_mappa_mappa': 'No such folder: {mappa}',
 'cpp_utvonal.tul_nagy_szoveg_formazashoz': 'The text is too large to format.',
 'csatolmany.celmappa_megvaltozott': 'The target folder changed during the upload. Try again.',
 'csatolmany.csak_fajl_masolhato': 'Only files can be copied.',
 'csatolmany.csak_vaulton_belul_kukaba': 'Only files and folders inside the workspace can be moved to the Trash.',
 'csatolmany.csatolmany_mappa_attachmentfolderpath_ervenytelen_cel': 'The attachment folder (attachmentFolderPath) is '
                                                                     'invalid: {cel}',
 'csatolmany.darabok_sorrendje_elter': 'The upload chunks arrived out of order.',
 'csatolmany.elso_darab_hianyzik': 'The first chunk of the upload is missing.',
 'csatolmany.ervenytelen_darabpozicio': 'Invalid chunk position.',
 'csatolmany.ervenytelen_fajlnev': 'Invalid file name.',
 'csatolmany.ervenytelen_feltoltesazonosito': 'Invalid upload ID.',
 'csatolmany.fajl_mentese_tart': 'A file is still being saved. Try again.',
 'csatolmany.fajl_tul_nagy': 'The file is larger than 20 GiB.',
 'csatolmany.finder_csak_macos': 'Reveal in Finder is only available on macOS.',
 'csatolmany.finder_nem_nyilik': 'Finder could not be opened.',
 'csatolmany.hibas_csatolmany_mappa': 'The attachment folder in the workspace settings is invalid.',
 'csatolmany.hibas_feltoltesi_adat': 'The upload data is invalid.',
 'csatolmany.kuka_megerosites': 'Moving to the Trash needs to be confirmed.',
 'csatolmany.masik_vault_muvelet_fut': 'Another workspace operation (an automated write or a backup) is running. Try '
                                       'again in a moment.',
 'csatolmany.mentetlen_dokumentum': 'The file or folder contains a document with unsaved changes.',
 'csatolmany.nev_foglalt': 'A file or folder with this name already exists.',
 'csatolmany.nincs_szabad_fajlnev': 'No free file name is available.',
 'csatolmany.nincs_fajl': 'There is no such file or folder.',
 'csatolmany.tul_nagy_feltoltesi_darab': 'The upload chunk is too large.',
 'elozmeny.commit_nem_erinti': 'This snapshot does not affect the note: {sha}',
 'elozmeny.hianyzo_sha': 'The snapshot ID is missing.',
 'elozmeny.iro_feladat_fut': 'A task that writes to the workspace is running. You can restore after it finishes.',
 'elozmeny.jegyzet_athelyezve': 'The note was renamed or deleted in the meantime: {ut}. Open it under its new name.',
 'elozmeny.jegyzet_athelyezve_rovid': 'The note was renamed or deleted in the meantime: {ut}',
 'elozmeny.jegyzet_torolve_a_commitban': 'The note was deleted in this snapshot, so there is nothing to restore.',
 'elozmeny.mar_jelenlegi': 'This is already the current version: {ut}',
 'elozmeny.nincs_pillanatkep_tarolo': 'The workspace snapshot store is not available, so history cannot be shown.',
 'elozmeny.valtozat_nem_olvashato': 'The content of this version cannot be read: {sha}:{ut}',
 'elozmeny.valtozat_tul_nagy': 'This version is too large to restore.',
 'elrendezes_ismeretlen': 'Unknown layout in MOS_ELRENDEZES: {ertek} (hordozhato or termek).',
 'feladat.automatikus_tiltott': 'This automatic task was cancelled. Start content generation manually.',
 'feladat.core_leall': 'Manifold is shutting down. Open the app again and restart the task.',
 'feladat.futtatas_hibas': 'The task could not be completed ({tipus}). Open its log for details.',
 'feladat.idotullepes': 'The task exceeded its maximum run time ({mp} s) and was stopped.',
 'feladat.ismeretlen_tipus': 'Unknown task type: {tipus}',
 'feladat.lepes_hibas': 'Step {lepes} failed with exit code {kilepes}.',
 'feladat.nem_fut': 'The task is no longer running.',
 'feladat.nincs': 'There is no such task.',
 'feladat.prioritas': 'The priority must be a whole number.',
 'feladat.teljes_mentes_belso_cel': 'The backup destination must be outside the data being backed up.',
 'feladat.teljes_mentes_cel': 'Choose a destination folder on a connected external volume.',
 'felkeszultseg.api.azon_kell': 'The `azon` field (the exam calendar ID) is required.',
 'felkeszultseg.api.datum_alak': 'The `datum` field must be a YYYY-MM-DD string.',
 'felkeszultseg.api.modell_nem_erheto_el': 'The text assessment model is not available: {e}',
 'felkeszultseg.api.modell_nev': 'The `modell` field must be the name of a registered model.',
 'felkeszultseg.api.modell_nincs_kotve': 'The text assessment model is not set up (the router table has no calibrated '
                                         '`szoveg` model).',
 'felkeszultseg.api.nem_szoveg_modell': '{nev} is not a `szoveg` model (see the `feladat` list in the registry).',
 'felkeszultseg.api.worker_nem_erheto_el': 'The model worker is not available.',
 'felkeszultseg.forras_hianyzik': 'The assessment source is not available. Sync the calendar and try again.',
 'felkeszultseg.keret.tartomany': 'The daily budget must be a whole number of minutes from 15 to 480.',
 'felkeszultseg.modell_hibas': 'The selected model is not registered or its settings are invalid.',
 'felkeszultseg.osszesit.nincs_dolgozat': 'There is no such exam in the calendar (or it is outside the window).',
 'felulet.allapot_json_objektum_kell_legyen': 'The state must be a JSON object.',
 'felulet.tul_nagy_allapot_len_bajt': 'The state is too large ({len} bytes, at most {MAX_MERET}).',
 'foglalt': 'An AI request is already running.',
 'fuzet_api.adat_nem_base64': 'The `adat` field is not valid base64.',
 'fuzet_api.csak_kepformatum': 'Only .jpg, .jpeg, .png or .heic notebook photos can be uploaded (file name up to 200 '
                               'bytes).',
 'fuzet_api.ervenytelen_csoport_azonosito': 'Invalid group ID.',
 'fuzet_api.foto_base64_mezo': 'The photo must be sent as base64 in the `adat` field, up to 11 MiB.',
 'fuzet_api.keplet_modell_nem_valaszolt': 'The formula reader model did not respond: {e}',
 'fuzet_api.nincs_keplet': 'The model did not return a formula.',
 'fuzet_api.nincs_szabad_nev': 'No free name is available in the inbox folder.',
 'fuzet_api.torzs_ures_objektum': 'The request body must be an empty object: Manifold reads the image from the '
                                  'clipboard itself.',
 'fuzet_api.ures_tul_nagy_foto': 'The photo is empty or too large.',
 'fuzet_api.vagolap_kepe_tul_nagy': 'The clipboard image is too large.',
 'fuzet_api.vagolap_nem_olvashato': 'The clipboard cannot be read: {e}',
 'fuzet_api.vagolapon_nincs_kep': 'There is no image on the clipboard. Take a screenshot of the formula (⌃⇧⌘4), then '
                                  'try again.',
 'fuzet_feladat.cel_vault_jegyzete_md_vault': 'The `cel` field must be a workspace note (`.md`, workspace-relative '
                                              'path).',
 'fuzet_feladat.csoport_feltoltott_fotok_csoport_azonositoja': 'The `csoport` field is the group ID of the uploaded '
                                                               'photos.',
 'fuzet_feladat.max_1_max_foto_egesz': 'The `max` field must be a whole number from 1 to {MAX_FOTO}.',
 'fuzet_feladat.nincs_ilyen_jegyzet_cel': 'No such note: {cel}',
 'fuzet_feladat.parameterek_json_objektum_kellenek': 'The parameters must be a JSON object.',
 'fuzet_feladat.proba_igaz_hamis_lehet': 'The `proba` field must be true or false.',
 'gepi_iras.behoz_celja_tetel_jegyzetenek_csatolmany': 'The target of `behoz` must be the attachment folder '
                                                       "(attachmentFolderPath) of the item's note, not: {ut}",
 'gepi_iras.behoz_csak_apkg_import_forrasaval': '`behoz` can only be requested with the .apkg import source ({join}), '
                                                'not with: {forras}',
 'gepi_iras.behoz_csak_feherlistas_mediat_viszi': '`behoz` only brings allowlisted media into the workspace ({join}): '
                                                  '{m}',
 'gepi_iras.behoz_fajljat_tetel_jegyzete_nev': 'A note in the item must embed the `behoz` file as `![[{nev}]]` '
                                               '(unlinked media does not go into the workspace).',
 'gepi_iras.behoz_forrasa_abszolut_ut_legyen': 'The source of `behoz` must be an absolute path.',
 'gepi_iras.behoz_keri_forras_sha256_jat': '`behoz` requires the sha256 of the source (64 hex digits).',
 'gepi_iras.behoz_muveletet_csak_core_apkg': "The `behoz` action can only be requested by Manifold's own .apkg import, not "
                                             'through the automated write endpoint.',
 'gepi_iras.canvas_ervenyes_json_canvas_rp': 'The canvas is not valid JSON Canvas ({rp}): {hiba}',
 'gepi_iras.csatolmany_mappa_hasznalhato_e': 'The attachment folder cannot be used: {e}',
 'gepi_iras.dokumentum_nyitva': 'The document is open with unsaved changes, so the machine does not write into it: '
                                '{utak}',
 'gepi_iras.ervenytelen_celmappa_cel_mappa': 'Invalid target folder: {cel_mappa}',
 'gepi_iras.ervenytelen_celmappa_join': 'Invalid target folder: {join}',
 'gepi_iras.ervenytelen_celmappa_relpath': 'Invalid target folder: {relpath}',
 'gepi_iras.ervenytelen_fajlnev_reszek': 'Invalid file name: {reszek}',
 'gepi_iras.ervenytelen_fajlnev_reszek_tilos_benne': 'Invalid file name: {reszek}. It cannot contain \\ / : * ? " < > '
                                                     '| # ^ [ ]',
 'gepi_iras.ervenytelen_feladat_azonosito_feladat': 'Invalid task ID: {feladat}',
 'gepi_iras.ervenytelen_forras_mos_forras_forras': 'Invalid source (Mos-Forras): {forras} (format: mos-<chain>, '
                                                   'lowercase letters, digits and hyphens, at most 40 characters)',
 'gepi_iras.ervenytelen_kor_azonosito_kor_alak': 'Invalid round ID: {kor} (format: PREFIX-YYYYMMDD-HHMMSS)',
 'gepi_iras.ervenytelen_mappa_uj_fajl_utjaban': 'Invalid folder in the path of the new file: {join}',
 'gepi_iras.esemeny_alakja_tipus_ut_adat': 'The `esemeny` field must have the shape tipus, ut, adat, using the keys '
                                           'the source allows.',
 'gepi_iras.fajl_ervenyes_utf_8_gep': 'The file is not valid UTF-8, so the machine does not write into it: {rp}',
 'gepi_iras.fajl_gep_olvasasa_ota_megvaltozott': 'The file changed since the machine read it: {rp}',
 'gepi_iras.fajl_iras_kozben_megvaltozott_ut': 'The file changed while writing: {ut}',
 'gepi_iras.fajl_kozben_letrejott_ut': 'The file was created in the meantime: {ut}',
 'gepi_iras.fajlban_vegyes_sorvegek_allnak_gepi': 'The file has mixed line endings, so an automated insertion cannot '
                                                  'be written byte-exactly.',
 'gepi_iras.forras_forras_tetelehez_ilyen_tracker': 'This tracker event cannot be sent for an item from the `{forras}` '
                                                    'source.',
 'gepi_iras.gep_csak_pillanatkepben_kovetett_szoveges': 'The machine can only write text files tracked in the '
                                                        'snapshot: {m}',
 'gepi_iras.h1_szabaly': 'The insertion would break the workspace H1 rule ({ut}): {problemak}',
 'gepi_iras.hianyzik_alapvaltozat_alap_vakon_irunk': 'The base version (alap) is missing: we do not overwrite blindly.',
 'gepi_iras.hianyzik_muvelet_kulcs_mezoje_m': 'The action is missing its `{kulcs}` field ({m}).',
 'gepi_iras.hova_vege_eleje_lehet': 'The `hova` field must be vege or eleje.',
 'gepi_iras.import_mappa': 'Files can only be imported from the importer temporary extraction folder.',
 'gepi_iras.kicsomagolt_fajl_ellenorzes_ota_megvaltozott': 'The extracted file changed since it was checked: {name}',
 'gepi_iras.kulcs_egysoros_legfeljebb_max_hossz': 'The `{kulcs}` field must be a single line of at most {max_hossz} '
                                                  'characters.',
 'gepi_iras.mar_van_ilyen_nevu_fajl': 'A file with this name already exists: {rp}',
 'gepi_iras.mar_van_ilyen_nevu_fajl_2': 'A file with this name already exists (we do not overwrite; a new name is '
                                        'needed): {rp}',
 'gepi_iras.media_celmappa': 'This media file must be placed in its configured destination folder ({cel_mappa}).',
 'gepi_iras.media_nincs': 'The source media file was not found: {src}',
 'gepi_iras.media_valtozott': 'The source media file changed after it was read: {nev}',
 'gepi_iras.megszakadt_naplo': 'The journal of an interrupted automated write is present ({d}); no new automated write '
                               'can start until it is handled.',
 'gepi_iras.megszakadt_naplo_hibas': 'The journal of an interrupted automated write is present ({d}) and could not be '
                                     'processed: {e}. No new automated write can start until it is handled.',
 'gepi_iras.modell_alakja_feladat_modell_proba': 'The `modell` field must have the shape feladat, modell (optionally '
                                                 'proba), or be null.',
 'gepi_iras.modell_kulcs_kotelezo_ai_funkcio': 'The `modell` field is required: for AI output use feladat and modell, '
                                               'for deterministic writes explicitly null.',
 'gepi_iras.modell_nincs_kalibralva': 'The {modell} model is not calibrated for the “{feladat}” task: its output can '
                                      'only be written in trial mode (`proba: true`, on the clone).',
 'gepi_iras.modell_probakent_futott': 'The {modell} model ran as a trial (on explicit request, not chosen by the '
                                      'router): its output can only be written in trial mode (`proba: true`, on the '
                                      'clone).',
 'gepi_iras.modell_router_feladat_join_modell': '“{modell}” is not a router task ({join}): `modell.feladat` must be an '
                                                'item of `[router] feladatok`.',
 'gepi_iras.mozgat_csak_figyelt_mappak_vaulton': '`mozgat` only moves a new photo from the watched folders (outside '
                                                 'the workspace) into the workspace: {src}',
 'gepi_iras.mozgat_csak_fuzetfotot_kep_videolanc': '`mozgat` only moves a notebook photo (image) or a video from the '
                                                   'video chain into the workspace: {m}',
 'gepi_iras.mozgat_csak_szoveges_irassal_beagyazassal': '`mozgat` can only be requested together with a text write '
                                                        '(the embedding).',
 'gepi_iras.mozgat_forrasa_abszolut_ut_legyen': 'The source of `mozgat` must be an absolute path.',
 'gepi_iras.mozgat_keri_forras_sha256_jat': '`mozgat` requires the sha256 of the source (64 hex digits).',
 'gepi_iras.mozgat_videot_csak_videolanc_stagingje': '`mozgat` only moves a video into the workspace from the video '
                                                     'chain staging area (outside the workspace): {src}',
 'gepi_iras.muvelet_tipus_uj_csere_beszuras': 'The action `tipus` must be uj, csere, beszuras, mozgat or behoz.',
 'gepi_iras.muveletek_1_max_muvelet_elemu': 'The `muveletek` field must be a list of 1 to {MAX_MUVELET} items (plus at '
                                            'most {MAX_BEHOZ} `behoz` actions).',
 'gepi_iras.muveletek_legfeljebb_max_muvelet_szoveges': 'The `muveletek` field can contain at most {MAX_MUVELET} text '
                                                        'or move actions and {MAX_BEHOZ} `behoz` actions.',
 'gepi_iras.nincs_cel_nevu_szakasz': 'There is no section named “{cel}”.',
 'gepi_iras.nincs_ilyen_fajl_rp': 'No such file: {rp}',
 'gepi_iras.nincs_ilyen_kicsomagolt_fajl_src': 'No such extracted file: {src}',
 'gepi_iras.nincs_pillanatkep_tarolo': 'There is no live snapshot store: without a snapshot, nothing is written '
                                       'automatically to the workspace.',
 'gepi_iras.nincs_pillanatkep_tarolo_proba': 'There is no live snapshot store: a trial clone cannot be made either.',
 'gepi_iras.pillanatkep_tarolo_hiba': 'The snapshot store (git) reported an error and the automated write did not '
                                      'happen: {exc}',
 'gepi_iras.proba_igaz_hamis_lehet': 'The `proba` field must be true or false.',
 'gepi_iras.proba_kor_elesben_irhat_kor': 'A `-proba` round cannot write live: {kor}',
 'gepi_iras.probaklon_hiba': 'The trial clone could not be created: {e}',
 'gepi_iras.sema_csere': 'The replacement breaks the workspace schema ({ut}): {problemak}',
 'gepi_iras.sema_nelkuli_ugynok_hordozo_fajlba': 'The machine does not write into files without a schema (agent '
                                                 'carrier files): {rp}',
 'gepi_iras.sema_uj_jegyzet': 'The new note breaks the workspace schema ({ut}): {problemak}',
 'gepi_iras.semaosztaly_elter': 'The schema class of the new note by its path is “{varhato}”, but the request says '
                                '“{kert}”: new automated note types can only be written with a registered schema '
                                'class.',
 'gepi_iras.status_felhasznaloe': 'Only you can fill the Status property, not the machine.',
 'gepi_iras.status_felhasznaloe_csere': 'Only you can fill and change the Status property, not the machine.',
 'gepi_iras.szakasz_ala_beszurni_csak_jegyzetbe': 'Inserting under a heading is only possible in a note (.md).',
 'gepi_iras.szakasz_fejezet_szovege_legyen': 'The `szakasz` field must be the text of a heading.',
 'gepi_iras.szandeknaplo_all': 'An intent journal is present ({d}); no new automated write can start until it is '
                               'handled.',
 'gepi_iras.tetel_mas_tartalommal': 'Item {kor} · {tetel} has already run, but with different content: another write '
                                    'cannot be repeated with the same round and item ID (a new item ID is needed).',
 'gepi_iras.tobbertelmu_szakasz': 'There are several sections named “{cel}”, so the insertion point is ambiguous.',
 'gepi_iras.tul_nagy_fajl_rp': 'The file is too large: {rp}',
 'gepi_iras.ures_beszurando_szoveg': 'The text to insert is empty.',
 'gepi_iras.ut_tetelben_egyszer_szerepelhet_m': 'A path can appear only once in an item: {m}',
 'grafikon_api.ablak_hatarok': 'The lower bound of the window must be less than the upper bound.',
 'grafikon_api.ablak_ket_szam': 'The `ablak` field must be two finite numbers: [lower, upper].',
 'grafikon_api.ablak_tul_nagy': 'The window is too large.',
 'grafikon_api.cas_homokozo': 'The CAS sandbox is not available: {uzenet}',
 'grafikon_api.elemzes_idokorlat': 'The analysis hit its time limit ({idokorlat} s).',
 'grafikon_api.elemzo_elutasitotta': 'The analyzer rejected the request: {uzenet}',
 'grafikon_api.elemzo_ertelmezhetetlen': 'The analyzer returned a response that could not be read.',
 'grafikon_api.elemzo_foglalt': 'The analyzer is busy (the sandbox is serving another request). Try again.',
 'grafikon_api.elemzo_hibas_kilepes': 'The analyzer exited with an error ({kod}): {hiba}',
 'grafikon_api.elemzo_nem_indult': 'The analyzer did not start: {exc}',
 'grafikon_api.elemzo_tetelszam': 'The analyzer returned an invalid response (the item count does not match).',
 'grafikon_api.fuggvenyek_lista': 'The `fuggvenyek` field must be a list of 1 to {MAX_FUGGVENY} strings.',
 'grafikon_api.kifejezes_jelek': 'An expression can have at most {max} characters, and only numbers, letters, '
                                 '`+-*/^().,!_` and spaces.',
 'grafikon_api.kulcs_hexa': 'The `kulcs` field must be a 16-digit hexadecimal string.',
 'grafikon_api.nincs_kulcs_tiltolistan': 'There is no such key on the blocklist.',
 'grafikon_api.tiltolista_nem_olvashato': 'The blocklist cannot be read: {e}',
 'grafikon_api.torzs_objektum': 'The request body must be a JSON object.',
 'grafikon_feladat.kulcs_igaz_hamis_lehet': 'The `{kulcs}` field must be true or false.',
 'grafikon_feladat.max_1_max_jegyzet_egesz': 'The `max` field must be a whole number from 1 to {MAX_JEGYZET}.',
 'grafikon_feladat.modell_ag_kezzel_csak_proba': '`modell_ag` can only be requested manually together with `proba` '
                                                 '(the live model branch is controlled by a setting).',
 'grafikon_feladat.parameterek_json_objektum_kellenek': 'The parameters must be a JSON object.',
 'grafikon_feladat.utak_1_max_ut_tartalmi': 'The `utak` field must be a list of 1 to {MAX_UT} relative paths of '
                                            'content notes.',
 'helyorzo_ismeretlen': 'Unknown placeholder: {kulcs}',
 'helyorzo_korkoros': 'A placeholder refers back to itself.',
 'helyorzo_melyseg': 'The placeholder chain is too deep.',
 'hibrid.hasonlo.celok_utak_listaja': 'The `celok` field must be a list of paths.',
 'hibrid.hasonlo.hianyzik_ut': 'The `ut` parameter is missing.',
 'hibrid.hasonlo.legfeljebb_max_cel_cel_kerdezheto': 'At most {MAX_CEL} targets can be queried at once.',
 'hibrid.hasonlo.nincs_ilyen_fajl_ut': 'No such file: {ut}',
 'hibrid.kerdezz.ures_kerdes': 'The question is empty.',
 'hibrid.kereso.ismeretlen_keresesi_mod_mod_join': 'Unknown search mode: {mod} ({join})',
 'hibrid.kereso.ures_kerdes': 'The question is empty.',
 'hibrid.kereso.ures_kereses': 'The search is empty.',
 'higienia.nincs_ilyen_jegyzet_indexben_ut': 'No such note in the index: {ut}',
 'hordozhato_bundleben': 'The portable layout can only be started in Developer mode inside an app bundle.',
 'http.belso_hiba': 'The operation could not be completed because of an internal error.',
 'http.content_length': 'The Content-Length header is not valid.',
 'http.egesz_szam': 'Invalid {kulcs}: a whole number is required.',
 'http.json_hibas': 'The request is not valid JSON.',
 'http.json_objektum': 'The request must be a JSON object.',
 'http.keres_hibas': 'The request is invalid.',
 'http.lepes_tiltott': 'A task step cannot call this endpoint. It writes to the workspace through the automated write '
                       'service.',
 'http.nem_elerheto': 'The service is not available. Try again.',
 'http.nem_talalhato': 'The requested item was not found.',
 'http.nincs_ilyen': 'Not found.',
 'http.nincs_vegpont': 'There is no such endpoint.',
 'http.tartomany': 'Invalid {kulcs}: it must be between {also} and {felso}.',
 'http.tul_nagy': 'The request is too large.',
 'http.utkozes': 'The operation conflicts with the current state. Refresh and try again.',
 'http.x_manifold': 'The X-Manifold header is missing or not valid.',
 'index.api.nincs_vegpont': 'There is no such endpoint.',
 'index.kereses.folosleges_zaro_zarojel': 'There is an extra closing parenthesis.',
 'index.kereses.hianyzo_zaro_zarojel': 'A closing parenthesis is missing.',
 'index.kereses.hibas_regex_e': 'Invalid regex: {e}',
 'index.kereses.ismeretlen_keresesi_elem_f': 'Unknown search element: {f}',
 'index.kereses.operator_utan_ertek_kell': 'A value is needed after the operator.',
 'index.kereses.regex_tul_sokaig_futott_idokorlat': 'The regex ran for too long (it did not finish within {idokorlat} '
                                                    's). Simplify the pattern, for example nested repetition such as '
                                                    '“(a|aa)+”.',
 'index.kereses.ures_kereses': 'The search is empty.',
 'index.kereses.ures_keresesi_kifejezes': 'The search expression is empty.',
 'index.kereses.varatlan_elem_keresesben_v': 'Unexpected element in the search: {v}',
 'index.nem_kesz': 'The index is still being built. Try again shortly.',
 'index.olvaso.alcel_szoveg': 'The heading target (`alcel`) must be text.',
 'index.olvaso.celok_legfeljebb_500_szoveg_listaja': 'The `celok` field must be a list of at most 500 strings.',
 'index.olvaso.ervenytelen_ut_rp': 'Invalid path: {rp}',
 'index.olvaso.hianyzo_cel': 'The target is missing.',
 'index.olvaso.hianyzo_kulcs': 'The key is missing.',
 'index.olvaso.hianyzo_ut': 'The path is missing.',
 'index.olvaso.nincs_ilyen_fajl_indexben_rp': 'No such file in the index: {rp}',
 'index.olvaso.nincs_ilyen_fajl_indexben_ut': 'No such file in the index: {ut}',
 'iras_a_kodba': 'The {kulcs} path points into the read-only code tree: {ut}',
 'ismeretlen_ut': 'There is no such path in the configuration: {kulcs}',
 'kartya_api.azon_kartya_azonosito_c': 'The `azon` field must be a card ID (c-…).',
 'kartya_api.cel_abszolut_apkg_ut': 'The `cel` field must be an absolute .apkg path.',
 'kartya_api.csomag_kerulhet_vaultba': 'The package cannot go into the workspace.',
 'kartya_api.csomag_olvashato_e': 'The package cannot be read: {e}',
 'kartya_api.fajl_abszolut_apkg_ut': 'The `fajl` field must be an absolute .apkg path.',
 'kartya_api.hianyzik_ut': 'The `ut` parameter is missing.',
 'kartya_api.jegy_1_4_again_hard': 'The `jegy` field must be 1 to 4 (Again, Hard, Good, Easy).',
 'kartya_api.kartyapakli_csak_mappa_mappabol_toltheto': 'A card deck can only be loaded from the “{mappa}” folder: '
                                                        '{rp}',
 'kartya_api.limit_egesz_szam': 'The `limit` field must be a whole number.',
 'kartya_api.ms_negativ_egesz': 'The `ms` field must be a non-negative whole number.',
 'kartya_api.proba_igaz_hamis': 'The `proba` field must be true or false.',
 'kartya_api.tanulasi_adatbazis': 'The study database is not available: {e}',
 'kartya_api.utak_kiserojegyzet_utak_listaja': 'The `utak` field must be a list of companion note paths.',
 'kartya_feladat.kartya_csak_tartalmi_jegyzetbol_keszul': 'Cards are only made from content notes (not from companion '
                                                          'notes or hidden folders).',
 'kartya_feladat.kijeloles_jegyzet_kijelolt_szovege_legyen': 'The `kijeloles` field must be the selected text of the '
                                                             'note (at most {MAX_KIJELOLES} characters).',
 'kartya_feladat.modell_regisztralt_modell_neve_legyen': 'The `modell` field must be the name of a registered model.',
 'kartya_feladat.nev_szoveg_modell_regiszter_feladat': '{nev} is not a `szoveg` model (see the `feladat` list in the '
                                                       'registry).',
 'kartya_feladat.parameterek_json_objektum_kellenek': 'The parameters must be a JSON object.',
 'kartya_feladat.proba_igaz_hamis_lehet': 'The `proba` field must be true or false.',
 'kartya_feladat.ut_vault_markdown_jegyzetenek_relativ': 'The `ut` field must be the relative path of a Markdown note '
                                                         'in the workspace.',
 'kartya_feladat.utak_1_max_ut_jegyzet': 'The `utak` field must be a list of 1 to {MAX_UT} relative note paths.',
 'kereses_api.hianyzo_kerdes': 'The question is missing.',
 'kereses_api.kerdes_legfeljebb_2000_karakter': 'The question can have at most 2000 characters.',
 'kereses_api.modell_nem_erheto_el': 'The Ask your workspace model is not available: {e}',
 'kereses_api.modell_nincs_kotve': 'The Ask your workspace model is not set up (the router table has no calibrated '
                                   '`szoveg` model).',
 'kuka_hiba': 'The item could not be moved to the Trash. Check the file tree and the Trash.',
 'kviz_api.hianyzik_kerdes': 'The `kerdes` field is missing.',
 'kviz_api.hianyzik_token_get_api_kviz': 'The `token` field is missing (it comes from `GET /api/kviz/kviz`).',
 'kviz_api.hianyzik_ut': 'The `ut` parameter is missing.',
 'kviz_api.hianyzik_valasz_valasz_sorszama_null': 'The `valasz` field is missing (the answer number, or null for “I '
                                                  "don't know”): there is no solution without an answer.",
 'kviz_api.hibas_igaz_hamis_legyen': 'The `hibas` field must be true or false.',
 'kviz_api.ido_ms_negativ_egesz_ms': 'The `ido_ms` field must be a non-negative whole number (ms).',
 'kviz_api.jegyzet_rp': 'Not a note: {rp}',
 'kviz_api.kerdest_elobb_meg_kell_valaszolni': 'Answer the question in the attempt first; only then can it be marked '
                                               'as wrong.',
 'kviz_api.kitoltes_lejart': 'The attempt has expired or is unknown. Open the quiz again.',
 'kviz_api.kulcs_8_80_karakteres_azonosito': 'The `kulcs` field must be an ID of 8 to 80 characters (letters, digits, '
                                             '`_`, `-`).',
 'kviz_api.kulcs_foglalt': 'This submission is already being saved. Wait and try again.',
 'kviz_api.kviz_megvaltozott': 'The quiz changed in the meantime. Open it again.',
 'kviz_api.kvizjegyzet_csak_mappa_mappabol_toltheto': 'A quiz note can only be loaded from the “{mappa}” folder: {rp}',
 'kviz_api.masik_kviz': 'This attempt belongs to a different quiz.',
 'kviz_api.megjegyzes_szoveg_legyen': 'The `megjegyzes` field must be text.',
 'kviz_api.mod_teljes_hibasak_lehet': 'The `mod` field must be teljes or hibasak.',
 'kviz_api.nincs_ertekelheto_valasz_ervenyes_kerdesre': 'There is no answer to assess: no valid question received an '
                                                        'answer.',
 'kviz_api.nincs_ilyen_kerdes_kid': 'No such question: {kid}',
 'kviz_api.tanulasi_adatbazis': 'The study database is not available: {e}',
 'kviz_api.valasz_valasz_sorszama_egesz_null': 'The `valasz` field must be the answer number (a whole number) or null.',
 'kviz_feladat.kviz_csak_tartalmi_jegyzetbol_keszul': 'Quizzes are only made from content notes (not from companion '
                                                      'notes or hidden folders).',
 'kviz_feladat.modell_regisztralt_modell_neve_legyen': 'The `modell` field must be the name of a registered model.',
 'kviz_feladat.n_kerdesek_szama_lo_hi': 'The `n` field (the number of questions) must be a whole number from {lo} to '
                                        '{hi}.',
 'kviz_feladat.nev_kviz_modell_regiszter_feladat': '{nev} is not a `kviz` model (see the `feladat` list in the '
                                                   'registry).',
 'kviz_feladat.parameterek_json_objektum_kellenek': 'The parameters must be a JSON object.',
 'kviz_feladat.proba_igaz_hamis_lehet': 'The `proba` field must be true or false.',
 'kviz_feladat.ut_vault_markdown_jegyzetenek_relativ': 'The `ut` field must be the relative path of a Markdown note in '
                                                       'the workspace.',
 'lemez.eacces': 'The file was not saved because the disk or folder is not writable. Check its permissions.',
 'lemez.edquot': 'The disk quota is exhausted. The file was not saved; the previous version is intact.',
 'lemez.efbig': 'The file exceeds the disk or file size limit. The file was not saved; the previous version is intact.',
 'lemez.eio': 'A disk I/O error prevented the operation. Check the volume.',
 'lemez.enodev': 'The disk is not available. Reconnect its volume and try again.',
 'lemez.enospc': 'The disk is full. The file was not saved; the previous version is intact. Free up space and saving '
                 'will retry.',
 'lemez.enxio': 'The disk is not available. Reconnect its volume and try again.',
 'lemez.eperm': 'The file was not saved because this operation is not permitted on the file or folder.',
 'lemez.erofs': 'The volume is read-only. The file was not saved.',
 'lemez.hiba': 'A file system error prevented the operation ({errno}).',
 'lemez.nem_elerheto': 'The vault is not available ({vault}). Your unsaved text is still in the editor; saving will '
                       'resume when the volume returns.',
 'ma.nincs_naptaradat': 'No calendar data is available yet. Allow calendar access and sync the calendar.',
 'ma.szakasz_hiba': 'This section could not be loaded. Try again.',
 'matek.cas_nem_elerheto': 'The CAS sandbox is not available: {ok}',
 'matek.ellenorzo_elutasitotta': 'The checker rejected the request: {hiba}',
 'matek.ellenorzo_ertelmezhetetlen': 'The checker returned a response that could not be read.',
 'matek.ellenorzo_foglalt': 'The checker is busy with another request. Try again.',
 'matek.ellenorzo_kilepes': 'The checker exited with an error ({kilepes}): {hiba}',
 'matek.ellenorzo_nem_indult': 'The checker did not start: {hiba}',
 'matek.idokorlat': 'The check timed out ({mp} s).',
 'matek.kikotesek': 'The constraints must be at most {max} short texts.',
 'matek.sor_alak': 'Each line must have a positive whole number and text of at most {max} characters.',
 'matek.sorok_lista': 'The lines must be a list of 1 to {max} items.',
 'matek.torzs_objektum': 'The request body must be a JSON object.',
 'matek.vegeredmeny_logikai': 'The final result must be true or false.',
 'media.poszter_csak_video': 'A poster can only be requested for a video.',
 'media.poszter_nem_keszul': 'The poster could not be created.',
 'media.range_hibas': 'The Range header is not valid.',
 'media.t_hibas': 'The time value is not valid.',
 'media.token_ervenytelen': 'The media token is not valid.',
 'megerosites_kell': 'The full solution can only be requested with a separate confirmation.',
 'mentetlen': 'The file has unsaved changes. Save it first.',
 'munkater_hasznalatban': 'This workspace is in use by another Manifold window.',
 'munkater_symlink': 'The workspace folder cannot be a symbolic link or point outside the workspace: {ut}',
 'naplo.datum_alak': 'The date must be in YYYY-MM-DD format.',
 'naplo.datum_ervenytelen': 'The date is not valid.',
 'naptar.azon_kategoria_szoveg': 'The id and the category must be text.',
 'naptar.azonok_lista': 'The ids must be a list of whole numbers.',
 'naptar.beiras_nem_sikerult': 'Could not write to the calendar: {hiba}',
 'naptar.javaslat_eldontve': 'The suggestion has already been decided ({allapot}).',
 'naptar.javaslat_elmult': 'The suggested time has already passed.',
 'naptar.javaslat_nincs': 'There is no such suggestion.',
 'naptar.kategoria_hibas': 'The calendar category is invalid.',
 'naptar.keret_elfogyott': 'The daily study budget has run out or changed. Refresh the suggestions.',
 'naptar.nincs_naptar': 'The calendar could not be found.',
 'naptar.nincs_tanulas_naptar': 'There is no calendar in the study category to write the block to. Categorise your '
                                'calendars in the Manifold panel, or set the study calendar in the settings.',
 'naptar.sav_foglalt': 'The suggested slot has been taken in the calendar.',
 'nem_workspace': 'This folder is not a Manifold workspace: {vault}',
 'nincs_cpp': 'No C++ solution file was found.',
 'nincs_eredmeny': 'The hint has not arrived yet.',
 'nincs_eszkoztar': 'The C++ tools are not installed. Open Settings to install them.',
 'nincs_install': 'The Manifold installation could not be found.',
 'nincs_kalibralt': 'No calibrated model is available for this task. Use trial mode or calibrate a model.',
 'nincs_vault': 'The {kulcs} location is not set up yet.',
 'nincs_workspace': 'The {kulcs} location is not set up yet.',
 'osszefoglalas.kontextus_hiba': 'The context could not be prepared. Check the selected notes and context limit.',
 'pdf.ut_hianyzik': 'The path is missing.',
 'pillanatkep.commit_ervenytelen': 'Invalid commit: {sha}',
 'pillanatkep.feladat_azon': 'Invalid task id: {feladat}',
 'pillanatkep.foglalt': 'Another snapshot operation is in progress. Try again when it finishes.',
 'pillanatkep.hibas': 'The snapshot operation could not be completed.',
 'pillanatkep.kor_ervenytelen': 'Invalid round or trial round: {kor}',
 'pillanatkep.naplo_all': 'An interrupted operation needs recovery before snapshot changes can proceed.',
 'pillanatkep.nincs_tar': 'There is no such live snapshot store: {tar}',
 'pillanatkep.sha_vagy_kor': 'Give exactly one of a commit or a round.',
 'pillanatkep.visszavonas_utkozes': 'Undo conflicts with later changes. Review the affected files.',
 'preset_toml_hibas': 'Invalid TOML file {ut}: {hiba}',
 'reteg_ismeretlen': 'Unknown configuration layer: {reteg}',
 'sablon.nem_sablon': 'Not a template (the template folder is {mappa}): {ut}',
 'sablon.nincs': 'There is no such template: {ut}',
 'settings_toml_hibas': 'Invalid TOML file {ut}: {hiba}',
 'tobbertelmu': 'Several task notes embed this .cpp file. Choose one.',
 'tracker.nem_irhato': 'The tracker database cannot be written.',
 'tracker.nem_irhato_kotegelt': 'The tracker database cannot be written right now. The app will send the batch again '
                                'later.',
 'tulajdonsag.fm_nem_blokk': 'The front matter is not a valid block.',
 'tulajdonsag.forras': 'The source must be user or machine.',
 'tulajdonsag.kulcs_hianyzik': 'The property name is missing.',
 'tulajdonsag.kulcs_szoveg': 'The value of {kulcs} must be text.',
 'tulajdonsag.megerosit_logikai': 'The confirmation must be true or false.',
 'tulajdonsag.muvelet': 'The operation must be set or remove.',
 'tulajdonsag.tipus': 'Unknown type: {tipus}',
 'vault.alap_hianyzik': 'The base version is missing. Files are not overwritten blindly.',
 'vault.canvas_ervenytelen': 'The canvas is not valid JSON Canvas and was not saved: {hiba}',
 'vault.fajl_eltunt': 'The file disappeared meanwhile (moved or deleted?): {ut}',
 'vault.fajltipus': 'This file type cannot be served: {ut}',
 'vault.jegyzet_mentes_kozben': 'The note changed while saving.',
 'vault.jegyzet_valtozott': 'The note changed since it was loaded (Obsidian, sync or a task wrote it).',
 'vault.kor_zar_foglalt': 'Manifold is writing to the workspace right now. The version on disk is not '
                          'in a snapshot yet, so the overwrite is waiting.',
 'vault.link_cel_hianyzik': 'The link target is missing.',
 'vault.link_cel_nincs': 'The target is not a note (file not found): {cel}',
 'vault.link_mappa': 'A folder cannot be given together with a link, and the type can only be md or cpp.',
 'vault.menthetetlen_tipus': 'Only a note (.md), a Bases view (.base), a canvas (.canvas) or source code in a known '
                             'language (for example .cpp or .py) can be saved.',
 'vault.nem_szoveges': 'Not a text file: {ut}',
 'vault.nev_ervenytelen': 'Invalid name. It cannot contain \\ / : * ? " < > | # ^ [ ] and cannot start with a dot.',
 'vault.nincs_fajl': 'There is no such file: {ut}',
 'vault.nincs_mappa': 'There is no such folder: {mappa}',
 'vault.mappa_nem_relativ': 'The folder must be a path inside the workspace, not an absolute path.',
 'vault.tartalom_alak': 'The content can only be a (not too large) text, and only for a note or C++ source.',
 'vault.tartalom_hianyzik': 'The content is missing.',
 'vault.tipus_hibas': 'The file type must be `md`, `base`, `canvas` or `cpp`.',
 'vault.tul_nagy_fajl': 'The file is too large.',
 'vault.tul_nagy_jegyzet': 'The note is too large.',
 'vault.ut_ervenytelen': 'Invalid path: {ut}',
 'vault.ut_hianyzik': 'The path is missing.',
 'vault.van_ilyen_fajl': 'A file with this name already exists: {ut}',
 'vault.vaulton_kivul': 'The path is outside the workspace: {ut}',
 'vault_nem_elerheto': 'The vault is not available. Reconnect its volume or restore its folder. Your unsaved text is '
                       'still in the editor.',
 'vezerlo.feladat_azon': 'Invalid task id: {fid}',
 'vezerlo.kapcsolo_hibas': 'The setting is invalid. Check its value and try again.',
 'video.adat_mezo': 'The chunk comes as base64 in the data field, at most 8 MiB.',
 'video.base64': 'The data is not valid base64.',
 'video.bejaras_nem_olvashato': 'The crawl result could not be read. Start the crawl again.',
 'video.csak_video': 'Only video files can be uploaded (mp4, m4v, mov, mkv, webm, avi; name up to 200 bytes).',
 'video.csoport_ervenytelen': 'Invalid group id.',
 'video.darab_helye': 'The chunk position ({offset}) is not the current end of the file ({vege}).',
 'video.fajl_nagy': 'The file is larger than allowed ({gib} GiB).',
 'video.nincs_nev': 'There is no free name in the inbox folder.',
 'video.offset': 'The offset must be a non-negative whole number.',
 'video.torzs_objektum': 'The request must be a JSON object.',
 'video.ures': 'The file is empty.',
 'video.url_hianyzik': 'Enter the link of the page to crawl.',
 'workspace_beallitas_hibas': 'The workspace settings could not be read.',
 'workspace_csere': 'A different workspace is now at this location. Reopen the intended workspace.',
 'workspace_id_csere_hiba': 'The workspace ID could not be renewed.',
 'workspace_id_hibas': 'The workspace ID is invalid.',
 'workspace_toml_hibas': 'Invalid TOML file {ut}: {hiba}',
 'workspace_ujabb': 'This workspace needs a newer version of Manifold.',
 'ws.kezfogas_hibas': 'The WebSocket handshake is not valid.',
 'ws.kezfogas_kell': 'A WebSocket handshake is required.',
 'ws.origin': 'Unknown origin.',
 'ws.titok': 'The WebSocket secret is missing or not valid.'}

ANGOL.update({
    "feladat.core_megszakadt": "Manifold stopped before the task finished.",
    "feladat.arva_leallitva": "Manifold stopped before the task finished. Its orphaned step (pid {pid}) was stopped.",
    "konfig_hiba": "The configuration is invalid.",
    "vault.nem_elerheto": "The vault is not available.",
})

# Compatibility for historic task metadata: translate only exact known phrases.
FELADAT_SZOVEGEK = {'A bekötött füzetfotók újradöntése; eltérésnél a beágyazás a jobb jegyzetbe költözik (gépi írás, visszavonható).': 'Notebook '
                                                                                                                    'photos '
                                                                                                                    'that '
                                                                                                                    'were '
                                                                                                                    'linked '
                                                                                                                    'are '
                                                                                                                    're-judged. '
                                                                                                                    'If '
                                                                                                                    'the '
                                                                                                                    'result '
                                                                                                                    'differs, '
                                                                                                                    'the '
                                                                                                                    'embed '
                                                                                                                    'moves '
                                                                                                                    'to '
                                                                                                                    'the '
                                                                                                                    'better '
                                                                                                                    'note '
                                                                                                                    '(automated '
                                                                                                                    'write, '
                                                                                                                    'can '
                                                                                                                    'be '
                                                                                                                    'undone).',
 'A frissen szerkesztett jegyzetek biztosan felismert képletei alá ```plot blokk kerül (gépi írás, visszavonható).': 'A '
                                                                                                                     '```plot '
                                                                                                                     'block '
                                                                                                                     'is '
                                                                                                                     'added '
                                                                                                                     'under '
                                                                                                                     'each '
                                                                                                                     'reliably '
                                                                                                                     'recognised '
                                                                                                                     'formula '
                                                                                                                     'in '
                                                                                                                     'recently '
                                                                                                                     'edited '
                                                                                                                     'notes '
                                                                                                                     '(automated '
                                                                                                                     'write, '
                                                                                                                     'can '
                                                                                                                     'be '
                                                                                                                     'undone).',
 'A fájl bemásolódott, a szöveges pillanatkép nem sikerült.': 'The file was copied, but the text snapshot failed.',
 'A fájl bemásolódott, az index frissítése még folyamatban van.': 'The file was copied. The index is still updating.',
 'A fájl bemásolódott, az index frissítése még várat magára.': 'The file was copied. The index update is still '
                                                               'pending.',
 'A keresés vektorindexe': 'Search vector index',
 'A keresés vektorindexének frissítése': 'Update the search vector index',
 'A modell kártyákat javasol a jegyzetből; a kapukon átment kártyák a kísérőjegyzetbe kerülnek, a forrásba blokkazonosító és beágyazó sor (gépi írás, visszavonható).': 'The '
                                                                                                                                                                        'model '
                                                                                                                                                                        'suggests '
                                                                                                                                                                        'cards '
                                                                                                                                                                        'from '
                                                                                                                                                                        'the '
                                                                                                                                                                        'note. '
                                                                                                                                                                        'Cards '
                                                                                                                                                                        'that '
                                                                                                                                                                        'pass '
                                                                                                                                                                        'the '
                                                                                                                                                                        'gates '
                                                                                                                                                                        'go '
                                                                                                                                                                        'to '
                                                                                                                                                                        'the '
                                                                                                                                                                        'companion '
                                                                                                                                                                        'note, '
                                                                                                                                                                        'and '
                                                                                                                                                                        'a '
                                                                                                                                                                        'block '
                                                                                                                                                                        'ID '
                                                                                                                                                                        'and '
                                                                                                                                                                        'an '
                                                                                                                                                                        'embed '
                                                                                                                                                                        'line '
                                                                                                                                                                        'are '
                                                                                                                                                                        'added '
                                                                                                                                                                        'to '
                                                                                                                                                                        'the '
                                                                                                                                                                        'source '
                                                                                                                                                                        '(automated '
                                                                                                                                                                        'write, '
                                                                                                                                                                        'can '
                                                                                                                                                                        'be '
                                                                                                                                                                        'undone).',
 'A modell kérdéseket javasol a jegyzetből; a kapukon átment kérdések a kvízjegyzetbe kerülnek, a forrás `## Gyakorlás` szakaszába a beágyazó sor (gépi írás, visszavonható). Ha a kvíz modellje csak a távol-keretbe fér, a feladat tétlenségben készül el.': 'The '
                                                                                                                                                                                                                                                               'model '
                                                                                                                                                                                                                                                               'suggests '
                                                                                                                                                                                                                                                               'questions '
                                                                                                                                                                                                                                                               'from '
                                                                                                                                                                                                                                                               'the '
                                                                                                                                                                                                                                                               'note. '
                                                                                                                                                                                                                                                               'Questions '
                                                                                                                                                                                                                                                               'that '
                                                                                                                                                                                                                                                               'pass '
                                                                                                                                                                                                                                                               'the '
                                                                                                                                                                                                                                                               'gates '
                                                                                                                                                                                                                                                               'go '
                                                                                                                                                                                                                                                               'to '
                                                                                                                                                                                                                                                               'the '
                                                                                                                                                                                                                                                               'quiz '
                                                                                                                                                                                                                                                               'note, '
                                                                                                                                                                                                                                                               'and '
                                                                                                                                                                                                                                                               'an '
                                                                                                                                                                                                                                                               'embed '
                                                                                                                                                                                                                                                               'line '
                                                                                                                                                                                                                                                               'is '
                                                                                                                                                                                                                                                               'added '
                                                                                                                                                                                                                                                               'to '
                                                                                                                                                                                                                                                               'the '
                                                                                                                                                                                                                                                               '`## '
                                                                                                                                                                                                                                                               'Gyakorlás` '
                                                                                                                                                                                                                                                               'section '
                                                                                                                                                                                                                                                               'of '
                                                                                                                                                                                                                                                               'the '
                                                                                                                                                                                                                                                               'source '
                                                                                                                                                                                                                                                               '(automated '
                                                                                                                                                                                                                                                               'write, '
                                                                                                                                                                                                                                                               'can '
                                                                                                                                                                                                                                                               'be '
                                                                                                                                                                                                                                                               'undone). '
                                                                                                                                                                                                                                                               'If '
                                                                                                                                                                                                                                                               'the '
                                                                                                                                                                                                                                                               'quiz '
                                                                                                                                                                                                                                                               'model '
                                                                                                                                                                                                                                                               'only '
                                                                                                                                                                                                                                                               'fits '
                                                                                                                                                                                                                                                               'the '
                                                                                                                                                                                                                                                               'idle '
                                                                                                                                                                                                                                                               'budget, '
                                                                                                                                                                                                                                                               'the '
                                                                                                                                                                                                                                                               'task '
                                                                                                                                                                                                                                                               'runs '
                                                                                                                                                                                                                                                               'while '
                                                                                                                                                                                                                                                               'the '
                                                                                                                                                                                                                                                               'machine '
                                                                                                                                                                                                                                                               'is '
                                                                                                                                                                                                                                                               'idle.',
 'Az oldal videóinak felderítése': 'Find videos on the page',
 'Füzet-bekötések ellenőrzése': 'Check notebook links',
 'Füzetfotók (automatikus)': 'Notebook photos (automatic)',
 'Füzetfotók az aktív jegyzetbe': 'Notebook photos into the active note',
 'Füzetfotók bekötése': 'Link notebook photos',
 'Grafikonok a képletek alá': 'Graphs under the formulas',
 'Grafikonok a képletek alá (automatikus)': 'Graphs under the formulas (automatic)',
 'Kvíz a jegyzetből (modell + kapuk)': 'Quiz from the note (model and gates)',
 'Kvíz ebből': 'Quiz from this',
 'Kártyák (automatikus)': 'Cards (automatic)',
 'Kártyák a jegyzetből (modell + kapuk)': 'Cards from the note (model and gates)',
 'Kártyák az új vagy erősen módosult jegyzetekből': 'Cards from new or heavily changed notes',
 'Kártyák ebből': 'Cards from this',
 'Megoldás (matek)': 'Solution (math)',
 'Megoldás modellel és CAS-ellenőrzéssel': 'Solve with a model and CAS verification',
 'Mentés a belső lemezre': 'Back up to the local disk',
 'Mentés a belső lemezre (git bundle)': 'Back up to the local disk (Git bundle)',
 'Próbafeladat': 'Trial task',
 'Próbamód: a blokkok a vault APFS-klónjára kerülnek, a vaultba nem.': 'Trial mode: the blocks go to an APFS clone of '
                                                                       'the workspace, not to the workspace itself.',
 'Próbamód: a kvíz a vault APFS-klónjára kerül, a vaultba nem.': 'Trial mode: the quiz goes to an APFS clone of the '
                                                                 'workspace, not to the workspace itself.',
 'Próbamód: a kártyák a vault APFS-klónjára kerülnek, a vaultba nem.': 'Trial mode: the cards go to an APFS clone of '
                                                                       'the workspace, not to the workspace itself.',
 'Próbamód: az írás a vault APFS-klónjára megy, a fotók a helyükön maradnak.': 'Trial mode: the write goes to an APFS '
                                                                               'clone of the workspace and the photos '
                                                                               'stay where they are.',
 'Próbamód: csak javaslat, a vault nem változik.': 'Trial mode: suggestions only, the workspace does not change.',
 'Teljes mentés külső lemezre': 'Full backup to an external disk',
 'Teljes mentés és ellenőrzés': 'Full backup and verification',
 'Videó letöltése': 'Download video',
 'Videók bevitele a vaultba': 'Import videos into the workspace',
 'Videók letöltése': 'Download videos',
 'a felirat a vaulton kívülre mutató symlink: nem olvasható': 'The subtitles file is a symlink pointing outside the '
                                                              'workspace, so it cannot be read.',
 'a felirat túl nagy, nem töltődött be': 'The subtitles file is too large and was not loaded.',
 'a feliratfájlban nincs olvasható cue': 'The subtitles file has no readable cues.',
 'a vault pillanatkép-tárolója nem érhető el: az átnevezés előtti útvonalak nem követhetők': 'The workspace snapshot '
                                                                                             'store is not available, '
                                                                                             'so paths from before a '
                                                                                             'rename cannot be '
                                                                                             'followed.',
 'az index még épül: a felkészülési jegyzetek és a témák később jelennek meg': 'The index is still building. Readiness '
                                                                               'notes and topics will appear later.',
 'Árva jegyzet: nincs bejövő és nincs kimenő jegyzet-link.': 'Orphan note: it has no incoming and no outgoing note '
                                                             'links.',
 'Összefoglaló (automatikus)': 'Summary (automatic)',
 'Összefoglaló a jegyzetből (modell + kapuk)': 'Summary from the note (model and gates)',
 'Összefoglaló a mappából (jegyzet-összefoglalókból)': 'Summary from the folder (note summaries)',
 'Összefoglaló a videóból (az átirat alapján)': 'Summary from the video (transcript)',
 'Összefoglalók az új vagy erősen módosult jegyzetekből': 'Summaries from new or heavily changed notes'}

ANGOL.update({
    "felkeszultseg.ertekeles_hiba": "This assessment could not be loaded. Try again.",
    "kereses.modell_hiba": "The model is not available. Try again or check its calibration in Settings.",
    "nem_indul": "The AI request could not start. Open its log for details.",
    "motor_hiba": "The AI engine stopped unexpectedly. Open its log for details.",
})

FELADAT_SZOVEGEK.update({'A mappa jegyzet-összefoglalóiból (a hiányzókat előbb elkészíti) a modell mappa-szintű állításokat ír; mindegyik az eredeti jegyzet mondatára vezethető vissza. A kísérőjegyzet az összefoglaló-mappába kerül (visszavonható).': 'The '
                                                                                                                                                                                                                                  'model '
                                                                                                                                                                                                                                  'combines '
                                                                                                                                                                                                                                  'the '
                                                                                                                                                                                                                                  'folder’s '
                                                                                                                                                                                                                                  'note '
                                                                                                                                                                                                                                  'summaries '
                                                                                                                                                                                                                                  'into '
                                                                                                                                                                                                                                  'claims '
                                                                                                                                                                                                                                  'traceable '
                                                                                                                                                                                                                                  'to '
                                                                                                                                                                                                                                  'the '
                                                                                                                                                                                                                                  'original '
                                                                                                                                                                                                                                  'notes. '
                                                                                                                                                                                                                                  'Missing '
                                                                                                                                                                                                                                  'note '
                                                                                                                                                                                                                                  'summaries '
                                                                                                                                                                                                                                  'are '
                                                                                                                                                                                                                                  'created '
                                                                                                                                                                                                                                  'first. '
                                                                                                                                                                                                                                  'The '
                                                                                                                                                                                                                                  'companion '
                                                                                                                                                                                                                                  'note '
                                                                                                                                                                                                                                  'is '
                                                                                                                                                                                                                                  'written '
                                                                                                                                                                                                                                  'to '
                                                                                                                                                                                                                                  'the '
                                                                                                                                                                                                                                  'summaries '
                                                                                                                                                                                                                                  'folder '
                                                                                                                                                                                                                                  '(undoable).',
 'A modell megoldja a kijelölt feladatot; a kódja a CAS-homokozóban fut, és a megoldás `[!solution]` calloutként a feladat alá kerül (gépi írás, visszavonható).': 'The '
                                                                                                                                                                   'model '
                                                                                                                                                                   'solves '
                                                                                                                                                                   'the '
                                                                                                                                                                   'selected '
                                                                                                                                                                   'problem '
                                                                                                                                                                   'and '
                                                                                                                                                                   'runs '
                                                                                                                                                                   'its '
                                                                                                                                                                   'code '
                                                                                                                                                                   'in '
                                                                                                                                                                   'the '
                                                                                                                                                                   'CAS '
                                                                                                                                                                   'sandbox. '
                                                                                                                                                                   'The '
                                                                                                                                                                   'solution '
                                                                                                                                                                   'is '
                                                                                                                                                                   'placed '
                                                                                                                                                                   'below '
                                                                                                                                                                   'the '
                                                                                                                                                                   'problem '
                                                                                                                                                                   'in '
                                                                                                                                                                   'a '
                                                                                                                                                                   '`[!solution]` '
                                                                                                                                                                   'callout '
                                                                                                                                                                   '(machine '
                                                                                                                                                                   'write, '
                                                                                                                                                                   'undoable).',
 'A modell állításokat javasol a jegyzetből, mindegyik mellé a jegyzet szó szerinti mondatával; ami átmegy a kapukon, a kísérőjegyzetbe kerül, a forrásba blokkazonosító és beágyazó sor (gépi írás, visszavonható).': 'The '
                                                                                                                                                                                                                       'model '
                                                                                                                                                                                                                       'suggests '
                                                                                                                                                                                                                       'claims '
                                                                                                                                                                                                                       'supported '
                                                                                                                                                                                                                       'by '
                                                                                                                                                                                                                       'exact '
                                                                                                                                                                                                                       'quotations '
                                                                                                                                                                                                                       'from '
                                                                                                                                                                                                                       'the '
                                                                                                                                                                                                                       'note. '
                                                                                                                                                                                                                       'Claims '
                                                                                                                                                                                                                       'that '
                                                                                                                                                                                                                       'pass '
                                                                                                                                                                                                                       'the '
                                                                                                                                                                                                                       'gates '
                                                                                                                                                                                                                       'go '
                                                                                                                                                                                                                       'to '
                                                                                                                                                                                                                       'the '
                                                                                                                                                                                                                       'companion '
                                                                                                                                                                                                                       'note, '
                                                                                                                                                                                                                       'with '
                                                                                                                                                                                                                       'block '
                                                                                                                                                                                                                       'IDs '
                                                                                                                                                                                                                       'and '
                                                                                                                                                                                                                       'embeds '
                                                                                                                                                                                                                       'added '
                                                                                                                                                                                                                       'to '
                                                                                                                                                                                                                       'the '
                                                                                                                                                                                                                       'source '
                                                                                                                                                                                                                       '(machine '
                                                                                                                                                                                                                       'write, '
                                                                                                                                                                                                                       'undoable).',
 'A médiafájl melletti átirat (VTT) időablakaiból a modell állításokat javasol, időkód-linkekkel; a kísérőjegyzet az összefoglaló-mappába kerül (visszavonható).': 'The '
                                                                                                                                                                   'model '
                                                                                                                                                                   'suggests '
                                                                                                                                                                   'claims '
                                                                                                                                                                   'from '
                                                                                                                                                                   'the '
                                                                                                                                                                   'media '
                                                                                                                                                                   'transcript '
                                                                                                                                                                   '(VTT), '
                                                                                                                                                                   'with '
                                                                                                                                                                   'links '
                                                                                                                                                                   'to '
                                                                                                                                                                   'timestamps. '
                                                                                                                                                                   'The '
                                                                                                                                                                   'companion '
                                                                                                                                                                   'note '
                                                                                                                                                                   'is '
                                                                                                                                                                   'written '
                                                                                                                                                                   'to '
                                                                                                                                                                   'the '
                                                                                                                                                                   'summaries '
                                                                                                                                                                   'folder '
                                                                                                                                                                   '(undoable).',
 'A változott jegyzetek darabjai beágyazódnak a jelentés szerinti kereséshez (a vaultba nem ír).': 'Build embeddings '
                                                                                                   'for the changed '
                                                                                                   'notes so they can '
                                                                                                   'be searched by '
                                                                                                   'meaning (the vault '
                                                                                                   'is unchanged).',
 'Próbamód: a megoldás a vault APFS-klónjára kerül, a jegyzetbe nem.': 'Trial mode: the solution is written to an APFS '
                                                                       'clone of the workspace. The note is unchanged.',
 'Próbamód: a staging és az archívum a var/tmp alá kerül, pillanatkép nincs.': 'Trial mode: staging and archives use '
                                                                               'the temporary data folder; no snapshot '
                                                                               'is created.',
 'Próbamód: az írás a vault APFS-klónjára megy, a staging nem változik.': 'Trial mode: the write goes to an APFS clone '
                                                                          'of the workspace. Staging is unchanged.',
 'Próbamód: az összefoglaló a vault APFS-klónjára kerül, a vaultba nem.': 'Trial mode: the summary is written to an '
                                                                          'APFS clone of the workspace. The workspace '
                                                                          'is unchanged.'})

ANGOL.update({
    "portable_termekben": "Portable setup can only run from a checkout installation.",
    "vault_nem_letezik": "The vault folder does not exist: {vault}",
    "vault_a_kodban": "The vault must be outside the read-only code folder: {vault}",
    "settings_ervenytelen": "Some installation settings are invalid. Review the rejected values.",
    "settings_kikapcsolva": "Installation settings are disabled because MOS_SETTINGS is empty.",
    "settings_letezik": "Installation settings already exist: {ut}. Confirm replacement to continue.",
})

ANGOL.update({
    "video.link_hianyzik": "Enter at least one video link.",
    "video.link_szoveg": "Each video link must be text.",
    "video.link_hibas": "The video link is invalid.",
    "video.link_http": "Only http(s) links are supported.",
    "video.link_hitelesites": "Video links cannot contain a username or password.",
    "video.link_helyi": "Videos cannot be downloaded from local or private addresses.",
    "video.link_sok": "A task can contain at most {max} video links ({n} received).",
    "video.ffmpeg_hianyzik": "The bundled ffmpeg is missing. Install the runtime tools before downloading videos.",
})

ANGOL.update({
    "beallitas.hibas": "This setting is not valid. Check its value and try again.",
    "beallitas.utkozes": "Settings changed elsewhere. Reload them before saving again.",
    "beallitas.symlink": "The settings location is not safe to write. Reopen this workspace.",
    "beallitas.munkater_csere": "The workspace changed on disk. Reopen it before saving settings.",
    "indito.hibas_keres": "The workspace request is not valid. Choose a folder and try again.",
    "indito.megerosites": "Preview and confirm this folder before opening it as a workspace.",
    "indito.lemez": "The folder could not be read or written. Check that its disk is connected and writable, then try again.",
    "demo.nem_demo": "This is not the demo workspace. The demo can only be reset inside the demo workspace.",
    "demo.megerosites": "Confirm the reset: it restores the demo notes and sets the demo's sample data back.",
    "demo.hibas_keres": "The reset request takes only a confirmation.",
    "demo.nincs": "The demo workspace has not been created yet. Choose \"Try demo\" first.",
    "demo.fut": "The demo workspace is open. Close it, then reset it from the launcher.",
    "demo.nem_biztonsagos_ut": "A folder of the demo workspace is a link or not a normal folder, so it cannot be reset safely.",
    "modul.kikapcsolva": "This module is turned off. Enable it in Settings → Modules to use it.",
    "tulajdonsag_tipus.utkozes": "Property types changed. Reload the list before trying again.",
    "tulajdonsag_tipus.munkater_csere": "The workspace changed on disk. Reopen it before changing property types.",
    "tulajdonsag_tipus.nem_biztonsagos": "Property types must be stored in a regular file, not a symbolic link.",
    "tulajdonsag_tipus.tul_nagy": "The property types file is too large to edit safely.",
    "tulajdonsag_tipus.hibas_json": "The property types file is not valid JSON. Repair it before changing a type; it was not overwritten.",
    "tulajdonsag_tipus.bonyolult_json": "The property types file is too complex to edit safely. It was not overwritten.",
    "tulajdonsag_tipus.mappa": "The vault configuration folder is unavailable or is a symbolic link.",
    "tulajdonsag_tipus.keres": "Choose a property key, a type and the loaded revision.",
    "tulajdonsag_tipus.kulcs": "Enter a valid property name.",
    "tulajdonsag_tipus.tipus": "Choose a supported property type.",
    "tulajdonsag_tipus.rogzitett": "Tags and aliases have fixed property types.",
    "tulajdonsag_tipus.rev": "Reload property types before saving a change.",
    "tulajdonsag_tipus.pillanat_nincs": "Property types were not changed because snapshots are unavailable. Repair the snapshot store and try again.",
    "tulajdonsag_tipus.pillanat_hiba": "Property types were not changed because the safety snapshot failed. Repair the snapshot store and try again.",
    "tulajdonsag_tipus.foglalt": "The vault is busy. Wait for the current operation to finish, then try again.",
})

# 04-embeds-02: explicit external image download (core/kulso_kep.py)
ANGOL.update({
    "kulso_kep.url_hianyzik": "The image link is missing.",
    "kulso_kep.url_hibas": "The image link is not valid.",
    "kulso_kep.csak_https": "Only https image links can be downloaded.",
    "kulso_kep.hitelesites": "The image link must not contain a user name or password.",
    "kulso_kep.port": "The image link must use the default https port.",
    "kulso_kep.helyi_cim": "Images are not downloaded from local or private addresses.",
    "kulso_kep.nincs_kiszolgalo": "The image server could not be found.",
    "kulso_kep.nem_elerheto": "The image server could not be reached.",
    "kulso_kep.tanusitvany": "The image server's certificate could not be verified.",
    "kulso_kep.idotullepes": "The image download timed out.",
    "kulso_kep.megszakadt": "The image download was interrupted.",
    "kulso_kep.hibas_valasz": "The server sent an invalid response.",
    "kulso_kep.http_hiba": "The server did not provide the image (HTTP {statusz}).",
    "kulso_kep.nem_kep": "The link does not point to a supported image.",
    "kulso_kep.tul_nagy": "The image is larger than {max_mib} MiB.",
    "kulso_kep.atiranyitas": "The image link redirects too many times.",
    "kulso_kep.forras_hianyzik": "The source note is missing.",
    "egeszseg.ismeretlen_javitas": "This fix is not available.",
    "egeszseg.nincs_mit_javitani": "There is nothing to fix right now.",
    "egeszseg.ismeretlen_ellenorzes": "This check does not exist.",
})

# F6: Model Manager, calibration gates and the shared AI error contract (core/modell/{api,manifeszt,kuszob,teszt,aranycsomag}.py)
ANGOL.update({
    "csak_tavol": "This model only runs while you are away from the computer.",
    "nincs_ai_runtime": "The local AI component is not installed or did not start.",
    "nincs_telepitve": "This feature needs a local AI model. Install one in Settings › Models.",
    "worker_hiba": "The local AI model did not respond. Try again.",
    "modell.ismeretlen": "Unknown model: {modell}",
    "modell.manifeszt_hianyzik": "The model list of the installation is missing.",
    "modell.manifeszt_hibas": "The model list of the installation is damaged.",
    "modell.forras_tiltott": "This model source is not supported.",
    "modell.host_tiltott": "Downloads from {host} are not allowed.",
    "modell.torles_tiltott": "Manifold cannot remove this model folder.",
    "modell.letoltes_hiba": "The model download failed. Try again later.",
    "modell.nincs_fajl": "The model source has no files to download.",
    "modell.tiltott_fajlnev": "The model source contains an unsafe file name.",
    "modell.nincs_hely": "Not enough disk space: {szukseges_gb} GB is needed.",
    "modell.hash_elter": "A downloaded file failed the integrity check and was removed: {fajl}",
    "modell.letoltes_fut": "This model is already downloading.",
    "modell.nincs_letoltes": "This model is not downloading.",
    "modell.teszt_fut": "A model test is already running.",
    "modell.megerosites_kell": "Confirm that the model should be removed.",
    "modell.foglalt": "The model is in use by a download or a test. Try again when it finishes.",
    "modell.kuszob_nincs": "This task has no calibration threshold yet, so no model can be marked as calibrated.",
    "modell.keves_tetel": "The set has {n} items; at least {min_tetel} are needed.",
    "modell.kuszob_alatt": "The score {pontszam} is below the threshold {kuszob}.",
    "modell.reszpont_alatt": "The partial score {mezo} is below {kuszob}.",
    "modell.feladat_ismeretlen": "Unknown AI task: {feladat}",
    "modell.konvertalas_kell": "This model needs a local conversion before it can be used.",
    "modell.nincs_telepitve": "The model is not installed.",
    "modell.tul_nagy": "The model needs {csucs_gb} GB of memory; at most {keret_gb} GB is available for AI.",
    "modell.halmaz_nincs": "There are no example items for this task.",
    "modell.halmaz_vazlat": "The example set is not approved yet.",
    "modell.eloproba_ervenytelen": "The trial run failed: the answers were cut off, repeated, empty or failed.",
    "modell.nem_teljes": "The measurement did not cover the whole example set.",
    "modell.ervenytelen": "The measurement is not valid: too many answers were cut off, repeated, empty or failed.",
    "modell.teszt_hiba": "The model test could not run.",
    "modell.nincs_teszt": "This model has not been tested on this task yet.",
    "modell.sajat_nem_tamogatott": "Your own examples are not available for this task.",
    "modell.sajat_hibas_tetel": "Item {sor} is invalid ({mezo}).",
})

# F10: the multi-language code workbench (core/kod_utvonal.py; the engine's event codes from modulok/kod)
ANGOL.update({
    "kod.hianyzik_ut": "The path (`ut`) is missing.",
    "kod.ismeretlen_kiterjesztes": "Not a task note or a source file of a known language: {ut}",
    "kod.motor_nem_valaszol": "The code engine does not answer: {hiba}",
    "kod.nincs_forras": "The source file is not found or not readable: {ut}",
    "kod.nincs_beagyazott_forras": "The note embeds no source file of a known language, or the embedded file is not found.",
    "kod.forras_nem_talalhato": "The embedded file is not found (or ambiguous): {nev}",
    "kod.nincs_jegyzet": "The task note is not readable.",
    "kod.tobbertelmu": "More than one task note embeds this source: choose one.",
    "kod.ismeretlen_nyelv": "Unknown language: {nyelv}",
    "kod.mentetlen": "The file has unsaved changes: save it first.",
    "kod.ismeretlen_mod": "The mode is `gyors` or `hibakereso`.",
    "kod.mod_nem_tamogatott": "The {mod} mode is only available for C and C++.",
    "kod.ismeretlen_ai_mod": "The mode is one of: {modok}.",
    "kod.megerosites_kell": "The full solution can only be requested with a separate confirmation.",
    "kod.core_leall": "Manifold is shutting down.",
    "kod.foglalt": "A run is already in progress.",
    "kod.nincs_ilyen_futas": "No such run: {id}",
    "kod.hianyzik_azonosito": "The `{mezo}` field is missing.",
    "kod.nincs_eszkozlanc": "No {nyelv} toolchain (missing: {hianyzo}). {tipp}",
    "kod.nincs_eszkoz": "No usable `{eszkoz}` found.",
    "kod.nincs_homokozo": "The sandbox is not available: {uzenet}",
    "kod.tul_nagy_forras": "The source is too large (at most {max_mib} MiB).",
    "kod.forditasi_hiba": "The compilation failed.",
    "kod.nincs_program": "The compiler produced no runnable program.",
    "kod.nincs_teszt": "There is no test block in the note: only the compile step ran.",
    "kod.nem_indul": "The code engine does not start: {hiba}",
    "kod.motor_hiba": "The code engine stopped unexpectedly.",
    "kod.nincs_kalibralt": "There is no calibrated model for {nyelv} ({kulcs}) and no trial model. Settings › AI › Calibration.",
    "kod.csak_tavol": "The calibrated code model only fits the away budget: it runs when you are not working on the machine.",
    "kod.worker_hiba": "The model worker does not answer.",
    "kod.modell_hiba": "The generation stopped with an error.",
    "kod.nincs_hiba": "The program compiles and passes every test: there is nothing to explain.",
    "kod.nincs_kodblokk": "The answer has no code block in this language.",
    "kod.generator_hiba": "The generator is missing or does not compile.",
    "kod.referencia_hiba": "The reference is missing or does not compile.",
    "kod.sajat_nem_fordul": "Your own solution does not compile: fix the compile error first.",
    "vault.nyelv_ismeretlen": "Unknown programming language.",
    "doku.hianyzik_tema": "The `tema` parameter is missing.",
    "doku.ismeretlen_tema": "There is no guide page for this topic: {tema}",
    "doku.nincs_oldal": "The guide page is not installed.",
})

# F8: import (core/importalas.py)
ANGOL.update({
    "import.ervenytelen_keres": "The import request is not valid ({mezo}).",
    "import.tilos": "The import cannot start: {akadaly}.",
    "import.terv_valtozott": "The folders changed since the preview. Preview the import again.",
    "import.utkozes": "A file with different content already exists in the destination: {ut}.",
    "import.fut": "This import is already running.",
    "import.forras_valtozik": "A source file kept changing during the import: {ut}.",
    "import.beallitas_hibas": "This setting is not valid: {kulcs}.",
    "import.munkater_csere": "The workspace changed on disk. Reopen it before importing.",
    "import.masolas_hiba": "The import stopped: {ok}. Resume it to continue, or undo it.",
    "import.nincs": "There is no such import.",
    "import.visszafordit_utkozes": "The import cannot be undone because of {ut}. Nothing was changed.",
    "import.munkater_hasznalatban": "Close the imported workspace before undoing the import.",
    "import.fejleszto_mod": "This import is available in Developer mode only.",
    "import.nem_fut": "This import is not running.",
    "import.megszakitva": "The import was cancelled. Run the import again to continue, or undo it.",
})
