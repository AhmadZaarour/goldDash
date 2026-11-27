import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { get } from "./api";
import type { Values } from "./ui";

export type DefaultLocation = { location_id: number | null };
export const defaultLocationKey = ["settings", "default-location"];

export function useDefaultLocation(enabled = true) {
  return useQuery({
    queryKey: defaultLocationKey,
    queryFn: () => get<DefaultLocation>("/locations/default"),
    enabled,
  });
}

export function useLocationChoice(fallback = "") {
  const [choice, setChoice] = useState<string>();
  const locationId = useDefaultLocation().data?.location_id;
  return [choice ?? String(locationId ?? fallback), setChoice] as const;
}

export function useLocationValues(
  initial: Values = {},
  locationKey: string | null = "location_id",
) {
  const [values, setValues] = useState(initial);
  const locationId = useDefaultLocation(locationKey !== null).data?.location_id;
  const effectiveValues =
    locationKey && locationId && values[locationKey] === undefined
      ? { ...values, [locationKey]: String(locationId) }
      : values;
  return [effectiveValues, setValues] as const;
}
