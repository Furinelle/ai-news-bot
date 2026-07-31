const DEFAULT_KEY = "weekly/latest.html";

const CONTENT_TYPES = {
  ".html": "text/html; charset=utf-8",
  ".md": "text/markdown; charset=utf-8",
  ".json": "application/json; charset=utf-8",
};

export default {
  async fetch(request, env) {
    if (request.method !== "GET" && request.method !== "HEAD") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const url = new URL(request.url);
    const key = objectKeyFromPath(url.pathname);
    if (!key) {
      return new Response("Not Found", { status: 404 });
    }

    const object = await env.REPORTS.get(key);
    if (!object) {
      return new Response("Not Found", { status: 404 });
    }

    const headers = new Headers();
    object.writeHttpMetadata(headers);
    headers.set("etag", object.httpEtag);
    headers.set("cache-control", key === DEFAULT_KEY ? "public, max-age=60" : "public, max-age=86400");
    if (!headers.has("content-type")) {
      headers.set("content-type", contentTypeForKey(key));
    }

    if (request.method === "HEAD") {
      return new Response(null, { headers });
    }
    return new Response(object.body, { headers });
  },
};

function objectKeyFromPath(pathname) {
  const decodedPath = decodeURIComponent(pathname);
  // 周报路径
  if (decodedPath === "/" || decodedPath === "/weekly" || decodedPath === "/weekly/") {
    return DEFAULT_KEY;
  }
  if (decodedPath.startsWith("/weekly/")) {
    return decodedPath.slice(1).replace(/\/+/g, "/");
  }
  // 兼容旧 daily 路径（历史归档）
  if (decodedPath === "/daily" || decodedPath === "/daily/") {
    return "daily/latest.html";
  }
  if (decodedPath.startsWith("/daily/")) {
    return decodedPath.slice(1).replace(/\/+/g, "/");
  }
  return "";
}

function contentTypeForKey(key) {
  const extension = key.match(/\.[^.]+$/)?.[0] || "";
  return CONTENT_TYPES[extension] || "application/octet-stream";
}
