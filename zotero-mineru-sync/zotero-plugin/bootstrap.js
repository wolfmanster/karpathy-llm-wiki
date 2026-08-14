/* Zotero 7 bootstrap entry. The implementation is loaded as a classic
 * sub-script because bootstrap.js is not an ES module context. */

var ZoteroMineruRuntime;

async function startup({ id, version, resourceURI, rootURI = resourceURI.spec }) {
  if (typeof Services === "undefined") {
    ({ Services } = ChromeUtils.importESModule("resource://gre/modules/Services.sys.mjs"));
  }
  // Zotero 9 exposes these objects globally. Older Gecko-based hosts may only
  // expose them through the Firefox module URI, so retain that fallback.
  const io = typeof IOUtils !== "undefined"
    ? { IOUtils }
    : ChromeUtils.importESModule("resource://gre/modules/IOUtils.sys.mjs");
  const paths = typeof PathUtils !== "undefined"
    ? { PathUtils }
    : ChromeUtils.importESModule("resource://gre/modules/PathUtils.sys.mjs");
  const scope = {
    Zotero,
    Services,
    Cc: typeof Cc === "undefined" ? Components.classes : Cc,
    Ci: typeof Ci === "undefined" ? Components.interfaces : Ci,
    Components,
    ChromeUtils,
    IOUtils: io.IOUtils,
    PathUtils: paths.PathUtils
  };
  Services.scriptloader.loadSubScript(rootURI + "runtime.js", scope);
  ZoteroMineruRuntime = scope.ZoteroMineruRuntime;
  await ZoteroMineruRuntime.startup({ id, version, rootURI });
}

function onMainWindowLoad({ window }) {
  ZoteroMineruRuntime?.onMainWindowLoad({ window });
}

function onMainWindowUnload({ window }) {
  ZoteroMineruRuntime?.onMainWindowUnload({ window });
}

function shutdown() {
  ZoteroMineruRuntime?.shutdown();
  ZoteroMineruRuntime = undefined;
}

function install() {}
function uninstall() {}
