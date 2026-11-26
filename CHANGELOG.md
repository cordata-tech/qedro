# Changelog

Notable changes, in the words of somebody deciding whether to upgrade.

`0.x` may change interfaces between releases. The entries below say which, and
output formats and the `qedro.yaml` schema are the parts most likely to move
before `1.0`.

## Unreleased

- **`qedro status --against` says why each change happened**, as far as the events and
  files show it, comparing each job before and after the end of the signed record's
  window (#49):
  - a value a job emits: the first run after the sign-off that emitted it, with its
    commit, and the commit the job ran at before;
  - a value from the mapping file: the rule, its file and line, and where `qedro.yaml`
    is in Git, the commit that last changed the rule, with author, date and message,
    read with `git log`, which is the only program qedro runs;
  - a classification: the run, and the job, whose event first tagged the dataset so;
  - a dataset newly read: the first run that read it, and the chain of jobs producing
    it, each before → after the sign-off, by commit and by the inputs it gained or lost;
  - a new activity or a dataset newly written: its first run; a declared activity: its
    document.

  A value gone with nothing supplying it is reported as stopped, anything else as
  unattributed with the reason, and a job with no run before the sign-off in the events
  as possibly older; nothing is guessed. The text prints a `why:` line under each change;
  the JSON gives each change and each new activity a `cause` object beside the existing
  fields, with `upstream`, `rule_change` and `history` for the chain and the rule's
  history.
- **The demo has a fourth week**, in `lineage-later/`: `lineage/` line for line, then a
  week in which a new job starts writing device profiles and the scoring job reads them
  and declares a purpose of its own. `qedro demo` now ends with the four commands that
  sign a record over the first three weeks and check it against all four, and
  `demo/README.md` shows what `qedro status` says and why.

## 0.30.0 — 2026-11-23

- **A job that processes no personal data can be left out of the Art. 30 record.** A
  `jobs:` rule with `out_of_scope: <why>` leaves the jobs it matches out of the
  activities, so a platform that also runs pipelines over fund prices or sensor
  readings no longer lists them with no purpose and withholds the mark for it. The
  scope statement names every job left out with the rule's reason, in every format, and
  the JSON lists them under `scope.left_out`, beside the fields a sign-off covers. A
  left-out job that reads or writes a dataset classified under Art. 30(1)(c) withholds
  the mark, unless the vocabulary flags the value `personal: false`; the shipped
  vocabulary now flags `subject_type: none`. A vocabulary of your own needs the flag on
  its own values for the same effect. Such a rule cannot also give a purpose, a legal
  basis, recipients or security measures (#65).
- **`qedro diff --format json` gives each finding in words**, as `says` and `costs`
  beside its fields: the sentence the text and Markdown print, such as *debt-collection,
  unchanged* and *evidence lost: emitted facet → mapping file*, with `costs` null where
  a finding costs nothing. `qedro status --against` already did, and a console reviewing
  a regenerated record now shows qedro's words rather than writing its own.

## 0.29.0 — 2026-11-23

- **Each step of a provenance chain says what was checked on what it read.** For every
  input, the data quality assertions reported on it after it was last written and up to
  the end of the step's run, one result per check, including those a separate check job
  ran: *3 checks, 2 held, 1 failed: every share class has a price*, or *no checks
  reported*. In every format; the JSON adds `checks` to each production and three
  counts to the scope, beside the fields a sign-off covers, so no approval reopens. A
  failed check is stated and does not withhold the mark (#64).
- **The assertion history counts each run's checks once.** An emitter that put
  `dataQualityAssertions` on both START and COMPLETE had every check counted twice, and
  the history contradicted itself: 5 runs for a dataset, 10 for each of its checks. A
  run's result for a check is now the one it ended on, or its latest where it reported
  none at the end, so the counts under a dataset and its checks agree and a check that
  failed at START and held at COMPLETE counts as held (#63).
- **The provenance PDF's note under the tree reads as a sentence.** It said each line
  joins a dataset "to one its producing run read"; it now says "to one that its
  producing run read".
- **The README is a landing page**: the four documents with a picture of each, the ways
  in (OpenLineage, adapters such as art30-emit, declared activities) as a diagram, and
  the name and the tombstone explained. The reference it held moved to `docs/`, one page
  per document, with how events are read in `docs/sources.md` and the name and the
  design commitments in `docs/about.md`.

## 0.28.0 — 2026-11-22

- **An erasure record names a descendant nothing wrote since the erasure, instead of
  leaving it out.** With `--since`, `qedro erasure` read only the events from that
  instant on, so a dataset derived from the erased one before the erasure, and not
  written after it, was missing from the record rather than counted as not reached:
  the one descendant the erasure had missed. It now reads everything up to `--until`,
  and `--since` is the erasure instant alone; the record's window starts with the
  earliest event read. Erasure records built with `--since` can list more
  descendants than before, and withhold the mark where one of them was missed.
  Found by qedro-lab's scripted fortnight, where a dbt run left one model out on the
  day of the erasure.
- **A Kafka broker that cannot be reached is named, not raised.** In 0.27.0 it ended
  `qedro events kafka://…` with a `KafkaException` traceback under some 550 lines of
  librdkafka's own reconnect log. It now reads *could not read broker:9092 (Failed to
  get metadata: …)* and exits 1, as an HTTP backend that is down does, and the client's
  logging is off unless `QEDRO_KAFKA_LOG_LEVEL` turns it on.

## 0.27.0 — 2026-11-21

A Kafka topic is a source, and the JSON carries the scope statement a reader can show.
New fields and a new extra; nothing existing changes shape or behaviour, and no approval
reopens.

- **Read OpenLineage from a Kafka topic** (#59): `qedro events kafka://broker:9092/topic`,
  and every projection, with the new `qedro[kafka]` extra. The read assigns partitions,
  joins no consumer group and commits nothing, so nobody's position on the topic moves.
  `--since` starts at the broker's offset for that time; a window that starts before the
  topic's retention is not fully covered, and the record withholds the mark with a reason
  saying from when the topic holds events. Authentication comes from `QEDRO_KAFKA_*`
  variables in librdkafka's names. The summary line counts partitions, and `scope.read`
  gains `partitions`, `retained_from` and the kind `kafka`.
- **The JSON carries the scope statement as rows a reader can show** (#61): each
  projection's `scope.statement` is every labelled row the text format prints in its
  scope — source, window, what each projection adds, files passed over, copies counted
  once, how domains were assigned, silent domains — as `{"label", "text"}` in the same
  order and the same words. For the console, which shows a record's scope without
  wording anything itself. Beside the numbers, which stay; outside every sign-off's
  covered fields.

## 0.26.0 — 2026-11-21

What the read found, said in the JSON and counted correctly: an event a backend stored
twice is counted once, and every projection's JSON says what the read found, for the
console's Sources page. Tested against Airflow 3.4 under the scheduler with four
emitters in one run. The JSON gains fields and changes none, and no approval reopens;
one thing behaves differently on upgrade: a source holding two versions of one event
now withholds the mark, with a reason saying how many.

- **Every projection's JSON says what the read found** (#57), in `scope.read`: the
  source and whether it is a directory, a bucket or an API; files or pages read,
  events, records skipped and each file that could not be read, with its reason; files
  passed over; duplicates and conflicting records (#58); the earliest and latest event
  time, so a reader can see that lineage stopped arriving; and in the Art. 30 record
  each domain in scope with the events its activities produced, a declared domain with
  none listed at zero. It is outside every sign-off's covered fields, so a record
  rebuilt over more events reopens no approval. For the console's Sources page.
- **An event a backend stored twice is counted once** (#58). Marquez keeps every
  attempt when the OpenLineage HTTP client retries after its timeout, and qedro counted
  each copy. A record identical to one already read is now set aside, whatever the
  source, and the summary line and every artefact's scope state how many: *1 record
  identical to one already read, counted once*. The mark stands, because the record
  then says exactly what was emitted. Two records with the same job, run, event type
  and time but different content are both kept, and the mark is withheld with a reason
  naming how many: which version the emitter meant is not something qedro can know.
  Every format gains the line, and the JSON's `scope` gains `duplicates`.
- **Tested against Airflow 3.4.0 with provider 2.21.0, under the scheduler**: a capture
  from [qedro-lab](https://github.com/cordata-tech/qedro-lab) with four emitters in one
  run — Airflow, and dbt-ol, art30-emit 0.2.0 and pipeline-runtime 0.2.13 each launched
  from a task and naming it as parent — and an orchestration three levels deep (DAG run,
  task, dbt invocation) that the record leaves out of the activities. No behaviour
  changed.
- **The pilot guide names the two Airflow limits** an OpenLineage emission has to fit
  inside, `[openlineage] execution_timeout` and `[core] task_success_overtime`, and
  lists the archive first in its composite example: qedro-lab lost events to both.

## 0.25.0 — 2026-11-20

Four eyes on sign-off (#47): the person who sent a record for sign-off can no longer
approve it, unless `qedro.yaml` says one person does both.

- `qedro sign --state approved` refuses an approval by the preparer, in a sentence
  naming both, comparing names without regard to case or spacing. **This changes what
  an existing workflow can do**: a script that sends for sign-off and approves under
  one name now stops at the approval. Use a second name, or set
  `signoff: {four_eyes: false}` in qedro.yaml; `qedro sign --config` points at one
  elsewhere.
- Every format prints the preparer beside the approver — *approved by B on …,
  prepared by A on …* — or *with no second person: A also prepared it*.
- The record JSON's `signoff` gains `prepared_by` and `second_person` (`null` until
  approved), beside the covered fields, so no existing approval is reopened. `qedro
  status` counts approvals with no second person, and its JSON gains
  `approved_without_second_person` and the same two fields per record.
- The names are typed with `--as`, not authenticated; the README says what that can
  and cannot prove.

## 0.24.0 — 2026-11-19

`qedro status` can write what it finds as JSON, for a console that shows which signed
records have gone stale. A new document; nothing existing changes shape.

- **`qedro status --format json`** writes what the text prints as a document a reader
  such as the console can use: every record with its verdict and where its sign-off
  stands, and, with `--against`, each activity's state and every change, with the
  words the text says it in. `"projection": "status"` in its `qedro` block. It names
  the fresh run's source and window rather than a time, so two runs over the same
  lineage write the same bytes. `--out` writes it to a file; `qedro status` reading
  the directory again passes over a status document rather than counting it.

## 0.23.0 — 2026-11-19

A stale signed record can be rebuilt and sent back for sign-off in one step, with what
changed named, and its new version keeps the same sign-off history. The sign-off file's
`record` field now always names the record.

- **`qedro status --against … --regenerate --as NAME`** (#55) writes, for each signed
  Art. 30 record with a stale or new activity, the fresh record beside it as
  `record.next.json`, and adds a *for sign-off* entry for that version by NAME, naming
  what changed. Records that are up to date or blocked are left alone, and running it
  again adds no second entry. The signed record and its entries are unchanged.
- **A `record.next.json` shares its record's sign-off file**: `qedro sign` and `qedro
  status` read and write `record.signoff.json` for it, so approving the new version and
  then replacing the record with it keeps one history. The sign-off file's `record`
  field always names the record, not the version an entry was added for.

## 0.22.0 — 2026-11-19

`qedro status --against` says, for every signed Art. 30 record, which activities still
match what runs and which have changed since the sign-off. Additions only: no output
changes shape.

- **`qedro status --against SOURCE` says whether each signed record still describes
  what runs** (#42). It builds a fresh Art. 30 record from the lineage, with the same
  `--config`, `--activities`, `--vocabulary`, `--since` and `--until` as `qedro ropa`,
  and compares every approved or published Art. 30 record under the directory with it,
  one activity at a time: *up to date*, *stale* with what changed named, *new*, or
  *blocked* with the reason. A value unchanged on weaker evidence is stale; a job that
  only ran again is not. A fresh run that read no events blocks every signed record
  instead of reporting each activity as gone. Without `--against`, `qedro status` is
  as before.

## 0.21.0 — 2026-11-19

Every format of the Art. 30 record can now say where each value came from: the PDF as
footnotes, the workbook on a sheet of its own, text and Markdown with `--explain`. This
completes #48. The workbook gains two sheets; nothing else changes shape.

- **The PDF and the workbook print the explanations** (#48). The PDF puts a numbered
  marker in each row's source column and the sentence as a footnote under that
  activity's table, the controller's under the controller, and ends with the
  regulation's wording for every requirement, quoted once. The workbook gains an
  Explanations sheet, one filterable row per explained value with the requirement it
  answers and what it rests on, and a Requirements sheet with the wording. A
  workbook now has four sheets rather than two.
- **`qedro ropa --explain`** adds the same to text and Markdown output, which stay as
  they were without it.

## 0.20.0 — 2026-11-18

Every Art. 30 field in the JSON is now explained: classification values, the datasets
nothing classified, and the controller join the purpose, legal basis, recipients and
security measures. Additions only, beside the existing keys, so sign-offs made with
0.19.0 still stand.

- **Classification, unclassified datasets and the controller are explained too** (#48).
  `explain.classification` lists, per job, each value with the datasets whose `tags`
  facet gave it, which the job read or wrote, and whose events carried it — the job's
  own, or another job's when only that one tagged the dataset. `explain.unclassified`
  says, for each dataset nothing classified, that no event tagged it with a key the
  record uses, and which jobs touched it. `explain.controller` points at the line of
  `controller:` in qedro.yaml. Each names the Art. 30(1) item it answers. They sit
  beside `explain.activities`, whose entries stay one explanation per field.

## 0.19.0 — 2026-11-18

The Art. 30 record's JSON says where each value came from in a sentence, and which
requirement of the GDPR the field answers, quoting the regulation's wording. Additions
only: no key is renamed or removed, and sign-offs made with 0.18.0 still stand.

- **The Art. 30 record's JSON explains its values** (#48, first part). A new `explain`
  object says, for each activity's purpose, legal basis, recipients and security
  measures, where the value came from in a sentence built only from what the record
  holds: *Asserted in qedro.yaml (line 37), rule `acme.fraud/transactions-*`, because
  `acme.fraud/transactions-scored-daily` emitted no purpose in a `processing` facet.*
  Each names the requirement the field answers and what it rests on (the run whose
  event carried the facet, the mapping rule and its line, or the declaration), so a
  reader can follow it. Declared activities get the same. No explanation judges a
  value; a test holds every one to that and to naming nothing the record does not
  hold.
- **What each field answers is a document**, `regulations/gdpr.yaml`, loaded at runtime
  like the vocabulary and quoting the regulation's wording once under `references` in
  the JSON. `references:` in qedro.yaml points at another one. YAML and JSON configs
  give each rule's line; a TOML config cannot, and its explanations name the rule
  without one.
- Both sit beside the activities rather than inside them, so a sign-off made with
  0.18.0 still stands. Text, Markdown, PDF and workbook output are unchanged for now.

## 0.18.0 — 2026-11-18

The JSON of every projection carries the words qedro prints, so a reader such as the
console says each state as qedro does, and the provenance PDF draws branching chains
correctly. Every change to the JSON adds a key; none is removed or renamed, and none of
the new keys is covered by a sign-off, so sign-offs made with 0.17.0 still stand.

- **Every projection's JSON carries `earned`**, the sentence the mark finishes — *every
  activity stands on emitted evidence*, *every step ran under a signed commit* — and the
  erasure record's tombstone carries `describe`, the line the text and PDF print. Each
  run in a provenance chain carries `describe` too: its code, signature, source and
  platform, as the PDF's step table prints them. A consumer such as the console shows
  these words rather than composing its own, and the text output takes each sentence
  from the same constant, so the two cannot drift.
- **The provenance PDF's tree hangs each step under the run that read it.** The walk is
  breadth-first, and the tree hung each step under the last step one level up, so in a
  chain where two branches both continued, every step two levels down was drawn under
  the second branch.

## 0.17.0 — 2026-11-18

The Art. 30 record's JSON says what ran each activity and where its data lives, and a
sign-off covers what a record states rather than every byte of it. Sign-offs made with
0.16.0 reopen once and need signing again; text and PDF output are unchanged.

- **The Art. 30 record's JSON says what ran each activity and where each dataset
  lives** (#39), as the erasure record and the provenance chain already do: each
  activity gains `ran_on`, `stored_in` and their kinds, and the record gains
  `datasets`, every dataset its activities read or write with where it lives. Read
  from the events only, `null` where they say nothing. The other formats are
  unchanged; this is what lets the console draw the same icons the PDF trees do.
- **A sign-off covers what a record states, not every byte of it** (#40). 0.16.0
  hashed the whole record, so rebuilding it over the next night's runs — new run
  counts, a later window — or with a qedro that adds an output field reopened every
  approval for nothing. A sign-off now covers an explicit list of each projection's
  statements: the controller, purposes, legal bases, categories, recipients, the
  datasets read and written, the verdict and its reasons. Each entry records which
  version of that list it was made under and is always checked against it, so an
  upgrade never reopens an approval by accident. **Sign-offs made with 0.16.0 still
  verify**, against the whole record as before, and therefore reopen once the record
  gains this release's new fields; sign them again with 0.17.0.

## 0.16.0 — 2026-11-17

A person can sign a record off, and qedro keeps who accepted which version beside it.
Two new commands, `qedro sign` and `qedro status`, and a `--signoff` flag on every
projection. Nothing changes in output that does not ask for a sign-off.

- **A person's sign-off on a record** (#40). `qedro sign record.json --as NAME --state
  STATE` adds an entry to `record.signoff.json` beside it: draft, for sign-off,
  approved or published, one step forward at a time or back to draft, each entry naming
  the SHA-256 of the record it covers. `qedro status <directory>` lists every record,
  whether it earned the mark, and where its sign-off stands, and reports a record that
  changed since it was signed as not signed off. `--signoff FILE` on any projection
  prints the sign-off under the verdict in every format. A sign-off is a person's
  acceptance, not evidence: it never changes the verdict, and output with no
  `--signoff` is unchanged.

## 0.15.0 — 2026-11-15

The PDF trees draw an icon for the kind of each step and set the platform line apart
from the state. `platforms:` entries can name a kind, and the JSON of the erasure
record and the provenance chain gains two fields. Text output is unchanged.

- **Icons in the PDF trees for the kind of thing each step is** (#39): a database,
  object storage, files or a stream beside each dataset's name, and a transformation,
  an orchestrator, a processing engine or a data quality check beside what ran it.
  An icon stands for a kind, never a vendor, and is drawn by qedro, so nothing is
  licensed or bundled. A legend under each tree names the icons it uses.
- **The platform line is drawn in its own colour**, apart from the state's grey and
  the tint, in the boxes and in the descendants table, and a note under each tree says
  what the lines, the colour and the tint mean. A job's name on a line now sits on a
  white backing instead of being crossed by it.
- **`platforms:` entries can give a kind**, `{label: AWS Glue, kind: database}`, so a
  platform qedro does not know still gets its icon. The JSON of both records gains
  `ran_on_kind` and `stored_in_kind`.

## 0.14.0 — 2026-11-14

The erasure record and the provenance chain say what ran each step and where its
data lives, in every format. Two things to know before upgrading: the text output of
both gains a `platform` line per descendant or step, and their JSON gains `ran_on`
and `stored_in`. No verdict changes.

- **A pipeline-runtime 0.2.10 capture** (#38), which marks each output it replaces whole
  with `lifecycleStateChange: OVERWRITE`. It is the first real capture in the tree
  that tells `qedro erasure` a descendant was rebuilt rather than only written. Nothing
  in qedro changed to read it; the compatibility table no longer lists pipeline-runtime
  among the emitters that say nothing about how they wrote.
- **The erasure record and the provenance chain say what ran each step and where its
  data lives** (#39), such as `dbt · Snowflake`. Read from the events only: the
  integration from the standard `jobType` facet or the `producer` URL, the platform
  from the dataset's namespace or its `dataSource` facet. Where they say neither, the
  output says *not reported* rather than guessing. Text output gains a `platform` line
  for each descendant and step, markdown a column, xlsx two (`Ran on`, `Stored in`),
  JSON the fields `ran_on` and `stored_in`, and each PDF box a line.
- **`platforms:` in `qedro.yaml`** labels an integration or a namespace scheme qedro
  does not know, or replaces one of its labels. A namespace scheme with no label is
  left out, because many namespaces are logical names written as URIs.
- **Every PDF page's footer carries the wordmark**, small, with the square filled only
  when the record earns the mark, so a page separated from its record still says
  whether that record claims to be a proof.
- **The demo's controller details are placeholders that read as placeholders.** The
  representative's address was a real Frankfurt street; it is now Musterstraße 1,
  00000 Musterstadt, and the data protection officer is Erika Mustermann. Every demo
  record, and the README's picture of one, showed the old address.

## 0.13.1 — 2026-11-14

A fix to how the erasure record's text output indents a tree that branches, and
the wordmark on every PDF. No verdict changes.

- **The erasure record's text output nests each descendant under the dataset it came
  from.** It printed them in the order the walk found them, breadth-first, indented by
  depth, so where two datasets branched a descendant appeared under its parent's
  sibling. The `derived by` line was right; the indentation contradicted it. No
  descendant, state or verdict changes, and a straight chain prints as before.
- **Every PDF opens with the wordmark**, QEDR and its square, as at the top of the
  README. The square is filled on a record that earns the mark and drawn as an outline
  on one that withholds it, so the wordmark never claims what the verdict below it does
  not. The scope statement is now kept on one page where it fits.
- **An example erasure that branches**, in `docs/examples/erasure`, which the README's
  picture of the erasure tree is drawn from. The demo's erasure is a straight chain;
  this one shows every state a descendant can be in.

## 0.13.0 — 2026-11-14

The Art. 30 record can be written as PDF too, which leaves only the deployer view
and the quality history without one. Nothing changes in what any record says.

- **The Art. 30 record as a PDF** (#37): `qedro ropa … --out record.pdf`, with the
  `pdf` extra. The controller and the verdict come first, then an overview of the
  activities, then one table per activity: each Art. 30(1) item, its value, and where
  the value came from, tinted where it is part of why the mark is withheld. A declared
  activity says *no lineage* wherever the events would have spoken. The deployer view
  and the quality history still refuse `--out *.pdf` in a sentence.
- **A dataset key too wide for its column breaks after a `/`** in every PDF, rather
  than wherever the column ended, which split
  `cordata://fraud/fraud_curated.transactions_scored` mid-word.

## 0.12.0 — 2026-11-14

The erasure record and the provenance chain can be written as PDF, for the people who
receive a record rather than run qedro. Nothing else changes in what either record
says; the erasure JSON gains one field.

- **The erasure record as a PDF** (#37): `qedro erasure … --out erasure.pdf`, for the
  people who receive a record rather than run qedro — an auditor who files it, a DPO
  who signs it. The verdict comes first; then a tree from the erased dataset down, each
  descendant's box labelled with its state and tinted where the proof does not reach;
  then the descendants, and the scope statement in full. The same events give the same
  bytes. It needs the new `pdf` extra, `pipx install 'qedro[pdf]'`, which installs
  reportlab; without it the command names that line.
- **The provenance chain as a PDF** (#37): `qedro provenance … --out chain.pdf`. The
  same layout, drawn from the published dataset back to its sources: each step's box
  names the job, the commit and whether it was signed, in words, and is tinted where
  the step is not shown to be authorised. The Art. 30 record, the deployer view and
  the quality history refuse `--out *.pdf` in a sentence until their PDFs exist.
- **The erasure JSON names each descendant's parent** as `derived_from`, so a consumer
  can draw the same tree.
- **An append reason reads correctly for one descendant.** It said *1 of 7 descendants
  were only appended to*; the verb now agrees with the count.

## 0.11.0 — 2026-11-07

`qedro erasure` stops claiming more than the events show about how a descendant was
written. Two things to know before upgrading: every erasure record's wording changes,
and its JSON renames the fields named below. Which descendants count as reached changes
only where dbt reports an `incremental` or `snapshot` model, which now withholds the
mark. Nothing in the demo or the evidence transcript changes verdict.

- **`qedro erasure` tells a rebuild from an append** (#35). A descendant was counted as
  reached when any run wrote it after the erasure, and the scope statement then said its
  contents had been replaced, which is false for an incremental model: its partitions
  from before the erasure still hold the erased data. Each write is now classified from
  what the event says. An `OVERWRITE`, `TRUNCATE` or `DROP` on the output, or dbt's
  `table` or `view` materialisation, is a **rebuild**. dbt's `incremental` or
  `snapshot` is an **append**, and a descendant only appended to since the erasure
  withholds the mark with a reason naming it. A write that says neither is counted as
  **written**, as before, with a `how` line saying it was not reported.
- **The wording no longer claims more than the events show.** *Rewritten since the
  tombstone* is now *written*, or *rebuilt* where the event says so; the scope
  statement's last sentence says a write replaced the contents only where the event says
  so; and a record that earns the mark ends *every descendant was written after the
  emitted …*. The JSON descendant entries carry `written`, `rebuilt` and `how` in place
  of `rewritten`, and the scope counts are `rebuilt`, `written`, `appended` and
  `not_written` in place of `rewritten` and `not_rewritten`. The workbook's column is
  *Written since the erasure*.

## 0.10.2 — 2026-11-04

One sentence. An erasure record that earns the mark now ends *every descendant was
rewritten after the emitted overwrite* (or *drop*, or *truncate*), naming what the
event reported. It read *after an emitted erasure*, which contradicted the tombstone
line above it whenever that line said *emitted overwrite, not a drop or truncate* —
the case `docs/evidence/erasure.md` run 2b shows. The transcript is recaptured.

## 0.10.1 — 2026-10-31

A security fix, and nothing else. Upgrading changes no output unless an emitter sent a
repository URL with credentials in it, in which case they no longer appear.

- **A repository URL is printed without any credentials it carried** (#34). `provenance`
  copied `sourceCodeLocation.repoUrl` into the record as received, so a token an
  emitter left in a git remote — `https://x-access-token:<token>@github.com/…`, as a CI
  checkout commonly does — would reach every output format and whoever received the
  artefact. An http or https URL now loses its userinfo, any other URL loses its
  password, and scp-style `git@host:org/repo` is left as it is. No committed fixture
  carried one; this protects against emitters qedro has not met.

## 0.10.0 — 2026-10-25

One change to what the Art. 30 record says, and it is visible: an activity can now
show a category of data another job declared on a dataset it read, marked with the job
that declared it. As with 0.6.0, the number counts releases and not milestones, so
nothing from the v0.10 milestone is in it.

- **A dataset's own classification reaches every job that touches it** (#32). The
  standard `tags` facet describes the dataset, so when one job tags what it writes and
  another reads the same dataset untagged, the reader's activity now carries those
  categories too, marked `(declared by <job>)` in text, markdown and the workbook and as
  `declared_by` in the JSON. Before, the reader showed the dataset as unclassified and
  the scope line counted it unclassified while the writer's activity said it was
  classified. Tags are never carried from one dataset to another: a job's output does
  not classify its source. A record from 0.9.0 compared with one from this version
  shows the new values on reading activities as additions.

## 0.9.0 — 2026-10-25

The provenance chain read against what `pipeline-runtime` actually emits. One output
change to know before upgrading: a step that names no commit is now explained as
*named no commit* rather than *emitted no code location*, and a signature verdict sent
without a commit is reported as set aside. The tests also read two fresh
pipeline-runtime captures, 0.2.4 from the wheel and 0.2.5 from a git checkout, in
place of the 0.1.0 capture they had used since August (#31).

- **`provenance` reads the commit `pipeline-runtime` reports** (#33). The commit was
  taken only from the standard `sourceCodeLocation` facet, which pipeline-runtime does
  not send, so a chain run from a git checkout said *no code location* about a commit
  the event carried. It now falls back to `cordata_provenance.descriptor_git_commit`,
  prefers the standard facet when both are present, and says which facet named it.
- **A signature verdict counts only with a commit.** A step that reports *signed* or
  *not signed* while naming no commit is no longer described as running under an
  unsigned commit: the verdict is set aside, and the output says one was given without
  a commit. The mark is withheld either way. The withholding reason for a step with no
  commit now reads *named no commit* rather than *emitted no code location*.

## 0.8.0 — 2026-10-23

A third kind of source, so that a pilot whose raw events land in a bucket can point
qedro at the bucket rather than copying it down first. Nothing a projection produces
changes. Read against a real S3 bucket before release, with the transcript on #30;
GCS and Azure use the same reader and have not been run against a real cloud.

- **Events can be read straight from a bucket** (#30): `qedro events s3://bucket/prefix/`,
  and the same for `gs://` and `az://`, in every command that reads events. Install the
  extra for the cloud — `qedro[s3]`, `qedro[gcs]` or `qedro[azure]` — and the base
  install is unchanged. Objects are chosen and parsed by the same code as a directory,
  so a prefix copied to disk and the same prefix read in place give the same events and
  the same report. Credentials come from the environment's own chain; the reader can
  only list and read, and `SECURITY.md` says what role to give it. A missing bucket, a
  denied listing or an empty prefix is reported and withholds the mark rather than
  reading as a clean zero.
- **On S3, set `AWS_REGION`** or grant `s3:GetBucketLocation`. Measured on #30: without
  either, a role that may list and read is refused, because the library asks the bucket
  where it is first, and the reason qedro gives now says so.
- **The dev extra pins ruff exactly**, after a ruff release failed `main` with no change
  here.

## 0.7.0 — 2026-10-11

Two fixes for problems found while writing the pilot guide, both of which a first run
on real lineage would hit. Output changes in two places worth knowing before upgrading:
every projection's scope statement can carry a new `passed over` row and its JSON a
`passed_over` list, and an erasure record built from several Spark overwrites without
`--since` no longer earns the mark.

- **A file with no extension is read when it starts with JSON** (#28). That is what an
  appending OpenLineage file transport writes, in the Python client to exactly the
  configured path and in the Java client to its `location`, and 0.6.0 read a directory
  holding one as empty without saying why. Every other file the reader does not read is
  now counted and named: on the `qedro events` summary, and as a `passed over` line in
  every projection's scope statement, with a `passed_over` list in the JSON. It does not
  withhold the mark, since a README beside the events is what a directory looks like.
  Hidden files and anything under a dot-directory are neither sniffed nor counted.
- **`qedro erasure` no longer takes a routine Spark overwrite as the erasure** (#29).
  Spark reports `lifecycleStateChange: OVERWRITE` on every overwriting write, and 0.6.0
  took the latest such event in the window as the instant of the erasure, which on a
  table overwritten nightly is last night's run. Candidates are now completed runs
  rather than events; a drop or truncate is preferred over an overwrite; with `--since`
  the first candidate after it is taken rather than the latest; and several overwrites
  with no `--since` withhold the mark with a reason saying to pass one. More than one
  candidate is stated in the scope, and the JSON tombstone gains `candidates` and
  `chosen_by_since`. An overwrite is now described as one — `emitted overwrite, not a
  drop or truncate` — rather than as the erasure.
- **`qedro events` said `0 pages` of a directory it read nothing in.** The noun now
  follows the source, so a directory is counted in files whatever the count.

## 0.6.0 — 2026-09-30

Nothing here changes what a projection produces. This release is for somebody trying
qedro for the first time: the package now carries its own demo, and there is a guide
for running it against your own lineage. The version counts releases and the v0.6
milestone counts planned work, so 0.6.0 does not include the store that milestone
describes; that is still gated on #15.

- **`qedro demo`** writes the demo company into an empty directory and prints the
  commands that run each projection against it, so an installed package is enough to
  try the tool without cloning the repository. The lineage is generated when the
  command runs, which keeps the wheel at a few kilobytes more rather than 1.5 MB. It
  refuses a directory that already has anything in it, including the default `./demo`.
  Every command it prints is run by the test suite.
- **`docs/pilot.md`** covers a first run against your own events: what you need, where
  qedro can read your events from, how to keep a raw copy with a composite OpenLineage
  transport when your backend cannot give them back, and what standard emitters leave
  out. `docs/compatibility.md` now records what each managed catalog can return — Amazon
  DataZone the posted event, Google Dataplex not the custom facets, DataHub and
  OpenMetadata only their own model.
- **Two known problems**, found while writing the guide and not fixed in this release. A
  file whose name does not end in `.json`, `.ndjson` or `.jsonl` is skipped without
  being counted (#28), which is what an appending OpenLineage file transport writes by
  default. And `qedro erasure` takes a routine Spark overwrite in the window as the
  instant of the erasure (#29); the output shows both instants when they differ.

## 0.5.0 — 2026-09-24

A fourth projection, and the existing chain reaching one hop further out.

`qedro erasure` (#4) answers the part of Art. 17 that lineage is actually for. Finding
where a subject's data lives is a catalog's job and deleting it is an orchestrator's;
proving the deletion reached everything derived from it, and naming the places the
proof does not reach, is what the downstream closure of a dataset is. `provenance`
(#25) now names the application release behind the data a run read, rather than
stopping at the commit behind the pipeline.

Neither invents a facet. The erasure instant comes from the standard
`lifecycleStateChange`, and where nothing emitted one the record says the instant was
typed rather than proved.

- **`qedro erasure`** — what descends from a dataset somebody erased, and whether the
  erasure reached it (#4). Walks the lineage graph forwards from the erased dataset and
  reports every dataset derived from it, transitively, with whether a job rewrote each
  one afterwards. The descendants nothing rewrote are **named rather than counted**:
  that list is the output, and it is the answer Art. 17 conversations rarely give.
- **The tombstone is evidence or an assertion**, and no facet had to be invented for
  it. OpenLineage has `lifecycleStateChange`, whose `DROP`, `TRUNCATE` and `OVERWRITE`
  are erasures and whose `ALTER`, `CREATE` and `RENAME` are not — a rename is not a
  deletion. An emitted one is the instant somebody proved; `--since` is the same instant
  typed by hand, works against any lineage, and withholds the mark. Where both exist the
  emitted one wins and both are printed.
- **It reports datasets, not rows**, in every format and on runs that earn the mark as
  much as on runs that do not. It can show that a dataset descends from the erased one
  and that a job rewrote it afterwards; no lineage event says a particular data
  subject's rows are gone, and this never implies otherwise.
- **`provenance` names the application release behind the data a run read** (#25), one
  hop further out than the commit behind the pipeline. Read from
  `cordata_provenance.source_published_by` and `.source_published_release`, with
  `source_schema_version` and `source_table` naming what was published — so the step
  says *version 7 of fraud_raw.transactions, published by catalog-loader release
  2026.07.3* rather than leaving the claim floating.
- **An unknown publisher is counted, not a withholding reason.** The signature withholds
  because the chain claims authorisation and cannot show it; a missing publisher says
  nothing about authorisation, so it joins the commit and signature counts in the scope
  statement. The rule this settles, for the next field somebody adds: the mark is
  withheld for what the chain claims and counted for what it merely covers.
- **Absent reads as unknown, never as unpublished**, as the signature does. An unset
  field means the catalog recorded no producer for that version, or the run read
  nothing.
- **The demo estate carries an erasure**: `acme.crm/subject-erasure` overwrites
  `crm_raw.contacts` on 2026-07-22 and emits the lifecycle facet, so the evidenced path
  runs against committed events. Two of its three descendants were rewritten in time
  and the weekly dunning job was not, which is the hole the record names. The erasure
  job is itself in the Art. 30 record, because honouring a right is processing.

## 0.4.0 — 2026-09-20

Comparing two records without a database (#14), and checking a hand-maintained
register against one (#24). Both answer a question no single record can: a purpose
emitted by the pipeline and the same purpose typed into a mapping file are the same
string and a different claim, and only a comparison can say which one you have now.

Neither prints the mark. ∎ means *this artefact stands on its own evidence*, and a
comparison's evidence is two documents it cannot verify.

- **`qedro diff before.json after.json`** — what changed between two records, with no
  database between them (#14). The finding it exists for is invisible in either
  document alone: a purpose emitted by the pipeline and the same purpose read from
  the mapping file are the same string and a different claim, so the provenance
  order decides what counts as a loss of evidence, and `fraud-detection, unchanged —
  evidence lost: emitted facet → mapping file` is a finding rather than a silence.
  All four formats, and a JSON consumer gets `loses_evidence` stated rather than
  having to know how `Provenance` is ordered.
- **`qedro diff register.yaml record.json`** — where a hand-maintained register and
  the generated record disagree (#24). Same command, dispatching on what each side
  is, and the order of the two paths does not matter. The finding says which side
  rests on evidence: a register contradicting an emitted facet is a different problem
  from two hand-maintained documents disagreeing, and a register naming something the
  record has no field for is a third. Every finding carries the **owner** of the
  register row, which is what turns a list of disagreements into a list of things
  somebody can do.
- **A comparison prints no mark, in any format.** ∎ means *this artefact stands on
  its own evidence*, and a comparison's evidence is two documents it cannot verify.
  It reports each record's own verdict instead — so a field that was wrong in both
  records is reported as unchanged, and unchanged is not the same as correct.
- **What is comparable is said before anything else**: a different source, and
  windows that are identical, overlapping, adjacent, disjoint or unknown. The one
  refusal is two documents of different shape. A difference in coverage is reported
  as a difference in coverage and never attributed to a particular finding, because
  that attribution would be a guess wearing a caveat.
- **A field the register does not carry is not a disagreement.** A register is a
  partial document by nature — it says nothing about residency or retention — and
  reporting everything it omits would bury the findings that matter. Nor is a
  difference of provenance between the two sides: a register is declared and a record
  evidenced by construction, so that is what the two documents *are*.
- **Art. 30 content is compared, volume is not.** Runs, events and timestamps differ
  between any two windows, and reporting them would bury the findings that matter
  under arithmetic — both numbers are already in the two scope statements.
- **Every JSON document says what it is**, in a `qedro` block at the top: `schema`
  (an integer, 1, which changes only when a consumer reading the old shape would now
  be wrong), `projection`, `view` where there is one, and the `version` that produced
  it. `qedro diff` (#14) has to refuse two documents of different shape, and it can
  only refuse what it can name — inferring the projection from which keys are present
  is a guess. There is deliberately **no generation timestamp**: two runs over the
  same events produce the same bytes, or every diff reports a change that is not a
  change in processing.
- **Breaking, deployer view JSON:** the top-level `"view": "deployer"` key is now
  `qedro.view`. Which document this is has one spelling rather than two.
- **`demo/register.yaml`**, four rows and four ways a register drifts: one still true,
  one whose purpose the pipeline changed, one for a pipeline that no longer exists,
  and one naming a model version no run ever reported. `docs/evidence/register-drift.md`
  is that comparison captured, and CI now checks both transcripts against what the
  commands actually print.
- **Real Flink lineage as a test fixture**, `tests/fixtures/flink-1.20.5`: Flink 1.20.5
  with `openlineage-flink` 1.53.0 and a Kafka topic on each side. The capture names its
  source on `START` and no datasets at all on the terminal event, which is what an
  activity's datasets being gathered across a job's events now has a fixture for.
- **The `processing` facet has a second implementation**, and the docs point at it:
  [`art30-emit`](https://github.com/cordata-tech/art30-emit) puts the facet on the
  wire from code no integration reaches — a Lambda, a stored procedure, a cron job —
  as a context manager or a command wrapper. Nothing in this package changes;
  `docs/art30-facet.md` and `docs/compatibility.md` stop describing that emitter as
  wanted and start linking to it.
- **Its events are a fixture here too**, `tests/fixtures/art30-emit-0.1.0`, because a
  `works` row has to be named by a test in this repository rather than in the thing it
  is a claim about. It is the first capture carrying a `tags` dataset facet from a
  real emitter — no integration sends one as of 1.53.0 — so the Art. 30(1)(c)–(f)
  path is no longer exercised against generated events alone, and the first where one
  activity classifies what it reads and what it writes differently.
- **`1 of 1 dataset carries no classification`**, not `carry`. The noun agrees with the
  total and the verb with the count, and the Flink capture — one job, one dataset — is
  where that showed.

## 0.3.0 — 2026-09-19

The rest of Art. 30(1) that evidence can supply (#13). The record stops covering two
of the seven items the regulation lists and starts covering all seven, with the two
nothing emits marked as assertions wherever they appear.

- **The vocabulary carries the classification terms** an Art. 30 record needs:
  `data_category` and `subject_type` open, because the categories an organisation
  processes and whose data it holds are its own; `special_category` closed on the
  Art. 9(1) list, for the same reason `legal_basis` is closed on Art. 6(1);
  `residency` and `retention` from the reference ontology. Every value says what it
  means, because a list of values without that is a dropdown rather than an ontology.
- **The demo estate carries classification**, in both tiers: the datasets emit the
  standard `tags` facet, so the record reports categories, data subjects, residency and
  retention. Two datasets carry none on purpose — a vendor feed and a table nobody got
  round to — because an estate where everything is classified is not an estate anybody
  has, and the record has to say which is which.
- **The two items nothing emits can be asserted**: Art. 30(1)(d) categories of
  recipients and (g) security measures, in a `jobs:` rule or in the declared-activities
  document. Every format marks them as declared, and asserting them does not withhold
  the mark — there is no evidenced case to fall short of. The Art. 30(1) line now says
  the record has a field for all seven items, and which two can only ever be declared.
- **The Art. 30 record reports what the data is**, from the standard `tags` dataset
  facet: categories of personal data and of data subjects, residency and retention,
  each with the datasets that carried it and which side they were on. Nothing is
  inferred from a column name, a classification is never carried from one dataset to
  another, and the datasets that carry none are counted and named — *nobody said* is
  not *no personal data*. A value outside a closed term withholds the mark; a missing
  classification does not. The scope statement counts how many activities report a
  value for each item, because a field is not an answer.
- **The reader reads the standard `tags` dataset facet**, including `field`-level tags
  that classify one column. The spec has carried it since `1-0-0` and the clients
  generate it, but no OpenLineage integration emits it as of 1.53.0, so absent means
  nothing reported it, never that nothing applies.

## 0.2.0 — 2026-09-18

> **First public release**, and the first version on PyPI.
>
> **0.1.0 was never released.** It was tagged locally on 2026-08-22 and deliberately
> not published, so that Qedro could first be run against real work. That run found
> the orchestration-parent, guessed-domain, Art. 30(1), file-naming and read-only
> changes below, and publishing 0.1.0 would have shipped a record that overstated
> what it covers. Everything that was in 0.1.0 is included in this entry, and there
> is no separate 0.1.0 to upgrade from.

First release. Three projections over OpenLineage, four output formats, and no
adoption of anything required beyond lineage a platform already emits.

### The reader

- `qedro events` reads a directory of `.json`, `.ndjson` or `.jsonl`, walking
  nested directories, or any Marquez-compatible HTTP API. Any spelling of the
  address works — a bare host, `.../api/v1`, or the full endpoint.
- The window is passed to the backend **and applied again to what comes back**,
  so a backend that ignores it produces a correct result rather than a quietly
  wider one.
- Reading stops after 10,000 events and says so, rather than returning a prefix
  of the history that looks like all of it.
- Malformed records are skipped and counted, never raised on, and the count
  reaches the completeness decision.
- Read-only by construction: `GET` is the only verb the code can build. A token
  comes from `QEDRO_API_TOKEN` and never from the command line, where it would
  land in shell history and in `ps`.

### `qedro ropa` — the Art. 30 record

- One activity per job, with the purpose and lawful basis that job declared and
  **where each field came from**. A value from an emitted facet is evidence; the
  same string from `qedro.yaml` is an assertion, and the two never merge.
- A facet always beats the mapping file. A config that could silently rewrite
  emitted evidence would make the record unfalsifiable.
- `qedro.yaml` — controller, domains and job patterns — read as YAML, JSON or
  TOML, with no behaviour depending on which.
- The Art. 30 processing facet is published as a spec in
  `schemas/openlineage-art30-processing-facet.json`, generated from
  `pipeline_runtime.descriptor.Processing` rather than written beside it.
- **Orchestration parents are not listed as activities.** A job whose run is named
  as a parent through the standard `ParentRunFacet`, and which read and wrote nothing
  and carries no `processing` facet, is named in the scope statement instead. The job
  count still includes it, and it does not withhold the mark. Found against real dbt
  lineage, where the invocation job showed up as an extra activity.
- **Activities that read datasets and wrote none are named** on a `read only` line in
  the Art. 30 scope statement, and in JSON as `scope.read_only`. They stay listed, and
  the mark is not withheld for them. Found against real Spark lineage, where the
  integration emits a job for each schema-reading action.
- **File datasets print as a URI**, `file:///data/raw/orders.csv`, instead of
  `file//data/raw/orders.csv`. The Airflow provider and the Spark integration emit
  the bare namespace `file` where the OpenLineage naming conventions give
  `file://{host}`, and an absolute path as the name; a name that starts with `/` is
  no longer given a second one, which also covers HDFS. No other dataset key
  changes, and `provenance --dataset` accepts the new spelling, the file name alone,
  or the old spelling.
- **Real Airflow and Spark lineage as test fixtures**, beside the dbt capture:
  Airflow 3.3.1 with the OpenLineage provider 2.20.1, and Spark 4.2.0 with
  openlineage-spark 1.53.0. The parent rule leaves out the Airflow DAG run and the
  Spark application run. `docs/compatibility.md` now names the captures, and no
  longer says dbt, Airflow and Spark emit `sourceCodeLocation`, which none of the
  captures carries.
- **The Art. 30 record states which Art. 30(1) items it has fields for**, on every
  run including one that earns the mark: (a) the controller and (b) the purposes, and
  none for (c) to (g). It is a scope line rather than a reason to withhold the mark,
  because it would otherwise fire on every run. JSON carries `scope.art30` as lists of
  covered and not covered letters. The deployer view does not repeat it.
- The text scope statement wraps long values under the value instead of running past
  the terminal width.
- **A guessed domain is said to be guessed.** When `domains:` is set, the scope
  statement names the domains guessed from the job namespace and those set by a
  rule's `domain:`, and the silent-domain reason names the guess and the override.
  JSON carries `domains_guessed`, `domains_mapped`, and a `domain_source` per
  activity. Found against real dbt lineage, whose default namespace `dbt` made a
  declared domain look silent.
- `--activities` reads a separate document of **declared activities**, meaning
  processing that emits no lineage. They appear beside the evidenced activities with
  every field marked `declared` and `no lineage` where the events would have spoken,
  are counted on their own line in the scope statement without changing the evidenced
  counts, and withhold the mark. The out-of-view sentence is reworded so that it is
  true whether or not anything is declared.

### `qedro ropa --view deployer` — the same record, per AI use case

- For each activity whose runs reported a model version: purpose and legal basis,
  the model versions with their run counts and dates, the inputs the latest run read,
  and the span of run records in view.
- Built from the Art. 30 record object, so purpose and legal basis are the record's
  own entries with their provenance, not a second reading of the events.
- The model version is read from the standard OpenLineage `tags` run facet (key
  `model_version`) or from `cordata_provenance.step_params`, where `pipeline-runtime`
  puts it.
- Art. 26 of the AI Act is cited from the consolidated text (CELEX
  02024R1689-20260727) with its condition: Annex III high-risk systems, from
  2 December 2027. The view does not decide whether a use case is high-risk.
- Retention is reported as the span of run records in view, never as a retention
  policy, and a short span does not withhold the mark.
- Declared activities that name a `model` are listed as AI use cases, marked
  `declared, no lineage`, and withhold the mark.

### `qedro quality` — the assertion history

- What was checked about each dataset and when, from the standard OpenLineage
  `dataQualityAssertions` facet that Great Expectations already emits.
- **Datasets with no assertions are half the artefact**, not a footnote: a
  dataset with no failures and a dataset with no checks look identical in every
  summary anybody writes, and they are opposites.
- A *failing* expectation does not withhold the mark. The mark says this account
  of what was checked is complete, not that the data is good.
- `--domain` narrows it, repeatably; `--days` is shorthand for the window. The scope
  statement names the filter and how many datasets it left out, in which domains, and
  whether each domain was guessed from the job namespace. A filter that leaves out
  every dataset says so, instead of reporting that no datasets were found.

### `qedro provenance` — the chain back to a commit

- Walks backwards from a dataset through the runs that produced it, the code
  each run executed and the commit it was at, using the standard
  `sourceCodeLocation` facet that dbt, Airflow and Spark all emit.
- **Unknown is not unsigned.** OpenLineage has no standard place for whether a
  commit was signed, so silence is a third state: it withholds the mark exactly
  as a failed signature would and is never rendered as one. `json` emits `null`,
  not `false`.
- A chain ends for three different reasons — a genuine source, a producing run
  outside the window, or the depth limit — and each is counted and named.
- An ambiguous `--dataset` is answered with the candidates rather than a guess.

### Output

- `text`, `markdown`, `json` and `xlsx`. The format follows `--out`'s filename
  unless `--format` says otherwise.
- **xlsx puts the verdict above the table on the first sheet.** A caveat below
  the data is a caveat nobody reads.
- Every format states the scope of what was looked at, on every run including
  one that earns the mark.

### The mark

- `∎` is printed only when an artefact stands on its own evidence, and the
  reasons for withholding it are always printed with it. `--no-symbol`, or
  `QEDRO_NO_SYMBOL=1`, for terminals with no glyph for U+220E.

### Also

- `demo/` — three weeks of synthetic lineage from dbt, Airflow and Spark, with
  no AWS anywhere in it, in two estates that differ only in whether the
  pipelines declare their Art. 30 fields.
- Apache-2.0. Python 3.12, 3.13 and 3.14.
