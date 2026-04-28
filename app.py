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
    "40 HC": {"L": 11938, "W": 2286, "H": 2540, "MAX_WT": 20000},
    "20 HC": {"L": 5898, "W": 2286, "H": 2540, "MAX_WT": 20000},
    "53 Dry Van": {"L": 16002, "W": 2286, "H": 2590, "MAX_WT": 20000},
}

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
# CORE PACKING (FIXED QUANTITY LOGIC)
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

        # large footprint first
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
# UI
# =====================================================
st.subheader("📥 Rack Input")

df_base = pd.DataFrame({
    "Rack": [""],
    "Quantity": [1],
    "Length": [0],
    "Width": [0],
    "Height": [0],
})

df = st.data_editor(df_base, num_rows="dynamic")
container_type = st.selectbox("Container", list(CONTAINERS.keys()))

# =====================================================
# RUN
# =====================================================
if st.button("Calculate Loading"):

    data = df[df["Rack"].astype(str).str.strip() != ""]
    if data.empty:
        st.error("No valid input.")
        st.stop()

    try:
        containers = pack_containers_exact(data, CONTAINERS[container_type])
    except ValueError as e:
        st.error(str(e))
        st.stop()

    # OUTPUT
    st.subheader("📦 Container‑wise Loading Plan")

    rows = []
    for i, cont in enumerate(containers, start=1):
        st.write(f"### 🚚 Container {i}")
        st.dataframe(
            pd.DataFrame(cont.items(), columns=["Rack", "Quantity"]),
            use_container_width=True
        )
        for r, q in cont.items():
            rows.append([i, r, q])

    st.subheader("📊 Summary")
    st.success(f"✅ Total Containers Required: {len(containers)}")

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(rows, columns=["Container", "Rack", "Quantity"]).to_excel(
            writer, index=False
        )

    output.seek(0)
    st.download_button(
        "📥 Download Loading Plan",
        output,
        "container_loading_plan.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
