<img src="docs/wordmark.svg" alt="Qedro" width="220">

[![CI status on main](https://github.com/cordata-tech/qedro/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/cordata-tech/qedro/actions/workflows/ci.yml)
[![qedro on PyPI](https://img.shields.io/pypi/v/qedro)](https://pypi.org/project/qedro/)
[![Python versions qedro runs on](https://img.shields.io/pypi/pyversions/qedro)](https://pypi.org/project/qedro/)
[![Licence: Apache-2.0](https://img.shields.io/badge/licence-Apache--2.0-blue)](LICENSE)

**The GDPR documents an auditor asks for, built from the lineage your pipelines already
emit, and saying plainly what each one cannot prove.**

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

```text
your pipelines      dbt · Airflow · Spark · Flink · your own jobs
      │  OpenLineage events
      ▼
where they land     a directory · S3 · GCS · Azure · Marquez · a Kafka topic
      │  read only
      ▼
qedro           ──▶ PDF · workbook · Markdown · JSON
```

qedro reads the [OpenLineage](https://openlineage.io) events your pipelines emit, from
wherever they land, and needs no server of its own. Each value in a document says where
it came from: an emitted facet, your `qedro.yaml` mapping, or a declaration for
processing that emits no lineage. Pipelines that say why they process, with the
`processing` facet ([`art30-emit`](https://github.com/cordata-tech/art30-emit) adds it
to a job without changing its code), produce a record that stands on evidence.
[docs/sources.md](docs/sources.md) covers each source.

## The mark ∎

**Q.E.D.**, *that which was to be demonstrated*: Art. 5(2) GDPR obliges a controller to
be able to **demonstrate** compliance. qedro ends a document with **∎** only when it
stands on its own evidence, and withholds it, with the reasons, wherever any part rests
on assertion: a purpose from a mapping file, a domain that produced no lineage, a step
whose code nobody named. The run still writes the document. Withholding is the signal,
because a record with invisible holes is worse than none. More in
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
