import { api } from "@/lib/api";
import type { Job } from "@/lib/types";

const DEFAULT_DEADLINE_MS = 10 * 60 * 1000;

/** Poll a job until it settles. Backs off from 1.5s to 4s; gives up after `deadlineMs`
 * (default 10 min) so a stuck worker can't wedge the caller's UI forever. */
export async function waitForJob(
  jobId: string,
  onTick?: (j: Job) => void,
  signal?: AbortSignal,
  deadlineMs = DEFAULT_DEADLINE_MS,
): Promise<Job> {
  const deadline = Date.now() + deadlineMs;
  let delay = 1500;
  for (;;) {
    if (signal?.aborted) throw new Error("cancelled");
    if (Date.now() > deadline) throw new Error("timed out");
    const j = await api<Job>(`/jobs/${jobId}`);
    onTick?.(j);
    if (j.status === "done" || j.status === "failed") return j;
    await new Promise((r) => setTimeout(r, delay));
    delay = Math.min(4000, delay * 1.3);
  }
}
