# -*- coding: utf-8 -*-
"""Test plugin initGui and unload cleanup lifecycle."""

from qgis.core import QgsApplication
from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtCore import pyqtSignal, QObject
from qgis.PyQt.QtWidgets import QMainWindow, QDockWidget, QToolBar

app = QgsApplication([], False)
app.initQgis()

win = QMainWindow()
canvas = QgsMapCanvas(win)
tb = QToolBar("Digitize", win)
win.addToolBar(tb)

class MockIface(QObject):
    currentLayerChanged = pyqtSignal(object)

    def mainWindow(self):
        return win
    def mapCanvas(self):
        return canvas
    def advancedDigitizeToolBar(self):
        return tb
    def addVectorToolBarIcon(self, a):
        tb.addAction(a)
    def removeVectorToolBarIcon(self, a):
        tb.removeAction(a)
    def addPluginToVectorMenu(self, n, a):
        pass
    def removePluginVectorMenu(self, n, a):
        pass
    def addDockWidget(self, area, d):
        win.addDockWidget(area, d)
    def removeDockWidget(self, d):
        win.removeDockWidget(d)
    def currentLayer(self):
        return None

from plugin import FilletPlugin

iface = MockIface()
plugin = FilletPlugin(iface)

# 1. First load
plugin.initGui()
print("Load 1: dock count =", len(win.findChildren(QDockWidget, "FilletChamferDockWidget")))

# 2. First unload
plugin.unload()
app.processEvents()
print("Unload 1: dock count =", len(win.findChildren(QDockWidget, "FilletChamferDockWidget")))

# 3. Second load (Reload)
plugin = FilletPlugin(iface)
plugin.initGui()
print("Load 2 (Reload): dock count =", len(win.findChildren(QDockWidget, "FilletChamferDockWidget")))

# 4. Second unload
plugin.unload()
app.processEvents()
print("Unload 2: dock count =", len(win.findChildren(QDockWidget, "FilletChamferDockWidget")))

app.exitQgis()
