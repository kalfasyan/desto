#!/bin/bash

# Script to set up the 'desto' command for running the dashboard

# --- Step 1: Determine the user's local bin directory ---
LOCAL_BIN="$HOME/.local/bin"

# Check if the directory exists, and create it if it doesn't
if [ ! -d "$LOCAL_BIN" ]; then
  echo "Creating directory: $LOCAL_BIN"
  mkdir -p "$LOCAL_BIN"
fi

# --- Step 2: Determine the path to ui.py ---
# Get the directory of the current script
SCRIPT_DIR=$(dirname "$(realpath "$0")")

# Construct the full path to ui.py relative to the repo's root
UI_PATH="$SCRIPT_DIR/../src/desto/app/ui.py"

# Resolve the full path
UI_PATH=$(realpath "$UI_PATH")

# Check if the resolved path exists
if [ ! -f "$UI_PATH" ]; then
  echo "Error: File '$UI_PATH' does not exist."
  exit 1
fi

# --- Step 3: Create the 'desto' script ---
DESTO_SCRIPT="$LOCAL_BIN/desto"
SCRIPT_CONTENT="#!/bin/bash
python \"$UI_PATH\"
"

echo "Creating script: $DESTO_SCRIPT"
echo "$SCRIPT_CONTENT" > "$DESTO_SCRIPT"

# --- Step 4: Make the script executable ---
echo "Making script executable..."
chmod +x "$DESTO_SCRIPT"

# --- Step 5: Update PATH (if necessary) ---
# Check if $LOCAL_BIN is already in PATH
if ! grep -q "$LOCAL_BIN" <<< "$PATH"; then
  echo "Adding '$LOCAL_BIN' to your PATH in ~/.bashrc or ~/.zshrc"
  # Determine which shell is being used and add the path accordingly
  SHELL_NAME=$(basename "$SHELL")
  case "$SHELL_NAME" in
    bash)
      echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
      echo "Remember to run 'source ~/.bashrc' or open a new terminal."
      ;;
    zsh)
      echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.zshrc"
      echo "Remember to run 'source ~/.zshrc' or open a new terminal."
      ;;
    *)
      echo "Could not automatically add to PATH. Please manually add '$LOCAL_BIN' to your PATH environment variable."
      ;;
  esac
else
  echo "'$LOCAL_BIN' is already in your PATH."
fi

# --- Step 6: Update .user_aliases if it exists ---
USER_ALIASES="$HOME/.user_aliases"
if [ -f "$USER_ALIASES" ]; then
  if ! grep -q "$LOCAL_BIN" "$USER_ALIASES"; then
    echo "Adding '$LOCAL_BIN' to your PATH in .user_aliases"
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$USER_ALIASES"
    echo "Remember to run 'source $USER_ALIASES' or open a new terminal."
  else
    echo "'$LOCAL_BIN' is already in your .user_aliases."
  fi
fi

echo "--- Installation complete! ---"
echo "You should now be able to run your dashboard by typing 'desto' in a new terminal."
echo "If you didn't see a message about updating your PATH, it was likely already set up."