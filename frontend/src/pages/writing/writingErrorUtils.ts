import { ApiError } from "../../services/apiClient";

export function extractMissingNumbers(err: unknown): number[] {
  if (!(err instanceof ApiError)) return [];
  if (err.code !== "CHAPTER_PREREQ_MISSING") return [];

  const details = err.details;
  if (!details || typeof details !== "object") return [];
  if (!("missing_numbers" in details)) return [];

  const missing = (details as { missing_numbers?: unknown }).missing_numbers;
  if (!Array.isArray(missing)) return [];
  return missing.filter((n): n is number => typeof n === "number");
}
