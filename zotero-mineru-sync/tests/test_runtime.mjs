import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const root = path.join(projectRoot, ".testdata", "runtime");
await fs.rm(root, { recursive: true, force: true });
await fs.mkdir(root, { recursive: true });
const prefs = new Map([
  ["extensions.zotero-mineru-sync.enabled", true],
  ["extensions.zotero-mineru-sync.command", "fake-sync"],
  ["extensions.zotero-mineru-sync.dataRoot", root],
  ["extensions.zotero-mineru-sync.cpu", true],
  ["extensions.zotero-mineru-sync.lastSummary", "未运行"]
]);
let timerCallback;
let notifier;
let processCount = 0;
const parent = (key, id) => ({ key, id, version: 1, parentItem: false, isRegularItem: () => true, getAttachments: () => [id + 100], getField: (field) => field === "language" ? "zh-CN" : "" });
const attachment = (key, id, parentKey) => ({ key, id, version: 2, parentKey, isAttachment: () => true, attachmentContentType: "application/pdf" });
const items = new Map([["P1", parent("P1", 1)], ["P2", parent("P2", 2)], ["A1", attachment("A1", 101, "P1")], ["A2", attachment("A2", 102, "P2")], [1, parent("P1", 1)], [2, parent("P2", 2)], [101, attachment("A1", 101, "P1")], [102, attachment("A2", 102, "P2")]]);
const library = { getItem: (key) => items.get(key), getChildItems: () => [items.get("P1"), items.get("P2")] };
const context = {
  console,
  setTimeout: (callback) => { timerCallback = callback; return 1; },
  clearTimeout: () => {},
  Services: {
    prefs: {
      PREF_INVALID: 0,
      getPrefType: (key) => prefs.has(key) ? 32 : 0,
      getBoolPref: (key) => prefs.get(key),
      getStringPref: (key) => prefs.get(key),
      getIntPref: (key) => prefs.get(key) ?? 0,
      setBoolPref: (key, value) => prefs.set(key, value),
      setStringPref: (key, value) => prefs.set(key, value),
      setIntPref: (key, value) => prefs.set(key, value),
      addObserver: () => {},
      removeObserver: () => {}
    },
    dirsvc: { get: () => ({ path: root }) }
  },
  Ci: { nsIFile: {} },
  Cc: {
    "@mozilla.org/process/util;1": {
      createInstance: () => ({
        init: () => {},
        runwAsync: async (args, _length, observer) => {
          processCount += 1;
          const request = JSON.parse(await fs.readFile(args[0], "utf8"));
          const resultPath = path.join(root, "results", `${request.request_id}.json`);
          await fs.mkdir(path.dirname(resultPath), { recursive: true });
          await fs.writeFile(resultPath, JSON.stringify({ status: "COMPLETED", counts: { SUCCESS: request.candidates.length } }));
          observer.observe(null, "process-finished", "0");
        }
      })
    }
  },
  IOUtils: {
    makeDirectory: (directory) => fs.mkdir(directory, { recursive: true }),
    writeUTF8: (file, value) => fs.writeFile(file, value, "utf8"),
    move: async (from, to) => { await fs.mkdir(path.dirname(to), { recursive: true }); await fs.rename(from, to); },
    readJSON: async (file) => JSON.parse(await fs.readFile(file, "utf8"))
  },
  PathUtils: { parent: (file) => path.dirname(file) },
  Zotero: {
    Libraries: { userLibraryID: 1, get: () => library },
    Items: {
      get: (id) => items.get(id),
      getIDFromLibraryAndKey: (_libraryId, key) => items.get(key)?.id,
      getAsync: async (ids) => ids.map((id) => items.get(id))
    },
    Search: class {
      constructor() { this.libraryID = null; }
      async search() { return [1, 2, 101, 102]; }
    },
    Duplicates: { getSets: () => [[1, 2]] },
    Notifier: { registerObserver: (observer) => { notifier = observer; }, unregisterObserver: () => {} },
    PreferencePanes: { register: () => {} },
    File: { pathToFile: (file) => file },
    getMainWindows: () => [],
    logError: (error) => { throw error; }
  }
};
vm.createContext(context);
const source = await fs.readFile(new URL("../zotero-plugin/runtime.js", import.meta.url), "utf8");
vm.runInContext(source, context);
await context.ZoteroMineruRuntime.startup({ id: "zotero-mineru-sync@local", version: "0.1.0", rootURI: "" });
assert.ok(timerCallback, "enabled startup should schedule a full scan");
await timerCallback();
assert.equal(processCount, 1);
const requestFiles = await fs.readdir(path.join(root, "requests"));
assert.equal(requestFiles.length, 1);
const request = JSON.parse(await fs.readFile(path.join(root, "requests", requestFiles[0]), "utf8"));
assert.equal(request.candidates.length, 0);
assert.equal(request.blocked_duplicates.length, 2);
assert.equal(request.library_id, "0");
assert.ok(notifier, "Zotero notifier should be registered");
items.delete("P2");
items.delete(2);
items.delete("A2");
items.delete(102);
notifier.notify("delete", "item", [2, 102]);
await timerCallback();
assert.equal(processCount, 2, "deletion should retrigger the affected parent");
const allRequests = (await fs.readdir(path.join(root, "requests"))).sort();
const mergedRequest = JSON.parse(await fs.readFile(path.join(root, "requests", allRequests.at(-1)), "utf8"));
assert.deepEqual(mergedRequest.candidates.map((item) => item.parent_item_key), ["P1"],
  "after a duplicate merge only the retained parent remains eligible");
assert.equal(mergedRequest.blocked_duplicates.length, 0);
context.ZoteroMineruRuntime.shutdown();
console.log("runtime integration simulation passed");
