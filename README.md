# Korean Air Mileage Watch

Chrome/CDP-based Korean Air SKYPASS award availability checker.

## Why Chrome/CDP?

Korean Air's award availability endpoint works reliably when called from an already logged-in, headed Chrome session. A plain HTTP replay can fail with `IBE-AP.1001`, so this tool connects to a Chrome profile launched with `--remote-debugging-port` and executes requests inside the real page context.

## Start Chrome

On this Mac the preferred launcher is:

```bash
dev-chrome
```

Or manually:

```bash
google-chrome \
  --remote-debugging-address=127.0.0.1 \
  --remote-debugging-port=9222 \
  --user-data-dir=/path/to/ke-chrome-profile \
  --no-first-run \
  --no-default-browser-check
```

Log in manually. The tool never types or stores SKYPASS credentials.

## Examples

Single destination, round trip:

```bash
python3 -m ke_watch search --from sel --to NRT --depart 2026-06-21 --return 2026-06-22
```

One-way:

```bash
python3 -m ke_watch search --from sel --to CDG --depart 2026-06-21 --trip OW
```

List region destinations, e.g. Europe:

```bash
python3 -m ke_watch destinations --region EUR
```

Region scan, e.g. Europe:

```bash
python3 -m ke_watch search --from sel --region EUR --depart 2026-06-21 --return 2026-06-28 --limit-destinations 5
```

Date range scan:

```bash
python3 -m ke_watch search --from sel --to NRT --depart-range 2026-06-20:2026-06-23 --return-offset 2
```

## Safety

- Low frequency only.
- No automatic booking/reservation/payment.
- Manual login only.
- Raw authenticated responses should not be persisted without redaction.
