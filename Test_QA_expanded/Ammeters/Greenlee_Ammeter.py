import logging
from typing import Optional, Tuple

from Ammeters.base_ammeter import AmmeterEmulatorBase
from src.utils.Utils import generate_random_float, mean_std_from_second_moment, uniform_moments

logger = logging.getLogger(__name__)

VOLTAGE_RANGE = (1.0, 10.0)
RESISTANCE_RANGE = (0.1, 100.0)


class GreenleeAmmeter(AmmeterEmulatorBase):
    @property
    def get_current_command(self) -> bytes:
        # Define the command to get the current from Greenlee
        return b'MEASURE_GREENLEE -get_measurement'

    def measure_current(self) -> float:
        voltage = generate_random_float(*VOLTAGE_RANGE)  # Random voltage (1V - 10V)
        resistance = generate_random_float(*RESISTANCE_RANGE)  # Random resistance (0.1Ω - 100Ω)
        current = voltage / resistance
        logger.debug("Greenlee Ammeter - Voltage: %sV, Resistance: %sΩ, Current: %sA", voltage, resistance, current)
        return current

    @classmethod
    def expected_statistics(cls) -> Optional[Tuple[float, float]]:
        # I = V / R with V, R independent: E[I] = E[V]E[1/R], E[I^2] = E[V^2]E[1/R^2]
        v_mean, v_second, _, _ = uniform_moments(*VOLTAGE_RANGE)
        _, _, r_inv, r_inv2 = uniform_moments(*RESISTANCE_RANGE)
        return mean_std_from_second_moment(v_mean * r_inv, v_second * r_inv2)
