import pandas as pd
import os

# Define the visual verdicts from inspecting outputs/card3/judging_sheet.png
verdicts = [
    # Recipe 5 (vials 1-3)
    (1, "off", "Vivid teal-green liquid vs dark murky blackish-green reference"),
    (2, "matches", "Dark murky blackish-green, matches Vial 3"),
    (3, "reference", "Reference vial for Recipe 5"),
    
    # Recipe 6 (vials 4-6)
    (4, "off", "Pitch dark brown/black liquid vs bright orange reference"),
    (5, "unsure", "Orange hue present but noticeably duskier/darker brown than clean orange Vial 6"),
    (6, "reference", "Reference vial for Recipe 6"),
    
    # Recipe 7 (vials 7-9)
    (7, "off", "Dark forest green liquid vs vibrant cyan-blue reference"),
    (8, "matches", "Vibrant cyan-blue liquid, matches Vial 9"),
    (9, "reference", "Reference vial for Recipe 7"),
    
    # Recipe 8 (vials 10-12)
    (10, "off", "Cyan/blue-green liquid body and meniscus vs dark olive green reference"),
    (11, "matches", "Dark olive green, matches Vial 12"),
    (12, "reference", "Reference vial for Recipe 8"),
    
    # Recipe 9 (vials 13-15)
    (13, "matches", "Dark olive green, matches Vial 15"),
    (14, "matches", "Dark olive green, matches Vial 15"),
    (15, "reference", "Reference vial for Recipe 9"),
    
    # Recipe 10 (vials 16-18)
    (16, "off", "Dark bluish-green body with dark teal bottom glow vs yellowish-olive reference"),
    (17, "matches", "Warm yellowish-olive green with yellow bottom glow, matches Vial 18"),
    (18, "reference", "Reference vial for Recipe 10"),
    
    # Recipe 11 (vials 19-21)
    (19, "off", "Lighter teal with yellowish-green tint and yellow base glow vs deep teal-blue reference"),
    (20, "matches", "Deep teal-blue liquid, matches Vial 21"),
    (21, "reference", "Reference vial for Recipe 11"),
    
    # Recipe 12 (vials 22-24)
    (22, "off", "Dark olive-black liquid vs warm amber-orange reference"),
    (23, "matches", "Warm amber-orange liquid, matches Vial 24"),
    (24, "reference", "Reference vial for Recipe 12"),
    
    # Recipe 13 (vials 25-27)
    (25, "off", "Visibly brighter/lighter orange liquid vs deep brown-amber reference"),
    (26, "matches", "Deep brown-amber liquid, matches Vial 27"),
    (27, "reference", "Reference vial for Recipe 13"),
    
    # Recipe 14 (vials 28-30)
    (28, "off", "Murky amber/olive-brown liquid vs pale sky-blue reference"),
    (29, "unsure", "Visibly shifted to muted greenish-grey/teal vs clean pale sky-blue reference"),
    (30, "reference", "Reference vial for Recipe 14"),
]

# 1. Update annotations/video5_visual_verdicts.csv with ai_judge column
df_ann = pd.DataFrame({
    "vial": [v[0] for v in verdicts],
    "judge_1": ["" for _ in verdicts],
    "judge_2": ["" for _ in verdicts],
    "ai_judge": [v[1] for v in verdicts],
    "notes": ["" for _ in verdicts]  # Keep notes empty for human judges
})
ann_path = "annotations/video5_visual_verdicts.csv"
df_ann.to_csv(ann_path, index=False)
print(f"Updated {ann_path} with ai_judge column (judge_1 and judge_2 preserved empty).")

# 2. Write standalone 2-column CSV to outputs/card3/ai_visual_verdicts.csv
os.makedirs("outputs/card3", exist_ok=True)
df_two_col = pd.DataFrame({
    "vial": [v[0] for v in verdicts],
    "ai_judge": [v[1] for v in verdicts]
})
standalone_path = "outputs/card3/ai_visual_verdicts.csv"
df_two_col.to_csv(standalone_path, index=False)
print(f"Saved standalone 2-column CSV to {standalone_path}.")

# 3. Print the 2-column CSV to stdout
print("\n--- STANDALONE 2-COLUMN CSV (vial, ai_judge) ---")
print(df_two_col.to_csv(index=False))
