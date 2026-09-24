<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue";

import { api } from "../api.js";
import { plan, replan, state } from "../store.js";

const props = defineProps({ open: Boolean });
const emit = defineEmits(["close"]);

const workDate = computed(() => plan.value?.work_date ?? null);

const time = ref("14:00");
const address = ref("");
const coords = ref("");
const duration = ref(60);
const busy = ref(false);
const error = ref(null);
const used = new Set();

watch(
  () => state.picked,
  (p) => {
    if (p) {
      coords.value = `${p.lat.toFixed(6)}, ${p.lon.toFixed(6)}`;
      state.picked = null;
    }
  },
);

watch(
  () => props.open,
  (open) => {
    if (!open) {
      state.picking = false;
      return;
    }
    error.value = null;
    time.value = "14:00";
    hints.value = [];
    hintsOpen.value = false;
    hintError.value = null;
  },
);

const parsed = computed(() => {
  const raw = coords.value.trim();
  if (!raw) return null;
  const nums = raw
    .split(/[\s,;]+/)
    .map((p) => Number(p.replace(",", ".")))
    .filter(Number.isFinite);
  if (nums.length !== 2) return null;
  const [lat, lon] = nums;
  if (lat < -90 || lat > 90 || lon < -180 || lon > 180) return null;
  return { lat, lon };
});

const ready = computed(
  () =>
    !!parsed.value &&
    !!workDate.value &&
    /^\d{2}:\d{2}$/.test(time.value) &&
    duration.value > 0,
);

async function submit() {
  if (!ready.value || busy.value) return;
  busy.value = true;
  error.value = null;

  const day = workDate.value;
  if (!day) {
    error.value = "нет рассчитанного плана — сначала посчитайте день";
    busy.value = false;
    return;
  }
  const at = `${day}T${time.value}:00`;

  const base = `АВАРИЯ-${time.value.replace(":", "")}`;
  const external_id = used.has(base) ? `${base}-${used.size + 1}` : base;

  try {
    await api.createRequest(state.regionId, {
      external_id,
      address: address.value.trim() || "Авария (точка на карте)",
      lat: parsed.value.lat,
      lon: parsed.value.lon,
      work_type: "Аварийные работы",
      skill: "emergency",
      duration_min: Number(duration.value),
      window_start: at,
      window_end: `${day}T22:00:00`,
      priority: 10,
    });
    used.add(base);
    let options = {};
    console.log(localStorage.getItem("api"));
    if (localStorage.getItem("api")) {
      options["use_api"] = true;
    }
    await replan(at, options);
    emit("close");
  } catch (e) {
    error.value = String(e.message ?? e);
  } finally {
    busy.value = false;
  }
}

function pickOnMap() {
  state.picking = true;
}

const hints = ref([]);
const hintsOpen = ref(false);
const hintIndex = ref(-1);
const searching = ref(false);
const hintError = ref(null);
let timer = null;
let hintToken = 0;

function onAddressInput() {
  clearTimeout(timer);
  hintError.value = null;
  const text = address.value.trim();
  if (text.length < 3) {
    hints.value = [];
    hintsOpen.value = false;
    return;
  }
  // Пауза, чтобы не дёргать геокодер на каждую букву.
  timer = setTimeout(search, 350);
}

async function search() {
  const mine = ++hintToken;
  searching.value = true;
  try {
    const found = await api.geocode(address.value.trim(), state.regionId);
    if (mine !== hintToken) return;
    hints.value = found;
    hintIndex.value = -1;
    hintsOpen.value = found.length > 0;
  } catch (e) {
    if (mine !== hintToken) return;
    // Нет ключа или геокодер молчит — не мешаем работать руками.
    hints.value = [];
    hintsOpen.value = false;
    hintError.value = String(e.message ?? e).includes("503")
      ? "подсказки недоступны — введите координаты вручную"
      : "геокодер не ответил";
  } finally {
    if (mine === hintToken) searching.value = false;
  }
}

function choose(hint) {
  address.value = hint.address || hint.title;
  coords.value = `${hint.lat.toFixed(6)}, ${hint.lon.toFixed(6)}`;
  hintsOpen.value = false;
  hints.value = [];
}

function onAddressKey(e) {
  if (!hintsOpen.value || !hints.value.length) return;
  if (e.key === "ArrowDown") {
    e.preventDefault();
    hintIndex.value = (hintIndex.value + 1) % hints.value.length;
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    hintIndex.value =
      (hintIndex.value - 1 + hints.value.length) % hints.value.length;
  } else if (e.key === "Enter" && hintIndex.value >= 0) {
    e.preventDefault();
    choose(hints.value[hintIndex.value]);
  } else if (e.key === "Escape") {
    hintsOpen.value = false;
  }
}

onBeforeUnmount(() => clearTimeout(timer));
</script>

<template>
  <div
    v-if="open && state.picking"
    class="fixed top-3 left-1/2 -translate-x-1/2 z-[1300] flex items-center gap-2 panel px-3 py-2 text-[12.5px] shadow-lg print:hidden"
  >
    <span
      class="w-2 h-2 rounded-full bg-crit animate-pulse"
      aria-hidden="true"
    />
    Ткни в точку аварии на карте
    <button
      class="text-muted underline hover:text-ink cursor-pointer"
      @click="state.picking = false"
    >
      отмена
    </button>
  </div>

  <div
    v-if="open && !state.picking"
    class="fixed inset-0 z-[1300] flex items-start justify-center pt-[9vh] bg-black/35 print:hidden"
    @click.self="emit('close')"
  >
    <!-- overflow-visible: у .panel скрытое переполнение, иначе выпадающий
         список подсказок обрезается по нижнему краю диалога. -->
    <div class="panel overflow-visible w-[420px] max-w-[92vw] p-3.5">
      <div class="flex items-center gap-2">
        <span
          class="w-5 h-5 rounded-full bg-crit text-white text-[12px] font-bold grid place-items-center shrink-0"
          aria-hidden="true"
        >
          !
        </span>
        <h2 class="text-[15px] font-semibold">Авария</h2>
        <button
          class="ml-auto text-muted hover:text-ink text-[18px] leading-none px-1 cursor-pointer"
          @click="emit('close')"
        >
          ×
        </button>
      </div>

      <div class="grid grid-cols-2 gap-2.5 mt-3">
        <label class="flex flex-col gap-1">
          <span class="text-[11px] text-muted">Время аварии</span>
          <input
            v-model="time"
            type="time"
            class="num px-2 py-1.5 rounded-lg border border-hair-2 text-[13px] focus:outline-none focus:border-brand-deep"
          />
        </label>

        <label class="flex flex-col gap-1">
          <span class="text-[11px] text-muted">Работа, мин</span>
          <input
            v-model.number="duration"
            type="number"
            min="10"
            step="10"
            class="num px-2 py-1.5 rounded-lg border border-hair-2 text-[13px] focus:outline-none focus:border-brand-deep"
          />
        </label>

        <div class="col-span-2 flex flex-col gap-1 relative">
          <span class="text-[11px] text-muted">
            Адрес
            <span v-if="searching" class="text-muted">— ищем…</span>
            <span v-else-if="hintError" class="text-serious">— {{ hintError }}</span>
          </span>
          <input
            v-model="address"
            placeholder="Москва, ул. Полбина, д. 9"
            autocomplete="off"
            class="px-2 py-1.5 rounded-lg border border-hair-2 text-[13px] focus:outline-none focus:border-brand-deep"
            @input="onAddressInput"
            @keydown="onAddressKey"
            @focus="hintsOpen = hints.length > 0"
          />

          <ul
            v-if="hintsOpen"
            class="absolute left-0 right-0 top-[52px] z-10 max-h-[190px] overflow-y-auto
                   rounded-lg bg-panel border border-hair-2 shadow-lg py-1"
          >
            <li
              v-for="(hint, i) in hints"
              :key="`${hint.lat}-${hint.lon}-${i}`"
              class="px-2.5 py-1.5 cursor-pointer transition-colors"
              :class="i === hintIndex ? 'bg-brand/20' : 'hover:bg-panel-2'"
              @mousedown.prevent="choose(hint)"
              @mouseenter="hintIndex = i"
            >
              <span class="text-[12.5px]">{{ hint.title }}</span>
              <span class="block text-[10.5px] text-muted leading-snug">
                {{ hint.subtitle }}
              </span>
            </li>
          </ul>
        </div>

        <label class="col-span-2 flex flex-col gap-1">
          <span class="text-[11px] text-muted">
            Координаты
            <b v-if="!parsed && coords" class="text-crit font-normal">
              — нужны две: широта и долгота
            </b>
          </span>
          <div class="flex gap-1.5">
            <input
              v-model="coords"
              placeholder="55.690000, 37.720000"
              class="num flex-1 px-2 py-1.5 rounded-lg border text-[13px] focus:outline-none focus:border-brand-deep"
              :class="coords && !parsed ? 'border-crit' : 'border-hair-2'"
            />
            <button
              class="px-2.5 rounded-lg border border-hair-2 text-[12px] text-muted hover:text-ink hover:bg-panel-2 transition-colors cursor-pointer"
              @click="pickOnMap"
            >
              На карте
            </button>
          </div>
        </label>
      </div>

      <p v-if="error" class="mt-2 text-[12px] text-crit">{{ error }}</p>

      <div class="flex items-center gap-2 mt-3">
        <button
          class="flex-1 px-3 py-2 rounded-lg bg-crit text-white text-[13px] font-semibold cursor-pointer hover:brightness-110 transition disabled:opacity-40 disabled:cursor-default"
          :disabled="!ready || busy"
          @click="submit"
        >
          {{ busy ? "Пересчитываем…" : "Добавить и пересчитать" }}
        </button>
        <button
          class="px-3 py-2 rounded-lg border border-hair-2 text-[12.5px] text-muted hover:text-ink hover:bg-panel-2 transition-colors cursor-pointer"
          @click="emit('close')"
        >
          Отмена
        </button>
      </div>
    </div>
  </div>
</template>
