"""
Fixed implementation for chain logging that ensures all scripts log to the same file properly.
"""
from pathlib import Path


def build_logging_command_fixed(log_file, info_block, exec_cmd, finished_marker, keep_alive=False):
    """
    Build a logging command that properly handles chained scripts.
    """
    quoted_log_file = f"'{log_file}'"
    cmd_parts = []

    # Check if log file exists to determine append vs create
    append_mode = log_file.exists() if hasattr(log_file, 'exists') else False
    redirect_op = ">>" if append_mode else ">"

    # Add session separator if appending
    if append_mode:
        separator = f'printf "\\n---- NEW SESSION (%s) ----\\n" "$(date +\'%Y-%m-%d %H:%M:%S\')" >> {quoted_log_file}'
        cmd_parts.append(separator)

    # Add info block if provided
    if info_block:
        # Handle newlines properly by converting \\n to actual newlines first
        clean_info = info_block.replace('\\n', '\n')
        info_cmd = f'printf "%s\\n" {repr(clean_info)} {redirect_op if not append_mode else ">>"} {quoted_log_file}'
        cmd_parts.append(info_cmd)
        redirect_op = ">>"  # Now we're always appending

    # Add pre-script logging with proper formatting
    pre_script_log = f'printf "\\n=== SCRIPT STARTING at %s ===\\n" "$(date)" {redirect_op} {quoted_log_file}'
    cmd_parts.append(pre_script_log)

    # Group the execution command in parentheses for proper redirection
    exec_with_redirect = f'({exec_cmd}) >> {quoted_log_file} 2>&1'
    cmd_parts.append(exec_with_redirect)

    # Add post-script logging
    post_script_log = f'printf "\\n=== SCRIPT FINISHED at %s ===\\n" "$(date)" >> {quoted_log_file}'
    cmd_parts.append(post_script_log)

    # Add finished marker
    cmd_parts.append(finished_marker)

    # Add keep alive if requested
    if keep_alive:
        cmd_parts.append(f"tail -f /dev/null >> {quoted_log_file} 2>&1")

    # Join all parts with &&
    return " && ".join(cmd_parts)


def build_chain_command_fixed(chain_queue, continue_on_failure=False):
    """
    Build a chain command that properly handles script execution and logging.
    """
    chain_commands = []

    for script_path, arguments in chain_queue:
        script_file = Path(script_path)

        # Add separator using echo instead of printf to avoid option parsing issues
        separator = f"echo '---- Running {script_file.name} ----'"
        chain_commands.append(separator)

        # Build execution command
        if script_file.suffix == '.py':
            exec_cmd = f"python3 '{script_path}'"
        else:
            exec_cmd = f"bash '{script_path}'"

        if arguments.strip():
            exec_cmd += f" {arguments}"

        if continue_on_failure:
            # Add exit code logging for debugging
            exec_with_exit_code = f"{exec_cmd}; printf 'Exit code: %d\\n' $?"
            chain_commands.append(exec_with_exit_code)
        else:
            chain_commands.append(exec_cmd)

    # Join commands
    if continue_on_failure:
        # Use semicolons to continue on failure
        return "; ".join(chain_commands)
    else:
        # Use && to stop on failure (current behavior)
        return " && ".join(chain_commands)
