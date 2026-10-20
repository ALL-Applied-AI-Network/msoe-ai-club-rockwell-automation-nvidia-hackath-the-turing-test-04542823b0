"""
app/dashboard.py
Card 10, Step 5: Recipe queue panel with risk lights and reorder advisor.

Carryover Copilot · Fluid Mixing Station 3
Three panels side by side:
1. Recipe Queue: Pre-fill risk lights and queue reorder advisor (LIVE - wired to flush_advisor.py)
2. Latest Vial: Post-fill camera color verification, patch metrics, and PASS/UNSURE/FAIL verdict (example text until Step 6)
3. Explanation: Plain-English explanation grounded in camera evidence and recipes (example text until Step 7)

Run with:
    streamlit run app/dashboard.py
"""

from pathlib import Path
import sys
import itertools
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

st.set_page_config(
    page_title="Carryover Copilot · Fluid Mixing Station 3",
    page_icon="🧪",
    layout="wide",
)

st.title("🧪 Carryover Copilot · Fluid Mixing Station 3")
st.caption("Predictive Flush Advisory · In-Line Camera Color Verification · Cosmos Physical AI Explanations")
st.info("ℹ️ **Card 10 Step 5:** Panel 1 is LIVE (wired to flush_advisor.py). Panels 2 & 3 show example text until Steps 6 & 7.")
st.markdown("---")

# Layout: 3 panels side by side
col_queue, col_vial, col_expl = st.columns([1.2, 1.1, 1.3], gap="medium")

# ---------------------------------------------------------------------------
# Panel 1: Recipe Queue (LIVE)
# ---------------------------------------------------------------------------
with col_queue:
    st.subheader("1. Recipe Queue")
    st.caption("Pre-Fill Carryover Risk Advisor · Lookahead Scheduler")

    # Pre-flight check: ensure required baseline and model files exist
    if not BASELINE_CSV.exists():
        st.error("Missing outputs/card3/baseline_results.csv. Run scripts/baseline_check.py first.")
    elif not RISK_JSON.exists():
        st.error("Missing outputs/card4/risk_model.json. Run scripts/baseline_check.py, then scripts/fit_risk_model.py first.")
    else:
        refs = load_clean_references()
        high_alpha, low_alpha = load_risk_alphas()

        # Full recipe order for video 5
        QUEUE_RECIPES = [5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
        evaluations, num_red, num_amber, total_err = evaluate_order(
            QUEUE_RECIPES, None, refs, high_alpha, low_alpha
        )

        # Active / next change (default 6 -> 7; Step 6 replay feed updates this dynamically)
        upcoming_change = st.session_state.get("active_change", (6, 7))

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
            st.markdown(f"#### ⚡ Next Change: Recipe {up_r1} → Recipe {up_r2}")
            
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

        # -------------------------------------------------------------------
        # Reorder Advice for the next 3 recipes (Batch Scheduler holds up to 3)
        # -------------------------------------------------------------------
        st.markdown("**Queue Reorder Advisor:**")
        # Identify next 3 recipes in queue starting from upcoming_change[1]
        try:
            up_idx = QUEUE_RECIPES.index(upcoming_change[1])
            window_3 = QUEUE_RECIPES[up_idx : up_idx + 3]
            after_r = upcoming_change[0]
        except Exception:
            window_3 = QUEUE_RECIPES[:3]
            after_r = None

        st.caption(f"Active Batch Scheduler window (3 recipes): `{' → '.join(str(r) for r in window_3)}` (after Recipe {after_r})")

        if len(window_3) <= 1:
            st.info("Current order is already optimal (only 1 recipe remaining in queue window).")
        else:
            _, cur_red, cur_amber, cur_err = evaluate_order(window_3, after_r, refs, high_alpha, low_alpha)

            unique_perms = sorted(list(set(itertools.permutations(window_3))))
            best_perm = tuple(window_3)
            best_red = cur_red
            best_amber = cur_amber
            best_err = cur_err
            found_improvement = False

            for perm in unique_perms:
                if perm == tuple(window_3):
                    continue
                _, num_r, num_a, tot_e = evaluate_order(perm, after_r, refs, high_alpha, low_alpha)
                if num_r is None:
                    continue

                is_strictly_fewer_red = num_r < best_red
                is_fewer_amber = (num_r == best_red) and (num_a < best_amber)
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

# ---------------------------------------------------------------------------
# Panel 2: Latest Vial (placeholder text until Step 6)
# ---------------------------------------------------------------------------
with col_vial:
    st.subheader("2. Latest Vial Inspection")
    st.caption("*(EXAMPLE TEXT, NOT LIVE)*")
    st.markdown("### **Vial 07** *(Recipe 7 · Batch 1 of 3 — EXAMPLE TEXT, NOT LIVE)*")

    # Display vial 7 image if available; show "no image yet" if missing or failed
    v7_img_path = REPO_ROOT / "scratch/replay_v7.jpg"
    if v7_img_path.exists():
        try:
            st.image(str(v7_img_path), caption="Vial 7 parked under vial_fill camera (t = 309.43 s)", use_container_width=True)
        except Exception:
            st.info("no image yet")
    else:
        st.info("no image yet")

    st.markdown(
        "*(EXAMPLE TEXT, NOT LIVE)*\n"
        "- **Target Volume:** 70 mL\n"
        "- **Measurement Patch:** HIGH patch (normal confidence)\n"
        "- **Clean Reference:** Vial 09 (Recipe 7 clean 3rd vial)\n"
        "- **Color Difference:** **ΔE2000 = 25.55**"
    )

    st.error("## 🔴 FAIL (Discolored) *(EXAMPLE TEXT, NOT LIVE)*")
    st.caption("Threshold rule: pass < 2.0, unsure 2.0–5.0, fail > 5.0")

# ---------------------------------------------------------------------------
# Panel 3: Explanation (placeholder text until Step 7)
# ---------------------------------------------------------------------------
with col_expl:
    st.subheader("3. Cosmos Explanation")
    st.caption("*(EXAMPLE TEXT, NOT LIVE)*")
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
