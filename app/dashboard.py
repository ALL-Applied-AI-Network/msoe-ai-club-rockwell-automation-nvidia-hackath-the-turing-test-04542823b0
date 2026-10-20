"""
app/dashboard.py
Card 10, Step 4: Operator dashboard page skeleton.

Carryover Copilot · Fluid Mixing Station 3
Three panels side by side:
1. Recipe Queue: Pre-fill risk lights and queue reorder advisor
2. Latest Vial: Post-fill camera color verification, patch metrics, and PASS/UNSURE/FAIL verdict
3. Explanation: Plain-English explanation grounded in camera evidence and recipes (Cosmos Reason)

Run with:
    streamlit run app/dashboard.py
"""

from pathlib import Path
import sys
import streamlit as st

# Add scripts folder to sys.path so we can import project modules cleanly
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

st.set_page_config(
    page_title="Carryover Copilot · Fluid Mixing Station 3",
    page_icon="🧪",
    layout="wide",
)

st.title("🧪 Carryover Copilot · Fluid Mixing Station 3")
st.caption("Predictive Flush Advisory · In-Line Camera Color Verification · Cosmos Physical AI Explanations")
st.warning("⚠️ **EXAMPLE TEXT, NOT LIVE** — Dashboard skeleton (Step 4). Live model predictions and data replay arrive in Steps 5–7.")
st.markdown("---")

# Layout: 3 panels side by side
col_queue, col_vial, col_expl = st.columns([1.1, 1.2, 1.3], gap="medium")

# ---------------------------------------------------------------------------
# Panel 1: Recipe Queue
# ---------------------------------------------------------------------------
with col_queue:
    st.subheader("1. Recipe Queue")
    st.caption("*(EXAMPLE TEXT, NOT LIVE)*")
    st.markdown("**Upcoming Recipe Sequence:** *(EXAMPLE TEXT, NOT LIVE)*")
    st.code("5 → 6 → [ 7 ] → 8 → 9 → 10 → 11 → 12 → 13 → 14", language="text")

    st.markdown("#### Next Change: Recipe 6 → Recipe 7 *(EXAMPLE TEXT, NOT LIVE)*")
    st.info(
        "**Dispense Shift:** *(EXAMPLE TEXT, NOT LIVE)*\n"
        "- From Recipe 6: `10 mL orange + 30 mL clear` (40 mL)\n"
        "- To Recipe 7: `50 mL blue + 20 mL clear` (70 mL)\n"
        "- Expected recipe color gap: **ΔE = 30.1** (LOW patch)"
    )

    st.error("🔴 **HIGH RISK (RED LIGHT)** *(EXAMPLE TEXT, NOT LIVE)*\n\n**Action:** Flush or reorder; a flush needs the plant manager's approval, and its effect isn't measured yet.")

    st.markdown("---")
    st.markdown("**Queue Reorder Advisor:** *(EXAMPLE TEXT, NOT LIVE)*")
    st.markdown(
        "*Active batch window (next 3 recipes: 7, 8, 9):*\n"
        "> Reordering to `8 → 9 → 7` reduces RED changes from 3 to 2. *(Needs the planner's OK)*\n\n"
        "*(EXAMPLE TEXT, NOT LIVE)*"
    )

# ---------------------------------------------------------------------------
# Panel 2: Latest Vial
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
# Panel 3: Explanation
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
