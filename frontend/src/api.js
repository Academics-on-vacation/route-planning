const BASE = "/api";

async function req(path, options) {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = JSON.stringify(body.detail);
    } catch {}
    throw new Error(detail);
  }
  return res.json();
}
export const api = {
  regions: () => req("/regions"),
  requests: (id) => req(`/regions/${id}/requests`),
  engineers: (id) => req(`/regions/${id}/engineers`),
  allEngineers: (regionId = null) =>
    req(`/engineers${regionId == null ? "" : `?region_id=${regionId}`}`),
  setStartPoint: (id, start_lat, start_lon) =>
    req(`/engineers/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ start_lat, start_lon }),
    }),

  // Новая заявка (в том числе авария) в регионе.
  createRequest: (regionId, body) =>
    req(`/regions/${regionId}/requests`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  replan: (regionId, at, options = {}) =>
    req("/plan/replan", {
      method: "POST",
      body: JSON.stringify({ region_id: regionId, at, options }),
    }),

  plan: (id, options = {}) =>
    req("/plan", {
      method: "POST",
      body: JSON.stringify({ region_id: id, options }),
    }),
};
