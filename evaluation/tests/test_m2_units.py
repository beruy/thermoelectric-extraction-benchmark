"""Tests for the M2 mapping code that runs without the model (units, text normalisation, names)."""
import unittest

from materialsbert_extractor.predict import kappa_type, normalise_text, property_of
from materialsbert_extractor.units import to_canonical


class TestUnits(unittest.TestCase):
    def check(self, prop, value, unit, expected):
        got, why = to_canonical(prop, value, unit)
        self.assertIsNotNone(got, why)
        self.assertAlmostEqual(got / expected, 1.0, places=9)

    def test_conversions(self):
        self.check("S_uVK", 0.2, "mV/K", 200)
        self.check("S_uVK", 150, "µV/°C", 150)
        self.check("kappa", 0.56, "W/mK", 0.56)
        self.check("kappa", 560, "mW m-1 K-1", 0.56)
        self.check("sigma", 1000, "S cm^{-1}", 1e5)
        self.check("sigma", 100, "(Ω cm)^{-1}", 1e4)
        self.check("sigma", 10, "μΩ m", 1e5)
        self.check("PF", 1000, "μW m^{-1} K^{-2}", 10)
        self.check("PF", 3e-3, "W m-1 K-2", 30)
        self.check("doping", 1e26, "m-3", 1e20)
        self.check("PF", 0.02, "W/m. K^{2}", 200)
        self.check("PF", 75e-4, "W/mK^{2}", 75)

    def test_rejections(self):
        self.assertIsNone(to_canonical("kappa", 1, "μV/K")[0])
        self.assertIsNone(to_canonical("S_uVK", 1, "")[0])
        self.assertIsNone(to_canonical("sigma", 1, "banana")[0])


class TestText(unittest.TestCase):
    def test_normalise(self):
        self.assertEqual(normalise_text("0.56 W m-1 K-1."), "0.56 W m^{-1} K^{-1}.")
        self.assertEqual(normalise_text("2 × 10^20 cm−3"), "2x10^{20} cm^{-3}")
        self.assertEqual(normalise_text("300 K-1000 K, Bi2Te3-x"), "300 K-1000 K, Bi2Te3-x")
        self.assertEqual(normalise_text("200 μV K⁻¹"), "200 μV K^{-1}")
        self.assertEqual(normalise_text("75 x 10-4 W/mK2"), "75x10^{-4} W/mK^{2}")
        self.assertEqual(normalise_text("K2Bi8Se13"), "K2Bi8Se13")
        self.assertEqual(normalise_text("0.02 - 0.08 W/m.K^2."), "0.02 - 0.08 W/m.K^{2}.")

    def test_names(self):
        self.assertEqual(property_of("thermoelectric figure of merit"), ("ZT", False))
        self.assertEqual(property_of("electrical resistivity"), ("sigma", True))
        self.assertEqual(property_of("thermal diffusivity"), (None, False))
        self.assertEqual(kappa_type("lattice thermal conductivity"), "lattice")


if __name__ == "__main__":
    unittest.main()
