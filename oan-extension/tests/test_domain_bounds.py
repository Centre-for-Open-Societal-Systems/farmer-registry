import importlib.util
from datetime import date
from pathlib import Path

import pytest

SERVICES = (
    Path(__file__).parents[1]
    / "src/oan_farmer_registry_extension/register_domain/services"
)


def load(name):
    spec = importlib.util.spec_from_file_location(name, SERVICES / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bounds, widgets = load("domain_bounds"), load("widget_rules")
say = widgets._Say(
    {"year_of_acquisition": "Year of Acquisition", "collected_date": "Count Date"}
)


@pytest.mark.parametrize("year", [1900, 2026, 2026.0, "2026", "2026.0"])
def test_acquisition_year_in_range(year):
    assert (
        bounds.check_domain_bounds(
            [{"year_of_acquisition": year}], "Land", {}, say, date(2026, 10, 25)
        )
        == []
    )


@pytest.mark.parametrize("year", [1899, 2027, True, "bad", 2025.5])
def test_acquisition_year_outside_range(year):
    assert bounds.check_domain_bounds(
        [{"year_of_acquisition": year}], "Land", {}, say, date(2026, 10, 25)
    ) == [
        "Year of Acquisition: enter a whole year from 1900 to 2026, or leave it empty."
    ]


def test_count_date_today_and_future():
    assert (
        bounds.check_domain_bounds(
            [{"collected_date": "2026-10-25"}], "Livestock", {}, say, date(2026, 10, 25)
        )
        == []
    )
    assert bounds.check_domain_bounds(
        [{"collected_date": "2026-10-26"}], "Livestock", {}, say, date(2026, 10, 25)
    ) == ["Count Date: the date is in the future. Choose today or an earlier date."]
