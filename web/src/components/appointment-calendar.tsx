import { useState } from "react";
import type { CalendarStatus, CarePlan } from "@/lib/care-api";
import { datedVisits, sameDay } from "@/lib/plan-schedule";

export function AppointmentCalendar({
  appointments,
  calendar,
  syncing,
  onConnect,
  onDisconnect,
  onSync,
}: {
  appointments: CarePlan["appointments"];
  calendar: (CalendarStatus & { note: string }) | null;
  syncing: boolean;
  onConnect: () => void;
  onDisconnect: () => void;
  onSync: () => void;
}) {
  const visits = datedVisits(appointments);
  const first = visits[0]?.date ?? new Date();
  const [cursor, setCursor] = useState(new Date(first.getFullYear(), first.getMonth(), 1));
  const monthStart = new Date(cursor.getFullYear(), cursor.getMonth(), 1);
  const gridStart = new Date(monthStart);
  gridStart.setDate(1 - monthStart.getDay());
  const days = Array.from({ length: 42 }, (_, index) => {
    const day = new Date(gridStart);
    day.setDate(gridStart.getDate() + index);
    return day;
  });
  const weeks = Array.from({ length: 6 }, (_, index) =>
    days.slice(index * 7, index * 7 + 7),
  ).filter((week) => week.some((day) => day.getMonth() === monthStart.getMonth()));
  const title = monthStart.toLocaleDateString("en-US", { month: "long", year: "numeric" });
  const connected = Boolean(calendar?.connected);
  return (
    <section className="h-full rounded-2xl border bg-card p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-display text-2xl">Appointments</h2>
          <p className="text-sm text-muted-foreground">{title}</p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <button
            type="button"
            onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() - 1, 1))}
            className="rounded-full border px-2.5 py-1 text-xs"
          >
            Previous
          </button>
          <button
            type="button"
            onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1))}
            className="rounded-full border px-2.5 py-1 text-xs"
          >
            Next
          </button>
          {connected ? (
            <>
              <button
                type="button"
                onClick={onSync}
                disabled={syncing}
                className="rounded-full bg-primary px-3 py-1 text-xs font-semibold text-primary-foreground disabled:opacity-60"
              >
                {syncing ? "Sending…" : "Send to my phone"}
              </button>
              <button
                type="button"
                onClick={onDisconnect}
                className="rounded-full border px-2.5 py-1 text-xs"
              >
                Disconnect
              </button>
            </>
          ) : (
            <button
              type="button"
              onClick={onConnect}
              className="rounded-full bg-primary px-3 py-1 text-xs font-semibold text-primary-foreground"
            >
              Connect Google Calendar
            </button>
          )}
        </div>
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        {connected
          ? `Connected${calendar?.email ? ` as ${calendar.email}` : ""}. Send these visits to Google Calendar for a reminder on your phone a day before and an hour before.`
          : "These visits stay on this page until you connect Google Calendar. After you connect, CareBridge can add them so your phone reminds you."}
      </p>
      {calendar?.note && <p className="mt-2 text-sm text-warning-foreground">{calendar.note}</p>}
      {visits.length === 0 && (
        <p className="mt-4 text-sm text-muted-foreground">
          No follow-up date was written in this report.
        </p>
      )}
      <div className="mt-3 overflow-hidden rounded-xl border bg-card">
        <div className="grid grid-cols-7 border-b bg-muted/70 text-center text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((name) => (
            <div key={name} className="px-1 py-1">
              {name}
            </div>
          ))}
        </div>
        <div className="grid grid-cols-7">
          {weeks.flat().map((day) => {
            const inMonth = day.getMonth() === monthStart.getMonth();
            const events = visits.filter((visit) => sameDay(visit.date, day));
            return (
              <div
                key={day.toISOString()}
                className={`min-h-12 border-b border-r px-1 py-0.5 ${inMonth ? "bg-card" : "bg-muted/40 text-muted-foreground"} ${events.length > 0 ? "bg-secondary/60" : ""}`}
              >
                <p
                  className={`text-[10px] leading-none ${events.length > 0 ? "font-semibold text-primary" : ""}`}
                >
                  {day.getDate()}
                </p>
                <ul className="mt-0.5 space-y-0.5">
                  {events.map((visit) => (
                    <li
                      key={`${visit.title}-${visit.time}`}
                      className="rounded bg-primary px-1 py-0.5 text-primary-foreground"
                    >
                      <p className="text-[9px] font-semibold leading-tight">
                        {visit.time} {visit.title}
                      </p>
                      {visit.who && (
                        <p className="text-[9px] leading-tight opacity-90">{visit.who}</p>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
