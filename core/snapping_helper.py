# -*- coding: utf-8 -*-
"""
Snapping and vertex identification helper for Fillet & Chamfer plugin.
"""

from typing import NamedTuple, Optional

from qgis.core import (
    QgsGeometry,
    QgsPointLocator,
    QgsPointXY,
    QgsTolerance,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.gui import QgsMapCanvas


class VertexMatch(NamedTuple):
    """Information about a matched vertex."""

    fid: int
    part_idx: int
    ring_idx: int
    vertex_idx: int
    point: QgsPointXY
    geometry: QgsGeometry


class SnappingHelper:
    """Helper to detect and snap to vertices in vector layers."""

    @staticmethod
    def find_vertex_at_position(
        layer: QgsVectorLayer,
        canvas: QgsMapCanvas,
        map_point: QgsPointXY,
    ) -> Optional[VertexMatch]:
        """
        Finds the closest vertex to the given map_point in the editable layer.
        """
        if not layer or not layer.isEditable():
            return None

        geom_type = layer.geometryType()
        if geom_type not in (QgsWkbTypes.LineGeometry, QgsWkbTypes.PolygonGeometry):
            return None

        # Determine search tolerance in map units
        search_radius = QgsTolerance.vertexSearchRadius(layer, canvas.mapSettings())

        # Transform search point to layer CRS if needed
        layer_crs = layer.crs()
        canvas_crs = canvas.mapSettings().destinationCrs()

        search_point = map_point
        if canvas_crs != layer_crs:
            from qgis.core import QgsCoordinateTransform, QgsProject
            transform = QgsCoordinateTransform(canvas_crs, layer_crs, QgsProject.instance())
            search_point = transform.transform(map_point)

        # Search bounding box
        rect = QgsGeometry.fromPointXY(search_point).buffer(search_radius, 4).boundingBox()

        closest_match: Optional[VertexMatch] = None
        min_dist_sq = search_radius * search_radius

        request = layer.getFeatures(rect)
        for feature in request:
            geom = feature.geometry()
            if geom.isEmpty() or geom.isNull():
                continue

            # Find closest vertex in geometry
            closest_pt, closest_v_id, _, _, dist_sq = geom.closestVertex(search_point)
            if dist_sq <= min_dist_sq and closest_v_id >= 0:
                # Get part, ring, vertex index from QgsVertexId
                # QgsGeometry.vertexIdFromVertexNr gives QgsVertexId in QGIS 3.x/4.x
                v_id = geom.vertexIdFromVertexNr(closest_v_id)[1]
                part_idx = v_id.part
                ring_idx = v_id.ring
                vertex_idx = v_id.vertex

                min_dist_sq = dist_sq
                closest_match = VertexMatch(
                    fid=feature.id(),
                    part_idx=part_idx,
                    ring_idx=ring_idx,
                    vertex_idx=vertex_idx,
                    point=closest_pt,
                    geometry=geom,
                )

        return closest_match
