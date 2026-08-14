var ZoteroMineruPreferences = {
  init() {
    const summary = document.getElementById("zotero-mineru-summary");
    let value = "未运行";
    try { value = Zotero.Prefs.get("extensions.zotero-mineru-sync.lastSummary") || value; } catch (_) {}
    if (summary) summary.textContent = `当前任务摘要：${value}`;
  }
};
