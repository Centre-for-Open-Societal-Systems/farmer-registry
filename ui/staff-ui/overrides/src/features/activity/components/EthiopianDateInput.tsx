"use client";

import { useState } from "react";
import { EC_MONTHS, ecMonthDays, ecToGregorian, gregorianToEc } from "../utils/ethiopianCalendar";

interface Props {
    id: string;
    value?: string; // Gregorian YYYY-MM-DD
    onChange: (value: string | undefined) => void;
    disabled?: boolean;
}

/**
 * A date picker that lets the user enter a date in the Ethiopian calendar
 * (day / month / year) or the Gregorian one. The stored value is always the
 * Gregorian ISO date; the other calendar is shown alongside.
 */
export default function EthiopianDateInput({ id, value, onChange, disabled }: Props) {
    const [calendar, setCalendar] = useState<"EC" | "GC">("EC");
    // A partly entered Ethiopian date (e.g. year still being typed). Once it is a
    // valid date it is reported through onChange and the draft is dropped, so the
    // shown date always follows `value`.
    const [draft, setDraft] = useState<[number, number, number] | null>(null);
    const ec = draft ?? (value ? gregorianToEc(value) : null);

    const updateEc = (next: [number, number, number]) => {
        const [y, m, d] = next;
        const day = Math.min(d, ecMonthDays(y, m));
        if (y > 1900 && m && day) {
            setDraft(null);
            onChange(ecToGregorian(y, m, day));
        } else {
            setDraft([y, m, day]);
        }
    };

    const inputClass = "border border-secondary-second rounded-md px-2 py-1.5 bg-neutral-second text-sm";

    return (
        <div className="flex flex-col gap-1">
            <div className="flex items-center gap-2">
                {calendar === "EC" ? (
                    <>
                        <select
                            id={`${id}-day`}
                            aria-label="Day"
                            className={inputClass}
                            disabled={disabled}
                            value={ec?.[2] ?? ""}
                            onChange={(e) => updateEc([ec?.[0] ?? 2019, ec?.[1] ?? 1, Number(e.target.value)])}
                        >
                            <option value="">Day</option>
                            {Array.from({ length: 30 }, (_, i) => i + 1).map((d) => (
                                <option key={d} value={d}>{d}</option>
                            ))}
                        </select>
                        <select
                            id={`${id}-month`}
                            aria-label="Month"
                            className={inputClass}
                            disabled={disabled}
                            value={ec?.[1] ?? ""}
                            onChange={(e) => updateEc([ec?.[0] ?? 2019, Number(e.target.value), ec?.[2] ?? 1])}
                        >
                            <option value="">Month</option>
                            {EC_MONTHS.map((name, i) => (
                                <option key={name} value={i + 1}>{name}</option>
                            ))}
                        </select>
                        <input
                            id={`${id}-year`}
                            aria-label="Year"
                            type="number"
                            className={`${inputClass} w-24`}
                            disabled={disabled}
                            placeholder="Year"
                            value={ec?.[0] ?? ""}
                            onChange={(e) => updateEc([Number(e.target.value), ec?.[1] ?? 1, ec?.[2] ?? 1])}
                        />
                    </>
                ) : (
                    <input
                        id={id}
                        type="date"
                        className={inputClass}
                        disabled={disabled}
                        value={value ?? ""}
                        onChange={(e) => onChange(e.target.value || undefined)}
                    />
                )}
                <button
                    type="button"
                    className="text-xs underline text-primary-first"
                    onClick={() => setCalendar(calendar === "EC" ? "GC" : "EC")}
                >
                    {calendar === "EC" ? "Use Gregorian" : "Use Ethiopian"}
                </button>
            </div>
            {value && (
                <span className="text-xs opacity-70">
                    {calendar === "EC" ? `Gregorian: ${value}` : `Ethiopian: ${(() => {
                        const [y, m, d] = gregorianToEc(value);
                        return `${d} ${EC_MONTHS[m - 1]} ${y}`;
                    })()}`}
                </span>
            )}
        </div>
    );
}
