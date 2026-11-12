import { Link, Navigate, Route, Routes } from "react-router";

import AppShell from "./components/AppShell";
import { Button, FullScreenMessage } from "./components/ui";
import { ALL_PAGES, isBuilt } from "./nav";
import ComingSoon from "./pages/ComingSoon";
import Login from "./pages/Login";
import Overview from "./pages/Overview";
import SetupWizard from "./pages/SetupWizard";
import Unions from "./pages/Unions";
import Upazilas from "./pages/Upazilas";
import Wards from "./pages/Wards";
import { useSession } from "./session";

function NotFound() {
  return (
    <section className="panel mx-auto mt-6 max-w-xl px-8 py-12 text-center">
      <p className="eyebrow">404</p>
      <h1 className="mt-2 text-2xl font-semibold text-mist-50">This path leads nowhere</h1>
      <Link to="/" className="mt-6 inline-block text-sm font-medium text-lantern-300 underline-offset-4 hover:underline">
        Back to Village Overview
      </Link>
    </section>
  );
}

/**
 * Routing rule: setup not done → /setup; not logged in → /login; otherwise the app shell.
 */
export default function App() {
  const { state, refresh } = useSession();

  if (state.phase === "loading") {
    return <FullScreenMessage title="Opening the village gates…" />;
  }
  if (state.phase === "error") {
    return (
      <FullScreenMessage title="Cannot load the Village">
        <p role="alert" className="text-sm text-clay-300">
          {state.message}
        </p>
        <Button onClick={() => void refresh()}>Try again</Button>
      </FullScreenMessage>
    );
  }

  const needsSetup = state.phase === "needs-setup";
  const authed = state.phase === "authed" ? state : null;
  const gate = needsSetup ? "/setup" : "/login";

  return (
    <Routes>
      <Route path="/setup" element={needsSetup ? <SetupWizard onComplete={refresh} /> : <Navigate to="/" replace />} />
      <Route
        path="/login"
        element={needsSetup ? <Navigate to="/setup" replace /> : authed ? <Navigate to="/" replace /> : <Login onLoggedIn={refresh} />}
      />
      <Route element={authed ? <AppShell user={authed.user} village={authed.village} /> : <Navigate to={gate} replace />}>
        <Route index element={authed ? <Overview village={authed.village} /> : null} />
        <Route path="/upazilas" element={<Upazilas />} />
        <Route path="/unions" element={<Unions />} />
        <Route path="/wards" element={<Wards />} />
        {ALL_PAGES.filter((page) => !isBuilt(page)).map((page) => (
          <Route key={page.id} path={page.path} element={<ComingSoon page={page} />} />
        ))}
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
