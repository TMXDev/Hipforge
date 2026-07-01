/**
 * Re-export from the Timeline component directory.
 * This shim exists because the project structure pre-created Timeline.tsx
 * as a stub; the actual implementation lives in components/Timeline/.
 */
export { default } from "./Timeline/Timeline";
export type { StageState, JobState, StageStatus } from "./Timeline/types";
