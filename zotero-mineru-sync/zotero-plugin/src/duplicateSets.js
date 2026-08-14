/* Zotero-version-sensitive duplicate access is isolated in this adapter. */

export function normalizeDuplicateSets(rawSets) {
  return rawSets
    .map((set) => Array.from(new Set(set.filter((key) => typeof key === "string" && key.length))))
    .filter((set) => set.length > 1);
}

export function duplicateKeys(sets) {
  const result = new Set();
  for (const set of normalizeDuplicateSets(sets)) {
    for (const key of set) result.add(key);
  }
  return result;
}

export function queryDuplicateSets(zotero) {
  const raw = zotero?.Duplicates?.getSets?.() ?? [];
  return raw.map((set) => {
    if (Array.isArray(set)) return set.map((item) => typeof item === "string" ? item : item?.key);
    return Array.from(set ?? []).map((item) => typeof item === "string" ? item : item?.key);
  });
}
