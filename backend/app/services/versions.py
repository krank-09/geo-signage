"""Agent version comparison and the compatibility policy."""
import re


def parse(version: str | None) -> tuple[int, ...] | None:
    """'1.2.0' -> (1, 2, 0). Tolerates suffixes like '1.2.0-rc1' and short versions like '1.2'."""
    if not version:
        return None
    nums = re.findall(r"\d+", version.split("-")[0])
    if not nums:
        return None
    return tuple(int(n) for n in (nums + ["0", "0", "0"])[:3])


def compare(a: str | None, b: str | None) -> int:
    pa, pb = parse(a), parse(b)
    if pa is None or pb is None:
        return 0
    return (pa > pb) - (pa < pb)


def compatibility(version: str | None, recommended: str | None, supported: str | None) -> str:
    """unknown | unsupported | outdated | ok.  `supported` is the floor (below it we cannot promise anything works);
    `recommended` is the version we want everyone on."""
    if parse(version) is None:
        return "unknown"
    if supported and compare(version, supported) < 0:
        return "unsupported"
    if recommended and compare(version, recommended) < 0:
        return "outdated"
    return "ok"
