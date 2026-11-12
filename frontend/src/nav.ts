// The 22 dashboard pages from docs/SPEC.md §13, grouped for the sidebar.
//
// `milestone` is the milestone in which a page gets built. Pages up to BUILT_MILESTONE exist
// today; every other page renders an honest "Coming in M<n>" placeholder with no data.
// NOTE: the M2-M8 assignment below is provisional — adjust it here if the build plan differs.

import {
  Activity,
  Bot,
  Brain,
  Building2,
  ChartColumn,
  Cpu,
  DatabaseBackup,
  FileText,
  House,
  IdCard,
  LayoutDashboard,
  ListChecks,
  Map as MapIcon,
  MessagesSquare,
  Network,
  Package,
  Plug,
  Radio,
  Settings,
  ShieldCheck,
  ShoppingCart,
  Store,
  type LucideIcon,
} from "lucide-react";

export interface PageDef {
  id: string;
  path: string;
  label: string;
  icon: LucideIcon;
  milestone: number;
  /** What the page will do once built (from the spec). */
  blurb: string;
}

export interface NavGroup {
  label: string;
  pages: PageDef[];
}

export const NAV_GROUPS: NavGroup[] = [
  {
    label: "Village",
    pages: [
      { id: "overview", path: "/", label: "Village Overview", icon: LayoutDashboard, milestone: 1, blurb: "Your village at a glance." },
      { id: "map", path: "/map", label: "Interactive Village Map", icon: MapIcon, milestone: 5, blurb: "A clickable map of the village: Upazila buildings, Union offices, Wards and the agents working in them." },
    ],
  },
  {
    label: "Administration",
    pages: [
      { id: "upazilas", path: "/upazilas", label: "Upazila Management", icon: Building2, milestone: 2, blurb: "Create and manage Upazilas, and generate a standard structure from a template." },
      { id: "unions", path: "/unions", label: "Union Management", icon: Network, milestone: 2, blurb: "Manage the Unions inside each Upazila." },
      { id: "wards", path: "/wards", label: "Ward & Office Management", icon: House, milestone: 2, blurb: "Manage Wards and the Office that belongs to each one." },
    ],
  },
  {
    label: "Agents",
    pages: [
      { id: "agents", path: "/agents", label: "Agent Management", icon: Bot, milestone: 3, blurb: "Create agents from templates, assign them to offices, and enable, pause or disable them." },
      { id: "agent-profile", path: "/agents/profile", label: "Agent Profile", icon: IdCard, milestone: 3, blurb: "One agent's role, instructions, tools, permissions and task history." },
      { id: "agent-chat", path: "/chat", label: "Agent Chat", icon: MessagesSquare, milestone: 3, blurb: "Talk to an agent directly." },
    ],
  },
  {
    label: "Operations",
    pages: [
      { id: "tasks", path: "/tasks", label: "Task Center", icon: ListChecks, milestone: 4, blurb: "Create, delegate and follow tasks through the Central Manager." },
      { id: "approvals", path: "/approvals", label: "Approval Center", icon: ShieldCheck, milestone: 4, blurb: "Approve or reject sensitive actions that agents request." },
      { id: "communication", path: "/communication", label: "Communication History", icon: Radio, milestone: 4, blurb: "The structured messages agents send to each other." },
    ],
  },
  {
    label: "Knowledge",
    pages: [
      { id: "memory", path: "/memory", label: "Memory & Knowledge Center", icon: Brain, milestone: 6, blurb: "Review and delete Village, Upazila and Agent memories." },
      { id: "documents", path: "/documents", label: "Document Manager", icon: FileText, milestone: 6, blurb: "Upload, organise and search local documents." },
    ],
  },
  {
    label: "Commerce",
    pages: [
      { id: "commerce", path: "/commerce", label: "Commerce Dashboard", icon: Store, milestone: 7, blurb: "Sales, orders and stock at a glance." },
      { id: "products", path: "/products", label: "Product & Inventory Management", icon: Package, milestone: 7, blurb: "Products, variants, prices and stock history." },
      { id: "orders", path: "/orders", label: "Order Management", icon: ShoppingCart, milestone: 7, blurb: "Orders, deliveries and payment records." },
    ],
  },
  {
    label: "Insights",
    pages: [
      { id: "reports", path: "/reports", label: "Reports & Analytics", icon: ChartColumn, milestone: 8, blurb: "Generated reports and activity analytics." },
    ],
  },
  {
    label: "System",
    pages: [
      { id: "integrations", path: "/integrations", label: "Integration Settings", icon: Plug, milestone: 7, blurb: "Connector configuration and status (for example Messenger)." },
      { id: "ai-models", path: "/ai-models", label: "AI Model Settings", icon: Cpu, milestone: 3, blurb: "Choose and test the AI provider: Demo, Ollama or Anthropic." },
      { id: "settings", path: "/settings", label: "Application Settings", icon: Settings, milestone: 8, blurb: "Village name, timezone, password and other application settings." },
      { id: "backup", path: "/backup", label: "Backup & Restore", icon: DatabaseBackup, milestone: 8, blurb: "Create and restore backups of the village." },
      { id: "health", path: "/health", label: "System Health & Logs", icon: Activity, milestone: 8, blurb: "Server health, background jobs and logs." },
    ],
  },
];

export const ALL_PAGES: PageDef[] = NAV_GROUPS.flatMap((group) => group.pages);

/** The last milestone whose pages are really built. */
export const BUILT_MILESTONE = 2;

export function isBuilt(page: PageDef): boolean {
  return page.milestone <= BUILT_MILESTONE;
}

export function findPage(pathname: string): PageDef | undefined {
  return ALL_PAGES.find((page) => page.path === pathname);
}
