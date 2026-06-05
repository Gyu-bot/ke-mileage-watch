from __future__ import annotations

import json
import random
import time
from datetime import date, datetime, timedelta
from typing import Any

from .cdp import CdpClient
from .parser import parse_award_availability, summarize_available

REGION_ALIASES = {
    "EUROPE": "EUR",
    "유럽": "EUR",
    "EUR": "EUR",
    "JAPAN": "EAA",
    "일본": "JP",
    "EAA": "EAA",
    "SOUTHEAST_ASIA": "SEA",
    "동남아": "SEA",
    "SEA": "SEA",
    "AMERICA": "AME",
    "미주": "AME",
    "AME": "AME",
    "OCEANIA": "OCN",
    "대양주": "OCN",
    "OCN": "OCN",
    "MIDDLE_EAST": "MEA",
    "중동": "MEA",
    "MEA": "MEA",
}


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def normalize_yyyymmdd(value: str) -> str:
    return datetime.strptime(value, "%Y-%m-%d").strftime("%Y%m%d")


def iter_dates(start: str, end: str) -> list[date]:
    s = datetime.strptime(start, "%Y-%m-%d").date()
    e = datetime.strptime(end, "%Y-%m-%d").date()
    if e < s:
        raise ValueError("date range end is before start")
    days = []
    cur = s
    while cur <= e:
        days.append(cur)
        cur += timedelta(days=1)
    return days


class KoreanAirClient:
    def __init__(self, cdp_url: str = "http://127.0.0.1:9222"):
        self.cdp = CdpClient(cdp_url)

    def __enter__(self) -> "KoreanAirClient":
        self.cdp.connect()
        self.cdp.ensure_koreanair_page()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.cdp.close()

    def is_logged_in(self) -> bool:
        js = """
        (() => {
          const raw = sessionStorage.getItem('loggedInUserInfo');
          if (!raw) return false;
          try { return !!JSON.parse(raw).signinStatus; } catch(e) { return false; }
        })()
        """
        return bool(self.cdp.evaluate(js))

    def traveler_stub(self) -> dict[str, str]:
        js = """
        (() => {
          const raw = sessionStorage.getItem('loggedInUserInfo');
          if (!raw) return null;
          const u = JSON.parse(raw).userInfo || {};
          return {
            travellerType: 'ADT',
            fqtvNumber: u.skypassNumber || '',
            lastName: u.englishLastName || '',
            firstName: u.englishFirstName || '',
            discountCode: ''
          };
        })()
        """
        value = self.cdp.evaluate(js)
        if not value or not value.get("fqtvNumber"):
            raise RuntimeError("Korean Air login info not found in Chrome session. Log in manually first.")
        return value

    def airport_list(self, flow_type: str = "RE", lang: str = "ko") -> list[dict[str, Any]]:
        js = f"""
        (async () => {{
          const urls = [
            '/api/et/route/c/a/getReservationAirport?airportCode=&directionType=D&flowType=NR&langCode={lang}&nationCode=kr&tripType=RO',
            '/api/et/route/c/a/getReservationAirport?directionType=D&flowType={flow_type}&langCode={lang}&nationCode=kr&tripType=RO',
            '/api/et/uiCommon/c/a/airportList?flowType={flow_type}&langCode={lang}'
          ];
          for (const url of urls) {{
            const r = await fetch(url, {{credentials:'include', headers: {{'accept':'application/json'}}}});
            if (!r.ok) continue;
            const j = await r.json();
            const list = j.airportInfoList || j.locationInfoList || j.airportList || [];
            if (Array.isArray(list) && list.length) return list;
          }}
          return [];
        }})()
        """
        return self.cdp.evaluate(js) or []

    def region_destinations(self, region: str, exclude_country: str | None = "KR") -> list[str]:
        wanted = REGION_ALIASES.get(region.upper(), region.upper())
        airports = self.airport_list()
        codes: list[str] = []
        seen: set[str] = set()
        for a in airports:
            code = (a.get("airportCode") or "").upper()
            if not code:
                continue
            country = (a.get("countryCode") or "").upper()
            area = (a.get("areaCode") or "").upper()
            city = (a.get("cityCode") or "").upper()
            airport_type = (a.get("airportType") or "").upper()
            award = str(a.get("ibeAwardAirport", a.get("ibeAirport", "true"))).lower() != "false"
            if exclude_country and country == exclude_country.upper():
                continue
            if not award:
                continue
            if airport_type not in {"APO", "CTY", ""}:
                continue
            if wanted not in {area, country, city, code}:
                continue
            if code not in seen:
                seen.add(code)
                codes.append(code)
        return codes

    def search_award(self, origin: str, destination: str, depart: date, return_date: date | None = None) -> dict[str, Any]:
        traveler = self.traveler_stub()
        segments = [
            {
                "departureDate": depart.strftime("%Y%m%d"),
                "departureAirport": origin,
                "arrivalAirport": destination,
            }
        ]
        if return_date:
            segments.append(
                {
                    "departureDate": return_date.strftime("%Y%m%d"),
                    "departureAirport": destination,
                    "arrivalAirport": origin,
                }
            )
        payload = {
            "commercialFareFamilies": ["KEBONUSNEW"],
            "currency": "",
            "sta": False,
            "segmentList": segments,
            "travelers": [traveler],
            "corporateCode": "string",
        }
        js = f"""
        (async () => {{
          const payload = {compact_json(payload)};
          const ksessionId = sessionStorage.getItem('ksessionId') || '';
          const r = await fetch('/api/ap/booking/avail/awardAvailability', {{
            method: 'POST',
            credentials: 'include',
            headers: {{
              'accept': 'application/json',
              'content-type': 'application/json',
              'channel': 'pc',
              'timestamp': String(Date.now()),
              'ksessionId': ksessionId,
              'x-queueit-ajaxpageurl': encodeURIComponent(location.href)
            }},
            body: JSON.stringify(payload)
          }});
          const text = await r.text();
          let json = null;
          try {{ json = JSON.parse(text); }} catch(e) {{}}
          return {{ok: r.ok, status: r.status, json, text}};
        }})()
        """
        result = self.cdp.evaluate(js, timeout=40)
        if not result.get("ok"):
            raise RuntimeError(f"awardAvailability HTTP {result.get('status')}: {result.get('text')[:500]}")
        data = result.get("json")
        if isinstance(data, dict) and data.get("code"):
            raise RuntimeError(f"awardAvailability app error {data.get('code')}: {data.get('message')}")
        return data


def search_matrix(
    client: KoreanAirClient,
    origin: str,
    destinations: list[str],
    depart_dates: list[date],
    trip: str = "RT",
    return_dates: list[date | None] | None = None,
    return_offset: int | None = None,
    min_seats: int = 1,
    cabins: set[str] | None = None,
    sleep_min: float = 0,
    sleep_max: float = 0,
    continue_on_error: bool = False,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    first_call = True
    for dest in destinations:
        for depart in depart_dates:
            candidate_returns: list[date | None]
            if trip.upper() == "OW":
                candidate_returns = [None]
            elif return_dates:
                candidate_returns = return_dates
            elif return_offset is not None:
                candidate_returns = [depart + timedelta(days=return_offset)]
            else:
                raise ValueError("round-trip search requires return_dates or return_offset")
            for ret in candidate_returns:
                if not first_call and sleep_max > 0:
                    delay = random.uniform(sleep_min, sleep_max)
                    print(f"sleep {delay:.1f}s before {dest} {depart.isoformat()} {ret.isoformat() if ret else 'OW'}", flush=True)
                    time.sleep(delay)
                first_call = False
                try:
                    data = client.search_award(origin, dest, depart, ret)
                except Exception as exc:
                    if not continue_on_error:
                        raise
                    rows.append(
                        {
                            "type": "error",
                            "query_origin": origin,
                            "query_destination": dest,
                            "query_depart": depart.isoformat(),
                            "query_return": ret.isoformat() if ret else "",
                            "error": str(exc),
                        }
                    )
                    continue
                parsed = parse_award_availability(data)
                for row in summarize_available(parsed, min_seats=min_seats, cabins=cabins):
                    row.update(
                        {
                            "type": "availability",
                            "query_origin": origin,
                            "query_destination": dest,
                            "query_depart": depart.isoformat(),
                            "query_return": ret.isoformat() if ret else "",
                        }
                    )
                    rows.append(row)
    return rows
