# F11 — Daily editing and navigation implementation

Status: in progress, first implementation checkpoint (2026-10-16). F5 is closed; no later phase is being started here.

The product objective is an easy, dependable editor that can compete with Obsidian while retaining Manifold's existing tools and AI gates. The original v2 checkout and the real vault remain read-only. All verification uses synthetic data. The source audits are evidence and implementation proposals; product constraints in CLAUDE.md and the user's request remain authoritative.

## First checkpoint

- Line transformations are shared between Source and Live Preview, keep multiple selections, protect non-prose syntax, and form one undo step. Cmd+Enter toggles tasks; Alt+Enter follows a link. H1–H6/text, list, task, quote and clear-format commands appear in the command palette. Source Cmd+K preserves the selection. Auto-pairs track only generated closing characters and leave code/YAML/links/comments alone; fence/display-math creation on blank lines takes priority over pairing.
- Local Markdown images use the existing embed renderer and core resolver. Markdown link targets are decoded once, after splitting the raw fragment. URI schemes never become vault API targets. Reading and both editor modes use the same core navigation and preview path; inactive LP links expose their labels. Arbitrary frontend path resolution is prohibited.
- Embedded task edits operate on the resolved target Dokumentum, validate the exact current core-provided slice and line, then use the existing atomic/CAS save path. The host note is never the implicit target. Read-only, stale and conflict states remain visible. Nested render cancellation follows the parent lifetime. CodeMirror widget resource ownership is attached to DOM lifetime, including equal-widget reuse.
- Content events refresh Reading/LP embeds independently of structural link-cache invalidation. Alias lookup follows both signals. Per-target refresh optimization and canvas-card refresh are still separate checklist work.
- Cmd+N and the new-tab create action open the existing safe name workflow. The quick switcher searches aliases and can create from Enter with no result or Shift+Enter. Explicit folder paths override the configured default; errors retain the name and allow retry. The core remains the exclusive authority for valid names and collisions.
- Pins survive workspace persistence. Group close operations preserve pinned tabs unless the user explicitly closes the whole group. Directional focus uses the actual split tree. Counts are keyed by tab and path, merge overlapping selections, and use Unicode word/grapheme segmentation; publication is deferred out of the keystroke transaction.
- Rich clipboard HTML is converted locally into Markdown through an inert, bounded parser. Files keep the attachment-import path; Shift+Cmd+V keeps plain paste. No scripts or remote resources execute. Conversion preserves code whitespace and falls back to plain text when bounds are exceeded.
- `%%` comments share one opaque parser between the views. Reading hides them; LP and Source show muted source as specified by audit 01. Existing PDF-highlight marker/block operations remain covered. Arbitrary inline-open comments spanning blank paragraphs are not yet complete.

## Remaining release work

The per-gap inventory is [CHECKLIST.md](CHECKLIST.md). The first open daily-use priorities are body tags and completion/navigation, unresolved-link feedback, property-type editing, explorer sorting, and a docked persistent search view. Additional must/should work includes folding, Reading find, complete workspace layouts/navigation history, richer property/search operations, and link-format preservation through renames.

Remote images remain a visible offline placeholder. D3 permits explicit downloads, not an automatic proxy fetch or a relaxed CSP; the implementation still needs a concrete user-triggered download path with bounds and error recovery. Existing AI features remain intact, with model/calibration changes reserved for their planned phases.

PLAN §10 names fourteen audits and a ranked critical top-25. Only eight audit documents are present. That source gap is recorded in the checklist; implementation proceeds on the available concrete requirements, without claiming the missing scope was audited or the final must100%/should80% gate was reached.

## Verification

Use targeted component/CodeMirror tests during edits, then the complete frontend suite and Svelte/production build for the frozen checkpoint. Actual WebKit integration must exercise open/embed/type/save/link and exit/unmount-before-autosave using a temporary synthetic workspace. The complete Python regression suite remains required at final phase closure; a checkpoint records exactly which integration modules ran and does not inherit a prior full run as current evidence. No browser visual audit is claimed without actual visual inspection.
