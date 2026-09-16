"""Check selection boundaries and replacement of the published collection."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location(
    "build_pages", Path(__file__).resolve().parents[1] / "build-pages.py"
)
pages = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pages)


class BuildPagesTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repository = Path(self.temporary.name)
        self.write(".github/pages/index.html", "<main><!-- NOTE_LIST --></main>")

    def write(self, name, text):
        path = self.repository / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def note(self, name, **fields):
        path = self.write(name, r"\documentclass{noteformyself}")
        path.with_suffix(".pdf").write_bytes(b"%PDF-1.7\n" + name.encode())
        return {
            "id": name.removesuffix(".tex").replace("/", "-"),
            "title": f"Note from {name}",
            "tex": name,
            "url": "pdf/" + str(Path(name).with_suffix(".pdf")),
            "compile": True,
            "status": {"published": 0, "finished": 0},
            **fields,
        }

    def manifest(self, notes, **fields):
        data = {
            "schemaVersion": 1,
            "build": {"engine": "xelatex"},
            "notes": notes,
            **fields,
        }
        self.write("notes.json", json.dumps(data))
        return pages.load_manifest(self.repository)

    def select(self, notes):
        return pages.selected_notes(self.manifest(notes))

    def test_explicit_selection_preserves_order_across_layouts(self):
        old = self.note("before2026/course/lecture.tex")
        new = self.note("chapters/topic/topic.tex")
        self.note("chapters/unselected/unselected.tex")
        self.assertEqual(
            self.select([new, old]), [new, old]
        )

    def test_compile_flag_selects_notes_independently_of_status(self):
        enabled = self.note("chapter/draft.tex")
        disabled = self.note("chapter/planned.tex", compile=False)
        # A disabled entry may describe a note that has not been created yet.
        (self.repository / disabled["tex"]).unlink()
        self.assertEqual(self.select([disabled, enabled]), [enabled])

    def test_invalid_selection_fails_before_compilation(self):
        note = self.note("chapter/note.tex")
        for path in [
            "/tmp/note.tex", "../note.tex", "chapter/missing.tex",
            "chapter/note.pdf", "chapter/*.tex", "chapter/@(note).tex",
            "chapter/a note.tex", "", None, False, 42,
        ]:
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.select([{**note, "tex": path}])

    def test_duplicate_identifiers_sources_and_urls_are_rejected(self):
        first = self.note("chapter/first.tex")
        second = self.note("chapter/second.tex")
        for field in ["id", "tex", "url"]:
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "duplicate"):
                self.select([first, {**second, field: first[field]}])

    def test_invalid_record_fields_and_output_paths_are_rejected(self):
        note = self.note("chapter/note.tex")
        for fields in [
            {"compile": "false"}, {"compile": 1}, {"title": ""},
            {"status": {"published": 2, "finished": 0}},
            {"url": "../outside.pdf"}, {"url": "/outside.pdf"},
            {"url": "https://example.com/note.pdf"},
            {"url": "outside.pdf"}, {"url": "pdf/../outside.pdf"},
            {"url": "pdf/note%20name.pdf"},
        ]:
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                self.select([{**note, **fields}])

    def test_malformed_json_and_wrong_schema_are_not_an_empty_selection(self):
        for content in [
            '{"notes": [}',
            '{}',
            '[]',
            'null',
            '{"notes": null}',
            '{"notes": "chapter/note.tex"}',
        ]:
            with self.subTest(content=content):
                self.write("notes.json", content)
                with self.assertRaisesRegex(ValueError, "notes.json"):
                    pages.load_manifest(self.repository)
        for fields in [{"schemaVersion": 3}, {"build": {"engine": "pdflatex"}}]:
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                self.manifest([], **fields)
        for entry in [None, "chapter/note.tex", {}, False, 42]:
            with self.subTest(entry=entry), self.assertRaises(ValueError):
                self.select([entry])

    def test_source_symlinks_cannot_leave_repository(self):
        note = self.note("linked.tex")
        (self.repository / "linked.tex").unlink()
        (self.repository / "linked.tex").symlink_to(
            self.repository.parent / "outside.tex"
        )
        with self.assertRaisesRegex(ValueError, "outside the repository"):
            self.select([note])

    def test_only_selected_pdfs_are_staged_without_filename_collisions(self):
        first = self.note("chapters/a&b/note.tex", title="A & B <comparison>")
        second = self.note("2026spring/course/note.tex")
        disabled = self.note("before2026/unselected.tex", compile=False)
        self.write("_site/pdf/removed.pdf", "old deployment")
        pages.assemble_site(self.repository, self.manifest([first, disabled, second]))
        site = self.repository / "_site"
        self.assertEqual(
            {path.relative_to(site) for path in site.rglob("*.pdf")},
            {Path(first["url"]), Path(second["url"])},
        )
        index = (site / "index.html").read_text()
        self.assertIn('href="pdf/chapters/a%26b/note.pdf"', index)
        self.assertIn("A &amp; B &lt;comparison&gt;", index)
        self.assertIn("Unpublished", index)
        self.assertIn("Draft", index)
        self.assertLess(index.index("a%26b"), index.index("2026spring"))
        self.assertTrue((site / ".nojekyll").is_file())
        self.assertEqual(json.loads((site / "notes.json").read_text())["notes"], [first, second])
        self.assertIn("builtAt", json.loads((site / "build.json").read_text()))

    def test_explicit_pdf_url_survives_moving_a_source(self):
        note = self.note("old/note.tex", url="pdf/stable-note.pdf")
        pages.assemble_site(self.repository, self.manifest([note]))
        moved = self.note("new/location/note.tex", id=note["id"], url=note["url"])
        (self.repository / note["tex"]).unlink()
        pages.assemble_site(self.repository, self.manifest([moved]))
        site = self.repository / "_site"
        self.assertEqual(list(site.rglob("*.pdf")), [site / "pdf/stable-note.pdf"])
        self.assertEqual(
            (site / "pdf/stable-note.pdf").read_bytes(),
            (self.repository / moved["tex"]).with_suffix(".pdf").read_bytes(),
        )

    def test_empty_list_removes_previously_selected_pdfs(self):
        self.write("_site/pdf/removed.pdf", "old deployment")
        pages.assemble_site(self.repository, self.manifest([]))
        site = self.repository / "_site"
        self.assertEqual(list(site.rglob("*.pdf")), [])
        self.assertIn("No notes have been published", (site / "index.html").read_text())

    def test_missing_or_invalid_pdf_does_not_stage_a_partial_site(self):
        first = self.note("chapter/first.tex")
        second = self.note("chapter/second.tex")
        previous = self.write("_site/index.html", "previous site")
        manifest = self.manifest([first, second])
        pdf = (self.repository / second["tex"]).with_suffix(".pdf")
        pdf.unlink()
        with self.assertRaises(FileNotFoundError):
            pages.assemble_site(self.repository, manifest)
        self.assertEqual(previous.read_text(), "previous site")
        pdf.write_text("not a PDF")
        with self.assertRaisesRegex(ValueError, "Not a compiled PDF"):
            pages.assemble_site(self.repository, manifest)
        self.assertEqual(previous.read_text(), "previous site")


if __name__ == "__main__":
    unittest.main()
