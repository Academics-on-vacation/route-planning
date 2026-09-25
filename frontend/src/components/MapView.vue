<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

import { MaptilerLayer } from "@maptiler/leaflet-maptilersdk";
import {
  colorOfEngineer,
  focusEngineer,
  hover,
  isActive,
  isDimmed,
  isSelected,
  plan,
  routes,
  state,
  unassigned,
  engineerOf,
  select,
  isHovered,
  isFocused,
} from "../store.js";
import { hhmm } from "../time.js";

const MAPTILER_KEY =
  import.meta.env.VITE_MAPTILER_KEY || "BOcuCBryrZXZ49qwmbE2";
const MAP_STYLE = "dataviz-light";

const el = ref(null);

let map = null;
let layer = null;
const markers = new Map(); // requestId -> { marker, color }
const ghosts = new Map(); // requestId -> circleMarker не назначенной
const lines = new Map(); // engineerId -> polyline

const UNASSIGNED = "#99271f";
const INK = "#14161a";

onMounted(() => {
  map = L.map(el.value, {
    preferCanvas: true,
    attributionControl: true,
  }).setView([55.7, 37.7], 10);

  new MaptilerLayer({ apiKey: MAPTILER_KEY, style: MAP_STYLE }).addTo(map);

  layer = L.layerGroup().addTo(map);

  // Клик по пустому месту снимает выделение — привычный жест.
  map.on("click", (e) => {
    if (state.picking) {
      state.picked = { lat: e.latlng.lat, lon: e.latlng.lng };
      state.picking = false;
      return;
    }
    select(null);
  });

  document.querySelector(".leaflet-control-attribution").remove();
  redraw();
});

onBeforeUnmount(() => {
  map?.remove();
  map = null;
});

watch([plan, () => state.regionId], redraw);
watch(() => [state.selected, state.hovered, state.focused], restyle);

watch(
  () => state.selected,
  (id) => {
    if (id == null || !map) return;
    const marker = markers.get(String(id)) ?? ghosts.get(String(id));
    if (!marker) return;
    const latlng = markers.has(String(id))
      ? marker.marker.getLatLng()
      : marker.getLatLng();
    if (!map.getBounds().pad(-0.15).contains(latlng)) map.panTo(latlng);
  },
);

function officeIcon() {
  return L.divIcon({
    className: "",
    iconSize: [30, 30],
    iconAnchor: [15, 15],
    html: `
      <div class="map-office">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M3 11.2 12 4l9 7.2" fill="none" stroke="currentColor"
                stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M5.5 10.6V19h13v-8.4" fill="none" stroke="currentColor"
                stroke-width="2.1" stroke-linejoin="round"/>
          <path d="M10 19v-4.2h4V19" fill="none" stroke="currentColor"
                stroke-width="2.1" stroke-linejoin="round"/>
        </svg>
      </div>`,
  });
}

function homeIcon() {
  return L.divIcon({
    className: "",
    iconSize: [15, 15],
    iconAnchor: [12, 12],
    html: `
      <div class="map-home">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M3 11.2 12 4l9 7.2" fill="none" stroke="currentColor"
                stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M5.5 10.6V19h13v-8.4" fill="none" stroke="currentColor"
                stroke-width="2.1" stroke-linejoin="round"/>
          <path d="M10 19v-4.2h4V19" fill="none" stroke="currentColor"
                stroke-width="2.1" stroke-linejoin="round"/>
        </svg>
      </div>`,
  });
}

function pin(color, size, ring) {
  return L.divIcon({
    className: "",
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    html: `<div class="map-pin" style="width:${size}px;height:${size}px;background:${color}${
      ring ? `;box-shadow:0 0 0 3px ${ring},0 1px 3px rgba(0,0,0,.4)` : ""
    }"></div>`,
  });
}

function redraw() {
  if (!map || !layer) return;
  layer.clearLayers();
  markers.clear();
  ghosts.clear();
  lines.clear();

  const bounds = [];
  const region = state.regions.find((r) => r.id === state.regionId);

  console.log(region);
  if (region) {
    L.marker([region.office_lat, region.office_lon], {
      icon: officeIcon(),
      zIndexOffset: 2000, // офис всегда поверх точек заявок
    })
      .bindPopup(
        `<b>Офис региона «${region.title}»</b><br>${region.office_address ?? ""}<br>
         <span style="color:#6e6e76">отсюда инженеры начинают день</span>`,
      )
      .addTo(layer);
    bounds.push([region.office_lat, region.office_lon]);
  }

  for (const route of routes.value) {
    const color = colorOfEngineer.value[String(route.engineer_id)];
    const path = [];
    if (route.start) {
      path.push([route.start.lat, route.start.lon]);
      L.marker([route.start.lat, route.start.lon], {
        icon: homeIcon(),
        zIndexOffset: 1000,
      })
        .bindPopup(`<b>Дом (старт) инженера «${route.engineer_name}»</b>`)
        .addTo(layer);
    }

    for (const stop of route.stops) {
      const req = state.requests[String(stop.request_id)];
      if (!req) continue;
      path.push([req.lat, req.lon]);

      const urgent = req.priority != null && req.priority <= 10;
      const marker = L.marker([req.lat, req.lon], {
        icon: pin(
          color,
          stop.frozen ? 10 : urgent ? 15 : 12,
          stop.frozen ? "#b9b4a8" : urgent ? UNASSIGNED : null,
        ),
        opacity: stop.frozen ? 0.65 : 1,
        zIndexOffset: urgent ? 600 : 0,
      })
        .bindPopup(
          `<b>${req.id}</b><br>${req.district ?? ""}<br>окно ${hhmm(
            req.window_start,
          )}–${hhmm(req.window_end)}, приезд ${hhmm(stop.start_at)}<br>${
            route.engineer_name
          }, (${req.lat}, ${req.lon})`,
        )
        .on("click", () => select(req.id))
        .on("mouseover", () => hover(req.id))
        .on("mouseout", () => hover(null))
        .addTo(layer);

      markers.set(String(req.id), { marker, color });
      bounds.push([req.lat, req.lon]);
    }

    lines.set(
      String(route.engineer_id),
      L.polyline(route.geometry ?? path, { color, weight: 5, opacity: 0.75 })
        // Клик по линии = клик по имени инженера в списке.
        .on("click", (e) => {
          L.DomEvent.stop(e);
          focusEngineer(route.engineer_id);
        })
        .addTo(layer),
    );
  }

  for (const u of unassigned.value) {
    console.log("AAAAAA");
    console.log(u);
    const req = state.requests[String(u.request_id)];
    if (!req) continue;
    const ghost = L.circleMarker([req.lat, req.lon], {
      radius: 7,
      color: UNASSIGNED,
      weight: 2,
      fillColor: "#fff",
      fillOpacity: 1,
    })
      .bindPopup(`<b>${req.id} — не назначена</b><br>${u.reason_text ?? ""}`)
      .on("click", () => select(req.id))
      .on("mouseover", () => hover(req.id))
      .on("mouseout", () => hover(null))
      .addTo(layer);
    ghosts.set(String(req.id), ghost);
    bounds.push([req.lat, req.lon]);
  }

  if (bounds.length > 1) map.fitBounds(bounds, { padding: [20, 20] });
  restyle();
}

function restyle() {
  for (const [id, { marker, color }] of markers) {
    const dim = isDimmed(engineerOf(id));
    const sel = isSelected(id);
    const act = isActive(id);
    marker.setIcon(
      pin(color, sel ? 18 : act ? 14 : dim ? 8 : 12, sel ? INK : null),
    );
    marker.setOpacity(dim ? 0.35 : 1);
    marker.setZIndexOffset(sel ? 1000 : act ? 500 : 0);
  }
  // Не назначенные — отдельный реестр: у circleMarker нет setIcon.
  for (const [id, ghost] of ghosts) {
    const sel = isSelected(id);
    const act = isActive(id);
    ghost.setStyle({
      radius: sel ? 11 : act ? 9 : 7,
      weight: sel ? 3.5 : 2,
      color: sel ? INK : UNASSIGNED,
      fillColor: sel ? UNASSIGNED : "#fff",
    });
    if (sel) ghost.bringToFront();
  }
  for (const [engineerId, line] of lines) {
    const dim = isDimmed(engineerId);
    line.setStyle({ weight: dim ? 1.5 : 3, opacity: dim ? 0.2 : 0.75 });
  }
}
</script>

<template>
  <div ref="el" class="flex-1 min-h-[200px] border-b border-hair" />
</template>
