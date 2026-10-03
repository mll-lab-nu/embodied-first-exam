"""Approved low-tier layouts with the existing scene and terminal contract."""

from topogym.tasks.base import merge_parameters

from .common import BuzzWireTask


class BuzzWireSimplifiedTask(BuzzWireTask):
    variant_parameters = dict(linear_scale=1.0, geometry={}, base_elevation_m=.125)
    defaults = merge_parameters(BuzzWireTask.defaults, variant_parameters)
    fixed_parameters = ("linear_scale", "geometry", "base_elevation_m")
