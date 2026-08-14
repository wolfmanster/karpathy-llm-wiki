/* Classic-script runtime loaded by bootstrap.js through loadSubScript(). */

var ZoteroMineruRuntime = (() => {
  const PLUGIN_ID = "zotero-mineru-sync@local";
  const PREF_BRANCH = "extensions.zotero-mineru-sync.";
  const DELAY_MS = 15000;
  let state = null;
  let e2eHelperScope = null;

  function nativePath(path) {
    const value = String(path ?? "");
    return Services.appinfo?.OS === "WINNT" ? value.replaceAll("/", "\\\\") : value;
  }

  function joinPath(...parts) {
    if (PathUtils?.join) return PathUtils.join(...parts.map(nativePath));
    return parts.join("/");
  }

  function prefAdapter() {
    return {
      getBool(key, fallback) {
        try { return Services.prefs.getBoolPref(PREF_BRANCH + key); } catch (_) { return fallback; }
      },
      getString(key, fallback) {
        try { return Services.prefs.getStringPref(PREF_BRANCH + key); } catch (_) { return fallback; }
      },
      setBool(key, value) { Services.prefs.setBoolPref(PREF_BRANCH + key, Boolean(value)); },
      getInt(key, fallback) {
        try { return Services.prefs.getIntPref(PREF_BRANCH + key); } catch (_) { return fallback; }
      },
      setInt(key, value) { Services.prefs.setIntPref(PREF_BRANCH + key, Number(value) || 0); },
      setString(key, value) { Services.prefs.setStringPref(PREF_BRANCH + key, String(value ?? "")); }
    };
  }

  function dataRoot(settings) {
    if (String(settings.dataRoot || "").trim()) return nativePath(settings.dataRoot);
    throw new Error("Set a project-local Zotero-MinerU data root before enabling synchronization");
  }

  function atomicWrite(path, document) {
    const parent = PathUtils.parent(path);
    const temporary = `${path}.${Date.now()}-${Math.random().toString(16).slice(2)}.tmp`;
    return IOUtils.makeDirectory(parent, { createAncestors: true })
      .then(() => IOUtils.writeUTF8(temporary, `${JSON.stringify(document, null, 2)}\n`))
      .then(() => IOUtils.move(temporary, path, { noOverwrite: false }));
  }

  async function duplicateSets() {
    const legacyGetter = Zotero.Duplicates?.getSets;
    if (typeof legacyGetter === "function") {
      const raw = legacyGetter.call(Zotero.Duplicates) ?? [];
      return raw.map((set) => Array.from(set || []).map((item) => {
        if (typeof item === "string") return item;
        if (typeof item === "number") {
          const zoteroItem = Zotero.Items.get(item);
          state.duplicateIdToKey.set(String(item), zoteroItem?.key);
          return zoteroItem?.key;
        }
        if (item?.key) return item.key;
        if (item?.id) {
          const zoteroItem = Zotero.Items.get(item.id);
          state.duplicateIdToKey.set(String(item.id), zoteroItem?.key);
          return zoteroItem?.key;
        }
        return undefined;
      })).map((set) => [...new Set(set.filter(Boolean))]).filter((set) => set.length > 1);
    }

    // Zotero 7/9 exposes the detector as a constructor. Running its search
    // keeps duplicate semantics in Zotero instead of reimplementing them here.
    if (typeof Zotero.Duplicates === "function") {
      const detector = new Zotero.Duplicates(state.libraryId);
      const search = await detector.getSearchObject();
      const ids = await search.search();
      const groups = [];
      const seen = new Set();
      for (const id of ids || []) {
        const memberIds = detector.getSetItemsByItemID(id) || [];
        const keys = [...new Set(memberIds.map((memberId) => {
          const zoteroItem = Zotero.Items.get(memberId);
          state.duplicateIdToKey.set(String(memberId), zoteroItem?.key);
          return zoteroItem?.key;
        }).filter(Boolean))];
        if (keys.length < 2) continue;
        const signature = [...keys].sort().join("\u0000");
        if (!seen.has(signature)) {
          seen.add(signature);
          groups.push(keys);
        }
      }
      return groups;
    }
    return [];
  }

  async function duplicateKeys() {
    const keys = new Set();
    for (const set of await duplicateSets()) for (const key of set) keys.add(key);
    return keys;
  }

  async function refreshDuplicateGroups() {
    const groups = new Map();
    state.duplicateIdGroups = new Map();
    for (const group of await duplicateSets()) for (const key of group) groups.set(key, group);
    for (const [id, key] of state.duplicateIdToKey) {
      const group = groups.get(key);
      if (group) state.duplicateIdGroups.set(id, group);
    }
    state.duplicateGroups = groups;
  }

  function parentKey(item) {
    if (!item) return null;
    if (item.isAttachment?.()) return item.parentKey;
    return item.isRegularItem?.() && !item.parentItem ? item.key : null;
  }

  function rememberItem(item) {
    if (!item || item.id == null || !state?.itemIndex) return;
    state.itemIndex.set(String(item.id), { key: item.key, parentKey: parentKey(item) });
  }

  function getItem(keyOrId) {
    if (typeof keyOrId === "string") {
      const id = Zotero.Items.getIDFromLibraryAndKey?.(state.libraryId, keyOrId);
      if (id) return Zotero.Items.get(id);
    }
    return Zotero.Items.get(keyOrId);
  }

  async function collectCandidates(keys) {
    const blocked = await duplicateKeys();
    const candidates = [];
    const blockedDuplicates = [];
    for (const key of keys) {
      const parent = getItem(key);
      if (!parent || !parent.isRegularItem?.() || parent.parentItem) continue;
      rememberItem(parent);
      for (const attachmentKey of parent.getAttachments?.() ?? []) {
        const attachment = getItem(attachmentKey);
        if (!attachment || !attachment.isAttachment?.()) continue;
        rememberItem(attachment);
        const contentType = attachment.attachmentContentType || attachment.getField?.("contentType");
        if (String(contentType).toLowerCase() !== "application/pdf") continue;
        const candidate = {
          parent_item_key: parent.key,
          parent_item_version: parent.version,
          attachment_key: attachment.key,
          attachment_version: attachment.version,
          language: parent.getField?.("language") || "",
        };
        if (blocked.has(parent.key)) blockedDuplicates.push(candidate);
        else candidates.push(candidate);
      }
    }
    return { candidates, blockedDuplicates };
  }

  async function allParentKeys() {
    if (typeof Zotero.Search === "function") {
      const search = new Zotero.Search();
      search.libraryID = state.libraryId;
      const ids = await search.search();
      const items = Zotero.Items.getAsync ? await Zotero.Items.getAsync(ids) : ids.map((id) => Zotero.Items.get(id));
      for (const item of items) rememberItem(item);
      return items.filter((item) => item?.isRegularItem?.() && !item.parentItem).map((item) => item.key);
    }
    // Test/dev fallback for older embedded Zotero contexts.
    const items = Zotero.Libraries.get(state.libraryId).getChildItems?.() ?? [];
    for (const item of items) rememberItem(item);
    return items.map((item) => item.key);
  }

  class EventQueue {
    constructor(onQuiet) {
      this.pending = new Set();
      this.timer = null;
      this.running = false;
      this.onQuiet = onQuiet;
    }
    add(keys) {
      for (const key of keys || []) if (key) this.pending.add(key);
      if (this.timer !== null) clearTimeout(this.timer);
      this.timer = setTimeout(() => this.quiet(), DELAY_MS);
    }
    async quiet() {
      this.timer = null;
      if (this.running || !this.pending.size) return;
      const keys = [...this.pending];
      this.pending.clear();
      this.running = true;
      try { await this.onQuiet(keys); }
      catch (error) { Zotero.logError(error); }
      finally {
        this.running = false;
        if (this.pending.size) this.add([]);
      }
    }
    cancel() {
      if (this.timer !== null) clearTimeout(this.timer);
      this.timer = null;
      this.pending.clear();
    }
  }

  async function requestDocument(keys) {
    const forceKeys = state.forceKeys;
    const collected = await collectCandidates(keys);
    const candidates = collected.candidates.map((candidate) => ({
      ...candidate,
      eligible: true,
      force: forceKeys.has(candidate.parent_item_key)
    }));
    for (const key of keys) forceKeys.delete(key);
    return {
      schema_version: 1,
      protocol_version: "1",
      request_id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
      generated_at: new Date().toISOString(),
      library_id: String(state.apiLibraryId),
      plugin_generation: String(++state.generation),
      candidates,
      blocked_duplicates: collected.blockedDuplicates
    };
  }

  function launch(requestPath, requestId) {
    const settings = state.settings;
    const args = [requestPath];
    if (settings.dataRoot) args.push("--data-root", settings.dataRoot);
    if (settings.cpuThreads > 0) args.push("--cpu-threads", String(settings.cpuThreads));
    const storageRoot = Zotero.getStorageDirectory?.()?.path;
    if (storageRoot) args.push("--storage-root", nativePath(storageRoot));
    const process = Cc["@mozilla.org/process/util;1"].createInstance(Ci.nsIProcess);
    process.init(Zotero.File.pathToFile(nativePath(settings.command)));
    return new Promise((resolve, reject) => {
      const observer = {
        observe(_subject, topic, data) {
          if (topic === "process-finished") resolve(data);
          if (topic === "process-failed") reject(new Error(`sync command failed: ${data}`));
        }
      };
      process.runwAsync(args, args.length, observer, false);
    }).then(async () => {
      const resultPath = joinPath(dataRoot(settings), "results", `${requestId}.json`);
      try {
        const result = await IOUtils.readJSON(resultPath);
        state.settings.lastSummary = JSON.stringify(result.counts || {});
        saveSettings(state.settings);
        if (result.status === "STALE") state.queue.add(state.lastKeys || []);
      } catch (error) {
        Zotero.logError(error);
      }
    });
  }

  function saveSettings(settings) {
    const pref = prefAdapter();
    pref.setBool("enabled", settings.enabled);
    pref.setString("command", settings.command);
    pref.setString("dataRoot", settings.dataRoot);
    pref.setBool("cpu", settings.cpu);
    pref.setInt("cpuThreads", settings.cpuThreads);
    pref.setString("lastSummary", settings.lastSummary);
  }

  async function runForKeys(keys) {
    const request = await requestDocument(keys);
    state.lastKeys = keys;
    const path = joinPath(dataRoot(state.settings), "requests", `${request.request_id}.json`);
    await atomicWrite(path, request);
    await launch(path, request.request_id);
  }

  function installNotifier() {
    const observer = {
      notify(_event, type, ids) {
        if (!state.settings.enabled || !["item", "file", "collection-item", "trash"].includes(type)) return;
        const affected = new Set();
        for (const id of ids || []) {
          const item = getItem(id);
          const snapshot = state.itemIndex.get(String(id));
          const key = parentKey(item) || snapshot?.parentKey || (item?.isRegularItem?.() ? item.key : null);
          if (key) affected.add(key);
          const itemKey = item?.key || snapshot?.key;
          for (const keyInGroup of state.duplicateGroups.get(itemKey) || state.duplicateIdGroups.get(String(id)) || []) affected.add(keyInGroup);
          rememberItem(item);
        }
        state.queue.add(affected);
        refreshDuplicateGroups().catch((error) => Zotero.logError(error));
      }
    };
    Zotero.Notifier.registerObserver(observer, ["item", "file", "collection-item", "trash"]);
    return () => Zotero.Notifier.unregisterObserver(observer);
  }

  function installMenus(window) {
    const parent = window?.document?.getElementById("zotero-itemmenu");
    if (!parent || parent.querySelector("#zotero-mineru-resync-item")) return;
    const make = (id, label) => {
      const item = window.document.createXULElement("menuitem");
      item.id = id;
      item.setAttribute("label", label);
      return item;
    };
    const separator = window.document.createXULElement("menuseparator");
    const resync = make("zotero-mineru-resync-item", "重新同步此条目");
    const full = make("zotero-mineru-full-rescan", "立即全库重算");
    resync.addEventListener("command", () => {
      const pane = Zotero.getActiveZoteroPane?.() || window.ZoteroPane;
      const item = pane?.getSelectedItems?.()[0];
      const key = parentKey(item);
      if (key) {
        state.forceKeys.add(key);
        state.queue.add([key]);
      }
    });
    full.addEventListener("command", () => {
      allParentKeys().then((keys) => state.queue.add(keys)).catch((error) => Zotero.logError(error));
    });
    parent.append(separator, resync, full);
  }

  function removeMenus(window) {
    for (const id of ["zotero-mineru-resync-item", "zotero-mineru-full-rescan"]) {
      window?.document?.getElementById(id)?.remove();
    }
  }

  function saveDefaults() {
    const pref = prefAdapter();
    if (Services.prefs.getPrefType(PREF_BRANCH + "enabled") === Services.prefs.PREF_INVALID) {
      saveSettings({ enabled: false, command: "zotero-mineru-sync", dataRoot: "", cpu: true, cpuThreads: 0, lastSummary: "未运行" });
    }
  }

  function startE2EHelper() {
    let enabled;
    try { enabled = Services.prefs.getBoolPref(PREF_BRANCH + "e2eBootstrap", false); }
    catch (_) { return; }
    if (!enabled) return;
    try {
      const helperURI = state.rootURI + "e2e_helper.js";
      const helperScope = {
        Zotero,
        Services,
        Cc,
        Ci,
        Components,
        ChromeUtils,
        IOUtils,
        PathUtils
      };
      Services.scriptloader.loadSubScript(helperURI, helperScope);
      if (typeof helperScope.startup !== "function") throw new Error("E2E helper has no startup() hook");
      e2eHelperScope = helperScope;
      helperScope.startup({ id: "zotero-mineru-sync-e2e-helper@local", version: "0.1.0", rootURI: helperURI });
    } catch (error) {
      Zotero.logError(error);
    }
  }

  async function startup({ id, version, rootURI }) {
    saveDefaults();
    const pref = prefAdapter();
    const settings = {
      enabled: pref.getBool("enabled", false),
      command: pref.getString("command", "zotero-mineru-sync"),
      dataRoot: pref.getString("dataRoot", ""),
      cpu: pref.getBool("cpu", true),
      cpuThreads: Math.max(0, pref.getInt("cpuThreads", 0)),
      lastSummary: pref.getString("lastSummary", "未运行")
    };
    const libraryId = Zotero.Libraries.userLibraryID;
    // Zotero's internal user-library ID is 1, while the read-only Local API
    // addresses the personal library as users/0. Keep both boundaries explicit.
    const apiLibraryId = "0";
    state = { id, version, rootURI, libraryId, apiLibraryId, settings, generation: 0,
      itemIndex: new Map(),
      duplicateGroups: new Map(), duplicateIdGroups: new Map(), duplicateIdToKey: new Map(), forceKeys: new Set() };
    await refreshDuplicateGroups();
    state.queue = new EventQueue(runForKeys);
    state.unregister = installNotifier();
    state.prefObserver = {
      observe(_subject, _topic, name) {
        const enabled = prefAdapter().getBool("enabled", false);
        state.settings.command = prefAdapter().getString("command", state.settings.command);
        state.settings.dataRoot = prefAdapter().getString("dataRoot", state.settings.dataRoot);
        state.settings.cpu = prefAdapter().getBool("cpu", state.settings.cpu);
        state.settings.cpuThreads = Math.max(0, prefAdapter().getInt("cpuThreads", state.settings.cpuThreads));
        if (enabled && !state.settings.enabled) {
          state.settings.enabled = true;
          allParentKeys().then((keys) => state.queue.add(keys)).catch((error) => Zotero.logError(error));
        } else if (!enabled) {
          state.settings.enabled = false;
          state.queue.cancel();
        }
      }
    };
    Services.prefs.addObserver(PREF_BRANCH, state.prefObserver);
    Zotero.PreferencePanes?.register?.({ pluginID: PLUGIN_ID, src: "content/options.xhtml", scripts: ["content/options.js"] });
    if (settings.enabled) {
      state.queue.add(await allParentKeys());
    }
    startE2EHelper();
  }

  function onMainWindowLoad({ window }) { installMenus(window); }
  function onMainWindowUnload({ window }) { removeMenus(window); }
  function shutdown() {
    e2eHelperScope?.shutdown?.();
    e2eHelperScope = null;
    state?.queue.cancel();
    state?.unregister?.();
    if (state?.prefObserver) Services.prefs.removeObserver(PREF_BRANCH, state.prefObserver);
    for (const window of Zotero.getMainWindows?.() || []) removeMenus(window);
    state = null;
  }

  return { startup, shutdown, onMainWindowLoad, onMainWindowUnload };
})();
