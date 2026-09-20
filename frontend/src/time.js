export function toMinutes(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  return d.getHours() * 60 + d.getMinutes();
}

export function hhmm(v) {
  const m = typeof v === "number" ? v : toMinutes(v);
  if (m == null) return "—";
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
}
