import magic
import gzip
import zipfile
import shutil
import os

def detect_file_type(file_path):
    """Detect the file type using magic library."""
    file_type = magic.from_file(file_path, mime=True)
    return file_type

def extract_gzip(file_path, output_path):
    """Extract a gzip file."""
    try:
        with gzip.open(file_path, 'rb') as f_in:
            with open(output_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        print(f"Extracted GZIP file: {output_path}")
    except Exception as e:
        print(f"Failed to extract GZIP: {e}")

def extract_zip(file_path, output_folder):
    """Extract a zip file."""
    try:
        with zipfile.ZipFile(file_path, 'r') as zip_ref:
            zip_ref.extractall(output_folder)
        print(f"Extracted ZIP file to: {output_folder}")
    except Exception as e:
        print(f"Failed to extract ZIP: {e}")

def process_tfl_file(file_path):
    """Process the TFL file based on its detected format."""
    file_type = detect_file_type(file_path)
    print(f"Detected file type: {file_type}")

    if 'gzip' in file_type:
        output_json = file_path.replace('.tfl', '.json')
        extract_gzip(file_path, output_json)
    elif 'zip' in file_type:
        output_folder = file_path.replace('.tfl', '_extracted')
        extract_zip(file_path, output_folder)
    else:
        print("Unknown or proprietary format. Further analysis needed.")

# Example Usage
tfl_file = r"D:\MScript Testing\MScript Testing\Demo_Analysis.tfl"
process_tfl_file(tfl_file)
