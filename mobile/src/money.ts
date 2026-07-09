// Price formatting shared by the menu listing and the dish detail.
// Symbols for the currencies the backend seeds; anything unknown falls back
// to its ISO code. Zero-decimal currencies never show cents; the rest drop
// them when the amount is whole ("€9.50", "120 Kč", "¥1200").

import { Money } from "./api";

const SYMBOL_BEFORE: Record<string, string> = {
  EUR: "€",
  USD: "$",
  GBP: "£",
  JPY: "¥",
  CNY: "¥",
  KRW: "₩",
  THB: "฿",
  VND: "₫",
  INR: "₹",
  TRY: "₺",
  MXN: "$",
  BRL: "R$",
  CAD: "$",
  AUD: "$",
  NZD: "$",
};

const SYMBOL_AFTER: Record<string, string> = {
  CZK: "Kč",
  PLN: "zł",
  HUF: "Ft",
  CHF: "Fr",
  SEK: "kr",
  NOK: "kr",
  DKK: "kr",
  RON: "lei",
};

const NO_DECIMALS = new Set(["JPY", "KRW", "VND", "IDR", "HUF"]);

/** The bare currency symbol ("฿", "Kč") — used by the price-level meter so
 *  it counts in the menu's own money ("฿฿฿"). ISO code fallback. */
export function currencySymbol(currency: string | null | undefined): string {
  if (!currency) return "€";
  return SYMBOL_BEFORE[currency] ?? SYMBOL_AFTER[currency] ?? currency;
}

export function fmtMoney(money: Money): string {
  const { amount, currency } = money;
  const wholes = NO_DECIMALS.has(currency) || Number.isInteger(amount);
  const num = wholes ? Math.round(amount).toString() : amount.toFixed(2);
  if (SYMBOL_BEFORE[currency]) return `${SYMBOL_BEFORE[currency]}${num}`;
  if (SYMBOL_AFTER[currency]) return `${num} ${SYMBOL_AFTER[currency]}`;
  return `${num} ${currency}`;
}
