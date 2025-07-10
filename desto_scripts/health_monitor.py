#!/usr/bin/env python3

import json
import sys
import time
from datetime import datetime

import requests


def check_service(name, url, timeout=5):
    """Check if a service is responding."""
    try:
        print(f"🔍 Checking {name}...")
        start_time = time.time()

        response = requests.get(url, timeout=timeout)
        response_time = (time.time() - start_time) * 1000

        status = (
            "✅ UP"
            if response.status_code == 200
            else f"⚠️ STATUS {response.status_code}"
        )
        print(f"   {name}: {status} ({response_time:.0f}ms)")

        return {
            "service": name,
            "url": url,
            "status": "up" if response.status_code == 200 else "degraded",
            "response_time_ms": round(response_time, 2),
            "status_code": response.status_code,
        }

    except requests.exceptions.Timeout:
        print(f"   {name}: ❌ TIMEOUT")
        return {
            "service": name,
            "url": url,
            "status": "timeout",
            "response_time_ms": None,
            "status_code": None,
        }
    except requests.exceptions.ConnectionError:
        print(f"   {name}: ❌ CONNECTION ERROR")
        return {
            "service": name,
            "url": url,
            "status": "down",
            "response_time_ms": None,
            "status_code": None,
        }
    except Exception as e:
        print(f"   {name}: ❌ ERROR - {str(e)}")
        return {"service": name, "url": url, "status": "error", "error": str(e)}


def main():
    """Monitor various web services."""
    print("🌐 Service Health Monitor Starting...")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Default services to check
    services = [
        ("Google", "https://www.google.com"),
        ("GitHub", "https://github.com"),
        ("Python.org", "https://www.python.org"),
        ("JSONPlaceholder API", "https://jsonplaceholder.typicode.com/posts/1"),
    ]

    # Allow custom URLs via command line
    if len(sys.argv) > 1:
        print(f"Custom URLs provided: {sys.argv[1:]}")
        custom_services = []
        for i, url in enumerate(sys.argv[1:], 1):
            custom_services.append((f"Custom Service {i}", url))
        services.extend(custom_services)

    print(f"\nChecking {len(services)} services...\n")

    results = []
    start_time = time.time()

    for service_name, url in services:
        result = check_service(service_name, url)
        results.append(result)
        time.sleep(0.5)  # Small delay between checks

    total_time = time.time() - start_time

    # Summary
    print(f"\n{'=' * 50}")
    print("📊 HEALTH CHECK SUMMARY")
    print(f"{'=' * 50}")

    up_count = sum(1 for r in results if r.get("status") == "up")
    down_count = len(results) - up_count

    print(f"✅ Services UP: {up_count}")
    print(f"❌ Services DOWN/ERROR: {down_count}")
    print(f"⏱️ Total check time: {total_time:.2f}s")

    # Detailed results
    print("\n📋 DETAILED RESULTS:")
    for result in results:
        status_emoji = {
            "up": "✅",
            "down": "❌",
            "timeout": "⏰",
            "error": "💥",
            "degraded": "⚠️",
        }.get(result["status"], "❓")
        response_time = (
            f" ({result['response_time_ms']}ms)"
            if result.get("response_time_ms")
            else ""
        )
        print(f"   {status_emoji} {result['service']}{response_time}")

    # Generate JSON report if requested
    if "--json" in sys.argv:
        report = {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_services": len(results),
                "services_up": up_count,
                "services_down": down_count,
                "total_check_time_seconds": round(total_time, 2),
            },
            "results": results,
        }

        filename = f"health_check_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\n💾 JSON report saved: {filename}")

    print("\n🏁 Health check completed!")

    # Exit with error code if any services are down
    if down_count > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
