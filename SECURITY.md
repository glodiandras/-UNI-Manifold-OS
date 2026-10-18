# Security policy

## Reporting a vulnerability

Please report security problems privately, not in a public issue or pull request.

Contact: `<security contact>`

Include what you found, how to reproduce it (a minimal synthetic workspace is ideal), the version or commit, and your macOS version. Please do not include private notes or real personal data in a report.

You can expect an acknowledgement of your report; a fix and a public note follow once the problem is understood and resolved. This project has no bug bounty.

## Supported versions

Manifold is pre-release. Only the latest commit on the default branch is supported; there are no maintained older releases yet.

## What is in scope

Manifold is a local application. Reports are most valuable when they concern:

- escaping the code sandbox, or a model/pipeline writing outside the paths the machine-write service allows;
- reading or writing outside the workspace (path traversal, symlinks), or the local API accepting requests it should reject;
- unintended network access at runtime (the product makes network requests only for explicit downloads);
- loss or silent corruption of notes, snapshots or backups;
- secrets or personal data shipped in the repository or in the app bundle.

## Design notes relevant to security

- No account and no cloud service: notes stay as Markdown files in a folder the user owns.
- Network is used only for explicit downloads (models, media, runtime), which are hash-pinned where a pin exists.
- Automated writes are snapshotted and undoable; deletes go to the trash.
