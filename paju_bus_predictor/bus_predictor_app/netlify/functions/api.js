const { XMLParser } = require("fast-xml-parser");

const BASES = {
  stations: "https://apis.data.go.kr/6410000/busstationservice/v2/getBusStationListv2",
  around: "https://apis.data.go.kr/6410000/busstationservice/v2/getBusStationAroundListv2",
  via: "https://apis.data.go.kr/6410000/busstationservice/v2/getBusStationViaRouteListv2",
  arrival_list: "https://apis.data.go.kr/6410000/busarrivalservice/v2/getBusArrivalListv2",
  arrival_item: "https://apis.data.go.kr/6410000/busarrivalservice/v2/getBusArrivalItemv2",
  route_info: "https://apis.data.go.kr/6410000/busrouteservice/v2/getBusRouteInfoItemv2",
  route_stations: "https://apis.data.go.kr/6410000/busrouteservice/v2/getBusRouteStationListv2",
  route_line: "https://apis.data.go.kr/6410000/busrouteservice/v2/getBusRouteLineListv2",
};

const ALLOWED = {
  stations: ["keyword"],
  around: ["x", "y"],
  via: ["stationId"],
  arrival_list: ["stationId"],
  arrival_item: ["stationId", "routeId"],
  route_info: ["routeId"],
  route_stations: ["routeId"],
  route_line: ["routeId"],
};

const SUFFIXES = {
  stations: ["busStationList"],
  around: ["busStationAroundList"],
  via: ["busStationViaRouteList"],
  arrival_list: ["busArrivalList"],
  arrival_item: ["busArrivalItem", "item"],
  route_info: ["busRouteInfoItem", "item"],
  route_stations: ["busRouteStationList"],
  route_line: ["busRouteLineList"],
};

function collectNamed(value, suffixes, found = []) {
  if (Array.isArray(value)) {
    value.forEach((item) => collectNamed(item, suffixes, found));
    return found;
  }
  if (!value || typeof value !== "object") return found;
  Object.entries(value).forEach(([key, child]) => {
    if (suffixes.some((suffix) => key.toLowerCase().endsWith(suffix.toLowerCase()))) {
      if (Array.isArray(child)) found.push(...child.filter((item) => item && typeof item === "object"));
      else if (child && typeof child === "object") found.push(child);
    }
    collectNamed(child, suffixes, found);
  });
  return found;
}

function normalizeBody(text, endpoint) {
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    const parser = new XMLParser({ ignoreAttributes: false, trimValues: true });
    data = parser.parse(text);
  }
  return {
    ok: true,
    endpoint,
    rows: collectNamed(data, SUFFIXES[endpoint] || []),
    raw: data,
  };
}

exports.handler = async (event) => {
  const endpoint = event.queryStringParameters?.endpoint || "";
  if (!BASES[endpoint]) {
    return json(404, { ok: false, error: "알 수 없는 API입니다." });
  }

  const apiKey = process.env.BUS_API_KEY;
  if (!apiKey) {
    return json(500, { ok: false, error: "BUS_API_KEY가 설정되지 않았습니다." });
  }

  const params = new URLSearchParams({ serviceKey: apiKey });
  for (const name of ALLOWED[endpoint]) {
    const value = event.queryStringParameters?.[name];
    if (value) params.set(name, value);
  }

  try {
    const response = await fetch(`${BASES[endpoint]}?${params.toString()}`, {
      headers: { "user-agent": "PajuBusPredictor/1.0" },
    });
    const body = await response.text();
    if (!response.ok) {
      return json(response.status, { ok: false, error: `공공 API 오류: HTTP ${response.status}` });
    }
    return json(200, normalizeBody(body, endpoint));
  } catch (error) {
    return json(502, { ok: false, error: `공공 API 연결 실패: ${error.message}` });
  }
};

function json(statusCode, payload) {
  return {
    statusCode,
    headers: { "content-type": "application/json; charset=utf-8" },
    body: JSON.stringify(payload),
  };
}
