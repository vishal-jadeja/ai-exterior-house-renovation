export function money(v: number, currency: string) {
  try {
    return new Intl.NumberFormat(currency === "INR" ? "en-IN" : "en-US", { style: "currency", currency, maximumFractionDigits: 0 }).format(v);
  } catch {
    return `${currency} ${Math.round(v).toLocaleString()}`;
  }
}
export const num = (v: number, d = 1) => v.toLocaleString(undefined, { maximumFractionDigits: d });

/** Status-line colour: errors red, progress/info grey. Messages come from the API or our own copy. */
export function msgClass(msg: string): string {
  return /fail|error|could not|must|try again|changed|first|too |not /i.test(msg) ? "text-red-600" : "text-zinc-600";
}
