import type { CSSProperties } from "react";

export function Skeleton({ width = "100%", height = 16, radius }: { width?: string | number; height?: number; radius?: number }) {
  const style: CSSProperties = {
    width,
    height,
    borderRadius: radius ?? 6,
  };
  return <div className="argus-skeleton" style={style} />;
}
