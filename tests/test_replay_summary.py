"""R4: replay impact must be reduced within a run, not pooled across points."""

from __future__ import annotations

import unittest

from scripts.reproduce.summarize_replay import summarize


def _row(run_key, solution_id, *, f1=0.0, f2=0.0, representative=False):
    return {
        "run_key": run_key,
        "solution_id": solution_id,
        "decision_hash": f"hash-{solution_id}",
        "planning_model": "v2",
        "case_id": "S025",
        "instance_seed": "101",
        "planning_F1": "1.0",
        "planning_F2": "100.0",
        "planning_F3": "-0.9",
        "replay_F1": str(1.0 + f1),
        "replay_F2": str(100.0 + f2),
        "replay_F3": "-0.9",
        "replay_minus_planning_F1": str(f1),
        "replay_minus_planning_F2": str(f2),
        "replay_minus_planning_F3": "0.0",
        "representative_selected_before_replay": str(representative),
    }


class ReplaySummaryTest(unittest.TestCase):
    def test_a_long_run_does_not_outvote_a_short_one(self):
        """Two runs, one with 10 points and one with 1, weigh the same."""
        rows = [_row("run:PR1_HT1_EC1:a", f"p{i:04d}", f1=0.0) for i in range(10)]
        rows += [_row("run:PR1_HT1_EC1:b", "p0001", f1=1.0)]

        group_rows, run_rows, _representatives = summarize(rows)
        self.assertEqual(len(run_rows), 2)
        self.assertEqual(len(group_rows), 1)
        # The mean of run means is (0 + 1) / 2, not 1 * (1 / 11).
        self.assertAlmostEqual(group_rows[0]["mean_of_run_mean_delta_F1"], 0.5, places=12)
        self.assertEqual(group_rows[0]["runs_with_any_F1_change"], 1)

    def test_sub_resolution_changes_are_not_counted_as_changes(self):
        """The change tolerance is the pinned objective resolution."""
        rows = [
            _row("run:PR1_HT0_EC1:a", "p0001", f1=1e-12),   # noise
            _row("run:PR1_HT0_EC1:a", "p0002", f1=1e-3),    # real
            _row("run:PR1_HT0_EC1:a", "p0003", f1=0.0),
        ]
        _group_rows, run_rows, _representatives = summarize(rows)
        run = run_rows[0]
        self.assertEqual(run["nonzero_solutions_F1"], 1)
        self.assertAlmostEqual(run["max_abs_delta_F1"], 1e-3, places=12)
        self.assertEqual(run["max_abs_delta_F1_solution"], "p0002")

    def test_the_worst_case_reports_where_it_came_from(self):
        rows = [
            _row("run:PR1_HT0_EC1:a", "p0001", f2=0.1),
            _row("run:PR1_HT0_EC1:b", "p0007", f2=12.5),
        ]
        group_rows, _run_rows, _representatives = summarize(rows)
        group = group_rows[0]
        self.assertAlmostEqual(group["worst_run_max_abs_delta_F2"], 12.5, places=12)
        self.assertEqual(group["worst_run_F2"], "run:PR1_HT0_EC1:b")
        self.assertEqual(group["worst_run_F2_solution"], "p0007")
        # Reported as the worst of the run maxima, not as a pooled mean.
        self.assertAlmostEqual(
            group["mean_of_run_mean_delta_F2"], (0.1 + 12.5) / 2, places=12
        )

    def test_groups_are_separated_and_ordered(self):
        rows = [
            _row("run:PR1_HT0_EC1:a", "p0001", f1=0.5),
            _row("run:PR0_HT1_EC1:a", "p0001", f2=3.0),
            _row("run:PR1_HT1_EC1:a", "p0001"),
        ]
        group_rows, _run_rows, _representatives = summarize(rows)
        self.assertEqual(
            [row["model_group"] for row in group_rows],
            ["PR1_HT1_EC1", "PR0_HT1_EC1", "PR1_HT0_EC1"],
        )
        by_group = {row["model_group"]: row for row in group_rows}
        self.assertEqual(by_group["PR1_HT1_EC1"]["runs_with_any_F1_change"], 0)
        self.assertEqual(by_group["PR1_HT0_EC1"]["runs_with_any_F1_change"], 1)
        self.assertEqual(by_group["PR0_HT1_EC1"]["runs_with_any_F2_change"], 1)

    def test_the_representative_is_reported_on_its_own(self):
        rows = [
            _row("run:PR1_HT0_EC1:a", "p0001", f1=0.024, representative=True),
            _row("run:PR1_HT0_EC1:a", "p0002", f1=0.9),
        ]
        _group_rows, _run_rows, representatives = summarize(rows)
        self.assertEqual(len(representatives), 1)
        self.assertEqual(representatives[0]["solution_id"], "p0001")
        self.assertAlmostEqual(
            representatives[0]["replay_minus_planning_F1"], 0.024, places=12
        )


if __name__ == "__main__":
    unittest.main()
