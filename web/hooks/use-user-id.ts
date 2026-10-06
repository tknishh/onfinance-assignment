"use client";

import { useSyncExternalStore } from "react";
import { v4 as uuidv4 } from "uuid";

const KEY = "uml_uid";

function subscribe() {
  return () => {};
}

function getClientId(): string {
  let existing = localStorage.getItem(KEY);
  if (!existing) {
    existing = uuidv4();
    localStorage.setItem(KEY, existing);
  }
  return existing;
}

function getServerId(): string | null {
  return null;
}

export function useUserId(): string | null {
  return useSyncExternalStore(subscribe, getClientId, getServerId);
}
