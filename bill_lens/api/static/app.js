"use strict";
const $ = (id) => document.getElementById(id);
const labels = {
  retailer: "Retailer",
  period_start: "Period start",
  period_end: "Period end",
  stated_billing_days: "Stated days",
  total_usage_kwh: "Total usage",
  daily_supply_rate: "Daily supply rate",
  current_bill_amount: "Current charges",
};
const flags = {
  current_bill_amount_role_unconfirmed:
    "The label near this amount could not be confirmed. Check that this is the current-period total, not the account balance due.",
  current_bill_amount_not_printed:
    "The current-period amount was not found in the PDF text.",
  total_usage_kwh_not_printed: "The total usage was not found in the PDF text.",
  daily_supply_rate_not_printed:
    "The daily supply rate was not found in the PDF text.",
  stated_billing_days_not_printed:
    "The stated billing days were not found in the PDF text.",
  retailer_not_printed: "The retailer name was not found in the PDF text.",
  current_bill_amount_missing:
    "The current-period charges could not be confirmed.",
  daily_supply_rate_missing: "The daily supply rate could not be confirmed.",
  period_end_before_start: "The end date is before the start date.",
  period_end_missing: "The period end date could not be confirmed.",
  period_start_missing: "The period start date could not be confirmed.",
  retailer_missing: "The retailer could not be confirmed.",
  stated_days_mismatch:
    "The stated billing days do not match the start and end dates.",
  supply_rate_gst_basis_unknown: "It is unclear whether the rate includes GST.",
  total_usage_kwh_missing: "The total usage could not be confirmed.",
};
const errors = {
  review_conflict:
    "This bill has a newer version. Your input is still here. Note your changes, then select Reload to reconcile them with the latest record.",
  unsupported_fixture:
    "The local demo extractor supports only the five original sample PDFs in the dataset folder.",
  invalid_request:
    "Some fields are invalid. Check the dates, numbers and reviewer name.",
  file_too_large: "The PDF is too large. The limit is 10 MiB.",
  invalid_pdf_signature: "This file is not a valid PDF.",
  pdf_not_found: "The saved PDF was not found. Check the local file.",
  bill_not_found: "This bill was not found.",
  pdf_integrity_error:
    "The PDF does not match the original file record. The review cannot be saved.",
};
let offset = 0,
  total = 0,
  current = null,
  dirty = false,
  busy = false,
  historyCursor = null,
  historyLoadingGeneration = null,
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
  let response;
  try {
    response = await fetch(path, { cache: "no-store", ...options });
  } catch {
    throw new Error(
      "Could not connect to the API. Check your connection and try again.",
    );
  }
  const fallback = response.ok
    ? "The API returned an unexpected response. Please try again."
    : `The request could not be completed (${response.status}). Please try again.`;
  let body;
  try {
    body = await response.json();
  } catch {
    throw new Error(fallback);
  }
  if (!response.ok)
    throw new Error(
      body && Object.hasOwn(errors, body.error) ? errors[body.error] : fallback,
    );
  if (!body || typeof body !== "object" || Array.isArray(body))
    throw new Error(fallback);
  return body;
}
function badge(text, cls = "") {
  return element("span", text, "badge " + cls);
}
function machineBadge(status) {
  return badge(
    {
      processed: "Checks passed",
      needs_review: "Warnings",
      failed: "Extraction failed",
    }[status],
    { processed: "success", needs_review: "warning", failed: "failed" }[status],
  );
}
function reviewBadge(state) {
  return badge(
    state === "reviewed" ? "Reviewed" : "Pending",
    state === "reviewed" ? "success" : "warning",
  );
}
function display(value) {
  if (value === null || value === undefined) return "Not confirmed";
  if (typeof value === "object")
    return `${value.value} ${value.unit} · GST ${{ inclusive: "inclusive", exclusive: "exclusive", unknown: "Not confirmed" }[value.gst_basis]}`;
  return String(value);
}
function dateTime(value) {
  return new Date(value).toLocaleString("en-AU", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}
async function loadList() {
  const generation = ++listGeneration;
  $("list-state").hidden = false;
  $("list-state").textContent = "Loading bills…";
  $("bill-rows").replaceChildren();
  $("previous").disabled = true;
  $("next").disabled = true;
  try {
    const query = new URLSearchParams({ limit: 20, offset });
    if ($("review-filter").value)
      query.set("review_state", $("review-filter").value);
    if ($("status-filter").value) query.set("status", $("status-filter").value);
    const page = await api(`/bills?${query}`);
    if (generation !== listGeneration) return;
    total = page.total;
    if (offset && offset >= total) {
      offset = Math.max(0, Math.floor((total - 1) / 20) * 20);
      return loadList();
    }
    $("count-all").textContent = page.counts.all;
    $("count-pending").textContent = page.counts.pending;
    $("count-reviewed").textContent = page.counts.reviewed;
    $("result-count").textContent = total;
    for (const bill of page.items) {
      const fields = bill.effective_fields || {};
      const tr = element("tr");
      const retailer = element(
        "td",
        fields.retailer || "Retailer not confirmed",
      );
      retailer.append(
        element(
          "small",
          `${bill.id.slice(0, 8)} · ${bill.review ? "Reviewed values" : "Original extraction"}`,
        ),
      );
      const period = element("td", undefined, "period");
      period.append(
        element("span", fields.period_start || "—"),
        element("span", `to ${fields.period_end || "—"}`),
      );
      tr.append(
        retailer,
        period,
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
      const open = element("button", "Review →", "row-open");
      open.setAttribute(
        "aria-label",
        `View bill from ${fields.retailer || bill.id}`,
      );
      open.addEventListener("click", () => navigate(bill.id));
      const action = element("td");
      action.append(open);
      tr.append(auto, reviewed, action);
      [
        "Retailer",
        "Billing period",
        "Amount · AUD",
        "Checks",
        "Review",
        "",
      ].forEach((label, index) => {
        tr.children[index].dataset.label = label;
      });
      $("bill-rows").append(tr);
    }
    $("list-state").hidden = page.items.length > 0;
    $("list-state").textContent = page.counts.all
      ? "No bills match these filters."
      : "No bills yet. Upload a sample PDF to get started.";
    $("page-label").textContent = total
      ? `${offset + 1}–${Math.min(offset + 20, total)} / ${total} bills`
      : "0 bills";
    $("previous").disabled = offset === 0;
    $("next").disabled = offset + 20 >= total;
  } catch (error) {
    if (generation !== listGeneration) return;
    $("list-state").textContent =
      "Could not load bills. Check that the local API and database are running, then select Refresh.";
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
    ? `Changes: ${changed.map((key) => labels[key]).join(", ")}`
    : "No values changed. Saving will record a confirmation.";
  $("save-review").textContent = changed.length
    ? "Save changes and review"
    : "Save review";
}
function fillDetail(bill) {
  current = bill;
  dirty = false;
  $("detail-title").textContent =
    bill.effective_fields?.retailer || "Retailer not confirmed";
  $("detail-subtitle").textContent =
    `Bill ${bill.id.slice(0, 8)} · Uploaded ${dateTime(bill.created_at)}`;
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
      `Originally extracted: ${display(bill.fields?.[key])}`;
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
  const checkDetails = element("details");
  checkDetails.open = activeFlags.length > 0 || bill.status === "failed";
  checkDetails.append(
    element(
      "summary",
      bill.status === "failed"
        ? "Extraction needs attention"
        : activeFlags.length
          ? `${activeFlags.length} automated ${activeFlags.length === 1 ? "warning" : "warnings"}`
          : "No automated warnings",
    ),
  );
  $("flags").append(checkDetails);
  checkDetails.append(
    element(
      "p",
      bill.review
        ? "Automated checks on reviewed values"
        : "Automated checks on the original extraction",
    ),
  );
  if (bill.status === "failed")
    checkDetails.append(
      element(
        "p",
        "Extraction failed. You can enter values manually using the PDF. The original failure record will be preserved.",
      ),
    );
  if (activeFlags.length) {
    const ul = element("ul");
    for (const flag of activeFlags)
      ul.append(element("li", flags[flag] || flag));
    checkDetails.append(ul);
  } else
    checkDetails.append(
      element(
        "p",
        "No automated warnings. Please still check the original bill.",
      ),
    );
  if (bill.review)
    checkDetails.append(
      element(
        "p",
        `Last reviewed by ${bill.review.reviewer} · Revision ${bill.review.revision}. Original warnings: ${bill.flags.length}.`,
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
    historyCursor = null;
    $("history").replaceChildren();
    await loadHistory(id, generation);
  } catch (error) {
    if (generation === detailGeneration) notice(error.message, true);
  }
}
async function loadPreview(id, page) {
  const generation = ++previewGeneration;
  $("preview-state").hidden = false;
  $("preview-state").textContent = "Loading preview…";
  $("pdf-preview").hidden = true;
  $("pdf-previous").disabled = true;
  $("pdf-next").disabled = true;
  try {
    const response = await fetch(`/bills/${id}/preview/${page}`, {
      cache: "no-store",
    });
    if (!response.ok)
      throw new Error(
        "Preview unavailable. Select Open PDF to view the original.",
      );
    const blob = await response.blob();
    if (generation !== previewGeneration || current?.id !== id) return;
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = URL.createObjectURL(blob);
    $("pdf-preview").src = previewUrl;
    $("pdf-preview").alt = `Original bill, page ${page}`;
    $("pdf-preview").hidden = false;
    $("preview-state").hidden = true;
    previewPage = page;
    previewCount = Number(response.headers.get("X-Page-Count"));
    $("pdf-page-label").textContent = `${page} / ${previewCount}`;
    $("pdf-previous").disabled = page <= 1;
    $("pdf-next").disabled = page >= previewCount;
  } catch (error) {
    if (generation === previewGeneration)
      $("preview-state").textContent =
        "Preview unavailable. Select Open PDF to view the original.";
  }
}
async function loadHistory(id = current?.id, generation = detailGeneration) {
  if (!id || historyLoadingGeneration === generation) return;
  historyLoadingGeneration = generation;
  $("more-history").disabled = true;
  try {
    const query = new URLSearchParams({ limit: 20 });
    if (historyCursor !== null) query.set("before_revision", historyCursor);
    const page = await api(`/bills/${id}/reviews?${query}`);
    if (generation !== detailGeneration) return;
    $("history-count").textContent = `${page.total} review records`;
    if (!page.total)
      $("history").append(element("div", "No reviews yet.", "empty-state"));
    for (const review of page.items) {
      const entry = element("article", undefined, "history-entry");
      const header = element("header");
      header.append(
        element("strong", `Revision ${review.revision}`),
        badge(review.action === "corrected" ? "Correction" : "Confirmation"),
        element("span", review.reviewer),
        element("time", dateTime(review.created_at)),
      );
      entry.append(header);
      if (review.note) entry.append(element("p", review.note));
      const details = element("details");
      details.append(element("summary", "View saved values and warnings"));
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
            : "No automated warnings at the time of review.",
        ),
      );
      entry.append(details);
      $("history").append(entry);
    }
    historyCursor = page.next_before_revision;
    $("more-history").hidden = historyCursor === null;
  } catch (error) {
    if (generation === detailGeneration) notice(error.message, true);
  } finally {
    if (historyLoadingGeneration === generation) {
      historyLoadingGeneration = null;
      $("more-history").disabled = false;
    }
  }
}
function navigate(id) {
  if (busy) return;
  if (dirty && !confirm("You have unsaved changes. Leave without saving?"))
    return;
  dirty = false;
  location.hash = id ? `bill/${id}` : "";
}
function route() {
  if (
    busy ||
    (dirty && !confirm("You have unsaved changes. Leave without saving?"))
  ) {
    history.replaceState(null, "", location.pathname + lastHash);
    return;
  }
  dirty = false;
  lastHash = location.hash;
  const match = location.hash.match(/^#bill\/([0-9a-f-]{36})$/i);
  $("notice").hidden = true;
  $("list-view").hidden = !!match;
  $("detail-view").hidden = !match;
  window.scrollTo({ top: 0, left: 0, behavior: "instant" });
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
$("show-original").addEventListener("change", () => {
  $("review-form").classList.toggle(
    "show-original",
    $("show-original").checked,
  );
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
    notice("Review saved. The original extraction has been preserved.");
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
  if (
    !busy &&
    (!dirty || confirm("Reloading will discard unsaved changes. Continue?"))
  )
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
  $("upload").textContent = "Uploading…";
  try {
    const form = new FormData();
    form.append("file", file);
    const bill = await api("/bills", { method: "POST", body: form });
    navigate(bill.id);
  } catch (error) {
    notice(error.message, true);
  } finally {
    $("upload").disabled = false;
    $("upload").textContent = "+ Upload bill";
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
