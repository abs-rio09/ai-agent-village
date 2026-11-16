export const BUILD_BLOCK: RegExp;
export function isPrecachable(url: string): boolean;
export function renderServiceWorker(template: string, version: string, urls: string[]): string;
export function buildServiceWorker(outDir: string): { version: string; urls: string[] };
