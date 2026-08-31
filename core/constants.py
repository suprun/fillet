# -*- coding: utf-8 -*-
"""
Central configuration constants and default values for Fillet & Chamfer Tool.
"""

# Operation modes
MODE_FILLET = "fillet"
MODE_CHAMFER = "chamfer"
MODE_RESTORE = "restore"

# Fillet default parameters
DEFAULT_RADIUS_METRIC = 5.0
DEFAULT_RADIUS_GEO = 0.0001
DEFAULT_SEGMENTS_COUNT = 20
MIN_SEGMENTS_COUNT = 2
MAX_SEGMENTS_COUNT = 64

# Chamfer default parameters
DEFAULT_DIST1_METRIC = 5.0
DEFAULT_DIST2_METRIC = 5.0
DEFAULT_DIST1_GEO = 0.0001
DEFAULT_DIST2_GEO = 0.0001
DEFAULT_LINK_DISTANCES = True

# Metric CRS bounds and precision
MIN_METRIC_VALUE = 0.0
MAX_METRIC_VALUE = 9999999.0
STEP_METRIC_VALUE = 1.0
DECIMALS_METRIC = 3

# Geographic (degree-based) CRS bounds and precision
MIN_GEO_VALUE = 0.0
MAX_GEO_VALUE = 100.0
STEP_GEO_VALUE = 0.00005
DECIMALS_GEO = 6

# Geometry mathematical tolerances
EPSILON_GEOMETRY = 1e-8
EPSILON_CHAMFER_EQUALITY = 1e-11
