import { NextResponse } from "next/server";
import { readFileSync } from "fs";

let _apiBase: string | null = null;

function getApiBase(): string {
  if (_apiBase) return _apiBase;
  // 1. 尝试从运行时配置文件读取（Docker 启动时写入）
  try {
    const cfg = JSON.parse(readFileSync("/app/runtime-config.json", "utf-8"));
    _apiBase = cfg.apiUrl;
    if (_apiBase) return _apiBase;
  } catch {}
  // 2. 环境变量
  _apiBase = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  return _apiBase;
}

async function proxyRequest(request: Request, method: string) {
  const apiBase = getApiBase();
  const { pathname } = new URL(request.url);
  const url = `${apiBase}${pathname}`;

  try {
    const opts: RequestInit = { method };
    if (method !== "GET" && method !== "HEAD") {
      opts.body = await request.text();
      opts.headers = { "Content-Type": "application/json" };
    }
    const res = await fetch(url, opts);
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 502 });
  }
}

export async function GET(request: Request) { return proxyRequest(request, "GET"); }
export async function POST(request: Request) { return proxyRequest(request, "POST"); }
export async function PUT(request: Request) { return proxyRequest(request, "PUT"); }
export async function DELETE(request: Request) { return proxyRequest(request, "DELETE"); }
