# Notes by Times

Mathematical notes by Tianle Yang, organized by topic and time. Notes live in
`chapters/`, `2026spring/`, and `before2026/`; they do not form a single book.
The shared LaTeX class and notation are in the [`accessories/`](accessories/README.md)
submodule.

## Select notes for GitHub Pages

Edit [`notes.json`](notes.json). It follows the sibling `aaa-dynamics`
manifest's document fields and build settings. Here, a flat `notes` array
describes independent entry points across all folders:

```json
{
  "schemaVersion": 1,
  "build": {
    "engine": "xelatex"
  },
  "notes": [
    {
      "id": "dynamics-on-projective-spaces",
      "title": "Dynamics on Projective Spaces",
      "tex": "chapters/dynamics-on-projective-spaces/dynamics-on-projective-spaces.tex",
      "url": "pdf/chapters/dynamics-on-projective-spaces/dynamics-on-projective-spaces.pdf",
      "compile": true,
      "status": {
        "published": 0,
        "finished": 0
      }
    }
  ]
}
```

Every entry has these fields:

| Field | Meaning |
| --- | --- |
| `id` | Unique, stable identifier for the note |
| `title` | Human-readable title shown on the website |
| `tex` | Repository-relative path to its `.tex` wrapper |
| `url` | Site-relative PDF URL, starting with `pdf/` |
| `compile` | `true` to compile and include this note on Pages; `false` to leave it out |
| `status.published` | `0` or `1`, matching the sibling repository's publication metadata |
| `status.finished` | `0` or `1`, displayed as Draft or Finished |

Only entries with `compile: true` are compiled, listed on the website, and
included in its public manifest. Set `compile: false` to keep a note's record
without building it. Disabled notes may refer to sources you have not created
yet. Publication and completion flags describe the content; they do not select
notes for compilation or change LaTeX's `status` setting or watermark.

Use valid JSON, without comments or trailing commas. `schemaVersion: 1`
identifies this repository's independent-note format, and `build.engine` is
`xelatex`, as required by `noteformyself`. IDs, source paths, and PDF URLs must
be unique. Paths must be plain relative paths without whitespace, shell
patterns, percent encoding, query strings, or fragments. Choose wrappers that
contain `\documentclass`, rather than content fragments such as `text.tex`.

A chapter wrapper produces one combined PDF containing whatever it includes.
To publish individual sections as well, add their wrappers separately. The
order of the list is also the order on the website. For direct cross-document
references that load generated `.aux` files, list the referenced document before
its consumer.

The [workflow](.github/workflows/pages.yml) follows the sibling's stages:
validate and select documents, compile with XeLaTeX, assemble the Pages site,
upload the artifact, and deploy. It rebuilds all notes with `compile: true`
on every push to `main`. This also picks up changes to included content,
bibliographies, images, fonts, and the shared template. To run it manually,
open **Actions → Build and publish selected notes → Run workflow** and choose
`main`. Manual runs on other branches build an artifact but do not deploy.

## Published PDF links

The site has a PDF index using the titles and statuses from `notes.json`.
Each selected note's `url` determines its destination under the Pages base URL.
Mirroring the source path is a useful convention, for example:

```text
Source: chapters/dynamics-on-projective-spaces/dynamics-on-projective-spaces.tex
PDF:    <Pages URL>/pdf/chapters/dynamics-on-projective-spaces/dynamics-on-projective-spaces.pdf
```

Links remain the same across builds while `url` stays the same. When moving or
renaming a wrapper, update `tex` and keep `url` to preserve existing links.
Notes can share a source filename as long as their source paths and URLs are
different.

Like the sibling site, Pages serves `notes.json` alongside the PDFs so a
personal website can read their titles, statuses, and URLs. The deployed copy
contains only enabled notes. `build.json` records the build's commit and UTC
timestamp; local previews have a null commit when `GITHUB_SHA` is unset.

Each successful deployment contains exactly the selected PDFs. Removing an
entry or setting `compile: false` removes that PDF from the next deployment.
An empty `notes` array, or disabling every entry, publishes an empty index.
A failed compilation leaves the previously deployed site in place.
Generated PDFs and `_site/` are build outputs and do not need to be committed.

## Enable publishing

In the repository's **Settings → Pages → Build and deployment**, set **Source**
to **GitHub Actions**, as described in the
[GitHub Pages documentation](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site).
Push the workflow and build list to `main`, or run the workflow manually after
they are present on `main`. The deployment exposes the actual site URL in the
workflow run.

The workflow checks out the recorded `accessories` submodule commit. When
changing the template, commit and push those changes in the accessories
repository first, then commit its updated submodule reference here. Uncommitted
local template changes are not available to GitHub Actions.

## Compile locally

Initialize the shared infrastructure after cloning:

```sh
git submodule update --init --recursive
```

Use XeLaTeX, `latexmk`, and Biber with a recent TeX Live installation. From the
repository root, compile the selected chapter using the checked-out class:

```sh
export TEXINPUTS="$PWD/accessories/templates-of-latex/noteformyself//:${TEXINPUTS:-}"
cd chapters/dynamics-on-projective-spaces
latexmk -xelatex -file-line-error -halt-on-error -interaction=nonstopmode dynamics-on-projective-spaces.tex
```

The trailing default search path in `TEXINPUTS` keeps TeX's standard packages
available. Compile each entry point from its own directory so relative inputs
and bibliography paths resolve correctly. The GitHub workflow uses TeX Live
2026, installs the shared class and bundled LXGW WenKai font, and runs
`latexmk` with XeLaTeX; `latexmk` invokes Biber and repeats passes as needed.

Validate the manifest and print enabled source paths from the repository root:

```sh
python3 .github/build-pages.py roots
```

This helper validates this repository's format; the shared `manage-notes`
validator expects the sibling repositories' book/chapter/section manifest.

After compiling every selected document, preview the site locally:

```sh
python3 .github/build-pages.py site
python3 -m http.server --directory _site 8000
```

Open `http://localhost:8000`. Older notes may need missing bibliography files
or locally installed fonts supplied before they can build in GitHub Actions.
See the [template README](accessories/README.md) for the class interface.
