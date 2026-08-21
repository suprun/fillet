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


class SegmentMatch(NamedTuple):
    """Information about a matched edge/segment."""

    fid: int
    part_idx: int
    ring_idx: int
    segment_idx: int  # index of start vertex of segment (0-indexed within ring/part)
    point: QgsPointXY  # closest point projected on the segment
    p1: QgsPointXY  # start vertex of the segment
    p2: QgsPointXY  # end vertex of the segment
    geometry: QgsGeometry


class SnappingHelper:
    """Helper to detect and snap to vertices and segments in vector layers."""

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
        if geom_type not in (QgsWkbTypes.GeometryType.LineGeometry, QgsWkbTypes.GeometryType.PolygonGeometry):
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

    @staticmethod
    def find_segment_at_position(
        layer: QgsVectorLayer,
        canvas: QgsMapCanvas,
        map_point: QgsPointXY,
    ) -> Optional[SegmentMatch]:
        """
        Finds the closest segment/edge to the given map_point in the editable layer.
        """
        if not layer or not layer.isEditable():
            return None

        geom_type = layer.geometryType()
        if geom_type not in (QgsWkbTypes.GeometryType.LineGeometry, QgsWkbTypes.GeometryType.PolygonGeometry):
            return None

        search_radius = QgsTolerance.vertexSearchRadius(layer, canvas.mapSettings()) * 1.5

        layer_crs = layer.crs()
        canvas_crs = canvas.mapSettings().destinationCrs()

        search_point = map_point
        if canvas_crs != layer_crs:
            from qgis.core import QgsCoordinateTransform, QgsProject
            transform = QgsCoordinateTransform(canvas_crs, layer_crs, QgsProject.instance())
            search_point = transform.transform(map_point)

        rect = QgsGeometry.fromPointXY(search_point).buffer(search_radius, 4).boundingBox()

        closest_match: Optional[SegmentMatch] = None
        min_dist_sq = search_radius * search_radius

        request = layer.getFeatures(rect)
        for feature in request:
            geom = feature.geometry()
            if geom.isEmpty() or geom.isNull():
                continue

            dist_sq, proj_pt, after_v, _ = geom.closestSegmentWithContext(search_point)
            if dist_sq <= min_dist_sq and after_v > 0:
                v_id = geom.vertexIdFromVertexNr(after_v)[1]
                part_idx = v_id.part
                ring_idx = v_id.ring
                segment_idx = v_id.vertex - 1

                p1_pt = geom.vertexAt(after_v - 1)
                p2_pt = geom.vertexAt(after_v)

                min_dist_sq = dist_sq
                closest_match = SegmentMatch(
                    fid=feature.id(),
                    part_idx=part_idx,
                    ring_idx=ring_idx,
                    segment_idx=segment_idx,
                    point=proj_pt,
                    p1=QgsPointXY(p1_pt.x(), p1_pt.y()),
                    p2=QgsPointXY(p2_pt.x(), p2_pt.y()),
                    geometry=geom,
                )

        return closest_match
