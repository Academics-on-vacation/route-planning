<script setup>

import { computed } from 'vue'

import {
  colorOfEngineer,
  routes,
  state,
} from '../store.js'
import { hhmm, toMinutes } from '../time.js'

const bounds = computed(() => {
  let from = Infinity
  let to = -Infinity
  for (const route of routes.value) {
    console.log('route', route)
    const start = toMinutes(route.start?.at)
    if (start != null) from = Math.min(from, start)
    const finish = toMinutes(route.finish_at)
    if (finish != null) to = Math.max(to, finish)
    for (const s of route.stops) {
      const a = toMinutes(s.arrive_at)
      if (a != null) from = Math.min(from, a - (s.travel_min ?? 0))
      const e = toMinutes(s.end_at)
      if (e != null) to = Math.max(to, e)
    }
    console.log(start, finish)
  }
  if (!Number.isFinite(from)) return { from: 540, to: 1320 }
  return { from: Math.floor(from / 60) * 60, to: Math.ceil(to / 60) * 60 }
})

const span = computed(() => Math.max(1, bounds.value.to - bounds.value.from))
const pct = (m) => ((m - bounds.value.from) / span.value) * 100

const hours = computed(() => {
  const out = []
  for (let m = bounds.value.from; m <= bounds.value.to; m += 60) out.push(m)
  return out
})

function band(fromIso, toIso) {
  const a = toMinutes(fromIso)
  const b = toMinutes(toIso)
  if (a == null || b == null || b <= a) return null
  return { left: `${pct(a)}%`, width: `${((b - a) / span.value) * 100}%` }
}

function travel(stop) {
  const arrive = toMinutes(stop.arrive_at)
  if (arrive == null || !stop.travel_min) return null
  return {
    left: `${pct(arrive - stop.travel_min)}%`,
    width: `${(stop.travel_min / span.value) * 100}%`,
  }
}

const color = (engineerId) => colorOfEngineer.value[String(engineerId)]
</script>

<template>
  <div class="col">
    <div class="row">
      <div class="row-name">Расписание</div>
      <div class="track" style="height: 16px">
        <small v-for="h in hours" :key="h" class="tick" :style="{ left: `${pct(h)}%`, width: 'auto' }">
          {{ hhmm(h) }}
        </small>
      </div>
    </div>

    <div class="scroll">
      <div
        v-for="route in routes"
        :key="route.engineer_id"
        class="row"
        :style="{ opacity:  1 }"
      >
        <div class="row-name">
          <small>
<!--            <a href="#" @click.prevent="focusEngineer(route.engineer_id)">-->
              {{ route.engineer_name }}
<!--            </a>-->
          </small>
        </div>

        <div class="track">
          <!-- часовая сетка -->
          <span
            v-for="h in hours"
            :key="h"
            class="tick"
            :style="{ left: `${pct(h)}%`, background: '#ddd' }"
          />

          <template v-for="stop in route.stops" :key="stop.request_id">
            <span
              v-if="travel(stop)"
              class="travel"
              :style="{ ...travel(stop), background: color(route.engineer_id) }"
            />
            <span
              v-if="band(stop.arrive_at, stop.start_at)"
              class="wait"
              :style="{
                ...band(stop.arrive_at, stop.start_at),
                background: color(route.engineer_id),
                opacity: 0.25,
              }"
              :title="`Простой ${stop.wait_min} мин`"
            />
            <span
              v-if="band(stop.start_at, stop.end_at)"
              class="bar"
              :style="{
                ...band(stop.start_at, stop.end_at),
                background: color(route.engineer_id),
                outline: false
                  ? '2px solid #000'
                  : false
                    ? '1px solid #000'
                    : 'none',
              }"
              :title="`${stop.request_id}: ${hhmm(stop.start_at)}–${hhmm(stop.end_at)}`"
            />
          </template>
        </div>
      </div>
    </div>
  </div>
</template>
