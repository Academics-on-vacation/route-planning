import { computed, reactive, shallowRef } from "vue";

import { api } from "./api.js";

const key = (id) => String(id);

export const COLORS = [
  "#1f6b4a",
  "#b0410e",
  "#2563a8",
  "#7a3fa0",
  "#a8880c",
  "#0f7b86",
  "#98263c",
  "#4a6b1f",
  "#5a4bb5",
  "#a1542c",
  "#186f9b",
  "#6b3f1f",
];

export const SKILLS = {
  local: "Локальные работы",
  install: "Работы на подключение и дозаказы",
  emergency: "Аварийные работы",
};

export const state = reactive({
  regions: [],
  regionId: null,
  requests: {},
  engineers: {},
  selected: null,
  hovered: null,
  focused: null,
  loading: false,
  error: null,
});

export const plan = shallowRef(null);

export const routes = computed(() =>
  (plan.value?.routes ?? []).filter((r) => r.stops?.length),
);

export const unassigned = computed(() => plan.value?.unassigned ?? []);

export const requestList = computed(() => Object.values(state.requests));

export const colorOfEngineer = computed(() => {
  const map = {};
  Object.values(state.engineers).forEach((e, i) => {
    map[key(e.id)] = COLORS[i % COLORS.length];
  });
  return map;
});

export const stopIndex = computed(() => {
  const map = {};
  for (const route of routes.value) {
    route.stops.forEach((stop, i) => {
      map[key(stop.request_id)] = {
        route,
        stop,
        request: state.requests[key(stop.request_id)] ?? null,
        seq: stop.seq ?? i + 1,
        total: route.stops.length,
      };
    });
  }
  return map;
});

export const unassignedIndex = computed(() => {
  const map = {};
  for (const u of unassigned.value) map[key(u.request_id)] = u;
  return map;
});

export const metrics = computed(() => plan.value?.metrics ?? null);

export const engineerOf = (requestId) =>
  requestId == null
    ? null
    : (stopIndex.value[key(requestId)]?.route.engineer_id ?? null);

const same = (a, b) => a != null && b != null && String(a) === String(b);

/** Клик по заявке. Повторный клик по той же снимает выделение. */
export function select(id) {
  state.selected = same(state.selected, id) ? null : id;
}

export function hover(id) {
  state.hovered = id;
}

/** Подсветить весь маршрут инженера; повторный клик снимает. */
export function focusEngineer(id) {
  state.focused = same(state.focused, id) ? null : id;
}

export function clearSelection() {
  state.selected = null;
  state.hovered = null;
  state.focused = null;
}

export const isSelected = (id) => same(state.selected, id);
export const isHovered = (id) => same(state.hovered, id);

/** Заявка под вниманием: выбрана или под курсором. */
export const isActive = (id) => isSelected(id) || isHovered(id);

/**
 * Глушим только когда выделен маршрут ДРУГОГО инженера. Выбор одной
 * заявки другие не глушит: иначе при клике карта наполовину гаснет,
 * а смотрят как раз на соседние маршруты — кому её передать.
 */
export const isDimmed = (engineerId) =>
  state.focused != null && !same(state.focused, engineerId);

export const isFocused = (engineerId) => same(state.focused, engineerId);

/** Цвет заявки = цвет её исполнителя. Не назначенная — красная. */
export const colorOfRequest = (requestId) => {
  const eng = engineerOf(requestId);
  return eng == null ? "#99271f" : colorOfEngineer.value[key(eng)];
};

const indexById = (rows) => {
  const map = {};
  for (const row of rows) map[key(row.id)] = row;
  return map;
};

export async function loadRegions() {
  try {
    state.regions = await api.regions();
    if (state.regions.length) await loadRegion(state.regions[0].id);
  } catch (e) {
    state.error = String(e.message ?? e);
  }
}

export async function loadRegion(id) {
  state.loading = true;
  state.error = null;
  try {
    const [reqs, engs] = await Promise.all([
      api.requests(id),
      api.engineers(id),
    ]);
    state.regionId = id;
    state.requests = indexById(reqs);
    state.engineers = indexById(engs);
    // Выделение снимаем: заявки из другого региона здесь нет.
    state.selected = null;
    state.hovered = null;
    state.focused = null;
    plan.value = await api.plan(id);
  } catch (e) {
    state.error = String(e.message ?? e);
  } finally {
    state.loading = false;
  }
}

export async function rebuild(options = {}) {
  state.loading = true;
  state.error = null;
  try {
    plan.value = await api.plan(state.regionId, options);
  } catch (e) {
    state.error = String(e.message ?? e);
  } finally {
    state.loading = false;
  }
}
