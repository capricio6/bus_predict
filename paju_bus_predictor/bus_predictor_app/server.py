from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qs
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import json
import mimetypes
import os
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parent


def load_local_env():
    env_path = ROOT / "config.env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_local_env()
API_KEY = os.environ.get("BUS_API_KEY", "")

BASES = {
    "stations": "https://apis.data.go.kr/6410000/busstationservice/v2/getBusStationListv2",
    "around": "https://apis.data.go.kr/6410000/busstationservice/v2/getBusStationAroundListv2",
    "via": "https://apis.data.go.kr/6410000/busstationservice/v2/getBusStationViaRouteListv2",
    "arrival_list": "https://apis.data.go.kr/6410000/busarrivalservice/v2/getBusArrivalListv2",
    "arrival_item": "https://apis.data.go.kr/6410000/busarrivalservice/v2/getBusArrivalItemv2",
    "route_info": "https://apis.data.go.kr/6410000/busrouteservice/v2/getBusRouteInfoItemv2",
    "route_stations": "https://apis.data.go.kr/6410000/busrouteservice/v2/getBusRouteStationListv2",
    "route_line": "https://apis.data.go.kr/6410000/busrouteservice/v2/getBusRouteLineListv2",
}


def strip_namespace(tag):
    return tag.split("}", 1)[-1] if "}" in tag else tag


def flatten(node):
    children = list(node)
    if not children:
        return (node.text or "").strip()
    grouped = {}
    for child in children:
        key = strip_namespace(child.tag)
        value = flatten(child)
        if key in grouped:
            if not isinstance(grouped[key], list):
                grouped[key] = [grouped[key]]
            grouped[key].append(value)
        else:
            grouped[key] = value
    return grouped


def collect_named(obj, suffixes):
    found = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            lower = key.lower()
            if any(lower.endswith(s.lower()) for s in suffixes):
                if isinstance(value, list):
                    found.extend([v for v in value if isinstance(v, dict)])
                elif isinstance(value, dict):
                    found.append(value)
            found.extend(collect_named(value, suffixes))
    elif isinstance(obj, list):
        for value in obj:
            found.extend(collect_named(value, suffixes))
    return found


def normalize_payload(body, endpoint):
    text = body.decode("utf-8", errors="replace")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        root = ET.fromstring(text)
        data = {strip_namespace(root.tag): flatten(root)}

    suffixes = {
        "stations": ["busStationList"],
        "around": ["busStationAroundList"],
        "via": ["busStationViaRouteList"],
        "arrival_list": ["busArrivalList"],
        "arrival_item": ["busArrivalItem"],
        "route_info": ["busRouteInfoItem"],
        "route_stations": ["busRouteStationList"],
        "route_line": ["busRouteLineList"],
    }.get(endpoint, [])

    rows = collect_named(data, suffixes)
    if not rows and endpoint in {"arrival_item", "route_info"}:
        rows = collect_named(data, ["item"])
    return {"ok": True, "endpoint": endpoint, "rows": rows, "raw": data}


def call_api(endpoint, query):
    if endpoint not in BASES:
        return 404, {"ok": False, "error": "알 수 없는 API입니다."}
    if not API_KEY:
        return 500, {
            "ok": False,
            "error": "BUS_API_KEY가 설정되지 않았습니다. 배포 서비스의 환경변수에 API 키를 등록해 주세요.",
        }

    allowed = {
        "stations": ["keyword"],
        "around": ["x", "y"],
        "via": ["stationId"],
        "arrival_list": ["stationId"],
        "arrival_item": ["stationId", "routeId"],
        "route_info": ["routeId"],
        "route_stations": ["routeId"],
        "route_line": ["routeId"],
    }[endpoint]
    params = {"serviceKey": API_KEY}
    for name in allowed:
        if name in query and query[name][0] != "":
            params[name] = query[name][0]
    if endpoint == "around":
        params["x"] = query.get("x", [""])[0]
        params["y"] = query.get("y", [""])[0]

    url = BASES[endpoint] + "?" + urlencode(params)
    req = Request(url, headers={"User-Agent": "PajuBusPredictor/1.0"})
    try:
        with urlopen(req, timeout=12) as res:
            return 200, normalize_payload(res.read(), endpoint)
    except HTTPError as exc:
        return exc.code, {"ok": False, "error": f"공공 API 오류: HTTP {exc.code}"}
    except URLError as exc:
        return 502, {"ok": False, "error": f"공공 API 연결 실패: {exc.reason}"}
    except Exception as exc:
        return 500, {"ok": False, "error": f"응답 해석 실패: {exc}"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def send_json(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            endpoint = parsed.path.rsplit("/", 1)[-1]
            code, payload = call_api(endpoint, parse_qs(parsed.query))
            self.send_json(code, payload)
            return

        target = ROOT / ("index.html" if parsed.path in {"/", ""} else parsed.path.lstrip("/"))
        if not target.resolve().is_relative_to(ROOT) or not target.exists():
            self.send_error(404)
            return
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if target.suffix in {".html", ".txt", ".js", ".json", ".svg", ".webmanifest"}:
            content_type += "; charset=utf-8"
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8765"))
    host = os.environ.get("HOST", "0.0.0.0")
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"파주 버스 예측 앱: http://127.0.0.1:{port}")
    print("배포 환경에서는 서비스가 제공하는 공개 주소로 접속하세요.")
    server.serve_forever()
