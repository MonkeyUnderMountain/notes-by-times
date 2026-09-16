#!/usr/bin/env python3
"""Validate notes.json, select enabled notes, and assemble their Pages site."""

import argparse
from datetime import datetime, timezone
import html
import json
import os
from pathlib import Path
import shutil
import sys
from urllib.parse import quote


REPOSITORY = Path(__file__).resolve().parent.parent
MANIFEST = "notes.json"


def relative_path(value, suffix, location):
    if not isinstance(value, str) or not value:
        raise ValueError(f"{location}: expected a nonempty {suffix} path string")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or path.suffix != suffix:
        raise ValueError(f"{location}: expected a relative {suffix} path: {value}")
    # latex-action expands source paths as shell patterns. URLs must also stay
    # unescaped relative paths, without query strings or fragments.
    if any(c.isspace() or c in "*?[]()\\#%:" for c in value):
        raise ValueError(f"{location}: use a plain relative path without spaces or patterns")
    if path.name.startswith("-"):
        raise ValueError(f"{location}: the filename must not start with '-'")
    return path


def load_manifest(repository):
    try:
        manifest = json.loads((repository / MANIFEST).read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(
            f"{MANIFEST}:{error.lineno}:{error.colno}: invalid JSON: {error.msg}"
        ) from error
    if not isinstance(manifest, dict) or not isinstance(manifest.get("notes"), list):
        raise ValueError(f"{MANIFEST}: expected an object with a 'notes' array")
    if type(manifest.get("schemaVersion")) is not int or manifest["schemaVersion"] != 1:
        raise ValueError(f"{MANIFEST}: schemaVersion must be 1")
    build = manifest.get("build")
    if not isinstance(build, dict) or build.get("engine") != "xelatex":
        raise ValueError(f"{MANIFEST}: build.engine must be 'xelatex' for noteformyself")
    seen = {field: set() for field in ("id", "tex", "url")}
    for index, note in enumerate(manifest["notes"]):
        location = f"{MANIFEST}:notes[{index}]"
        if not isinstance(note, dict):
            raise ValueError(f"{location}: expected a note object")
        for field in ("id", "title"):
            value = note.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{location}.{field}: expected a nonempty string")
        if type(note.get("compile")) is not bool:
            raise ValueError(f"{location}.compile: expected true or false")
        status = note.get("status")
        if not isinstance(status, dict) or any(
            type(status.get(field)) is not int or status[field] not in (0, 1)
            for field in ("published", "finished")
        ):
            raise ValueError(f"{location}.status: published and finished must each be 0 or 1")
        tex = relative_path(note.get("tex"), ".tex", f"{location}.tex")
        url = relative_path(note.get("url"), ".pdf", f"{location}.url")
        if url.parts[0] != "pdf":
            raise ValueError(f"{location}.url: PDF URLs must start with 'pdf/'")
        note["tex"], note["url"] = tex.as_posix(), url.as_posix()
        for field in seen:
            value = note[field]
            if value in seen[field]:
                raise ValueError(f"{location}.{field}: duplicate value: {value}")
            seen[field].add(value)
        source = repository / tex
        if not source.resolve().is_relative_to(repository.resolve()):
            raise ValueError(f"{location}: path resolves outside the repository")
        if note["compile"] and not source.is_file():
            raise ValueError(f"{location}.tex: file does not exist: {tex}")
    return manifest


def selected_notes(manifest):
    return [note for note in manifest["notes"] if note["compile"]]


def write_roots(manifest):
    notes = selected_notes(manifest)
    roots = "\n".join(note["tex"] for note in notes)
    if roots:
        print(roots)
    if output := os.environ.get("GITHUB_OUTPUT"):
        with open(output, "a", encoding="utf-8") as stream:
            stream.write(f"compile_required={str(bool(notes)).lower()}\n")
            stream.write(f"engine={manifest['build']['engine']}\n")
            stream.write(f"root_files<<__NOTE_ROOTS__\n{roots}\n__NOTE_ROOTS__\n")
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write("Selected notes:\n\n" if notes else "No notes selected.\n")
            for note in notes:
                stream.write(f"- `{note['tex']}` → `{note['url']}`\n")


def assemble_site(repository, manifest):
    notes = selected_notes(manifest)
    # Check every expected output before staging. An incomplete build must not
    # replace the previously deployed site with a partial collection.
    for note in notes:
        pdf = (repository / note["tex"]).with_suffix(".pdf")
        if not pdf.resolve().is_relative_to(repository.resolve()):
            raise ValueError(f"PDF resolves outside the repository: {pdf}")
        with pdf.open("rb") as stream:
            if stream.read(5) != b"%PDF-":
                raise ValueError(f"Not a compiled PDF: {pdf}")

    template = (repository / ".github/pages/index.html").read_text(encoding="utf-8")
    site = repository / "_site"
    if site.exists():
        shutil.rmtree(site)
    site.mkdir()
    items = []
    for note in notes:
        pdf = Path(note["tex"]).with_suffix(".pdf")
        route = Path(note["url"])
        destination = site / route
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repository / pdf, destination)
        publication = "Published" if note["status"]["published"] else "Unpublished"
        completion = "Finished" if note["status"]["finished"] else "Draft"
        items.append(
            f'<li><a href="{quote(route.as_posix())}">'
            f'{html.escape(note["title"])}<span class="format">PDF</span></a>'
            f'<div class="statuses"><span class="status">{publication}</span>'
            f'<span class="status">{completion}</span></div></li>'
        )
    content = (
        '<ul class="notes">\n' + "\n".join(items) + "\n</ul>"
        if items else '<p class="empty">No notes have been published yet.</p>'
    )
    (site / "index.html").write_text(
        template.replace("<!-- NOTE_LIST -->", content), encoding="utf-8"
    )
    (site / ".nojekyll").touch()
    # Expose the same per-document metadata as the sibling sites, limited to
    # the entries whose PDFs are included in this deployment.
    (site / MANIFEST).write_text(
        json.dumps({**manifest, "notes": notes}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (site / "build.json").write_text(
        json.dumps({
            "commit": os.environ.get("GITHUB_SHA"),
            "builtAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Staged {len(notes)} PDF(s) in {site}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("roots", "site"))
    args = parser.parse_args()
    try:
        manifest = load_manifest(REPOSITORY)
        if args.command == "roots":
            write_roots(manifest)
        else:
            assemble_site(REPOSITORY, manifest)
    except (OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
