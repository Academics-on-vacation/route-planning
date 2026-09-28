<script setup>
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from "vue";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { RouterLink } from "vue-router";

import RouteLoader from "../components/RouteLoader.vue";
import TransportChip from "../components/TransportChip.vue";
import {
  SKILLS,
  colorOfEngineer,
  loadRegion,
  plan,
  routes,
  state,
  transportOf,
} from "../store.js";
import { hhmm, toMinutes } from "../time.js";

const props = defineProps({
  regionId: { type: Number, required: true },
  engineerId: { type: Number, required: true },
});

watch(
  () => props.regionId,
  (id) => {
    if (state.regionId !== id || !plan.value) loadRegion(id);
  },
  { immediate: true },
);

const route = computed(
  () =>
    routes.value.find(
      (r) => String(r.engineer_id) === String(props.engineerId),
    ) ?? null,
);
const engineer = computed(
  () => state.engineers[String(props.engineerId)] ?? null,
);
const color = computed(
  () => colorOfEngineer.value[String(props.engineerId)] ?? "#141414",
);

const dayLabel = computed(() => {
  const iso = plan.value?.work_date;
  if (!iso) return "";
  return new Date(`${iso}T00:00:00`).toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "long",
    weekday: "long",
  });
});

const visits = computed(() =>
  (route.value?.stops ?? []).map((stop, i) => {
    const req = state.requests[String(stop.request_id)] ?? null;
    const slack = req
      ? toMinutes(req.window_end) - toMinutes(stop.end_at)
      : null;
    return {
      stop,
      req,
      seq: stop.seq ?? i + 1,
      slack,
      urgent: req?.priority != null && req.priority <= 10,
    };
  }),
);

const summary = computed(() => {
  const r = route.value;
  if (!r) return [];
  return [
    { k: "визитов", v: r.stops.length, lead: true },
    { k: "пробег", v: `${Math.round(r.distance_km)} км` },
    { k: "в пути", v: `${Math.round(r.travel_min / 60)} ч` },
    { k: "простой", v: `${r.wait_min} мин` },
    { k: "конец", v: hhmm(r.finish_at) },
  ];
});

const RTT = { car: "auto", transit: "mt", bike: "bc", foot: "pd" };

const navUrl = (req) =>
  `https://yandex.ru/maps/?rtext=~${req.lat},${req.lon}&rtt=${
    RTT[transportOf(props.engineerId)] ?? "auto"
  }`;

const gisUrl = (req) =>
  `https://2gis.ru/routeSearch/rsType/${
    transportOf(props.engineerId) === "car" ? "car" : "pedestrian"
  }/to/${req.lon},${req.lat}`;

const printPage = () => window.print();

const el = ref(null);
let map = null;
let layer = null;

const stepIcon = (n, bg) =>
  L.divIcon({
    className: "",
    iconSize: [26, 26],
    iconAnchor: [13, 13],
    html:
      `<div style="background:${bg};width:26px;height:26px;border-radius:50%;` +
      `border:2px solid #fff;box-shadow:0 1px 3px rgba(0,0,0,.35);color:#fff;` +
      `font:600 12px/22px ui-monospace,monospace;text-align:center">${n}</div>`,
  });

const startIcon = () =>
  L.divIcon({
    className: "",
    iconSize: [22, 22],
    iconAnchor: [11, 11],
    html:
      `<div style="background:#ffc800;width:22px;height:22px;border-radius:6px;` +
      `border:2px solid #141414;box-shadow:0 1px 3px rgba(0,0,0,.35)"></div>`,
  });

function draw() {
  if (!map) return;
  layer.clearLayers();
  const r = route.value;
  if (!r) return;

  const path = [[r.start.lat, r.start.lon]];
  L.marker([r.start.lat, r.start.lon], {
    icon: startIcon(),
    title: "Начало смены",
  }).addTo(layer);

  for (const { stop, req, seq } of visits.value) {
    if (!req) continue;
    path.push([req.lat, req.lon]);
    L.marker([req.lat, req.lon], {
      icon: stepIcon(seq, color.value),
      zIndexOffset: 1000 - seq,
    })
      .bindPopup(
        `<b>${seq}. ${hhmm(stop.start_at)}</b><br>${req.address ?? ""}<br>` +
          `окно ${hhmm(req.window_start)}–${hhmm(req.window_end)}`,
      )
      .addTo(layer);
  }

  L.polyline(r.geometry ?? path, {
    color: color.value,
    weight: 4,
    opacity: 0.8,
  }).addTo(layer);

  if (path.length > 1) map.fitBounds(L.latLngBounds(path).pad(0.18));
  else map.setView(path[0], 13);
}

onMounted(() => {
  map = L.map(el.value, {
    preferCanvas: true,
    scrollWheelZoom: false,
  }).setView([55.7, 37.7], 10);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png").addTo(map);
  layer = L.layerGroup().addTo(map);
  draw();
});

onBeforeUnmount(() => {
  map?.remove();
  map = null;
});

watch([plan, () => props.engineerId], async () => {
  await nextTick();
  map?.invalidateSize();
  draw();
});
</script>

<template>
  <div class="relative flex-1 min-h-0 overflow-y-auto">
    <RouteLoader />

    <div class="max-w-[760px] mx-auto p-2.5 flex flex-col gap-2.5">
      <!-- Шапка -->
      <div class="panel px-3 py-2.5">
        <div class="flex items-center gap-2">
          <h1 class="">
            {{ route?.engineer_name ?? engineer?.name ?? "Инженер" }}
          </h1>
          <TransportChip :kind="transportOf(engineerId)" />
          <RouterLink
            :to="{ name: 'region', params: { regionId } }"
            class="ml-auto shrink-0 text-[12px] text-muted hover:text-ink underline underline-offset-2 print:hidden"
          >
            к плану
          </RouterLink>
        </div>

        <p class="">
          {{ dayLabel }}
          <template v-if="engineer">
            · смена {{ hhmm(engineer.shift_start) }}–{{
              hhmm(engineer.shift_end)
            }}
          </template>
        </p>

        <dl v-if="summary.length" class="flex flex-wrap gap-x-5 gap-y-1 mt-2">
          <div v-for="s in summary" :key="s.k">
            <dt class="uppercase">
              {{ s.k }}
            </dt>
            <dd class="" :class="s.lead ? 'font-semibold' : ''">
              {{ s.v }}
            </dd>
          </div>
        </dl>
      </div>

      <div v-show="route" class="panel overflow-hidden">
        <div ref="el" class="h-[38vh] min-h-[220px] w-full" />
        <p
          v-if="route"
          class="px-3 py-1.5 text-[11px] text-muted border-t border-hair"
        >
          Выезд {{ hhmm(route.start.at) }} из офиса дальше по номерам.
        </p>
      </div>

      <!-- Визиты -->
      <div v-if="route" class="flex flex-col gap-1.5">
        <template v-for="(v, i) in visits" :key="v.stop.request_id">
          <p class="flex items-center">
            <span class="" />
            <template v-if="v.stop.travel_min === 0 && !v.stop.travel_km">
              без переезда, сразу следующая
            </template>
            <template v-else>
              {{ i === 0 ? "выезд" : "переезд" }} {{ v.stop.travel_min }} мин ·
              {{ v.stop.travel_km?.toFixed(1) }} км
            </template>
            <span v-if="v.stop.wait_min > 0" class="text-serious">
              · ждать {{ v.stop.wait_min }} мин
            </span>
          </p>

          <article class="panel p-3" :style="{ borderLeftColor: color }">
            <div class="flex items-baseline gap-2">
              <b class="">
                {{ hhmm(v.stop.start_at) }}
              </b>
              <span class=""> до {{ hhmm(v.stop.end_at) }} </span>
              <span v-if="v.urgent" class=""> авария </span>
              <span class="" :class="v.urgent ? '' : 'ml-auto'">
                {{ v.seq }}/{{ visits.length }}
              </span>
            </div>

            <p class="">
              {{ v.req?.address ?? "адрес не указан" }}
            </p>
            <p v-if="v.req?.district" class="">
              {{ v.req.district }}
            </p>

            <dl class="">
              <div>
                <dt class="">Окно заявки</dt>
                <dd class="num">
                  {{ hhmm(v.req?.window_start) }}–{{ hhmm(v.req?.window_end) }}
                </dd>
              </div>
              <div>
                <dt class="d">Работа</dt>
                <dd class="">{{ v.req?.duration_min }} мин</dd>
              </div>
              <div class="col-span-2">
                <dt class="">Что делаем</dt>
                <dd>{{ SKILLS[v.req?.skill] ?? v.req?.skill ?? "—" }}</dd>
              </div>
              <div class="col-span-2">
                <dt class="">Запас до закрытия окна</dt>
                <dd class="">
                  {{
                    v.slack == null
                      ? "—"
                      : v.slack < 0
                        ? `просрочка ${-v.slack} мин`
                        : `${v.slack} мин`
                  }}
                </dd>
              </div>
            </dl>

            <div v-if="v.req" class="flex items-center gap-2 mt-2">
              <a
                :href="navUrl(v.req)"
                target="_blank"
                rel="noopener"
                class="flex-1 text-center px-3 py-2 rounded-lg"
              >
                Проложить маршрут
              </a>
              <a
                :href="gisUrl(v.req)"
                target="_blank"
                rel="noopener"
                class="px-3 py-2 rounded-lg border"
              >
                2ГИС
              </a>
            </div>

            <p class="num mt-1.5 text-[10.5px] text-muted">
              заявка {{ v.stop.request_id }}
            </p>
          </article>
        </template>

        <!--        <button-->
        <!--          class="self-center mt-2 px-4 py-2 rounded-lg border border-hair-2 text-[12px] text-muted hover:text-ink hover:bg-panel-2 transition-colors cursor-pointer print:hidden"-->
        <!--          @click="printPage"-->
        <!--        >-->
        <!--          Распечатать памятку-->
        <!--        </button>-->
      </div>

      <div
        v-else-if="!state.loading"
        class="panel px-3 py-6 text-center text-[13px] text-muted"
      >
        На этот день выездов нет.
        <RouterLink
          :to="{ name: 'region', params: { regionId } }"
          class="text-ink underline underline-offset-2"
        >
          Вернуться к плану
        </RouterLink>
      </div>
    </div>
  </div>
</template>
