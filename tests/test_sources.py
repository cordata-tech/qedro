"""Reading events, including the parts that go wrong.

Both sources are here rather than in two files, because the property worth
protecting is that they agree. A directory and a Marquez-compatible API have to
produce the same events and the same report shape, or every projection above
them has two behaviours.

The report matters as much as the events. A projection built from 900 of
1,000 events is not wrong, but it cannot claim to be complete, and that
distinction is the whole design of `qedro.mark`.
"""

import json
import socket
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from qedro.errors import ConfigError
from qedro.sources import lineage_url, read, read_api, read_dir

from .lineage_api import Backend, event

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
        assert len(report.unreadable) == 1
        assert not report.clean

    def test_a_missing_directory_reports_rather_than_raises(self, tmp_path):
        events, report = read_dir(tmp_path / "nope")
        assert events == []
        assert not report.clean
        assert "does not exist" in report.unreadable[0]

    def test_reasons_are_phrased_for_a_summary_line(self, tmp_path):
        (tmp_path / "a.ndjson").write_text('{"nope": 1}\n{"also": 2}\n')
        _, report = read_dir(tmp_path)
        assert report.reasons() == ["2 records were not usable OpenLineage events"]

    def test_a_clean_read_has_nothing_to_report(self):
        _, report = read_dir(FIXTURES)
        assert report.reasons() == []


# --------------------------------------------------------------------------
# A Marquez-compatible API
# --------------------------------------------------------------------------


class TestTheAddress:
    """People paste whatever their browser had. All of it has to work."""

    @pytest.mark.parametrize(
        "base",
        [
            "https://marquez.internal",
            "https://marquez.internal/",
            "https://marquez.internal/api/v1",
            "https://marquez.internal/api/v1/events/lineage",
        ],
    )
    def test_every_spelling_of_the_same_host_resolves_alike(self, base):
        url = urlsplit(lineage_url(base, limit=10, offset=0))
        assert url.path == "/api/v1/events/lineage"
        assert url.netloc == "marquez.internal"

    def test_a_host_on_a_path_prefix_is_kept(self):
        # Marquez behind a reverse proxy at /lineage is common enough.
        url = urlsplit(lineage_url("https://internal/lineage", limit=10, offset=0))
        assert url.path == "/lineage/api/v1/events/lineage"

    def test_the_window_is_passed_as_marquez_spells_it(self):
        url = lineage_url(
            "https://m",
            limit=5,
            offset=10,
            since=datetime(2026, 1, 1, tzinfo=UTC),
            until=datetime(2026, 2, 1, tzinfo=UTC),
        )
        query = parse_qs(urlsplit(url).query)
        assert query["after"] == ["2026-01-01T00:00:00+00:00"]
        assert query["before"] == ["2026-02-01T00:00:00+00:00"]
        assert query["limit"] == ["5"] and query["offset"] == ["10"]

    def test_a_naive_bound_is_sent_as_utc(self):
        # Naive on purpose: `--since 2026-01-01` is what people type, and the
        # client has to decide what it means rather than refuse to compare.
        url = lineage_url("https://m", limit=1, offset=0, since=datetime(2026, 1, 1))  # noqa: DTZ001
        assert parse_qs(urlsplit(url).query)["after"] == ["2026-01-01T00:00:00+00:00"]

    def test_only_http_addresses_are_read(self):
        # `file://` through urlopen would read local paths.
        with pytest.raises(ConfigError, match="only http"):
            lineage_url("file:///etc/passwd", limit=1, offset=0)

    def test_an_address_with_no_host_is_refused(self):
        with pytest.raises(ConfigError, match="no host"):
            lineage_url("https://", limit=1, offset=0)


class TestReadingTheApi:
    def test_reads_a_page(self, serve):
        base = serve(Backend(events=[event(f"j{i}") for i in range(3)]))
        events, report = read_api(base)
        assert report.events == 3 and report.pages == 1
        assert report.clean
        assert {e.job.name for e in events} == {"j0", "j1", "j2"}

    def test_pages_until_the_backend_runs_out(self, serve):
        backend = Backend(events=[event(f"j{i}") for i in range(5)])
        base = serve(backend)
        _, report = read_api(base, page_size=2)
        assert report.events == 5
        assert report.pages == 3  # 2, 2, then a short page that ends it
        assert [q["offset"] for _, _, q in backend.requests] == [["0"], ["2"], ["4"]]

    def test_a_bare_array_is_accepted_as_well_as_an_envelope(self, serve):
        base = serve(Backend(events=[event()], envelope=False))
        _, report = read_api(base)
        assert report.events == 1 and report.clean

    def test_the_client_never_issues_anything_but_get(self, serve):
        backend = Backend(events=[event()])
        read_api(serve(backend))
        assert backend.methods == {"GET"}

    def test_the_origin_is_recorded_for_the_summary_line(self, serve):
        base = serve(Backend(events=[event()]))
        _, report = read_api(base)
        assert report.origin == base


class TestTheWindowSurvivesABackendThatIgnoresIt:
    """The stand-in ignores `after` and `before`, exactly as a backend may."""

    def test_events_outside_the_window_are_dropped_client_side(self, serve):
        base = serve(
            Backend(
                events=[
                    event("old", "2025-01-01T00:00:00Z"),
                    event("new", "2026-08-21T10:00:00Z"),
                ]
            )
        )
        events, report = read_api(base, since=datetime(2026, 1, 1, tzinfo=UTC))
        assert [e.job.name for e in events] == ["new"]
        assert report.events == 1

    def test_an_event_with_no_usable_timestamp_is_not_placed_in_a_window(self, serve):
        base = serve(Backend(events=[event("undated", "not a timestamp")]))
        events, _ = read_api(base, since=datetime(2026, 1, 1, tzinfo=UTC))
        assert events == []

    def test_and_is_kept_when_no_window_was_asked_for(self, serve):
        base = serve(Backend(events=[event("undated", "not a timestamp")]))
        events, _ = read_api(base)
        assert len(events) == 1


class TestWhatTheApiReportIsFor:
    def test_a_bad_record_in_a_page_is_counted_not_fatal(self, serve):
        base = serve(Backend(events=[event(), {"hello": "world"}, event("j2")]))
        _, report = read_api(base)
        assert report.events == 2 and report.skipped_records == 1
        assert not report.clean

    def test_an_http_error_is_reported_rather_than_raised(self, serve):
        base = serve(Backend(status=503))
        events, report = read_api(base)
        assert events == []
        assert "HTTP 503" in report.unreadable[0]
        assert not report.clean

    def test_a_body_that_is_not_json_is_reported(self, serve):
        base = serve(Backend(body="<html>proxy error</html>"))
        _, report = read_api(base)
        assert "not JSON" in report.unreadable[0]

    def test_a_json_body_with_no_events_is_reported(self, serve):
        base = serve(Backend(body=json.dumps({"totalCount": 0})))
        _, report = read_api(base)
        assert "no events" in report.unreadable[0]

    def test_an_unreachable_host_is_reported(self):
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        events, report = read_api(f"http://127.0.0.1:{port}", timeout=2)
        assert events == []
        assert report.unreadable and not report.clean


class TestTruncation:
    """A prefix of the history is worth projecting from. Claiming it is the
    whole history is not, so the budget has to be visible in the report."""

    def test_stopping_early_is_reported(self, serve):
        base = serve(Backend(events=[event(f"j{i}") for i in range(5)]))
        _, report = read_api(base, page_size=2, max_events=4)
        assert report.events == 4
        assert report.truncated and not report.clean

    def test_a_budget_that_happens_to_match_the_history_is_not_truncation(self, serve):
        # Withholding the mark here would be a false negative, and a mark that
        # is wrong in either direction stops meaning anything.
        base = serve(Backend(events=[event(f"j{i}") for i in range(4)]))
        _, report = read_api(base, page_size=2, max_events=4)
        assert report.events == 4
        assert not report.truncated and report.clean

    def test_truncation_stands_when_it_cannot_be_disproved(self, serve):
        # The probe that would settle it failed. Not being able to show the
        # history ended is not the same as showing that it did.
        backend = Backend(events=[event(f"j{i}") for i in range(4)])
        base = serve(backend)

        original = backend.events

        class Failing(list):
            def __getitem__(self, item):
                if isinstance(item, slice) and item.start >= 4:
                    raise RuntimeError("backend fell over")
                return original[item]

        backend.events = Failing(original)
        _, report = read_api(base, page_size=2, max_events=4)
        assert report.truncated

    def test_the_reason_reaches_the_summary_line(self, serve):
        base = serve(Backend(events=[event(f"j{i}") for i in range(5)]))
        _, report = read_api(base, page_size=2, max_events=4)
        assert any("not fully covered" in r for r in report.reasons())


class TestOneEntryPoint:
    """`read` is what every projection above this line calls."""

    def test_a_url_goes_to_the_api(self, serve):
        base = serve(Backend(events=[event()]))
        _, report = read(base)
        assert report.pages == 1 and report.files == 0

    def test_a_path_goes_to_the_directory_reader(self):
        _, report = read(str(FIXTURES))
        assert report.files == 1 and report.pages == 0

    def test_a_window_applies_to_a_directory_too(self, tmp_path):
        (tmp_path / "a.ndjson").write_text(
            "\n".join(
                json.dumps(e)
                for e in (
                    event("old", "2025-01-01T00:00:00Z"),
                    event("new", "2026-08-21T10:00:00Z"),
                )
            )
        )
        events, report = read(str(tmp_path), since=datetime(2026, 1, 1, tzinfo=UTC))
        assert [e.job.name for e in events] == ["new"]
        assert report.events == 1

    def test_a_path_that_looks_like_a_scheme_is_still_a_path(self, tmp_path):
        # Only http:// and https:// dispatch to the API. A directory called
        # `s3:` is a directory.
        odd = tmp_path / "s3:"
        odd.mkdir()
        (odd / "a.ndjson").write_text(json.dumps(event()))
        _, report = read(str(odd))
        assert report.files == 1


class TestPointingAtAFile:
    """Found against a real dbt export, which is one `.jsonl` file.

    `rglob` on a file yields nothing, so this reported a clean zero and exited
    0 — with a reason that blamed the estate for having emitted nothing. A
    wrong reason is worse than no reason: it sends the reader to look in the
    wrong place, and it is the exact failure this tool exists to prevent,
    committed by the tool.
    """

    def test_a_single_file_is_read(self, tmp_path):
        events = tmp_path / "events.jsonl"
        events.write_text(
            json.dumps(
                {
                    "eventType": "COMPLETE",
                    "eventTime": "2026-03-01T10:00:00Z",
                    "run": {"runId": "r"},
                    "job": {"namespace": "n", "name": "j"},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        found, report = read_dir(events)
        assert len(found) == 1
        assert report.files == 1
        assert report.clean

    def test_the_same_file_read_via_its_directory_agrees(self, tmp_path):
        events = tmp_path / "events.ndjson"
        events.write_text(
            json.dumps(
                {
                    "eventType": "COMPLETE",
                    "eventTime": "2026-03-01T10:00:00Z",
                    "run": {"runId": "r"},
                    "job": {"namespace": "n", "name": "j"},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        direct, _ = read_dir(events)
        via_dir, _ = read_dir(tmp_path)
        assert [e.job.key for e in direct] == [e.job.key for e in via_dir]

    def test_a_file_it_cannot_read_says_so_rather_than_returning_nothing(self, tmp_path):
        other = tmp_path / "README.md"
        other.write_text("not lineage", encoding="utf-8")
        found, report = read_dir(other)
        assert found == []
        assert not report.clean
        assert any("not one of" in r for r in report.reasons())

    def test_the_reasons_read_as_sentences(self, tmp_path):
        # `reasons()` renders these as "could not read {entry}", so an entry
        # names a thing and parenthesises its reason. Both of these used to
        # produce "could not read /x does not exist".
        _, missing = read_dir(tmp_path / "nope")
        assert "could not read" in missing.reasons()[0]
        assert "(does not exist)" in missing.reasons()[0]
