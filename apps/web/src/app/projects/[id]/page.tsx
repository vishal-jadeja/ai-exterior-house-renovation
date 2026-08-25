"use client";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Shell } from "@/components/Shell";
import { UploadPanel } from "@/components/UploadPanel";
import { StructureStep } from "@/components/StructureStep";
import { DesignStep } from "@/components/DesignStep";
import { api } from "@/lib/api";
import type { ImageRec, Project, Region } from "@/lib/types";

export default function ProjectPage() {
  const { id } = useParams<{ id: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [image, setImage] = useState<ImageRec | null>(null);
  const [regions, setRegions] = useState<Region[]>([]);

  const load = useCallback(async () => {
    const [p, imgs] = await Promise.all([
      api<Project>(`/projects/${id}`),
      api<ImageRec[]>(`/projects/${id}/images?kind=sanitized`),
    ]);
    setProject(p);
    setImage(imgs[0] ?? null);
  }, [id]);
  // eslint-disable-next-line react-hooks/set-state-in-effect -- async fetch-then-set is the intended pattern here
  useEffect(() => { load().catch(() => {}); }, [load]);

  if (!project) return <Shell><p className="text-sm text-zinc-500">Loading project…</p></Shell>;

  return (
    <Shell>
      <div className="mb-4 flex items-center justify-between">
        <div>
          <Link href="/projects" className="text-xs text-zinc-500 hover:underline">← Projects</Link>
          <h1 className="text-2xl font-semibold">{project.name}</h1>
        </div>
        <span className="rounded-full bg-zinc-100 px-3 py-1 text-xs">{project.status} · {project.currency}</span>
      </div>

      <section className="grid gap-6 lg:grid-cols-[1fr_360px]">
        <div className="rounded-lg border bg-white p-4">
          <h2 className="mb-2 font-medium">1 · House photo</h2>
          {image?.url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={image.url} alt="House exterior" className="w-full rounded-md" />
          ) : (
            <p className="text-sm text-zinc-500">No photo yet. Upload one to begin.</p>
          )}
        </div>
        <div>
          <UploadPanel projectId={project.id} onUploaded={(img) => { setImage(img); load(); }} />
        </div>
      </section>

      {image && (
        <section className="mt-6">
          <StructureStep projectId={project.id} image={image} onRegionsChanged={setRegions} />
        </section>
      )}

      {regions.length > 0 && (
        <section className="mt-6">
          <DesignStep projectId={project.id} regions={regions} />
        </section>
      )}
    </Shell>
  );
}
