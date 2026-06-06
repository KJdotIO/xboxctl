import { createServer } from "node:http";
import { mkdir, readFile, unlink, writeFile } from "node:fs/promises";
import { Buffer } from "node:buffer";
import { dirname, join } from "node:path";
import { createRequire } from "node:module";
import { chromium } from "playwright";
import { Msal, TokenStore } from "xal-node";

const require = createRequire(import.meta.url);
const PLAYER_ASSET = require.resolve(
  "xbox-xcloud-player/dist/assets/xCloudPlayer.min.js",
);
const DEFAULT_TIMEOUT_MS = 120_000;
const DEFAULT_FORMAT = "png";
const DEFAULT_QUALITY = 80;
const DEFAULT_SETTLE_MS = 5000;

class ObserveFailure extends Error {}

function parseArgs(argv) {
  const parsed = {
    serve: false,
    tokens: "",
    output: "",
    outputDir: "",
    sessionFile: "",
    sessionToken: "",
    serverId: "",
    timeoutMs: DEFAULT_TIMEOUT_MS,
    idleTimeoutMs: 600_000,
    format: DEFAULT_FORMAT,
    width: 0,
    quality: DEFAULT_QUALITY,
    settleMs: DEFAULT_SETTLE_MS,
    steps: [],
  };
  for (let index = 2; index < argv.length; index += 1) {
    const name = argv[index];
    if (name === "--serve") {
      parsed.serve = true;
      continue;
    }
    const value = argv[index + 1];
    if (value === undefined) {
      throw new ObserveFailure(`Missing value for ${name}`);
    }
    if (name === "--tokens") parsed.tokens = value;
    else if (name === "--output") parsed.output = value;
    else if (name === "--output-dir") parsed.outputDir = value;
    else if (name === "--session-file") parsed.sessionFile = value;
    else if (name === "--session-token") parsed.sessionToken = value;
    else if (name === "--server-id") parsed.serverId = value;
    else if (name === "--timeout") parsed.timeoutMs = Number(value) * 1000;
    else if (name === "--idle-timeout") parsed.idleTimeoutMs = Number(value) * 1000;
    else if (name === "--format") parsed.format = value;
    else if (name === "--width") parsed.width = Number(value);
    else if (name === "--quality") parsed.quality = Number(value);
    else if (name === "--settle-ms") parsed.settleMs = Number(value);
    else if (name === "--step") parsed.steps.push(value);
    else throw new ObserveFailure(`Unknown argument: ${name}`);
    index += 1;
  }
  if (!parsed.tokens) throw new ObserveFailure("--tokens is required");
  if (parsed.serve && !parsed.sessionFile) {
    throw new ObserveFailure("--session-file is required with --serve");
  }
  if (parsed.serve && !parsed.sessionToken) {
    throw new ObserveFailure("--session-token is required with --serve");
  }
  if (!parsed.serve && !parsed.output && !parsed.outputDir) {
    throw new ObserveFailure("--output or --output-dir is required");
  }
  if ([parsed.output, parsed.outputDir, parsed.sessionFile].filter(Boolean).length > 1) {
    throw new ObserveFailure("--output and --output-dir cannot be combined");
  }
  if (parsed.outputDir && parsed.steps.length === 0) {
    throw new ObserveFailure("--step is required with --output-dir");
  }
  if (!["png", "jpeg"].includes(parsed.format)) {
    throw new ObserveFailure("--format must be png or jpeg");
  }
  if (!Number.isInteger(parsed.width) || parsed.width < 0) {
    throw new ObserveFailure("--width must be a positive integer");
  }
  if (!Number.isInteger(parsed.quality) || parsed.quality < 1 || parsed.quality > 100) {
    throw new ObserveFailure("--quality must be between 1 and 100");
  }
  if (!Number.isInteger(parsed.settleMs) || parsed.settleMs < 0 || parsed.settleMs > 30000) {
    throw new ObserveFailure("--settle-ms must be between 0 and 30000");
  }
  if (!Number.isInteger(parsed.idleTimeoutMs) || parsed.idleTimeoutMs < 1000) {
    throw new ObserveFailure("--idle-timeout must be at least 1 second");
  }
  return parsed;
}

function buttonName(value) {
  const names = {
    a: "A",
    b: "B",
    x: "X",
    y: "Y",
    up: "DPadUp",
    "dpad-up": "DPadUp",
    down: "DPadDown",
    "dpad-down": "DPadDown",
    left: "DPadLeft",
    "dpad-left": "DPadLeft",
    right: "DPadRight",
    "dpad-right": "DPadRight",
    home: "Nexus",
    xbox: "Nexus",
    menu: "Menu",
    view: "View",
    lb: "LeftShoulder",
    rb: "RightShoulder",
    "left-shoulder": "LeftShoulder",
    "right-shoulder": "RightShoulder",
  };
  const name = names[value.toLowerCase()];
  if (!name) throw new ObserveFailure(`Unsupported flow button: ${value}`);
  return name;
}

function parseStep(raw) {
  const parts = raw.split(":");
  if (parts[0] === "capture" && parts.length === 2) {
    return { kind: "capture", name: parts[1] };
  }
  if (parts[0] === "press" && (parts.length === 2 || parts.length === 3)) {
    const repeat = parts.length === 3 ? Number(parts[2]) : 1;
    if (!Number.isInteger(repeat) || repeat < 1 || repeat > 20) {
      throw new ObserveFailure(`Invalid repeat in flow step: ${raw}`);
    }
    return { kind: "press", button: buttonName(parts[1]), repeat };
  }
  if (parts[0] === "wait" && parts.length === 2) {
    const delayMs = Number(parts[1]);
    if (!Number.isInteger(delayMs) || delayMs < 0 || delayMs > 30000) {
      throw new ObserveFailure(`Invalid wait in flow step: ${raw}`);
    }
    return { kind: "wait", delayMs };
  }
  throw new ObserveFailure(`Invalid flow step: ${raw}`);
}

function safeCaptureName(value) {
  const safe = value.replaceAll(/[^A-Za-z0-9._-]/g, "-");
  if (!safe) throw new ObserveFailure("Capture step name must not be empty");
  return safe;
}

function tokenExpiry(raw) {
  const expiresIn = Number(raw.expires_in || 3600);
  const issuedMs = raw.issued ? Date.parse(raw.issued) : Number.NaN;
  const baseMs = Number.isNaN(issuedMs) ? Date.now() : issuedMs;
  return {
    expiresIn,
    expiresOn: new Date(baseMs + Math.max(60, expiresIn) * 1000),
  };
}

async function adaptedTokenStore(tokensFile) {
  const raw = JSON.parse(await readFile(tokensFile, "utf8"));
  const { expiresIn, expiresOn } = tokenExpiry(raw);
  const storePath = join(
    dirname(tokensFile),
    ".xboxctl-xhome-tokens.generated.json",
  );
  await writeFile(
    storePath,
    JSON.stringify(
      {
        userToken: {
          token_type: raw.token_type || "Bearer",
          expires_in: expiresIn,
          scope: raw.scope || "xboxlive.signin openid profile offline_access",
          access_token: raw.access_token,
          refresh_token: raw.refresh_token,
          user_id: raw.user_id,
          expires_on: expiresOn.toISOString(),
        },
      },
      null,
      2,
    ),
  );
  const store = new TokenStore();
  store.load(storePath, true);
  return store;
}

async function streamingContext(tokensFile) {
  const store = await adaptedTokenStore(tokensFile);
  const msal = new Msal(store);
  const tokens = await msal.getStreamingTokens();
  const token = tokens.xHomeToken;
  return {
    baseUri: token.getDefaultRegion().baseUri,
    gsToken: token.data.gsToken,
  };
}

function requestBody(request) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    request.on("data", (chunk) => chunks.push(chunk));
    request.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
    request.on("error", reject);
  });
}

function normaliseIceBody(pathname, body) {
  if (!pathname.endsWith("/ice") || body.iceCandidates === undefined) {
    return body;
  }
  return {
    candidates: body.iceCandidates.map((candidate) =>
      JSON.stringify({
        candidate: candidate.candidate,
        sdpMid: candidate.sdpMid,
        sdpMLineIndex: candidate.sdpMLineIndex,
        usernameFragment: candidate.usernameFragment,
      }),
    ),
  };
}

async function proxyXboxRequest(request, response, context) {
  const target = new URL(request.url, context.baseUri);
  const rawBody = await requestBody(request);
  const parsedBody = rawBody ? JSON.parse(rawBody) : undefined;
  const body =
    parsedBody === undefined
      ? undefined
      : JSON.stringify(normaliseIceBody(target.pathname, parsedBody));
  const upstream = await fetch(target, {
    method: request.method,
    headers: {
      accept: "application/json",
      authorization: `Bearer ${context.gsToken}`,
      "content-type": "application/json",
      "x-gssv-client": "XboxComBrowser",
      ...(request.headers["x-ms-device-info"]
        ? { "x-ms-device-info": request.headers["x-ms-device-info"] }
        : {}),
    },
    body,
  });
  response.writeHead(upstream.status, {
    "content-type": upstream.headers.get("content-type") || "application/json",
  });
  response.end(Buffer.from(await upstream.arrayBuffer()));
}

function isSessionRequest(url) {
  return ["/capture", "/press", "/session", "/status"].includes(url.pathname);
}

function authoriseSessionRequest(request, response, control) {
  if (!control?.token) {
    response.writeHead(503, { "content-type": "text/plain" });
    response.end("Observe session is not ready");
    return false;
  }
  if (request.headers.authorization !== `Bearer ${control.token}`) {
    response.writeHead(401, { "content-type": "text/plain" });
    response.end("Unauthorised");
    return false;
  }
  return true;
}

async function handleSessionRequest(request, response, url, control) {
  if (!authoriseSessionRequest(request, response, control)) return;
  if (!control.capture || !control.press || !control.touch) {
    response.writeHead(503, { "content-type": "text/plain" });
    response.end("Observe session is not ready");
    return;
  }
  control.touch();
  if (url.pathname === "/status" && request.method === "GET") {
    response.writeHead(200, { "content-type": "application/json" });
    response.end(JSON.stringify({ ready: true }));
    return;
  }
  if (url.pathname === "/capture" && request.method === "POST") {
    const body = await requestBody(request);
    const overrides = body ? JSON.parse(body) : {};
    const frame = await control.capture(overrides);
    response.writeHead(200, { "content-type": frame.contentType });
    response.end(Buffer.from(frame.dataUrl.split(",")[1], "base64"));
    return;
  }
  if (url.pathname === "/press" && request.method === "POST") {
    const body = JSON.parse(await requestBody(request));
    await control.press(buttonName(body.button), Number(body.repeat || 1));
    response.writeHead(204);
    response.end();
    return;
  }
  if (url.pathname === "/session" && request.method === "DELETE") {
    response.writeHead(204);
    response.end();
    setTimeout(() => control.stop(), 0);
    return;
  }
  response.writeHead(404);
  response.end();
}

function html() {
  return `<!doctype html>
<meta charset="utf-8">
<body>
  <div id="videoHolder"></div>
  <script src="/assets/xCloudPlayer.min.js"></script>
  <script>
    const deviceInfo = JSON.stringify({
      appInfo: {
        env: {
          clientAppId: "www.xbox.com",
          clientAppType: "browser",
          clientAppVersion: "21.1.98",
          clientSdkVersion: "8.5.3",
          httpEnvironment: "prod",
          sdkInstallId: "",
        },
      },
      dev: {
        hw: { make: "Microsoft", model: "unknown", sdktype: "web" },
        os: { name: "windows", ver: "22631.2715", platform: "desktop" },
        displayInfo: {
          dimensions: { widthInPixels: 1920, heightInPixels: 1080 },
          pixelDensity: { dpiX: 2, dpiY: 2 },
        },
        browser: { browserName: "chrome", browserVersion: "119.0" },
      },
    });

    async function waitFor(predicate, timeoutMs, label) {
      const start = Date.now();
      while (Date.now() - start < timeoutMs) {
        const result = await predicate();
        if (result) return result;
        await new Promise((resolve) => setTimeout(resolve, 250));
      }
      throw new Error("Timed out waiting for " + label);
    }

    async function jsonOrNull(response) {
      if (response.status === 204) return null;
      return response.json();
    }

    async function getConsoles() {
      const response = await fetch("/v6/servers/home", {
        headers: {
          "accept": "application/json",
          "content-type": "application/json",
          "x-gssv-client": "XboxComBrowser",
          "x-ms-device-info": deviceInfo,
        },
      });
      return response.json();
    }

    async function startStream(serverId) {
      const response = await fetch("/v5/sessions/home/play", {
        method: "POST",
        headers: {
          "accept": "application/json",
          "content-type": "application/json",
          "x-gssv-client": "XboxComBrowser",
          "x-ms-device-info": deviceInfo,
        },
        body: JSON.stringify({
          clientSessionId: "",
          titleId: "",
          systemUpdateGroup: "",
          settings: {
            nanoVersion: "V3;WebrtcTransport.dll",
            enableOptionalDataCollection: false,
            enableTextToSpeech: false,
            highContrast: 0,
            locale: "en-GB",
            useIceConnection: false,
            timezoneOffsetMinutes: 120,
            sdkType: "web",
            osName: "windows",
          },
          serverId,
          fallbackRegionNames: [],
        }),
      });
      const stream = await response.json();
      await waitFor(async () => {
        const state = await fetch("/" + stream.sessionPath + "/state").then((item) => item.json());
        return state.state === "Provisioned";
      }, 60000, "provisioned stream");
      return stream;
    }

    async function sendSdp(sessionPath, offer) {
      await fetch("/" + sessionPath + "/sdp", {
        method: "POST",
        headers: { "accept": "application/json", "content-type": "application/json" },
        body: JSON.stringify({
          messageType: "offer",
          requestId: "1",
          sdp: offer.sdp,
          configuration: {
            chatConfiguration: {
              bytesPerSample: 2,
              expectedClipDurationMs: 20,
              format: { codec: "opus", container: "webm" },
              numChannels: 1,
              sampleFrequencyHz: 24000,
            },
            chat: { minVersion: 1, maxVersion: 1 },
            control: { minVersion: 1, maxVersion: 3 },
            input: { minVersion: 1, maxVersion: 9 },
            message: { minVersion: 1, maxVersion: 1 },
            reliableinput: { minVersion: 9, maxVersion: 9 },
            unreliableinput: { minVersion: 9, maxVersion: 9 },
          },
        }),
      });
      return waitFor(async () => {
        const result = await fetch("/" + sessionPath + "/sdp").then(jsonOrNull);
        return result && result.exchangeResponse ? result : null;
      }, 30000, "SDP answer");
    }

    async function sendIce(sessionPath, candidates) {
      await fetch("/" + sessionPath + "/ice", {
        method: "POST",
        headers: { "accept": "application/json", "content-type": "application/json" },
        body: JSON.stringify({ iceCandidates: candidates }),
      });
      return waitFor(async () => {
        const result = await fetch("/" + sessionPath + "/ice").then(jsonOrNull);
        return result && result.exchangeResponse ? result : null;
      }, 30000, "ICE answer");
    }

    window.startXHomeSession = async function(serverId) {
      const client = new xCloudPlayer.default("videoHolder", {
        ui_systemui: [],
        ui_touchenabled: false,
        input_legacykeyboard: false
      });
      client.bind();
      const consoles = await getConsoles();
      const selected = serverId
        ? consoles.results.find((item) => item.serverId === serverId)
        : consoles.results[0];
      if (!selected) throw new Error("No xHome console matched");
      const stream = await startStream(selected.serverId);
      const offer = await client.createOffer();
      const sdpResponse = await sendSdp(stream.sessionPath, offer);
      client.setRemoteOffer(JSON.parse(sdpResponse.exchangeResponse).sdp);
      await waitFor(() => client.getIceCandidates().length > 0, 15000, "ICE candidates");
      const iceResponse = await sendIce(stream.sessionPath, client.getIceCandidates());
      client.setIceCandidates(JSON.parse(iceResponse.exchangeResponse));
      await waitFor(() => {
        const video = document.querySelector("video");
        return video && video.videoWidth > 0 && video.videoHeight > 0 && video.readyState >= 2;
      }, 90000, "video frame");
      await new Promise((resolve) => setTimeout(resolve, 1000));
      window.xboxctlSession = { client, stream, selected };
      return {
        sessionId: stream.sessionId,
        console: selected.deviceName,
      };
    };

    window.captureXHomeFrame = function(captureOptions) {
      if (!window.xboxctlSession) throw new Error("No active xHome session");
      const video = document.querySelector("video");
      const targetWidth = captureOptions.width > 0 ? captureOptions.width : video.videoWidth;
      const targetHeight = Math.round(video.videoHeight * (targetWidth / video.videoWidth));
      const canvas = document.createElement("canvas");
      canvas.width = targetWidth;
      canvas.height = targetHeight;
      canvas.getContext("2d").drawImage(video, 0, 0, targetWidth, targetHeight);
      const mimeType = captureOptions.format === "jpeg" ? "image/jpeg" : "image/png";
      const dataUrl = canvas.toDataURL(mimeType, captureOptions.quality / 100);
      return {
        dataUrl,
        width: targetWidth,
        height: targetHeight,
      };
    };

    window.pressXHomeButton = async function(button, repeat) {
      if (!window.xboxctlSession) throw new Error("No active xHome session");
      for (let index = 0; index < repeat; index += 1) {
        window.xboxctlSession.client._inputDriver.pressButton(0, button);
        await new Promise((resolve) => setTimeout(resolve, 160));
      }
    };

    window.closeXHomeSession = function() {
      if (window.xboxctlSession) {
        window.xboxctlSession.client.close();
      }
    };
  </script>
</body>`;
}

async function startServer(context, control = null) {
  const asset = await readFile(PLAYER_ASSET);
  const server = createServer(async (request, response) => {
    try {
      const url = new URL(request.url || "/", "http://127.0.0.1");
      if (url.pathname === "/") {
        response.writeHead(200, { "content-type": "text/html" });
        response.end(html());
      } else if (url.pathname === "/assets/xCloudPlayer.min.js") {
        response.writeHead(200, { "content-type": "text/javascript" });
        response.end(asset);
      } else if (url.pathname.startsWith("/v5/") || url.pathname.startsWith("/v6/")) {
        await proxyXboxRequest(request, response, context);
      } else if (isSessionRequest(url)) {
        await handleSessionRequest(request, response, url, control);
      } else {
        response.writeHead(404);
        response.end();
      }
    } catch (error) {
      response.writeHead(500, { "content-type": "text/plain" });
      response.end(error instanceof Error ? error.message : String(error));
    }
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  return server;
}

async function stopSession(context, sessionId) {
  if (!sessionId) return;
  await fetch(new URL(`/v5/sessions/home/${sessionId}`, context.baseUri), {
    method: "DELETE",
    headers: {
      authorization: `Bearer ${context.gsToken}`,
      "content-type": "application/json",
    },
  }).catch(() => undefined);
}

function captureOptions(args, overrides = {}) {
  const format = overrides.format || args.format;
  return {
    format,
    width: Number(overrides.width ?? args.width),
    quality: Number(overrides.quality ?? args.quality),
    contentType: format === "jpeg" ? "image/jpeg" : "image/png",
  };
}

async function writeDataUrl(output, dataUrl) {
  const data = Buffer.from(dataUrl.split(",")[1], "base64");
  await writeFile(output, data);
}

async function captureOne(page, args) {
  const started = await page.evaluate(
    ([serverId]) => window.startXHomeSession(serverId),
    [args.serverId],
  );
  if (args.settleMs > 0) {
    await new Promise((resolve) => setTimeout(resolve, args.settleMs));
  }
  const frame = await page.evaluate(
    ([options]) => window.captureXHomeFrame(options),
    [captureOptions(args)],
  );
  await writeDataUrl(args.output, frame.dataUrl);
  return {
    sessionId: started.sessionId,
    summary: {
      output: args.output,
      console: started.console,
      width: frame.width,
      height: frame.height,
    },
  };
}

async function runFlow(page, args) {
  await mkdir(args.outputDir, { recursive: true });
  const started = await page.evaluate(
    ([serverId]) => window.startXHomeSession(serverId),
    [args.serverId],
  );
  if (args.settleMs > 0) {
    await new Promise((resolve) => setTimeout(resolve, args.settleMs));
  }
  const captures = [];
  for (const rawStep of args.steps) {
    const step = parseStep(rawStep);
    if (step.kind === "capture") {
      const frame = await page.evaluate(
        ([options]) => window.captureXHomeFrame(options),
        [captureOptions(args)],
      );
      const extension = args.format === "jpeg" ? "jpg" : "png";
      const output = join(args.outputDir, `${safeCaptureName(step.name)}.${extension}`);
      await writeDataUrl(output, frame.dataUrl);
      captures.push({ output, width: frame.width, height: frame.height });
    } else if (step.kind === "press") {
      await page.evaluate(
        ([button, repeat]) => window.pressXHomeButton(button, repeat),
        [step.button, step.repeat],
      );
    } else if (step.kind === "wait") {
      await new Promise((resolve) => setTimeout(resolve, step.delayMs));
    }
  }
  return {
    sessionId: started.sessionId,
    summary: {
      outputDir: args.outputDir,
      console: started.console,
      captures,
    },
  };
}

function createControl(page, args, stop) {
  let idleTimer;
  const control = {
    token: args.sessionToken,
    touch() {
      clearTimeout(idleTimer);
      idleTimer = setTimeout(() => stop(), args.idleTimeoutMs);
    },
    async capture(overrides) {
      const options = captureOptions(args, overrides);
      const frame = await page.evaluate(
        ([capture]) => window.captureXHomeFrame(capture),
        [options],
      );
      return { dataUrl: frame.dataUrl, contentType: options.contentType };
    },
    async press(button, repeat) {
      await page.evaluate(
        ([buttonName, count]) => window.pressXHomeButton(buttonName, count),
        [button, repeat],
      );
    },
    stop,
  };
  control.touch();
  return control;
}

async function closeBrowserPages(browser) {
  const pages = browser.contexts().flatMap((browserContext) => browserContext.pages());
  await Promise.all(
    pages.map((page) =>
      page.evaluate(() => window.closeXHomeSession()).catch(() => undefined),
    ),
  );
}

async function serveSession(args, context) {
  let stopResolve;
  const stopped = new Promise((resolve) => {
    stopResolve = resolve;
  });
  const serverControl = { token: args.sessionToken };
  const server = await startServer(context, serverControl);
  const address = server.address();
  if (typeof address !== "object" || address === null) {
    throw new ObserveFailure("Could not start observe proxy server");
  }
  let browser;
  let sessionId = "";
  try {
    browser = await chromium.launch({
      headless: true,
      args: ["--autoplay-policy=no-user-gesture-required"],
    });
    const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
    await page.goto(`http://127.0.0.1:${address.port}/`);
    const started = await page.evaluate(
      ([serverId]) => window.startXHomeSession(serverId),
      [args.serverId],
    );
    sessionId = started.sessionId;
    if (args.settleMs > 0) {
      await new Promise((resolve) => setTimeout(resolve, args.settleMs));
    }
    const control = createControl(page, args, () => stopResolve());
    Object.assign(serverControl, control);
    await writeFile(
      args.sessionFile,
      JSON.stringify(
        {
          pid: process.pid,
          port: address.port,
          token: args.sessionToken,
        },
        null,
        2,
      ),
    );
    await stopped;
  } finally {
    await unlink(args.sessionFile).catch(() => undefined);
    if (browser) {
      await closeBrowserPages(browser);
      await browser.close().catch(() => undefined);
    }
    await stopSession(context, sessionId);
    await new Promise((resolve) => server.close(resolve));
  }
}

async function main() {
  const args = parseArgs(process.argv);
  const context = await streamingContext(args.tokens);
  if (args.serve) {
    await serveSession(args, context);
    return;
  }
  const server = await startServer(context);
  const address = server.address();
  if (typeof address !== "object" || address === null) {
    throw new ObserveFailure("Could not start observe proxy server");
  }
  let browser;
  let sessionId = "";
  try {
    browser = await chromium.launch({
      headless: true,
      args: ["--autoplay-policy=no-user-gesture-required"],
    });
    const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
    await page.goto(`http://127.0.0.1:${address.port}/`);
    const result = args.output
      ? await captureOne(page, args)
      : await runFlow(page, args);
    sessionId = result.sessionId;
    console.log(JSON.stringify(result.summary));
  } finally {
    if (browser) {
      await closeBrowserPages(browser);
    }
    if (browser) await browser.close().catch(() => undefined);
    await stopSession(context, sessionId);
    await new Promise((resolve) => server.close(resolve));
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
