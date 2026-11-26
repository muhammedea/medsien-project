import { useEffect, useState } from "react";

// Placeholder. The server management dashboard and run pages come in a later step.
export default function App() {
  const [health, setHealth] = useState("checking…");

  useEffect(() => {
    fetch("/api/health")
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((d) => setHealth(`ok (engine ${d.engine_version})`))
      .catch(() => setHealth("unreachable"));
  }, []);

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", padding: "2rem" }}>
      <h1>Load Balancer Simulation</h1>
      <p>Dashboard not implemented yet.</p>
      <p>Backend: {health}</p>
    </main>
  );
}
