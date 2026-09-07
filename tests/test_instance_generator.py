import unittest

from scripts.reproduce.instance_generator import generate_random_instance


class InstanceGeneratorTest(unittest.TestCase):
    def test_instance_generation_counts_and_seed_reproducibility(self):
        first = generate_random_instance(
            num_nodes=25,
            gamma=3,
            damage_ratio=0.3,
            eta_hours=12,
            seed=7,
        )
        second = generate_random_instance(
            num_nodes=25,
            gamma=3,
            damage_ratio=0.3,
            eta_hours=12,
            seed=7,
        )

        self.assertEqual(first.graph.number_of_nodes(), 25)
        self.assertEqual(first.graph.number_of_edges(), 75)
        self.assertEqual(len(first.damaged_edges), 23)
        self.assertEqual(first.suppliers, second.suppliers)
        self.assertEqual(first.demands, second.demands)
        self.assertEqual(first.demand_amounts, second.demand_amounts)
        self.assertEqual(
            [(edge.u, edge.v, edge.repair_time) for edge in first.damaged_edges.values()],
            [(edge.u, edge.v, edge.repair_time) for edge in second.damaged_edges.values()],
        )



if __name__ == "__main__":
    unittest.main()
