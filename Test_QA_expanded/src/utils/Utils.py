import math
import random
from typing import Tuple


def generate_random_float(min_value: float, max_value: float) -> float:
    """Generate a random float between min_value and max_value."""
    return random.uniform(min_value, max_value)


# --- Moments of U(a, b), used to derive the theoretical statistics of each emulator ---

def uniform_moments(a: float, b: float) -> Tuple[float, float, float, float]:
    """Return (E[X], E[X^2], E[1/X], E[1/X^2]) for X ~ Uniform(a, b), with 0 < a < b."""
    mean = (a + b) / 2
    second = (a * a + a * b + b * b) / 3
    inv = math.log(b / a) / (b - a)
    inv2 = 1 / (a * b)
    return mean, second, inv, inv2


def mean_std_from_second_moment(mean: float, second_moment: float) -> Tuple[float, float]:
    return mean, math.sqrt(max(second_moment - mean * mean, 0.0))
