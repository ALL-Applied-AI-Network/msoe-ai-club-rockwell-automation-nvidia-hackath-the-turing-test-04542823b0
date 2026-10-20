"""
app/dashboard.py
Card 10, Step 7: Explanation panel and cascade counter.

Carryover Copilot · Fluid Mixing Station 3
Three panels side by side + cascade counter:
1. Recipe Queue: Pre-fill risk lights and queue reorder advisor (LIVE - flush_advisor.py)
2. Latest Vial: Post-fill camera color verification, patch metrics, and PASS/UNSURE/FAIL verdict (LIVE - replay_feed.py & vial_check.py)
3. Explanation: Plain-English explanation grounded in camera evidence and recipes (LIVE - explanation_cache.py)
Below: Inference Cascade Counter tracking vials across all 4 cascade steps.

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
    load_risk_alphas,
    BASELINE_CSV,
    RISK_JSON,
)
from replay_feed import get_vial, VialFeedItem, DEFAULT_TIMES_CSV, DEFAULT_VIDEO_MP4
from vial_check import check_vial, load_references, HIGH_PATCH, LOW_PATCH
from explanation_cache import get as get_explanation

st.set_page_config(
    page_title="Carryover Copilot · Fluid Mixing Station 3",
    page_icon="🧪",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Session State Initialization
# ---------------------------------------------------------------------------
if "vial_index" not in st.session_state:
    st.session_state.vial_index = 1


def get_active_change_for_vial(vial_num: int, recipe_id: int) -> tuple[int, int]:
    """
    Determines which recipe transition Panel 1 should highlight based on current vial.
    For the 3rd vial of a batch (before next batch starts), looks ahead to (R, R+1).
    Otherwise, highlights the transition that introduced this recipe (R-1, R).
    """
    batch_pos = ((vial_num - 1) % 3) + 1
    if batch_pos == 3 and recipe_id < 14:
        return (recipe_id, recipe_id + 1)
    elif recipe_id > 5:
        return (recipe_id - 1, recipe_id)
    else:
        return (5, 6)


# Cache reference colors from clean 3rd vials
@st.cache_resource
def get_cached_vial_references():
    return load_references()


# Cache recipe composition descriptions (e.g. "10 mL orange + 30 mL clear")
@st.cache_data
def get_cached_recipe_descriptions():
    rec_csv = REPO_ROOT / "data/csi-vial-fill-dataset/vial_fill/labels/video5_vial_recipes.csv"
    if not rec_csv.exists():
        return {}
    df = pd.read_csv(rec_csv).set_index("vial")
    lookup = {}
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


# Precompute & cache verdicts and color check duration across all 30 vials
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
            "verdict": verdict,
            "delta_e": res["delta_e"],
            "patch": res["patch"],
        })
    avg_math_ms = sum(math_durations) / len(math_durations) if math_durations else 0.7
    avg_total_ms = sum(total_durations) / len(total_durations) if total_durations else 75.0
    return records, avg_math_ms, avg_total_ms


st.title("🧪 Carryover Copilot · Fluid Mixing Station 3")
st.caption("Predictive Flush Advisory · In-Line Camera Color Verification · Cosmos Physical AI Explanations")
st.info("ℹ️ **Card 10 Step 7:** All 3 panels and Cascade Counter are LIVE (wired to flush_advisor.py, replay_feed.py, vial_check.py, and explanation_cache.py).")
st.markdown("---")

# Layout: 3 panels side by side
col_queue, col_vial, col_expl = st.columns([1.1, 1.2, 1.3], gap="medium")

# Pre-flight check: ensure required baseline and model files exist
prereqs_ok = True
if not BASELINE_CSV.exists():
    st.error("Missing outputs/card3/baseline_results.csv. Run scripts/baseline_check.py first.")
    prereqs_ok = False
elif not RISK_JSON.exists():
    st.error("Missing outputs/card4/risk_model.json. Run scripts/baseline_check.py, then scripts/fit_risk_model.py first.")
    prereqs_ok = False

if prereqs_ok:
    advisor_refs = load_clean_references()
    high_alpha, low_alpha = load_risk_alphas()
    vial_refs = get_cached_vial_references()
    recipe_descriptions = get_cached_recipe_descriptions()
    all_30_records, avg_math_ms, avg_total_ms = get_all_30_verdicts()

    df_times = pd.read_csv(DEFAULT_TIMES_CSV).set_index("vial")

    # Determine current vial and active change
    current_vial = st.session_state.vial_index
    current_item = get_vial(current_vial, with_frame=True)
    upcoming_change = get_active_change_for_vial(current_vial, current_item.recipe_id)

    # -----------------------------------------------------------------------
    # Panel 1: Recipe Queue (LIVE)
    # -----------------------------------------------------------------------
    with col_queue:
        st.subheader("1. Recipe Queue")
        st.caption("Pre-Fill Carryover Risk Advisor · Lookahead Scheduler")

        # Full recipe order for video 5
        QUEUE_RECIPES = [5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
        evaluations, num_red, num_amber, total_err = evaluate_order(
            QUEUE_RECIPES, None, advisor_refs, high_alpha, low_alpha
        )

        # Visual sequence of recipe boxes with risk lights
        st.markdown("**Recipe Sequence & Risk Lights (Video 5):**")
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
                light_icon = "🔴" if t_res["light"] == "RED" else ("🟡" if t_res["light"] == "AMBER" else "🟢")
                is_active_trans = (r == upcoming_change[0] and r_next == upcoming_change[1])
                sep_style = "font-weight: bold; padding: 0 2px;"
                if is_active_trans:
                    pills_html.append(f'<span style="{sep_style}; color: #00c0f0;">👉{light_icon}→</span>')
                else:
                    pills_html.append(f'<span style="{sep_style}">{light_icon}→</span>')
        pills_html.append('</div>')
        st.markdown("".join(pills_html), unsafe_allow_html=True)

        # Highlight the next change coming up
        up_r1, up_r2 = upcoming_change
        up_eval = next((res for r1, r2, res in evaluations if r1 == up_r1 and r2 == up_r2), None)

        if up_eval:
            light_name = up_eval["light"]
            light_badge = "🔴 HIGH RISK (RED LIGHT)" if light_name == "RED" else (
                "🟡 MEDIUM RISK (AMBER LIGHT)" if light_name == "AMBER" else "🟢 LOW RISK (GREEN LIGHT)"
            )
            st.markdown(f"#### ⚡ Active Change: Recipe {up_r1} → Recipe {up_r2}")
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

        # Details list of all transitions in video 5
        with st.expander("📋 All Queue Transitions (5 → 14)", expanded=False):
            for r1, r2, res in evaluations:
                is_active = (r1 == upcoming_change[0] and r2 == upcoming_change[1])
                marker = "👉 " if is_active else ""
                icon = "🔴" if res["light"] == "RED" else ("🟡" if res["light"] == "AMBER" else "🟢")
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
            if st.button("▶ Next Vial", use_container_width=True, disabled=(current_vial >= 30)):
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
            max_value=30,
            value=current_vial,
            key="vial_slider",
            label_visibility="collapsed",
        )
        if slider_val != current_vial:
            st.session_state.vial_index = slider_val
            st.rerun()

        # Inspection calculation
        batch_pos = ((current_vial - 1) % 3) + 1
        is_reference = (batch_pos == 3)
        vial_res = check_vial(
            current_item.frame,
            current_item.recipe_id,
            current_item.total_ml,
            vial_refs,
            is_reference=is_reference,
        )

        if is_reference:
            vial_res["verdict"] = "reference"

        st.markdown(f"### **Vial {current_vial:02d}** *(Recipe {current_item.recipe_id} · Batch {batch_pos} of 3)*")

        # Reference and confidence badges
        if is_reference:
            st.info("🏷️ **Reference vial** (clean 3rd vial of this recipe; not inspected)")
        if vial_res["confidence"] == "low":
            st.warning("⚠️ **Low confidence** (< 60 mL target volume; LOW patch used)")

        # Crop vial
        CROP_Y1, CROP_Y2 = 130, 420
        CROP_X1, CROP_X2 = 250, 370
        vial_crop = current_item.frame[CROP_Y1:CROP_Y2, CROP_X1:CROP_X2].copy()

        # Only draw colored patch outline on checked production vials (not on reference vials)
        if not is_reference:
            patch_def = HIGH_PATCH if vial_res["patch"] == "HIGH" else LOW_PATCH
            px1 = patch_def["x_min"] - CROP_X1
            px2 = patch_def["x_max"] - CROP_X1
            py1 = patch_def["y_min"] - CROP_Y1
            py2 = patch_def["y_max"] - CROP_Y1

            outline_bgr = (0, 220, 0) if vial_res["verdict"] == "pass" else (
                (0, 190, 255) if vial_res["verdict"] == "unsure" else (0, 0, 255)
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
        ref_vial_num = vial_refs[current_item.recipe_id]["reference_vial"]
        ref_note = " *(self-reference)*" if is_reference else ""

        st.markdown(
            f"- **Target Volume:** {current_item.total_ml} mL\n"
            f"- **Recipe:** Recipe {current_item.recipe_id} *(Previous: {prev_v_text})*\n"
            f"- **Clean Reference:** Vial {ref_vial_num:02d} (Recipe {current_item.recipe_id}){ref_note}\n"
            f"- **Measurement Patch:** `{vial_res['patch']}` ({vial_res['confidence']} confidence)\n"
            f"- **Color Difference:** **ΔE2000 = {vial_res['delta_e']:.2f}**"
        )

        # Verdict Banner: Gray banner for reference vials, colored banner for checked production vials
        if is_reference:
            st.markdown(
                '<div style="background-color: #44474f; color: #f0f2f6; padding: 12px 16px; '
                'border-radius: 6px; font-weight: bold; font-size: 1.25em; text-align: center; margin: 10px 0;">'
                '⚪ REFERENCE (not checked)'
                '</div>',
                unsafe_allow_html=True,
            )
            st.caption("Clean 3rd vial: baseline reference for this recipe, not an inspected production vial.")
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
            st.caption("Clean 3rd vial of this recipe: used as clean baseline reference, not checked for carryover.")

        # 2. PASS vials: within spec
        elif vial_res["verdict"] == "pass":
            st.success("### 🟢 No explanation needed")
            st.caption(f"Liquid color matches Recipe {current_item.recipe_id} specification (ΔE = {vial_res['delta_e']:.2f} < 2.0).")

        # 3. UNSURE vials: borderline
        elif vial_res["verdict"] == "unsure":
            st.warning("### 🟡 Check by eye (vial model not built)")
            st.caption("Borderline color difference (2.0 ≤ ΔE ≤ 5.0). Small synthetic-trained vial model (Cascade Step 3) not built.")

        # 4. FAIL vials: carryover investigation
        else:
            if current_vial == 1:
                st.warning("### ⚪ No explanation: the recipe before vial 1 is unknown (the recording starts here)")
            else:
                # Look up cached explanation using batch_previous_recipe -> recipe_id
                prev_batch_r = current_item.batch_previous_recipe
                target_r = current_item.recipe_id
                cached_exp = get_explanation(prev_batch_r, target_r)

                if cached_exp:
                    st.markdown("#### 🔍 Likely Cause:")
                    st.warning(f"**{cached_exp.get('likely_cause', '')}**")

                    st.markdown("#### 🛠️ Operator Action:")
                    st.success(f"**{cached_exp.get('operator_action', '')}**")
                else:
                    st.warning("### ⚠️ Explanation unavailable (Cosmos not running)")
                    st.caption("Cosmos NIM reasoner server not connected or explanation not cached yet.")

        # Evidence line (shown for FAIL, UNSURE, and checked vials)
        if not is_reference:
            rec_desc = recipe_descriptions.get(current_item.recipe_id, "")
            rec_desc_str = f" (`{rec_desc}`)" if rec_desc else ""

            # Check if 2nd vial of batch
            if batch_pos == 2:
                intended_str = f"Recipe {current_item.recipe_id}{rec_desc_str} — *2nd vial of the batch*"
            else:
                intended_str = f"Recipe {current_item.recipe_id}{rec_desc_str}"

            if current_vial == 1:
                prev_recipe_str = "unknown (recording starts here)"
            else:
                p_batch = current_item.batch_previous_recipe
                p_desc = recipe_descriptions.get(p_batch, "")
                p_desc_str = f" (`{p_desc}`)" if p_desc else ""
                prev_recipe_str = f"Recipe {p_batch}{p_desc_str} (batch previous recipe before Recipe {current_item.recipe_id})"

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
                f"- **Color Distance:** ΔE2000 = **{vial_res['delta_e']:.2f}** on `{vial_res['patch']}` patch ({patch_span})\n"
                f"- **Camera Frame:** Frame {frame_idx} (`vial_fill_video_5.mp4`, t = {current_item.mp4_time:.2f} s)"
            )

    # -----------------------------------------------------------------------
    # Inference Cascade Counter
    # -----------------------------------------------------------------------
    st.markdown("---")
    st.subheader("📊 Inference Cascade Counter")
    st.caption("Cascade execution metrics across Video 5 sequence · Cheap math first, AI only when needed")

    # Metrics replayed so far (up to current_vial)
    so_far_records = all_30_records[:current_vial]
    n_refs_so_far = sum(1 for r in so_far_records if r["verdict"] == "reference")
    n_prod_so_far = len(so_far_records) - n_refs_so_far
    n_pass_so_far = sum(1 for r in so_far_records if r["verdict"] == "pass")
    n_unsure_so_far = sum(1 for r in so_far_records if r["verdict"] == "unsure")
    n_fail_so_far = sum(1 for r in so_far_records if r["verdict"] == "fail")

    cnt_col1, cnt_col2, cnt_col3, cnt_col4, cnt_col5 = st.columns(5)

    with cnt_col1:
        st.metric(
            "Step 1 · Pre-Fill",
            f"{min(current_vial, 9)} / 9 Changes",
            "100% queue advisory",
        )
    with cnt_col2:
        st.metric(
            "Step 2 · Color-Checked",
            f"{n_prod_so_far} / 20 Vials",
            f"{n_pass_so_far} passed",
        )
    with cnt_col3:
        st.metric(
            "Reference Vials",
            f"{n_refs_so_far} / 10 Vials",
            "Clean 3rd (not checked)",
        )
    with cnt_col4:
        st.metric(
            "Step 3 · Unsure Zone",
            f"{n_unsure_so_far} / 2 Vials",
            "Borderline (eye check)",
        )
    with cnt_col5:
        st.metric(
            "Step 4 · Explanation",
            f"{n_fail_so_far} / 11 Vials",
            "Flagged for Cosmos",
        )

    st.markdown(
        f"**Run Throughput:** Progress: Vial **{current_vial} of 30** replayed · "
        f"**Reference vials (10)** (clean 3rd vials; not checked) · "
        f"20 production vials color-checked: **{n_pass_so_far} PASS**, **{n_unsure_so_far} UNSURE** · "
        f"**Flagged for explanation: {n_fail_so_far}** (10 with a known recipe change, 1 with unknown previous recipe)"
    )
    st.caption(
        f"⏱️ **Timing:** color math only, frame already loaded: ~{avg_math_ms:.1f} ms/vial · "
        f"including reading frame from video: ~{avg_total_ms:.0f} ms/vial"
    )

    # -----------------------------------------------------------------------
    # Auto-play Handler (advances one vial every 3 seconds)
    # -----------------------------------------------------------------------
    if auto_play and st.session_state.vial_index < 30:
        time.sleep(3)
        st.session_state.vial_index += 1
        st.rerun()
