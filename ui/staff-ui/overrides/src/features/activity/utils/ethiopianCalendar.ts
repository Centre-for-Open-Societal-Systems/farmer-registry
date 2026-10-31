/**
 * Ethiopian (Amete Mihret) <-> Gregorian conversion, the same algorithm as the
 * server (openg2p_registry_core.helpers.ethiopian_calendar): via the Julian Day
 * Number, epoch 1 Meskerem 1 EC = JDN 1724221. Year Y is a leap year when
 * Y % 4 === 3 (Pagume then has 6 days).
 */
const EPOCH = 1724221;
const UNIX_EPOCH_JDN = 2440588; // 1970-01-01

export const EC_MONTHS = [
    "Meskerem", "Tikimt", "Hidar", "Tahsas", "Tir", "Yekatit",
    "Megabit", "Miyazia", "Ginbot", "Sene", "Hamle", "Nehase", "Pagume",
];

export function isEcLeapYear(year: number): boolean {
    return year % 4 === 3;
}

export function ecMonthDays(year: number, month: number): number {
    return month <= 12 ? 30 : isEcLeapYear(year) ? 6 : 5;
}

export function ecToJdn(year: number, month: number, day: number): number {
    return EPOCH + 365 * (year - 1) + Math.floor(year / 4) + 30 * (month - 1) + day - 1;
}

export function jdnToEc(jdn: number): [number, number, number] {
    const offset = jdn - EPOCH;
    const cycle = Math.floor(offset / 1461);
    const remainder = offset - cycle * 1461;
    const starts = [0, 365, 730, 1096];
    let yearInCycle = 0;
    starts.forEach((start, i) => { if (remainder >= start) yearInCycle = i; });
    const dayOfYear = remainder - starts[yearInCycle];
    return [4 * cycle + yearInCycle + 1, Math.floor(dayOfYear / 30) + 1, (dayOfYear % 30) + 1];
}

/** "YYYY-MM-DD" Gregorian -> [year, month, day] Ethiopian. */
export function gregorianToEc(iso: string): [number, number, number] {
    const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
    const jdn = Math.floor(Date.UTC(y, m - 1, d) / 86400000) + UNIX_EPOCH_JDN;
    return jdnToEc(jdn);
}

/** Ethiopian date -> "YYYY-MM-DD" Gregorian. */
export function ecToGregorian(year: number, month: number, day: number): string {
    const ms = (ecToJdn(year, month, day) - UNIX_EPOCH_JDN) * 86400000;
    return new Date(ms).toISOString().slice(0, 10);
}

export function formatEc(iso?: string | null): string {
    if (!iso) return "";
    const [y, m, d] = gregorianToEc(iso);
    return `${d} ${EC_MONTHS[m - 1]} ${y}`;
}

export function ecIso(iso?: string | null): string {
    if (!iso) return "";
    const [y, m, d] = gregorianToEc(iso);
    return `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
}
