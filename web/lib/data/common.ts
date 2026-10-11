import "server-only";

import { type Access, type Granted, type Viewer, authorize } from "../entitlements";
import type { ModelName } from "../registry";

export interface Result<T> {
  access: Access;
  data: T | null; // null whenever access is denied: the data is never read, so it cannot be sent
}

export async function withModel<T>(viewer: Viewer, model: ModelName, read: (granted: Granted) => Promise<T>): Promise<Result<T>> {
  const access = authorize(viewer, model);
  if (!access.allowed) return { access, data: null };
  return { access, data: await read(access) };
}

/** The requested date if it is allowed, else the latest the access allows (a free preview stops at its date). */
export function cappedDate(access: Granted, requested: string | undefined): string | undefined {
  if (!requested) return access.maxDate ?? undefined;
  if (access.maxDate && requested > access.maxDate) return access.maxDate;
  return requested;
}
