"""Checks for frozen cross-budget references and complete paired designs."""
import copy
import json
import unittest
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory
from scripts.reproduce.benchmark_algorithms import BenchmarkBudget
from scripts.reproduce.run_model_ablation import run_model_ablation
from scripts.reproduce.budget_convergence_analysis import (
    collect_runs, analyze_budgets, budget_decision, validate_design, representative_traces, main,
)
from scripts.reproduce.run_benchmark import pooled_quality_indicators
from scripts.reproduce.objective_precision import V2_PRECISION

class BudgetAnalysisTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=TemporaryDirectory();cls.roots=[]
        for budget in (8,12,16):
            root=Path(cls.tmp.name)/str(budget);cls.roots.append(root)
            run_model_ablation(suite='benchmark',cases=['S025'],instance_seeds=[101],
                solver_repeats=1,algorithm='nsga2',model_version='v2',
                model_ids=['PR1_HT1_EC1','PR0_HT1_EC1','PR1_HT0_EC1','PR1_HT1_EC0'],
                budget=BenchmarkBudget(budget,4),output_dir=root)
        cls.runs,cls.contexts=collect_runs(cls.roots)
        record=cls.runs[0].record
        cls.protocol={'case_id':'S025','instance_seed':101,'algorithm':'nsga2',
            'source_fingerprint':record['source_fingerprint'],
            'model_ids':['PR1_HT1_EC1','PR0_HT1_EC1','PR1_HT0_EC1','PR1_HT1_EC0'],
            'initial_budgets':[8,12,16],'pop_size':4,
            'solver_seeds':[record['solver_seed']],'solver_repeats':1,
            'plateau_screen':{'confirmation_budget':20,'pairs_per_model':1,
                'minimum_small_change_pairs':1,'hv_relative_change_tolerance':.01,'igd_absolute_change_tolerance':.01}}
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_shared_reference_and_preserved_representatives(self):
        result=analyze_budgets(self.runs,self.protocol)
        self.assertEqual(len(result['run_quality']),12)
        self.assertEqual(len(result['model_pairs']),9)
        self.assertEqual(len(result['reference_metadata']),5)
        refs=[r for r in result['reference_metadata'] if r['evaluation_space']=='execution']
        self.assertEqual(refs[0]['included_runs'],12)
        lookup={r.record['run_key']:r for r in self.runs}
        for row in result['run_quality']:
            self.assertEqual(row['representative_decision_hash'],lookup[row['run_key']].record['decision_hash'])
        p,d=representative_traces(self.runs,self.contexts)
        self.assertTrue(p and d)
        self.assertIn('period_end_hours',p[0]);self.assertIn('demand_node',d[0])
    def test_incomplete_model_rejected(self):
        with self.assertRaisesRegex(ValueError,'missing or duplicate'):validate_design(self.runs[:-1],self.protocol)
    def test_command_writes_complete_audit_manifest(self):
        root=Path(self.tmp.name)
        protocol=root/'protocol.json';protocol.write_text(json.dumps(self.protocol))
        output=root/'analysis'
        argv=['budget_convergence_analysis','--input-roots',*map(str,self.roots),
              '--protocol',str(protocol),'--output-dir',str(output),'--representative-traces']
        with patch('sys.argv',argv), patch('scripts.reproduce.budget_convergence_analysis.collect_runs',
                                          return_value=(self.runs,self.contexts)):
            main()
        manifest=json.loads((output/'analysis_manifest.json').read_text())
        self.assertEqual(manifest['runs'],12)
        self.assertEqual(manifest['actual_evaluations'],4*(8+12+16))
        self.assertEqual(manifest['max_abs_identity_error'],0)
        self.assertTrue(manifest['validated_input_hashes'])
        self.assertTrue((output/'representative_demand_periods.csv').exists())
    def test_duplicate_run_rejected(self):
        with self.assertRaisesRegex(ValueError,'duplicate input'):validate_design(self.runs+[self.runs[0]],self.protocol)
    def test_changed_population_rejected(self):
        runs=copy.deepcopy(self.runs);runs[0].record['budget']['pop_size']=5
        with self.assertRaisesRegex(ValueError,'only max_evaluations'):validate_design(runs,self.protocol)
    def test_incomplete_budget_rejected(self):
        runs=copy.deepcopy(self.runs);runs[0].record['evaluations']-=1
        with self.assertRaisesRegex(ValueError,'did not exhaust'):validate_design(runs,self.protocol)
    def test_model_wins_do_not_enter_plateau(self):
        models=['Full','No-PR','No-HT','No-EC']
        steps=[{'low_budget':lo,'high_budget':hi,'planning_model':m,'planning_plateau_screen':lo==12}
               for lo,hi in [(8,12),(12,16)] for m in models]
        result=budget_decision(steps,[8,12,16],self.protocol)
        self.assertTrue(result['confirmation_required']);self.assertIsNone(result['candidate_budget'])
        steps[4]['planning_plateau_screen']=False
        result=budget_decision(steps,[8,12,16],self.protocol)
        self.assertEqual(result['status'],'no_common_plateau_in_tested_range')
if __name__=='__main__':unittest.main()
