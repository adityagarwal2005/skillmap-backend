"""Input parsing helpers for values that arrive as query/form strings.

Every one of these used to be a bare float()/int() on request data, so a
client sending "abc" (or a scanner probing the API) turned into a 500
instead of a handled response.
"""

# How long a gig or collab may stay visible. The create form offers
# 2/6/12/24/48h; this is the ceiling both create views clamp to so the
# limit holds for anything posting to the API directly.
MAX_VISIBILITY_HOURS = 48


def parse_coord(value):
    """A latitude/longitude from request data, or None if unusable.

    Range-checks as well as type-checks: a numeric-but-impossible value
    like 999 would otherwise sail through and corrupt every distance
    calculation it touched.
    """
    if value in (None, ''):
        return None
    try:
        coord = float(value)
    except (TypeError, ValueError):
        return None
    if coord != coord or coord in (float('inf'), float('-inf')):  # NaN/inf
        return None
    return coord


def parse_lat(value):
    lat = parse_coord(value)
    return lat if lat is not None and -90 <= lat <= 90 else None


def parse_lon(value):
    lon = parse_coord(value)
    return lon if lon is not None and -180 <= lon <= 180 else None


def parse_float(value, default, minimum=None, maximum=None):
    """A float from request data, falling back to default when unusable."""
    result = parse_coord(value)
    if result is None:
        result = default
    if minimum is not None:
        result = max(minimum, result)
    if maximum is not None:
        result = min(maximum, result)
    return result
