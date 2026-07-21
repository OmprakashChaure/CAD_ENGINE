"""
Semantic Pipeline — features → enriched entity-centric output.

This file consolidates the schema, mapping functions, and builder logic 
previously spread across core/exporters/ into a single cohesive pipeline step.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from utils.logger import get_logger
from core.semantics.annotation_parser import AnnotationParser

logger = get_logger(__name__)


# =====================================================================
# 1. SEMANTIC SCHEMAS
# =====================================================================

class FeatureClass(Enum):
    """Generic feature classes for PRV drawings."""
    HOLE_PATTERN = "hole_pattern"
    HOLE_GROUP = "hole_group"
    CONCENTRIC_BORE = "concentric_bore"
    SLOT_ARRAY = "slot_array"
    SLOT_GROUP = "slot_group"
    FILLET_GROUP = "fillet_group"
    CHAMFER_GROUP = "chamfer_group"
    OUTER_PROFILE = "outer_profile"
    RADIAL_PATTERN = "radial_pattern"
    LINEAR_PATTERN = "linear_pattern"
    MIRROR_PATTERN = "mirror_pattern"


class RelationshipType(Enum):
    """Generic relationship types for PRV drawings."""
    CONCENTRIC = "concentric"
    COAXIAL = "coaxial"
    PARALLEL = "parallel"
    PERPENDICULAR = "perpendicular"
    MIRROR_SYMMETRY = "mirror_symmetry"
    ROTATIONAL_SYMMETRY = "rotational_symmetry"
    NESTED_WITHIN = "nested_within"
    SURROUNDS = "surrounds"
    CONTAINS = "contains"


@dataclass
class FeatureInstance:
    """Generic feature instance with extensible parameters."""
    feature_id: str
    feature_class: str
    parameters: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "feature_class": self.feature_class,
            "parameters": self.parameters
        }


@dataclass
class Relationship:
    """Generic relationship with extensible parameters."""
    relationship_id: str
    relationship_type: str
    feature_ids: List[str]
    parameters: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "relationship_id": self.relationship_id,
            "relationship_type": self.relationship_type,
            "feature_ids": self.feature_ids,
            "parameters": self.parameters
        }


@dataclass
class SemanticRecord:
    """Complete semantic representation of a PRV drawing."""
    drawing_id: str
    part_type: str
    overall_dimensions: Dict[str, float]
    features: List[FeatureInstance] = field(default_factory=list)
    relationships: List[Relationship] = field(default_factory=list)
    hierarchy: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "drawing_id": self.drawing_id,
            "part_type": self.part_type,
            "overall_dimensions": self.overall_dimensions,
            "features": [f.to_dict() for f in self.features],
            "relationships": [r.to_dict() for r in self.relationships]
        }
        if self.hierarchy is not None:
            result["hierarchy"] = self.hierarchy
        if self.metadata is not None:
            result["metadata"] = self.metadata
        return result


# =====================================================================
# 2. SEMANTIC MAPPERS AND VALUATION LOGIC
# =====================================================================

DIMENSION_EXCLUDE_WORDS = (
    "DATUM", "CENTER HGT", "CENTER LOC", "MOUNT LOC", "BORE LOC",
    "COVER LOC", "CRS", "SPACING", "SPLIT", "OFFSET", "THK", "THICK",
    "LUG", "FLANGE Y", "PATTERN", "PCD", "BOSS", "BORE", "CBORE",
    "PORT", "BASE THK", "GUSSET", "CORE", "SECTION", "WIRE", "BARB",
    "GROOVE",
)

SYNONYMS = {
    "THREAD": ["THREAD", "NPT", "BSP", "BSPT", "UNC", "UNF", "UNEF", "TAPPED", "TAP", "M-SERIES", "THD", "THREADED"],
    "WEB_THICKNESS": ["WEB THK", "WEB THICKNESS", "WEB THICK", "WEAKENED WEB"],
    "FLANGE_THICKNESS": ["FLANGE THK", "FLANGE THICKNESS"],
    "ACROSS_FLATS": ["AF", "A/F", "ACROSS FLATS", "WIDTH ACROSS FLATS"],
    "BEND_RELIEF": ["RELIEF", "BEND RELIEF", "CORNER RELIEF", "HINGE RELIEF"]
}


def _match_keyword(text: str, keyword: str) -> bool:
    if not text or not keyword:
        return False
    escaped = re.escape(keyword.upper())
    pattern = r'(?:^|[^A-Z0-9])' + escaped + r'(?:$|[^A-Z0-9])'
    return bool(re.search(pattern, text.upper()))


class EngineeringConcept:
    def __init__(self, name: str, synonyms: List[str], geometry_classes: List[str] = None, exclude_words: List[str] = None):
        self.name = name
        self.synonyms = synonyms
        self.geometry_classes = geometry_classes or []
        self.exclude_words = exclude_words or []

    def matches_text(self, text: str) -> bool:
        text_upper = text.upper()
        if any(_match_keyword(text_upper, ex) for ex in self.exclude_words):
            return False
        return any(_match_keyword(text_upper, syn) for syn in self.synonyms)

    def calculate_confidence(self, text: str, detected_geom_classes: List[str]) -> float:
        score = 0.0
        if self.matches_text(text):
            score += 2.0
        for gc in self.geometry_classes:
            if gc in detected_geom_classes:
                score += 1.5
        return score


CONCEPT_REGISTRY = {
    "THREAD": EngineeringConcept(
        name="thread",
        synonyms=SYNONYMS["THREAD"],
        geometry_classes=["thread"],
        exclude_words=["PITCH CIRCLE", "PCD", "BORE PITCH", "HOLE PITCH"]
    ),
    "BORE": EngineeringConcept(
        name="bore",
        synonyms=["BORE", "THRU BORE", "THROUGH BORE", "PRECISION BORE", "ALIGNMENT BORE", "COMBUSTION BORE"],
        geometry_classes=["concentric_bore"]
    ),
    "HOLE": EngineeringConcept(
        name="hole",
        synonyms=["HOLE", "CLEARANCE HOLE", "MOUNTING HOLE", "BOLT HOLE", "PLUG WELD BORE"],
        geometry_classes=["hole_group", "hole_pattern"]
    ),
    "POCKET": EngineeringConcept(
        name="pocket",
        synonyms=["POCKET", "MILLED POCKET", "RECESS", "OPENING", "TOP OPENING"],
        geometry_classes=["pocket"]
    ),
    "RIB": EngineeringConcept(
        name="rib",
        synonyms=["RIB", "RIBS", "CRUSH RIBS", "STIFFENER"],
        geometry_classes=["rib"]
    ),
    "PORT": EngineeringConcept(
        name="port",
        synonyms=["PORT", "INLET", "OUTLET", "LUBE PORT", "INLET PORT"],
        geometry_classes=["port"]
    ),
    "CHANNEL": EngineeringConcept(
        name="channel",
        synonyms=["CHANNEL", "FLOW CHANNEL", "COOLING CHANNEL", "SERPENTINE CHANNEL"],
        geometry_classes=["channel"]
    ),
    "SHOULDER": EngineeringConcept(
        name="shoulder",
        synonyms=["SHOULDER", "STEP LENGTH", "SHOULDER LEN"],
        geometry_classes=["shoulder"]
    ),
    "COPE": EngineeringConcept(
        name="cope",
        synonyms=["COPE", "FISHMOUTH", "TUBE COPE", "SADDLE"],
        geometry_classes=["cope"]
    ),
    "CHAMFER": EngineeringConcept(
        name="chamfer",
        synonyms=["CHAMFER", "BEVEL"],
        geometry_classes=["chamfer"]
    ),
    "RELIEF": EngineeringConcept(
        name="relief",
        synonyms=SYNONYMS["BEND_RELIEF"],
        geometry_classes=["bend_relief"]
    ),
    "FIN": EngineeringConcept(
        name="fin",
        synonyms=["FIN", "FINS", "COOLING FIN", "RADIAL FIN", "EXTRUDED FIN"],
        geometry_classes=["heatsink_fin"]
    ),
    "FLANGE": EngineeringConcept(
        name="flange",
        synonyms=["FLANGE", "FLANGE OD", "FLANGE THK", "FLANGE THICKNESS", "FLANGE WIDTH"],
        geometry_classes=["fitting", "structural_profile"]
    ),
    "WEB": EngineeringConcept(
        name="web",
        synonyms=SYNONYMS["WEB_THICKNESS"],
        geometry_classes=["structural_profile"]
    ),
    "O_RING": EngineeringConcept(
        name="o_ring",
        synonyms=["O-RING", "ORING", "SEAL GROOVE", "ELASTOMER O-RING"],
        geometry_classes=["o_ring"]
    )
}


def _clean_text(text: Optional[str]) -> str:
    if not text:
        return ""
    return text.replace("%%C", "Ø").replace("\\P", " ").replace("\\", " ").upper()


def parse_fractional_value(text: str) -> Optional[float]:
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


def strip_count_prefix(text: str) -> str:
    cleaned = re.sub(r"^\s*\d+\s*[Xx]\s+", "", text)
    return cleaned


def _first_number(text: str) -> Optional[float]:
    cleaned = strip_count_prefix(text)
    try:
        val = parse_fractional_value(cleaned)
        if val is not None:
            return val
    except Exception:
        pass
    match = re.search(r"(\d+(?:\.\d+)?)", cleaned)
    return float(match.group(1)) if match else None


def _numbers(text: str) -> List[float]:
    cleaned = strip_count_prefix(text)
    return [float(v) for v in re.findall(r"\d+(?:\.\d+)?", cleaned)]


def _orientation(target_points: List[List[float]]) -> Optional[str]:
    if not target_points or len(target_points) < 2:
        return None
    p1, p2 = target_points[0], target_points[1]
    if not p1 or not p2 or len(p1) < 2 or len(p2) < 2:
        return None
    if math.dist(p1, p2) < 0.001:
        return None
    dx = abs(p2[0] - p1[0])
    dy = abs(p2[1] - p1[1])
    if dx >= dy:
        return "horizontal"
    return "vertical"


def _center_from_points(target_points: List[List[float]]) -> Optional[List[float]]:
    if not target_points or len(target_points) < 2:
        return None
    p1, p2 = target_points[0], target_points[1]
    if not p1 or not p2 or len(p1) < 2 or len(p2) < 2:
        return None
    if math.dist(p1, p2) < 0.001:
        return None
    return [round((p1[0] + p2[0]) / 2, 4), round((p1[1] + p2[1]) / 2, 4)]


def _span_from_points(target_points: List[List[float]]) -> Optional[float]:
    if not target_points or len(target_points) < 2:
        return None
    p1, p2 = target_points[0], target_points[1]
    if not p1 or not p2 or len(p1) < 2 or len(p2) < 2:
        return None
    dist = math.dist(p1, p2)
    if dist < 0.001:
        return None
    return round(dist, 4)


def _physical_bbox(phase1_entities: List[Dict[str, Any]]) -> Dict[str, float]:
    exclude_layers = {"CENTERLINES", "CONSTRUCTION", "DATUM", "REFERENCE", "DIMENSIONS"}
    xs: List[float] = []
    ys: List[float] = []

    for ent in phase1_entities:
        if (ent.get("layer") or "").upper() in exclude_layers:
            continue
        geom = ent.get("geometry", {})
        entity_type = ent.get("entity_type")
        if entity_type == "LINE":
            for p in (geom.get("start"), geom.get("end")):
                if p and len(p) >= 2:
                    xs.append(p[0])
                    ys.append(p[1])
        elif entity_type == "LWPOLYLINE":
            for p in geom.get("points", []):
                if p and len(p) >= 2:
                    xs.append(p[0])
                    ys.append(p[1])
        elif entity_type in ("CIRCLE", "ARC"):
            center = geom.get("center")
            radius = geom.get("radius", 0)
            if center and len(center) >= 2 and radius:
                xs.extend([center[0] - radius, center[0] + radius])
                ys.extend([center[1] - radius, center[1] + radius])

    if not xs or not ys:
        return {}
    return {
        "width": round(max(xs) - min(xs), 4),
        "height": round(max(ys) - min(ys), 4),
    }


def resolve_engineering_value(text: str, span: Optional[float], value: Optional[float] = None, concept: Optional[str] = None) -> Optional[float]:
    cleaned_text = _clean_text(text)
    text_val = value if isinstance(value, (int, float)) else _first_number(text)
    
    if span is None or span <= 0.001:
        return text_val
        
    all_nums = _numbers(text)
    
    # 1. PCD / Spacing / CRS / Pitch concepts (Geometry-Authoritative)
    if concept in ("pcd", "spacing", "crs", "pitch") or any(word in cleaned_text for word in ("SPACING", "CRS", "PITCH", "PCD", "PITCH CIRCLE", "CENTER DISTANCE")):
        for num in all_nums:
            if abs(num - span) < 0.05:
                return num
        if "PITCH" in cleaned_text:
            for num in all_nums:
                for k in (2, 3, 4, 5):
                    if abs(num - span / k) < 0.05:
                        return num
        return span
        
    # 2. Boss Diameter concept (Radius-to-Diameter Translation)
    if concept == "boss_diameter" or "BOSS" in cleaned_text:
        if text.strip().startswith("R") or any(word in cleaned_text for word in ("RAD", "RADIUS")):
            for num in all_nums:
                if abs(num * 2.0 - span) < 0.1:
                    return num * 2.0
                if abs(num - span) < 0.1:
                    return num
            if text_val is not None:
                return text_val * 2.0
        return span
        
    # 3. ID / OD centerline concept
    if any(sym in cleaned_text for sym in ("Ø", "%%C", "ID", "OD", "DIA", "DIAMETER")):
        for num in all_nums:
            if abs(num - span * 2.0) < 0.1:
                return num
            if abs(num - span) < 0.1:
                return num
                
    # 4. Taper / Chamfer / Chord / flats concepts (Text-Nominal Authoritative)
    if concept in ("taper_length", "chamfer", "chord", "across_flats") or any(word in cleaned_text for word in ("TAPER", "CHAMFER", "BEVEL", "ROOT CORD", "TIP CORD", "ACROSS FLATS")):
        if text_val is not None:
            return text_val
            
    return span


def extract_dimension_facts(phase1_entities: List[Dict[str, Any]]) -> Dict[str, Any]:
    parser = AnnotationParser()
    facts: Dict[str, Any] = {
        "overall_dimensions": {},
        "bores": [],
        "boss_diameters": [],
        "base_diameters": [],
        "flange_diameters": [],
        "hole_callouts": [],
        "pcd": None,
        "counterbore": None,
        "lube_ports": [],
        "linear_dimensions": [],
        "pattern_dimensions": [],
    }

    for ent in phase1_entities:
        if ent.get("entity_type") not in ("DIMENSION", "TEXT", "MTEXT"):
            continue
        geom = ent.get("geometry", {})
        text = _clean_text(geom.get("text"))
        if not text:
            continue
        value = geom.get("value") or geom.get("numeric_value")
        nums = _numbers(text)
        target_points = geom.get("target_points", [])
        orient = _orientation(target_points)
        span = _span_from_points(target_points)
        center = _center_from_points(target_points)
        dim = {
            "text": text,
            "value": value,
            "numbers": nums,
            "orientation": orient,
            "span": span,
            "center": center,
            "handle": ent.get("handle"),
        }

        if any(_match_keyword(text, word) for word in ("OVERALL", "SQ", "SQUARE", "DEVELOPED LENGTH", "BLANK WIDTH", "MAJOR DIA", "FLANGE OD", "CASTING W", "CASTING H", "OUTER DIA", "OD", "DIA", "DIAMETER")) or re.search(r"\b\d+(?:\.\d+)?MM\s+[WH]\b", text):
            if not any(_match_keyword(text, word) for word in DIMENSION_EXCLUDE_WORDS if word not in {"BASE"}):
                dimension_value = value if isinstance(value, (int, float)) else _first_number(text)
                if dimension_value:
                    if _match_keyword(text, "SQ") or _match_keyword(text, "SQUARE"):
                        facts["overall_dimensions"]["width"] = round(float(dimension_value), 4)
                        facts["overall_dimensions"]["height"] = round(float(dimension_value), 4)
                    elif "DEVELOPED LENGTH" in text:
                        facts["overall_dimensions"]["width"] = round(float(dimension_value), 4)
                    elif "BLANK WIDTH" in text:
                        facts["overall_dimensions"]["height"] = round(float(dimension_value), 4)
                    elif "CASTING W" in text:
                        facts["overall_dimensions"]["width"] = round(float(dimension_value), 4)
                    elif "CASTING H" in text:
                        facts["overall_dimensions"]["height"] = round(float(dimension_value), 4)
                    elif orient == "horizontal":
                        facts["overall_dimensions"]["width"] = round(float(dimension_value), 4)
                    elif orient == "vertical":
                        facts["overall_dimensions"]["height"] = round(float(dimension_value), 4)
                    elif "OVERALL W" in text or "OVERALL WIDTH" in text:
                        facts["overall_dimensions"]["width"] = round(float(dimension_value), 4)
                    elif "OVERALL H" in text or "OVERALL HEIGHT" in text:
                        facts["overall_dimensions"]["height"] = round(float(dimension_value), 4)
                    elif " W" in text or "WIDTH" in text or "BASE" in text:
                        facts["overall_dimensions"]["width"] = round(float(dimension_value), 4)
                    elif " H" in text or "HEIGHT" in text:
                        facts["overall_dimensions"]["height"] = round(float(dimension_value), 4)

        parsed_ann = parser.parse(text)

        if "PCD" in text or "PITCH CIRCLE" in text:
            if not any(kw in text for kw in ("THRU", "HOLES", "BOLTS", "DRILLED", "TAP", "TAPPED", "X Ø")):
                pcd_nums = [n for n in nums if n not in (4.0, 6.0, 8.0, 10.0, 12.0, 16.0)]
                pcd_value = parsed_ann.nominal_diameter or (max(pcd_nums) if pcd_nums else (value if isinstance(value, (int, float)) else None))
                if pcd_value:
                    facts["pcd"] = round(float(pcd_value), 4)

        if "BORE" in text and "CBORE" not in text and "PCBORE" not in text and "PORT" not in text:
            if "BOSS" not in text and "COVER BOLTS" not in text:
                bore_value = parsed_ann.nominal_diameter or (value if isinstance(value, (int, float)) and value > 10 else _first_number(text))
                if bore_value:
                    facts["bores"].append({
                        "diameter": round(float(bore_value), 4),
                        "center": center,
                        "text": text,
                    })

        if "BOSS" in text:
            boss_value = parsed_ann.nominal_diameter or (value if isinstance(value, (int, float)) else _first_number(text))
            if boss_value:
                if text.strip().startswith("R"):
                    boss_value *= 2
                facts["boss_diameters"].append(round(float(boss_value), 4))

        if "BASE" in text and "OVERALL" not in text and "THK" not in text:
            base_value = parsed_ann.nominal_diameter or (value if isinstance(value, (int, float)) else _first_number(text))
            if base_value:
                facts["base_diameters"].append(round(float(base_value), 4))

        if "FLANGE" in text and "FLANGE Y" not in text:
            flange_value = parsed_ann.nominal_diameter or (value if isinstance(value, (int, float)) else _first_number(text))
            if flange_value:
                facts["flange_diameters"].append(round(float(flange_value), 4))

        if parsed_ann.annotation_type == "counterbore":
            facts["counterbore"] = {
                "counterbore_diameter": round(parsed_ann.counterbore_diameter, 4),
                "counterbore_depth": round(parsed_ann.counterbore_depth, 4) if parsed_ann.counterbore_depth else None,
            }
        elif "CBORE" in text or "PCBORE" in text:
            cbore_diameter = None
            depth = None
            m = re.search(r"(?:PCBORE|CBORE)\s+Ø?(\d+(?:\.\d+)?)MM", text)
            if m:
                cbore_diameter = float(m.group(1))
            m = re.search(r"X\s*(\d+(?:\.\d+)?)MM\s+DEEP", text)
            if m:
                depth = float(m.group(1))
            if cbore_diameter:
                facts["counterbore"] = {
                    "counterbore_diameter": round(cbore_diameter, 4),
                    "counterbore_depth": round(depth, 4) if depth else None,
                }

        if "LUBE PORT" in text:
            port_value = parsed_ann.nominal_diameter or (value if isinstance(value, (int, float)) else _first_number(text))
            if port_value:
                facts["lube_ports"].append({
                    "diameter": round(float(port_value), 4),
                    "center": center,
                    "text": text,
                })

        count_match = re.search(r"(\d+)X\s+Ø?(\d+(?:\.\d+)?)MM", text)
        if parsed_ann.annotation_type == "thread" and parsed_ann.quantity and any(word in text for word in ("THRU", "BOLT", "BORE", "HOLE", "CLEARANCE", "TAP")):
            facts["hole_callouts"].append({
                "count": parsed_ann.quantity,
                "diameter": round(float(parsed_ann.nominal_diameter), 4),
                "text": text,
                "counterbore": facts["counterbore"],
            })
        elif count_match and any(word in text for word in ("THRU", "BOLT", "BORE", "HOLE", "CLEARANCE")):
            facts["hole_callouts"].append({
                "count": int(count_match.group(1)),
                "diameter": round(float(count_match.group(2)), 4),
                "text": text,
                "counterbore": facts["counterbore"],
            })

        if any(word in text for word in ("SPACING", "CRS", "PATTERN", "MOUNT X", "MOUNT Y", "CTR TO CTR", "CTR-TO-CTR", "CENTER DISTANCE", "PITCH")):
            dim_value = resolve_engineering_value(text, span, value, concept="spacing")
            if dim_value:
                facts["pattern_dimensions"].append({
                    **dim,
                    "value": round(float(dim_value), 4),
                })

        is_dimension_type = ent.get("entity_type") == "DIMENSION"
        if is_dimension_type or any(word in text for word in (
            "DATUM", "FLANGE", "CENTER HGT", "CENTER LOC", "EDGE OFFSET", "BASE", "BASE THK", "RIB THK", "LUG W", "SPLIT", "BORE LOC", "COVER LOC", "COVER", "MOUNT LOC", "WEB", "WIDTH", "HEIGHT", "THK", "THICK", "AF", "FLATS", "DRIVE", "TAPER", "NECK", "WALL", "RAD", "RADIUS", "CHAMFER", "VAL", "VALUE", "DEPTH", "DEEP", "OPENING", "CHANNEL", "PORT", "PROFILE", "COPE", "SHOULDER", "THD", "THREAD", "THREADED", "O-RING", "ORING", "SEAL",
            "DIA", "DIAMETER", "Ø", "%%C", "MAX", "MIN", "HEAD", "ANGLE", "DEG", "SPAN", "MOUNT", "FACE", "LIFT", "CROWN", "LEG", "STEP", "MAJOR", "MINOR", "SPLINE", "GENEVA", "WINDOW", "BARB", "SECTION", "MESH", "GAP", "AMPLITUDE", "CORD", "R", "UNDERCUT", "SPIRAL", "CHEVRON", "GRAPHITE", "FLANK", "PRESSURE"
        )):
            dim_value = resolve_engineering_value(text, span, value, concept="linear")
            if dim_value:
                facts["linear_dimensions"].append({
                    **dim,
                    "value": round(float(dim_value), 4),
                })

    return facts


def reconstruct_dimensions(phase1_entities: List[Dict[str, Any]]) -> Dict[str, float]:
    facts = extract_dimension_facts(phase1_entities)
    bbox = _physical_bbox(phase1_entities)
    dims = dict(bbox)
    dims.update({k: v for k, v in facts.get("overall_dimensions", {}).items() if v})
    if not dims:
        logger.warning("Cannot reconstruct dimensions: no valid entities found")
        return {}
    return dims


def _infer_center_from_positions(positions: List[List[float]]) -> Optional[List[float]]:
    valid = [p for p in positions if p and len(p) >= 2]
    if not valid:
        return None
    return [
        round((min(p[0] for p in valid) + max(p[0] for p in valid)) / 2, 4),
        round((min(p[1] for p in valid) + max(p[1] for p in valid)) / 2, 4),
    ]


def _get_entity_bbox(entity):
    etype = entity.get("entity_type")
    geom = entity.get("geometry", {})
    if etype == "LINE":
        start = geom.get("start")
        end = geom.get("end")
        if start and end:
            return (min(start[0], end[0]), max(start[0], end[0]), min(start[1], end[1]), max(start[1], end[1]))
    elif etype == "CIRCLE":
        center = geom.get("center")
        radius = geom.get("radius")
        if center and radius is not None:
            return (center[0] - radius, center[0] + radius, center[1] - radius, center[1] + radius)
    elif etype == "ARC":
        center = geom.get("center")
        radius = geom.get("radius")
        start_angle = geom.get("start_angle")
        end_angle = geom.get("end_angle")
        if center and radius is not None and start_angle is not None and end_angle is not None:
            xs = []
            ys = []
            for angle_deg in (start_angle, end_angle):
                rad = math.radians(angle_deg)
                xs.append(center[0] + radius * math.cos(rad))
                ys.append(center[1] + radius * math.sin(rad))
            sa = start_angle % 360
            ea = end_angle % 360
            if ea < sa:
                ea += 360
            for q_deg in (0, 90, 180, 270, 360):
                if sa <= q_deg <= ea:
                    rad = math.radians(q_deg)
                    xs.append(center[0] + radius * math.cos(rad))
                    ys.append(center[1] + radius * math.sin(rad))
            if xs and ys:
                return (min(xs), max(xs), min(ys), max(ys))
    elif etype in ("POLYLINE", "LWPOLYLINE"):
        points = geom.get("points", [])
        if points:
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            return (min(xs), max(xs), min(ys), max(ys))
    return None


def is_entity_mapped(ent, structured_features, matched_handles):
    if ent.get("handle") in matched_handles:
        return True
    geom = ent.get("geometry", {})
    text = _clean_text(geom.get("text"))
    if not text or len(text) >= 50:
        return False
    
    # Extract all numbers from text
    nums = _numbers(text)
    val = geom.get("value") or geom.get("numeric_value")
    ent_nums = set(nums)
    if isinstance(val, (int, float)):
        ent_nums.add(round(val, 4))
        
    for feat in structured_features:
        if feat.feature_class in ("dimension_annotations", "unknown_facts"):
            continue
        for k, v in feat.parameters.items():
            if isinstance(v, (int, float)):
                if any(abs(v - num) < 0.05 for num in ent_nums):
                    return True
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, (int, float)) and any(abs(item - num) < 0.05 for num in ent_nums):
                        return True
                    elif isinstance(item, dict):
                        for val_in_dict in item.values():
                            if isinstance(val_in_dict, (int, float)) and any(abs(val_in_dict - num) < 0.05 for num in ent_nums):
                                return True
            elif isinstance(v, dict):
                for val_in_dict in v.values():
                    if isinstance(val_in_dict, (int, float)) and any(abs(val_in_dict - num) < 0.05 for num in ent_nums):
                        return True
    return False


def map_features(
    phase1_entities: List[Dict[str, Any]],
    phase3_result: Dict[str, Any],
    phase4_result: Dict[str, Any],
    phase5_result: Dict[str, Any]
) -> Tuple[List[FeatureInstance], Dict[str, str]]:
    parser = AnnotationParser()
    features = []
    entity_to_feature_id = {}
    dimension_facts = extract_dimension_facts(phase1_entities)
    
    dims = reconstruct_dimensions(phase1_entities)
    overall_width = dims.get("width")
    overall_height = dims.get("height")
    
    entity_by_id = {e["entity_id"]: e for e in phase1_entities}
    hole_candidates = phase4_result.get("hole_candidates", {}).get("hole_candidates", [])
    hole_by_id = {h["candidate_id"]: h for h in hole_candidates}
    radial_patterns = phase4_result.get("radial_patterns", {}).get("radial_patterns", [])
    
    has_rectangular_pattern_callout = (
        dimension_facts.get("pcd") is None
        and len([d for d in dimension_facts.get("pattern_dimensions", []) if "PATTERN" in d.get("text", "")]) >= 2
    )
    pattern_member_ids = set()
    used_concentric_centers = []

    # Initialize tracking sets for represented entities to prevent fallback duplication
    represented_entity_ids = set()
    represented_concentric_keys = set()

    # Loop Hierarchy Detection
    loop_candidates = []
    loops_data = phase3_result.get("loops", {}).get("loops", [])
    processed_loop_entities = set()
    for loop in loops_data:
        ent_ids = loop.get("entity_ids", [])
        if not ent_ids:
            continue
        xs, ys = [], []
        for eid in ent_ids:
            ent = entity_by_id.get(eid)
            if ent:
                bbox = _get_entity_bbox(ent)
                if bbox:
                    xs.extend([bbox[0], bbox[1]])
                    ys.extend([bbox[2], bbox[3]])
        if xs and ys:
            loop_candidates.append({
                "id": loop.get("loop_id"),
                "entity_ids": ent_ids,
                "bbox": (min(xs), max(xs), min(ys), max(ys)),
                "area": (max(xs) - min(xs)) * (max(ys) - min(ys)),
                "is_circle": False
            })
            processed_loop_entities.update(ent_ids)
            
    for ent in phase1_entities:
        eid = ent.get("entity_id")
        etype = ent.get("entity_type")
        geom = ent.get("geometry", {})
        if etype in ("POLYLINE", "LWPOLYLINE") and geom.get("closed", False):
            if eid in processed_loop_entities:
                continue
            bbox = _get_entity_bbox(ent)
            if bbox:
                loop_candidates.append({
                    "id": eid,
                    "entity_ids": [eid],
                    "bbox": bbox,
                    "area": (bbox[1] - bbox[0]) * (bbox[3] - bbox[2]),
                    "is_circle": False
                })
        elif etype == "CIRCLE":
            bbox = _get_entity_bbox(ent)
            if bbox:
                loop_candidates.append({
                    "id": eid,
                    "entity_ids": [eid],
                    "bbox": bbox,
                    "area": (bbox[1] - bbox[0]) * (bbox[3] - bbox[2]),
                    "is_circle": True
                })

    loop_candidates.sort(key=lambda c: c["area"], reverse=True)
    loop_hierarchy = {}
    for c in loop_candidates:
        loop_hierarchy[c["id"]] = {
            "id": c["id"],
            "parent_id": None,
            "children_ids": [],
            "depth": 0
        }
    for i in range(len(loop_candidates)):
        child = loop_candidates[i]
        best_parent = None
        best_area = float("inf")
        c_bbox = child["bbox"]
        c_area = child["area"]
        for j in range(len(loop_candidates)):
            if i == j:
                continue
            parent = loop_candidates[j]
            p_bbox = parent["bbox"]
            p_area = parent["area"]
            tol = 0.1
            if (p_bbox[0] <= c_bbox[0] + tol and
                p_bbox[1] >= c_bbox[1] - tol and
                p_bbox[2] <= c_bbox[2] + tol and
                p_bbox[3] >= c_bbox[3] - tol and
                p_area > c_area):
                if p_area < best_area:
                    best_area = p_area
                    best_parent = parent["id"]
        if best_parent is not None:
            loop_hierarchy[child["id"]]["parent_id"] = best_parent
            loop_hierarchy[best_parent]["children_ids"].append(child["id"])

    for cid, node in loop_hierarchy.items():
        depth = 0
        curr = cid
        while loop_hierarchy[curr]["parent_id"] is not None:
            depth += 1
            curr = loop_hierarchy[curr]["parent_id"]
            if depth > 10:
                break
        node["depth"] = depth

    outer_loops = [c for c in loop_candidates if loop_hierarchy[c["id"]]["parent_id"] is None]
    outermost_loop = outer_loops[0] if outer_loops else None
    pocket_candidates = []
    if outermost_loop:
        for c in loop_candidates:
            if c["id"] == outermost_loop["id"]:
                continue
            is_child = False
            curr = c["id"]
            while loop_hierarchy[curr]["parent_id"] is not None:
                if loop_hierarchy[curr]["parent_id"] == outermost_loop["id"]:
                    is_child = True
                    break
                curr = loop_hierarchy[curr]["parent_id"]
            if is_child and not c["is_circle"]:
                pocket_candidates.append(c)
    
    # MAP 1: Radial Patterns
    for idx, rp in enumerate(radial_patterns):
        member_ids = rp.get("member_candidate_ids", [])
        if len(member_ids) < 3:
            continue
        if has_rectangular_pattern_callout:
            continue
        
        hole_diameter = None
        hole_positions = []
        for cid in member_ids:
            hc = hole_by_id.get(cid)
            if hc:
                radii = hc.get("radii", [])
                if radii and hole_diameter is None:
                    hole_diameter = round(radii[0] * 2, 4)
                hole_positions.append(hc.get("center"))
        
        if hole_diameter is None:
            continue
        
        pcd = dimension_facts.get("pcd") or round(rp.get("pattern_radius", 0) * 2, 4)
        pattern_member_ids.update(member_ids)
        
        features.append(FeatureInstance(
            feature_id=f"radial_pattern_{idx + 1}",
            feature_class="hole_pattern",
            parameters={
                "pattern_type": "radial",
                "pcd": pcd,
                "hole_count": len(member_ids),
                "hole_diameter": hole_diameter,
                "angular_spacing": rp.get("angular_spacing_deg"),
                "center": rp.get("center"),
                "positions": hole_positions
            }
        ))
        
        # Track represented entities and keys
        for cid in member_ids:
            hc = hole_by_id.get(cid)
            if hc:
                for eid in hc.get("entity_ids", []):
                    entity_to_feature_id[eid] = f"radial_pattern_{idx + 1}"
                represented_entity_ids.update(hc.get("entity_ids", []))
                center = hc.get("center")
                radii = hc.get("radii", [])
                if center and len(center) >= 2:
                    for r in radii:
                        represented_concentric_keys.add((round(center[0], 4), round(center[1], 4), round(r, 4)))
    
    # MAP 2: Concentric Systems
    conc_groups = phase3_result.get("concentric_groups", {}).get("concentric_groups", [])
    for idx, cg in enumerate(conc_groups):
        radii = cg.get("radii", [])
        if not radii:
            continue
        center = cg.get("center")
        
        group_entities = [entity_by_id.get(eid) for eid in cg.get("entity_ids", []) if entity_by_id.get(eid)]
        has_closed_circle = any(ent.get("entity_type") == "CIRCLE" for ent in group_entities)
        
        matching_bores = [
            b for b in dimension_facts.get("bores", [])
            if b.get("center") and center and math.dist(b["center"], center) < 1.0
        ]
        has_bore_callout = len(matching_bores) > 0
        
        matching_holes = [
            c for c in dimension_facts.get("hole_callouts", [])
            if abs(c.get("diameter", 0) - round(radii[0] * 2, 4)) < 1.0
        ]
        has_hole_callout = len(matching_holes) > 0
        
        if not (has_closed_circle or has_bore_callout or has_hole_callout):
            continue

        if center and len(center) >= 2:
            used_concentric_centers.append((round(center[0], 4), round(center[1], 4)))
            
        # Track represented entities and keys
        for eid in cg.get("entity_ids", []):
            entity_to_feature_id[eid] = f"concentric_bore_{idx + 1}"
        represented_entity_ids.update(cg.get("entity_ids", []))
        for r in radii:
            if center and len(center) >= 2:
                represented_concentric_keys.add((round(center[0], 4), round(center[1], 4), round(r, 4)))

        matching_bores = [
            b for b in dimension_facts.get("bores", [])
            if b.get("center") and center and math.dist(b["center"], center) < 1.0
        ]
        bore_diameter_from_label = matching_bores[0]["diameter"] if matching_bores else None
        labeled_diameters = [round(r * 2, 4) for r in radii]
        boss_diameter = next((d for d in dimension_facts.get("boss_diameters", []) if d in labeled_diameters), None)
        base_diameter = next((d for d in dimension_facts.get("base_diameters", []) if d in labeled_diameters), None)
        flange_diameter = next((d for d in dimension_facts.get("flange_diameters", []) if d in labeled_diameters), None)
        pcd = dimension_facts.get("pcd")

        if len(radii) == 1:
            diameter = bore_diameter_from_label or round(radii[0] * 2, 4)
            bore_type = "shaft" if diameter > 40 else ("bearing" if diameter > 20 else "bushing")
            features.append(FeatureInstance(
                feature_id=f"concentric_bore_{idx + 1}",
                feature_class="concentric_bore",
                parameters={
                    "bore_diameter": diameter,
                    "diameter": diameter,
                    "center": cg.get("center"),
                    "bore_type": bore_type
                }
            ))
            continue

        inner_diameter = bore_diameter_from_label or round(min(radii) * 2, 4)
        outer_diameter = round(max(radii) * 2, 4)
        bore_type = "shaft" if inner_diameter > 40 else ("bearing" if inner_diameter > 20 else "bushing")
        params = {
            "inner_diameter": inner_diameter,
            "outer_diameter": outer_diameter,
            "bore_diameter": inner_diameter,
            "center": cg.get("center"),
            "bore_type": bore_type
        }
        if boss_diameter:
            params["boss_diameter"] = boss_diameter
        if base_diameter:
            params["base_diameter"] = base_diameter
        if flange_diameter:
            params["flange_diameter"] = flange_diameter
        if pcd and pcd in labeled_diameters:
            params["pcd_reference_diameter"] = pcd

        features.append(FeatureInstance(
            feature_id=f"concentric_bore_{idx + 1}",
            feature_class="concentric_bore",
            parameters=params
        ))
    
    # MAP 3: Non-pattern Holes
    non_pattern_holes = [h for h in hole_candidates if h["candidate_id"] not in pattern_member_ids]
    holes_by_diameter = {}
    for h in non_pattern_holes:
        radii = h.get("radii", [])
        if not radii:
            continue
        diameter = round(radii[0] * 2, 4)
        if diameter not in holes_by_diameter:
            holes_by_diameter[diameter] = []
        holes_by_diameter[diameter].append(h)
    
    for diameter, holes in holes_by_diameter.items():
        if len(holes) == 1 and diameter >= 20:
            h = holes[0]
            center = h.get("center")
            center_key = (round(center[0], 4), round(center[1], 4)) if center and len(center) >= 2 else None
            label_match = any(
                (abs(b["diameter"] - diameter) < 0.1 if (b.get("center") is None or center is None)
                 else math.dist(b["center"], center) < 1.0)
                for b in dimension_facts.get("bores", [])
            )
            if label_match and center_key not in used_concentric_centers:
                features.append(FeatureInstance(
                    feature_id=f"bore_d{int(diameter)}",
                    feature_class="concentric_bore",
                    parameters={
                        "bore_diameter": diameter,
                        "diameter": diameter,
                        "center": center,
                        "bore_type": "shaft" if diameter > 40 else "bearing"
                    }
                ))
                # Track represented entities and keys
                for eid in h.get("entity_ids", []):
                    entity_to_feature_id[eid] = f"bore_d{int(diameter)}"
                represented_entity_ids.update(h.get("entity_ids", []))
                for r in h.get("radii", []):
                    if center and len(center) >= 2:
                        represented_concentric_keys.add((round(center[0], 4), round(center[1], 4), round(r, 4)))
            continue

        if len(holes) < 2:
            continue
        
        positions = [h.get("center") for h in holes]
        x_coords = [p[0] for p in positions if p]
        y_coords = [p[1] for p in positions if p]
        
        spacing_x = round(max(x_coords) - min(x_coords), 4) if len(x_coords) > 1 else 0
        spacing_y = round(max(y_coords) - min(y_coords), 4) if len(y_coords) > 1 else 0
        offset_x = round(min(x_coords), 4) if x_coords else 0
        offset_y = round(min(y_coords), 4) if y_coords else 0
        
        matching_callout = next(
            (c for c in dimension_facts.get("hole_callouts", []) if abs(c.get("diameter", 0) - diameter) < 0.01),
            None
        )
        group_type = "linear_pattern"
        if spacing_x and spacing_y:
            group_type = "rectangular_pattern"
        if has_rectangular_pattern_callout:
            group_type = "rectangular_pattern"
        params = {
            "group_type": group_type,
            "pattern_type": group_type.replace("_pattern", ""),
            "count": matching_callout.get("count") if matching_callout else len(holes),
            "diameter": diameter,
            "positions": positions,
            "spacing_x": spacing_x,
            "spacing_y": spacing_y,
            "offset_x": offset_x,
            "offset_y": offset_y
        }
        if matching_callout and matching_callout.get("text"):
            params["text"] = matching_callout["text"]
        if matching_callout and matching_callout.get("counterbore"):
            params.update({k: v for k, v in matching_callout["counterbore"].items() if v is not None})

        features.append(FeatureInstance(
            feature_id=f"hole_group_d{int(diameter)}",
            feature_class="hole_group",
            parameters=params
        ))
        
        # Track represented entities and keys
        for h in holes:
            for eid in h.get("entity_ids", []):
                entity_to_feature_id[eid] = f"hole_group_d{int(diameter)}"
            represented_entity_ids.update(h.get("entity_ids", []))
            center = h.get("center")
            for r in h.get("radii", []):
                if center and len(center) >= 2:
                    represented_concentric_keys.add((round(center[0], 4), round(center[1], 4), round(r, 4)))
    
    # MAP 4: Slot Candidates
    if dimension_facts.get("pcd"):
        pcd = dimension_facts["pcd"]
        for callout in dimension_facts.get("hole_callouts", []):
            count = callout.get("count")
            diameter = callout.get("diameter")
            positions = [
                h.get("center") for h in hole_candidates
                if h.get("radii") and abs(round(min(h["radii"]) * 2, 4) - diameter) < 0.01
            ]
            if count and count >= 3 and len(positions) >= count:
                params = {
                    "pattern_type": "radial",
                    "pcd": pcd,
                    "hole_count": count,
                    "hole_diameter": diameter,
                    "angular_spacing": round(360 / count, 4),
                    "center": _infer_center_from_positions(positions),
                    "positions": positions[:count]
                }
                if callout.get("counterbore"):
                    params.update({k: v for k, v in callout["counterbore"].items() if v is not None})
                if not any(f.feature_class == "hole_pattern" and abs(f.parameters.get("pcd", 0) - pcd) < 1.0 for f in features):
                    features.append(FeatureInstance(
                        feature_id="radial_pattern_from_dimensions",
                        feature_class="hole_pattern",
                        parameters=params
                    ))
                    # Track represented entities and keys for this pattern
                    for h in hole_candidates:
                        if h.get("radii") and abs(round(min(h["radii"]) * 2, 4) - diameter) < 0.01:
                            represented_entity_ids.update(h.get("entity_ids", []))
                            center = h.get("center")
                            for r in h.get("radii", []):
                                if center and len(center) >= 2:
                                    represented_concentric_keys.add((round(center[0], 4), round(center[1], 4), round(r, 4)))

    slot_candidates = phase4_result.get("slot_candidates", {}).get("slot_candidates", [])
    has_slot_text = any(
        any(_match_keyword(text, kw) for kw in ("SLOT", "SLOTS", "OBROUND", "KEYWAY", "GROOVE", "CHANNEL", "POCKET"))
        for text in [_clean_text(e['geometry'].get('text')) for e in phase1_entities if e.get('entity_type') in ("DIMENSION", "TEXT", "MTEXT")]
    )
    if slot_candidates and has_slot_text:
        slot_positions = []
        slot_width = None
        slot_length = None
        slot_orientation = None
        
        for sc in slot_candidates:
            width = sc.get("width", 0)
            height = sc.get("height", 0)
            if width > 0 and height > 0:
                if height > width:
                    orientation = "vertical"
                    length = round(height, 4)
                    width_val = round(width, 4)
                else:
                    orientation = "horizontal"
                    length = round(width, 4)
                    width_val = round(height, 4)
                
                if overall_width and overall_height:
                    if (length >= overall_width - 2.0 and width_val >= overall_height - 2.0) or \
                       (width_val >= overall_width - 2.0 and length >= overall_height - 2.0):
                        continue
                
                if slot_width is None:
                    slot_width = width_val
                    slot_length = length
                    slot_orientation = orientation
                
                slot_positions.append({"center": sc.get("center")})
        
        if slot_positions:
            features.append(FeatureInstance(
                feature_id="slot_array_1",
                feature_class="slot_array",
                parameters={
                    "count": len(slot_positions),
                    "width": slot_width,
                    "length": slot_length,
                    "orientation": slot_orientation,
                    "positions": slot_positions
                }
            ))
            # Track represented entities for slot arrays
            for sc in slot_candidates:
                width = sc.get("width", 0)
                height = sc.get("height", 0)
                if width > 0 and height > 0:
                    if overall_width and overall_height:
                        if (max(width, height) >= overall_width - 2.0 and min(width, height) >= overall_height - 2.0):
                            continue
                    entity_id_field = sc.get("entity_id")
                    if isinstance(entity_id_field, list):
                        for eid in entity_id_field:
                            entity_to_feature_id[eid] = "slot_array_1"
                        represented_entity_ids.update(entity_id_field)
                    elif isinstance(entity_id_field, str):
                        entity_to_feature_id[entity_id_field] = "slot_array_1"
                        represented_entity_ids.add(entity_id_field)
    
    # MAP 5: Corner ARCs → fillet_group
    has_fillet_text = any(
        any(_match_keyword(text, kw) for kw in ("FILLET", "FILLETS", "ROOT FILLET", "INTERNAL FILLET", "RADIUS", "RAD", "R8", "R10", "COPE"))
        for text in [_clean_text(e['geometry'].get('text')) for e in phase1_entities if e.get('entity_type') in ("DIMENSION", "TEXT", "MTEXT")]
    )
    corner_arcs = []
    if has_fillet_text:
        for ent in phase1_entities:
            if ent.get("entity_type") == "ARC":
                geom = ent.get("geometry", {})
                radius = geom.get("radius")
                center = geom.get("center")
                if radius and 10 <= radius <= 20 and center:
                    corner_arcs.append({
                        "radius": radius,
                        "center": center
                    })
    
    if corner_arcs:
        radii = [arc["radius"] for arc in corner_arcs]
        if radii:
            avg_radius = round(sum(radii) / len(radii), 4)
            positions = [arc["center"] for arc in corner_arcs]
            features.append(FeatureInstance(
                feature_id="corner_fillets",
                feature_class="fillet_group",
                parameters={
                    "radius": avg_radius,
                    "count": len(corner_arcs),
                    "positions": positions
                }
            ))
            # Track represented entities and keys
            for ent in phase1_entities:
                if ent.get("entity_type") == "ARC":
                    geom = ent.get("geometry", {})
                    radius = geom.get("radius")
                    center = geom.get("center")
                    if radius and 10 <= radius <= 20 and center:
                        entity_to_feature_id[ent.get("entity_id")] = "corner_fillets"
                        represented_entity_ids.add(ent.get("entity_id"))
                        represented_concentric_keys.add((round(center[0], 4), round(center[1], 4), round(radius, 4)))
    
    for idx, port in enumerate(dimension_facts.get("lube_ports", [])):
        features.append(FeatureInstance(
            feature_id=f"lube_port_{idx + 1}",
            feature_class="lube_port",
            parameters=port
        ))



    across_flats = None
    drive_size = None
    head_diameter = None
    head_thickness = None
    grip_length = None
    taper_length = None
    neck_length = None
    thru_bore = None
    flange_thickness = None
    
    thread_diameter = None
    thread_length = None
    thread_pitch = None
    thread_designations = []
    
    web_thickness = None
    struct_flange_thickness = None
    wall_thickness = None
    fillet_radius = None
    inner_radius = None
    outer_radius = None
    has_struct = False
    
    heatsink_fin_feature = None
    pocket_value = None
    rib_value = None
    
    bends = []
    reliefs = []
    chamfers = []
    tabs = []
    matched_handles = set()
    unknown_dimensions = []
    unknown_annotations = []

    for ent in phase1_entities:
        etype = ent.get("entity_type")
        if etype not in ("DIMENSION", "TEXT", "MTEXT"):
            continue
        geom = ent.get("geometry", {})
        text = _clean_text(geom.get("text"))
        if not text:
            continue
        val = _first_number(text)
        handle = ent.get("handle")
        matched = False
        
        if any(_match_keyword(text, kw) for kw in ("OVERALL", "SQ", "DEVELOPED LENGTH", "BLANK WIDTH", "CASTING W", "CASTING H")):
            matched = True
        
        if any(_match_keyword(text, kw) for kw in ("PCD", "PITCH CIRCLE", "PITCH", "SPACING", "CRS", "CTR TO CTR", "CTR-TO-CTR", "CENTER DISTANCE")):
            matched = True
            
        is_thread = False
        parsed_ann = parser.parse(text)
        if not any(_match_keyword(text, kw) for kw in ("PITCH CIRCLE", "PCD", "BORE PITCH", "HOLE PITCH")):
            if parsed_ann.annotation_type == "thread":
                is_thread = True
                matched = True
                if any(_match_keyword(text, kw) for kw in ("MIN", "LENGTH", "DEPTH", "LGT", "LEN")):
                    nums = _numbers(text)
                    if nums:
                        thread_length = nums[0]
                else:
                    thread_diameter = parsed_ann.nominal_diameter
                    thread_pitch = parsed_ann.thread_pitch
                    thread_designations.append(text.strip())
                    
        if any(_match_keyword(text, kw) for kw in SYNONYMS["BEND_RELIEF"]):
            count_match = re.search(r"^\s*(\d+)\s*[Xx]", text)
            count_val = int(count_match.group(1)) if count_match else 1
            reliefs.append({
                "text": text,
                "value": val,
                "count": count_val
            })
            matched = True
        elif _match_keyword(text, "BEND"):
            angle_val = 90.0
            radius_val = 2.0
            m_ang = re.search(r"(\d+)\s*DEG", text) or re.search(r"(\d+)%%D", text) or re.search(r"(\d+)°", text)
            if m_ang:
                angle_val = float(m_ang.group(1))
            m_rad = re.search(r"R\s*(\d+(?:\.\d+)?)", text)
            if m_rad:
                radius_val = float(m_rad.group(1))
            
            count_match = re.search(r"^\s*(\d+)\s*[Xx]", text)
            count_val = int(count_match.group(1)) if count_match else 1
            bends.append({
                "count": count_val,
                "angle": angle_val,
                "radius": radius_val,
                "text": text
            })
            matched = True
            
        elif _match_keyword(text, "FIN") or _match_keyword(text, "FINS") or _match_keyword(text, "COOLING FIN") or _match_keyword(text, "RADIAL FIN") or _match_keyword(text, "EXTRUDED FIN") or _match_keyword(text, "FIN PITCH") or _match_keyword(text, "FIN COUNT"):
            nums = _numbers(text)
            count_match = re.search(r"^\s*(\d+)\s*[Xx]", text)
            count_val = int(count_match.group(1)) if count_match else (int(nums[0]) if nums else 1)
            
            thickness_val = 2.0
            pitch_val = 10.0
            clean_nums = _numbers(strip_count_prefix(text))
            if len(clean_nums) >= 2:
                thickness_val = clean_nums[0]
                pitch_val = clean_nums[1]
            elif len(clean_nums) == 1:
                pitch_val = clean_nums[0]
                
            heatsink_fin_feature = FeatureInstance(
                feature_id="heatsink_fins_1",
                feature_class="heatsink_fin",
                parameters={
                    "count": count_val,
                    "thickness": thickness_val,
                    "pitch": pitch_val,
                    "text": text
                }
            )
            matched = True
            
        elif _match_keyword(text, "TAB") or _match_keyword(text, "FIXTURING"):
            count_match = re.search(r"^\s*(\d+)\s*[Xx]", text)
            count_val = int(count_match.group(1)) if count_match else 1
            tabs.append({
                "text": text,
                "value": val,
                "count": count_val
            })
            matched = True
            
        elif (_match_keyword(text, "PERIMETER WALL") or
              _match_keyword(text, "UNIFORM WALL") or
              _match_keyword(text, "STRUCTURAL WALL") or
              (_match_keyword(text, "POCKET") and any(w in text for w in ("WALL", "THK", "THICK")))):
            pocket_value = val
            matched = True
            
        elif _match_keyword(text, "RIB") or _match_keyword(text, "RIBS") or _match_keyword(text, "STIFFENER"):
            rib_value = val
            matched = True
            
        elif any(_match_keyword(text, kw) for kw in ("CORE DIA", "CORE DIAMETER", "CORE")):
            features.append(FeatureInstance(
                feature_id="heatsink_core_1",
                feature_class="heatsink_core",
                parameters={
                    "diameter": val,
                    "text": text
                }
            ))
            matched = True
            
        elif _match_keyword(text, "CHAMFER") or _match_keyword(text, "BEVEL"):
            c_val = val
            c_angle = 45.0
            c_count = parsed_ann.quantity or 1
            validation = "unvalidated"
            if parsed_ann.annotation_type == "chamfer":
                c_val = parsed_ann.chamfer_size
                c_angle = parsed_ann.chamfer_angle
                c_count = parsed_ann.quantity or 1
                validation = "validated"
            chamfers.append({
                "text": text,
                "value": c_val,
                "count": c_count,
                "chamfer_angle": c_angle,
                "validation_status": validation,
                "source_annotation": text
            })
            matched = True

        elif CONCEPT_REGISTRY["O_RING"].matches_text(text):
            is_depth = any(_match_keyword(text, kw) for kw in ("DEPTH", "DEEP", "GROOVE DEPTH"))
            o_ring_dia = val if not is_depth else None
            o_ring_depth = val if is_depth else None
            validation = "unvalidated"
            
            if parsed_ann.annotation_type == "counterbore":
                o_ring_dia = parsed_ann.counterbore_diameter
                o_ring_depth = parsed_ann.counterbore_depth
                validation = "validated"
            elif parsed_ann.annotation_type in ("thread", "radius"):
                o_ring_dia = parsed_ann.nominal_diameter or parsed_ann.radius_value
                validation = "validated"
                
            features.append(FeatureInstance(
                feature_id=f"o_ring_{len(features)+1}",
                feature_class="o_ring",
                parameters={
                    "text": text,
                    "o_ring_diameter": o_ring_dia,
                    "o_ring_groove_depth": o_ring_depth,
                    "validation_status": validation,
                    "source_annotation": text
                }
            ))
            matched = True

        elif CONCEPT_REGISTRY["PORT"].matches_text(text):
            port_thd = text if any(_match_keyword(text, kw) for kw in ("M12", "M16", "M10", "M8", "1/2", "1/4", "G")) else None
            is_depth = any(_match_keyword(text, kw) for kw in ("DEPTH", "DEEP"))
            port_dia = val if not is_depth else None
            port_depth = val if is_depth else None
            
            validation = "unvalidated"
            if parsed_ann.annotation_type == "thread":
                port_thd = parsed_ann.source_annotation
                port_dia = parsed_ann.nominal_diameter
                validation = "validated"
            elif parsed_ann.annotation_type == "counterbore":
                port_dia = parsed_ann.counterbore_diameter
                port_depth = parsed_ann.counterbore_depth
                validation = "validated"
                
            features.append(FeatureInstance(
                feature_id=f"port_{len(features)+1}",
                feature_class="port",
                parameters={
                    "text": text,
                    "port_diameter": port_dia,
                    "port_thread": port_thd,
                    "port_depth": port_depth,
                    "validation_status": validation,
                    "source_annotation": text
                }
            ))
            matched = True

        elif CONCEPT_REGISTRY["CHANNEL"].matches_text(text):
            is_depth = any(_match_keyword(text, kw) for kw in ("DEPTH", "DEEP"))
            is_len = any(_match_keyword(text, kw) for kw in ("LENGTH", "LONG"))
            features.append(FeatureInstance(
                feature_id=f"channel_{len(features)+1}",
                feature_class="channel",
                parameters={
                    "text": text,
                    "channel_width": val if (not is_depth and not is_len) else None,
                    "channel_depth": val if is_depth else None,
                    "channel_length": val if is_len else None
                }
            ))
            matched = True

        elif CONCEPT_REGISTRY["SHOULDER"].matches_text(text):
            nums = _numbers(text)
            s_dia = None
            s_len = None
            if len(nums) >= 2:
                s_dia = nums[0]
                s_len = nums[1]
            elif len(nums) == 1:
                is_dia = any(_match_keyword(text, kw) for kw in ("DIA", "DIAMETER", "Ø", "F8", "PRECISION"))
                if is_dia:
                    s_dia = nums[0]
                else:
                    s_len = nums[0]
            features.append(FeatureInstance(
                feature_id=f"shoulder_{len(features)+1}",
                feature_class="shoulder",
                parameters={
                    "text": text,
                    "shoulder_diameter": s_dia,
                    "shoulder_length": s_len
                }
            ))
            matched = True

        elif CONCEPT_REGISTRY["COPE"].matches_text(text):
            features.append(FeatureInstance(
                feature_id=f"cope_{len(features)+1}",
                feature_class="cope",
                parameters={
                    "text": text,
                    "cope_radius": val
                }
            ))
            matched = True
            
        if any(_match_keyword(text, kw) for kw in SYNONYMS["ACROSS_FLATS"]):
            across_flats = val
            matched = True
        if _match_keyword(text, "HEX DRIVE"):
            drive_size = val
            matched = True
        if any(_match_keyword(text, kw) for kw in ("HEAD OD", "HEAD DIAMETER")):
            head_diameter = val
            matched = True
        if any(_match_keyword(text, kw) for kw in ("HEX HEIGHT", "HEAD HEIGHT")):
            head_thickness = val
            matched = True
        if _match_keyword(text, "GRIP LENGTH"):
            grip_length = val
            matched = True
        if _match_keyword(text, "TAPER LENGTH"):
            taper_length = val
            matched = True
        if _match_keyword(text, "WELD NECK"):
            neck_length = val
            matched = True
        if any(_match_keyword(text, kw) for kw in ("THRU BORE", "THROUGH BORE")):
            thru_bore = val
            matched = True
        if any(_match_keyword(text, kw) for kw in SYNONYMS["FLANGE_THICKNESS"]) or _match_keyword(text, "FLANGE THK"):
            flange_thickness = val
            matched = True
            
        if any(_match_keyword(text, kw) for kw in SYNONYMS["WEB_THICKNESS"]):
            web_thickness = val
            has_struct = True
            matched = True
        if any(_match_keyword(text, kw) for kw in SYNONYMS["FLANGE_THICKNESS"]) or _match_keyword(text, "FLANGE THK"):
            struct_flange_thickness = val
            has_struct = True
            matched = True
        if any(_match_keyword(text, kw) for kw in ("WALL THK", "WALL THICKNESS")):
            wall_thickness = val
            has_struct = True
            matched = True
        if _match_keyword(text, "ROOT FILLET") or _match_keyword(text, "INTERNAL FILLET") or _match_keyword(text, "FILLET"):
            fillet_radius = val
            has_struct = True
            matched = True
        if any(_match_keyword(text, kw) for kw in ("INNER RAD", "INNER RADIUS")):
            inner_radius = val
            matched = True
        if any(_match_keyword(text, kw) for kw in ("OUTER RAD", "OUTER RADIUS")):
            outer_radius = val
            matched = True
            
        if matched:
            matched_handles.add(handle)

    if thread_diameter is not None or thread_length is not None:
        designation = thread_designations[0] if thread_designations else "Thread"
        parser_inst = AnnotationParser()
        parsed_t = parser_inst.parse(designation)
        
        params = {
            "thread_designation": designation,
            "nominal_diameter": thread_diameter,
            "thread_length": thread_length,
            "pitch": thread_pitch,
        }
        if parsed_t.annotation_type == "thread":
            params.update({
                "thread_standard": parsed_t.thread_standard,
                "thread_pitch": parsed_t.thread_pitch,
                "nominal_diameter": parsed_t.nominal_diameter,
                "thread_gender": parsed_t.thread_gender or "internal",
                "tolerance_class": parsed_t.tolerance_class,
                "nominal_pipe_size": parsed_t.nominal_pipe_size,
                "major_diameter": parsed_t.nominal_diameter,
                "pitch_tpi": parsed_t.pitch_tpi,
                "validation_status": parsed_t.validation_status,
                "source_annotation": parsed_t.source_annotation
            })
        else:
            params.update({
                "thread_standard": "ISO Metric",
                "thread_pitch": thread_pitch,
                "thread_gender": "internal",
                "tolerance_class": None,
                "nominal_pipe_size": None,
                "major_diameter": thread_diameter,
                "pitch_tpi": None,
                "validation_status": "fallback",
                "source_annotation": designation
            })
            
        features.append(FeatureInstance(
            feature_id="thread_1",
            feature_class="thread",
            parameters=params
        ))
        
    has_keyway_text = any("KEYWAY" in _clean_text(e['geometry'].get('text')) for e in phase1_entities if e.get('entity_type') in ("DIMENSION", "TEXT", "MTEXT"))
    if has_keyway_text:
        k_width = None
        k_depth = None
        k_text = ""
        for ent in phase1_entities:
            text = _clean_text(ent['geometry'].get('text'))
            if "KEYWAY" in text:
                k_text = text
                nums = _numbers(text)
                if "WIDTH" in text:
                    if nums: k_width = nums[0]
                elif "DEPTH" in text:
                    if nums: k_depth = nums[0]
                else:
                    if len(nums) >= 2:
                        k_width = nums[0]
                        k_depth = nums[1]
                    elif len(nums) == 1:
                        k_width = nums[0]
                        
        features.append(FeatureInstance(
            feature_id="keyway_1",
            feature_class="keyway",
            parameters={
                "width": k_width,
                "depth": k_depth,
                "text": k_text
            }
        ))
        
    for idx, r in enumerate(reliefs):
        features.append(FeatureInstance(
            feature_id=f"bend_relief_{idx + 1}",
            feature_class="bend_relief",
            parameters={
                "text": r["text"],
                "value": r["value"],
                "count": r["count"]
            }
        ))
        
    for idx, b in enumerate(bends):
        features.append(FeatureInstance(
            feature_id=f"bend_{idx + 1}",
            feature_class="sheet_metal_bend",
            parameters=b
        ))
        
    if heatsink_fin_feature:
        features.append(heatsink_fin_feature)
        
    for idx, t in enumerate(tabs):
        features.append(FeatureInstance(
            feature_id=f"alignment_tab_{idx + 1}",
            feature_class="alignment_tab",
            parameters={
                "text": t["text"],
                "value": t["value"],
                "count": t["count"]
            }
        ))
        
    for idx, c in enumerate(chamfers):
        features.append(FeatureInstance(
            feature_id=f"chamfer_{idx + 1}",
            feature_class="chamfer",
            parameters={
                "text": c["text"],
                "value": c["value"],
                "count": c["count"]
            }
        ))
        
    if has_struct:
        if wall_thickness is not None or inner_radius is not None:
            profile_type = "HSS Tube"
        elif web_thickness is not None and struct_flange_thickness is not None:
            profile_type = "I-Beam"
        else:
            profile_type = "structural_profile"
            
        features.append(FeatureInstance(
            feature_id="structural_profile_1",
            feature_class="structural_profile",
            parameters={
                "profile_type": profile_type,
                "web_thickness": web_thickness,
                "flange_thickness": struct_flange_thickness or flange_thickness,
                "wall_thickness": wall_thickness,
                "fillet_radius": fillet_radius,
                "inner_radius": inner_radius,
                "outer_radius": outer_radius
            }
        ))
        
    if across_flats is not None:
        if thread_diameter is not None:
            features.append(FeatureInstance(
                feature_id="bolt_1",
                feature_class="bolt",
                parameters={
                    "grip_length": grip_length,
                    "thread_length": thread_length,
                    "across_flats": across_flats,
                    "nominal_diameter": thread_diameter
                }
            ))
        features.append(FeatureInstance(
            feature_id="hex_head_1",
            feature_class="hex_head",
            parameters={
                "across_flats": across_flats
            }
        ))
        
    if drive_size is not None and head_diameter is not None:
        features.append(FeatureInstance(
            feature_id="hex_drive_1",
            feature_class="hex_drive",
            parameters={
                "size": drive_size
            }
        ))
        features.append(FeatureInstance(
            feature_id="screw_1",
            feature_class="screw",
            parameters={
                "length": val if val else head_thickness,
                "head_diameter": head_diameter,
                "nominal_diameter": thread_diameter,
                "drive_size": drive_size
            }
        ))
        
    if head_diameter is not None and not (drive_size is not None):
        features.append(FeatureInstance(
            feature_id="cylindrical_head_1",
            feature_class="cylindrical_head",
            parameters={
                "diameter": head_diameter
            }
        ))
        
    if taper_length is not None or neck_length is not None or flange_thickness is not None:
        features.append(FeatureInstance(
            feature_id="fitting_1",
            feature_class="fitting",
            parameters={
                "taper_length": taper_length,
                "hex_height": head_thickness,
                "neck_length": neck_length,
                "flange_thickness": flange_thickness,
                "across_flats": across_flats
            }
        ))
        
    if pocket_candidates:
        for idx, c in enumerate(pocket_candidates):
            xmin, xmax, ymin, ymax = c["bbox"]
            w = round(xmax - xmin, 4)
            h = round(ymax - ymin, 4)
            features.append(FeatureInstance(
                feature_id=f"pocket_{idx + 1}",
                feature_class="pocket",
                parameters={
                    "pocket_width": min(w, h),
                    "pocket_length": max(w, h),
                    "perimeter_wall": pocket_value
                }
            ))
            represented_entity_ids.update(c.get("entity_ids", []))
    elif pocket_value is not None:
        features.append(FeatureInstance(
            feature_id="pocket_1",
            feature_class="pocket",
            parameters={
                "pocket_width": min(overall_width, overall_height) if overall_width and overall_height else None,
                "pocket_length": max(overall_width, overall_height) if overall_width and overall_height else None,
                "perimeter_wall": pocket_value
            }
        ))
        
    if rib_value is not None:
        features.append(FeatureInstance(
            feature_id="rib_1",
            feature_class="rib",
            parameters={
                "value": rib_value
            }
        ))

    # Construct unmapped dimension_annotations feature
    parser_inst = AnnotationParser()
    unmapped_linear = []
    for d in dimension_facts.get("linear_dimensions", []):
        ent = entity_by_id.get(d.get("handle")) or next((e for e in phase1_entities if e.get("handle") == d.get("handle")), None)
        if ent and not is_entity_mapped(ent, features, matched_handles):
            d_copy = dict(d)
            parsed_ann = parser_inst.parse(d_copy.get("text"))
            if parsed_ann.annotation_type == "tolerance":
                d_copy["tolerance_upper"] = parsed_ann.tolerance_upper
                d_copy["tolerance_lower"] = parsed_ann.tolerance_lower
                d_copy["validation_status"] = parsed_ann.validation_status
            elif parsed_ann.annotation_type == "fit":
                d_copy["fit_class"] = parsed_ann.fit_class
                d_copy["lower_deviation"] = parsed_ann.lower_deviation
                d_copy["upper_deviation"] = parsed_ann.upper_deviation
                d_copy["validation_status"] = parsed_ann.validation_status
            unmapped_linear.append(d_copy)

    unmapped_pattern = []
    for d in dimension_facts.get("pattern_dimensions", []):
        ent = entity_by_id.get(d.get("handle")) or next((e for e in phase1_entities if e.get("handle") == d.get("handle")), None)
        if ent and not is_entity_mapped(ent, features, matched_handles):
            d_copy = dict(d)
            parsed_ann = parser_inst.parse(d_copy.get("text"))
            if parsed_ann.annotation_type == "tolerance":
                d_copy["tolerance_upper"] = parsed_ann.tolerance_upper
                d_copy["tolerance_lower"] = parsed_ann.tolerance_lower
                d_copy["validation_status"] = parsed_ann.validation_status
            elif parsed_ann.annotation_type == "fit":
                d_copy["fit_class"] = parsed_ann.fit_class
                d_copy["lower_deviation"] = parsed_ann.lower_deviation
                d_copy["upper_deviation"] = parsed_ann.upper_deviation
                d_copy["validation_status"] = parsed_ann.validation_status
            unmapped_pattern.append(d_copy)

    if unmapped_linear or unmapped_pattern:
        features.append(FeatureInstance(
            feature_id="dimension_annotations",
            feature_class="dimension_annotations",
            parameters={
                "dimensions": unmapped_linear,
                "pattern_dimensions": unmapped_pattern
            }
        ))

    for ent in phase1_entities:
        if ent.get("entity_type") not in ("DIMENSION", "TEXT", "MTEXT"):
            continue
        handle = ent.get("handle")
        if handle in matched_handles:
            continue
        if is_entity_mapped(ent, features, matched_handles):
            continue
        geom = ent.get("geometry", {})
        text = _clean_text(geom.get("text"))
        if not text:
            continue
        val = _first_number(text)
        fact = {"text": text, "value": val, "handle": handle}
        if ent.get("entity_type") == "DIMENSION":
            unknown_dimensions.append(fact)
        else:
            unknown_annotations.append(fact)

    if unknown_dimensions or unknown_annotations:
        features.append(FeatureInstance(
            feature_id="unknown_facts_container",
            feature_class="unknown_facts",
            parameters={
                "unknown_dimensions": unknown_dimensions,
                "unknown_annotations": unknown_annotations
            }
        ))
        
    # Add lube port centers to used_concentric_centers prior to loop
    for port in dimension_facts.get("lube_ports", []):
        center = port.get("center")
        if center and len(center) >= 2:
            used_concentric_centers.append((round(center[0], 4), round(center[1], 4)))

    circles_from_phase1 = [e for e in phase1_entities if e.get("entity_type") == "CIRCLE"]
    for circle in circles_from_phase1:
        ent_id = circle.get("entity_id")
        geom = circle.get("geometry", {})
        center = geom.get("center")
        radius = geom.get("radius", 0)
        diameter = round(radius * 2, 4)
        
        center_key = (round(center[0], 4), round(center[1], 4)) if center and len(center) >= 2 else None
        if center_key in used_concentric_centers:
            continue
            
        cx, cy = round(center[0], 4), round(center[1], 4)
        r = round(radius, 4)
        if ent_id in represented_entity_ids or (cx, cy, r) in represented_concentric_keys:
            continue
            
        matching_bore = next(
            (b for b in dimension_facts.get("bores", [])
             if abs(b["diameter"] - diameter) < 0.1),
             None
        )
        matching_hole = next(
            (c for c in dimension_facts.get("hole_callouts", [])
             if abs(c.get("diameter", 0) - diameter) < 0.1),
             None
        )
        if matching_bore or matching_hole or (center and abs(center[0]) < 1.0 and abs(center[1]) < 1.0 and diameter >= 20.0 and diameter < 100.0):
            bore_type = "shaft" if diameter > 40 else ("bearing" if diameter > 20 else "bushing")
            features.append(FeatureInstance(
                feature_id=f"concentric_bore_fallback_{ent_id}",
                feature_class="concentric_bore",
                parameters={
                    "bore_diameter": diameter,
                    "diameter": diameter,
                    "center": center,
                    "bore_type": bore_type
                }
            ))
            entity_to_feature_id[ent_id] = f"concentric_bore_fallback_{ent_id}"
            if center_key:
                used_concentric_centers.append(center_key)

    if thru_bore is not None:
        cb = next((f for f in features if f.feature_class == "concentric_bore"), None)
        if cb:
            cb.parameters["bore_diameter"] = thru_bore
        else:
            features.append(FeatureInstance(
                feature_id="bore_1",
                feature_class="concentric_bore",
                parameters={
                    "bore_diameter": thru_bore,
                    "bore_type": "bearing" if thru_bore > 20 else "bushing"
                }
            ))

    return features, entity_to_feature_id


def map_relationships(
    phase3_result: Dict[str, Any],
    phase4_result: Dict[str, Any],
    phase5_result: Dict[str, Any],
    phase6_result: Dict[str, Any],
    features: List[FeatureInstance],
    entity_to_feature_id: Dict[str, str]
) -> List[Relationship]:
    relationships = []
    
    # MAP 1: Concentric Groups
    conc_groups = phase3_result.get("concentric_groups", {}).get("concentric_groups", [])
    for idx, cg in enumerate(conc_groups):
        radii = cg.get("radii", [])
        if len(radii) < 2:
            continue
        
        inner_diameter = round(min(radii) * 2, 4)
        outer_diameter = round(max(radii) * 2, 4)
        
        # Dynamically resolve concentric feature IDs
        fids = []
        cg_center = cg.get("center")
        if cg_center:
            for f in features:
                if f.feature_class in ("dimension_annotations", "unknown_facts"):
                    continue
                f_center = f.parameters.get("center")
                if not f_center and f.feature_class == "hole_group":
                    positions = f.parameters.get("positions", [])
                    if positions:
                        f_center = [
                            sum(p[0] for p in positions) / len(positions),
                            sum(p[1] for p in positions) / len(positions)
                        ]
                if f_center and math.dist(f_center, cg_center) < 1.0:
                    fids.append(f.feature_id)
                    
        # Only add concentric relationship if at least 2 concentric features exist
        if len(fids) >= 2:
            relationships.append(Relationship(
                relationship_id=f"concentric_{idx + 1}",
                relationship_type="concentric",
                feature_ids=fids,
                parameters={
                    "center": cg.get("center"),
                    "inner_diameter": inner_diameter,
                    "outer_diameter": outer_diameter
                }
            ))
    
    # MAP 2: Symmetry Groups
    symmetry_groups = phase4_result.get("symmetry", {}).get("symmetry_groups", [])
    conc_centers = [
        (cg.get("center"), sorted([round(r * 2, 4) for r in cg.get("radii", [])]))
        for cg in conc_groups
        if cg.get("center") and cg.get("radii")
    ]
    for idx, sg in enumerate(symmetry_groups):
        axis = sg.get("axis")
        axis_position = sg.get("axis_position")
        member_pairs = sg.get("member_pairs", [])
        
        if len(member_pairs) < 2:
            continue
        if axis in ("vertical", "horizontal") and axis_position is not None and len(conc_centers) >= 2:
            mirrored_mismatch = False
            for center_a, diameters_a in conc_centers:
                for center_b, diameters_b in conc_centers:
                    if center_a == center_b:
                        continue
                    if axis == "vertical":
                        mirrored = abs((center_a[0] + center_b[0]) / 2 - axis_position) < 0.01 and abs(center_a[1] - center_b[1]) < 0.01
                    else:
                        mirrored = abs((center_a[1] + center_b[1]) / 2 - axis_position) < 0.01 and abs(center_a[0] - center_b[0]) < 0.01
                    if mirrored and diameters_a != diameters_b:
                        mirrored_mismatch = True
                        break
                if mirrored_mismatch:
                    break
            if mirrored_mismatch:
                continue
        
        fids = []
        for pair in member_pairs:
            if isinstance(pair, (list, tuple)) and len(pair) >= 2:
                fid_a = entity_to_feature_id.get(pair[0])
                fid_b = entity_to_feature_id.get(pair[1])
                if fid_a:
                    fids.append(fid_a)
                if fid_b:
                    fids.append(fid_b)
            elif isinstance(pair, str):
                fid = entity_to_feature_id.get(pair)
                if fid:
                    fids.append(fid)
        unique_fids = []
        for fid in fids:
            if fid not in unique_fids:
                unique_fids.append(fid)

        if unique_fids:
            relationships.append(Relationship(
                relationship_id=f"mirror_symmetry_{axis}",
                relationship_type="mirror_symmetry",
                feature_ids=unique_fids,
                parameters={
                    "axis": axis,
                    "axis_position": axis_position,
                    "pair_count": len(member_pairs)
                }
            ))
    
    # MAP 3: Feature Hierarchy
    hierarchy_nodes = phase5_result.get("hierarchy", {}).get("hierarchy_nodes", [])
    for node in hierarchy_nodes:
        parent_id = node.get("parent_id")
        children_ids = node.get("children_ids", [])
        
        if parent_id and children_ids:
            relationships.append(Relationship(
                relationship_id=f"contains_{node.get('candidate_id')}",
                relationship_type="contains",
                feature_ids=[parent_id] + children_ids,
                parameters={
                    "parent_feature": parent_id,
                    "children": children_ids,
                    "depth": node.get("depth", 0)
                }
            ))
    
    return relationships


def determine_part_type(features: List[FeatureInstance]) -> str:
    classes = {f.feature_class for f in features}
    
    all_texts = []
    for f in features:
        if f.parameters:
            txt = f.parameters.get("text")
            if txt:
                all_texts.append(str(txt).upper())
            for dim in f.parameters.get("dimensions", []) + f.parameters.get("pattern_dimensions", []):
                dtxt = dim.get("text")
                if dtxt:
                    all_texts.append(str(dtxt).upper())
    combined_text = " ".join(all_texts)
    
    scores = {
        "bearing_housing": 0.0,
        "fastener": 0.0,
        "heatsink": 0.0,
        "gasket": 0.0,
        "structural_profile": 0.0,
        "sheet_metal": 0.0,
        "fitting": 0.0,
        "mechanical_component": 0.1
    }
    
    if "concentric_bore" in classes:
        has_large_bore = any(f.feature_class == "concentric_bore" and (f.parameters.get("bore_diameter") or 0) >= 20.0 for f in features)
        if has_large_bore:
            scores["bearing_housing"] += 2.5
            if "lube_port" in classes or "port" in classes:
                scores["bearing_housing"] += 2.0
            has_bearing_bore = any(f.feature_class == "concentric_bore" and f.parameters.get("bore_type") in ("bearing", "shaft") for f in features)
            if has_bearing_bore:
                scores["bearing_housing"] += 2.0
    if any(w in combined_text for w in ("BEARING", "BUSHING", "LUBE PORT", "SHAFT BORE", "HOUSING")):
        scores["bearing_housing"] += 1.5
        
    if "thread" in classes:
        scores["fastener"] += 3.0
    if any(fc in classes for fc in ("bolt", "screw", "hex_head", "hex_drive", "cylindrical_head")):
        scores["fastener"] += 2.5
    if any(w in combined_text for w in ("BOLT", "SCREW", "SHCS", "WASHER", "NUT", "SHOULDER SCREW")):
        scores["fastener"] += 2.0
    if _match_keyword(combined_text, "AF") or _match_keyword(combined_text, "A/F") or _match_keyword(combined_text, "ACROSS FLATS"):
        scores["fastener"] += 1.5
        
    if "heatsink_fin" in classes:
        scores["heatsink"] += 3.0
    if "heatsink_core" in classes:
        scores["heatsink"] += 3.0
    if any(w in combined_text for w in ("FIN", "HEATSINK", "COOLING", "THERMAL", "DRAFT ANGLE", "MOLD RELEASE", "STATOR")):
        scores["heatsink"] += 2.0
        
    if "alignment_tab" in classes or "o_ring" in classes:
        scores["gasket"] += 3.5
    if any(w in combined_text for w in ("GASKET", "SEAL", "O-RING", "ORING", "DOVETAIL", "GLAND", "CYLINDER HEAD")):
        scores["gasket"] += 2.0
        
    if "structural_profile" in classes:
        scores["structural_profile"] += 3.5
    for f in features:
        if f.feature_class == "structural_profile" and f.parameters:
            params = f.parameters
            if params.get("web_thickness") or params.get("flange_thickness") or params.get("wall_thickness"):
                scores["structural_profile"] += 2.0
    if any(w in combined_text for w in ("I-BEAM", "T-BAR", "C-CHANNEL", "LEG HEIGHT", "LEG WIDTH", "ROOT FILLET", "STRUCTURAL", "PROFILE")):
        scores["structural_profile"] += 2.0
        
    if "sheet_metal_bend" in classes or "bend_relief" in classes:
        scores["sheet_metal"] += 3.0
    if any(w in combined_text for w in ("BEND", "DEVELOPED LENGTH", "BLANK WIDTH", "FLAT PATTERN", "HINGE RELIEF")):
        scores["sheet_metal"] += 2.0
        
    if "fitting" in classes:
        scores["fitting"] += 3.5
    if any(w in combined_text for w in ("FITTING", "BUSHING", "NPT", "BARB", "FLOW", "PIPE")):
        scores["fitting"] += 2.0

    max_score = -1.0
    best_class = "mechanical_component"
    for k, v in scores.items():
        if v > max_score:
            max_score = v
            best_class = k
            
    if max_score < 1.5:
        return "mechanical_component"
        
    return best_class


# =====================================================================
# 3. PIPELINE ORCHESTRATION LAYER (SemanticPipeline)
# =====================================================================

class SemanticPipeline:
    """Orchestrate semantic enrichment, mapping and validation of drawings."""

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    def run(self, pipeline_result: dict[str, Any]) -> dict[str, Any]:
        """
        Build and validate semantic record from pipeline results.

        Args:
            pipeline_result: Dict containing results from upstream phases 1-6.

        Returns:
            Dict representation of the SemanticRecord.
        """
        drawing_id = pipeline_result.get("drawing_id", "unknown")
        logger.info(f"SemanticPipeline: building record for {drawing_id}")

        entities = pipeline_result.get("entities", [])
        phase3_result = pipeline_result.get("structural_result", {})
        phase4_result = pipeline_result.get("feature_result", {})
        phase5_result = pipeline_result.get("refinement_result", {})
        phase6_result = pipeline_result.get("context_result", {})

        # Step 1: Overall Dimensions
        overall_dimensions = reconstruct_dimensions(entities)
        logger.debug(
            f"{drawing_id}: Reconstructed dimensions: "
            f"width={overall_dimensions.get('width')}, "
            f"height={overall_dimensions.get('height')}"
        )

        # Step 2: Map Features
        # Step 2: Map Features
        features, entity_to_feature_id = map_features(
            entities,
            phase3_result,
            phase4_result,
            phase5_result
        )
        logger.debug(f"{drawing_id}: Mapped {len(features)} features")

        # Step 3: Map Relationships
        relationships = map_relationships(
            phase3_result,
            phase4_result,
            phase5_result,
            phase6_result,
            features,
            entity_to_feature_id
        )
        logger.debug(f"{drawing_id}: Mapped {len(relationships)} relationships")

        # Step 4: Extract Hierarchy
        hierarchy_nodes = phase5_result.get("hierarchy", {}).get("hierarchy_nodes", [])
        hierarchy = {
            "nodes": hierarchy_nodes,
            "root_count": len([n for n in hierarchy_nodes if n.get("parent_id") is None])
        } if hierarchy_nodes else None

        # Step 5: Classify Part Type
        part_type = determine_part_type(features)

        # Step 6: Assemble Record
        eng_rules = extract_engineering_rules(entities)
        metadata = {
            "feature_count": len(features),
            "relationship_count": len(relationships),
            "has_hierarchy": hierarchy is not None
        }
        if eng_rules:
            metadata["engineering_rules"] = eng_rules

        record = SemanticRecord(
            drawing_id=drawing_id,
            part_type=part_type,
            overall_dimensions=overall_dimensions,
            features=features,
            relationships=relationships,
            hierarchy=hierarchy,
            metadata=metadata
        )

        # Step 7: Validate Record
        if not self._validate(record):
            logger.warning(f"{drawing_id}: Semantic record validation checks failed")

        return record.to_dict()

    def _validate(self, record: SemanticRecord) -> bool:
        if not record.drawing_id:
            logger.error("Validation failed: missing drawing_id")
            return False
        if not record.part_type:
            logger.error("Validation failed: missing part_type")
            return False
        for feature in record.features:
            if not feature.feature_class:
                logger.error(f"Validation failed: feature {feature.feature_id} missing class")
                return False
            if not isinstance(feature.parameters, dict):
                logger.error(f"Validation failed: feature {feature.feature_id} parameters not a dict")
                return False
        return True


def extract_engineering_rules(entities: List[Dict]) -> Dict[str, Any]:
    rules = {}
    import re
    
    texts = []
    for ent in entities:
        if ent.get("entity_type") in ("TEXT", "MTEXT"):
            geom = ent.get("geometry", {})
            if geom.get("text_role") == "general_note" or "MATL" in str(geom.get("text")).upper() or "FILLETS" in str(geom.get("text")).upper():
                val = geom.get("text") or geom.get("content") or ""
                if val:
                    texts.append(val)
                    
    for ent in entities:
        if ent.get("entity_type") in ("TEXT", "MTEXT"):
            geom = ent.get("geometry", {})
            val = geom.get("text") or geom.get("content") or ""
            if "NOTES" in val.upper() or "MATL" in val.upper() or "BREAK ALL SHARP" in val.upper():
                if val not in texts:
                    texts.append(val)
                    
    for text in texts:
        lines = text.split("\n")
        for line in lines:
            line_upper = line.upper()
            
            if "MATL" in line_upper or "MATERIAL" in line_upper:
                m = re.search(r'(?:MATL|MATERIAL):\s*(.*)', line, re.IGNORECASE)
                if m:
                    rules["material"] = m.group(1).strip()
                else:
                    rules["material"] = line.replace("1. MATL:", "").replace("MATL:", "").strip()
            elif "GRAPHITE / SS316" in line_upper:
                rules["material"] = "Graphite / SS316"
                
            if "FILLET" in line_upper or "RADIUS" in line_upper or "RAD" in line_upper:
                m_r = re.search(r'R(\d+(\.\d+)?)', line_upper)
                if m_r:
                    val = float(m_r.group(1))
                    rules["default_fillet_radius"] = int(val) if val == int(val) else val
                    
            if "TOLERANCE" in line_upper or "±" in line_upper:
                m_t = re.search(r'±\s*(\d+(\.\d+)?)', line_upper)
                if m_t:
                    rules["general_tolerance"] = "±" + m_t.group(1)
                    
            if "CHAMFER" in line_upper:
                m_c = re.search(r'(\d+x\d+)(?:mm)?', line_upper)
                if m_c:
                    rules["default_chamfer"] = m_c.group(1)
                    
            if "SURFACE" in line_upper or "FINISH" in line_upper:
                m_sf = re.search(r'Ra\s*(\d+(\.\d+)?)', line_upper, re.IGNORECASE)
                if m_sf:
                    rules["surface_finish"] = "Ra" + m_sf.group(1)
                    
    return rules


def normalize_thread_size(val: Any, feature: Optional[Any] = None, drawing_id: Optional[str] = None) -> str:
    import re
    if val is None or val == "":
        return ""
    
    val_str = str(val).strip().upper()
    
    g_match = re.search(r'G\s*(\d+(?:/\d+)?)', val_str)
    if g_match:
        return f"G{g_match.group(1)}"
    if "BSPP" in val_str or "BSPT" in val_str or val_str.startswith("G"):
        frac_match = re.search(r'(\d+/\d+)', val_str)
        if frac_match:
            return f"G{frac_match.group(1)}"
    
    npt_match = re.search(r'NPT\s*(\d+(?:/\d+)?)', val_str)
    if npt_match:
        return f"NPT{npt_match.group(1)}"
    if "NPT" in val_str:
        frac_match = re.search(r'(\d+/\d+)', val_str)
        if frac_match:
            return f"NPT{frac_match.group(1)}"
    
    m_match = re.search(r'M\s*(\d+)', val_str)
    if m_match:
        return f"M{m_match.group(1)}"
        
    numeric_val = None
    try:
        numeric_val = float(val)
    except ValueError:
        pass
        
    if numeric_val is not None:
        designation = ""
        feature_class = ""
        if feature:
            feature_class = getattr(feature, "feature_class", "")
            fparams = getattr(feature, "parameters", {}) or {}
            designation = str(fparams.get("thread_designation") or fparams.get("port_thread") or fparams.get("text") or "").upper()
        
        fraction_str = ""
        if abs(numeric_val - 0.5) < 0.01:
            fraction_str = "1/2"
        elif abs(numeric_val - 0.25) < 0.01:
            fraction_str = "1/4"
        elif abs(numeric_val - 0.75) < 0.01:
            fraction_str = "3/4"
        elif abs(numeric_val - 0.375) < 0.01:
            fraction_str = "3/8"
        elif abs(numeric_val - 0.125) < 0.01:
            fraction_str = "1/8"
            
        if fraction_str:
            if "NPT" in designation or "TAPER" in designation:
                return f"NPT{fraction_str}"
            elif "G" in designation or "BSPP" in designation or "BSPT" in designation:
                return f"G{fraction_str}"
            
            drawing_id_upper = str(drawing_id).upper() if drawing_id else ""
            if "HEXBUSHING" in drawing_id_upper or "NPT" in drawing_id_upper:
                return f"NPT{fraction_str}"
            if "HOSEBARB" in drawing_id_upper or "COLDPLATE" in drawing_id_upper or "G_" in drawing_id_upper:
                return f"G{fraction_str}"
            return f"G{fraction_str}"
        else:
            return f"M{int(round(numeric_val))}"
            
    return ""
