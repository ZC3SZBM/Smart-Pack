import streamlit as st
import pandas as pd
import io
import os

# =====================================================
# PAGE CONFIG
# =====================================================
st.set_page_config(page_title="SmartPack - Container Load Planner", layout="wide")

# =====================================================
# HEADER (LOGO | TITLE | JD TEXT)
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
        leftover = []
        if self.w > w:
            leftover.append(Rect(self.x + w, self.y, self.w - w, h))
        if self.h > h:
            leftover.append(Rect(self.x, self.y + h, self.w, self.h - h))
        return leftover


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
# PACKING ENGINE (CORRECTED ORDER: QTY → WEIGHT → FLOOR)
# =====================================================
def pack_containers_exact(df, container):

    remaining = dict(zip(df["Rack / Finished Good"], df["Quantity"]))
    dims = df.set_index("Rack / Finished Good").to_dict("index")
    containers = []

    while any(v > 0 for v in remaining.values()):
        floor = MaxRectsBin(container["L"], container["W"])
        load = {}
        used_weight = 0

        # Larger footprints first
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

                # Calculate allowed quantity FIRST
                max_by_height = container["H"] // h
                max_by_weight = (container["MAX_WT"] - used_weight) // wt

                add_qty = min(remaining[rack], max_by_height, max_by_weight)
                if add_qty <= 0:
                    break

                # ONLY then reserve floor space
                if not floor.place(l, w):
                    break

                load[rack] = load.get(rack, 0) + add_qty
                remaining[rack] -= add_qty
                used_weight += add_qty * wt

        if not load:
            raise ValueError("No rack fits due to weight or space constraints.")

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

    # Remove empty rows
    df = df[df["Rack / Finished Good"].astype(str).str.strip() != ""]

    # Safely convert numerics
    for c in DISPLAY_COLUMNS[1:]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df = df.dropna()

    if df.empty:
        st.error("Please enter valid numeric values.")
        st.stop()

    containers = pack_containers_exact(df, CONTAINERS[container_type])

    st.subheader("📦 Container-wise Loading Plan")

    results = []
    for i, cont in enumerate(containers, 1):
        st.write(f"### 🚚 Container {i}")
        st.dataframe(
            pd.DataFrame(cont.items(), columns=["Rack / Finished Good", "Quantity"]),
            use_container_width=True
        )
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
