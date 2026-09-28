<script setup>
import { computed } from "vue";
import { RouterLink, RouterView, useRoute } from "vue-router";

import { metrics, state } from "./store.js";
import beelineLogo from "./assets/beeline-logo.svg";

// Справочник регионов грузит guard роутера — до того, как покажется
// хоть один экран. Здесь только рисуем.

const summary = computed(() => {
  const m = metrics.value;
  if (!m) return [];
  return [
    { k: "закрыто", v: `${m.assigned}/${m.requests_total}`, lead: true },
    { k: "бригад", v: m.engineers_used },
    { k: "пробег", v: `${Math.round(m.total_distance_km)} км` },
    { k: "в пути", v: `${Math.round(m.total_travel_min / 60)} ч` },
  ];
});
</script>

<template>
  <div class="h-full flex flex-col">
    <header class="flex-none bg-black text-white border-b-[3px] border-brand">
      <div class="flex flex-wrap items-center gap-x-4 gap-y-2 px-3 py-2.5">
        <div class="flex items-center gap-2.5">
          <img
            :src="beelineLogo"
            alt="билайн"
            class="h-6 w-auto rounded-[3px] shrink-0"
          />
          <span class="leading-tight">
            <span class="block font-medium tracking-tight"
              >Планирование выездов</span
            >
          </span>
        </div>

        <nav class="flex items-center gap-1 p-0.5 rounded-lg bg-white/10">
          <RouterLink
            v-for="r in state.regions"
            :key="r.id"
            :to="{ name: 'region', params: { regionId: r.id } }"
            class="px-2.5 py-1 rounded-md text-[12px] transition-colors text-white/60 hover:text-white hover:bg-white/10"
            exact-active-class="!bg-brand !text-black font-semibold"
            :class="r.id === state.pendingRegionId ? 'animate-pulse' : ''"
            :aria-busy="r.id === state.pendingRegionId ? 'true' : undefined"
          >
            {{ r.title }}
          </RouterLink>
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
      </div>

      <div v-if="state.loading" class="bar" />

      <p
        v-if="state.error"
        class="m-0 px-3 py-2 bg-crit text-white text-[12px] flex items-center gap-2"
      >
        <b class="shrink-0">Ошибка</b>
        <span class="truncate">{{ state.error }}</span>
      </p>
    </header>

    <RouterView />
  </div>
</template>
