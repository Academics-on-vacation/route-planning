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
  <div class="flex flex-col min-h-0">
    <div class="flex-1 min-h-0 overflow-y-auto overscroll-contain">
      <section v-for="route in routes" :key="route.engineer_id">
        <h3
          class="sticky top-0 z-1 px-2.5 py-1.5 bg-panel-2
                 border-y border-hair text-[12.5px] font-semibold"
        >
          <i
            class="inline-block w-2.5 h-2.5 rounded-full mr-1.5"
            :style="{ background: colorOfEngineer[String(route.engineer_id)] }"
          />
          {{ route.engineer_name }}
          <small class="num block text-[10.5px] font-normal text-muted">
            {{ route.stops.length }} зв, {{ route.distance_km?.toFixed(0) }} км,
            до {{ hhmm(route.finish_at) }}
          </small>
        </h3>

        <ol class="list-decimal pl-8 pt-0.5 pb-1.5 marker:text-hair-2 marker:text-[11px]">
          <li
            v-for="stop in route.stops"
            :key="stop.request_id"
            :ref="(el) => registerNode(stop.request_id, el)"
            class="py-0.5 pr-2.5 hover:bg-panel-2"
          >
            {{ hhmm(stop.start_at) }} — {{ stop.request_id }}
            {{ districtOf(stop.request_id) }}
            <template v-if="stop.wait_min > 15">(простой {{ stop.wait_min }} мин)</template>
          </li>
        </ol>
      </section>

      <section v-if="unassigned.length">
        <h3
          class="sticky top-0 z-1 px-2.5 py-1.5 bg-panel-2 border-y border-hair
                 text-[12.5px] font-semibold text-crit"
        >
          Не назначено: {{ unassigned.length }}
        </h3>
        <ul class="list-disc pl-8 pt-0.5 pb-1.5 marker:text-crit">
          <li
            v-for="u in unassigned"
            :key="u.request_id"
            :ref="(el) => registerNode(u.request_id, el)"
            class="py-0.5 pr-2.5 text-crit hover:bg-panel-2"
          >
            {{ u.request_id }} — {{ u.reason_text ?? u.reason }}
          </li>
        </ul>
      </section>
    </div>
  </div>
</template>
