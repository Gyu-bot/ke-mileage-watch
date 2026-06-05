---
name: korean-air-mileage-watch
description: Use when building, running, or maintaining 민규's Korean Air SKYPASS mileage award-seat watcher via a logged-in headed Chrome/CDP session; includes safe scan patterns, CLI usage, result interpretation, and API pitfalls.
version: 1.0.0
author: Som / Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [travel, korean-air, skypass, mileage, cdp, chrome, award-availability]
    related_skills: [authenticated-web-api-recon, software-development-workflows]
---

# Korean Air Mileage Watch

## Overview

Use this skill for 대한항공/SKYPASS mileage award-seat discovery using 민규's local Chrome/CDP watcher project.

The working implementation lives at:

```text
~/dev/ke-mileage-watch
```

The safe operating model is **headed Chrome + manual login + CDP/page-context fetch**:

```text
dev-chrome with --remote-debugging-port=9222
→ 민규 manually logs in / completes 2FA
→ CLI connects to Chrome CDP
→ CLI executes fetch inside koreanair.com page context
→ parse /api/ap/booking/avail/awardAvailability
→ summarize availability
```

Do **not** automate SKYPASS login, OTP, booking, payment, cancellation, or reservation finalization.

## When to Use

Use this when 민규 asks to:

- Check Korean Air mileage award availability.
- Scan date ranges, 왕복/편도, or destination regions such as 유럽/서유럽.
- Maintain or extend `~/dev/ke-mileage-watch`.
- Interpret prior scan results under `~/dev/ke-mileage-watch/runs/`.
- Add reporting/diff/Discord notification around Korean Air mileage seats.

Do **not** use this for:

- Actual booking/reservation/payment actions.
- Typing or storing credentials.
- High-frequency scraping without explicit risk discussion.
- General flight cash-fare search unrelated to SKYPASS award availability.

## Current Project Shape

Project files:

```text
~/dev/ke-mileage-watch/
  README.md
  pyproject.toml
  ke_watch/
    __main__.py      # CLI
    cdp.py           # raw dependency-free CDP client
    koreanair.py     # Korean Air session, airport expansion, API calls
    parser.py        # awardAvailability response parser
  tests/
    test_parser.py
  runs/              # output JSON files
```

Important: 민규 prefers dev projects under `~/dev/`, not directly under `$HOME`.

## Prerequisites

1. Launch development Chrome:

```bash
dev-chrome
```

or manually:

```bash
google-chrome \
  --remote-debugging-address=127.0.0.1 \
  --remote-debugging-port=9222 \
  --user-data-dir=/path/to/ke-chrome-profile \
  --no-first-run \
  --no-default-browser-check
```

2. 민규 logs in manually to Korean Air in that Chrome profile.

3. Work from project root:

```bash
cd ~/dev/ke-mileage-watch
```

4. Verify parser/unit test:

```bash
python3 -m unittest discover -s tests -v
```

## CLI Usage

### Single round-trip destination

```bash
python3 -m ke_watch search \
  --from sel \
  --to NRT \
  --depart 2026-06-21 \
  --return 2026-06-22 \
  --cabin prestige
```

### One-way

```bash
python3 -m ke_watch search \
  --from sel \
  --to CDG \
  --depart 2026-10-01 \
  --trip OW \
  --cabin prestige --cabin first
```

### Date range + return range

```bash
python3 -m ke_watch search \
  --from sel \
  --to LHR --to CDG --to FRA \
  --depart-range 2026-10-01:2026-10-04 \
  --return-range 2026-10-11:2026-10-13 \
  --cabin prestige --cabin first \
  --sleep-min 5 --sleep-max 12 \
  --continue-on-error \
  --output runs/example.json
```

### Region destination listing

```bash
python3 -m ke_watch destinations --region EUR
```

Observed Europe codes from Korean Air route data included:

```text
LHR FCO LIS MAD MXP BUD VIE AMS IST ZRH CDG PRG FRA
```

For a practical 서유럽 주요 9개 scan, use:

```text
LHR CDG FRA AMS ZRH MAD LIS FCO MXP
```

## Known Working API Details

Endpoint:

```text
POST https://www.koreanair.com/api/ap/booking/avail/awardAvailability
```

The request must be sent from inside the logged-in Korean Air page context with relevant browser/session headers. A simple browser-context fetch failed until these were added:

```text
accept: application/json
content-type: application/json
channel: pc
timestamp: String(Date.now())
ksessionId: sessionStorage.ksessionId
x-queueit-ajaxpageurl: encodeURIComponent(location.href)
```

Core payload shape:

```json
{
  "commercialFareFamilies": ["KEBONUSNEW"],
  "currency": "",
  "sta": false,
  "segmentList": [
    {"departureDate": "20261001", "departureAirport": "sel", "arrivalAirport": "CDG"},
    {"departureDate": "20261011", "departureAirport": "CDG", "arrivalAirport": "sel"}
  ],
  "travelers": [
    {
      "travellerType": "ADT",
      "fqtvNumber": "<from loggedInUserInfo>",
      "lastName": "<from loggedInUserInfo>",
      "firstName": "<from loggedInUserInfo>",
      "discountCode": ""
    }
  ],
  "corporateCode": "string"
}
```

Response top-level:

```text
currency
upsellBoundAvailList[]
```

Within each bound:

```text
boundId
upsellCalendarFareList[]
availFlightList[]
```

Seat availability is parsed from:

```text
availFlightList[].commercialFareFamilyList[].seatCount
availFlightList[].commercialFareFamilyList[].soldout
availFlightList[].commercialFareFamilyList[].totalMileage
availFlightList[].commercialFareFamilyList[].totalTax
```

Cabin/fare families:

```text
KEBONUSEY = economy / 일반석
KEBONUSPR = prestige / 프레스티지
KEBONUSFR = first / 일등석
```

## Interpreting Results

Output rows may contain:

```text
type: availability
```

or:

```text
type: error
```

If a scan output has fewer rows than expected, that does not mean the missing combinations were skipped: successful no-seat combinations produce no availability rows. To interpret properly, compare expected combinations against:

- availability rows
- error rows
- expected total combinations

Example from the first 서유럽 scan:

```text
Round-trip expected: 108
Availability rows: 0
Errors: 61
Success/no prestige+ availability: 47
```

One-way follow-up:

```text
Outbound OW expected: 36
Availability rows: 0
Errors: 12
Success/no prestige+ availability: 24

Inbound OW expected: 27
Availability rows: 0
Errors: 9
Success/no prestige+ availability: 18
```

For combined reporting, group by:

```text
query_destination, query_depart, query_return, bound_id
```

For OW inbound scans, destination/origin are inverted:

```text
--from CDG --to sel --trip OW
```

So group by `query_origin` as the European airport for inbound candidates.

## Safety / Rate Limits

Observed during testing:

```text
ERT.7190: 정상적으로 처리되지 않았습니다. 잠시 후 다시 시도해 주세요.
ERT.7126
HTTP 429
```

A 429 appeared during a 5~12 second randomized sleep scan. Treat this as a rate-limit warning.

Recommended operating posture:

- For quick manual tests: `--sleep-min 5 --sleep-max 12` is acceptable but aggressive.
- For routine scans: prefer `--sleep-min 15 --sleep-max 45`.
- Avoid immediate retry loops after `ERT.7190`, `ERT.7126`, or `HTTP 429`.
- Split large scans into smaller batches.
- Avoid 100+ calls in one burst unless 민규 explicitly accepts the risk.
- Do not run multiple Korean Air scan processes concurrently.

## Scan Recipes

### 서유럽 9개 왕복 프레스티지+ scan

```bash
cd ~/dev/ke-mileage-watch

python3 -m ke_watch search \
  --from sel \
  --to LHR --to CDG --to FRA --to AMS --to ZRH --to MAD --to LIS --to FCO --to MXP \
  --depart-range 2026-10-01:2026-10-04 \
  --return-range 2026-10-11:2026-10-13 \
  --cabin prestige --cabin first \
  --sleep-min 5 --sleep-max 12 \
  --continue-on-error \
  --output runs/west-europe-YYYY-MM-DD.json
```

Expected calls:

```text
9 destinations × 4 departure dates × 3 return dates = 108 calls
```

Observed timing at 5~12s random sleep:

```text
왕복 108 calls: about 15–17 minutes
편도 63 calls: about 8–10 minutes
Combined test: about 23–27 minutes
```

### 편도 follow-up scan

Outbound:

```bash
python3 -m ke_watch search \
  --from sel \
  --to LHR --to CDG --to FRA --to AMS --to ZRH --to MAD --to LIS --to FCO --to MXP \
  --depart-range 2026-10-01:2026-10-04 \
  --trip OW \
  --cabin prestige --cabin first \
  --sleep-min 5 --sleep-max 12 \
  --continue-on-error \
  --output runs/west-europe-outbound-ow.json
```

Inbound must be run per origin unless the CLI is extended to support multiple origins:

```bash
python3 -m ke_watch search \
  --from CDG --to sel \
  --depart-range 2026-10-11:2026-10-13 \
  --trip OW \
  --cabin prestige --cabin first \
  --sleep-min 5 --sleep-max 12 \
  --continue-on-error \
  --output runs/CDG-inbound-ow.json
```

## Common Pitfalls

1. **Assuming headless or pure HTTP is enough.** It is not reliable. Direct replay outside the browser context produced Korean Air app errors.

2. **Using computer-use for scans.** Computer-use was only for recon. Production scanning should use CDP/page-context fetch.

3. **Forgetting `ksessionId` and Queue-It headers.** Without these, `awardAvailability` may return app errors even inside Chrome.

4. **Treating empty output as failure.** Empty availability rows can mean successful scan with no matching cabin/seats.

5. **Running too fast.** `HTTP 429` was observed. Slow down and split scans.

6. **Confusing city codes and airport codes.** `sel` is accepted as Seoul/all airports in observed flows; region expansion returns mixed city/airport codes. Verify route validity before very large scans.

7. **Persisting raw captures.** Raw authenticated responses can include personal SKYPASS profile data. Keep only minimized/redacted fixtures.

8. **Saving projects in `$HOME`.** 민규 prefers development projects under `~/dev/`.

## Next Improvements

Good next additions to `~/dev/ke-mileage-watch`:

- `report` subcommand: summarize JSON files into 왕복 가능 / 출국 편도 / 귀국 편도 / errors.
- Config file for named scans.
- Built-in multi-origin inbound scans.
- Retry queue that defers `ERT.*` / `429` combinations to later batches.
- Discord notification with diff against previous successful results.
- Safer default sleeps for routine monitoring.

## Verification Checklist

- [ ] `dev-chrome` is running with CDP port 9222.
- [ ] 민규 manually logged into Korean Air; no password/OTP automation used.
- [ ] `cd ~/dev/ke-mileage-watch` before commands.
- [ ] `python3 -m unittest discover -s tests -v` passes after code changes.
- [ ] Scan uses randomized sleep and `--continue-on-error` for broad ranges.
- [ ] Output JSON is saved under `runs/`.
- [ ] Results are interpreted using expected combination count, availability count, and error count.
- [ ] Any 429 or repeated ERT errors are treated as a signal to slow down or stop.
