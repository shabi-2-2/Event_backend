import {
  CalendarCheck2,
  CalendarX2,
  CheckCircle2,
  CircleSlash2,
  ClipboardList,
  MailCheck,
  MailClock,
  MailWarning,
  Ticket,
  UserCheck,
  Users,
  type LucideIcon,
} from "lucide-react";
import type {
  AttendanceAnalyticsResponse,
  OverviewAnalyticsResponse,
} from "@/lib/api/contracts";

export type MetricValue = number | null | undefined;

export type MetricDescriptor = {
  key: string;
  label: string;
  value: MetricValue;
  description: string;
  format?: "count" | "percentage";
  icon?: LucideIcon;
  tone?: "default" | "success" | "warning" | "destructive";
};

export type MetricGroupDescriptor = {
  key: string;
  title: string;
  description: string;
  metrics: MetricDescriptor[];
};

function count(value: MetricValue): string {
  return typeof value === "number" ? value.toLocaleString() : "—";
}

function percentage(value: MetricValue): string {
  return typeof value === "number"
    ? `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}%`
    : "—";
}

export function formatMetric(metric: MetricDescriptor): string {
  return metric.format === "percentage" ? percentage(metric.value) : count(metric.value);
}

export function buildMetricGroups(
  overview?: OverviewAnalyticsResponse | null,
  attendance?: AttendanceAnalyticsResponse | null,
): MetricGroupDescriptor[] {
  return [
    {
      key: "registrations",
      title: "Registrations",
      description: "All-time registration counts reported by the backend.",
      metrics: [
        {
          key: "total_registrations",
          label: "Total registrations",
          value: overview?.total_registrations,
          description: "All registrations for this event, regardless of status.",
          icon: ClipboardList,
        },
        {
          key: "confirmed_registrations",
          label: "Confirmed registrations",
          value: overview?.confirmed_registrations,
          description:
            "Backend-defined as total registrations minus cancellations; includes checked-in registrations.",
          icon: CheckCircle2,
          tone: "success",
        },
        {
          key: "declined_rsvps",
          label: "Declined RSVPs",
          value: overview?.declined_rsvps,
          description:
            "Distinct declined form submissions recorded with the ignored_declined webhook outcome; separate from cancellations.",
          icon: CalendarX2,
        },
        {
          key: "cancelled_registrations",
          label: "Cancelled registrations",
          value: overview?.cancelled_registrations,
          description: "Registrations with status cancelled.",
          icon: CircleSlash2,
          tone: "destructive",
        },
      ],
    },
    {
      key: "attendance",
      title: "Attendance",
      description: "Registration-status counts and the backend-calculated attendance rate.",
      metrics: [
        {
          key: "checked_in_attendees",
          label: "Checked-in attendees",
          value: overview?.checked_in_attendees,
          description: "Registrations with status checked_in.",
          icon: UserCheck,
          tone: "success",
        },
        {
          key: "not_checked_in_attendees",
          label: "Not yet checked in",
          value: overview?.not_checked_in_attendees,
          description: "Confirmed registrations minus checked-in registrations, as calculated by the backend.",
          icon: Users,
        },
        {
          key: "attendance_percentage",
          label: "Attendance percentage",
          value: attendance?.attendance_percentage,
          description:
            "Checked-in registrations divided by non-cancelled registrations, rounded to two decimals by the backend.",
          format: "percentage",
          icon: CalendarCheck2,
        },
      ],
    },
    {
      key: "tickets",
      title: "Tickets",
      description: "Ticket status counts. The analytics endpoint does not expose an issued-total metric.",
      metrics: [
        {
          key: "active_tickets",
          label: "Active tickets",
          value: overview?.active_tickets,
          description: "Tickets with status active; this is not the number of tickets issued.",
          icon: Ticket,
          tone: "success",
        },
        {
          key: "used_tickets",
          label: "Used tickets",
          value: overview?.used_tickets,
          description: "Tickets with status used.",
          icon: Ticket,
        },
        {
          key: "revoked_tickets",
          label: "Revoked tickets",
          value: overview?.revoked_tickets,
          description: "Tickets with status revoked.",
          icon: Ticket,
          tone: "destructive",
        },
        {
          key: "expired_tickets",
          label: "Expired tickets",
          value: overview?.expired_tickets,
          description: "Tickets with status expired; not derived from expiry timestamps.",
          icon: Ticket,
          tone: "warning",
        },
      ],
    },
    {
      key: "email-deliveries",
      title: "Email deliveries",
      description: "Delivery-job status counts. Sent jobs are not pending deliveries.",
      metrics: [
        {
          key: "pending_email_deliveries",
          label: "Pending deliveries",
          value: overview?.pending_email_deliveries,
          description: "Delivery rows with status pending.",
          icon: MailClock,
          tone: "warning",
        },
        {
          key: "sent_email_deliveries",
          label: "Sent deliveries",
          value: overview?.sent_email_deliveries,
          description: "Delivery rows with status sent.",
          icon: MailCheck,
          tone: "success",
        },
        {
          key: "failed_email_deliveries",
          label: "Failed deliveries",
          value: overview?.failed_email_deliveries,
          description: "Delivery rows with status failed.",
          icon: MailWarning,
          tone: "destructive",
        },
        {
          key: "dead_letter_email_deliveries",
          label: "Dead-letter deliveries",
          value: overview?.dead_letter_email_deliveries,
          description: "Delivery rows with status dead_letter.",
          icon: MailWarning,
          tone: "destructive",
        },
      ],
    },
  ];
}
