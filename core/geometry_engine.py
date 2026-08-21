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

        if geom_type == QgsWkbTypes.LineGeometry:
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

        elif geom_type == QgsWkbTypes.PolygonGeometry:
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

        if geom_type == QgsWkbTypes.LineGeometry:
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

        elif geom_type == QgsWkbTypes.PolygonGeometry:
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
        if geom_type == QgsWkbTypes.LineGeometry:
            if not is_multi:
                return geom.constGet()
            else:
                multi = geom.constGet()
                if multi and part_idx < multi.numGeometries():
                    return multi.geometryN(part_idx)
        elif geom_type == QgsWkbTypes.PolygonGeometry:
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
    def detect_fillet_chamfer_span(
        cls,
        curve: Union[QgsLineString, QgsAbstractGeometry],
        vertex_idx: int,
    ) -> Optional[Tuple[int, int, QgsPoint]]:
        """
        Detects the arc or chamfer span [start_idx, end_idx] around vertex_idx and calculates V_sharp.
        Returns: (start_idx, end_idx, V_sharp) or None
        """
        if not curve:
            return None
        num_pts = curve.numPoints()
        if num_pts < 3:
            return None

        is_closed = curve.isClosed()
        effective_count = (
            num_pts - 1
            if (is_closed and num_pts > 1 and curve.pointN(0) == curve.pointN(num_pts - 1))
            else num_pts
        )
        if effective_count < 3:
            return None

        def get_pt(idx):
            return curve.pointN(idx % effective_count if is_closed else idx)

        k = vertex_idx % effective_count

        # 1. Check for circular arc spans of length L in 3..65 (smallest to largest to find the tightest true arc)
        for length in range(3, min(65, effective_count)):
            for offset in range(length):
                start_cand = (k - offset) % effective_count if is_closed else (k - offset)
                end_cand = (start_cand + length - 1) % effective_count if is_closed else (start_cand + length - 1)
                if not is_closed and (start_cand < 1 or end_cand + 1 >= num_pts):
                    continue

                p_in_prev = get_pt(start_cand - 1)
                p_in = get_pt(start_cand)
                p_out_prev = get_pt(end_cand + 1)
                p_out = get_pt(end_cand)

                v_sharp = cls.compute_line_intersection(p_in_prev, p_in, p_out_prev, p_out)
                if not v_sharp:
                    continue

                vin_x, vin_y = p_in.x() - p_in_prev.x(), p_in.y() - p_in_prev.y()
                vout_x, vout_y = p_out.x() - p_out_prev.x(), p_out.y() - p_out_prev.y()
                dot_in = vin_x * (v_sharp.x() - p_in.x()) + vin_y * (v_sharp.y() - p_in.y())
                dot_out = vout_x * (v_sharp.x() - p_out.x()) + vout_y * (v_sharp.y() - p_out.y())
                if dot_in <= 1e-6 or dot_out <= 1e-6:
                    continue

                # Circumcircle through start, mid, end
                mid_idx = (start_cand + length // 2) % effective_count if is_closed else (start_cand + length // 2)
                p_mid = get_pt(mid_idx)

                ax, ay = p_in.x(), p_in.y()
                bx, by = p_mid.x(), p_mid.y()
                cx, cy = p_out.x(), p_out.y()
                d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
                if abs(d) < 1e-9:
                    continue
                ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d
                uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d
                radius = math.hypot(ax - ux, ay - uy)

                # Tangency check at entry and exit
                len_in = math.hypot(vin_x, vin_y)
                len_out = math.hypot(vout_x, vout_y)
                if len_in < 1e-9 or len_out < 1e-9 or radius < 1e-9:
                    continue

                tangent_dot_in = abs(vin_x * (ax - ux) + vin_y * (ay - uy)) / (len_in * radius)
                tangent_dot_out = abs(vout_x * (cx - ux) + vout_y * (cy - uy)) / (len_out * radius)
                if tangent_dot_in > 0.08 or tangent_dot_out > 0.08:
                    continue

                # Check circle tolerance for all intermediate points
                is_valid_circle = True
                for i in range(1, length - 1):
                    cur_idx = (start_cand + i) % effective_count if is_closed else (start_cand + i)
                    p_cur = get_pt(cur_idx)
                    cur_r = math.hypot(p_cur.x() - ux, p_cur.y() - uy)
                    if abs(cur_r - radius) > max(0.04 * radius, 0.005):
                        is_valid_circle = False
                        break

                if is_valid_circle:
                    return (start_cand, end_cand, v_sharp)

        # 2. Check for 2-point chamfer [k, k+1] or [k-1, k]
        for start_cand in [k, (k - 1) % effective_count if is_closed else k - 1]:
            if not is_closed and (start_cand < 1 or start_cand + 2 >= num_pts):
                continue
            end_cand = (start_cand + 1) % effective_count if is_closed else start_cand + 1
            p_in_prev = get_pt(start_cand - 1)
            p_in = get_pt(start_cand)
            p_out_prev = get_pt(end_cand + 1)
            p_out = get_pt(end_cand)

            # Chamfer touch points must NOT be sharp corners themselves
            def turn_angle(pa, pb, pc):
                v1x, v1y = pb.x() - pa.x(), pb.y() - pa.y()
                v2x, v2y = pc.x() - pb.x(), pc.y() - pb.y()
                c = v1x * v2y - v1y * v2x
                d = v1x * v2x + v1y * v2y
                return abs(math.atan2(c, d))

            turn_start = turn_angle(p_in_prev, p_in, p_out)
            turn_end = turn_angle(p_in, p_out, p_out_prev)
            if turn_start > math.radians(65) or turn_end > math.radians(65):
                continue
            if turn_start < math.radians(5) or turn_end < math.radians(5):
                continue

            v_sharp = cls.compute_line_intersection(p_in_prev, p_in, p_out_prev, p_out)
            if v_sharp:
                vin_x, vin_y = p_in.x() - p_in_prev.x(), p_in.y() - p_in_prev.y()
                vout_x, vout_y = p_out.x() - p_out_prev.x(), p_out.y() - p_out_prev.y()
                dot_in = vin_x * (v_sharp.x() - p_in.x()) + vin_y * (v_sharp.y() - p_in.y())
                dot_out = vout_x * (v_sharp.x() - p_out.x()) + vout_y * (v_sharp.y() - p_out.y())
                if dot_in > 1e-6 and dot_out > 1e-6:
                    d_to_sharp1 = math.hypot(v_sharp.x() - p_in.x(), v_sharp.y() - p_in.y())
                    d_to_sharp2 = math.hypot(v_sharp.x() - p_out.x(), v_sharp.y() - p_out.y())
                    if d_to_sharp1 > 1e-4 and d_to_sharp2 > 1e-4:
                        return (start_cand, end_cand, v_sharp)

        return None

    @classmethod
    def restore_sharp_corner_in_curve(
        cls,
        curve: QgsAbstractGeometry,
        vertex_idx: int,
    ) -> Optional[QgsAbstractGeometry]:
        """
        Restores the sharp corner in a curve at the given vertex by replacing the arc/chamfer span.
        """
        if not curve:
            return None

        ls = curve if isinstance(curve, QgsLineString) else QgsLineString(curve.points())
        match = cls.detect_fillet_chamfer_span(ls, vertex_idx)
        if not match:
            return None

        start_idx, end_idx, v_sharp = match
        num_pts = ls.numPoints()
        is_closed = ls.isClosed()
        effective_count = (
            num_pts - 1 if (is_closed and num_pts > 1 and ls.pointN(0) == ls.pointN(num_pts - 1)) else num_pts
        )

        if not is_closed:
            new_pts = (
                [ls.pointN(i) for i in range(start_idx)]
                + [v_sharp]
                + [ls.pointN(i) for i in range(end_idx + 1, num_pts)]
            )
        else:
            if start_idx <= end_idx:
                pts_before = [ls.pointN(i) for i in range(start_idx)]
                pts_after = [ls.pointN(i) for i in range(end_idx + 1, effective_count)]
                new_pts = pts_before + [v_sharp] + pts_after
            else:
                span_indices = set(list(range(start_idx, effective_count)) + list(range(0, end_idx + 1)))
                preserved = [ls.pointN(i) for i in range(effective_count) if i not in span_indices]
                new_pts = [v_sharp] + preserved

            if new_pts and (new_pts[0].x() != new_pts[-1].x() or new_pts[0].y() != new_pts[-1].y()):
                new_pts.append(QgsPoint(new_pts[0].x(), new_pts[0].y()))

        res = QgsLineString()
        for pt in new_pts:
            res.addVertex(pt)
        return res

    @classmethod
    def restore_sharp_corner_at_vertex(
        cls,
        geom: QgsGeometry,
        part_idx: int,
        ring_idx: int,
        vertex_idx: int,
    ) -> Optional[QgsGeometry]:
        """
        Removes a fillet or chamfer at the given vertex by restoring the sharp corner.
        """
        if geom.isEmpty() or geom.isNull():
            return None

        geom_type = geom.type()
        is_multi = geom.isMultipart()

        if geom_type == QgsWkbTypes.LineGeometry:
            if not is_multi:
                orig_curve = geom.constGet()
                if not orig_curve:
                    return None
                new_curve = cls.restore_sharp_corner_in_curve(orig_curve, vertex_idx)
                if not new_curve:
                    return None
                return QgsGeometry(new_curve)
            else:
                multi = geom.constGet()
                if not multi or part_idx >= multi.numGeometries():
                    return None
                new_multi = QgsMultiLineString()
                for p in range(multi.numGeometries()):
                    line = multi.geometryN(p)
                    if p == part_idx:
                        new_line = cls.restore_sharp_corner_in_curve(line, vertex_idx)
                        new_multi.addGeometry(new_line if new_line else line.clone())
                    else:
                        new_multi.addGeometry(line.clone())
                return QgsGeometry(new_multi)

        elif geom_type == QgsWkbTypes.PolygonGeometry:
            if not is_multi:
                poly = geom.constGet()
                if not poly:
                    return None
                new_poly = QgsPolygon()
                ext_ring = poly.exteriorRing()
                if ext_ring is None:
                    return None
                if ring_idx == 0:
                    new_ext = cls.restore_sharp_corner_in_curve(ext_ring, vertex_idx)
                    new_poly.setExteriorRing(new_ext if new_ext else ext_ring.clone())
                else:
                    new_poly.setExteriorRing(ext_ring.clone())

                for r in range(poly.numInteriorRings()):
                    int_ring = poly.interiorRing(r)
                    if ring_idx == r + 1:
                        new_int = cls.restore_sharp_corner_in_curve(int_ring, vertex_idx)
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
                            new_ext = cls.restore_sharp_corner_in_curve(ext_ring, vertex_idx)
                            new_poly.setExteriorRing(new_ext if new_ext else ext_ring.clone())
                        else:
                            new_poly.setExteriorRing(ext_ring.clone())

                        for r in range(poly.numInteriorRings()):
                            int_ring = poly.interiorRing(r)
                            if ring_idx == r + 1:
                                new_int = cls.restore_sharp_corner_in_curve(int_ring, vertex_idx)
                                new_poly.addInteriorRing(new_int if new_int else int_ring.clone())
                            else:
                                new_poly.addInteriorRing(int_ring.clone())
                        new_multi.addGeometry(new_poly)
                    else:
                        new_multi.addGeometry(poly.clone())
                return QgsGeometry(new_multi)

        return None

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
        Batch applies fillet, chamfer, or sharp corner restoration to all corners of all parts and rings in the geometry.
        """
        if geom.isEmpty() or geom.isNull():
            return None

        geom_type = geom.type()
        is_multi = geom.isMultipart()
        curr_geom = QgsGeometry(geom)

        if mode == "restore":
            # For restore mode, repeatedly find and restore detected spans until none remain
            if geom_type == QgsWkbTypes.LineGeometry:
                for part_idx in range(num_parts):
                    for _ in range(500):
                        curve = cls.get_vertex_curve(curr_geom, part_idx, 0)
                        if not curve or curve.numPoints() < 3:
                            break
                        found = False
                        for v_idx in range(curve.numPoints()):
                            m = cls.detect_fillet_chamfer_span(curve, v_idx)
                            if m:
                                res = cls.restore_sharp_corner_at_vertex(curr_geom, part_idx, 0, v_idx)
                                if res and not res.isEmpty():
                                    curr_geom = res
                                    found = True
                                    break
                        if not found:
                            break
            elif geom_type == QgsWkbTypes.PolygonGeometry:
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
                        for _ in range(500):
                            curve = cls.get_vertex_curve(curr_geom, part_idx, ring_idx)
                            if not curve:
                                break
                            n_pts = curve.numPoints()
                            eff = (
                                n_pts - 1
                                if (n_pts > 1 and curve.pointN(0) == curve.pointN(n_pts - 1))
                                else n_pts
                            )
                            if eff < 3:
                                break
                            found = False
                            for v_idx in range(eff):
                                m = cls.detect_fillet_chamfer_span(curve, v_idx)
                                if m:
                                    res = cls.restore_sharp_corner_at_vertex(curr_geom, part_idx, ring_idx, v_idx)
                                    if res and not res.isEmpty():
                                        curr_geom = res
                                        found = True
                                        break
                            if not found:
                                break
            return curr_geom

        if geom_type == QgsWkbTypes.LineGeometry:
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

        elif geom_type == QgsWkbTypes.PolygonGeometry:
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

    # Alias for backwards compatibility
    batch_process_geometry = batch_apply_geometry
