<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

import {
  colorOfEngineer,
  plan,
  routes,
  state,
  unassigned,
  engineerOf,
} from '../store.js'
import { hhmm } from '../time.js'

const el = ref(null)

let map = null
let layer = null
const markers = new Map() // requestId -> { marker, color }
const ghosts = new Map() // requestId -> circleMarker не назначенной
const lines = new Map() // engineerId -> polyline

const UNASSIGNED = '#99271f'

onMounted(() => {
  map = L.map(el.value, { preferCanvas: true }).setView([55.7, 37.7], 10)
  // L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map)
  layer = L.layerGroup().addTo(map)

  redraw()
})

onBeforeUnmount(() => {
  map?.remove()
  map = null
})

watch([plan, () => state.regionId], redraw)
watch(() => [state.selected, state.hovered, state.focused], restyle)

function officeIcon() {
  return L.divIcon({
    className: '',
    iconSize: [14, 14],
    iconAnchor: [7, 7],
    html: '<div class="map-office"></div>',
  })
}

function pin(color, size, ring) {
  return L.divIcon({
    className: '',
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    html: `<div class="map-pin" style="width:${size}px;height:${size}px;background:${color}${
      ring ? `;box-shadow:0 0 0 3px ${ring}` : ''
    }"></div>`,
  })
}

function redraw() {
  if (!map || !layer) return
  layer.clearLayers()
  markers.clear()
  ghosts.clear()
  lines.clear()

  const bounds = []
  const region = state.regions.find((r) => r.id === state.regionId)

  console.log(region);
  if (region) {
    L.marker([region.office_lat, region.office_lon], { icon: officeIcon() })
      .bindPopup(`Офис: ${region.office_address ?? ''}`)
      .addTo(layer)
    bounds.push([region.office_lat, region.office_lon])
  }

  for (const route of routes.value) {
    const color = colorOfEngineer.value[String(route.engineer_id)]
    const path = []
    if (route.start) path.push([route.start.lat, route.start.lon])

    for (const stop of route.stops) {
      const req = state.requests[String(stop.request_id)]
      if (!req) continue
      path.push([req.lat, req.lon])

      const marker = L.marker([req.lat, req.lon], { icon: pin(color, 12) })
        // .bindPopup(
        //   `${req.id}<br>${req.district ?? ''}<br>окно ${hhmm(req.window_start)}–${hhmm(
        //     req.window_end,
        //   )}, приезд ${hhmm(stop.start_at)}<br>${route.engineer_name}`,
        // )
        // .on('click', () => select(req.id))
        // .on('mouseover', () => hover(req.id))
        // .on('mouseout', () => hover(null))
        .addTo(layer)

      markers.set(String(req.id), { marker, color })
      bounds.push([req.lat, req.lon])
    }

    lines.set(
      String(route.engineer_id),
      L.polyline(route.geometry ?? path, { color, weight: 3, opacity: 0.75 }).addTo(layer),
    )
  }

  for (const u of unassigned.value) {
    console.log('AAAAAA')
    console.log(u)
    const req = state.requests[String(u.request_id)]
    if (!req) continue
    const ghost = L.circleMarker([req.lat, req.lon], {
      radius: 7,
      color: UNASSIGNED,
      weight: 2,
      fillColor: '#fff',
      fillOpacity: 1,
    })
      .bindPopup(`${req.id} — не назначена<br>${u.reason_text ?? ''}`)
      // .on('click', () => select(req.id))
      .addTo(layer)
    ghosts.set(String(req.id), ghost)
    bounds.push([req.lat, req.lon])
  }

  if (bounds.length > 1) map.fitBounds(bounds, { padding: [20, 20] })
  restyle()
}

function restyle() {
  for (const [id, { marker, color }] of markers) {
    const dim = false
    const sel = false
    marker.setIcon(pin(color, sel ? 18 : false ? 14 : dim ? 8 : 12, sel ? '#000' : null))
    marker.setOpacity(dim ? 0.35 : 1)
    marker.setZIndexOffset(sel ? 1000 : 0)
  }
  // Не назначенные — отдельный реестр: у circleMarker нет setIcon.
  for (const [id, ghost] of ghosts) {
    const sel = false
    ghost.setStyle({
      radius: sel ? 11 : 7,
      weight: sel ? 3.5 : 2,
      fillColor: sel ? UNASSIGNED : '#fff',
    })
  }
  for (const [engineerId, line] of lines) {
    const dim = false
    line.setStyle({ weight: dim ? 1.5 : 3, opacity: dim ? 0.2 : 0.75 })
  }
}
</script>

<template>
  <div ref="el" class="flex-1 min-h-[200px] border-b border-hair" />
</template>
