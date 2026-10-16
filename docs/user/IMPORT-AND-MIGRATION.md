# Import & migration

Manifold works on ordinary Markdown folders, so there is little to convert. This page explains how to bring existing notes in, what Manifold changes in a folder, and how to move away again.

## Opening an existing folder

1. In the workspace window, choose **Open folder…** and select the folder with your notes.
2. Manifold checks the folder without changing any files. If something needs attention, it says so in plain words, for example that the folder is on a network drive or inside another workspace.
3. You see a preview of what Manifold will add and confirm it.
4. Manifold takes a safety snapshot and opens the workspace.

The preview lists changes such as:

- create a hidden `.manifold` folder for settings, local history and indexes,
- create an empty `.obsidian` folder if there is none, for Markdown compatibility,
- create the initial local snapshot. **Existing notes are not rewritten.**

Your Markdown files and your Obsidian settings stay intact.

## Obsidian vaults

An Obsidian vault opens as it is, and it keeps working in Obsidian too. Both apps can use the same folder.

- Wikilinks `[[…]]`, embeds `![[…]]`, `#tags`, properties, aliases, callouts, `%%comments%%`, canvases and Bases views are understood.
- If you have not set a folder for new notes or for attachments in Manifold, it follows the vault's own Obsidian settings for them. Settings you choose in Manifold apply to Manifold only.
- Property types are saved in the vault's `.obsidian/types.json` file, the same file Obsidian uses.
- If Obsidian (or any other app) changes a file that is open in Manifold, Manifold does not overwrite that version. If you had unsaved edits, yours stay on screen, unsaved.
- Snapshots and the search index belong to Manifold and are not part of the vault. A vault in a synced folder syncs notes and settings, while history and indexes stay on this Mac.

### Import a copy of a vault

If you would rather keep the original vault untouched, import a copy of it into a **new** workspace folder instead of opening it in place. The import works in four steps:

1. **Preview.** Manifold reads the vault without changing it and shows what it found: how many notes, canvases, Bases views, attachments and other files it would copy, what it would skip, and whether anything blocks the import. Nothing is written yet.
2. **Copy.** After you confirm, Manifold copies every file unchanged into the new folder: notes, attachments, canvases, Bases views and the `.obsidian` settings. Progress is shown while it runs. It never overwrites an existing file.
3. **Set up.** The new folder becomes a workspace. Your daily-note and template settings from Obsidian are carried over to the workspace settings.
4. **Undo if you want to.** Every step is recorded in a journal. If something stops the import, running it again continues where it left off, and running it again after it finished changes nothing. **Undo** moves what the import created to the macOS Trash: files you changed after the import and files you added stay where they are.

The original vault is only read, never written. Symbolic links, special files, `.DS_Store` files, a `.git` folder and other hidden items outside `.obsidian` are skipped and reported, and so is Obsidian's own trash folder unless you choose to include it.

> [!note] Still being finished
> The import screen is being finished. The steps above describe how the import works. Until the screen is released, opening the folder in place, as described earlier on this page, is the way to bring a vault in, and it never rewrites your notes.

## Bringing in other things

- **Files**: drag files from Finder into the file tree. They are copied into the workspace.
- **Attachments**: drop or paste images and files into a note. They are saved in the attachment folder from **Settings › Files & links**.
- **Videos**: in the Manifold panel, open the **Import** section, paste video links (one per line) or drop a video file (mp4, m4v, mov, mkv, webm, avi). The download uses the network only because you asked for it.
- **Notebook photos**: use *Add notebook photos…* from the command palette to turn photos of handwritten pages into notes. This needs AI models; see [AI & models](AI-AND-MODELS.md).

## Moving or copying a workspace

Quit Manifold, or at least close the workspace, before moving the folder. Then use **Open folder…** at the new location. The workspace keeps its settings, because they are stored in its `.manifold` folder. Remove the old entry from the recent list with **Remove from list**. The search index rebuilds itself if needed.

## Newer and older versions

A workspace created or upgraded by a newer version of Manifold may refuse to open in an older one, with the message that it needs a newer version. Update the app. Your notes are not affected.

## Leaving Manifold

Your notes are plain Markdown files in your own folder. To stop using Manifold, just keep the folder. To remove everything Manifold added, delete the hidden `.manifold` folder. If the folder had no `.obsidian` before, an empty one was created for compatibility, and it is safe to delete too.

## Related pages

- [Workspaces](WORKSPACES.md)
- [Getting started](GETTING-STARTED.md)
- [Demo workspace](DEMO-WORKSPACE.md)
