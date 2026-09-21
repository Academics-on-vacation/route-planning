import { createRouter, createWebHistory } from "vue-router";

import RegionView from "./views/RegionView.vue";
import { ensureRegions, state } from "./store.js";

const routes = [
  {
    path: "/region/:regionId(\\d+)",
    name: "region",
    component: RegionView,
    props: (route) => ({ regionId: Number(route.params.regionId) }),
  },
  { path: "/:pathMatch(.*)*", redirect: "/region/0" },
];

export const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach(async (to) => {
  const regions = await ensureRegions();
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
  document.title = region ? `${region.title} — выезды` : "Планирование выездов";
});
