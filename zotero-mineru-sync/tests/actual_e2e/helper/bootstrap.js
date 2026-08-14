/* Test-only helper. It is installed only into the project-local E2E profile. */

async function writeMarker(path, document) {
  await Zotero.File.putContentsAsync(path, `${JSON.stringify(document, null, 2)}\n`);
}

function getServices() {
  if (typeof Services !== "undefined") return Services;
  return ChromeUtils.importESModule("resource://gre/modules/Services.sys.mjs").Services;
}

async function createFixture() {
  const services = getServices();
  const fixture = services.prefs.getStringPref("extensions.zotero-mineru-sync-e2e.fixture");
  const marker = services.prefs.getStringPref("extensions.zotero-mineru-sync-e2e.marker");
  try {
    await Zotero.initializationPromise;
    const parent = new Zotero.Item("journalArticle");
    parent.libraryID = Zotero.Libraries.userLibraryID;
    parent.setField("title", "Zotero MinerU actual E2E paper");
    parent.setField("language", "en");
    const parentID = await parent.saveTx();
    const attachment = await Zotero.Attachments.linkFromFile({
      file: Zotero.File.pathToFile(fixture),
      parentItemID: parentID
    });
    const item = Zotero.Items.get(parentID);
    const child = typeof attachment === "object" ? attachment : Zotero.Items.get(attachment);
    await writeMarker(marker, {
      status: "created",
      library_id: String(Zotero.Libraries.userLibraryID),
      parent_item_key: item.key,
      parent_item_version: item.version,
      attachment_key: child.key,
      attachment_version: child.version,
      fixture
    });
  } catch (error) {
    await writeMarker(marker, { status: "error", error: String(error), stack: error?.stack || "" });
    Zotero.logError(error);
  }
}

function startup() {
  // Let the real plugin finish startup and notifier registration first.
  const marker = getServices().prefs.getStringPref("extensions.zotero-mineru-sync-e2e.marker");
  Zotero.File.putContentsAsync(`${marker}.debug`, "bootstrap-started\n")
    .then(() => Zotero.Promise.delay(5000))
    .then(() => createFixture())
    .catch(async (error) => {
      await Zotero.File.putContentsAsync(`${marker}.error`, `${error}\n${error?.stack || ""}\n`);
      Zotero.logError(error);
    });
}

function shutdown() {}
function install() {}
function uninstall() {}
