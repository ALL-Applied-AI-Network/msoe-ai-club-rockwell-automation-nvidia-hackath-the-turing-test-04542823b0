"""Blindly summarize filled vials in an unlabeled CSI vial-fill recording.

Reads:
- A vial_fill MP4 supplied with --video.
- Clean Video 5 recipe reference colors from outputs/card3/baseline_results.csv.

Writes:
- outputs/runs/<name>/blind_vials.csv with one departure snapshot per detected
  vial: the final stable frame immediately before the starwheel sends it onward,
  its measured color, color-group label, nearest known-recipe candidates, and
  uncertainty.
- parked_vials.csv and contact_sheet.png through detect_parked_vials.py.

This script never assigns a verified recipe or PASS/FAIL verdict. Candidate
recipes are nearest-color estimates only because the intended production
recipe is not present in an unlabeled video.

Usage:
  python scripts/blind_analyze.py --video outputs/runs/csi_run_2/vial_fill.mp4 --name csi_run_2
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import colour
import cv2
import numpy as np
import pandas as pd
from sklearn.cluster import AgglomerativeClustering

from detect_parked_vials import LOW_PATCH, detect_parked_vials


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASELINE = REPO_ROOT / "outputs" / "card3" / "baseline_results.csv"
CLUSTER_DELTA_E = 6.0


def extract_low_color(frame: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return median LOW-patch sRGB (0-255) and CIELAB color."""
    crop = frame[
        LOW_PATCH["y_min"] : LOW_PATCH["y_max"],
        LOW_PATCH["x_min"] : LOW_PATCH["x_max"],
    ]
    rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
    median_rgb = np.median(rgb, axis=(0, 1))
    lab = colour.XYZ_to_Lab(colour.sRGB_to_XYZ(median_rgb / 255.0))
    return median_rgb, lab


def color_name(rgb: np.ndarray) -> str:
    """Give a deliberately broad visual color name for an observed patch."""
    pixel = np.uint8([[np.clip(rgb, 0, 255)]])
    h, s, v = cv2.cvtColor(pixel, cv2.COLOR_RGB2HSV)[0, 0]
    h_deg = float(h) * 2.0
    if v < 35:
        return "very dark"
    if s < 28:
        return "clear/neutral"
    if h_deg < 20 or h_deg >= 345:
        return "red-brown"
    if h_deg < 55:
        return "orange-brown"
    if h_deg < 85:
        return "yellow"
    if h_deg < 165:
        return "green"
    if h_deg < 255:
        return "blue"
    if h_deg < 300:
        return "purple"
    return "magenta-red"


def load_recipe_references(path: Path) -> pd.DataFrame:
    """Load one clean LOW-patch reference color per known Video 5 recipe."""
    df = pd.read_csv(path)
    refs = df[df["batch_pos"] == 3][["recipe_id", "L_low", "a_low", "b_low"]].copy()
    refs = refs.dropna().sort_values("recipe_id")
    if refs.empty:
        raise ValueError(f"No clean recipe reference rows found in {path}")
    return refs


def cluster_colors(labs: np.ndarray) -> list[str]:
    """Group similar observed colors using a fixed Delta-E threshold."""
    n = len(labs)
    if n == 0:
        return []
    if n == 1:
        return ["A"]

    distances = np.zeros((n, n), dtype=float)
    for i in range(n):
        for j in range(i + 1, n):
            d = float(colour.delta_E(labs[i], labs[j], method="CIE 2000"))
            distances[i, j] = distances[j, i] = d

    model = AgglomerativeClustering(
        n_clusters=None,
        metric="precomputed",
        linkage="average",
        distance_threshold=CLUSTER_DELTA_E,
    )
    raw_labels = model.fit_predict(distances)

    # Stable A/B/C labels ordered by the first vial in each group.
    label_map: dict[int, str] = {}
    for raw in raw_labels:
        raw_int = int(raw)
        if raw_int not in label_map:
            idx = len(label_map)
            label_map[raw_int] = chr(ord("A") + idx) if idx < 26 else f"G{idx + 1}"
    return [label_map[int(raw)] for raw in raw_labels]


def candidate_for_lab(lab: np.ndarray, refs: pd.DataFrame) -> dict[str, object]:
    """Return nearest and runner-up known recipes plus transparent uncertainty."""
    scored: list[tuple[float, int]] = []
    for _, ref in refs.iterrows():
        ref_lab = np.array([ref["L_low"], ref["a_low"], ref["b_low"]], dtype=float)
        distance = float(colour.delta_E(lab, ref_lab, method="CIE 2000"))
        scored.append((distance, int(ref["recipe_id"])))
    scored.sort()
    best_de, best_recipe = scored[0]
    second_de, second_recipe = scored[1]
    margin = second_de - best_de

    if best_de <= 5.0 and margin >= 3.0:
        confidence = "higher"
    elif best_de <= 10.0 and margin >= 1.5:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "candidate_recipe": best_recipe,
        "candidate_delta_e": round(best_de, 2),
        "second_candidate_recipe": second_recipe,
        "candidate_margin": round(margin, 2),
        "candidate_confidence": confidence,
    }


def analyze_blind_run(video_path: Path, name: str, baseline_path: Path) -> Path:
    """Detect fills and write the blind color summary for one recording."""
    video_path = Path(video_path)
    out_dir = REPO_ROOT / "outputs" / "runs" / name
    out_dir.mkdir(parents=True, exist_ok=True)

    detected = detect_parked_vials(
        video_path=video_path,
        name=name,
        out_dir=out_dir,
        save_outputs=True,
    )
    if detected.empty:
        raise RuntimeError(f"No filled vials were detected in {video_path}")

    refs = load_recipe_references(baseline_path)
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    rows: list[dict[str, object]] = []
    labs: list[np.ndarray] = []
    try:
        for _, vial in detected.iterrows():
            frame_num = int(vial["frame"])
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError(f"Could not read frame {frame_num} from {video_path}")

            rgb, lab = extract_low_color(frame)
            labs.append(lab)

            row = {
                "vial": int(vial["vial"]),
                "frame": frame_num,
                "mp4_s": float(vial["mp4_s"]),
                "analysis_moment": "final stable frame before departure",
                "observed_color": color_name(rgb),
                "observed_hex": "#" + "".join(f"{int(round(x)):02X}" for x in rgb),
                "L_low": round(float(lab[0]), 3),
                "a_low": round(float(lab[1]), 3),
                "b_low": round(float(lab[2]), 3),
            }
            row.update(candidate_for_lab(lab, refs))
            rows.append(row)
    finally:
        cap.release()

    groups = cluster_colors(np.asarray(labs))
    for row, group in zip(rows, groups):
        row["color_group"] = group

    output_columns = [
        "vial",
        "frame",
        "mp4_s",
        "analysis_moment",
        "observed_color",
        "observed_hex",
        "color_group",
        "L_low",
        "a_low",
        "b_low",
        "candidate_recipe",
        "candidate_delta_e",
        "second_candidate_recipe",
        "candidate_margin",
        "candidate_confidence",
    ]
    output = out_dir / "blind_vials.csv"
    pd.DataFrame(rows)[output_columns].to_csv(output, index=False)

    n_groups = len(set(groups))
    print(f"Blind analysis saved: {output}")
    print(f"Departure snapshots: {len(rows)} | color groups: {n_groups}")
    print("Every color measurement uses only the final stable frame before departure.")
    print("Recipe candidates are estimates from color only; they are not verified recipe labels.")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Blind color analysis for an unlabeled CSI vial-fill video.")
    parser.add_argument("--video", type=Path, required=True, help="Path to the vial_fill MP4")
    parser.add_argument("--name", required=True, help="Run folder name under outputs/runs/")
    parser.add_argument(
        "--baseline",
        type=Path,
        default=DEFAULT_BASELINE,
        help="Known clean-recipe color table (default: outputs/card3/baseline_results.csv)",
    )
    args = parser.parse_args()
    analyze_blind_run(args.video, args.name, args.baseline)


if __name__ == "__main__":
    main()
