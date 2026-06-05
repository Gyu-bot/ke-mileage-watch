from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timedelta
from typing import Any

from .koreanair import KoreanAirClient, iter_dates, search_matrix
from .parser import parse_award_availability, summarize_available


def parse_date_range(value: str) -> list:
    if ":" in value:
        start, end = value.split(":", 1)
        return iter_dates(start, end)
    return [datetime.strptime(value, "%Y-%m-%d").date()]


def print_rows(rows: list[dict[str, Any]], fmt: str) -> None:
    if fmt == "json":
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    if fmt == "csv":
        if not rows:
            return
        writer = csv.DictWriter(sys.stdout, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
        return
    if not rows:
        print("No available award seats found.")
        return
    for r in rows:
        op = f" / op {r['operating_flight']}" if r.get("operating_flight") else ""
        print(
            f"[{r['query_destination']}] bound {r['bound_id']} "
            f"{r['departure_airport']}→{r['arrival_airport']} "
            f"{r['departure_at']} {r['flight']}{op} "
            f"{r['cabin_label']} {r['seats']}석 "
            f"{r['miles']:,}mi + {r['tax']:,.0f}{r['currency']}"
        )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Korean Air SKYPASS award availability checker via logged-in Chrome/CDP")
    p.add_argument("--cdp", default="http://127.0.0.1:9222", help="Chrome DevTools endpoint")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("search", help="Search live Korean Air award availability")
    s.add_argument("--from", dest="origin", default="sel", help="Origin airport/city code, e.g. sel, ICN")
    s.add_argument("--to", dest="destinations", action="append", help="Destination airport/city code. Repeatable.")
    s.add_argument("--region", help="Destination region/country/area code, e.g. EUR, Europe, 유럽, JP")
    s.add_argument("--depart", help="Departure date YYYY-MM-DD")
    s.add_argument("--depart-range", help="Departure range YYYY-MM-DD:YYYY-MM-DD")
    s.add_argument("--return", dest="return_date", help="Return date YYYY-MM-DD")
    s.add_argument("--return-range", help="Return range YYYY-MM-DD:YYYY-MM-DD")
    s.add_argument("--return-offset", type=int, help="Return N days after each departure date")
    s.add_argument("--trip", choices=["RT", "OW"], default="RT", help="Round-trip or one-way")
    s.add_argument("--cabin", action="append", choices=["economy", "prestige", "first", "KEBONUSEY", "KEBONUSPR", "KEBONUSFR"], help="Filter cabin. Repeatable.")
    s.add_argument("--min-seats", type=int, default=1)
    s.add_argument("--limit-destinations", type=int, help="Safety limit for region scans")
    s.add_argument("--format", choices=["text", "json", "csv"], default="text")
    s.add_argument("--output", help="Write result rows to a file instead of stdout")
    s.add_argument("--sleep-min", type=float, default=0, help="Minimum seconds to sleep between API calls")
    s.add_argument("--sleep-max", type=float, default=0, help="Maximum seconds to sleep between API calls")
    s.add_argument("--continue-on-error", action="store_true", help="Record per-query errors and continue scanning")

    d = sub.add_parser("destinations", help="List destination airport/city codes for a Korean Air region/country")
    d.add_argument("--region", required=True, help="Region/country/area code, e.g. EUR, Europe, 유럽, JP")
    d.add_argument("--limit", type=int)
    d.add_argument("--format", choices=["text", "json"], default="text")

    f = sub.add_parser("parse-fixture", help="Parse a saved sanitized awardAvailability fixture")
    f.add_argument("path")
    f.add_argument("--format", choices=["text", "json", "csv"], default="text")
    f.add_argument("--min-seats", type=int, default=1)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "parse-fixture":
        fixture = json.load(open(args.path, encoding="utf-8"))
        data = fixture.get("response", fixture)
        rows = summarize_available(parse_award_availability(data), min_seats=args.min_seats)
        for r in rows:
            r.setdefault("query_destination", "fixture")
        print_rows(rows, args.format)
        return 0

    if args.cmd == "destinations":
        with KoreanAirClient(args.cdp) as client:
            codes = client.region_destinations(args.region)
        if args.limit:
            codes = codes[: args.limit]
        if args.format == "json":
            print(json.dumps(codes, ensure_ascii=False, indent=2))
        else:
            print(" ".join(codes))
        return 0

    depart_dates = parse_date_range(args.depart_range or args.depart)
    return_dates = None
    if args.trip == "RT":
        if args.return_range:
            return_dates = parse_date_range(args.return_range)
        elif args.return_date:
            return_dates = parse_date_range(args.return_date)
        elif args.return_offset is None:
            raise SystemExit("RT search needs --return, --return-range, or --return-offset")

    cabins = set(args.cabin or []) or None
    with KoreanAirClient(args.cdp) as client:
        if not client.is_logged_in():
            raise SystemExit("Chrome is not logged in to Korean Air. Log in manually first.")
        destinations = [d.upper() for d in (args.destinations or [])]
        if args.region:
            region_codes = client.region_destinations(args.region)
            if args.limit_destinations:
                region_codes = region_codes[: args.limit_destinations]
            destinations.extend(region_codes)
        if not destinations:
            raise SystemExit("Specify --to or --region")
        rows = search_matrix(
            client,
            origin=args.origin,
            destinations=destinations,
            depart_dates=depart_dates,
            trip=args.trip,
            return_dates=return_dates,
            return_offset=args.return_offset,
            min_seats=args.min_seats,
            cabins=cabins,
            sleep_min=args.sleep_min,
            sleep_max=args.sleep_max,
            continue_on_error=args.continue_on_error,
        )
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
    else:
        print_rows(rows, args.format)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
