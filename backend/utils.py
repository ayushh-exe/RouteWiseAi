def seconds_to_minutes(seconds: int) -> float:
    return round(seconds / 60, 2)

def seconds_to_hhmm(seconds: int) -> str:
    minutes = seconds // 60
    hours = minutes // 60
    minutes = minutes % 60
    return f"{hours:02d}:{minutes:02d}"

def km_from_travel_time(seconds: int, speed_kmph=30) -> float:
    hours = seconds / 3600
    return round(speed_kmph * hours, 2)

def normalize_traffic_delay(delay_seconds: int) -> int:
    return min(10, max(0, delay_seconds // 60))

def print_debug(label: str, value):
    print(f"[DEBUG] {label}: {value}")