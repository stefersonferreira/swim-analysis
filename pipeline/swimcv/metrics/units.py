"""Conversão para apresentação. Por dentro tudo é SI; jardas só aqui."""

from swimcv.contracts import Metric, PoolUnit
from swimcv.contracts.race import YARD_M

_DIST_UNITS = {"m": "yd", "m/s": "yd/s"}


def display(metric: Metric, pool_unit: PoolUnit) -> tuple[float | None, str]:
    if metric.value is None or pool_unit == PoolUnit.METERS or metric.unit not in _DIST_UNITS:
        return metric.value, metric.unit
    return metric.value / YARD_M, _DIST_UNITS[metric.unit]
