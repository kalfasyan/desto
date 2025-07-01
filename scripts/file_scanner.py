#!/usr/bin/env python3

import hashlib
import os
import sys
import time
from datetime import datetime
from pathlib import Path


def calculate_file_hash(file_path, algorithm="md5"):
    """Calculate hash of a file."""
    hash_obj = hashlib.new(algorithm)

    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_obj.update(chunk)
        return hash_obj.hexdigest()
    except Exception as e:
        print(f"Error calculating hash for {file_path}: {e}")
        return None


def scan_directory(directory, extensions=None):
    """Scan directory for files and calculate their hashes."""
    print(f"🔍 Scanning directory: {directory}")

    if not Path(directory).exists():
        print(f"❌ Directory not found: {directory}")
        return []

    files = []
    total_size = 0

    for file_path in Path(directory).rglob("*"):
        if file_path.is_file():
            # Filter by extensions if provided
            if extensions and file_path.suffix.lower() not in extensions:
                continue

            try:
                stat = file_path.stat()
                file_info = {
                    "path": str(file_path),
                    "name": file_path.name,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "hash": None,
                }

                # Calculate hash for smaller files only (< 100MB)
                if stat.st_size < 100 * 1024 * 1024:
                    print(f"   📄 Processing: {file_path.name}")
                    file_info["hash"] = calculate_file_hash(file_path)
                else:
                    print(f"   📄 Skipping hash for large file: {file_path.name}")

                files.append(file_info)
                total_size += stat.st_size

            except Exception as e:
                print(f"   ❌ Error processing {file_path}: {e}")

    print(
        f"✅ Found {len(files)} files, total size: {total_size / (1024 * 1024):.2f} MB"
    )
    return files


def find_duplicates(files):
    """Find duplicate files based on hash."""
    print("\n🔎 Looking for duplicate files...")

    hash_groups = {}
    for file_info in files:
        if file_info["hash"]:
            hash_val = file_info["hash"]
            if hash_val not in hash_groups:
                hash_groups[hash_val] = []
            hash_groups[hash_val].append(file_info)

    duplicates = {h: files for h, files in hash_groups.items() if len(files) > 1}

    if duplicates:
        print(f"🔥 Found {len(duplicates)} groups of duplicate files:")
        for hash_val, dup_files in duplicates.items():
            print(f"\n   Hash: {hash_val}")
            for file_info in dup_files:
                print(f"     📄 {file_info['path']} ({file_info['size']} bytes)")
    else:
        print("✨ No duplicate files found!")

    return duplicates


def generate_report(files, duplicates, output_file="file_scan_report.txt"):
    """Generate a detailed report."""
    print(f"\n📝 Generating report: {output_file}")

    with open(output_file, "w") as f:
        f.write("File Scanner Report\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"{'=' * 50}\n\n")

        f.write("SUMMARY:\n")
        f.write(f"  Total files scanned: {len(files)}\n")
        f.write(f"  Duplicate groups found: {len(duplicates)}\n")

        total_size = sum(f["size"] for f in files)
        f.write(f"  Total size: {total_size / (1024 * 1024):.2f} MB\n\n")

        if duplicates:
            f.write("DUPLICATE FILES:\n")
            for hash_val, dup_files in duplicates.items():
                f.write(f"\n  Hash: {hash_val}\n")
                for file_info in dup_files:
                    f.write(f"    {file_info['path']} ({file_info['size']} bytes)\n")

        f.write("\nALL FILES:\n")
        for file_info in sorted(files, key=lambda x: x["path"]):
            f.write(f"  {file_info['path']}\n")
            f.write(f"    Size: {file_info['size']} bytes\n")
            f.write(f"    Modified: {file_info['modified']}\n")
            if file_info["hash"]:
                f.write(f"    Hash: {file_info['hash']}\n")
            f.write("\n")


def main():
    """Main function to run the file scanner."""
    print("📂 File Scanner & Duplicate Detector")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Get directory from command line or use current directory
    if len(sys.argv) > 1:
        scan_dir = sys.argv[1]
        print(f"Scanning provided directory: {scan_dir}")
    else:
        scan_dir = os.getcwd()
        print(f"No directory provided, scanning current directory: {scan_dir}")

    # Optional file extensions filter
    extensions = None
    if "--ext" in sys.argv:
        ext_index = sys.argv.index("--ext")
        if ext_index + 1 < len(sys.argv):
            extensions = [
                f".{ext.lstrip('.')}" for ext in sys.argv[ext_index + 1].split(",")
            ]
            print(f"Filtering for extensions: {extensions}")

    start_time = time.time()

    try:
        # Scan directory
        files = scan_directory(scan_dir, extensions)

        if not files:
            print("No files found to process.")
            return

        # Find duplicates
        duplicates = find_duplicates(files)

        # Generate report
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = f"file_scan_report_{timestamp}.txt"
        generate_report(files, duplicates, report_file)

        # Summary
        elapsed = time.time() - start_time
        print(f"\n{'=' * 50}")
        print("🎯 SCAN COMPLETE!")
        print(f"   Files processed: {len(files)}")
        print(f"   Duplicate groups: {len(duplicates)}")
        print(f"   Time taken: {elapsed:.2f} seconds")
        print(f"   Report saved: {report_file}")
        print(f"{'=' * 50}")

    except KeyboardInterrupt:
        print("\n⚠️ Scan interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Error during scan: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
