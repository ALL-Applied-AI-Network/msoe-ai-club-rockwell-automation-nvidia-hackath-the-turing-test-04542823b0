"""
scripts/plot_time_gaps.py
Plots a histogram of the time gaps between each vial's fill end time and the
nearest captured frame from each of the 3 cameras (cap_seal, tank_level,
vial_fill), read from outputs/card2/aligned_camera_frames.csv.
Lists any vial where a camera has no frame within 2.0 seconds and saves the
chart to outputs/card2/time_gaps_histogram.png.
"""

from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def plot_histogram():
    base_dir = Path(__file__).resolve().parent.parent
    csv_path = base_dir / "outputs" / "card2" / "aligned_camera_frames.csv"
    output_png = base_dir / "outputs" / "card2" / "time_gaps_histogram.png"

    if not csv_path.exists():
        raise FileNotFoundError(
            f"Alignment file not found: {csv_path}\nPlease run scripts/align_cameras.py first."
        )

    df = pd.read_csv(csv_path)

    # Each camera saves its own frames on its own schedule, so the gap to the
    # nearest frame is different for each camera. Check all three, not just one.
    cameras = ["cap_seal", "tank_level", "vial_fill"]
    camera_colors = {
        "cap_seal": "#7c3aed",
        "tank_level": "#d97706",
        "vial_fill": "#2b5c8f",
    }
    gaps = {cam: df[f"{cam}_time_gap_s"] for cam in cameras}
    abs_gaps = {cam: gaps[cam].abs() for cam in cameras}

    # Check for any vial where at least one camera has no frame within 2.0 seconds
    threshold = 2.0

    print("=" * 60)
    print("TIME GAP ANALYSIS REPORT (Threshold = 2.0 seconds)")
    print("=" * 60)
    print(f"Total vials inspected: {len(df)}")
    for cam in cameras:
        print("-" * 60)
        print(f"Camera: {cam}")
        print(f"  Min signed gap:      {gaps[cam].min():+.3f} s")
        print(f"  Max signed gap:      {gaps[cam].max():+.3f} s")
        print(f"  Mean signed gap:     {gaps[cam].mean():+.3f} s")
        print(f"  Max absolute gap:    {abs_gaps[cam].max():.3f} s")
        print(f"  Mean absolute gap:   {abs_gaps[cam].mean():.3f} s")
    print("-" * 60)

    problem_rows = []
    for _, row in df.iterrows():
        late_cams = [
            cam for cam in cameras if abs(row[f"{cam}_time_gap_s"]) > threshold
        ]
        if late_cams:
            problem_rows.append((row, late_cams))

    if not problem_rows:
        print(
            f"RESULT: Every camera has a frame within {threshold}s of every vial's fill end."
        )
    else:
        print(
            f"RESULT: {len(problem_rows)} vial(s) have a camera with no frame within {threshold}s:"
        )
        for row, late_cams in problem_rows:
            details = ", ".join(
                f"{cam} {row[f'{cam}_time_gap_s']:+.3f} s" for cam in late_cams
            )
            print(
                f"  - Vial {int(row['vial'])} (Recipe {int(row['recipe_id'])}): {details}"
            )
    print("=" * 60)

    # Bin edges cover the largest gap seen, so no vial falls off the chart
    largest_gap = max(threshold, max(abs_gaps[cam].max() for cam in cameras))
    axis_limit = np.ceil(largest_gap * 2) / 2 + 0.5

    # Create figure with 2 subplots:
    # 1. Signed time gap (shows before vs after pump stop)
    # 2. Absolute time gap (shows total distance to nearest frame)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5))
    fig.patch.set_facecolor("#f8f9fa")

    # Subplot 1: Signed Time Gap Histogram, one color per camera
    bins_signed = np.arange(-axis_limit, axis_limit + 0.25, 0.25)
    ax1.set_facecolor("#ffffff")
    ax1.hist(
        [gaps[cam] for cam in cameras],
        bins=bins_signed,
        color=[camera_colors[cam] for cam in cameras],
        label=cameras,
        alpha=0.85,
        rwidth=0.9,
    )
    ax1.axvline(
        0,
        color="#198754",
        linestyle="--",
        linewidth=2,
        label="Exact Fill End (0.0s)",
    )
    ax1.axvline(
        -threshold,
        color="#dc3545",
        linestyle=":",
        linewidth=2,
        label=f"±{threshold}s Threshold",
    )
    ax1.axvline(threshold, color="#dc3545", linestyle=":", linewidth=2)
    ax1.set_title(
        "Signed Time Gap (Camera Capture vs. Pump Stop)",
        fontsize=12,
        fontweight="bold",
        pad=10,
    )
    ax1.set_xlabel(
        "Time Gap in Seconds (Negative = Before, Positive = After)", fontsize=10
    )
    ax1.set_ylabel("Number of Vials", fontsize=10)
    ax1.set_xlim(-axis_limit, axis_limit)
    ax1.grid(axis="y", linestyle="--", alpha=0.5)
    ax1.legend(loc="upper left", frameon=True, facecolor="#ffffff")

    # Subplot 2: Absolute Time Gap Histogram, one color per camera
    bins_abs = np.arange(0, axis_limit + 0.25, 0.25)
    ax2.set_facecolor("#ffffff")
    ax2.hist(
        [abs_gaps[cam] for cam in cameras],
        bins=bins_abs,
        color=[camera_colors[cam] for cam in cameras],
        label=cameras,
        alpha=0.85,
        rwidth=0.9,
    )
    ax2.axvline(
        threshold,
        color="#dc3545",
        linestyle=":",
        linewidth=2,
        label=f"{threshold}s Threshold Limit",
    )
    ax2.set_title(
        "Absolute Time Gap Magnitude", fontsize=12, fontweight="bold", pad=10
    )
    ax2.set_xlabel(
        "Absolute Time Difference |Δt| in Seconds", fontsize=10
    )
    ax2.set_ylabel("Number of Vials", fontsize=10)
    ax2.set_xlim(0, axis_limit)
    ax2.grid(axis="y", linestyle="--", alpha=0.5)
    ax2.legend(loc="upper right", frameon=True, facecolor="#ffffff")

    plt.suptitle(
        f"Camera-to-Fill Synchronization Time Gaps (Video 5 — {len(df)} Vials)",
        fontsize=15,
        fontweight="bold",
        y=0.98,
    )
    plt.tight_layout(rect=[0, 0, 1, 0.94])

    plt.savefig(output_png, dpi=200, facecolor=fig.get_facecolor())
    plt.close()

    print(f"Histogram successfully saved to: {output_png}")


if __name__ == "__main__":
    plot_histogram()
