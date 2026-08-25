import { normalizeSiteText } from "./opportunityGroups.ts";

export type ManualProductRoute = "direct_secondary" | "initial_stocking" | "ready_to_list";
export type ManualCompetitorKey = "lowest" | "most_orders" | "new_arrival";

export type ManualCompetitorDraft = {
  url: string;
  price: string;
  monthly_sales: string;
};

export type ManualProductChildDraft = {
  sub_sku: string;
  sub_sku_name: string;
  target_daily_sales: string;
  reference_price: string;
  secondary_competitor_url: string;
  competitors: Record<ManualCompetitorKey, ManualCompetitorDraft>;
};

export type ManualProductDraft = {
  country: string;
  salesperson_name: string;
  business_period: string;
  main_sku: string;
  main_sku_name: string;
  keyword: string;
  children: ManualProductChildDraft[];
};

type ManualCompetitorPayload = {
  url: string | null;
  price: number | null;
  monthly_sales: number | null;
};

export type ManualProductEntryPayload = {
  country: string;
  salesperson_name: string | null;
  business_period: string | null;
  main_sku: string;
  main_sku_name: string | null;
  keyword: string | null;
  route: ManualProductRoute;
  children: Array<{
    sub_sku: string;
    sub_sku_name: string | null;
    target_daily_sales: number | null;
    reference_price: number | null;
    secondary_competitor_url: string | null;
    competitors: Partial<Record<ManualCompetitorKey, ManualCompetitorPayload>>;
  }>;
};

const COMPETITOR_KEYS: ManualCompetitorKey[] = ["lowest", "most_orders", "new_arrival"];
const CURRENCY_BY_SITE: Record<string, string> = {
  PH: "PHP",
  TH: "THB",
  VN: "VND",
  MY: "MYR",
  SG: "SGD",
  ID: "IDR"
};

function emptyCompetitor(): ManualCompetitorDraft {
  return { url: "", price: "", monthly_sales: "" };
}

export function emptyManualProductChild(): ManualProductChildDraft {
  return {
    sub_sku: "",
    sub_sku_name: "",
    target_daily_sales: "",
    reference_price: "",
    secondary_competitor_url: "",
    competitors: {
      lowest: emptyCompetitor(),
      most_orders: emptyCompetitor(),
      new_arrival: emptyCompetitor()
    }
  };
}

export function createManualProductDraft(
  country = "",
  salespersonName = "",
  businessPeriod = ""
): ManualProductDraft {
  return {
    country,
    salesperson_name: salespersonName,
    business_period: businessPeriod,
    main_sku: "",
    main_sku_name: "",
    keyword: "",
    children: [emptyManualProductChild()]
  };
}

export function manualProductCurrency(value?: string | null) {
  return CURRENCY_BY_SITE[normalizeSiteText(value)] || "";
}

function isNonNegativeNumber(value: string) {
  const text = value.trim();
  return !text || (Number.isFinite(Number(text)) && Number(text) >= 0);
}

function isHttpUrl(value: string) {
  const text = value.trim();
  if (!text) return true;
  try {
    const parsed = new URL(text);
    return (parsed.protocol === "http:" || parsed.protocol === "https:") && Boolean(parsed.hostname);
  } catch {
    return false;
  }
}

export function validateManualProductDraft(draft: ManualProductDraft, route: ManualProductRoute) {
  const errors: Record<string, string> = {};
  if (!draft.country.trim()) errors.country = "请选择国家";
  else if (!manualProductCurrency(draft.country)) errors.country = "暂不支持该国家/站点";
  if (!draft.salesperson_name.trim()) errors.salesperson_name = "请选择负责人";
  if (!draft.main_sku.trim()) errors.main_sku = "请填写主 SKU";
  if (!draft.children.length) errors.children = "至少添加一个子 SKU";

  const seen = new Set<string>();
  draft.children.forEach((child, index) => {
    const prefix = `children.${index}`;
    const subSku = child.sub_sku.trim().toLowerCase();
    if (!subSku) errors[`${prefix}.sub_sku`] = "请填写子 SKU";
    else if (seen.has(subSku)) errors[`${prefix}.sub_sku`] = "子 SKU 不能重复";
    else seen.add(subSku);

    const target = child.target_daily_sales.trim();
    if (route !== "direct_secondary" && (!target || !Number.isFinite(Number(target)) || Number(target) <= 0)) {
      errors[`${prefix}.target_daily_sales`] = route === "initial_stocking"
        ? "首次备货必须填写大于 0 的目标单销"
        : "可刊登必须填写大于 0 的目标单销";
    } else if (!isNonNegativeNumber(target)) {
      errors[`${prefix}.target_daily_sales`] = "目标单销必须是大于或等于 0 的数字";
    }
    if (!isNonNegativeNumber(child.reference_price)) {
      errors[`${prefix}.reference_price`] = "竞对参考售价必须是大于或等于 0 的数字";
    }
    if (!isHttpUrl(child.secondary_competitor_url)) {
      errors[`${prefix}.secondary_competitor_url`] = "请输入 http:// 或 https:// 开头的有效链接";
    }
    for (const key of COMPETITOR_KEYS) {
      const competitor = child.competitors[key];
      if (!isHttpUrl(competitor.url)) {
        errors[`${prefix}.competitors.${key}.url`] = "请输入 http:// 或 https:// 开头的有效链接";
      }
      if (!isNonNegativeNumber(competitor.price)) {
        errors[`${prefix}.competitors.${key}.price`] = "竞品售价必须是大于或等于 0 的数字";
      }
      if (!isNonNegativeNumber(competitor.monthly_sales)) {
        errors[`${prefix}.competitors.${key}.monthly_sales`] = "竞品月销必须是大于或等于 0 的数字";
      }
    }
  });
  return errors;
}

function optionalText(value: string) {
  return value.trim() || null;
}

function optionalNumber(value: string) {
  const text = value.trim();
  return text ? Number(text) : null;
}

export function buildManualProductPayload(
  draft: ManualProductDraft,
  route: ManualProductRoute
): ManualProductEntryPayload {
  return {
    country: draft.country.trim(),
    salesperson_name: optionalText(draft.salesperson_name),
    business_period: optionalText(draft.business_period),
    main_sku: draft.main_sku.trim(),
    main_sku_name: optionalText(draft.main_sku_name),
    keyword: optionalText(draft.keyword),
    route,
    children: draft.children.map((child) => {
      const competitors: Partial<Record<ManualCompetitorKey, ManualCompetitorPayload>> = {};
      for (const key of COMPETITOR_KEYS) {
        const competitor = child.competitors[key];
        if ([competitor.url, competitor.price, competitor.monthly_sales].some((value) => value.trim())) {
          competitors[key] = {
            url: optionalText(competitor.url),
            price: optionalNumber(competitor.price),
            monthly_sales: optionalNumber(competitor.monthly_sales)
          };
        }
      }
      return {
        sub_sku: child.sub_sku.trim(),
        sub_sku_name: optionalText(child.sub_sku_name),
        target_daily_sales: optionalNumber(child.target_daily_sales),
        reference_price: optionalNumber(child.reference_price),
        secondary_competitor_url: optionalText(child.secondary_competitor_url),
        competitors
      };
    })
  };
}
