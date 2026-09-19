<script setup>
/**
 * Левая панель. Три взгляда на одни и те же данные:
 *
 *   Бригады   — план глазами исполнителя, по маршрутам;
 *   Заявки    — план глазами диспетчера, по времени;
 *   Не назн.  — то, что алгоритм не смог разложить, с причиной.
 *
 * Вкладка не сбрасывает выделение: заявка, выбранная в списке заявок,
 * остаётся выбранной и в бригадах — просто видна в другом контексте.
 */

import { computed, ref, watch } from 'vue'

import { useSelection } from '../composables/useSelection.js'
import { SKILL_TITLES } from '../store/plan.js'
import { hhmm } from '../utils/time.js'
import RequestDetail from './RequestDetail.vue'

const {
  store,
  select,
  hover,
  focusEngineer,
  isSelected,
  isHovered,
  isFocused,
  isDimmed,
  registerNode,
} = useSelection('list')

const tab = ref('crews')
const query = ref('')

const unassignedList = computed(() => store.plan?.unassigned ?? [])

const tabs = computed(() => [
  { key: 'crews', title: 'Бригады', count: store.activeRoutes.length },
  { key: 'requests', title: 'Заявки', count: store.requestList.length },
  { key: 'unassigned', title: 'Не назн.', count: unassignedList.value.length },
])

/** Заявки по времени начала работы: так их читает диспетчер. */
const orderedRequests = computed(() => {
  const q = query.value.trim().toLowerCase()
  const rows = store.requestList.filter(
    (r) =>
      !q ||
      String(r.id).includes(q) ||
      (r.district ?? '').toLowerCase().includes(q) ||
      (r.address ?? '').toLowerCase().includes(q),
  )
  return rows.sort((a, b) => {
    const pa = store.stopIndex[String(a.id)]
    const pb = store.stopIndex[String(b.id)]
    // Назначенные — по факту приезда, остальные — по началу окна.
    const ka = pa ? pa.stop.start_at : a.window_start
    const kb = pb ? pb.stop.start_at : b.window_start
    return ka < kb ? -1 : ka > kb ? 1 : 0
  })
})

/**
 * Какие маршруты раскрыты. Два повода: инженер подсвечен целиком
 * (focusEngineer) или в нём лежит выбранная заявка.
 *
 * Второй повод — не то же самое, что первый, и связывать их нельзя.
 * Если клик по заявке будет ставить focusedEngineer, карта и Гант
 * погасят все остальные маршруты, а именно на них и смотрят, когда
 * решают, кому заявку передать.
 */
const openEngineers = computed(() => {
  const set = new Set()
  if (store.focusedEngineerId != null) set.add(String(store.focusedEngineerId))
  const own = store.engineerOfRequest(store.selectedRequestId)
  if (own != null) set.add(String(own))
  return set
})

const isOpen = (engineerId) => openEngineers.value.has(String(engineerId))

// Заявку выбрали на карте, а она не разложена — показываем её там,
// где видно причину. Из вкладки «Заявки» не уводим: человек уже там,
// где хотел быть.
watch(
  () => store.selectedRequestId,
  (id) => {
    if (id == null || tab.value !== 'crews') return
    if (store.engineerOfRequest(id) == null) tab.value = 'unassigned'
  },
)

const skillLetter = { local: 'Л', install: 'П', emergency: 'А' }
const skillClass = {
  local: 'border-accent/40 text-accent bg-accent/8',
  install: 'border-hair-2 text-muted bg-panel-2',
  emergency: 'border-crit/40 text-crit bg-crit/8',
}
</script>

<template>
  <aside class="panel flex flex-col min-h-0">
    <!-- Вкладки -->
    <div class="flex-none flex border-b border-hair bg-panel-2">
      <button
        v-for="t in tabs"
        :key="t.key"
        class="flex-1 px-2 py-2 text-[12px] border-b-2 -mb-px transition-colors"
        :class="
          tab === t.key
            ? 'border-ink text-ink font-medium bg-panel'
            : 'border-transparent text-muted hover:text-ink'
        "
        @click="tab = t.key"
      >
        {{ t.title }}
        <span class="num text-[10.5px] text-muted">{{ t.count }}</span>
      </button>
    </div>

    <!-- ------------------------------------------------------ Бригады -->
    <div v-if="tab === 'crews'" class="scrolly">
      <div
        v-if="!store.activeRoutes.length"
        class="px-3 py-6 text-center text-[12px] text-muted"
      >
        План пуст
      </div>

      <section
        v-for="route in store.activeRoutes"
        :key="route.engineer_id"
        class="border-b border-hair last:border-b-0"
        :class="isDimmed(route.engineer_id) ? 'opacity-45' : ''"
      >
        <button
          class="w-full flex items-center gap-2 px-2.5 py-2 text-left hover:bg-panel-2
                 transition-colors"
          :class="isFocused(route.engineer_id) ? 'bg-panel-2' : ''"
          @click="focusEngineer(route.engineer_id)"
        >
          <span
            class="w-1 self-stretch rounded-full shrink-0"
            :style="{ background: store.colorByEngineer[String(route.engineer_id)] }"
          />
          <span class="min-w-0 flex-1">
            <span class="block font-medium truncate">{{ route.engineer_name }}</span>
            <span class="num block text-[11px] text-muted">
              {{ route.stops.length }} зв · {{ route.distance_km?.toFixed(0) }} км ·
              до {{ hhmm(route.finish_at) }}
            </span>
          </span>
          <svg
            viewBox="0 0 10 10"
            class="w-2.5 h-2.5 text-muted shrink-0 transition-transform"
            :class="isOpen(route.engineer_id) ? 'rotate-90' : ''"
          >
            <path d="M3 1 L7 5 L3 9" stroke="currentColor" stroke-width="1.6" fill="none" />
          </svg>
        </button>

        <ol v-if="isOpen(route.engineer_id)" class="pb-1">
          <li
            v-for="stop in route.stops"
            :key="stop.request_id"
            :ref="(el) => registerNode(stop.request_id, el)"
          >
            <button
              class="w-full flex items-baseline gap-2 pl-5 pr-2.5 py-1 text-left
                     border-l-2 transition-colors"
              :class="
                isSelected(stop.request_id)
                  ? 'bg-ink text-white border-ink'
                  : isHovered(stop.request_id)
                    ? 'bg-panel-2 border-hair-2'
                    : 'border-transparent hover:bg-panel-2'
              "
              @click="select(stop.request_id)"
              @mouseenter="hover(stop.request_id)"
              @mouseleave="hover(null)"
            >
              <span class="num w-8 shrink-0 opacity-70">{{ hhmm(stop.start_at) }}</span>
              <span class="num shrink-0">{{ stop.request_id }}</span>
              <span class="text-[11px] truncate opacity-70">
                {{ store.requests[String(stop.request_id)]?.district ?? '' }}
              </span>
              <span
                v-if="stop.wait_min > 15"
                class="num ml-auto shrink-0 text-[10.5px]"
                :class="isSelected(stop.request_id) ? 'text-white/60' : 'text-warn'"
                :title="`Простой перед визитом ${stop.wait_min} мин`"
              >
                +{{ stop.wait_min }}
              </span>
            </button>
          </li>
        </ol>
      </section>
    </div>

    <!-- ------------------------------------------------------ Заявки -->
    <template v-else-if="tab === 'requests'">
      <div class="flex-none px-2 py-1.5 border-b border-hair">
        <input
          v-model="query"
          type="search"
          placeholder="Номер, район, адрес"
          class="w-full px-2 py-1 text-[12px] bg-panel-2 border border-hair rounded
                 outline-none focus:border-hair-2 focus:bg-panel"
        />
      </div>

      <ul class="scrolly">
        <li
          v-for="r in orderedRequests"
          :key="r.id"
          :ref="(el) => registerNode(r.id, el)"
        >
          <button
            class="w-full flex items-center gap-2 px-2.5 py-1.5 text-left border-b
                   border-hair/60 transition-colors"
            :class="
              isSelected(r.id)
                ? 'bg-ink text-white'
                : isHovered(r.id)
                  ? 'bg-panel-2'
                  : 'hover:bg-panel-2'
            "
            @click="select(r.id)"
            @mouseenter="hover(r.id)"
            @mouseleave="hover(null)"
          >
            <!-- Назначенная — заливка цветом исполнителя, не назначенная —
                 пустой кружок в обводке: тот же знак, что и на карте. -->
            <span
              class="w-2 h-2 rounded-full shrink-0"
              :class="store.stopIndex[String(r.id)] ? '' : 'ring-2 ring-crit'"
              :style="{
                background: store.stopIndex[String(r.id)]
                  ? store.colorByEngineer[String(store.engineerOfRequest(r.id))]
                  : '#fff',
              }"
            />
            <span class="min-w-0 flex-1">
              <span class="num block">{{ r.id }}</span>
              <span class="block text-[11px] truncate opacity-70">
                {{ r.district ?? r.address ?? '—' }}
              </span>
            </span>
            <span class="text-right shrink-0">
              <span class="num block text-[11px]">
                {{ hhmm(r.window_start) }}–{{ hhmm(r.window_end) }}
              </span>
              <span
                class="num block text-[10.5px]"
                :class="isSelected(r.id) ? 'text-white/70' : 'text-muted'"
              >
                {{
                  store.stopIndex[String(r.id)]
                    ? `приезд ${hhmm(store.stopIndex[String(r.id)].stop.start_at)}`
                    : 'не назначена'
                }}
              </span>
            </span>
            <span
              class="chip shrink-0"
              :class="isSelected(r.id) ? 'border-white/30 text-white' : skillClass[r.skill]"
              :title="SKILL_TITLES[r.skill] ?? r.skill"
            >
              {{ skillLetter[r.skill] ?? '?' }}
            </span>
          </button>
        </li>
      </ul>
    </template>

    <!-- ------------------------------------------------- Не назначено -->
    <ul v-else class="scrolly">
      <li
        v-if="!unassignedList.length"
        class="px-3 py-6 text-center text-[12px] text-muted"
      >
        Все заявки разложены
      </li>
      <li
        v-for="u in unassignedList"
        :key="u.request_id"
        :ref="(el) => registerNode(u.request_id, el)"
      >
        <button
          class="w-full px-2.5 py-2 text-left border-b border-hair/60 transition-colors"
          :class="isSelected(u.request_id) ? 'bg-ink text-white' : 'hover:bg-panel-2'"
          @click="select(u.request_id)"
          @mouseenter="hover(u.request_id)"
          @mouseleave="hover(null)"
        >
          <span class="flex items-baseline gap-2">
            <span class="num">{{ u.request_id }}</span>
            <span class="num text-[11px] opacity-70">
              {{ hhmm(store.requests[String(u.request_id)]?.window_start) }}–{{
                hhmm(store.requests[String(u.request_id)]?.window_end)
              }}
            </span>
          </span>
          <span
            class="block text-[11px] mt-0.5"
            :class="isSelected(u.request_id) ? 'text-white/70' : 'text-crit'"
          >
            {{ u.reason_text ?? u.reason }}
          </span>
        </button>
      </li>
    </ul>

    <RequestDetail />
  </aside>
</template>
