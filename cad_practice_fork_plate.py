
import ezdxf
import math
from collections import Counter
from ezdxf.lldxf.const import DXFTableEntryError

# --- MASTER RULE #1: FULLY COMPLIANT VALIDATOR ---
class DXFValidationException(Exception): pass

class CADValidator:
    @staticmethod
    def validate_closed_contours(msp, tolerance=3):
        endpoints = []
        for entity in msp.query('LINE ARC LWPOLYLINE'):
            if entity.dxf.layer != 'GEOMETRY': continue
            
            # RULE: Correct Arc logic to prevent AttributeError
            if entity.dxftype() == 'ARC':
                center = entity.dxf.center
                r = entity.dxf.radius
                sa = math.radians(entity.dxf.start_angle)
                ea = math.radians(entity.dxf.end_angle)
                endpoints.append((round(center.x + r * math.cos(sa), tolerance), round(center.y + r * math.sin(sa), tolerance)))
                endpoints.append((round(center.x + r * math.cos(ea), tolerance), round(center.y + r * math.sin(ea), tolerance)))
            
            # RULE: Correct LWPOLYLINE logic
            elif entity.dxftype() == 'LWPOLYLINE':
                pts = entity.get_points(format='xy')
                for i in range(len(pts)):
                    p1 = pts[i]
                    p2 = pts[(i + 1) % len(pts)] if entity.closed else pts[min(i + 1, len(pts)-1)]
                    endpoints.append((round(p1[0], tolerance), round(p1[1], tolerance)))
                    endpoints.append((round(p2[0], tolerance), round(p2[1], tolerance)))
            
            # RULE: Correct LINE logic
            elif entity.dxftype() == 'LINE':
                endpoints.append((round(entity.dxf.start.x, tolerance), round(entity.dxf.start.y, tolerance)))
                endpoints.append((round(entity.dxf.end.x, tolerance), round(entity.dxf.end.y, tolerance)))
                
        vertex_counts = Counter(endpoints)
        open_vertices = [v for v, count in vertex_counts.items() if count == 1]
        if open_vertices: raise DXFValidationException(f"Open profile at: {open_vertices[:3]}")
        return True

# --- MASTER RULE #2: COMPLIANT GENERATOR ---
class PlateGenerator:
    def __init__(self):
        self.doc = ezdxf.new('R2010', setup=True)
        self.msp = self.doc.modelspace()
        for l in ["GEOMETRY", "DIMENSIONS", "CENTERLINES", "DETAILS"]:
            self.doc.layers.add(l)
        try:
            self.dimstyle = self.doc.dimstyles.new("STRUCTURAL_STYLE")
        except DXFTableEntryError:
            self.dimstyle = self.doc.dimstyles.get("STRUCTURAL_STYLE")
            
    def build_plate(self):
        # GEOMETRY (Rule: Airtight)
        self.msp.add_line((-35, 0), (35, 0), dxfattribs={'layer': 'GEOMETRY'})
        self.msp.add_line((-35, 0), (-35, 60), dxfattribs={'layer': 'GEOMETRY'})
        self.msp.add_line((35, 0), (35, 60), dxfattribs={'layer': 'GEOMETRY'})
        self.msp.add_arc((0, 60), 35, 0, 180, dxfattribs={'layer': 'GEOMETRY'})
        self.msp.add_circle((0, 60), 20, dxfattribs={'layer': 'GEOMETRY'})
        self.msp.add_lwpolyline([(-25, 30), (25, 30), (25, 45), (-25, 45)], close=True, dxfattribs={'layer': 'GEOMETRY'})
        
        # CENTERLINES
        self.msp.add_line((0, -10), (0, 100), dxfattribs={'layer': 'CENTERLINES'})
        self.msp.add_line((-45, 60), (45, 60), dxfattribs={'layer': 'CENTERLINES'})
        
        # VALIDATE AND SAVE
        CADValidator.validate_closed_contours(self.msp)
        self.doc.saveas("AR05_Plate_Page7_Final.dxf")
        print("PASS: AR05_Plate_Page7_Final.dxf validated and saved.")

if __name__ == "__main__":
    PlateGenerator().build_plate()