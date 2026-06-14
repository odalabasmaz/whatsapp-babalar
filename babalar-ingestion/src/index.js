const fs = require("fs");
const cron = require("node-cron");
const { initWhatsApp } = require("./whatsapp");
const { runIngestion } = require("./scheduler");
const { checkTrigger, checkReconnect } = require("./api-client");

const CRON = process.env.INGEST_CRON || "0 2 * * *";
const POLL_INTERVAL_MS = 30_000;

async function main() {
  console.log("[babalar-ingestion] Starting...");
  const client = await initWhatsApp();

  let isRunning = false;

  async function safeRun(reason, targetGroupId = null) {
    if (isRunning) return;
    isRunning = true;
    const label = targetGroupId ? `group:${targetGroupId}` : "all";
    console.log(`[babalar-ingestion] Running ingestion (${reason}, ${label})...`);
    try {
      await runIngestion(client, targetGroupId);
    } catch (err) {
      console.error("[babalar-ingestion] Ingestion error:", err);
    } finally {
      isRunning = false;
    }
  }

  console.log(`[babalar-ingestion] Cron scheduled: ${CRON}`);
  cron.schedule(CRON, () => safeRun("cron", null));

  // Poll for manual triggers, new unprocessed groups, and reconnect requests
  setInterval(async () => {
    try {
      const { reconnect } = await checkReconnect();
      if (reconnect) {
        console.log("[babalar-ingestion] Reconnect requested — clearing session and restarting...");
        try { fs.rmSync("./session", { recursive: true, force: true }); } catch (_) {}
        process.exit(0);
      }
    } catch (_) {}

    if (isRunning) return;
    try {
      const { should_run, group_id } = await checkTrigger();
      if (should_run) safeRun("trigger", group_id || null);
    } catch (_) {}
  }, POLL_INTERVAL_MS);

  console.log("[babalar-ingestion] Ready.");

  if (process.env.RUN_NOW === "true") {
    await safeRun("startup");
  }
}

main().catch((err) => {
  console.error("[babalar-ingestion] Fatal:", err);
  process.exit(1);
});
