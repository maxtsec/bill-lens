const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");
const vm = require("node:vm");

const comparisonSourceCode = readFileSync(
  path.join(__dirname, "../../bill_lens/api/static/comparison.js"),
  "utf8",
);
const source =
  comparisonSourceCode +
  "\n" +
  readFileSync(
    path.join(__dirname, "../../bill_lens/api/static/app.js"),
    "utf8",
  );

function setup() {
  function element() {
    return {
      value: "",
      textContent: "",
      hidden: false,
      get options() {
        return this.children;
      },
      children: [],
      listeners: {},
      addEventListener(name, callback) {
        this.listeners[name] = callback;
      },
      setAttribute() {},
      append(...nodes) {
        this.children.push(...nodes);
      },
      replaceChildren(...nodes) {
        this.children = nodes;
      },
    };
  }
  const nodes = new Map();
  const node = (id) => {
    if (!nodes.has(id)) nodes.set(id, element());
    return nodes.get(id);
  };
  const context = vm.createContext({
    document: { getElementById: node, createElement: element },
    window: { addEventListener() {}, scrollTo() {} },
    location: { hash: "", pathname: "/" },
    URLSearchParams,
    fetch: () => new Promise(() => {}),
  });
  vm.runInContext(source, context);
  return { context, node, run: (code) => vm.runInContext(code, context) };
}

test("network errors never expose transport details", async () => {
  const { context, run } = setup();
  context.fetch = async () => {
    throw new Error("private proxy/path/token");
  };
  await assert.rejects(run("api('/bills')"), {
    message:
      "Could not connect to the API. Check your connection and try again.",
  });
});

for (const status of [200, 502]) {
  test(`non-JSON response ${status} has a safe message`, async () => {
    const { context, run } = setup();
    context.fetch = async () => ({
      ok: status === 200,
      status,
      json: async () => {
        throw new Error("<html>internal diagnostics</html>");
      },
    });
    await assert.rejects(run("api('/bills')"), {
      message:
        status === 200
          ? "The API returned an unexpected response. Please try again."
          : "The request could not be completed (502). Please try again.",
    });
  });
}

test("known API errors are translated; unknown and inherited keys are not displayed", async () => {
  const { context, run } = setup();
  for (const error of ["private server error", "__proto__", "toString"]) {
    context.fetch = async () => ({
      ok: false,
      status: 500,
      json: async () => ({ error }),
    });
    await assert.rejects(run("api('/bills')"), {
      message: "The request could not be completed (500). Please try again.",
    });
  }
  context.fetch = async () => ({
    ok: false,
    status: 422,
    json: async () => ({ error: "invalid_request" }),
  });
  await assert.rejects(run("api('/bills')"), {
    message:
      "Some fields are invalid. Check the dates, numbers and reviewer name.",
  });
});

test("a refresh reads bills and all summary counts with one request", async () => {
  const { context, node, run } = setup();
  const calls = [];
  node("review-filter").value = "pending";
  context.fetch = async (url) => {
    calls.push(url);
    return {
      ok: true,
      json: async () => ({
        total: 0,
        items: [],
        counts: { all: 3, reviewed: 3, pending: 0 },
      }),
    };
  };
  await run("loadList()");
  assert.deepEqual(calls, ["/bills?limit=20&offset=0&review_state=pending"]);
  assert.equal(node("count-all").textContent, 3);
  assert.equal(node("count-pending").textContent, 0);
  assert.equal(node("list-state").textContent, "No bills match these filters.");
});

test("empty failed extraction tells the reviewer it will save a confirmation", () => {
  const { node, run } = setup();
  run("current = {effective_fields:null}; updateChanges()");
  assert.equal(
    node("changes").textContent,
    "No values changed. Saving will record a confirmation.",
  );
  assert.equal(node("save-review").textContent, "Save review");
});

test("history uses the revision cursor and prevents overlapping loads", async () => {
  const { context, node, run } = setup();
  const calls = [];
  let finish;
  context.fetch = (url) => {
    calls.push(url);
    return new Promise((resolve) => {
      finish = resolve;
    });
  };
  run("current = {id:'bill-id'}");
  const pending = run("loadHistory()");
  await run("loadHistory()");
  assert.equal(calls.length, 1);
  const review = (revision) => ({
    revision,
    action: "confirmed",
    reviewer: "Max",
    created_at: "2026-10-02T01:00:00Z",
    fields: {},
    review_flags: [],
  });
  finish({
    ok: true,
    json: async () => ({
      total: 3,
      items: [review(3), review(2)],
      next_before_revision: 2,
    }),
  });
  await pending;
  const next = run("loadHistory()");
  assert.equal(calls[1], "/bills/bill-id/reviews?limit=20&before_revision=2");
  finish({
    ok: true,
    json: async () => ({
      total: 4,
      items: [review(1)],
      next_before_revision: null,
    }),
  });
  await next;
  assert.equal(node("history").children.length, 3);
  assert.equal(node("more-history").hidden, true);
});

test("comparison requires two different bills and household acknowledgement", async () => {
  const { context, node, run } = setup();
  let calls = 0;
  context.fetch = () => {
    calls++;
    return new Promise(() => {});
  };
  node("baseline-bill").value = "one";
  node("comparison-bill").value = "one";
  node("same-household").checked = true;
  await run("runComparison()");
  node("comparison-bill").value = "two";
  node("same-household").checked = false;
  await run("runComparison()");
  assert.equal(calls, 0);
  node("same-household").checked = true;
  run("updateComparisonButton()");
  assert.equal(node("run-comparison").disabled, false);
  node("baseline-bill").listeners.change();
  assert.equal(node("same-household").checked, false);
  assert.equal(node("run-comparison").disabled, true);
});

test("obsolete comparison responses cannot replace a new selection", async () => {
  const { context, node, run } = setup();
  node("baseline-bill").value = "one";
  node("comparison-bill").value = "two";
  node("same-household").checked = true;
  let finish;
  context.fetch = () =>
    new Promise((resolve) => {
      finish = resolve;
    });
  const pending = run("runComparison()");
  node("comparison-bill").listeners.change();
  finish({ ok: true, json: async () => ({ obsolete: true }) });
  await pending;
  assert.equal(node("comparison-results").hidden, true);
  assert.equal(
    node("comparison-state").children[1].textContent,
    "See what changed",
  );
});

test("picker pages deduplicate options and preserve selection", async () => {
  const { context, node, run } = setup();
  const bill = (id) => ({
    id,
    effective_fields: {
      retailer: "Example",
      period_start: "2026-01-01",
      period_end: "2026-01-31",
    },
  });
  const calls = [];
  context.fetch = async (url) => {
    calls.push(url);
    return {
      ok: true,
      json: async () => ({
        items:
          calls.length === 1
            ? [bill("one"), bill("two")]
            : [bill("two"), bill("three")],
        total: 4,
        next_before_bill_id: calls.length === 1 ? "two" : null,
      }),
    };
  };
  await run("loadComparisonBills()");
  node("baseline-bill").value = "one";
  node("comparison-bill").value = "two";
  await run("loadComparisonBills(true)");
  assert.deepEqual(calls, [
    "/bills?review_state=reviewed&limit=100",
    "/bills?review_state=reviewed&limit=100&before_bill_id=two",
  ]);
  assert.equal(node("baseline-bill").options.length, 4);
  assert.equal(node("baseline-bill").value, "one");
  assert.equal(node("more-comparison-bills").hidden, true);
});

test("failed load more preserves the chosen pair and retries the same cursor", async () => {
  const { context, node, run } = setup();
  const calls = [];
  context.fetch = async (url) => {
    calls.push(url);
    if (calls.length === 2) throw new Error("offline");
    return {
      ok: true,
      json: async () => ({
        items: (calls.length === 1 ? ["one", "two"] : ["three"]).map((id) => ({
          id,
        })),
        next_before_bill_id: calls.length === 1 ? "two" : null,
      }),
    };
  };
  await run("loadComparisonBills()");
  node("baseline-bill").value = "one";
  node("comparison-bill").value = "two";
  node("same-household").checked = true;
  await run("loadComparisonBills(true)");
  assert.equal(node("baseline-bill").disabled, false);
  assert.equal(node("comparison-bill").disabled, false);
  assert.equal(node("run-comparison").disabled, false);
  assert.equal(node("more-comparison-bills").hidden, false);
  assert.match(node("compare-picker-state").textContent, /Could not connect/);
  assert.equal(node("baseline-bill").value, "one");
  assert.equal(node("comparison-bill").value, "two");
  await run("loadComparisonBills(true)");
  assert.equal(calls[1], calls[2]);
  assert.equal(node("baseline-bill").options.length, 4);
  assert.equal(node("more-comparison-bills").hidden, true);
});

test("failed initial picker load stays disabled until a successful refresh", async () => {
  const { context, node, run } = setup();
  context.fetch = async () => {
    throw new Error("offline");
  };
  await run("loadComparisonBills()");
  assert.equal(node("baseline-bill").disabled, true);
  assert.equal(node("run-comparison").disabled, true);
  context.fetch = async () => ({
    ok: true,
    json: async () => ({
      items: [{ id: "one" }, { id: "two" }],
      next_before_bill_id: null,
    }),
  });
  await run("loadComparisonBills()");
  assert.equal(node("baseline-bill").disabled, false);
  assert.equal(node("run-comparison").disabled, true);
});

test("comparison formats large decimals and tiny changes without binary floats", () => {
  const { run } = setup();
  assert.equal(
    run('comparisonNumber("100000000000000000000.01")'),
    "100,000,000,000,000,000,000.01",
  );
  assert.equal(run("comparisonNumber(null)"), "—");
  assert.equal(
    run(
      'comparisonDelta({delta:"0.00",direction:"increase",precision:2,unit:"AUD"})',
    ),
    "+<0.01 AUD",
  );
  assert.equal(run("comparisonDelta({delta:null})"), "Not comparable");
  assert.equal(
    run(
      'comparisonDelta({delta:"-9.00",direction:"decrease",precision:2,unit:"AUD"})',
    ),
    "−9.00 AUD",
  );
});
