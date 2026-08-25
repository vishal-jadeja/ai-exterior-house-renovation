import { api } from "@/lib/api";
import type { Job } from "@/lib/types";

/** Poll a job until it settles. Backs off from 1.5s to 4s. */
export async function waitForJob(jobId: string, onTick?: (j: Job) => void, signal?: AbortSignal): Promise<Job> {
  let delay = 1500;
  for (;;) {
    if (signal?.aborted) throw new Error("cancelled");
    const j = await api<Job>(`/jobs/${jobId}`);
    onTick?.(j);
    if (j.status === "done" || j.status === "failed") return j;
    await new Promise((r) => setTimeout(r, delay));
    delay = Math.min(4000, delay * 1.3);
  }
}
