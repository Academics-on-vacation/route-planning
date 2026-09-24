"""
Вторая фаза: улучшение готового плана перестановками.
"""

from __future__ import annotations

from ..models.domain import Engeneer, Stop, Ticket

# Веса целевой функции.
W_DROP = 10_000  # нераспределённая заявка
W_ENGINEER = 2_000  # бригада, выехавшая в этот день (хоть один визит)
W_LATE = 10  # минута работы после закрытия окна
W_KM = 15  # километр пробега
W_IDLE = 3  # минута ожидания окна
W_DELAY = 0.5  # минута промедления со срочной заявкой, на единицу срочности

# Приоритет обычной заявки. Меньше значение — выше приоритет, поэтому
# срочность считается делением: 10 -> 10x, 50 -> 2x, 100 -> 1x.
BASE_PRIORITY = 100


def urgency(ticket: Ticket) -> float:
    """
    Во сколько раз заявка важнее обычной.

    Нужна в двух местах: отказаться от аварии должно быть в разы дороже,
    чем от локальных работ, и тянуть с ней до вечера — тоже.
    """
    return BASE_PRIORITY / max(1, getattr(ticket, "priority", None) or BASE_PRIORITY)


def schedule(
    eng: Engeneer, tickets: list[Ticket], leg, max_leg_min: int | None = None
) -> tuple[list[Stop], float] | None:
    """
    Цена маршрута
    """
    where, now = eng.start_point, eng.work_shift_start_minutes
    stops: list[Stop] = []
    cost = 0.0

    for ticket in tickets:
        minutes, km = leg(where, ticket.point, eng.transport, now)
        arrive = now + minutes
        start = max(arrive, ticket.work_start)
        end = start + ticket.duration_minutes

        if max_leg_min is not None and minutes > max_leg_min:
            return None
        if start > ticket.work_finish or end > eng.work_shift_end_minutes:
            return None

        stops.append(Stop(ticket, now, arrive, start, end, minutes, km))
        cost += W_KM * km + W_IDLE * (start - arrive) + W_LATE * max(0, end - ticket.work_finish)
        cost += W_DELAY * (urgency(ticket) - 1) * max(0, start - ticket.work_start)
        where, now = ticket.point, end

    return stops, cost


def improve(
    plan_tickets: dict[int, list[Ticket]],
    dropped: list[Ticket],
    engineers: list[Engeneer],
    leg,
    max_leg_min: int | None = None,
    max_rounds: int = 12,
) -> tuple[dict[int, list[Ticket]], list[Ticket], dict]:
    """
    Улучшать, пока улучшается.
    """
    by_id = {e.id: e for e in engineers}
    order = dict(plan_tickets)
    dropped = list(dropped)

    def opening(eng_id: int) -> float:
        """Сколько стоит поднять бригаду"""
        return 0.0 if by_id[eng_id].deployed else W_ENGINEER

    # Кэш цен маршрутов: за один проход один и тот же маршрут пересчитывается десятки раз.
    cache: dict[tuple, float | None] = {}

    def price(eng_id: int, tickets: list[Ticket]) -> float | None:
        key = (eng_id, tuple(t.id for t in tickets))
        if key not in cache:
            got = schedule(by_id[eng_id], tickets, leg, max_leg_min)
            cache[key] = None if got is None else got[1]
        return cache[key]

    def cost_of(plan: dict[int, list[Ticket]], unplaced: int) -> float:
        """Цена всего дня: маршруты + отказы + выехавшие бригады."""
        return (
            sum(price(e, ts) or 0 for e, ts in plan.items())
            + W_DROP * sum(urgency(t) for t in unplaced)
            + sum(opening(e) for e, ts in plan.items() if ts)
        )

    def total() -> float:
        return cost_of(order, dropped)

    moves = {"insert": 0, "relocate": 0, "swap": 0, "freed": 0}
    before = total()

    for _ in range(max_rounds):
        changed = False

        # 1. Пристроить нераспределённые — в любое место любого маршрута
        for ticket in list(dropped):
            best = None
            for eng_id, tickets in order.items():
                base = price(eng_id, tickets)
                if base is None:
                    continue
                for i in range(len(tickets) + 1):
                    candidate = tickets[:i] + [ticket] + tickets[i:]
                    got = price(eng_id, candidate)
                    if got is None:
                        continue
                    delta = got - base + (0 if tickets else opening(eng_id))
                    if best is None or delta < best[0]:
                        best = (delta, eng_id, candidate)
            # Заявка в плане всегда лучше заявки в отказе: W_DROP заведомо
            # больше любой разумной прибавки к цене маршрута. Для срочной
            # порог соответственно выше.
            if best and best[0] < W_DROP * urgency(ticket):
                order[best[1]] = best[2]
                dropped.remove(ticket)
                moves["insert"] += 1
                changed = True

        # 2. Перенос визита: вынуть из одного маршрута, вставить в другой
        for src in list(order):
            # Список берём свежий на каждом шаге
            tickets = order[src]
            for idx in range(len(tickets)):
                ticket = tickets[idx]
                without = tickets[:idx] + tickets[idx + 1 :]
                # Оба порядка должны быть выполнимы. Выбросить визит из середины — не всегда безобидно: между соседями
                # появляется новое длинное плечо, и оно может не влезть в потолок
                now_cost, cut_cost = price(src, tickets), price(src, without)
                if now_cost is None or cut_cost is None:
                    continue
                gain = now_cost - cut_cost
                # Последний визит уходит — бригада вообще не выезжает
                if not without:
                    gain += opening(src)
                best = None
                for dst, dst_tickets in order.items():
                    base = price(dst, without if dst == src else dst_tickets) or 0
                    pool = without if dst == src else dst_tickets
                    for i in range(len(pool) + 1):
                        if dst == src and i == idx:
                            continue
                        candidate = pool[:i] + [ticket] + pool[i:]
                        got = price(dst, candidate)
                        if got is None:
                            continue
                        delta = got - base
                        # Поднимать ради одного визита ещё одну бригаду дорого
                        if dst != src and not pool:
                            delta += opening(dst)
                        if best is None or delta < best[0]:
                            best = (delta, dst, candidate)
                if best and best[0] < gain - 1e-9:  # строго дешевле, чем было
                    order[src] = without
                    order[best[1]] = best[2]
                    moves["relocate"] += 1
                    changed = True
                    break  # список изменился, начинаем маршрут заново

        # 3. Обмен визитами между маршрутами
        ids = list(order)
        for a in ids:
            for b in ids:
                if a >= b:
                    continue
                for i, ta in enumerate(order[a]):
                    for j, tb in enumerate(order[b]):
                        na = order[a][:i] + [tb] + order[a][i + 1 :]
                        nb = order[b][:j] + [ta] + order[b][j + 1 :]
                        pa, pb = price(a, na), price(b, nb)
                        wa, wb = price(a, order[a]), price(b, order[b])
                        if None in (pa, pb, wa, wb):
                            continue
                        if pa + pb < wa + wb - 1e-9:
                            order[a], order[b] = na, nb
                            moves["swap"] += 1
                            changed = True
                            break
                    else:
                        continue
                    break

        # 4. Расформировать бригаду целиком
        for src in sorted(order, key=lambda k: len(order[k])):
            if not order[src]:
                continue
            trial = {k: list(v) for k, v in order.items()}
            trial[src] = []
            placed = True

            for ticket in order[src]:
                best = None
                for dst in trial:
                    if dst == src:
                        continue
                    base = price(dst, trial[dst])
                    if base is None:
                        continue
                    for i in range(len(trial[dst]) + 1):
                        candidate = trial[dst][:i] + [ticket] + trial[dst][i:]
                        got = price(dst, candidate)
                        if got is None:
                            continue
                        delta = got - base + (opening(dst) if not trial[dst] else 0)
                        if best is None or delta < best[0]:
                            best = (delta, dst, candidate)
                if best is None:
                    placed = False
                    break
                trial[best[1]] = best[2]

            if placed and cost_of(trial, dropped) < cost_of(order, dropped) - 1e-9:
                order = trial
                moves["freed"] += 1
                changed = True

        if not changed:
            break

    return order, dropped, {**moves, "cost_before": round(before), "cost_after": round(total())}
