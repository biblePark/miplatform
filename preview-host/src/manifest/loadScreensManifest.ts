import type { ScreenManifestEntry, ScreensManifest } from "./types";

const SCREEN_ID_RE = /^[A-Za-z0-9][A-Za-z0-9_-]*$/;
const ENTRY_MODULE_RE = /^screens\/[A-Za-z0-9/_-]+$/;

export class ManifestContractError extends Error {}

type UnknownRecord = Record<string, unknown>;

function expectRecord(value: unknown, label: string): UnknownRecord {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new ManifestContractError(`${label} must be an object.`);
  }
  return value as UnknownRecord;
}

function expectString(
  value: unknown,
  label: string,
  options?: { pattern?: RegExp }
): string {
  if (typeof value !== "string" || value.trim().length === 0) {
    throw new ManifestContractError(`${label} must be a non-empty string.`);
  }
  if (options?.pattern && !options.pattern.test(value)) {
    throw new ManifestContractError(`${label} has an invalid format: ${value}`);
  }
  return value;
}

function parseScreenEntry(value: unknown, index: number): ScreenManifestEntry {
  const item = expectRecord(value, `screens[${index}]`);
  return {
    screenId: expectString(item.screenId, `screens[${index}].screenId`, {
      pattern: SCREEN_ID_RE,
    }),
    title:
      item.title === undefined
        ? undefined
        : expectString(item.title, `screens[${index}].title`),
    entryModule: expectString(item.entryModule, `screens[${index}].entryModule`, {
      pattern: ENTRY_MODULE_RE,
    }),
    sourceXmlPath: expectString(
      item.sourceXmlPath,
      `screens[${index}].sourceXmlPath`
    ),
    sourceNodePath: expectString(
      item.sourceNodePath,
      `screens[${index}].sourceNodePath`
    ),
  };
}

export function loadScreensManifest(payload: unknown): ScreensManifest {
  const root = expectRecord(payload, "manifest");
  const schemaVersion = expectString(root.schemaVersion, "schemaVersion");
  if (schemaVersion !== "1.0") {
    throw new ManifestContractError(
      `schemaVersion must be "1.0", received "${schemaVersion}".`
    );
  }

  const generatedAtUtc = expectString(root.generatedAtUtc, "generatedAtUtc");
  if (Number.isNaN(Date.parse(generatedAtUtc))) {
    throw new ManifestContractError(
      `generatedAtUtc must be a valid ISO-8601 datetime: ${generatedAtUtc}`
    );
  }

  if (!Array.isArray(root.screens)) {
    throw new ManifestContractError("screens must be an array.");
  }

  const screens = root.screens.map((item, index) => parseScreenEntry(item, index));
  const dedup = new Set<string>();
  for (const screen of screens) {
    if (dedup.has(screen.screenId)) {
      throw new ManifestContractError(
        `Duplicate screenId detected in manifest: ${screen.screenId}`
      );
    }
    dedup.add(screen.screenId);
  }

  return {
    schemaVersion: "1.0",
    generatedAtUtc,
    screens,
  };
}
