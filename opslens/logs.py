"""Log template mining: mask variable parts, count templates, surface patterns new during an incident."""
import re
from collections import Counter

MASKS = [(re.compile(r"\b\d{1,3}(\.\d{1,3}){3}(:\d+)?\b"), "<ip>"), (re.compile(r"\b0x[0-9a-f]+\b"), "<hex>"),
         (re.compile(r"(?<![A-Za-z])\d+(\.\d+)?"), "<n>")]


def template(line):
    for rx, rep in MASKS:
        line = rx.sub(rep, line)
    return line


def novel_templates(lines, split, end, top=5):
    base = {template(l) for t, l in lines if t < split}
    cnt = Counter(template(l) for t, l in lines if split <= t <= end)
    return [dict(template=k, count=v) for k, v in cnt.most_common() if k not in base][:top]
