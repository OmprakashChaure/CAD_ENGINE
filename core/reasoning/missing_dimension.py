import re
import json
import copy
from typing import Dict, List, Any

class MissingDimensionGenerator:
    """
    Stage 3 Module 1: Missing Dimension Generator.
    
    Converts fully constrained engineering drawings (semantic records)
    into under-dimensioned, mathematically solvable representations.
    """
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}

    def generate(self, semantic_record: Dict[str, Any], result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Generate missing dimension reasoning tasks.
        
        Args:
            semantic_record: The Stage 7 semantic representation of the drawing.
            result: The pipeline results containing raw entities and structural graphs.
            
        Returns:
            A list of task dictionary objects matching the Stage 3 schema.
        """
        tasks = []
        drawing_id = semantic_record.get("drawing_id")
        part_type = semantic_record.get("part_type", "mechanical_component")
        overall_dims = semantic_record.get("overall_dimensions", {})
        features = semantic_record.get("features", [])
        relationships = semantic_record.get("relationships", [])
        topology = semantic_record.get("metadata", {})
        
        width = overall_dims.get("width")
        height = overall_dims.get("height")
        
        # Gate 1: Check overall bounds exist
        if not width and not height:
            return []

        # 1. Pocket Dimension Loops
        # Loop Equation: pocket_length + 2 * perimeter_wall = overall_width
        pockets = [f for f in features if f.get("feature_class") == "pocket"]
        for p in pockets:
            params = p.get("parameters", {})
            p_len = params.get("pocket_length")
            p_wid = params.get("pocket_width")
            wall = params.get("perimeter_wall")
            
            # X-Axis loop
            if width and p_len and wall:
                if abs((2 * wall + p_len) - width) < 0.1:
                    # Task A: Mask pocket_length
                    t1 = self._create_pocket_task(
                        drawing_id=drawing_id,
                        overall_dims=overall_dims,
                        feature=p,
                        mask_prop="pocket_length",
                        mask_val=p_len,
                        other_params={"perimeter_wall": wall},
                        axis="X",
                        formula="pocket_length = width - 2 * perimeter_wall",
                        calc=f"{width} - 2 * {wall} = {p_len}",
                        relationships=relationships,
                        topology=topology
                    )
                    if t1:
                        tasks.append(t1)
                        
                    # Task B: Mask perimeter_wall
                    t2 = self._create_pocket_task(
                        drawing_id=drawing_id,
                        overall_dims=overall_dims,
                        feature=p,
                        mask_prop="perimeter_wall",
                        mask_val=wall,
                        other_params={"pocket_length": p_len},
                        axis="X",
                        formula="perimeter_wall = (width - pocket_length) / 2",
                        calc=f"({width} - {p_len}) / 2 = {wall}",
                        relationships=relationships,
                        topology=topology
                    )
                    if t2:
                        tasks.append(t2)
                        
            # Y-Axis loop
            if height and p_wid and wall:
                if abs((2 * wall + p_wid) - height) < 0.1:
                    # Task C: Mask pocket_width
                    t3 = self._create_pocket_task(
                        drawing_id=drawing_id,
                        overall_dims=overall_dims,
                        feature=p,
                        mask_prop="pocket_width",
                        mask_val=p_wid,
                        other_params={"perimeter_wall": wall},
                        axis="Y",
                        formula="pocket_width = height - 2 * perimeter_wall",
                        calc=f"{height} - 2 * {wall} = {p_wid}",
                        relationships=relationships,
                        topology=topology
                    )
                    if t3:
                        tasks.append(t3)
                        
                    # Task D: Mask perimeter_wall
                    t4 = self._create_pocket_task(
                        drawing_id=drawing_id,
                        overall_dims=overall_dims,
                        feature=p,
                        mask_prop="perimeter_wall",
                        mask_val=wall,
                        other_params={"pocket_width": p_wid},
                        axis="Y",
                        formula="perimeter_wall = (height - pocket_width) / 2",
                        calc=f"({height} - {p_wid}) / 2 = {wall}",
                        relationships=relationships,
                        topology=topology
                    )
                    if t4:
                        tasks.append(t4)

        # 2. Concentric Bore Wall Loops
        # Loop Equation: flange_diameter = inner_diameter + 2 * wall_thickness
        bores = [f for f in features if f.get("feature_class") == "concentric_bore"]
        for b in bores:
            params = b.get("parameters", {})
            o_dia = params.get("flange_diameter") or params.get("outer_diameter")
            i_dia = params.get("inner_diameter") or params.get("bore_diameter")
            
            if o_dia and i_dia and o_dia > i_dia:
                wall = (o_dia - i_dia) / 2.0
                # Task A: Mask inner_diameter
                t1 = self._create_bore_task(
                    drawing_id=drawing_id,
                    overall_dims=overall_dims,
                    feature=b,
                    mask_prop="inner_diameter",
                    mask_val=i_dia,
                    other_params={"outer_diameter": o_dia, "wall_thickness": wall},
                    formula="inner_diameter = outer_diameter - 2 * wall_thickness",
                    calc=f"{o_dia} - 2 * {wall} = {i_dia}",
                    relationships=relationships,
                    topology=topology
                )
                if t1:
                    tasks.append(t1)
                
                # Task B: Mask outer_diameter
                t2 = self._create_bore_task(
                    drawing_id=drawing_id,
                    overall_dims=overall_dims,
                    feature=b,
                    mask_prop="outer_diameter",
                    mask_val=o_dia,
                    other_params={"inner_diameter": i_dia, "wall_thickness": wall},
                    formula="outer_diameter = inner_diameter + 2 * wall_thickness",
                    calc=f"{i_dia} + 2 * {wall} = {o_dia}",
                    relationships=relationships,
                    topology=topology
                )
                if t2:
                    tasks.append(t2)

        # 3. Pattern Spacing Loops
        # Loop Equation: feature_span = spacing * (count - 1)
        hole_groups = [f for f in features if f.get("feature_class") == "hole_group"]
        for hg in hole_groups:
            params = hg.get("parameters", {})
            count = params.get("count")
            spacing = params.get("spacing_x") or params.get("spacing_y") or params.get("spacing")
            
            if count and spacing and count > 1:
                span = spacing * (count - 1)
                # Task A: Mask spacing
                t1 = self._create_pattern_task(
                    drawing_id=drawing_id,
                    overall_dims=overall_dims,
                    feature=hg,
                    mask_prop="spacing",
                    mask_val=spacing,
                    other_params={"count": count, "feature_span": span},
                    formula="spacing = feature_span / (count - 1)",
                    calc=f"{span} / ({count} - 1) = {spacing}",
                    relationships=relationships,
                    topology=topology
                )
                if t1:
                    tasks.append(t1)
                    
                # Task B: Mask count
                t2 = self._create_pattern_task(
                    drawing_id=drawing_id,
                    overall_dims=overall_dims,
                    feature=hg,
                    mask_prop="count",
                    mask_val=count,
                    other_params={"spacing": spacing, "feature_span": span},
                    formula="count = (feature_span / spacing) + 1",
                    calc=f"({span} / {spacing}) + 1 = {count}",
                    relationships=relationships,
                    topology=topology
                )
                if t2:
                    tasks.append(t2)

        return tasks

    def _create_pocket_task(self, drawing_id, overall_dims, feature, mask_prop, mask_val, other_params, axis, formula, calc, relationships, topology):
        inq_params = {mask_prop: None}
        for k, v in other_params.items():
            inq_params[k] = v
            
        context = {
            "part_family": feature.get("feature_class"),
            "overall_dimensions": overall_dims,
            "inquiry_feature": {
                "feature_class": feature.get("feature_class"),
                "visible_parameters": inq_params
            },
            "neighbour_features": [],
            "relationships": self._mask_target_relationship_values(relationships, mask_prop),
            "topology": topology
        }
        
        task_display = mask_prop.replace("_", " ").title()
        pocket_details = ", ".join(f"{k.replace('_', ' ').title()} = {v} mm" for k, v in other_params.items())
        user_prompt = (
            f"Task:\nInfer the missing {task_display.lower()} for drawing '{drawing_id}'.\n\n"
            f"Drawing Description:\n"
            f"The overall plate dimensions are {overall_dims.get('width')} mm x {overall_dims.get('height')} mm.\n"
            f"The drawing details a Pocket feature with {pocket_details}.\n\n"
            f"Question:\nBased on the drawing layout and dimensions, infer the missing {task_display.lower()} in mm."
        )
        
        # Validation Gate: Leakage Prevention
        if self._detect_leakage(mask_val, user_prompt):
            return None
            
        return self._build_task_dict(drawing_id, context, mask_prop, mask_val, user_prompt, formula, calc, f"{axis}-axis pocket dimension loop")

    def _create_bore_task(self, drawing_id, overall_dims, feature, mask_prop, mask_val, other_params, formula, calc, relationships, topology):
        inq_params = {mask_prop: None}
        for k, v in other_params.items():
            inq_params[k] = v
            
        context = {
            "part_family": feature.get("feature_class"),
            "overall_dimensions": overall_dims,
            "inquiry_feature": {
                "feature_class": feature.get("feature_class"),
                "visible_parameters": inq_params
            },
            "neighbour_features": [],
            "relationships": self._mask_target_relationship_values(relationships, mask_prop),
            "topology": topology
        }
        
        task_display = mask_prop.replace("_", " ").title()
        bore_details = ", ".join(f"{k.replace('_', ' ').title()} = {v} mm" for k, v in other_params.items())
        user_prompt = (
            f"Task:\nInfer the missing {task_display.lower()} for drawing '{drawing_id}'.\n\n"
            f"Drawing Description:\n"
            f"The drawing details a Concentric Bore feature with {bore_details}.\n\n"
            f"Question:\nBased on the drawing layout and dimensions, infer the missing {task_display.lower()} in mm."
        )
        
        if self._detect_leakage(mask_val, user_prompt):
            return None
            
        return self._build_task_dict(drawing_id, context, mask_prop, mask_val, user_prompt, formula, calc, "Concentric bore wall thickness loop")

    def _create_pattern_task(self, drawing_id, overall_dims, feature, mask_prop, mask_val, other_params, formula, calc, relationships, topology):
        inq_params = {mask_prop: None}
        for k, v in other_params.items():
            inq_params[k] = v
            
        context = {
            "part_family": feature.get("feature_class"),
            "overall_dimensions": overall_dims,
            "inquiry_feature": {
                "feature_class": feature.get("feature_class"),
                "visible_parameters": inq_params
            },
            "neighbour_features": [],
            "relationships": self._mask_target_relationship_values(relationships, mask_prop),
            "topology": topology
        }
        
        task_display = mask_prop.replace("_", " ").title()
        unit_str = "" if mask_prop == "count" else " in mm"
        val_suffix = "" if mask_prop == "count" else " mm"
        
        param_list = []
        for k, v in other_params.items():
            name = k.replace("_", " ").title()
            val_str = str(v) if k == "count" else f"{v} mm"
            param_list.append(f"{name} = {val_str}")
            
        user_prompt = (
            f"Task:\nInfer the missing {task_display.lower()} for drawing '{drawing_id}'.\n\n"
            f"Drawing Description:\n"
            f"The drawing details a Hole Group pattern with {', '.join(param_list)}.\n\n"
            f"Question:\nBased on the drawing layout and dimensions, infer the missing {task_display.lower()}{unit_str}."
        )
        
        if self._detect_leakage(mask_val, user_prompt):
            return None
            
        return self._build_task_dict(drawing_id, context, mask_prop, mask_val, user_prompt, formula, calc, "Linear spacing array loop")

    def _detect_leakage(self, value: Any, text: str) -> bool:
        """Verify the target value is not leaked inside the instruction text."""
        val_str = str(value)
        escaped_val = re.escape(val_str)
        # Check boundary matches to ensure it doesn't appear as a standalone number
        if re.search(rf'(?<![\d.]){escaped_val}(?![\d.])', text):
            return True
        # Check float conversion leakage
        try:
            f_val = float(value)
            i_val = int(f_val)
            if f_val == i_val:
                patterns = [rf'(?<![\d.]){i_val}(?![\d.])', rf'(?<![\d.]){i_val}\.0+(?![\d.])']
            else:
                patterns = [rf'(?<![\d.]){f_val}(?![\d.])']
            for pat in patterns:
                if re.search(pat, text):
                    return True
        except (ValueError, TypeError):
            pass
        return False

    def _mask_target_relationship_values(self, relationships: List[Dict[str, Any]], target_property: str) -> List[Dict[str, Any]]:
        """Keep relationship structure while hiding any direct copy of the target property."""
        def mask(node: Any) -> Any:
            if isinstance(node, dict):
                return {
                    key: (None if key == target_property else mask(value))
                    for key, value in node.items()
                }
            if isinstance(node, list):
                return [mask(item) for item in node]
            return copy.deepcopy(node)

        return mask(relationships)

    def _build_task_dict(self, drawing_id, context, mask_prop, mask_val, user_prompt, formula, calc, loop_type):
        return {
            "drawing_id": drawing_id,
            "task_class": "missing_dimension",
            "context": context,
            "target": {
                "property": mask_prop,
                "value": mask_val
            },
            "system": (
                "You are an expert mechanical engineering assistant specializing in engineering drawings and CAD reasoning. "
                "Infer missing engineering dimensions and properties from the provided engineering context."
            ),
            "user": user_prompt,
            "assistant": str(mask_val),
            "reasoning_metadata": {
                "loop_type": loop_type,
                "formula": formula,
                "calculation": calc,
                "complexity_steps": len(formula.split(" ")) // 2
            }
        }
