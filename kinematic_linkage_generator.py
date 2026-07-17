import ezdxf
import math
from collections import Counter

class DXFValidationException(Exception):
    pass

class CADValidator:
    @staticmethod
    def validate_closed_contours(msp, tolerance=2):
        endpoints = []
        for entity in msp.query('LINE ARC LWPOLYLINE CIRCLE'):
            if entity.dxf.layer != 'GEOMETRY':
                continue
            
            if entity.dxftype() == 'CIRCLE':
                continue 
                
            if entity.dxftype() == 'LINE':
                endpoints.append((round(entity.dxf.start.x, tolerance), round(entity.dxf.start.y, tolerance)))
                endpoints.append((round(entity.dxf.end.x, tolerance), round(entity.dxf.end.y, tolerance)))
            elif entity.dxftype() == 'ARC':
                center = entity.dxf.center
                r = entity.dxf.radius
                sa = math.radians(entity.dxf.start_angle)
                ea = math.radians(entity.dxf.end_angle)
                endpoints.append((round(center.x + r * math.cos(sa), tolerance), round(center.y + r * math.sin(sa), tolerance)))
                endpoints.append((round(center.x + r * math.cos(ea), tolerance), round(center.y + r * math.sin(ea), tolerance)))
            elif entity.dxftype() == 'LWPOLYLINE':
                if not entity.closed:
                    pts = list(entity.vertices())
                    endpoints.append((round(pts[0][0], tolerance), round(pts[0][1], tolerance)))
                    endpoints.append((round(pts[-1][0], tolerance), round(pts[-1][1], tolerance)))
                
        vertex_counts = Counter(endpoints)
        open_vertices = [v for v, count in vertex_counts.items() if count == 1]
        if open_vertices:
            raise DXFValidationException(f"Open profile detected. Hanging vertices at: {open_vertices[:3]}")
        return True

    @staticmethod
    def validate_clean_export(doc):
        allowed_layers = {"GEOMETRY", "DIMENSIONS", "CENTERLINES", "0", "Defpoints"}
        for layer in doc.layers:
            if layer.dxf.name not in allowed_layers:
                raise DXFValidationException(f"Prohibited layer found: {layer.dxf.name}. Remove construction geometry.")
        return True

    @staticmethod
    def validate_reasoning_supervision(msp, required_keywords):
        dim_texts = [dim.dxf.text.upper() for dim in msp.query('DIMENSION') if dim.has_dxf_attrib('text')]
        mtext_texts = [mtext.text.upper() for mtext in msp.query('MTEXT')]
        
        all_text = " ".join(dim_texts + mtext_texts)
        for keyword in required_keywords:
            if keyword.upper() not in all_text:
                raise DXFValidationException(f"Missing Reasoning Supervision: Required feature '{keyword}' not annotated.")
        return True

class KinematicGenerator:
    def __init__(self):
        self.doc = None
        self.msp = None

    def _reset_document(self):
        self.doc = ezdxf.new('R2010', setup=True)
        self.msp = self.doc.modelspace()
        
        self.doc.layers.add("GEOMETRY", color=7, lineweight=50)       
        self.doc.layers.add("DIMENSIONS", color=7, lineweight=25)     
        
        if "CENTER" not in self.doc.linetypes:
            self.doc.linetypes.add("CENTER", pattern="A, 15, -3, 3, -3", description="Center ____ _ ____")
        self.doc.layers.add("CENTERLINES", color=7, linetype="CENTER", lineweight=25) 

        if "ENGINEERING_STYLE" not in self.doc.dimstyles:
            dimstyle = self.doc.dimstyles.new("ENGINEERING_STYLE")
            dimstyle.dxf.dimtxt = 2.5     
            dimstyle.dxf.dimasz = 2.5     
            dimstyle.dxf.dimtad = 1       
            dimstyle.dxf.dimgap = 0.8     
            dimstyle.dxf.dimexe = 1.0     
            dimstyle.dxf.dimexo = 1.5     
            dimstyle.dxf.dimdec = 2       
            dimstyle.dxf.dimtfill = 1  

    def add_dim(self, base, p1, p2, text="", angle=0):
        dim = self.msp.add_linear_dim(
            base=base, p1=p1, p2=p2, angle=angle, text=text, 
            dimstyle="ENGINEERING_STYLE", dxfattribs={'layer': 'DIMENSIONS'}
        )
        dim.render()

    def add_leader(self, target, text_pos, text):
        self.msp.add_leader(
            vertices=[target, text_pos], 
            dimstyle="ENGINEERING_STYLE", 
            dxfattribs={'layer': 'DIMENSIONS'}
        )
        self.msp.add_mtext(
            text, 
            dxfattribs={'char_height': 2.5, 'layer': 'DIMENSIONS'}
        ).set_location(text_pos)

    def add_center_mark(self, cx, cy, size):
        self.msp.add_line((cx - size, cy), (cx + size, cy), dxfattribs={'layer': 'CENTERLINES'})
        self.msp.add_line((cx, cy - size), (cx, cy + size), dxfattribs={'layer': 'CENTERLINES'})

    def validate_and_save(self, filename, required_keywords):
        try:
            CADValidator.validate_closed_contours(self.msp)
            CADValidator.validate_clean_export(self.doc)
            CADValidator.validate_reasoning_supervision(self.msp, required_keywords)
            self.doc.saveas(filename)
            print(f"PASS: {filename} (Supervising: {', '.join(required_keywords)})")
        except DXFValidationException as e:
            print(f"FAIL: {filename} - {str(e)}")

    # =================================================================
    # LK01: Eccentric Lobe Cam (Teaches Offset Centers & Lift)
    # =================================================================
    def build_LK01_eccentric_cam(self):
        self._reset_document()
        pivot_x, pivot_y = 100, 100
        cam_x, cam_y = 100, 125 # Cam lobe is offset 25mm vertically
        
        # Outer Cam Profile (Eccentric Circle)
        self.msp.add_circle((cam_x, cam_y), radius=50, dxfattribs={'layer': 'GEOMETRY'})
        self.add_center_mark(cam_x, cam_y, 60) # Center of the lobe
        
        # Pivot Bore (Where the shaft goes)
        self.msp.add_circle((pivot_x, pivot_y), radius=15, dxfattribs={'layer': 'GEOMETRY'})
        self.add_center_mark(pivot_x, pivot_y, 30) # Center of rotation
        
        # Keyway on the pivot
        kw_w, kw_d = 8, 18.3
        ang = math.degrees(math.asin((kw_w/2) / 15))
        self.msp.add_arc((pivot_x, pivot_y), radius=15, start_angle=90+ang, end_angle=90-ang, dxfattribs={'layer': 'GEOMETRY'})
        self.msp.add_line((pivot_x-kw_w/2, pivot_y+15*math.cos(math.radians(ang))), (pivot_x-kw_w/2, pivot_y+kw_d), dxfattribs={'layer': 'GEOMETRY'})
        self.msp.add_line((pivot_x+kw_w/2, pivot_y+15*math.cos(math.radians(ang))), (pivot_x+kw_w/2, pivot_y+kw_d), dxfattribs={'layer': 'GEOMETRY'})
        self.msp.add_line((pivot_x-kw_w/2, pivot_y+kw_d), (pivot_x+kw_w/2, pivot_y+kw_d), dxfattribs={'layer': 'GEOMETRY'})

        # Dimensions (Massive offsets)
        self.add_dim((-30, pivot_y), (pivot_x, pivot_y), (cam_x, cam_y), angle=90, text="25mm %%P0.05 ECCENTRIC OFFSET")
        self.add_dim((cam_x, cam_y + 90), (cam_x - 50, cam_y), (cam_x + 50, cam_y), text="%%C100mm CAM PROFILE")
        
        # Critical Lift Dimension (From pivot center to top of lobe)
        self.add_dim((230, pivot_y), (pivot_x, pivot_y), (cam_x, cam_y + 50), angle=90, text="75mm MAX LIFT")
        
        self.add_leader(target=(pivot_x+10, pivot_y-10), text_pos=(180, 40), text="%%C30mm H7 PIVOT BORE\\P W/ 8mm KEYWAY")

        self.validate_and_save("Kinematic_LK01_EccentricCam.dxf", ["ECCENTRIC", "LIFT", "H7"])

    # =================================================================
    # LK02: Connecting Rod (Teaches Tangent Blends & Pitch Distance)
    # =================================================================
    def build_LK02_connecting_rod(self):
        self._reset_document()
        c1x, c1y = 100, 100 # Big end
        c2x, c2y = 300, 100 # Small end
        r1_out, r1_in = 35, 22
        r2_out, r2_in = 20, 12
        
        # Web offset math for perfectly tangent blending lines
        web_half_1 = 15
        web_half_2 = 10
        ang1 = math.degrees(math.asin(web_half_1 / r1_out))
        ang2 = math.degrees(math.asin(web_half_2 / r2_out))
        
        # Outer Arcs
        self.msp.add_arc((c1x, c1y), radius=r1_out, start_angle=ang1, end_angle=360-ang1, dxfattribs={'layer': 'GEOMETRY'})
        self.msp.add_arc((c2x, c2y), radius=r2_out, start_angle=180+ang2, end_angle=180-ang2, dxfattribs={'layer': 'GEOMETRY'})
        
        # Connecting Web Lines
        self.msp.add_line((c1x + r1_out*math.cos(math.radians(ang1)), c1y + web_half_1), 
                          (c2x - r2_out*math.cos(math.radians(ang2)), c2y + web_half_2), dxfattribs={'layer': 'GEOMETRY'})
        self.msp.add_line((c1x + r1_out*math.cos(math.radians(ang1)), c1y - web_half_1), 
                          (c2x - r2_out*math.cos(math.radians(ang2)), c2y - web_half_2), dxfattribs={'layer': 'GEOMETRY'})
        
        # Internal Bores
        self.msp.add_circle((c1x, c1y), radius=r1_in, dxfattribs={'layer': 'GEOMETRY'})
        self.msp.add_circle((c2x, c2y), radius=r2_in, dxfattribs={'layer': 'GEOMETRY'})
        
        self.add_center_mark(c1x, c1y, 45)
        self.add_center_mark(c2x, c2y, 30)
        self.msp.add_line((c1x, c1y), (c2x, c2y), dxfattribs={'layer': 'CENTERLINES'})

        # Dimensions
        self.add_dim((200, c1y - 90), (c1x, c1y), (c2x, c2y), text="200mm %%P0.02 PITCH LENGTH")
        self.add_dim((c1x, c1y + 80), (c1x - r1_out, c1y), (c1x + r1_out, c1y), text="%%C70mm CRANK BOSS")
        self.add_dim((c2x, c2y + 80), (c2x - r2_out, c2y), (c2x + r2_out, c2y), text="%%C40mm PIN BOSS")
        
        self.add_leader(target=(c1x-15, c1y-15), text_pos=(0, 20), text="%%C44mm g6 CRANK BORE")
        self.add_leader(target=(c2x+8, c2y+8), text_pos=(360, 160), text="%%C24mm H7 PIN BORE")

        self.validate_and_save("Kinematic_LK02_ConnectingRod.dxf", ["PITCH LENGTH", "g6", "H7"])

    # =================================================================
    # LK03: Guide Plate with Radial Tracking Slot
    # =================================================================
    def build_LK03_curved_track(self):
        self._reset_document()
        cx, cy = 100, 100
        
        # Outer rectangular base plate
        self.msp.add_lwpolyline([(0, 0), (200, 0), (200, 200), (0, 200)], close=True, dxfattribs={'layer': 'GEOMETRY'})
        
        # Radial Tracking Slot (Arc slot from 45 deg to 135 deg)
        track_radius = 60
        track_width = 16
        r_inner = track_radius - (track_width/2)
        r_outer = track_radius + (track_width/2)
        
        # Inner and outer track curves
        self.msp.add_arc((cx, cy), radius=r_inner, start_angle=45, end_angle=135, dxfattribs={'layer': 'GEOMETRY'})
        self.msp.add_arc((cx, cy), radius=r_outer, start_angle=45, end_angle=135, dxfattribs={'layer': 'GEOMETRY'})
        
        # Rounded caps at the ends of the slot
        cap_r = track_width / 2
        # Right cap (at 45 deg)
        cap1_x, cap1_y = cx + track_radius*math.cos(math.radians(45)), cy + track_radius*math.sin(math.radians(45))
        self.msp.add_arc((cap1_x, cap1_y), radius=cap_r, start_angle=-45, end_angle=135, dxfattribs={'layer': 'GEOMETRY'})
        
        # Left cap (at 135 deg)
        cap2_x, cap2_y = cx + track_radius*math.cos(math.radians(135)), cy + track_radius*math.sin(math.radians(135))
        self.msp.add_arc((cap2_x, cap2_y), radius=cap_r, start_angle=45, end_angle=225, dxfattribs={'layer': 'GEOMETRY'})

        # Reference centerlines for the slot path
        self.msp.add_arc((cx, cy), radius=track_radius, start_angle=45, end_angle=135, dxfattribs={'layer': 'CENTERLINES'})
        self.add_center_mark(cx, cy, 20)
        self.msp.add_line((cx, cy), (cap1_x, cap1_y), dxfattribs={'layer': 'CENTERLINES'})
        self.msp.add_line((cx, cy), (cap2_x, cap2_y), dxfattribs={'layer': 'CENTERLINES'})

        # Dimensions
        self.add_dim((100, -40), (0, 0), (200, 0), text="200mm BASE WIDTH")
        self.add_dim((-40, 100), (0, 0), (0, 200), angle=90, text="200mm BASE HEIGHT")
        
        # Leader for the slot width and radius
        self.add_leader(target=(cap1_x, cap1_y + cap_r), text_pos=(250, 180), text="16mm +0.1/-0.0 SLOT WIDTH\\P ON R60mm TRACK")
        
        # Angular dimension represented via text note (since linear dim doesn't support arcs natively in pure ezdxf easily)
        self.add_leader(target=(cx, cy + track_radius), text_pos=(100, 240), text="90%%D TOTAL TRACK SWEEP")

        self.validate_and_save("Kinematic_LK03_CurvedTrack.dxf", ["SLOT", "TRACK SWEEP", "+0.1"])

if __name__ == "__main__":
    generator = KinematicGenerator()
    generator.build_LK01_eccentric_cam()
    generator.build_LK02_connecting_rod()
    generator.build_LK03_curved_track()