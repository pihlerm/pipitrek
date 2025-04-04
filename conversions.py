import math

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
    """Convert LX200 RA string (HH:MM:SS) to degrees."""
    try:
        h, m, s = map(int, ra_str.split(':'))
        return h * 15 + m * 15 / 60 + s * 15 / 3600
    except ValueError:
        raise ValueError(f"Invalid RA format: {ra_str}")

def lx200_to_dec_deg(dec_str):
    """Convert LX200 DEC string (+DD*MM:SS or -DD*MM:SS) to degrees."""
    try:
        sign = 1 if dec_str[0] == '+' else -1
        d, m, s = map(int, dec_str[1:].replace('*', ':').split(':'))
        return sign * (d + m / 60 + s / 3600)
    except ValueError:
        raise ValueError(f"Invalid DEC format: {dec_str}")