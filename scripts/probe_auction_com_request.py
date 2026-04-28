"""
scripts/probe_auction_com_request.py
-------------------------------------
Captures the GraphQL request payload (query + variables) sent by
the auction.com search page to graph.auction.com/graphql.

Output: data/raw/auction_com_request_probe.json

Usage:
    python scripts/probe_auction_com_request.py
"""
import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT   = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "data" / "raw" / "auction_com_request_probe.json"
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

        # Capture both request AND response for GraphQL calls
        def handle_request(request):
            if API_HOST in request.url:
                try:
                    payload = request.post_data
                    captured.append({
                        "type":     "request",
                        "url":      request.url,
                        "method":   request.method,
                        "headers":  dict(request.headers),
                        "payload":  json.loads(payload) if payload else None,
                    })
                    print(f"  Request captured: {request.url} "
                          f"method={request.method}")
                except Exception as exc:
                    print(f"  Request capture error: {exc}")

        page.on("request", handle_request)

        print(f"Loading: {TARGET_URL}")

        with page.expect_response(
            lambda r: API_HOST in r.url and
                      "seek_listings" in (r.text() if r.status == 200 else ""),
            timeout=30_000,
        ) as resp_info:
            page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30_000)

        resp = resp_info.value
        print(f"  Response captured: {resp.url} status={resp.status}")
        try:
            body = resp.json()
            captured.append({
                "type":   "response",
                "url":    resp.url,
                "status": resp.status,
                "body":   body,
            })
        except Exception as exc:
            print(f"  Response parse error: {exc}")

        page.close()
        context.close()
        browser.close()

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(captured, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"\nWritten to: {OUTPUT}")

    # Print request payloads
    for item in captured:
        if item["type"] == "request":
            print(f"\n--- REQUEST ---")
            print(f"  URL: {item['url']}")
            print(f"  Method: {item['method']}")
            payload = item.get("payload")
            if payload:
                print(f"  operationName: {payload.get('operationName')}")
                print(f"  variables: {json.dumps(payload.get('variables', {}), indent=4)}")
                query = payload.get("query", "")
                print(f"  query (first 300 chars): {query[:300]}")


if __name__ == "__main__":
    main()
