const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");
const vm = require("node:vm");

const source = readFileSync(
  path.join(__dirname, "../../bill_lens/api/static/app.js"),
  "utf8",
);

function setup() {
  function element() {
    return {
      value: "",
      textContent: "",
      hidden: false,
      children: [],
      addEventListener() {},
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
