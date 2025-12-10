import io
import zipfile
import requests
from PIL import Image
import pandas as pd
import streamlit as st
from bs4 import BeautifulSoup

# ------------- CONFIG -------------

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# ------------- UI -------------

st.title("Amazon Image Downloader (Excel → ZIP)")
st.write(
    """
    Upload an Excel file with columns **sku** and **url**.

    - If **url** is a direct image link (ends with .jpg/.png/.webp) → it downloads directly.
    - If **url** is an Amazon product page (contains `amazon.`) → it will try to grab the main product image.
    """
)

# ------------- HELPERS -------------

def is_direct_image_url(url: str) -> bool:
    url_lower = url.lower()
    return url_lower.endswith((".jpg", ".jpeg", ".png", ".webp"))


def download_image_bytes(image_url: str) -> bytes:
    resp = requests.get(image_url, headers=HEADERS, timeout=25)
    resp.raise_for_status()
    return resp.content


def get_amazon_main_image_url(product_url: str) -> str | None:
    """
    Very basic Amazon product page parser.
    May break if Amazon changes layout or blocks the request.
    Returns direct image URL or None.
    """
    resp = requests.get(product_url, headers=HEADERS, timeout=25)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # Common pattern: main image with id="landingImage"
    img = soup.find("img", id="landingImage")
    if img:
        # Amazon sometimes stores URL in data attributes
        for attr in ("data-old-hires", "data-a-dynamic-image", "src"):
            val = img.get(attr)
            if not val:
                continue

            if attr == "data-a-dynamic-image":
                # Format: {"https://...jpg":[500,500], "https://...":[...]}
                import json
                try:
                    data = json.loads(val)
                    if isinstance(data, dict) and data:
                        return next(iter(data.keys()))
                except Exception:
                    continue
            else:
                return val

    # Fallback: grab first large-ish image on the page
    for img in soup.find_all("img"):
        src = img.get("src")
        if not src:
            continue
        if "SL1500" in src or src.endswith((".jpg", ".jpeg", ".png", ".webp")):
            return src

    return None


def normalize_to_canvas(image_bytes: bytes, target: int = 1500) -> bytes:
    """Put the image into a centered 1500x1500 white canvas."""
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    w, h = img.size

    if w > target or h > target:
        scale = min(target / w, target / h)
        new_w = max(1, int(w * scale))
        new_h = max(1, int(h * scale))
        img = img.resize((new_w, new_h), Image.LANCZOS)
        w, h = img.size

    canvas = Image.new("RGB", (target, target), (255, 255, 255))
    offset_x = (target - w) // 2
    offset_y = (target - h) // 2
    canvas.paste(img, (offset_x, offset_y))

    out = io.BytesIO()
    canvas.save(out, format="JPEG", quality=95)
    out.seek(0)
    return out.getvalue()


def download_images_from_excel(uploaded_file):
    # Read Excel
    df = pd.read_excel(uploaded_file)
    df.columns = [c.strip().lower() for c in df.columns]

    if "sku" not in df.columns or "url" not in df.columns:
        raise ValueError("Excel must contain 'sku' and 'url' columns.")

    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
        for idx, row in df.iterrows():
            sku = str(row["sku"]).strip()
            url = str(row["url"]).strip()

            if not sku or not url or url.lower() == "nan":
                continue

            try:
                image_bytes = None

                if is_direct_image_url(url):
                    # Already an image
                    image_bytes = download_image_bytes(url)

                elif "amazon." in url:
                    # Amazon product URL
                    st.write(f"🔎 Fetching image from Amazon for SKU {sku}...")
                    image_url = get_amazon_main_image_url(url)
                    if not image_url:
                        st.write(f"❌ Could not find main image for SKU {sku}")
                        continue
                    image_bytes = download_image_bytes(image_url)

                else:
                    st.write(
                        f"⚠️ URL for SKU {sku} is neither a direct image nor Amazon URL. Skipping."
                    )
                    continue

                # Normalize and add to ZIP
                normalized = normalize_to_canvas(image_bytes)

                # Name: sku-1, sku-2, ...
                base_name = sku
                counter = 1
                filename = f"{base_name}-{counter}.jpg"
                while filename in zipf.namelist():
                    counter += 1
                    filename = f"{base_name}-{counter}.jpg"

                zipf.writestr(filename, normalized)

            except Exception as e:
                st.write(f"Error downloading for SKU {sku}: {e}")
                continue

    zip_buffer.seek(0)
    return zip_buffer

# ------------- MAIN UI FLOW -------------

uploaded_file = st.file_uploader(
    "Upload Excel file (.xlsx)",
    type=["xlsx"],
    help="File must have 'sku' and 'url' columns. URL can be a direct image link or an Amazon product page.",
)

if uploaded_file is not None:
    st.write("✅ File uploaded.")
    if st.button("Start Download"):
        with st.spinner("Downloading images and building ZIP..."):
            try:
                zip_buffer = download_images_from_excel(uploaded_file)
                st.success("Done! Click below to download your images.")
                st.download_button(
                    label="Download Images ZIP",
                    data=zip_buffer.getvalue(),
                    file_name="images.zip",
                    mime="application/zip",
                )
            except Exception as e:
                st.error(f"Something went wrong: {e}")
else:
    st.info("Please upload an Excel file to continue.")
