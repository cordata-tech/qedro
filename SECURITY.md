# Security

## Reporting

Email **privacy@cordata.tech**, or open a private advisory through GitHub's
*Report a vulnerability* on this repository. Please do not open a public issue
for anything exploitable.

Expect an acknowledgement within three working days. If a fix is warranted it
ships as a patch release with an entry in the changelog naming what was wrong;
credit is given unless you would rather it were not.

Supported: the most recent `0.x` release. There is no long-term support branch
before `1.0`.

## What this tool can reach, by construction

Worth stating plainly, because it is most of the security posture and it is a
property of the code rather than a policy applied to it.

**No write path exists.** No projection, source or handler can modify anything
it reads. The HTTP source can only build a `GET` request — this is not a check
that could be bypassed, it is the absence of any code that constructs another
verb, and `tests/test_cli.py::TestRopaAgainstAnApi` asserts the requests
actually issued.

**No credential that could acquire one.** If a backend needs a token it comes
from `QEDRO_API_TOKEN` and nowhere else — never a command-line flag, where it
would land in shell history and in the output of `ps`. Nothing is written to
disk except the artefact you asked for, at the path you named.

**Buckets use your environment's credentials, so give them a read-only role.**
Reading an `s3://`, `gs://` or `az://` prefix goes through the cloud's own
credential chain — an AWS profile or instance role, Google's application default
credentials, Azure's — which qedro neither stores nor takes as a flag. Those
credentials are yours and may allow writing. The code cannot use that: the bucket
reader holds a wrapper exposing listing and reading only, and
`tests/test_sources.py::TestReadingABucket::test_it_can_only_list_and_read` hands it
a filesystem that fails on any other call. A role limited to listing and reading
(`s3:ListBucket` and `s3:GetObject`, `roles/storage.objectViewer`, *Storage Blob Data
Reader*) makes the same true of the credentials. On S3, set `AWS_REGION` as well, or
add `s3:GetBucketLocation`, which is also read-only: without a region the library asks
the bucket where it is before reading it.

**Nothing is sent anywhere.** No telemetry, no update check, no analytics. The
only network traffic is reading from the source address you passed, and for a
bucket whatever the cloud's credential chain does to obtain credentials.

**User documents are parsed, never executed.** `qedro.yaml` and vocabulary
documents go through `yaml.safe_load` or `tomllib`, so nothing in a config file
can construct a Python object.

## What is in the artefacts

An Art. 30 record contains job names, dataset names, purposes, lawful bases and
run counts — metadata about processing rather than the data being processed. The
quality and provenance artefacts add expectation names, commit identifiers and
repository URLs.

**A repository URL is printed without any credentials it carried.** An emitter
that sends a git remote as configured can put a token in it — a CI checkout
commonly leaves `https://x-access-token:<token>@github.com/…` behind — so qedro
removes the userinfo of an http or https URL, and the password of any other, where
it reads the URL, before any record holds it. `tests/test_provenance.py::TestARepositoryUrlNeverCarriesCredentials`
checks every output format for the token. Dataset namespaces are not rewritten:
the OpenLineage naming rules keep credentials out of them, and qedro uses them as
dataset identity.

**But the input can be more sensitive than the output.** OpenLineage schema
facets carry column names, and column names can be disclosive on their own: the
demo estate has `iban` and `device_fingerprint` in it. Qedro reads those and does
not put them in a record, but the events themselves deserve the handling their
contents warrant.

## Dependencies

Two at runtime — `pyyaml` and `openpyxl` — chosen partly for how little each
brings with it. Both are widely used and neither executes anything from a
document it parses.

Reading a bucket adds more, and only when you ask for it: the `s3`, `gcs` and
`azure` extras install `fsspec` with `s3fs`, `gcsfs` or `adlfs`, which bring each
cloud's client libraries. A plain `pip install qedro` installs none of them.

## Not a compliance verdict

An artefact this produces is evidence about processing, not a statement that an
obligation is met. Reading it as a verdict is a misuse the wording works to prevent:
the scope statement says what was looked at, the mark says only that what was found
stands on emitted evidence, and both are printed on every run. A defect that makes an
artefact claim more than that is a security issue here, and is listed as one above.

## Scope

In scope: anything that lets a crafted lineage event, config file or vocabulary
document cause code execution, a file write outside `--out`, a network request
to an address you did not name, or **an artefact that claims to be a proof when
it is not**. That last one is a security issue here in a way it would not be
elsewhere: the tombstone is a claim somebody may rely on in front of a regulator.

Out of scope: the contents of lineage you point it at, and anything requiring an
attacker who can already run code as you.
