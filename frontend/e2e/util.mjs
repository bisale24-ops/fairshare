import { randomBytes } from "node:crypto";

/** Unique per run even when several runs start in the same millisecond (parallel CI jobs, stress runs). */
export const uid = () => `${Date.now()}${randomBytes(3).toString("hex")}`;
