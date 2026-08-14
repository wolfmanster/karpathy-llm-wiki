/* Test-only helper. It is installed only into the project-local E2E profile. */

var zoteroMineruE2EPrefBranch = "extensions.zotero-mineru-sync-e2e.";
var zoteroMineruE2ETitle = "Zotero MinerU actual E2E paper";
var zoteroMineruE2ETimeoutMs = 9 * 60 * 1000;

function getServices() {
  if (typeof Services !== "undefined") return Services;
  return ChromeUtils.importESModule("resource://gre/modules/Services.sys.mjs").Services;
}

function getPref(name) {
  return getServices().prefs.getStringPref(zoteroMineruE2EPrefBranch + name);
}

function getIOUtils() {
  if (typeof IOUtils !== "undefined") return IOUtils;
  return ChromeUtils.importESModule("resource://gre/modules/IOUtils.sys.mjs").IOUtils;
}

function nativePath(path) {
  const value = String(path ?? "");
  return getServices().appinfo?.OS === "WINNT" ? value.replaceAll("/", "\\") : value;
}

function writeText(path, value) {
  try {
    return Promise.resolve(getIOUtils().writeUTF8(nativePath(path), value));
  } catch (error) {
    if (Zotero.File?.putContentsAsync) return Zotero.File.putContentsAsync(nativePath(path), value);
    return Promise.reject(error);
  }
}

function joinPath(...parts) {
  return typeof PathUtils !== "undefined" && PathUtils.join
    ? PathUtils.join(...parts.map(nativePath))
    : parts.map(nativePath).join("\\");
}

async function writeMarker(path, document) {
  await writeText(path, `${JSON.stringify(document, null, 2)}\n`);
}

async function resultFiles(dataRoot) {
  try {
    return (await getIOUtils().getChildren(nativePath(joinPath(dataRoot, "results"))))
      .filter((path) => path.toLowerCase().endsWith(".json"));
  } catch (_) {
    return [];
  }
}

async function readResult(path) {
  try {
    return await getIOUtils().readJSON(nativePath(path));
  } catch (_) {
    return null;
  }
}

async function waitForResult(dataRoot, predicate, description) {
  const deadline = Date.now() + zoteroMineruE2ETimeoutMs;
  while (Date.now() < deadline) {
    for (const path of await resultFiles(dataRoot)) {
      const result = await readResult(path);
      if (result && predicate(result)) return result;
    }
    await Zotero.Promise.delay(1000);
  }
  throw new Error(`timed out waiting for ${description}`);
}

async function countArchiveManifests(dataRoot) {
  const root = joinPath(dataRoot, "archive");
  async function walk(path) {
    let children;
    try {
      children = await getIOUtils().getChildren(nativePath(path));
    } catch (_) {
      return 0;
    }
    let count = 0;
    for (const child of children) {
      if (child.toLowerCase().endsWith("manifest.json")) count++;
      else count += await walk(child);
    }
    return count;
  }
  return walk(root);
}

async function topLevelItems() {
  if (typeof Zotero.Search === "function") {
    const search = new Zotero.Search();
    search.libraryID = Zotero.Libraries.userLibraryID;
    const ids = await search.search();
    const items = Zotero.Items.getAsync ? await Zotero.Items.getAsync(ids) : ids.map((id) => Zotero.Items.get(id));
    return items.filter((item) => item?.isRegularItem?.() && !item.parentItem && !item.deleted);
  }
  return (Zotero.Libraries.get(Zotero.Libraries.userLibraryID).getChildItems?.() ?? [])
    .filter((item) => item?.isRegularItem?.() && !item.parentItem && !item.deleted);
}

async function runLifecycle() {
  const fixture = getPref("fixture");
  const marker = getPref("marker");
  const dataRoot = getPref("dataRoot");
  await Zotero.initializationPromise;

  const existing = (await topLevelItems()).filter((item) => item.getField?.("title") === zoteroMineruE2ETitle);
  if (existing.length !== 2) {
    throw new Error(`expected two seeded duplicate items, found ${existing.length}`);
  }
  const master = existing.find((item) => item.key === "E2EPAPER");
  const duplicateItem = existing.find((item) => item.key === "E2EDUPE1");
  if (!master || !duplicateItem) throw new Error("seeded duplicate keys were not found");
  const masterAttachment = Zotero.Items.get(master.getAttachments()[0]);
  const duplicateAttachment = Zotero.Items.get(duplicateItem.getAttachments()[0]);
  const created = {
    library_id: String(Zotero.Libraries.userLibraryID),
    master_parent_item_key: master.key,
    master_parent_item_version: master.version,
    master_attachment_key: masterAttachment.key,
    duplicate_parent_item_key: duplicateItem.key,
    duplicate_parent_item_version: duplicateItem.version,
    duplicate_attachment_key: duplicateAttachment.key,
    duplicate_attachment_version: duplicateAttachment.version,
    fixture
  };
  await writeMarker(marker, { status: "duplicates_ready", ...created });

  const blocked = await waitForResult(
    dataRoot,
    (result) => result.counts?.BLOCKED_DUPLICATE === 2
      && (result.entries || []).every((entry) => entry.status === "BLOCKED_DUPLICATE"),
    "the duplicate-blocked result"
  );
  const archiveCountBeforeMerge = await countArchiveManifests(dataRoot);
  if (archiveCountBeforeMerge !== 0) {
    throw new Error(`duplicate was converted before merge: ${archiveCountBeforeMerge} archive manifests`);
  }
  await writeMarker(marker, {
    status: "duplicate_skipped",
    ...created,
    blocked_request_id: blocked.request_id,
    blocked_result: blocked,
    archive_count_before_merge: archiveCountBeforeMerge
  });

  const { mergeItems } = ChromeUtils.importESModule("chrome://zotero/content/mergeItems.mjs");
  await mergeItems(master, [duplicateItem]);
  const survivingAttachments = master.getAttachments().map((id) => Zotero.Items.get(id)).filter(Boolean);
  if (survivingAttachments.length !== 1) {
    throw new Error(`Zotero merge left ${survivingAttachments.length} attachments on the surviving item`);
  }
  const survivingAttachment = survivingAttachments[0];
  const survivingAttachmentKey = survivingAttachment?.key;
  if (!master || master.deleted || !duplicateItem.deleted || !survivingAttachmentKey) {
    throw new Error("Zotero merge did not leave one surviving parent and PDF attachment");
  }
  await writeMarker(marker, {
    status: "merged",
    ...created,
    blocked_request_id: blocked.request_id,
    archive_count_before_merge: archiveCountBeforeMerge,
    surviving_parent_item_key: master.key,
    surviving_attachment_key: survivingAttachmentKey,
    duplicate_parent_deleted: Boolean(duplicateItem.deleted)
  });

  const finalResult = await waitForResult(
    dataRoot,
    (result) => result.request_id !== blocked.request_id
      && result.counts?.SUCCESS === 1
      && (result.entries || []).filter((entry) => entry.status === "SUCCESS").length === 1
      && result.entries.filter((entry) => entry.status === "SUCCESS")[0].parent_item_key === master.key
      && result.entries.filter((entry) => entry.status === "SUCCESS")[0].attachment_key === survivingAttachmentKey,
    "the post-merge successful result"
  );
  await writeMarker(marker, {
    status: "completed",
    ...created,
    blocked_request_id: blocked.request_id,
    blocked_result: blocked,
    archive_count_before_merge: archiveCountBeforeMerge,
    surviving_parent_item_key: master.key,
    surviving_attachment_key: survivingAttachmentKey,
    duplicate_parent_deleted: Boolean(duplicateItem.deleted),
    final_result: finalResult,
    archive_count_after_merge: await countArchiveManifests(dataRoot)
  });
}

function startup() {
  let marker;
  try {
    marker = getPref("marker");
    getServices().prefs.setStringPref(zoteroMineruE2EPrefBranch + "state", "startup");
  } catch (error) {
    Zotero.logError(error);
    return;
  }
  writeText(`${marker}.debug`, "bootstrap-started\n")
    .then(() => Zotero.Promise.delay(5000))
    .then(() => runLifecycle())
    .catch(async (error) => {
      try {
        await writeMarker(marker, { status: "error", error: String(error), stack: error?.stack || "" });
        await writeText(`${marker}.error`, `${error}\n${error?.stack || ""}\n`);
      } catch (writeError) {
        Zotero.logError(writeError);
      }
      Zotero.logError(error);
    });
}

function shutdown() {}
function install() {}
function uninstall() {}
