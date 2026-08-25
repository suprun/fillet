# -*- coding: utf-8 -*-
"""
Fillet & Chamfer Geometry Engine for QGIS 3.x and 4.x
Provides core mathematical algorithms for vertex and segment filleting/chamfering.
"""

import math
from typing import List, Optional, Tuple, Union

from qgis.core import (
    QgsAbstractGeometry,
    QgsCircularString,
    QgsCompoundCurve,
    QgsCurvePolygon,
    QgsGeometry,
    QgsGeometryUtils,
    QgsLineString,
    QgsMultiLineString,
    QgsMultiPolygon,
    QgsPoint,
    QgsPointXY,
    QgsPolygon,
    QgsVertexId,
    QgsWkbTypes,
)


class GeometryEngine:
    """Core mathematical engine for Fillet and Chamfer operations."""

    EPSILON = 1e-8

    @staticmethod
    def distance(p1: Union[QgsPoint, QgsPointXY], p2: Union[QgsPoint, QgsPointXY]) -> float:
        """Euclidean distance between two 2D points."""
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        return math.hypot(dx, dy)

    @staticmethod
    def normalize_vector(dx: float, dy: float) -> Tuple[float, float, float]:
        """Returns (unit_dx, unit_dy, length)."""
        length = math.hypot(dx, dy)
        if length < GeometryEngine.EPSILON:
            return 0.0, 0.0, 0.0
        return dx / length, dy / length, length

    @staticmethod
    def compute_fillet_points(
        p_prev: Union[QgsPoint, QgsPointXY],
        v: Union[QgsPoint, QgsPointXY],
        p_next: Union[QgsPoint, QgsPointXY],
        radius: float,
        epsilon: float = 1e-8,
    ) -> Tuple[bool, Optional[QgsPoint], Optional[QgsPoint], Optional[QgsPoint], float]:
        """
        Calculates the 3 points defining the fillet circular arc at vertex v:
        (t1, arc_mid, t2) and the tangent distance.

        Returns: (success, t1, arc_mid, t2, tangent_distance)
        """
        if radius <= 0:
            return False, None, None, None, 0.0

        # Vector from V to P_prev
        u1x, u1y, len1 = GeometryEngine.normalize_vector(p_prev.x() - v.x(), p_prev.y() - v.y())
        # Vector from V to P_next
        u2x, u2y, len2 = GeometryEngine.normalize_vector(p_next.x() - v.x(), p_next.y() - v.y())

        if len1 < epsilon or len2 < epsilon:
            return False, None, None, None, 0.0

        # Dot product
        dot = u1x * u2x + u1y * u2y
        dot = max(-1.0, min(1.0, dot))

        # Angle between the two vectors (0 to pi)
        angle = math.acos(dot)

        # Check for collinear or overlapping segments
        if angle < epsilon or angle > (math.pi - epsilon):
            return False, None, None, None, 0.0

        half_angle = angle / 2.0
        tan_half = math.tan(half_angle)
        sin_half = math.sin(half_angle)

        if tan_half < epsilon or sin_half < epsilon:
            return False, None, None, None, 0.0

        tangent_dist = radius / tan_half

        # Max allowed tangent distance - clamp to maximum possible if requested radius is too large
        max_dist = min(len1, len2)
        if tangent_dist > max_dist:
            tangent_dist = max_dist * 0.9999
            radius = tangent_dist * tan_half

        # Tangent points
        t1 = QgsPoint(v.x() + tangent_dist * u1x, v.y() + tangent_dist * u1y)
        t2 = QgsPoint(v.x() + tangent_dist * u2x, v.y() + tangent_dist * u2y)

        # Bisector unit vector (points into the angle interior)
        bx, by, blen = GeometryEngine.normalize_vector(u1x + u2x, u1y + u2y)
        if blen < epsilon:
            return False, None, None, None, 0.0

        # Circle center C: distance from V = radius / sin(half_angle)
        center_dist = radius / sin_half
        cx = v.x() + center_dist * bx
        cy = v.y() + center_dist * by

        # Arc midpoint M: on circle, closest to vertex V
        # M = C - radius * bisector = V + (center_dist - radius) * bisector
        mid_x = cx - radius * bx
        mid_y = cy - radius * by
        arc_mid = QgsPoint(mid_x, mid_y)

        return True, t1, arc_mid, t2, tangent_dist

    @staticmethod
    def compute_chamfer_points(
        p_prev: Union[QgsPoint, QgsPointXY],
        v: Union[QgsPoint, QgsPointXY],
        p_next: Union[QgsPoint, QgsPointXY],
        dist1: float,
        dist2: float,
        epsilon: float = 1e-8,
    ) -> Tuple[bool, Optional[QgsPoint], Optional[QgsPoint]]:
        """
        Calculates the 2 chamfer points at vertex v along segments to p_prev and p_next.
        Returns: (success, c1, c2)
        """
        if dist1 <= 0:
            return False, None, None
        if dist2 <= 0:
            dist2 = dist1

        u1x, u1y, len1 = GeometryEngine.normalize_vector(p_prev.x() - v.x(), p_prev.y() - v.y())
        u2x, u2y, len2 = GeometryEngine.normalize_vector(p_next.x() - v.x(), p_next.y() - v.y())

        if len1 < epsilon or len2 < epsilon:
            return False, None, None

        # Clamp distances to maximum possible if they exceed segment lengths
        if abs(dist1 - dist2) < 1e-11:
            # Isosceles chamfer: strictly equal and bounded by shorter edge
            max_d = min(len1, len2) * 0.9999
            if dist1 > max_d:
                dist1 = max_d
                dist2 = max_d
        else:
            if dist1 > len1:
                dist1 = len1 * 0.9999
            if dist2 > len2:
                dist2 = len2 * 0.9999

        c1 = QgsPoint(v.x() + dist1 * u1x, v.y() + dist1 * u1y)
        c2 = QgsPoint(v.x() + dist2 * u2x, v.y() + dist2 * u2y)

        return True, c1, c2

    @staticmethod
    def max_fillet_radius(
        p_prev: Union[QgsPoint, QgsPointXY],
        v: Union[QgsPoint, QgsPointXY],
        p_next: Union[QgsPoint, QgsPointXY],
        epsilon: float = 1e-8,
    ) -> float:
        """Calculates the maximum possible fillet radius for vertex v."""
        u1x, u1y, len1 = GeometryEngine.normalize_vector(p_prev.x() - v.x(), p_prev.y() - v.y())
        u2x, u2y, len2 = GeometryEngine.normalize_vector(p_next.x() - v.x(), p_next.y() - v.y())

        if len1 < epsilon or len2 < epsilon:
            return -1.0

        dot = u1x * u2x + u1y * u2y
        dot = max(-1.0, min(1.0, dot))
        angle = math.acos(dot)

        if angle < epsilon or angle > (math.pi - epsilon):
            return -1.0

        tan_half = math.tan(angle / 2.0)
        return min(len1, len2) * tan_half

    @staticmethod
    def segmentize_arc_3p(
        p1: QgsPoint,
        pm: QgsPoint,
        p2: QgsPoint,
        segments_count: int = 12,
    ) -> List[QgsPoint]:
        """
        Discretizes a 3-point circular arc (p1 -> pm -> p2) into a list of QgsPoints
        with exactly `segments_count` linear segments (segments_count + 1 vertices).
        """
        if segments_count < 2:
            segments_count = 2

        ax, ay = p1.x(), p1.y()
        bx, by = pm.x(), pm.y()
        cx, cy = p2.x(), p2.y()

        d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
        if abs(d) < 1e-10:
            return [QgsPoint(p1.x(), p1.y()), QgsPoint(pm.x(), pm.y()), QgsPoint(p2.x(), p2.y())]

        ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d
        uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d
        r = math.hypot(ax - ux, ay - uy)

        a1 = math.atan2(ay - uy, ax - ux)
        am = math.atan2(by - uy, bx - ux)
        a2 = math.atan2(cy - uy, cx - ux)

        def norm_ang(a):
            while a < a1:
                a += 2 * math.pi
            return a

        am_norm = norm_ang(am)
        a2_norm = norm_ang(a2)

        if am_norm < a2_norm:
            start_ang = a1
            end_ang = a2_norm
        else:
            start_ang = a1
            end_ang = a2_norm - 2 * math.pi

        points = [QgsPoint(p1.x(), p1.y())]
        for i in range(1, segments_count):
            t = i / float(segments_count)
            ang = start_ang + t * (end_ang - start_ang)
            points.append(QgsPoint(ux + r * math.cos(ang), uy + r * math.sin(ang)))
        points.append(QgsPoint(p2.x(), p2.y()))

        return points

    @classmethod
    def apply_fillet_to_curve(
        cls,
        curve: QgsAbstractGeometry,
        vertex_index: int,
        radius: float,
        segments_count: int = 12,
        use_true_curve: bool = False,
    ) -> Optional[QgsAbstractGeometry]:
        """
        Applies fillet to a vertex of a single curve (QgsLineString).
        """
        if hasattr(QgsGeometryUtils, "filletVertex") and use_true_curve:
            try:
                res = QgsGeometryUtils.filletVertex(curve, vertex_index, radius, 0 if use_true_curve else segments_count)
                if res is not None:
                    return res
            except (AttributeError, RuntimeError, TypeError):
                # Fallback to custom geometry engine below
                pass  # nosec B110

        num_vertices = curve.numPoints() if hasattr(curve, "numPoints") else 0
        if num_vertices < 3:
            return None

        is_closed = curve.isClosed() if hasattr(curve, "isClosed") else False

        if is_closed:
            effective_count = num_vertices - 1 if (curve.pointN(0) == curve.pointN(num_vertices - 1)) else num_vertices
            if vertex_index == 0 or vertex_index == num_vertices - 1:
                idx_curr = 0
                idx_prev = effective_count - 1
                idx_next = 1
            else:
                idx_curr = vertex_index
                idx_prev = (idx_curr - 1) % effective_count
                idx_next = (idx_curr + 1) % effective_count
        else:
            if vertex_index <= 0 or vertex_index >= num_vertices - 1:
                return None
            idx_curr = vertex_index
            idx_prev = vertex_index - 1
            idx_next = vertex_index + 1

        p_prev = curve.pointN(idx_prev)
        v = curve.pointN(idx_curr)
        p_next = curve.pointN(idx_next)

        success, t1, arc_mid, t2, _ = cls.compute_fillet_points(p_prev, v, p_next, radius)
        if not success or t1 is None or arc_mid is None or t2 is None:
            return None

        arc_pts = cls.segmentize_arc_3p(t1, arc_mid, t2, segments_count)

        new_pts = []
        if is_closed and (vertex_index == 0 or vertex_index == num_vertices - 1):
            middle_pts = [curve.pointN(i) for i in range(1, num_vertices - 1)]
            new_pts.append(t2)
            new_pts.extend(middle_pts)
            new_pts.append(t1)
            new_pts.extend(arc_pts[1:])
        else:
            for i in range(num_vertices):
                if i == idx_curr:
                    new_pts.extend(arc_pts)
                else:
                    new_pts.append(curve.pointN(i))

        if is_closed and (new_pts[0] != new_pts[-1]):
            new_pts.append(new_pts[0])

        return QgsLineString(new_pts)

    @classmethod
    def apply_chamfer_to_curve(
        cls,
        curve: QgsAbstractGeometry,
        vertex_index: int,
        dist1: float,
        dist2: float,
    ) -> Optional[QgsAbstractGeometry]:
        """
        Applies chamfer to a vertex of a single curve (QgsLineString).
        """
        if hasattr(QgsGeometryUtils, "chamferVertex"):
            try:
                res = QgsGeometryUtils.chamferVertex(curve, vertex_index, dist1, dist2)
                if res is not None:
                    return res
            except (AttributeError, RuntimeError, TypeError):
                # Fallback to custom geometry engine below
                pass  # nosec B110

        num_vertices = curve.numPoints() if hasattr(curve, "numPoints") else 0
        if num_vertices < 3:
            return None

        is_closed = curve.isClosed() if hasattr(curve, "isClosed") else False

        if is_closed:
            effective_count = num_vertices - 1 if (curve.pointN(0) == curve.pointN(num_vertices - 1)) else num_vertices
            if vertex_index == 0 or vertex_index == num_vertices - 1:
                idx_curr = 0
                idx_prev = effective_count - 1
                idx_next = 1
            else:
                idx_curr = vertex_index
                idx_prev = (idx_curr - 1) % effective_count
                idx_next = (idx_curr + 1) % effective_count
        else:
            if vertex_index <= 0 or vertex_index >= num_vertices - 1:
                return None
            idx_curr = vertex_index
            idx_prev = vertex_index - 1
            idx_next = vertex_index + 1

        p_prev = curve.pointN(idx_prev)
        v = curve.pointN(idx_curr)
        p_next = curve.pointN(idx_next)

        success, c1, c2 = cls.compute_chamfer_points(p_prev, v, p_next, dist1, dist2)
        if not success or c1 is None or c2 is None:
            return None

        new_pts = []
        if is_closed and (vertex_index == 0 or vertex_index == num_vertices - 1):
            middle_pts = [curve.pointN(i) for i in range(1, num_vertices - 1)]
            new_pts.append(c2)
            new_pts.extend(middle_pts)
            new_pts.append(c1)
            new_pts.append(c2)
        else:
            for i in range(num_vertices):
                if i == idx_curr:
                    new_pts.append(c1)
                    new_pts.append(c2)
                else:
                    new_pts.append(curve.pointN(i))

        if is_closed and (new_pts[0] != new_pts[-1]):
            new_pts.append(new_pts[0])

        return QgsLineString(new_pts)

    @classmethod
    def apply_fillet_to_geometry(
        cls,
        geom: QgsGeometry,
        part_idx: int,
        ring_idx: int,
        vertex_idx: int,
        radius: float,
        segments_count: int = 12,
        use_true_curve: bool = False,
    ) -> Optional[QgsGeometry]:
        """
        Applies fillet to a specific vertex in any QgsGeometry (LineString, Polygon, MultiPart).
        Returns the updated QgsGeometry or None if failed.
        """
        if geom.isEmpty() or geom.isNull():
            return None

        geom_type = geom.type()
        is_multi = geom.isMultipart()

        if geom_type == QgsWkbTypes.GeometryType.LineGeometry:
            if not is_multi:
                curve = geom.constGet()
                if not curve:
                    return None
                new_curve = cls.apply_fillet_to_curve(curve, vertex_idx, radius, segments_count, use_true_curve)
                if new_curve:
                    return QgsGeometry(new_curve)
            else:
                multi = geom.constGet()
                if not multi or part_idx >= multi.numGeometries():
                    return None
                new_multi = QgsMultiLineString()
                for p in range(multi.numGeometries()):
                    c = multi.geometryN(p)
                    if p == part_idx:
                        nc = cls.apply_fillet_to_curve(c, vertex_idx, radius, segments_count, use_true_curve)
                        new_multi.addGeometry(nc if nc else c.clone())
                    else:
                        new_multi.addGeometry(c.clone())
                return QgsGeometry(new_multi)

        elif geom_type == QgsWkbTypes.GeometryType.PolygonGeometry:
            if not is_multi:
                poly = geom.constGet()
                if not poly:
                    return None
                new_poly = QgsPolygon()
                ext_ring = poly.exteriorRing()
                if ext_ring is None:
                    return None

                if ring_idx == 0:
                    new_ext = cls.apply_fillet_to_curve(ext_ring, vertex_idx, radius, segments_count, use_true_curve)
                    new_poly.setExteriorRing(new_ext if new_ext else ext_ring.clone())
                else:
                    new_poly.setExteriorRing(ext_ring.clone())

                for r in range(poly.numInteriorRings()):
                    int_ring = poly.interiorRing(r)
                    if ring_idx == r + 1:
                        new_int = cls.apply_fillet_to_curve(int_ring, vertex_idx, radius, segments_count, use_true_curve)
                        new_poly.addInteriorRing(new_int if new_int else int_ring.clone())
                    else:
                        new_poly.addInteriorRing(int_ring.clone())

                return QgsGeometry(new_poly)
            else:
                multi = geom.constGet()
                if not multi or part_idx >= multi.numGeometries():
                    return None
                new_multi = QgsMultiPolygon()
                for p in range(multi.numGeometries()):
                    poly = multi.geometryN(p)
                    if p == part_idx:
                        new_poly = QgsPolygon()
                        ext_ring = poly.exteriorRing()
                        if ext_ring is None:
                            new_multi.addGeometry(poly.clone())
                            continue
                        if ring_idx == 0:
                            new_ext = cls.apply_fillet_to_curve(ext_ring, vertex_idx, radius, segments_count, use_true_curve)
                            new_poly.setExteriorRing(new_ext if new_ext else ext_ring.clone())
                        else:
                            new_poly.setExteriorRing(ext_ring.clone())

                        for r in range(poly.numInteriorRings()):
                            int_ring = poly.interiorRing(r)
                            if ring_idx == r + 1:
                                new_int = cls.apply_fillet_to_curve(int_ring, vertex_idx, radius, segments_count, use_true_curve)
                                new_poly.addInteriorRing(new_int if new_int else int_ring.clone())
                            else:
                                new_poly.addInteriorRing(int_ring.clone())
                        new_multi.addGeometry(new_poly)
                    else:
                        new_multi.addGeometry(poly.clone())
                return QgsGeometry(new_multi)

        return None

    @classmethod
    def apply_chamfer_to_geometry(
        cls,
        geom: QgsGeometry,
        part_idx: int,
        ring_idx: int,
        vertex_idx: int,
        dist1: float,
        dist2: float,
    ) -> Optional[QgsGeometry]:
        """
        Applies chamfer to a specific vertex in any QgsGeometry.
        """
        if geom.isEmpty() or geom.isNull():
            return None

        geom_type = geom.type()
        is_multi = geom.isMultipart()

        if geom_type == QgsWkbTypes.GeometryType.LineGeometry:
            if not is_multi:
                curve = geom.constGet()
                if not curve:
                    return None
                new_curve = cls.apply_chamfer_to_curve(curve, vertex_idx, dist1, dist2)
                if new_curve:
                    return QgsGeometry(new_curve)
            else:
                multi = geom.constGet()
                if not multi or part_idx >= multi.numGeometries():
                    return None
                new_multi = QgsMultiLineString()
                for p in range(multi.numGeometries()):
                    c = multi.geometryN(p)
                    if p == part_idx:
                        nc = cls.apply_chamfer_to_curve(c, vertex_idx, dist1, dist2)
                        new_multi.addGeometry(nc if nc else c.clone())
                    else:
                        new_multi.addGeometry(c.clone())
                return QgsGeometry(new_multi)

        elif geom_type == QgsWkbTypes.GeometryType.PolygonGeometry:
            if not is_multi:
                poly = geom.constGet()
                if not poly:
                    return None
                new_poly = QgsPolygon()
                ext_ring = poly.exteriorRing()
                if ext_ring is None:
                    return None

                if ring_idx == 0:
                    new_ext = cls.apply_chamfer_to_curve(ext_ring, vertex_idx, dist1, dist2)
                    new_poly.setExteriorRing(new_ext if new_ext else ext_ring.clone())
                else:
                    new_poly.setExteriorRing(ext_ring.clone())

                for r in range(poly.numInteriorRings()):
                    int_ring = poly.interiorRing(r)
                    if ring_idx == r + 1:
                        new_int = cls.apply_chamfer_to_curve(int_ring, vertex_idx, dist1, dist2)
                        new_poly.addInteriorRing(new_int if new_int else int_ring.clone())
                    else:
                        new_poly.addInteriorRing(int_ring.clone())

                return QgsGeometry(new_poly)
            else:
                multi = geom.constGet()
                if not multi or part_idx >= multi.numGeometries():
                    return None
                new_multi = QgsMultiPolygon()
                for p in range(multi.numGeometries()):
                    poly = multi.geometryN(p)
                    if p == part_idx:
                        new_poly = QgsPolygon()
                        ext_ring = poly.exteriorRing()
                        if ext_ring is None:
                            new_multi.addGeometry(poly.clone())
                            continue
                        if ring_idx == 0:
                            new_ext = cls.apply_chamfer_to_curve(ext_ring, vertex_idx, dist1, dist2)
                            new_poly.setExteriorRing(new_ext if new_ext else ext_ring.clone())
                        else:
                            new_poly.setExteriorRing(ext_ring.clone())

                        for r in range(poly.numInteriorRings()):
                            int_ring = poly.interiorRing(r)
                            if ring_idx == r + 1:
                                new_int = cls.apply_chamfer_to_curve(int_ring, vertex_idx, dist1, dist2)
                                new_poly.addInteriorRing(new_int if new_int else int_ring.clone())
                            else:
                                new_poly.addInteriorRing(int_ring.clone())
                        new_multi.addGeometry(new_poly)
                    else:
                        new_multi.addGeometry(poly.clone())
                return QgsGeometry(new_multi)

        return None

    @classmethod
    def get_vertex_curve(
        cls,
        geom: QgsGeometry,
        part_idx: int,
        ring_idx: int,
    ) -> Optional[QgsAbstractGeometry]:
        """Extracts the specific sub-curve (ring or line part) containing the vertex."""
        if geom.isEmpty() or geom.isNull():
            return None
        geom_type = geom.type()
        is_multi = geom.isMultipart()
        if geom_type == QgsWkbTypes.GeometryType.LineGeometry:
            if not is_multi:
                return geom.constGet()
            else:
                multi = geom.constGet()
                if multi and part_idx < multi.numGeometries():
                    return multi.geometryN(part_idx)
        elif geom_type == QgsWkbTypes.GeometryType.PolygonGeometry:
            if not is_multi:
                poly = geom.constGet()
                if poly:
                    if ring_idx == 0:
                        return poly.exteriorRing()
                    elif ring_idx - 1 < poly.numInteriorRings():
                        return poly.interiorRing(ring_idx - 1)
            else:
                multi = geom.constGet()
                if multi and part_idx < multi.numGeometries():
                    poly = multi.geometryN(part_idx)
                    if poly:
                        if ring_idx == 0:
                            return poly.exteriorRing()
                        elif ring_idx - 1 < poly.numInteriorRings():
                            return poly.interiorRing(ring_idx - 1)
        return None

    @classmethod
    def compute_tangent_points_for_vertex(
        cls,
        geom: QgsGeometry,
        part_idx: int,
        ring_idx: int,
        vertex_idx: int,
        is_fillet: bool,
        val1: float,
        val2: float = 0.0,
    ) -> Tuple[Optional[QgsPointXY], Optional[QgsPointXY]]:
        """
        Returns (t1, t2) tangent/cut points on adjacent segments for the given vertex.
        """
        curve = cls.get_vertex_curve(geom, part_idx, ring_idx)
        if not curve:
            return None, None
        num_vertices = curve.numPoints() if hasattr(curve, "numPoints") else 0
        if num_vertices < 3:
            return None, None

        is_closed = curve.isClosed() if hasattr(curve, "isClosed") else False
        if is_closed:
            effective_count = num_vertices - 1 if (curve.pointN(0) == curve.pointN(num_vertices - 1)) else num_vertices
            if effective_count < 3:
                return None, None
            idx_curr = vertex_idx % effective_count
            idx_prev = (idx_curr - 1) % effective_count
            idx_next = (idx_curr + 1) % effective_count
        else:
            if vertex_idx <= 0 or vertex_idx >= num_vertices - 1:
                return None, None
            idx_curr = vertex_idx
            idx_prev = vertex_idx - 1
            idx_next = vertex_idx + 1

        p_prev = curve.pointN(idx_prev)
        v = curve.pointN(idx_curr)
        p_next = curve.pointN(idx_next)

        if is_fillet:
            success, t1, _, t2, _ = cls.compute_fillet_points(p_prev, v, p_next, val1)
            if success and t1 and t2:
                return QgsPointXY(t1.x(), t1.y()), QgsPointXY(t2.x(), t2.y())
        else:
            d2 = val2 if val2 > 0 else val1
            success, c1, c2 = cls.compute_chamfer_points(p_prev, v, p_next, val1, d2)
            if success and c1 and c2:
                return QgsPointXY(c1.x(), c1.y()), QgsPointXY(c2.x(), c2.y())

        return None, None

    @classmethod
    def get_adjacent_points(
        cls,
        geom: QgsGeometry,
        part_idx: int,
        ring_idx: int,
        vertex_idx: int,
    ) -> Tuple[Optional[QgsPointXY], Optional[QgsPointXY], Optional[QgsPointXY]]:
        """
        Returns (p_prev, v, p_next) for the specified vertex.
        """
        curve = cls.get_vertex_curve(geom, part_idx, ring_idx)
        if not curve:
            return None, None, None
        num_vertices = curve.numPoints() if hasattr(curve, "numPoints") else 0
        if num_vertices < 3:
            return None, None, None

        is_closed = curve.isClosed() if hasattr(curve, "isClosed") else False
        if is_closed:
            effective_count = num_vertices - 1 if (curve.pointN(0) == curve.pointN(num_vertices - 1)) else num_vertices
            if effective_count < 3:
                return None, None, None
            idx_curr = vertex_idx % effective_count
            idx_prev = (idx_curr - 1) % effective_count
            idx_next = (idx_curr + 1) % effective_count
        else:
            if vertex_idx <= 0 or vertex_idx >= num_vertices - 1:
                return None, None, None
            idx_curr = vertex_idx
            idx_prev = vertex_idx - 1
            idx_next = vertex_idx + 1

        p_prev = curve.pointN(idx_prev)
        v = curve.pointN(idx_curr)
        p_next = curve.pointN(idx_next)

        return (
            QgsPointXY(p_prev.x(), p_prev.y()),
            QgsPointXY(v.x(), v.y()),
            QgsPointXY(p_next.x(), p_next.y()),
        )

    @staticmethod
    def compute_line_intersection(
        p1: Union[QgsPoint, QgsPointXY],
        p2: Union[QgsPoint, QgsPointXY],
        p3: Union[QgsPoint, QgsPointXY],
        p4: Union[QgsPoint, QgsPointXY],
        epsilon: float = 1e-10,
    ) -> Optional[QgsPoint]:
        """
        Intersects the infinite line passing through (p1 -> p2) with the line passing through (p3 -> p4).
        Returns QgsPoint of intersection or None if parallel/colinear.
        """
        dx1 = p2.x() - p1.x()
        dy1 = p2.y() - p1.y()
        dx2 = p4.x() - p3.x()
        dy2 = p4.y() - p3.y()
        det = dx1 * dy2 - dy1 * dx2
        if abs(det) < epsilon:
            return None
        dx = p3.x() - p1.x()
        dy = p3.y() - p1.y()
        t = (dx * dy2 - dy * dx2) / det
        return QgsPoint(p1.x() + t * dx1, p1.y() + t * dy1)

    @classmethod
    def batch_apply_geometry(
        cls,
        geom: QgsGeometry,
        mode: str,
        radius: float = 0.0,
        segments_count: int = 8,
        dist1: float = 0.0,
        dist2: float = 0.0,
        use_true_curve: bool = False,
    ) -> Optional[QgsGeometry]:
        """
        Batch applies fillet or chamfer to all corners of all parts and rings in the geometry.
        """
        if geom.isEmpty() or geom.isNull():
            return None

        geom_type = geom.type()
        is_multi = geom.isMultipart()
        curr_geom = QgsGeometry(geom)

        if geom_type == QgsWkbTypes.GeometryType.LineGeometry:
            abstract_geom = curr_geom.constGet()
            if not abstract_geom:
                return None
            num_parts = abstract_geom.numGeometries() if is_multi else 1
            for part_idx in range(num_parts):
                curve = cls.get_vertex_curve(curr_geom, part_idx, 0)
                if not curve:
                    continue
                n_pts = curve.numPoints()
                if n_pts < 3:
                    continue
                is_closed = curve.isClosed()
                start_v = n_pts - 2 if is_closed else n_pts - 2
                end_v = 0 if is_closed else 1
                for v_idx in range(start_v, end_v - 1, -1):
                    if mode == "fillet":
                        res = cls.apply_fillet_to_geometry(
                            curr_geom, part_idx, 0, v_idx, radius, segments_count, use_true_curve
                        )
                    elif mode == "chamfer":
                        res = cls.apply_chamfer_to_geometry(
                            curr_geom, part_idx, 0, v_idx, dist1, dist2
                        )
                    else:
                        res = None

                    if res and not res.isEmpty():
                        curr_geom = res

        elif geom_type == QgsWkbTypes.GeometryType.PolygonGeometry:
            abstract_geom = curr_geom.constGet()
            if not abstract_geom:
                return None
            num_parts = abstract_geom.numGeometries() if is_multi else 1
            for part_idx in range(num_parts):
                poly = abstract_geom.geometryN(part_idx) if is_multi else abstract_geom
                if not poly or not hasattr(poly, "numInteriorRings"):
                    continue
                num_rings = 1 + poly.numInteriorRings()
                for ring_idx in range(num_rings):
                    ring_curve = cls.get_vertex_curve(curr_geom, part_idx, ring_idx)
                    if not ring_curve:
                        continue
                    n_pts = ring_curve.numPoints()
                    effective_count = (
                        n_pts - 1
                        if (n_pts > 1 and ring_curve.pointN(0) == ring_curve.pointN(n_pts - 1))
                        else n_pts
                    )
                    if effective_count < 3:
                        continue
                    for v_idx in range(effective_count - 1, -1, -1):
                        if mode == "fillet":
                            res = cls.apply_fillet_to_geometry(
                                curr_geom, part_idx, ring_idx, v_idx, radius, segments_count, use_true_curve
                            )
                        elif mode == "chamfer":
                            res = cls.apply_chamfer_to_geometry(
                                curr_geom, part_idx, ring_idx, v_idx, dist1, dist2
                            )
                        else:
                            res = None

                        if res and not res.isEmpty():
                            curr_geom = res

        return curr_geom

    @classmethod
    def restore_sharp_corner_between_segments_in_curve(
        cls,
        curve: QgsLineString,
        seg1_idx: int,
        seg2_idx: int,
    ) -> Optional[Tuple[QgsLineString, QgsPoint]]:
        """
        Reconstructs sharp corner between seg1 (p[seg1] -> p[seg1+1]) and seg2 (p[seg2] -> p[seg2+1]).
        Removes all intermediate vertices (the fillet/chamfer curve) between the two segments and inserts V_sharp.
        """
        if not curve or curve.numPoints() < 3:
            return None

        num_pts = curve.numPoints()
        is_closed = curve.isClosed()
        effective_count = (
            num_pts - 1
            if (is_closed and num_pts > 1 and curve.pointN(0) == curve.pointN(num_pts - 1))
            else num_pts
        )

        if seg1_idx == seg2_idx:
            return None

        def get_pt(idx):
            return curve.pointN(idx % effective_count if is_closed else idx)

        # In open LineString
        if not is_closed:
            a = min(seg1_idx, seg2_idx)
            b = max(seg1_idx, seg2_idx)
            if a + 1 > b or b + 1 >= num_pts:
                return None

            p_a = get_pt(a)
            p_a1 = get_pt(a + 1)
            p_b = get_pt(b)
            p_b1 = get_pt(b + 1)

            # Line 1: p_a -> p_a1. Line 2: p_b1 -> p_b
            v_sharp = cls.compute_line_intersection(p_a, p_a1, p_b1, p_b)
            if not v_sharp:
                return None

            # Build new points: [0..a] + [v_sharp] + [b+1..num_pts-1]
            new_pts = (
                [get_pt(i) for i in range(a + 1)]
                + [v_sharp]
                + [get_pt(i) for i in range(b + 1, num_pts)]
            )
            res = QgsLineString()
            for pt in new_pts:
                res.addVertex(pt)
            return res, v_sharp

        # In closed Polygon / closed LineString
        candidates = []
        for s_from, s_to in [(seg1_idx, seg2_idx), (seg2_idx, seg1_idx)]:
            if s_to >= s_from + 1:
                removed_count = s_to - s_from
            else:
                removed_count = (effective_count - s_from - 1) + s_to + 1

            p_from = get_pt(s_from)
            p_from1 = get_pt(s_from + 1)
            p_to = get_pt(s_to)
            p_to1 = get_pt(s_to + 1)

            v_sharp = cls.compute_line_intersection(p_from, p_from1, p_to1, p_to)
            if not v_sharp:
                continue

            vin_x = p_from1.x() - p_from.x()
            vin_y = p_from1.y() - p_from.y()
            vout_x = p_to.x() - p_to1.x()
            vout_y = p_to.y() - p_to1.y()

            dot_in = vin_x * (v_sharp.x() - p_from1.x()) + vin_y * (v_sharp.y() - p_from1.y())
            dot_out = vout_x * (v_sharp.x() - p_to.x()) + vout_y * (v_sharp.y() - p_to.y())

            # Forward projection check
            if dot_in > -1e-5 and dot_out > -1e-5:
                candidates.append((removed_count, s_from, s_to, v_sharp))

        if not candidates:
            # Fallback: if dot product is slightly negative due to floating tolerance, take any valid intersection
            for s_from, s_to in [(seg1_idx, seg2_idx), (seg2_idx, seg1_idx)]:
                if s_to >= s_from + 1:
                    removed_count = s_to - s_from
                else:
                    removed_count = (effective_count - s_from - 1) + s_to + 1
                p_from = get_pt(s_from)
                p_from1 = get_pt(s_from + 1)
                p_to = get_pt(s_to)
                p_to1 = get_pt(s_to + 1)
                v_sharp = cls.compute_line_intersection(p_from, p_from1, p_to1, p_to)
                if v_sharp:
                    candidates.append((removed_count, s_from, s_to, v_sharp))

        if not candidates:
            return None

        candidates.sort(key=lambda x: x[0])
        _, s_from, s_to, v_sharp = candidates[0]

        if s_to >= s_from + 1:
            preserved_before = [get_pt(i) for i in range(s_from + 1)]
            preserved_after = [get_pt(i) for i in range(s_to + 1, effective_count)]
            new_pts = preserved_before + [v_sharp] + preserved_after
        else:
            preserved = [get_pt(i) for i in range(s_to + 1, s_from + 1)]
            new_pts = preserved + [v_sharp]

        if new_pts and (new_pts[0].x() != new_pts[-1].x() or new_pts[0].y() != new_pts[-1].y()):
            new_pts.append(QgsPoint(new_pts[0].x(), new_pts[0].y()))

        res = QgsLineString()
        for pt in new_pts:
            res.addVertex(pt)
        return res, v_sharp

    @classmethod
    def restore_sharp_corner_between_segments(
        cls,
        geom: QgsGeometry,
        part_idx: int,
        ring_idx: int,
        seg1_idx: int,
        seg2_idx: int,
    ) -> Optional[Tuple[QgsGeometry, QgsPoint]]:
        """
        Replaces the curve between seg1 and seg2 with a sharp intersection corner V_sharp.
        Returns (new_geometry, v_sharp) or None.
        """
        if geom.isEmpty() or geom.isNull():
            return None

        geom_type = geom.type()
        is_multi = geom.isMultipart()

        if geom_type == QgsWkbTypes.GeometryType.LineGeometry:
            if not is_multi:
                curve = geom.constGet()
                if not curve or not isinstance(curve, QgsLineString):
                    return None
                res = cls.restore_sharp_corner_between_segments_in_curve(curve, seg1_idx, seg2_idx)
                if not res:
                    return None
                new_curve, v_sharp = res
                return QgsGeometry(new_curve), v_sharp
            else:
                multi = geom.constGet()
                if not multi or part_idx >= multi.numGeometries():
                    return None
                new_multi = QgsMultiLineString()
                v_sharp_res = None
                for p in range(multi.numGeometries()):
                    line = multi.geometryN(p)
                    if p == part_idx:
                        res = cls.restore_sharp_corner_between_segments_in_curve(line, seg1_idx, seg2_idx)
                        if res:
                            new_line, v_sharp_res = res
                            new_multi.addGeometry(new_line)
                        else:
                            new_multi.addGeometry(line.clone())
                    else:
                        new_multi.addGeometry(line.clone())
                return (QgsGeometry(new_multi), v_sharp_res) if v_sharp_res else None

        elif geom_type == QgsWkbTypes.GeometryType.PolygonGeometry:
            if not is_multi:
                poly = geom.constGet()
                if not poly:
                    return None
                new_poly = QgsPolygon()
                ext_ring = poly.exteriorRing()
                if ext_ring is None:
                    return None

                v_sharp_res = None
                if ring_idx == 0:
                    res = cls.restore_sharp_corner_between_segments_in_curve(ext_ring, seg1_idx, seg2_idx)
                    if res:
                        new_ext, v_sharp_res = res
                        new_poly.setExteriorRing(new_ext)
                    else:
                        new_poly.setExteriorRing(ext_ring.clone())
                else:
                    new_poly.setExteriorRing(ext_ring.clone())

                for r in range(poly.numInteriorRings()):
                    int_ring = poly.interiorRing(r)
                    if ring_idx == r + 1:
                        res = cls.restore_sharp_corner_between_segments_in_curve(int_ring, seg1_idx, seg2_idx)
                        if res:
                            new_int, v_sharp_res = res
                            new_poly.addInteriorRing(new_int)
                        else:
                            new_poly.addInteriorRing(int_ring.clone())
                    else:
                        new_poly.addInteriorRing(int_ring.clone())

                return (QgsGeometry(new_poly), v_sharp_res) if v_sharp_res else None
            else:
                multi = geom.constGet()
                if not multi or part_idx >= multi.numGeometries():
                    return None
                new_multi = QgsMultiPolygon()
                v_sharp_res = None
                for p in range(multi.numGeometries()):
                    poly = multi.geometryN(p)
                    if p == part_idx:
                        new_poly = QgsPolygon()
                        ext_ring = poly.exteriorRing()
                        if ext_ring is None:
                            new_multi.addGeometry(poly.clone())
                            continue
                        if ring_idx == 0:
                            res = cls.restore_sharp_corner_between_segments_in_curve(ext_ring, seg1_idx, seg2_idx)
                            if res:
                                new_ext, v_sharp_res = res
                                new_poly.setExteriorRing(new_ext)
                            else:
                                new_poly.setExteriorRing(ext_ring.clone())
                        else:
                            new_poly.setExteriorRing(ext_ring.clone())

                        for r in range(poly.numInteriorRings()):
                            int_ring = poly.interiorRing(r)
                            if ring_idx == r + 1:
                                res = cls.restore_sharp_corner_between_segments_in_curve(int_ring, seg1_idx, seg2_idx)
                                if res:
                                    new_int, v_sharp_res = res
                                    new_poly.addInteriorRing(new_int)
                                else:
                                    new_poly.addInteriorRing(int_ring.clone())
                            else:
                                new_poly.addInteriorRing(int_ring.clone())
                        new_multi.addGeometry(new_poly)
                    else:
                        new_multi.addGeometry(poly.clone())

                return (QgsGeometry(new_multi), v_sharp_res) if v_sharp_res else None

    @classmethod
    def fillet_or_chamfer_two_lines(
        cls,
        geom1: QgsGeometry,
        seg1_idx: int,
        click_pt1: Union[QgsPoint, QgsPointXY],
        geom2: QgsGeometry,
        seg2_idx: int,
        click_pt2: Union[QgsPoint, QgsPointXY],
        mode: str = "fillet",
        radius: float = 1.0,
        dist1: float = 1.0,
        dist2: float = 1.0,
        segments_count: int = 12,
        use_true_curve: bool = False,
    ) -> Optional[Tuple[QgsGeometry, QgsPoint, QgsPoint, QgsPoint]]:
        """
        Performs CAD Fillet or Chamfer between two line geometries, trimming/extending them
        and stitching them into a single continuous QgsLineString geometry.

        Returns: (new_geometry, v_intersection, t1, t2) or None
        """
        if not geom1 or geom1.isEmpty() or not geom2 or geom2.isEmpty():
            return None

        curve1 = geom1.constGet()
        curve2 = geom2.constGet()
        if not curve1 or not curve2:
            return None

        if isinstance(curve1, QgsMultiLineString):
            curve1 = curve1.geometryN(0) if curve1.numGeometries() > 0 else None
        if isinstance(curve2, QgsMultiLineString):
            curve2 = curve2.geometryN(0) if curve2.numGeometries() > 0 else None

        if not isinstance(curve1, QgsLineString) or not isinstance(curve2, QgsLineString):
            return None

        n1 = curve1.numPoints()
        n2 = curve2.numPoints()
        if n1 < 2 or n2 < 2:
            return None
        if seg1_idx < 0 or seg1_idx >= n1 - 1 or seg2_idx < 0 or seg2_idx >= n2 - 1:
            return None

        a1, b1 = curve1.pointN(seg1_idx), curve1.pointN(seg1_idx + 1)
        a2, b2 = curve2.pointN(seg2_idx), curve2.pointN(seg2_idx + 1)

        v = cls.compute_line_intersection(a1, b1, a2, b2)
        if not v:
            return None

        # Line 1 ray direction
        d1x = b1.x() - a1.x()
        d1y = b1.y() - a1.y()
        len1 = math.hypot(d1x, d1y)
        if len1 < cls.EPSILON:
            return None
        ud1x, ud1y = d1x / len1, d1y / len1

        t_click1 = (click_pt1.x() - v.x()) * ud1x + (click_pt1.y() - v.y()) * ud1y
        if abs(t_click1) < 1e-6:
            p0 = curve1.pointN(0)
            pn1 = curve1.pointN(n1 - 1)
            t0 = (p0.x() - v.x()) * ud1x + (p0.y() - v.y()) * ud1y
            t_end = (pn1.x() - v.x()) * ud1x + (pn1.y() - v.y()) * ud1y
            t_click1 = t0 if abs(t0) > abs(t_end) else t_end

        u1x = ud1x if t_click1 > 0 else -ud1x
        u1y = ud1y if t_click1 > 0 else -ud1y

        # Line 2 ray direction
        d2x = b2.x() - a2.x()
        d2y = b2.y() - a2.y()
        len2 = math.hypot(d2x, d2y)
        if len2 < cls.EPSILON:
            return None
        ud2x, ud2y = d2x / len2, d2y / len2

        t_click2 = (click_pt2.x() - v.x()) * ud2x + (click_pt2.y() - v.y()) * ud2y
        if abs(t_click2) < 1e-6:
            p0 = curve2.pointN(0)
            pn2 = curve2.pointN(n2 - 1)
            t0 = (p0.x() - v.x()) * ud2x + (p0.y() - v.y()) * ud2y
            t_end = (pn2.x() - v.x()) * ud2x + (pn2.y() - v.y()) * ud2y
            t_click2 = t0 if abs(t0) > abs(t_end) else t_end

        u2x = ud2x if t_click2 > 0 else -ud2x
        u2y = ud2y if t_click2 > 0 else -ud2y

        # Angle between rays
        dot = u1x * u2x + u1y * u2y
        dot = max(-1.0, min(1.0, dot))
        angle = math.acos(dot)
        if angle < 1e-6 or angle > (math.pi - 1e-6):
            return None

        half_angle = angle / 2.0
        tan_half = math.tan(half_angle)
        sin_half = math.sin(half_angle)

        # Maximum extents along rays u1 and u2 from intersection v restricted strictly to the selected segments
        a1, b1 = curve1.pointN(seg1_idx), curve1.pointN(seg1_idx + 1)
        sa1 = (a1.x() - v.x()) * u1x + (a1.y() - v.y()) * u1y
        sb1 = (b1.x() - v.x()) * u1x + (b1.y() - v.y()) * u1y
        max_len1 = max(0.0, max(sa1, sb1))

        a2, b2 = curve2.pointN(seg2_idx), curve2.pointN(seg2_idx + 1)
        sa2 = (a2.x() - v.x()) * u2x + (a2.y() - v.y()) * u2y
        sb2 = (b2.x() - v.x()) * u2x + (b2.y() - v.y()) * u2y
        max_len2 = max(0.0, max(sa2, sb2))

        if max_len1 < 1e-6 or max_len2 < 1e-6:
            return None

        if mode == "fillet":
            if radius <= 0:
                t1 = v
                t2 = v
                arc_pts = [v]
            else:
                max_tangent = min(max_len1, max_len2) * 0.9999
                tangent_dist = min(radius / tan_half, max_tangent)
                eff_radius = tangent_dist * tan_half

                t1 = QgsPoint(v.x() + tangent_dist * u1x, v.y() + tangent_dist * u1y)
                t2 = QgsPoint(v.x() + tangent_dist * u2x, v.y() + tangent_dist * u2y)

                bx, by, blen = cls.normalize_vector(u1x + u2x, u1y + u2y)
                center_dist = eff_radius / sin_half
                cx = v.x() + center_dist * bx
                cy = v.y() + center_dist * by

                arc_mid = QgsPoint(cx - eff_radius * bx, cy - eff_radius * by)
                arc_pts = cls.segmentize_arc_3p(t1, arc_mid, t2, segments_count)
        elif mode == "chamfer":
            d1_in = dist1 if dist1 > 0 else 0.0
            d2_in = dist2 if dist2 > 0 else d1_in
            if d1_in <= 0 and d2_in <= 0:
                t1 = v
                t2 = v
                arc_pts = [v]
            else:
                d1 = min(d1_in, max_len1 * 0.9999)
                d2 = min(d2_in, max_len2 * 0.9999)
                t1 = QgsPoint(v.x() + d1 * u1x, v.y() + d1 * u1y)
                t2 = QgsPoint(v.x() + d2 * u2x, v.y() + d2 * u2y)
                arc_pts = [t1, t2]
        else:
            return None

        # Check if operation is on the same closed ring
        is_closed1 = (n1 >= 4 and cls.distance(curve1.pointN(0), curve1.pointN(n1 - 1)) < 1e-6)
        is_closed2 = (n2 >= 4 and cls.distance(curve2.pointN(0), curve2.pointN(n2 - 1)) < 1e-6)
        is_same_closed_ring = (
            is_closed1
            and is_closed2
            and (
                curve1 == curve2
                or (
                    n1 == n2
                    and cls.distance(curve1.pointN(0), curve2.pointN(0)) < 1e-6
                    and cls.distance(curve1.pointN(1), curve2.pointN(1)) < 1e-6
                )
            )
        )

        if is_same_closed_ring:
            m = n1 - 1
            a1, b1 = curve1.pointN(seg1_idx), curve1.pointN((seg1_idx + 1) % m)
            sa1 = (a1.x() - v.x()) * u1x + (a1.y() - v.y()) * u1y
            sb1 = (b1.x() - v.x()) * u1x + (b1.y() - v.y()) * u1y
            if sa1 >= sb1:
                far1, near1 = seg1_idx, (seg1_idx + 1) % m
            else:
                far1, near1 = (seg1_idx + 1) % m, seg1_idx

            a2, b2 = curve2.pointN(seg2_idx), curve2.pointN((seg2_idx + 1) % m)
            sa2 = (a2.x() - v.x()) * u2x + (a2.y() - v.y()) * u2y
            sb2 = (b2.x() - v.x()) * u2x + (b2.y() - v.y()) * u2y
            if sa2 >= sb2:
                far2, near2 = seg2_idx, (seg2_idx + 1) % m
            else:
                far2, near2 = (seg2_idx + 1) % m, seg2_idx

            # Walk along ring from far2 towards far1 away from near2
            step = -1 if near2 == (far2 + 1) % m else 1

            ring_pts = []
            curr = far2
            for _ in range(m + 1):
                ring_pts.append(curve1.pointN(curr))
                if curr == far1:
                    break
                curr = (curr + step + m) % m

            full_pts = arc_pts + ring_pts + [arc_pts[0]]
        else:
            # Segment 1 points
            a1, b1 = curve1.pointN(seg1_idx), curve1.pointN(seg1_idx + 1)
            sa1 = (a1.x() - v.x()) * u1x + (a1.y() - v.y()) * u1y
            sb1 = (b1.x() - v.x()) * u1x + (b1.y() - v.y()) * u1y

            # Line 1 topological chain towards t1:
            # If sa1 >= sb1, b1 is closer to V so we keep prefix 0 -> seg1_idx (a1).
            # If sb1 > sa1, a1 is closer to V so we keep suffix n1 - 1 down to seg1_idx + 1 (b1).
            l1_pts = []
            if sa1 >= sb1:
                for i in range(0, seg1_idx + 1):
                    l1_pts.append(curve1.pointN(i))
            else:
                for i in range(n1 - 1, seg1_idx, -1):
                    l1_pts.append(curve1.pointN(i))

            # Segment 2 points
            a2, b2 = curve2.pointN(seg2_idx), curve2.pointN(seg2_idx + 1)
            sa2 = (a2.x() - v.x()) * u2x + (a2.y() - v.y()) * u2y
            sb2 = (b2.x() - v.x()) * u2x + (b2.y() - v.y()) * u2y

            # Line 2 topological chain from t2 towards far end:
            # If sa2 >= sb2, b2 is closer to V so from t2 we connect to a2 (seg2_idx) down to 0.
            # If sb2 > sa2, a2 is closer to V so from t2 we connect to b2 (seg2_idx + 1) up to n2 - 1.
            l2_pts = []
            if sa2 >= sb2:
                for i in range(seg2_idx, -1, -1):
                    l2_pts.append(curve2.pointN(i))
            else:
                for i in range(seg2_idx + 1, n2):
                    l2_pts.append(curve2.pointN(i))

            # Stitch all points
            full_pts = l1_pts + arc_pts + l2_pts

        clean_pts = []
        for pt in full_pts:
            if not clean_pts or cls.distance(clean_pts[-1], pt) > 1e-7:
                clean_pts.append(pt)

        if len(clean_pts) < 2:
            return None

        res_line = QgsLineString()
        for pt in clean_pts:
            res_line.addVertex(pt)

        return QgsGeometry(res_line), v, t1, t2

    @classmethod
    def calculate_bearing(
        cls,
        center: Union[QgsPoint, QgsPointXY],
        pt: Union[QgsPoint, QgsPointXY],
    ) -> float:
        """
        Calculates the mathematical angle (in degrees, CCW from positive X-axis)
        of the vector from center to pt.
        """
        dx = pt.x() - center.x()
        dy = pt.y() - center.y()
        return math.degrees(math.atan2(dy, dx))

    @classmethod
    def calculate_rotation_angle(
        cls,
        center: Union[QgsPoint, QgsPointXY],
        base_pt: Union[QgsPoint, QgsPointXY],
        target_pt: Union[QgsPoint, QgsPointXY],
    ) -> float:
        """
        Calculates the counter-clockwise rotation angle in degrees from base_pt to target_pt around center.
        Normalized to (-180.0, 180.0].
        """
        a_base = math.atan2(base_pt.y() - center.y(), base_pt.x() - center.x())
        a_target = math.atan2(target_pt.y() - center.y(), target_pt.x() - center.x())
        delta_deg = math.degrees(a_target - a_base)
        # Normalize to (-180, 180]
        while delta_deg <= -180.0:
            delta_deg += 360.0
        while delta_deg > 180.0:
            delta_deg -= 360.0
        return delta_deg

    @classmethod
    def rotate_geometry(
        cls,
        geom: QgsGeometry,
        center: Union[QgsPoint, QgsPointXY],
        angle_degrees_ccw: float,
    ) -> QgsGeometry:
        """
        Rotates a QgsGeometry around center by angle_degrees_ccw (counter-clockwise).
        """
        if geom.isEmpty() or geom.isNull() or abs(angle_degrees_ccw) < cls.EPSILON:
            return QgsGeometry(geom)

        rotated = QgsGeometry(geom)
        center_pt = QgsPointXY(center.x(), center.y())
        # QgsGeometry.rotate takes degrees clockwise, so we negate angle_degrees_ccw
        rotated.rotate(-angle_degrees_ccw, center_pt)
        return rotated

    @classmethod
    def mirror_point(
        cls,
        p: Union[QgsPoint, QgsPointXY],
        p1: Union[QgsPoint, QgsPointXY],
        p2: Union[QgsPoint, QgsPointXY],
    ) -> QgsPoint:
        """
        Reflects a point p across the infinite axis line passing through p1 and p2.
        """
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        len_sq = dx * dx + dy * dy
        is_3d = getattr(p, "is3D", lambda: False)()
        is_m = getattr(p, "isMeasure", lambda: False)()
        z_val = p.z() if is_3d else 0.0
        m_val = p.m() if is_m else 0.0

        if len_sq < 1e-12:
            if is_3d and is_m:
                return QgsPoint(p.x(), p.y(), z_val, m_val)
            elif is_3d:
                return QgsPoint(p.x(), p.y(), z_val)
            elif is_m:
                return QgsPoint(QgsWkbTypes.Type.PointM, p.x(), p.y(), 0.0, m_val)
            else:
                return QgsPoint(p.x(), p.y())

        vx = p.x() - p1.x()
        vy = p.y() - p1.y()

        length = math.sqrt(len_sq)
        ux, uy = dx / length, dy / length
        nx, ny = -uy, ux

        dist = vx * nx + vy * ny
        mx = p.x() - 2.0 * dist * nx
        my = p.y() - 2.0 * dist * ny

        if is_3d and is_m:
            return QgsPoint(mx, my, z_val, m_val)
        elif is_3d:
            return QgsPoint(mx, my, z_val)
        elif is_m:
            return QgsPoint(QgsWkbTypes.Type.PointM, mx, my, 0.0, m_val)
        else:
            return QgsPoint(mx, my)

    @classmethod
    def _mirror_abstract_geometry(cls, abstract_geom, p1, p2):
        """Recursively mirrors an abstract geometry (QgsAbstractGeometry subclass)."""
        if abstract_geom is None or abstract_geom.isEmpty():
            return abstract_geom.clone() if abstract_geom else None

        wkb_type = abstract_geom.wkbType()
        flat_type = QgsWkbTypes.flatType(wkb_type)

        if flat_type == QgsWkbTypes.Type.Point:
            return cls.mirror_point(abstract_geom, p1, p2)

        elif flat_type == QgsWkbTypes.Type.LineString or flat_type == QgsWkbTypes.Type.CircularString:
            if flat_type == QgsWkbTypes.Type.LineString:
                ls = QgsLineString()
                for i in range(abstract_geom.numPoints()):
                    m_pt = cls.mirror_point(abstract_geom.pointN(i), p1, p2)
                    ls.addVertex(m_pt)
                return ls
            else:
                clone = abstract_geom.clone()
                for i in range(clone.numPoints()):
                    m_pt = cls.mirror_point(clone.pointN(i), p1, p2)
                    clone.moveVertex(QgsVertexId(0, 0, i), m_pt)
                return clone

        elif flat_type == QgsWkbTypes.Type.Polygon:
            poly = QgsPolygon()
            ext_ring = abstract_geom.exteriorRing()
            if ext_ring:
                m_ext = cls._mirror_abstract_geometry(ext_ring, p1, p2)
                poly.setExteriorRing(m_ext)
            for r_idx in range(abstract_geom.numInteriorRings()):
                int_ring = abstract_geom.interiorRing(r_idx)
                m_int = cls._mirror_abstract_geometry(int_ring, p1, p2)
                poly.addInteriorRing(m_int)
            return poly

        elif QgsWkbTypes.isMultiType(wkb_type) or abstract_geom.isMultipart():
            geom_col = abstract_geom.createEmptyWithSameType()
            part_count = abstract_geom.partCount() if hasattr(abstract_geom, "partCount") else abstract_geom.numGeometries()
            for part_idx in range(part_count):
                sub_geom = abstract_geom.geometryN(part_idx)
                m_sub = cls._mirror_abstract_geometry(sub_geom, p1, p2)
                if m_sub:
                    geom_col.addGeometry(m_sub)
            return geom_col

        else:
            clone = abstract_geom.clone()
            for i in range(clone.nCoordinates()):
                pt = clone.vertexAt(QgsVertexId(0, 0, i))
                m_pt = cls.mirror_point(pt, p1, p2)
                clone.moveVertex(QgsVertexId(0, 0, i), m_pt)
            return clone

    @classmethod
    def mirror_geometry(
        cls,
        geom: QgsGeometry,
        p1: Union[QgsPoint, QgsPointXY],
        p2: Union[QgsPoint, QgsPointXY],
    ) -> QgsGeometry:
        """
        Reflects a QgsGeometry across the axis line passing through p1 and p2.
        """
        if geom.isEmpty() or geom.isNull():
            return QgsGeometry(geom)

        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        if dx * dx + dy * dy < 1e-12:
            return QgsGeometry(geom)

        abstract_geom = geom.constGet()
        mirrored_abstract = cls._mirror_abstract_geometry(abstract_geom, p1, p2)
        if mirrored_abstract:
            return QgsGeometry(mirrored_abstract)
        return QgsGeometry(geom)

    @classmethod
    def compute_3point_scale_and_rotation(
        cls,
        p_origin: Union[QgsPoint, QgsPointXY],
        p_ref: Union[QgsPoint, QgsPointXY],
        p_target: Union[QgsPoint, QgsPointXY],
        snap_step_deg: Optional[float] = None,
    ) -> Tuple[float, float]:
        """
        Calculates (scale_factor, delta_angle_degrees_ccw) from 3 points:
        p_origin: Center/Pivot point
        p_ref: Base Reference point
        p_target: Current Target point

        Returns: (scale_factor, delta_angle_deg) where delta_angle_deg is in (-180, 180].
        """
        dx_ref = p_ref.x() - p_origin.x()
        dy_ref = p_ref.y() - p_origin.y()
        len_ref = math.hypot(dx_ref, dy_ref)

        dx_tar = p_target.x() - p_origin.x()
        dy_tar = p_target.y() - p_origin.y()
        len_tar = math.hypot(dx_tar, dy_tar)

        if len_ref < cls.EPSILON:
            scale_factor = 1.0
            delta_deg = 0.0
        else:
            scale_factor = len_tar / len_ref
            a_ref = math.atan2(dy_ref, dx_ref)
            a_tar = math.atan2(dy_tar, dx_tar)
            delta_deg = math.degrees(a_tar - a_ref)

            # Snap delta_deg to snap_step_deg if provided
            if snap_step_deg is not None and snap_step_deg > 0:
                delta_deg = round(delta_deg / snap_step_deg) * snap_step_deg

            # Normalize to (-180, 180]
            while delta_deg <= -180.0:
                delta_deg += 360.0
            while delta_deg > 180.0:
                delta_deg -= 360.0

        return scale_factor, delta_deg

    @classmethod
    def scale_and_rotate_point(
        cls,
        p: Union[QgsPoint, QgsPointXY],
        center: Union[QgsPoint, QgsPointXY],
        scale_factor: float,
        angle_degrees_ccw: float,
    ) -> QgsPoint:
        """
        Transforms a point p by scaling by scale_factor and rotating by angle_degrees_ccw
        around center.
        """
        is_3d = getattr(p, "is3D", lambda: False)()
        is_m = getattr(p, "isMeasure", lambda: False)()
        z_val = p.z() if is_3d else 0.0
        m_val = p.m() if is_m else 0.0

        rad = math.radians(angle_degrees_ccw)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)

        dx = p.x() - center.x()
        dy = p.y() - center.y()

        nx = center.x() + scale_factor * (dx * cos_a - dy * sin_a)
        ny = center.y() + scale_factor * (dx * sin_a + dy * cos_a)

        if is_3d and is_m:
            return QgsPoint(nx, ny, z_val, m_val)
        elif is_3d:
            return QgsPoint(nx, ny, z_val)
        elif is_m:
            return QgsPoint(QgsWkbTypes.Type.PointM, nx, ny, 0.0, m_val)
        else:
            return QgsPoint(nx, ny)

    @classmethod
    def _scale_rotate_abstract_geometry(cls, abstract_geom, center, scale_factor, angle_degrees_ccw):
        """Recursively scales and rotates an abstract geometry (QgsAbstractGeometry subclass)."""
        if abstract_geom is None or abstract_geom.isEmpty():
            return abstract_geom.clone() if abstract_geom else None

        wkb_type = abstract_geom.wkbType()
        flat_type = QgsWkbTypes.flatType(wkb_type)

        if flat_type == QgsWkbTypes.Type.Point:
            return cls.scale_and_rotate_point(abstract_geom, center, scale_factor, angle_degrees_ccw)

        elif flat_type == QgsWkbTypes.Type.LineString or flat_type == QgsWkbTypes.Type.CircularString:
            if flat_type == QgsWkbTypes.Type.LineString:
                ls = QgsLineString()
                for i in range(abstract_geom.numPoints()):
                    sr_pt = cls.scale_and_rotate_point(abstract_geom.pointN(i), center, scale_factor, angle_degrees_ccw)
                    ls.addVertex(sr_pt)
                return ls
            else:
                clone = abstract_geom.clone()
                for i in range(clone.numPoints()):
                    sr_pt = cls.scale_and_rotate_point(clone.pointN(i), center, scale_factor, angle_degrees_ccw)
                    clone.moveVertex(QgsVertexId(0, 0, i), sr_pt)
                return clone

        elif flat_type == QgsWkbTypes.Type.Polygon:
            poly = QgsPolygon()
            ext_ring = abstract_geom.exteriorRing()
            if ext_ring:
                sr_ext = cls._scale_rotate_abstract_geometry(ext_ring, center, scale_factor, angle_degrees_ccw)
                poly.setExteriorRing(sr_ext)
            for r_idx in range(abstract_geom.numInteriorRings()):
                int_ring = abstract_geom.interiorRing(r_idx)
                sr_int = cls._scale_rotate_abstract_geometry(int_ring, center, scale_factor, angle_degrees_ccw)
                poly.addInteriorRing(sr_int)
            return poly

        elif QgsWkbTypes.isMultiType(wkb_type) or abstract_geom.isMultipart():
            geom_col = abstract_geom.createEmptyWithSameType()
            part_count = abstract_geom.partCount() if hasattr(abstract_geom, "partCount") else abstract_geom.numGeometries()
            for part_idx in range(part_count):
                sub_geom = abstract_geom.geometryN(part_idx)
                sr_sub = cls._scale_rotate_abstract_geometry(sub_geom, center, scale_factor, angle_degrees_ccw)
                if sr_sub:
                    geom_col.addGeometry(sr_sub)
            return geom_col

        else:
            clone = abstract_geom.clone()
            for i in range(clone.nCoordinates()):
                pt = clone.vertexAt(QgsVertexId(0, 0, i))
                sr_pt = cls.scale_and_rotate_point(pt, center, scale_factor, angle_degrees_ccw)
                clone.moveVertex(QgsVertexId(0, 0, i), sr_pt)
            return clone

    @classmethod
    def scale_and_rotate_geometry(
        cls,
        geom: QgsGeometry,
        center: Union[QgsPoint, QgsPointXY],
        scale_factor: float,
        angle_degrees_ccw: float,
    ) -> QgsGeometry:
        """
        Transforms a QgsGeometry by scaling by scale_factor and rotating by angle_degrees_ccw
        around center.
        """
        if geom.isEmpty() or geom.isNull():
            return QgsGeometry(geom)

        if abs(scale_factor - 1.0) < cls.EPSILON and abs(angle_degrees_ccw) < cls.EPSILON:
            return QgsGeometry(geom)

        abstract_geom = geom.constGet()
        sr_abstract = cls._scale_rotate_abstract_geometry(abstract_geom, center, scale_factor, angle_degrees_ccw)
        if sr_abstract:
            return QgsGeometry(sr_abstract)
        return QgsGeometry(geom)

    @classmethod
    def offset_segment_in_curve(
        cls,
        curve: QgsLineString,
        segment_idx: int,
        distance: float,
        mode: str = "extend",
    ) -> Optional[QgsLineString]:
        """
        Offsets a single segment (segment_idx) in curve by distance along its normal vector.
        Supports:
          - mode="extend": extends/trims adjacent segments to intersect the shifted line.
          - mode="step": inserts two perpendicular connector segments (jog).
        """
        if not curve or curve.numPoints() < 2:
            return None

        num_pts = curve.numPoints()
        is_closed = curve.isClosed() or (num_pts > 2 and curve.pointN(0) == curve.pointN(num_pts - 1))
        effective_count = num_pts - 1 if is_closed else num_pts

        if not is_closed and (segment_idx < 0 or segment_idx >= num_pts - 1):
            return None
        if is_closed and (segment_idx < 0 or segment_idx >= effective_count):
            return None

        if abs(distance) < cls.EPSILON:
            return curve.clone()

        i = segment_idx
        v_i = curve.pointN(i)
        v_next = curve.pointN((i + 1) % effective_count if is_closed else i + 1)

        dx = v_next.x() - v_i.x()
        dy = v_next.y() - v_i.y()
        length = math.hypot(dx, dy)
        if length < cls.EPSILON:
            return None

        # Unit tangent and normal vectors (left normal)
        ux = dx / length
        uy = dy / length
        nx = -dy / length
        ny = dx / length

        # Shifted endpoints of the segment
        p1 = QgsPoint(v_i.x() + distance * nx, v_i.y() + distance * ny)
        p2 = QgsPoint(v_next.x() + distance * nx, v_next.y() + distance * ny)

        if mode == "step":
            # Insert rectangular step / jog
            if not is_closed:
                if num_pts == 2:
                    # Single segment open polyline: simply shift the segment
                    new_pts = [p1, p2]
                elif i == 0:
                    # First segment of open polyline: starts at p1 -> p2 -> v1 -> v2 ...
                    new_pts = [p1, p2] + [curve.pointN(k) for k in range(1, num_pts)]
                elif i == num_pts - 2:
                    # Last segment of open polyline: v0 -> ... -> v_{n-2} -> p1 -> p2
                    new_pts = [curve.pointN(k) for k in range(0, num_pts - 1)] + [p1, p2]
                else:
                    # Middle segment: v0 -> ... -> v_i -> p1 -> p2 -> v_{i+1} -> ... -> v_{n-1}
                    new_pts = (
                        [curve.pointN(k) for k in range(0, i + 1)]
                        + [p1, p2]
                        + [curve.pointN(k) for k in range(i + 1, num_pts)]
                    )
            else:
                if i == effective_count - 1:
                    new_pts = (
                        [curve.pointN(k) for k in range(effective_count)]
                        + [p1, p2, curve.pointN(0)]
                    )
                else:
                    new_pts = (
                        [curve.pointN(k) for k in range(0, i + 1)]
                        + [p1, p2]
                        + [curve.pointN(k) for k in range(i + 1, num_pts)]
                    )

            res = QgsLineString()
            for pt in new_pts:
                res.addVertex(pt)
            return res

        # mode == "extend" (CAD Stretch / Extend & Trim adjacent edges)
        # 1. Compute new start vertex V'_i
        if i > 0:
            v_prev = curve.pointN(i - 1)
            v_prime_i = cls.compute_line_intersection(v_prev, v_i, p1, p2)
            if v_prime_i is None:
                v_prime_i = p1
        elif is_closed:
            v_prev = curve.pointN(effective_count - 1)
            v_prime_i = cls.compute_line_intersection(v_prev, v_i, p1, p2)
            if v_prime_i is None:
                v_prime_i = p1
        else:
            v_prime_i = p1

        # 2. Compute new end vertex V'_{i+1}
        if not is_closed:
            if i + 1 < num_pts - 1:
                v_after = curve.pointN(i + 2)
                v_prime_next = cls.compute_line_intersection(p1, p2, v_next, v_after)
                if v_prime_next is None:
                    v_prime_next = p2
            else:
                # Open polyline last segment (i == num_pts - 2):
                # Preserve segment length L starting from extended start joint v_prime_i
                v_prime_next = QgsPoint(v_prime_i.x() + length * ux, v_prime_i.y() + length * uy)
        else:
            next_next_idx = (i + 2) % effective_count
            v_after = curve.pointN(next_next_idx)
            v_prime_next = cls.compute_line_intersection(p1, p2, v_next, v_after)
            if v_prime_next is None:
                v_prime_next = p2

        # If i == 0 on open polyline: preserve segment length L ending at extended end joint v_prime_next
        if not is_closed and i == 0:
            if num_pts > 2:
                v_after = curve.pointN(i + 2)
                v_prime_next = cls.compute_line_intersection(p1, p2, v_next, v_after)
                if v_prime_next is None:
                    v_prime_next = p2
                v_prime_i = QgsPoint(v_prime_next.x() - length * ux, v_prime_next.y() - length * uy)
            else:
                v_prime_i = p1
                v_prime_next = p2

        # 3. Prevent bowtie self-intersection / collapse only for internal segments with constrained adjacent edges
        t1 = (v_prime_i.x() - p1.x()) * ux + (v_prime_i.y() - p1.y()) * uy
        t2 = (v_prime_next.x() - p1.x()) * ux + (v_prime_next.y() - p1.y()) * uy

        is_internal = is_closed or (i > 0 and i + 1 < num_pts - 1)

        if is_internal and t2 <= t1 + cls.EPSILON:
            # Find the apex intersection of the two adjacent edges
            v_prev_pt = curve.pointN(i - 1 if i > 0 else effective_count - 1)
            v_after_pt = curve.pointN((i + 2) % effective_count if is_closed else i + 2)
            v_apex = cls.compute_line_intersection(v_prev_pt, v_i, v_next, v_after_pt)
            if v_apex is None:
                v_apex = p1

            # Build new vertices list where segment [V_i, V_{i+1}] collapses to single vertex v_apex
            if not is_closed:
                if num_pts > 2:
                    new_pts = [curve.pointN(k) for k in range(0, i)] + [v_apex] + [curve.pointN(k) for k in range(i + 2, num_pts)]
                else:
                    new_pts = [v_apex, v_apex]
            else:
                # Minimum closed polygon must retain at least 3 unique vertices (4 total with closing)
                if effective_count > 3:
                    if i == 0:
                        new_pts = [v_apex] + [curve.pointN(k) for k in range(2, num_pts - 1)] + [v_apex]
                    elif i == effective_count - 1:
                        new_pts = [v_apex] + [curve.pointN(k) for k in range(1, effective_count - 1)] + [v_apex]
                    else:
                        new_pts = [curve.pointN(k) for k in range(0, i)] + [v_apex] + [curve.pointN(k) for k in range(i + 2, num_pts)]
                else:
                    new_pts = [v_apex if k in (i, (i + 1) % effective_count) else curve.pointN(k) for k in range(num_pts)]
                    if i == 0 or i == effective_count - 1:
                        new_pts[num_pts - 1] = new_pts[0]
        else:
            # 4. Normal extension: update the two vertices in the ring / polyline
            new_pts = [curve.pointN(k) for k in range(num_pts)]
            if not is_closed:
                new_pts[i] = v_prime_i
                new_pts[i + 1] = v_prime_next
            else:
                if i == 0:
                    new_pts[0] = v_prime_i
                    new_pts[1] = v_prime_next
                    new_pts[num_pts - 1] = v_prime_i
                elif i == effective_count - 1:
                    new_pts[i] = v_prime_i
                    new_pts[0] = v_prime_next
                    new_pts[num_pts - 1] = v_prime_next
                else:
                    new_pts[i] = v_prime_i
                    new_pts[i + 1] = v_prime_next

        res = QgsLineString()
        for pt in new_pts:
            res.addVertex(pt)
        return res

    @classmethod
    def offset_segment(
        cls,
        geom: QgsGeometry,
        part_idx: int,
        ring_idx: int,
        segment_idx: int,
        distance: float,
        mode: str = "extend",
    ) -> Optional[QgsGeometry]:
        """
        Offsets the specified segment in geom by distance.
        Works across Polygons, MultiPolygons, LineStrings, and MultiLineStrings.
        """
        if geom.isEmpty() or geom.isNull():
            return None

        if abs(distance) < cls.EPSILON:
            return QgsGeometry(geom)

        geom_type = geom.type()
        is_multi = geom.isMultipart()

        if geom_type == QgsWkbTypes.GeometryType.LineGeometry:
            if not is_multi:
                curve = geom.constGet()
                if not curve:
                    return None
                new_curve = cls.offset_segment_in_curve(curve, segment_idx, distance, mode)
                return QgsGeometry(new_curve) if new_curve else None
            else:
                multi = geom.constGet()
                if not multi or part_idx >= multi.numGeometries():
                    return None
                new_multi = QgsMultiLineString()
                for p in range(multi.numGeometries()):
                    line = multi.geometryN(p)
                    if p == part_idx:
                        new_line = cls.offset_segment_in_curve(line, segment_idx, distance, mode)
                        new_multi.addGeometry(new_line if new_line else line.clone())
                    else:
                        new_multi.addGeometry(line.clone())
                return QgsGeometry(new_multi)

        elif geom_type == QgsWkbTypes.GeometryType.PolygonGeometry:
            if not is_multi:
                poly = geom.constGet()
                if not poly:
                    return None
                new_poly = QgsPolygon()
                ext_ring = poly.exteriorRing()
                if ext_ring is None:
                    return None

                if ring_idx == 0:
                    new_ext = cls.offset_segment_in_curve(ext_ring, segment_idx, distance, mode)
                    new_poly.setExteriorRing(new_ext if new_ext else ext_ring.clone())
                else:
                    new_poly.setExteriorRing(ext_ring.clone())

                for r in range(poly.numInteriorRings()):
                    int_ring = poly.interiorRing(r)
                    if ring_idx == r + 1:
                        new_int = cls.offset_segment_in_curve(int_ring, segment_idx, distance, mode)
                        new_poly.addInteriorRing(new_int if new_int else int_ring.clone())
                    else:
                        new_poly.addInteriorRing(int_ring.clone())

                res_geom = QgsGeometry(new_poly)
                if mode == "extend" and not res_geom.isEmpty() and not res_geom.isGeosValid():
                    fallback_geom = cls.offset_segment(geom, part_idx, ring_idx, segment_idx, distance, mode="step")
                    if fallback_geom and fallback_geom.isGeosValid():
                        return fallback_geom
                return res_geom
            else:
                multi = geom.constGet()
                if not multi or part_idx >= multi.numGeometries():
                    return None
                new_multi = QgsMultiPolygon()
                for p in range(multi.numGeometries()):
                    poly = multi.geometryN(p)
                    if p == part_idx:
                        new_poly = QgsPolygon()
                        ext_ring = poly.exteriorRing()
                        if ext_ring is None:
                            new_multi.addGeometry(poly.clone())
                            continue
                        if ring_idx == 0:
                            new_ext = cls.offset_segment_in_curve(ext_ring, segment_idx, distance, mode)
                            new_poly.setExteriorRing(new_ext if new_ext else ext_ring.clone())
                        else:
                            new_poly.setExteriorRing(ext_ring.clone())

                        for r in range(poly.numInteriorRings()):
                            int_ring = poly.interiorRing(r)
                            if ring_idx == r + 1:
                                new_int = cls.offset_segment_in_curve(int_ring, segment_idx, distance, mode)
                                new_poly.addInteriorRing(new_int if new_int else int_ring.clone())
                            else:
                                new_poly.addInteriorRing(int_ring.clone())
                        new_multi.addGeometry(new_poly)
                    else:
                        new_multi.addGeometry(poly.clone())

                res_multi = QgsGeometry(new_multi)
                if mode == "extend" and not res_multi.isEmpty() and not res_multi.isGeosValid():
                    fallback_multi = cls.offset_segment(geom, part_idx, ring_idx, segment_idx, distance, mode="step")
                    if fallback_multi and fallback_multi.isGeosValid():
                        return fallback_multi
                return res_multi

        return None

    # Alias for backwards compatibility
    batch_process_geometry = batch_apply_geometry

