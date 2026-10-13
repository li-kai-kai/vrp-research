"""Guard the v2-only entry points and the frozen parallel evidence matrix."""
import csv
import hashlib
import json
import unittest
from collections import defaultdict
from pathlib import Path

from scripts.reproduce.capacity_recovery import EvaluationConfig, build_wenchuan_instance
from scripts.reproduce.objective_precision import V2_PRECISION, precision_for


class CurrentResearchTest(unittest.TestCase):
    def test_default_model_is_v2_and_retired_profiles_are_rejected(self):
        instance = build_wenchuan_instance(seed=1)
        self.assertEqual(instance.evaluation, EvaluationConfig.for_version("v2"))
        self.assertIs(precision_for(instance), V2_PRECISION)
        with self.assertRaises(ValueError):
            EvaluationConfig.for_version("legacy")
        with self.assertRaises(ValueError):
            EvaluationConfig(fair_share_cap=True)

    def test_frozen_parallel_matrix_is_complete_and_consistent(self):
        root = Path(__file__).resolve().parents[1] / "exp" / "full_budget"
        rows = json.loads((root / "results.json").read_text())
        with (root / "results.csv").open() as handle:
            csv_rows = list(csv.DictReader(handle))
        seeds = (11, 22, 33, 44, 55, 66, 77, 88)
        expected = {
            (case, seed, workers)
            for case in ("WEN38", "S025", "S050", "M100")
            for seed in seeds
            for workers in ((0, 1, 2, 4, 8) if case == "WEN38" else (1, 2, 4, 8))
        }
        actual = {(r["case_id"], r["solver_seed"], r["workers"]) for r in rows}
        self.assertEqual(actual, expected)
        self.assertEqual(len(rows), len(expected))
        self.assertEqual(len(csv_rows), len(rows))
        by_key = {(r["case_id"], int(r["solver_seed"]), int(r["workers"])): r for r in csv_rows}
        groups = defaultdict(list)
        for row in rows:
            self.assertEqual(row["evaluations"], row["max_evaluations"])
            self.assertEqual(len(row["front"]), row["front_size"])
            key = (row["case_id"], row["solver_seed"], row["workers"])
            self.assertEqual(float(by_key[key]["runtime_seconds"]), row["runtime_seconds"])
            self.assertEqual(float(by_key[key]["hypervolume"]), row["hypervolume"])
            self.assertEqual(float(by_key[key]["igd"]), row["igd"])
            groups[key[:2]].append(row)
        for group in groups.values():
            baseline = min(group, key=lambda row: row["workers"])
            for row in group:
                for field in ("front", "cache_hits", "hypervolume", "igd"):
                    self.assertEqual(row[field], baseline[field])

    def test_retained_evidence_matches_its_frozen_checksums(self):
        root = Path(__file__).resolve().parents[1]
        inventory = json.loads((root / "docs/evidence_inventory.json").read_text())
        self.assertGreater(len(inventory["files"]), 0)
        for row in inventory["files"]:
            with self.subTest(path=row["path"]):
                data = (root / row["path"]).read_bytes()
                self.assertEqual(len(data), row["bytes"])
                self.assertEqual(hashlib.sha256(data).hexdigest(), row["sha256"])
