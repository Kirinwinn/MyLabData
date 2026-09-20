import { useEffect, useRef } from "react";
import type { GLViewer } from "3dmol";

export function Molecule3DRenderer({ molBlock, onError }: { molBlock: string; onError: () => void }) {
  const target = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = target.current;
    if (!element) return;
    let disposed = false;
    let viewer: GLViewer | undefined;

    void import("3dmol")
      .then(({ createViewer }) => {
        if (disposed) return;
        viewer = createViewer(element, { backgroundColor: "#ffffff" });
        viewer.addModel(molBlock, "mol");
        viewer.setStyle({}, { stick: { radius: 0.16 }, sphere: { scale: 0.26 } });
        viewer.zoomTo();
        viewer.render();
      })
      .catch(() => {
        if (!disposed) onError();
      });

    return () => {
      disposed = true;
      viewer?.clear();
      element.replaceChildren();
    };
  }, [molBlock, onError]);

  return <div className="molecule-3d-renderer" aria-label="Interactive 3D molecule structure" ref={target} />;
}
