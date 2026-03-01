import { afterEach, describe, expect, it, vi } from "vitest";

const spawnMock = vi.hoisted(() => vi.fn());

vi.mock("node:child_process", () => ({
  spawn: (...args: unknown[]) => spawnMock(...args),
}));

import { restartGatewayProcessWithFreshPid } from "./process-respawn.js";

const originalEnv = { ...process.env };
const originalArgv = [...process.argv];
const originalExecArgv = [...process.execArgv];

function restoreEnv() {
  for (const key of Object.keys(process.env)) {
    if (!(key in originalEnv)) {
      delete process.env[key];
    }
  }
  for (const [key, value] of Object.entries(originalEnv)) {
    if (value === undefined) {
      delete process.env[key];
    } else {
      process.env[key] = value;
    }
  }
}

afterEach(() => {
  restoreEnv();
  process.argv = [...originalArgv];
  process.execArgv = [...originalExecArgv];
  spawnMock.mockReset();
});

function clearSupervisorHints() {
  delete process.env.OPENCLAW_SUPERVISED;
  delete process.env.LAUNCH_JOB_LABEL;
  delete process.env.LAUNCH_JOB_NAME;
  delete process.env.INVOCATION_ID;
  delete process.env.SYSTEMD_EXEC_PID;
  delete process.env.JOURNAL_STREAM;
}

describe("restartGatewayProcessWithFreshPid", () => {
  it("returns disabled when OPENCLAW_NO_RESPAWN is set", () => {
    process.env.OPENCLAW_NO_RESPAWN = "1";
    const result = restartGatewayProcessWithFreshPid();
    expect(result.mode).toBe("disabled");
    expect(spawnMock).not.toHaveBeenCalled();
  });

  it("returns supervised when launchd/systemd hints are present", () => {
    process.env.LAUNCH_JOB_LABEL = "ai.openclaw.gateway";
    const result = restartGatewayProcessWithFreshPid();
    expect(result.mode).toBe("supervised");
    expect(spawnMock).not.toHaveBeenCalled();
  });

  it("spawns detached child with current exec argv", () => {
    delete process.env.OPENCLAW_NO_RESPAWN;
    clearSupervisorHints();
    process.execArgv = ["--import", "tsx"];
    process.argv = ["/usr/local/bin/node", "/repo/dist/index.js", "gateway", "run"];
    spawnMock.mockReturnValue({ pid: 4242, unref: vi.fn() });

    const result = restartGatewayProcessWithFreshPid();

    expect(result).toEqual({ mode: "spawned", pid: 4242 });
    expect(spawnMock).toHaveBeenCalledWith(
      process.execPath,
      ["--import", "tsx", "/repo/dist/index.js", "gateway", "run"],
      expect.objectContaining({
        detached: true,
        stdio: "inherit",
      }),
    );
  });

  it("returns failed when spawn throws", () => {
    delete process.env.OPENCLAW_NO_RESPAWN;
    clearSupervisorHints();

    spawnMock.mockImplementation(() => {
      throw new Error("spawn failed");
    });
    const result = restartGatewayProcessWithFreshPid();
    expect(result.mode).toBe("failed");
    expect(result.detail).toContain("spawn failed");
  });

  // FIX 1 — isLikelySupervisedProcess() checks OPENCLAW_SUPERVISED env var
  describe("isLikelySupervisedProcess() via OPENCLAW_SUPERVISED (fix 1)", () => {
    it("returns supervised mode when OPENCLAW_SUPERVISED=1 is set", () => {
      delete process.env.OPENCLAW_NO_RESPAWN;
      clearSupervisorHints();
      process.env.OPENCLAW_SUPERVISED = "1";
      const result = restartGatewayProcessWithFreshPid();
      expect(result.mode).toBe("supervised");
      expect(spawnMock).not.toHaveBeenCalled();
    });

    it("returns supervised mode when OPENCLAW_SUPERVISED=true is set", () => {
      delete process.env.OPENCLAW_NO_RESPAWN;
      clearSupervisorHints();
      process.env.OPENCLAW_SUPERVISED = "true";
      const result = restartGatewayProcessWithFreshPid();
      expect(result.mode).toBe("supervised");
    });

    it("returns supervised mode when legacy launchd/systemd hints are present (original behaviour)", () => {
      delete process.env.OPENCLAW_NO_RESPAWN;
      clearSupervisorHints();
      process.env.LAUNCH_JOB_LABEL = "ai.openclaw.gateway";
      const result = restartGatewayProcessWithFreshPid();
      expect(result.mode).toBe("supervised");
    });

    it("returns supervised mode when INVOCATION_ID is set (systemd)", () => {
      delete process.env.OPENCLAW_NO_RESPAWN;
      clearSupervisorHints();
      process.env.INVOCATION_ID = "abc123";
      const result = restartGatewayProcessWithFreshPid();
      expect(result.mode).toBe("supervised");
    });

    it("spawns (not supervised) when no supervisor env vars are present", () => {
      delete process.env.OPENCLAW_NO_RESPAWN;
      clearSupervisorHints();
      spawnMock.mockReturnValue({ pid: 9999, unref: vi.fn() });
      const result = restartGatewayProcessWithFreshPid();
      expect(result.mode).toBe("spawned");
      expect(spawnMock).toHaveBeenCalledTimes(1);
    });
  });
});
