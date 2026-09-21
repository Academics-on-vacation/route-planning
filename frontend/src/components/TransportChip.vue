<script setup>
import { computed } from "vue";

const props = defineProps({
  kind: { type: String, default: null },
  // compact — только значок, без подписи: для узких мест вроде
  // заголовка маршрута, где и так тесно.
  compact: { type: Boolean, default: false },
});

const KINDS = {
  car: { label: "авто", title: "На автомобиле" },
  transit: { label: "транспорт", title: "Пешком и на общественном транспорте" },
  bike: { label: "вело", title: "На велосипеде" },
};

const kind = computed(() => KINDS[props.kind] ?? null);
</script>

<template>
  <span
    v-if="kind"
    class="inline-flex items-center gap-1 shrink-0 px-1.5 py-0.5 rounded bg-hair/70 text-muted text-[10px] leading-none"
    :title="kind.title"
  >
    <svg
      viewBox="0 0 24 24"
      class="w-3.5 h-3.5"
      fill="none"
      stroke="currentColor"
      stroke-width="1.9"
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
    >
      <template v-if="props.kind === 'car'">
        <path
          d="M3 16.4v-2.7c0-.5.2-1 .6-1.3l2.2-1.7 1.6-2.8c.3-.6.9-.9 1.5-.9h6.2c.6 0
             1.2.3 1.5.9l1.6 2.8 2.2 1.7c.4.3.6.8.6 1.3v2.7"
        />
        <circle cx="7.4" cy="16.4" r="1.8" />
        <circle cx="16.6" cy="16.4" r="1.8" />
        <path d="M9.2 16.4h5.6" />
      </template>

      <template v-else-if="props.kind === 'transit'">
        <rect x="5.5" y="4" width="13" height="12" rx="2.4" />
        <path d="M5.5 10.5h13" />
        <path d="M8.5 19.8 10 16M15.5 19.8 14 16" />
        <path d="M9 13.3h.01M15 13.3h.01" />
      </template>

      <template v-else-if="props.kind === 'bike'">
        <circle cx="6" cy="16.5" r="3.5" />
        <circle cx="18" cy="16.5" r="3.5" />
        <path d="M6 16.5 10 9h4M14.5 5.5h2.2M18 16.5 14.5 8" />
      </template>

      <template v-else>
        <circle cx="13" cy="4.6" r="1.7" />
        <path
          d="M8 21l3-5.4-1.4-3.4L7 14.4M9.6 12.2 11.4 8l3 1.8 1.2 2.6 2.4 1.2M11.4 15.6l3.6 2 1 3.4"
        />
      </template>
    </svg>

    <span v-if="!compact">{{ kind.label }}</span>
  </span>
</template>
