import os

missing = [
    "Aero_LW10_Orthogrid",
    "CNC_WW09_VCarveBoundary",
    "PCB_PC05_EdgeConnector",
    "SheetMetal_SM02_PrecisionZClip",
    "Turned_Shaft_TS04",
    "Weldment_WD03_VGroovePrep"
]

log_path = "outputs/logs/pipeline.log"
if os.path.exists(log_path):
    with open(log_path) as f:
        lines = f.readlines()
        
    for m in missing:
        print(f"--- LOGS FOR {m} ---")
        matches = [line.strip() for line in lines if m in line]
        for match in matches[-5:]: # show last 5 logs for each
            print(f"  {match}")
else:
    print("Log file not found.")
