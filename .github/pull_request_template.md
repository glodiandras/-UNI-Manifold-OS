## What and why

<!-- One or two sentences. Link the plan phase or issue if there is one. -->

## Checklist

- [ ] `MOS_SETTINGS='' MOS_SZIGORU=1 bin/mos test` is green (or the relevant modules, listed below)
- [ ] `bin/mos app test` and `bin/mos app build` (svelte-check + build) are green for UI changes
- [ ] A `docs/plan/NAPLO.md` entry describes what changed, what remains, regressions and risks (needed for phase work)
- [ ] No personal data: no developer paths, real names, vault or folder names, private notes, handwriting or gold-set material
- [ ] No hardcoded absolute paths; paths come from the layered config
- [ ] User-facing text is English via `t()` and `app/src/lib/i18n/en/*.json` (UI) or `kod` + `param` + English fallback (core); no new raw Hungarian UI strings
- [ ] New UI uses design tokens only and passes `app/tests/tokenek.test.ts` and `app/tests/kontraszt.test.ts`
- [ ] Data safety is unchanged: atomic writes with snapshots, trash instead of delete, undo by `git revert`, machine writes only through the machine-write service
- [ ] Measured-AI gates are not weakened

## Tests run

<!-- Commands and results, e.g. `bin/mos test test_dokumentacio` -> OK -->

## Risks and notes for the reviewer

<!-- Anything that could not be tested in CI (model, ffmpeg, LLVM, WKWebView) and how you checked it. -->
