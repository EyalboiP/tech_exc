import logging
from typing import Optional, Tuple

from Ammeters.base_ammeter import AmmeterEmulatorBase
from src.utils.Utils import generate_random_float, mean_std_from_second_moment, uniform_moments

logger = logging.getLogger(__name__)

FIELD_RANGE = (0.01, 0.1)
CALIBRATION_RANGE = (500, 2000)


class EntesAmmeter(AmmeterEmulatorBase):
    @property
    def get_current_command(self) -> bytes:
        # Define the command to get the current from ENTES
        return b'MEASURE_ENTES -get_data'

    def measure_current(self) -> float:
        magnetic_field = generate_random_float(*FIELD_RANGE)  # Magnetic field strength (0.01T - 0.1T)
        calibration_factor = generate_random_float(*CALIBRATION_RANGE)  # Calibration factor (500 - 2000)
        current = magnetic_field * calibration_factor
        logger.debug("ENTES Ammeter - Magnetic Field: %sT, Calibration Factor: %s, Current: %sA",
                     magnetic_field, calibration_factor, current)
        return current

    @classmethod
    def expected_statistics(cls) -> Optional[Tuple[float, float]]:
        # I = B * K with B, K independent
        b_mean, b_second, _, _ = uniform_moments(*FIELD_RANGE)
        k_mean, k_second, _, _ = uniform_moments(*CALIBRATION_RANGE)
        return mean_std_from_second_moment(b_mean * k_mean, b_second * k_second)
