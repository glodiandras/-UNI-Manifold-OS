# Synthetic data generator (developer tool)

`tools/gen_szintetikus.py` makes **synthetic, neutral** candidate data for this repository with your own Anthropic Console API key.
It is a developer tool: it is not part of the product, it is not packaged (`tools/` is outside the packaged tree and marked
`export-ignore`), and nothing it writes is used by Manifold until you adopt it explicitly.

## What it makes

| Template (`tools/gen_sablonok/`) | Output | Default |
|---|---|---|
| `kiegeszites` | text-continuation items (`elotte`, `utana`, `elfogadhato`) | yes |
| `matek` | school maths problems with a machine-checkable answer | yes |
| `kod` | complete C++ debugging tasks (statement, reference, brute force, input generator, three planted bugs) | yes |
| `demo_jegyzetek` | extra demo-workspace notes in the style of `core/demo_tartalom.py` | yes |
| `doku_atnezes` | review remarks on `docs/user/*.md` (a suggestions report only, nothing is modified) | no: `--sablon doku_atnezes` |

All output is English. The shipped sets are marked `nyelv = "hu"`, so candidates never go into `arany.json`: they form a separate
English **draft** set `arany_en.json` next to it (`modulok/eval/{kiegeszites,matek,kod}/`, demo notes in `core/demo_kiegeszito.json`).

## Steps

1. **Put the key in the Keychain** (prompted, so it is not in your shell history):
   `security add-generic-password -s manifold-anthropic -a "$USER" -w`
   Alternative, only with the explicit `--kulcs-env` switch: the `ANTHROPIC_API_KEY` environment variable.
2. **Check the prices**: open `tools/gen_arak.toml` and compare it with the price list in your Console. The values are
   conservative upper estimates, but you own them: raise them if the Console says more.
3. **Dry run** (no network, no key read): `python3 tools/gen_szintetikus.py --szaraz` prints the number of calls and the
   worst-case cost.
4. **Run**: `python3 tools/gen_szintetikus.py [--sablon NAME ...] [--max-usd 2] [--max-hivas 30]`.
   Results land in `var/staging/szintetikus/<run-id>/` (gitignored): `tetelek.jsonl` (kept items), `elutasitott.jsonl` (rejected,
   with the reason), `jovahagyas.toml` (review list), `manifest.json`, `koltseg.json`.
5. **Review** `tetelek.jsonl`. In `jovahagyas.toml` set `jovahagyva = true` for every item you accept. Check maths answers by
   hand (they are not independently verified) and run `modulok/eval/kod/keszit.py` in the sandbox for code tasks.
6. **Adopt** (no network): `python3 tools/gen_szintetikus.py --atvesz <run-id> --cel kiegeszites` (add `--szaraz` for a
   preview, `--mind-jovahagy` to take everything kept). Review the diff and commit yourself.

## Cost limits

- `--max-usd` (default 5.00) and `--max-hivas` (default 60) bound one run; `--osszes-max-usd` (default 20.00) bounds all runs
  together (`var/staging/szintetikus/osszes_koltseg.json`).
- Before every call the worst case (generous input estimate + `max_tokens` at the output price) must fit what is left; the run
  stops otherwise. The real cost comes from the response `usage`, and both cost files are rewritten after every call. A call
  that was in flight when the process died stays reserved in them.
- A damaged cost file stops the tool; it never resets a budget by itself.

## What it does not do

- It never reads a vault or workspace and sends no user data; only the checked-in templates (and, for `doku_atnezes`, the
  repository's own user-guide pages) are sent.
- It never prints, logs, stores or passes the key in argv, and uses no SDK: one fixed HTTPS endpoint, standard library only.
- It does not modify `arany.json`, `csomag.toml`, any approval state (`allapot` stays `vazlat`) or `docs/`.
- It does not verify generated answers or code; it checks structure, safety patterns, duplicates, secrets / personal data,
  size and language only.
- It does not commit and does not write to `docs/plan/NAPLO.md`.
