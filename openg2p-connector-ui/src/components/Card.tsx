import type { ReactNode } from "react";

interface Props {
  title?: string;
  subtitle?: string;
  children: ReactNode;
  className?: string;
}

export default function Card({ title, subtitle, children, className = "" }: Props) {
  return (
    <section className={`bg-white rounded-lg border border-[#d9d5c5] shadow-sm ${className}`}>
      {title && (
        <div className="px-5 py-3 border-b border-[#e8e5d9]">
          <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">{title}</h2>
          {subtitle && <p className="mt-1 text-xs text-gray-500 normal-case tracking-normal">{subtitle}</p>}
        </div>
      )}
      <div className="px-5 py-4">{children}</div>
    </section>
  );
}
