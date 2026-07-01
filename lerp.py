def lerp(a: float, b: float, t: float) -> float:
    return min(b, (1 - t) * a + t * b)


def fast_lerp(a: float, b: float, t: float, err: float) -> float:
    if abs(a - b) < err:
        return b
    return lerp(a, b, t)


def inv_lerp(a: float, b: float, v: float) -> float:
    return max(0, min(1, (v - a) / (b - a)))
