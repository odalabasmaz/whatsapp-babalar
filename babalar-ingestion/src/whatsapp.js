const { Client, LocalAuth } = require("whatsapp-web.js");
const qrcode = require("qrcode-terminal");
const QRCode = require("qrcode");
const fs = require("fs");
const path = require("path");
const { setQR, clearQR } = require("./api-client");

function clearChromiumLocks(sessionPath) {
  const patterns = ["SingletonLock", "SingletonCookie", "SingletonSocket"];
  try {
    const walk = (dir) => {
      if (!fs.existsSync(dir)) return;
      for (const f of fs.readdirSync(dir)) {
        const full = path.join(dir, f);
        if (patterns.includes(f)) {
          fs.unlinkSync(full);
          console.log(`[whatsapp] Removed lock: ${full}`);
        } else if (fs.statSync(full).isDirectory()) {
          walk(full);
        }
      }
    };
    walk(sessionPath);
  } catch (e) {}
}

async function initWhatsApp() {
  clearChromiumLocks("./session");

  const client = new Client({
    authStrategy: new LocalAuth({ dataPath: "./session" }),
    puppeteer: {
      executablePath: process.env.PUPPETEER_EXECUTABLE_PATH || undefined,
      headless: true,
      protocolTimeout: 600000, // 10 min — loading full group history can take a while
      args: [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-blink-features=AutomationControlled",
        "--disable-features=IsolateOrigins,site-per-process",
        "--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
      ],
    },
  });

  client.on("qr", async (qr) => {
    console.log("\n[whatsapp] Scan QR code:");
    qrcode.generate(qr, { small: true });
    try {
      const dataUrl = await QRCode.toDataURL(qr, { width: 300, margin: 2 });
      await setQR(dataUrl);
      console.log("[whatsapp] QR posted to backend.");
    } catch (e) {
      console.warn("[whatsapp] Could not post QR to backend:", e.message);
    }
  });

  client.on("authenticated", async () => {
    console.log("[whatsapp] Session authenticated.");
    try { await clearQR(); } catch (_) {}
  });

  client.on("auth_failure", (msg) => {
    console.error("[whatsapp] Auth failure:", msg);
    process.exit(1);
  });

  client.on("disconnected", (reason) => {
    console.warn("[whatsapp] Disconnected:", reason);
    if (reason === "LOGOUT") {
      console.warn("[whatsapp] LOGOUT detected — clearing session and restarting...");
      try { fs.rmSync("./session", { recursive: true, force: true }); } catch (_) {}
      process.exit(1);
    }
  });

  await new Promise((resolve) => {
    client.on("ready", async () => {
      console.log("[whatsapp] Connected. Waiting for sync (10s)...");
      await new Promise((r) => setTimeout(r, 10000));
      console.log("[whatsapp] Ready.");
      resolve();
    });
    client.initialize();
  });

  return client;
}

// Fetch messages available in the current WhatsApp web session's in-memory cache.
// whatsapp-web.js only has access to messages WhatsApp web has loaded — typically the last
// ~50–100 per group on fresh connection. loadEarlierMsgs only works for actively viewed chats.
async function* streamGroupMessages(chat, since) {
  const PAGE_SIZE = 100;

  // Large limit so fetchMessages calls loadEarlierMsgs repeatedly until it runs out of history.
  // 200k covers ~10 years even for very active groups; WhatsApp stops loading when history is exhausted.
  const all = await chat.fetchMessages({ limit: 200000 });

  const filtered = [];
  for (const msg of all) {
    const msgDate = new Date(msg.timestamp * 1000);
    if (msgDate <= since) continue;
    if (msg.body && msg.body.trim().length >= 10) {
      filtered.push({
        sender_name: msg._data.notifyName || msg.author || null,
        content: msg.body,
        sent_at: msgDate.toISOString(),
      });
    }
  }

  console.log(`[whatsapp] "${chat.name}": ${all.length} in cache, ${filtered.length} new after ${since.toISOString().slice(0,10)}.`);

  for (let i = 0; i < filtered.length; i += PAGE_SIZE) {
    yield filtered.slice(i, i + PAGE_SIZE);
  }
}

module.exports = { initWhatsApp, streamGroupMessages };
