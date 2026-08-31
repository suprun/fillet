# -*- coding: utf-8 -*-
"""Small QGIS test helpers shared by the research-tool test modules."""

from qgis.core import QgsFeature
from qgis.PyQt.QtCore import QObject


class TestMessageBar(QObject):
    """Capture warnings without requiring the full QGIS main window."""

    __test__ = False

    def __init__(self):
        super().__init__()
        self.messages = []

    def pushWarning(self, title, text):
        self.messages.append((title, text))

    def pushMessage(self, title, text, level=0, duration=0):
        self.messages.append((title, text, level, duration))


class TestIface:
    """Minimal interface required by the new map tools."""

    __test__ = False

    def __init__(self, canvas):
        self.canvas = canvas
        self.messages = TestMessageBar()

    def messageBar(self):
        return self.messages


def add_geometry_feature(layer, geometry, attributes=None):
    """Add one feature and return its provider-assigned identifier."""
    feature = QgsFeature(layer.fields())
    feature.setGeometry(geometry)
    if attributes is not None:
        feature.setAttributes(attributes)
    success, added = layer.dataProvider().addFeatures([feature])
    if not success or not added:
        raise AssertionError("Could not prepare memory-layer test feature")
    return added[0].id()
