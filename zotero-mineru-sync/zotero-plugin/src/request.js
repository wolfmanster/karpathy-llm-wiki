/* Pure request construction plus atomic JSON writing for the bootstrap layer. */

export const SCHEMA_VERSION = 1;
export const PROTOCOL_VERSION = "1";

export function makeRequest({ requestId, generatedAt, libraryId, generation, candidates }) {
  if (candidates.some((candidate) => candidate.eligible !== true)) {
    throw new Error("blocked candidates must not be placed in the parse request");
  }
  return {
    schema_version: SCHEMA_VERSION,
    protocol_version: PROTOCOL_VERSION,
    request_id: requestId,
    generated_at: generatedAt,
    library_id: libraryId,
    plugin_generation: generation,
    candidates: candidates.map((candidate) => ({
      parent_item_key: candidate.parent_item_key,
      parent_item_version: candidate.parent_item_version,
      attachment_key: candidate.attachment_key,
      attachment_version: candidate.attachment_version,
      eligible: candidate.eligible === true,
      force: candidate.force === true,
      language: candidate.language ?? ""
    }))
  };
}

export function atomicJsonWriter(io) {
  return async function writeAtomic(path, document) {
    const temporary = `${path}.${io.randomSuffix()}.tmp`;
    await io.makeParentDirectory(path);
    await io.writeText(temporary, `${JSON.stringify(document, null, 2)}\n`);
    await io.rename(temporary, path);
  };
}
