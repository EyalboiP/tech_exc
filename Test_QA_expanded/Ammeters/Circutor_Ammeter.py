import logging
from typing import Optional, Tuple

from Ammeters.base_ammeter import AmmeterEmulatorBase
from src.utils.Utils import generate_random_float, mean_std_from_second_moment, uniform_moments

logger = logging.getLogger(__name__)

NUM_SAMPLES = 10
TIME_STEP_RANGE = (0.001, 0.01)
VOLTAGE_RANGE = (0.1, 1.0)


class CircutorAmmeter(AmmeterEmulatorBase):
    @property
    def get_current_command(self) -> bytes:
        # Define the command to get the current from CIRCUTOR (matches the README)
        return b'MEASURE_CIRCUTOR -get_measurement'

    def measure_current(self) -> float:
        num_samples = NUM_SAMPLES
        time_step = generate_random_float(*TIME_STEP_RANGE)  # Time step (0.001s - 0.01s)
        voltages = [generate_random_float(*VOLTAGE_RANGE) for _ in range(num_samples)]  # Voltage values

        logger.debug("CIRCUTOR Ammeter - Voltages: %s, Time Step: %ss", voltages, time_step)
        current = sum(v * time_step for v in voltages)
        logger.debug("Current: %sA", current)
        return current

    @classmethod
    def expected_statistics(cls) -> Optional[Tuple[float, float]]:
        # I = dt * S, with S = sum of NUM_SAMPLES iid voltages, dt independent of S
        v_mean, v_second, _, _ = uniform_moments(*VOLTAGE_RANGE)
        v_var = v_second - v_mean ** 2
        s_mean = NUM_SAMPLES * v_mean
        s_second = NUM_SAMPLES * v_var + s_mean ** 2
        dt_mean, dt_second, _, _ = uniform_moments(*TIME_STEP_RANGE)
        return mean_std_from_second_moment(dt_mean * s_mean, dt_second * s_second)
