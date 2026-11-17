import re


def vtuple(version):
    """版本号转可比较元组：1.2.10 > 1.2.9；非数字段按字符串比较。"""
    if not version:
        return ()
    out = []
    for p in re.split(r"[.\-_]", str(version).strip().lstrip("vV")):
        out.append((0, int(p), "") if p.isdigit() else (1, 0, p))
    return tuple(out)


def compare(a, b) -> int:
    ta, tb = vtuple(a), vtuple(b)
    return (ta > tb) - (ta < tb)


def model_matches(applicable, model) -> bool:
    return not applicable or "*" in applicable or model in applicable
