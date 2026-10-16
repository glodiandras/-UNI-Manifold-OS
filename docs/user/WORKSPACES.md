# Workspaces

A workspace is a folder of Markdown files that Manifold has been set up to work with. Your notes stay ordinary files: other apps can open the same folder at any time.

## Create a workspace

Choose **Create workspace…** in the workspace window and name the new folder. Manifold first checks the location and shows what it will do. Typically it will:

- create the folder you named,
- create a hidden `.manifold` folder for Manifold's own settings, local history and indexes,
- create an empty `.obsidian` folder if there is none, so the folder stays compatible with Obsidian,
- take a first local snapshot. Existing notes are not rewritten.

Nothing is created until you confirm.

## Open an existing folder

Choose **Open folder…** and pick the folder that holds your notes. The same preview appears. Existing Markdown files and Obsidian settings are preserved. The details are in [Import & migration](IMPORT-AND-MIGRATION.md).

## Where a workspace can live

Manifold refuses or warns about a few locations so your notes stay safe:

- **Inside the application or its data folder**: choose a separate notes folder.
- **Inside another workspace, or a folder that contains one**: open the other workspace directly instead.
- **Network folders**: they cannot provide reliable locks. Choose a folder on a local disk.
- **Disks that are not APFS**: editing works, but the safe trial copies used by AI features are unavailable (see [AI & models](AI-AND-MODELS.md)).
- **Synced folders**: notes and settings sync, while local history and indexes stay on this Mac.
- **Little free space**: below 1 GB free you get a warning before importing a large folder.
- **Very large folders**: the first snapshot can take a while. Your notes are preserved.

A workspace can be open in one Manifold window at a time. If you try to open it twice, Manifold tells you it is already open.

## Switch between workspaces

Use **Switch workspace** from the command palette, or **Open workspace…** from the File menu. Manifold saves your open notes first. If a task is still running it waits for the task to finish and then switches.

**Settings › General › On startup** decides whether Manifold opens the last workspace or shows the workspace picker.

## The recent list

The workspace window lists recent workspaces. A workspace on a disk that is not connected is marked as unavailable: connect the disk or choose another folder. **Remove from list** only forgets the entry. It never deletes files.

## What Manifold adds to a workspace

| Item | Purpose |
|---|---|
| `.manifold/workspace.toml` | Settings for this workspace |
| `.manifold` (the rest) | Local history and the search index, kept apart from your notes |
| `.obsidian` | Kept as it is; created empty only if missing |

Deleting the `.manifold` folder removes Manifold's data for that workspace. Your notes are untouched. See [Privacy & data](PRIVACY-AND-DATA.md) for the full list of what is stored where.

## Settings per workspace

Settings are saved per workspace, so two workspaces can have different folders for new notes, different modules and different layouts. See [Settings & modules](SETTINGS-AND-MODULES.md).

## If a workspace will not open

- *The workspace folder is not available*: reconnect the drive that holds it, or reopen the workspace from the launcher. Do not move the folder while Manifold is running.
- *This workspace needs a newer version of Manifold*: it was created or upgraded by a newer version. Update the app.
- *This workspace is in use by another Manifold window*: close the other window first.

More help is in [Health & troubleshooting](HEALTH-AND-TROUBLESHOOTING.md).
