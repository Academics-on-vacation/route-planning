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
  plan: (id, options = {}) => {
    console.log("here!!!", id, options);
    return req("/plan", {
      method: "POST",
      body: JSON.stringify({ region_id: id, options }),
    });
  },
};
