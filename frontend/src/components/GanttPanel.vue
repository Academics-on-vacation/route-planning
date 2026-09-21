<script setup>
import { computed } from "vue";

import {
  colorOfEngineer,
  focusEngineer,
  hover,
  isActive,
  isDimmed,
  isFocused,
  isSelected,
  routes,
  select,
  state,
} from "../store.js";
import { hhmm, toMinutes } from "../time.js";

const bounds = computed(() => {
  let from = Infinity;
  let to = -Infinity;
  for (const route of routes.value) {
    console.log("route", route);
    const start = toMinutes(route.start?.at);
    if (start != null) from = Math.min(from, start);
    const finish = toMinutes(route.finish_at);
    if (finish != null) to = Math.max(to, finish);
    for (const s of route.stops) {
      const a = toMinutes(s.arrive_at);
      if (a != null) from = Math.min(from, a - (s.travel_min ?? 0));
      const e = toMinutes(s.end_at);
      if (e != null) to = Math.max(to, e);
    }
    console.log(start, finish);
  }
  if (!Number.isFinite(from)) return { from: 540, to: 1320 };
  return { from: Math.floor(from / 60) * 60, to: Math.ceil(to / 60) * 60 };
});

const span = computed(() => Math.max(1, bounds.value.to - bounds.value.from));
const pct = (m) => ((m - bounds.value.from) / span.value) * 100;

const hours = computed(() => {
  const out = [];
  for (let m = bounds.value.from; m <= bounds.value.to; m += 60) out.push(m);
  return out;
});

function band(fromIso, toIso) {
  const a = toMinutes(fromIso);
  const b = toMinutes(toIso);
  if (a == null || b == null || b <= a) return null;
  return { left: `${pct(a)}%`, width: `${((b - a) / span.value) * 100}%` };
}

function travel(stop) {
  const arrive = toMinutes(stop.arrive_at);
  if (arrive == null || !stop.travel_min) return null;
  return {
    left: `${pct(arrive - stop.travel_min)}%`,
    width: `${(stop.travel_min / span.value) * 100}%`,
  };
}

const color = (engineerId) => colorOfEngineer.value[String(engineerId)]

const hatch = (engineerId) =>
  `repeating-linear-gradient(135deg, ${color(engineerId)} 0 2px, transparent 2px 5px)`
</script>

<template>
  <div class="flex flex-col min-h-0">
    <div
      class="flex items-stretch pr-8 sticky top-0 bg-panel-2 border-b border-hair-2"
    >
      <div
        class="w-[140px] flex-none flex items-center px-2 border-r border-hair text-[10.5px] font-semibold uppercase tracking-wider text-muted"
      >
        Расписание
      </div>
      <div class="relative flex-1 h-4">
        <small
          v-for="h in hours"
          :key="h"
          class="num absolute top-0 pl-[3px] text-[10px] text-muted"
          :style="{ left: `${pct(h)}%` }"
        >
          {{ hhmm(h) }}
        </small>
      </div>
    </div>

    <div class="flex-1 min-h-0 overflow-y-auto overscroll-contain">
      <div
        v-for="route in routes"
        :key="route.engineer_id"
        class="flex items-stretch pr-8 border-b border-hair last:border-b-0
               hover:bg-panel-2 transition-opacity"
        :class="isDimmed(route.engineer_id) ? 'opacity-35' : ''"
      >
        <div
          class="w-[140px] flex-none flex items-center gap-1.5 px-2 border-r border-hair
                 text-[11.5px] truncate cursor-pointer hover:bg-hair/40 transition-colors"
          :class="isFocused(route.engineer_id) ? 'bg-brand/15' : ''"
          @click="focusEngineer(route.engineer_id)"
        >
          <i
            class="w-1.5 h-1.5 rounded-full shrink-0"
            :style="{ background: color(route.engineer_id) }"
          />
          <span class="truncate">{{ route.engineer_name }}</span>
        </div>

        <div class="relative flex-1 h-[26px]">
          <span
            v-for="h in hours"
            :key="h"
            class="absolute inset-y-0 w-px bg-hair"
            :style="{ left: `${pct(h)}%` }"
          />

          <template v-for="stop in route.stops" :key="stop.request_id">
            <span
              v-if="travel(stop)"
              class="absolute top-1/2 -translate-y-1/2 h-0.5 rounded-full opacity-55"
              :style="{ ...travel(stop), background: color(route.engineer_id) }"
            />
            <span
              v-if="band(stop.arrive_at, stop.start_at)"
              class="absolute top-2.5 h-4 rounded-[2px] opacity-70"
              :style="{
                ...band(stop.arrive_at, stop.start_at),
                background: hatch(route.engineer_id),
              }"
              :title="`Простой ${stop.wait_min} мин`"
            />
            <span
              v-if="band(stop.start_at, stop.end_at)"
              class="absolute top-1.5 h-6 rounded-[4px] ring-2 ring-panel cursor-pointer"
              :class="
                isSelected(stop.request_id)
                  ? 'outline-2 outline-ink z-10'
                  : isActive(stop.request_id)
                    ? 'outline-2 outline-ink/40 z-10'
                    : ''
              "
              :style="{
                ...band(stop.start_at, stop.end_at),
                background: color(route.engineer_id),
              }"
              :title="`${stop.request_id}: ${hhmm(stop.start_at)}–${hhmm(stop.end_at)}`"
              @click="select(stop.request_id)"
              @mouseenter="hover(stop.request_id)"
              @mouseleave="hover(null)"
            />
          </template>
        </div>
      </div>
    </div>
  </div>
</template>
