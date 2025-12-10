import io
import zipfile
import requests
from PIL import Image
import pandas as pd
import streamlit as st

# ===========================
# Amazon Image Downloader Web
# ===========================

st.title("Amazon Image Downloader (Excel → ZIP)")
st.write(
    "Upload an Excel file with columns **sku** and **url**. "
    "The app will download the images and give you a ZIP file."
)

# ---------- HELPER FUNCTION ----------

def download_images_from_excel(uploaded_file):
    """
    Takes an uploaded Excel file, reads sku + url,
    downloads images, and returns a ZIP (as BytesIO).
    """
    # Read Excel into DataFrame
    df = pd.read_excel(uploaded_file)

    # Normalize column names
    df.columns = [c.strip().lower() for c in df.columns]

    if "sku" not in df.columns or "url" not in df.columns:
        raise ValueError("Excel must contain 'sku' and 'url' columns.")

    # Create an in-memory ZIP file
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
        for idx, row in df.iterrows():
            sku = str(row["sku"]).strip()
            url = str(row["url"]).strip()

            if not sku or not url or url.lower() == "nan":
                continue

            try:
                # -------- DIRECT IMAGE DOWNLOAD --------
                resp = requests.get(url, timeout=25)
                resp.raise_for_status()

                # Guess extension
                ext = ".jpg"
                for candidate in [".jpg", ".jpeg", ".png", ".webp"]:
                    if candidate in url.lower():
                        ext = candidate
                        break

                # Open and convert
                img = Image.open(io.BytesIO(resp.content)).convert("RGB")

                # Resize into 1500x1500 white canvas
                target = 1500
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

                # Write image
                img_bytes = io.BytesIO()
                canvas.save(img_bytes, format="JPEG", quality=95)
                img_bytes.seek(0)

                # Naming: sku-1, sku-2...
                base_name = sku
                counter = 1
                filename = f"{base_name}-{counter}.jpg"
                while filename in zipf.namelist():
                    counter += 1
                    filename = f"{base_name}-{counter}.jpg"

                zipf.writestr(filename, img_bytes.getvalue())

            except Exception as e:
                st.write(f"Error downloading for SKU {sku}: {e}")
                continue

    zip_buffer.seek(0)
    return zip_buffer

# ---------- STREAMLIT UI ----------

uploaded_file = st.file_uploader(
    "Upload Excel file (.xlsx)",
    type=["xlsx"],
    help="File must have 'sku' and 'url' columns.",
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
