import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts.reproduce import mechanism_zone_search as zone
from scripts.reproduce.solution_io import RunStore, SolutionIOError, decision_from_json
from scripts.reproduce.capacity_recovery import evaluate_capacity_solution_detailed
from tests.test_model_contract import _make_instance


class ZoneStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.instance = _make_instance(model_version='v2', suppliers=[0], demands=[1, 2],
            supply_amounts={0: 80}, demand_amounts={1: 50, 2: 50},
            edges=[(0, 1, 10, 1000), (1, 2, 10, 1000)], damaged=[(1, 2, 900)])

    def run_zone(self, *extra):
        argv = ['zone', '--suite', 'benchmark', '--case', 'S025', '--instance-seeds', '101',
                '--solver-repeats', '1', '--max-evaluations', '4', '--pop-size', '4',
                '--output-dir', str(self.root), *extra]
        with patch('sys.argv', argv), patch.object(zone, '_scenario', return_value=self.instance), patch.object(
            zone, 'calibrate_zones', return_value=[(z, 1.0, 0.2) for z, _ in zone.ZONE_TARGETS]):
            zone.main()

    def test_identical_physical_zones_do_not_collide_and_replay(self):
        self.run_zone()
        store = RunStore(self.root)
        records = store.load_all_runs()
        self.assertEqual(len(records), 12)
        self.assertEqual(len({r['physical_instance_hash'] for r in records}), 1)
        for r in records:
            inst = store.load_instance(r['instance_file'])
            store.load_execution_instance(r['physical_instance_hash'], require_full=True)
            for s in r['pareto_front']:
                actual = evaluate_capacity_solution_detailed(inst, decision_from_json(s['decision'], inst))
                self.assertEqual(list(actual.objectives), s['objectives'])

    def test_resume_skips_solver_and_preserves_records(self):
        self.run_zone()
        before = {p.name: p.read_bytes() for p in (self.root / 'runs').glob('*.json')}
        with patch.object(zone, 'solve_benchmark_algorithm', side_effect=AssertionError('solver invoked')):
            self.run_zone('--resume')
        self.assertEqual(before, {p.name: p.read_bytes() for p in (self.root / 'runs').glob('*.json')})

    def test_conflicts_rejected_before_overwrite(self):
        self.run_zone()
        before = {str(p): p.read_bytes() for p in self.root.rglob('*.json')}
        for option in [('--max-evaluations', '8'), ('--instance-seeds', '102'), ('--solver-repeats', '2')]:
            with self.assertRaises(SolutionIOError):
                self.run_zone('--resume', *option)
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.rglob('*.json')})
