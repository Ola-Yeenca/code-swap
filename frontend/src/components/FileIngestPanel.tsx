import { useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { ingestFile, presignUpload } from "../api/client";

interface Props {
  onReady: (fileId?: string) => void;
  workspaceId?: string;
}

export function FileIngestPanel({ onReady, workspaceId }: Props) {
  const [selectedName, setSelectedName] = useState("");
  const [status, setStatus] = useState<string>("");

  const presign = useMutation({ mutationFn: presignUpload });
  const ingest = useMutation({ mutationFn: ingestFile });

  async function onFileChange(file?: File) {
    if (!file) {
      return;
    }
    setSelectedName(file.name);
    setStatus("Registering file...");

    try {
      const created = await presign.mutateAsync({
        filename: file.name,
        mimeType: file.type || "application/octet-stream",
        sizeBytes: file.size,
        workspaceId,
      });

      setStatus("Ingesting file...");
      await ingest.mutateAsync(created.fileId);
      setStatus(`Ready: ${created.fileId}`);
      onReady(created.fileId);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Upload failed");
      onReady(undefined);
    }
  }

  return (
    <section className="panel p-4">
      <h2 className="font-display text-lg font-semibold">File Analysis</h2>
      <p className="mt-1 text-sm text-slate-600">Attach a file to include ingested context in prompts.</p>

      <label className="mt-3 block rounded border border-dashed border-slate-400 p-3 text-sm">
        <input
          className="hidden"
          type="file"
          onChange={(event) => onFileChange(event.target.files?.[0])}
        />
        <span>{selectedName ? `Selected: ${selectedName}` : "Choose file"}</span>
      </label>

      {status ? <p className="mt-2 text-xs text-slate-700">{status}</p> : null}
    </section>
  );
}
