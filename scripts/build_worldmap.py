"""세계 지도 SVG 경로를 만든다(한 번만 실행, 결과를 저장소에 둔다. 외부 CDN 불필요).

입력: world-atlas@2 의 countries-110m.json(Natural Earth 1:110m, TopoJSON, ISC 라이선스)
      예) npm pack world-atlas@2.0.2 && tar xzf world-atlas-2.0.2.tgz → package/countries-110m.json
출력: site/data/global/worldmap.json = {w, h, lon0, lat0, k, countries: {숫자코드: SVG path}}
투영: 등장방형(경도·위도 그대로), 남극 제외, 위도 83°N ~ 56°S. 화면에서 점 위치는 같은 식으로 계산한다.
사용: python scripts/build_worldmap.py package/countries-110m.json
"""
import json
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "site" / "data" / "global" / "worldmap.json"
W, LON0, LAT0, LAT1 = 1000, -180.0, 83.0, -56.0
K = W / 360.0
H = round((LAT0 - LAT1) * K)


def xy(lon, lat):
    return round((lon - LON0) * K, 1), round((LAT0 - lat) * K, 1)


def decode_arcs(topo):
    sx, sy = topo["transform"]["scale"]
    tx, ty = topo["transform"]["translate"]
    arcs = []
    for arc in topo["arcs"]:
        x = y = 0
        pts = []
        for dx, dy in arc:
            x += dx
            y += dy
            pts.append((x * sx + tx, y * sy + ty))
        arcs.append(pts)
    return arcs


def ring(arcs, idxs):
    pts = []
    for i in idxs:
        a = arcs[i] if i >= 0 else arcs[~i][::-1]
        pts.extend(a if not pts else a[1:])
    return pts


def path(arcs, polys):
    out = []
    for poly in polys:
        for r in poly:
            pts, last = [], None
            for lon, lat in ring(arcs, r):
                p = xy(lon, lat)
                if p != last:
                    pts.append(p)
                    last = p
            if len(pts) >= 3:
                out.append("M" + "L".join(f"{x:g},{y:g}" for x, y in pts) + "Z")
    return "".join(out)


def main(src):
    topo = json.loads(Path(src).read_text(encoding="utf-8"))
    arcs = decode_arcs(topo)
    countries = {}
    for g in topo["objects"]["countries"]["geometries"]:
        if g.get("id") in (None, "010"):  # 남극 제외
            continue
        polys = g["arcs"] if g["type"] == "MultiPolygon" else [g["arcs"]] if g["type"] == "Polygon" else []
        d = path(arcs, polys)
        if d:
            countries[g["id"]] = countries.get(g["id"], "") + d
    OUT.write_text(json.dumps({"source": "Natural Earth 1:110m via world-atlas@2 (ISC)", "w": W, "h": H, "lon0": LON0, "lat0": LAT0,
                               "k": round(K, 6), "countries": countries}, separators=(",", ":")), encoding="utf-8")
    print(f"saved {OUT} ({OUT.stat().st_size // 1024} KB, {len(countries)}개국)")


if __name__ == "__main__":
    main(sys.argv[1])
