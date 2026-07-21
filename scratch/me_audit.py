"""
Mechanical Engineer audit of train.jsonl.
Flags issues in each record systematically.
"""
import json, math, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from pathlib import Path

subdirs = sorted(Path("data/intermediate").glob("2026_*"))
JSONL = (subdirs[-1] / "phase7_export" / "train.jsonl") if subdirs else Path(r"data/intermediate/2026_07_21_15_06_52/phase7_export/train.jsonl")

issues = []  # list of (drawing_id, severity, category, detail)

def flag(did, sev, cat, detail):
    issues.append((did, sev, cat, detail))

def check(rec):
    did = rec["drawing_id"]
    topo = rec.get("topology", {})
    feats = rec.get("features", [])
    rels  = rec.get("relationships", [])
    anns  = rec.get("annotations", [])
    dims  = rec.get("dimension_entities", [])
    cons  = rec.get("engineering_constraints", [])
    odim  = rec.get("overall_dimensions", {})

    # ── 1. engineering_constraints always empty ──────────────────────────────
    if not cons:
        flag(did, "WARN", "missing_constraints",
             "engineering_constraints=[] — no material, tolerance, or surface finish captured")

    # ── 2. symmetry relationships have empty feature_ids ────────────────────
    for r in rels:
        if r["relationship_type"] == "mirror_symmetry" and not r.get("feature_ids"):
            flag(did, "WARN", "unlinked_symmetry",
                 f"Relationship '{r['relationship_id']}' has feature_ids=[] — symmetry not linked to features")
            break  # one flag per drawing is enough

    # ── 3. concentric relationships reference non-existent feature IDs ───────
    feat_ids = {f["feature_id"] for f in feats}
    for r in rels:
        if r["relationship_type"] == "concentric":
            for fid in r.get("feature_ids", []):
                if fid not in feat_ids:
                    flag(did, "ERROR", "dangling_relationship",
                         f"Relationship '{r['relationship_id']}' references missing feature '{fid}'")

    # ── 4. nesting=0 when bore inside outer contour ──────────────────────────
    has_bore = any(f["feature_class"] == "concentric_bore" for f in feats)
    is_cross_section = any(k in did.lower() for k in ("bushing", "weldneck", "fitting", "coupling", "flange_sectional"))
    if has_bore and topo.get("nesting", 0) == 0 and not is_cross_section:
        flag(did, "WARN", "nesting_zero",
             "Has concentric_bore but topology.nesting=0 — inner loop not counted as nested")

    # ── 5. duplicate bore_diameter / inner_diameter fields ───────────────────
    for f in feats:
        p = f.get("parameters", {})
        if "bore_diameter" in p and "inner_diameter" in p:
            if p["bore_diameter"] == p["inner_diameter"]:
                flag(did, "INFO", "redundant_field",
                     f"Feature '{f['feature_id']}': bore_diameter == inner_diameter (same value duplicated)")
                break

    # ── 6. radial pattern — PCD set to hole_diameter (copy/paste bug) ────────
    for f in feats:
        if f["feature_class"] == "hole_pattern":
            p = f.get("parameters", {})
            pcd = p.get("pcd", 0)
            hdiam = p.get("hole_diameter", 0)
            if pcd > 0 and pcd == hdiam:
                flag(did, "ERROR", "pcd_equals_diameter",
                     f"Feature '{f['feature_id']}': pcd={pcd} == hole_diameter={hdiam} — PCD is clearly wrong")

    # ── 7. radial pattern — edge-to-edge hole interference check ─────────────
    for f in feats:
        if f["feature_class"] == "hole_pattern":
            p = f.get("parameters", {})
            n     = p.get("hole_count", 0)
            pcd   = p.get("pcd", 0)
            hdiam = p.get("hole_diameter", 0)
            if n > 1 and pcd > 0 and hdiam > 0:
                chord = 2 * (pcd / 2) * math.sin(math.pi / n)
                clearance = chord - hdiam
                if clearance < hdiam:  # edge dist < 1D
                    flag(did, "WARN", "tight_hole_clearance",
                         f"Feature '{f['feature_id']}': edge-edge clearance={clearance:.1f}mm < 1×D={hdiam}mm (tight for machining)")

    # ── 8. unknown_facts_container / dimension_annotations as real features ──
    junk_classes = {"unknown_facts", "dimension_annotations"}
    junk_feats = [f["feature_id"] for f in feats if f["feature_class"] in junk_classes]
    if junk_feats:
        flag(did, "WARN", "semantic_noise",
             f"Catch-all features pollute feature list: {junk_feats} — these are annotation artefacts, not engineering features")

    # ── 9. pocket perimeter_wall == pocket dimension (clearly wrong) ─────────
    for f in feats:
        if f["feature_class"] == "pocket":
            p = f.get("parameters", {})
            pw  = p.get("perimeter_wall", 0)
            plen = p.get("pocket_length", 0)
            pwid = p.get("pocket_width", 0)
            if pw and pw > 0 and (pw == plen or pw == pwid):
                flag(did, "ERROR", "pocket_wall_equals_dimension",
                     f"Feature '{f['feature_id']}': perimeter_wall={pw} == pocket_length or pocket_width — wall thickness is nonsensical")

    # ── 10. manufacturing_type mismatch ──────────────────────────────────────
    mfg = rec.get("manufacturing_type", "")
    part = rec.get("part_family", "")
    # Snap-fit / living hinge / shelled box are injection-moulded, not machined
    plastic_keywords = {"SnapFit", "LivingHinge", "ShelledBox", "CrushRibs", "ScrewBoss"}
    if mfg == "machined" and any(k in did for k in plastic_keywords):
        flag(did, "ERROR", "wrong_mfg_type",
             f"manufacturing_type='machined' but part name '{did}' is a plastic/injection-moulded feature — should be 'injection_moulded'")

    # ── 11. dimension value=null ──────────────────────────────────────────────
    for d in dims:
        if d.get("value") is None:
            flag(did, "WARN", "null_dimension",
                 f"Dimension handle '{d['handle']}' text='{d['text']}' has value=null — numeric extraction failed")

    # ── 12. Blueprint parts have no real features (only annotation artefacts) ─
    real_classes = {"concentric_bore","hole_pattern","hole_group","pocket","slot_array",
                    "fillet_group","radial_pattern","lube_port","port","bend_relief","structural_profile",
                    "heatsink_fin","heatsink_core","o_ring","channel","shoulder","cope","keyway",
                    "thread","bolt","screw","cylindrical_head","fitting","sheet_metal_bend",
                    "alignment_tab","rib","hex_head","hex_drive"}
    real_feats = [f for f in feats if f["feature_class"] in real_classes]
    if not real_feats:
        flag(did, "WARN", "no_real_features",
             "No real engineering features detected — only annotation/dimension artefacts remain")

    # ── 13. hole_group classified as rectangular when it's radial ────────────
    for f in feats:
        if f["feature_class"] == "hole_group":
            p = f.get("parameters", {})
            if p.get("group_type") == "rectangular_pattern":
                # check if positions lie on a circle
                positions = p.get("positions", [])
                if len(positions) >= 3:
                    cx = sum(x for x,y in positions) / len(positions)
                    cy = sum(y for x,y in positions) / len(positions)
                    radii = [math.hypot(x-cx, y-cy) for x,y in positions]
                    r_mean = sum(radii)/len(radii)
                    r_var  = max(abs(r - r_mean) for r in radii)
                    if r_var < 1.0 and r_mean > 10:  # all on same circle
                        flag(did, "WARN", "misclassified_pattern",
                             f"Feature '{f['feature_id']}': group_type='rectangular_pattern' but positions lie on a circle (r≈{r_mean:.1f}mm) — should be radial_pattern")

with JSONL.open() as fh:
    for line in fh:
        line = line.strip()
        if line:
            check(json.loads(line))

# ── Print report ─────────────────────────────────────────────────────────────
from collections import Counter
SEP = '=' * 70
print(f"\n{SEP}")
print(f"MECHANICAL ENGINEER AUDIT - {JSONL}")
print(f"{SEP}\n")
print(f"Total issues: {len(issues)}")
cat_counts = Counter(c for _, _, c, _ in issues)
for cat, n in cat_counts.most_common():
    print(f"  {n:3d}  {cat}")

print(f"\n{'-'*70}")
current = None
for did, sev, cat, detail in sorted(issues, key=lambda x: (x[0], x[1])):
    if did != current:
        print(f"\n[{did}]")
        current = did
    print(f"  [{sev}] {cat}: {detail}")
