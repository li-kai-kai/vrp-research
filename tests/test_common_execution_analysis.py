"""Behavioral regression checks for paired replay and evidence boundaries."""
import csv
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts.reproduce.benchmark_algorithms import BenchmarkBudget
from scripts.reproduce.common_execution_analysis import analyze, aggregate, changed, PAIR_METRICS
from scripts.reproduce.run_model_ablation import run_model_ablation
from scripts.reproduce.run_benchmark import _non_dominated, pooled_quality_indicators
from scripts.reproduce.objective_precision import V2_PRECISION
from scripts.reproduce.solution_io import RunStore, SolutionIOError


class AnalysisTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = TemporaryDirectory()
        cls.root = Path(cls.tmp.name) / 'input'
        run_model_ablation(suite='benchmark', cases=['S025'], instance_seeds=[101],
                           solver_repeats=1, algorithm='nsga2', model_version='v2',
                           model_ids=['PR1_HT1_EC1', 'PR0_HT1_EC1', 'PR1_HT0_EC1', 'PR1_HT1_EC0'],
                           budget=BenchmarkBudget(8, 4), output_dir=cls.root)
        cls.store = RunStore(cls.root)
        cls.records = cls.store.load_all_runs()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        for record in self.records:
            self.store.save_run(record)
        self.out = Path(self.tmp.name) / 'analysis'

    def mutate(self, change):
        record = json.loads(json.dumps(self.records[0]))
        change(record)
        self.store.save_run(record)

    def test_valid_replay_and_trace(self):
        report = analyze([self.root], self.out, True)
        self.assertEqual(report['counts']['execution_runs'], 4)
        self.assertEqual(report['counts']['execution_pairs'], 3)
        self.assertEqual(report['self_replay_max_abs_error'], [0, 0, 0])
        with (self.out / 'execution_runs.csv').open() as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual({r['representative_hash'] for r in rows}, {r['decision_hash'] for r in self.records})

    def test_duplicate_roots_rejected(self):
        with self.assertRaisesRegex(SolutionIOError, 'duplicate input'):
            analyze([self.root, self.root], self.out)

    def test_missing_model_rejected(self):
        path = self.store.run_path(self.records[0]['run_key'])
        path.unlink()
        with self.assertRaisesRegex(SolutionIOError, 'missing model'):
            analyze([self.root], self.out)

    def test_duplicate_decision_rejected(self):
        self.mutate(lambda r: r['pareto_front'].append(r['pareto_front'][0]))
        with self.assertRaisesRegex(SolutionIOError, 'duplicate decision'):
            analyze([self.root], self.out)

    def test_missing_representative_rejected(self):
        self.mutate(lambda r: r.update(decision_hash='missing'))
        with self.assertRaisesRegex(SolutionIOError, 'missing preselected'):
            analyze([self.root], self.out)

    def test_prediction_tampering_rejected(self):
        self.mutate(lambda r: r['pareto_front'][0]['objectives'].__setitem__(0, 12345))
        with self.assertRaisesRegex(SolutionIOError, 'self-replay failed'):
            analyze([self.root], self.out)

    def test_model_label_mismatch_rejected(self):
        self.mutate(lambda r: r.update(model_id='PR1_HT1_EC1'))
        with self.assertRaises(SolutionIOError):
            analyze([self.root], self.out)

    def test_budget_and_precision_rejected(self):
        self.mutate(lambda r: r.update(evaluations=999))
        with self.assertRaisesRegex(SolutionIOError, 'budget'):
            analyze([self.root], self.out)
        self.setUp()
        self.mutate(lambda r: r.update(objective_precision={}))
        with self.assertRaisesRegex(SolutionIOError, 'precision'):
            analyze([self.root], self.out)

    def test_empty_or_failed_replay_rejected(self):
        with patch('scripts.reproduce.common_execution_analysis._replay_solution', return_value={'replay_success': False}):
            with self.assertRaisesRegex(SolutionIOError, 'replay failed'):
                analyze([self.root], self.out)
        self.mutate(lambda r: r.update(pareto_front=[]))
        with self.assertRaisesRegex(SolutionIOError, 'empty front'):
            analyze([self.root], self.out)

    def test_nonfinite_objectives_rejected(self):
        from scripts.reproduce.common_execution_analysis import objectives
        for value in [float('nan'), float('inf'), -float('inf')]:
            with self.assertRaisesRegex(SolutionIOError, 'non-finite'):
                objectives([value, 0, 0])

    def test_duplicate_model_slot_rejected(self):
        record = json.loads(json.dumps(self.records[0]))
        record['run_key'] += '_duplicate'
        path = self.store.save_run(record)
        try:
            with self.assertRaisesRegex(SolutionIOError, 'duplicate planning model'):
                analyze([self.root], self.out)
        finally:
            path.unlink()

    def test_renamed_physical_seed_rejected(self):
        contract_path = self.store.contract_path
        original = contract_path.read_bytes()
        contract = json.loads(original)
        contract['varying']['instance_seeds'].append(102)
        contract_path.write_text(json.dumps(contract))
        record = json.loads(json.dumps(self.records[0]))
        record.update(run_key=record['run_key'] + '_alias', instance_seed=102,
                      solver_seed=record['solver_seed'] + 10000)
        path = self.store.save_run(record)
        try:
            with self.assertRaisesRegex(SolutionIOError, 'renamed to multiple seeds'):
                analyze([self.root], self.out)
        finally:
            path.unlink()
            contract_path.write_bytes(original)

    def test_contract_mismatch_rejected(self):
        self.mutate(lambda r: r['budget'].update(pop_size=123))
        with self.assertRaisesRegex(SolutionIOError, 'outside contract'):
            analyze([self.root], self.out)

    def test_dominated_execution_representative_still_retained(self):
        from scripts.reproduce.replay_solutions import _replay_solution
        target = next(r for r in self.records if len(r['pareto_front']) > 1)
        def replay(**kwargs):
            row = _replay_solution(**kwargs)
            if kwargs['execution_model'] == 'full' and kwargs['record']['run_key'] == target['run_key']:
                value = 2.0 if kwargs['solution']['decision_hash'] == target['decision_hash'] else 1.0
                for j in (1, 2, 3):
                    row[f'replay_F{j}'] = value
            return row
        with patch('scripts.reproduce.common_execution_analysis._replay_solution', side_effect=replay):
            analyze([self.root], self.out)
        with (self.out / 'execution_runs.csv').open() as stream:
            row = next(r for r in csv.DictReader(stream) if r['run_key'] == target['run_key'])
        self.assertEqual(row['representative_hash'], target['decision_hash'])
        self.assertEqual(float(row['representative_F1']), 2.0)
        self.assertEqual(int(row['execution_front_size']), 1)

    def test_front_refilter_and_constant_key(self):
        front = _non_dominated([(1, 2, 0), (2, 3, 0), (1+1e-12, 2, 1e-12)], V2_PRECISION)
        self.assertEqual(front, [(1, 2, 0)])
        quality, meta = pooled_quality_indicators([[(1, 2, 0)], [(1, 2, 1e-12)]], V2_PRECISION)
        self.assertEqual(quality[0], quality[1])
        self.assertEqual(meta['degenerate_dimensions'], [0, 1, 2])

    def test_quantization_boundary(self):
        self.assertTrue(changed((0.49e-8, 0, 0), (0.51e-8, 0, 0))[0])
        self.assertFalse(changed((0.1e-8, 0, 0), (0.4e-8, 0, 0))[0])

    def test_instance_equal_weight(self):
        rows = [{'instance': 1, **dict.fromkeys(PAIR_METRICS, 0)},
                {'instance': 1, **dict.fromkeys(PAIR_METRICS, 0)},
                {'instance': 2, **dict.fromkeys(PAIR_METRICS, 6)}]
        first = aggregate(rows, ('instance',))
        self.assertEqual(aggregate(first, ())[0]['delta_hv'], 3)


if __name__ == '__main__':
    unittest.main()
