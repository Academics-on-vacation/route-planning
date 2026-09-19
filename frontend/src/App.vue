<script setup>
import { computed, onMounted } from 'vue'

import GanttPanel from './components/GanttPanel.vue'
import ListPanel from './components/ListPanel.vue'
import MapView from './components/MapView.vue'
import {
  SKILLS,
  loadRegion,
  loadRegions,
  metrics,
  rebuild,
  state,
  stopIndex,
  unassignedIndex,
} from './store.js'
import { hhmm, toMinutes } from './time.js'

onMounted(loadRegions)

const request = computed(() =>
  state.selected == null ? null : state.requests[String(state.selected)] ?? null,
)
const placement = computed(() =>
  state.selected == null ? null : stopIndex.value[String(state.selected)] ?? null,
)
const reason = computed(() =>
  state.selected == null ? null : unassignedIndex.value[String(state.selected)] ?? null,
)

const slack = computed(() => {
  if (!request.value || !placement.value) return null
  return toMinutes(request.value.window_end) - toMinutes(placement.value.stop.end_at)
})

const onRegion = (e) => loadRegion(Number(e.target.value))
</script>

<template>
  <div class="app">
    <header>
      <select :value="state.regionId" @change="onRegion">
        <option v-for="r in state.regions" :key="r.id" :value="r.id">
          {{ r.title }}
        </option>
      </select>

      <button :disabled="state.loading" @click="rebuild()">
        {{ state.loading ? 'считаю…' : 'пересчитать' }}
      </button>

      <small v-if="metrics">
        заявок {{ metrics.assigned }}/{{ metrics.requests_total }} ·
        исполнителей {{ metrics.engineers_used }} ·
        пробег {{ Math.round(metrics.total_distance_km) }} км ·
        в пути {{ metrics.total_travel_min }} мин ·
        простой {{ metrics.total_wait_min }} мин ·
        нарушений окон {{ metrics.window_violations }}
      </small>

      <p v-if="state.error"><b>Ошибка:</b> {{ state.error }}</p>
    </header>

    <div class="main">
      <div class="col">
        <ListPanel style="flex: 1; min-height: 0" />

        <div v-if="request" class="detail">
          <hr />
          <b>{{ request.id }}</b>
          {{ request.address ?? request.district ?? '' }}<br />
          <small>
            окно {{ hhmm(request.window_start) }}–{{ hhmm(request.window_end) }},
            работа {{ request.duration_min }} мин,
            {{ SKILLS[request.skill] ?? request.skill }}
          </small>
          <div v-if="placement">
            <small>
              приезд {{ hhmm(placement.stop.arrive_at) }},
              работа {{ hhmm(placement.stop.start_at) }}–{{ hhmm(placement.stop.end_at) }},
              плечо {{ placement.stop.travel_km?.toFixed(1) }} км /
              {{ placement.stop.travel_min }} мин<br />
              {{ placement.route.engineer_name }},
              визит {{ placement.seq }} из {{ placement.total }},
              запас до окна
              <b>{{ slack == null ? '—' : slack < 0 ? `просрочка ${-slack} мин` : `${slack} мин` }}</b>
            </small>
          </div>
          <div v-else-if="reason">
            <small>не назначена: {{ reason.reason_text ?? reason.reason }}</small>
          </div>
        </div>
      </div>

      <div class="col">
        <MapView />
        <GanttPanel style="flex: 1; min-height: 0" />
      </div>
    </div>
  </div>
</template>
