<script setup>
import { watch } from "vue";
import { RouterLink } from "vue-router";

import TransportChip from "./TransportChip.vue";
import {
  routes,
  state,
  colorOfEngineer,
  focusEngineer,
  hover,
  isDimmed,
  isActive,
  isFocused,
  isHovered,
  isSelected,
  select,
  transportOf,
  unassigned,
} from "../store.js";
import { hhmm } from "../time.js";

const nodes = new Map();
const registerNode = (id, el) => {
  if (el) nodes.set(String(id), el);
  else nodes.delete(String(id));
};

watch(
  () => state.selected,
  (id) => {
    if (id == null) return;
    nodes.get(String(id))?.scrollIntoView({ block: "nearest" });
  },
  { flush: "post" },
);

const districtOf = (id) => state.requests[String(id)]?.district ?? "";
const skillOf = (id) => state.requests[String(id)]?.skill ?? "";
</script>

<template>
  <div class="flex flex-col min-h-0">
    <div class="flex-1 min-h-0 overflow-y-auto overscroll-contain">
      <section
        v-for="route in routes"
        :key="route.engineer_id"
        class="transition-opacity"
        :class="isDimmed(route.engineer_id) ? 'opacity-40' : ''"
      >
        <h3
          class="sticky top-0 z-1 flex items-center gap-1.5 px-2.5 py-1.5 bg-panel-2 border-y border-hair text-[12.5px] font-semibold cursor-pointer hover:bg-hair/50 transition-colors"
          :class="isFocused(route.engineer_id) ? 'bg-brand/15' : ''"
          @click="focusEngineer(route.engineer_id)"
        >
          <i
            class="w-2.5 h-2.5 rounded-full shrink-0"
            :style="{ background: colorOfEngineer[String(route.engineer_id)] }"
          />
          <span class="min-w-0 truncate">
            {{ route.engineer_name }}
            <small class="num block text-[10.5px] font-normal text-muted">
              {{ route.stops.length }} заявок,
              {{ route.distance_km?.toFixed(0) }} км, до
              {{ hhmm(route.finish_at) }}
            </small>
          </span>
          <!-- Транспорт справа, а не в строке с километрами: иначе
               при узкой панели строка переносится и заголовок прыгает. -->
          <TransportChip
            class="ml-auto"
            :kind="transportOf(route.engineer_id)"
          />

          <RouterLink
            :to="{
              name: 'engineer',
              params: {
                regionId: state.regionId,
                engineerId: route.engineer_id,
              },
            }"
            class="shrink-0 -my-1 p-1 rounded text-muted hover:text-ink hover:bg-hair/70 transition-colors"
            title="Памятка инженера на день"
            @click.stop
          >
            <svg
              viewBox="0 0 24 24"
              class="w-4 h-4"
              fill="none"
              stroke="currentColor"
              stroke-width="1.8"
              stroke-linecap="round"
              stroke-linejoin="round"
              aria-hidden="true"
            >
              <rect x="5" y="3" width="14" height="18" rx="2" />
              <path d="M9 8h6M9 12h6M9 16h3" />
            </svg>
          </RouterLink>
        </h3>

        <ol
          class="list-decimal pl-8 pt-0.5 pb-1.5 marker:text-hair-2 marker:text-[11px]"
        >
          <li
            v-for="stop in route.stops"
            :key="stop.request_id"
            :ref="(el) => registerNode(stop.request_id, el)"
            class="py-0.5 pr-2.5 -ml-2 pl-2 border-l-2 cursor-pointer transition-colors"
            :class="
              isSelected(stop.request_id)
                ? 'border-ink bg-brand/25'
                : isHovered(stop.request_id)
                  ? 'border-hair-2 bg-panel-2'
                  : 'border-transparent hover:bg-panel-2'
            "
            @click="select(stop.request_id)"
            @mouseenter="hover(stop.request_id)"
            @mouseleave="hover(null)"
          >
            <span class="num text-[12px] text-muted mr-1.5">
              {{ hhmm(stop.start_at) }}
            </span>
            <span
              :class="
                skillOf(stop.request_id) === 'emergency'
                  ? 'num text-[12.5px] font-bold text-yellow-800'
                  : 'num text-[12.5px] font-medium'
              "
              >{{ stop.request_id }}</span
            >
            <span class="ml-1 text-muted">{{
              districtOf(stop.request_id)
            }}</span>
            <!-- Простой — единственное, что подсвечено в строке: это
                 то, что диспетчер ищет глазами. -->
            <span
              v-if="stop.wait_min > 15"
              class="num text-[11px] text-serious"
            >
              · простой {{ stop.wait_min }} мин
            </span>
          </li>
        </ol>
      </section>

      <section v-if="unassigned.length">
        <h3
          class="sticky top-0 z-1 flex items-center gap-2 px-3 py-2 bg-crit/8 border-y border-crit/25"
        >
          <span
            class="w-4 h-4 rounded-full bg-crit text-white text-[11px] font-bold grid place-items-center shrink-0"
            aria-hidden="true"
          >
            !
          </span>
          <span class="text-[13px] font-semibold text-crit">
            Не назначено: {{ unassigned.length }}
          </span>
        </h3>
        <ul class="py-1">
          <li
            v-for="u in unassigned"
            :key="u.request_id"
            :ref="(el) => registerNode(u.request_id, el)"
            class="px-3 py-1.5 border-l-2 cursor-pointer transition-colors"
            :class="
              isSelected(u.request_id)
                ? 'border-crit bg-crit/15'
                : 'border-transparent hover:border-crit hover:bg-crit/5'
            "
            @click="select(u.request_id)"
            @mouseenter="hover(u.request_id)"
            @mouseleave="hover(null)"
          >
            <span class="num text-[12.5px] font-medium">{{
              u.request_id
            }}</span>
            <span class="block text-[11.5px] text-crit">
              {{ u.reason_text ?? u.reason }}
            </span>
          </li>
        </ul>
      </section>
    </div>
  </div>
</template>
