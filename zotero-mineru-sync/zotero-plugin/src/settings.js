export const DEFAULT_SETTINGS = Object.freeze({
  enabled: false,
  command: "zotero-mineru-sync",
  dataRoot: "",
  cpu: true,
  lastSummary: "未运行"
});

export function loadSettings(pref) {
  return {
    ...DEFAULT_SETTINGS,
    enabled: pref.getBool("enabled", DEFAULT_SETTINGS.enabled),
    command: pref.getString("command", DEFAULT_SETTINGS.command),
    dataRoot: pref.getString("dataRoot", DEFAULT_SETTINGS.dataRoot),
    cpu: pref.getBool("cpu", DEFAULT_SETTINGS.cpu),
    lastSummary: pref.getString("lastSummary", DEFAULT_SETTINGS.lastSummary)
  };
}

export function saveSettings(pref, settings) {
  pref.setBool("enabled", Boolean(settings.enabled));
  pref.setString("command", settings.command);
  pref.setString("dataRoot", settings.dataRoot);
  pref.setBool("cpu", Boolean(settings.cpu));
  pref.setString("lastSummary", settings.lastSummary ?? "");
}
