# Desto CLI

A command-line interface for managing tmux sessions with clean, modular architecture.

## Architecture

The CLI is structured into the following modules:

```
src/desto/cli/
├── __init__.py          # Package initialization and exports
├── main.py              # Main CLI application with typer
├── sessions.py          # Session management commands
├── scripts.py           # Script management commands
├── session_manager.py   # Core session management logic (UI-independent)
└── utils.py             # Utility functions for formatting and logging
```

## Design Principles

1. **Modular Design**: Each module has a single responsibility
2. **Clean Dependencies**: Core session logic is independent of UI frameworks
3. **Error Handling**: Comprehensive error handling with user-friendly messages
4. **Type Safety**: Full type hints for better development experience
5. **Extensible**: Easy to add new commands and functionality

## Core Components

### CLISessionManager

The heart of the CLI - manages tmux sessions without any UI dependencies:

- **Session lifecycle**: Start, stop, list, attach to sessions
- **Log management**: View and follow session logs
- **Status tracking**: Monitor session state and runtime
- **Directory management**: Handle scripts and logs directories

### Commands Structure

```bash
# Session Management
desto-cli sessions list                    # List all sessions
desto-cli sessions start "name" "command"  # Start new session
desto-cli sessions kill "name"             # Kill specific session  
desto-cli sessions kill --all              # Kill all sessions
desto-cli sessions attach "name"           # Attach to session
desto-cli sessions logs "name"             # View session logs
desto-cli sessions status [name]           # Show session status

# Script Management
desto-cli scripts list                     # List all scripts
desto-cli scripts list --details           # List with detailed info
desto-cli scripts create "name" --type bash|python  # Create new script
desto-cli scripts edit "name"              # Edit script in $EDITOR
desto-cli scripts show "name"              # Display script content
desto-cli scripts delete "name"            # Delete script
desto-cli scripts copy "src" "dest"        # Copy script
desto-cli scripts run "name" [args]        # Run script directly or in tmux
```

## Key Features

### 🎯 **Session Management**
- Start sessions with custom commands
- List sessions with rich formatting
- Kill individual or all sessions
- Attach to running sessions
- Track session status (running/finished)

### � **Script Management**
- Create scripts with templates (bash/python)
- List scripts with icons and metadata
- Edit scripts in preferred editor ($EDITOR)
- Show script content with syntax highlighting
- Copy and delete scripts
- Run scripts directly or in tmux sessions
- Automatic executable permission handling

### �📊 **Rich Output**
- Colorized terminal output using Rich
- Formatted tables for session listings
- Progress indicators and status icons
- Human-readable timestamps and durations
- Syntax highlighting for script content

### 📝 **Logging**
- Automatic log file creation per session
- View last N lines or entire logs
- Follow logs in real-time (tail -f behavior)
- Configurable log directory

### ⚙️ **Configuration**
- Environment variable support (`DESTO_SCRIPTS_DIR`, `DESTO_LOGS_DIR`)
- Custom directory paths via command line options
- Verbose output modes
- System requirements checking

## Future Enhancements

The modular architecture makes it easy to add:

- ~~Script management commands~~ ✅ **Implemented**
- Chain/queue management for script sequences
- Scheduling functionality  
- Configuration management
- Advanced filtering and search
- Integration with other tools

## Dependencies

Core functionality requires only:
- `loguru` - Logging
- `psutil` - System information (if added)

Optional rich CLI experience:
- `typer` - CLI framework
- `rich` - Terminal formatting

The code is designed to gracefully handle missing optional dependencies.
