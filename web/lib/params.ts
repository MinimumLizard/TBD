import { notFound } from "next/navigation";

/** A path segment decoded, or a 404 for a malformed one (e.g. a broken %-sequence). */
export function decodeSegment(raw: string): string {
  try {
    return decodeURIComponent(raw);
  } catch {
    notFound();
  }
}
