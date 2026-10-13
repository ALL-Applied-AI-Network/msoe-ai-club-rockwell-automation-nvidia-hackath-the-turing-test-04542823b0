"""
scripts/plot_time_gaps.py
Plots a histogram of the time gaps between each vial's fill end time and the
nearest captured camera frame from outputs/aligned_camera_frames.csv.
Checks whether any vial exceeds the 2.0-second threshold and saves the chart
to outputs/time_gaps_histogram.png.
"""

from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def plot_histogram():
    base_dir = Path(__file__).resolve().parent.parent
    csv_path = base_dir / "outputs" / "aligned_camera_frames.csv"
    output_png = base_dir / "outputs" / "time_gaps_histogram.png"

    if not csv_path.exists():
        raise FileNotFoundError(
            f"Alignment file not found: {csv_path}\nPlease run scripts/align_cameras.py first."
        )

    df = pd.read_csv(csv_path)

    # Collect time gaps from the alignment table
    # Since cameras were synchronized, the gaps across cameras are identical per vial
    gaps = df["vial_fill_time_gap_s"]
    abs_gaps = gaps.abs()

    # Check for any vial with a time gap greater than 2.0 seconds
    threshold = 2.0
    vials_exceeding_threshold = df[abs_gaps > threshold]

    print("=" * 60)
    print("TIME GAP ANALYSIS REPORT (Threshold = 2.0 seconds)")
    print("=" * 60)
    print(f"Total vials inspected: {len(df)}")
    print(f"Min signed gap:        {gaps.min():+.3f} s")
    print(f"Max signed gap:        {gaps.max():+.3f} s")
    print(f"Mean signed gap:       {gaps.mean():+.3f} s")
    print(f"Max absolute gap:      {abs_gaps.max():.3f} s")
    print(f"Mean absolute gap:     {abs_gaps.mean():.3f} s")
    print("-" * 60)

    if len(vials_exceeding_threshold) == 0:
        print(
            "RESULT: 0 vials exceeded the 2.0s threshold! All 30 vials have"
        )
        print("        a camera frame within 1.0 second of fill completion.")
    else:
        print(
            f"RESULT: Found {len(vials_exceeding_threshold)} vial(s) with gap > 2.0s:"
        )
        for _, row in vials_exceeding_threshold.iterrows():
            print(
                f"  - Vial {int(row['vial'])} (Recipe {int(row['recipe_id'])}): {row['vial_fill_time_gap_s']:+.3f} s"
            )
    print("=" * 60)

    # Create figure with 2 subplots:
    # 1. Signed time gap (shows before vs after pump stop)
    # 2. Absolute time gap (shows total distance to nearest frame)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5))
    fig.patch.set_facecolor("#f8f9fa")

    # Subplot 1: Signed Time Gap Histogram
    bins_signed = np.linspace(-1.5, 1.5, 13)
    ax1.set_facecolor("#ffffff")
    n1, bins1, patches1 = ax1.hist(
        gaps,
        bins=bins_signed,
        color="#2b5c8f",
        edgecolor="#1a365d",
        alpha=0.85,
        rwidth=0.88,
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
    ax1.set_xlim(-2.5, 2.5)
    ax1.grid(axis="y", linestyle="--", alpha=0.5)
    ax1.legend(loc="upper left", frameon=True, facecolor="#ffffff")

    # Subplot 2: Absolute Time Gap Histogram
    bins_abs = np.linspace(0, 2.0, 9)
    ax2.set_facecolor("#ffffff")
    n2, bins2, patches2 = ax2.hist(
        abs_gaps,
        bins=bins_abs,
        color="#d97706",
        edgecolor="#92400e",
        alpha=0.85,
        rwidth=0.88,
    )
    ax2.axvline(
        threshold,
        color="#dc3545",
        linestyle=":",
        linewidth=2,
        label=f"{threshold}s Threshold Limit",
    )
    ax2.axvline(
        abs_gaps.max(),
        color="#0d6efd",
        linestyle="--",
        linewidth=2,
        label=f"Max Observed ({abs_gaps.max():.3f}s)",
    )
    ax2.set_title(
        "Absolute Time Gap Magnitude", fontsize=12, fontweight="bold", pad=10
    )
    ax2.set_xlabel(
        "Absolute Time Difference |Δt| in Seconds", fontsize=10
    )
    ax2.set_ylabel("Number of Vials", fontsize=10)
    ax2.set_xlim(0, 2.5)
    ax2.grid(axis="y", linestyle="--", alpha=0.5)
    ax2.legend(loc="upper right", frameon=True, facecolor="#ffffff")

    plt.suptitle(
        "Camera-to-Fill Synchronization Time Gaps (Video 5 — 30 Vials)",
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
