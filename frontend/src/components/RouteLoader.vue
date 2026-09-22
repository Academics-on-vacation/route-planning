<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue";

import { state } from "../store.js";

const SHOW_AFTER = 180;
const HOLD_DONE = 2000;

const visible = ref(false);
const done = ref(false);
const elapsed = ref(0);

let showTimer = null;
let doneTimer = null;
let tick = null;

watch(
  () => state.loading,
  (loading) => {
    clearTimeout(showTimer);
    clearTimeout(doneTimer);
    if (loading) {
      done.value = false;
      showTimer = setTimeout(() => {
        visible.value = true;
        start();
      }, SHOW_AFTER);
    } else if (visible.value) {
      done.value = true;
      stop();
      doneTimer = setTimeout(() => (visible.value = false), HOLD_DONE);
    }
  },
  { immediate: true },
);

function start() {
  stop();
  tick = setInterval(() => {
    elapsed.value = Date.now() - (state.loadingSince ?? Date.now());
  }, 80);
}
function stop() {
  clearInterval(tick);
  tick = null;
}
onBeforeUnmount(() => {
  stop();
  clearTimeout(showTimer);
  clearTimeout(doneTimer);
});

const percent = computed(() => {
  if (done.value) return 100;
  const eta = Math.max(800, state.lastLoadMs || 4000);
  const t = elapsed.value / eta;
  const value = t < 1 ? 1 - (1 - t) ** 3 : 1 + (0.04 - 0.04 * Math.exp(1 - t));
  return Math.round(Math.min(0.96, value * 0.96) * 100);
});

const seconds = computed(() => (elapsed.value / 1000).toFixed(1));

// const SOLVER_STEPS = [
//   "жадная раскладка по бригадам",
//   "уточняем плечи через 2ГИС",
//   "улучшаем перестановками",
// ];
const step = computed(() => {
  if (done.value) return "готово";
  if (state.stage === "refs") return "справочник региона";
  const i = Math.min(SOLVER_STEPS.length - 1, Math.floor(elapsed.value / 1600));
  return SOLVER_STEPS[i];
});
// const title = computed(() =>
//   done.value
//     ? "План готов"
//     : state.stage === "refs"
//       ? "Читаем заявки и бригады"
//       : "Прокладываем маршруты",
// );
</script>

<template>
  <Transition
    enter-active-class="transition-opacity duration-200"
    leave-active-class="transition-opacity duration-300"
    enter-from-class="opacity-0"
    leave-to-class="opacity-0"
  >
    <div
      v-if="visible"
      class="loader-overlay absolute inset-0 z-[1200] flex flex-col items-center justify-center gap-6"
      role="status"
      aria-live="polite"
    >
      <svg class="w-[232px] h-[164px]" viewBox="0 0 200 140" aria-hidden="true">
        <defs>
          <linearGradient id="ld-signal" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stop-color="#ffcc00" stop-opacity=".15" />
            <stop offset="50%" stop-color="#ffcc00" stop-opacity="1" />
            <stop offset="100%" stop-color="#ffcc00" stop-opacity=".15" />
          </linearGradient>
          <radialGradient id="ld-ground" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stop-color="#ffcc00" stop-opacity=".35" />
            <stop offset="100%" stop-color="#ffcc00" stop-opacity="0" />
          </radialGradient>
          <filter id="ld-glow" x="-60%" y="-60%" width="220%" height="220%">
            <feGaussianBlur stdDeviation="2.6" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        <!-- Радар под вышкой -->
        <ellipse cx="42" cy="114" rx="34" ry="8" fill="url(#ld-ground)">
          <animate
            attributeName="rx"
            values="22;40;22"
            dur="2.4s"
            repeatCount="indefinite"
          />
          <animate
            attributeName="opacity"
            values=".4;1;.4"
            dur="2.4s"
            repeatCount="indefinite"
          />
        </ellipse>

        <!-- Сигнальные дуги: чем дальше дуга, тем позже вспышка -->
        <g
          fill="none"
          stroke="url(#ld-signal)"
          stroke-width="3.4"
          stroke-linecap="round"
        >
          <path d="M32 40 A14 14 0 0 1 52 40">
            <animate
              attributeName="opacity"
              values=".12;1;.12"
              dur="1.8s"
              begin="0s"
              repeatCount="indefinite"
            />
          </path>
          <path d="M25 32 A23 23 0 0 1 59 32">
            <animate
              attributeName="opacity"
              values=".12;1;.12"
              dur="1.8s"
              begin=".35s"
              repeatCount="indefinite"
            />
          </path>
          <path d="M18 24 A32 32 0 0 1 66 24">
            <animate
              attributeName="opacity"
              values=".12;1;.12"
              dur="1.8s"
              begin=".7s"
              repeatCount="indefinite"
            />
          </path>
        </g>

        <!-- Мачта -->
        <g
          stroke="var(--color-ink)"
          stroke-width="2.2"
          stroke-linecap="round"
          fill="none"
        >
          <path d="M30 114 L42 52 L54 114" />
          <path d="M33 98 L51 98" />
          <path d="M36 80 L48 80" />
          <path d="M27.5 110 L56.5 110" />
          <path d="M39 64 L45 64" />
        </g>
        <circle cx="42" cy="48" r="3.6" fill="var(--color-ink)" />
        <circle
          cx="42"
          cy="48"
          r="3.6"
          fill="var(--color-brand)"
          filter="url(#ld-glow)"
          opacity=".9"
        >
          <animate
            attributeName="opacity"
            values=".35;1;.35"
            dur="1.2s"
            repeatCount="indefinite"
          />
        </circle>

        <!-- Импульс вверх по мачте: сигнал ушёл в эфир -->
        <circle cx="42" r="2.2" fill="var(--color-brand)">
          <animate
            attributeName="cy"
            values="114;48;48"
            dur="2s"
            repeatCount="indefinite"
          />
          <animate
            attributeName="opacity"
            values="1;1;0"
            dur="2s"
            repeatCount="indefinite"
          />
        </circle>

        <!--
          Маршрут. Рисуется штрихом: pathLength=100 нормирует длину,
          и dashoffset можно гнать от 100 до 0 независимо от реальной
          геометрии кривой.
        -->
        <path
          id="ld-route"
          d="M46 112 C 68 120, 74 92, 96 94 S 126 112, 140 100 S 164 74, 184 88"
          fill="none"
          stroke="var(--color-ink)"
          stroke-opacity=".3"
          stroke-width="2"
          stroke-linecap="round"
          stroke-dasharray="3 5"
          pathLength="100"
        />
        <path
          d="M46 112 C 68 120, 74 92, 96 94 S 126 112, 140 100 S 164 74, 184 88"
          fill="none"
          stroke="var(--color-brand)"
          stroke-width="3"
          stroke-linecap="round"
          pathLength="100"
          stroke-dasharray="100"
        >
          <animate
            attributeName="stroke-dashoffset"
            values="100;0;0"
            keyTimes="0;.7;1"
            dur="3.2s"
            repeatCount="indefinite"
          />
        </path>

        <!-- Точки визитов загораются по мере того, как линия до них дошла -->
        <g fill="var(--color-ink)">
          <circle cx="96" cy="94" r="0">
            <animate
              attributeName="r"
              values="0;4.2;3.2;3.2"
              keyTimes="0;.32;.4;1"
              dur="3.2s"
              repeatCount="indefinite"
            />
          </circle>
          <circle cx="140" cy="100" r="0">
            <animate
              attributeName="r"
              values="0;0;4.2;3.2;3.2"
              keyTimes="0;.42;.5;.58;1"
              dur="3.2s"
              repeatCount="indefinite"
            />
          </circle>
          <circle cx="184" cy="88" r="0">
            <animate
              attributeName="r"
              values="0;0;4.2;3.2;3.2"
              keyTimes="0;.62;.7;.78;1"
              dur="3.2s"
              repeatCount="indefinite"
            />
          </circle>
        </g>

        <!-- Бригада едет по только что проложенному маршруту -->
        <circle
          r="3.4"
          fill="var(--color-brand)"
          stroke="var(--color-ink)"
          stroke-width="1.6"
        >
          <animateMotion
            dur="3.2s"
            repeatCount="indefinite"
            keyPoints="0;1;1"
            keyTimes="0;.7;1"
            calcMode="linear"
          >
            <mpath href="#ld-route" />
          </animateMotion>
        </circle>
      </svg>

      <div class="flex flex-col items-center gap-2 min-w-[260px]">
        <div class="text-[14px] font-medium text-ink">{{ title }}</div>

        <div class="w-[260px] h-1 rounded-full bg-ink/10 overflow-hidden">
          <div
            class="h-full rounded-full bg-gradient-to-r from-brand to-brand-deep shadow-[0_0_10px_rgba(255,204,0,.7)] transition-[width] duration-200 ease-out"
            :style="{ width: percent + '%' }"
          />
        </div>

        <div
          class="num flex items-center gap-2 text-[11px] text-muted tabular-nums"
        >
          <!--          <span>{{ step }}</span>-->
          <!--          <span class="opacity-40">·</span>-->
          <span>{{ seconds }} с</span>
        </div>
      </div>
    </div>
  </Transition>
</template>
