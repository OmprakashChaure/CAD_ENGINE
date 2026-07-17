import re
from typing import Dict, Optional, Tuple
from pydantic import BaseModel, Field

from utils.standards_lookup import StandardsLookup


class ParsedAnnotation(BaseModel):
    annotation_type: str  # "thread" | "counterbore" | "chamfer" | "radius" | "tolerance" | "fit" | "unknown"
    source_annotation: str
    validation_status: str  # "validated" | "fallback" | "unvalidated"

    # Thread specific
    thread_standard: Optional[str] = None
    nominal_diameter: Optional[float] = None
    thread_pitch: Optional[float] = None
    thread_gender: Optional[str] = None
    tolerance_class: Optional[str] = None
    nominal_pipe_size: Optional[str] = None
    major_diameter: Optional[float] = None
    pitch_tpi: Optional[float] = None
    taper: Optional[float] = None
    quantity: Optional[int] = None
    role: Optional[str] = None

    # Counterbore specific
    counterbore_diameter: Optional[float] = None
    counterbore_depth: Optional[float] = None

    # Chamfer specific
    chamfer_size: Optional[float] = None
    chamfer_angle: Optional[float] = None

    # Radius specific
    radius_value: Optional[float] = None

    # Tolerance specific
    tolerance_upper: Optional[float] = None
    tolerance_lower: Optional[float] = None

    # Fit specific
    fit_class: Optional[str] = None
    lower_deviation: Optional[float] = None
    upper_deviation: Optional[float] = None


class AnnotationParser:
    """
    Modular, deterministic engineering parser for annotation text.
    Queries StandardLookup configuration tables.
    """

    def __init__(self):
        self.lookup = StandardsLookup()

    def normalize(self, text: str) -> str:
        """Clean and prepare annotation string."""
        if not text:
            return ""
        # Clean control characters and normalize to upper case
        cleaned = text.upper().strip()
        cleaned = cleaned.replace("%%C", "Ø")
        cleaned = cleaned.replace("\\P", " ")
        cleaned = cleaned.replace("\\", " ")
        return re.sub(r"\s+", " ", cleaned).strip()

    def parse(self, text: str) -> ParsedAnnotation:
        """
        Parse raw annotation into structured properties.
        """
        normalized = self.normalize(text)
        if not normalized:
            return ParsedAnnotation(
                annotation_type="unknown",
                source_annotation=text,
                validation_status="unvalidated",
            )

        # 1. Quantity Check (e.g. 6X ...)
        quantity = None
        quantity_match = re.match(r"^(\d+)\s*[Xx]\s+(.*)$", normalized)
        core_text = normalized
        if quantity_match:
            quantity = int(quantity_match.group(1))
            core_text = quantity_match.group(2).strip()

        # 2. Match Metric Threads (e.g. M12, M12X1.75, M12X1.75-6G)
        metric_match = re.match(
            r"^M(\d+(?:\.\d+)?)(?:\s*[Xx]\s*(\d+(?:\.\d+)?))?(?:\s*-\s*(\d+)?([a-zA-Z]))?(?:\s+(.*))?$",
            core_text,
        )
        if metric_match:
            nominal_d = float(metric_match.group(1))
            pitch = metric_match.group(2)
            tol_grade = metric_match.group(3)
            tol_pos = metric_match.group(4)
            rem = metric_match.group(5) or ""

            # Check if internal or external thread gender
            gender = None
            if "INTERNAL" in rem or "FEMALE" in rem or "TAP" in rem:
                gender = "internal"
            elif "EXTERNAL" in rem or "MALE" in rem or "BOLT" in rem:
                gender = "external"

            tol_class = None
            if tol_grade or tol_pos:
                tol_class = f"{tol_grade or ''}{tol_pos or ''}"

            validation = "unvalidated"
            thread_pitch = None
            if pitch:
                thread_pitch = float(pitch)
                # Verify pitch matches standards
                std_pitch = self.lookup.get_metric_coarse_pitch(nominal_d)
                if std_pitch and abs(std_pitch - thread_pitch) < 0.01:
                    validation = "validated"
                else:
                    std_fine = self.lookup.get_metric_fine_pitch(nominal_d)
                    if std_fine and abs(std_fine - thread_pitch) < 0.01:
                        validation = "validated"
            else:
                # Query coarse pitch lookup fallback
                std_pitch = self.lookup.get_metric_coarse_pitch(nominal_d)
                if std_pitch:
                    thread_pitch = std_pitch
                    validation = "fallback"

            role = rem.strip() if rem else None

            return ParsedAnnotation(
                annotation_type="thread",
                source_annotation=text,
                validation_status=validation,
                thread_standard="ISO Metric",
                nominal_diameter=nominal_d,
                thread_pitch=thread_pitch,
                thread_gender=gender,
                tolerance_class=tol_class,
                quantity=quantity,
                role=role,
            )

        # 3. Match Unified Threads (e.g. 1/2-13 UNC, 3/8-24 UNF)
        unified_match = re.match(
            r"^(\d+(?:/\d+)?)\s*-\s*(\d+)\s*(UNC|UNF)(?:\s+(.*))?$", core_text
        )
        if unified_match:
            size_frac = unified_match.group(1)
            tpi = int(unified_match.group(2))
            series = unified_match.group(3)
            rem = unified_match.group(4) or ""

            # Convert size fraction to major diameter in mm
            major_d = None
            if "/" in size_frac:
                parts = size_frac.split("/")
                major_d = (float(parts[0]) / float(parts[1])) * 25.4
            else:
                major_d = float(size_frac) * 25.4

            validation = "unvalidated"
            # Verify TPI against standard tables
            std_tpi = None
            if series == "UNC":
                std_tpi = self.lookup.get_unc_tpi(size_frac)
            elif series == "UNF":
                std_tpi = self.lookup.get_unf_tpi(size_frac)

            if std_tpi and std_tpi == tpi:
                validation = "validated"

            pitch = 25.4 / tpi
            role = rem.strip() if rem else None

            return ParsedAnnotation(
                annotation_type="thread",
                source_annotation=text,
                validation_status=validation,
                thread_standard=series,
                nominal_diameter=round(major_d, 4) if major_d else None,
                thread_pitch=round(pitch, 4),
                pitch_tpi=float(tpi),
                nominal_pipe_size=size_frac,
                quantity=quantity,
                role=role,
            )

        # 4. Match Pipe Threads (e.g. G1/4 BSPP, NPT1/2)
        pipe_match = re.match(
            r"^(G|NPT)\s*(\d+(?:/\d+)?)(?:\s+(BSPP|BSPT))?(?:\s+(.*))?$",
            core_text,
        )
        if pipe_match:
            standard_type = pipe_match.group(1)
            size_frac = pipe_match.group(2)
            sub_type = pipe_match.group(3) or ""
            rem = pipe_match.group(4) or ""

            validation = "unvalidated"
            major_d = None
            tpi = None
            taper = 0.0

            if standard_type == "G":
                std_data = self.lookup.get_bsp_parallel_g(size_frac)
                if std_data:
                    major_d = std_data["major_diameter"]
                    tpi = std_data["pitch_tpi"]
                    validation = "validated"
                thread_std = "BSPP" if "BSPP" in sub_type else "BSP"
            else:  # NPT
                std_data = self.lookup.get_npt_taper(size_frac)
                if std_data:
                    major_d = std_data["major_diameter"]
                    tpi = std_data["pitch_tpi"]
                    taper = std_data["taper"]
                    validation = "validated"
                thread_std = "NPT"

            pitch = 25.4 / tpi if tpi else None
            role = rem.strip() if rem else None

            return ParsedAnnotation(
                annotation_type="thread",
                source_annotation=text,
                validation_status=validation,
                thread_standard=thread_std,
                nominal_diameter=major_d,
                thread_pitch=round(pitch, 4) if pitch else None,
                pitch_tpi=float(tpi) if tpi else None,
                nominal_pipe_size=size_frac,
                taper=taper,
                quantity=quantity,
                role=role,
            )

        # 5. Match Counterbores (e.g. CBORE Ø20MM X 10MM DEEP)
        cbore_match = re.match(
            r"^(?:CBORE|PCBORE)\s+Ø?\s*(\d+(?:\.\d+)?)(?:MM)?(?:\s*[Xx]\s*(\d+(?:\.\d+)?)(?:MM)?(?:\s*DEEP|\s*DEPTH)?)?$",
            core_text,
        )
        if cbore_match:
            cb_dia = float(cbore_match.group(1))
            cb_depth = cbore_match.group(2)
            return ParsedAnnotation(
                annotation_type="counterbore",
                source_annotation=text,
                validation_status="validated",
                counterbore_diameter=cb_dia,
                counterbore_depth=float(cb_depth) if cb_depth else None,
                quantity=quantity,
            )

        # 6. Match Chamfers (e.g. CHAMFER 2MM X 45 DEG)
        chamfer_match = re.match(
            r"^CHAMFER\s+(\d+(?:\.\d+)?)(?:MM)?(?:\s*[Xx]\s*(\d+(?:\.\d+)?)\s*(?:DEG|D)?)?$",
            core_text,
        )
        if chamfer_match:
            c_size = float(chamfer_match.group(1))
            c_angle = chamfer_match.group(2)
            return ParsedAnnotation(
                annotation_type="chamfer",
                source_annotation=text,
                validation_status="validated",
                chamfer_size=c_size,
                chamfer_angle=float(c_angle) if c_angle else 45.0,
                quantity=quantity,
            )

        # 7. Match Radius (e.g. R10, RADIUS 15)
        radius_match = re.match(
            r"^(?:R|RADIUS)\s*(\d+(?:\.\d+)?)$", core_text
        )
        if radius_match:
            r_val = float(radius_match.group(1))
            return ParsedAnnotation(
                annotation_type="radius",
                source_annotation=text,
                validation_status="validated",
                radius_value=r_val,
                quantity=quantity,
            )

        # 8. Match Tolerances (e.g. ±0.05, +0.02/-0.01)
        tol_match1 = re.match(r"^±\s*(\d+(?:\.\d+)?)$", core_text)
        if tol_match1:
            val = float(tol_match1.group(1))
            return ParsedAnnotation(
                annotation_type="tolerance",
                source_annotation=text,
                validation_status="validated",
                tolerance_upper=val,
                tolerance_lower=-val,
                quantity=quantity,
            )

        tol_match2 = re.match(
            r"^\+\s*(\d+(?:\.\d+)?)\s*/\s*-\s*(\d+(?:\.\d+)?)$", core_text
        )
        if tol_match2:
            val_u = float(tol_match2.group(1))
            val_l = float(tol_match2.group(2))
            return ParsedAnnotation(
                annotation_type="tolerance",
                source_annotation=text,
                validation_status="validated",
                tolerance_upper=val_u,
                tolerance_lower=-val_l,
                quantity=quantity,
            )

        # 9. Match Fits (e.g. 50H7, 20G6)
        fit_match = re.match(r"^(\d+(?:\.\d+)?)\s*(H7|G6)$", core_text)
        if fit_match:
            diameter = float(fit_match.group(1))
            f_class = fit_match.group(2)
            dev = self.lookup.get_fit_deviation(f_class, diameter)
            validation = "unvalidated"
            l_dev, u_dev = None, None
            if dev:
                l_dev, u_dev = dev
                validation = "validated"

            return ParsedAnnotation(
                annotation_type="fit",
                source_annotation=text,
                validation_status=validation,
                fit_class=f_class,
                lower_deviation=l_dev,
                upper_deviation=u_dev,
                nominal_diameter=diameter,
                quantity=quantity,
            )

        return ParsedAnnotation(
            annotation_type="unknown",
            source_annotation=text,
            validation_status="unvalidated",
            quantity=quantity,
        )
