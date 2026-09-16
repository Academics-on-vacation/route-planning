<script setup>
import { onMounted, onBeforeUnmount, ref, nextTick } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

const el = ref(null)
let map = null
let layer = null
const markerByRequest = new Map()

onMounted(async () => {
  map = L.map(el.value, {
    zoomControl: true,
    preferCanvas: true,
  }).setView([55.68, 37.68], 10)

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 18,
  }).addTo(map)

  layer = L.layerGroup().addTo(map)

  draw()
})

onBeforeUnmount(() => {
  if (map) map.remove()
  map = null
  layer = null
})

function draw() {
  if (!map || !layer) return
  layer.clearLayers()
  markerByRequest.clear()
}
</script>

<template>
  <div class="wrap panel">
    <div ref="el" class="map" />
  </div>
</template>

<style scoped>
.wrap {
  position: relative;
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  overflow: hidden;
}
.map {
  flex: 1 1 auto;
  min-height: 260px;
  width: 100%;
}
</style>