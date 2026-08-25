export function money(v: number, currency: string) {
  try {
    return new Intl.NumberFormat(currency === "INR" ? "en-IN" : "en-US", { style: "currency", currency, maximumFractionDigits: 0 }).format(v);
  } catch {
    return `${currency} ${Math.round(v).toLocaleString()}`;
  }
}
export const num = (v: number, d = 1) => v.toLocaleString(undefined, { maximumFractionDigits: d });
