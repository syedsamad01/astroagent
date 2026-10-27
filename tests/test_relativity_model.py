import math
import unittest
G=6.67430e-11; C=299792458.0; M_SUN=1.98847e30; R_SUN=6.957e8; M_EARTH=5.9722e24; R_EARTH=6.371e6

def grav_factor(mass_kg, radius_m):
    compactness=2*G*mass_kg/(radius_m*C*C)
    if compactness>=1: return None
    return math.sqrt(1-compactness)

def rate_ratio(star_mass_solar, star_radius_solar, speed_kms):
    star=grav_factor(star_mass_solar*M_SUN, star_radius_solar*R_SUN)
    earth=grav_factor(M_EARTH,R_EARTH)
    beta=speed_kms*1000/C
    return (star*math.sqrt(1-beta*beta))/earth

class RelativityModelTests(unittest.TestCase):
    def test_solar_like_star_rate_near_earth_surface(self):
        self.assertTrue(0.99998 < rate_ratio(1,1,0) < 1.00002)
    def test_higher_speed_lowers_clock_rate(self):
        self.assertLess(rate_ratio(1,1,30000),rate_ratio(1,1,0))
    def test_compact_object_invalid_for_surface_model(self):
        self.assertIsNone(grav_factor(10*M_SUN,1))

if __name__=='__main__': unittest.main(verbosity=2)
