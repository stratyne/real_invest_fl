"""
scripts/probe_auction_com.py
-----------------------------
One-time network probe to capture the auction.com GraphQL API
request and response for the Escambia County search page.

Uses page.expect_response() to block until each GraphQL response
arrives and capture the body before the page closes.

Output: data/raw/auction_com_probe.json

Usage:
    python scripts/probe_auction_com.py
"""
import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT   = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "data" / "raw" / "auction_com_probe.json"
TARGET_URL = "https://www.auction.com/residential/fl/escambia-county"
API_HOST   = "graph.auction.com"


def main() -> None:
    captured = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()

        print(f"Loading: {TARGET_URL}")

        # expect_response() must be set up BEFORE goto() fires
        # It blocks until a response matching the predicate arrives
        # and returns the response object synchronously
        with page.expect_response(
            lambda r: API_HOST in r.url,
            timeout=30_000,
        ) as first_response_info:
            page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30_000)

        # First response is now safely captured
        first = first_response_info.value
        print(f"  First response: {first.url} (status={first.status})")
        try:
            body = first.json()
            captured.append({"url": first.url, "status": first.status, "body": body})
        except Exception as exc:
            print(f"  Could not parse first response: {exc}")
            captured.append({
                "url": first.url,
                "status": first.status,
                "body": first.text(),
            })

        # Wait a few more seconds and capture any additional GraphQL calls
        # that fire after the first (pagination, details, etc.)
        print("Waiting for additional API calls...")
        for attempt in range(5):
            try:
                with page.expect_response(
                    lambda r: API_HOST in r.url,
                    timeout=4_000,
                ) as additional_info:
                    time.sleep(0.1)  # tiny yield to let events queue
                resp = additional_info.value
                print(f"  Additional response: {resp.url} (status={resp.status})")
                try:
                    body = resp.json()
                    captured.append({
                        "url":    resp.url,
                        "status": resp.status,
                        "body":   body,
                    })
                except Exception:
                    captured.append({
                        "url":    resp.url,
                        "status": resp.status,
                        "body":   resp.text(),
                    })
            except Exception:
                # Timeout — no more responses arriving
                print(f"  No more responses after attempt {attempt + 1}")
                break

        page.close()
        context.close()
        browser.close()

    print(f"\nCaptured {len(captured)} API response(s)")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(captured, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"Written to: {OUTPUT}")

    # Print summary of each response
    for i, r in enumerate(captured):
        print(f"\n--- Response {i+1} ---")
        print(f"  URL: {r['url']}")
        print(f"  Status: {r['status']}")
        body = r["body"]
        if isinstance(body, dict):
            print(f"  Top-level keys: {list(body.keys())}")
            data = body.get("data", {})
            if isinstance(data, dict):
                print(f"  data keys: {list(data.keys())}")
                # Go one level deeper to find the property list
                for k, v in data.items():
                    if isinstance(v, dict):
                        print(f"  data.{k} keys: {list(v.keys())}")
                    elif isinstance(v, list):
                        print(f"  data.{k}: list of {len(v)} items")
                        if v:
                            print(f"  data.{k}[0] keys: "
                                  f"{list(v[0].keys()) if isinstance(v[0], dict) else type(v[0])}")


if __name__ == "__main__":
    main()
