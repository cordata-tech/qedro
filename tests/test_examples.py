"""The example lineage the README draws its erasure tree from.

The picture is redrawn by hand (`tools/readme_image.py` needs pypdfium2), so
what is checked here is the input: that the file is what its generator writes,
and that the tree it gives still shows every state the caption says it does.
"""

from __future__ import annotations

import tools.erasure_example as example

from qedro import config, erasure
from qedro.sources import read


def test_the_file_is_what_the_generator_writes():
    assert example.PATH.read_text(encoding="utf-8") == example.rendered()


def test_one_tree_shows_every_state_a_descendant_can_be_in():
    events, report = read(str(example.PATH.parent))
    record = erasure.build(
        events,
        dataset="warehouse/crm_raw.contacts",
        config=config.parse("controller: ACME Finanz GmbH\n"),
        report=report,
    )
    assert record.tombstone.evidenced
    assert {d.how for d in record.descendants} == {"rebuilt", "written", "appended", ""}
    # Branching, not a chain: the reason this exists beside the demo.
    assert max(d.depth for d in record.descendants) == 3
    assert sum(d.depth == 1 for d in record.descendants) == 2
    assert not record.complete


def test_the_text_record_nests_each_descendant_under_its_parent():
    # The walk is breadth-first; printed in that order and indented by depth,
    # `invoices` sat under `marketing.audiences` instead of `customers`.
    from qedro import render

    events, report = read(str(example.PATH.parent))
    record = erasure.build(
        events,
        dataset="warehouse/crm_raw.contacts",
        config=config.parse("controller: ACME Finanz GmbH\n"),
        report=report,
    )
    keys = {d.dataset for d in record.descendants}
    order = [line.strip() for line in render.text(record).splitlines() if line.strip() in keys]
    assert order.index("warehouse/billing_curated.invoices") == (
        order.index("warehouse/crm_curated.customers") + 1
    )
    assert order.index("s3://acme-partner-exports/partner_feed") == (
        order.index("warehouse/marketing.audiences") + 1
    )


def test_every_box_can_say_where_its_data_lives():
    # #39: the reason the warehouse names Snowflake and the feed lives in S3.
    events, report = read(str(example.PATH.parent))
    record = erasure.build(
        events,
        dataset="warehouse/crm_raw.contacts",
        config=config.parse("controller: ACME Finanz GmbH\n"),
        report=report,
    )
    assert record.stored_in == "Snowflake"
    by_key = {d.dataset: d.stack.describe() for d in record.descendants}
    assert by_key["warehouse/crm_curated.customers"] == "dbt · Snowflake"
    assert by_key["s3://acme-partner-exports/partner_feed"] == "Spark · S3"
