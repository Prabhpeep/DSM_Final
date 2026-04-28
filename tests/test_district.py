"""
Tests for the gazetteer-based district classifier.

Run: `python -m pytest tests/test_district.py -v`
"""
from __future__ import annotations

import pytest
from pathlib import Path
import sys

# Ensure project root is on sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.classifiers.district import (
    load_gazetteer,
    classify,
    detect_title_mismatch,
    _exact_substring_match,
    _fuzzy_match,
    District,
    Gazetteer,
)

GAZETTEER_PATH = ROOT / "src" / "classifiers" / "assam_gazetteer.yaml"

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def gazetteer() -> Gazetteer:
    """Load the full gazetteer once for all tests."""
    return load_gazetteer(GAZETTEER_PATH)


# --------------------------------------------------------------------------- #
# Gazetteer integrity
# --------------------------------------------------------------------------- #
class TestGazetteerIntegrity:
    def test_has_35_districts(self, gazetteer):
        assert len(gazetteer.districts) == 35

    def test_all_have_names(self, gazetteer):
        for d in gazetteer.districts:
            assert d.name, "District must have a non-empty name"

    def test_all_have_census_codes(self, gazetteer):
        for d in gazetteer.districts:
            assert d.census_code, f"{d.name} missing census_code"

    def test_unique_names(self, gazetteer):
        names = [d.name for d in gazetteer.districts]
        assert len(names) == len(set(names)), f"Duplicate names: {names}"

    def test_no_empty_aliases(self, gazetteer):
        for d in gazetteer.districts:
            for a in d.aliases:
                assert a.strip(), f"{d.name} has an empty alias"

    def test_canonical_name_in_aliases(self, gazetteer):
        """The canonical name should be searchable too."""
        for d in gazetteer.districts:
            assert d.name in d.aliases, \
                f"{d.name} not in its own aliases"


# --------------------------------------------------------------------------- #
# Exact substring matching — known addresses
# --------------------------------------------------------------------------- #
class TestExactMatch:
    # (address, expected_district)
    CASES = [
        # Direct district names
        ("Kokrajhar", "Kokrajhar"),
        ("Dibrugarh", "Dibrugarh"),
        ("GUWAHATI", "Kamrup Metropolitan"),
        ("Barpeta", "Barpeta"),

        # Guwahati-specific landmarks → Kamrup Metropolitan
        ("O/O The CE, PWD (Bldg), Assam, Chandmari, Ghy-3",
         "Kamrup Metropolitan"),
        ("Bijulee Bhawan Guwahati", "Kamrup Metropolitan"),
        ("3rd Floor, Janata Bhawan", "Kamrup Metropolitan"),
        ("Guwahati Municipal Corporation, Panbazar, Guwahati",
         "Kamrup Metropolitan"),
        ("4th Floor Paribahan Bhawan Khanapara",
         "Kamrup Metropolitan"),
        ("SIPRD, Assam, Khanapara, Guwahati-22",
         "Kamrup Metropolitan"),

        # District HQ town names
        ("Central Jail Silchar", "Cachar"),
        ("DFO Karimganj Division", "Karimganj"),
        ("S.E., PWD, Tezpur Building Circle, Tezpur", "Sonitpur"),
        ("SE PWD Silchar Building Circle Silchar", "Cachar"),
        ("Central Jail Nagaon", "Nagaon"),
        ("AAU, Jorhat", "Jorhat"),
        ("Mangaldoi", "Darrang"),
        ("Haflong", "Dima Hasao"),
        ("Diphu", "Karbi Anglong"),
        ("Hamren", "West Karbi Anglong"),

        # Dibrugarh sub-towns
        ("AGCL Duliajan", "Dibrugarh"),
        ("APL Namrup", "Dibrugarh"),
    ]

    @pytest.mark.parametrize("address,expected", CASES)
    def test_exact_address(self, address, expected, gazetteer):
        name, method = classify(address, None, gazetteer)
        assert name == expected, \
            f"'{address}' → {name} (expected {expected})"

    def test_online_is_unclassified(self, gazetteer):
        name, method = classify("Online", None, gazetteer)
        # Online matches entity_name fallback or Unclassified if no entity name provided.
        # But wait! 'Online' doesn't match state_hq 'Online'? No, state_hq is 'Assam', 'NHM' etc.
        assert name == "Unclassified"

    def test_none_address_unclassified(self, gazetteer):
        name, method = classify(None, None, gazetteer)
        assert name == "Unclassified"


# --------------------------------------------------------------------------- #
# Entity name fallback
# --------------------------------------------------------------------------- #
class TestEntityFallback:
    def test_entity_dibrugarh(self, gazetteer):
        name, method = classify(
            "Managing Director",  # no district info
            "Addl. Chief Engineer, UAZ, W. R. Deptt. Dibrugarh",
            gazetteer,
        )
        assert name == "Dibrugarh"
        assert method == "entity_name"

    def test_entity_kokrajhar(self, gazetteer):
        name, method = classify(
            "Online",  # no district
            "SE, PWD (R and B) Circle, Kokrajhar",
            gazetteer,
        )
        assert name == "Kokrajhar"
        assert method == "entity_name"

    def test_address_takes_priority(self, gazetteer):
        """Address match should be preferred over entity match."""
        name, method = classify(
            "Central Jail Silchar",
            "SE PWD Kokrajhar",
            gazetteer,
        )
        assert name == "Cachar", "Address match should win"
        assert method == "address"


# --------------------------------------------------------------------------- #
# Title-district mismatch detection
# --------------------------------------------------------------------------- #
class TestTitleMismatch:
    def test_mismatch_detected(self, gazetteer):
        """Guwahati address but title mentions Nagaon → mismatch."""
        has_mm, title_dist = detect_title_mismatch(
            "Construction of road in Nagaon district",
            "Kamrup Metropolitan",
            gazetteer.districts,
        )
        assert has_mm is True
        assert title_dist == "Nagaon"

    def test_no_mismatch_when_same(self, gazetteer):
        has_mm, _ = detect_title_mismatch(
            "Construction of bridge in Guwahati",
            "Kamrup Metropolitan",
            gazetteer.districts,
        )
        assert has_mm is False

    def test_no_mismatch_when_unclassified(self, gazetteer):
        has_mm, _ = detect_title_mismatch(
            "Construction in Nagaon",
            "Unclassified",
            gazetteer.districts,
        )
        assert has_mm is False

    def test_no_mismatch_when_title_empty(self, gazetteer):
        has_mm, _ = detect_title_mismatch(
            None,
            "Kamrup Metropolitan",
            gazetteer.districts,
        )
        assert has_mm is False


# --------------------------------------------------------------------------- #
# Full pipeline (integration) — only runs if DB exists
# --------------------------------------------------------------------------- #
DB_PATH = ROOT / "db" / "dsm.sqlite"

@pytest.mark.skipif(not DB_PATH.exists(), reason="db/dsm.sqlite not found")
class TestFullPipeline:
    def test_unmatched_rate_below_15_percent(self, gazetteer):
        from src.classifiers.district import load_tenders
        rows = load_tenders()
        total = len(rows)
        unmatched = 0
        for ocid, address, entity_name, title in rows:
            name, method = classify(address, entity_name, gazetteer)
            if name == "Unclassified":
                unmatched += 1
        rate = 100 * unmatched / total
        print(f"\nUnmatched: {unmatched:,} / {total:,} = {rate:.1f}%")
        assert rate < 15, f"Unmatched rate {rate:.1f}% exceeds 15% target"
