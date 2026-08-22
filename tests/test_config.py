"""`qedro.yaml` — the controller, the scope, and the mapping fallback."""

from __future__ import annotations

import pytest

from qedro import config
from qedro.errors import ConfigError


class TestTheController:
    def test_a_mapping(self):
        loaded = config.parse("controller:\n  name: ACME GmbH\n  contact: dpo@acme.example\n")
        assert loaded.controller.name == "ACME GmbH"
        assert loaded.controller.contact == "dpo@acme.example"

    def test_a_bare_string_is_read_as_the_name(self):
        # What people write first, and reading it costs nothing.
        assert config.parse("controller: ACME GmbH\n").controller.name == "ACME GmbH"

    def test_a_controller_section_with_no_name_raises(self):
        with pytest.raises(ConfigError, match="no `name`"):
            config.parse("controller:\n  contact: dpo@acme.example\n")

    def test_absent_is_not_an_error_here(self):
        # The projection decides what a missing controller means for the
        # artefact. Parsing does not.
        assert not config.parse("domains: [a]\n").controller


class TestTheMappingPatterns:
    def test_matches_namespace_and_name(self):
        loaded = config.parse('jobs:\n  "cordata.fraud/*": {purpose: p}\n')
        assert loaded.rule_for("cordata.fraud", "scored-daily")
        assert not loaded.rule_for("cordata.policy", "scored-daily")

    def test_matches_the_bare_name_too(self):
        loaded = config.parse('jobs:\n  "*.validate": {purpose: qa}\n')
        assert loaded.rule_for("anything", "job.validate")

    def test_first_match_in_file_order_wins(self):
        # Order in the file, not a specificity rule, so a reader can resolve a
        # job by reading down the page.
        loaded = config.parse(
            "jobs:\n"
            '  "cordata.fraud/scored": {purpose: specific}\n'
            '  "cordata.fraud/*": {purpose: general}\n'
        )
        rule = loaded.rule_for("cordata.fraud", "scored")
        assert rule is not None and rule.purpose == "specific"

    def test_order_is_not_alphabetical(self):
        loaded = config.parse('jobs:\n  "z/*": {purpose: first}\n  "*": {purpose: second}\n')
        rule = loaded.rule_for("z", "j")
        assert rule is not None and rule.purpose == "first"

    def test_case_matters(self):
        # fnmatchcase, not fnmatch: on macOS the case-folding default would
        # make a config behave differently than on Linux, and a compliance
        # artefact that depends on the developer's laptop is not one.
        loaded = config.parse('jobs:\n  "Fraud/*": {purpose: p}\n')
        assert not loaded.rule_for("fraud", "j")


class TestTypoesAreToldAbout:
    def test_an_unknown_key_raises_rather_than_being_ignored(self):
        # `legalbasis:` silently ignored produces a record with a hole in it
        # and no indication why.
        with pytest.raises(ConfigError, match="unknown keys: legalbasis"):
            config.parse('jobs:\n  "*": {purpose: p, legalbasis: consent}\n')

    def test_the_message_says_what_is_allowed(self):
        with pytest.raises(ConfigError, match="Allowed: domain, legal_basis, purpose"):
            config.parse('jobs:\n  "*": {nonsense: 1}\n')


class TestAnyFormatTheUserPrefers:
    def test_json(self):
        loaded = config.parse('{"controller": "ACME", "domains": ["fraud"]}', origin="qedro.json")
        assert loaded.controller.name == "ACME" and loaded.domains == ("fraud",)

    def test_toml(self):
        loaded = config.parse(
            'controller = "ACME"\ndomains = ["fraud"]\n[jobs."a/*"]\npurpose = "p"\n',
            origin="qedro.toml",
        )
        assert loaded.controller.name == "ACME"
        assert loaded.rule_for("a", "b")

    def test_finding_one_beside_the_working_directory(self, tmp_path):
        (tmp_path / "qedro.toml").write_text('controller = "T"\n', encoding="utf-8")
        found = config.find(None, start=tmp_path)
        assert found is not None and found.name == "qedro.toml"

    def test_yaml_wins_when_several_exist(self, tmp_path):
        # Deterministic rather than glob order, so two machines agree.
        (tmp_path / "qedro.toml").write_text('controller = "T"\n', encoding="utf-8")
        (tmp_path / "qedro.yaml").write_text("controller: Y\n", encoding="utf-8")
        found = config.find(None, start=tmp_path)
        assert found is not None and found.name == "qedro.yaml"


class TestAbsenceVersusError:
    def test_no_config_at_all_is_fine(self, tmp_path):
        # A run against pipelines that all emit the facet needs no mapping,
        # and that is the case worth making easy.
        assert config.find(None, start=tmp_path) is None
        assert not config.load(None).present

    def test_an_empty_file_is_fine(self):
        # A placeholder somebody committed intending to fill it in.
        assert config.parse("").present

    def test_a_named_file_that_is_missing_raises(self, tmp_path):
        # The user named it and meant it.
        with pytest.raises(ConfigError, match="no config file at"):
            config.find(tmp_path / "absent.yaml")
