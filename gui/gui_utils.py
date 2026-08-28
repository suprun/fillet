# -*- coding: utf-8 -*-
"""
Shared GUI utility functions for CAD tools in QGIS.
Compatible with QGIS 3.16 to 4.x (Qt5 and Qt6).
"""

from contextlib import contextmanager
from typing import Iterator, List, Optional

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsGeometry,
    QgsProject,
    QgsVectorLayer,
)
from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtWidgets import QMessageBox


def require_edit_success(success: bool, operation: str) -> None:
    """Raise when a vector-layer edit operation reports failure."""
    if not success:
        raise RuntimeError(operation)


@contextmanager
def checked_edit_command(layer: QgsVectorLayer, title: str) -> Iterator[None]:
    """Run a QGIS edit command atomically and destroy it on any failure."""
    layer.beginEditCommand(title)
    try:
        yield
        layer.endEditCommand()
    except Exception:
        layer.destroyEditCommand()
        raise


def transform_geometry_copy(
    geom: QgsGeometry,
    source_crs: QgsCoordinateReferenceSystem,
    destination_crs: QgsCoordinateReferenceSystem,
) -> QgsGeometry:
    """Return a transformed clone, preserving raw coordinates for invalid CRS."""
    result = QgsGeometry(geom)
    if (
        source_crs.isValid()
        and destination_crs.isValid()
        and source_crs != destination_crs
    ):
        coordinate_transform = QgsCoordinateTransform(
            source_crs,
            destination_crs,
            QgsProject.instance(),
        )
        transform_result = result.transform(coordinate_transform)
        if transform_result not in (None, 0):
            raise RuntimeError("Geometry CRS transformation failed")
    return result


def confirm_features_in_canvas_extent(
    canvas: Optional[QgsMapCanvas],
    layer: Optional[QgsVectorLayer],
    features: List[QgsFeature],
    tool_title: str,
) -> bool:
    """
    Checks if any of the target features are outside the current visible map canvas view.
    If outside, prompts the user with the standard QGIS confirmation dialog:
    'Some of the selected features are outside of the current map view. Would you still like to continue?'
    Returns True if all features are within extent or if the user confirmed 'Yes'.
    Returns False if any feature is outside and the user declined ('No').
    """
    if not canvas or not layer or not features:
        return True

    canvas_extent = canvas.mapSettings().visibleExtent()
    if canvas_extent.isEmpty() or canvas_extent.isNull():
        return True

    map_crs = canvas.mapSettings().destinationCrs()
    layer_crs = layer.crs()

    ct = None
    if map_crs.isValid() and layer_crs.isValid() and map_crs != layer_crs:
        try:
            ct = QgsCoordinateTransform(layer_crs, map_crs, QgsProject.instance())
        except Exception:
            ct = None

    outside = False
    for feat in features:
        if not feat.hasGeometry() or feat.geometry().isEmpty():
            continue
        bbox = feat.geometry().boundingBox()
        if bbox.isEmpty() or bbox.isNull():
            continue
        if ct is not None:
            try:
                bbox_map = ct.transformBoundingBox(bbox)
            except Exception:
                bbox_map = bbox
        else:
            bbox_map = bbox

        if not canvas_extent.contains(bbox_map):
            outside = True
            break

    if not outside:
        return True

    prompt_text = "Some of the selected features are outside of the current map view. Would you still like to continue?"
    # Try QGIS built-in translation first, then fallback to plugin translator
    msg = QCoreApplication.translate("QgsMapToolMoveFeature", prompt_text)
    if msg == prompt_text:
        msg = QCoreApplication.translate("FilletPlugin", prompt_text)

    # Safe cross-version standard buttons
    btn_yes = getattr(QMessageBox.StandardButton, "Yes", getattr(QMessageBox, "Yes", 0x00004000))
    btn_no = getattr(QMessageBox.StandardButton, "No", getattr(QMessageBox, "No", 0x00010000))

    res = QMessageBox.warning(
        canvas,
        tool_title,
        msg,
        btn_yes | btn_no,
        btn_no,
    )
    return res == btn_yes
