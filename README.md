<img src="docs/wordmark.svg" alt="Qedro" width="220">

[![CI status on main](https://github.com/cordata-tech/qedro/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/cordata-tech/qedro/actions/workflows/ci.yml)
[![qedro on PyPI](https://img.shields.io/pypi/v/qedro)](https://pypi.org/project/qedro/)
[![Python versions qedro runs on](https://img.shields.io/pypi/pyversions/qedro)](https://pypi.org/project/qedro/)
[![Licence: Apache-2.0](https://img.shields.io/badge/licence-Apache--2.0-blue)](LICENSE)

**The GDPR documents an auditor asks for, built from the evidence your pipelines already
emit, and saying plainly where that evidence ends.**

Point qedro at your OpenLineage events. It writes your Art. 30 record of processing
activities, a record of how far an erasure reached, the provenance of a published
figure, and the history of every data check, as PDF, workbook, Markdown and JSON.

![The first pages of three documents qedro writes, side by side. An Art. 30 record of processing activities whose verdict ends with the mark, listing seven activities with purpose, legal basis and where each came from. The provenance of a published dataset, a tree from the dataset back through the runs that produced it, each box naming the job, its commit and the platform, with two reasons the chain is not a proof. An erasure record, a tree of the datasets derived from the erased one, saying in each box whether the erasure reached it, with two tinted boxes it did not reach.](https://raw.githubusercontent.com/cordata-tech/qedro/main/docs/images/documents.png)

*Three of the four documents, as `qedro demo`'s lineage produces them: the Art. 30
record, the provenance of a published dataset, and what an erasure reached.*

## What you get

| Document | The question it answers | Command | More |
|---|---|---|---|
| **Art. 30 record** | What processing happens, for what purpose, on what legal basis, and how we know | `qedro ropa` | [docs/art30-record.md](docs/art30-record.md) |
| **Erasure record** | Did an erasure reach every dataset derived from the erased one? | `qedro erasure` | [docs/erasure.md](docs/erasure.md) |
| **Provenance chain** | Where did this published figure come from, which code made it, which checks ran on its inputs? | `qedro provenance` | [docs/provenance.md](docs/provenance.md) |
| **Assertion history** | Which data checks ran, on what, and when did they fail? | `qedro quality` | [docs/quality.md](docs/quality.md) |

Around them: `qedro diff` compares two records, `qedro sign` records who prepared and
who approved one, with four eyes, and `qedro status --against` says whether a signed
record still describes what runs ([docs/review.md](docs/review.md)). The AI Act's
deployer questions are a view of the Art. 30 record, `qedro ropa --view deployer`.

## Try it

```console
$ pipx install qedro
$ qedro demo
$ qedro ropa demo/lineage --config demo/qedro.yaml            # asserted, no mark
$ qedro ropa demo/lineage-declared --config demo/qedro.yaml   # evidenced      ∎
```

`qedro demo` writes three weeks of dbt, Airflow and Spark lineage from a company that
does not exist. The two directories hold the same runs and differ only in whether the
pipelines declare why they process, which is the difference between a record somebody
asserts and one that stands on its own evidence.
[`demo/README.md`](demo/README.md) walks through it.

![A 40-second terminal recording: pip installs qedro, qedro demo writes the fictitious company ACME Finanz GmbH, qedro ropa writes the Art. 30 record from the plain lineage with two reasons it is not a proof and from the declaring lineage with the mark, and qedro erasure names the one descendant not written since. It ends on the first pages of the PDFs.](https://raw.githubusercontent.com/cordata-tech/qedro/main/docs/images/demo.gif)

To see it read events that real emitters sent, [qedro-lab](https://github.com/cordata-tech/qedro-lab)
runs Airflow, dbt and other emitters in Docker Compose and delivers every event to each
place qedro reads from.

## How it works

![Four ways into qedro. Pipelines that emit lineage, such as dbt, Airflow, Spark, Flink and Dagster, send OpenLineage events; your own jobs, wrapped by art30-emit with their code unchanged, send them too; and for other systems, an adapter turns their logs or metadata into events. The events land in a directory, S3, GCS, Azure, Marquez or a Kafka topic, where qedro reads them and never writes. Processing with no pipeline, such as SaaS tools or manual steps, is declared in a file that qedro reads and marks as declared. qedro writes the documents: the Art. 30 record, the erasure record, provenance and data checks, as PDF, workbook, Markdown and JSON, each ending with the mark only where every part stands on evidence.](https://raw.githubusercontent.com/cordata-tech/qedro/main/docs/images/ways-in.png)

You do not need OpenLineage in place already. qedro reads
[OpenLineage](https://openlineage.io) events, the open standard for what a pipeline
ran, read and wrote, and there are several ways to get them:

- **Pipelines that already emit them**: dbt, Airflow, Spark, Flink and Dagster do, once
  their OpenLineage integration is switched on.
- **Your own jobs**, which emit nothing today:
  [`art30-emit`](https://github.com/cordata-tech/art30-emit) wraps a job's command and
  emits what it read and wrote, why it processes, and which code it ran, without
  changing the job.
- **Other systems**: an adapter turns their logs or metadata, such as a warehouse's
  query history, into the same events. Tell us which system you need, in an
  [issue](https://github.com/cordata-tech/qedro/issues).
- **Processing with no pipeline at all**, such as a SaaS tool or a manual step: you
  declare it in a file, and every document marks it as declared rather than evidenced.

The events can land as files in a directory or a bucket you own; qedro needs no server
of its own, and reads without writing anything back. Each value in a document says
where it came from, so you can see what rests on evidence and what does not.
[docs/sources.md](docs/sources.md) covers each place qedro reads from.

## The mark ∎

**Q.E.D.**, *quod erat demonstrandum*, *that which was to be demonstrated*, closed
mathematical proofs for centuries. The mathematician **Paul Halmos** replaced it with a
small solid square borrowed from magazine typography, the end-of-proof mark now called
the **tombstone**, or the *halmos*: **∎**. The wordmark puts it where the last letter
goes, **QEDR∎**, so a complete run finishes the name.

The link to the GDPR is the word *demonstrate*. Art. 5(2) obliges a controller to be
able to **demonstrate** compliance, which makes a record of processing something to
prove rather than something to fill in. A proof stands on what can be checked, and so
does a qedro document: each value says whether it rests on **evidence**, a fact the
pipelines emitted about what they ran, or on **assertion**, something a person wrote
down, such as a purpose in a mapping file or a declared activity. A record built from
assertions looks exactly like one built from evidence, and that is the problem a
hand-kept record has.

So qedro ends a document with the tombstone **∎** only when every part stands on
evidence, and withholds it, listing the reasons, wherever any part rests on assertion
or on nothing at all: a purpose from a mapping file, a domain that produced no lineage,
a step whose code nobody named. The run still writes the document. Withholding is the
signal, because a record with invisible holes is worse than none. More in
[docs/about.md](docs/about.md).

![The first page of two Art. 30 records of the same pipelines, side by side. The left one ends its verdict with the mark; the right one lists three reasons it does not claim to be a proof and tints every activity row whose purpose and legal basis came from a mapping file or a declaration.](https://raw.githubusercontent.com/cordata-tech/qedro/main/docs/images/art30-pdf.png)

*The same three weeks of demo lineage, recorded twice. On the left, the pipelines
emitted why they process, so the record ends with ∎. On the right, the purposes came
from a mapping file, so the record says it is not a proof and tints each row that is
part of why.*

## Run it on your lineage

```console
$ pipx install 'qedro[pdf]'
$ qedro ropa s3://your-bucket/lineage/ --config qedro.yaml --out ropa.pdf
```

[`docs/pilot.md`](docs/pilot.md) covers what you need, how to keep a copy of your events
when the place they go today cannot give them back, and what the first hour produces.
[`docs/compatibility.md`](docs/compatibility.md) lists what qedro runs against.

## Commitments

- **Read-only.** No write path, and no credential that could acquire one.
- **Not bound to a cloud or a catalogue.** Classification sources are adapters; the
  record runs against a Marquez instance with no cloud at all.
- **Vocabularies and regulation texts are data**, loaded at runtime, so an organisation
  can use its own.
- **Not legal advice.** A document reports what the events say and where each value
  came from; whether it meets an obligation is for the person accountable for it.

## Documentation

| | |
|---|---|
| [docs/art30-record.md](docs/art30-record.md) | the Art. 30 record: what it reads, what only a person can say, output and configuration, the deployer view |
| [docs/review.md](docs/review.md) | comparing records, signing them off with four eyes, and whether a signed record still describes what runs |
| [docs/provenance.md](docs/provenance.md) · [docs/quality.md](docs/quality.md) · [docs/erasure.md](docs/erasure.md) | the other three documents |
| [docs/sources.md](docs/sources.md) | every place qedro reads OpenLineage from |
| [docs/art30-facet.md](docs/art30-facet.md) | the `processing` facet, for anyone who wants to emit it |
| [docs/pilot.md](docs/pilot.md) · [docs/compatibility.md](docs/compatibility.md) | a first run on your own lineage, and what it runs against |
| [docs/about.md](docs/about.md) | the name, why qedro exists, what it is not, and the design commitments in full |
| [docs/evidence/](docs/evidence/) | captured runs that published writing quotes |
| [CHANGELOG.md](CHANGELOG.md) · [CONTRIBUTING.md](CONTRIBUTING.md) · [SECURITY.md](SECURITY.md) | changes, contributing, and what the tool can reach |

Early development: every document is written as text, Markdown, JSON and a workbook,
and all but the assertion history as PDF, and the tests run against lineage captured
from real dbt, Airflow, Spark, Flink and `art30-emit` runs. `0.x` interfaces may still
move, and the changelog says which.

## Licence

[Apache-2.0](LICENSE). Everything, including the parts that would be the commercial
tier elsewhere.
