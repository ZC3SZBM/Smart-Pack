import streamlit as st
import pandas as pd
import io
import os

# =====================================================
# PAGE CONFIG
# =====================================================
st.set_page_config(page_title="SmartPack - Container Load Planner", layout="wide")

# =====================================================
# GLOBAL CSS
# =====================================================
st.markdown("""
<style>
html, body, [class*="css"] {
    font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont,
                 "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}
h1, h2, h3 { color: #1F2937; font-weight: 600; }
label { font-weight: 500; color: #1F2937; }
.stButton > button {
    background-color: #22863A;
    color: white;
    font-weight: 600;
    border-radius: 8px;
}
.stButton > button:hover { background-color: #1E7A35; }
</style>
""", unsafe_allow_html=True)

# =====================================================
# HEADER
# =====================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGO_PATH = os.path.join(BASE_DIR, "john_deere_logo.png")

c1, c2, c3 = st.columns([1.5, 4, 2])

with c1:
    if os.path.exists(LOGO_PATH):
        st.image(LOGO_PATH, width=140)
    else:
        st.markdown("<h3 style='color:#367C2B;'>John Deere</h3>", unsafe_allow_html=True)

with c2:
    st.markdown(
        "<h1 style='text-align:center;'>🚚 SmartPack - Container Load Planner</h1>",
        unsafe_allow_html=True
    )

with c3:
    st.markdown(
        "<div style='text-align:right; font-weight:600;'>"
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

DISPLAY_COLUMNS = [
    "Rack / Finished Good",
    "Quantity",
    "Length (MM)",
    "Width (MM)",
    "Height (MM)",
    "Weight (Kg)",
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
        if self.w > w:
            parts.append(Rect(self.x + w, self.y, self.w - w, h))
        if self.h > h:
            parts.append(Rect(self.x, self.y + h, self.w, self.h - h))
        return parts


class MaxRectsBin:
    def __init__(self, w, h):
        self.free = [Rect(0, 0, w, h)]

    def place(self, w, h):
        for fr in self.free:
            for pw, ph in ((w, h), (h, w)):
                if fr.fits(pw, ph):
                    self.free.remove(fr)
                    self.free.extend(fr.split(pw, ph))
                    return True
        return False

# =====================================================
# PACKING ENGINE (SAFE, NO CASTING INSIDE)
# =====================================================
def pack_containers_exact(df, container):

    remaining = dict(zip(df["Rack / Finished Good"], df["Quantity"]))
    dims = df.set_index("Rack / Finished Good").to_dict("index")

    containers = []

    while any(v > 0 for v in remaining.values()):
        bin = MaxRectsBin(container["L"], container["W"])
        load = {}
        cur_weight = 0

        order = sorted(
            dims.keys(),
            key=lambda r: dims[r]["Length (MM)"] * dims[r]["Width (MM)"],
            reverse=True
        )

        for rack in order:
            while remaining[rack] > 0:
                l = dims[rack]["Length (MM)"]
                w = dims[rack]["Width (MM)"]
                h = dims[rack]["Height (MM)"]
                wt = dims[rack]["Weight (Kg)"]

                if not bin.place(l, w):
                    break

                max_by_height = container["H"] // h
                remaining_capacity = container["MAX_WT"] - cur_weight
                max_by_weight = remaining_capacity // wt

                add = min(remaining[rack], max_by_height, max_by_weight)
                if add <= 0:
                    break

                load[rack] = load.get(rack, 0) + add
                remaining[rack] -= add
                cur_weight += add * wt

        if not load:
            raise ValueError("No rack fits due to weight or volume limits.")

        containers.append(load)

    return containers

# =====================================================
# INPUT SECTION
# =====================================================
uploaded = st.file_uploader("Upload Rack Excel", type=["xlsx"])

if uploaded:
    df = pd.read_excel(uploaded)
else:
    df = st.data_editor(
        pd.DataFrame({c: [""] for c in DISPLAY_COLUMNS}),
        num_rows="dynamic"
    )

container_type = st.selectbox("Container Type", CONTAINERS)

# =====================================================
# RUN
# =====================================================
if st.button("Calculate Loading"):

    # Remove empty racks
    df = df[df["Rack / Finished Good"].astype(str).str.strip() != ""]

    # Convert numeric columns safely
    for col in DISPLAY_COLUMNS[1:]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna()

    if df.empty:
        st.error("Please enter valid numeric values for all rack fields.")
        st.stop()

    containers = pack_containers_exact(df, CONTAINERS[container_type])

    st.subheader("📦 Container-wise Loading Plan")

    results = []
    for i, cont in enumerate(containers, 1):
        st.write(f"### 🚚 Container {i}")
        st.dataframe(pd.DataFrame(cont.items(), columns=["Rack / Finished Good", "Quantity"]))
        for r, q in cont.items():
            results.append([i, r, q])

    st.success(f"✅ Total Containers Required: {len(containers)}")

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(
            results,
            columns=["Container", "Rack / Finished Good", "Quantity"]
        ).to_excel(writer, index=False)
    output.seek(0)

    st.download_button(
        "📥 Download Loading Plan",
        output,
        "smartpack_container_loading_plan.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
