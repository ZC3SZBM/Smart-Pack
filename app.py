import streamlit as st
import pandas as pd
import math
import io

# =====================================================
# PAGE CONFIG
# =====================================================
st.set_page_config(page_title="SmartPack - Container Load Planner", layout="wide")

# =====================================================
# GLOBAL CSS (FONT + COLORS)
# =====================================================
st.markdown("""
<style>
html, body, [class*="css"]  {
    font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont,
                 "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}

h1, h2, h3 {
    color: #1F2937;
    font-weight: 600;
}

label {
    font-weight: 500;
    color: #1F2937;
}

.stTextInput input, .stNumberInput input, .stSelectbox select {
    border-radius: 8px;
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
# HEADER (TITLE LEFT, TEXT RIGHT)
# =====================================================
col1, col2 = st.columns([3, 2])
with col1:
    st.title("🚚 SmartPack - Container Load Planner")
with col2:
    st.markdown(
        "<div style='text-align:right; font-weight:600; color:#1F2937; padding-top:20px;'>"
        "JOHN DEERE LOGISTICS ENGINEERING<br>"
        "JOHN DEERE KERNERSVILLE"
        "</div>",
        unsafe_allow_html=True
    )

# =====================================================
# CONTAINER DEFINITIONS
# =====================================================
CONTAINERS = {
    "40 HC": {"L": 11938, "W": 2286, "H": 2540},
    "20 HC": {"L": 5898, "W": 2286, "H": 2540},
    "53 Dry Van": {"L": 16002, "W": 2286, "H": 2590},
}

# =====================================================
# EXPECTED INPUT COLUMNS
# =====================================================
DISPLAY_COLUMNS = [
    "Rack / Finished Good",
    "Quantity",
    "Length (MM)",
    "Width (MM)",
    "Height (MM)",
    "Weight (Kg)"
]

# =====================================================
# MAXRECTS GEOMETRY
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
# PACKING ENGINE (UNCHANGED LOGIC)
# =====================================================
def pack_containers_exact(df, container):

    remaining_qty = {
        r["Rack / Finished Good"]: int(r["Quantity"]) for _, r in df.iterrows()
    }

    rack_dims = {
        r["Rack / Finished Good"]: (
            int(r["Length (MM)"]),
            int(r["Width (MM)"]),
            int(r["Height (MM)"])
        )
        for _, r in df.iterrows()
    }

    containers = []

    while any(q > 0 for q in remaining_qty.values()):
        bin = MaxRectsBin(container["L"], container["W"])
        load = {}
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

            l, w, h = rack_dims[rack]
            stack = container["H"] // h
            if stack <= 0:
                continue

            while qty_left > 0:
                if not bin.place(l, w):
                    break

                add = min(stack, qty_left)
                load[rack] = load.get(rack, 0) + add
                qty_left -= add
                remaining_qty[rack] -= add
                placed_any = True

        if not placed_any:
            raise ValueError("Some racks cannot physically fit in container.")

        containers.append(load)

    return containers

# =====================================================
# DOWNLOAD EXCEL TEMPLATE
# =====================================================
st.subheader("📄 Download Excel Template")

template_df = pd.DataFrame(columns=DISPLAY_COLUMNS)
buffer = io.BytesIO()
with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
    template_df.to_excel(writer, index=False)
buffer.seek(0)

st.download_button(
    "⬇️ Download Input Template",
    buffer,
    "smartpack_input_template.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

# =====================================================
# INPUT SECTION
# =====================================================
st.subheader("📥 Upload Rack Excel or Use Manual Input")

uploaded_file = st.file_uploader("Upload filled Excel template", type=["xlsx"])

if uploaded_file:
    df_input = pd.read_excel(uploaded_file)
    missing = [c for c in DISPLAY_COLUMNS if c not in df_input.columns]
    if missing:
        st.error(f"Missing columns in Excel: {missing}")
        st.stop()
    df_input = df_input[DISPLAY_COLUMNS].dropna()
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

    st.subheader("📦 Container-wise Loading Plan")

    rows = []
    for i, cont in enumerate(containers, start=1):
        st.write(f"### 🚚 Container {i}")
        st.dataframe(
            pd.DataFrame(cont.items(), columns=["Rack / Finished Good", "Quantity"]),
            use_container_width=True
        )
        for r, q in cont.items():
            rows.append([i, r, q])

    st.subheader("📊 Summary")
    st.success(f"✅ Total Containers Required: {len(containers)}")

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(
            rows,
            columns=["Container", "Rack / Finished Good", "Quantity"]
        ).to_excel(writer, index=False)

    output.seek(0)

    st.download_button(
        "📥 Download Loading Plan",
        output,
        "smartpack_container_loading_plan.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
