#!/usr/bin/env python3
"""Version bumping utility for desto package."""

import argparse
import re
import sys
from pathlib import Path


def get_current_version():
    """Get the current version from _version.py."""
    version_file = Path("src/desto/_version.py")
    if not version_file.exists():
        raise FileNotFoundError("_version.py not found")

    content = version_file.read_text()
    match = re.search(r'__version__ = ["\']([^"\']+)["\']', content)
    if not match:
        raise ValueError("Version not found in _version.py")

    return match.group(1)


def parse_version(version_str):
    """Parse a semantic version string."""
    match = re.match(r"(\d+)\.(\d+)\.(\d+)(?:-(.+))?", version_str)
    if not match:
        raise ValueError(f"Invalid version format: {version_str}")

    major, minor, patch = map(int, match.groups()[:3])
    pre_release = match.group(4)
    return major, minor, patch, pre_release


def bump_version(current_version, bump_type):
    """Bump version based on type."""
    major, minor, patch, pre_release = parse_version(current_version)

    if bump_type == "major":
        major += 1
        minor = 0
        patch = 0
    elif bump_type == "minor":
        minor += 1
        patch = 0
    elif bump_type == "patch":
        patch += 1
    else:
        raise ValueError(f"Invalid bump type: {bump_type}")

    return f"{major}.{minor}.{patch}"


def update_version_file(new_version):
    """Update the _version.py file with new version."""
    version_file = Path("src/desto/_version.py")
    content = version_file.read_text()

    new_content = re.sub(
        r'__version__ = ["\'][^"\']+["\']', f'__version__ = "{new_version}"', content
    )

    version_file.write_text(new_content)
    print(f"Updated {version_file} to version {new_version}")


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Bump desto package version")
    parser.add_argument(
        "bump_type", choices=["major", "minor", "patch"], help="Type of version bump"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )

    args = parser.parse_args()

    try:
        current_version = get_current_version()
        new_version = bump_version(current_version, args.bump_type)

        print(f"Current version: {current_version}")
        print(f"New version: {new_version}")

        if args.dry_run:
            print("(Dry run - no changes made)")
        else:
            update_version_file(new_version)
            print(f"\n✅ Version bumped from {current_version} to {new_version}")
            print("\nNext steps:")
            print("1. Review the changes")
            print("2. Run: uv build --wheel")
            print(
                "3. Run: git add . && git commit -m 'Bump version to {}'".format(
                    new_version
                )
            )
            print("4. Run: git tag v{}".format(new_version))

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
