import math
import re


def parse_fractional_value(text: str):
    # Match fractional patterns, allowing optional whole number prefix.
    # Exclude strict word boundary check to avoid DXF formatting string issues (e.g. \S1/2;).
    match = re.search(r"(?:(\d+)[- ])?(\d+)/(\d+)", text)
    if match:
        whole_str, num_str, den_str = match.groups()
        whole = float(whole_str) if whole_str else 0.0
        num = float(num_str)
        den = float(den_str)
        if den != 0.0:
            return whole + num / den
    return None


class GeometryNormalizer:
    """
    Converts raw DXF entities into canonical geometry dictionaries.
    """

    @staticmethod
    def normalize(entity):
        entity_type = entity.dxftype()

        if entity_type == "LINE":
            return GeometryNormalizer._normalize_line(entity)

        elif entity_type == "CIRCLE":
            return GeometryNormalizer._normalize_circle(entity)

        elif entity_type == "ARC":
            return GeometryNormalizer._normalize_arc(entity)

        elif entity_type == "LWPOLYLINE":
            return GeometryNormalizer._normalize_lwpolyline(entity)

        elif entity_type == "POLYLINE":
            return GeometryNormalizer._normalize_polyline(entity)

        elif entity_type == "DIMENSION":
            return GeometryNormalizer._normalize_dimension(entity)

        elif entity_type in ("TEXT", "MTEXT"):
            return GeometryNormalizer._normalize_text(entity)

        else:
            return {
                "type": entity_type,
                "geometry": None,
                "supported": False
            }

    # ---------------------------------------------------------
    # LINE
    # ---------------------------------------------------------

    @staticmethod
    def _normalize_line(entity):
        start = entity.dxf.start
        end = entity.dxf.end

        return {
            "type": "LINE",
            "geometry": {
                "start": [float(start.x), float(start.y)],
                "end": [float(end.x), float(end.y)],
                "length": GeometryNormalizer._distance(start, end)
            },
            "supported": True
        }

    # ---------------------------------------------------------
    # CIRCLE
    # ---------------------------------------------------------

    @staticmethod
    def _normalize_circle(entity):
        center = entity.dxf.center
        radius = float(entity.dxf.radius)

        return {
            "type": "CIRCLE",
            "geometry": {
                "center": [float(center.x), float(center.y)],
                "radius": radius,
                "diameter": radius * 2.0,
                "area": math.pi * radius * radius
            },
            "supported": True
        }

    # ---------------------------------------------------------
    # ARC
    # ---------------------------------------------------------

    @staticmethod
    def _normalize_arc(entity):
        center = entity.dxf.center

        return {
            "type": "ARC",
            "geometry": {
                "center": [float(center.x), float(center.y)],
                "radius": float(entity.dxf.radius),
                "start_angle": float(entity.dxf.start_angle),
                "end_angle": float(entity.dxf.end_angle)
            },
            "supported": True
        }

    # ---------------------------------------------------------
    # LWPOLYLINE
    # ---------------------------------------------------------

    @staticmethod
    def _normalize_lwpolyline(entity):
        points = []
        bulge_data = []
        has_arcs = False

        for point in entity.get_points():
            x, y = point[0], point[1]
            points.append([float(x), float(y)])
            # LWPOLYLINE point format: (x, y, start_width, end_width, bulge)
            bulge = point[4] if len(point) > 4 else 0.0
            if abs(bulge) > 1e-6:
                has_arcs = True
                bulge_data.append({
                    "index": len(points) - 1,
                    "bulge": round(float(bulge), 6),
                    "direction": "ccw" if bulge > 0 else "cw",
                })

        geometry = {
            "points": points,
            "closed": bool(entity.closed),
        }

        if has_arcs:
            geometry["has_arcs"] = True
            geometry["arc_segments"] = bulge_data
            geometry["arc_count"] = len(bulge_data)
        else:
            geometry["has_arcs"] = False

        return {
            "type": "LWPOLYLINE",
            "geometry": geometry,
            "supported": True
        }

    # ---------------------------------------------------------
    # POLYLINE
    # ---------------------------------------------------------

    @staticmethod
    def _normalize_polyline(entity):
        points = []
        bulge_data = []
        has_arcs = False

        for vertex in entity.vertices:
            location = vertex.dxf.location
            points.append([
                float(location.x),
                float(location.y)
            ])
            # Preserve bulge value (DXF group code 42)
            bulge = getattr(vertex.dxf, "bulge", 0.0)
            if abs(bulge) > 1e-6:
                has_arcs = True
                bulge_data.append({
                    "index": len(points) - 1,
                    "bulge": round(float(bulge), 6),
                    "direction": "ccw" if bulge > 0 else "cw",
                })

        geometry = {
            "points": points,
            "closed": bool(entity.is_closed),
        }

        # Additive arc metadata (does not replace geometry)
        if has_arcs:
            geometry["has_arcs"] = True
            geometry["arc_segments"] = bulge_data
            geometry["arc_count"] = len(bulge_data)
        else:
            geometry["has_arcs"] = False

        return {
            "type": "POLYLINE",
            "geometry": geometry,
            "supported": True
        }

    # ---------------------------------------------------------
    # DIMENSION (supervision entity)
    # ---------------------------------------------------------

    @staticmethod
    def _normalize_dimension(entity):
        """
        Normalize DIMENSION entity into canonical supervision structure.
        Preserves: numeric value, position, target points, dimension type.
        """
        import re

        raw_text = str(getattr(entity.dxf, "text", ""))
        defpoint = entity.dxf.defpoint

        # Extract numeric value
        numeric_value = None
        try:
            numeric_value = parse_fractional_value(raw_text)
        except Exception:
            pass

        if numeric_value is None:
            try:
                actual = getattr(entity.dxf, "actual_measurement", None)
                if actual and actual > 0:
                    numeric_value = round(float(actual), 4)
            except Exception:
                pass

        if numeric_value is None:
            # Parse from text
            cleaned_t = re.sub(r"^\s*\d+\s*[Xx]\s+", "", raw_text)
            cleaned = re.sub(r'[^\d.\-]', ' ', cleaned_t).strip()
            parts = cleaned.split()
            for part in parts:
                try:
                    numeric_value = round(float(part.rstrip('-')), 4)
                    break
                except ValueError:
                    continue

        # Collect target points (defpoints)
        target_points = []
        for attr in ("defpoint2", "defpoint3", "defpoint4", "defpoint5"):
            if hasattr(entity.dxf, attr):
                p = getattr(entity.dxf, attr)
                target_points.append([float(p.x), float(p.y)])

        # Determine dimension type
        dim_type_code = getattr(entity.dxf, "dimtype", 0) & 7
        dim_type_map = {
            0: "linear", 1: "aligned", 2: "angular",
            3: "diameter", 4: "radius", 5: "angular_3point", 6: "ordinate",
        }
        dim_type = dim_type_map.get(dim_type_code, "linear")

        # Override from text symbols
        if "Ø" in raw_text or "ø" in raw_text:
            dim_type = "diameter"
        elif raw_text.strip().startswith("R") and any(c.isdigit() for c in raw_text):
            dim_type = "radius"
        elif "°" in raw_text:
            dim_type = "angular"

        return {
            "type": "DIMENSION",
            "geometry": {
                "dimension_type": dim_type,
                "value": numeric_value,
                "text": raw_text,
                "position": [float(defpoint.x), float(defpoint.y)],
                "target_points": target_points,
            },
            "supported": True,
        }

    # ---------------------------------------------------------
    # TEXT / MTEXT (supervision entity)
    # ---------------------------------------------------------

    @staticmethod
    def _normalize_text(entity):
        """
        Normalize TEXT/MTEXT entity into canonical supervision structure.
        Preserves: text content, position, semantic role detection.
        """
        import re

        entity_type = entity.dxftype()

        if entity_type == "MTEXT":
            text_content = entity.plain_text()
        else:
            text_content = str(getattr(entity.dxf, "text", ""))

        insert = entity.dxf.insert
        height = getattr(entity.dxf, "height", None)

        # Detect if this text contains a dimension value
        t = text_content.strip()
        has_numeric = bool(re.search(r'\d', t))

        # Classify text role
        if t.startswith("M") and any(c.isdigit() for c in t[:4]):
            text_role = "thread_callout"
        elif "±" in t:
            text_role = "tolerance"
        elif t.startswith("R") and has_numeric:
            text_role = "radius_value"
        elif "Ø" in t or "ø" in t:
            text_role = "diameter_value"
        elif "°" in t:
            text_role = "angle_value"
        elif has_numeric:
            text_role = "dimension_value"
        else:
            text_role = "annotation"

        # Extract numeric value if present
        numeric_value = None
        if has_numeric:
            try:
                numeric_value = parse_fractional_value(t)
            except Exception:
                pass
            if numeric_value is None:
                cleaned_t = re.sub(r"^\s*\d+\s*[Xx]\s+", "", t)
                cleaned = re.sub(r'[^\d.\-]', ' ', cleaned_t).strip()
                parts = cleaned.split()
                for part in parts:
                    try:
                        numeric_value = round(float(part.rstrip('-')), 4)
                        break
                    except ValueError:
                        continue

        return {
            "type": entity_type,
            "geometry": {
                "text": text_content,
                "position": [float(insert.x), float(insert.y)],
                "height": float(height) if height else None,
                "text_role": text_role,
                "numeric_value": numeric_value,
            },
            "supported": True,
        }

    # ---------------------------------------------------------
    # HELPERS
    # ---------------------------------------------------------

    @staticmethod
    def _distance(p1, p2):
        return math.sqrt(
            (p2.x - p1.x) ** 2 +
            (p2.y - p1.y) ** 2
        )