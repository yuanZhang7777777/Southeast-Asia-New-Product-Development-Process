import assert from "node:assert/strict";
import test from "node:test";

import { productImageSrc } from "../src/imageSource.ts";

// node --test 下无 window，apiBase 回落默认值。
const API_BASE = "http://localhost:8000";

test("空 url 返回空串", () => {
  assert.equal(productImageSrc(""), "");
  assert.equal(productImageSrc(null), "");
  assert.equal(productImageSrc(undefined), "");
});

test("阿里云 OSS 直链改写为后端 /media/oss-image 代理", () => {
  const url = "https://hz-sea-np-flow-prod.oss-cn-shanghai.aliyuncs.com/product-images/history_selection1/row-3-abc.png";
  assert.equal(productImageSrc(url), `${API_BASE}/media/oss-image?src=${encodeURIComponent(url)}`);
  const httpUrl = "http://other-bucket.oss-cn-hangzhou.aliyuncs.com/product-images/x.jpg";
  assert.equal(productImageSrc(httpUrl), `${API_BASE}/media/oss-image?src=${encodeURIComponent(httpUrl)}`);
});

test("本地 /uploaded-sources/ 前缀补 API base，其它 URL 原样返回", () => {
  assert.equal(
    productImageSrc("/uploaded-sources/product-images/selection1/row-9.png"),
    `${API_BASE}/uploaded-sources/product-images/selection1/row-9.png`
  );
  assert.equal(productImageSrc("https://example.com/pic.png"), "https://example.com/pic.png");
  // 路径里出现 aliyuncs.com 但 host 不是 OSS 的不改写。
  assert.equal(
    productImageSrc("https://example.com/x.aliyuncs.com/pic.png"),
    "https://example.com/x.aliyuncs.com/pic.png"
  );
});
