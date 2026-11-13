import base64
import hashlib
import io
import math
import zipfile
from pathlib import Path

import pandas as pd
import streamlit as st
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ============================================================
# COMPATIBILITY & CLOUD BRIDGE FOR STREAMLIT-DRAWABLE-CANVAS
# ============================================================
# On Streamlit Cloud / production deployments, relative '/media/...' URLs
# fail inside sandboxed component iframes due to domain isolation / CORS.
# Serializing background images to Base64 Data URIs fixes this everywhere.

def _image_to_data_uri(
    image, width=None, clamp=False, channels="RGB", output_format="PNG", image_id=""
):
    try:
        if isinstance(image, str) and (
            image.startswith("data:") or image.startswith("http://") or image.startswith("https://")
        ):
            return image

        if hasattr(image, "save"):
            buffered = io.BytesIO()
            image.save(buffered, format="PNG")
            encoded = base64.b64encode(buffered.getvalue()).decode("ascii")
            return f"data:image/png;base64,{encoded}"

        if isinstance(image, (bytes, bytearray)):
            encoded = base64.b64encode(image).decode("ascii")
            return f"data:image/png;base64,{encoded}"
    except Exception:
        pass

    try:
        import streamlit.elements.lib.image_utils as image_utils
        from streamlit.elements.lib.layout_utils import LayoutConfig
        return image_utils.image_to_url(
            image,
            layout_config=LayoutConfig(width=width),
            clamp=clamp,
            channels=channels,
            output_format=output_format,
            image_id=image_id,
        )
    except Exception:
        return ""

try:
    import streamlit.elements.image as st_image
    st_image.image_to_url = _image_to_data_uri
except Exception:
    pass

try:
    import streamlit.elements.lib.image_utils as image_utils
    image_utils.image_to_url = _image_to_data_uri
except Exception:
    pass

from streamlit_drawable_canvas import st_canvas
import streamlit_drawable_canvas as _sdc_mod
if hasattr(_sdc_mod, "image_to_url"):
    _sdc_mod.image_to_url = _image_to_data_uri



# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="NameCraft Studio",
    page_icon="🪪",
    layout="wide",
)

APP_DIR = Path(__file__).parent
FONT_DIR = APP_DIR / "fonts"

BUNDLED_BOLD_ITALIC = FONT_DIR / "DejaVuSans-BoldOblique.ttf"
BUNDLED_BOLD = FONT_DIR / "DejaVuSans-Bold.ttf"


# ============================================================
# CSS
# ============================================================

st.markdown("""
<style>
.block-container {
    padding-top: 1rem;
    padding-bottom: 2rem;
    max-width: 1550px;
}
.hero {
    padding: 1rem 1.35rem;
    border-radius: 15px;
    background: linear-gradient(115deg, #e8f0fe, #f4f8f5);
    margin-bottom: 1rem;
}
.hero h1 {
    margin: 0;
    color: #18352b;
    font-size: 1.9rem;
}
.hero p {
    margin: .3rem 0 0;
    color: #53645d;
}
.tip {
    padding: .8rem 1rem;
    border-radius: 9px;
    background: #edf5ff;
    color: #23466c;
    margin: .4rem 0 .9rem;
    font-size: .92rem;
}
div[data-testid="stCanvas"] {
    border: 2px solid #00C853;
    border-radius: 12px;
    padding: 6px;
    background: #f7faf8;
}
div[data-testid="stCanvas"] canvas {
    touch-action: none;
}
</style>

<div class="hero">
    <h1>🪪 NameCraft Studio V4</h1>
    <p>Design once, position names visually, and generate attendee badges in bulk.</p>
</div>
""", unsafe_allow_html=True)


# ============================================================
# FILE / FONT HELPERS
# ============================================================

def load_names(uploaded_file):
    uploaded_file.seek(0)
    if uploaded_file.name.lower().endswith(".csv"):
        try:
            return pd.read_csv(uploaded_file, encoding="utf-8-sig")
        except UnicodeDecodeError:
            uploaded_file.seek(0)
            return pd.read_csv(uploaded_file, encoding="latin-1")
    return pd.read_excel(uploaded_file)


@st.cache_resource(show_spinner=False)
def get_font(font_bytes, size, italic):
    size = max(1, int(round(size)))
    if font_bytes:
        return ImageFont.truetype(io.BytesIO(font_bytes), size=size)

    font_path = BUNDLED_BOLD_ITALIC if italic else BUNDLED_BOLD
    if not font_path.exists():
        raise FileNotFoundError(
            "Bundled font files are missing. Keep the fonts folder beside app.py."
        )
    return ImageFont.truetype(str(font_path), size=size)


def display_name(raw_name, uppercase):
    value = str(raw_name).strip()
    return value.upper() if uppercase else value


# ============================================================
# FONT SIZE FITTING
# ============================================================

def fit_font_size(template_size, text, cfg, font_bytes):
    width, height = template_size
    max_w = max(1, int(width * cfg.get("max_width_pct", 82) / 100))
    max_h = max(1, int(height * cfg.get("max_height_pct", 25) / 100))

    size = max(1, int(cfg.get("font_size", cfg.get("default_font_size", 155))))
    min_size = max(1, int(cfg.get("min_font_size", 24)))

    probe = ImageDraw.Draw(Image.new("RGBA", (2, 2)))

    while size > min_size:
        font = get_font(font_bytes, size, cfg.get("italic", True))
        box = probe.textbbox(
            (0, 0),
            text,
            font=font,
            stroke_width=cfg.get("stroke_width", 0)
        )
        text_w = box[2] - box[0]
        text_h = box[3] - box[1]

        if text_w <= max_w * 0.94 and text_h <= max_h * 0.90:
            break
        size -= 1

    return max(size, min_size)


# ============================================================
# PILLOW TEXT RENDERING
# ============================================================

def make_text_layer(
    text,
    font,
    fill,
    stroke_width,
    stroke_fill,
    shadow_enabled,
    shadow_color,
    shadow_blur,
    shadow_x,
    shadow_y,
):
    probe = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    bbox = ImageDraw.Draw(probe).textbbox(
        (0, 0),
        text,
        font=font,
        stroke_width=stroke_width
    )

    text_w = max(1, bbox[2] - bbox[0])
    text_h = max(1, bbox[3] - bbox[1])

    pad = max(
        24,
        stroke_width * 4
        + shadow_blur * 3
        + abs(shadow_x)
        + abs(shadow_y)
        + 12
    )

    layer = Image.new(
        "RGBA",
        (text_w + pad * 2, text_h + pad * 2),
        (0, 0, 0, 0)
    )
    draw = ImageDraw.Draw(layer)
    text_pos = (pad - bbox[0], pad - bbox[1])

    if shadow_enabled:
        shadow_layer = Image.new("RGBA", layer.size, (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow_layer)
        shadow_rgba = Image.new("RGBA", (1, 1), shadow_color).getpixel((0, 0))
        shadow_draw.text(
            (text_pos[0] + shadow_x, text_pos[1] + shadow_y),
            text,
            font=font,
            fill=shadow_rgba,
            stroke_width=stroke_width,
            stroke_fill=shadow_rgba
        )
        if shadow_blur:
            shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(shadow_blur))
        layer.alpha_composite(shadow_layer)

    draw.text(
        text_pos,
        text,
        font=font,
        fill=fill,
        stroke_width=stroke_width,
        stroke_fill=stroke_fill
    )
    return layer


def make_rendered_name_layer(raw_name, cfg, font_bytes, template_size):
    text = display_name(raw_name, cfg.get("uppercase", True))
    fitted_size = fit_font_size(template_size, text, cfg, font_bytes)
    font = get_font(font_bytes, fitted_size, cfg.get("italic", True))

    layer = make_text_layer(
        text,
        font,
        cfg.get("text_color", "#FFFFFF"),
        cfg.get("stroke_width", 0),
        cfg.get("stroke_color", "#18352b"),
        cfg.get("shadow", False),
        cfg.get("shadow_color", "#17102B"),
        cfg.get("shadow_blur", 0),
        cfg.get("shadow_x", 0),
        cfg.get("shadow_y", 0),
    )
    return layer, fitted_size


# ============================================================
# FINAL CARD RENDERER
# ============================================================

def render_card(template, raw_name, cfg, font_bytes=None):
    base = template.convert("RGBA").copy()
    text = display_name(raw_name, cfg.get("uppercase", True))
    fitted_size = fit_font_size(base.size, text, cfg, font_bytes)
    font = get_font(font_bytes, fitted_size, cfg.get("italic", True))

    text_layer = make_text_layer(
        text,
        font,
        cfg.get("text_color", "#FFFFFF"),
        cfg.get("stroke_width", 0),
        cfg.get("stroke_color", "#18352b"),
        cfg.get("shadow", False),
        cfg.get("shadow_color", "#17102B"),
        cfg.get("shadow_blur", 0),
        cfg.get("shadow_x", 0),
        cfg.get("shadow_y", 0),
    )

    # 1. Apply canvas resize/scaling values
    scale_x = float(cfg.get("scale_x", 1.0))
    scale_y = float(cfg.get("scale_y", 1.0))
    new_w = max(1, int(round(text_layer.width * scale_x)))
    new_h = max(1, int(round(text_layer.height * scale_y)))

    if new_w != text_layer.width or new_h != text_layer.height:
        text_layer = text_layer.resize((new_w, new_h), Image.Resampling.LANCZOS)

    # 2. Apply canvas rotation (Fabric is clockwise; Pillow is counter-clockwise)
    rotation = float(cfg.get("rotation", 0.0)) % 360.0
    if abs(rotation) > 1e-4:
        text_layer = text_layer.rotate(
            -rotation,
            resample=Image.Resampling.BICUBIC,
            expand=True
        )

    # 3. Position at exact center coordinates
    center_x = int(round(base.width * float(cfg.get("x_pct", 54.0)) / 100.0))
    center_y = int(round(base.height * float(cfg.get("y_pct", 47.0)) / 100.0))

    base.alpha_composite(
        text_layer,
        (
            center_x - text_layer.width // 2,
            center_y - text_layer.height // 2
        )
    )
    return base.convert("RGB")


@st.cache_data(show_spinner=False, max_entries=48)
def cached_preview(template_bytes, raw_name, cfg_items, font_bytes):
    template = Image.open(io.BytesIO(template_bytes)).convert("RGBA")
    return render_card(template, raw_name, dict(cfg_items), font_bytes)


# ============================================================
# IMAGE DATA URL FOR FABRIC CANVAS
# ============================================================

def layer_to_data_url(layer):
    buffer = io.BytesIO()
    layer.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


# ============================================================
# CANVAS IMAGE OBJECT (DIRECT EDITING - ALWAYS ENABLED)
# ============================================================

def make_canvas_drawing(
    raw_name,
    canvas_w,
    canvas_h,
    scale,
    cfg,
    font_bytes,
    template_size,
    transform
):
    layer, fitted_size = make_rendered_name_layer(
        raw_name,
        cfg,
        font_bytes,
        template_size
    )

    editor_w = max(1, int(round(layer.width * scale)))
    editor_h = max(1, int(round(layer.height * scale)))
    editor_layer = layer.resize((editor_w, editor_h), Image.Resampling.LANCZOS)

    left = canvas_w * float(transform.get("x_pct", 54.0)) / 100.0
    top = canvas_h * float(transform.get("y_pct", 47.0)) / 100.0
    scale_x = float(transform.get("scale_x", 1.0))
    scale_y = float(transform.get("scale_y", 1.0))
    angle = float(transform.get("rotation", 0.0))

    drawing = {
        "version": "4.4.0",
        "objects": [
            {
                "type": "image",
                "version": "4.4.0",
                "originX": "center",
                "originY": "center",
                "left": left,
                "top": top,
                "width": editor_w,
                "height": editor_h,
                "fill": "rgb(0,0,0)",
                "stroke": None,
                "strokeWidth": 0,
                "src": layer_to_data_url(editor_layer),
                "crossOrigin": "anonymous",
                "scaleX": scale_x,
                "scaleY": scale_y,
                "angle": angle,
                "opacity": 1,
                "visible": True,
                # Direct manipulation: always enabled
                "selectable": True,
                "evented": True,
                "hasControls": True,
                "hasBorders": True,
                "hasRotatingPoint": True,
                "rotatingPointOffset": 55,
                "borderColor": "#00E676",
                "borderOpacityWhenMoving": 1,
                "borderScaleFactor": 4,
                "cornerStyle": "circle",
                "cornerSize": 22,
                "cornerColor": "#FFFFFF",
                "cornerStrokeColor": "#00C853",
                "transparentCorners": False,
                "padding": 12,
                "lockMovementX": False,
                "lockMovementY": False,
                "lockScalingX": False,
                "lockScalingY": False,
                "lockRotation": False,
                "lockUniScaling": True,
                "lockSkewingX": True,
                "lockSkewingY": True,
                "lockScalingFlip": True,
            }
        ]
    }
    return drawing, fitted_size


# ============================================================
# READ CANVAS TRANSFORM (COORDINATE CONVERSION)
# ============================================================

def extract_transform(obj, canvas_w, canvas_h):
    if not obj:
        return {
            "x_pct": 54.0,
            "y_pct": 47.0,
            "scale_x": 1.0,
            "scale_y": 1.0,
            "rotation": 0.0
        }

    left = float(obj.get("left", canvas_w * 0.54))
    top = float(obj.get("top", canvas_h * 0.47))
    scale_x = float(obj.get("scaleX", 1.0))
    scale_y = float(obj.get("scaleY", 1.0))
    angle = float(obj.get("angle", 0.0)) % 360.0

    origin_x = str(obj.get("originX", "center")).lower()
    origin_y = str(obj.get("originY", "center")).lower()

    if origin_x != "center" or origin_y != "center":
        w = float(obj.get("width", 0)) * scale_x
        h = float(obj.get("height", 0)) * scale_y

        dx = 0.0
        if origin_x == "left":
            dx = w / 2.0
        elif origin_x == "right":
            dx = -w / 2.0

        dy = 0.0
        if origin_y == "top":
            dy = h / 2.0
        elif origin_y == "bottom":
            dy = -h / 2.0

        rad = math.radians(angle)
        center_x = left + (dx * math.cos(rad) - dy * math.sin(rad))
        center_y = top + (dx * math.sin(rad) + dy * math.cos(rad))
    else:
        center_x = left
        center_y = top

    x_pct = max(0.0, min(100.0, (center_x / canvas_w) * 100.0))
    y_pct = max(0.0, min(100.0, (center_y / canvas_h) * 100.0))

    return {
        "x_pct": round(x_pct, 4),
        "y_pct": round(y_pct, 4),
        "scale_x": round(scale_x, 4),
        "scale_y": round(scale_y, 4),
        "rotation": round(angle, 2)
    }


def read_canvas_transform(canvas_data, canvas_w, canvas_h, fallback_size=None):
    try:
        objects = (
            canvas_data.get("objects")
            if isinstance(canvas_data, dict)
            else None
        ) or []

        if not objects:
            return {
                "x_pct": 54.0,
                "y_pct": 47.0,
                "scale_x": 1.0,
                "scale_y": 1.0,
                "rotation": 0.0
            }

        return extract_transform(objects[0], canvas_w, canvas_h)
    except Exception:
        return {
            "x_pct": 54.0,
            "y_pct": 47.0,
            "scale_x": 1.0,
            "scale_y": 1.0,
            "rotation": 0.0
        }


# ============================================================
# BUILD EXPORT CONFIG
# ============================================================

def build_config_from_canvas(
    canvas_data_or_transform,
    canvas_w=None,
    canvas_h=None,
    style=None
):
    if style is None and isinstance(canvas_w, dict):
        style = canvas_w

    if isinstance(canvas_data_or_transform, dict) and "x_pct" in canvas_data_or_transform:
        transform = canvas_data_or_transform
    else:
        transform = read_canvas_transform(
            canvas_data_or_transform,
            canvas_w or 1,
            canvas_h or 1
        )

    return {
        "x_pct": float(transform.get("x_pct", 54.0)),
        "y_pct": float(transform.get("y_pct", 47.0)),
        "scale_x": float(transform.get("scale_x", 1.0)),
        "scale_y": float(transform.get("scale_y", 1.0)),
        "rotation": float(transform.get("rotation", 0.0)),
        "font_size": style.get("font_size", style.get("default_font_size", 155)),
        "default_font_size": style.get("default_font_size", 155),
        "max_width_pct": style["max_width_pct"],
        "max_height_pct": style["max_height_pct"],
        "min_font_size": style["min_font_size"],
        "uppercase": style["uppercase"],
        "italic": style["italic"],
        "text_color": style["text_color"],
        "stroke_width": style["stroke_width"],
        "stroke_color": style["stroke_color"],
        "shadow": style["shadow"],
        "shadow_color": style["shadow_color"],
        "shadow_blur": style["shadow_blur"],
        "shadow_x": style["shadow_x"],
        "shadow_y": style["shadow_y"]
    }


# ============================================================
# 1. UPLOAD FILES
# ============================================================

st.subheader("1. Upload your files")

upload_col1, upload_col2 = st.columns(2)

with upload_col1:
    template_file = st.file_uploader(
        "Blank card design (PNG/JPG)",
        type=["png", "jpg", "jpeg"],
        key="template_upload"
    )

with upload_col2:
    names_file = st.file_uploader(
        "Attendee names (CSV/Excel)",
        type=["csv", "xlsx", "xls"],
        key="names_upload"
    )

if not template_file or not names_file:
    st.info("Upload a blank card template and an attendee names file to continue.")
    st.stop()

try:
    template_bytes = template_file.getvalue()
    template = Image.open(io.BytesIO(template_bytes)).convert("RGBA")
    data = load_names(names_file)
except Exception as error:
    st.error(f"Could not read the uploaded file: {error}")
    st.stop()

if data.empty or len(data.columns) == 0:
    st.error("The names file is empty.")
    st.stop()


# ============================================================
# 2. SELECT NAME COLUMN
# ============================================================

st.subheader("2. Select the names column")

name_col = st.selectbox("Column containing attendee names", list(data.columns))

names = [
    str(value).strip()
    for value in data[name_col].dropna().tolist()
    if str(value).strip() and str(value).strip().lower() != "nan"
]

if not names:
    st.error("No names were found in this column.")
    st.stop()


# ============================================================
# CANVAS SIZE
# ============================================================

max_canvas_width = 1050
max_canvas_height = 760

canvas_scale = min(
    max_canvas_width / template.width,
    max_canvas_height / template.height,
    1.0
)

canvas_w = max(1, int(template.width * canvas_scale))
canvas_h = max(1, int(template.height * canvas_scale))

canvas_bg = template.resize((canvas_w, canvas_h), Image.Resampling.LANCZOS)


# ============================================================
# 3. TEXT SETTINGS
# ============================================================

left_col, right_col = st.columns([0.82, 2.18], gap="large")

with left_col:
    st.subheader("3. Text settings")

    preview_idx = st.selectbox(
        "Preview attendee",
        range(len(names)),
        format_func=lambda index: names[index],
        key="preview_attendee"
    )

    uppercase = st.checkbox(
        "Convert names to UPPERCASE",
        True,
        key="uppercase_setting"
    )

    italic = st.checkbox(
        "Use italic font",
        True,
        key="italic_setting"
    )

    font_file = st.file_uploader(
        "Optional custom font (TTF/OTF)",
        type=["ttf", "otf"],
        key="custom_font_upload"
    )

    text_color = st.color_picker(
        "Text color",
        "#FFFFFF",
        key="text_color_setting"
    )

    with st.expander("Outline and shadow", expanded=False):
        outline = st.checkbox("Text outline", True, key="outline_setting")
        stroke_width = st.slider(
            "Outline thickness",
            0,
            8,
            1,
            disabled=not outline,
            key="outline_width_setting"
        )
        stroke_color = st.color_picker(
            "Outline color",
            "#18352b",
            disabled=not outline,
            key="outline_color_setting"
        )
        shadow = st.checkbox("Drop shadow", True, key="shadow_setting")
        shadow_color = st.color_picker(
            "Shadow color",
            "#17102B",
            disabled=not shadow,
            key="shadow_color_setting"
        )
        shadow_blur = st.slider(
            "Shadow softness",
            0,
            12,
            2,
            disabled=not shadow,
            key="shadow_blur_setting"
        )
        shadow_x = st.slider(
            "Shadow horizontal offset",
            -12,
            12,
            3,
            disabled=not shadow,
            key="shadow_x_setting"
        )
        shadow_y = st.slider(
            "Shadow vertical offset",
            -12,
            12,
            4,
            disabled=not shadow,
            key="shadow_y_setting"
        )

    with st.expander("Advanced text limits", expanded=False):
        max_width_pct = st.slider("Maximum text width (%)", 20, 100, 82, key="max_width_setting")
        max_height_pct = st.slider("Maximum text height (%)", 5, 50, 25, key="max_height_setting")
        min_font_size = st.slider("Minimum size for long names", 8, 100, 24, key="min_font_setting")

font_bytes = font_file.getvalue() if font_file else None
active_name = names[preview_idx]
font_signature = hashlib.sha256(font_bytes).hexdigest() if font_bytes else "bundled"


# ============================================================
# STYLE CONFIG
# ============================================================

style = {
    "scale": canvas_scale,
    "font_size": 155,
    "default_font_size": 155,
    "max_width_pct": max_width_pct,
    "max_height_pct": max_height_pct,
    "min_font_size": min_font_size,
    "uppercase": uppercase,
    "italic": italic,
    "text_color": text_color,
    "stroke_width": stroke_width if outline else 0,
    "stroke_color": stroke_color,
    "shadow": shadow,
    "shadow_color": shadow_color,
    "shadow_blur": shadow_blur if shadow else 0,
    "shadow_x": shadow_x if shadow else 0,
    "shadow_y": shadow_y if shadow else 0,
}


# ============================================================
# CANVAS SESSION STATE & PERSISTENCE
# ============================================================

template_signature = (
    f"{template_file.name}:{len(template_bytes)}:{template.width}:{template.height}"
)
name_signature = f"{preview_idx}:{active_name}"

style_signature = hashlib.sha256(
    repr((
        uppercase,
        italic,
        text_color,
        style["stroke_width"],
        stroke_color,
        shadow,
        style["shadow_color"],
        style["shadow_blur"],
        style["shadow_x"],
        style["shadow_y"],
        max_width_pct,
        max_height_pct,
        min_font_size,
        font_signature
    )).encode()
).hexdigest()[:16]

# Reset coordinates only when new template is uploaded
if (
    "_transform" not in st.session_state
    or st.session_state.get("_template_signature") != template_signature
):
    st.session_state["_transform"] = {
        "x_pct": 54.0,
        "y_pct": 47.0,
        "scale_x": 1.0,
        "scale_y": 1.0,
        "rotation": 0.0
    }
    st.session_state["_template_signature"] = template_signature
    st.session_state["_applied_cfg"] = None
    st.session_state["_applied_name"] = None

# Construct fresh artwork drawing with current transform
canvas_drawing, fitted_font_size = make_canvas_drawing(
    active_name,
    canvas_w,
    canvas_h,
    canvas_scale,
    style,
    font_bytes,
    template.size,
    st.session_state["_transform"]
)


# ============================================================
# 4. LIVE EDITOR (DIRECT MANIPULATION VIA FORM - NO BLINKING)
# ============================================================

with right_col:
    st.subheader("4. Live editor")

    st.markdown("""
    <div style="
        border:2px solid #00C853;
        background:#10251c;
        color:#ffffff;
        padding:15px 18px;
        border-radius:12px;
        margin:4px 0 12px 0;
    ">
        <div style="font-weight:750;font-size:16px;letter-spacing:.4px">
            NAME EDITING GUIDE
        </div>
        <div style="color:#d8f5e2;line-height:1.9;margin-top:7px">
            <b>1.</b> Click the name to select it<br>
            <b>2.</b> Drag inside the box to move it<br>
            <b>3.</b> Drag a corner handle to resize it<br>
            <b>4.</b> Drag the top round handle to rotate it
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Wrapped in st.form: prevents premature reruns while moving/resizing/rotating!
    # Eliminates all text blinking, flickering, and disappearing.
    with st.form("namecraft_editor_form", clear_on_submit=False):
        canvas_key = (
            f"namecraft_canvas_"
            f"{template_signature}_"
            f"{name_signature}_"
            f"{style_signature}"
        )

        canvas_result = st_canvas(
            fill_color="rgba(0,0,0,0)",
            stroke_width=0,
            stroke_color="rgba(0,0,0,0)",
            background_image=canvas_bg,
            update_streamlit=True,
            height=canvas_h,
            width=canvas_w,
            drawing_mode="transform",
            initial_drawing=canvas_drawing,
            display_toolbar=False,
            key=canvas_key
        )

        apply_clicked = st.form_submit_button(
            "✓ Apply Changes",
            use_container_width=True,
            type="primary"
        )

    # When Apply is clicked: read the latest canvas position and commit to preview & exports
    if apply_clicked:
        if canvas_result is not None and canvas_result.json_data:
            returned_objects = canvas_result.json_data.get("objects") or []
            if returned_objects:
                st.session_state["_transform"] = extract_transform(
                    returned_objects[0],
                    canvas_w,
                    canvas_h
                )

        st.session_state["_applied_cfg"] = build_config_from_canvas(
            st.session_state["_transform"],
            style=style
        )
        st.session_state["_applied_name"] = active_name
        st.success("Your live design has been applied to the final preview and exports.")
        st.rerun()

    st.caption(
        "Directly move, resize, and rotate the name above. "
        "Click Apply Changes to update the final preview and badge exports."
    )


# ============================================================
# 5. FINAL PREVIEW
# ============================================================

if st.session_state.get("_applied_cfg") is None:
    st.session_state["_applied_cfg"] = build_config_from_canvas(
        st.session_state["_transform"],
        style=style
    )
    st.session_state["_applied_name"] = active_name

applied_cfg = st.session_state["_applied_cfg"]
applied_name = st.session_state.get("_applied_name") or active_name

st.divider()
st.subheader("5. Final preview")

try:
    preview_image = cached_preview(
        template_bytes,
        applied_name,
        tuple(sorted(applied_cfg.items())),
        font_bytes
    )

    st.image(
        preview_image,
        caption=f"Final output preview — {applied_name}",
        width=390
    )
except Exception as error:
    st.error(f"Could not render the final preview: {error}")
    st.stop()

st.caption(
    f"Original card: {template.width} × {template.height} px"
    f" | Attendee cards: {len(names)}"
)

if applied_name != active_name:
    st.info(
        "You selected another attendee. Apply the design again to update the final preview for this attendee."
    )


# ============================================================
# 6. BULK EXPORT
# ============================================================

st.divider()
st.subheader("6. Generate all attendee cards")

if st.button(
    "Generate attendee cards",
    type="primary",
    use_container_width=True,
    key="generate_attendee_cards",
    disabled=st.session_state.get("_applied_cfg") is None
):
    zip_buffer = io.BytesIO()
    generated_cards = []
    progress = st.progress(0)

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for index, person in enumerate(names, start=1):
            card = render_card(template, person, applied_cfg, font_bytes)

            image_buffer = io.BytesIO()
            card.save(image_buffer, format="PNG", dpi=(300, 300))

            safe_name = "".join(
                char if char.isalnum() or char in "-_ " else "_"
                for char in person
            ).strip().replace(" ", "_")

            zip_file.writestr(
                f"{index:03d}_{safe_name or 'attendee'}.png",
                image_buffer.getvalue()
            )

            generated_cards.append(card)
            progress.progress(index / len(names))

    st.success(f"Successfully generated {len(generated_cards)} attendee cards.")

    st.download_button(
        "⬇️ Download all PNG cards (ZIP)",
        zip_buffer.getvalue(),
        "attendee_cards.zip",
        "application/zip",
        use_container_width=True
    )

    pdf_buffer = io.BytesIO()
    generated_cards[0].save(
        pdf_buffer,
        format="PDF",
        save_all=True,
        append_images=generated_cards[1:],
        resolution=300
    )

    st.download_button(
        "⬇️ Download multi-page PDF",
        pdf_buffer.getvalue(),
        "attendee_cards.pdf",
        "application/pdf",
        use_container_width=True
    )


# ============================================================
# TIPS
# ============================================================

with st.expander("Tips and troubleshooting"):
    st.markdown("""
    - Use a blank card template without an old attendee name already printed on it.
    - Drag the name to move it anywhere on the badge.
    - Drag a corner handle to resize it proportionally.
    - Drag the top circular handle to rotate it (horizontal, vertical, diagonal).
    - Click Apply Changes to update the final preview and exports.
    - PNG/PDF exports use the original template resolution.
    """)