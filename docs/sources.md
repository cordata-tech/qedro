# The reader

Worth running on its own before anything else — it tells you whether your lineage is
readable at all:

```console
$ qedro events ./lineage
  1,284 events · 37 jobs · 112 datasets · 14 files                             ∎
  complete 641, start 641, fail 2
```

Point it at a directory of `.json`, `.ndjson` or `.jsonl`. It reads newline-delimited
events, JSON arrays and single objects without being told which, walks nested
directories, and never stops on a bad record — malformed events are counted and
reported rather than thrown.

Or point it at a bucket. An `s3://`, `gs://` or `az://` prefix is read with the same
rules as a directory, using the credentials your environment already has, once the
extra for that cloud is installed — `pipx install 'qedro[s3]'`:

```console
$ qedro events s3://acme-lineage/openlineage/
```

Or point it at a Marquez-compatible API and it reads the same events over HTTP:

```console
$ qedro events https://marquez.internal --since 2026-01-01
  4,102 events · 37 jobs · 112 datasets · 42 pages                             ∎
```

Any spelling of the address works — a bare host, `.../api/v1`, or the full endpoint.
The window is passed to the backend as a query and **applied again to what comes
back**, so a backend that ignores it still produces a correct result rather than a
quietly wider one. Reading stops after 10,000 events, and says so, rather than
returning a prefix of the history that looks like all of it.

The HTTP source is read-only by construction: GET is the only verb the code can
build. If the backend needs a token, it comes from `QEDRO_API_TOKEN` and never from
the command line, where it would land in shell history and in `ps`.

Or point it at a Kafka topic, once `pipx install 'qedro[kafka]'` has added the client
the OpenLineage Python transport itself uses:

```console
$ qedro events kafka://broker:9092/openlineage.events --since 2026-11-01
```

Reading a topic moves nobody's position on it: qedro assigns partitions rather than
joining a consumer group, and never commits an offset. `--since` starts each partition
at the offset the broker's timestamp index gives for that time, and the read stops at
the end the topic had when it began. A topic keeps events only as long as its retention,
so when the window starts before the oldest event it still holds, the record says from
when it holds them and does not claim to be a proof. Authentication and TLS settings
come from `QEDRO_KAFKA_*` variables in librdkafka's own names —
`QEDRO_KAFKA_SECURITY_PROTOCOL=SASL_SSL` is `security.protocol` — and a setting that
would commit or join a group is refused. The client's own logging is off unless
`QEDRO_KAFKA_LOG_LEVEL=7` turns it on; a broker that cannot be reached is named in
qedro's summary either way.

If anything was unusable the tombstone is withheld and the reason goes to stderr:

```console
$ qedro events ./lineage
  1,282 events · 37 jobs · 112 datasets · 14 files
  complete 640, start 641, fail 1
  ! 2 records were not usable OpenLineage events
```

Use `--no-symbol`, or `QEDRO_NO_SYMBOL=1`, where U+220E has no glyph.
