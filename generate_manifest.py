ASSETS_FOLDER = "assets"
RAW_BASE = "https://raw.githubusercontent.com/USERNAME/REPO/main/assets"

def generate_manifest():
    assets = []

    for category in sorted(os.listdir(ASSETS_FOLDER)):
        category_path = os.path.join(ASSETS_FOLDER, category)

        if not os.path.isdir(category_path) or category.startswith("."):
            continue

        for asset_name in sorted(os.listdir(category_path)):
            asset_path = os.path.join(category_path, asset_name)

            if not os.path.isdir(asset_path):
                continue

            files = os.listdir(asset_path)

            blend_files = [f for f in files if f.endswith(".blend")]
            if not blend_files:
                continue

            png_files = [f for f in files if f.endswith(".png")]
            preview = f"{RAW_BASE}/{category}/{asset_name}/{png_files[0]}" if png_files else None

            blend_file = blend_files[0]
            collection_name = os.path.splitext(blend_file)[0]

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

    print(f"Generated manifest with {len(assets)} assets.")
