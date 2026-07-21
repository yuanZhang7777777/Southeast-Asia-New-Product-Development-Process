import { useEffect, useMemo, useRef, useState } from "react";

import { api, SecondaryResearchGroup } from "./api";
import { createRequestGate, summarySalespersonScope } from "./listingObservation";
import { resolveImageUrl } from "./SecondaryResearchView";

export function SecondaryResearchSummary(props: {
  mainSku: string;
  country?: string | null;
  currentBusinessPeriod?: string | null;
  role: "operator" | "manager";
  operatorName: string;
  canManage: boolean;
}) {
  const [groups, setGroups] = useState<SecondaryResearchGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const requestGate = useRef(createRequestGate());

  useEffect(() => {
    const requestId = requestGate.current.start();
    setLoading(true);
    setError("");
    void api.secondaryResearch(
      summarySalespersonScope(props.role, props.canManage, props.operatorName) || "",
      "__all__",
      ""
    ).then((response) => {
      if (requestGate.current.isCurrent(requestId)) setGroups(response);
    }).catch((reason) => {
      if (requestGate.current.isCurrent(requestId)) {
        setError(reason instanceof Error ? reason.message : "二次调研历史加载失败");
      }
    }).finally(() => {
      if (requestGate.current.isCurrent(requestId)) setLoading(false);
    });
  }, [props.mainSku, props.country, props.role, props.operatorName, props.canManage]);

  const visibleGroups = useMemo(() => groups.flatMap((group) => {
    if (group.main_sku !== props.mainSku || (props.country && group.country !== props.country)) return [];
    const items = group.items.filter((item) => item.secondary_research_submitted_at);
    return items.length ? [{ ...group, items }] : [];
  }).sort((left, right) =>
    Number(right.business_period === props.currentBusinessPeriod)
      - Number(left.business_period === props.currentBusinessPeriod)
      || (right.business_period || "").localeCompare(left.business_period || "")
      || left.salesperson_name.localeCompare(right.salesperson_name)
  ), [groups, props.country, props.currentBusinessPeriod, props.mainSku]);

  if (loading) return <p className="muted detail-empty">正在加载二次调研历史...</p>;
  if (error) return <p className="muted detail-empty">{error}</p>;
  if (!visibleGroups.length) return <p className="muted detail-empty">暂无已提交的二次调研记录。</p>;

  return (
    <div className="secondary-summary-readonly">
      {visibleGroups.map((group, index) => (
        <details key={group.key} open={index === 0}>
          <summary>
            {group.business_period || "未标记业务期"} · {group.salesperson_name} · {group.items.length} 个子 SKU
          </summary>
          <div className="secondary-summary-items">
            {group.items.map((item) => (
              <article className="secondary-summary-item" key={item.claim_record_id}>
                <header>
                  <div>
                    <b>{item.sub_sku}</b>
                    <span>{item.sub_sku_name || "未填写子 SKU 名称"}</span>
                  </div>
                  <span className="pill green">{item.product_positioning || "未填写定位"}</span>
                </header>
                <dl>
                  <div><dt>调研时间</dt><dd>{dateTimeText(item.secondary_research_at)}</dd></div>
                  <div><dt>提交时间</dt><dd>{dateTimeText(item.secondary_research_submitted_at)}</dd></div>
                  <div><dt>竞品链接</dt><dd>{item.secondary_competitor_url
                    ? <a href={item.secondary_competitor_url} target="_blank" rel="noreferrer">打开竞品链接</a>
                    : "-"}</dd></div>
                  <div className="secondary-summary-conclusion"><dt>调研结论</dt><dd>{item.secondary_conclusion || "-"}</dd></div>
                </dl>
                {item.secondary_evidence_images.length > 0 && (
                  <div className="secondary-summary-images">
                    {item.secondary_evidence_images.map((image, imageIndex) => (
                      <a href={resolveImageUrl(image.url)} target="_blank" rel="noreferrer" key={`${image.url}-${imageIndex}`}>
                        <img src={resolveImageUrl(image.url)} alt={image.name || `${item.sub_sku} 调研图片`} />
                      </a>
                    ))}
                  </div>
                )}
              </article>
            ))}
          </div>
        </details>
      ))}
    </div>
  );
}

function dateTimeText(value?: string | null) {
  return value?.slice(0, 16).replace("T", " ") || "-";
}
