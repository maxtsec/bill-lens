"use strict";
let comparisonGeneration = 0,
  pickerGeneration = 0,
  pickerCursor = null;
let comparisonBillOptions = new Map();
let pickerLoading = false,
  comparisonLoading = false;

function cancelComparison() {
  ++comparisonGeneration;
  ++pickerGeneration;
  pickerLoading = false;
  comparisonLoading = false;
}

function clearComparison() {
  ++comparisonGeneration;
  comparisonLoading = false;
  $("comparison-results").hidden = true;
  $("comparison-state").hidden = false;
  $("comparison-state").replaceChildren(
    element("span", "⇄", "comparison-symbol"),
    element("h2", "See what changed"),
    element(
      "p",
      "Choose two reviewed bills for the same home to compare usage and charges.",
    ),
  );
  updateComparisonButton();
}

function updateComparisonButton() {
  const a = $("baseline-bill").value,
    b = $("comparison-bill").value;
  $("run-comparison").disabled =
    pickerLoading ||
    comparisonLoading ||
    $("baseline-bill").disabled ||
    $("comparison-bill").disabled ||
    !a ||
    !b ||
    a === b ||
    !$("same-household").checked;
  $("run-comparison").textContent = comparisonLoading
    ? "Comparing…"
    : "Compare bills →";
  $("swap-bills").disabled = pickerLoading || !a || !b || a === b;
  for (const [id, other] of [
    ["baseline-bill", b],
    ["comparison-bill", a],
  ]) {
    for (const option of $(id).options)
      option.disabled = !!option.value && option.value === other;
  }
}

function billOptionText(bill) {
  const fields = bill.effective_fields;
  return `${fields?.retailer || "Retailer not confirmed"} · ${fields?.period_start || "?"} to ${fields?.period_end || "?"} · ${bill.id.slice(0, 8)}`;
}

async function loadComparisonBills(append = false) {
  if (append && pickerLoading) return;
  const generation = ++pickerGeneration;
  clearComparison();
  pickerLoading = true;
  const selected = [$("baseline-bill").value, $("comparison-bill").value];
  if (!append) {
    pickerCursor = null;
    comparisonBillOptions.clear();
    $("same-household").checked = false;
  }
  for (const id of ["baseline-bill", "comparison-bill"]) $(id).disabled = true;
  $("more-comparison-bills").hidden = true;
  $("compare-picker-state").textContent = "Loading reviewed bills…";
  updateComparisonButton();
  try {
    const query = new URLSearchParams({
      review_state: "reviewed",
      limit: "100",
    });
    if (pickerCursor) query.set("before_bill_id", pickerCursor);
    const page = await api(`/bills?${query}`);
    if (generation !== pickerGeneration) return;
    for (const bill of page.items) comparisonBillOptions.set(bill.id, bill);
    pickerCursor = page.next_before_bill_id;
    for (const [index, id] of ["baseline-bill", "comparison-bill"].entries()) {
      const placeholder = element(
        "option",
        index ? "Select a bill to compare" : "Select a baseline bill",
      );
      placeholder.value = "";
      $(id).replaceChildren(placeholder);
      for (const bill of comparisonBillOptions.values()) {
        const option = element("option", billOptionText(bill));
        option.value = bill.id;
        $(id).append(option);
      }
      $(id).value = comparisonBillOptions.has(selected[index])
        ? selected[index]
        : "";
    }
    $("more-comparison-bills").hidden = !pickerCursor;
    $("compare-picker-state").textContent =
      comparisonBillOptions.size < 2
        ? "Review at least two bills to start a comparison."
        : `${comparisonBillOptions.size} reviewed bills available. Choose bills for the same home; retailer names alone do not identify a home.`;
    if (comparisonBillOptions.size < 2) {
      const link = element("a", "Review your bills →", "review-bills-link");
      link.href = "#";
      $("comparison-state").append(link);
    }
  } catch (error) {
    if (generation !== pickerGeneration) return;
    $("compare-picker-state").textContent = error.message;
    $("more-comparison-bills").hidden = !append;
  } finally {
    if (generation === pickerGeneration) {
      pickerLoading = false;
      for (const id of ["baseline-bill", "comparison-bill"])
        $(id).disabled = comparisonBillOptions.size < 2;
      updateComparisonButton();
    }
  }
}

function comparisonNumber(value) {
  if (value === null) return "—";
  const [integer, fraction] = value.split(".");
  return (
    integer.replace(/\B(?=(\d{3})+(?!\d))/g, ",") +
    (fraction === undefined ? "" : `.${fraction}`)
  );
}

function comparisonSource(bill, letter, days) {
  const card = element("article", undefined, "panel comparison-source");
  const header = element("div", undefined, "comparison-source-heading");
  header.append(
    element("span", letter, "bill-letter"),
    element(
      "span",
      letter === "A" ? "Baseline bill" : "Comparison bill",
      "muted small",
    ),
  );
  const link = element("a", "View bill ↗");
  link.href = `#bill/${bill.id}`;
  header.append(link);
  const fields = bill.effective_fields;
  card.append(
    header,
    element("h2", fields.retailer || "Retailer not confirmed"),
    element(
      "p",
      `${fields.period_start || "Date unconfirmed"} — ${fields.period_end || "Date unconfirmed"}`,
      "small muted",
    ),
    element(
      "p",
      `${days === null ? "Billing days need review" : `${days} days`} · Review ${bill.review.revision}`,
      "small muted",
    ),
  );
  const badges = element("div", undefined, "badges");
  badges.append(reviewBadge("reviewed"));
  if (bill.review.review_flags.length)
    badges.append(
      badge(`${bill.review.review_flags.length} warnings remain`, "warning"),
    );
  if (bill.status === "failed") badges.append(badge("Manual entry"));
  card.append(badges);
  return card;
}

function comparisonDelta(metric) {
  if (metric.delta === null) return "Not comparable";
  if (metric.direction === "unchanged") return "No change";
  const magnitude = metric.delta.replace(/^-/, "");
  const amount = /^0(?:\.0+)?$/.test(magnitude)
    ? `<${metric.precision ? `0.${"0".repeat(metric.precision - 1)}1` : "1"}`
    : comparisonNumber(magnitude);
  return `${metric.direction === "increase" ? "+" : "−"}${amount} ${metric.unit}`;
}

function renderComparison(result) {
  $("comparison-sources").replaceChildren(
    comparisonSource(result.baseline, "A", result.baseline_days),
    comparisonSource(result.comparison, "B", result.comparison_days),
  );
  $("comparison-warnings").replaceChildren();
  for (const warning of result.warnings)
    $("comparison-warnings").append(element("p", warning));
  $("comparison-warnings").hidden = !result.warnings.length;
  $("comparison-metrics").replaceChildren();
  for (const metric of result.metrics) {
    const card = element(
      "article",
      undefined,
      `panel comparison-metric ${metric.key === "daily_usage" ? "comparison-featured" : ""}`,
    );
    card.append(
      element("h3", metric.label),
      element("p", metric.unit, "metric-unit"),
    );
    const values = element("div", undefined, "comparison-values");
    for (const [letter, value] of [
      ["A", metric.baseline],
      ["B", metric.comparison],
    ]) {
      const column = element("div");
      column.append(
        element("span", letter, "small muted"),
        element("strong", comparisonNumber(value)),
      );
      if (metric.key === "supply_rate") {
        const rate = (letter === "A" ? result.baseline : result.comparison)
          .effective_fields.daily_supply_rate;
        column.append(
          element(
            "small",
            rate
              ? {
                  inclusive: "GST inclusive",
                  exclusive: "GST exclusive",
                  unknown: "GST not confirmed",
                }[rate.gst_basis]
              : "Rate not confirmed",
            "muted",
          ),
        );
      }
      values.append(column);
    }
    const change = element("div", undefined, "comparison-change");
    change.append(element("strong", comparisonDelta(metric)));
    if (metric.percent_change !== null) {
      const percent = metric.percent_change;
      const sign =
        metric.direction === "increase"
          ? "+"
          : metric.direction === "decrease"
            ? "−"
            : "";
      const magnitude = percent.replace(/^-/, "");
      change.append(
        element(
          "span",
          `${sign}${magnitude === "0.0" && metric.direction !== "unchanged" ? "<0.1" : magnitude}%`,
          "change-percent",
        ),
      );
    }
    card.append(values, change);
    if (metric.unavailable_reason || metric.percent_unavailable_reason)
      card.append(
        element(
          "p",
          metric.unavailable_reason || metric.percent_unavailable_reason,
          "metric-explanation",
        ),
      );
    card.append(element("p", metric.note, "metric-explanation"));
    $("comparison-metrics").append(card);
  }
  $("comparison-state").hidden = true;
  $("comparison-results").hidden = false;
}

async function runComparison() {
  const a = $("baseline-bill").value,
    b = $("comparison-bill").value;
  if (
    comparisonLoading ||
    pickerLoading ||
    !a ||
    !b ||
    a === b ||
    !$("same-household").checked
  )
    return;
  const generation = ++comparisonGeneration;
  comparisonLoading = true;
  $("comparison-results").hidden = true;
  $("comparison-state").hidden = false;
  $("comparison-state").replaceChildren(
    element("p", "Comparing the latest reviewed values…"),
  );
  updateComparisonButton();
  try {
    const query = new URLSearchParams({
      baseline_id: a,
      comparison_id: b,
      same_household: "true",
    });
    const result = await api(`/comparisons?${query}`);
    if (generation === comparisonGeneration) renderComparison(result);
  } catch (error) {
    if (generation === comparisonGeneration)
      $("comparison-state").replaceChildren(
        element("h2", "Comparison unavailable"),
        element("p", error.message),
      );
  } finally {
    if (generation === comparisonGeneration) {
      comparisonLoading = false;
      updateComparisonButton();
    }
  }
}

function initComparison() {
  $("compare-form").addEventListener("submit", (event) => {
    event.preventDefault();
    runComparison();
  });
  for (const id of ["baseline-bill", "comparison-bill"])
    $(id).addEventListener("change", () => {
      $("same-household").checked = false;
      clearComparison();
    });
  $("same-household").addEventListener("change", clearComparison);
  $("swap-bills").addEventListener("click", () => {
    const a = $("baseline-bill").value;
    $("baseline-bill").value = $("comparison-bill").value;
    $("comparison-bill").value = a;
    clearComparison();
  });
  $("refresh-comparison-bills").addEventListener("click", () =>
    loadComparisonBills(),
  );
  $("more-comparison-bills").addEventListener("click", () =>
    loadComparisonBills(true),
  );
}
