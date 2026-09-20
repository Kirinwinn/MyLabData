export const DISPLAY_LOCALE = "zh-CN";
export const EMPTY_VALUE = "—";

export interface DateTimeFormatOptions {
  locale?: string;
  timeZone?: string;
}

export function formatDateTime(
  value: string | Date | null | undefined,
  options: DateTimeFormatOptions = {},
) {
  if (value === null || value === undefined || value === "") return EMPTY_VALUE;
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return EMPTY_VALUE;

  return new Intl.DateTimeFormat(options.locale ?? DISPLAY_LOCALE, {
    dateStyle: "medium",
    timeStyle: "medium",
    hour12: false,
    timeZone: options.timeZone,
  }).format(date);
}

export function formatNumber(
  value: number | null | undefined,
  options: Intl.NumberFormatOptions = {},
) {
  if (value === null || value === undefined || !Number.isFinite(value)) return EMPTY_VALUE;
  return new Intl.NumberFormat(DISPLAY_LOCALE, {
    maximumFractionDigits: 6,
    ...options,
  }).format(value);
}

export function formatValueWithUnit(
  value: number | null | undefined,
  unit: string | null | undefined,
  options?: Intl.NumberFormatOptions,
) {
  const formatted = formatNumber(value, options);
  if (formatted === EMPTY_VALUE || !unit) return formatted;
  return `${formatted}\u00a0${unit}`;
}

export function formatBoolean(value: boolean | null | undefined) {
  if (value === null || value === undefined) return EMPTY_VALUE;
  return value ? "Yes" : "No";
}
