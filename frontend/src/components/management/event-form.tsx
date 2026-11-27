"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useState } from "react";
import { useForm, type FieldPath } from "react-hook-form";
import { Button } from "@/components/ui/button";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ManagementErrorState } from "@/components/management/management-error-state";
import type { EventRecord } from "@/lib/api/contracts";
import { validationFieldErrors } from "@/lib/management/errors";
import {
  eventFormSchema,
  eventToFormValues,
  type EventFormValues,
} from "@/lib/management/event-form";

export function EventForm({
  mode,
  event,
  onSubmit,
  submitLabel,
}: {
  mode: "create" | "edit";
  event?: EventRecord;
  onSubmit: (values: EventFormValues) => Promise<void>;
  submitLabel: string;
}) {
  const [submitError, setSubmitError] = useState<unknown | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<EventFormValues>({
    resolver: zodResolver(eventFormSchema),
    defaultValues: event ? eventToFormValues(event) : {
      slug: "",
      name: "",
      description: "",
      starts_at: "",
      ends_at: "",
      timezone: "UTC",
      venue: "",
      capacity: "",
      registration_opens_at: "",
      registration_closes_at: "",
    },
  });

  const onValidSubmit = handleSubmit(async (values) => {
    setSubmitError(null);
    try {
      await onSubmit(values);
    } catch (error) {
      const fieldErrors = validationFieldErrors(error);
      Object.entries(fieldErrors).forEach(([field, message]) => {
        setError(field as FieldPath<EventFormValues>, { type: "server", message });
      });
      setSubmitError(error);
    }
  });

  return (
    <form onSubmit={onValidSubmit} className="space-y-6" noValidate>
      {submitError ? <ManagementErrorState error={submitError} /> : null}

      <div className="grid gap-5 md:grid-cols-2">
        <FormField label="Slug" htmlFor="event-slug" error={errors.slug?.message} hint="Lowercase letters, numbers, and hyphens.">
          <Input
            id="event-slug"
            className="font-mono"
            readOnly={mode === "edit"}
            aria-invalid={Boolean(errors.slug)}
            aria-describedby={errors.slug ? "event-slug-error" : undefined}
            {...register("slug")}
          />
        </FormField>

        <FormField label="Name" htmlFor="event-name" error={errors.name?.message}>
          <Input
            id="event-name"
            maxLength={200}
            aria-invalid={Boolean(errors.name)}
            aria-describedby={errors.name ? "event-name-error" : undefined}
            {...register("name")}
          />
        </FormField>

        <FormField label="Starts at (UTC)" htmlFor="event-starts" error={errors.starts_at?.message}>
          <Input
            id="event-starts"
            type="datetime-local"
            step={60}
            aria-invalid={Boolean(errors.starts_at)}
            aria-describedby={errors.starts_at ? "event-starts-error" : undefined}
            {...register("starts_at")}
          />
        </FormField>

        <FormField label="Ends at (UTC)" htmlFor="event-ends" error={errors.ends_at?.message}>
          <Input
            id="event-ends"
            type="datetime-local"
            step={60}
            aria-invalid={Boolean(errors.ends_at)}
            aria-describedby={errors.ends_at ? "event-ends-error" : undefined}
            {...register("ends_at")}
          />
        </FormField>

        <FormField label="Time zone (IANA)" htmlFor="event-timezone" error={errors.timezone?.message} hint="For example, UTC or America/New_York.">
          <Input
            id="event-timezone"
            maxLength={64}
            aria-invalid={Boolean(errors.timezone)}
            aria-describedby={errors.timezone ? "event-timezone-error" : undefined}
            {...register("timezone")}
          />
        </FormField>

        <FormField label="Venue" htmlFor="event-venue" error={errors.venue?.message}>
          <Input
            id="event-venue"
            maxLength={200}
            aria-invalid={Boolean(errors.venue)}
            aria-describedby={errors.venue ? "event-venue-error" : undefined}
            {...register("venue")}
          />
        </FormField>

        <FormField label="Capacity" htmlFor="event-capacity" error={errors.capacity?.message} hint="Leave blank for no limit.">
          <Input
            id="event-capacity"
            type="number"
            min={1}
            max={1_000_000}
            aria-invalid={Boolean(errors.capacity)}
            aria-describedby={errors.capacity ? "event-capacity-error" : undefined}
            {...register("capacity")}
          />
        </FormField>

        <FormField label="Registration opens (UTC)" htmlFor="event-registration-opens" error={errors.registration_opens_at?.message}>
          <Input
            id="event-registration-opens"
            type="datetime-local"
            step={60}
            aria-invalid={Boolean(errors.registration_opens_at)}
            aria-describedby={errors.registration_opens_at ? "event-registration-opens-error" : undefined}
            {...register("registration_opens_at")}
          />
        </FormField>

        <FormField label="Registration closes (UTC)" htmlFor="event-registration-closes" error={errors.registration_closes_at?.message}>
          <Input
            id="event-registration-closes"
            type="datetime-local"
            step={60}
            aria-invalid={Boolean(errors.registration_closes_at)}
            aria-describedby={errors.registration_closes_at ? "event-registration-closes-error" : undefined}
            {...register("registration_closes_at")}
          />
        </FormField>

        <FormField label="Description" htmlFor="event-description" error={errors.description?.message} className="md:col-span-2">
          <Textarea
            id="event-description"
            maxLength={5000}
            rows={5}
            aria-invalid={Boolean(errors.description)}
            aria-describedby={errors.description ? "event-description-error" : undefined}
            {...register("description")}
          />
        </FormField>
      </div>

      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <Button asChild variant="outline" type="button">
          <Link href={event ? `/events/${encodeURIComponent(event.slug)}` : "/events"}>
            Cancel
          </Link>
        </Button>
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Saving…" : submitLabel}
        </Button>
      </div>
    </form>
  );
}
