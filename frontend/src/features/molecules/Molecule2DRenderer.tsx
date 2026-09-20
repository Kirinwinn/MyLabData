import { useEffect, useRef } from "react";
import SmilesDrawer from "smiles-drawer";

export function Molecule2DRenderer({ canonicalSmiles }: { canonicalSmiles: string }) {
  const target = useRef<SVGSVGElement>(null);

  useEffect(() => {
    const svg = target.current;
    if (!svg) return;

    svg.replaceChildren();
    const drawer = new SmilesDrawer.SvgDrawer({
      width: 620,
      height: 500,
      padding: 24,
      compactDrawing: false,
    });
    SmilesDrawer.parse(
      canonicalSmiles,
      (tree) => drawer.draw(tree, svg, "light"),
      () => svg.replaceChildren(),
    );
  }, [canonicalSmiles]);

  return (
    <div className="molecule-2d-renderer" aria-label="2D molecule structure">
      <svg ref={target} role="img" aria-label="2D molecular structure" />
    </div>
  );
}
