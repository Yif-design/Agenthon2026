from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import date, timedelta

from evaluation.rolling_origin import Observation, chronological_splits, run_rolling_origin


def sample_observations() -> list[Observation]:
    rows = []
    base = date(2020, 1, 1)
    for index in range(15):
        origin = base + timedelta(days=30 * index)
        resolution = origin + timedelta(days=10)
        for entity, offset in (("A", 0.0), ("B", 10.0)):
            rows.append(Observation(
                family="synthetic",
                event_id=f"event-{index}",
                entity_id=entity,
                origin_date=origin,
                resolution_date=resolution,
                target=float(index) + offset,
                target_kind="level",
                season_period=4,
                features={"production_rule": "fallback"},
            ))
    return rows


class RollingOriginTest(unittest.TestCase):
    def test_future_outcome_cannot_change_earlier_predictions(self) -> None:
        original = sample_observations()
        baseline = run_rolling_origin(original)
        changed = [replace(row, target=99999.0) if row.event_id == "event-14" else row for row in original]
        candidate = run_rolling_origin(changed)
        before = date(2021, 1, 1)
        left = [(row.event_id, row.entity_id, row.predictions) for row in baseline if row.origin_date < before]
        right = [(row.event_id, row.entity_id, row.predictions) for row in candidate if row.origin_date < before]
        self.assertEqual(left, right)

    def test_same_origin_entities_do_not_leak_into_each_other(self) -> None:
        rows = sample_observations()
        changed = [replace(row, target=-5000.0) if row.event_id == "event-8" and row.entity_id == "A" else row for row in rows]
        baseline = run_rolling_origin(rows)
        candidate = run_rolling_origin(changed)
        expected = next(row for row in baseline if row.event_id == "event-8" and row.entity_id == "B")
        actual = next(row for row in candidate if row.event_id == "event-8" and row.entity_id == "B")
        self.assertEqual(expected.predictions, actual.predictions)

    def test_training_resolutions_are_strictly_before_origin(self) -> None:
        for row in run_rolling_origin(sample_observations()):
            if row.latest_training_resolution is not None:
                self.assertLess(row.latest_training_resolution, row.origin_date)

    def test_splits_are_chronological_and_deterministic(self) -> None:
        rows = sample_observations()
        splits = chronological_splits(rows)
        names = [splits[("synthetic", origin)] for origin in sorted({row.origin_date for row in rows})]
        self.assertEqual(names, sorted(names, key={"development": 0, "time_forward_test": 1, "confirmation": 2}.get))
        self.assertEqual(run_rolling_origin(rows), run_rolling_origin(list(reversed(rows))))


if __name__ == "__main__":
    unittest.main()
