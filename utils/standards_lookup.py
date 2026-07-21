import os
import yaml
from pathlib import Path
from typing import Dict, Optional, Tuple


class StandardsLookup:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(StandardsLookup, cls).__new__(
                cls, *args, **kwargs
            )
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.base_dir = (
            Path(__file__).parent.parent / "configs" / "standards"
        )
        self.threads = {}
        self.fits = {}
        self.load_standards()

    def load_standards(self):
        threads_path = self.base_dir / "threads.yaml"
        fits_path = self.base_dir / "fits.yaml"

        if threads_path.exists():
            with open(threads_path, "r") as f:
                self.threads = yaml.safe_load(f) or {}

        if fits_path.exists():
            with open(fits_path, "r") as f:
                self.fits = yaml.safe_load(f) or {}

    def get_metric_coarse_pitch(self, diameter: float) -> Optional[float]:
        if not self.threads or "metric_coarse" not in self.threads:
            return None
        diameter_key = float(diameter)
        for k, v in self.threads["metric_coarse"].items():
            if abs(float(k) - diameter_key) < 0.05:
                return float(v)
        return None

    def get_metric_fine_pitch(self, diameter: float) -> Optional[float]:
        if not self.threads or "metric_fine" not in self.threads:
            return None
        diameter_key = float(diameter)
        for k, v in self.threads["metric_fine"].items():
            if abs(float(k) - diameter_key) < 0.05:
                return float(v)
        return None

    def get_unc_tpi(self, size_fraction: str) -> Optional[int]:
        if not self.threads or "unified_unc" not in self.threads:
            return None
        return self.threads["unified_unc"].get(str(size_fraction).strip())

    def get_unf_tpi(self, size_fraction: str) -> Optional[int]:
        if not self.threads or "unified_unf" not in self.threads:
            return None
        return self.threads["unified_unf"].get(str(size_fraction).strip())

    def get_bsp_parallel_g(self, size_fraction: str) -> Optional[Dict]:
        if not self.threads or "bsp_parallel_g" not in self.threads:
            return None
        return self.threads["bsp_parallel_g"].get(str(size_fraction).strip())

    def get_npt_taper(self, size_fraction: str) -> Optional[Dict]:
        if not self.threads or "npt_taper" not in self.threads:
            return None
        return self.threads["npt_taper"].get(str(size_fraction).strip())

    def get_fit_deviation(
        self, fit_type: str, diameter: float
    ) -> Optional[Tuple[float, float]]:
        if not self.fits:
            return None

        table_name = None
        fit_strip = fit_type.strip()
        if fit_strip == "H7":
            table_name = "iso_286_h7_holes"
        elif fit_strip == "h7":
            table_name = "iso_286_h7_shafts"
        elif fit_strip in ("g6", "G6"):
            table_name = "iso_286_g6_shafts"

        if not table_name or table_name not in self.fits:
            return None

        val = float(diameter)
        for entry in self.fits[table_name]:
            r_min, r_max = entry["range"]
            if r_min == 0.0:
                if 0.0 <= val <= r_max:
                    return (
                        float(entry["lower_deviation"]) / 1000.0,
                        float(entry["upper_deviation"]) / 1000.0,
                    )
            else:
                if r_min < val <= r_max:
                    return (
                        float(entry["lower_deviation"]) / 1000.0,
                        float(entry["upper_deviation"]) / 1000.0,
                    )
        return None
