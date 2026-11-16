// Finishes the service worker after `vite build`: writes the precache list and a version into
// <outDir>/sw.js (a copy of public/sw.js). Plain Node, no dependencies.
//
//   node scripts/build-sw.mjs [outDir]        (default: dist)
//
// The version is a hash of every precached file, so any change to the built app gives a new
// cache name: the old cache is deleted and the open app is told that an update is waiting.

import { createHash } from "node:crypto";
import { readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

export const BUILD_BLOCK = /\/\* BUILD:BEGIN[\s\S]*?\/\* BUILD:END \*\//;

/** Files of the build that must never be precached. */
export function isPrecachable(url) {
  if (url === "/sw.js") return false; // the worker itself
  if (url.endsWith(".map")) return false;
  if (url === "/api" || url.startsWith("/api/")) return false; // cannot exist in a build; never cache the API
  return true;
}

/** The service worker source with the build block replaced by the real version and list. */
export function renderServiceWorker(template, version, urls) {
  if (!BUILD_BLOCK.test(template)) throw new Error("sw.js has no BUILD:BEGIN … BUILD:END block");
  const block = [
    "/* BUILD:BEGIN — written by scripts/build-sw.mjs */",
    `const VERSION = ${JSON.stringify(version)};`,
    `const PRECACHE = ${JSON.stringify(urls, null, 2)};`,
    "/* BUILD:END */",
  ].join("\n");
  return template.replace(BUILD_BLOCK, () => block);
}

function listFiles(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? listFiles(path) : [path];
  });
}

export function buildServiceWorker(outDir) {
  const root = resolve(outDir);
  const files = listFiles(root)
    .map((path) => ({ path, url: "/" + relative(root, path).split(sep).join("/") }))
    .filter((file) => isPrecachable(file.url))
    .sort((a, b) => a.url.localeCompare(b.url));
  const hash = createHash("sha256");
  for (const file of files) {
    hash.update(file.url);
    hash.update(readFileSync(file.path));
  }
  const swPath = join(root, "sw.js");
  const template = readFileSync(swPath, "utf8");
  hash.update(template);
  const version = hash.digest("hex").slice(0, 16);
  const urls = files.map((file) => file.url);
  writeFileSync(swPath, renderServiceWorker(template, version, urls));
  return { version, urls };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const outDir = process.argv[2] ?? "dist";
  const { version, urls } = buildServiceWorker(outDir);
  console.log(`service worker: version ${version}, ${urls.length} files precached (${outDir}/sw.js)`);
}
