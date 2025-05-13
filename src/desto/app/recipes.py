RECIPES = {
    "custom": {
        "title": "Custom Recipe",
        "script_name": "custom.sh",
        "code": "#!/bin/bash\n",
        "args_label": "Arguments (optional)",
        "placeholder": "",
        "default_session_name": "custom_recipe",
        "custom": True,
    },
    "rec_patt_search": {
        "title": "Pattern Search",
        "script_name": "search_pattern.sh",
        "code": """#!/bin/bash
# Usage: ./search_pattern.sh <directory> <pattern>
dir="$1"
pattern="$2"
grep -rnw "$dir" -e "$pattern"
""",
        "args_label": "Directory and Pattern (e.g. /home/user mypattern)",
        "placeholder": "/path/to/dir pattern",
        "default_session_name": "rec_patt_search",
        "custom": False,
    },
    "count_files": {
        "title": "Count Files",
        "script_name": "count_files.sh",
        "code": """#!/bin/bash\n\n# Check if the directory exists\nif [ ! -d \"$1\" ]; then\n  echo \"Error: $1 is not a valid directory.\"\n  exit 1\nfi\n\n# Use find to count files directly\nfile_count=$(find \"$1\" -type f | wc -l)\n\n# Print the total number of files\necho \"Total number of files in $1 and its subdirectories: $file_count\"\n""",
        "args_label": "Directory (e.g. /home/user)",
        "placeholder": "/path/to/dir",
        "default_session_name": "count_files",
        "custom": False,
    },
    "sync_folders": {
        "title": "Sync Folders",
        "script_name": "sync_folders.sh",
        "code": """#!/bin/bash\n\n# Check if the correct number of arguments is provided\nif [ \"$#\" -ne 2 ]; then\n  echo \"Usage: $0 <source_directory> <destination_directory>\"\n  echo \"  <source_directory> is the directory to copy from.\"\n  echo \"  <destination_directory> is the directory to copy to.\"\n  exit 1\nfi\n\n# Use rsync to sync the folders, creating the destination if it doesn't exist\nrsync --ignore-existing -avz \"$1/\" \"$2\" || { echo \"Error: rsync failed.\" >&2; exit 1; }\n\necho \"Successfully synced '$1' to '$2'.\n\"\n""",
        "args_label": "Source and Destination Directory (e.g. /src /dst)",
        "placeholder": "/path/to/source /path/to/destination",
        "default_session_name": "sync_folders",
        "custom": False,
    },
    # Add more recipes here...
}
