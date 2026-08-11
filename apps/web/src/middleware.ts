import { NextRequest, NextResponse } from "next/server";

/**
 * 访问口令门（2026-08-02 用户裁定，取代 Google 邮箱白名单门）。
 *
 * 口令只存运行时环境变量 `CAMPUSPATH_DEMO_PASSCODE`——不在代码里、
 * 不在快照里、不在界面上。校验发生在服务端（/api/auth/passcode），
 * 通过后签发 HMAC 签名的 httpOnly cookie，全站（含 /api/v1 反代）过门。
 * **本地开发不设该变量，门自动不存在**——drive.mjs 与三门禁不受影响。
 */
import { GATE_COOKIE as COOKIE, signGate } from "@/lib/gate";

/** 页面 HTML 一律不缓存（2026-08-02 白屏事故）：Next 静态预渲染给 HTML 打
 * `s-maxage=31536000`，Google 门时代所有请求先 307 从未暴露；门一撤，
 * 缓存节点把**上一次部署**的 HTML 发给用户，其引用的 chunk 已不存在 → 白屏。
 * 静态资源（_next/）不经此 middleware，内容哈希长缓存不受影响。 */
const noStore = (res: NextResponse): NextResponse => {
  res.headers.set("Cache-Control", "private, no-store");
  return res;
};

/** 门前公开路径。加进来之前先想清楚：这一条会被任何人看到。
 *
 * PWA 那几件（2026-08-11 P6）必须在门外：manifest / sw.js / 图标一旦被
 * 302 到登录页，浏览器拿到的是一份 HTML——**安装提示直接消失**，
 * 而现象是「线上装不上，本地能装」，极难查。这几个文件本身不含任何内容，
 * 门挡不挡它们对保密没有区别。 */
const PUBLIC_PATHS = new Set([
  "/login", "/landing", "/landing.html",
  "/manifest.webmanifest", "/sw.js", "/sw-unregister",
  "/icon-192.png", "/icon-512.png", "/icon-512-maskable.png",
  "/apple-touch-icon.png",
]);

export async function middleware(request: NextRequest) {
  const passcode = process.env.CAMPUSPATH_DEMO_PASSCODE;
  const secret = process.env.AUTH_SECRET ?? passcode;
  if (!passcode || !secret) return noStore(NextResponse.next());

  // 登录页本身放行——口令就在那里输入。
  // 宣传页同样放行：它是**把人领到门口**的东西，自己被门挡住就没有意义了
  // （页面上印着体验口令，读者看完直接进门——2026-08-10 用户裁定）。
  if (PUBLIC_PATHS.has(request.nextUrl.pathname)) {
    return noStore(NextResponse.next());
  }

  const cookie = request.cookies.get(COOKIE)?.value;
  if (cookie) {
    const [payload, sig] = cookie.split(".");
    if (payload && sig && sig === (await signGate(payload, secret))) {
      try {
        const pad = payload.replace(/-/g, "+").replace(/_/g, "/");
        const data = JSON.parse(atob(pad));
        if (typeof data.exp === "number" && data.exp > Date.now()) {
          return noStore(NextResponse.next());
        }
      } catch {
        /* 坏 cookie 当未登录 */
      }
    }
  }

  // 反代 API 请求给 401（fetch 不该吃 307 HTML）；页面请求回登录页
  if (request.nextUrl.pathname.startsWith("/api/")) {
    return NextResponse.json({ detail: "passcode_required" }, { status: 401 });
  }
  const origin = process.env.APP_ORIGIN
    ?? `${request.headers.get("x-forwarded-proto") ?? "https"}://${request.headers.get("x-forwarded-host") ?? request.headers.get("host")}`;
  return NextResponse.redirect(new URL("/login", origin));
}

export const config = {
  // 放行静态资源与口令校验路由自身；其余全部过门
  matcher: ["/((?!_next/|favicon|api/auth/).*)"],
};
