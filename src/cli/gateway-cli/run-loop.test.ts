import { afterEach, describe, expect, it, vi } from "vitest";

const acquireGatewayLock = vi.fn(async () => ({
  release: vi.fn(async () => {}),
}));
const consumeGatewaySigusr1RestartAuthorization = vi.fn(() => true);
const isGatewaySigusr1RestartExternallyAllowed = vi.fn(() => false);
const markGatewaySigusr1RestartHandled = vi.fn();
const getActiveTaskCount = vi.fn(() => 0);
const waitForActiveTasks = vi.fn(async () => ({ drained: true }));
const resetAllLanes = vi.fn();
const DRAIN_TIMEOUT_LOG = "drain timeout reached; proceeding with restart";
const gatewayLog = {
  info: vi.fn(),
  warn: vi.fn(),
  error: vi.fn(),
};

vi.mock("../../infra/gateway-lock.js", () => ({
  acquireGatewayLock: () => acquireGatewayLock(),
}));

vi.mock("../../infra/restart.js", () => ({
  consumeGatewaySigusr1RestartAuthorization: () => consumeGatewaySigusr1RestartAuthorization(),
  isGatewaySigusr1RestartExternallyAllowed: () => isGatewaySigusr1RestartExternallyAllowed(),
  markGatewaySigusr1RestartHandled: () => markGatewaySigusr1RestartHandled(),
}));

const restartGatewayProcessWithFreshPidMock = vi.fn(() => ({ mode: "skipped" as string }));

vi.mock("../../infra/process-respawn.js", () => ({
  restartGatewayProcessWithFreshPid: () => restartGatewayProcessWithFreshPidMock(),
}));

vi.mock("../../process/command-queue.js", () => ({
  getActiveTaskCount: () => getActiveTaskCount(),
  waitForActiveTasks: (timeoutMs: number) => waitForActiveTasks(timeoutMs),
  resetAllLanes: () => resetAllLanes(),
}));

vi.mock("../../logging/subsystem.js", () => ({
  createSubsystemLogger: () => gatewayLog,
}));

function removeNewSignalListeners(
  signal: NodeJS.Signals,
  existing: Set<(...args: unknown[]) => void>,
) {
  for (const listener of process.listeners(signal)) {
    const fn = listener as (...args: unknown[]) => void;
    if (!existing.has(fn)) {
      process.removeListener(signal, fn);
    }
  }
}

// FIX 2 — exits with code 1 on supervised restart, code 0 on spawned restart
describe("runGatewayLoop exit codes (fix 2)", () => {
  afterEach(() => {
    // Restore the mock to the neutral default used by other test suites in this file.
    restartGatewayProcessWithFreshPidMock.mockReset();
    restartGatewayProcessWithFreshPidMock.mockImplementation(() => ({ mode: "skipped" as string }));
    consumeGatewaySigusr1RestartAuthorization.mockReset();
    consumeGatewaySigusr1RestartAuthorization.mockImplementation(() => true);
    acquireGatewayLock.mockReset();
    acquireGatewayLock.mockImplementation(async () => ({ release: vi.fn(async () => {}) }));
  });

  async function runLoopWithRespawnMode(
    mode: "supervised" | "spawned",
  ): Promise<number | undefined> {
    restartGatewayProcessWithFreshPidMock.mockReset();
    restartGatewayProcessWithFreshPidMock.mockReturnValue({ mode, pid: 1234 });
    consumeGatewaySigusr1RestartAuthorization.mockReset();
    consumeGatewaySigusr1RestartAuthorization.mockReturnValue(true);
    acquireGatewayLock.mockReset();
    acquireGatewayLock.mockResolvedValue({ release: vi.fn(async () => {}) });

    let capturedCode: number | undefined;
    const exitMock = vi.fn((code: number) => {
      capturedCode = code;
    }) as unknown as (code: number) => never;

    // start: first call returns a server; all subsequent calls stall indefinitely
    // (they'll never be reached because exit is called before the loop iterates)
    const start = vi
      .fn()
      .mockResolvedValueOnce({ close: vi.fn(async () => {}) })
      .mockImplementation(() => new Promise(() => {})); // hang forever on second call

    const beforeSigusr1 = new Set(
      process.listeners("SIGUSR1") as Array<(...args: unknown[]) => void>,
    );
    const newListeners: Array<(...args: unknown[]) => void> = [];

    const loopPromise = import("./run-loop.js").then(({ runGatewayLoop }) =>
      runGatewayLoop({ start, runtime: { exit: exitMock } }),
    );

    try {
      await vi.waitFor(() => expect(start).toHaveBeenCalledTimes(1));
      process.emit("SIGUSR1");
      // Wait until exit is called; then clean up listeners and return
      await vi.waitFor(() => expect(exitMock).toHaveBeenCalledTimes(1), { timeout: 10_000 });
      return capturedCode;
    } finally {
      // Remove any SIGUSR1 listeners registered by this test's loop
      for (const listener of process.listeners("SIGUSR1")) {
        const fn = listener as (...args: unknown[]) => void;
        if (!beforeSigusr1.has(fn)) process.removeListener("SIGUSR1", fn);
      }
      // Let the dangling loopPromise settle quietly (it will hang on start() forever
      // but vitest's fork pool will clean it up after the test suite finishes)
      loopPromise.catch(() => {});
    }
  }

  it("exits with code 1 when respawn mode is supervised", async () => {
    const code = await runLoopWithRespawnMode("supervised");
    expect(code).toBe(1);
  });

  it("exits with code 0 when respawn mode is spawned (no regression)", async () => {
    const code = await runLoopWithRespawnMode("spawned");
    expect(code).toBe(0);
  });
});

describe("runGatewayLoop", () => {
  it("restarts after SIGUSR1 even when drain times out, and resets lanes for the new iteration", async () => {
    vi.clearAllMocks();
    getActiveTaskCount.mockReturnValueOnce(2).mockReturnValueOnce(0);
    waitForActiveTasks.mockResolvedValueOnce({ drained: false });

    type StartServer = () => Promise<{
      close: (opts: { reason: string; restartExpectedMs: number | null }) => Promise<void>;
    }>;

    const closeFirst = vi.fn(async () => {});
    const closeSecond = vi.fn(async () => {});
    const start = vi
      .fn<StartServer>()
      .mockResolvedValueOnce({ close: closeFirst })
      .mockResolvedValueOnce({ close: closeSecond })
      .mockRejectedValueOnce(new Error("stop-loop"));

    const beforeSigterm = new Set(
      process.listeners("SIGTERM") as Array<(...args: unknown[]) => void>,
    );
    const beforeSigint = new Set(
      process.listeners("SIGINT") as Array<(...args: unknown[]) => void>,
    );
    const beforeSigusr1 = new Set(
      process.listeners("SIGUSR1") as Array<(...args: unknown[]) => void>,
    );

    const loopPromise = import("./run-loop.js").then(({ runGatewayLoop }) =>
      runGatewayLoop({
        start,
        runtime: {
          exit: vi.fn(),
        } as { exit: (code: number) => never },
      }),
    );

    try {
      await vi.waitFor(() => {
        expect(start).toHaveBeenCalledTimes(1);
      });

      process.emit("SIGUSR1");

      await vi.waitFor(() => {
        expect(start).toHaveBeenCalledTimes(2);
      });

      expect(waitForActiveTasks).toHaveBeenCalledWith(30_000);
      expect(gatewayLog.warn).toHaveBeenCalledWith(DRAIN_TIMEOUT_LOG);
      expect(closeFirst).toHaveBeenCalledWith({
        reason: "gateway restarting",
        restartExpectedMs: 1500,
      });
      expect(markGatewaySigusr1RestartHandled).toHaveBeenCalledTimes(1);
      expect(resetAllLanes).toHaveBeenCalledTimes(1);

      process.emit("SIGUSR1");

      await expect(loopPromise).rejects.toThrow("stop-loop");
      expect(closeSecond).toHaveBeenCalledWith({
        reason: "gateway restarting",
        restartExpectedMs: 1500,
      });
      expect(markGatewaySigusr1RestartHandled).toHaveBeenCalledTimes(2);
      expect(resetAllLanes).toHaveBeenCalledTimes(2);
    } finally {
      removeNewSignalListeners("SIGTERM", beforeSigterm);
      removeNewSignalListeners("SIGINT", beforeSigint);
      removeNewSignalListeners("SIGUSR1", beforeSigusr1);
    }
  });
});
