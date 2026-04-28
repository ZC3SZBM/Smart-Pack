import streamlit as st
import pandas as pd
import math
import io

# =====================================================
# APP CONFIG
# =====================================================
st.set_page_config(page_title="Container Loading Optimizer", layout="wide")
st.title("🚚 Container Loading Optimizer")

# =====================================================
# CONTAINER DEFINITIONS
# =====================================================
CONTAINERS = {
    "40 HC": {"L": 11938, "W": 2286, "H": 2540},
    "20 HC": {"L": 5898, "W": 2286, "H": 2540},
    "53 Dry Van": {"L": 16002, "W": 2286, "H": 2590},
}

REQUIRED_COLUMNS = ["Rack", "Quantity", "Length", "Width", "Height", "Weight"]

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
# PACKING ENGINE (EXACT GEOMETRY + CORRECT QUANTITIES)
# =====================================================
def pack_containers_exact(df, container):

    remaining_qty = {
        r["Rack"]: int(r["Quantity"]) for _, r in df.iterrows()
    }

    rack_dims = {
        r["Rack"]: (int(r["Length"]), int(r["Width"]), int(r["Height"]))
        for _, r in df.iterrows()
    }

    containers = []

    while any(q > 0 for q in remaining_qty.values()):
        bin = MaxRectsBin(container["L"], container["W"])
        load = {}

        order = sorted(
            remaining_qty.keys(),
            key=lambda k: rack_dims[k][0] * rack_dims[k][1],
            reverse=True
        )

        placed_any = False

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
# EXCEL TEMPLATE DOWNLOAD
# =====================================================
st.subheader("📄 Download Excel Template")

template_df = pd.DataFrame(columns=REQUIRED_COLUMNS)
template_buffer = io.BytesIO()
with pd.ExcelWriter(template_buffer, engine="openpyxl") as writer:
    template_df.to_excel(writer, index=False)
template_buffer.seek(0)

st.download_button(
    "⬇️ Download Input Template",
    template_buffer,
    "rack_input_template.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

# =====================================================
# INPUT SECTION
# =====================================================
st.subheader("📥 Upload Rack Excel or Use Manual Input")

uploaded_file = st.file_uploader("Upload filled Excel template", type=["xlsx"])

if uploaded_file:
    df_input = pd.read_excel(uploaded_file)

    missing = [c for c in REQUIRED_COLUMNS if c not in df_input.columns]
    if missing:
        st.error(f"Missing columns in Excel: {missing}")
        st.stop()

    df_input = df_input[REQUIRED_COLUMNS].dropna()

else:
    df_base = pd.DataFrame({
        "Rack": [""],
        "Quantity": [1],
        "Length": [0],
        "Width": [0],
        "Height": [0],
        "Weight": [0],
    })
    df_input = st.data_editor(df_base, num_rows="dynamic")

container_type = st.selectbox("Container Type", list(CONTAINERS.keys()))

# =====================================================
# RUN
# =====================================================
if st.button("Calculate Loading"):

    data = df_input[df_input["Rack"].astype(str).str.strip() != ""]

    if data.empty:
        st.error("No valid rack data.")
        st.stop()

    try:
        containers = pack_containers_exact(data, CONTAINERS[container_type])
    except ValueError as e:
        st.error(str(e))
        st.stop()

    st.subheader("📦 Container‑wise Loading Plan")

    output_rows = []
    for i, cont in enumerate(containers, start=1):
        st.write(f"### 🚚 Container {i}")
        st.dataframe(
            pd.DataFrame(cont.items(), columns=["Rack", "Quantity"]),
            use_container_width=True
        )
        for r, q in cont.items():
            output_rows.append([i, r, q])

    st.subheader("📊 Summary")
    st.success(f"✅ Total Containers Required: {len(containers)}")

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(
            output_rows, columns=["Container", "Rack", "Quantity"]
        ).to_excel(writer, index=False)

    output.seek(0)

    st.download_button(
        "📥 Download Loading Plan",
        output,
        "container_loading_plan.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
