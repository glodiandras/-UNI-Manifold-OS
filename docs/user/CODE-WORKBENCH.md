# Code workbench

The code workbench lets you write a solution to a programming exercise inside your notes and check it against tests, all in a sandbox on your Mac. Turn it on or off in **Settings › Modules › Code workbench**.

## Languages

| Language | Toolchain |
|---|---|
| C and C++ | A compiler toolchain that Manifold downloads when you ask for it |
| Python, JavaScript, TypeScript | Built into Manifold. TypeScript is run directly, **without type checking** |
| Java, Go, Rust, Swift | A toolchain already installed on your Mac |

Run *Code: languages and toolchains* from the command palette to see which languages are ready and what to install for the others. If a toolchain is missing, Manifold says so and tells you what to do. Nothing is downloaded unless you choose to (see [Privacy & data](PRIVACY-AND-DATA.md)).

> [!note] Still being finished
> Support for languages other than C++ is new. The notes below apply to all supported languages unless they say otherwise, and this page will change as the workbench is finished.

## How it fits together

A **task note** is an ordinary Markdown note that holds:

- the description of the exercise,
- one or more **test blocks**,
- an embed of your solution file, such as `![[solution.cpp]]` or `![[solution.py]]`.

The solution is a normal source file in your workspace. Open it and it appears in a code tab. The embedded copy inside the task note is read-only, with a badge that shows the result of your last check.

Create a new C++ exercise with the command *New C++ task…*. It creates the task note and the solution file for you. For the other languages, create the source file next to a note of your own and embed it.

## Writing tests

A test block is a code block whose language is `teszt`. It holds the input the program receives, the output it should produce, and optionally a time limit:

````
```teszt Edge case
--- bemenet
5
1 2 3 4 5
--- kimenet
15
--- idokorlat
1.5
```
````

- The text after `teszt` on the first line is the title of the test.
- `--- bemenet` starts the input and `--- kimenet` starts the expected output. The expected output is required; leave it empty if the program should print nothing.
- `--- idokorlat` is a time limit in seconds, for example `2`, `1.5 s` or `500 ms`.
- `--- memoria` limits memory, for example `64 MB`.
- `--- osszevetes` chooses how output is compared: the default compares line by line and ignores trailing spaces and blank lines at the end. The other modes are `pontos` (exact), `tures` (compare space-separated tokens) and `lebego` (numbers within a tolerance).

The section names are written exactly like this in the file, because they are part of the file format.

## Checking a solution

| To do this | Press |
|---|---|
| Compile (when the language needs it) and run all tests | ⌘R |
| Check with a debug build that catches memory and undefined-behaviour errors (C and C++ only) | ⇧⌘R |
| Format the code (C++ only, with clang-format) | ⌥⇧F |
| Cancel a running check | *Code: cancel the running check* in the command palette |

Compile errors and warnings are shown on the line they belong to. Each test reports whether it passed, how long it took and how much memory it used. For a wrong answer you see the expected output and the actual output.

Everything runs in a sandbox: no network, strict limits on time and memory, and a private temporary folder as the only place a program can write.

## AI help

The command palette offers code help: explain an error, give a hint, write edge-case tests and run a stress test. A full solution is produced only when you explicitly ask. The suggestions are shown to you and are never written to your code automatically.

For C++ the help is available once a calibrated code model is installed. For the other languages no model has been measured yet, so help runs as a **Trial** and is always labelled as one. See [AI & models](AI-AND-MODELS.md).

## Related pages

- [Settings & modules](SETTINGS-AND-MODULES.md)
- [Notes & editing](NOTES-AND-EDITING.md)
