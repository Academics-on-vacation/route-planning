<script setup>
import { computed, onMounted, ref } from "vue";
import { RouterLink } from "vue-router";

import { api } from "../../api.js";
import TransportChip from "../../components/TransportChip.vue";
import { ensureRegions, state } from "../../store.js";

const rows = ref([]);
const loading = ref(true);
const error = ref(null);
const regionId = ref(null); // null — все регионы
// Черновики по инженерам: { [id]: "55.7, 37.6" }
const draft = ref({});
const status = ref({}); // { [id]: "saving" | "saved" | текст ошибки }

const regionTitle = (id) =>
  state.regions.find((r) => r.id === id)?.title ?? `Регион ${id}`;

const visible = computed(() =>
  regionId.value == null
    ? rows.value
    : rows.value.filter((e) => e.region_id === regionId.value),
);

const fromHome = (e) => e.start_lat != null && e.start_lon != null;
const homeCount = computed(() => visible.value.filter(fromHome).length);

async function load() {
  loading.value = true;
  error.value = null;
  try {
    await ensureRegions();
    rows.value = await api.allEngineers();
    draft.value = Object.fromEntries(
      rows.value.map((e) => [
        e.id,
        fromHome(e) ? `${e.start_lat}, ${e.start_lon}` : "",
      ]),
    );
  } catch (e) {
    error.value = String(e.message ?? e);
  } finally {
    loading.value = false;
  }
}
onMounted(load);

/**
 * Разбор строки координат.
 *
 * Принимаем то, что реально копируют из 2ГИС и Яндекса: «55.7, 37.6»,
 * «55.7 37.6», с точкой или запятой в качестве десятичного разделителя
 * тоже, если разделены точкой с запятой.
 */
function parse(text) {
  const raw = String(text ?? "").trim();
  if (!raw) return { lat: null, lon: null };

  const parts = raw.includes(";")
    ? raw.split(";")
    : raw.replace(/,\s*(?=\d{2}[.,]|\d{2}$)/g, " ").split(/[\s,]+/);
  const nums = parts
    .map((p) => Number(String(p).trim().replace(",", ".")))
    .filter((n) => Number.isFinite(n));

  if (nums.length !== 2)
    return { error: "нужны две координаты: широта и долгота" };
  const [lat, lon] = nums;
  if (lat < -90 || lat > 90) return { error: "широта вне диапазона (−90…90)" };
  if (lon < -180 || lon > 180)
    return { error: "долгота вне диапазона (−180…180)" };
  // Москва и область — 55.x, 37.x. Перепутанные местами координаты
  // выглядят как 37.6, 55.7 и уводят инженера в Турцию.
  if (lat < 40 && lon > 50)
    return { error: "похоже, широта и долгота перепутаны местами" };
  return { lat, lon };
}

async function save(engineer) {
  const parsed = parse(draft.value[engineer.id]);
  if (parsed.error) {
    status.value = { ...status.value, [engineer.id]: parsed.error };
    return;
  }
  status.value = { ...status.value, [engineer.id]: "saving" };
  try {
    const updated = await api.setStartPoint(
      engineer.id,
      parsed.lat,
      parsed.lon,
    );
    rows.value = rows.value.map((e) => (e.id === updated.id ? updated : e));
    draft.value[engineer.id] = fromHome(updated)
      ? `${updated.start_lat}, ${updated.start_lon}`
      : "";
    status.value = { ...status.value, [engineer.id]: "saved" };
    setTimeout(() => {
      const next = { ...status.value };
      if (next[engineer.id] === "saved") delete next[engineer.id];
      status.value = next;
    }, 1600);
  } catch (e) {
    status.value = { ...status.value, [engineer.id]: String(e.message ?? e) };
  }
}

/** Вернуть в офис: обе координаты null — так это понимает бэкенд. */
async function reset(engineer) {
  draft.value[engineer.id] = "";
  status.value = { ...status.value, [engineer.id]: "saving" };
  try {
    const updated = await api.setStartPoint(engineer.id, null, null);
    rows.value = rows.value.map((e) => (e.id === updated.id ? updated : e));
    status.value = { ...status.value, [engineer.id]: "saved" };
    setTimeout(() => {
      const next = { ...status.value };
      if (next[engineer.id] === "saved") delete next[engineer.id];
      status.value = next;
    }, 1600);
  } catch (e) {
    status.value = { ...status.value, [engineer.id]: String(e.message ?? e) };
  }
}

const dirty = (e) =>
  (draft.value[e.id] ?? "").trim() !==
  (fromHome(e) ? `${e.start_lat}, ${e.start_lon}` : "");
</script>

<template>
  <div class="flex-1 min-h-0 overflow-y-auto">
    <div class="max-w-[940px] mx-auto p-3 flex flex-col gap-2.5">
      <div class="panel px-3 py-2.5">
        <div class="flex flex-wrap items-center gap-2">
          <h1 class="text-[16px] font-semibold">Исполнители</h1>
          <span class="num text-[11.5px] text-muted">
            {{ visible.length }} всего · {{ homeCount }} стартуют из дома
          </span>

          <nav
            class="ml-auto flex items-center gap-1 p-0.5 rounded-lg bg-hair/60"
          >
            <button
              class="px-2.5 py-1 rounded-md text-[12px] cursor-pointer transition-colors"
              :class="
                regionId == null
                  ? 'bg-panel font-semibold'
                  : 'text-muted hover:text-ink'
              "
              @click="regionId = null"
            >
              Все
            </button>
            <button
              v-for="r in state.regions"
              :key="r.id"
              class="px-2.5 py-1 rounded-md text-[12px] cursor-pointer transition-colors"
              :class="
                regionId === r.id
                  ? 'bg-panel font-semibold'
                  : 'text-muted hover:text-ink'
              "
              @click="regionId = r.id"
            >
              {{ r.title }}
            </button>
          </nav>
        </div>

        <p class="mt-1 text-[11.5px] text-muted">
          Пустое поле — инженер начинает день из офиса региона. Координаты можно
          вставить как есть: «55.702267, 37.773852».
        </p>
      </div>

      <p v-if="error" class="panel px-3 py-2.5 text-[12.5px] text-crit">
        {{ error }}
        <button class="ml-2 underline cursor-pointer" @click="load">
          повторить
        </button>
      </p>

      <p
        v-else-if="loading"
        class="panel px-3 py-6 text-center text-[13px] text-muted"
      >
        Загружаем…
      </p>

      <div v-else class="panel divide-y divide-hair">
        <article
          v-for="e in visible"
          :key="e.id"
          class="flex flex-wrap items-center gap-x-3 gap-y-2 px-3 py-2.5"
          :class="e.is_active ? '' : 'opacity-50'"
        >
          <div class="min-w-[180px] flex-1">
            <div class="flex items-center gap-1.5">
              <span class="text-[13.5px] font-medium">{{ e.name }}</span>
              <TransportChip :kind="e.transport" compact />
              <span
                v-if="!e.is_active"
                class="text-[10px] uppercase tracking-wide text-muted"
              >
                выключен
              </span>
            </div>
            <div class="num text-[11px] text-muted">
              {{ regionTitle(e.region_id) }} · смена
              {{ e.shift_start?.slice(0, 5) }}–{{ e.shift_end?.slice(0, 5) }}
            </div>
          </div>

          <!-- Точка старта: одно поле на пару координат — так их копируют
               из карт, и так меньше шансов заполнить только половину. -->
          <label class="flex items-center gap-2">
            <span
              class="w-[74px] shrink-0 text-[11px]"
              :class="fromHome(e) ? 'text-ink' : 'text-muted'"
            >
              {{ fromHome(e) ? "из дома" : "из офиса" }}
            </span>
            <input
              v-model="draft[e.id]"
              class="num w-[210px] px-2 py-1.5 rounded-lg border text-[12.5px] focus:outline-none focus:border-brand-deep"
              :class="
                status[e.id] &&
                status[e.id] !== 'saved' &&
                status[e.id] !== 'saving'
                  ? 'border-crit'
                  : 'border-hair-2'
              "
              placeholder="широта, долгота"
              @keyup.enter="save(e)"
            />
          </label>

          <div class="flex items-center gap-1.5">
            <button
              class="px-3 py-1.5 rounded-lg bg-brand text-black text-[12px] font-semibold cursor-pointer hover:bg-brand-deep transition-colors disabled:opacity-40 disabled:cursor-default"
              :disabled="!dirty(e) || status[e.id] === 'saving'"
              @click="save(e)"
            >
              Сохранить
            </button>
            <button
              v-if="fromHome(e)"
              class="px-3 py-1.5 rounded-lg border border-hair-2 text-[12px] text-muted cursor-pointer hover:text-ink hover:bg-panel-2 transition-colors"
              title="Вернуть старт в офис региона"
              @click="reset(e)"
            >
              В офис
            </button>
          </div>

          <p
            v-if="status[e.id]"
            class="w-full text-[11px]"
            :class="
              status[e.id] === 'saved'
                ? 'text-good'
                : status[e.id] === 'saving'
                  ? 'text-muted'
                  : 'text-crit'
            "
          >
            {{
              status[e.id] === "saved"
                ? "сохранено"
                : status[e.id] === "saving"
                  ? "сохраняем…"
                  : status[e.id]
            }}
          </p>
        </article>

        <p
          v-if="!visible.length"
          class="px-3 py-6 text-center text-[13px] text-muted"
        >
          В этом регионе исполнителей нет.
        </p>
      </div>
    </div>
  </div>
</template>
