"""
app/dashboard.py
Card 10, Step 6: Vial replay panel wired to replay_feed.py and vial_check.py.

Carryover Copilot · Fluid Mixing Station 3
Three panels side by side:
1. Recipe Queue: Pre-fill risk lights and queue reorder advisor (LIVE - flush_advisor.py)
2. Latest Vial: Post-fill camera color verification, patch metrics, and PASS/UNSURE/FAIL verdict (LIVE - replay_feed.py & vial_check.py)
3. Explanation: Plain-English explanation grounded in camera evidence and recipes (example text until Step 7)

Run with:
    streamlit run app/dashboard.py
"""

from pathlib import Path
import sys
import time
import itertools
import cv2
import numpy as np
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


st.title("🧪 Carryover Copilot · Fluid Mixing Station 3")
st.caption("Predictive Flush Advisory · In-Line Camera Color Verification · Cosmos Physical AI Explanations")
st.info("ℹ️ **Card 10 Step 6:** Panels 1 & 2 are LIVE (wired to flush_advisor.py, replay_feed.py, and vial_check.py). Panel 3 shows example text until Step 7.")
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
        batch_p_text = (
            f"Recipe {current_item.batch_previous_recipe}"
            if current_item.batch_previous_recipe is not None
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
    # Panel 3: Explanation (placeholder text until Step 7)
    # -----------------------------------------------------------------------
    with col_expl:
        st.subheader("3. Cosmos Explanation")
        st.caption("*(EXAMPLE TEXT, NOT LIVE — live explanation cache arrives in Step 7)*")
        st.markdown("#### Status: Flagged Vial Discoloration Analysis *(EXAMPLE TEXT, NOT LIVE)*")

        st.markdown("##### 🔍 Likely Cause: *(EXAMPLE TEXT, NOT LIVE)*")
        st.warning("Carryover from Recipe 6 (orange dye) tinted the initial Recipe 7 fill (blue dye), producing green liquid.\n\n*(EXAMPLE TEXT, NOT LIVE)*")

        st.markdown("##### 🛠️ Operator Action: *(EXAMPLE TEXT, NOT LIVE)*")
        st.success("Quarantine vial 7 and verify vial 8 is clear blue before continuing production.\n\n*(EXAMPLE TEXT, NOT LIVE)*")

        st.markdown("---")
        st.markdown("##### 📋 Physical Camera Evidence: *(EXAMPLE TEXT, NOT LIVE)*")
        st.markdown(
            "*(EXAMPLE TEXT, NOT LIVE)*\n"
            "- **Intended Recipe:** Recipe 7 (`50 mL blue + 20 mL clear`)\n"
            "- **Previous Recipe:** Recipe 6 (`10 mL orange + 30 mL clear`)\n"
            "- **Observed Color Shift:** Measured Lab `[16.0, -14.2, 4.6]` vs Reference Lab `[34.1, -8.3, -26.0]`\n"
            "- **Color Distance:** ΔE2000 = **25.55** on HIGH patch (y 268–288)\n"
            "- **Camera Frame:** Frame 9283 (`vial_fill_video_5.mp4`, t = 309.43 s)"
        )

    # -----------------------------------------------------------------------
    # Auto-play Handler (advances one vial every 3 seconds)
    # -----------------------------------------------------------------------
    if auto_play and st.session_state.vial_index < 30:
        time.sleep(3)
        st.session_state.vial_index += 1
        st.rerun()
