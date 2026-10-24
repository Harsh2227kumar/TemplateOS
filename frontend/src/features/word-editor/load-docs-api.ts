/**
 * Loads the ONLYOFFICE Docs JS API from the Document Server (no npm package):
 * one <script> per server URL, cached, rejected after 20 s.
 */

export interface DocEditorInstance {
  destroyEditor: () => void;
}

export interface DocsAPI {
  DocEditor: new (elementId: string, config: Record<string, unknown>) => DocEditorInstance;
}

declare global {
  interface Window {
    DocsAPI?: DocsAPI;
  }
}

export const DOCS_API_LOAD_ERROR = "The document editor could not be loaded";
const LOAD_TIMEOUT_MS = 20_000;
const loading = new Map<string, Promise<DocsAPI>>();

export function docsApiScriptUrl(baseUrl: string): string {
  return `${baseUrl.replace(/\/+$/, "")}/web-apps/apps/api/documents/api.js`;
}

export function loadDocsApi(baseUrl: string): Promise<DocsAPI> {
  const src = docsApiScriptUrl(baseUrl);
  const cached = loading.get(src);
  if (cached) return cached;

  const promise = new Promise<DocsAPI>((resolve, reject) => {
    if (window.DocsAPI) {
      resolve(window.DocsAPI);
      return;
    }
    const script = document.createElement("script");
    script.src = src;
    script.async = true;
    const fail = () => {
      window.clearTimeout(timer);
      script.remove();
      loading.delete(src);
      reject(new Error(DOCS_API_LOAD_ERROR));
    };
    const timer = window.setTimeout(fail, LOAD_TIMEOUT_MS);
    script.onload = () => {
      window.clearTimeout(timer);
      if (window.DocsAPI) resolve(window.DocsAPI);
      else fail();
    };
    script.onerror = fail;
    document.head.appendChild(script);
  });
  loading.set(src, promise);
  return promise;
}
