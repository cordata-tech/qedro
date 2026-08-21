"""Reading a directory, including the parts that go wrong.

The report matters as much as the events. A projection built from 900 of
1,000 events is not wrong, but it cannot claim to be complete, and that
distinction is the whole design of `qedro.mark`.
"""

import json
from pathlib import Path

from qedro.sources import read_dir

FIXTURES = Path(__file__).parent / "fixtures" / "events"


class TestRealLineage:
    """Against events actually emitted by cordata-tech/pipeline-runtime."""

    def test_reads_the_fixture(self):
        _, report = read_dir(FIXTURES)
        assert report.events == 4
        assert report.clean
        assert report.skipped_records == 0

    def test_the_custom_facets_survive_the_round_trip(self):
        events, _ = read_dir(FIXTURES)
        complete = [e for e in events if e.event_type == "COMPLETE"]
        processing = [e.job_facet("processing") for e in complete]
        assert {"purpose": "fraud-detection", "legal_basis": "legitimate-interest"} in processing

    def test_provenance_reaches_the_reader_intact(self):
        # The chain from a published number back to a signed commit is the
        # thing `qedro provenance` will be built on.
        events, _ = read_dir(FIXTURES)
        prov = next(p for e in events if (p := e.run_facet("cordata_provenance")))
        assert "descriptor_sha256" in prov
        assert "descriptor_git_commit_signed" in prov

    def test_schema_facets_give_column_names(self):
        events, _ = read_dir(FIXTURES)
        cols = {c for e in events for d in e.datasets for c in d.field_names()}
        assert "iban" in cols


class TestFileShapes:
    """Three shapes turn up in practice; none is worth a flag."""

    def _write(self, tmp_path, name, content):
        p = tmp_path / name
        p.write_text(content, encoding="utf-8")
        return p

    def _one(self, job="j"):
        return {
            "eventType": "COMPLETE",
            "eventTime": "2026-08-21T10:00:00Z",
            "run": {"runId": "r"},
            "job": {"namespace": "ns", "name": job},
        }

    def test_newline_delimited(self, tmp_path):
        self._write(
            tmp_path, "a.ndjson", "\n".join(json.dumps(self._one(f"j{i}")) for i in range(3))
        )
        _, report = read_dir(tmp_path)
        assert report.events == 3 and report.clean

    def test_a_json_array(self, tmp_path):
        self._write(tmp_path, "a.json", json.dumps([self._one("j1"), self._one("j2")]))
        _, report = read_dir(tmp_path)
        assert report.events == 2 and report.clean

    def test_a_single_event_object(self, tmp_path):
        self._write(tmp_path, "a.json", json.dumps(self._one()))
        _, report = read_dir(tmp_path)
        assert report.events == 1 and report.clean

    def test_blank_lines_are_not_records(self, tmp_path):
        self._write(tmp_path, "a.ndjson", json.dumps(self._one()) + "\n\n\n")
        _, report = read_dir(tmp_path)
        assert report.events == 1 and report.skipped_records == 0

    def test_an_empty_file_is_not_an_error(self, tmp_path):
        self._write(tmp_path, "a.ndjson", "")
        _, report = read_dir(tmp_path)
        assert report.events == 0 and report.clean

    def test_unrelated_suffixes_are_ignored(self, tmp_path):
        self._write(tmp_path, "notes.txt", "not lineage")
        self._write(tmp_path, "a.jsonl", json.dumps(self._one()))
        _, report = read_dir(tmp_path)
        assert report.files == 1 and report.events == 1

    def test_nested_directories_are_walked(self, tmp_path):
        (tmp_path / "2026" / "08").mkdir(parents=True)
        (tmp_path / "2026" / "08" / "a.ndjson").write_text(json.dumps(self._one()))
        _, report = read_dir(tmp_path)
        assert report.events == 1


class TestWhatTheReportIsFor:
    def test_a_bad_line_is_counted_not_fatal(self, tmp_path):
        good = json.dumps(
            {"eventType": "COMPLETE", "run": {}, "job": {"namespace": "n", "name": "j"}}
        )
        (tmp_path / "a.ndjson").write_text(f"{good}\n{{not json\n{good}\n")
        _, report = read_dir(tmp_path)
        assert report.events == 2
        assert report.skipped_records == 1
        assert not report.clean

    def test_a_record_that_is_not_an_event_is_counted(self, tmp_path):
        (tmp_path / "a.ndjson").write_text(json.dumps({"hello": "world"}))
        _, report = read_dir(tmp_path)
        assert report.events == 0 and report.skipped_records == 1

    def test_an_unreadable_file_does_not_stop_the_others(self, tmp_path):
        (tmp_path / "bad.json").write_text("{ definitely not json")
        (tmp_path / "good.ndjson").write_text(
            json.dumps({"eventType": "COMPLETE", "run": {}, "job": {"namespace": "n", "name": "j"}})
        )
        _, report = read_dir(tmp_path)
        assert report.events == 1
        assert len(report.unreadable_files) == 1
        assert not report.clean

    def test_a_missing_directory_reports_rather_than_raises(self, tmp_path):
        events, report = read_dir(tmp_path / "nope")
        assert events == []
        assert not report.clean
        assert "does not exist" in report.unreadable_files[0]

    def test_reasons_are_phrased_for_a_summary_line(self, tmp_path):
        (tmp_path / "a.ndjson").write_text('{"nope": 1}\n{"also": 2}\n')
        _, report = read_dir(tmp_path)
        assert report.reasons() == ["2 records were not usable OpenLineage events"]

    def test_a_clean_read_has_nothing_to_report(self):
        _, report = read_dir(FIXTURES)
        assert report.reasons() == []
