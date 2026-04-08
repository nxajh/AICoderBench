import { NextResponse } from "next/server";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://34.84.95.125:8000";

async function proxyRequest(request: Request, method: string) {
  const { pathname } = new URL(request.url);
  const url = `${API_BASE}${pathname}`;

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
