<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";

import EmergencyDialog from "../components/EmergencyDialog.vue";
import GanttPanel from "../components/GanttPanel.vue";
import ListPanel from "../components/ListPanel.vue";
import MapView from "../components/MapView.vue";
import RouteLoader from "../components/RouteLoader.vue";
import TransportChip from "../components/TransportChip.vue";
import {
  SKILLS,
  clearSelection,
  loadRegion,
  replanInfo,
  state,
  stopIndex,
  transportOf,
  unassignedIndex,
} from "../store.js";
import { hhmm, toMinutes } from "../time.js";

const props = defineProps({ regionId: { type: Number, required: true } });

watch(() => props.regionId, loadRegion, { immediate: true });

const emergencyOpen = ref(false);

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
</script>

<template>
  <div class="relative flex-1 min-h-0 grid grid-cols-[336px_1fr] gap-2.5 p-2.5">
    <RouteLoader />

    <EmergencyDialog :open="emergencyOpen" @close="emergencyOpen = false" />

    <div
      class="absolute top-4 right-4 z-[1100] flex flex-col items-end gap-1.5"
    >
      <button
        class="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-crit text-white text-[12.5px] font-semibold shadow cursor-pointer hover:brightness-110 transition print:hidden"
        @click="emergencyOpen = true"
      >
        <span
          class="w-4 h-4 rounded-full bg-white/25 grid place-items-center text-[11px]"
          aria-hidden="true"
        >
          !
        </span>
        Авария
      </button>

      <div
        v-if="replanInfo"
        class="panel px-2.5 py-2 w-[232px] text-[11.5px] leading-snug"
      >
        <div class="font-semibold text-[12px]">
          Пересчёт с {{ replanInfo.frozen_at?.slice(11, 16) }}
        </div>
        <dl class="num mt-1 grid grid-cols-[1fr_auto] gap-x-2">
          <dt class="text-muted">заморожено визитов</dt>
          <dd>{{ replanInfo.frozen_stops }}</dd>
          <dt class="text-muted">пересчитано</dt>
          <dd>{{ replanInfo.replanned_stops }}</dd>
          <dt class="text-muted">сменили бригаду</dt>
          <dd :class="replanInfo.moved > 0 ? 'text-serious' : ''">
            {{ replanInfo.moved }}
          </dd>
        </dl>
      </div>
    </div>

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
            class="ml-auto shrink-0 text-muted hover:text-ink text-[16px] leading-none px-1 cursor-pointer"
            title="Снять выделение (Esc)"
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
              <dd class="flex items-center gap-1.5">
                <span>
                  {{ placement.route.engineer_name }} · визит
                  {{ placement.seq }} из {{ placement.total }}
                </span>
                <TransportChip
                  :kind="transportOf(placement.route.engineer_id)"
                />
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
</template>
