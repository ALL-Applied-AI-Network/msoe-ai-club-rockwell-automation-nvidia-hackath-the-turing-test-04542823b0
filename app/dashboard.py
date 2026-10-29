"""
app/dashboard.py
Carryover Copilot · Fluid Mixing Station 3

Three panels side by side + cascade counter + end-of-run summary table:
1. Recipe Queue: Pre-fill risk lights and queue reorder advisor (LIVE - flush_advisor.py)
2. Latest Vial: Post-fill camera color verification, patch metrics, and PASS/UNSURE/FAIL verdict
3. Explanation: Plain-English explanation grounded in camera evidence and recipes (LIVE - explanation_cache.py)
Below: Inference Cascade Counter + End-of-Run Summary.

Sidebar Source Options:
- 'Video 5 (demo)': Replay of Video 5 using baseline reference colors and raw color checks.
- 'Recorded run': Replay of on-site CSI recordings using run-specific reference vials,
  blank-normalized color math, and lighting change warnings.

Run with:
    streamlit run app/dashboard.py
"""

from pathlib import Path
import sys
import time
import itertools
import cv2
import numpy as np
import pandas as pd
import streamlit as st

# Add scripts folder to sys.path so we can import project modules cleanly
REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from flush_advisor import (
    evaluate_transition,
    evaluate_order,
    load_clean_references,
    load_run_clean_references,
    load_risk_alphas,
    BASELINE_CSV,
    RISK_JSON,
)
from replay_feed import get_vial, VialFeedItem, DEFAULT_TIMES_CSV, DEFAULT_VIDEO_MP4
from vial_check import (
    check_vial,
    load_references,
    load_run_references,
    check_vial_normalized,
    HIGH_PATCH,
    LOW_PATCH,
)
from explanation_cache import get as get_explanation

st.set_page_config(
    page_title="Carryover Copilot · Fluid Mixing Station 3",
    page_icon="🧪",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Session State Initialization & Query Parameter Support
# ---------------------------------------------------------------------------
if "vial_index" not in st.session_state:
    if "vial" in st.query_params:
        try:
            st.session_state.vial_index = int(st.query_params["vial"])
        except Exception:
            st.session_state.vial_index = 1
    else:
        st.session_state.vial_index = 1
elif "vial" in st.query_params and "param_vial_handled" not in st.session_state:
    try:
        st.session_state.vial_index = int(st.query_params["vial"])
        st.session_state.param_vial_handled = True
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Sidebar: Source Selection
# ---------------------------------------------------------------------------
st.sidebar.title("Configuration")
default_src_idx = 1 if st.query_params.get("source") in ("run", "recorded", "Recorded run") else 0
source_mode = st.sidebar.radio(
    "Source",
    ["Video 5 (demo)", "Recorded run"],
    index=default_src_idx,
    help="Switch between Video 5 demonstration replay and on-site recorded runs.",
)

selected_run = None
run_vials_csv = None
run_video_mp4 = None

if source_mode == "Recorded run":
    runs_dir = REPO_ROOT / "outputs" / "runs"
    available_runs = (
        sorted([d.name for d in runs_dir.iterdir() if d.is_dir() and (d / "vials.csv").exists()])
        if runs_dir.exists()
        else []
    )
    if not available_runs:
        st.sidebar.error("No recorded runs found in outputs/runs/. Run scripts/new_run.py first.")
        st.stop()
    default_run_idx = (
        available_runs.index(st.query_params["run"])
        if st.query_params.get("run") in available_runs
        else 0
    )
    selected_run = st.sidebar.selectbox("Recorded Run", available_runs, index=default_run_idx)
    run_vials_csv = runs_dir / selected_run / "vials.csv"
    run_video_cand1 = REPO_ROOT / "data" / "runs" / selected_run / "video.mp4"
    run_video_cand2 = DEFAULT_VIDEO_MP4
    run_video_mp4 = run_video_cand1 if run_video_cand1.exists() else run_video_cand2

# Reset vial index if switching configuration
curr_config = (source_mode, selected_run)
if "prev_config" not in st.session_state:
    st.session_state.prev_config = curr_config
elif st.session_state.prev_config != curr_config:
    st.session_state.vial_index = 1
    st.session_state.prev_config = curr_config


def get_batch_previous_recipe_for_vial(df_v: pd.DataFrame, vial_num: int) -> int | None:
    """Finds the recipe ID of the batch that ran immediately before this vial's batch."""
    cur_recipe = int(df_v.loc[vial_num, "recipe_id"])
    vials_before = df_v.loc[:vial_num - 1]
    diff_before = vials_before[vials_before["recipe_id"] != cur_recipe]
    if len(diff_before) == 0:
        return None
    return int(diff_before.iloc[-1]["recipe_id"])


def get_active_change_for_vial(vial_num: int, df_v: pd.DataFrame) -> tuple[int, int]:
    """
    Determines which recipe transition Panel 1 should highlight based on current vial.
    For the reference vial of a batch (before next batch starts), looks ahead to (R, R_next).
    Otherwise, highlights the transition that introduced this recipe (R_prev, R).
    """
    rec_id = int(df_v.loc[vial_num, "recipe_id"])
    is_ref = bool(df_v.loc[vial_num, "is_reference"]) if "is_reference" in df_v.columns else (((vial_num - 1) % 3) == 2)

    vials_before = df_v.loc[:vial_num - 1]
    diff_before = vials_before[vials_before["recipe_id"] != rec_id]
    prev_batch_r = int(diff_before.iloc[-1]["recipe_id"]) if len(diff_before) > 0 else None

    vials_after = df_v.loc[vial_num + 1:]
    diff_after = vials_after[vials_after["recipe_id"] != rec_id]
    next_batch_r = int(diff_after.iloc[0]["recipe_id"]) if len(diff_after) > 0 else None

    if is_ref and next_batch_r is not None:
        return (rec_id, next_batch_r)
    elif prev_batch_r is not None:
        return (prev_batch_r, rec_id)
    elif next_batch_r is not None:
        return (rec_id, next_batch_r)
    else:
        return (rec_id, rec_id)


# Cache reference colors from clean 3rd vials for demo
@st.cache_resource
def get_cached_vial_references():
    return load_references()


# Cache run references for recorded runs
@st.cache_resource
def get_cached_run_references(vials_csv_str: str, video_mp4_str: str):
    return load_run_references(Path(vials_csv_str), Path(video_mp4_str))


# Cache recipe composition descriptions
@st.cache_data
def get_reviewed_scores(scores_path_str: str = "annotations/card9_scores.csv") -> dict[str, bool]:
    p = Path(scores_path_str)
    if not p.exists():
        return {}
    try:
        df = pd.read_csv(p)
        return {
            str(row["change"]).strip(): (str(row["correct"]).strip().lower() == "yes")
            for _, row in df.iterrows()
            if "change" in row and "correct" in row
        }
    except Exception:
        return {}


# Cache recipe composition descriptions
@st.cache_data
def get_cached_recipe_descriptions(vials_csv_str: str | None = None):
    lookup = {}
    if vials_csv_str is not None:
        v_path = Path(vials_csv_str)
        if v_path.exists():
            df = pd.read_csv(v_path)
            for _, row in df.iterrows():
                r_id = int(row["recipe_id"])
                if r_id not in lookup and ("t100_ml" in row or "t200_ml" in row or "t400_ml" in row):
                    t100 = 0 if pd.isna(row.get("t100_ml")) else int(row.get("t100_ml", 0))
                    t200 = 0 if pd.isna(row.get("t200_ml")) else int(row.get("t200_ml", 0))
                    t400 = 0 if pd.isna(row.get("t400_ml")) else int(row.get("t400_ml", 0))
                    parts = []
                    if t200 > 0:
                        parts.append(f"{t200} mL orange")
                    if t400 > 0:
                        parts.append(f"{t400} mL blue")
                    if t100 > 0:
                        parts.append(f"{t100} mL clear")
                    if parts:
                        lookup[r_id] = " + ".join(parts)
            if lookup:
                return lookup

    rec_csv = REPO_ROOT / "data/csi-vial-fill-dataset/vial_fill/labels/video5_vial_recipes.csv"
    if rec_csv.exists():
        df = pd.read_csv(rec_csv).set_index("vial")
        for v in df.index:
            r_id = int(df.loc[v, "recipe_id"])
            if r_id not in lookup:
                t100 = 0 if pd.isna(df.loc[v, "t100_ml"]) else int(df.loc[v, "t100_ml"])
                t200 = 0 if pd.isna(df.loc[v, "t200_ml"]) else int(df.loc[v, "t200_ml"])
                t400 = 0 if pd.isna(df.loc[v, "t400_ml"]) else int(df.loc[v, "t400_ml"])
                parts = []
                if t200 > 0:
                    parts.append(f"{t200} mL orange")
                if t400 > 0:
                    parts.append(f"{t400} mL blue")
                if t100 > 0:
                    parts.append(f"{t100} mL clear")
                lookup[r_id] = " + ".join(parts)
    return lookup


# Precompute verdicts across all 30 vials for demo
@st.cache_data
def get_all_30_verdicts():
    refs = load_references()
    records = []
    math_durations = []
    total_durations = []
    for v in range(1, 31):
        t_tot0 = time.perf_counter()
        item = get_vial(v, with_frame=True)
        bpos = ((v - 1) % 3) + 1
        is_ref = (bpos == 3)
        t_math0 = time.perf_counter()
        res = check_vial(item.frame, item.recipe_id, item.total_ml, refs, is_reference=is_ref)
        math_durations.append((time.perf_counter() - t_math0) * 1000)
        total_durations.append((time.perf_counter() - t_tot0) * 1000)
        verdict = "reference" if is_ref else res["verdict"]
        records.append({
            "vial": v,
            "recipe_id": item.recipe_id,
            "total_ml": item.total_ml,
            "batch_pos": bpos,
            "verdict": verdict,
            "delta_e": res["delta_e"],
            "patch": res["patch"],
            "blank_fallback": "measured",
            "lighting_warning": None,
        })
    avg_math_ms = sum(math_durations) / len(math_durations) if math_durations else 0.7
    avg_total_ms = sum(total_durations) / len(total_durations) if total_durations else 75.0
    return records, avg_math_ms, avg_total_ms


# Precompute verdicts for a recorded run
@st.cache_data
def get_all_run_verdicts(run_name: str, vials_csv_str: str, video_mp4_str: str):
    v_csv = Path(vials_csv_str)
    v_mp4 = Path(video_mp4_str)
    df_v = pd.read_csv(v_csv).set_index("vial")
    run_refs = load_run_references(v_csv, v_mp4)

    records = []
    math_durations = []
    total_durations = []

    for v in df_v.index:
        t_tot0 = time.perf_counter()
        item = get_vial(v, times_csv=v_csv, video_mp4=v_mp4, with_frame=True)
        is_ref = bool(df_v.loc[v, "is_reference"])
        cur_r = int(df_v.loc[v, "recipe_id"])
        batch_vials = df_v[df_v["recipe_id"] == cur_r].index.tolist()
        bpos = batch_vials.index(v) + 1 if v in batch_vials else 1

        t_math0 = time.perf_counter()
        res = check_vial_normalized(
            item.frame, item.recipe_id, item.total_ml, run_refs, is_reference=is_ref, vial_num=v
        )
        math_durations.append((time.perf_counter() - t_math0) * 1000)
        total_durations.append((time.perf_counter() - t_tot0) * 1000)

        verdict = "reference" if is_ref else res["verdict"]
        records.append({
            "vial": v,
            "recipe_id": item.recipe_id,
            "total_ml": item.total_ml,
            "batch_pos": bpos,
            "verdict": verdict,
            "delta_e": res["delta_e"],
            "patch": res["patch"],
            "blank_fallback": res["blank_status"],
            "lighting_warning": res["lighting_warning"],
        })

    avg_math_ms = sum(math_durations) / len(math_durations) if math_durations else 1.0
    avg_total_ms = sum(total_durations) / len(total_durations) if total_durations else 80.0
    return records, avg_math_ms, avg_total_ms


def log_trial_vial_if_needed(
    run_name: str,
    vial_num: int,
    recipe_id: int,
    prev_recipe: int | None,
    risk_light: str,
    verdict: str,
    delta_e: float,
    patch: str,
    blank_fallback: str,
    lighting_warning: str | None,
    ms_per_vial: float,
    notes: str,
):
    """Appends one row to outputs/runs/<name>/trial_log.csv when a vial is shown."""
    log_path = REPO_ROOT / "outputs" / "runs" / run_name / "trial_log.csv"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    header = "time_shown,vial,recipe,previous_recipe,risk_light,verdict,delta_e,patch,blank_fallback,lighting_warning,ms_per_vial,notes\n"
    if not log_path.exists():
        log_path.write_text(header, encoding="utf-8")

    # Avoid duplicate writes for the exact same view event in session
    session_key = f"logged_{run_name}_{vial_num}"
    if session_key in st.session_state:
        return
    st.session_state[session_key] = True

    time_str = time.strftime("%Y-%m-%d %H:%M:%S")
    prev_str = str(prev_recipe) if prev_recipe is not None else "None"
    light_str = str(risk_light) if risk_light else "N/A"
    warn_str = str(lighting_warning) if lighting_warning else "none"
    fb_str = str(blank_fallback)

    row = (
        f"{time_str},{vial_num},{recipe_id},{prev_str},{light_str},{verdict},"
        f"{delta_e:.2f},{patch},{fb_str},{warn_str},{ms_per_vial:.1f},{notes}\n"
    )

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(row)


# ---------------------------------------------------------------------------
# Main Application Header & Honesty Banner
# ---------------------------------------------------------------------------
st.title("🧪 Carryover Copilot · Fluid Mixing Station 3")
st.caption("Predictive Flush Advisory · In-Line Camera Color Verification · Cosmos Physical AI Explanations")

if source_mode == "Recorded run":
    st.warning(
        f"⚠️ **Recorded run {selected_run}:** reference vials are the last vial of each recipe in this recording, so they are not checked."
    )
else:
    st.warning(
        "⚠️ **Replay of recorded video 5.** Clean references are the 3rd vials of this same run, "
        "so this replay is a demonstration, not a score. Our score is the Card 3 leave-one-recipe-out result."
    )
st.markdown("---")

# Layout: 3 panels side by side
col_queue, col_vial, col_expl = st.columns([1.1, 1.2, 1.3], gap="medium")

# Pre-flight check: ensure required files exist
prereqs_ok = True
if not RISK_JSON.exists():
    st.error("Missing outputs/card4/risk_model.json. Run scripts/fit_risk_model.py first.")
    prereqs_ok = False
elif source_mode == "Video 5 (demo)" and not BASELINE_CSV.exists():
    st.error("Missing outputs/card3/baseline_results.csv. Run scripts/baseline_check.py first.")
    prereqs_ok = False
elif source_mode == "Recorded run" and not run_vials_csv.exists():
    st.error(f"Missing vials table at {run_vials_csv}. Run scripts/new_run.py first.")
    prereqs_ok = False

if prereqs_ok:
    high_alpha, low_alpha = load_risk_alphas()

    if source_mode == "Video 5 (demo)":
        advisor_refs = load_clean_references()
        vial_refs = get_cached_vial_references()
        recipe_descriptions = get_cached_recipe_descriptions()
        all_records, avg_math_ms, avg_total_ms = get_all_30_verdicts()
        times_csv = DEFAULT_TIMES_CSV
        video_mp4 = DEFAULT_VIDEO_MP4
        df_times = pd.read_csv(times_csv).set_index("vial")
        max_vials = 30
        QUEUE_RECIPES = [5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
        run_refs_data = None
    else:
        advisor_refs, QUEUE_RECIPES = load_run_clean_references(selected_run, video_mp4=run_video_mp4)
        run_refs_data = get_cached_run_references(str(run_vials_csv), str(run_video_mp4))
        recipe_descriptions = get_cached_recipe_descriptions(str(run_vials_csv))
        all_records, avg_math_ms, avg_total_ms = get_all_run_verdicts(selected_run, str(run_vials_csv), str(run_video_mp4))
        times_csv = run_vials_csv
        video_mp4 = run_video_mp4
        df_times = pd.read_csv(times_csv).set_index("vial")
        max_vials = len(df_times)
        vial_refs = None

    # Determine current vial
    current_vial = min(st.session_state.vial_index, max_vials)
    current_item = get_vial(current_vial, times_csv=times_csv, video_mp4=video_mp4, with_frame=True)
    upcoming_change = get_active_change_for_vial(current_vial, df_times)

    # -----------------------------------------------------------------------
    # Panel 1: Recipe Queue (LIVE)
    # -----------------------------------------------------------------------
    with col_queue:
        st.subheader("1. Recipe Queue")
        st.caption("Pre-Fill Carryover Risk Advisor · Lookahead Scheduler")

        evaluations, num_red, num_amber, total_err = evaluate_order(
            QUEUE_RECIPES, None, advisor_refs, high_alpha, low_alpha
        )

        # Visual sequence of recipe boxes with risk lights
        seq_label = f"Recipe Sequence & Risk Lights ({selected_run if source_mode == 'Recorded run' else 'Video 5'}):"
        st.markdown(f"**{seq_label}**")
        pills_html = [
            '<div style="display: flex; flex-wrap: wrap; align-items: center; gap: 4px; margin-bottom: 12px;">'
        ]
        for i, r in enumerate(QUEUE_RECIPES):
            is_upcoming_target = (r == upcoming_change[1])
            bg = "#1a3a4a" if is_upcoming_target else "#262730"
            border = "2px solid #00c0f0" if is_upcoming_target else "1px solid #555"
            pills_html.append(
                f'<span style="border: {border}; background: {bg}; border-radius: 4px; '
                f'padding: 3px 8px; font-weight: bold; font-size: 0.9em;">R{r}</span>'
            )
            if i < len(QUEUE_RECIPES) - 1:
                r_next = QUEUE_RECIPES[i + 1]
                t_res = evaluations[i][2]
                light_icon = (
                    "🔴"
                    if t_res["light"] == "RED"
                    else ("🟡" if t_res["light"] == "AMBER" else ("🟢" if t_res["light"] == "GREEN" else "⚪"))
                )
                is_active_trans = (r == upcoming_change[0] and r_next == upcoming_change[1])
                sep_style = "font-weight: bold; padding: 0 2px;"
                if is_active_trans:
                    pills_html.append(f'<span style="{sep_style}; color: #00c0f0;">👉{light_icon}→</span>')
                else:
                    pills_html.append(f'<span style="{sep_style}">{light_icon}→</span>')
        pills_html.append('</div>')
        st.markdown("".join(pills_html), unsafe_allow_html=True)

        # Highlight active change coming up
        up_r1, up_r2 = upcoming_change
        up_eval = next((res for r1, r2, res in evaluations if r1 == up_r1 and r2 == up_r2), None)

        if up_eval:
            light_name = up_eval["light"]
            light_badge = (
                "🔴 HIGH RISK (RED LIGHT)"
                if light_name == "RED"
                else (
                    "🟡 MEDIUM RISK (AMBER LIGHT)"
                    if light_name == "AMBER"
                    else ("🟢 LOW RISK (GREEN LIGHT)" if light_name == "GREEN" else "⚪ UNKNOWN RECIPE")
                )
            )
            st.markdown(f"#### ⚡ Active Change: Recipe {up_r1} → Recipe {up_r2}")
            if up_eval["status"] == "unknown":
                st.warning(f"**{light_badge}**\n\n- {up_eval['message']}")
            else:
                box_content = (
                    f"**{light_badge}**\n\n"
                    f"- **Recipe gap:** ΔE = **{up_eval['gap']:.1f}** ({up_eval['patch']} patch)\n"
                    f"- **Action:** {up_eval['action']}"
                )
                if light_name == "RED":
                    st.error(box_content)
                elif light_name == "AMBER":
                    st.warning(box_content)
                else:
                    st.success(box_content)

        # Details list of all transitions
        with st.expander(f"📋 All Queue Transitions ({QUEUE_RECIPES[0]} → {QUEUE_RECIPES[-1]})", expanded=False):
            for r1, r2, res in evaluations:
                is_active = (r1 == upcoming_change[0] and r2 == upcoming_change[1])
                marker = "👉 " if is_active else ""
                icon = (
                    "🔴"
                    if res["light"] == "RED"
                    else ("🟡" if res["light"] == "AMBER" else ("🟢" if res["light"] == "GREEN" else "⚪"))
                )
                if res["status"] == "unknown":
                    st.markdown(f"**{marker}{icon} Change {r1} → {r2}:** {res['message']}")
                else:
                    st.markdown(
                        f"**{marker}{icon} Change {r1} → {r2}:** Patch `{res['patch']}` | "
                        f"Gap ΔE **{res['gap']:.1f}** | **{res['light']}**\n\n"
                        f"*{res['action']}*"
                    )

        st.markdown("---")

        # Reorder advice for next 3 recipes (Batch Scheduler window)
        st.markdown("**Queue Reorder Advisor:**")
        try:
            up_idx = QUEUE_RECIPES.index(upcoming_change[1])
            window_3 = QUEUE_RECIPES[up_idx : up_idx + 3]
            after_r = upcoming_change[0]
        except Exception:
            window_3 = QUEUE_RECIPES[:3]
            after_r = None

        st.caption(f"Batch Scheduler window (up to 3): `{' → '.join(str(r) for r in window_3)}` (after Recipe {after_r})")

        if len(window_3) <= 1:
            st.info("Current order is already optimal (only 1 recipe remaining in window).")
        else:
            _, cur_red, cur_amber, cur_err = evaluate_order(window_3, after_r, advisor_refs, high_alpha, low_alpha)

            unique_perms = sorted(list(set(itertools.permutations(window_3))))
            best_perm = tuple(window_3)
            best_red = cur_red
            best_amber = cur_amber
            best_err = cur_err
            found_improvement = False

            for perm in unique_perms:
                if perm == tuple(window_3):
                    continue
                _, num_r, num_a, tot_e = evaluate_order(perm, after_r, advisor_refs, high_alpha, low_alpha)
                if num_r is None:
                    continue

                is_strictly_fewer_red = num_r < best_red
                is_fewer_amber = (num_red == best_red) and (num_a < best_amber)
                is_tie_break = (
                    (num_r == best_red)
                    and (num_a == best_amber)
                    and found_improvement
                    and (tot_e < best_err - 1e-4)
                )

                if is_strictly_fewer_red or is_fewer_amber or is_tie_break:
                    best_perm = perm
                    best_red = num_r
                    best_amber = num_a
                    best_err = tot_e
                    found_improvement = True

            if found_improvement:
                suggested_str = " → ".join(str(r) for r in best_perm)
                st.warning(
                    f"**Suggested order (needs the planner's OK):** `{suggested_str}`\n\n"
                    f"- Current order: **{cur_red} RED**, **{cur_amber} AMBER** change(s)\n"
                    f"- Suggested order: **{best_red} RED**, **{best_amber} AMBER** change(s)"
                )
            else:
                if cur_red is not None and cur_red > 0:
                    st.info("No order removes a red change; consider a flush (needs the plant manager's approval).")
                else:
                    st.success("Current order is already optimal.")

    # -----------------------------------------------------------------------
    # Panel 2: Latest Vial Inspection (LIVE)
    # -----------------------------------------------------------------------
    with col_vial:
        st.subheader("2. Latest Vial Inspection")

        # Controls: Next vial, Reset, Auto-play
        ctrl_c1, ctrl_c2, ctrl_c3 = st.columns([1, 1, 1.2])
        with ctrl_c1:
            if st.button("▶ Next Vial", use_container_width=True, disabled=(current_vial >= max_vials)):
                st.session_state.vial_index += 1
                st.rerun()
        with ctrl_c2:
            if st.button("⏮ Reset (V1)", use_container_width=True):
                st.session_state.vial_index = 1
                st.rerun()
        with ctrl_c3:
            auto_play = st.toggle("Auto-play (3s)", value=False, key="auto_play_toggle")

        # Quick slider to jump to any vial
        slider_val = st.slider(
            "Jump to vial",
            min_value=1,
            max_value=max_vials,
            value=current_vial,
            key="vial_slider",
            label_visibility="collapsed",
        )
        if slider_val != current_vial:
            st.session_state.vial_index = slider_val
            st.rerun()

        # Batch position and reference determination
        cur_r = int(df_times.loc[current_vial, "recipe_id"])
        batch_vials = df_times[df_times["recipe_id"] == cur_r].index.tolist()
        batch_total = len(batch_vials)
        batch_pos = batch_vials.index(current_vial) + 1 if current_vial in batch_vials else (((current_vial - 1) % 3) + 1)
        is_reference = (
            bool(df_times.loc[current_vial, "is_reference"])
            if "is_reference" in df_times.columns
            else (batch_pos == batch_total)
        )

        # Inspection calculation
        t_chk0 = time.perf_counter()
        if source_mode == "Video 5 (demo)":
            vial_res = check_vial(
                current_item.frame,
                current_item.recipe_id,
                current_item.total_ml,
                vial_refs,
                is_reference=is_reference,
            )
            vial_dur_ms = (time.perf_counter() - t_chk0) * 1000
            ref_vial_num = vial_refs[current_item.recipe_id]["reference_vial"]
            check_mode_label = "raw CIELAB"
        else:
            vial_res = check_vial_normalized(
                current_item.frame,
                current_item.recipe_id,
                current_item.total_ml,
                run_refs_data,
                is_reference=is_reference,
                vial_num=current_vial,
            )
            vial_dur_ms = (time.perf_counter() - t_chk0) * 1000
            ref_vial_num = run_refs_data["recipes"][current_item.recipe_id]["reference_vial"]
            check_mode_label = "blank-normalized"

        if is_reference:
            vial_res["verdict"] = "reference"

        # Log to trial_log.csv in Recorded run mode
        if source_mode == "Recorded run":
            trans_for_log = None
            if current_item.previous_vial_recipe is not None and current_item.previous_vial_recipe != current_item.recipe_id:
                t_log = next(
                    (res["light"] for r1, r2, res in evaluations if r1 == current_item.previous_vial_recipe and r2 == current_item.recipe_id),
                    "N/A",
                )
            else:
                t_log = "GREEN" if current_item.previous_vial_recipe == current_item.recipe_id else "N/A"

            log_trial_vial_if_needed(
                selected_run,
                current_vial,
                current_item.recipe_id,
                current_item.previous_vial_recipe,
                t_log,
                "REFERENCE" if is_reference else vial_res["verdict"].upper(),
                vial_res["delta_e"],
                vial_res["patch"],
                vial_res.get("blank_status", "measured"),
                vial_res.get("lighting_warning"),
                vial_dur_ms,
                "reference vial" if is_reference else "",
            )

        st.markdown(
            f"### **Vial {current_vial:02d}** *(Recipe {current_item.recipe_id} · Batch {batch_pos} of {batch_total})*"
        )

        # Prominent Lighting Warning in Panel 2 if fired
        if source_mode == "Recorded run" and vial_res.get("lighting_warning"):
            st.error(f"💡 **Lighting Warning:** {vial_res['lighting_warning']}")

        # Reference and confidence badges
        if is_reference:
            st.info("🏷️ **Reference vial** (clean reference for this recipe; not inspected)")
        if vial_res["confidence"] == "low":
            st.warning("⚠️ **Low confidence** (< 60 mL target volume; LOW patch used)")

        # Crop vial
        CROP_Y1, CROP_Y2 = 130, 420
        CROP_X1, CROP_X2 = 250, 370
        vial_crop = current_item.frame[CROP_Y1:CROP_Y2, CROP_X1:CROP_X2].copy()

        # Draw colored patch outline on checked production vials
        if not is_reference:
            patch_def = HIGH_PATCH if vial_res["patch"] == "HIGH" else LOW_PATCH
            px1 = patch_def["x_min"] - CROP_X1
            px2 = patch_def["x_max"] - CROP_X1
            py1 = patch_def["y_min"] - CROP_Y1
            py2 = patch_def["y_max"] - CROP_Y1

            outline_bgr = (
                (0, 220, 0)
                if vial_res["verdict"] == "pass"
                else ((0, 190, 255) if vial_res["verdict"] == "unsure" else (0, 0, 255))
            )
            cv2.rectangle(vial_crop, (px1, py1), (px2, py2), outline_bgr, 2)
            cv2.putText(
                vial_crop,
                vial_res["patch"],
                (px1 - 2, py1 - 4),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.36,
                outline_bgr,
                1,
                cv2.LINE_AA,
            )
            caption_text = f"Vial {current_vial:02d} (t = {current_item.mp4_time:.2f} s · {vial_res['patch']} patch outlined)"
        else:
            caption_text = f"Vial {current_vial:02d} (t = {current_item.mp4_time:.2f} s · Clean reference vial)"

        crop_rgb = cv2.cvtColor(vial_crop, cv2.COLOR_BGR2RGB)
        st.image(
            crop_rgb,
            caption=caption_text,
            width=220,
        )

        # Vial metadata and measurement
        prev_v_text = (
            f"Recipe {current_item.previous_vial_recipe}"
            if current_item.previous_vial_recipe is not None
            else "unknown (recording starts here)"
        )
        ref_note = " *(self-reference)*" if is_reference else ""

        st.markdown(
            f"- **Target Volume:** {current_item.total_ml} mL\n"
            f"- **Recipe:** Recipe {current_item.recipe_id} *(Previous: {prev_v_text})*\n"
            f"- **Clean Reference:** Vial {ref_vial_num:02d} (Recipe {current_item.recipe_id}){ref_note}\n"
            f"- **Measurement Patch:** `{vial_res['patch']}` ({vial_res['confidence']} confidence)\n"
            f"- **Color Difference ({check_mode_label}):** **ΔE2000 = {vial_res['delta_e']:.2f}**"
        )

        # Verdict Banner
        if is_reference:
            st.markdown(
                '<div style="background-color: #44474f; color: #f0f2f6; padding: 12px 16px; '
                'border-radius: 6px; font-weight: bold; font-size: 1.25em; text-align: center; margin: 10px 0;">'
                '⚪ REFERENCE (not checked)'
                '</div>',
                unsafe_allow_html=True,
            )
            st.caption("Clean baseline reference for this recipe, not an inspected production vial.")
        else:
            if vial_res["verdict"] == "pass":
                st.success("## 🟢 PASS (In Spec)")
            elif vial_res["verdict"] == "unsure":
                st.warning("## 🟡 UNSURE (Borderline)")
            else:
                st.error("## 🔴 FAIL (Discolored)")
            st.caption("Threshold rule: pass < 2.0, unsure 2.0–5.0, fail > 5.0")

    # -----------------------------------------------------------------------
    # Panel 3: Cosmos Explanation (LIVE)
    # -----------------------------------------------------------------------
    with col_expl:
        st.subheader("3. Cosmos Explanation")
        st.caption("Physical AI Carryover Diagnosis · Grounded in Camera Evidence")

        # 1. Clean reference vials: no carryover explanation needed
        if is_reference:
            st.info("### ⚪ Reference vial (not checked)")
            st.caption("Clean vial of this recipe: used as clean baseline reference, not checked for carryover.")

        # 2. PASS vials: within spec
        elif vial_res["verdict"] == "pass":
            st.success("### 🟢 No explanation needed")
            st.caption(f"Liquid color matches Recipe {current_item.recipe_id} specification (ΔE = {vial_res['delta_e']:.2f} < 2.0).")

        # 3. UNSURE vials: borderline
        elif vial_res["verdict"] == "unsure":
            st.warning("### 🟡 Check by eye (borderline vial)")
            st.caption("Borderline color difference (2.0 ≤ ΔE ≤ 5.0). Operator visual check required.")

        # 4. FAIL vials: carryover diagnosis
        else:
            prev_batch_r = get_batch_previous_recipe_for_vial(df_times, current_vial)
            if prev_batch_r is None:
                st.warning("### ⚪ No explanation: the recipe before this vial is unknown (the recording starts here)")
            else:
                target_r = current_item.recipe_id
                cached_exp = get_explanation(prev_batch_r, target_r)

                if cached_exp:
                    scores_map = get_reviewed_scores()
                    change_key = f"{prev_batch_r}->{target_r}"
                    is_approved = scores_map.get(change_key, False)

                    if is_approved:
                        st.markdown("#### 🔍 Likely Cause:")
                        st.warning(f"**{cached_exp.get('likely_cause', '')}**")

                        st.markdown("#### 🛠️ Operator Action:")
                        st.success(f"**{cached_exp.get('operator_action', '')}**")
                    else:
                        st.warning("### ⚠️ Explanation withheld: failed review (annotations/card9_scores.csv)")
                        st.caption("Cosmos generated an explanation, but human review rejected it against the quality/safety rubric.")
                else:
                    st.warning("### ⚠️ Explanation unavailable (Cosmos not running)")
                    st.caption("Cosmos NIM reasoner server not connected or explanation not cached yet.")

        # Evidence line
        if not is_reference:
            rec_desc = recipe_descriptions.get(current_item.recipe_id, "")
            rec_desc_str = f" (`{rec_desc}`)" if rec_desc else ""

            if batch_pos == 2:
                intended_str = f"Recipe {current_item.recipe_id}{rec_desc_str} — *2nd vial of the batch*"
            else:
                intended_str = f"Recipe {current_item.recipe_id}{rec_desc_str}"

            prev_batch_r = get_batch_previous_recipe_for_vial(df_times, current_vial)
            if prev_batch_r is None:
                prev_recipe_str = "unknown (recording starts here)"
            else:
                p_desc = recipe_descriptions.get(prev_batch_r, "")
                p_desc_str = f" (`{p_desc}`)" if p_desc else ""
                prev_recipe_str = f"Recipe {prev_batch_r}{p_desc_str} (batch previous recipe before Recipe {current_item.recipe_id})"

            measured_lab_str = f"[{vial_res['measured_lab'][0]:.1f}, {vial_res['measured_lab'][1]:.1f}, {vial_res['measured_lab'][2]:.1f}]"
            ref_lab_str = f"[{vial_res['reference_lab'][0]:.1f}, {vial_res['reference_lab'][1]:.1f}, {vial_res['reference_lab'][2]:.1f}]"
            frame_idx = int(df_times.loc[current_vial, "last_parked_frame"])
            patch_span = "y 268–288" if vial_res["patch"] == "HIGH" else "y 352–372"

            st.markdown("---")
            st.markdown("##### 📋 Physical Camera Evidence:")
            st.markdown(
                f"- **Intended Recipe:** {intended_str}\n"
                f"- **Previous Recipe:** {prev_recipe_str}\n"
                f"- **Observed Color Shift:** Measured Lab `{measured_lab_str}` vs Reference Lab `{ref_lab_str}`\n"
                f"- **Color Distance ({check_mode_label}):** ΔE2000 = **{vial_res['delta_e']:.2f}** on `{vial_res['patch']}` patch ({patch_span})\n"
                f"- **Camera Frame:** Frame {frame_idx} (`{Path(video_mp4).name}`, t = {current_item.mp4_time:.2f} s)"
            )

    # -----------------------------------------------------------------------
    # Inference Cascade Counter
    # -----------------------------------------------------------------------
    st.markdown("---")
    st.subheader("📊 Inference Cascade Counter")
    st.caption("Cascade execution metrics · Cheap math first, AI only when needed")

    so_far_records = all_records[:current_vial]
    n_refs_so_far = sum(1 for r in so_far_records if r["verdict"] == "reference")
    n_prod_so_far = len(so_far_records) - n_refs_so_far
    n_pass_so_far = sum(1 for r in so_far_records if r["verdict"] == "pass")
    n_unsure_so_far = sum(1 for r in so_far_records if r["verdict"] == "unsure")
    n_fail_so_far = sum(1 for r in so_far_records if r["verdict"] == "fail")

    cnt_col1, cnt_col2, cnt_col3, cnt_col4, cnt_col5 = st.columns(5)

    n_changes_total = len(QUEUE_RECIPES) - 1
    with cnt_col1:
        st.metric(
            "Step 1 · Pre-Fill",
            f"{min(current_vial, n_changes_total)} / {n_changes_total} Changes",
            "100% queue advisory",
        )
    with cnt_col2:
        st.metric(
            "Step 2 · Color-Checked",
            f"{n_prod_so_far} / {max_vials - sum(1 for r in all_records if r['verdict'] == 'reference')} Vials",
            f"{n_pass_so_far} passed",
        )
    with cnt_col3:
        st.metric(
            "Reference Vials",
            f"{n_refs_so_far} / {sum(1 for r in all_records if r['verdict'] == 'reference')} Vials",
            "Clean references (not checked)",
        )
    with cnt_col4:
        st.metric(
            "Step 3 · Unsure Zone",
            f"{n_unsure_so_far} Vials",
            "Borderline (eye check)",
        )
    with cnt_col5:
        st.metric(
            "Step 4 · Explanation",
            f"{n_fail_so_far} Vials",
            "Flagged for Cosmos",
        )

    st.markdown(
        f"**Run Throughput:** Progress: Vial **{current_vial} of {max_vials}** replayed · "
        f"**Reference vials ({n_refs_so_far})** (not checked) · "
        f"{n_prod_so_far} production vials color-checked: **{n_pass_so_far} PASS**, **{n_unsure_so_far} UNSURE** · "
        f"**Flagged for explanation: {n_fail_so_far}**"
    )
    st.caption(
        f"⏱️ **Timing:** color math only, frame already loaded: ~{avg_math_ms:.1f} ms/vial · "
        f"including reading frame from video: ~{avg_total_ms:.0f} ms/vial"
    )

    # -----------------------------------------------------------------------
    # Step 8: End-of-Run Summary Table
    # -----------------------------------------------------------------------
    if current_vial == max_vials:
        judge_df = None
        judge_source_name = None

        if source_mode == "Video 5 (demo)":
            verdicts_csv = REPO_ROOT / "annotations" / "video5_visual_verdicts.csv"
            if verdicts_csv.exists():
                judge_df = pd.read_csv(verdicts_csv).set_index("vial")
                judge_source_name = "judge_1 (Teammate By-Eye)"
        else:
            run_judge_csv = REPO_ROOT / "outputs" / "runs" / selected_run / "judge_verdicts.csv"
            if run_judge_csv.exists():
                judge_df = pd.read_csv(run_judge_csv).set_index("vial")
                judge_source_name = "Judge (On-Site By-Eye)"

        # Only display summary table if judge verdicts are available
        if judge_df is not None:
            st.markdown("---")
            st.subheader("📋 End-of-Run Summary (All FAIL & UNSURE Vials)")
            st.caption(
                f"Side-by-side comparison of Copilot color check verdicts vs {judge_source_name}. "
                "Verified against on-site / annotated by-eye judging sheet."
            )

            summary_rows = []
            for r in all_records:
                v_num = r["vial"]
                verd = r["verdict"]
                if verd in ("fail", "unsure"):
                    j_col = "judge_1" if "judge_1" in judge_df.columns else "verdict"
                    j_val = judge_df.loc[v_num, j_col] if v_num in judge_df.index else "N/A"
                    bpos_str = f"{r['batch_pos']} of 3"
                    verdict_badge = "🔴 FAIL" if verd == "fail" else "🟡 UNSURE"
                    summary_rows.append({
                        "Vial": f"Vial {v_num:02d}",
                        "Recipe": f"Recipe {r['recipe_id']}",
                        "Batch Pos": bpos_str,
                        "Volume": f"{r['total_ml']} mL",
                        "Patch": r["patch"],
                        "ΔE2000": f"{r['delta_e']:.2f}",
                        "Copilot Verdict": verdict_badge,
                        judge_source_name: str(j_val),
                    })

            if summary_rows:
                df_summary = pd.DataFrame(summary_rows)
                st.dataframe(df_summary, use_container_width=True, hide_index=True)

                pass_vials = [r["vial"] for r in all_records if r["verdict"] == "pass"]
                j_col = "judge_1" if "judge_1" in judge_df.columns else "verdict"
                pass_misses = sum(
                    1
                    for v in pass_vials
                    if v in judge_df.index and judge_df.loc[v, j_col] in ("off", "unsure")
                )
                st.markdown(
                    f"**Verification:** PASS vials the judge called off or unsure: **{pass_misses} of {len(pass_vials)}**."
                )

    # -----------------------------------------------------------------------
    # Auto-play Handler (advances one vial every 3 seconds)
    # -----------------------------------------------------------------------
    if auto_play and st.session_state.vial_index < max_vials:
        time.sleep(3)
        st.session_state.vial_index += 1
        st.rerun()
