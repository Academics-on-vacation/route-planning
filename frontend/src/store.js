import { computed, reactive, shallowRef } from "vue";

import { api } from "./api.js";
import { toMinutes } from "./time.js";

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
  pendingRegionId: null,
  loadingSince: null,
  stage: null,
  lastLoadMs: 4000,
  requests: {},
  engineers: {},
  selected: null,
  hovered: null,
  focused: null,
  loading: false,
  error: null,
  picking: false,
  picked: null,
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

/** План на этот день ещё ни разу не считали. */
export const planMissing = computed(
  () => !!plan.value && plan.value.meta?.stored === false,
);

/** Сводка перепланирования, если текущий план получен по аварии. */
export const replanInfo = computed(() => plan.value?.meta?.replan ?? null);

/** Момент заморозки в минутах от полуночи — по нему Гант рисует черту. */
export const frozenAt = computed(() => toMinutes(replanInfo.value?.frozen_at));

/**
 * Заявки, ушедшие от инженера к другому: {id бригады: [{request_id, to}]}.
 */
export const movedAway = computed(() => {
  const map = {};
  for (const m of replanInfo.value?.moves ?? []) {
    (map[key(m.from)] ??= []).push(m);
  }
  return map;
});

/** Имя инженера по id — для подписей «от кого» и «к кому». */
export const engineerName = (id) =>
  state.engineers[key(id)]?.name ?? `Инженер ${id}`;

/** Чем ездит инженер: car / transit / bike / foot. Берём из справочника
 *  исполнителей — в маршруте плана этого поля нет. */
export const transportOf = (engineerId) =>
  engineerId == null
    ? null
    : (state.engineers[key(engineerId)]?.transport ?? null);

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

let regionsPromise = null;

export function ensureRegions() {
  regionsPromise ??= api
    .regions()
    .then((rows) => (state.regions = rows))
    .catch((e) => {
      state.error = String(e.message ?? e);
      regionsPromise = null; // дадим следующему переходу попробовать снова
      return [];
    });
  return regionsPromise;
}

let token = 0;

export async function loadRegion(id) {
  const mine = ++token;
  const startedAt = Date.now();
  state.pendingRegionId = id;
  state.loading = true;
  state.loadingSince = startedAt;
  state.stage = "refs";
  state.error = null;
  clearSelection();
  plan.value = null;

  try {
    const [reqs, engs] = await Promise.all([
      api.requests(id),
      api.engineers(id),
    ]);
    if (mine !== token) return; // нас обогнали, этот ответ уже не нужен
    state.regionId = id;
    state.requests = indexById(reqs);
    state.engineers = indexById(engs);

    // Дальше считает солвер — самая долгая часть загрузки.
    state.stage = "plan";
    const fresh = await api.storedPlan(id);
    if (mine !== token) return;
    plan.value = fresh;
    // Ориентир для полосы прогресса на следующий раз.
    state.lastLoadMs = Date.now() - startedAt;
  } catch (e) {
    if (mine !== token) return;
    state.error = String(e.message ?? e);
  } finally {
    if (mine === token) {
      state.loading = false;
      state.pendingRegionId = null;
      state.stage = null;
    }
  }
}

/** Пересчитать план текущего региона. Тот же счётчик: если во время
 *  пересчёта переключили регион, старый ответ выбрасываем. */
export async function rebuild(options = {}) {
  const mine = ++token;
  const id = state.regionId;
  const startedAt = Date.now();
  state.loading = true;
  state.loadingSince = startedAt;
  state.stage = "plan";
  state.error = null;
  if (localStorage.getItem("api")) {
    options["use_api"] = true;
  }
  try {
    const fresh = await api.plan(id, options);
    if (mine !== token) return;
    plan.value = fresh;
    state.lastLoadMs = Date.now() - startedAt;
  } catch (e) {
    if (mine !== token) return;
    state.error = String(e.message ?? e);
  } finally {
    if (mine === token) {
      state.loading = false;
      state.stage = null;
    }
  }
}

/**
 * Перепланировать день с момента аварии.
 */
export async function replan(at, options = {}) {
  const mine = ++token;
  const id = state.regionId;
  const startedAt = Date.now();
  state.loading = true;
  state.loadingSince = startedAt;
  state.stage = "plan";
  state.error = null;
  try {
    const fresh = await api.replan(id, at, options);
    if (mine !== token) return;
    state.requests = indexById(await api.requests(id));
    if (mine !== token) return;
    plan.value = fresh;
    state.lastLoadMs = Date.now() - startedAt;
  } catch (e) {
    if (mine !== token) return;
    state.error = String(e.message ?? e);
    throw e;
  } finally {
    if (mine === token) {
      state.loading = false;
      state.stage = null;
    }
  }
}
