"use client";

import { CalendarRange } from "lucide-react";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import {
  DATE_RANGE_PRESETS,
  type DateRangePreset,
} from "@/lib/analytics/date-range";

export function DateRangeSelector({
  preset,
  fromInput,
  toInput,
  error,
  onPresetChange,
  onFromChange,
  onToChange,
}: {
  preset: DateRangePreset;
  fromInput: string;
  toInput: string;
  error?: string;
  onPresetChange: (preset: DateRangePreset) => void;
  onFromChange: (value: string) => void;
  onToChange: (value: string) => void;
}) {
  return (
    <div className="w-full space-y-2 sm:w-72">
      <Label htmlFor="analytics-range" className="flex items-center gap-1.5">
        <CalendarRange className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
        Analytics range
      </Label>
      <Select
        id="analytics-range"
        value={preset}
        onChange={(event) => onPresetChange(event.target.value as DateRangePreset)}
        aria-describedby={error ? "analytics-range-error" : "analytics-range-hint"}
      >
        {DATE_RANGE_PRESETS.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </Select>

      {preset === "custom" ? (
        <div className="grid grid-cols-2 gap-2">
          <FormField label="From" htmlFor="analytics-from" error={undefined}>
            <Input
              id="analytics-from"
              type="date"
              value={fromInput}
              max={toInput || undefined}
              onChange={(event) => onFromChange(event.target.value)}
              aria-invalid={Boolean(error)}
            />
          </FormField>
          <FormField label="To" htmlFor="analytics-to" error={undefined}>
            <Input
              id="analytics-to"
              type="date"
              value={toInput}
              min={fromInput || undefined}
              onChange={(event) => onToChange(event.target.value)}
              aria-invalid={Boolean(error)}
            />
          </FormField>
        </div>
      ) : null}

      {error ? (
        <p id="analytics-range-error" className="text-xs text-destructive" role="alert">
          {error}
        </p>
      ) : (
        <p id="analytics-range-hint" className="text-xs text-muted-foreground">
          Applies to registration and check-in trends only.
        </p>
      )}
    </div>
  );
}
