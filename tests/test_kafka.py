"""Reading OpenLineage from a Kafka topic without moving anyone's offsets (#59).

Against a stand-in consumer that fails the test if anything subscribes or
commits, so the read-only rule is checked by every test here rather than by one.
A run against a real broker is in qedro-lab.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from qedro import config, ropa, vocabulary
from qedro.errors import ConfigError
from qedro.sources import kafka_settings, read, read_kafka

TOPIC = "openlineage.events"
ADDRESS = f"kafka://kafka:9092/{TOPIC}"


def ms(day: int, hour: int = 10) -> int:
    return int(datetime(2026, 11, day, hour, tzinfo=UTC).timestamp() * 1000)


def payload(job: str, day: int) -> bytes:
    when = datetime(2026, 11, day, 10, tzinfo=UTC).isoformat()
    return json.dumps(
        {
            "eventType": "COMPLETE",
            "eventTime": when,
            "run": {"runId": f"run-{job}-{day}"},
            "job": {"namespace": "acme", "name": job},
        }
    ).encode()


@dataclass
class Message:
    p: int
    o: int
    stamp: int
    body: bytes | None

    def partition(self):
        return self.p

    def offset(self):
        return self.o

    def value(self):
        return self.body

    def timestamp(self):
        return (1, self.stamp)  # TIMESTAMP_CREATE_TIME

    def error(self):
        return None


@dataclass
class Broker:
    """Partitions as lists of (timestamp ms, value); `low` is the first retained offset."""

    partitions: dict[int, list[tuple[int, bytes | None]]]
    low: dict[int, int] = field(default_factory=dict)
    queue: list[Message] = field(default_factory=list)
    assigned: list = field(default_factory=list)
    closed: bool = False

    def _offsets(self, p):
        start = self.low.get(p, 0)
        return [(start + i, stamp, body) for i, (stamp, body) in enumerate(self.partitions[p])]

    def list_topics(self, topic, timeout):
        class Topic:
            error = None
            partitions = dict.fromkeys(self.partitions)

        class Metadata:
            topics = {TOPIC: Topic()} if topic == TOPIC else {}

        return Metadata()

    def get_watermark_offsets(self, tp, timeout):
        low = self.low.get(tp.partition, 0)
        return low, low + len(self.partitions[tp.partition])

    def offsets_for_times(self, tps, timeout):
        out = []
        for tp in tps:
            later = [o for o, stamp, _ in self._offsets(tp.partition) if stamp >= tp.offset]
            tp.offset = later[0] if later else -1
            out.append(tp)
        return out

    def assign(self, tps):
        self.assigned = list(tps)
        for tp in tps:
            for o, stamp, body in self._offsets(tp.partition):
                if o >= tp.offset:
                    self.queue.append(Message(tp.partition, o, stamp, body))

    def poll(self, timeout):
        return self.queue.pop(0) if self.queue else None

    def close(self):
        self.closed = True

    def subscribe(self, *args, **kwargs):
        raise AssertionError("a read joined a consumer group")

    def commit(self, *args, **kwargs):
        raise AssertionError("a read committed an offset")

    def store_offsets(self, *args, **kwargs):
        raise AssertionError("a read stored an offset")


def two_partitions():
    return Broker(
        {
            0: [(ms(2), payload("a", 2)), (ms(4), payload("a", 4))],
            1: [(ms(3), payload("b", 3))],
        }
    )


class TestReadingATopic:
    def test_every_event_is_read_by_assigning_partitions_and_nothing_is_committed(self):
        broker = two_partitions()
        events, report = read_kafka(ADDRESS, consumer=broker)
        assert sorted(e.job.name for e in events) == ["a", "a", "b"]
        assert (report.events, report.partitions, report.clean) == (3, 2, True)
        assert {tp.partition for tp in broker.assigned} == {0, 1}
        assert broker.closed

    def test_since_starts_each_partition_at_the_brokers_offset_for_that_time(self):
        broker = two_partitions()
        events, _ = read_kafka(ADDRESS, since=datetime(2026, 11, 3, tzinfo=UTC), consumer=broker)
        assert sorted((e.job.name, e.event_time.day) for e in events) == [("a", 4), ("b", 3)]

    def test_a_message_that_is_not_an_event_is_counted_not_raised(self):
        broker = Broker({0: [(ms(2), b"not json"), (ms(3), payload("a", 3)), (ms(4), None)]})
        events, report = read_kafka(ADDRESS, consumer=broker)
        assert len(events) == 1 and report.skipped_records == 2
        assert not report.clean

    def test_a_topic_that_does_not_exist_is_named_as_unreadable(self):
        _, report = read_kafka("kafka://kafka:9092/nope", consumer=two_partitions())
        assert report.unreadable == ("nope (no such topic on kafka:9092)",)

    def test_a_read_stops_at_the_event_limit_and_says_so(self):
        broker = Broker({0: [(ms(d), payload("a", d)) for d in range(1, 9)]})
        events, report = read_kafka(ADDRESS, max_events=3, consumer=broker)
        assert len(events) == 3 and report.truncated


class TestRetention:
    """A window that starts before the topic's oldest retained event is not covered.

    Withholding the mark here was the maintainer's decision, as for a truncated read.
    """

    def deleted(self):
        # Offsets 0 to 4 are gone; the oldest event still held is from the 6th.
        return Broker({0: [(ms(6), payload("a", 6)), (ms(7), payload("a", 7))]}, low={0: 5})

    def test_retention_inside_the_window_is_a_reason_and_withholds_the_mark(self):
        events, report = read_kafka(
            ADDRESS, since=datetime(2026, 11, 1, tzinfo=UTC), consumer=self.deleted()
        )
        assert len(events) == 2
        assert report.retained_from == datetime(2026, 11, 6, 10, tzinfo=UTC)
        assert not report.clean
        [reason] = report.reasons()
        assert reason.startswith("the topic holds events only from 2026-11-06T10:00:00+00:00")
        record = ropa.build(
            events,
            config=config.parse("controller: ACME GmbH\n"),
            vocabulary=vocabulary.load(),
            report=report,
        )
        assert not record.completeness.complete

    def test_a_window_that_starts_after_what_was_deleted_is_covered(self):
        _, report = read_kafka(
            ADDRESS, since=datetime(2026, 11, 6, 12, tzinfo=UTC), consumer=self.deleted()
        )
        assert report.retained_from is None and report.clean

    def test_without_since_nothing_is_said_about_retention(self):
        # No window was asked for, so none can be cut short.
        _, report = read_kafka(ADDRESS, consumer=self.deleted())
        assert report.retained_from is None and report.clean


class TestSettings:
    def test_authentication_comes_from_qedro_kafka_variables_in_librdkafkas_names(self):
        settings = kafka_settings(
            {
                "QEDRO_KAFKA_SECURITY_PROTOCOL": "SASL_SSL",
                "QEDRO_KAFKA_SASL_MECHANISMS": "SCRAM-SHA-512",
                "OTHER": "ignored",
            }
        )
        assert settings == {"security.protocol": "SASL_SSL", "sasl.mechanisms": "SCRAM-SHA-512"}

    @pytest.mark.parametrize("name", ["QEDRO_KAFKA_GROUP_ID", "QEDRO_KAFKA_ENABLE_AUTO_COMMIT"])
    def test_a_setting_that_would_move_offsets_is_refused(self, name):
        with pytest.raises(ConfigError, match="moves nobody's position"):
            kafka_settings({name: "x"})

    @pytest.mark.parametrize("address", ["kafka://kafka:9092", "kafka:///topic", "kafka://k/a/b"])
    def test_an_address_without_one_topic_is_refused(self, address):
        with pytest.raises(ConfigError, match="kafka://broker:9092/topic"):
            read_kafka(address, consumer=two_partitions())


def test_without_the_extra_the_error_names_it():
    try:
        import confluent_kafka  # noqa: F401
    except ImportError:
        with pytest.raises(ConfigError, match=r"pip install 'qedro\[kafka\]'"):
            read(ADDRESS)
    else:
        pytest.skip("confluent-kafka is installed here")
