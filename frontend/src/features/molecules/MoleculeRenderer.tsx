import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { apiClient, ApiError, queryKeys } from "../../api";
import { Molecule2DRenderer } from "./Molecule2DRenderer";
import { Molecule3DRenderer } from "./Molecule3DRenderer";

type StructureMode = "2d" | "3d";

export function MoleculeRenderer({
  canonicalSmiles,
  moleculeId,
}: {
  canonicalSmiles: string;
  moleculeId: number;
}) {
  const [mode, setMode] = useState<StructureMode>("2d");
  const [requestId, setRequestId] = useState(0);
  const [viewerError, setViewerError] = useState(false);
  const structure = useQuery({
    queryKey: queryKeys.molecules.structure3d(moleculeId, requestId),
    queryFn: ({ signal }) => apiClient.molecule3dStructure(moleculeId, { signal }),
    enabled: mode === "3d" && requestId > 0,
    gcTime: 0,
  });

  function show2d() {
    setMode("2d");
    setViewerError(false);
  }

  function show3d() {
    setViewerError(false);
    setRequestId((current) => current + 1);
    setMode("3d");
  }

  return (
    <div className="molecule-renderer" aria-label="Molecule structure preview">
      <div className="molecule-renderer__mode-toggle" aria-label="Structure display mode">
        <button
          aria-pressed={mode === "2d"}
          className={mode === "2d" ? "is-active" : undefined}
          onClick={show2d}
          type="button"
        >
          2D
        </button>
        <button
          aria-pressed={mode === "3d"}
          className={mode === "3d" ? "is-active" : undefined}
          onClick={show3d}
          type="button"
        >
          3D
        </button>
      </div>
      {mode === "2d" ? <Molecule2DRenderer canonicalSmiles={canonicalSmiles} /> : null}
      {mode === "3d" && structure.isPending ? (
        <p className="molecule-renderer__status">Generating 3D structure…</p>
      ) : null}
      {mode === "3d" && structure.data && !viewerError ? (
        <Molecule3DRenderer molBlock={structure.data.mol_block} onError={() => setViewerError(true)} />
      ) : null}
      {mode === "3d" && (structure.error || viewerError) ? (
        <div className="molecule-renderer__error" role="alert">
          <p>{errorMessage(structure.error, viewerError)}</p>
          <button onClick={show3d} type="button">
            Retry
          </button>
        </div>
      ) : null}
    </div>
  );
}

function errorMessage(error: Error | null, viewerError: boolean) {
  if (viewerError) return "The 3D structure could not be displayed.";
  return error instanceof ApiError ? error.message : "The 3D structure could not be generated.";
}
