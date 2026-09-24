import { createRouter, createWebHistory } from "vue-router";

import EngineerView from "./views/EngineerView.vue";
import RegionView from "./views/RegionView.vue";
import { ensureRegions, state } from "./store.js";
import EngineersEditView from "./views/admin/EngineersEditView.vue";

const routes = [
  {
    path: "/region/:regionId(\\d+)",
    name: "region",
    component: RegionView,
    props: (route) => ({ regionId: Number(route.params.regionId) }),
  },
  {
    path: "/region/:regionId(\\d+)/engineer/:engineerId(\\d+)",
    name: "engineer",
    component: EngineerView,
    props: (route) => ({
      regionId: Number(route.params.regionId),
      engineerId: Number(route.params.engineerId),
    }),
  },
  // Админка исполнителей. Регион в адресе не нужен: страница про всех
  // сразу, фильтр по региону — локальное состояние экрана.
  {
    path: "/admin/engineers",
    name: "admin-engineers",
    component: EngineersEditView,
  },
  // Корень и любой мусор — на регион по умолчанию. Какой именно,
  // знает только справочник, поэтому решает guard ниже.
  { path: "/:pathMatch(.*)*", redirect: "/region/0" },
];

export const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach(async (to) => {
  const regions = await ensureRegions();
  // У админки нет региона в адресе — проверять нечего.
  if (to.name === "admin-engineers") return true;
  if (!regions.length) return true; // бэкенд молчит — покажем ошибку из store

  const id = Number(to.params.regionId);
  if (regions.some((r) => r.id === id)) return true;

  return {
    name: "region",
    params: { regionId: regions[0].id },
    replace: true,
  };
});

router.afterEach((to) => {
  const region = state.regions.find((r) => r.id === Number(to.params.regionId));
  const title = region ? `${region.title} — выезды` : "Планирование выездов";
  if (to.name === "admin-engineers") {
    document.title = "Исполнители — настройка";
    return;
  }
  document.title = to.name === "engineer" ? `Памятка · ${title}` : title;
});
