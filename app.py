import io
import zipfile
from functools import lru_cache
from pathlib import Path

import pandas as pd
import streamlit as st
from PIL import Image, ImageDraw, ImageFont, ImageFilter

st.set_page_config(page_title="NameCraft Studio", page_icon="🪪", layout="wide")

APP_DIR = Path(__file__).parent
FONT_DIR = APP_DIR / "fonts"
BUNDLED_BOLD_ITALIC = FONT_DIR / "DejaVuSans-BoldOblique.ttf"
BUNDLED_BOLD = FONT_DIR / "DejaVuSans-Bold.ttf"

st.markdown("""
<style>
.block-container{padding-top:1.5rem;max-width:1250px}
.hero{padding:1.2rem 1.4rem;border-radius:16px;background:linear-gradient(120deg,#e8f0fe,#f8f9fa);margin-bottom:1rem}
.hero h1{margin:0;color:#202124;font-size:2rem}
.hero p{margin:.35rem 0 0;color:#5f6368}
@media (min-width: 900px){
  [class*="st-key-preview_panel"]{
    position: sticky;
    top: 1rem;
    align-self: flex-start;
  }
}
</style>
<div class="hero"><h1>🪪 NameCraft Studio</h1>
<p>Reusable card-name generator · Upload a design and names, style the text, preview, and export.</p></div>
""", unsafe_allow_html=True)


def load_names(file):
    if file.name.lower().endswith(".csv"):
        try:
            return pd.read_csv(file, encoding="utf-8-sig")
        except UnicodeDecodeError:
            file.seek(0)
            return pd.read_csv(file, encoding="latin-1")
    return pd.read_excel(file)


@st.cache_resource(show_spinner=False)
def get_font(font_bytes, size, italic=True):
    """Load a scalable TrueType font; never silently fall back to tiny bitmap text."""
    if font_bytes:
        return ImageFont.truetype(io.BytesIO(font_bytes), size=size)

    font_path = BUNDLED_BOLD_ITALIC if italic else BUNDLED_BOLD
    if not font_path.exists():
        raise FileNotFoundError(
            f"Bundled font not found: {font_path}. Keep the fonts folder beside app.py."
        )
    return ImageFont.truetype(str(font_path), size=size)


def make_text_layer(text, font, fill, stroke_width, stroke_fill,
                    shadow_enabled, shadow_color, shadow_blur, shadow_x, shadow_y):
    probe = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(probe)
    bbox = d.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad = max(24, stroke_width * 4 + shadow_blur * 3 + abs(shadow_x) + abs(shadow_y) + 12)
    layer = Image.new("RGBA", (tw + pad * 2, th + pad * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    pos = (pad - bbox[0], pad - bbox[1])

    if shadow_enabled:
        shadow = Image.new("RGBA", layer.size, (0, 0, 0, 0))
        sd = ImageDraw.Draw(shadow)
        rgba = Image.new("RGBA", (1, 1), shadow_color).getpixel((0, 0))
        sd.text((pos[0] + shadow_x, pos[1] + shadow_y), text, font=font,
                fill=rgba, stroke_width=stroke_width, stroke_fill=rgba)
        if shadow_blur:
            shadow = shadow.filter(ImageFilter.GaussianBlur(shadow_blur))
        layer.alpha_composite(shadow)

    draw.text(pos, text, font=font, fill=fill, stroke_width=stroke_width,
              stroke_fill=stroke_fill)
    return layer


def render_card(template, raw_name, cfg, font_bytes=None):
    base = template.convert("RGBA").copy()
    text = str(raw_name).strip()
    if cfg["uppercase"]:
        text = text.upper()

    W, H = base.size
    max_w = int(W * cfg["max_width_pct"] / 100)
    max_h = int(H * cfg["max_height_pct"] / 100)
    size = cfg["font_size"]

    while size > cfg["min_font_size"]:
        font = get_font(font_bytes, size, cfg["italic"])
        probe = ImageDraw.Draw(Image.new("RGBA", (2, 2)))
        box = probe.textbbox((0, 0), text, font=font, stroke_width=cfg["stroke_width"])
        if (box[2] - box[0] <= max_w * 0.94 and
                box[3] - box[1] <= max_h * 0.90):
            break
        size -= 1

    font = get_font(font_bytes, max(size, cfg["min_font_size"]), cfg["italic"])
    layer = make_text_layer(
        text, font, cfg["text_color"], cfg["stroke_width"], cfg["stroke_color"],
        cfg["shadow"], cfg["shadow_color"], cfg["shadow_blur"],
        cfg["shadow_x"], cfg["shadow_y"]
    )
    layer = layer.rotate(cfg["rotation"], resample=Image.Resampling.BICUBIC, expand=True)
    cx = int(W * cfg["x_pct"] / 100)
    cy = int(H * cfg["y_pct"] / 100)
    left = cx - layer.width // 2
    top = cy - layer.height // 2
    base.alpha_composite(layer, (left, top))
    return base.convert("RGB")


@st.cache_data(show_spinner=False, max_entries=64)
def cached_preview(template_bytes, raw_name, cfg_items, font_bytes):
    """Cache identical previews so Streamlit reruns don't redraw the same card."""
    template = Image.open(io.BytesIO(template_bytes)).convert("RGBA")
    cfg = dict(cfg_items)
    return render_card(template, raw_name, cfg, font_bytes)


st.subheader("1. Upload files")
c1, c2 = st.columns(2)
with c1:
    template_file = st.file_uploader("Blank card design (PNG/JPG)", type=["png", "jpg", "jpeg"])
with c2:
    names_file = st.file_uploader("Names list (CSV/Excel)", type=["csv", "xlsx", "xls"])

if not template_file or not names_file:
    st.info("Upload a card template and attendee list to continue.")
    st.stop()

try:
    template_bytes = template_file.getvalue()
    template = Image.open(io.BytesIO(template_bytes)).convert("RGBA")
    data = load_names(names_file)
except Exception as exc:
    st.error(f"Could not read uploaded file: {exc}")
    st.stop()

if data.empty or len(data.columns) == 0:
    st.error("The names file is empty.")
    st.stop()

st.subheader("2. Choose names column")
name_col = st.selectbox("Column containing names", list(data.columns))
names = [str(x).strip() for x in data[name_col].dropna().tolist()
         if str(x).strip() and str(x).strip().lower() != "nan"]
if not names:
    st.error("No names found in this column.")
    st.stop()

settings_col, preview_col = st.columns([1.08, 0.92], gap="large")

with settings_col:
    st.subheader("3. Name styling")
    st.caption("Change any setting here; the preview on the right updates automatically.")

    with st.expander("Position and angle", expanded=True):
        x_pct = st.slider("Horizontal position (%)", 0, 100, 54)
        y_pct = st.slider("Vertical position (%)", 0, 100, 47)
        rotation = st.slider("Tilt / rotation (degrees)", -30, 30, -11)
        max_width_pct = st.slider("Maximum text width (%)", 20, 100, 82)
        max_height_pct = st.slider("Maximum text height (%)", 5, 35, 17)

    with st.expander("Font and size", expanded=True):
        font_size = st.slider("Font size", 20, 260, 155)
        min_font_size = st.slider("Minimum size for long names", 8, 100, 24)
        uppercase = st.checkbox("Convert names to UPPERCASE", True)
        italic = st.checkbox("Use italic font", True)
        font_file = st.file_uploader("Optional TTF/OTF font file", type=["ttf", "otf"])
        text_color = st.color_picker("Text color", "#FFFFFF")

    with st.expander("Outline and shadow", expanded=True):
        outline = st.checkbox("Text outline", True)
        stroke_width = st.slider("Outline thickness", 0, 8, 1, disabled=not outline)
        stroke_color = st.color_picker("Outline color", "#252044", disabled=not outline)
        shadow = st.checkbox("Drop shadow", True)
        shadow_color = st.color_picker("Shadow color", "#17102B", disabled=not shadow)
        shadow_blur = st.slider("Shadow softness", 0, 12, 2, disabled=not shadow)
        shadow_x = st.slider("Shadow horizontal offset", -12, 12, 3, disabled=not shadow)
        shadow_y = st.slider("Shadow vertical offset", -12, 12, 4, disabled=not shadow)

    cfg = {
        "x_pct": x_pct, "y_pct": y_pct, "rotation": rotation,
        "max_width_pct": max_width_pct, "max_height_pct": max_height_pct,
        "font_size": font_size, "min_font_size": min_font_size,
        "uppercase": uppercase, "italic": italic,
        "text_color": text_color, "stroke_width": stroke_width if outline else 0,
        "stroke_color": stroke_color, "shadow": shadow,
        "shadow_color": shadow_color, "shadow_blur": shadow_blur if shadow else 0,
        "shadow_x": shadow_x if shadow else 0, "shadow_y": shadow_y if shadow else 0,
    }
    font_bytes = font_file.getvalue() if font_file else None

with preview_col:
    with st.container(key="preview_panel"):
        st.subheader("4. Live preview")
        idx = st.selectbox("Preview attendee", range(len(names)), format_func=lambda i: names[i])
        try:
            preview = cached_preview(
                template_bytes, names[idx], tuple(cfg.items()), font_bytes
            )
            st.image(preview, caption=f"Preview: {names[idx]}", use_container_width=True)
        except Exception as exc:
            st.error(f"Could not render preview: {exc}")
            st.stop()
        st.metric("Cards to generate", len(names))
        st.caption(f"Card size: {template.width} × {template.height} px")
        st.caption("The preview updates when you change a setting on the left.")

st.divider()
st.subheader("5. Generate all cards")

if st.button("Generate attendee cards", type="primary", use_container_width=True):
    zip_data = io.BytesIO()
    generated = []
    progress = st.progress(0)

    with zipfile.ZipFile(zip_data, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, person in enumerate(names, 1):
            card = render_card(template, person, cfg, font_bytes)
            image_data = io.BytesIO()
            card.save(image_data, format="PNG", dpi=(300, 300))
            safe = "".join(ch if ch.isalnum() or ch in "-_ " else "_" for ch in person)
            safe = safe.strip().replace(" ", "_")
            zf.writestr(f"{i:03d}_{safe or 'attendee'}.png", image_data.getvalue())
            generated.append(card)
            progress.progress(i / len(names))

    st.success(f"Generated {len(generated)} cards.")
    st.download_button("⬇️ Download all PNG cards (ZIP)", zip_data.getvalue(),
                       "attendee_cards.zip", "application/zip", use_container_width=True)

    pdf = io.BytesIO()
    generated[0].save(pdf, format="PDF", save_all=True,
                      append_images=generated[1:], resolution=300)
    st.download_button("⬇️ Download multi-page PDF", pdf.getvalue(),
                       "attendee_cards.pdf", "application/pdf", use_container_width=True)
    st.image(generated[0], caption="First generated card", use_container_width=True)

with st.expander("Tips / troubleshooting"):
    st.markdown("""
- Use a **blank template without the old ATTENDEE word**; this app adds the names but does not erase existing text.
- The app now uses a bundled scalable TrueType font, so font size works consistently on Windows and Streamlit Cloud.
- For a closer font match, upload your own TTF/OTF font file.
- Always preview both a short name and the longest name before printing the full batch.
""")
