// Which robot an agent is drawn as. ONE table: agent template → robot role (docs/SPEC.md §6).
// A backend test reads this file and fails when a template of the catalogue is missing here.

export type RobotRole = "manager" | "pion" | "doctor" | "technician" | "researcher" | "sales" | "default";

export const TEMPLATE_ROBOTS: Record<string, RobotRole> = {
  village_manager: "manager",
  office_manager: "manager",
  business_manager: "manager",
  project_manager: "manager",
  pion_helper: "pion",
  doctor_wellness: "doctor",
  repair_technician: "technician",
  technical_support: "technician",
  research_librarian: "researcher",
  study_assistant: "researcher",
  teacher_tutor: "researcher",
  daily_reporter: "researcher",
  sales_assistant: "sales",
  customer_support: "sales",
  accountant: "sales",
};

/** What each robot wears — used for the accessible description. */
export const ROBOT_OUTFITS: Record<RobotRole, string> = {
  manager: "formal outfit with an ID badge",
  pion: "helper uniform with a cap",
  doctor: "medical coat — assistant only, not a doctor",
  technician: "maintenance uniform with a tool belt",
  researcher: "holding a book",
  sales: "business suit with a briefcase",
  default: "plain uniform",
};

/** The robot for an agent made from `templateKey`; the plain robot when there is no template. */
export function robotRoleFor(templateKey: string | null | undefined): RobotRole {
  return (templateKey && TEMPLATE_ROBOTS[templateKey]) || "default";
}

export type Activity = "working" | "idle" | "waiting" | "offline";

export const ACTIVITY_TEXT: Record<Activity, string> = {
  working: "working",
  idle: "idle",
  waiting: "waiting for your approval",
  offline: "offline",
};
