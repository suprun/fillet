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

        return None

    # Alias for backwards compatibility
    batch_process_geometry = batch_apply_geometry
