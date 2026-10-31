"""Render a monthly GitHub contribution line chart as SVG.

Mimics github-readme-activity-graph (theme=github-compact, area=true),
but buckets contributions per calendar month over the last year instead of per day.

Usage: GITHUB_TOKEN=... python scripts/activity_graph.py <username> <output.svg>
"""

import json
import math
import os
import sys
import urllib.request
from datetime import date

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""

WIDTH, HEIGHT = 1200, 420
LEFT, RIGHT, TOP, BOTTOM = 90, 1150, 80, 350
LINE, POINT, TEXT = "#26a641", "#8b949e", "#8b949e"


def fetch_months(login: str, token: str) -> list[tuple[date, int]]:
    body = json.dumps({"query": QUERY, "variables": {"login": login}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    if "errors" in payload:
        raise RuntimeError(payload["errors"])
    weeks = payload["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    months: dict[date, int] = {}
    for w in weeks:
        for d in w["contributionDays"]:
            day = date.fromisoformat(d["date"])
            key = day.replace(day=1)
            months[key] = months.get(key, 0) + d["contributionCount"]
    # The calendar starts mid-month a year ago; keep the last 12 calendar months.
    return sorted(months.items())[-12:]


def nice_step(max_value: int) -> int:
    # Aim for about 10 horizontal grid lines with a 1/2/5 x 10^n step.
    raw = max(max_value, 1) / 10
    mag = 10 ** math.floor(math.log10(raw)) if raw >= 1 else 1
    for m in (1, 2, 5, 10):
        if m * mag >= raw:
            return int(m * mag)
    return int(10 * mag)


def smooth_path(points: list[tuple[float, float]]) -> str:
    # Monotone cubic interpolation so the curve never overshoots below zero.
    n = len(points)
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    d = [(ys[i + 1] - ys[i]) / (xs[i + 1] - xs[i]) for i in range(n - 1)]
    m = [d[0]] + [0.0 if d[i - 1] * d[i] <= 0 else (d[i - 1] + d[i]) / 2 for i in range(1, n - 1)] + [d[-1]]
    for i in range(n - 1):
        if d[i] == 0:
            m[i] = m[i + 1] = 0.0
            continue
        a, b = m[i] / d[i], m[i + 1] / d[i]
        s = a * a + b * b
        if s > 9:
            t = 3 / math.sqrt(s)
            m[i], m[i + 1] = t * a * d[i], t * b * d[i]
    out = [f"M{xs[0]:.2f},{ys[0]:.2f}"]
    for i in range(n - 1):
        h = (xs[i + 1] - xs[i]) / 3
        out.append(
            f"C{xs[i] + h:.2f},{ys[i] + m[i] * h:.2f},"
            f"{xs[i + 1] - h:.2f},{ys[i + 1] - m[i + 1] * h:.2f},"
            f"{xs[i + 1]:.2f},{ys[i + 1]:.2f}"
        )
    return "".join(out)


def render(login: str, months: list[tuple[date, int]]) -> str:
    counts = [c for _, c in months]
    step = nice_step(max(counts))
    top_value = step * max(1, math.ceil(max(counts) / step))
    dx = (RIGHT - LEFT) / (len(months) - 1)

    def y_of(v: float) -> float:
        return BOTTOM - (BOTTOM - TOP) * v / top_value

    points = [(LEFT + i * dx, y_of(c)) for i, c in enumerate(counts)]
    line = smooth_path(points)
    area = f"M{LEFT},{BOTTOM}L{line[1:]}L{RIGHT},{BOTTOM}Z"

    parts = []
    for i, (month, _) in enumerate(months):
        x = LEFT + i * dx
        parts.append(f'<line x1="{x:.2f}" x2="{x:.2f}" y1="{TOP}" y2="{BOTTOM}" class="grid"/>')
        parts.append(
            f'<text x="{x:.2f}" y="{BOTTOM + 22}" text-anchor="middle" class="label">'
            f'{month.strftime("%b %y")}</text>'
        )
    for v in range(0, top_value + 1, step):
        y = y_of(v)
        parts.append(f'<line x1="{LEFT}" x2="{RIGHT}" y1="{y:.2f}" y2="{y:.2f}" class="grid"/>')
        parts.append(f'<text x="{LEFT - 10}" y="{y + 4:.2f}" text-anchor="end" class="label">{v}</text>')

    parts.append(f'<path d="{area}" class="area"/>')
    parts.append(f'<path d="{line}" class="line"/>')
    for (x, y), c in zip(points, counts):
        parts.append(f'<line x1="{x:.2f}" y1="{y:.2f}" x2="{x + 0.01:.2f}" y2="{y:.2f}" class="point"><title>{c}</title></line>')

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" fill="none">
<style>
  text {{ font-family: 'Segoe UI', Ubuntu, Sans-Serif; fill: {TEXT}; }}
  .title {{ font-size: 20px; font-weight: 600; }}
  .label {{ font-size: 12px; font-weight: 600; }}
  .grid {{ stroke: {POINT}; stroke-width: 1px; stroke-opacity: 0.3; stroke-dasharray: 2px; }}
  .area {{ fill: {LINE}; fill-opacity: 0.1; stroke: none; }}
  .line {{ fill: none; stroke: {LINE}; stroke-width: 4px; stroke-dasharray: 5000; stroke-dashoffset: 5000; animation: dash 5s ease-in-out forwards; }}
  .point {{ stroke: {POINT}; stroke-width: 10px; stroke-linecap: round; animation: blink 1s ease-in-out forwards; }}
  @keyframes dash {{ to {{ stroke-dashoffset: 0; }} }}
  @keyframes blink {{ from {{ opacity: 0; transform: translateX(-20px); }} to {{ opacity: 1; transform: translateX(0); }} }}
</style>
<text x="{WIDTH / 2}" y="38" text-anchor="middle" class="title">{login}'s Contribution Graph</text>
{chr(10).join(parts)}
<text x="{(LEFT + RIGHT) / 2}" y="{HEIGHT - 20}" text-anchor="middle" class="label">Months</text>
<text x="20" y="{(TOP + BOTTOM) / 2}" transform="rotate(-90, 20, {(TOP + BOTTOM) / 2})" text-anchor="middle" dominant-baseline="hanging" class="label">Contributions</text>
</svg>
"""


def main() -> None:
    login, output = sys.argv[1], sys.argv[2]
    months = fetch_months(login, os.environ["GITHUB_TOKEN"])
    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    with open(output, "w") as f:
        f.write(render(login, months))


if __name__ == "__main__":
    main()
