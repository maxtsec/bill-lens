"use strict";
const $ = (id) => document.getElementById(id);
const labels = {
  retailer: "供應商",
  period_start: "期間開始",
  period_end: "期間結束",
  stated_billing_days: "列明日數",
  total_usage_kwh: "總用電量",
  daily_supply_rate: "每日供電費率",
  current_bill_amount: "本期費用",
};
const flags = {
  current_bill_amount_role_unconfirmed:
    "本期金額附近嘅標籤未能確認，請避免將應繳結餘當成本期費用。",
  current_bill_amount_not_printed: "未能喺 PDF 文字中找到本期金額。",
  total_usage_kwh_not_printed: "未能喺 PDF 文字中找到總用電量。",
  daily_supply_rate_not_printed: "未能喺 PDF 文字中找到每日供電費率。",
  stated_billing_days_not_printed: "未能喺 PDF 文字中找到列明日數。",
  retailer_not_printed: "未能喺 PDF 文字中找到供應商名稱。",
  current_bill_amount_missing: "未能確認本期費用。",
  daily_supply_rate_missing: "未能確認每日供電費率。",
  period_end_before_start: "結束日期早於開始日期。",
  period_end_missing: "未能確認期間結束日期。",
  period_start_missing: "未能確認期間開始日期。",
  retailer_missing: "未能確認供應商。",
  stated_days_mismatch: "列明日數與起止日期計算不一致。",
  supply_rate_gst_basis_unknown: "未能確認費率有冇包含 GST。",
  total_usage_kwh_missing: "未能確認總用電量。",
};
const errors = {
  review_conflict:
    "呢張帳單已有新版本。你嘅輸入仍然保留，請記低修改後按「重新載入」核對最新紀錄。",
  unsupported_fixture:
    "目前使用本地示範抽取器，只支援 dataset 入面 5 份原始測試 PDF。",
  invalid_request: "欄位格式不正確。請檢查日期、數值同覆核者名稱。",
  file_too_large: "檔案過大，PDF 上限為 10 MiB。",
  invalid_pdf_signature: "呢個檔案唔係有效 PDF。",
  pdf_not_found: "搵唔到已儲存嘅 PDF，請檢查本地檔案。",
  bill_not_found: "搵唔到呢張帳單。",
  pdf_integrity_error: "PDF 與原始檔案記錄不符，暫時無法儲存覆核。",
};
let offset = 0,
  total = 0,
  current = null,
  dirty = false,
  busy = false,
  historyOffset = 0,
  listGeneration = 0,
  detailGeneration = 0;
let previewGeneration = 0,
  previewPage = 1,
  previewCount = 0,
  previewUrl = null,
  lastHash = location.hash;
function element(tag, text, cls) {
  const e = document.createElement(tag);
  if (text !== undefined) e.textContent = text;
  if (cls) e.className = cls;
  return e;
}
function notice(message, error = false) {
  $("notice").textContent = message;
  $("notice").className = "notice" + (error ? " error" : "");
  $("notice").hidden = false;
}
async function api(path, options = {}) {
  const response = await fetch(path, { cache: "no-store", ...options });
  const body = await response.json();
  if (!response.ok)
    throw new Error(
      errors[body.error] || `操作未完成（${response.status}）。請稍後重試。`,
    );
  return body;
}
function badge(text, cls = "") {
  return element("span", text, "badge " + cls);
}
function machineBadge(status) {
  return badge(
    { processed: "自動檢查通過", needs_review: "有警告", failed: "抽取失敗" }[
      status
    ],
    { processed: "success", needs_review: "warning", failed: "failed" }[status],
  );
}
function reviewBadge(state) {
  return badge(
    state === "reviewed" ? "已覆核" : "待覆核",
    state === "reviewed" ? "success" : "warning",
  );
}
function display(value) {
  if (value === null || value === undefined) return "未能確認";
  if (typeof value === "object")
    return `${value.value} ${value.unit} · GST ${{ inclusive: "已包含", exclusive: "未包含", unknown: "未能確認" }[value.gst_basis]}`;
  return String(value);
}
function dateTime(value) {
  return new Date(value).toLocaleString("zh-HK", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}
async function loadList() {
  const generation = ++listGeneration;
  $("list-state").hidden = false;
  $("list-state").textContent = "正在載入帳單…";
  $("bill-rows").replaceChildren();
  $("previous").disabled = true;
  $("next").disabled = true;
  try {
    const query = new URLSearchParams({ limit: 20, offset });
    if ($("review-filter").value)
      query.set("review_state", $("review-filter").value);
    if ($("status-filter").value) query.set("status", $("status-filter").value);
    const [page, all, pending, reviewed] = await Promise.all([
      api(`/bills?${query}`),
      api("/bills?limit=1"),
      api("/bills?limit=1&review_state=pending"),
      api("/bills?limit=1&review_state=reviewed"),
    ]);
    if (generation !== listGeneration) return;
    total = page.total;
    if (offset && offset >= total) {
      offset = Math.max(0, Math.floor((total - 1) / 20) * 20);
      return loadList();
    }
    $("count-all").textContent = all.total;
    $("count-pending").textContent = pending.total;
    $("count-reviewed").textContent = reviewed.total;
    $("result-count").textContent = total;
    for (const bill of page.items) {
      const fields = bill.effective_fields || {};
      const tr = element("tr");
      const retailer = element("td", fields.retailer || "未能確認供應商");
      retailer.append(
        element(
          "small",
          `${bill.id.slice(0, 8)} · ${bill.review ? "人工覆核版本" : "原始抽取版本"}`,
        ),
      );
      tr.append(
        retailer,
        element(
          "td",
          `${fields.period_start || "—"} → ${fields.period_end || "—"}`,
        ),
        element(
          "td",
          fields.current_bill_amount === null ||
            fields.current_bill_amount === undefined
            ? "—"
            : `$ ${fields.current_bill_amount}`,
          "amount",
        ),
      );
      const auto = element("td");
      auto.append(machineBadge(bill.status));
      const reviewed = element("td");
      reviewed.append(reviewBadge(bill.review_state));
      const open = element("button", "檢視 →", "row-open");
      open.setAttribute(
        "aria-label",
        `檢視 ${fields.retailer || bill.id} 帳單`,
      );
      open.addEventListener("click", () => navigate(bill.id));
      const action = element("td");
      action.append(open);
      tr.append(auto, reviewed, action);
      $("bill-rows").append(tr);
    }
    $("list-state").hidden = page.items.length > 0;
    $("list-state").textContent = all.total
      ? "冇符合篩選條件嘅帳單。"
      : "未有帳單。上傳第一份測試 PDF，開始核對。";
    $("page-label").textContent = total
      ? `${offset + 1}–${Math.min(offset + 20, total)} / ${total} 張帳單`
      : "0 張帳單";
    $("previous").disabled = offset === 0;
    $("next").disabled = offset + 20 >= total;
  } catch (error) {
    if (generation !== listGeneration) return;
    $("list-state").textContent =
      "未能載入帳單，請確認本地 API 同資料庫已啟動，再按重新整理。";
    notice(error.message, true);
  }
}
function readFields() {
  const result = {};
  for (const key of Object.keys(labels)) {
    if (key === "daily_supply_rate") continue;
    const v = $(key).value.trim();
    result[key] =
      v === "" ? null : key === "stated_billing_days" ? Number(v) : v;
  }
  const value = $("rate_value").value.trim();
  result.daily_supply_rate = value
    ? { value, unit: $("rate_unit").value, gst_basis: $("rate_gst").value }
    : null;
  return result;
}
function changedKeys(fields, baseline) {
  return Object.keys(labels).filter(
    (key) =>
      JSON.stringify(fields[key]) !== JSON.stringify(baseline?.[key] ?? null),
  );
}
function updateChanges() {
  if (!current) return;
  const changed = changedKeys(readFields(), current.effective_fields);
  $("changes").textContent = changed.length
    ? `今次修改：${changed.map((key) => labels[key]).join("、")}`
    : "數值未有修改，儲存將記錄為確認。";
  $("save-review").textContent = changed.length
    ? "儲存修正並完成覆核"
    : "確認並儲存覆核";
}
function fillDetail(bill) {
  current = bill;
  dirty = false;
  $("detail-title").textContent =
    bill.effective_fields?.retailer || "未能確認供應商";
  $("detail-subtitle").textContent =
    `帳單 ${bill.id.slice(0, 8)} · 上傳於 ${dateTime(bill.created_at)}`;
  $("detail-badges").replaceChildren(
    machineBadge(bill.status),
    reviewBadge(bill.review_state),
  );
  $("pdf-link").href = `/bills/${bill.id}/pdf`;
  loadPreview(bill.id, 1);
  const fields = bill.effective_fields || {};
  for (const key of Object.keys(labels)) {
    if (key !== "daily_supply_rate") $(key).value = fields[key] ?? "";
    document.querySelector(`[data-original="${key}"]`).textContent =
      `原始抽取：${display(bill.fields?.[key])}`;
  }
  $("rate_value").value = fields.daily_supply_rate?.value ?? "";
  $("rate_unit").value = fields.daily_supply_rate?.unit || "cents/day";
  $("rate_gst").value = fields.daily_supply_rate?.gst_basis || "unknown";
  $("note").value = "";
  $("acknowledged").checked = false;
  const activeFlags = bill.review ? bill.review.review_flags : bill.flags;
  $("flags").replaceChildren();
  $("flags").className =
    "flags" + (activeFlags.length || bill.status === "failed" ? "" : " clear");
  $("flags").append(
    element(
      "strong",
      bill.review ? "覆核版本嘅自動提示" : "原始抽取嘅自動提示",
    ),
  );
  if (bill.status === "failed")
    $("flags").append(
      element(
        "p",
        "自動抽取失敗。你可以對照 PDF 手動填寫；原始失敗紀錄會保留。",
      ),
    );
  if (activeFlags.length) {
    const ul = element("ul");
    for (const flag of activeFlags)
      ul.append(element("li", flags[flag] || flag));
    $("flags").append(ul);
  } else
    $("flags").append(
      element("p", "未發現自動檢查警告，仍請對照原始帳單核實。"),
    );
  if (bill.review)
    $("flags").append(
      element(
        "p",
        `最近覆核：${bill.review.reviewer} · 第 ${bill.review.revision} 版。原始警告：${bill.flags.length} 項。`,
      ),
    );
  updateChanges();
}
async function loadDetail(id) {
  const generation = ++detailGeneration;
  current = null;
  $("review-form").inert = true;
  try {
    const bill = await api(`/bills/${id}/detail`);
    if (generation !== detailGeneration) return;
    fillDetail(bill);
    $("review-form").inert = false;
    historyOffset = 0;
    $("history").replaceChildren();
    await loadHistory(id, generation);
  } catch (error) {
    if (generation === detailGeneration) notice(error.message, true);
  }
}
async function loadPreview(id, page) {
  const generation = ++previewGeneration;
  $("preview-state").hidden = false;
  $("preview-state").textContent = "正在載入預覽…";
  $("pdf-preview").hidden = true;
  $("pdf-previous").disabled = true;
  $("pdf-next").disabled = true;
  try {
    const response = await fetch(`/bills/${id}/preview/${page}`, {
      cache: "no-store",
    });
    if (!response.ok)
      throw new Error("無法產生預覽，請使用「開啟 PDF」查看原文。");
    const blob = await response.blob();
    if (generation !== previewGeneration || current?.id !== id) return;
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = URL.createObjectURL(blob);
    $("pdf-preview").src = previewUrl;
    $("pdf-preview").alt = `原始帳單第 ${page} 頁`;
    $("pdf-preview").hidden = false;
    $("preview-state").hidden = true;
    previewPage = page;
    previewCount = Number(response.headers.get("X-Page-Count"));
    $("pdf-page-label").textContent = `${page} / ${previewCount}`;
    $("pdf-previous").disabled = page <= 1;
    $("pdf-next").disabled = page >= previewCount;
  } catch (error) {
    if (generation === previewGeneration)
      $("preview-state").textContent = error.message;
  }
}
async function loadHistory(id = current?.id, generation = detailGeneration) {
  if (!id) return;
  $("more-history").disabled = true;
  try {
    const page = await api(
      `/bills/${id}/reviews?limit=20&offset=${historyOffset}`,
    );
    if (generation !== detailGeneration) return;
    $("history-count").textContent = `${page.total} 次覆核`;
    if (!page.total)
      $("history").append(element("div", "未有覆核紀錄。", "empty-state"));
    for (const review of page.items) {
      const entry = element("article", undefined, "history-entry");
      const header = element("header");
      header.append(
        element("strong", `第 ${review.revision} 版`),
        badge(review.action === "corrected" ? "修正" : "確認"),
        element("span", review.reviewer),
        element("time", dateTime(review.created_at)),
      );
      entry.append(header);
      if (review.note) entry.append(element("p", review.note));
      const details = element("details");
      details.append(element("summary", "查看當時數值與警告"));
      const dl = element("dl");
      for (const [key, label] of Object.entries(labels))
        dl.append(
          element("dt", label),
          element("dd", display(review.fields[key])),
        );
      details.append(
        dl,
        element(
          "p",
          review.review_flags.length
            ? review.review_flags.map((f) => flags[f] || f).join("\n")
            : "當時無自動檢查警告。",
        ),
      );
      entry.append(details);
      $("history").append(entry);
    }
    historyOffset += page.items.length;
    $("more-history").hidden = historyOffset >= page.total;
  } catch (error) {
    notice(error.message, true);
  } finally {
    $("more-history").disabled = false;
  }
}
function navigate(id) {
  if (busy) return;
  if (dirty && !confirm("未儲存嘅修改會失去，要離開嗎？")) return;
  dirty = false;
  location.hash = id ? `bill/${id}` : "";
}
function route() {
  if (busy || (dirty && !confirm("未儲存嘅修改會失去，要離開嗎？"))) {
    history.replaceState(null, "", location.pathname + lastHash);
    return;
  }
  dirty = false;
  lastHash = location.hash;
  const match = location.hash.match(/^#bill\/([0-9a-f-]{36})$/i);
  $("notice").hidden = true;
  $("list-view").hidden = !!match;
  $("detail-view").hidden = !match;
  if (match) loadDetail(match[1]);
  else {
    ++detailGeneration;
    ++previewGeneration;
    current = null;
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
      previewUrl = null;
    }
    loadList();
  }
}
$("review-form").addEventListener("input", () => {
  dirty = true;
  updateChanges();
});
$("review-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!current || busy) return;
  const id = current.id;
  busy = true;
  $("save-review").disabled = true;
  $("review-form").inert = true;
  try {
    await api(`/bills/${id}/reviews`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source_run_id: current.run.id,
        expected_review_id: current.latest_review_id,
        fields: readFields(),
        reviewer: $("reviewer").value.trim(),
        note: $("note").value,
        acknowledged: $("acknowledged").checked,
      }),
    });
    dirty = false;
    await loadDetail(id);
    notice("覆核已儲存。原始抽取結果保留不變。");
  } catch (error) {
    notice(error.message, true);
  } finally {
    busy = false;
    $("save-review").disabled = false;
    $("review-form").inert = false;
  }
});
$("back").addEventListener("click", () => navigate(null));
$("reload-detail").addEventListener("click", () => {
  if (!busy && (!dirty || confirm("重新載入會清除未儲存修改，繼續嗎？")))
    loadDetail(current?.id || location.hash.slice(6));
});
$("more-history").addEventListener("click", () => loadHistory());
$("previous").addEventListener("click", () => {
  offset = Math.max(0, offset - 20);
  loadList();
});
$("next").addEventListener("click", () => {
  offset += 20;
  loadList();
});
for (const id of ["review-filter", "status-filter"])
  $(id).addEventListener("change", () => {
    offset = 0;
    loadList();
  });
$("refresh").addEventListener("click", () => loadList());
$("upload").addEventListener("click", () => $("upload-file").click());
$("pdf-previous").addEventListener("click", () => {
  if (current && previewPage > 1) loadPreview(current.id, previewPage - 1);
});
$("pdf-next").addEventListener("click", () => {
  if (current && previewPage < previewCount)
    loadPreview(current.id, previewPage + 1);
});
$("upload-file").addEventListener("change", async () => {
  const file = $("upload-file").files[0];
  if (!file) return;
  if (file.size > 10 * 1024 * 1024) {
    notice(errors.file_too_large, true);
    $("upload-file").value = "";
    return;
  }
  $("upload").disabled = true;
  $("upload").textContent = "上傳中…";
  try {
    const form = new FormData();
    form.append("file", file);
    const bill = await api("/bills", { method: "POST", body: form });
    navigate(bill.id);
  } catch (error) {
    notice(error.message, true);
  } finally {
    $("upload").disabled = false;
    $("upload").textContent = "＋ 上傳帳單";
    $("upload-file").value = "";
  }
});
window.addEventListener("beforeunload", (event) => {
  if (dirty || busy) {
    event.preventDefault();
    event.returnValue = "";
  }
});
window.addEventListener("hashchange", route);
route();
