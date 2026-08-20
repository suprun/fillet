# -*- coding: utf-8 -*-
"""
Fillet & Chamfer Plugin for QGIS
"""


def classFactory(iface):
    """Load FilletPlugin class from file plugin.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    from .plugin import FilletPlugin

    return FilletPlugin(iface)
