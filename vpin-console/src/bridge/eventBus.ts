import type { EventLogEntry, InferenceEvent } from "./types";

type Listener<T> = (payload: T) => void;

class SimpleBus<T> {
  private listeners = new Set<Listener<T>>();

  subscribe(fn: Listener<T>): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  emit(payload: T): void {
    for (const fn of this.listeners) fn(payload);
  }
}

export const inferenceEventBus = new SimpleBus<InferenceEvent>();
export const eventLogBus = new SimpleBus<EventLogEntry>();

let logSeq = 0;

export function appendEventLog(
  channel: string,
  message: string,
  level: EventLogEntry["level"] = "info",
): EventLogEntry {
  const entry: EventLogEntry = {
    id: `log-${++logSeq}`,
    ts: new Date().toISOString().slice(11, 23),
    channel,
    message,
    level,
  };
  eventLogBus.emit(entry);
  return entry;
}

export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
