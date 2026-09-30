import math
import time

# RA/Dec conversion helpers
def deg_to_stellarium_ra(deg):
    rad = math.radians(deg)
    return int(rad * (0x80000000 / math.pi)) & 0xFFFFFFFF  # Unsigned 32-bit

def deg_to_stellarium_dec(deg):
    rad = math.radians(deg)
    return int(rad * (0x80000000 / math.pi))  # Signed 32-bit

def stellarium_to_deg(ra_or_dec, is_ra=True):
    rad = ra_or_dec * (math.pi / 0x80000000)
    deg = math.degrees(rad)
    if is_ra:
        return deg % 360
    return max(min(deg, 90), -90)

def deg_to_lx200_ra(deg):
    ra_hours = deg / 15
    h = int(ra_hours)
    m = int((ra_hours - h) * 60)
    s = int(((ra_hours - h) * 60 - m) * 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def deg_to_lx200_dec(deg):
    sign = '+' if deg >= 0 else '-'
    deg_abs = abs(deg)
    d = int(deg_abs)
    m = int((deg_abs - d) * 60)
    s = int(((deg_abs - d) * 60 - m) * 60)
    return f"{sign}{d:02d}*{m:02d}:{s:02d}"

def lx200_to_ra_deg(ra_str):
    """Convert LX200 RA string (HH:MM:SS) to degrees. Returns None if uninitialized (contains '?')."""
    if '?' in ra_str:
        return None
    try:
        h, m, s = map(int, ra_str.split(':'))
        return h * 15 + m * 15 / 60 + s * 15 / 3600
    except ValueError:
        raise ValueError(f"Invalid RA format: {ra_str}")

def lx200_to_dec_deg(dec_str):
    """Convert LX200 DEC string (+DD*MM:SS or -DD*MM:SS) to degrees. Returns None if uninitialized (contains '?')."""
    if '?' in dec_str:
        return None
    try:
        sign = 1 if dec_str[0] == '+' else -1
        d, m, s = map(int, dec_str[1:].replace('*', ':').split(':'))
        return sign * (d + m / 60 + s / 3600)
    except ValueError:
        raise ValueError(f"Invalid DEC format: {dec_str}")


def calculate_lst(longitude_deg):
    now = time.gmtime()  # UTC time
    JD = get_julian_date(now)
    T = (JD - 2451545.0) / 36525.0

    # Calculate Greenwich Mean Sidereal Time (GMST) in degrees
    GMST = 280.46061837 + 360.98564736629 * (JD - 2451545) + 0.000387933 * T * T - (T * T * T) / 38710000

    # Normalize to 0–360
    GMST = (GMST % 360 + 360) % 360

    # Local Sidereal Time
    LST = GMST + longitude_deg

    # Normalize to 0–360
    LST = (LST % 360 + 360) % 360

    # Convert to hours
    return LST / 15

def get_julian_date(now):
    year, month, day, hour, minute, second = now.tm_year, now.tm_mon, now.tm_mday, now.tm_hour, now.tm_min, now.tm_sec
    if month <= 2:
        year -= 1
        month += 12
    A = year // 100
    B = 2 - A + A // 4
    JD = int(365.25 * (year + 4716)) + int(30.6001 * (month + 1)) + day + B - 1524.5
    JD += (hour + minute / 60 + second / 3600) / 24
    return JD
