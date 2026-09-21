<script setup>
import { computed, onBeforeUnmount, onMounted } from "vue";

import GanttPanel from "./components/GanttPanel.vue";
import ListPanel from "./components/ListPanel.vue";
import MapView from "./components/MapView.vue";
import {
  SKILLS,
  clearSelection,
  loadRegion,
  loadRegions,
  metrics,
  rebuild,
  state,
  stopIndex,
  unassignedIndex,
} from "./store.js";
import { hhmm, toMinutes } from "./time.js";

onMounted(loadRegions);

const onKey = (e) => {
  if (e.key === "Escape") clearSelection();
};
onMounted(() => window.addEventListener("keydown", onKey));
onBeforeUnmount(() => window.removeEventListener("keydown", onKey));

const request = computed(() =>
  state.selected == null
    ? null
    : (state.requests[String(state.selected)] ?? null),
);
const placement = computed(() =>
  state.selected == null
    ? null
    : (stopIndex.value[String(state.selected)] ?? null),
);
const reason = computed(() =>
  state.selected == null
    ? null
    : (unassignedIndex.value[String(state.selected)] ?? null),
);

const slack = computed(() => {
  if (!request.value || !placement.value) return null;
  return (
    toMinutes(request.value.window_end) - toMinutes(placement.value.stop.end_at)
  );
});

// const summary = computed(() => {
//   const m = metrics.value
//   if (!m) return []
//   return [
//     { k: 'закрыто', v: `${m.assigned}/${m.requests_total}`, lead: true },
//     { k: 'бригад', v: m.engineers_used },
//     { k: 'пробег', v: `${Math.round(m.total_distance_km)} км` },
//     { k: 'в пути', v: `${Math.round(m.total_travel_min / 60)} ч` },
//     { k: 'простой', v: `${Math.round(m.total_wait_min / 60)} ч` },
//     { k: 'окна', v: m.window_violations, bad: m.window_violations > 0 },
//   ]
// })
</script>

<template>
  <div class="h-full flex flex-col bg-canvas">
    <header class="flex-none bg-black text-white border-b-[3px] border-brand">
      <div class="flex flex-wrap items-center gap-x-4 gap-y-2 px-3 py-2.5">
        <div class="flex items-center gap-2.5">
          <!--          <span-->
          <!--            class="w-7 h-7 rounded-lg bg-brand grid place-items-center shrink-0"-->
          <!--            aria-hidden="true"-->
          <!--          >-->
          <!--            <svg viewBox="0 0 24 24" class="w-4.5 h-4.5">-->
          <!--              <path-->
          <!--                d="M4 17 L9 8 L13 14 L20 5"-->
          <!--                fill="none"-->
          <!--                stroke="#000"-->
          <!--                stroke-width="2.6"-->
          <!--                stroke-linecap="round"-->
          <!--                stroke-linejoin="round"-->
          <!--              />-->
          <!--            </svg>-->
          <!--          </span>-->
          <span class="leading-tight">
            <!--            <span class="block font-semibold tracking-tight">Планирование выездов</span>-->
            <!--            <span class="block text-[10.5px] text-white/45">билайн бизнес</span>-->
          </span>
        </div>

        <!-- Регионы кнопками, а не выпадашкой: их три, и переключают
             их постоянно — прятать под клик незачем. -->
        <nav class="flex items-center gap-1 p-0.5 rounded-lg bg-white/10">
          <button
            v-for="r in state.regions"
            :key="r.id"
            class="px-2.5 py-1 rounded-md text-[12px] transition-colors cursor-pointer"
            :class="
              r.id === state.regionId
                ? 'bg-brand text-black font-semibold'
                : 'text-white/60 hover:text-white hover:bg-white/10'
            "
            @click="loadRegion(r.id)"
          >
            {{ r.title }}
          </button>
        </nav>

        <dl class="hidden lg:flex items-center gap-4 ml-auto">
          <div v-for="s in summary" :key="s.k" class="leading-tight">
            <dt class="text-[9.5px] uppercase tracking-[0.1em] text-white/40">
              {{ s.k }}
            </dt>
            <dd
              class="num text-[14px]"
              :class="
                s.bad
                  ? 'text-crit'
                  : s.lead
                    ? 'text-brand font-semibold'
                    : 'text-white'
              "
            >
              {{ s.v }}
            </dd>
          </div>
        </dl>

        <!--        <button-->
        <!--          class="ml-auto lg:ml-0 px-3.5 py-1.5 rounded-lg bg-brand text-black font-semibold-->
        <!--                 text-[12.5px] hover:bg-brand-deep active:translate-y-px-->
        <!--                 disabled:opacity-40 disabled:cursor-default cursor-pointer-->
        <!--                 transition-all"-->
        <!--          :disabled="state.loading"-->
        <!--          @click="rebuild()"-->
        <!--        >-->
        <!--          {{ state.loading ? 'считаю…' : 'Пересчитать' }}-->
        <!--        </button>-->
      </div>

      <p
        v-if="state.error"
        class="m-0 px-3 py-2 bg-crit text-white text-[12px] flex items-center gap-2"
      >
        <b class="shrink-0">Ошибка</b>
        <span class="truncate">{{ state.error }}</span>
      </p>
    </header>

    <div class="flex-1 min-h-0 grid grid-cols-[336px_1fr] gap-2.5 p-2.5">
      <div class="panel flex flex-col min-h-0">
        <ListPanel class="flex-1 min-h-0" />

        <div
          v-if="request"
          class="flex-none max-h-[42%] overflow-auto px-3 py-2.5 border-t-2 border-brand bg-panel-2"
        >
          <div class="flex items-baseline gap-2">
            <b class="num text-[14px]">{{ request.id }}</b>
            <span class="text-[11.5px] text-muted truncate">
              {{ request.address ?? request.district ?? "" }}
            </span>
            <button
              class="ml-auto shrink-0 text-muted hover:text-ink text-[16px] leading-none
                     px-1 cursor-pointer"
              title="Снять выделение"
              @click="clearSelection()"
            >
              ×
            </button>
          </div>

          <dl class="grid grid-cols-2 gap-x-3 gap-y-1 mt-2 text-[11.5px]">
            <div>
              <dt class="text-muted">Окно</dt>
              <dd class="num">
                {{ hhmm(request.window_start) }}–{{ hhmm(request.window_end) }}
              </dd>
            </div>
            <div>
              <dt class="text-muted">Работа</dt>
              <dd class="num">{{ request.duration_min }} мин</dd>
            </div>
            <div class="col-span-2">
              <dt class="text-muted">Тип</dt>
              <dd>{{ SKILLS[request.skill] ?? request.skill }}</dd>
            </div>

            <template v-if="placement">
              <div>
                <dt class="text-muted">Приезд</dt>
                <dd class="num">{{ hhmm(placement.stop.arrive_at) }}</dd>
              </div>
              <div>
                <dt class="text-muted">Работа с</dt>
                <dd class="num">
                  {{ hhmm(placement.stop.start_at) }}–{{
                    hhmm(placement.stop.end_at)
                  }}
                </dd>
              </div>
              <div>
                <dt class="text-muted">Плечо</dt>
                <dd class="num">
                  {{ placement.stop.travel_km?.toFixed(1) }} км ·
                  {{ placement.stop.travel_min }} мин
                </dd>
              </div>
              <div>
                <dt class="text-muted">Запас до окна</dt>
                <dd
                  class="num font-semibold"
                  :class="slack != null && slack < 0 ? 'text-crit' : 'text-ink'"
                >
                  {{
                    slack == null
                      ? "—"
                      : slack < 0
                        ? `просрочка ${-slack} мин`
                        : `${slack} мин`
                  }}
                </dd>
              </div>
              <div class="col-span-2 pt-1 mt-0.5 border-t border-hair">
                <dt class="text-muted">Исполнитель</dt>
                <dd>
                  {{ placement.route.engineer_name }} · визит
                  {{ placement.seq }} из {{ placement.total }}
                </dd>
              </div>
            </template>

            <div v-else-if="reason" class="col-span-2">
              <dt class="font-semibold text-crit">Не назначена</dt>
              <dd class="text-muted">
                {{ reason.reason_text ?? reason.reason }}
              </dd>
            </div>
          </dl>
        </div>
      </div>

      <div class="panel flex flex-col min-h-0">
        <MapView />
        <GanttPanel class="flex-1 min-h-0" />
      </div>
    </div>
  </div>
</template>
