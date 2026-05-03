import streamlit as st
import pandas as pd
import io
import os

# =====================================================
# PAGE CONFIG
# =====================================================
st.set_page_config(page_title="SmartPack - Container Load Planner", layout="wide")

# =====================================================
# GLOBAL CSS (FONT + COLORS)
# =====================================================
st.markdown("""
<style>
html, body, [class*="css"] {
    font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont,
                 "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}

h1 {
    color: #1F2937;
    font-weight: 600;
}

label {
    font-weight: 500;
    color: #1F2937;
}

.stButton > button {
    background-color: #22863A;
    color: white;
    font-weight: 600;
    border-radius: 8px;
    padding: 10px 16px;
}

.stButton > button:hover {
    background-color: #1E7A35;
}
</style>
""", unsafe_allow_html=True)

# =====================================================
# HEADER (LOGO LEFT, TITLE CENTER, TEXT RIGHT)
# =====================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGO_PATH = os.path.join(BASE_DIR, "john_deere_logo.png")

col1, col2, col3 = st.columns([1.5, 4, 2])

with col1:
    if os.path.exists(LOGO_PATH):
        st.image(LOGO_PATH, width=140)
    else:
        st.markdown("<h4 style='color:#367C2B;'>John Deere</h4>", unsafe_allow_html=True)

with col2:
    st.markdown(
        "<h1 style='text-align:center;'>🚚 SmartPack - Container Load Planner</h1>",
        unsafe_allow_html=True
    )

with col3:
    st.markdown(
        "<div style='text-align:right; font-weight:600; padding-top:22px;'>"
        "JOHN DEERE LOGISTICS ENGINEERING<br>"
        "JOHN DEERE KERNERSVILLE"
        "</div>",
        unsafe_allow_html=True
    )

st.markdown("---")

# =====================================================
# CONTAINER DEFINITIONS
# =====================================================
CONTAINERS = {
    "40 HC": {"L": 11938, "W": 2286, "H": 2540, "MAX_WT": 18000},
    "20 HC": {"L": 5898, "W": 2286, "H": 2540, "MAX_WT": 18000},
    "53 Dry Van": {"L": 16002, "W": 2286, "H": 2590, "MAX_WT": 18000},
}

# =====================================================
# INPUT COLUMNS
# =====================================================
DISPLAY_COLUMNS = [
    "Rack / Finished Good",
    "Quantity",
    "Length (MM)",
    "Width (MM)",
    "Height (MM)",
    "Weight (Kg)",
]

# =====================================================
# MAXRECTS GEOMETRY (UNCHANGED)
# =====================================================
class Rect:
    def __init__(self, x, y, w, h):
        self.x, self.y, self.w, self.h = x, y, w, h

    def fits(self, w, h):
        return w <= self.w and h <= self.h

    def split(self, w, h):
        parts = []
        if self.w - w > 0:
            parts.append(Rect(self.x + w, self.y, self.w - w, h))
        if self.h - h > 0:
            parts.append(Rect(self.x, self.y + h, self.w, self.h - h))
        return parts


class MaxRectsBin:
    def __init__(self, w, h):
        self.free = [Rect(0, 0, w, h)]

    def place(self, w, h):
        best = None
        best_score = None
        for fr in self.free:
            for pw, ph in ((w, h), (h, w)):
                if fr.fits(pw, ph):
                    score = min(fr.w - pw, fr.h - ph)
                    if best is None or score < best_score:
                        best = (fr, pw, ph)
                        best_score = score
        if not best:
            return False
        fr, pw, ph = best
        self.free.remove(fr)
        self.free.extend(fr.split(pw, ph))
        return True

# =====================================================
# PACKING ENGINE (UNCHANGED BEHAVIOR + WEIGHT LIMIT)
# =====================================================
def pack_containers_exact(df, container):

    remaining_qty = {
        r["Rack / Finished Good"]: int(r["Quantity"])
        for _, r in df.iterrows()
    }

    rack_dims = {
        r["Rack / Finished Good"]: (
            int(r["Length (MM)"]),
            int(r["Width (MM)"]),
            int(r["Height (MM)"]),
            float(r["Weight (Kg)"]),
        )
        for _, r in df.iterrows()
    }

    containers = []

    while any(q > 0 for q in remaining_qty.values()):
        bin = MaxRectsBin(container["L"], container["W"])
        load = {}
        current_weight = 0.0
        placed_any = False

        order = sorted(
            remaining_qty.keys(),
            key=lambda k: rack_dims[k][0] * rack_dims[k][1],
            reverse=True
        )

        for rack in order:
            qty_left = remaining_qty[rack]
            if qty_left <= 0:
                continue

            l, w, h, wt = rack_dims[rack]
            stack = container["H"] // h
            if stack <= 0:
                continue

            while qty_left > 0:
                if not bin.place(l, w):
                    break

                add = min(stack, qty_left)

                if current_weight + (add * wt) > container["MAX_WT"]:
                    break

                load[rack] = load.get(rack, 0) + add
                qty_left -= add
                remaining_qty[rack] -= add
                current_weight += add * wt
                placed_any = True

        if not placed_any:
            raise ValueError("Some racks cannot physically fit in the selected container.")

        containers.append(load)

    return containers

# =====================================================
# EXCEL TEMPLATE DOWNLOAD
# =====================================================
st.subheader("📄 Download Excel Input Template")

template_df = pd.DataFrame(columns=DISPLAY_COLUMNS)
template_buffer = io.BytesIO()
with pd.ExcelWriter(template_buffer, engine="openpyxl") as writer:
    template_df.to_excel(writer, index=False)
template_buffer.seek(0)

st.download_button(
    "⬇️ Download Input Template",
    template_buffer,
    "smartpack_input_template.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

# =====================================================
# INPUT SECTION
# =====================================================
st.subheader("📥 Upload Rack Excel or Use Manual Input")

uploaded_file = st.file_uploader("Upload filled Excel template", type=["xlsx"])

if uploaded_file:
    df_input = pd.read_excel(uploaded_file)
else:
    df_input = st.data_editor(
        pd.DataFrame({
            "Rack / Finished Good": [""],
            "Quantity": [1],
            "Length (MM)": [0],
            "Width (MM)": [0],
            "Height (MM)": [0],
            "Weight (Kg)": [0],
        }),
        num_rows="dynamic"
    )

container_type = st.selectbox("Container Type", list(CONTAINERS.keys()))

# =====================================================
# RUN
# =====================================================
if st.button("Calculate Loading"):

    data = df_input[df_input["Rack / Finished Good"].astype(str).str.strip() != ""]
    if data.empty:
        st.error("No valid rack data.")
        st.stop()

    containers = pack_containers_exact(data, CONTAINERS[container_type])

    st.subheader("📦 Container‑wise Loading Plan")

    container_volume = (
        CONTAINERS[container_type]["L"]
        * CONTAINERS[container_type]["W"]
        * CONTAINERS[container_type]["H"]
    )

    export_rows = []

    for i, cont in enumerate(containers, start=1):
        st.write(f"### 🚚 Container {i}")
        st.dataframe(
            pd.DataFrame(cont.items(), columns=["Rack / Finished Good", "Quantity"]),
            use_container_width=True
        )

        total_weight = 0
        total_volume = 0

        for rack, qty in cont.items():
            row = data[data["Rack / Finished Good"] == rack].iloc[0]
            total_weight += qty * row["Weight (Kg)"]
            total_volume += (
                qty
                * row["Length (MM)"]
                * row["Width (MM)"]
                * row["Height (MM)"]
            )

            export_rows.append([
                i,
                rack,
                qty,
                total_weight,
            ])

        weight_util = (total_weight / CONTAINERS[container_type]["MAX_WT"]) * 100
        volume_util = (total_volume / container_volume) * 100

        st.markdown(
            f"""
            **Weight Utilization:** {weight_util:.2f}%  
            **Volume Utilization:** {volume_util:.2f}%
            """
        )

    st.subheader("📊 Summary")
    st.success(f"✅ Total Containers Required: {len(containers)}")

    # =================================================
    # DOWNLOAD LOADING PLAN
    # =================================================
    export_df = pd.DataFrame(
        export_rows,
        columns=[
            "Container",
            "Rack / Finished Good",
            "Quantity",
            "Container Weight (KG)",
        ],
    )

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        export_df.to_excel(writer, index=False, sheet_name="Loading Plan")

    output.seek(0)

    st.download_button(
        "📥 Download Loading Plan",
        output,
        "smartpack_container_loading_plan.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
