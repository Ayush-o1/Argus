"use client";

import type { Core } from "cytoscape";
import { useEffect, useRef } from "react";
import { RISK_COLOR_UNKNOWN, RISK_COLORS } from "@/lib/theme";
import styles from "./GraphMinimap.module.css";

/**
 * A scaled-down rendering of the whole graph with a draggable viewport
 * rectangle — deferred at Phase 4 on the reasoning that fit-to-screen +
 * pan/zoom covers wayfinding without it at this scale. That holds for the
 * ~20K-node default world; it stops holding the moment an analyst expands a
 * dense hub a few times and the canvas fills with nodes far outside the
 * current viewport, with no cue which direction to pan to find them. This is
 * a plain `<canvas>` redraw, not a second Cytoscape instance or a plugin —
 * the minimap only ever needs dots and a rectangle, which is cheaper to draw
 * by hand than to load a second render pipeline for.
 */

const WIDTH = 168;
const HEIGHT = 112;
const PADDING = 6;

const TIER_COLOR: Record<string, string> = {
  critical: RISK_COLORS.Critical,
  high: RISK_COLORS.High,
  medium: RISK_COLORS.Medium,
  low: RISK_COLORS.Low,
  none: RISK_COLOR_UNKNOWN,
};

interface Transform {
  scale: number;
  offsetX: number;
  offsetY: number;
}

interface GraphMinimapProps {
  cy: Core | null;
}

export function GraphMinimap({ cy }: GraphMinimapProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef = useRef<number | null>(null);
  const transformRef = useRef<Transform>({ scale: 1, offsetX: 0, offsetY: 0 });
  const draggingRef = useRef(false);

  useEffect(() => {
    if (!cy) return;
    const canvas = canvasRef.current;
    if (!canvas) return;

    const dpr = window.devicePixelRatio || 1;
    canvas.width = WIDTH * dpr;
    canvas.height = HEIGHT * dpr;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.scale(dpr, dpr);

    function draw() {
      if (!ctx || !cy) return;
      ctx.clearRect(0, 0, WIDTH, HEIGHT);

      const nodes = cy.nodes().filter((n) => n.visible());
      const bb = nodes.boundingBox();
      const bbW = Math.max(bb.w, 1);
      const bbH = Math.max(bb.h, 1);
      const scale = Math.min((WIDTH - PADDING * 2) / bbW, (HEIGHT - PADDING * 2) / bbH);
      const offsetX = (WIDTH - bbW * scale) / 2 - bb.x1 * scale;
      const offsetY = (HEIGHT - bbH * scale) / 2 - bb.y1 * scale;
      transformRef.current = { scale, offsetX, offsetY };

      nodes.forEach((n) => {
        const pos = n.position();
        ctx.fillStyle = TIER_COLOR[n.data("riskTier") as string] ?? RISK_COLOR_UNKNOWN;
        ctx.globalAlpha = n.hasClass("faded") ? 0.25 : 0.85;
        ctx.beginPath();
        ctx.arc(pos.x * scale + offsetX, pos.y * scale + offsetY, 1.6, 0, Math.PI * 2);
        ctx.fill();
      });
      ctx.globalAlpha = 1;

      // The visible viewport, in the same model→minimap transform as the
      // dots above — dragging this rectangle is dragging the real viewport.
      const ext = cy.extent();
      const rx = ext.x1 * scale + offsetX;
      const ry = ext.y1 * scale + offsetY;
      const rw = (ext.x2 - ext.x1) * scale;
      const rh = (ext.y2 - ext.y1) * scale;
      ctx.strokeStyle = "#3d7bff";
      ctx.lineWidth = 1.5;
      ctx.strokeRect(rx, ry, rw, rh);
      ctx.fillStyle = "rgba(61, 123, 255, 0.08)";
      ctx.fillRect(rx, ry, rw, rh);
    }

    function scheduleDraw() {
      if (rafRef.current !== null) return;
      rafRef.current = requestAnimationFrame(() => {
        rafRef.current = null;
        draw();
      });
    }

    draw();
    cy.on("pan zoom render add remove data position", scheduleDraw);

    return () => {
      cy.off("pan zoom render add remove data position", scheduleDraw);
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
  }, [cy]);

  function panTo(clientX: number, clientY: number) {
    if (!cy) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const x = clientX - rect.left;
    const y = clientY - rect.top;
    const { scale, offsetX, offsetY } = transformRef.current;
    const modelX = (x - offsetX) / scale;
    const modelY = (y - offsetY) / scale;
    cy.pan({ x: cy.width() / 2 - cy.zoom() * modelX, y: cy.height() / 2 - cy.zoom() * modelY });
  }

  function handlePointerDown(e: React.PointerEvent<HTMLCanvasElement>) {
    e.currentTarget.setPointerCapture(e.pointerId);
    draggingRef.current = true;
    panTo(e.clientX, e.clientY);
  }

  function handlePointerMove(e: React.PointerEvent<HTMLCanvasElement>) {
    if (!draggingRef.current) return;
    panTo(e.clientX, e.clientY);
  }

  function handlePointerUp(e: React.PointerEvent<HTMLCanvasElement>) {
    draggingRef.current = false;
    e.currentTarget.releasePointerCapture(e.pointerId);
  }

  if (!cy) return null;

  return (
    <div className={styles.minimap}>
      <canvas
        ref={canvasRef}
        style={{ width: WIDTH, height: HEIGHT }}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        role="button"
        aria-label="Graph overview — click or drag to navigate to that area"
      />
    </div>
  );
}
