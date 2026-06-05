from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

CABIN_NAMES = {
    "KEBONUSEY": "economy",
    "KEBONUSPR": "prestige",
    "KEBONUSFR": "first",
}

CABIN_LABELS = {
    "KEBONUSEY": "일반석",
    "KEBONUSPR": "프레스티지",
    "KEBONUSFR": "일등석",
}


@dataclass(frozen=True)
class AwardFare:
    cabin: str
    cabin_label: str
    fare_family: str
    booking_class: str
    rbd: str
    miles: int
    tax: float
    currency: str
    seat_count: int
    sold_out: bool


@dataclass(frozen=True)
class AwardFlight:
    bound_id: str
    flight: str
    operating_flight: str
    code_share: bool
    departure_airport: str
    arrival_airport: str
    departure_at: str
    arrival_at: str
    duration: str
    aircraft: str
    fares: tuple[AwardFare, ...]

    @property
    def available_fares(self) -> tuple[AwardFare, ...]:
        return tuple(f for f in self.fares if not f.sold_out and f.seat_count > 0)


def _parse_dt(value: str) -> str:
    if not value:
        return ""
    return datetime.strptime(value, "%Y%m%d%H%M%S").isoformat(timespec="minutes")


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(str(value))
    except Exception:
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value))
    except Exception:
        return default


def parse_award_availability(data: dict[str, Any]) -> list[AwardFlight]:
    currency = data.get("currency") or ""
    flights: list[AwardFlight] = []
    for bound in data.get("upsellBoundAvailList") or []:
        bound_id = str(bound.get("boundId", ""))
        for item in bound.get("availFlightList") or []:
            info = (item.get("flightInfoList") or [{}])[0]
            carrier = info.get("carrierCode") or ""
            flight_no = info.get("flightNumber") or ""
            op_carrier = info.get("operationCarrierCode") or carrier
            op_no = info.get("operationFlightNo") or flight_no
            code_share = bool(info.get("codeShare")) and (op_carrier, op_no) != (carrier, flight_no)
            fares: list[AwardFare] = []
            for fare in item.get("commercialFareFamilyList") or []:
                traveller = (fare.get("travellerTypeFareList") or [{}])[0]
                seg_fare = (traveller.get("segmentFareInfoList") or [{}])[0]
                fare_family = fare.get("fareFamily") or seg_fare.get("fareFamily") or ""
                seat_count = _as_int(fare.get("seatCount"))
                sold_out = bool(fare.get("soldout") or fare.get("soldOut")) or seat_count <= 0
                fares.append(
                    AwardFare(
                        cabin=CABIN_NAMES.get(fare_family, fare_family),
                        cabin_label=CABIN_LABELS.get(fare_family, fare_family),
                        fare_family=fare_family,
                        booking_class=fare.get("bookingClass") or "",
                        rbd=seg_fare.get("rbd") or "",
                        miles=_as_int(fare.get("totalMileage") or traveller.get("mileage")),
                        tax=_as_float(fare.get("totalTax") or traveller.get("tax")),
                        currency=currency or traveller.get("currency") or "",
                        seat_count=seat_count,
                        sold_out=sold_out,
                    )
                )
            flights.append(
                AwardFlight(
                    bound_id=bound_id,
                    flight=f"{carrier}{flight_no}",
                    operating_flight=f"{op_carrier}{op_no}",
                    code_share=code_share,
                    departure_airport=item.get("departureAirport") or info.get("departureAirport") or "",
                    arrival_airport=item.get("arrivalAirport") or info.get("arrivalAirport") or "",
                    departure_at=_parse_dt(item.get("departureDate") or info.get("departureDateTime") or ""),
                    arrival_at=_parse_dt(item.get("arrivalDate") or info.get("arrivalDateTime") or ""),
                    duration=item.get("totalFlyingTime") or info.get("flyingTime") or "",
                    aircraft=info.get("aircraftTypeDesc") or info.get("aircraftType") or "",
                    fares=tuple(fares),
                )
            )
    return flights


def summarize_available(flights: list[AwardFlight], min_seats: int = 1, cabins: set[str] | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for flight in flights:
        for fare in flight.fares:
            if fare.sold_out or fare.seat_count < min_seats:
                continue
            if cabins and fare.cabin not in cabins and fare.fare_family not in cabins:
                continue
            rows.append(
                {
                    "bound_id": flight.bound_id,
                    "flight": flight.flight,
                    "operating_flight": flight.operating_flight if flight.code_share else "",
                    "departure_airport": flight.departure_airport,
                    "arrival_airport": flight.arrival_airport,
                    "departure_at": flight.departure_at,
                    "arrival_at": flight.arrival_at,
                    "duration": flight.duration,
                    "aircraft": flight.aircraft,
                    "cabin": fare.cabin,
                    "cabin_label": fare.cabin_label,
                    "seats": fare.seat_count,
                    "miles": fare.miles,
                    "tax": fare.tax,
                    "currency": fare.currency,
                    "booking_class": fare.booking_class,
                }
            )
    return rows
