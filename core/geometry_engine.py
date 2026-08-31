# -*- coding: utf-8 -*-
"""
Fillet & Chamfer Geometry Engine for QGIS 3.x and 4.x
Provides core mathematical algorithms for vertex and segment filleting/chamfering.
"""

import math
from enum import Enum
from typing import Dict, List, Optional, Tuple, Union

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
    QgsVectorLayer,
    QgsVertexId,
    QgsWkbTypes,
)


class BooleanOperation(str, Enum):
    """Supported polygon boolean operations for the shared CAD tool."""

    Subtract = "subtract"
    Clip = "clip"


class GeometryEngine:
    """Core mathematical engine for Fillet and Chamfer operations."""

    EPSILON = 1e-8

    @staticmethod
    def has_curved_segments(geom: Optional[QgsGeometry]) -> bool:
        """Return whether a geometry contains native curved segments."""
        if not geom or geom.isNull() or geom.isEmpty():
            return False

        abstract_geom = geom.constGet()
        if abstract_geom is None:
            return False

        has_curves = getattr(abstract_geom, "hasCurvedSegments", None)
        if callable(has_curves):
            return bool(has_curves())

        return bool(QgsWkbTypes.isCurvedType(geom.wkbType()))

    @staticmethod
    def _point_with_dimensions(
        x: float,
        y: float,
        has_z: bool = False,
        z_value: float = 0.0,
        has_m: bool = False,
        m_value: float = 0.0,
    ) -> QgsPoint:
        """Create a point without dropping its requested Z/M dimensions."""
        if has_z and has_m:
            return QgsPoint(x, y, z_value, m_value)
        if has_z:
            return QgsPoint(x, y, z_value)
        if has_m:
            return QgsPoint(x, y, m=m_value)
        return QgsPoint(x, y)

    @classmethod
    def _copy_point(cls, point: Union[QgsPoint, QgsPointXY]) -> QgsPoint:
        """Copy a point while preserving all available dimensions."""
        has_z = bool(getattr(point, "is3D", lambda: False)())
        has_m = bool(getattr(point, "isMeasure", lambda: False)())
        return cls._point_with_dimensions(
            point.x(),
            point.y(),
            has_z=has_z,
            z_value=point.z() if has_z else 0.0,
            has_m=has_m,
            m_value=point.m() if has_m else 0.0,
        )

    @classmethod
    def _interpolate_point_dimensions(
        cls,
        p1: Union[QgsPoint, QgsPointXY],
        p2: Union[QgsPoint, QgsPointXY],
        x: float,
        y: float,
        fraction: Optional[float] = None,
    ) -> QgsPoint:
        """Create an XY point with Z/M interpolated along the source segment."""
        if fraction is None:
            dx = p2.x() - p1.x()
            dy = p2.y() - p1.y()
            length_sq = dx * dx + dy * dy
            if length_sq < cls.EPSILON * cls.EPSILON:
                fraction = 0.0
            else:
                fraction = ((x - p1.x()) * dx + (y - p1.y()) * dy) / length_sq

        has_z = bool(getattr(p1, "is3D", lambda: False)()) and bool(
            getattr(p2, "is3D", lambda: False)()
        )
        has_m = bool(getattr(p1, "isMeasure", lambda: False)()) and bool(
            getattr(p2, "isMeasure", lambda: False)()
        )
        z_value = p1.z() + fraction * (p2.z() - p1.z()) if has_z else 0.0
        m_value = p1.m() + fraction * (p2.m() - p1.m()) if has_m else 0.0
        return cls._point_with_dimensions(
            x,
            y,
            has_z=has_z,
            z_value=z_value,
            has_m=has_m,
            m_value=m_value,
        )

    @classmethod
    def _average_dimension_points(
        cls,
        point1: QgsPoint,
        point2: QgsPoint,
        x: float,
        y: float,
    ) -> QgsPoint:
        """Combine dimensions from two coincident line-intersection results."""
        has_z = point1.is3D() and point2.is3D()
        has_m = point1.isMeasure() and point2.isMeasure()
        z_value = (point1.z() + point2.z()) * 0.5 if has_z else 0.0
        m_value = (point1.m() + point2.m()) * 0.5 if has_m else 0.0
        return cls._point_with_dimensions(
            x,
            y,
            has_z=has_z,
            z_value=z_value,
            has_m=has_m,
            m_value=m_value,
        )

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
        if radius < 0:
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

        if radius == 0:
            return (
                True,
                GeometryEngine._copy_point(v),
                GeometryEngine._copy_point(v),
                GeometryEngine._copy_point(v),
                0.0,
            )

        tangent_dist = radius / tan_half

        # Max allowed tangent distance - clamp to maximum possible if requested radius is too large
        max_dist = min(len1, len2)
        if tangent_dist > max_dist:
            tangent_dist = max_dist * 0.9999
            radius = tangent_dist * tan_half

        # Tangent points
        t1_x = v.x() + tangent_dist * u1x
        t1_y = v.y() + tangent_dist * u1y
        t2_x = v.x() + tangent_dist * u2x
        t2_y = v.y() + tangent_dist * u2y
        t1 = GeometryEngine._interpolate_point_dimensions(v, p_prev, t1_x, t1_y)
        t2 = GeometryEngine._interpolate_point_dimensions(v, p_next, t2_x, t2_y)

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
        arc_mid = GeometryEngine._interpolate_point_dimensions(t1, t2, mid_x, mid_y, 0.5)

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
        if dist1 < 0 or dist2 < 0:
            return False, None, None

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

        c1_x = v.x() + dist1 * u1x
        c1_y = v.y() + dist1 * u1y
        c2_x = v.x() + dist2 * u2x
        c2_y = v.y() + dist2 * u2y
        c1 = GeometryEngine._interpolate_point_dimensions(v, p_prev, c1_x, c1_y)
        c2 = GeometryEngine._interpolate_point_dimensions(v, p_next, c2_x, c2_y)

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
            return [
                GeometryEngine._copy_point(p1),
                GeometryEngine._copy_point(pm),
                GeometryEngine._copy_point(p2),
            ]

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

        points = [GeometryEngine._copy_point(p1)]
        for i in range(1, segments_count):
            t = i / float(segments_count)
            ang = start_ang + t * (end_ang - start_ang)
            x = ux + r * math.cos(ang)
            y = uy + r * math.sin(ang)
            points.append(GeometryEngine._interpolate_point_dimensions(p1, p2, x, y, t))
        points.append(GeometryEngine._copy_point(p2))

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
        if not isinstance(curve, QgsLineString):
            return None

        curve_wkb = curve.wkbType()
        has_dimensions = QgsWkbTypes.hasZ(curve_wkb) or QgsWkbTypes.hasM(curve_wkb)
        if (
            radius > 0
            and hasattr(QgsGeometryUtils, "filletVertex")
            and use_true_curve
            and not has_dimensions
        ):
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
        if radius == 0:
            return curve.clone()

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
        if not isinstance(curve, QgsLineString):
            return None

        curve_wkb = curve.wkbType()
        has_dimensions = QgsWkbTypes.hasZ(curve_wkb) or QgsWkbTypes.hasM(curve_wkb)
        if (
            dist1 > 0
            and dist2 > 0
            and hasattr(QgsGeometryUtils, "chamferVertex")
            and not has_dimensions
        ):
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
        if dist1 == 0 and dist2 == 0:
            return curve.clone()

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
        if cls.has_curved_segments(geom):
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
        if cls.has_curved_segments(geom):
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
            success, c1, c2 = cls.compute_chamfer_points(p_prev, v, p_next, val1, val2)
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

    @classmethod
    def compute_line_intersection(
        cls,
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
        u = (dx * dy1 - dy * dx1) / det
        x = p1.x() + t * dx1
        y = p1.y() + t * dy1
        point_on_first = cls._interpolate_point_dimensions(p1, p2, x, y, t)
        point_on_second = cls._interpolate_point_dimensions(p3, p4, x, y, u)

        if point_on_first.is3D() and point_on_second.is3D():
            return cls._average_dimension_points(point_on_first, point_on_second, x, y)
        if point_on_first.isMeasure() and point_on_second.isMeasure():
            return cls._average_dimension_points(point_on_first, point_on_second, x, y)
        if point_on_first.is3D() or point_on_first.isMeasure():
            return point_on_first
        if point_on_second.is3D() or point_on_second.isMeasure():
            return point_on_second
        return QgsPoint(x, y)

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
        if cls.has_curved_segments(geom):
            return None

        if mode == "fillet":
            if radius < 0:
                return None
            if radius == 0:
                return QgsGeometry(geom)
        elif mode == "chamfer":
            if dist1 < 0 or dist2 < 0:
                return None
            if dist1 == 0 and dist2 == 0:
                return QgsGeometry(geom)
        else:
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
            new_pts.append(cls._copy_point(new_pts[0]))

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
        if cls.has_curved_segments(geom):
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
        part1_idx: int = 0,
        part2_idx: int = 0,
    ) -> Optional[Tuple[QgsGeometry, QgsPoint, QgsPoint, QgsPoint]]:
        """
        Performs CAD Fillet or Chamfer between two line geometries, trimming/extending them
        and stitching them into a single continuous QgsLineString geometry.

        Returns: (new_geometry, v_intersection, t1, t2) or None
        """
        if not geom1 or geom1.isEmpty() or not geom2 or geom2.isEmpty():
            return None
        if cls.has_curved_segments(geom1) or cls.has_curved_segments(geom2):
            return None

        curve1 = geom1.constGet()
        curve2 = geom2.constGet()
        if not curve1 or not curve2:
            return None

        if isinstance(curve1, QgsMultiLineString):
            if part1_idx < 0 or part1_idx >= curve1.numGeometries():
                return None
            curve1 = curve1.geometryN(part1_idx)
        if isinstance(curve2, QgsMultiLineString):
            if part2_idx < 0 or part2_idx >= curve2.numGeometries():
                return None
            curve2 = curve2.geometryN(part2_idx)

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
            if radius < 0:
                return None
            if radius == 0:
                t1 = v
                t2 = v
                arc_pts = [v]
            else:
                max_tangent = min(max_len1, max_len2) * 0.9999
                tangent_dist = min(radius / tan_half, max_tangent)
                eff_radius = tangent_dist * tan_half

                t1_x = v.x() + tangent_dist * u1x
                t1_y = v.y() + tangent_dist * u1y
                t2_x = v.x() + tangent_dist * u2x
                t2_y = v.y() + tangent_dist * u2y
                t1 = cls._interpolate_point_dimensions(a1, b1, t1_x, t1_y)
                t2 = cls._interpolate_point_dimensions(a2, b2, t2_x, t2_y)

                bx, by, blen = cls.normalize_vector(u1x + u2x, u1y + u2y)
                center_dist = eff_radius / sin_half
                cx = v.x() + center_dist * bx
                cy = v.y() + center_dist * by

                arc_mid_x = cx - eff_radius * bx
                arc_mid_y = cy - eff_radius * by
                arc_mid = cls._interpolate_point_dimensions(t1, t2, arc_mid_x, arc_mid_y, 0.5)
                arc_pts = cls.segmentize_arc_3p(t1, arc_mid, t2, segments_count)
        elif mode == "chamfer":
            if dist1 < 0 or dist2 < 0:
                return None
            d1_in = dist1
            d2_in = dist2
            if d1_in == 0 and d2_in == 0:
                t1 = v
                t2 = v
                arc_pts = [v]
            else:
                d1 = min(d1_in, max_len1 * 0.9999)
                d2 = min(d2_in, max_len2 * 0.9999)
                t1_x = v.x() + d1 * u1x
                t1_y = v.y() + d1 * u1y
                t2_x = v.x() + d2 * u2x
                t2_y = v.y() + d2 * u2y
                t1 = cls._interpolate_point_dimensions(a1, b1, t1_x, t1_y)
                t2 = cls._interpolate_point_dimensions(a2, b2, t2_x, t2_y)
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
    def rebuild_two_line_geometry(
        cls,
        geom1: QgsGeometry,
        part1_idx: int,
        geom2: QgsGeometry,
        part2_idx: int,
        joined_geom: QgsGeometry,
        same_feature: bool,
    ) -> Optional[QgsGeometry]:
        """Rebuild source line geometry around a joined pair of selected parts."""
        if (
            not geom1
            or geom1.isEmpty()
            or not geom2
            or geom2.isEmpty()
            or not joined_geom
            or joined_geom.isEmpty()
        ):
            return None
        if cls.has_curved_segments(geom1) or cls.has_curved_segments(geom2):
            return None

        def line_parts(geom: QgsGeometry) -> Optional[List[QgsLineString]]:
            abstract_geom = geom.constGet()
            if isinstance(abstract_geom, QgsLineString):
                return [abstract_geom]
            if isinstance(abstract_geom, QgsMultiLineString):
                return [abstract_geom.geometryN(i) for i in range(abstract_geom.numGeometries())]
            return None

        parts1 = line_parts(geom1)
        parts2 = parts1 if same_feature else line_parts(geom2)
        joined_curve = joined_geom.constGet()
        if (
            parts1 is None
            or parts2 is None
            or not isinstance(joined_curve, QgsLineString)
            or part1_idx < 0
            or part1_idx >= len(parts1)
            or part2_idx < 0
            or part2_idx >= len(parts2)
        ):
            return None

        output_parts: List[QgsLineString] = []
        if same_feature:
            selected_parts = {part1_idx, part2_idx}
            insert_at = min(selected_parts)
            for index, part in enumerate(parts1):
                if index == insert_at:
                    output_parts.append(joined_curve.clone())
                if index not in selected_parts:
                    output_parts.append(part.clone())
        else:
            for index, part in enumerate(parts1):
                if index == part1_idx:
                    output_parts.append(joined_curve.clone())
                else:
                    output_parts.append(part.clone())
            for index, part in enumerate(parts2):
                if index != part2_idx:
                    output_parts.append(part.clone())

        if not output_parts:
            return None

        needs_multi = geom1.isMultipart() or geom2.isMultipart() or len(output_parts) > 1
        if not needs_multi:
            return QgsGeometry(output_parts[0])

        multi = QgsMultiLineString()
        for part in output_parts:
            multi.addGeometry(part)
        return QgsGeometry(multi)

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
    def create_polar_array_geometries(
        cls,
        geom: QgsGeometry,
        center: Union[QgsPoint, QgsPointXY],
        count: int,
        fill_angle_deg: float,
        rotate_features: bool = True,
        include_original: bool = False,
        step_angle_deg: Optional[float] = None,
    ) -> List[QgsGeometry]:
        """
        Generates a polar (circular) array of geometries around center point.
        :param geom: Source QgsGeometry to replicate.
        :param center: Center point of the circular/polar array.
        :param count: Total number of items in the array (>= 1).
        :param fill_angle_deg: Total fill angle in degrees (e.g. 360.0, 180.0, -90.0). CCW is positive.
        :param rotate_features: If True, each copy rotates around center.
                                If False, copies translate along the circle preserving original azimuth.
        :param include_original: If True, includes the i=0 element (original geometry).
        :param step_angle_deg: Optional explicit step angle. If None, computed from fill_angle_deg.
        :return: List of transformed QgsGeometry objects.
        """
        if geom.isEmpty() or geom.isNull() or count < 1:
            return []

        if count == 1:
            return [QgsGeometry(geom)] if include_original else []

        if step_angle_deg is not None:
            step_deg = step_angle_deg
        else:
            if abs(abs(fill_angle_deg) - 360.0) < 1e-4:
                step_deg = fill_angle_deg / float(count)
            else:
                step_deg = fill_angle_deg / float(count - 1) if count > 1 else 0.0

        results: List[QgsGeometry] = []
        start_idx = 0 if include_original else 1

        # Centroid for non-rotating translation
        ref_pt: Optional[QgsPointXY] = None
        if not rotate_features:
            centroid = geom.centroid()
            if not centroid.isEmpty():
                ref_pt = centroid.asPoint()
            else:
                box = geom.boundingBox()
                ref_pt = box.center()

        for i in range(start_idx, count):
            cur_angle_deg = i * step_deg
            if abs(cur_angle_deg) < cls.EPSILON:
                results.append(QgsGeometry(geom))
                continue

            if rotate_features or ref_pt is None:
                rotated_geom = cls.rotate_geometry(geom, center, cur_angle_deg)
                results.append(rotated_geom)
            else:
                # Rotate the reference point around center to find target translation vector
                cur_rad = math.radians(cur_angle_deg)
                cos_a = math.cos(cur_rad)
                sin_a = math.sin(cur_rad)
                dx0 = ref_pt.x() - center.x()
                dy0 = ref_pt.y() - center.y()
                # CCW rotation
                rx = center.x() + (dx0 * cos_a - dy0 * sin_a)
                ry = center.y() + (dx0 * sin_a + dy0 * cos_a)
                shift_x = rx - ref_pt.x()
                shift_y = ry - ref_pt.y()

                trans_geom = QgsGeometry(geom)
                trans_geom.translate(shift_x, shift_y)
                results.append(trans_geom)

        return results

    @classmethod
    def divide_line_geometries(
        cls,
        geom: QgsGeometry,
        count: Optional[int] = None,
        step_length: Optional[float] = None,
        reverse_direction: bool = False,
    ) -> List[QgsGeometry]:
        """
        Divides a line (or each part of a multi-line) into sub-geometries.
        Can divide by equal parts (count) or by fixed segment length (step_length).
        If reverse_direction is True, measurement starts from the opposite endpoint.
        """
        if geom.isNull() or geom.isEmpty():
            return []

        if geom.isMultipart():
            results = []
            for part in geom.asGeometryCollection():
                sub_parts = cls.divide_line_geometries(
                    part,
                    count=count,
                    step_length=step_length,
                    reverse_direction=reverse_direction,
                )
                results.extend(sub_parts)
            return results

        abstract_geom = geom.constGet()
        if abstract_geom is None:
            return [QgsGeometry(geom)]

        total_length = abstract_geom.length()
        if total_length <= cls.EPSILON:
            return [QgsGeometry(geom)]

        curve = abstract_geom.reversed() if reverse_direction else abstract_geom

        distances = [0.0]
        if count is not None and count >= 2:
            seg_len = total_length / count
            for i in range(1, count):
                distances.append(i * seg_len)
            distances.append(total_length)
        elif step_length is not None and step_length > cls.EPSILON:
            cur_d = step_length
            while cur_d < total_length - cls.EPSILON:
                distances.append(cur_d)
                cur_d += step_length
            distances.append(total_length)
        else:
            return [QgsGeometry(geom)]

        results = []
        for i in range(len(distances) - 1):
            d_start = distances[i]
            d_end = distances[i + 1]
            if d_end - d_start < cls.EPSILON:
                continue
            sub_curve = curve.curveSubstring(d_start, d_end)
            if sub_curve is not None:
                sub_geom = QgsGeometry(sub_curve)
                if not sub_geom.isEmpty():
                    results.append(sub_geom)

        return results if results else [QgsGeometry(geom)]

    @classmethod
    def get_division_points(
        cls,
        geom: QgsGeometry,
        count: Optional[int] = None,
        step_length: Optional[float] = None,
        reverse_direction: bool = False,
    ) -> List[QgsPointXY]:
        """Returns the intermediate division cut points along the line."""
        if geom.isNull() or geom.isEmpty():
            return []

        if geom.isMultipart():
            pts = []
            for part in geom.asGeometryCollection():
                pts.extend(cls.get_division_points(
                    part,
                    count=count,
                    step_length=step_length,
                    reverse_direction=reverse_direction,
                ))
            return pts

        abstract_geom = geom.constGet()
        if abstract_geom is None:
            return []

        total_length = abstract_geom.length()
        if total_length <= cls.EPSILON:
            return []

        split_dists = []
        if count is not None and count >= 2:
            seg_len = total_length / count
            for i in range(1, count):
                split_dists.append(i * seg_len)
        elif step_length is not None and step_length > cls.EPSILON:
            curr_dist = step_length
            while curr_dist < total_length - cls.EPSILON:
                split_dists.append(curr_dist)
                curr_dist += step_length

        if reverse_direction:
            split_dists = [total_length - d for d in reversed(split_dists)]

        cut_pts: List[QgsPointXY] = []
        for dist in split_dists:
            curve_pt = abstract_geom.interpolatePoint(dist)
            if curve_pt is not None and not curve_pt.isEmpty():
                cut_pts.append(QgsPointXY(curve_pt.x(), curve_pt.y()))

        return cut_pts

    @classmethod
    def orthogonalize_geometry(
        cls,
        geom: QgsGeometry,
        base_angle_rad: float,
        tolerance_deg: float = 15.0,
        preserve_area: bool = False,
    ) -> QgsGeometry:
        """
        Orthogonalizes the vertices of a polygon or linestring so that segments whose angles
        are within tolerance_deg of (base_angle_rad + k * 90°) become strictly parallel or
        perpendicular to base_angle_rad.

        :param geom: Source QgsGeometry (Polygon, MultiPolygon, LineString, MultiLineString).
        :param base_angle_rad: Base reference azimuth in radians.
        :param tolerance_deg: Angular tolerance in degrees (default 15.0°).
        :param preserve_area: If True for polygons, scales the result around its centroid
                              to match the original area exactly.
        :return: A new orthogonalized QgsGeometry.
        """
        if geom.isNull() or geom.isEmpty():
            return QgsGeometry(geom)
        if cls.has_curved_segments(geom):
            return QgsGeometry(geom)

        tol_rad = math.radians(max(0.1, min(45.0, tolerance_deg)))
        orig_area = geom.area() if geom.type() == QgsWkbTypes.GeometryType.PolygonGeometry else 0.0

        if geom.isMultipart():
            sub_geoms = []
            for part in geom.asGeometryCollection():
                sub_ortho = cls.orthogonalize_geometry(
                    part,
                    base_angle_rad=base_angle_rad,
                    tolerance_deg=tolerance_deg,
                    preserve_area=False,
                )
                sub_geoms.append(sub_ortho)
            if not sub_geoms:
                return QgsGeometry(geom)

            geom_type = geom.type()
            if geom_type == QgsWkbTypes.GeometryType.PolygonGeometry:
                multi_polygon = QgsMultiPolygon()
                for sub_geom in sub_geoms:
                    polygon = sub_geom.constGet()
                    if isinstance(polygon, QgsPolygon):
                        multi_polygon.addGeometry(polygon.clone())
                res = QgsGeometry(multi_polygon)
            elif geom_type == QgsWkbTypes.GeometryType.LineGeometry:
                multi_line = QgsMultiLineString()
                for sub_geom in sub_geoms:
                    line = sub_geom.constGet()
                    if isinstance(line, QgsLineString):
                        multi_line.addGeometry(line.clone())
                res = QgsGeometry(multi_line)
            else:
                return QgsGeometry(geom)

            if preserve_area and orig_area > cls.EPSILON and res.area() > cls.EPSILON:
                scale_factor = math.sqrt(orig_area / res.area())
                centroid = res.centroid().asPoint() if not res.centroid().isEmpty() else None
                if centroid:
                    res = cls.scale_and_rotate_geometry(res, centroid, scale_factor, 0.0)
            return res

        # Single part polygon or linestring
        geom_type = geom.type()
        if geom_type == QgsWkbTypes.GeometryType.PolygonGeometry:
            polygon = geom.constGet()
            if not isinstance(polygon, QgsPolygon) or polygon.exteriorRing() is None:
                return QgsGeometry(geom)
            new_polygon = QgsPolygon()
            exterior = polygon.exteriorRing()
            exterior_points = [exterior.pointN(i) for i in range(exterior.numPoints())]
            new_polygon.setExteriorRing(
                QgsLineString(cls._orthogonalize_ring(exterior_points, base_angle_rad, tol_rad, is_closed=True))
            )
            for ring_index in range(polygon.numInteriorRings()):
                interior = polygon.interiorRing(ring_index)
                interior_points = [interior.pointN(i) for i in range(interior.numPoints())]
                new_polygon.addInteriorRing(
                    QgsLineString(cls._orthogonalize_ring(interior_points, base_angle_rad, tol_rad, is_closed=True))
                )

            res = QgsGeometry(new_polygon)
            if preserve_area and orig_area > cls.EPSILON and res.area() > cls.EPSILON:
                scale_factor = math.sqrt(orig_area / res.area())
                centroid = res.centroid().asPoint() if not res.centroid().isEmpty() else None
                if centroid:
                    res = cls.scale_and_rotate_geometry(res, centroid, scale_factor, 0.0)
            return res

        elif geom_type == QgsWkbTypes.GeometryType.LineGeometry:
            line = geom.constGet()
            if not isinstance(line, QgsLineString) or line.numPoints() < 2:
                return QgsGeometry(geom)
            polyline = [line.pointN(i) for i in range(line.numPoints())]
            is_closed = line.isClosed() or (
                len(polyline) >= 4
                and cls.distance(polyline[0], polyline[-1]) < cls.EPSILON
            )
            ortho_pts = cls._orthogonalize_ring(polyline, base_angle_rad, tol_rad, is_closed=is_closed)
            return QgsGeometry(QgsLineString(ortho_pts))

        return QgsGeometry(geom)

    @classmethod
    def _orthogonalize_ring(
        cls,
        pts: List[QgsPoint],
        base_angle_rad: float,
        tol_rad: float,
        is_closed: bool,
    ) -> List[QgsPoint]:
        """Orthogonalize XY coordinates while retaining each vertex's Z/M values."""
        if len(pts) < 3:
            return list(pts)

        if is_closed and cls.distance(pts[0], pts[-1]) < cls.EPSILON:
            pts_work = pts[:-1]
        else:
            pts_work = list(pts)

        n = len(pts_work)
        if n < 3:
            return list(pts)

        # 1. Compute midpoints, original lengths, and adjusted directions for all edges
        lines = []
        half_pi = math.pi / 2.0
        quarter_pi = math.pi / 4.0

        num_edges = n if is_closed else n - 1
        for i in range(num_edges):
            p1 = pts_work[i]
            p2 = pts_work[(i + 1) % n]
            dx = p2.x() - p1.x()
            dy = p2.y() - p1.y()
            seg_len = math.hypot(dx, dy)
            if seg_len < cls.EPSILON:
                alpha = base_angle_rad
            else:
                alpha = math.atan2(dy, dx)

            # Measure difference relative to nearest orthogonal angle (base_angle_rad + k * 90°)
            delta = (alpha - base_angle_rad + quarter_pi) % half_pi - quarter_pi
            if abs(delta) <= tol_rad:
                alpha_adj = alpha - delta
            else:
                alpha_adj = alpha

            mx = (p1.x() + p2.x()) * 0.5
            my = (p1.y() + p2.y()) * 0.5

            # Line equation in form a*x + b*y = c
            # Direction vector (cos a, sin a) -> Normal vector (-sin a, cos a)
            a = -math.sin(alpha_adj)
            b = math.cos(alpha_adj)
            c = a * mx + b * my
            lines.append((a, b, c, mx, my, alpha_adj))

        # 2. Reconstruct vertices from adjacent line intersections
        new_pts: List[QgsPoint] = []
        for i in range(n):
            if is_closed:
                line_prev = lines[(i - 1) % n]
                line_next = lines[i]
                pt = cls._intersect_2d_lines(line_prev, line_next, pts_work[i])
                new_pts.append(cls._point_at_xy_with_source_dimensions(pt, pts_work[i]))
            else:
                if i == 0:
                    # Project first vertex onto first line
                    a, b, c, mx, my, _ = lines[0]
                    v = pts_work[0]
                    pt = cls._project_point_to_line(v, a, b, c)
                    new_pts.append(cls._point_at_xy_with_source_dimensions(pt, pts_work[i]))
                elif i == n - 1:
                    # Project last vertex onto last line
                    a, b, c, mx, my, _ = lines[-1]
                    v = pts_work[-1]
                    pt = cls._project_point_to_line(v, a, b, c)
                    new_pts.append(cls._point_at_xy_with_source_dimensions(pt, pts_work[i]))
                else:
                    line_prev = lines[i - 1]
                    line_next = lines[i]
                    pt = cls._intersect_2d_lines(line_prev, line_next, pts_work[i])
                    new_pts.append(cls._point_at_xy_with_source_dimensions(pt, pts_work[i]))

        if is_closed:
            new_pts.append(cls._copy_point(new_pts[0]))

        return new_pts

    @classmethod
    def _point_at_xy_with_source_dimensions(
        cls,
        point_xy: Union[QgsPoint, QgsPointXY],
        source_point: Union[QgsPoint, QgsPointXY],
    ) -> QgsPoint:
        """Move a point in XY while retaining dimensions from its source vertex."""
        has_z = bool(getattr(source_point, "is3D", lambda: False)())
        has_m = bool(getattr(source_point, "isMeasure", lambda: False)())
        return cls._point_with_dimensions(
            point_xy.x(),
            point_xy.y(),
            has_z=has_z,
            z_value=source_point.z() if has_z else 0.0,
            has_m=has_m,
            m_value=source_point.m() if has_m else 0.0,
        )

    @staticmethod
    def _intersect_2d_lines(
        line1: Tuple[float, float, float, float, float, float],
        line2: Tuple[float, float, float, float, float, float],
        fallback_pt: QgsPointXY,
    ) -> QgsPointXY:
        """Intersects two 2D lines (a1*x + b1*y = c1) and (a2*x + b2*y = c2)."""
        a1, b1, c1, _, _, _ = line1
        a2, b2, c2, _, _, _ = line2
        det = a1 * b2 - a2 * b1
        if abs(det) < 1e-7:
            return fallback_pt
        x = (c1 * b2 - c2 * b1) / det
        y = (a1 * c2 - a2 * c1) / det
        return QgsPointXY(x, y)

    @staticmethod
    def _project_point_to_line(pt: QgsPointXY, a: float, b: float, c: float) -> QgsPointXY:
        """Projects point (x0, y0) onto line a*x + b*y = c."""
        denom = a * a + b * b
        if denom < 1e-12:
            return pt
        x0, y0 = pt.x(), pt.y()
        d = (a * x0 + b * y0 - c) / denom
        return QgsPointXY(x0 - a * d, y0 - b * d)

    @classmethod
    def _scale_geometry_xy(cls, geom: QgsGeometry, center: QgsPointXY, factor: float) -> QgsGeometry:
        """Uniformly scales a geometry around center point by factor."""
        if abs(factor - 1.0) < cls.EPSILON:
            return QgsGeometry(geom)

        cx, cy = center.x(), center.y()
        if geom.type() == QgsWkbTypes.GeometryType.PolygonGeometry:
            if geom.isMultipart():
                multi_poly = []
                for poly in geom.asMultiPolygon():
                    poly_scaled = []
                    for ring in poly:
                        poly_scaled.append([QgsPointXY(cx + (p.x() - cx) * factor, cy + (p.y() - cy) * factor) for p in ring])
                    multi_poly.append(poly_scaled)
                return QgsGeometry.fromMultiPolygonXY(multi_poly)
            else:
                poly_scaled = []
                for ring in geom.asPolygon():
                    poly_scaled.append([QgsPointXY(cx + (p.x() - cx) * factor, cy + (p.y() - cy) * factor) for p in ring])
                return QgsGeometry.fromPolygonXY(poly_scaled)
        elif geom.type() == QgsWkbTypes.GeometryType.LineGeometry:
            if geom.isMultipart():
                multi_line = []
                for line in geom.asMultiPolyline():
                    multi_line.append([QgsPointXY(cx + (p.x() - cx) * factor, cy + (p.y() - cy) * factor) for p in line])
                return QgsGeometry.fromMultiPolylineXY(multi_line)
            else:
                line_scaled = [QgsPointXY(cx + (p.x() - cx) * factor, cy + (p.y() - cy) * factor) for p in geom.asPolyline()]
                return QgsGeometry.fromPolylineXY(line_scaled)

        return QgsGeometry(geom)

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
                return QgsPoint(p.x(), p.y(), m=m_val)
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
            return QgsPoint(mx, my, m=m_val)
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

        elif QgsWkbTypes.isMultiType(wkb_type) or bool(
            getattr(abstract_geom, "isMultipart", lambda: False)()
        ):
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
            return QgsPoint(nx, ny, m=m_val)
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

        elif QgsWkbTypes.isMultiType(wkb_type) or bool(
            getattr(abstract_geom, "isMultipart", lambda: False)()
        ):
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
    def compute_alignment_transform(
        cls,
        source_start: Union[QgsPoint, QgsPointXY],
        source_end: Union[QgsPoint, QgsPointXY],
        target_start: Union[QgsPoint, QgsPointXY],
        target_end: Union[QgsPoint, QgsPointXY],
        fit: bool = False,
        flip: bool = False,
    ) -> Tuple[float, float, float, float]:
        """Return angle, scale, and translation for two-reference alignment."""
        source_dx = source_end.x() - source_start.x()
        source_dy = source_end.y() - source_start.y()
        target_dx = target_end.x() - target_start.x()
        target_dy = target_end.y() - target_start.y()
        source_length = math.hypot(source_dx, source_dy)
        target_length = math.hypot(target_dx, target_dy)
        if source_length < cls.EPSILON:
            raise ValueError("Source reference must have a non-zero length")
        if target_length < cls.EPSILON:
            raise ValueError("Target reference must have a non-zero length")

        source_angle = math.atan2(source_dy, source_dx)
        target_angle = math.atan2(target_dy, target_dx)
        angle_degrees = math.degrees(target_angle - source_angle)
        if flip:
            angle_degrees += 180.0
        while angle_degrees <= -180.0:
            angle_degrees += 360.0
        while angle_degrees > 180.0:
            angle_degrees -= 360.0

        scale_factor = target_length / source_length if fit else 1.0
        return (
            angle_degrees,
            scale_factor,
            target_start.x() - source_start.x(),
            target_start.y() - source_start.y(),
        )

    @classmethod
    def apply_similarity_transform(
        cls,
        geom: QgsGeometry,
        origin: Union[QgsPoint, QgsPointXY],
        angle_degrees_ccw: float,
        scale_factor: float,
        translate_x: float,
        translate_y: float,
    ) -> QgsGeometry:
        """Apply a dimension-preserving similarity transform to a geometry clone."""
        if scale_factor <= cls.EPSILON:
            raise ValueError("Scale factor must be greater than zero")
        transformed = cls.scale_and_rotate_geometry(
            geom,
            origin,
            scale_factor,
            angle_degrees_ccw,
        )
        if abs(translate_x) >= cls.EPSILON or abs(translate_y) >= cls.EPSILON:
            if transformed.translate(translate_x, translate_y) not in (None, 0):
                raise RuntimeError("Geometry translation failed")
        return transformed

    @classmethod
    def compute_match_edge_transform(
        cls,
        source_start: Union[QgsPoint, QgsPointXY],
        source_end: Union[QgsPoint, QgsPointXY],
        target_start: Union[QgsPoint, QgsPointXY],
        target_end: Union[QgsPoint, QgsPointXY],
        collinear: bool = True,
        flip: bool = False,
    ) -> Tuple[float, QgsPointXY, float, float]:
        """Return minimal edge-match rotation, pivot, and optional translation."""
        source_dx = source_end.x() - source_start.x()
        source_dy = source_end.y() - source_start.y()
        target_dx = target_end.x() - target_start.x()
        target_dy = target_end.y() - target_start.y()
        if math.hypot(source_dx, source_dy) < cls.EPSILON:
            raise ValueError("Source edge must have a non-zero length")
        if math.hypot(target_dx, target_dy) < cls.EPSILON:
            raise ValueError("Target edge must have a non-zero length")

        angle_degrees = math.degrees(
            math.atan2(target_dy, target_dx) - math.atan2(source_dy, source_dx)
        )
        while angle_degrees <= -180.0:
            angle_degrees += 360.0
        while angle_degrees > 180.0:
            angle_degrees -= 360.0
        if flip:
            angle_degrees += 180.0
            while angle_degrees <= -180.0:
                angle_degrees += 360.0
            while angle_degrees > 180.0:
                angle_degrees -= 360.0

        pivot = QgsPointXY(
            (source_start.x() + source_end.x()) * 0.5,
            (source_start.y() + source_end.y()) * 0.5,
        )
        if not collinear:
            return angle_degrees, pivot, 0.0, 0.0

        line_a = target_start.y() - target_end.y()
        line_b = target_end.x() - target_start.x()
        line_c = line_a * target_start.x() + line_b * target_start.y()
        projected = cls._project_point_to_line(pivot, line_a, line_b, line_c)
        return (
            angle_degrees,
            pivot,
            projected.x() - pivot.x(),
            projected.y() - pivot.y(),
        )

    @classmethod
    def _replace_curve_in_geometry(
        cls,
        geom: QgsGeometry,
        part_idx: int,
        ring_idx: int,
        replacement: QgsLineString,
    ) -> QgsGeometry:
        """Return a geometry clone with one line part or polygon ring replaced."""
        geom_type = geom.type()
        is_multi = geom.isMultipart()

        if geom_type == QgsWkbTypes.GeometryType.LineGeometry:
            if not is_multi:
                if part_idx != 0 or ring_idx != 0:
                    raise ValueError("Source edge index is out of range")
                return QgsGeometry(replacement.clone())

            multi = geom.constGet()
            if multi is None or part_idx < 0 or part_idx >= multi.numGeometries():
                raise ValueError("Source edge index is out of range")
            new_multi = QgsMultiLineString()
            for index in range(multi.numGeometries()):
                line = replacement if index == part_idx else multi.geometryN(index)
                new_multi.addGeometry(line.clone())
            return QgsGeometry(new_multi)

        if geom_type != QgsWkbTypes.GeometryType.PolygonGeometry:
            raise ValueError("Source geometry must be linear or polygonal")

        def replace_ring(poly: QgsPolygon) -> QgsPolygon:
            if ring_idx < 0 or ring_idx > poly.numInteriorRings():
                raise ValueError("Source edge index is out of range")
            new_poly = QgsPolygon()
            exterior = poly.exteriorRing()
            if exterior is None:
                raise ValueError("Source geometry is empty")
            new_poly.setExteriorRing(
                replacement.clone() if ring_idx == 0 else exterior.clone()
            )
            for interior_index in range(poly.numInteriorRings()):
                interior = poly.interiorRing(interior_index)
                new_poly.addInteriorRing(
                    replacement.clone()
                    if ring_idx == interior_index + 1
                    else interior.clone()
                )
            return new_poly

        if not is_multi:
            if part_idx != 0:
                raise ValueError("Source edge index is out of range")
            polygon = geom.constGet()
            if polygon is None:
                raise ValueError("Source geometry is empty")
            return QgsGeometry(replace_ring(polygon))

        multi = geom.constGet()
        if multi is None or part_idx < 0 or part_idx >= multi.numGeometries():
            raise ValueError("Source edge index is out of range")
        new_multi = QgsMultiPolygon()
        for index in range(multi.numGeometries()):
            polygon = multi.geometryN(index)
            new_multi.addGeometry(
                replace_ring(polygon) if index == part_idx else polygon.clone()
            )
        return QgsGeometry(new_multi)

    @classmethod
    def _match_segment_in_curve(
        cls,
        curve: QgsLineString,
        segment_idx: int,
        target_start: Union[QgsPoint, QgsPointXY],
        target_end: Union[QgsPoint, QgsPointXY],
        collinear: bool,
        flip: bool,
    ) -> QgsLineString:
        """Replace one segment support line while retaining all other vertices."""
        if curve is None or curve.numPoints() < 2:
            raise ValueError("Source geometry is empty")

        num_points = curve.numPoints()
        is_closed = curve.isClosed() or (
            num_points > 2 and curve.pointN(0) == curve.pointN(num_points - 1)
        )
        effective_count = num_points - 1 if is_closed else num_points
        if segment_idx < 0 or segment_idx >= effective_count - (0 if is_closed else 1):
            raise ValueError("Source edge index is out of range")

        start_index = segment_idx
        end_index = (segment_idx + 1) % effective_count
        source_start = curve.pointN(start_index)
        source_end = curve.pointN(end_index)
        source_dx = source_end.x() - source_start.x()
        source_dy = source_end.y() - source_start.y()
        unit_x, unit_y, source_length = cls.normalize_vector(source_dx, source_dy)
        if source_length < cls.EPSILON:
            raise ValueError("Source edge must have a non-zero length")

        target_dx = target_end.x() - target_start.x()
        target_dy = target_end.y() - target_start.y()
        target_unit_x, target_unit_y, target_length = cls.normalize_vector(
            target_dx,
            target_dy,
        )
        if target_length < cls.EPSILON:
            raise ValueError("Target edge must have a non-zero length")
        if unit_x * target_unit_x + unit_y * target_unit_y < 0.0:
            target_unit_x = -target_unit_x
            target_unit_y = -target_unit_y

        is_terminal = not is_closed and (
            num_points == 2
            or segment_idx == 0
            or segment_idx == num_points - 2
        )
        if flip and is_terminal:
            target_unit_x = -target_unit_x
            target_unit_y = -target_unit_y

        midpoint = QgsPointXY(
            (source_start.x() + source_end.x()) * 0.5,
            (source_start.y() + source_end.y()) * 0.5,
        )
        if collinear:
            line_anchor = QgsPointXY(target_start)
        else:
            line_anchor = midpoint
        line_end = QgsPointXY(
            line_anchor.x() + target_unit_x,
            line_anchor.y() + target_unit_y,
        )

        if not is_closed and num_points == 2:
            center = midpoint
            if collinear:
                along = (
                    (midpoint.x() - line_anchor.x()) * target_unit_x
                    + (midpoint.y() - line_anchor.y()) * target_unit_y
                )
                center = QgsPointXY(
                    line_anchor.x() + along * target_unit_x,
                    line_anchor.y() + along * target_unit_y,
                )
            new_start = cls._point_at_xy_with_source_dimensions(
                QgsPointXY(
                    center.x() - source_length * 0.5 * target_unit_x,
                    center.y() - source_length * 0.5 * target_unit_y,
                ),
                source_start,
            )
            new_end = cls._point_at_xy_with_source_dimensions(
                QgsPointXY(
                    center.x() + source_length * 0.5 * target_unit_x,
                    center.y() + source_length * 0.5 * target_unit_y,
                ),
                source_end,
            )
        else:
            if segment_idx > 0:
                previous = curve.pointN(segment_idx - 1)
            elif is_closed:
                previous = curve.pointN(effective_count - 1)
            else:
                previous = None

            if end_index < effective_count - 1:
                following = curve.pointN(end_index + 1)
            elif is_closed:
                following = curve.pointN((end_index + 1) % effective_count)
            else:
                following = None

            if previous is not None:
                new_start = cls.compute_line_intersection(
                    previous,
                    source_start,
                    line_anchor,
                    line_end,
                )
                if new_start is None:
                    raise ValueError(
                        "Target line does not intersect the adjacent source edge"
                    )
            else:
                new_start = None

            if following is not None:
                new_end = cls.compute_line_intersection(
                    line_anchor,
                    line_end,
                    source_end,
                    following,
                )
                if new_end is None:
                    raise ValueError(
                        "Target line does not intersect the adjacent source edge"
                    )
            else:
                new_end = None

            if new_start is None and new_end is not None:
                new_start = cls._point_at_xy_with_source_dimensions(
                    QgsPointXY(
                        new_end.x() - source_length * target_unit_x,
                        new_end.y() - source_length * target_unit_y,
                    ),
                    source_start,
                )
            elif new_end is None and new_start is not None:
                new_end = cls._point_at_xy_with_source_dimensions(
                    QgsPointXY(
                        new_start.x() + source_length * target_unit_x,
                        new_start.y() + source_length * target_unit_y,
                    ),
                    source_end,
                )

        if new_start is None or new_end is None:
            raise ValueError("Could not construct the matched source edge")
        new_dx = new_end.x() - new_start.x()
        new_dy = new_end.y() - new_start.y()
        new_length = math.hypot(new_dx, new_dy)
        if new_length < cls.EPSILON:
            raise ValueError("Matched source edge would collapse")
        if new_dx * target_unit_x + new_dy * target_unit_y <= cls.EPSILON:
            raise ValueError("Matched source edge would reverse")

        new_points = [cls._copy_point(curve.pointN(index)) for index in range(num_points)]
        new_points[start_index] = new_start
        new_points[end_index] = new_end
        if is_closed:
            if start_index == 0:
                new_points[num_points - 1] = cls._copy_point(new_start)
            elif end_index == 0:
                new_points[num_points - 1] = cls._copy_point(new_end)

        for index in range(1, len(new_points)):
            if cls.distance(new_points[index - 1], new_points[index]) < cls.EPSILON:
                raise ValueError("Matched source edge would collapse an adjacent edge")

        result = QgsLineString()
        for point in new_points:
            result.addVertex(point)
        return result

    @classmethod
    def match_segment_to_reference(
        cls,
        geom: QgsGeometry,
        part_idx: int,
        ring_idx: int,
        segment_idx: int,
        target_start: Union[QgsPoint, QgsPointXY],
        target_end: Union[QgsPoint, QgsPointXY],
        collinear: bool = True,
        flip: bool = False,
    ) -> QgsGeometry:
        """Locally make one source segment collinear or parallel to a reference."""
        if not geom or geom.isNull() or geom.isEmpty():
            raise ValueError("Source geometry is empty")
        if geom.type() not in (
            QgsWkbTypes.GeometryType.LineGeometry,
            QgsWkbTypes.GeometryType.PolygonGeometry,
        ):
            raise ValueError("Source geometry must be linear or polygonal")
        if cls.has_curved_segments(geom) or QgsWkbTypes.isCurvedType(geom.wkbType()):
            raise ValueError("Native curved source geometries are not supported")
        if (
            geom.type() == QgsWkbTypes.GeometryType.PolygonGeometry
            and not geom.isGeosValid()
        ):
            raise ValueError("Source geometry is invalid")

        curve = cls.get_curve_from_geometry(geom, part_idx, ring_idx)
        if curve is None or not isinstance(curve, QgsLineString):
            raise ValueError("Source edge must be a straight segment")
        replacement = cls._match_segment_in_curve(
            curve,
            segment_idx,
            target_start,
            target_end,
            collinear,
            flip,
        )
        result = cls._replace_curve_in_geometry(
            geom,
            part_idx,
            ring_idx,
            replacement,
        )
        if result.isNull() or result.isEmpty():
            raise ValueError("Matched source geometry is empty")
        if (
            result.type() == QgsWkbTypes.GeometryType.PolygonGeometry
            and not result.isGeosValid()
        ):
            raise ValueError("Matched source geometry is invalid")
        return result

    @classmethod
    def _path_tangent_angle(cls, path: QgsGeometry, measure: float) -> float:
        """Return the mathematical tangent angle along increasing path measure."""
        path_length = path.length()
        if path_length < cls.EPSILON:
            raise ValueError("Path must have a non-zero length")
        clamped_measure = max(0.0, min(path_length, measure))
        sample_step = max(path_length * 1e-7, cls.EPSILON * 10.0)
        before_measure = max(0.0, clamped_measure - sample_step)
        after_measure = min(path_length, clamped_measure + sample_step)
        if after_measure - before_measure < cls.EPSILON:
            before_measure = max(0.0, clamped_measure - sample_step * 10.0)
            after_measure = min(path_length, clamped_measure + sample_step * 10.0)

        before_geom = path.interpolate(before_measure)
        after_geom = path.interpolate(after_measure)
        if before_geom.isEmpty() or after_geom.isEmpty():
            raise ValueError("Could not interpolate the selected path")
        before = before_geom.asPoint()
        after = after_geom.asPoint()
        dx = after.x() - before.x()
        dy = after.y() - before.y()
        if math.hypot(dx, dy) < cls.EPSILON:
            raise ValueError("Could not determine the path tangent")
        return math.atan2(dy, dx)

    @classmethod
    def compute_path_placements(
        cls,
        path: QgsGeometry,
        start_measure: float,
        end_measure: float,
        distribution_mode: str,
        value: float,
        include_start: bool = True,
        offset: float = 0.0,
        tangent_orientation: bool = False,
        reverse: bool = False,
    ) -> List[Tuple[QgsPointXY, float]]:
        """Return placement points and relative rotations along a line path."""
        if not path or path.isNull() or path.isEmpty():
            return []
        if path.type() != QgsWkbTypes.GeometryType.LineGeometry:
            raise ValueError("Array path must be a line geometry")

        path_length = path.length()
        if path_length < cls.EPSILON:
            return []
        start = max(0.0, min(path_length, float(start_measure)))
        end = max(0.0, min(path_length, float(end_measure)))
        if reverse:
            start, end = end, start
        range_length = abs(end - start)
        if range_length < cls.EPSILON:
            return []

        travel_distances: List[float]
        if distribution_mode == "count":
            count = int(value)
            if count < 1:
                return []
            if include_start:
                if count == 1:
                    travel_distances = [0.0]
                else:
                    step = range_length / float(count - 1)
                    travel_distances = [step * index for index in range(count)]
            else:
                step = range_length / float(count)
                travel_distances = [step * index for index in range(1, count + 1)]
        elif distribution_mode == "spacing":
            spacing = float(value)
            if spacing <= cls.EPSILON:
                return []
            travel_distances = [0.0] if include_start else []
            distance = spacing
            while distance <= range_length + cls.EPSILON:
                travel_distances.append(min(distance, range_length))
                distance += spacing
        else:
            raise ValueError("Unsupported path distribution mode")

        if not travel_distances:
            return []

        direction_sign = 1.0 if end > start else -1.0
        first_measure = start + direction_sign * travel_distances[0]
        base_angle = cls._path_tangent_angle(path, first_measure)
        if direction_sign < 0.0:
            base_angle += math.pi

        placements: List[Tuple[QgsPointXY, float]] = []
        for travel_distance in travel_distances:
            measure = start + direction_sign * travel_distance
            point_geom = path.interpolate(measure)
            if point_geom.isEmpty():
                continue
            point = point_geom.asPoint()
            original_tangent = cls._path_tangent_angle(path, measure)
            placed_x = point.x() - math.sin(original_tangent) * offset
            placed_y = point.y() + math.cos(original_tangent) * offset

            relative_angle = 0.0
            if tangent_orientation:
                effective_tangent = original_tangent
                if direction_sign < 0.0:
                    effective_tangent += math.pi
                relative_angle = math.degrees(effective_tangent - base_angle)
                while relative_angle <= -180.0:
                    relative_angle += 360.0
                while relative_angle > 180.0:
                    relative_angle -= 360.0
            placements.append((QgsPointXY(placed_x, placed_y), relative_angle))
        return placements

    @classmethod
    def extract_geometry_parts(
        cls,
        geom: QgsGeometry,
        part_indices: List[int],
    ) -> Tuple[QgsGeometry, List[QgsGeometry]]:
        """Return the remaining geometry and cloned parts at the given indices."""
        if not geom or geom.isNull() or geom.isEmpty():
            return QgsGeometry(geom), []
        parts = geom.asGeometryCollection() if geom.isMultipart() else [QgsGeometry(geom)]
        selected = sorted(set(int(index) for index in part_indices))
        if any(index < 0 or index >= len(parts) for index in selected):
            raise IndexError("Geometry part index is out of range")

        extracted = [QgsGeometry(parts[index]) for index in selected]
        remaining = [
            QgsGeometry(part)
            for index, part in enumerate(parts)
            if index not in selected
        ]
        if not remaining:
            remaining_geometry = QgsGeometry()
        elif len(remaining) == 1:
            remaining_geometry = remaining[0]
        else:
            remaining_geometry = QgsGeometry.collectGeometry(remaining)
        return remaining_geometry, extracted

    @classmethod
    def apply_polygon_boolean(
        cls,
        target: QgsGeometry,
        cutters: List[QgsGeometry],
        operation: Union[str, BooleanOperation],
    ) -> QgsGeometry:
        """Apply a safe polygon difference or intersection without layer edits."""
        try:
            normalized_operation = BooleanOperation(operation)
        except ValueError as error:
            raise ValueError("Unsupported polygon boolean operation") from error
        if not target or target.isNull() or target.isEmpty():
            raise ValueError("Target geometry is empty")
        if target.type() != QgsWkbTypes.GeometryType.PolygonGeometry:
            raise ValueError("Target geometry must be polygonal")
        if cls.has_curved_segments(target) or QgsWkbTypes.hasM(target.wkbType()):
            raise ValueError("M/ZM and curved polygon geometries are not supported")
        if not target.isGeosValid():
            raise ValueError("Target geometry is invalid")
        if not cutters:
            raise ValueError("At least one cutter is required")

        safe_cutters: List[QgsGeometry] = []
        for cutter in cutters:
            if not cutter or cutter.isNull() or cutter.isEmpty():
                continue
            if cutter.type() != QgsWkbTypes.GeometryType.PolygonGeometry:
                raise ValueError("Cutter geometry must be polygonal")
            if cls.has_curved_segments(cutter) or QgsWkbTypes.hasM(cutter.wkbType()):
                raise ValueError("M/ZM and curved polygon geometries are not supported")
            if not cutter.isGeosValid():
                raise ValueError("Cutter geometry is invalid")
            safe_cutters.append(QgsGeometry(cutter))
        if not safe_cutters:
            raise ValueError("At least one non-empty cutter is required")

        cutter_union = (
            safe_cutters[0]
            if len(safe_cutters) == 1
            else QgsGeometry.unaryUnion(safe_cutters)
        )
        if cutter_union.isNull() or not cutter_union.isGeosValid():
            raise ValueError("Cutter union is invalid")
        if normalized_operation == BooleanOperation.Subtract:
            result = target.difference(cutter_union)
        elif normalized_operation == BooleanOperation.Clip:
            result = target.intersection(cutter_union)

        if result.isNull():
            raise RuntimeError("Polygon boolean operation failed")
        if not result.isEmpty():
            if result.type() != QgsWkbTypes.GeometryType.PolygonGeometry:
                return QgsGeometry()
            if not result.isGeosValid():
                raise RuntimeError("Polygon boolean result is invalid")
        return result

    @classmethod
    def get_curve_from_geometry(
        cls,
        geom: QgsGeometry,
        part_idx: int = 0,
        ring_idx: int = 0,
    ) -> Optional[QgsLineString]:
        """Extracts the specific curve / ring (QgsLineString/QgsCurve) from a QgsGeometry."""
        if not geom or geom.isEmpty() or geom.isNull():
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
                if not poly:
                    return None
                if ring_idx == 0:
                    return poly.exteriorRing()
                elif ring_idx - 1 < poly.numInteriorRings():
                    return poly.interiorRing(ring_idx - 1)
            else:
                multi = geom.constGet()
                if not multi or part_idx >= multi.numGeometries():
                    return None
                poly = multi.geometryN(part_idx)
                if not poly:
                    return None
                if ring_idx == 0:
                    return poly.exteriorRing()
                elif ring_idx - 1 < poly.numInteriorRings():
                    return poly.interiorRing(ring_idx - 1)
        return None

    @classmethod
    def get_max_extend_distance(
        cls,
        curve: QgsLineString,
        segment_idx: int,
        distance_sign: float,
    ) -> Optional[float]:
        """
        Calculates the maximum allowable offset distance in the given direction (distance_sign: +1 or -1)
        for 'extend' mode before the shifted segment passes the far node of an adjacent edge or collapses at the apex.
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

        i = segment_idx
        v_i = curve.pointN(i)
        v_next = curve.pointN((i + 1) % effective_count if is_closed else i + 1)

        dx = v_next.x() - v_i.x()
        dy = v_next.y() - v_i.y()
        length = math.hypot(dx, dy)
        if length < cls.EPSILON:
            return None

        nx = -dy / length
        ny = dx / length

        limits = []

        # 1. Left adjacent edge (V_prev -> V_i)
        v_prev = None
        if i > 0:
            v_prev = curve.pointN(i - 1)
        elif is_closed:
            v_prev = curve.pointN(effective_count - 1)

        if v_prev is not None:
            d_signed_prev = (v_prev.x() - v_i.x()) * nx + (v_prev.y() - v_i.y()) * ny
            # V_prev can only limit the shift if it lies in the direction of shift (same sign)
            if (distance_sign > 0 and d_signed_prev > cls.EPSILON) or (distance_sign < 0 and d_signed_prev < -cls.EPSILON):
                l_prev = math.hypot(v_i.x() - v_prev.x(), v_i.y() - v_prev.y())
                if l_prev > cls.EPSILON:
                    dir_prev_x = (v_i.x() - v_prev.x()) / l_prev
                    dir_prev_y = (v_i.y() - v_prev.y()) / l_prev
                    proj_prev = dir_prev_x * nx + dir_prev_y * ny
                    # Moving in distance_sign trims (shortens) V_prev -> V_i when distance_sign and proj_prev have opposite signs
                    if (distance_sign > 0 and proj_prev < -cls.EPSILON) or (distance_sign < 0 and proj_prev > cls.EPSILON):
                        limits.append(abs(d_signed_prev))

        # 2. Right adjacent edge (V_{i+1} -> V_after)
        v_after = None
        if not is_closed:
            if i + 1 < num_pts - 1:
                v_after = curve.pointN(i + 2)
        else:
            v_after = curve.pointN((i + 2) % effective_count)

        if v_after is not None:
            d_signed_after = (v_after.x() - v_next.x()) * nx + (v_after.y() - v_next.y()) * ny
            # V_after can only limit the shift if it lies in the direction of shift (same sign)
            if (distance_sign > 0 and d_signed_after > cls.EPSILON) or (distance_sign < 0 and d_signed_after < -cls.EPSILON):
                l_next = math.hypot(v_after.x() - v_next.x(), v_after.y() - v_next.y())
                if l_next > cls.EPSILON:
                    dir_next_x = (v_after.x() - v_next.x()) / l_next
                    dir_next_y = (v_after.y() - v_next.y()) / l_next
                    proj_next = dir_next_x * nx + dir_next_y * ny
                    # Moving in distance_sign trims (shortens) V_{i+1} -> V_after when distance_sign and proj_next have same signs
                    if (distance_sign > 0 and proj_next > cls.EPSILON) or (distance_sign < 0 and proj_next < -cls.EPSILON):
                        limits.append(abs(d_signed_after))

        # 3. Apex of converging edges
        if v_prev is not None and v_after is not None:
            v_apex = cls.compute_line_intersection(v_prev, v_i, v_next, v_after)
            if v_apex is not None:
                d_apex = (v_apex.x() - v_i.x()) * nx + (v_apex.y() - v_i.y()) * ny
                if (distance_sign > 0 and d_apex > cls.EPSILON) or (distance_sign < 0 and d_apex < -cls.EPSILON):
                    limits.append(abs(d_apex))

        if limits:
            return min(limits)
        return None

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
        if mode == "extend":
            d_max = cls.get_max_extend_distance(curve, segment_idx, 1.0 if distance >= 0 else -1.0)
            if d_max is not None and abs(distance) > d_max:
                distance = d_max if distance >= 0 else -d_max

        p1 = cls._interpolate_point_dimensions(
            v_i,
            v_next,
            v_i.x() + distance * nx,
            v_i.y() + distance * ny,
            0.0,
        )
        p2 = cls._interpolate_point_dimensions(
            v_i,
            v_next,
            v_next.x() + distance * nx,
            v_next.y() + distance * ny,
            1.0,
        )

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
                v_prime_next = cls._point_at_xy_with_source_dimensions(
                    QgsPointXY(v_prime_i.x() + length * ux, v_prime_i.y() + length * uy),
                    v_next,
                )
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
                v_prime_i = cls._point_at_xy_with_source_dimensions(
                    QgsPointXY(v_prime_next.x() - length * ux, v_prime_next.y() - length * uy),
                    v_i,
                )
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

        # Clean up any consecutive duplicate vertices (e.g. when adjacent edge is consumed to its node)
        cleaned_pts = []
        for pt in new_pts:
            if not cleaned_pts:
                cleaned_pts.append(pt)
            else:
                last_pt = cleaned_pts[-1]
                if math.hypot(pt.x() - last_pt.x(), pt.y() - last_pt.y()) > cls.EPSILON:
                    cleaned_pts.append(pt)

        # For closed rings, ensure closing vertex matches first vertex
        if is_closed and len(cleaned_pts) > 2:
            first_pt = cleaned_pts[0]
            last_pt = cleaned_pts[-1]
            if math.hypot(first_pt.x() - last_pt.x(), first_pt.y() - last_pt.y()) > cls.EPSILON:
                cleaned_pts.append(first_pt)

        res = QgsLineString()
        for pt in cleaned_pts:
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
        if cls.has_curved_segments(geom):
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
                if not res_geom.isEmpty():
                    res_geom.removeDuplicateNodes(cls.EPSILON)
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
                if not res_multi.isEmpty():
                    res_multi.removeDuplicateNodes(cls.EPSILON)
                if mode == "extend" and not res_multi.isEmpty() and not res_multi.isGeosValid():
                    fallback_multi = cls.offset_segment(geom, part_idx, ring_idx, segment_idx, distance, mode="step")
                    if fallback_multi and fallback_multi.isGeosValid():
                        return fallback_multi
                return res_multi

        return None

    @classmethod
    def get_all_curves_from_geometry(cls, geom: QgsGeometry) -> List[Tuple[int, int, QgsLineString]]:
        """
        Returns all curves from geometry as (part_idx, ring_idx, curve).
        ring_idx=0 is exterior ring / polyline, ring_idx >= 1 are interior rings (holes).
        """
        results = []
        if not geom or geom.isEmpty() or geom.isNull():
            return results
        geom_type = geom.type()
        is_multi = geom.isMultipart()

        if geom_type == QgsWkbTypes.GeometryType.LineGeometry:
            if not is_multi:
                curve = geom.constGet()
                if curve is not None:
                    results.append((0, 0, curve))
            else:
                multi = geom.constGet()
                if multi is not None:
                    for p in range(multi.numGeometries()):
                        curve = multi.geometryN(p)
                        if curve is not None:
                            results.append((p, 0, curve))

        elif geom_type == QgsWkbTypes.GeometryType.PolygonGeometry:
            if not is_multi:
                poly = geom.constGet()
                if poly is not None:
                    ext = poly.exteriorRing()
                    if ext is not None:
                        results.append((0, 0, ext))
                    for r in range(poly.numInteriorRings()):
                        intr = poly.interiorRing(r)
                        if intr is not None:
                            results.append((0, r + 1, intr))
            else:
                multi = geom.constGet()
                if multi is not None:
                    for p in range(multi.numGeometries()):
                        poly = multi.geometryN(p)
                        if poly is not None:
                            ext = poly.exteriorRing()
                            if ext is not None:
                                results.append((p, 0, ext))
                            for r in range(poly.numInteriorRings()):
                                intr = poly.interiorRing(r)
                                if intr is not None:
                                    results.append((p, r + 1, intr))

        return results

    @classmethod
    def find_duplicate_nodes(cls, geom: QgsGeometry, tolerance: float = 1e-6) -> List[Dict]:
        """
        Finds all clusters of duplicate (consecutive) nodes within tolerance in the geometry.
        Returns a list of dicts with part_idx, ring_idx, v1_idx, v2_idx, vertex_indices, count, point, next_point, is_closed.
        """
        dups = []
        curves = cls.get_all_curves_from_geometry(geom)
        for part_idx, ring_idx, curve in curves:
            num_pts = curve.numPoints()
            if num_pts < 2:
                continue
            is_closed = curve.isClosed() or (num_pts > 2 and curve.pointN(0) == curve.pointN(num_pts - 1))
            check_limit = (num_pts - 1) if is_closed else num_pts
            visited = set()
            for i in range(check_limit):
                if i in visited:
                    continue
                p1 = curve.pointN(i)
                matching_indices = [i]
                j = i + 1
                while j < check_limit:
                    pj = curve.pointN(j)
                    if math.hypot(p1.x() - pj.x(), p1.y() - pj.y()) <= tolerance:
                        matching_indices.append(j)
                        visited.add(j)
                        j += 1
                    else:
                        break

                if len(matching_indices) > 1:
                    dups.append({
                        "part_idx": part_idx,
                        "ring_idx": ring_idx,
                        "v1_idx": matching_indices[0],
                        "v2_idx": matching_indices[1],
                        "vertex_indices": matching_indices,
                        "count": len(matching_indices),
                        "point": p1,
                        "next_point": curve.pointN(matching_indices[1]),
                        "is_closed": is_closed,
                        "total_points": num_pts,
                    })
        return dups

    @classmethod
    def remove_duplicate_node_at_index(
        cls,
        geom: QgsGeometry,
        part_idx: int,
        ring_idx: int,
        vertex_idx: int,
    ) -> QgsGeometry:
        """
        Removes the single vertex at vertex_idx in the specified part and ring of geometry.
        """
        if not geom or geom.isEmpty() or geom.isNull():
            return geom

        def _remove_from_curve(curve: QgsLineString, v_idx: int, closed: bool) -> QgsLineString:
            n = curve.numPoints()
            if n <= 2:
                return curve.clone()
            pts = [curve.pointN(k) for k in range(n)]
            if 0 <= v_idx < n:
                del pts[v_idx]
            if closed and len(pts) >= 3:
                if pts[0] != pts[-1]:
                    pts[-1] = pts[0]
            return QgsLineString(pts)

        geom_type = geom.type()
        is_multi = geom.isMultipart()

        if geom_type == QgsWkbTypes.GeometryType.LineGeometry:
            if not is_multi:
                curve = geom.constGet()
                if not curve:
                    return geom
                is_closed = curve.isClosed() or (curve.numPoints() > 2 and curve.pointN(0) == curve.pointN(curve.numPoints() - 1))
                new_curve = _remove_from_curve(curve, vertex_idx, is_closed)
                return QgsGeometry(new_curve)
            else:
                multi = QgsMultiLineString()
                orig_multi = geom.constGet()
                for p in range(orig_multi.numGeometries()):
                    curve = orig_multi.geometryN(p)
                    if p == part_idx:
                        is_closed = curve.isClosed() or (curve.numPoints() > 2 and curve.pointN(0) == curve.pointN(curve.numPoints() - 1))
                        curve = _remove_from_curve(curve, vertex_idx, is_closed)
                    multi.addGeometry(curve.clone())
                return QgsGeometry(multi)

        elif geom_type == QgsWkbTypes.GeometryType.PolygonGeometry:
            if not is_multi:
                poly = geom.constGet()
                if not poly:
                    return geom
                new_poly = QgsPolygon()
                ext = poly.exteriorRing()
                if ext is not None:
                    if ring_idx == 0:
                        ext = _remove_from_curve(ext, vertex_idx, closed=True)
                    new_poly.setExteriorRing(ext.clone())
                for r in range(poly.numInteriorRings()):
                    intr = poly.interiorRing(r)
                    if intr is not None:
                        if ring_idx == r + 1:
                            intr = _remove_from_curve(intr, vertex_idx, closed=True)
                        new_poly.addInteriorRing(intr.clone())
                return QgsGeometry(new_poly)
            else:
                multi = QgsMultiPolygon()
                orig_multi = geom.constGet()
                for p in range(orig_multi.numGeometries()):
                    poly = orig_multi.geometryN(p)
                    new_poly = QgsPolygon()
                    ext = poly.exteriorRing()
                    if ext is not None:
                        if p == part_idx and ring_idx == 0:
                            ext = _remove_from_curve(ext, vertex_idx, closed=True)
                        new_poly.setExteriorRing(ext.clone())
                    for r in range(poly.numInteriorRings()):
                        intr = poly.interiorRing(r)
                        if intr is not None:
                            if p == part_idx and ring_idx == r + 1:
                                intr = _remove_from_curve(intr, vertex_idx, closed=True)
                            new_poly.addInteriorRing(intr.clone())
                    multi.addGeometry(new_poly)
                return QgsGeometry(multi)

        return geom

    @classmethod
    def remove_duplicate_indices_except(
        cls,
        geom: QgsGeometry,
        part_idx: int,
        ring_idx: int,
        keep_vertex_idx: int,
        cluster_indices: List[int],
    ) -> QgsGeometry:
        """
        Removes all duplicate indices in cluster_indices except keep_vertex_idx.
        """
        if not geom or geom.isEmpty() or geom.isNull():
            return geom

        indices_to_remove = set(idx for idx in cluster_indices if idx != keep_vertex_idx)

        def _clean_curve(curve: QgsLineString, closed: bool) -> QgsLineString:
            n = curve.numPoints()
            pts = [curve.pointN(i) for i in range(n) if i not in indices_to_remove]
            if closed and len(pts) >= 3 and pts[0] != pts[-1]:
                pts.append(pts[0])
            return QgsLineString(pts)

        geom_type = geom.type()
        is_multi = geom.isMultipart()

        if geom_type == QgsWkbTypes.GeometryType.LineGeometry:
            if not is_multi:
                curve = geom.constGet()
                if not curve:
                    return geom
                is_closed = curve.isClosed() or (curve.numPoints() > 2 and curve.pointN(0) == curve.pointN(curve.numPoints() - 1))
                return QgsGeometry(_clean_curve(curve, is_closed))
            else:
                multi = QgsMultiLineString()
                orig_multi = geom.constGet()
                for p in range(orig_multi.numGeometries()):
                    curve = orig_multi.geometryN(p)
                    if p == part_idx:
                        is_closed = curve.isClosed() or (curve.numPoints() > 2 and curve.pointN(0) == curve.pointN(curve.numPoints() - 1))
                        curve = _clean_curve(curve, is_closed)
                    multi.addGeometry(curve.clone())
                return QgsGeometry(multi)

        elif geom_type == QgsWkbTypes.GeometryType.PolygonGeometry:
            if not is_multi:
                poly = geom.constGet()
                if not poly:
                    return geom
                new_poly = QgsPolygon()
                ext = poly.exteriorRing()
                if ext is not None:
                    if ring_idx == 0:
                        ext = _clean_curve(ext, True)
                    new_poly.setExteriorRing(ext.clone())
                for r in range(poly.numInteriorRings()):
                    intr = poly.interiorRing(r)
                    if intr is not None:
                        if ring_idx == r + 1:
                            intr = _clean_curve(intr, True)
                        new_poly.addInteriorRing(intr.clone())
                return QgsGeometry(new_poly)
            else:
                multi = QgsMultiPolygon()
                orig_multi = geom.constGet()
                for p in range(orig_multi.numGeometries()):
                    poly = orig_multi.geometryN(p)
                    new_poly = QgsPolygon()
                    ext = poly.exteriorRing()
                    if ext is not None:
                        if p == part_idx and ring_idx == 0:
                            ext = _clean_curve(ext, True)
                        new_poly.setExteriorRing(ext.clone())
                    for r in range(poly.numInteriorRings()):
                        intr = poly.interiorRing(r)
                        if intr is not None:
                            if p == part_idx and ring_idx == r + 1:
                                intr = _clean_curve(intr, True)
                            new_poly.addInteriorRing(intr.clone())
                    multi.addGeometry(new_poly)
                return QgsGeometry(multi)

        return geom

    @classmethod
    def merge_duplicate_nodes_at_point(
        cls,
        geom: QgsGeometry,
        target_pt: QgsPoint,
        tolerance: float = 1e-5,
    ) -> QgsGeometry:
        """
        Removes all duplicate consecutive vertices at target_pt across the geometry,
        leaving exactly 1 vertex at this location regardless of how many duplicates exist (2, 3, 4...).
        """
        if not geom or geom.isEmpty() or geom.isNull():
            return geom

        geom_type = geom.type()
        is_multi = geom.isMultipart()

        def _clean_curve_at_point(curve, is_closed: bool):
            n = curve.numPoints()
            if n == 0:
                return curve
            new_pts = []
            found_target = False
            for i in range(n):
                pt = curve.pointN(i)
                # Check distance
                dx = pt.x() - target_pt.x()
                dy = pt.y() - target_pt.y()
                if math.hypot(dx, dy) <= tolerance:
                    if not found_target:
                        new_pts.append(pt)
                        found_target = True
                    else:
                        # Skip duplicate at this point
                        continue
                else:
                    new_pts.append(pt)
            if is_closed and len(new_pts) > 0 and new_pts[0] != new_pts[-1]:
                new_pts.append(new_pts[0])
            return QgsLineString(new_pts)

        if geom_type == QgsWkbTypes.GeometryType.LineGeometry:
            if not is_multi:
                line = geom.constGet()
                return QgsGeometry(_clean_curve_at_point(line, line.isClosed()))
            else:
                multi = QgsMultiLineString()
                orig_multi = geom.constGet()
                for p in range(orig_multi.numGeometries()):
                    line = orig_multi.geometryN(p)
                    multi.addGeometry(_clean_curve_at_point(line, line.isClosed()))
                return QgsGeometry(multi)

        elif geom_type == QgsWkbTypes.GeometryType.PolygonGeometry:
            if not is_multi:
                poly = geom.constGet()
                new_poly = QgsPolygon()
                ext = poly.exteriorRing()
                if ext is not None:
                    new_poly.setExteriorRing(_clean_curve_at_point(ext, True))
                for r in range(poly.numInteriorRings()):
                    intr = poly.interiorRing(r)
                    if intr is not None:
                        new_poly.addInteriorRing(_clean_curve_at_point(intr, True))
                return QgsGeometry(new_poly)
            else:
                multi = QgsMultiPolygon()
                orig_multi = geom.constGet()
                for p in range(orig_multi.numGeometries()):
                    poly = orig_multi.geometryN(p)
                    new_poly = QgsPolygon()
                    ext = poly.exteriorRing()
                    if ext is not None:
                        new_poly.setExteriorRing(_clean_curve_at_point(ext, True))
                    for r in range(poly.numInteriorRings()):
                        intr = poly.interiorRing(r)
                        if intr is not None:
                            new_poly.addInteriorRing(_clean_curve_at_point(intr, True))
                    multi.addGeometry(new_poly)
                return QgsGeometry(multi)

        return geom

    @classmethod
    def remove_all_duplicate_nodes(
        cls,
        geom: QgsGeometry,
        tolerance: float = 1e-6,
    ) -> Tuple[QgsGeometry, int]:
        """
        Cleans all duplicate nodes across the geometry within tolerance.
        Returns a tuple of (cleaned_geometry, count_removed).
        """
        if not geom or geom.isEmpty() or geom.isNull():
            return geom, 0

        dups = cls.find_duplicate_nodes(geom, tolerance)
        if not dups:
            return geom, 0

        cleaned_geom = QgsGeometry(geom)
        cleaned_geom.removeDuplicateNodes(tolerance)
        if not cleaned_geom.isGeosValid():
            cleaned_geom = cleaned_geom.makeValid()

        return cleaned_geom, len(dups)

    @classmethod
    def find_self_intersections(cls, geom: QgsGeometry) -> List[Dict]:
        """
        Finds all segment-segment self-intersections in the geometry.
        Returns a list of dicts with part_idx, ring_idx, seg1_idx, seg2_idx, point.
        """
        intersections = []
        if not geom or geom.isEmpty() or geom.isNull():
            return intersections

        curves = cls.get_all_curves_from_geometry(geom)
        for part_idx, ring_idx, curve in curves:
            n = curve.numPoints()
            if n < 4:
                continue
            is_closed = curve.isClosed() or (n > 2 and curve.pointN(0) == curve.pointN(n - 1))
            num_segs = n - 1

            for i in range(num_segs):
                p1 = curve.pointN(i)
                p2 = curve.pointN(i + 1)
                for j in range(i + 2, num_segs):
                    if is_closed and i == 0 and j == num_segs - 1:
                        continue  # Adjacent at closing point
                    p3 = curve.pointN(j)
                    p4 = curve.pointN(j + 1)

                    # Compute intersection
                    x1, y1 = p1.x(), p1.y()
                    x2, y2 = p2.x(), p2.y()
                    x3, y3 = p3.x(), p3.y()
                    x4, y4 = p4.x(), p4.y()

                    denom = (y4 - y3) * (x2 - x1) - (x4 - x3) * (y2 - y1)
                    if abs(denom) < 1e-12:
                        continue

                    ua = ((x4 - x3) * (y1 - y3) - (y4 - y3) * (x1 - x3)) / denom
                    ub = ((x2 - x1) * (y1 - y3) - (y2 - y1) * (x1 - x3)) / denom

                    if 1e-6 < ua < 1.0 - 1e-6 and 1e-6 < ub < 1.0 - 1e-6:
                        ix = x1 + ua * (x2 - x1)
                        iy = y1 + ua * (y2 - y1)
                        inter_pt = cls.compute_line_intersection(p1, p2, p3, p4)
                        if inter_pt is None:
                            inter_pt = QgsPoint(ix, iy)
                        intersections.append({
                            "part_idx": part_idx,
                            "ring_idx": ring_idx,
                            "seg1_idx": i,
                            "seg2_idx": j,
                            "point": inter_pt,
                        })
        return intersections

    @classmethod
    def untangle_self_intersection(
        cls,
        geom: QgsGeometry,
        part_idx: int,
        ring_idx: int,
        seg1_idx: int,
        seg2_idx: int,
        inter_pt: QgsPoint,
        keep_loop: int = 0,
    ) -> QgsGeometry:
        """
        Untangles a self-intersecting polygon ring at inter_pt.
        keep_loop=0 keeps the larger loop, keep_loop=1 keeps loop 1, keep_loop=2 keeps loop 2.
        """
        if not geom or geom.isEmpty() or geom.isNull():
            return geom
        if cls.has_curved_segments(geom):
            return QgsGeometry(geom)

        curve = cls.get_curve_from_geometry(geom, part_idx, ring_idx)
        if not curve or curve.numPoints() < 4:
            return geom.makeValid() if not geom.isGeosValid() else geom

        n = curve.numPoints()
        i = min(seg1_idx, seg2_idx)
        j = max(seg1_idx, seg2_idx)

        dimensioned_intersection = cls.compute_line_intersection(
            curve.pointN(i),
            curve.pointN(i + 1),
            curve.pointN(j),
            curve.pointN(j + 1),
        )
        if dimensioned_intersection is not None:
            inter_pt = dimensioned_intersection

        # Loop 1: 0..i, inter_pt, j+1..n-1
        pts_loop1 = [curve.pointN(k) for k in range(i + 1)] + [inter_pt] + [curve.pointN(k) for k in range(j + 1, n)]
        if pts_loop1[0] != pts_loop1[-1]:
            pts_loop1.append(pts_loop1[0])

        # Loop 2: inter_pt, i+1..j, inter_pt
        pts_loop2 = [inter_pt] + [curve.pointN(k) for k in range(i + 1, j + 1)] + [inter_pt]

        poly1 = QgsPolygon()
        poly1.setExteriorRing(QgsLineString(pts_loop1))
        g1 = QgsGeometry(poly1)

        poly2 = QgsPolygon()
        poly2.setExteriorRing(QgsLineString(pts_loop2))
        g2 = QgsGeometry(poly2)

        if keep_loop == 1:
            chosen_ring = QgsLineString(pts_loop1)
        elif keep_loop == 2:
            chosen_ring = QgsLineString(pts_loop2)
        else:
            chosen_ring = QgsLineString(pts_loop1) if g1.area() >= g2.area() else QgsLineString(pts_loop2)

        # Reconstruct geometry with untangled ring
        geom_type = geom.type()
        is_multi = geom.isMultipart()

        if geom_type == QgsWkbTypes.GeometryType.PolygonGeometry:
            if not is_multi:
                poly = geom.constGet()
                new_poly = QgsPolygon()
                if ring_idx == 0:
                    new_poly.setExteriorRing(chosen_ring.clone())
                else:
                    ext = poly.exteriorRing()
                    if ext:
                        new_poly.setExteriorRing(ext.clone())
                for r in range(poly.numInteriorRings()):
                    intr = poly.interiorRing(r)
                    if ring_idx == r + 1:
                        new_poly.addInteriorRing(chosen_ring.clone())
                    elif intr:
                        new_poly.addInteriorRing(intr.clone())
                res = QgsGeometry(new_poly)
                if not res.isGeosValid():
                    res = res.makeValid()
                return res

        # Fallback to makeValid
        valid_res = geom.makeValid()
        return valid_res if valid_res and not valid_res.isEmpty() else geom

    @classmethod
    def clean_all_topology_errors(
        cls,
        geom: QgsGeometry,
        tolerance: float = 1e-6,
    ) -> Tuple[QgsGeometry, int]:
        """
        Cleans all duplicate nodes and resolves self-intersections in one shot.
        Returns a tuple of (cleaned_geometry, count_of_errors_resolved).
        """
        if not geom or geom.isEmpty() or geom.isNull():
            return geom, 0
        if cls.has_curved_segments(geom):
            return QgsGeometry(geom), 0

        dups = cls.find_duplicate_nodes(geom, tolerance)
        intersections = cls.find_self_intersections(geom)
        total_errors = len(dups) + len(intersections)

        if total_errors == 0:
            return geom, 0

        cleaned_geom = QgsGeometry(geom)
        if dups:
            cleaned_geom.removeDuplicateNodes(tolerance)

        if not cleaned_geom.isGeosValid() or intersections:
            cleaned_geom = cleaned_geom.makeValid()

        return cleaned_geom, total_errors

    @classmethod
    def extract_singlepart_geometries(
        cls,
        geom: QgsGeometry,
        target_type: Optional[QgsWkbTypes.GeometryType] = None,
    ) -> List[QgsGeometry]:
        """
        Extracts all individual single-part geometries from a multi-geometry or collection.
        Optionally filters by target_type (PolygonGeometry or LineGeometry).
        """
        parts: List[QgsGeometry] = []
        if not geom or geom.isEmpty() or geom.isNull():
            return parts

        if target_type is None:
            target_type = geom.type()

        if geom.isMultipart():
            for part in geom.asGeometryCollection():
                if part.type() == target_type and not part.isEmpty():
                    parts.append(part)
        elif geom.type() == target_type and not geom.isEmpty():
            parts.append(geom)
        return parts

    @classmethod
    def get_largest_singlepart_geometry(
        cls,
        geom: QgsGeometry,
        target_type: Optional[QgsWkbTypes.GeometryType] = None,
    ) -> QgsGeometry:
        """
        Returns the largest single-part geometry by area (for polygons) or length (for lines).
        """
        parts = cls.extract_singlepart_geometries(geom, target_type)
        if not parts:
            return geom

        if target_type == QgsWkbTypes.GeometryType.PolygonGeometry or (
            target_type is None and geom.type() == QgsWkbTypes.GeometryType.PolygonGeometry
        ):
            return max(parts, key=lambda p: p.area())
        else:
            return max(parts, key=lambda p: p.length())

    @classmethod
    def coerce_geometry_to_layer(
        cls,
        geom: QgsGeometry,
        layer: Optional[QgsVectorLayer],
    ) -> QgsGeometry:
        """
        Coerces geometry to be compatible with layer's WKB type (singlepart vs multipart).
        """
        if not geom or geom.isEmpty() or not layer:
            return geom

        is_multi_layer = QgsWkbTypes.isMultiType(layer.wkbType())
        if is_multi_layer:
            if not geom.isMultipart():
                res = QgsGeometry(geom)
                res.convertToMultiType()
                return res
            return geom
        else:
            if geom.isMultipart():
                return cls.get_largest_singlepart_geometry(geom, layer.geometryType())
            return geom

    @classmethod
    def can_explode_line(cls, geom: QgsGeometry, as_multipart: bool = False) -> bool:
        """
        Determines whether a line geometry can be exploded into multiple segments or parts.
        Returns False if the geometry is empty, or is already a single 2-point segment.
        """
        if not geom or geom.isEmpty():
            return False
        if cls.has_curved_segments(geom):
            return False

        abstract_geom = geom.constGet()
        if not abstract_geom:
            return False

        curves = []
        if isinstance(abstract_geom, (QgsMultiLineString,)):
            for i in range(abstract_geom.numGeometries()):
                g = abstract_geom.geometryN(i)
                if g:
                    curves.append(g)
        elif hasattr(abstract_geom, "numGeometries") and abstract_geom.numGeometries() > 0:
            for i in range(abstract_geom.numGeometries()):
                g = abstract_geom.geometryN(i)
                if isinstance(g, QgsLineString):
                    curves.append(g)
        else:
            curves.append(abstract_geom)

        total_segments = sum(max(0, curve.numPoints() - 1) for curve in curves if hasattr(curve, "numPoints"))
        if total_segments <= 1:
            return False

        if as_multipart:
            if isinstance(abstract_geom, (QgsMultiLineString,)) or (hasattr(abstract_geom, "numGeometries") and abstract_geom.numGeometries() > 1):
                has_multi_vertex_part = any(getattr(c, "numPoints", lambda: 0)() > 2 for c in curves)
                if not has_multi_vertex_part:
                    return False
            return True
        else:
            return True

    @classmethod
    def explode_line(cls, geom: QgsGeometry, as_multipart: bool = False) -> List[QgsGeometry]:
        """
        Splits a line, polyline, or MultiLineString into individual 2-point segments.
        If as_multipart is True, returns a single QgsGeometry containing all segments as a MultiLineString.
        If as_multipart is False, returns a list of individual 2-point QgsGeometry LineStrings.
        """
        if not geom or geom.isEmpty():
            return []
        if cls.has_curved_segments(geom):
            return []

        segments = []
        abstract_geom = geom.constGet()
        if not abstract_geom:
            return []

        curves = []
        if isinstance(abstract_geom, (QgsMultiLineString,)):
            for i in range(abstract_geom.numGeometries()):
                g = abstract_geom.geometryN(i)
                if g:
                    curves.append(g)
        elif hasattr(abstract_geom, "numGeometries") and abstract_geom.numGeometries() > 0:
            for i in range(abstract_geom.numGeometries()):
                g = abstract_geom.geometryN(i)
                if isinstance(g, QgsLineString):
                    curves.append(g)
        else:
            curves.append(abstract_geom)

        for curve in curves:
            num_pts = curve.numPoints() if hasattr(curve, "numPoints") else 0
            for i in range(num_pts - 1):
                p1 = curve.pointN(i)
                p2 = curve.pointN(i + 1)
                segments.append(QgsLineString([p1, p2]))

        if not segments:
            return [geom]

        if as_multipart:
            mls = QgsMultiLineString()
            for seg in segments:
                mls.addGeometry(seg)
            return [QgsGeometry(mls)]
        else:
            return [QgsGeometry(seg) for seg in segments]

    @classmethod
    def join_lines(cls, geometries: List[QgsGeometry], tolerance: float = 1e-6) -> List[QgsGeometry]:
        """
        Connects multiple line segments/polylines sharing coincident endpoints (within tolerance)
        into continuous polyline(s). Automatically reverses line orientation when needed and
        closes loops if start point equals end point.
        """
        if not geometries:
            return []

        all_polylines = []
        for geom in geometries:
            if not geom or geom.isEmpty():
                continue
            if cls.has_curved_segments(geom):
                return []
            abstract_geom = geom.constGet()
            if not abstract_geom:
                continue

            curves = []
            if isinstance(abstract_geom, (QgsMultiLineString,)):
                for i in range(abstract_geom.numGeometries()):
                    g = abstract_geom.geometryN(i)
                    if g:
                        curves.append(g)
            elif hasattr(abstract_geom, "numGeometries") and abstract_geom.numGeometries() > 0:
                for i in range(abstract_geom.numGeometries()):
                    g = abstract_geom.geometryN(i)
                    if g:
                        curves.append(g)
            else:
                curves.append(abstract_geom)

            for curve in curves:
                num_pts = curve.numPoints() if hasattr(curve, "numPoints") else 0
                if num_pts >= 2:
                    pts = [curve.pointN(i) for i in range(num_pts)]
                    all_polylines.append(pts)

        if not all_polylines:
            return []

        pool = [list(pts) for pts in all_polylines]
        joined_chains = []

        while pool:
            current = pool.pop(0)
            extended = True
            while extended:
                extended = False
                end_pt = current[-1]
                start_pt = current[0]

                # If already a closed loop, don't extend
                if len(current) > 2 and current[0].distance(current[-1]) <= tolerance:
                    break

                best_idx = None
                best_action = None

                for i, candidate in enumerate(pool):
                    c_start = candidate[0]
                    c_end = candidate[-1]

                    # 1. current[-1] == candidate[0] (End-to-Start)
                    if end_pt.distance(c_start) <= tolerance:
                        best_idx = i
                        best_action = "append_normal"
                        break
                    # 2. current[-1] == candidate[-1] (End-to-End)
                    elif end_pt.distance(c_end) <= tolerance:
                        best_idx = i
                        best_action = "append_reversed"
                        break
                    # 3. current[0] == candidate[-1] (Start-to-End)
                    elif start_pt.distance(c_end) <= tolerance:
                        best_idx = i
                        best_action = "prepend_normal"
                        break
                    # 4. current[0] == candidate[0] (Start-to-Start)
                    elif start_pt.distance(c_start) <= tolerance:
                        best_idx = i
                        best_action = "prepend_reversed"
                        break

                if best_idx is not None:
                    cand = pool.pop(best_idx)
                    if best_action == "append_normal":
                        current.extend(cand[1:])
                    elif best_action == "append_reversed":
                        cand_rev = list(reversed(cand))
                        current.extend(cand_rev[1:])
                    elif best_action == "prepend_normal":
                        current = cand[:-1] + current
                    elif best_action == "prepend_reversed":
                        cand_rev = list(reversed(cand))
                        current = cand_rev[:-1] + current
                    extended = True

            # If closed ring within tolerance, snap exact endpoint closure
            if len(current) > 2 and current[0].distance(current[-1]) <= tolerance:
                current[-1] = cls._copy_point(current[0])

            joined_chains.append(current)

        return [QgsGeometry(QgsLineString(pts)) for pts in joined_chains if len(pts) >= 2]

    # Alias for backwards compatibility
    batch_process_geometry = batch_apply_geometry


