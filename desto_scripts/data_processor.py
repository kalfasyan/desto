#!/usr/bin/env python3

import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path


def log_message(message, level="INFO"):
    """Log a message with timestamp and level."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {level}: {message}")


def simulate_data_processing():
    """Simulate processing some data files."""
    log_message("Starting data processing simulation")

    # Simulate finding files
    file_count = random.randint(5, 15)
    log_message(f"Found {file_count} files to process")

    processed = 0
    errors = 0

    for i in range(file_count):
        filename = f"data_file_{i + 1:03d}.csv"
        log_message(f"Processing {filename}...")

        # Simulate processing time
        processing_time = random.uniform(0.5, 2.0)
        time.sleep(processing_time)

        # Simulate occasional errors
        if random.random() < 0.1:  # 10% chance of error
            log_message(f"Error processing {filename}: Corrupted data", "ERROR")
            errors += 1
        else:
            log_message(f"Successfully processed {filename} in {processing_time:.2f}s")
            processed += 1

    return processed, errors


def generate_report(processed, errors, output_dir="./output"):
    """Generate a simple JSON report."""
    log_message("Generating processing report")

    # Create output directory if it doesn't exist
    Path(output_dir).mkdir(exist_ok=True)

    report = {
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "total_files": processed + errors,
            "processed_successfully": processed,
            "errors": errors,
            "success_rate": f"{(processed / (processed + errors) * 100):.1f}%"
            if (processed + errors) > 0
            else "0%",
        },
        "python_version": sys.version,
        "script_args": sys.argv[1:] if len(sys.argv) > 1 else [],
    }

    report_file = (
        Path(output_dir)
        / f"processing_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )

    with open(report_file, "w") as f:
        json.dump(report, f, indent=2)

    log_message(f"Report saved to: {report_file}")
    return report_file


def main():
    """Main function to run the data processing simulation."""
    log_message("🐍 Python Data Processing Script Started!")
    log_message(f"Python version: {sys.version}")

    # Parse command line arguments
    if len(sys.argv) > 1:
        log_message(f"Script arguments received: {sys.argv[1:]}")

        # Check for special commands
        if "--quick" in sys.argv:
            log_message("Quick mode enabled - reducing processing time")
            # You could modify behavior based on args

        if "--verbose" in sys.argv:
            log_message("Verbose mode enabled")
    else:
        log_message("No arguments provided - running in default mode")

    try:
        # Run the main processing
        processed, errors = simulate_data_processing()

        # Generate report
        report_file = generate_report(processed, errors)

        # Print summary
        log_message("=" * 50)
        log_message("PROCESSING COMPLETE!")
        log_message(f"✅ Files processed: {processed}")
        if errors > 0:
            log_message(f"❌ Errors encountered: {errors}")
        log_message(f"📊 Report: {report_file}")
        log_message("=" * 50)

        # Exit with appropriate code
        if errors > 0:
            log_message("Completed with errors", "WARN")
            sys.exit(1)
        else:
            log_message("Completed successfully!")
            sys.exit(0)

    except KeyboardInterrupt:
        log_message("Processing interrupted by user", "WARN")
        sys.exit(130)
    except Exception as e:
        log_message(f"Unexpected error: {e}", "ERROR")
        sys.exit(1)


if __name__ == "__main__":
    main()
