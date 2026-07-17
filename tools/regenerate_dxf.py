"""
Regenerate malformed synthetic DXF files using ezdxf entity APIs only.

This script:
1. Identifies malformed DXF files (those that fail ezdxf.readfile)
2. Regenerates them using ONLY ezdxf entity APIs
3. Overwrites the malformed files with valid CAD-compatible DXFs

NEVER uses raw DXF string writing.
ALL geometry is created via ezdxf msp.add_* methods.
"""
import ezdxf
import os
import math
import random

DXF_DIR = "data/raw_dxf"


def is_malformed(path: str) -> bool:
    """Check if a DXF file fails to load."""
    try:
        ezdxf.readfile(path)
        return False
    except Exception:
        return True


def regenerate_industrial_part(path: str, seed: int) -> None:
    """
    Regenerate an industrial_part DXF using ezdxf APIs only.
    Creates closed LWPOLYLINE contours with engineering proportions.
    """
    rng = random.Random(seed)

    doc = ezdxf.new("R2010")
    msp = doc.modelspace()

    # Generate 8-20 closed contour features
    num_features = rng.randint(8, 20)
    x_offset = 0.0

    for i in range(num_features):
        # Feature dimensions
        w = round(rng.uniform(20.0, 300.0), 1)
        h = round(rng.uniform(10.0, 150.0), 1)
        x = round(x_offset + rng.uniform(10.0, 50.0), 1)
        y = round(rng.uniform(10.0, 200.0), 1)

        # Closed rectangular contour (LWPOLYLINE)
        pts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        msp.add_lwpolyline(pts, close=True)

        x_offset += w + rng.uniform(5.0, 30.0)

    doc.saveas(path)


def regenerate_synthetic_part(path: str, seed: int) -> None:
    """
    Regenerate a synthetic_part DXF using ezdxf APIs only.
    Creates mixed geometry: LWPOLYLINE + CIRCLE + TEXT annotations.
    """
    rng = random.Random(seed)

    doc = ezdxf.new("R2010")
    msp = doc.modelspace()

    # Outer boundary
    w = round(rng.uniform(100.0, 400.0), 1)
    h = round(rng.uniform(80.0, 300.0), 1)
    msp.add_lwpolyline(
        [(0, 0), (w, 0), (w, h), (0, h)],
        close=True
    )

    # Inner features (slots)
    num_slots = rng.randint(2, 8)
    for i in range(num_slots):
        sw = round(rng.uniform(20.0, 80.0), 1)
        sh = round(rng.uniform(8.0, 25.0), 1)
        sx = round(rng.uniform(10.0, w - sw - 10.0), 1)
        sy = round(rng.uniform(10.0, h - sh - 10.0), 1)
        msp.add_lwpolyline(
            [(sx, sy), (sx + sw, sy), (sx + sw, sy + sh), (sx, sy + sh)],
            close=True
        )

        # Dimension annotation text
        dim_val = round(sw, 1)
        msp.add_text(
            f"{dim_val}",
            dxfattribs={
                "insert": (sx + sw / 2, sy - 5.0),
                "height": 3.5,
                "layer": "DIM",
            }
        )

    # Circles (holes)
    num_holes = rng.randint(1, 4)
    for i in range(num_holes):
        r = round(rng.uniform(3.0, 15.0), 1)
        cx = round(rng.uniform(r + 5, w - r - 5), 1)
        cy = round(rng.uniform(r + 5, h - r - 5), 1)
        msp.add_circle((cx, cy), r)
        msp.add_text(
            f"Ø{r * 2:.1f}",
            dxfattribs={
                "insert": (cx + r + 2, cy),
                "height": 3.0,
                "layer": "DIM",
            }
        )

    doc.saveas(path)


def main():
    dxf_files = sorted(f for f in os.listdir(DXF_DIR) if f.endswith(".dxf"))
    malformed = []
    ok_count = 0

    print(f"Scanning {len(dxf_files)} DXF files...")

    for fname in dxf_files:
        path = os.path.join(DXF_DIR, fname)
        if is_malformed(path):
            malformed.append(fname)
        else:
            ok_count += 1

    print(f"  OK: {ok_count}")
    print(f"  Malformed: {len(malformed)}")

    if not malformed:
        print("No malformed files found. Nothing to regenerate.")
        return

    print(f"\nRegenerating {len(malformed)} malformed files...")

    for i, fname in enumerate(malformed):
        path = os.path.join(DXF_DIR, fname)
        seed = hash(fname) % 100000

        try:
            if fname.startswith("industrial_part_"):
                regenerate_industrial_part(path, seed)
            elif fname.startswith("synthetic_part_"):
                regenerate_synthetic_part(path, seed)
            else:
                # Generic: regenerate as industrial part
                regenerate_industrial_part(path, seed)

            # Verify it loads correctly
            ezdxf.readfile(path)
            print(f"  [OK] {fname}")

        except Exception as e:
            print(f"  [FAIL] {fname}: {e}")

    # Final validation
    print("\nFinal validation...")
    still_malformed = []
    for fname in malformed:
        path = os.path.join(DXF_DIR, fname)
        if is_malformed(path):
            still_malformed.append(fname)

    if still_malformed:
        print(f"  STILL MALFORMED: {still_malformed}")
    else:
        print(f"  All {len(malformed)} files regenerated successfully.")


if __name__ == "__main__":
    main()
