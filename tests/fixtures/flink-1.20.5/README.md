Real OpenLineage from Flink, not hand-written.

`events.jsonl` is one bounded Flink job reading a Kafka topic and writing another,
captured on 2026-09-19 with Flink 1.20.5, `flink-connector-kafka` 3.4.0-1.20 and
`openlineage-flink` 1.53.0, running in a local MiniCluster against a Kafka broker in
Docker. The job, its Dockerfile and the compose file are in
`cordata/flink-lineage-probe`. Nothing was removed.

Two events, and both are the point:

- `START` names the source, `kafka://kafka:9092/orders`.
- `COMPLETE` names **no datasets at all**. So an activity's datasets have to be
  gathered across a job's events rather than read off the terminal one, which is what
  `ropa` does and what this fixture holds it to.

What makes Flink different from the three emitters already captured:

- **Lineage comes from connectors, not from the plan.** The integration extracts
  datasets only from a short list of sources and sinks — Kafka, Iceberg and a few
  more — so a job reading files would emit a job with no datasets at all.
- **The hook is registered in the job's own code**, a Flink `JobListener`, rather than
  configured from outside as the Spark listener is. That is why the probe is a Java job.
- **`jobType` says `STREAMING`** even though this source is bounded and the run ends.
- Datasets are namespaced by broker, `kafka://kafka:9092`, so a topic's identity
  includes where it lives.

## Three defects this capture found, all in the integration

1. **No START event at all without `flink-avro` on the classpath.** The Kafka source
   wrapper references `AvroDeserializationSchema` while working out a schema facet,
   whatever the job's actual deserialiser, so the listener dies with
   `NoClassDefFoundError` and the run emits only a terminal event. The probe adds
   `flink-avro` as a dependency it otherwise has no use for.
2. **The sink is never reported.** `KafkaSinkWrapper.getKafkaTopic` looks for a nested
   `topicSelector` field and calls `.get()` on an empty `Optional` when
   `flink-connector-kafka` 3.4 does not have one, so the output side is empty and the
   job reads as an activity that read data and wrote none. The job uses the connector's
   documented builder API; nothing about it is unusual.
3. **Configuration not in a file is reported as an error**, `No OpenLineage
   configuration file found`, before the Flink configuration is read successfully. A
   stack trace for the supported path is a defect in the message, not in the run.

The first two are recorded as possible OpenLineage contributions. Together they are why
this fixture has one dataset rather than two — and why `ropa` reports the job under the
`read only` line from #22, which is the honest reading of what the events say.
