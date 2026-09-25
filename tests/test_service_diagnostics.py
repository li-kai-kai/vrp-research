import unittest

from scripts.reproduce.capacity_recovery import CapacityIndividual
from scripts.reproduce.service_diagnostics import service_rows
from tests.test_model_contract import _make_instance


class ServiceDiagnosticsTest(unittest.TestCase):
    def test_stock_path_reasons_and_supplier_conservation(self):
        instance = _make_instance(model_version='v2', suppliers=[0, 3], demands=[1, 2, 4],
            supply_amounts={0: 20, 3: 0}, demand_amounts={1: 30, 2: 30, 4: 30},
            edges=[(0, 1, 10, 1000), (3, 2, 10, 1000)])
        decision = CapacityIndividual([], [], [(s, d) for s in [0, 3] for d in [1, 2, 4]])
        p, d, z = service_rows(instance, decision, {}, path_diagnostics=True)
        self.assertTrue(all(row['remaining_supply_3'] == 0 for row in p))
        self.assertAlmostEqual(sum(row['delivered'] for row in d) + p[-1]['remaining_supply'], 20)
        reasons = {row['demand']: row['reason'] for row in z}
        self.assertEqual(reasons[2], 'no_stocked_feasible_supplier')
        self.assertEqual(reasons[4], 'no_topology_time_path')
        self.assertTrue(all(row['first_service_period'] == 1 for row in d if row['demand'] == 1))

    def test_time_infeasible_path_is_not_topologically_sufficient(self):
        instance = _make_instance(model_version='v2', suppliers=[0], demands=[1],
            supply_amounts={0: 30}, demand_amounts={1: 30}, edges=[(0, 1, 600, 1000)])
        _, _, rows = service_rows(instance, CapacityIndividual([], [], [(0, 1)]), {}, path_diagnostics=True)
        self.assertEqual(rows[0]['reason'], 'no_topology_time_path')
