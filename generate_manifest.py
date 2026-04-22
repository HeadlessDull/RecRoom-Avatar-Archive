import os
import json

ASSETS_FOLDER = "Assets"
RAW_BASE = "https://raw.githubusercontent.com/HeadlessDull/RecRoom-Avatar-Archive/main/Assets"

def generate_manifest():
    assets = []

    print(f"Looking in folder: {ASSETS_FOLDER}")
    print(f"Current working directory: {os.getcwd()}")
    print(f"Files in current directory: {os.listdir('.')}")

    if not os.path.exists(ASSETS_FOLDER):
        print(f"ERROR: '{ASSETS_FOLDER}' folder not found!")
        return

    print(f"Contents of {ASSETS_FOLDER}: {os.listdir(ASSETS_FOLDER)}")

    for category in sorted(os.listdir(ASSETS_FOLDER)):
        category_path = os.path.join(ASSETS_FOLDER, category)
        print(f"  Category: {category} | is dir: {os.path.isdir(category_path)}")

        if not os.path.isdir(category_path) or category.startswith("."):
            continue

        for asset_name in sorted(os.listdir(category_path)):
            asset_path = os.path.join(category_path, asset_name)
            print(f"    Asset: {asset_name} | is dir: {os.path.isdir(asset_path)}")

            if not os.path.isdir(asset_path):
                continue

            files = os.listdir(asset_path)
            print(f"      Files: {files}")

            blend_files = [f for f in files if f.endswith(".blend")]
            png_files = [f for f in files if f.endswith(".png")]

            print(f"      .blend files: {blend_files}")
            print(f"      .png files: {png_files}")

            if not blend_files:
                print(f"      SKIPPING - no .blend found")
                continue

            blend_file = blend_files[0]
            collection_name = os.path.splitext(blend_file)[0]
            preview = f"{RAW_BASE}/{category}/{asset_name}/{png_files[0]}" if png_files else None

            assets.append({
                "category": category,
                "name": asset_name,
                "preview": preview,
                "blend": f"{RAW_BASE}/{category}/{asset_name}/{blend_file}",
                "collection": collection_name
            })

    manifest = {"assets": assets}
    with open("manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\nGenerated manifest with {len(assets)} assets.")

if __name__ == "__main__":
    generate_manifest()
