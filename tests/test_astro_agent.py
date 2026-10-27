import unittest
from astro_agent import build_adql, normalize, dedupe, PLANS


class AstroAgentTests(unittest.TestCase):
    def test_adql_contains_requested_limit_and_quality_threshold(self):
        query = build_adql("distant", 25, 7.5)
        self.assertIn("SELECT TOP 25", query)
        self.assertIn("parallax_over_error >= 7.5", query)
        self.assertNotIn('"parallax"', query)
        self.assertIn("gaiadr3.gaia_source", query)

    def test_normalize_converts_parallax_to_distance(self):
        # 1 mas corresponds to 1000 pc, using the project's inverse-parallax estimate.
        csv_text = (
            "source_id,ra,dec,parallax,parallax_error,parallax_over_error,"
            "phot_g_mean_mag,bp_rp,teff_gspphot,logg_gspphot,mh_gspphot\n"
            "123,12.0,-4.0,1.0,0.1,10,7.0,0.5,12000,4.0,-1.2\n"
        )
        rows = normalize(csv_text, "distant")
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["distance_pc"], 1000.0, places=3)
        self.assertAlmostEqual(rows[0]["distance_ly"], 3261.56, places=1)
        self.assertIn("high-parallax-SNR", rows[0]["agent_tags"])
        self.assertIn("hot-star-candidate", rows[0]["agent_tags"])
        self.assertIn("low-metallicity-candidate", rows[0]["agent_tags"])
        self.assertEqual(rows[0]["research_priority_score"], 38.0)
        self.assertAlmostEqual(rows[0]["relative_distance_uncertainty_pct_approx"], 10.0)
        self.assertAlmostEqual(rows[0]["distance_low_pc_approx"], 909.091, places=2)
        self.assertAlmostEqual(rows[0]["distance_high_pc_approx"], 1111.111, places=2)

    def test_uncertainty_upper_bound_is_missing_if_parallax_error_crosses_zero(self):
        csv_text = (
            "source_id,ra,dec,parallax,parallax_error,parallax_over_error,"
            "phot_g_mean_mag,bp_rp,teff_gspphot,logg_gspphot,mh_gspphot\n"
            "456,12.0,-4.0,0.5,0.6,0.83,12.0,1.0,,,\n"
        )
        rows = normalize(csv_text, "distant")
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["distance_high_pc_approx"])
        self.assertIsNone(rows[0]["distance_high_ly_approx"])

    def test_non_positive_parallax_is_excluded(self):
        csv_text = (
            "source_id,ra,dec,parallax,parallax_error,parallax_over_error,"
            "phot_g_mean_mag,bp_rp,teff_gspphot,logg_gspphot,mh_gspphot\n"
            "123,12.0,-4.0,-0.5,0.1,-5,7.0,0.5,,, \n"
        )
        self.assertEqual(normalize(csv_text, "distant"), [])

    def test_dedupe_merges_query_provenance(self):
        base = {
            "source_id": "42", "distance_pc": 100, "found_by_queries": ["distant"],
            "agent_tags": ["high-parallax-SNR"]
        }
        second = {
            "source_id": "42", "distance_pc": 100, "found_by_queries": ["hot"],
            "agent_tags": ["hot-star-candidate"]
        }
        rows = dedupe([base, second])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["found_by_queries"], ["distant", "hot"])
        self.assertIn("hot-star-candidate", rows[0]["agent_tags"])

    def test_all_query_plans_have_purpose(self):
        for name, plan in PLANS.items():
            self.assertTrue(plan["label"])
            self.assertTrue(plan["purpose"])
            self.assertIn("parallax", plan["where"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
