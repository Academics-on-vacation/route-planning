<script setup>
import { computed, ref } from "vue";

const props = defineProps({
  visits: { type: Array, default: () => [] },
});

const UNIT = /,\s*(м|м2|мм|см|шт|компл|пар|кг|л)\.?$/i;

const parse = (v) => {
  const raw = String(v ?? "").trim();
  const unit = raw.match(UNIT);
  const name = (unit ? raw.slice(0, unit.index) : raw)
    .trim()
    .replace(/^./, (c) => c.toUpperCase());
  return { name, unit: unit ? unit[1].toLowerCase() : "" };
};

function itemsOf(equipment) {
  if (!equipment) return [];

  if (Array.isArray(equipment)) {
    return equipment
      .map((it) =>
        typeof it === "object" && it
          ? {
              ...parse(it.name ?? it.title ?? it.type),
              qty: Number(it.qty ?? it.count ?? it.amount ?? 1) || 1,
            }
          : { ...parse(it), qty: 1 },
      )
      .filter((it) => it.name);
  }

  if (typeof equipment === "object") {
    return Object.entries(equipment)
      .map(([name, value]) => ({
        ...parse(name),
        // {роутер: 2} и {роутер: true} — оба живые варианты выгрузки
        qty: typeof value === "number" ? value : Number(value?.qty ?? 1) || 1,
      }))
      .filter((it) => it.name);
  }

  return String(equipment)
    .split(/;/)
    .map((name) => ({ ...parse(name), qty: 1 }))
    .filter((it) => it.name);
}

const items = computed(() => {
  const acc = new Map();
  for (const { seq, req } of props.visits) {
    for (const { name, unit, qty } of itemsOf(req?.equipment)) {
      const key = `${name}|${unit}`;
      const row = acc.get(key) ?? { name, unit, qty: 0, visits: [] };
      row.qty += qty;
      row.visits.push(seq);
      acc.set(key, row);
    }
  }
  return [...acc.values()].sort(
    (a, b) => b.qty - a.qty || a.name.localeCompare(b.name),
  );
});

const taken = ref(new Set());
const toggle = (name) => {
  // const next = new Set(taken.value);
  // next.has(name) ? next.delete(name) : next.add(name);
  // taken.value = next;
};

const left = computed(
  () => items.value.filter((i) => !taken.value.has(i.name)).length,
);
</script>

<template>
  <section v-if="items.length" class="panel px-3 py-2.5">
    <header class="flex items-baseline gap-2">
      <svg
        viewBox="0 0 24 24"
        class="w-4 h-4 text-muted shrink-0 self-center"
        fill="none"
        stroke="currentColor"
        stroke-width="1.8"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
      >
        <path d="M3 8.5 12 4l9 4.5v7L12 20l-9-4.5v-7Z" />
        <path d="M3 8.5 12 13l9-4.5M12 13v7" />
      </svg>
      <h2 class="text-[13px] font-semibold">Взять с собой</h2>
      <!--      <span class="num ml-auto text-[11px] text-muted">-->
      <!--        {{ left ? `осталось ${left} из ${items.length}` : "всё собрано" }}-->
      <!--      </span>-->
    </header>

    <ul class="mt-2 flex flex-col gap-1">
      <li v-for="item in items" :key="item.name">
        <button
          class="w-full flex items-center gap-2.5 px-2 py-1.5 rounded-lg text-left border border-hair hover:bg-panel-2 transition-colors cursor-pointer"
          :class="taken.has(item.name) ? 'opacity-45' : ''"
          @click="toggle(item.name)"
        >
          <span
            class="w-4 h-4 shrink-0 rounded border-2 grid place-items-center transition-colors"
            :class="
              taken.has(item.name)
                ? 'bg-ink border-ink text-white'
                : 'border-hair-2'
            "
            aria-hidden="true"
          >
            <svg
              v-if="taken.has(item.name)"
              viewBox="0 0 24 24"
              class="w-3 h-3"
              fill="none"
              stroke="currentColor"
              stroke-width="3.2"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <path d="m5 12.5 4.5 4.5L19 7" />
            </svg>
          </span>

          <span class="min-w-0 flex-1">
            <span
              class="text-[13px] leading-snug"
              :class="taken.has(item.name) ? 'line-through' : ''"
            >
              {{ item.name }}
            </span>
            <span class="num block text-[10.5px] text-muted">
              заявк{{ item.visits.length > 1 ? "и" : "а" }}
              {{ item.visits.join(", ") }}
            </span>
          </span>

          <b
            v-if="item.qty > 1 || item.unit"
            class="num shrink-0 px-1.5 py-0.5 rounded bg-brand text-black text-[12px]"
          >
            {{ item.unit ? `${item.qty} ${item.unit}` : `×${item.qty}` }}
          </b>
        </button>
      </li>
    </ul>
  </section>
</template>
