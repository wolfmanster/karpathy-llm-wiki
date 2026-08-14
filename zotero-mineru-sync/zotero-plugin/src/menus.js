/* Small UI adapter for the two explicit user-triggered commands. */

export function registerMenus(window, commands) {
  const document = window?.document;
  const parent = document?.getElementById("zotero-itemmenu");
  if (!parent) return () => {};

  const separator = document.createXULElement?.("menuseparator") || document.createElement("menuseparator");
  const resync = document.createXULElement?.("menuitem") || document.createElement("menuitem");
  const full = document.createXULElement?.("menuitem") || document.createElement("menuitem");
  resync.id = "zotero-mineru-resync-item";
  resync.label = "重新同步此条目";
  full.id = "zotero-mineru-full-rescan";
  full.label = "立即全库重算";
  resync.addEventListener("command", () => {
    const item = globalThis.ZoteroPane?.getSelectedItems?.()[0];
    if (item) commands.resyncItem(item.key);
  });
  full.addEventListener("command", () => commands.fullRescan());
  parent.append(separator, resync, full);
  return () => {
    separator.remove();
    resync.remove();
    full.remove();
  };
}
