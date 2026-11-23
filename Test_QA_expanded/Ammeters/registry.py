"""Maps the ammeter names used in config.yaml to their emulator classes.

To add a new ammeter type: write a subclass of AmmeterEmulatorBase, register it
here and add an entry under `ammeters:` in config/config.yaml.
"""
from typing import Dict, Type

from Ammeters.base_ammeter import AmmeterEmulatorBase
from Ammeters.Circutor_Ammeter import CircutorAmmeter
from Ammeters.Entes_Ammeter import EntesAmmeter
from Ammeters.Greenlee_Ammeter import GreenleeAmmeter

AMMETER_REGISTRY: Dict[str, Type[AmmeterEmulatorBase]] = {
    "greenlee": GreenleeAmmeter,
    "entes": EntesAmmeter,
    "circutor": CircutorAmmeter,
}
