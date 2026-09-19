<script setup>

import { watch } from 'vue'

import {
  routes,
  state,
  colorOfEngineer,
  unassigned,
} from '../store.js'
import { hhmm } from '../time.js'

const nodes = new Map()
const registerNode = (id, el) => {
  if (el) nodes.set(String(id), el)
  else nodes.delete(String(id))
}

watch(
  () => state.selected,
  (id) => {
    if (id == null) return
    nodes.get(String(id))?.scrollIntoView({ block: 'nearest' })
  },
  { flush: 'post' },
)

const districtOf = (id) => state.requests[String(id)]?.district ?? ''
</script>

<template>
  <div class="col">
    <div class="scroll">
      <section
        v-for="route in routes"
        :key="route.engineer_id"
        :style="{ opacity:  1 }"
      >
        <h3>
          {{ route.engineer_name }}
<!--          <button @click="focusEngineer(route.engineer_id)">-->
<!--            {{ state.focused === route.engineer_id ? 'снять' : 'только он' }}-->
<!--          </button>-->
          <small>
            {{ route.stops.length }} зв, {{ route.distance_km?.toFixed(0) }} км,
            до {{ hhmm(route.finish_at) }}
          </small>
        </h3>

        <ol>
          <li
            v-for="stop in route.stops"
            :key="stop.request_id"
            :ref="(el) => registerNode(stop.request_id, el)"
          >
            <component :is="'span'">
              {{ hhmm(stop.start_at) }} — {{ stop.request_id }}
              {{ districtOf(stop.request_id) }}
              <template v-if="stop.wait_min > 15">(простой {{ stop.wait_min }} мин)</template>
            </component>
          </li>
        </ol>
      </section>

      <section v-if="unassigned.length">
        <h3>Не назначено: {{ unassigned.length }}</h3>
        <ul>
          <li
            v-for="u in unassigned"
            :key="u.request_id"
            :ref="(el) => registerNode(u.request_id, el)"
          >
            <component :is="'span'">
              {{ u.request_id }} — {{ u.reason_text ?? u.reason }}
            </component>
          </li>
        </ul>
      </section>
    </div>
  </div>
</template>
